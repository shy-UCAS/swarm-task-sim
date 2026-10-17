"""Versioned, SI/ENU contracts for the deterministic airborne M1 backend.

Only net translational acceleration is implemented. Names of future control
types describe unsupported capabilities; they are never silently converted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from enum import Enum
import math
from numbers import Integral, Real
from typing import Any, Mapping

import numpy as np

ENGINE_VERSION = "0.1.0"
PROTOCOL_VERSION = "fast_dynamics_v1"
PLANT_VERSION = "point_mass_jerk_v1"
CONTROLLER_VERSION = "velocity_response_v1"
OBSERVER_VERSION = "ideal_kinematics_v1"
INTEGRATOR_VERSION = "constant_jerk_v1"


class ControlType(str, Enum):
    ACCELERATION_ENU = "AccelerationENU"
    BODY_WRENCH = "BodyWrench"
    MOTOR_COMMAND = "MotorCommand"


def _positive(name: str, value: Any, *, zero: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    if (zero and value < 0) or (not zero and value <= 0):
        raise ValueError(f"{name} must be {'nonnegative' if zero else 'positive'}")


def _integer(name: str, value: Any, *, zero: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    _positive(name, value, zero=zero)


def _array3(value: Any, name: str) -> np.ndarray:
    result = np.array(value, dtype=np.float64, copy=True)
    if result.ndim != 2 or result.shape[1] != 3 or result.shape[0] < 1:
        raise ValueError(f"{name} must have shape (N, 3), with N >= 1")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain only finite values")
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class PlantState:
    p: np.ndarray
    v: np.ndarray
    a: np.ndarray

    def __post_init__(self) -> None:
        for name in ("p", "v", "a"):
            object.__setattr__(self, name, _array3(getattr(self, name), name))
        if self.p.shape != self.v.shape or self.p.shape != self.a.shape:
            raise ValueError("position, velocity and acceleration shapes must match")

    @property
    def num_agents(self) -> int:
        return self.p.shape[0]

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name).tolist() for name in ("p", "v", "a")}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PlantState":
        if set(value) != {"p", "v", "a"}:
            raise ValueError("plant state must contain exactly p, v, a")
        return cls(**value)


@dataclass(frozen=True)
class AccelerationENU:
    values: np.ndarray
    control_type: ControlType = field(default=ControlType.ACCELERATION_ENU, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _array3(self.values, "acceleration_request"))


@dataclass(frozen=True)
class StateView:
    t_us: int
    p: np.ndarray
    v: np.ndarray
    a: np.ndarray
    source: str = "engine_truth"
    coordinate_frame: str = "ENU"

    @classmethod
    def from_state(cls, t_us: int, state: PlantState) -> "StateView":
        _integer("t_us", t_us, zero=True)
        return cls(t_us=t_us, p=state.p, v=state.v, a=state.a)

    @property
    def t_s(self) -> float:
        return self.t_us / 1_000_000.0


@dataclass(frozen=True)
class EngineConfig:
    step_us: int = 20_000
    output_period_us: int = 100_000

    def __post_init__(self) -> None:
        _integer("step_us", self.step_us)
        _integer("output_period_us", self.output_period_us)
        if self.output_period_us != 100_000:
            raise ValueError("fast_dynamics_v1 requires 10 Hz output (100000 us)")
        if self.step_us > self.output_period_us:
            raise ValueError("step_us must not exceed output_period_us")


@dataclass(frozen=True)
class VehicleProfile:
    max_speed_xy_m_s: float = 12.0
    max_speed_up_m_s: float = 4.0
    max_speed_down_m_s: float = 3.0
    max_accel_xy_m_s2: float = 3.0
    max_accel_up_m_s2: float = 2.0
    max_accel_down_m_s2: float = 2.0
    max_jerk_m_s3: float = 8.0
    response_time_s: float = 0.25

    def __post_init__(self) -> None:
        for item in fields(self):
            _positive(item.name, getattr(self, item.name))


@dataclass(frozen=True)
class ControllerConfig:
    velocity_response_time_s: float = 0.8
    state_source: str = "truth"
    control_type: str = "AccelerationENU"

    def __post_init__(self) -> None:
        _positive("velocity_response_time_s", self.velocity_response_time_s)
        if self.state_source != "truth":
            raise ValueError("M1 supports only controller state_source=truth")
        if self.control_type != ControlType.ACCELERATION_ENU.value:
            raise ValueError("point_mass_jerk_v1 supports only AccelerationENU")


@dataclass(frozen=True)
class ObservationConfig:
    mode: str = "ideal"

    def __post_init__(self) -> None:
        if self.mode != "ideal":
            raise ValueError("M1 supports only ideal observations; noisy models are not implemented")


@dataclass(frozen=True)
class EnvironmentConfig:
    mode: str = "zero_disturbance"

    def __post_init__(self) -> None:
        if self.mode != "zero_disturbance":
            raise ValueError("M1 supports only zero_disturbance environment")


@dataclass(frozen=True)
class ExecutionConfig:
    lifecycle_scope: str = "airborne_mission"
    max_duration_s: float = 600.0
    arrival_radius_m: float = 1.0
    arrival_speed_m_s: float = 0.15
    terminal_hold_s: float = 0.0

    def __post_init__(self) -> None:
        if self.lifecycle_scope != "airborne_mission":
            raise ValueError("M1 supports only lifecycle_scope=airborne_mission")
        for name in ("max_duration_s", "arrival_radius_m", "arrival_speed_m_s"):
            _positive(name, getattr(self, name))
        _positive("terminal_hold_s", self.terminal_hold_s, zero=True)


@dataclass(frozen=True)
class QualityConfig:
    max_speed_tolerance_m_s: float = 0.75
    min_separation_m: float = 2.0

    def __post_init__(self) -> None:
        for item in fields(self):
            _positive(item.name, getattr(self, item.name), zero=True)


_CONFIG_GROUPS = {
    "engine": EngineConfig,
    "vehicle_profile": VehicleProfile,
    "controller": ControllerConfig,
    "observation": ObservationConfig,
    "environment": EnvironmentConfig,
    "execution": ExecutionConfig,
    "quality": QualityConfig,
}


@dataclass(frozen=True)
class FastDynamicsConfig:
    engine: EngineConfig = field(default_factory=EngineConfig)
    vehicle_profile: VehicleProfile = field(default_factory=VehicleProfile)
    controller: ControllerConfig = field(default_factory=ControllerConfig)
    observation: ObservationConfig = field(default_factory=ObservationConfig)
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)

    def __post_init__(self) -> None:
        for name, group_type in _CONFIG_GROUPS.items():
            if not isinstance(getattr(self, name), group_type):
                raise ValueError(f"{name} must be a {group_type.__name__}")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FastDynamicsConfig":
        if not isinstance(value, Mapping):
            raise ValueError("configuration must be an object")
        unknown = set(value) - set(_CONFIG_GROUPS)
        if unknown:
            raise ValueError(f"unknown configuration groups: {sorted(unknown)}")
        groups = {}
        for name, group_type in _CONFIG_GROUPS.items():
            group = value.get(name, {})
            if not isinstance(group, Mapping):
                raise ValueError(f"{name} must be an object")
            unknown = set(group) - {item.name for item in fields(group_type)}
            if unknown:
                raise ValueError(f"unknown {name} fields: {sorted(unknown)}")
            groups[name] = group_type(**group)
        return cls(**groups)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def capabilities() -> dict[str, Any]:
    """No false attitude, IMU, firmware or takeoff/landing evidence."""
    return {
        "control_types": [ControlType.ACCELERATION_ENU.value],
        "state_fields": ["position_enu_m", "velocity_enu_m_s", "net_acceleration_enu_m_s2"],
        "unsupported_state_fields": ["attitude", "angular_velocity", "specific_force", "motor_state"],
        "controller_state_source": "truth",
        "observation_modes": ["ideal"],
        "environment_modes": ["zero_disturbance"],
        "lifecycle_scope": "airborne_mission",
        "numerical_calibration": "uncalibrated",
    }


def model_versions() -> dict[str, str]:
    return {"engine": ENGINE_VERSION, "plant": PLANT_VERSION,
            "controller": CONTROLLER_VERSION, "observer": OBSERVER_VERSION,
            "integrator": INTEGRATOR_VERSION}


M2_ENGINE_VERSION = "0.2.0"
M2_BEHAVIOR_VERSION = "m2_continuous_v2"
M2_CONFIG_SCHEMA_VERSION = "fast_dynamics_config_v2"


@dataclass(frozen=True)
class ReferenceConfig:
    policy: str = "continuous_route_v2"
    corner_cut_max_m: float = 0.25
    corner_leg_fraction: float = 0.1
    tracking_tube_m: float = 0.5
    position_gain_per_s: float = 1.25
    velocity_damping: float = 0.25
    preview_time_s: float = 0.2

    def __post_init__(self) -> None:
        if self.policy not in ("continuous_route_v2", "continuous_route_v3"):
            raise ValueError("unsupported continuous reference policy")
        for name, upper in (("corner_cut_max_m", .25), ("corner_leg_fraction", .1),
                            ("tracking_tube_m", .5), ("preview_time_s", .2),
                            ("velocity_damping", 1.)):
            value = getattr(self, name)
            _positive(name, value, zero=name == "velocity_damping")
            if value > upper:
                raise ValueError(f"{name} must not exceed {upper}")
        _positive("position_gain_per_s", self.position_gain_per_s)


@dataclass(frozen=True)
class M2Config(FastDynamicsConfig):
    reference: ReferenceConfig = field(default_factory=ReferenceConfig)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.reference, ReferenceConfig):
            raise ValueError("reference must be a ReferenceConfig")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "M2Config":
        if not isinstance(value, Mapping):
            raise ValueError("configuration must be an object")
        extra = set(value) - (set(_CONFIG_GROUPS) | {"reference"})
        if extra:
            raise ValueError(f"unknown configuration groups: {sorted(extra)}")
        base = FastDynamicsConfig.from_dict({k: v for k, v in value.items() if k != "reference"})
        reference = value.get("reference", {})
        if not isinstance(reference, Mapping):
            raise ValueError("reference must be an object")
        extra = set(reference) - {item.name for item in fields(ReferenceConfig)}
        if extra:
            raise ValueError(f"unknown reference fields: {sorted(extra)}")
        return cls(**{name: getattr(base, name) for name in _CONFIG_GROUPS},
                   reference=ReferenceConfig(**reference))


def config_from_dict(value: Mapping[str, Any]) -> FastDynamicsConfig:
    """Execution may complete defaults; readers additionally require exact round trips."""
    return (M2Config if "reference" in value else FastDynamicsConfig).from_dict(value)


def model_versions_m2() -> dict[str, str]:
    return dict(model_versions(), engine=M2_ENGINE_VERSION,
                reference="continuous_route_v2", executor="airborne_multi_intent_m2")
