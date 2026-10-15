"""Legacy execution measurements and new morphology diagnostics; never gates."""
import numpy as np
from .detectors import runs


def role_diagnostics(kind, skeleton, agent, t, positions, velocity, levels, distance, center, work, cfg, core, work_end):
    from .labels import longest_hold, event, azimuth_deg
    ref = skeleton["references"][agent]
    xy = positions[:, :2]; speed = np.linalg.norm(velocity, axis=1)
    seconds = t / 1e6
    heading = np.arctan2(velocity[:, 1], velocity[:, 0])
    moving = speed >= cfg["detectors"]["revisit"]["min_speed_m_s"]
    lag = round(cfg["diagnostics"]["reversal_lag_s"] * 10)
    reverse = np.zeros(len(t), bool)
    if len(t) > lag:
        delta = np.abs(np.degrees(np.angle(np.exp(1j * (heading[lag:] - heading[:-lag])))))
        reverse[lag:] = work[lag:] & work[:-lag] & moving[lag:] & moving[:-lag] & (delta >= cfg["diagnostics"]["reversal_angle_deg"])
    metrics = {"work_reversal_count": len(runs(reverse)),
               "work_reversal_start_frames": [b for b, _ in runs(reverse)],
               "minimum_contour_distance_m": float(distance.min()),
               "minimum_contour_distance_frame": int(np.argmin(distance))}
    endpoint = np.linalg.norm(positions - np.asarray(ref["endpoint_enu_m"]), axis=1)
    after = seconds >= (core["t_s"] if kind == "intrusion" and core["t_s"] is not None else work_end) if (
        work_end is not None or kind == "intrusion" and core["t_s"] is not None) else np.zeros(len(t), bool)
    terminal = (endpoint <= skeleton["terminal_radius_m"]) & (speed <= skeleton["terminal_speed_m_s"]) & after
    retreat = None
    if (kind != "intrusion" or skeleton.get("abort_observation")) and ref.get("retreat_required"):
        retreat = event((endpoint <= skeleton["terminal_radius_m"]) & after, t, "retreat_point_arrival")
        retreat.pop("role_core_event")
        retreat.update(planned_warning_clearance_m=ref.get("retreat_warning_clearance_m"),
                       minimum_observed_endpoint_distance_m=float(endpoint.min()))
    extra = {"endpoint_min_distance_m": float(endpoint.min()), "endpoint_hold_s": longest_hold(terminal),
             "retreat_event": retreat}
    if kind == "intrusion":
        # protected depth = protected offset - signed contour distance.
        metrics["maximum_protected_depth_m"] = None  # filled from geometry_facts by caller
        metrics["entry_azimuth_deg"] = None if core["frame_index"] is None else azimuth_deg(xy[core["frame_index"]] - center)
    elif kind == "transit":
        visits = runs(levels >= 1)
        first = visits[0][0] if visits else None
        last = visits[0][1] - 1 if visits and visits[0][1] < len(t) else None
        visit = np.zeros(len(t), bool)
        if visits: visit[visits[0][0]:visits[0][1]] = True
        entry = None if first is None else azimuth_deg(xy[first] - center)
        exit_angle = None if last is None else azimuth_deg(xy[last] - center)
        delta = np.abs(np.degrees(np.angle(np.exp(1j * np.diff(heading)))))
        valid = visit[1:] & visit[:-1] & moving[1:] & moving[:-1]
        metrics.update(warning_entry_s=None if first is None else float(seconds[first]),
            warning_exit_s=None if last is None else float(seconds[last + 1]), warning_last_inside_frame=last,
            warning_visit_duration_s=None if last is None else float(seconds[last] - seconds[first]),
            chord_length_m=None if last is None else float(np.linalg.norm(xy[last] - xy[first])),
            entry_azimuth_deg=entry, exit_azimuth_deg=exit_angle,
            entry_exit_azimuth_difference_deg=None if last is None else abs((exit_angle - entry + 180) % 360 - 180),
            longest_low_speed_in_warning_s=longest_hold(visit & ~moving), cumulative_turn_in_warning_deg=float(delta[valid].sum()))
    elif kind == "close_observation":
        rules = skeleton.get("close_observation", {})
        if "observation_point_enu_m" in ref and "observation_radius_m" in rules:
            point = np.asarray(ref["observation_point_enu_m"][:2]); separation = np.linalg.norm(xy - point, axis=1)
            inside = separation <= rules["observation_radius_m"]; hits = np.flatnonzero(inside)
            metrics.update(observation_radius_m=rules["observation_radius_m"], dwell_s=longest_hold(inside),
                observation_enter_s=None if not len(hits) else float(seconds[hits[0]]),
                observation_exit_s=None if not len(hits) or hits[-1] == len(t) - 1 else float(seconds[hits[-1]]),
                observation_point_enu_m=point.tolist(), min_distance_to_obs_m=float(separation.min()))
    elif kind == "area_search":
        cursor = 0; visits = []
        endpoints = ref.get("scan_lane_endpoints_m", [])
        for point in endpoints:
            hit = np.flatnonzero(np.linalg.norm(xy[cursor:] - point, axis=1) <= skeleton["survey"]["lane_endpoint_radius_m"])
            if not len(hit): break
            cursor += int(hit[0]); visits.append(float(seconds[cursor]))
        done = bool(endpoints) and len(visits) == len(endpoints)
        metrics.update(ordered_lane_endpoint_times_s=visits, scan_pattern_observed=done,
            expected_lane_endpoint_count=len(endpoints), planned_strip_count=ref.get("scan_strip_count", len(endpoints) // 2),
            scan_end_s=visits[-1] if done else None,
            scan_segment_duration_s=visits[-1] - core["t_s"] if done and core["t_s"] is not None else None)
    elif kind == "feint":
        alert = np.flatnonzero(levels >= 2)
        turn = int(alert[0] + np.argmin(distance[alert[0]:])) if len(alert) else None
        exit_frames = np.flatnonzero((levels == 0) & (np.arange(len(t)) > turn)) if turn is not None else []
        drop = descending = retreat_ok = None
        if len(exit_frames):
            window = distance[turn:exit_frames[0] + 1]
            drop = float((np.maximum.accumulate(window) - window).max())
            descending = float(np.count_nonzero(np.diff(window) < 0) / max(1, len(window) - 1))
            rules = skeleton.get("feint", {})
            if "retreat_distance_tolerance_m" in rules and "retreat_drop_fraction_max" in rules:
                retreat_ok = drop <= rules["retreat_distance_tolerance_m"] and descending <= rules["retreat_drop_fraction_max"]
        metrics.update(alert_entry_s=None if not len(alert) else float(seconds[alert[0]]),
            turnaway_s=None if turn is None else float(seconds[turn]), turnaway_frame=turn,
            maximum_retreat_drop_m=drop, retreat_descending_fraction=descending, retreat_ok=retreat_ok,
            entered_protected=bool((levels == 3).any()))
        metrics.update(retreat_tolerance_m=skeleton.get("feint", {}).get("retreat_distance_tolerance_m"),
                       retreat_drop_fraction_max=skeleton.get("feint", {}).get("retreat_drop_fraction_max"))
    elif kind == "monitoring":
        rules = skeleton.get("monitoring", {})
        orbit_center = np.asarray(rules.get("orbit_center_enu_m", center)[:2])
        radial = xy - orbit_center
        angles = np.arctan2(radial[:, 1], radial[:, 0])
        valid = work & moving
        if "orbit_radius_m" in rules and "track_tolerance_m" in rules:
            valid &= np.abs(np.linalg.norm(radial, axis=1) - rules["orbit_radius_m"]) <= rules["track_tolerance_m"]
            norm = np.linalg.norm(radial, axis=1) * np.linalg.norm(velocity[:, :2], axis=1)
            tangent = np.c_[radial[:, 1], -radial[:, 0]]
            cosine = np.divide(np.abs(np.sum(tangent * velocity[:, :2], axis=1)), norm, out=np.zeros(len(t)), where=norm > 0)
            valid &= np.degrees(np.arccos(np.clip(cosine, 0, 1))) <= cfg["detectors"]["revisit"]["parallel_max_deg"]
        delta = np.angle(np.exp(1j * np.diff(angles)))
        starts = runs(valid); first = None
        if "min_loop_duration_s" in rules:
            needed = round(rules["min_loop_duration_s"] * 10) + 1
            first = next((b for b, e in starts if e - b >= needed), None)
        metrics.update(orbit_radius_m=rules.get("orbit_radius_m"), track_tolerance_m=rules.get("track_tolerance_m"),
            lap_count_observed=round(abs(float(delta[valid[1:]].sum())) / (2 * np.pi), 3), planned_laps=rules.get("planned_laps"),
            first_loop_start_s=None if first is None else float(seconds[first]), in_band_fraction=float((levels == 1).mean()),
            entry_to_patrol_s=None if first is None or core["t_s"] is None else float(seconds[first] - core["t_s"]))
        extra["_patrol_mask"] = valid; extra["_patrol_angles"] = angles
    return metrics, extra, terminal


def group_revisit_diagnostic(skeleton, seconds, masks, angles):
    if not masks or any(not m.any() for m in masks.values()): return None
    lo = max(float(seconds[np.flatnonzero(m)[0]]) for m in masks.values())
    hi = min(float(seconds[np.flatnonzero(m)[-1]]) for m in masks.values())
    if hi <= lo: return None
    maximum = 0.
    for sector in range(36):
        visits = []
        for agent, mask in masks.items():
            bins = np.floor((angles[agent] % (2 * np.pi)) * 36 / (2 * np.pi)).astype(int)
            hits = mask & (bins == sector) & (seconds >= lo) & (seconds <= hi)
            visits.extend(float(seconds[b]) for b, _ in runs(hits))
        maximum = max(maximum, float(np.diff([lo, *sorted(visits), hi]).max()))
    rules = skeleton.get("monitoring", {})
    radius = rules.get("orbit_radius_m"); speed = skeleton.get("cruise_speed_m_s")
    return {"window_s": [lo, hi], "maximum_interval_s": maximum, "sector_count": 36,
            "allowed_interval_s": 1.5 * 2 * np.pi * radius / (len(masks) * speed) if radius and speed else None,
            "diagnostic_only": True}
