"""Ordered continuous EN route references; only the plant moves actual state.

Routes retain their unfolded original node identities, including coincident
nodes on different laps. Geometric references never grant progress: witnesses
come from the committed constant-jerk polynomial supplied to observe_segment.
"""
from __future__ import annotations

import copy
import math

import numpy as np
from numpy.polynomial import polynomial as poly
from numpy.polynomial.legendre import leggauss

from .contracts import ControllerConfig, ReferenceConfig, VehicleProfile
from .references import _roots, arrival_intervals, endpoint_velocity

REFERENCE_VERSION = "continuous_route_v2"


def _bezier(control, t):
    t = np.asarray(t, dtype=float)
    n = len(control) - 1
    weights = np.stack([math.comb(n, k) * (1-t)**(n-k) * t**k for k in range(n+1)], axis=-1)
    return weights @ control


_GAUSS = {n: leggauss(n) for n in (16, 32)}


def _arc_integral(derivative, a, b, depth=0):
    estimates = []
    for n in (16, 32):
        x, w = _GAUSS[n]
        estimates.append(float(np.dot(w, np.linalg.norm(_bezier(derivative, a+(x+1)*(b-a)/2), axis=1))*(b-a)/2))
    if abs(estimates[1]-estimates[0]) <= 1e-11 * max(1., abs(estimates[1])):
        return estimates[1]
    if depth >= 16:
        raise ValueError("Bezier arc length did not converge")
    m = (a+b)/2
    return _arc_integral(derivative, a, m, depth+1) + _arc_integral(derivative, m, b, depth+1)


def _restrict(control, a, b):
    def split(values, t):
        levels = [np.asarray(values)]
        while len(levels[-1]) > 1:
            levels.append((1-t)*levels[-1][:-1]+t*levels[-1][1:])
        return np.array([x[0] for x in levels]), np.array([x[-1] for x in levels[::-1]])
    left = split(control, b)[0]
    return split(left, a/b)[1] if a else left


def _curvature_bounds(derivatives):
    """Bernstein convex-hull bounds for curvature and arclength derivative."""
    curvature = change = 0.
    for i in range(64):
        a, b = i/64, (i+1)/64
        tangent = _bezier(derivatives[1], (a+b)/2)
        tangent /= np.linalg.norm(tangent)
        ds = [_restrict(c, a, b) for c in derivatives[1:]]
        lower_speed = float(np.min(ds[0]@tangent))
        if lower_speed <= 0:
            raise ValueError("nonregular Bezier tangent interval")
        b2, b3 = (float(np.linalg.norm(c, axis=1).max()) for c in ds[1:])
        curvature = max(curvature, b2/lower_speed**2)
        change = max(change, b3/lower_speed**3+3*b2**2/lower_speed**4)
    return curvature, change


class _Primitive:
    def __init__(self, start, end, *, control=None, stop=False, node_index=None):
        self.start, self.end = np.array(start, float), np.array(end, float)
        self.control = None if control is None else np.array(control, float)
        self.stop, self.node_index = stop, node_index
        self.direction = (self.end-self.start) / np.linalg.norm(self.end-self.start)
        self.cap = float("inf")
        if control is None:
            self.length = float(np.linalg.norm(self.end-self.start))
            self.derivatives = None
        else:
            ds = [self.control]
            for _ in range(3):
                ds.append((len(ds[-1])-1)*np.diff(ds[-1], axis=0))
            self.derivatives = ds
            self.length = _arc_integral(ds[1], 0., 1.)
            self.ts = np.linspace(0., 1., 65)
            self.ss = np.array([_arc_integral(ds[1], 0., float(t)) for t in self.ts])
            # Power coefficients support the exact nearest-point polynomial.
            self.power = np.array([sum(((-1)**(j-k) * math.comb(5, k) * math.comb(5-k, j-k) * self.control[k]
                                       for k in range(j+1)), start=np.zeros(2)) for j in range(6)])

    def point(self, s):
        if self.control is None:
            return self.start + self.direction * float(np.clip(s, 0., self.length)), self.direction, np.zeros(2)
        s = float(np.clip(s, 0., self.length))
        t = float(np.interp(s, self.ss, self.ts))
        # Safeguarded Newton inversion of actual arclength, never 2*cut.
        lo, hi = 0., 1.
        for _ in range(12):
            err = _arc_integral(self.derivatives[1], 0., t)-s
            if abs(err) <= 1e-9:
                break
            if err > 0:
                hi = t
            else:
                lo = t
            d1 = _bezier(self.derivatives[1], t)
            proposal = t-err/float(np.linalg.norm(d1))
            t = proposal if lo < proposal < hi else (lo+hi)/2
        else:
            raise ValueError("Bezier inverse arc length did not converge")
        p = _bezier(self.control, t)
        d1, d2 = (_bezier(self.derivatives[i], t) for i in (1, 2))
        n = float(np.linalg.norm(d1))
        tangent = d1/n
        curvature = (d2-tangent*float(d2@tangent))/n**2
        return p, tangent, curvature

    def project(self, position):
        if self.control is None:
            s = float((position-self.start) @ self.direction)
            p = self.start + np.clip(s, 0., self.length)*self.direction
            return s, float(np.linalg.norm(position-p))
        shifted = self.power.copy()
        shifted[0] -= position
        coeff = np.zeros(10)
        for axis in (0, 1):
            coeff = poly.polyadd(coeff, poly.polymul(shifted[:, axis], poly.polyder(self.power[:, axis])))
        candidates = [0., 1.] + [float(r.real) for r in poly.polyroots(coeff)
                                 if abs(r.imag) < 1e-7 and 0 < r.real < 1]
        t = min(candidates, key=lambda q: (float(np.linalg.norm(_bezier(self.control, q)-position)), q))
        return _arc_integral(self.derivatives[1], 0., t), float(np.linalg.norm(_bezier(self.control, t)-position))


def _disk_intervals(segment, agent_index, center, radius):
    """Polynomial intervals inside an EN disk on the committed segment."""
    i = agent_index
    coefficients = np.stack((segment.state.p[i, :2]-center, segment.state.v[i, :2],
                             segment.state.a[i, :2]/2, segment.jerk[i, :2]/6))
    squared = np.zeros(7)
    for axis in (0, 1):
        squared = poly.polyadd(squared, poly.polymul(coefficients[:, axis], coefficients[:, axis]))
    squared[0] -= radius**2
    duration = (segment.end_us-segment.start_us)/1e6
    if duration == 0:
        return [(0., 0.)] if squared[0] <= 1e-13 else []
    bounds = sorted(set([0., duration] + _roots(squared, duration)))
    return [(a, b) for a, b in zip(bounds, bounds[1:])
            if poly.polyval((a+b)/2, squared) <= 1e-13]


class RouteTracker:
    """One agent's reference and physical, ordered route evidence.

    ``points`` includes the original phase start. ``command`` is read-only;
    call ``observe_segment`` after a shared physics prefix has been committed.
    The object is deepcopy-safe for executor transactions. No-op routes consist
    of one target; the executor still performs full-3D arrival/dwell/hold.
    """
    def __init__(self, points, speed_m_s, profile=None, controller_config=None, reference_config=None, step_us=20_000):
        self.points = np.array(points, dtype=float, copy=True)
        if self.points.ndim != 2 or self.points.shape[1] != 3 or not len(self.points) or not np.all(np.isfinite(self.points)):
            raise ValueError("route points must be finite (N,3), N>=1")
        if not math.isfinite(speed_m_s) or speed_m_s <= 0:
            raise ValueError("route speed must be finite and positive")
        if np.ptp(self.points[:, 2]) > 1e-9:
            raise ValueError("M2 continuous routes require constant planned altitude")
        self.profile = profile or VehicleProfile()
        self.controller = controller_config or ControllerConfig()
        if not isinstance(step_us, int) or isinstance(step_us, bool) or not 0 < step_us <= 100_000:
            raise ValueError("step_us must be an integer in (0,100000]")
        self.step_s = step_us/1e6
        self.reference = reference_config or ReferenceConfig()
        if isinstance(self.reference, dict):
            self.reference = ReferenceConfig(**self.reference)
        self.speed = min(float(speed_m_s), self.profile.max_speed_xy_m_s)
        self.target = self.points[-1].copy()
        self.complete = len(self.points) == 1
        self.primitive_index = 0
        self.next_node = 0 if not self.complete else 1
        self.witnesses = []
        self.stop_since_us = None
        self.events = []
        self.primitives = []
        self.gates = np.array([.5])
        self.short_continuations = frozenset()
        self._build()

    def __deepcopy__(self, memo):
        # Geometry/configuration are never mutated after construction. Only
        # route evidence and stop bookkeeping participate in transactions.
        result = object.__new__(type(self))
        memo[id(self)] = result
        result.__dict__ = self.__dict__.copy()
        for key in ("witnesses", "events"):
            result.__dict__[key] = copy.deepcopy(self.__dict__[key], memo)
        return result

    def _build(self):
        if self.complete:
            return
        lengths = np.linalg.norm(np.diff(self.points[:, :2], axis=0), axis=1)
        if np.any(lengths <= 0):
            raise ValueError("zero-length raw EN legs must be cleaned by the task compiler")
        directions = np.diff(self.points[:, :2], axis=0)/lengths[:, None]
        # A collinear node immediately after a tiny leg has a much smaller
        # witness disk than the tracking tube. Crossing its normal plane is
        # insufficient: the residual lateral error from the preceding bend
        # may miss that disk and otherwise consume the next lap's witness.
        self.short_continuations = frozenset(i for i in range(1, len(self.points)-1)
            if min(lengths[i-1], lengths[i]) < self.reference.tracking_tube_m
            and float(directions[i-1] @ directions[i]) >= 1.-1e-14)
        self.gates = np.array([min(.5, .2*min(lengths[max(0, i-1):min(len(lengths), i+1)]))
                               for i in range(len(self.points))])
        bends, stops = {}, set()
        for i in range(1, len(self.points)-1):
            u, w = directions[i-1:i+1]
            angle = math.acos(float(np.clip(u@w, -1, 1)))
            if angle >= math.radians(175):
                stops.add(i)
            elif angle > 1e-8:
                if self.reference.policy == "continuous_route_v3":
                    from .reference_r3 import cut_distance
                    d = cut_distance(self.gates[i], angle, lengths[i-1], lengths[i])
                else:
                    d = min(self.reference.corner_cut_max_m, self.reference.corner_leg_fraction*lengths[i-1],
                            self.reference.corner_leg_fraction*lengths[i])
                v = self.points[i, :2]
                e, x = v-d*u, v+d*w
                ctrl = [e, e+d*u/3, e+2*d*u/3, x-2*d*w/3, x-d*w/3, x]
                curve = _Primitive(e, x, control=ctrl, node_index=i)
                # Response horizon also bounds how far a moving reference can
                # pull the real vehicle away from tiny original-node gates.
                horizon = self.controller.velocity_response_time_s + self.profile.response_time_s
                k, ks = _curvature_bounds(curve.derivatives)
                curve.cap = min(self.speed, d/horizon,
                                math.sqrt(self.profile.max_accel_xy_m_s2/(2*k)),
                                (self.profile.max_jerk_m_s3/(2*(k*k+ks)))**(1/3))
                bends[i] = curve
        for k in range(len(lengths)):
            start = bends[k].end if k in bends else self.points[k, :2]
            end = bends[k+1].start if k+1 in bends else self.points[k+1, :2]
            self.primitives.append(_Primitive(start, end, stop=k+1 in stops,
                                               node_index=k+1))
            if k+1 in bends:
                self.primitives.append(bends[k+1])
        # Speed caps are local but braking looks through all downstream
        # primitives, so a short line cannot hide a slow adjacent corner.
        for i, primitive in enumerate(self.primitives):
            if primitive.control is None:
                primitive.exit_cap = (0. if primitive.stop or i == len(self.primitives)-1 else
                                      self.primitives[i+1].cap if self.primitives[i+1].control is not None else self.speed)
            else:
                primitive.exit_cap = primitive.cap

    @property
    def route_complete(self):
        return self.complete

    @property
    def diagnostics(self):
        return {"reference_version": self.reference.policy, "route_complete": self.complete,
                "primitive_index": self.primitive_index, "original_node_count": len(self.points),
                "witnessed_node_count": self.next_node, "witnesses": list(self.witnesses),
                "reference_length_m": sum(p.length for p in self.primitives)}

    def _endpoint(self, p, target, speed=None):
        return endpoint_velocity(np.asarray(p)[None, :], np.asarray(target)[None, :],
                                 self.speed if speed is None else speed,
                                 self.controller.velocity_response_time_s)[0]

    def command(self, position, velocity, acceleration):
        """Midpoint prediction improves h/h2 agreement without editing truth."""
        p, v, a = (np.asarray(x, dtype=float) for x in (position, velocity, acceleration))
        if any(x.shape != (3,) or not np.all(np.isfinite(x)) for x in (p, v, a)):
            raise ValueError("tracker state must contain three finite ENU vectors")
        half = self.step_s/2
        predicted_p = p+v*half+a*half**2/2
        predicted_v = v+a*half
        desired = self._command(predicted_p, predicted_v, a)
        request = (desired-predicted_v)/self.controller.velocity_response_time_s
        # Midpoint response of the first-order acceleration actuator. The
        # plant still applies its own capability limits and exact jerk step.
        factor = self.profile.response_time_s/(self.profile.response_time_s+half)
        request = a+(request-a)*factor
        return v+self.controller.velocity_response_time_s*request

    def _command(self, p, v, a):
        if self.complete:
            return self._endpoint(p, self.target)
        if self.next_node == 0:
            return self._endpoint(p, self.points[0])
        primitive = self.primitives[self.primitive_index]
        projected, error = primitive.project(p[:2])
        if (primitive.node_index in self.short_continuations
                and self.next_node <= primitive.node_index and projected >= primitive.length):
            # Acquire the real original node before continuing. This changes
            # only the reference; p/v/a still evolve through the same plant.
            return self._endpoint(p, self.points[primitive.node_index])
        if primitive.stop and (projected >= primitive.length-self.gates[primitive.node_index] or self.stop_since_us is not None):
            return self._endpoint(p, self.points[primitive.node_index])
        if error > self.reference.tracking_tube_m:
            target = np.r_[primitive.start, self.target[2]]
            return self._endpoint(p, target)
        if projected < 0 and np.linalg.norm(p[:2]-primitive.start) > min(.25, primitive.length*.2):
            return self._endpoint(p, np.r_[primitive.start, self.target[2]])
        horizon = self.controller.velocity_response_time_s + self.profile.response_time_s
        remaining = max(0., primitive.length-projected)
        cap = min(self.speed, primitive.cap)
        distance = remaining
        # Exponential stopping/reference envelope accounts for controller lag;
        # the actual jerk and acceleration remain governed by the plant.
        for next_i in range(self.primitive_index, len(self.primitives)):
            item = self.primitives[next_i]
            cap = min(cap, item.exit_cap + distance/(2*horizon))
            if item.stop or next_i == len(self.primitives)-1:
                break
            if next_i+1 < len(self.primitives):
                distance += self.primitives[next_i+1].length
            if distance > 4*self.speed*horizon:
                break
        # A finite terminal original-node gate removes the asymptotic endpoint
        # deadlock. No lower speed floor is imposed on tiny physical segments.
        lead = min(.2, .1*primitive.length, self.reference.preview_time_s*max(cap, float(np.linalg.norm(v[:2]))))
        q, tangent, curvature = primitive.point(min(primitive.length, max(0., projected)+lead))
        desired = np.zeros(3)
        desired[:2] = (cap*tangent + self.reference.position_gain_per_s*(q-p[:2]) -
                       self.reference.velocity_damping*(v[:2]-cap*tangent) +
                       self.controller.velocity_response_time_s*cap**2*curvature)
        magnitude = float(np.linalg.norm(desired[:2]))
        # Reference clipping, never actual p/v/a clipping.
        if magnitude > self.speed:
            desired[:2] *= self.speed/magnitude
        desired[2] = self._endpoint(p, np.r_[p[:2], self.target[2]])[2]
        return desired

    desired_velocity = command

    def observe_segment(self, segment, agent_index=0):
        if self.complete:
            return []
        emitted = []
        earliest = 0.
        while self.next_node < len(self.points):
            k = self.next_node
            intervals = _disk_intervals(segment, agent_index, self.points[k, :2], self.gates[k])
            eligible = [(max(a, earliest), b) for a, b in intervals if b >= earliest]
            if not eligible:
                break
            t = eligible[0][0]
            tick = min(segment.end_us, segment.start_us+int(math.ceil(t*1e6-1e-8)))
            # Verify the quantized witness, not just a rounded polynomial root.
            if np.linalg.norm(segment.at(tick).p[agent_index, :2]-self.points[k, :2]) > self.gates[k]+1e-10:
                break
            event = {"event": "route_node_witnessed", "t_us": tick, "node_index": k}
            self.witnesses.append(event)
            emitted.append(event)
            self.next_node += 1
            earliest = t
        end_state = segment.at(segment.end_us)
        progress_after = 0.
        while self.primitive_index < len(self.primitives)-1:
            primitive = self.primitives[self.primitive_index]
            if primitive.stop:
                target = self.points[primitive.node_index]
                duration = (segment.end_us-segment.start_us)/1e6
                intervals = arrival_intervals(segment.state, segment.jerk, agent_index, target,
                                               min(.25, self.gates[primitive.node_index]), .001, duration)
                accel = np.stack((segment.state.a[agent_index], segment.jerk[agent_index]))
                squared = sum((poly.polymul(accel[:, axis], accel[:, axis]) for axis in range(3)), start=np.zeros(3))
                squared[0] -= .01**2
                bounds = sorted(set([0., duration] + _roots(squared, duration)))
                acceleration_intervals = [(a, b) for a, b in zip(bounds, bounds[1:]) if poly.polyval((a+b)/2, squared) <= 1e-14]
                valid_intervals = [(max(a, c), min(b, d)) for a, b in intervals for c, d in acceleration_intervals
                                   if min(b, d) > max(a, c)]
                stopped_at = None
                covered_to = 0.
                for a, b in valid_intervals:
                    if a > covered_to+1e-12:
                        self.stop_since_us = None
                    if self.stop_since_us is None:
                        self.stop_since_us = segment.start_us+int(math.ceil(a*1e6-1e-8))
                    candidate = self.stop_since_us+50_000
                    if candidate <= segment.start_us+int(math.floor(b*1e6+1e-8)):
                        stopped_at = candidate
                        break
                    covered_to = b
                if stopped_at is None:
                    if not valid_intervals or covered_to < duration-1e-12:
                        self.stop_since_us = None
                    break
                emitted.append({"event": "route_corner_stopped", "t_us": stopped_at,
                                "node_index": primitive.node_index})
                self.stop_since_us = None
                progress_after = (stopped_at-segment.start_us)/1e6
            else:
                tangent = primitive.point(primitive.length)[1]
                coefficients = [float((segment.state.p[agent_index, :2]-primitive.end)@tangent),
                                float(segment.state.v[agent_index, :2]@tangent),
                                float(segment.state.a[agent_index, :2]@tangent)/2,
                                float(segment.jerk[agent_index, :2]@tangent)/6]
                duration = (segment.end_us-segment.start_us)/1e6
                roots = [t for t in _roots(coefficients, duration)
                         if t >= progress_after and poly.polyval(t, poly.polyder(coefficients)) > 0]
                if (coefficients[0] <= 1e-10 and poly.polyval(duration, coefficients) >= 0
                        and poly.polyval(duration, poly.polyder(coefficients)) > 0):
                    roots.append(duration)
                good = [t for t in roots if np.linalg.norm(segment.at(min(segment.end_us, segment.start_us+int(round(t*1e6)))).p[agent_index, :2]-primitive.end)
                        <= self.reference.tracking_tube_m]
                if (primitive.node_index in self.short_continuations
                        and self.next_node > primitive.node_index):
                    # Acquisition may enter the tiny disk from beyond the
                    # endpoint plane. That already-crossed plane cannot yield
                    # a second forward root; the actual ordered witness plus
                    # its location on the forward side completes this leg.
                    tick = max(segment.start_us, self.witnesses[primitive.node_index]["t_us"])
                    if tick <= segment.end_us:
                        delta = segment.at(tick).p[agent_index, :2]-primitive.end
                        if float(delta @ tangent) >= 0 and np.linalg.norm(delta) <= self.reference.tracking_tube_m:
                            good.append((tick-segment.start_us)/1e6)
                if not good:
                    break
                if (primitive.node_index in self.short_continuations
                        and self.next_node <= primitive.node_index):
                    break
                progress_after = min(good)
            self.primitive_index += 1
            emitted.append({"event": "route_primitive_advanced",
                            "t_us": min(segment.end_us, segment.start_us+int(math.ceil(progress_after*1e6-1e-8))),
                            "primitive_index": self.primitive_index})
        if self.next_node == len(self.points) and self.primitive_index == len(self.primitives)-1:
            self.complete = True
            emitted.append({"event": "route_completed", "t_us": self.witnesses[-1]["t_us"],
                            "node_index": len(self.points)-1})
        self.events.extend(emitted)
        return emitted

    observe = observe_segment
