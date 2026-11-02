"""执行内核（V8-08 第 3 部分）：在冻结引擎上留出扰动入口与每机参数接口。

InjectableEngine.step 逐行照抄冻结 SynchronousEngine.step（swarm_sim/fast_dynamics/engine.py），
只在控制器求出加速度请求之后插入扰动；扰动为 None 时与冻结引擎逐位相同。
"""
import dataclasses
import math

import numpy as np

from swarm_sim.fast_dynamics.contracts import AccelerationENU, StateView, _integer
from swarm_sim.fast_dynamics.engine import StepSegment, SynchronousEngine
from swarm_sim.fast_dynamics.reference_r3 import candidate_config

VEHICLE_KEYS = ("response_time_s", "max_accel_xy_m_s2", "max_jerk_m_s3")
CONTROLLER_KEYS = ("velocity_response_time_s",)


class InjectableEngine(SynchronousEngine):
    """disturbance(tau_us, snapshot) 返回与加速度请求同形的附加加速度；tau_us 为统一时钟时刻。"""

    def __init__(self, config, initial_state, disturbance=None, tau_offset_us=0):
        super().__init__(config, initial_state)
        self.disturbance = disturbance
        self.tau_offset_us = tau_offset_us

    def step(self, desired_velocity, dt_us=None):
        duration_us = self.config.engine.step_us if dt_us is None else dt_us
        _integer("dt_us", duration_us)
        if duration_us > self.config.engine.step_us:
            raise ValueError("dt_us cannot exceed the configured integration step")
        snapshot = self.state
        desired = desired_velocity(self.time_us, snapshot) if callable(desired_velocity) else desired_velocity
        request = self.controller.command(snapshot, desired)
        if self.disturbance is not None:
            extra = np.asarray(self.disturbance(self.tau_offset_us + self.time_us, snapshot),
                               float).reshape(request.values.shape)
            request = AccelerationENU(request.values + extra)
        next_state = self.plant.step(snapshot, request, duration_us / 1_000_000.0)
        end_us = self.time_us + duration_us
        segment = StepSegment(self.time_us, end_us, snapshot, self.plant.last_jerk)
        while self._next_output_us < end_us:
            self.samples.append(StateView.from_state(self._next_output_us, segment.at(self._next_output_us)))
            self._next_output_us += self.config.engine.output_period_us
        # Commit only after all inputs and the entire batch have been evaluated.
        self.state = next_state
        self.time_us = end_us
        self.last_jerk = self.plant.last_jerk
        self.last_segment = segment
        return self.state


def member_config(overrides=None):
    """每机参数：只允许覆盖 vehicle_profile 的三个响应参数与 controller 的速度响应时间。"""
    base = candidate_config()
    if not overrides:
        return base
    unknown = set(overrides) - set(VEHICLE_KEYS) - set(CONTROLLER_KEYS)
    if unknown:
        raise ValueError(f"不允许覆盖的参数 {sorted(unknown)}")
    for key, value in overrides.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"参数 {key} 须为正的有限数，实际 {value!r}")
    vehicle = {k: float(v) for k, v in overrides.items() if k in VEHICLE_KEYS}
    controller = {k: float(v) for k, v in overrides.items() if k in CONTROLLER_KEYS}
    return dataclasses.replace(
        base,
        vehicle_profile=dataclasses.replace(base.vehicle_profile, **vehicle),
        controller=dataclasses.replace(base.controller, **controller))
