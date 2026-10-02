"""Manifest-bound, channel-independent visible facts for the v0.5 language layer.

Task labels and simulated model metrics are deliberately kept apart from facts
obtained from the two exported position streams.  A fact which the FCU stream
does not corroborate is withheld rather than silently replaced with SIM truth.
"""

import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

from .episode_loader import load_episode
from .mission_evaluation import window_evidence


FACTS_VERSION = "observer_facts_v0"
PATTERN_VERSION = "pattern_detector_v0"
PATTERN_PARAMETERS = dict(perimeter_sample_fraction=0.80, full_lap_radians=2 * math.pi,
                          perimeter_visit_radius_m=3.0,
                          region_buffer_m=1.0, parallel_sample_fraction=0.80,
                          straight_path_fraction=0.60, direction_tolerance_deg=15.0,
                          minimum_straight_run_m=2.0)
EPS = 1e-8


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _traces(path, agents):
    """Read a hashed exported stream without treating invalid rows as positions."""
    result = {agent: [] for agent in agents}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"t_s", "agent_id", "valid", "east_m", "north_m", "up_m"}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError(f"missing position columns: {path.name}")
        for row in reader:
            agent = row["agent_id"]
            if agent not in result:
                raise ValueError(f"unexpected agent in {path.name}")
            try:
                stamp = float(row["t_s"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid time in {path.name}") from exc
            if not _finite(stamp) or stamp < 0 or row["valid"] not in ("0", "1"):
                raise ValueError(f"invalid sample in {path.name}")
            values = None
            if row["valid"] == "1":
                try:
                    values = [float(row[key]) for key in ("east_m", "north_m", "up_m")]
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"invalid position in {path.name}") from exc
                if not all(_finite(value) for value in values):
                    raise ValueError(f"nonfinite position in {path.name}")
            rows = result[agent]
            if rows and stamp <= rows[-1][0]:
                raise ValueError(f"nonmonotonic {path.name} time")
            rows.append((stamp, values))
    return result


def _point_at(rows, stamp, max_gap):
    if not _finite(stamp):
        return None
    for index, (time, point) in enumerate(rows):
        if abs(time - stamp) <= EPS:
            return point
        if time > stamp:
            if not index:
                return None
            before, left = rows[index - 1]
            if left is None or point is None or time - before > max_gap + EPS:
                return None
            fraction = (stamp - before) / (time - before)
            return [left[k] + fraction * (point[k] - left[k]) for k in range(3)]
    return None


def _window_by_agent(windows, semantic_phase, agents):
    selected = [window for window in windows if window.get("semantic_phase") == semantic_phase]
    if len(selected) != len(agents) or {window.get("agent_id") for window in selected} != set(agents):
        return None
    return {window["agent_id"]: window for window in selected}


def _region(task):
    mission = task["mission"]
    regions = [region for region in task["scenario"]["regions"]
               if region["id"] == mission["target_region_id"]]
    if len(regions) != 1:
        raise ValueError("target region is not unique")
    return regions[0]


def _entry_side(traces, windows, region, agents, max_gap):
    approach = _window_by_agent(windows, "approach", agents)
    if approach is None:
        return None
    points = [_point_at(traces[agent], approach[agent].get("start_s"), max_gap)
              for agent in agents]
    if any(point is None for point in points):
        return None
    east = statistics.mean(point[0] for point in points)
    north = statistics.mean(point[1] for point in points)
    dx = east - (region["min_east_m"] + region["width_m"] / 2)
    dy = north - (region["min_north_m"] + region["height_m"] / 2)
    if max(abs(dx), abs(dy)) <= EPS:
        return None
    return ("east" if dx >= 0 else "west") if abs(dx) >= abs(dy) else ("north" if dy >= 0 else "south")


def _main_points(traces, windows, agents, main_phase, max_gap):
    selected = _window_by_agent(windows, main_phase, agents)
    if selected is None:
        return {}
    points = {}
    for agent in agents:
        window = selected[agent]
        start, end = window.get("start_s"), window.get("arrival_s")
        if not _finite(start) or not _finite(end) or end <= start or window.get("complete_execution_window") is not True:
            return {}
        evidence = window_evidence(traces[agent], start, end, max_gap)
        if not evidence["complete"]:
            return {}
        ordered = sorted(evidence["points"], key=lambda row: row[0])
        distinct = []
        for time, point in ordered:
            if not distinct or time > distinct[-1][0] + EPS:
                distinct.append((time, point))
        if len(distinct) < 3:
            return {}
        points[agent] = distinct
    return points


def _distance_to_edge(point, region, standoff):
    left = region["min_east_m"] - standoff
    right = region["min_east_m"] + region["width_m"] + standoff
    bottom = region["min_north_m"] - standoff
    top = region["min_north_m"] + region["height_m"] + standoff
    x, y = point[:2]
    return min(math.hypot(x - max(left, min(right, x)), y - bottom),
               math.hypot(x - right, y - max(bottom, min(top, y))),
               math.hypot(x - max(left, min(right, x)), y - top),
               math.hypot(x - left, y - max(bottom, min(top, y))))


def _angular_travel(points, center):
    bearings = [math.atan2(point[1] - center[1], point[0] - center[0]) for _, point in points]
    return sum((right - left + math.pi) % (2 * math.pi) - math.pi
               for left, right in zip(bearings, bearings[1:]))


def _angular_distance(left, right):
    return abs((left - right + math.pi / 2) % math.pi - math.pi / 2)


def _straight_evidence(points_by_agent):
    increments = []
    for agent, rows in points_by_agent.items():
        local = []
        for (t0, first), (t1, second) in zip(rows, rows[1:]):
            dx, dy = second[0] - first[0], second[1] - first[1]
            length = math.hypot(dx, dy)
            if length > 0.05:
                local.append((agent, t0, length, math.atan2(dy, dx), t1))
        increments.extend(local)
    total = sum(row[2] for row in increments)
    if total <= EPS:
        return None, 0.0, False
    tolerance = math.radians(PATTERN_PARAMETERS["direction_tolerance_deg"])
    # Maximum weighted support over measured headings, with no planned axis.
    candidates = sorted({row[3] % math.pi for row in increments})
    heading = max(candidates, key=lambda angle: (sum(row[2] for row in increments
                                                     if _angular_distance(row[3], angle) <= tolerance), -angle))
    fraction = sum(row[2] for row in increments if _angular_distance(row[3], heading) <= tolerance) / total
    # Straight runs must actually alternate direction.  Tiny jitter cannot
    # manufacture an apparent reversal.
    alternates = False
    for agent in points_by_agent:
        rows = [row for row in increments if row[0] == agent]
        runs = []
        sign, length = None, 0.0
        for _, _, delta, angle, _ in rows:
            aligned = _angular_distance(angle, heading) <= tolerance
            direction = (1 if math.cos(angle - heading) >= 0 else -1) if aligned else None
            if direction == sign and direction is not None:
                length += delta
            else:
                if sign is not None and length >= PATTERN_PARAMETERS["minimum_straight_run_m"]:
                    runs.append(sign)
                sign, length = direction, delta if direction is not None else 0.0
        if sign is not None and length >= PATTERN_PARAMETERS["minimum_straight_run_m"]:
            runs.append(sign)
        if any(before != after for before, after in zip(runs, runs[1:])):
            alternates = True
    return heading, fraction, alternates


def detect_pattern(points_by_agent, region, visit_radius_m=3.0, standoff_m=0.0):
    """Classify measured main-phase geometry without using an intent label."""
    result = dict(observed_pattern="unclear", scan_orientation=None, loop_direction=None)
    if not points_by_agent or any(len(rows) < 3 for rows in points_by_agent.values()):
        return result
    all_points = [point for rows in points_by_agent.values() for _, point in rows]
    center = (region["min_east_m"] + region["width_m"] / 2,
              region["min_north_m"] + region["height_m"] / 2)
    if _finite(visit_radius_m) and visit_radius_m > 0:
        fraction = sum(_distance_to_edge(point, region, standoff_m) <= visit_radius_m + EPS
                       for point in all_points) / len(all_points)
        travel = [_angular_travel(rows, center) for rows in points_by_agent.values()]
        if (fraction >= PATTERN_PARAMETERS["perimeter_sample_fraction"]
                and statistics.median(abs(value) for value in travel) + EPS >= PATTERN_PARAMETERS["full_lap_radians"]):
            result["observed_pattern"] = "perimeter_loop"
            direction = statistics.median(travel)
            result["loop_direction"] = "ccw" if direction > 0 else "cw" if direction < 0 else None
            return result
    buffer = PATTERN_PARAMETERS["region_buffer_m"]
    inside = sum(region["min_east_m"] - buffer <= point[0] <= region["min_east_m"] + region["width_m"] + buffer
                 and region["min_north_m"] - buffer <= point[1] <= region["min_north_m"] + region["height_m"] + buffer
                 for point in all_points) / len(all_points)
    heading, straight_fraction, alternating = _straight_evidence(points_by_agent)
    if heading is not None and straight_fraction >= PATTERN_PARAMETERS["straight_path_fraction"]:
        angle = heading % math.pi
        tolerance = math.radians(PATTERN_PARAMETERS["direction_tolerance_deg"])
        if min(angle, math.pi - angle) <= tolerance:
            result["scan_orientation"] = "east_west"
        elif abs(angle - math.pi / 2) <= tolerance:
            result["scan_orientation"] = "north_south"
        else:
            result["scan_orientation"] = "oblique"
    if (inside >= PATTERN_PARAMETERS["parallel_sample_fraction"]
            and straight_fraction >= PATTERN_PARAMETERS["straight_path_fraction"] and alternating):
        result["observed_pattern"] = "parallel_strips"
    return result


def _return_observed(traces, windows, agents, main_phase, max_gap, duration_s, record_hz):
    main = _window_by_agent(windows, main_phase, agents)
    approach = _window_by_agent(windows, "approach", agents)
    if main is None or approach is None or not _finite(duration_s):
        return None
    outcomes = []
    for agent in agents:
        home = _point_at(traces[agent], approach[agent].get("start_s"), max_gap)
        start = main[agent].get("arrival_s")
        if home is None or not _finite(start) or duration_s < start or main[agent].get("complete_execution_window") is not True:
            return None
        # The exported 10 Hz grid is floored at mission end.  Its last sample
        # may be strictly less than one tick before that end.  A full missing
        # tick is not complete proof that no return happened afterward.
        final_valid = next((time for time, point in reversed(traces[agent]) if point is not None), None)
        if final_valid is None or duration_s - final_valid >= 1 / record_hz - EPS:
            return None
        evidence = window_evidence(traces[agent], start, duration_s, max_gap,
                                   edge_allowance=1 / record_hz)
        if not evidence["complete"]:
            return None
        points = sorted(evidence["points"], key=lambda row: row[0])
        if not points:
            return None
        distances = [math.dist(point[:3], home[:3]) for _, point in points]
        if distances[-1] <= 3.0 + EPS:
            outcomes.append(True)
        elif all(distance > 3.0 + EPS for distance in distances):
            outcomes.append(False)
        else:
            outcomes.append(None)
    return True if all(value is True for value in outcomes) else False if False in outcomes else None


def _channel_facts(traces, windows, task, region, manifest, metrics, agents):
    mission, execution = task["mission"], task["execution"]
    main_phase = "patrol" if mission["intent"] == "patrol" else "observe"
    max_gap = execution["max_gap_s"]
    points = _main_points(traces, windows, agents, main_phase, max_gap)
    # The classifier has its own frozen geometric threshold.  Using the
    # patrol-only TaskSpec parameter would make the same physical loop become
    # "unclear" whenever its assigned intent happened to be reconnaissance.
    pattern = detect_pattern(points, region,
                             visit_radius_m=PATTERN_PARAMETERS["perimeter_visit_radius_m"])
    patrol = metrics.get("perimeter_revisit", {})
    laps = patrol.get("per_agent_laps_observed")
    if isinstance(laps, dict) and set(laps) == set(agents) and all(type(laps[agent]) is int and laps[agent] >= 0 for agent in agents):
        laps = [laps[agent] for agent in agents]
    else:
        laps = None
    return dict(num_uavs=sum(sum(point is not None for _, point in traces[agent]) >= 2 for agent in agents),
                entry_side=_entry_side(traces, windows, region, agents, max_gap),
                **pattern, per_agent_laps_observed=laps,
                return_observed=_return_observed(traces, windows, agents, main_phase, max_gap,
                                                 manifest["duration_s"], execution["record_hz"]),
                max_revisit_gap_s=patrol.get("max_revisit_gap_s"))


def _same(left, right):
    if left is None or right is None:
        return left is right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if isinstance(left, float):
        return abs(left - right) <= max(0.5, 0.02 * max(abs(left), abs(right)))
    return left == right


def _compare(field, left, right, checked, disagreements):
    checked.append(field)
    if _same(left, right):
        return left
    disagreements.append(dict(field=field, sim=left, fcu=right,
                              reason="sim_fcu_fact_disagreement"))
    return None


def _segments(windows_by_channel, checked, disagreements):
    channels = windows_by_channel
    phases = list(dict.fromkeys(window["semantic_phase"] for window in channels["truth"]))
    result = []
    for phase in phases:
        selected = {channel: [window for window in channels[channel] if window.get("semantic_phase") == phase]
                    for channel in ("truth", "observation")}
        if not all(selected.values()):
            continue
        values = {}
        for channel in ("truth", "observation"):
            rows = selected[channel]
            starts = [window.get("start_s") for window in rows]
            ends = [window.get("arrival_s") for window in rows]
            values[channel] = (statistics.median(starts) if all(_finite(value) for value in starts) else None,
                               statistics.median(ends) if all(_finite(value) for value in ends) else None)
        ident = f"seg_{phase}"
        start = _compare(f"segments.{ident}.start_s", values["truth"][0], values["observation"][0],
                         checked, disagreements)
        end = _compare(f"segments.{ident}.end_s", values["truth"][1], values["observation"][1],
                       checked, disagreements)
        result.append(dict(id=ident, kind=phase, start_s=start, end_s=end,
                           boundary_source=dict(start="median_per_agent_start_s",
                                                end="median_per_agent_arrival_s")))
    return result


def _events(metrics_by_channel, checked, disagreements):
    result = []
    keys = (("first_boundary_coverage_time_s", "first_boundary_coverage"),
            ("first_complete_lap_time_s", "first_complete_lap"))
    for key, kind in keys:
        left = metrics_by_channel["truth"].get("perimeter_revisit", {}).get(key)
        right = metrics_by_channel["observation"].get("perimeter_revisit", {}).get(key)
        value = _compare(f"events.ev_{kind}.t", left, right, checked, disagreements)
        if _finite(value):
            result.append(dict(id=f"ev_{kind}", kind=kind, t=value,
                               boundary_source="perimeter_revisit_v1"))
    return result


def extract_observer_facts(episode_root: Path, dataset_manifest_sha256: str) -> dict:
    """Compute one episode's facts only from a frozen exported dataset episode."""
    root = Path(episode_root).resolve()
    dataset_path = root.parent.parent / "dataset_manifest.json"
    if not dataset_path.is_file():
        raise ValueError("dataset manifest is required for observer facts")
    actual_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    if actual_hash != dataset_manifest_sha256:
        raise ValueError("dataset manifest changed before fact extraction")
    loaded = load_episode(root, verify_hashes=True)
    manifest = _json(root / "manifest.json")
    if manifest.get("task_kind") != "mission_v3":
        raise ValueError("observer facts require a v3 mission episode")
    agents = loaded["agent_ids"]
    task, labels = _json(root / "task.json"), _json(root / "labels.json")
    semantic = _json(root / "semantic_validation.json")
    phase_windows = _json(root / "phase_windows.json")
    if set(phase_windows.get("channels", {})) != {"truth", "observation"}:
        raise ValueError("observer facts require dual-channel phase windows")
    channels = phase_windows["channels"]
    traces = {"truth": _traces(root / "truth.csv", agents),
              "observation": _traces(root / "observations.csv", agents)}
    region = _region(task)
    metrics = labels["mission_metrics"]
    if set(metrics) != {"truth", "observation"}:
        raise ValueError("observer facts require dual-channel mission metrics")
    checked, disagreements = [], []
    local = {channel: _channel_facts(traces[channel], channels[channel], task, region,
                                     manifest, metrics[channel], agents)
             for channel in ("truth", "observation")}
    observed = {field: _compare(field, local["truth"][field], local["observation"][field],
                                checked, disagreements)
                for field in local["truth"]}
    conditions = semantic.get("condition_results", {}).get("truth", {})
    if task["mission"]["intent"] == "patrol":
        normalized_conditions = {"visits": conditions.get("visits"),
                                 "max_gap": conditions.get("max_gap"),
                                 "return": conditions.get("return_to_launch")}
    else:
        normalized_conditions = {"coverage": conditions.get("coverage"),
                                 "return": conditions.get("return_to_launch")}
    coverage = metrics["truth"].get("coverage") if task["mission"]["intent"] == "reconnaissance" else None
    model = task["mission"]["intent_params"].get("observation_model", {})
    coverage_model = (f"{coverage['model_version']}, r={model['radius_m']}m, grid={coverage['requested_grid_m']}m"
                      if coverage and "model_version" in coverage and "radius_m" in model
                      and "requested_grid_m" in coverage else None)
    if coverage and coverage_model is None:
        raise ValueError("reconnaissance coverage metric lacks model declaration")
    versions = {key: manifest[key] for key in ("semantic_validation_version", "observation_processing_version",
                "duplicate_policy_version", "timeline_policy_version", "clock_model_version",
                "route_progress_version", "ac4_timing_version", "execution_artifacts_version") if key in manifest}
    versions.update(facts_version=FACTS_VERSION, pattern_detector_version=PATTERN_VERSION)
    return dict(facts_version=FACTS_VERSION,
                labels=dict(assigned_intent=labels["assigned_intent"],
                            return_required=task["mission"]["return_required"],
                            mission_result=dict(success=labels["mission_success"],
                                                conditions=normalized_conditions)),
                observed=observed,
                model_metrics=dict(coverage_ratio=coverage.get("global_coverage_ratio") if coverage else None,
                                   coverage_model=coverage_model),
                segments=_segments(channels, checked, disagreements),
                events=_events(metrics, checked, disagreements),
                channel_check=dict(fields_checked=checked, disagreements=disagreements,
                                   enum_policy="exact", continuous_policy="max(2_percent, 0.5_seconds)",
                                   primary_channel="sim", crosscheck_channel="fcu"),
                provenance=dict(primary_channel="sim", dataset_manifest_sha256=actual_hash,
                                versions=versions, pattern_parameters=PATTERN_PARAMETERS))
