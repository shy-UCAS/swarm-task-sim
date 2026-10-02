"""Read-only WP-V (V01--V05) evidence report and independent AC-6 check.

Usage: python scripts/verify_v04_v1.py records.json --output tmp_v04/wp_v/new_report
records.json contains {"records": [{"validation_id": "V02", "repeat": 1,
"run_directory": "runs/...", "exit_code": 0}]}. Relative run paths are relative
to the project root. This helper never launches SITL or imports swarm_sim/audit.
Only a previously nonexistent output directory below tmp_v04 may be written.
"""

import argparse
import copy
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
VERSION = "v04_v1_independent_verification_v1"
EXPECTED = {"V01": 1, "V02": 2, "V03": 1, "V04": 1, "V05": 1}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def digest(path):
    with Path(path).open("rb") as stream:
        result = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def conjunction(values):
    values = list(values)
    return False if False in values else True if values and all(v is True for v in values) else None


def status(value):
    return "PASS" if value is True else "FAIL" if value is False else "UNKNOWN"


def nested(value, *keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def read_json(path, guarded, issues):
    path = Path(path)
    if not path.is_file():
        issues.append(f"missing: {path}")
        return {}
    guarded[str(path)] = digest(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError("expected JSON object")
        return value
    except (ValueError, OSError) as exc:
        issues.append(f"unreadable: {path}: {exc}")
        return {}


def read_observations(path, agents, guarded, issues):
    """Keep invalid rows as barriers; never sort, interpolate or remove duplicates."""
    rows = {agent: [] for agent in agents}
    if not path.is_file():
        issues.append(f"missing: {path}")
        return rows
    guarded[str(path)] = digest(path)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            agent = row.get("agent_id")
            if agent not in rows:
                issues.append(f"unexpected observation agent: {agent}")
                continue
            values = [number(row.get(k)) for k in
                      ("east_m", "north_m", "up_m", "ve_m_s", "vn_m_s", "vu_m_s")]
            valid = row.get("valid") == "1" and all(v is not None for v in values)
            rows[agent].append((number(row.get("t_s")), math.hypot(*values[3:5]) if valid else None, valid))
    return rows


def read_events(path, guarded, issues):
    if not path.is_file():
        issues.append(f"missing: {path}")
        return []
    guarded[str(path)] = digest(path)
    try:
        events = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        if any(not isinstance(event, dict) for event in events):
            raise ValueError("expected JSON objects")
        return events
    except (ValueError, OSError) as exc:
        issues.append(f"unreadable: {path}: {exc}")
        return []


def controlled_failure_evidence(record, metadata, scene, events, quality, labels, analysis_retained, cleaned):
    """Require the injected phase deadline, not merely any TimeoutError.

    Runner evidence has phase_budget and run_failed events, with per-operation
    deadlines in phase_timing. Match these independent records; a timeout while
    connecting, reading parameters or taking off is not the intended V05 case.
    """
    def known_bool(value, predicate):
        return predicate(value) if value is not None else None

    override = nested(scene, "task_spec", "execution", "phase_timeout_override_s")
    agents = [v["id"] for v in scene.get("vehicles", [])]
    phases = metadata.get("phase_timing", {})
    failed = [(name, row) for name, row in phases.items() if row.get("status") == "failed"]
    phase, timing = failed[0] if len(failed) == 1 else (None, {})
    epoch, started, finished = (metadata.get("run_epoch_monotonic_s"),
                               timing.get("started_monotonic_s"), timing.get("finished_monotonic_s"))
    effective, remaining, nominal = (timing.get("effective_timeout_s"),
                                     timing.get("scenario_remaining_s"), timing.get("nominal_duration_s"))
    bound_nominal = nested(scene, "planning", "nominal_phase_timing", phase, "duration_s")
    deadline = started + effective if finite(started) and finite(effective) else None
    error = metadata.get("error")
    budgets = [event for event in events if event.get("event") == "phase_budget" and event.get("phase") == phase]
    failures = [event for event in events if event.get("event") == "run_failed"]
    preflight = [event for event in events if event.get("event") == "preflight_verified"]
    airborne = {agent: [event for event in events if event.get("event") == "airborne_ready"
                       and event.get("agent_id") == agent] for agent in agents}
    same = lambda a, b: abs(a - b) <= 1e-9 if finite(a) and finite(b) else None
    stage_time = started - epoch if finite(started) and finite(epoch) else None
    before_stage = lambda event: (event["t"] <= stage_time if finite(event.get("t")) and stage_time is not None else None)
    after_deadline = lambda event: (event["t"] + epoch >= deadline - 1e-9
                                    if finite(event.get("t")) and finite(epoch) and deadline is not None else None)
    budget_match = None
    if len(budgets) == 1:
        budget_match = conjunction([same(budgets[0].get(key), timing.get(key)) for key in
                                   ("phase_timeout_override_s", "effective_timeout_s", "nominal_duration_s", "scenario_remaining_s")])
    elif budgets:
        budget_match = False
    failed_operation_names = [name for name, operation in timing.get("operations", {}).items()
                              if operation.get("complete") is False]
    failed_operations = [timing["operations"][name] for name in failed_operation_names]
    timeout_context = None
    if error and phase and failed_operation_names:
        timeout_context = any(error == f"TimeoutError: phase {phase} {name} timeout"
                              for name in failed_operation_names)
        # The vehicle's upload waiter can raise before the controller checks its
        # same deadline. A stale-heartbeat TimeoutError is deliberately excluded.
        if "upload" in failed_operation_names and str(error).startswith("TimeoutError:"):
            timeout_context = timeout_context or "mission upload timed out" in error or (
                "waiting for" in error and "MISSION_REQUEST" in error and "MISSION_ACK" in error)
    operation_expired = conjunction(
        operation["finished_monotonic_s"] >= deadline - 1e-9
        if finite(operation.get("finished_monotonic_s")) and deadline is not None else None
        for operation in failed_operations)
    failure = dict(
        run_failed=known_bool(metadata.get("status"), lambda value: value == "failed"),
        timeout_recorded=known_bool(error, lambda value: str(value).startswith("TimeoutError:")),
        exit_code_nonzero=known_bool(record.get("exit_code"), lambda value: type(value) is int and value != 0),
        route_mode=nested(scene, "task_spec", "execution", "control_mode") == "semantic_phase_route_v1" if scene else None,
        bound_scene_matches=metadata["scenario"] == scene if "scenario" in metadata and scene else None,
        override_bound=override > 0 if finite(override) else None,
        override_applied=same(override, timing.get("phase_timeout_override_s")),
        phase_failure_recorded=True if len(failed) == 1 else False if failed else None,
        nominal_matches_bound_scene=same(nominal, bound_nominal),
        injected_budget_is_limiting=(effective > 0 and same(effective, override) is True
                                    and override < min(remaining, 3 * nominal + 30))
                                   if all(finite(v) for v in (effective, override, remaining, nominal)) else None,
        phase_deadline_expired=finished >= deadline - 1e-9 if finite(finished) and deadline is not None else None,
        phase_timeout_error_matches=timing["error"] == error if timing.get("error") and error else None,
        phase_timeout_context_matches=timeout_context,
        failed_operation_expired=operation_expired,
        phase_budget_event_matches=budget_match,
        run_failed_event_matches=(conjunction([failures[0].get("error") == error, after_deadline(failures[0])])
                                  if len(failures) == 1 and error else False if len(failures) > 1 else None),
        preflight_verified=known_bool(nested(metadata, "run_provenance", "status"), lambda value: value == "verified_before_takeoff"),
        preflight_event_before_phase=before_stage(preflight[0]) if len(preflight) == 1 else False if preflight else None,
        all_agents_airborne_before_phase=conjunction(before_stage(hits[0]) if len(hits) == 1 else False if hits else None
                                                    for hits in airborne.values()),
        mission_not_success=labels.get("mission_success") is not True if "mission_success" in labels else None,
        observation_not_success=labels.get("mission_success_observation") is not True if "mission_success_observation" in labels else None,
        quality_ineligible=quality.get("episode_quality_eligible") is False if type(quality.get("episode_quality_eligible")) is bool else None,
        analysis_retained=analysis_retained, cleanup_complete=cleaned)
    failure["as_expected"] = conjunction(failure.values())
    failure["evidence"] = dict(phase=phase, override_s=override, effective_timeout_s=effective,
                               deadline_monotonic_s=deadline, phase_finished_monotonic_s=finished,
                               phase_budget_events=budgets, run_failed_events=failures,
                               preflight_events=preflight, airborne_events=airborne)
    return failure


def independent_runs_below(samples, threshold, dt, minimum_s=.2):
    """Minimal A4_final.runs_below copy; None is an explicit invalid-row barrier.

    Duration uses the original exact last-first >= minimum_s comparison. The
    surrounding reader differs deliberately from A4 read_obs: no sorting and no
    skipping invalid rows. Strict chronology is checked before calling this.
    """
    segments, run = [], []
    for stamp, speed, _ in samples:
        if speed is not None and speed < threshold:
            if run and stamp - run[-1][0] > 1.5 * dt:
                segments.append(run)
                run = []
            run.append((stamp, speed))
        elif run:
            segments.append(run)
            run = []
    if run:
        segments.append(run)
    return [[r[0][0], r[-1][0]] for r in segments if r[-1][0] - r[0][0] >= minimum_s]


def independent_stops(rows, windows, dt):
    spans = [w for w in windows if finite(w.get("start_s")) and finite(w.get("end_s"))
             and w["end_s"] >= w["start_s"]]
    bounds = [min(w["start_s"] for w in spans), max(w["end_s"] for w in spans)] if spans else None
    invalid, complete = {}, {}
    for agent, samples in rows.items():
        if not any(s is not None for _, s, _ in samples):
            invalid[agent] = "missing_velocity_evidence"
        if bounds is None:
            invalid[agent] = "semantic_mission_window_missing"
        if (any(not finite(t) for t, _, _ in samples)
                or any(b[0] <= a[0] for a, b in zip(samples, samples[1:]))):
            invalid[agent] = "non_strict_timeline"
        selected = [r for r in samples if bounds and finite(r[0]) and bounds[0] <= r[0] <= bounds[1]]
        complete[agent] = bool(bounds and agent not in invalid and selected
            and samples[0][0] <= bounds[0] + 1.5 * dt and samples[-1][0] >= bounds[1] - 1.5 * dt
            and all(r[2] and r[1] is not None for r in selected)
            and all(b[0] - a[0] <= 1.5 * dt for a, b in zip(selected, selected[1:])))
    result = dict(fraction_window_s=bounds, invalid_agents=invalid, evidence_complete=bool(rows) and all(complete.values()), thresholds={})
    for threshold in (.3, .5):
        intervals = {a: independent_runs_below(r, threshold, dt) if a not in invalid else None for a, r in rows.items()}
        per_agent = {a: dict(stop_count=len(s) if s is not None else None, stop_intervals_s=s,
                            evidence_complete=complete[a], stop_count_is_lower_bound=a not in invalid and not complete[a],
                            invalid_reason=invalid.get(a)) for a, s in intervals.items()}
        stationary = sync = grid_points = sync_points = None
        if result["evidence_complete"]:
            start, end = bounds
            duration = end - start
            total = sum(max(0., min(right, end) - max(left, start)) for seq in intervals.values() for left, right in seq)
            stationary = total / (duration * len(rows)) if duration > 0 else None
            grid_points = int(round(duration / dt)) + 1
            sync_points = 0
            for index in range(grid_points):
                stamp = start + index * dt
                if all(any(left <= stamp <= right for left, right in seq) for seq in intervals.values()):
                    sync_points += 1
            sync = sync_points / grid_points
        result["thresholds"][str(threshold)] = dict(per_agent=per_agent, stationary_time_fraction=stationary,
            synchronized_time_fraction=sync, grid_points=grid_points, synchronized_grid_points=sync_points)
    return result


def compare_stops(reference, metrics):
    comparisons = {}
    for threshold, expected in reference["thresholds"].items():
        actual = nested(metrics, "thresholds", threshold) or {}
        agents = {}
        for agent, row in expected["per_agent"].items():
            reported = nested(actual, "per_agent", agent) or {}
            known = row["stop_count"] is not None and reported.get("stop_count") is not None
            matched = (row["stop_count"] == reported.get("stop_count")
                       and row["stop_intervals_s"] == reported.get("stop_intervals_s")) if known else None
            complete = row["evidence_complete"] and reported.get("evidence_complete") is True
            agents[agent] = dict(independent_stop_count=row["stop_count"], reported_stop_count=reported.get("stop_count"),
                observed_intervals_match=matched, evidence_complete=complete,
                passed=matched if complete or matched is False else None)
        fractions = {}
        for key in ("stationary_time_fraction", "synchronized_time_fraction"):
            left, right = expected[key], actual.get(key)
            delta = abs(left - right) if finite(left) and finite(right) else None
            fractions[key] = dict(independent=left, reported=right, absolute_difference=delta,
                                  passed=delta <= 1e-6 if delta is not None else None)
        comparisons[threshold] = dict(per_agent=agents, fractions=fractions,
            passed=conjunction([a["passed"] for a in agents.values()] + [f["passed"] for f in fractions.values()]))
    return dict(passed=conjunction(r["passed"] for r in comparisons.values()), thresholds=comparisons,
                independent=reference, comparison_scope="counts, exact intervals, stationary fraction and sampled sync fraction; both thresholds")


def check_hashes(base, hashes, guarded):
    rows = []
    for name, expected in (hashes or {}).items():
        path = base / name
        actual = digest(path) if path.is_file() else None
        if actual is not None:
            guarded[str(path)] = actual
        rows.append(dict(path=str(path), expected=expected, actual=actual,
                         matches=actual == expected if actual is not None else None))
    return dict(expected_count=len(rows), matched_count=sum(r["matches"] is True for r in rows),
                passed=conjunction(r["matches"] for r in rows), files=rows)


def zero_segments(scene):
    """Count actual planned positional moves; empty no-op routes add no segment."""
    phases = scene.get("phases", [])
    semantic = nested(scene, "semantic_plan", "execution_phases") or {}
    previous = {v["id"]: v for v in scene.get("vehicles", [])}
    records, missing, no_ops = [], [], 0
    for phase in phases:
        for agent in previous:
            if scene.get("schema_version") == 2:
                roles = nested(semantic, phase["name"], "agents", agent) or {}
                start = roles.get("start_point")
                route = phase.get("routes", {}).get(agent)
                if route == []:
                    no_ops += 1
            else:
                start = previous[agent]
                target = phase.get("targets", {}).get(agent)
                route = [target] if target else None
            if start is None or route is None:
                missing.append(dict(agent_id=agent, phase=phase.get("name")))
                continue
            for index, point in enumerate(route):
                # Missing altitude in a legacy spawn is the scenario takeoff altitude.
                def xyz(p):
                    return [p.get("east_m"), p.get("north_m"), p.get("up_m", scene.get("takeoff_alt_m"))]
                a, b = xyz(start), xyz(point)
                if not all(finite(x) for x in a + b):
                    missing.append(dict(agent_id=agent, phase=phase.get("name"), route_index=index))
                else:
                    distance = math.dist(a, b)
                    records.append(dict(agent_id=agent, phase=phase.get("name"), route_index=index, length_m=distance))
                start = point
            if route:
                previous[agent] = route[-1]
    return dict(segment_count=len(records), zero_length_count=sum(r["length_m"] <= 1e-9 for r in records) if not missing and phases else None,
                near_zero_below_005m_count=sum(r["length_m"] < .05 for r in records) if not missing and phases else None,
                no_op_routes=no_ops, missing=missing, records=records, zero_tolerance_m=1e-9)


def verify_record(record, guarded):
    issues = []
    directory = Path(record["run_directory"])
    directory = (directory if directory.is_absolute() else PROJECT / directory).resolve()
    metadata = read_json(directory / "metadata.json", guarded, issues)
    scene = read_json(directory / "scenario.json", guarded, issues)
    latest = read_json(directory / "analysis_latest.json", guarded, issues)
    analysis = directory / latest.get("directory", "__missing_analysis__")
    data = {name: read_json(analysis / (name + ".json"), guarded, issues) for name in
            ("manifest", "quality", "labels", "execution_metrics", "phase_windows", "semantic_validation")}
    manifest, quality, labels, metrics, windows = (data[k] for k in ("manifest", "quality", "labels", "execution_metrics", "phase_windows"))
    agents = [v["id"] for v in scene.get("vehicles", [])]
    observations = read_observations(analysis / "observations.csv", agents, guarded, issues)
    rate = scene.get("record_hz")
    dt = 1 / rate if finite(rate) and rate > 0 else None
    ac6 = compare_stops(independent_stops(observations, windows.get("windows", []), dt), metrics) if dt else dict(passed=None, reason="record_hz unavailable")
    intermediate = metrics.get("intermediate_waypoints", {})
    coverage = {c: nested(labels, "mission_metrics", c, "coverage", "global_coverage_ratio") for c in ("truth", "observation")}
    required = nested(scene, "task_spec", "mission", "coverage_required")
    if required is None:
        required = nested(scene, "task_spec", "mission", "intent_params", "coverage_required")
    coverage_passes = [value >= required if finite(value) and finite(required) else None for value in coverage.values()]
    consistency = labels.get("semantic_consistency")
    separation = quality.get("truth_separation", {})
    minimum, minimum_required = separation.get("minimum_m"), scene.get("min_separation_m")
    nominal = nested(metrics, "nominal_timing_deviation_s", "assessment") or {}
    zero = zero_segments(scene)
    semantic_phases = {p.get("semantic_phase") or nested(scene, "semantic_plan", "execution_phases", p.get("name"), "semantic_phase")
                       for p in scene.get("phases", [])}
    semantic_phases.discard(None)
    phase_count = len(semantic_phases) or None
    ac2 = {}
    for threshold in ("0.3", "0.5"):
        ac2[threshold] = {}
        for agent in agents:
            item = nested(metrics, "thresholds", threshold, "per_agent", agent) or {}
            count = item.get("stop_count")
            passed = count <= phase_count + 1 if finite(count) and phase_count and item.get("evidence_complete") is True else None
            ac2[threshold][agent] = dict(stop_count=count, limit=phase_count + 1 if phase_count else None,
                                       evidence_complete=item.get("evidence_complete"), passed=passed)
    ac1_rate = intermediate.get("stop_rate")
    ac4_distance = minimum >= minimum_required if finite(minimum) and finite(minimum_required) else None
    # The measured minimum cannot certify the missing intervals of a partial truth stream.
    if separation.get("status") != "clear_observed" and ac4_distance is True:
        ac4_distance = None
    criteria = {
        "AC1": ac1_rate <= .1 if finite(ac1_rate) else None,
        "AC2": conjunction(r["passed"] for r in ac2["0.3"].values()),
        "AC3": conjunction(coverage_passes + [consistency == "agree" if consistency in ("agree", "disagree") else None]),
        "AC4": conjunction([ac4_distance, nominal.get("within_tau")]),
        "AC5": zero["zero_length_count"] == 0 if zero["zero_length_count"] is not None else None,
        "AC6": ac6["passed"],
    }
    cleanup = metadata.get("cleanup", {})
    cleaned = conjunction(type(cleanup[agent]) is int if agent in cleanup else None for agent in agents)
    timings = metadata.get("phase_timing", {})
    overheads = [t.get("upload_release_confirmation_overhead_s") for t in timings.values()]
    totals = [t.get("total_duration_s") for t in timings.values()]
    overhead = sum(overheads) / sum(totals) if overheads and all(finite(x) for x in overheads + totals) and sum(totals) > 0 else None
    span = (metadata["mission_end_monotonic_s"] - metadata["flight_epoch_monotonic_s"]
            if all(finite(metadata.get(k)) for k in ("mission_end_monotonic_s", "flight_epoch_monotonic_s")) else None)
    hashes = dict(artifacts=check_hashes(analysis, manifest.get("artifact_sha256"), guarded),
        run_inputs=check_hashes(directory, manifest.get("source_sha256"), guarded),
        runtime_sources=check_hashes(PROJECT / "swarm_sim", metadata.get("source_sha256"), guarded),
        analysis_sources=check_hashes(PROJECT / "swarm_sim", manifest.get("analysis_source_sha256"), guarded))
    latest_hash = digest(analysis / "manifest.json") if (analysis / "manifest.json").is_file() else None
    hashes["latest_manifest_matches"] = latest_hash == latest.get("manifest_sha256") if latest_hash and latest.get("manifest_sha256") else None
    evidence_integrity = conjunction([hashes[key]["passed"] for key in
        ("artifacts", "run_inputs", "runtime_sources", "analysis_sources")] + [hashes["latest_manifest_matches"]])
    failure = None
    if record.get("validation_id") == "V05":
        failure = controlled_failure_evidence(record, metadata, scene,
            read_events(directory / "events.jsonl", guarded, issues), quality, labels,
            bool(manifest) if analysis.is_dir() else None, cleaned)
    report_arrival = None
    if scene.get("schema_version") == 1 and nested(scene, "task_spec", "execution", "control_mode") == "waypoint_barrier_v1":
        try:
            from scripts.v04_barrier_arrival_diagnostic import diagnose, load_fcu_grid, source_validity
        except ModuleNotFoundError:
            from v04_barrier_arrival_diagnostic import diagnose, load_fcu_grid, source_validity
        module_path = PROJECT / "scripts/v04_barrier_arrival_diagnostic.py"
        guarded[str(module_path)] = digest(module_path)
        processing = read_json(analysis / "observation_processing.json", guarded, issues)
        clocks = read_json(analysis / "clock_models.json", guarded, issues)
        epoch = manifest.get("time_epoch_host_s", metadata.get("run_epoch_monotonic_s"))
        if finite(epoch) and finite(metadata.get("run_epoch_monotonic_s")):
            report_arrival = diagnose(scene, load_fcu_grid(analysis / "observations.csv", agents),
                read_events(directory / "events.jsonl", guarded, issues), metadata, epoch,
                source_validity(agents, processing, clocks, quality))
        else:
            report_arrival = dict(available=False, report_only=True, distribution=dict(median=None),
                                  unknown_reason="run or observation epoch missing")
    return dict(validation_id=record.get("validation_id"), repeat=record.get("repeat"), run_id=metadata.get("run_id"),
        run_directory=str(directory), analysis_directory=str(analysis), exit_code=record.get("exit_code"),
        started_utc=metadata.get("started_utc"), run_status=metadata.get("status"), error=metadata.get("error"),
        control_mode=nested(scene, "task_spec", "execution", "control_mode"),
        elapsed_s=metadata.get("elapsed_s"), task_span_s=span, analysis_duration_s=manifest.get("duration_s"),
        flight_window_available=finite(metadata.get("flight_epoch_monotonic_s")) and finite(metadata.get("mission_end_monotonic_s")),
        acceptance_criteria_applicable=record.get("validation_id") in ("V02", "V03", "V04"),
        coverage=coverage, coverage_required=required, semantic_consistency=consistency,
        quality={key: quality.get(key) for key in ("clock_quality", "episode_quality_eligible", "benchmark_eligible", "strict_benchmark_eligible")},
        truth_minimum_separation_m=minimum, minimum_separation_required_m=minimum_required,
        truth_separation=separation, nominal_timing=nominal, zero_length_segments=zero,
        semantic_phase_count=phase_count, intermediate_waypoints=intermediate,
        ac2_per_agent=ac2, independent_stop_check=ac6, criteria=criteria,
        criteria_status={key: status(value) for key, value in criteria.items()},
        thresholds=metrics.get("thresholds"), arrival_lag_s=metrics.get("arrival_lag_s"),
        report_only_arrival_lag_s=report_arrival,
        barrier_wait_s=metrics.get("barrier_wait_s"), nominal_timing_deviation_s=metrics.get("nominal_timing_deviation_s"),
        upload_release_confirmation_fraction=overhead, overhead_fraction_denominator="sum of phase_timing.total_duration_s",
        phase_timing=timings, cleanup=dict(per_agent=cleanup, expected_agents=agents, complete=cleaned),
        code=dict(simulator_version=metadata.get("version"), runner_version=metadata.get("runner_version"),
                  analysis_version=manifest.get("analysis_version")),
        scenario_sha256=metadata.get("scenario_sha256"), task_sha256=hashlib.sha256(json.dumps(scene["task_spec"], sort_keys=True).encode()).hexdigest() if scene.get("task_spec") else None,
        task_sha256_definition="SHA256 of json.dumps(bound TaskSpec, sort_keys=True) UTF-8",
        firmware=metadata.get("binary_firmware"), parameters_sha256=metadata.get("parameters_sha256"),
        run_provenance=metadata.get("run_provenance"), hash_verification=hashes, evidence_integrity_pass=evidence_integrity,
        processing_versions={k: manifest.get(k) for k in ("observation_processing_version", "duplicate_policy_version", "timeline_policy_version", "clock_model_version")},
        expected_failure=failure, issues=issues)


def verify_records(records_path):
    guarded, issues = {}, []
    source = read_json(Path(records_path).resolve(), guarded, issues)
    records = source.get("records")
    if not isinstance(records, list):
        raise ValueError("records input requires a records list")
    identities = [(r.get("validation_id"), r.get("repeat")) for r in records]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate validation_id/repeat records")
    if any(key not in EXPECTED or type(repeat) is not int or not 1 <= repeat <= EXPECTED[key]
           for key, repeat in identities):
        raise ValueError("records must use V01--V05 and their planned repeat numbers")
    rows = [verify_record(record, guarded) for record in records]
    route = [r for r in rows if r["validation_id"] in ("V02", "V03", "V04")]
    counts = [r["intermediate_waypoints"].get("total_count") for r in route]
    stopped = [r["intermediate_waypoints"].get("stopped_count") for r in route]
    unknown = [r["intermediate_waypoints"].get("unknown_count") for r in route]
    total = sum(counts) if counts and all(finite(v) for v in counts) else None
    detected = sum(stopped) if stopped and all(finite(v) for v in stopped) else None
    missing = sum(unknown) if unknown and all(finite(v) for v in unknown) else None
    pooled_rate = detected / total if total and detected is not None and missing == 0 else None
    matrix = {key: dict(expected=count, observed=sum(r["validation_id"] == key for r in rows)) for key, count in EXPECTED.items()}
    for item in matrix.values():
        item["status"] = "NOT_RUN" if item["observed"] == 0 else "COMPLETE" if item["observed"] == item["expected"] else "PARTIAL"
    complete = all(row["expected"] == row["observed"] for row in matrix.values())
    route_complete = all(matrix[k]["expected"] == matrix[k]["observed"] for k in ("V02", "V03", "V04"))
    audit = PROJECT / "audit_v04/A4_final.py"
    if audit.is_file():
        guarded[str(audit)] = digest(audit)
    guarded[str(Path(__file__).resolve())] = digest(Path(__file__))
    changed = [path for path, original in guarded.items() if not Path(path).is_file() or digest(path) != original]
    aggregate = {f"AC{i}": conjunction(r["criteria"][f"AC{i}"] for r in route) for i in range(2, 7)}
    aggregate["AC1"] = pooled_rate <= .1 if pooled_rate is not None else None
    # An absent required run must never make a partially observed matrix pass.
    final = {key: value if value is False or route_complete else None for key, value in aggregate.items()}
    return dict(schema_version=1, version=VERSION, generated_utc=datetime.now(timezone.utc).isoformat(),
        input_records_path=str(Path(records_path).resolve()), new_sitl_runs=0, matrix=matrix, matrix_complete=complete,
        observed_route_criteria=aggregate, final_route_criteria=final,
        ac1_pooled=dict(total_count=total, stopped_count=detected, unknown_count=missing, stop_rate=pooled_rate,
                       contributing_runs=len(route), expected_runs=4, matrix_complete=route_complete,
                       aggregation="sum(stopped_count)/sum(total_count); any unknown makes rate null; V01/V05 excluded"),
        mode_comparison=[{key: row.get(key) for key in ("validation_id", "repeat", "run_id", "control_mode", "thresholds",
            "intermediate_waypoints", "arrival_lag_s", "report_only_arrival_lag_s", "upload_release_confirmation_fraction", "task_span_s", "elapsed_s",
            "coverage", "truth_minimum_separation_m")} for row in rows if row["validation_id"] in ("V01", "V02")],
        passing_speed_by_scan_line=[dict(validation_id=row["validation_id"], repeat=row["repeat"], run_id=row["run_id"],
            channel="FCU horizontal velocity", units="m/s", neighborhood_m=2,
            processing_versions=row["processing_versions"],
            groups=row["intermediate_waypoints"].get("by_scan_line_length_m"),
            note="group key is full planned scan-line length in m; count is valid minimum-speed values, waypoint_count is denominator")
            for row in rows if row["validation_id"] in ("V03", "V04")],
        ac6_method=dict(reference_file=str(audit), reference_sha256=guarded.get(str(audit)),
            imported_or_executed_original=False, imported_execution_metrics=False, thresholds_m_s=[.3, .5], minimum_stop_duration_s=.2,
            changes_from_A4="parameterized DT from record_hz; retain invalid rows as barriers instead of dropping; reject non-strict chronology instead of sorting; no interpolation",
            uncertainty="observed matching lower bounds are reported but incomplete or missing evidence cannot pass AC6; 1e-6 fraction tolerance"),
        records=rows, input_sha256=guarded, source_files_unchanged=not changed, changed_sources=changed, issues=issues)


def markdown(report):
    lines = ["# WP-V 离线证据核验", "", f"版本：`{report['version']}`。生成：{report['generated_utc']}。本工具启动 SITL：0 次。", "",
             "UNKNOWN 表示证据不足；单次失败与合并结果均保留。本报告仅整理已有产物，不重分析运行、不修改门槛。", "",
             "| 运行 | 状态 / 退出码 | 覆盖 SIM / FCU | 真值最小间距 m | 任务跨度 s / elapsed s | AC1–AC6 |", "| --- | --- | --- | --- | --- | --- |"]
    def fmt(value):
        return "UNKNOWN" if value is None else f"{value:.6f}" if type(value) is float else str(value)
    for row in report["records"]:
        flight=row["flight_window_available"]
        coverage=" / ".join(fmt(row["coverage"][c]) for c in ("truth","observation")) if flight else "NOT_MEASURED / NOT_MEASURED"
        separation=fmt(row["truth_minimum_separation_m"]) if flight else "NOT_MEASURED"
        criteria=", ".join(row["criteria_status"][f"AC{i}"] for i in range(1,7)) if row["acceptance_criteria_applicable"] else "NOT_APPLICABLE"
        lines.append(f"| {row['validation_id']} #{row['repeat']} | {row['run_status']} / {fmt(row['exit_code'])} | {coverage} | {separation} | {fmt(row['task_span_s'])} / {fmt(row['elapsed_s'])} | {criteria} |")
    lines += ["", "运行矩阵的 COMPLETE 仅表示已记录规定次数的尝试，不表示成功或验收通过。无完整任务飞行窗口时，表中不把地面观测作为飞行指标；JSON 中保留原始数值并标注 flight_window_available。AC1–AC6 仅适用于 V02–V04。"]
    lines += ["", "运行矩阵：`" + json.dumps(report["matrix"], ensure_ascii=False) + "`。", "",
              "合并 AC1（V02–V04，按点数加权）：`" + json.dumps(report["ac1_pooled"], ensure_ascii=False) + "`。", "",
              "完整矩阵门禁：`" + json.dumps({k: status(v) for k, v in report["final_route_criteria"].items()}, ensure_ascii=False) + "`。", "",
              "## V01 / V02 对照（0.3 m/s，持续至少 0.2 s）", "",
              "| 运行 | 每机停靠数 | 中间点停靠率 | 同步比例 | 静止比例 | arrival lag 原指标中位数 s | 旧模式独立 7.5 FCU 诊断中位数 s | 上传+放行+确认比例 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in report["mode_comparison"]:
        th = nested(row, "thresholds", "0.3") or {}
        counts = {a: r.get("stop_count") for a, r in th.get("per_agent", {}).items()}
        extra = row.get("report_only_arrival_lag_s")
        diagnostic = (fmt(nested(extra, "distribution", "median")) if extra and extra.get("available") else
                      "NOT_MEASURED" if extra is not None else "NOT_APPLICABLE")
        lines.append(f"| {row['validation_id']} #{row['repeat']} | {counts} | {fmt(nested(row, 'intermediate_waypoints', 'stop_rate'))} | {fmt(th.get('synchronized_time_fraction'))} | {fmt(th.get('stationary_time_fraction'))} | {fmt(nested(row, 'arrival_lag_s', 'distribution', 'median'))} | {diagnostic} | {fmt(row['upload_release_confirmation_fraction'])} |")
    lines += ["", "旧模式独立 7.5 诊断只读 FCU 观测采样与原始终点事件，不插值、不覆盖原 arrival_lag_s 或旧窗口；逐执行阶段统计，与连续模式逐语义阶段粒度不同。缺起飞/阶段事件或全流无效时为 NOT_MEASURED。", ""]
    lines += ["", "## 扫描线长度分组最低过点速度", "", "FCU 水平速度；2 m 邻域；速度单位 m/s，扫描线长度单位 m。分母为该组全部中间点。", "",
              "| 运行 | 扫描线长度 m | 有效 / 总数 | 未知 | min / p10 / median / p90 / max m/s |", "| --- | --- | --- | --- | --- |"]
    for row in report["passing_speed_by_scan_line"]:
        for length, group in (row["groups"] or {}).items():
            dist = group.get("minimum_passing_speed_m_s", {})
            lines.append(f"| {row['validation_id']} #{row['repeat']} | {length} | {fmt(dist.get('count'))} / {fmt(group.get('waypoint_count'))} | {fmt(group.get('unknown_count'))} | " + " / ".join(fmt(dist.get(k)) for k in ("min", "p10", "median", "p90", "max")) + " |")
    lines += ["", "## 证据范围", "", "AC6 独立复制 A4 的最小速度停靠检测，原审查脚本未导入或执行；两个阈值均复算。缺口与无效行断开区间，不排序、不插值，不完整证据不能判通过。", "",
              "原始输入哈希、运行及分析代码哈希、固件、参数读回、各阶段时长、逐点速度、AC6 区间和 V05 受控失败条件均保存在同目录 JSON。", "",
              f"读取前后输入不变：{report['source_files_unchanged']}。完整运行矩阵：{report['matrix_complete']}。", ""]
    for row in report["records"]:
        lines += [f"- {row['validation_id']} #{row['repeat']}: `{row['run_directory']}`；清理完整={row['cleanup']['complete']}；V05={row['expected_failure']}。"]
    return "\n".join(lines) + "\n"


def failure_helper_self_check():
    """Pure synthetic contract checks; never launch SITL or alter existing data."""
    scene = dict(schema_version=2, vehicles=[dict(id="uav_01"), dict(id="uav_02")],
        task_spec=dict(execution=dict(control_mode="semantic_phase_route_v1", phase_timeout_override_s=.01)),
        planning=dict(nominal_phase_timing=dict(p00_approach=dict(duration_s=5.0))))
    budget = dict(nominal_duration_s=5.0, scenario_remaining_s=90.0,
                  phase_timeout_override_s=.01, effective_timeout_s=.01)
    error = "TimeoutError: phase p00_approach upload timeout"
    metadata = dict(status="failed", error=error, scenario=scene, run_epoch_monotonic_s=100.0,
        run_provenance=dict(status="verified_before_takeoff"), phase_timing=dict(p00_approach=dict(
            **budget, status="failed", error=error, started_monotonic_s=110.0, finished_monotonic_s=110.011,
            operations=dict(upload=dict(complete=False, finished_monotonic_s=110.011)))))
    events = [dict(event="preflight_verified", t=2.0),
              dict(event="airborne_ready", agent_id="uav_01", t=8.0),
              dict(event="airborne_ready", agent_id="uav_02", t=9.0),
              dict(event="phase_budget", phase="p00_approach", t=10.0, **budget),
              dict(event="run_failed", t=10.011, error=error)]
    base = dict(record=dict(exit_code=1), metadata=metadata, scene=scene, events=events,
                quality=dict(episode_quality_eligible=False),
                labels=dict(mission_success=None, mission_success_observation=None),
                analysis_retained=True, cleaned=True)
    cases = [("valid_injected_phase_timeout", base, True)]
    def changed(name, expected, mutate):
        case = copy.deepcopy(base)
        mutate(case)
        cases.append((name, case, expected))
    changed("preflight_timeout_is_not_V05", False,
            lambda c: c["metadata"].update(phase_timing={}, run_provenance=dict(status="failed"),
                                          error="TimeoutError: TCP connection timeout"))
    changed("missing_airborne_evidence_is_unknown", None,
            lambda c: c.update(events=[e for e in c["events"] if e.get("agent_id") != "uav_02"]))
    changed("missing_budget_event_is_unknown", None,
            lambda c: c.update(events=[e for e in c["events"] if e["event"] != "phase_budget"]))
    changed("overridden_budget_not_applied_fails", False,
            lambda c: c["metadata"]["phase_timing"]["p00_approach"].update(effective_timeout_s=45.0))
    changed("unexpired_phase_timeout_fails", False,
            lambda c: c["metadata"]["phase_timing"]["p00_approach"].update(finished_monotonic_s=110.005))
    changed("incorrect_bound_nominal_fails", False,
            lambda c: c["scene"]["planning"]["nominal_phase_timing"]["p00_approach"].update(duration_s=7.0))
    changed("missing_injected_override_is_unknown", None,
            lambda c: c["scene"]["task_spec"]["execution"].pop("phase_timeout_override_s"))
    changed("mission_success_is_not_expected_failure", False,
            lambda c: c["labels"].update(mission_success=True))
    changed("incomplete_cleanup_fails", False, lambda c: c.update(cleaned=False))
    def replace_error(case, text):
        case["metadata"]["error"] = text
        case["metadata"]["phase_timing"]["p00_approach"]["error"] = text
        case["events"][-1]["error"] = text
    changed("stale_heartbeat_after_deadline_is_not_V05", False,
            lambda c: replace_error(c, "TimeoutError: uav_01: heartbeat stale for more than 5 s"))
    changed("upload_waiter_deadline_is_valid", True,
            lambda c: replace_error(c, "TimeoutError: uav_01: waiting for ['MISSION_REQUEST', 'MISSION_REQUEST_INT', 'MISSION_ACK']; no status text"))
    checks = []
    for name, arguments, expected in cases:
        result = controlled_failure_evidence(**arguments)
        checks.append(dict(name=name, expected=expected, actual=result["as_expected"],
                           passed=result["as_expected"] is expected, evidence=result))
    return dict(schema_version=1, version=VERSION, purpose="V05 controlled failure helper contract",
                new_sitl_runs=0, status="PASS" if all(c["passed"] for c in checks) else "FAIL", checks=checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path, nargs="?")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((PROJECT / "tmp_v04").resolve()) or output.exists():
        parser.error("output must be a previously nonexistent directory below project/tmp_v04")
    if args.self_check:
        if args.records is not None:
            parser.error("--self-check does not read a records file")
        report = failure_helper_self_check()
        output.mkdir(parents=True, exist_ok=False)
        report["script_sha256"] = digest(Path(__file__))
        (output / "v05_failure_helper_self_check.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps(dict(output=str(output), status=report["status"], checks=len(report["checks"]), new_sitl_runs=0)))
        if report["status"] != "PASS":
            raise SystemExit(1)
        return
    if args.records is None:
        parser.error("records is required unless --self-check is specified")
    report = verify_records(args.records)
    output.mkdir(parents=True, exist_ok=False)
    (output / "v04_v1_verification.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    (output / "v04_v1_verification.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps(dict(output=str(output), matrix_complete=report["matrix_complete"],
                         final_route_criteria=report["final_route_criteria"], source_files_unchanged=report["source_files_unchanged"])))


if __name__ == "__main__":
    main()
