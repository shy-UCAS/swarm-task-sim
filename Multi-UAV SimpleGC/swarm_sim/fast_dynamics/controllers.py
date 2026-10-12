"""M1 velocity response; the controller consumes the common truth snapshot."""
from __future__ import annotations

import numpy as np

from .contracts import AccelerationENU, ControllerConfig, PlantState, VehicleProfile, _array3
from .plants import project_acceleration


class VelocityController:
    output_type = "AccelerationENU"

    def __init__(self, profile: VehicleProfile | None = None,
                 config: ControllerConfig | None = None) -> None:
        self.profile = profile or VehicleProfile()
        self.config = config or ControllerConfig()

    def command(self, state: PlantState, desired_velocity: np.ndarray) -> AccelerationENU:
        desired = _array3(desired_velocity, "desired_velocity")
        if desired.shape != state.v.shape:
            raise ValueError("desired velocity and state shapes must match")
        # Reference speed clipping is allowed; actual velocity is never clipped.
        desired = desired.copy()
        speed = np.linalg.norm(desired[:, :2], axis=1)
        desired[:, :2] *= np.minimum(1.0, self.profile.max_speed_xy_m_s /
                                     np.maximum(speed, 1e-12))[:, None]
        desired[:, 2] = np.clip(desired[:, 2], -self.profile.max_speed_down_m_s,
                                self.profile.max_speed_up_m_s)
        request = (desired - state.v) / self.config.velocity_response_time_s
        return AccelerationENU(project_acceleration(request, self.profile))
