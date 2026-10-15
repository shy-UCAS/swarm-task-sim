"""Guidance-supplied Q0 geometry and analytic trajectories, sampled at 10 Hz."""
from copy import deepcopy
import math
import numpy as np
from scene_v07.contract import SCHEMA_VERSION, UNITS, validate_public_scene


def scene():
    public = {"schema_version": SCHEMA_VERSION, "coordinate_system": "ENU", "units": dict(UNITS),
        "world": {"id": "world", "geometry": {"type": "Polygon", "vertices_m": [[-3000, -3000], [3000, -3000], [3000, 3000], [-3000, 3000]]}},
        "entry_zones": [{"id": "E1", "geometry": {"type": "Polygon", "vertices_m": [[-2000, 1700], [2000, 1700], [2000, 2000], [-2000, 2000]]}}],
        "entities": [{"id": "F1", "type": "facility", "geometry": {"type": "Circle", "center_m": [0, 0], "radius_m": 40}},
            {"id": "R1", "type": "hard_constraint_obstacle", "geometry": {"type": "Circle", "center_m": [-1200, -1200], "radius_m": 100}},
            {"id": "radar", "type": "radar", "geometry": {"type": "Point", "position_m": [0, 0]}}]}
    for layer, offset in (("protected", 100), ("alert", 350), ("warning", 850)):
        public["entities"].append({"id": "F1_" + layer, "type": "protection_zone", "facility_id": "F1", "layer": layer,
            "offset_m": offset, "geometry": {"type": "Circle", "center_m": [0, 0], "radius_m": 40 + offset}})
    return validate_public_scene(public)


def line(a, b, speed):
    a, b = np.asarray(a, float), np.asarray(b, float)
    duration = float(np.linalg.norm(b - a) / speed); velocity = (b - a) / duration
    return duration, lambda t: (a + t[:, None] * velocity, np.broadcast_to(velocity, (len(t), 2)))


def hold(point, duration):
    return duration, lambda t: (np.repeat([point], len(t), axis=0), np.zeros((len(t), 2)))


def arc(center, radius, begin_deg, end_deg, speed):
    start, end = np.radians([begin_deg, end_deg]); direction = 1 if end > start else -1
    omega = direction * speed / radius
    def sample(t):
        theta = start + omega * t
        return (np.asarray(center) + radius * np.c_[np.cos(theta), np.sin(theta)],
                direction * speed * np.c_[-np.sin(theta), np.cos(theta)])
    return abs(end - start) * radius / speed, sample


def trajectory(segments, agent="a"):
    total = sum(s[0] for s in segments)
    time_us = np.arange(math.floor(total * 10 + 1e-8) + 1, dtype=np.int64) * 100000
    seconds = time_us / 1e6; p = np.zeros((len(seconds), 1, 3)); v = np.zeros_like(p); p[:, :, 2] = 120.
    begin = 0.
    for index, (duration, fn) in enumerate(segments):
        end = begin + duration
        selected = (seconds >= begin) & ((seconds < end) if index < len(segments) - 1 else (seconds <= end + 1e-8))
        xy, velocity = fn(seconds[selected] - begin)
        p[selected, 0, :2], v[selected, 0, :2] = xy, velocity
        begin = end
    return {"agent_ids": [agent], "time_us": time_us, "p": p, "v": v, "execution_status": "completed"}


def polyline(points, speed):
    return [line(a, b, speed) for a, b in zip(points[:-1], points[1:])]


def tracks():
    result = {"T1": trajectory([line((-1500, 600), (1500, 600), 4)]),
        "T2": trajectory([line((-1500, 600), (1500, 600), 10)]),
        "T3": trajectory([line((0, 1500), (0, 500), 6), hold((0, 500), 25), line((0, 500), (1500, 500), 6)]),
        "T4": trajectory([line((0, 1500), (0, 515), 6), arc((0, 500), 15, 90, 810, math.pi), line((0, 515), (1500, 515), 6)]),
        "T5": trajectory([line((0, 1500), (0, 600), 8), arc((0, 0), 600, 90, 630, 8), line((0, -600), (0, -1500), 8)])}
    for name, start, end in (("T6", 30, 180), ("T7", 40, 140)):
        direction = np.array([math.cos(math.radians(start)), math.sin(math.radians(start))])
        result[name] = trajectory([line(direction * 1500, direction * 600, 8), arc((0, 0), 600, start, end, 8),
            arc((0, 0), 600, end, start, 8), line(direction * 600, direction * 1500, 8)])
    points = [(-200, 1500), (-200, 830)]
    for i, y in enumerate((830, 760, 690, 620, 550, 480)):
        points.append((200 if i % 2 == 0 else -200, y))
        if i < 5: points.append((points[-1][0], y - 70))
    points.append((-200, 1500))
    result["T8"] = trajectory(polyline(points, 8))
    direction = np.array([math.cos(2 * math.pi / 3), math.sin(2 * math.pi / 3)])
    result["T9c"] = trajectory(polyline([(-1500, 600), (500, 600), np.array([500, 600]) + 1500 * direction], 4))
    for name, depth in (("T10", 240), ("T11", 130)):
        result[name] = trajectory(polyline([(0, 1500), (0, depth), (0, 1500)], 8))
    result["T12"] = trajectory([line((0, 1500), (0, 60), 8), hold((0, 60), 10)])
    result["T13"] = trajectory([line((-1500, -1200), (-900, -1200), 8)])
    return result


def skeleton(kind, run, gid="g"):
    role = "reconnaissance" if kind in ("area_search", "close_observation") else kind
    sk = {"base_intent": "penetration" if role == "intrusion" else role, "role": role, "execution_method": kind,
        "target_id": "F1", "group_id": gid, "members": run["agent_ids"], "agent_ids": run["agent_ids"],
        "approach_mode": "same_direction", "cruise_speed_m_s": 8., "terminal_radius_m": 1., "terminal_speed_m_s": .15,
        "terminal_hold_s": 2., "exclusion_policy": {a: {} for a in run["agent_ids"]}, "references": {}}
    for i, a in enumerate(run["agent_ids"]):
        sk["references"][a] = {"endpoint_enu_m": run["p"][-1, i].tolist(), "observation_point_enu_m": [0, 500, 120],
            "retreat_required": kind != "intrusion", "retreat_warning_clearance_m": 0., "scan_lane_endpoints_m": []}
    sk["close_observation"] = {"observation_radius_m": 30.}
    sk["monitoring"] = {"orbit_center_enu_m": [0, 0], "orbit_radius_m": 600., "track_tolerance_m": 30., "min_loop_duration_s": 5., "planned_laps": 1.5}
    sk["feint"] = {"retreat_distance_tolerance_m": 5., "retreat_drop_fraction_max": .1}
    if kind == "area_search":
        sk["survey"] = {"geometry": {"type": "Polygon", "vertices_m": [[-200, 480], [200, 480], [200, 830], [-200, 830]]},
            "bounds_m": [-200, 480, 200, 830], "grid_spacing_m": 10., "footprint_radius_m": 60., "lane_endpoint_radius_m": 5.,
            "model": "ideal_isotropic_horizontal_disk", "assumptions": "Geometric footprint only", "area_m2": 140000.}
    return sk


def combine(runs):
    length = max(len(r["time_us"]) for r in runs); parts_p, parts_v = [], []
    ids = []
    for run in runs:
        pad = length - len(run["time_us"])
        parts_p.append(np.concatenate([run["p"], np.repeat(run["p"][-1:], pad, axis=0)]))
        parts_v.append(np.concatenate([run["v"], np.zeros((pad, len(run["agent_ids"]), 3))]))
        ids.extend(run["agent_ids"])
    return {"agent_ids": ids, "time_us": np.arange(length, dtype=np.int64) * 100000,
            "p": np.concatenate(parts_p, axis=1), "v": np.concatenate(parts_v, axis=1), "execution_status": "completed"}


def fast_corner(speed):
    from task_v07.execution import execute
    points = [[-1500., 600., 120.], [500., 600., 120.], [500., 1500., 120.]]
    sk = {"agent_ids": ["a"], "initial_states": [{"agent_id": "a", "position_enu_m": points[0],
        "velocity_enu_m_s": [0., 0., 0.], "acceleration_enu_m_s2": [0., 0., 0.]}],
        "references": {"a": {"points_enu_m": points}}, "cruise_speed_m_s": speed,
        "initial_settle_s": 20., "terminal_radius_m": 1., "terminal_speed_m_s": .15, "terminal_hold_s": 2.}
    return execute(sk, {"a": 0.})
