"""Smooth velocity references and dense geometric events for the M1 executor."""

import math

import numpy as np
from numpy.polynomial import polynomial as poly


REFERENCE_VERSION = "endpoint_velocity_v1"


def endpoint_velocity(positions, targets, speed_m_s, response_time_s):
    """A smooth speed cap with asymptotic braking; never edits plant state.

    The braking horizon is derived from the velocity/acceleration response,
    rather than a second fitted position controller. All axes remain ENU.
    """
    delta = np.asarray(targets) - np.asarray(positions)
    distance = np.linalg.norm(delta, axis=1, keepdims=True)
    horizon = max(2.0, 2.0 * response_time_s)
    speed = speed_m_s * np.tanh(distance / (speed_m_s * horizon))
    return delta * np.divide(speed, distance, out=np.zeros_like(speed), where=distance > 0)


def _roots(coefficients, duration_s):
    coefficients = np.trim_zeros(np.asarray(coefficients), "b")
    if len(coefficients) < 2:
        return []
    # Bernstein coefficients bound the polynomial over this step. Most steps
    # are far from a boundary and need no eigenvalue/root calculation.
    degree = len(coefficients) - 1
    scaled = coefficients * duration_s ** np.arange(degree + 1)
    bernstein = [sum(scaled[j] * math.comb(k, j) / math.comb(degree, j)
                     for j in range(k + 1)) for k in range(degree + 1)]
    if min(bernstein) > 0 or max(bernstein) < 0:
        return []
    return sorted(float(r.real) for r in poly.polyroots(coefficients)
                  if abs(r.imag) < 1e-7 and 0 < r.real < duration_s)


def arrival_intervals(state, jerk, agent_index, target, radius_m, speed_m_s, duration_s):
    """Continuous intervals satisfying BOTH radius and speed on a cubic step.

    Roots of the squared distance/speed polynomials partition the step; this
    detects a short entry followed by an exit even when both endpoints fail.
    """
    i = agent_index
    position = np.stack((state.p[i] - target, state.v[i], state.a[i] / 2, jerk[i] / 6))
    velocity = np.stack((state.v[i], state.a[i], jerk[i] / 2))
    distance2, speed2 = np.zeros(7), np.zeros(5)
    for k in range(3):
        distance2 = poly.polyadd(distance2, poly.polymul(position[:, k], position[:, k]))
        speed2 = poly.polyadd(speed2, poly.polymul(velocity[:, k], velocity[:, k]))
    distance2[0] -= radius_m ** 2
    speed2[0] -= speed_m_s ** 2
    boundaries = sorted(set([0., duration_s] + _roots(distance2, duration_s) + _roots(speed2, duration_s)))
    intervals = []
    for a, b in zip(boundaries, boundaries[1:]):
        mid = (a + b) / 2
        if poly.polyval(mid, distance2) <= 1e-10 and poly.polyval(mid, speed2) <= 1e-10:
            intervals.append((a, b))
    return intervals


def region_crossings(state, jerk, region, duration_s):
    """Cubic-plane intersections retained as support; no semantic label here."""
    roots = []
    for i in range(len(state.p)):
        for axis, bounds in ((0, (region["min_east_m"], region["min_east_m"] + region["width_m"])),
                             (1, (region["min_north_m"], region["min_north_m"] + region["height_m"]))):
            for bound in bounds:
                roots.extend(_roots((state.p[i, axis] - bound, state.v[i, axis],
                                     state.a[i, axis] / 2, jerk[i, axis] / 6), duration_s))
    return sorted(set(roots))
