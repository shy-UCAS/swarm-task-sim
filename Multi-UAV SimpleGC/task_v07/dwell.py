"""Task-level intermediate hover; the frozen tracker and plant are unchanged."""
from copy import deepcopy
import math

import numpy as np
from swarm_sim.fast_dynamics.route_tracker import RouteTracker


class DwellRouteTracker:
    """Approach, settled hold on exported samples, then the remaining route."""
    def __init__(self, points, speed, cfg, dwell, radius_m=1., speed_m_s=.15):
        self.points = np.asarray(points, float)
        self.index = int(dwell['waypoint_index'])
        self.duration_us = math.ceil(float(dwell['duration_s'])*10)*100000
        if not 0 < self.index < len(points)-1 or self.duration_us <= 0:
            raise ValueError('Intermediate dwell must have a positive duration and a subsequent route')
        self.speed, self.cfg = speed, cfg
        self.radius, self.max_speed = radius_m, speed_m_s
        self.stage = 'approach'
        self.since_us = None
        self.events = []
        self.tracker = self._tracker(self.points[:self.index+1])

    def _tracker(self, points):
        c = self.cfg
        return RouteTracker(points, self.speed, c.vehicle_profile, c.controller, c.reference, c.engine.step_us)

    def __deepcopy__(self, memo):
        result = object.__new__(type(self))
        memo[id(self)] = result
        result.__dict__ = self.__dict__.copy()
        result.tracker = deepcopy(self.tracker, memo)
        result.events = deepcopy(self.events, memo)
        return result

    @property
    def complete(self):
        return self.stage == 'departure' and self.tracker.complete

    def command(self, *args):
        return self.tracker.command(*args)

    def observe_segment(self, *args, **kwargs):
        return self.tracker.observe_segment(*args, **kwargs)

    def observe_sample(self, sample, index):
        if self.stage == 'departure' or not self.tracker.complete:
            return
        settled = (np.linalg.norm(sample.p[index]-self.points[self.index]) <= self.radius
                   and np.linalg.norm(sample.v[index]) <= self.max_speed)
        if not settled:
            self.since_us = None
            return
        if self.since_us is None:
            self.since_us = int(sample.t_us)
            self.stage = 'hold'
        if sample.t_us-self.since_us >= self.duration_us:
            self.events.append({'hold_start_us': self.since_us, 'hold_end_us': int(sample.t_us),
                                'planned_duration_s': self.duration_us/1e6})
            self.tracker = self._tracker(self.points[self.index:])
            self.stage = 'departure'


def timed_route_samples(points, speed, sample_hz, dwell):
    """Nominal whole route including a stationary intermediate dwell."""
    pts = np.asarray(points, float)
    index = int(dwell['waypoint_index'])
    duration = math.ceil(float(dwell['duration_s'])*sample_hz)/sample_hz
    if not 0 < index < len(pts)-1 or duration <= 0:
        raise ValueError('Invalid intermediate dwell')
    times = np.r_[0., np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))/speed]
    times[index+1:] += duration
    times = np.insert(times, index+1, times[index]+duration)
    vertices = np.insert(pts, index+1, pts[index], axis=0)
    grid = np.arange(int(np.ceil(times[-1]*sample_hz))+3)/sample_hz
    return np.column_stack([np.interp(grid, times, vertices[:, axis]) for axis in range(3)])
