"""Independent criteria-r1 role, group, cluster, event and quality evidence."""
from itertools import combinations
from pathlib import Path
import numpy as np
from scripts.audit_v07_m1_detectors import (configuration, independent_dwell, independent_revisit, independent_coverage)
from scripts.audit_v07_s2_exact import _read, _inside, _signed_distance
from scripts.audit_v07_s2_roles import _center, _runs, _load_truth, _build_levels, _approach_heading_deg, _heading_span_deg
from scripts.audit_v07_s2_conditions import _equal


def positive(value, complete):
    return True if value else False if complete else None


def negative(violation, complete):
    return False if violation else True if complete else None


def outcome(checks):
    return "failure" if False in checks.values() else "unknown" if None in checks.values() else "success"


def independently_measure(scene, task, run, complete, *, detector_cache=None):
    cfg = configuration()
    ids, t, p, v = (run[key] for key in ("agent_ids", "time_us", "p", "v"))
    cache = {} if detector_cache is None else detector_cache
    def cached(key, compute):
        if key not in cache: cache[key] = compute()
        return cache[key]
    fids = sorted(e["id"] for e in scene["entities"] if e["type"] == "facility")
    levels = _build_levels(scene, p[:, :, :2], fids)
    blocked = np.zeros(p.shape[:2], bool)
    for e in scene["entities"]:
        if e["type"] == "hard_constraint_obstacle": blocked |= _inside(e["geometry"], p[:, :, :2])
    outside = ~_inside(scene["world"]["geometry"], p[:, :, :2])
    groups = task.get("group_skeletons", {task.get("group_id"): task})
    agent_expected, group_expected = {}, {}
    target_layers = np.zeros(p.shape[:2], np.int8)
    for gid, template in groups.items():
        target = fids.index(template["target_id"])
        facility = next(e for e in scene["entities"] if e["id"] == template["target_id"])
        center = _center(facility["geometry"])
        distance = _signed_distance(facility["geometry"], p[:, :, :2])
        kind = template["role"]
        if kind == "reconnaissance": kind = "close_observation" if template["execution_method"] == "close_observation" else "area_search"
        footprints, headings, events, statuses = [], {}, {}, []
        abort_values = []
        for a in sorted(template["members"]):
            i = ids.index(a); xy = p[:, i, :2]; layer = levels[:, i, target]; target_layers[:, i] = layer
            hit = np.flatnonzero(layer >= 1); selected = np.zeros(len(t), bool)
            if len(hit): selected[hit[0]:hit[-1] + 1] = True
            first_warning = int(hit[0]) if len(hit) else None
            identity = (id(p), id(v), id(t), template["target_id"], a)
            dwell = cached((identity, "work_dwell"), lambda: independent_dwell(xy, t, selected))
            revisit = cached((identity, "revisit"), lambda: independent_revisit(xy, v[:, i], t, layer, selected, center))
            evidence = {"dwell": dwell, "revisit": revisit, "minimum_contour_distance_m": float(distance[:, i].min()),
                        "minimum_contour_distance_frame": int(np.argmin(distance[:, i])), "dwell_total_duration_s": dwell["total_duration_s"]}
            def first(mask):
                found = np.flatnonzero(mask)
                return int(found[0]) if len(found) else None
            core = confirm = None
            if kind == "transit":
                count = len(_runs(layer >= 1)); core = first_warning; raw = "enter_warning_zone"
                checks = {"entered_warning": positive(count > 0, complete), "single_warning_visit": False if count > 1 else positive(count == 1, complete),
                    "no_dwell": negative(dwell["detected"], complete), "no_revisit": negative(revisit["detected"], complete)}
            elif kind == "area_search":
                footprint = independent_coverage(xy, np.linalg.norm(v[:, i], axis=1), layer, blocked[:, i], template["survey"])
                footprints.append(footprint["covered_mask"]); core = first(footprint["effective_mask"]); raw = "scan_start"
                checks = {"effective_observation": positive(core is not None, complete), "no_revisit": negative(revisit["detected"], complete)}
                evidence.update(covered_group_grid_points=int(footprint["covered_mask"].sum()), group_grid_point_count=footprint["grid_point_count"],
                    effective_observation_duration_s=float(footprint["effective_mask"].sum()) / 10)
            elif kind == "close_observation":
                obs = cached((identity, "band_dwell"), lambda: independent_dwell(xy, t, layer == 1)); evidence["observation_dwell"] = obs
                core, confirm, raw = obs["frame_index"], obs["confirm_frame_index"], "observation_point_arrival"
                checks = {"observation_dwell": positive(obs["detected"], complete), "no_revisit": negative(revisit["detected"], complete)}
            elif kind == "monitoring":
                core, raw = first_warning, "enter_warning_zone"
                checks = {"patrol_revisit": positive(revisit["detected"], complete)}
            elif kind == "feint":
                core, raw = first(layer >= 2), "enter_alert_zone"; count = len(_runs(layer >= 2))
                checks = {"entered_alert": positive(bool((layer == 2).any()), complete),
                          "single_alert_visit": False if count > 1 else positive(count == 1, complete)}
                offsets = {e["layer"]: e["offset_m"] for e in scene["entities"] if e.get("facility_id") == template["target_id"]}
                band = layer == 2
                depth = max([0., *(offsets["alert"] - distance[band, i]).tolist()])
                evidence.update(max_depth_in_alert_m=round(depth, 3), depth_fraction_in_alert_band=round(depth / (offsets["alert"] - offsets["protected"]), 3))
            else:
                core, raw = first(layer == 3), "enter_protected_zone"
                checks = {"entered_protected": positive(bool((layer == 3).any()), complete),
                          "near_facility_contour": positive(distance[:, i].min() <= cfg["roles"]["intrusion"]["max_contour_distance_m"], complete)}
                offset = next(e["offset_m"] for e in scene["entities"] if e.get("facility_id") == template["target_id"] and e.get("layer") == "protected")
                evidence["maximum_protected_depth_m"] = float(np.maximum(offset - distance[:, i], 0).max())
            if template.get("abort_observation"):
                from scripts.audit_v07_abort_facts import independent_abort
                ref = template["references"][a]
                abort_facts, abort_checks = independent_abort(t, p[:, i], distance[:, i], layer, ref["endpoint_enu_m"], template["terminal_radius_m"], complete)
                abort_checks.pop("abort_reached_retreat")
                abort_checks["abort_ended_outside_warning"] = bool(layer[-1] == 0) if complete else None
                abort_facts["approached_then_withdrew"] = all(x is True for x in abort_checks.values())
                checks.update(abort_checks); abort_values.extend(abort_checks.values()); evidence["abort_observation"] = abort_facts
                core = confirm = None
            if kind != "intrusion" or template.get("abort_observation"):
                checks["ended_outside_warning"] = bool(layer[-1] == 0) if complete else None
            violations = np.any(layer > cfg["exclusion_max_layer"][template["role"]])
            for j in range(len(fids)):
                if j != target: violations |= np.any(levels[:, i, j] > cfg["exclusion_max_layer"]["other_facilities"])
            checks["exclusion_policy_respected"] = negative(bool(violations), complete)
            if kind != "close_observation": confirm = core
            events[a] = None if core is None else float(t[core] / 1e6)
            headings[a] = _approach_heading_deg(xy, first_warning, cfg["approach"]["heading_distance_m"])
            lag = round(cfg["diagnostics"]["reversal_lag_s"] * 10)
            reversal = np.zeros(len(t), bool); speed = np.linalg.norm(v[:, i], axis=1)
            if len(t) > lag:
                headings_all = np.degrees(np.arctan2(v[:, i, 1], v[:, i, 0]))
                angles = np.abs((headings_all[lag:] - headings_all[:-lag] + 180) % 360 - 180)
                enough = speed >= cfg["detectors"]["revisit"]["min_speed_m_s"]
                reversal[lag:] = selected[lag:] & selected[:-lag] & enough[lag:] & enough[:-lag] & (angles >= cfg["diagnostics"]["reversal_angle_deg"])
            reversals = _runs(reversal)
            evidence.update(work_reversal_count=len(reversals), work_reversal_start_frames=[int(b) for b, e in reversals])
            status = outcome(checks); statuses.append(status)
            agent_expected[a] = {"result": {"status": status, "conditions": checks}, "core_event": {
                "raw_event_type": raw, "t_s": events[a], "frame_index": core,
                "t_confirm": None if confirm is None else float(t[confirm] / 1e6), "confirm_frame_index": confirm},
                "contribution": evidence, "hard_obstacle_sample_count": int(blocked[:, i].sum()), "outside_world_sample_count": int(outside[:, i].sum())}
        group_checks = {"member_contributions_complete": False if "failure" in statuses else None if "unknown" in statuses else True}
        shared = None
        if footprints:
            union = np.any(footprints, axis=0); fraction = float(union.mean()) if len(union) else 0.
            shared = {"grid_point_count": len(union), "covered_grid_point_count": int(union.sum()), "coverage_fraction": fraction,
                      "required_fraction": cfg["detectors"]["coverage"]["min_group_fraction"]}
            group_checks["shared_coverage"] = positive(fraction >= shared["required_fraction"], complete)
        if abort_values: group_checks["abort_group_withdrawal_observed"] = False if False in abort_values else None if None in abort_values else True
        span = _heading_span_deg(list(headings.values()))
        approach = ("unknown" if span is None else "same_direction" if span <= cfg["approach"]["same_max_deg"] else
                    "multi_direction" if span >= cfg["approach"]["multi_min_deg"] else "intermediate")
        from scripts.audit_v07_s2_groups import independent_coordination
        classification, batches = independent_coordination(events, cfg["coordination"]["sync_window_s"], cfg["coordination"]["batch_split_gap_s"])
        group_expected[gid] = {"result": {"status": outcome(group_checks), "conditions": group_checks},
            "shared_coverage": shared, "approach_headings_deg": headings, "approach_span_deg": span, "approach_classification": approach,
            "coordination": {"classification": classification, "event_times_s": events}, "batch_members": batches}
    states = [g["result"]["status"] for g in group_expected.values()]
    all_groups = False if "failure" in states else None if "unknown" in states else True
    primary = all_groups
    if "group_skeletons" in task and task["base_intent"] == "penetration":
        state = group_expected[task["main_group_id"]]["result"]["status"]
        primary = True if state == "success" else False if state == "failure" else None
    cluster = {"status": "unknown" if primary is None else "success" if primary else "failure",
               "primary_task_success": primary, "all_groups_complete": all_groups}
    minimum = min((float(np.linalg.norm(p[:, i] - p[:, j], axis=1).min()) for i, j in combinations(range(len(ids)), 2)), default=None)
    collision = minimum is not None and minimum < cfg["quality"]["min_separation_error_m"]
    restricted = bool(blocked.any())
    quality = {"status": cfg["quality"]["restricted_zone_entry"] if restricted else "generation_error" if collision else "valid",
        "retained": not collision and not restricted, "exclusion_reasons": (["minimum_separation_below_2m"] if collision else []) + (["restricted_zone_entry"] if restricted else []),
        "minimum_separation_m": minimum, "hard_obstacle_sample_count": int(blocked.sum()), "outside_world_sample_count": int(outside.sum())}
    return {"agents": agent_expected, "groups": group_expected, "cluster": cluster, "quality": quality,
            "facility_ids": fids, "levels": levels, "target_levels": target_layers, "blocked": blocked}


def audit_data(scene, task, run, labels, frame):
    expected = independently_measure(scene, task, run, labels["evidence"]["complete_observation"])
    errors = []
    def compare(path, actual, wanted):
        if isinstance(wanted, dict):
            if not isinstance(actual, dict):
                errors.append({"field": path, "label": actual, "independent": wanted}); return
            for key, value in wanted.items():
                if key not in actual: errors.append({"field": path + "." + key, "error": "missing field"})
                else: compare(path + "." + key, actual[key], value)
        elif not _equal(actual, wanted): errors.append({"field": path, "label": actual, "independent": wanted})
    for a, wanted in expected["agents"].items():
        ob = labels["agents"][a]["observed"]
        compare(a + ".result", labels["agents"][a]["result"], wanted["result"])
        if set(labels["agents"][a]["result"]["conditions"]) != set(wanted["result"]["conditions"]): errors.append({"field": a + ".condition_keys"})
        for key in ("core_event", "contribution", "hard_obstacle_sample_count", "outside_world_sample_count"):
            compare(a + "." + key, ob.get(key), wanted[key])
    for gid, wanted in expected["groups"].items():
        group = labels["task_groups"][gid]
        compare(gid + ".result", group["result"], wanted["result"])
        if set(group["result"]["conditions"]) != set(wanted["result"]["conditions"]): errors.append({"field": gid + ".condition_keys"})
        for key in ("shared_coverage", "approach_headings_deg", "approach_span_deg", "approach_classification", "coordination"):
            compare(gid + "." + key, group["observed"].get(key), wanted[key])
        compare(gid + ".batch_members", [b["members"] for b in group["observed"]["coordination"]["batches"]], wanted["batch_members"])
    compare("cluster.result", labels["cluster"]["result"], expected["cluster"])
    compare("generation_quality", labels["generation_quality"], expected["quality"])
    order = [expected["facility_ids"].index(f) for f in frame["facility_ids"].tolist()]
    region_diff = int(np.count_nonzero(frame["region_all_facilities"] != expected["levels"][:, :, order]))
    target_diff = int(np.count_nonzero(frame["region_assigned_target"] != expected["target_levels"]))
    if not np.array_equal(frame["inside_hard_obstacle"], expected["blocked"]): errors.append({"field": "inside_hard_obstacle"})
    if frame["agent_ids"].tolist() != list(run["agent_ids"]) or not np.array_equal(frame["time_us"], run["time_us"]):
        errors.append({"field": "frame_axes"})
    return {"status": "P0_STOP" if errors or region_diff or target_diff else "PASS", "frames": len(run["time_us"]),
        "agents": len(run["agent_ids"]), "facilities": len(order), "all_facility_frame_comparisons": int(expected["levels"].size),
        "region_difference_count": region_diff, "target_difference_count": target_diff,
        "event_or_metric_difference_count": len(errors), "event_or_metric_witnesses": errors,
        "uncovered_conditions": [e for e in errors if e["field"].endswith("condition_keys")],
        "method": "independent criteria-r1 detectors, role predicates, event confirmation, group/cluster composition and quality",
        "independent_role_facts": expected["agents"]}


def audit_episode(root):
    root = Path(root)
    scene, task, labels = (_read(root / name) for name in ("public_scene.json", "task.json", "labels.json"))
    ids, t, p, v = _load_truth(root)
    with np.load(root / "frame_labels.npz", allow_pickle=False) as stored:
        frame = {key: stored[key].copy() for key in stored.files}
    return audit_data(scene, task, {"agent_ids": ids, "time_us": t, "p": p, "v": v}, labels, frame)
