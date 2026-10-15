"""criteria/0.7-r1 labels; the vertical-slice implementation stays in labels.py."""
from itertools import combinations
import numpy as np
from scene_v07.geometry import center_of
from .criteria import load_criteria
from .detectors import coverage, dwell, revisit, runs, work_mask
from .geometry import geometry_facts, GEOMETRY_VERSION


def measure_criteria(scene, skeleton, run, mode, planned_batches=None, *, cutoff_s=None, timing_plan=None):
    from .labels import (role_kind, validate_grid, event, measurable, bounded,
                         observed_conditions_result, coordination, approach_heading_deg,
                         heading_span_deg, EVIDENCE_SOURCE, EXPANSION_LABEL_VERSION)
    cfg = load_criteria()
    ids = list(run["agent_ids"])
    t, p, v = (np.asarray(run[k]) for k in ("time_us", "p", "v"))
    complete = cutoff_s is None and run["execution_status"] in ("completed", "timeout")
    if cutoff_s is not None:
        take = t < round(cutoff_s * 1e6)
        t, p, v = t[take], p[take], v[take]
    validate_grid(t, p, v, ids)
    facilities = sorted((e for e in scene["entities"] if e["type"] == "facility"), key=lambda e: e["id"])
    fids = [e["id"] for e in facilities]
    target = fids.index(skeleton["target_id"])
    center = np.asarray(center_of(facilities[target]["geometry"]))
    facts = []
    for facility in facilities:
        offsets = {e["layer"]: e["offset_m"] for e in scene["entities"] if e.get("facility_id") == facility["id"]}
        facts.append(geometry_facts(facility["geometry"], p[:, :, :2], layer_offsets=offsets))
    levels = np.stack([f["layer"] for f in facts], axis=-1)
    obstacle = np.zeros(p.shape[:2], bool)
    for entity in scene["entities"]:
        if entity["type"] == "hard_constraint_obstacle":
            obstacle |= geometry_facts(entity["geometry"], p[:, :, :2])["inside"]
    outside = ~geometry_facts(scene["world"]["geometry"], p[:, :, :2])["inside"]
    minimum, closest = None, None
    minima = {a: None for a in ids}
    for a, b in combinations(sorted(ids), 2):
        distance = np.linalg.norm(p[:, ids.index(a)] - p[:, ids.index(b)], axis=1)
        k = int(np.argmin(distance)); value = float(distance[k])
        if minimum is None or value < minimum:
            minimum, closest = value, {"agents": [a, b], "t_s": float(t[k] / 1e6), "frame_index": k}
        for member in (a, b):
            minima[member] = value if minima[member] is None else min(minima[member], value)
    agents, events, headings, covered = {}, {}, {}, []
    phases = np.zeros(p.shape[:2], np.int8)
    kind = role_kind(skeleton)
    patrol_masks, patrol_angles = {}, {}
    for a in sorted(ids):
        i = ids.index(a); xy = p[:, i, :2]; speed = np.linalg.norm(v[:, i], axis=1)
        target_levels = levels[:, i, target]; distance = facts[target]["signed_distance_m"][:, i]
        work = work_mask(target_levels)
        dwelling = dwell(xy, t, work, cfg)
        observation = dwell(xy, t, target_levels == 1, cfg) if kind == "close_observation" else None
        revisiting = revisit(xy, v[:, i], t, target_levels, work, center, cfg)
        warning = event(target_levels >= 1, t, "enter_warning_zone")
        headings[a] = approach_heading_deg(xy, warning["frame_index"], cfg["approach"]["heading_distance_m"])
        contribution = {"dwell": dwelling, "revisit": revisiting}
        checks = {}
        behavior = []
        if kind == "transit":
            events[a] = warning
            visits = runs(target_levels >= 1)
            checks = {"entered_warning": measurable(bool(visits), complete),
                      "single_warning_visit": False if len(visits) > 1 else measurable(len(visits) == 1, complete),
                      "no_dwell": bounded(dwelling["detected"], complete),
                      "no_revisit": bounded(revisiting["detected"], complete)}
            if visits: behavior.append("entered_warning_zone")
        elif kind == "area_search":
            seen = coverage(xy, speed, target_levels, obstacle[:, i], skeleton["survey"], cfg)
            effective = seen["effective_mask"]
            covered.append(seen["covered_mask"])
            events[a] = event(effective, t, "scan_start")
            checks = {"effective_observation": measurable(bool(effective.any()), complete),
                      "no_revisit": bounded(revisiting["detected"], complete)}
            contribution.update(covered_group_grid_points=int(seen["covered_mask"].sum()),
                                group_grid_point_count=seen["grid_point_count"],
                                effective_observation_duration_s=float(effective.sum()) / 10)
            if effective.any(): behavior.append("effective_area_observation")
        elif kind == "close_observation":
            mask = np.zeros(len(t), bool)
            if observation["detected"]: mask[observation["frame_index"]] = True
            events[a] = event(mask, t, "observation_point_arrival")
            contribution["observation_dwell"] = observation
            checks = {"observation_dwell": measurable(observation["detected"], complete),
                      "no_revisit": bounded(revisiting["detected"], complete)}
            if observation["detected"]: behavior.append("close_observation_observed")
        elif kind == "monitoring":
            events[a] = warning
            checks = {"patrol_revisit": measurable(revisiting["detected"], complete)}
            if revisiting["detected"]: behavior.append("patrol_revisit_observed")
        elif kind == "feint":
            events[a] = event(target_levels >= 2, t, "enter_alert_zone")
            visits = runs(target_levels >= 2)
            checks = {"entered_alert": measurable(bool((target_levels == 2).any()), complete),
                      "single_alert_visit": False if len(visits) > 1 else measurable(len(visits) == 1, complete)}
            if visits: behavior.append("entered_alert_zone")
        else:
            events[a] = event(target_levels == 3, t, "enter_protected_zone")
            checks = {"entered_protected": measurable(bool((target_levels == 3).any()), complete),
                      "near_facility_contour": measurable(float(distance.min()) <= cfg["roles"]["intrusion"]["max_contour_distance_m"], complete)}
            if (target_levels == 3).any(): behavior.append("entered_protected_zone")
        if skeleton.get("abort_observation"):
            from .expansion.abort_measurement import observed_abort
            ref = skeleton["references"][a]
            abort_facts, abort_checks = observed_abort(t, p[:, i], distance, target_levels,
                np.asarray(ref["endpoint_enu_m"]), skeleton["terminal_radius_m"], complete, require_retreat=False)
            contribution["abort_observation"] = abort_facts
            checks.update(abort_checks)
            # An aborted intrusion remains an unsuccessful assigned intrusion;
            # withdrawal validity is reported separately, with no core event.
            events[a] = event(np.zeros(len(t), bool), t, "enter_protected_zone")
            if abort_facts["approached_then_withdrew"]: behavior.append("approached_then_withdrew")
        if kind != "intrusion" or skeleton.get("abort_observation"):
            checks["ended_outside_warning"] = bool(target_levels[-1] == 0) if complete else None
        events[a]["t_confirm"] = (observation["t_confirm"] if kind == "close_observation" and not skeleton.get("abort_observation")
                                  else events[a]["t_s"])
        events[a]["confirm_frame_index"] = (observation["confirm_frame_index"] if kind == "close_observation" and not skeleton.get("abort_observation")
                                             else events[a]["frame_index"])
        limit = cfg["exclusion_max_layer"][skeleton["role"]]
        forbidden = target_levels > limit
        for j in range(len(fids)):
            if j != target: forbidden |= levels[:, i, j] > cfg["exclusion_max_layer"]["other_facilities"]
        checks["exclusion_policy_respected"] = bounded(bool(forbidden.any()), complete)
        regions = {}
        for j, fid in enumerate(fids):
            regions[fid] = {}
            for name, code in (("warning", 1), ("alert", 2), ("protected", 3)):
                hit = event(levels[:, i, j] >= code, t, "enter_" + name + "_zone")
                regions[fid][name] = {"entered_observed": hit["t_s"] is not None,
                                     "first_entry_s": hit["t_s"], "sample_count": int((levels[:, i, j] >= code).sum())}
        inside_frames = np.flatnonzero(target_levels >= 1)
        end = (int(inside_frames[-1]) + 1 if len(inside_frames) and inside_frames[-1] < len(t) - 1 else None)
        work_end = None if end is None else float(t[end] / 1e6)
        from .criteria_diagnostics import role_diagnostics, group_revisit_diagnostic
        metrics, extra, terminal = role_diagnostics(kind, skeleton, a, t, p[:, i], v[:, i], target_levels,
            distance, center, work, cfg, events[a], work_end)
        if kind == "intrusion":
            metrics["maximum_protected_depth_m"] = float(facts[target]["protected_depth_m"][:, i].max())
        if kind == "feint":
            offsets = {e["layer"]: e["offset_m"] for e in scene["entities"] if e.get("facility_id") == skeleton["target_id"]}
            band = target_levels == 2
            depth = float(np.maximum(offsets["alert"] - distance, 0)[band].max()) if band.any() else 0.
            metrics.update(max_depth_in_alert_m=round(depth, 3),
                           depth_fraction_in_alert_band=round(depth / (offsets["alert"] - offsets["protected"]), 3))
        if kind == "monitoring":
            patrol_masks[a] = extra.pop("_patrol_mask"); patrol_angles[a] = extra.pop("_patrol_angles")
        contribution.update(metrics, dwell_total_duration_s=dwelling["total_duration_s"])
        phases[:, i] = np.where(speed >= cfg["detectors"]["coverage"]["effective_speed_min_m_s"], 1, 0)
        if events[a]["frame_index"] is not None: phases[events[a]["frame_index"]:, i] = 2
        if end is not None: phases[end:, i] = 3
        phases[terminal, i] = 4
        agents[a] = {"assigned": {"intent": skeleton["base_intent"], "role": skeleton["role"],
            "target": skeleton["target_id"], "task_group": skeleton["group_id"],
            "execution_method": skeleton["execution_method"], "planned_coordination": mode,
            "timing": None if timing_plan is None else {key: timing_plan[key][a] for key in
                ("target_event_times_s", "target_event_times_grid_s", "jitter_s", "departure_delays_s", "batch_by_agent")}},
            "observed": {"behaviors": behavior, "regions_by_facility": regions, "core_event": events[a],
                "contribution": contribution, "work_end_s": work_end, "batch_index": None,
                "minimum_separation_m": minima[a], "hard_obstacle_sample_count": int(obstacle[:, i].sum()),
                "outside_world_sample_count": int(outside[:, i].sum()), **extra},
            "result": {"status": observed_conditions_result(checks, complete), "conditions": checks}}
    coord = coordination(events, **cfg["coordination"])
    for batch in coord["batches"]:
        for a in batch["members"]: agents[a]["observed"]["batch_index"] = batch["batch_index"]
    statuses = [a["result"]["status"] for a in agents.values()]
    group_checks = {"member_contributions_complete": False if "failure" in statuses else None if "unknown" in statuses else True}
    shared = None
    if covered:
        union = np.logical_or.reduce(covered); survey = skeleton["survey"]
        shared = {"model": survey["model"], "assumptions": survey["assumptions"],
            "footprint_radius_m": survey["footprint_radius_m"], "grid_spacing_m": survey["grid_spacing_m"],
            "grid_point_count": len(union), "covered_grid_point_count": int(union.sum()),
            "coverage_fraction": float(union.mean()) if len(union) else 0.,
            "required_fraction": cfg["detectors"]["coverage"]["min_group_fraction"],
            "declared_region_area_m2": survey.get("area_m2"), "planned_strip_count": survey.get("strip_count")}
        group_checks["shared_coverage"] = measurable(shared["coverage_fraction"] >= shared["required_fraction"], complete)
    if skeleton.get("abort_observation"):
        values = [v for a in agents.values() for k, v in a["result"]["conditions"].items() if k.startswith("abort_")]
        group_checks["abort_group_withdrawal_observed"] = False if False in values else None if None in values else True
    timing = {"coordination_matches_assignment": None if coord["classification"] == "unknown" else coord["classification"] == mode,
              "batch_members_match_assignment": None}
    if planned_batches is not None and coord["classification"] not in ("unknown", "not_applicable"):
        timing["batch_members_match_assignment"] = {frozenset(b["members"]) for b in coord["batches"]} == {
            frozenset(a for a, b in planned_batches.items() if b == index) for index in set(planned_batches.values())}
    group = {"assigned": {"members": sorted(ids), "role": skeleton["role"], "target": skeleton["target_id"],
                 "intent": skeleton["base_intent"], "planned_coordination": mode, "planned_batches": planned_batches or {},
                 "execution_method": skeleton["execution_method"], "approach_mode": skeleton.get("approach_mode"), "timing": timing_plan},
             "observed": {"members": sorted(ids), "coordination": coord, "timing_diagnostics": timing, "shared_coverage": shared,
                 "work_area_center_m": center.tolist(), "approach_headings_deg": headings,
                 "approach_span_deg": heading_span_deg(list(headings.values())),
                 "members_with_known_core_event": sorted(a for a, e in events.items() if e["t_s"] is not None),
                 "behaviors": sorted({b for a in agents.values() for b in a["observed"]["behaviors"]})},
             "result": {"status": observed_conditions_result(group_checks, complete), "conditions": group_checks}}
    related = sorted(fid for j, fid in enumerate(fids) if (levels[:, :, j] >= 1).any())
    if kind == "monitoring":
        group["observed"]["shared_revisit"] = group_revisit_diagnostic(skeleton, t / 1e6, patrol_masks, patrol_angles)
    threshold = cfg["quality"]["min_separation_error_m"]
    error = minimum is not None and minimum < threshold
    labels = {"schema_version": EXPANSION_LABEL_VERSION,
        "evidence": {"source": EVIDENCE_SOURCE, "last_observed_s": float(t[-1] / 1e6), "frame_count": len(t),
            "complete_observation": complete, "future_events_used": False, "geometry_version": GEOMETRY_VERSION,
            "criteria_version": cfg["criteria_version"]}, "agents": agents, "task_groups": {skeleton["group_id"]: group},
        "cluster": {"assigned": {"intent": skeleton["base_intent"], "target_set": [skeleton["target_id"]],
            "task_groups": [skeleton["group_id"]], "planned_coordination": mode, "timing_by_group": {skeleton["group_id"]: timing_plan}},
            "observed": {"related_facilities": related, "primary_target": skeleton["target_id"] if all(e["t_s"] is not None for e in events.values()) else None,
                "group_coordination": [{"group_id": skeleton["group_id"], **coord}], "minimum_separation_m": minimum, "closest_pair": closest},
            "result": dict(group["result"])},
        "frame_labels": {"file": "frame_labels.npz", "source": EVIDENCE_SOURCE, "agent_ids": ids, "facility_ids": fids,
            "region_codes": {"0": "outside", "1": "warning", "2": "alert", "3": "protected"},
            "phase_codes": {"0": "low_speed", "1": "approach_motion", "2": "after_core_start", "3": "withdrawal", "4": "at_own_endpoint"}},
        "generation_quality": {"status": "generation_error" if error else "valid", "retained": not error,
            "exclusion_reasons": ["minimum_separation_below_2m"] if error else [], "minimum_separation_m": minimum,
            "separation_error_threshold_m": threshold, "separation_affects_task_result": False,
            "hard_obstacle_sample_count": int(obstacle.sum()), "outside_world_sample_count": int(outside.sum())}}
    frame = {"time_us": t, "agent_ids": np.array(ids), "facility_ids": np.array(fids),
             "region_all_facilities": levels, "region_assigned_target": levels[:, :, target],
             "phase": phases, "inside_hard_obstacle": obstacle}
    return labels, frame
