"""Explicit ideal kinematic observation projection for deterministic M1."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .contracts import ObservationConfig, PlantState, StateView, _integer


@dataclass(frozen=True)
class ObservationFrame:
    measurement_time_us: int
    delivery_time_us: int
    p: np.ndarray
    v: np.ndarray
    valid: np.ndarray
    source: str = "synthetic_observation"

    @property
    def t_us(self) -> int:
        return self.measurement_time_us


class IdealObserver:
    def __init__(self, config: ObservationConfig | None = None) -> None:
        self.config = config or ObservationConfig()

    def sample(self, state: PlantState | StateView, time_us: int | None = None) -> ObservationFrame:
        if isinstance(state, StateView):
            if time_us is not None and time_us != state.t_us:
                raise ValueError("time_us must match the state view measurement time")
            time_us = state.t_us
        if time_us is None:
            raise ValueError("a measurement time is required")
        _integer("time_us", time_us, zero=True)
        valid = np.ones(state.p.shape[0], dtype=bool)
        valid.setflags(write=False)
        return ObservationFrame(time_us, time_us, state.p, state.v, valid)
