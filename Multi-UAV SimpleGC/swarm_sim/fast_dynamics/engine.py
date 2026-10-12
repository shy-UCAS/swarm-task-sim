"""Integer-microsecond clock and atomic, vectorized world updates."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

import numpy as np

from .contracts import FastDynamicsConfig, PlantState, StateView, _integer, _positive
from .controllers import VelocityController
from .plants import PointMassJerkPlant, dense_state


def seconds_to_us(seconds: float) -> int:
    """Convert a specified duration once; never accumulate floating point time."""
    _positive("seconds", seconds, zero=True)
    microseconds = Decimal(str(seconds)) * 1_000_000
    if microseconds != microseconds.to_integral_value():
        raise ValueError("duration must be exactly representable in integer microseconds")
    return int(microseconds)


def output_frame_count(duration_us: int, period_us: int = 100_000) -> int:
    _integer("duration_us", duration_us, zero=True)
    _integer("period_us", period_us)
    return (int(duration_us) + int(period_us) - 1) // int(period_us)


def integer_output_grid(duration_us: int, period_us: int = 100_000) -> np.ndarray:
    return np.arange(output_frame_count(duration_us, period_us), dtype=np.int64) * int(period_us)


@dataclass(frozen=True)
class StepSegment:
    start_us: int
    end_us: int
    state: PlantState
    jerk: np.ndarray

    def at(self, time_us: int) -> PlantState:
        _integer("time_us", time_us, zero=True)
        if not self.start_us <= time_us <= self.end_us:
            raise ValueError("requested sample lies outside the integration step")
        return dense_state(self.state, self.jerk, (time_us - self.start_us) / 1_000_000.0)


class SynchronousEngine:
    """All agents read one immutable snapshot, then commit one next state.

    ``samples`` contains exactly the fixed 10 Hz grid in ``[0, time_us)``.
    Samples inside a physics step use its polynomial, not a linear chord.
    The actual end time is always ``time_us``, never the final sample time.
    """

    def __init__(self, config: FastDynamicsConfig, initial_state: PlantState) -> None:
        self.config = config
        self.state = initial_state
        self.time_us = 0
        self.plant = PointMassJerkPlant(config.vehicle_profile)
        self.controller = VelocityController(config.vehicle_profile, config.controller)
        if self.controller.output_type != self.plant.input_type:
            raise ValueError("controller and plant control capabilities do not match")
        self.last_jerk: np.ndarray | None = None
        self.last_segment: StepSegment | None = None
        self.samples: list[StateView] = []
        self._next_output_us = 0

    def step(self, desired_velocity: np.ndarray | Callable[[int, PlantState], np.ndarray],
             dt_us: int | None = None) -> PlantState:
        duration_us = self.config.engine.step_us if dt_us is None else dt_us
        _integer("dt_us", duration_us)
        if duration_us > self.config.engine.step_us:
            raise ValueError("dt_us cannot exceed the configured integration step")
        snapshot = self.state
        desired = desired_velocity(self.time_us, snapshot) if callable(desired_velocity) else desired_velocity
        request = self.controller.command(snapshot, desired)
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

    def truncate_last_step(self, end_us: int) -> PlantState:
        """Commit only the prefix of the last step at an actual dense event.

        The M1 controller/plant have no hidden integrator or stochastic state.
        Its exact polynomial can therefore be cut at a phase boundary before
        obtaining the next common control request. Already exported samples at
        or after the new endpoint are removed to preserve ``[0, end_us)``.
        No older step can be rewound with this operation.
        """
        _integer("end_us", end_us, zero=True)
        segment = self.last_segment
        if segment is None:
            raise ValueError("there is no integration step to truncate")
        if not segment.start_us <= end_us <= segment.end_us:
            raise ValueError("end_us must lie within the last integration step")
        self.state = segment.at(end_us)
        self.time_us = int(end_us)
        self.last_segment = StepSegment(segment.start_us, int(end_us), segment.state, segment.jerk)
        self.samples[:] = [sample for sample in self.samples if sample.t_us < end_us]
        period = self.config.engine.output_period_us
        self._next_output_us = output_frame_count(end_us, period) * period
        return self.state
