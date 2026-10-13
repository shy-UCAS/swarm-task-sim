"""Read-only, family-gated M3 reference selection and paired diagnostics.

The r2 internal split is deliberately separate from the untouched M2-02B holdout.
No function in this module launches SITL or fits dynamics parameters.
"""
from __future__ import annotations

import hashlib
import json
import copy
import csv
import math
from pathlib import Path

import numpy as np

SPLIT_SEED = "2026101205"
SPLIT_ID = "r2_tuning_internal_2026101205_v1"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def partition_families(families, development, seed=SPLIT_SEED):
    families, development = set(families), set(development)
    if not development <= families:
        raise ValueError("development families must belong to the source roster")
    ranked = sorted(families - development,
                    key=lambda f: (hashlib.sha256(f"{seed}|{f}".encode("utf-8")).hexdigest(), f))
    cutoff = 7 * len(ranked) // 10
    if cutoff == 0 or cutoff == len(ranked):
        raise ValueError("not enough families for both groups")
    return dict(development_reference=sorted(development), tuning=ranked[:cutoff],
                internal_holdout=ranked[cutoff:])


def freeze_r2_split(r2, t1, t4, output):
    """Only plan identities are opened; outcomes cannot influence this split."""
    roots = dict(r2=Path(r2).resolve(), t1=Path(t1).resolve(), t4=Path(t4).resolve())
    plans = {name: read_json(root / "plan.json") for name, root in roots.items()}
    development = {r["family_id"] for r in plans["t1"]["tasks"]}
    if development != {r["family_id"] for r in plans["t4"]["tasks"]} or len(development) != 14:
        raise ValueError("T1/T4 must identify the same 14 development families")
    groups = partition_families((r["family_id"] for r in plans["r2"]["tasks"]), development)
    assignments = {f: group for group, families in groups.items() for f in families}
    rows = []
    for task in plans["r2"]["tasks"]:
        row = {k: task[k] for k in ("mission_id", "family_id", "global_index", "shard_id")}
        row.update({k: task["entry"][k] for k in ("task", "task_sha256", "scene_content_sha256", "intent", "flight_pattern")})
        row["group"] = assignments[row["family_id"]]
        rows.append(row)
    result = dict(schema_version=1, split_id=SPLIT_ID, seed=SPLIT_SEED,
                  method="sort by SHA256(UTF8(seed+'|'+family_id)), tie family_id; first floor(7*G/10) tuning",
                  internal_holdout_qualification="internal holdout; not a strict blind test",
                  source_roots={k: str(v) for k, v in roots.items()},
                  plan_sha256={k: sha256(v / "plan.json") for k, v in roots.items()},
                  groups=groups, tasks=rows, status="FROZEN_BEFORE_OUTCOME_ACCESS")
    output = Path(output)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return result


def tuning_tasks(split):
    """Return the allow-list before a caller opens any input or run evidence."""
    if split.get("split_id") != SPLIT_ID or split.get("seed") != SPLIT_SEED:
        raise ValueError("unsupported M3 split; M2-02B must remain sealed")
    tuning = set(split["groups"]["tuning"])
    forbidden = set(split["groups"]["internal_holdout"]) | set(split["groups"]["development_reference"])
    if tuning & forbidden:
        raise ValueError("split groups overlap")
    return [row for row in split["tasks"] if row["family_id"] in tuning and row["group"] == "tuning"]


def final_tuning_attempts(split, batch):
    """Filter ledger rows by tuning identity before examining their results."""
    allowed = {(r["family_id"], r["mission_id"]): r for r in tuning_tasks(split)}
    batch = Path(batch).resolve()
    plan = read_json(batch / "plan.json")
    identity = {(r["family_id"], r["mission_id"]): r for r in plan["tasks"]}
    selected = {}
    for shard in sorted((batch / "shards").glob("shard_*/ledger.json")):
        for row in read_json(shard)["attempts"]:
            key = (row["family_id"], row["mission_id"])
            if key not in allowed:
                continue
            expected, source = allowed[key], identity[key]["entry"]
            if any(expected[k] != source[k] for k in ("task_sha256", "scene_content_sha256")):
                raise ValueError("same-name reference has a different source identity")
            if key not in selected or row["attempt_index"] > selected[key]["attempt_index"]:
                selected[key] = row
    rows = []
    for key, task in sorted(allowed.items()):
        attempt = selected.get(key)
        if attempt is None:
            rows.append(dict(task=task, status="MISSING_ATTEMPT", attempt=None))
            continue
        result = attempt.get("result") or {}
        status = ("INCOMPLETE" if attempt.get("status") != "finished" or result.get("run_status") != "completed"
                  else "ELIGIBLE" if result.get("episode_quality_eligible") is True else "QUALITY_INELIGIBLE")
        rows.append(dict(task=task, status=status, attempt=attempt))
    return rows


def distribution(values):
    values = [float(v) for v in values if v is not None and math.isfinite(v)]
    if not values:
        return dict(n=0, median=None, p90=None, p95=None, minimum=None, maximum=None)
    return dict(n=len(values), median=float(np.median(values)), p90=float(np.percentile(values, 90)),
                p95=float(np.percentile(values, 95)), minimum=min(values), maximum=max(values))


def read_positions(path, agents, transform=lambda t: t):
    rows = {a: [] for a in agents}
    unavailable = 0
    with Path(path).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            t = transform(float(row["t_s"]))
            if t is None:
                unavailable += 1
                continue
            if row["agent_id"] not in rows:
                raise ValueError("unknown trajectory agent")
            p = [float(row[k]) for k in ("east_m", "north_m", "up_m")] if row["valid"] == "1" else None
            if p is not None and not all(math.isfinite(x) for x in p):
                raise ValueError("nonfinite valid position")
            rows[row["agent_id"]].append((t, p))
    if any(any(b[0] <= a[0] for a, b in zip(series, series[1:])) for series in rows.values()):
        raise ValueError("non-increasing trajectory time")
    return rows, unavailable


def mapped_windows(windows, transform):
    result = copy.deepcopy(windows["channels"])
    for rows in result.values():
        for row in rows:
            for name in ("start_s", "arrival_s", "end_s", "phase_release_s"):
                value = row.get(name)
                row[name] = transform(value) if isinstance(value, (int, float)) else None
    return result


def phase_durations(windows):
    result = {}
    for name in dict.fromkeys(w["phase"] for w in windows):
        selected = [w for w in windows if w["phase"] == name]
        starts = [w.get("phase_release_s", w.get("start_s")) for w in selected]
        starts = [w.get("start_s") if s is None else s for w, s in zip(selected, starts)]
        ends = [w.get("end_s") for w in selected]
        result[name] = (max(ends) - min(starts) if all(v is not None for v in starts + ends) else None)
    return result


def interpolate_positions(rows, query, max_gap=.5):
    """Piecewise interpolation never bridges invalid rows or unsupported gaps."""
    query = np.asarray(query, dtype=float)
    result = np.full((len(query), 3), np.nan)
    if not rows:
        return result
    t = np.array([r[0] for r in rows])
    p = np.array([r[1] if r[1] is not None else [np.nan] * 3 for r in rows])
    right = np.searchsorted(t, query, side="left")
    clipped = np.minimum(right, len(t) - 1)
    exact = (right < len(t)) & (np.abs(t[clipped] - query) <= 1e-10)
    result[exact] = p[clipped[exact]]
    valid = (~exact) & (right > 0) & (right < len(t))
    locations = np.flatnonzero(valid)
    j = right[locations]
    locations = locations[(t[j] - t[j - 1]) <= max_gap + 1e-9]
    j = right[locations]
    fraction = (query[locations] - t[j - 1]) / (t[j] - t[j - 1])
    result[locations] = p[j - 1] + fraction[:, None] * (p[j] - p[j - 1])
    return result


def position_speeds(rows, centers, max_gap=.5):
    """Horizontal central displacement over one common simulation second."""
    centers = np.asarray(centers)
    if not rows:
        return np.full(len(centers), np.nan)
    before = interpolate_positions(rows, centers - .5, max_gap)
    after = interpolate_positions(rows, centers + .5, max_gap)
    speed = np.linalg.norm((after - before)[:, :2], axis=1)
    # Endpoint interpolation alone must not conceal an internal missing sample.
    stamps = np.array([r[0] for r in rows])
    missing = np.r_[0, np.cumsum([p is None for _, p in rows])]
    gaps = np.r_[0, np.cumsum(np.diff(stamps) > max_gap + 1e-9)]
    low = np.searchsorted(stamps, centers - .5, side="left")
    high = np.searchsorted(stamps, centers + .5, side="right")
    bad = (missing[high] - missing[low]) > 0
    bounded_low = np.minimum(low, max(0, len(rows) - 1))
    bounded_high = np.maximum(bounded_low, high - 1)
    bad |= (gaps[bounded_high] - gaps[bounded_low]) > 0
    speed[bad] = np.nan
    return speed


def minimum_separation(traces, max_gap=.5):
    """Synchronous piecewise-linear truth; never use per-agent arc alignment."""
    agents = sorted(traces)
    minimum, intervals = None, 0
    for i, left in enumerate(agents):
        for right in agents[i + 1:]:
            a, b = traces[left], traces[right]
            if not a or not b:
                continue
            low, high = max(a[0][0], b[0][0]), min(a[-1][0], b[-1][0])
            knots = sorted({t for rows in (a, b) for t, _ in rows if low <= t <= high})
            relative = interpolate_positions(a, knots, max_gap) - interpolate_positions(b, knots, max_gap)
            midpoints = (np.asarray(knots[:-1]) + np.asarray(knots[1:])) / 2
            supported = np.isfinite(interpolate_positions(a, midpoints, max_gap)).all(axis=1)
            supported &= np.isfinite(interpolate_positions(b, midpoints, max_gap)).all(axis=1)
            for p, q, support in zip(relative, relative[1:], supported):
                if not support or not np.isfinite([p, q]).all():
                    continue
                d = q - p
                f = float(np.clip(-p @ d / (d @ d), 0, 1)) if d @ d > 0 else 0
                distance = float(np.linalg.norm(p + f * d))
                minimum = distance if minimum is None else min(minimum, distance)
                intervals += 1
    return dict(minimum_m=minimum, valid_pair_intervals=intervals,
                method="3D simultaneous piecewise-linear minimum over overlapping valid source-clock support")


def xyz(point):
    return np.array([point[k] for k in ("east_m", "north_m", "up_m")])


def route_diagnostics(scene, traces, windows):
    """Ordered node witnesses constrain each separate leg and repeated lap."""
    from ..ac4_timing import ordered_route_progress_v2
    result, cruise, turns = {}, [], []
    for phase in scene["phases"]:
        roles = scene["semantic_plan"]["execution_phases"][phase["name"]]["agents"]
        for agent in sorted(traces):
            key = phase["name"] + "|" + agent
            candidates = [w for w in windows if w["phase"] == phase["name"] and w["agent_id"] == agent]
            points = [xyz(roles[agent]["start_point"])]
            collapsed = 0
            for point in phase["routes"][agent]:
                p = xyz(point)
                if np.linalg.norm(p - points[-1]) <= 1e-9:
                    collapsed += 1
                else:
                    points.append(p)
            lengths = np.linalg.norm(np.diff(points, axis=0), axis=1) if len(points) > 1 else np.array([])
            entry = dict(planned_length_m=float(sum(lengths)), matched_length_m=0., legs=[],
                         issues=[], collapsed_consecutive_duplicate_nodes=collapsed)
            result[key] = entry
            if len(candidates) != 1 or not len(lengths):
                entry["issues"] = ["no_unique_window_or_no_motion_route"]
                continue
            window = candidates[0]
            start, end = window.get("start_s"), window.get("end_s")
            if start is None or end is None or end <= start:
                entry["issues"] = ["unavailable_phase_clock"]
                continue
            # v0.6 stores a half-open recording: a final phase may end just
            # after the last sample. Limit diagnostics to recorded support,
            # keeping the original phase duration/labels and never extrapolating.
            samples = traces[agent]
            if not samples:
                entry['issues'] = ['no_recorded_positions']
                continue
            recorded_start, recorded_end = max(start, samples[0][0]), min(end, samples[-1][0])
            entry['recorded_domain_s'] = [recorded_start, recorded_end]
            entry['unrecorded_boundary_s'] = [recorded_start-start, end-recorded_end]
            if (recorded_end <= recorded_start
                    or max(entry['unrecorded_boundary_s']) > scene['max_gap_s'] + 1e-9):
                entry['issues'] = ['unsupported_phase_boundary_gap']
                continue
            targets = [dict(east_m=float(p[0]), north_m=float(p[1]), up_m=float(p[2])) for p in points[1:]]
            nominal = np.cumsum(lengths) / phase["speed_m_s"]
            progress = ordered_route_progress_v2(traces[agent], targets, nominal.tolist(), start_s=recorded_start,
                end_s=recorded_end, max_gap_s=scene["max_gap_s"], start_point=roles[agent]["start_point"])
            entry["issues"] = progress["issues"]
            entry["matched_nodes"] = len(progress["nodes"]) - 1
            entry["total_nodes"] = len(targets)
            entry["laps_observed"] = progress.get("per_agent_laps_observed")
            nodes = progress["nodes"]
            for j, (left, right) in enumerate(zip(nodes, nodes[1:])):
                a, b = points[j], points[j + 1]
                delta = b[:2] - a[:2]
                length = float(np.linalg.norm(delta))
                low, high = left["actual_s"], right["actual_s"]
                if length <= 1e-9 or high <= low:
                    continue
                rows = [(t, p) for t, p in traces[agent] if low <= t <= high]
                if (len(rows) < 2 or any(p is None for _, p in rows)
                        or any(b[0] - a[0] > scene['max_gap_s'] + 1e-9 for a, b in zip(rows, rows[1:]))):
                    continue
                positions = np.array([p[:3] for _, p in rows])
                direction = delta / length
                along = (positions[:, :2] - a[:2]) @ direction
                lateral = (positions[:, :2] - a[:2]) @ np.array([-direction[1], direction[0]])
                # First forward envelope: never sort spatial samples across time/laps.
                indices, peak = [], -math.inf
                for k, value in enumerate(along):
                    if value > peak + 1e-9:
                        indices.append(k)
                        peak = value
                reversal = float(np.max(np.maximum.accumulate(along) - along))
                if reversal > .5:
                    entry["issues"].append(f"leg_backtracking:{j}")
                    continue
                leg = dict(index=j, length_m=length, along_m=along[indices].tolist(),
                           lateral_m=lateral[indices].tolist(), node_start_s=low, node_end_s=high)
                entry["legs"].append(leg)
                entry["matched_length_m"] += length
                if phase["semantic_phase"] in ("observe", "patrol", "transit"):
                    times = [t for (t, _), distance in zip(rows, along) if .2 * length <= distance <= .8 * length
                             and start + .5 <= t <= end - .5]
                    if times:
                        cruise.extend(v for v in position_speeds(traces[agent], times, scene["max_gap_s"]) if math.isfinite(v))
                if j + 2 < len(points):
                    next_delta = points[j + 2][:2] - b[:2]
                    next_length = np.linalg.norm(next_delta)
                    if next_length and math.degrees(math.acos(float(np.clip(direction @ next_delta / next_length, -1, 1)))) >= 15:
                        times = [t for t, _ in traces[agent] if max(start + .5, high - 1.) <= t <= min(end - .5, high + 1.)]
                        values = position_speeds(traces[agent], times, scene["max_gap_s"])
                        valid = values[np.isfinite(values)]
                        if len(valid):
                            turns.append(float(min(valid)))
    return dict(routes=result, cruise_speed=distribution(cruise), turn_minimum_speed=distribution(turns),
                planned_length_m=sum(r["planned_length_m"] for r in result.values()),
                matched_length_m=sum(r["matched_length_m"] for r in result.values()))


def pair_lateral(left, right):
    values, matched, planned = [], 0., left["planned_length_m"]
    for key, a in left["routes"].items():
        other = right["routes"].get(key, {})
        by_index = {r["index"]: r for r in other.get("legs", [])}
        for leg in a["legs"]:
            peer = by_index.get(leg["index"])
            if peer is None or len(leg["along_m"]) < 2 or len(peer["along_m"]) < 2:
                continue
            low = max(0., leg["along_m"][0], peer["along_m"][0])
            high = min(leg["length_m"], leg["along_m"][-1], peer["along_m"][-1])
            if high <= low:
                continue
            grid = np.unique(np.r_[np.arange(low, high, .5), high])
            delta = np.abs(np.interp(grid, leg["along_m"], leg["lateral_m"]) -
                           np.interp(grid, peer["along_m"], peer["lateral_m"]))
            values.extend(delta.tolist())
            matched += high - low
    return dict(**distribution(values), mean=float(np.mean(values)) if values else None,
                matched_length_m=matched, planned_length_m=planned,
                matched_fraction=matched / planned if planned > 0 else None,
                method="horizontal normal difference on same phase/agent/ordered leg/lap; 0.5 m arc grid; no time warping for timing/separation")


def summarize_motion(scene, traces, channels, labels, semantic, duration, *, quality_eligible, source):
    from ..observer_facts_v0 import _channel_facts, _region
    agents = sorted(traces["truth"])
    task = scene["task_spec"]
    slots = {channel: _channel_facts(traces[channel], channels[channel], task, _region(task),
                dict(duration_s=duration), labels["mission_metrics"][channel], agents)["observed_pattern"]
             for channel in ("truth", "observation")}
    routes = route_diagnostics(scene, traces["truth"], channels["truth"])
    return dict(source=source, family_id=scene["family_id"], agents=len(agents),
                quality_eligible=quality_eligible, run_status=labels["run_status"],
                mission_success=labels["mission_success"], mission_success_observation=labels["mission_success_observation"],
                condition_results=semantic["condition_results"], motion_slots=slots,
                duration_sim_s=duration, phase_duration_sim_s=phase_durations(channels["truth"]),
                routes=routes, truth_separation=minimum_separation(traces["truth"], scene["max_gap_s"]))


def reference_summary(row, split, batch):
    """Read only the selected tuning attempt, preserving all historical files."""
    from ..tasks import compile_task
    from ..time_contract import CommonTimeAxis
    allowed = {(r["family_id"], r["mission_id"]) for r in tuning_tasks(split)}
    task, attempt = row["task"], row["attempt"]
    if (task["family_id"], task["mission_id"]) not in allowed or row["status"] != "ELIGIBLE":
        raise ValueError("only eligible tuning references may be opened")
    batch = Path(batch).resolve()
    parent = batch / "shards" / f'shard_{attempt["shard_id"]:02d}' / "attempts" / attempt["attempt_id"]
    result = attempt["result"]
    analysis, run = (Path(result[k]).resolve() for k in ("analysis_directory", "run_directory"))
    if not all(path.is_relative_to(parent.resolve()) for path in (analysis, run)):
        raise ValueError("reference paths escape the allowed tuning attempt")
    bindings = {}

    def bound(directory, name, expected):
        path = directory / name
        digest = sha256(path)
        if expected is None or digest != expected:
            raise ValueError(f"reference evidence hash mismatch: {path}")
        bindings[str(path)] = digest
        return path

    manifest_path = analysis / "manifest.json"
    manifest = read_json(bound(analysis, "manifest.json", result["evidence_sha256"].get(str(manifest_path))))
    if manifest["run_id"] != result["run_id"] or manifest.get("family_id") != task["family_id"]:
        raise ValueError("reference manifest identity mismatch")

    def artifact(name):
        return bound(analysis, name, manifest["artifact_sha256"].get(name))

    quality = read_json(artifact("quality.json"))
    if quality.get("episode_quality_eligible") is not True or manifest.get("episode_quality_eligible") is not True:
        raise ValueError("ledger and reference quality disagree")
    scene = read_json(bound(run, "scenario.json", manifest["source_sha256"].get("scenario.json")))
    input_path = batch / "bundle" / task["task"]
    input_task = read_json(bound(input_path.parent, input_path.name, task["task_sha256"]))
    if compile_task(input_task) != scene:
        raise ValueError("P0: current compiled planning differs from saved SITL scene")
    if scene["family_id"] != task["family_id"]:
        raise ValueError("P0: compiled reference family mismatch")
    labels, semantic = read_json(artifact("labels.json")), read_json(artifact("semantic_validation.json"))
    windows, clocks = read_json(artifact("phase_windows.json")), read_json(artifact("clock_models.json"))
    axis = CommonTimeAxis(clocks, manifest["time_epoch_host_s"])
    duration = axis.host(manifest["duration_s"])
    if not axis.available or duration is None or duration <= 0:
        return dict(status="CLOCK_UNAVAILABLE", mission_id=task["mission_id"], family_id=task["family_id"],
                    reference_run=result["run_id"], clock=axis.metadata), scene, input_path
    traces, unavailable = {}, {}
    for channel, name in (("truth", "truth.csv"), ("observation", "observations.csv")):
        traces[channel], unavailable[channel] = read_positions(artifact(name), manifest["agent_ids"], axis.host)
    channels = mapped_windows(windows, axis.host)
    summary = summarize_motion(scene, traces, channels, labels, semantic, duration, quality_eligible=True,
                               source=dict(batch=batch.name, run_id=result["run_id"], analysis=str(analysis)))
    summary.update(status="COMPLETE", mission_id=task["mission_id"], input_task_sha256=task["task_sha256"],
                   clock=axis.metadata, unmapped_position_rows=unavailable,
                   original_host_duration_s=manifest["duration_s"],
                   historical_truth_minimum_m=quality.get("truth_separation", {}).get("minimum_m"),
                   metric_clock_policy="T1 reference inverse, no extrapolation; position-difference speeds; original labels preserved",
                   evidence_sha256=bindings)
    return summary, scene, input_path


def fast_summary(run, mission_id):
    run = Path(run)
    pointer = read_json(run / "analysis_latest.json")
    # M2 writers currently use analysis/, but resolve their explicit pointer.
    analysis = run / pointer["directory"]
    manifest = read_json(analysis / "manifest.json")
    scene = read_json(analysis / "compiled_scene.json")
    labels = read_json(analysis / "labels.json")
    semantic = read_json(analysis / "semantic_validation.json")
    windows = read_json(analysis / "phase_windows.json")
    quality = read_json(analysis / "quality.json")
    traces = {channel: read_positions(analysis / filename, manifest["agent_ids"])[0]
              for channel, filename in (("truth", "support_truth.csv"), ("observation", "support_observations.csv"))}
    summary = summarize_motion(scene, traces, windows["channels"], labels, semantic, manifest["end_us"] / 1e6,
                quality_eligible=manifest["episode_quality_eligible"],
                source=dict(batch="fast_default_uncalibrated", run_id=manifest["run_id"], analysis=str(analysis)))
    summary.update(status="COMPLETE", mission_id=mission_id, numerical=quality["numerical"],
                   input_task_sha256=read_json(analysis / "source.json")["input_sha256"])
    return summary


def agreement(a, b, *, unclear_unknown=False):
    if a is None or b is None or unclear_unknown and (a == "unclear" or b == "unclear"):
        return None
    return a == b


def paired_metrics(reference, candidate):
    if reference["family_id"] != candidate["family_id"] or reference["mission_id"] != candidate["mission_id"]:
        raise ValueError("cannot pair different task identities")
    relative = lambda a, b: (b - a) / a if a is not None and b is not None and a > 0 else None
    phases = {k: relative(v, candidate["phase_duration_sim_s"].get(k))
              for k, v in reference["phase_duration_sim_s"].items()}
    condition_pairs = {}
    for channel in ("truth", "observation"):
        a, b = reference["condition_results"].get(channel, {}), candidate["condition_results"].get(channel, {})
        condition_pairs[channel] = {k: dict(reference=a.get(k), candidate=b.get(k), agree=agreement(a.get(k), b.get(k)))
                                    for k in sorted(a.keys() | b.keys())}
    ra, rb = reference["routes"], candidate["routes"]
    minimum_a, minimum_b = reference["truth_separation"]["minimum_m"], candidate["truth_separation"]["minimum_m"]
    return dict(mission_id=reference["mission_id"], family_id=reference["family_id"], agents=reference["agents"],
        reference_quality=reference["quality_eligible"], candidate_quality=candidate["quality_eligible"],
        reference_status=reference["run_status"], candidate_status=candidate["run_status"],
        success_agreement=agreement(reference["mission_success"], candidate["mission_success"]),
        observation_success_agreement=agreement(reference["mission_success_observation"], candidate["mission_success_observation"]),
        success_values=[reference["mission_success"], candidate["mission_success"]],
        condition_pairs=condition_pairs,
        motion_slots={c: dict(reference=reference["motion_slots"][c], candidate=candidate["motion_slots"][c],
            agree=agreement(reference["motion_slots"][c], candidate["motion_slots"][c], unclear_unknown=True))
            for c in ("truth", "observation")},
        duration_relative_error=relative(reference["duration_sim_s"], candidate["duration_sim_s"]),
        duration_s=[reference["duration_sim_s"], candidate["duration_sim_s"]],
        phase_duration_relative_error=phases, lateral_m=pair_lateral(ra, rb),
        cruise_speed_m_s=[ra["cruise_speed"]["median"], rb["cruise_speed"]["median"]],
        turn_minimum_speed_m_s=[ra["turn_minimum_speed"]["median"], rb["turn_minimum_speed"]["median"]],
        truth_minimum_separation_m=[minimum_a, minimum_b],
        truth_minimum_separation_difference_m=minimum_b - minimum_a if minimum_a is not None and minimum_b is not None else None)


def aggregate_pairs(rows):
    """Task distributions and family-equal summaries; frames are not replicates."""
    families = sorted({r['family_id'] for r in rows})

    def numeric(get, applicable=None):
        cohort = rows if applicable is None else [r for r in rows if applicable(r)]
        values = [(r['family_id'], get(r)) for r in cohort]
        usable = [(f, v) for f, v in values if v is not None and math.isfinite(v)]
        family_medians = [float(np.median([v for g, v in usable if g == f]))
                          for f in families if any(g == f for g, _ in usable)]
        return dict(task=distribution([v for _, v in usable]), missing=len(cohort)-len(usable),
                    not_applicable=len(rows)-len(cohort),
                    family_median=distribution(family_medians))

    def binary(get, applicable=None):
        cohort = rows if applicable is None else [r for r in rows if applicable(r)]
        values = [(r['family_id'], get(r)) for r in cohort]
        matched = sum(v is True for _, v in values)
        mismatched = sum(v is False for _, v in values)
        known = matched + mismatched
        fractions = [sum(v is True for g, v in values if g == f) /
                     sum(v is not None for g, v in values if g == f)
                     for f in families if any(g == f and v is not None for g, v in values)]
        return dict(total=len(cohort), not_applicable=len(rows)-len(cohort), agree=matched, disagree=mismatched, unknown=len(cohort)-known,
                    known_rate=matched / known if known else None,
                    all_task_rate=matched / len(cohort) if cohort else None,
                    family_equal_known_rate=float(np.mean(fractions)) if fractions else None)

    def difference(row, name, relative=False):
        a, b = row[name]
        return ((b - a) / a if relative and a > 0 else b - a if not relative else None
                ) if a is not None and b is not None else None

    result = dict(tasks=len(rows), families=len(families),
        success=binary(lambda r: r['success_agreement']),
        observation_success=binary(lambda r: r['observation_success_agreement']),
        motion_slots={c: binary(lambda r: r['motion_slots'][c]['agree']) for c in ('truth','observation')},
        motion_reference_known={c: binary(lambda r: r['motion_slots'][c]['reference']==r['motion_slots'][c]['candidate'],
            lambda r: r['motion_slots'][c]['reference'] not in (None,'unclear')) for c in ('truth','observation')},
        quality_eligible=sum(r['candidate_quality'] is True for r in rows),
        duration_relative_error=numeric(lambda r: r['duration_relative_error']),
        duration_absolute_relative_error=numeric(lambda r: abs(r['duration_relative_error'])
                                                if r['duration_relative_error'] is not None else None),
        lateral_task_p95_m=numeric(lambda r: r['lateral_m']['p95']),
        lateral_matched_fraction=numeric(lambda r: r['lateral_m']['matched_fraction']),
        separation_difference_m=numeric(lambda r: r['truth_minimum_separation_difference_m']),
        separation_absolute_difference_m=numeric(lambda r: abs(r['truth_minimum_separation_difference_m'])
                                                if r['truth_minimum_separation_difference_m'] is not None else None))
    result['phase_absolute_relative_error'] = {p: numeric(lambda r: abs(r['phase_duration_relative_error'][p])
        if r['phase_duration_relative_error'].get(p) is not None else None,
        lambda r: p in r['phase_duration_relative_error'])
        for p in sorted({p for r in rows for p in r['phase_duration_relative_error']})}
    for name in ('cruise_speed_m_s','turn_minimum_speed_m_s'):
        result[name] = dict(reference=numeric(lambda r: r[name][0]), candidate=numeric(lambda r: r[name][1]),
                           difference=numeric(lambda r: difference(r,name)),
                           absolute_difference=numeric(lambda r: abs(difference(r,name))
                                                       if difference(r,name) is not None else None),
                           relative_error=numeric(lambda r: difference(r,name,True)))
    result['conditions'] = {c: {name: binary(lambda r: r['condition_pairs'][c].get(name,{}).get('agree'),
                                           lambda r: name in r['condition_pairs'][c])
        for name in sorted({name for r in rows for name in r['condition_pairs'][c]})}
        for c in ('truth','observation')}
    return result
