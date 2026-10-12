"""Bounded net acceleration with exact constant-jerk integration per step."""
from __future__ import annotations

import numpy as np

from .contracts import AccelerationENU, PlantState, VehicleProfile, _array3, _positive


def project_acceleration(values: np.ndarray, profile: VehicleProfile) -> np.ndarray:
    result = np.array(values, dtype=np.float64, copy=True)
    horizontal = np.linalg.norm(result[:, :2], axis=1)
    scale = np.minimum(1.0, profile.max_accel_xy_m_s2 / np.maximum(horizontal, 1e-12))
    result[:, :2] *= scale[:, None]
    result[:, 2] = np.clip(result[:, 2], -profile.max_accel_down_m_s2, profile.max_accel_up_m_s2)
    return result


def dense_state(state: PlantState, jerk: np.ndarray, dt_s: float) -> PlantState:
    """Evaluate the step polynomial, also usable for output/event boundaries."""
    _positive("dt_s", dt_s, zero=True)
    jerk = _array3(jerk, "jerk")
    if jerk.shape != state.p.shape:
        raise ValueError("jerk and state shapes must match")
    h = float(dt_s)
    return PlantState(state.p + state.v * h + state.a * h**2 / 2 + jerk * h**3 / 6,
                      state.v + state.a * h + jerk * h**2 / 2,
                      state.a + jerk * h)


class PointMassJerkPlant:
    """The feasible acceleration set is a horizontal disk × vertical interval.

    The end acceleration lies on the segment from the current feasible value to
    the projected request. Thus it, and the entire constant-jerk step, stay in
    the convex feasible set without any inconsistent velocity/position clip.
    """
    input_type = "AccelerationENU"

    def __init__(self, profile: VehicleProfile | None = None) -> None:
        self.profile = profile or VehicleProfile()
        self.last_jerk: np.ndarray | None = None

    def step(self, state: PlantState, acceleration_request: AccelerationENU | np.ndarray,
             dt_s: float) -> PlantState:
        _positive("dt_s", dt_s)
        if isinstance(acceleration_request, AccelerationENU):
            request = acceleration_request.values
        else:
            if hasattr(acceleration_request, "control_type"):
                raise ValueError("point_mass_jerk_v1 requires AccelerationENU")
            request = _array3(acceleration_request, "acceleration_request")
        if request.shape != state.p.shape:
            raise ValueError("request and state shapes must match")
        feasible = project_acceleration(state.a, self.profile)
        if not np.allclose(feasible, state.a, rtol=0, atol=1e-10):
            raise ValueError("initial acceleration exceeds vehicle capability")
        target = project_acceleration(request, self.profile)
        # dt > response time still may not overshoot the target acceleration.
        jerk = (target - state.a) / max(self.profile.response_time_s, float(dt_s))
        magnitude = np.linalg.norm(jerk, axis=1)
        scale = np.minimum(1.0, self.profile.max_jerk_m_s3 / np.maximum(magnitude, 1e-12))
        jerk *= scale[:, None]
        jerk.setflags(write=False)
        self.last_jerk = jerk
        return dense_state(state, jerk, dt_s)
