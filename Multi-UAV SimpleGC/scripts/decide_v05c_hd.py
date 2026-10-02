"""Read-only VP1/VP4 dwell comparison; create one immutable HD decision JSON.

No SITL is started. A measured terminal window is each flown route's raw
terminal-waypoint event through its phase end. SIM horizontal speed is the
backward difference of adjacent valid truth-grid positions; invalid/gapped
intervals never prove a stop.
"""

import argparse
import csv
import json
import math
from pathlib import Path


from scripts.run_v05c_validation import (ROOT, CASE_ORDER, EXPECTED_ROOT,
    HISTORICAL_ATTEMPTS, MAX_ATTEMPTS, MAX_EXTRA_RETRIES, TOTAL_SITL_BUDGET,
    VERSION as VALIDATION_VERSION,
    _bound_inputs, _run_artifacts, assert_hashes, assert_historical_binding,
    assert_protected, finite, read)
from swarm_sim.generation import checked_path, file_hash, verify_generation


VERSION = "v05c_hd_terminal_truth_dwell_v1"
SPEED_THRESHOLD_M_S = 0.3
DISTANCE_THRESHOLD_M = 1.0
MIN_DURATION_S = 0.2


def truth_rows(path):
    rows = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        for item in csv.DictReader(stream):
            agent = item.get("agent_id")
            if not agent:
                raise ValueError("truth.csv has no agent ID")
            t = float(item["t_s"])
            if not math.isfinite(t):
                raise ValueError("truth.csv has nonfinite time")
            valid = item.get("valid") == "1"
            point = (tuple(float(item[key]) for key in ("east_m", "north_m", "up_m"))
                     if valid else None)
            if point is not None and not all(math.isfinite(value) for value in point):
                raise ValueError("truth.csv has nonfinite position")
            rows.setdefault(agent, []).append((t, point))
    for agent, values in rows.items():
        if any(right[0] <= left[0] for left, right in zip(values, values[1:])):
            raise ValueError("truth.csv has nonstrict timeline: " + agent)
    return rows


def stable_terminal_window(rows, window, max_gap_s, sample_dt_s=None):
    """Prove a >=0.2 s contiguous suffix of near-target, low-speed samples."""
    start, end, target = (window.get("terminal_waypoint_reached_s"),
                          window.get("end_s"), window.get("terminal_point"))
    if (not finite(start) or not finite(end) or end < start or
            not isinstance(target, dict) or not all(finite(target.get(key)) for key in
                ("east_m", "north_m", "up_m"))):
        return dict(stopped=False, evidence_complete=False, reason="terminal event/window/target unavailable")
    target_xyz = tuple(target[key] for key in ("east_m", "north_m", "up_m"))
    selected = [(t, point) for t, point in rows if start <= t <= end]
    edge = sample_dt_s if finite(sample_dt_s) and sample_dt_s > 0 else max_gap_s
    complete = (bool(selected) and selected[0][0] <= start + edge + 1e-9
                and selected[-1][0] >= end - edge - 1e-9
                and all(point is not None for _, point in selected)
                and all(right[0] - left[0] <= max_gap_s + 1e-9
                        for left, right in zip(selected, selected[1:])))
    streak_start = previous_good = None
    best_duration = 0.0
    available = 0
    for (previous_t, previous), (t, point) in zip(rows, rows[1:]):
        if t < start or t > end:
            continue
        if (point is None or previous is None or t - previous_t <= 0 or
                t - previous_t > max_gap_s):
            streak_start = previous_good = None
            continue
        available += 1
        speed = math.hypot(point[0] - previous[0], point[1] - previous[1]) / (t - previous_t)
        distance = math.dist(point, target_xyz)
        if speed < SPEED_THRESHOLD_M_S and distance <= DISTANCE_THRESHOLD_M:
            if previous_good is None or t - previous_good > max_gap_s:
                streak_start = t
            previous_good = t
            best_duration = max(best_duration, t - streak_start)
        else:
            streak_start = previous_good = None
    complete = complete and available > 0
    return dict(stopped=best_duration + 1e-9 >= MIN_DURATION_S,
                evidence_complete=complete,
                reason=None if complete else "missing/gapped SIM samples or speed interval in terminal window",
                terminal_event_s=start, phase_end_s=end, best_stable_duration_s=best_duration,
                speed_threshold_m_s=SPEED_THRESHOLD_M_S, distance_threshold_m=DISTANCE_THRESHOLD_M,
                minimum_duration_s=MIN_DURATION_S)


def terminal_fraction(scene, phase_windows, truths):
    windows = phase_windows.get("channels", {}).get("truth", [])
    by_key = {(row.get("phase"), row.get("agent_id")): row for row in windows}
    if len(by_key) != len(windows):
        raise ValueError("duplicate SIM terminal windows; HD evidence is ambiguous")
    results = []
    for phase in scene.get("phases", []):
        for agent, route in phase.get("routes", {}).items():
            if not route:
                continue
            key = phase["name"], agent
            if key not in by_key or agent not in truths:
                result = dict(stopped=False, evidence_complete=False,
                              reason="truth terminal window or agent trace absent")
            else:
                result = stable_terminal_window(truths[agent], by_key[key], scene["max_gap_s"],
                    1 / scene["record_hz"])
            results.append(dict(phase=phase["name"], semantic_phase=phase.get("semantic_phase"),
                                agent_id=agent, **result))
    count = len(results)
    stopped = sum(row["stopped"] for row in results)
    return dict(window_count=count, stopped_count=stopped, unknown_count=sum(
        row["evidence_complete"] is not True for row in results),
        fraction=stopped / count if count else None, windows=results,
        denominator="all non-no-op agent/phase terminal windows",
        criterion="within 1 m, SIM backward-difference horizontal speed <0.3 m/s, continuous >=0.2 s")


def same_terminal_denominator(vp1_fraction, vp4_fraction):
    left = {(row["phase"], row["agent_id"]) for row in vp1_fraction["windows"]}
    right = {(row["phase"], row["agent_id"]) for row in vp4_fraction["windows"]}
    return (left == right and len(left) == vp1_fraction["window_count"] ==
            vp4_fraction["window_count"])


def validation_attempts_clean(records):
    if not isinstance(records, list) or not len(CASE_ORDER) <= len(records) <= MAX_ATTEMPTS:
        return False
    terminal = [row for row in records if row.get("retryable_pre_takeoff") is not True]
    retries = [index for index, row in enumerate(records)
               if row.get("retryable_pre_takeoff") is True]
    return (len(retries) <= MAX_EXTRA_RETRIES and
            [row.get("case_id") for row in terminal] == list(CASE_ORDER) and
            all(row.get("individual_pass") is True and
                row.get("run_status") == "completed" and
                row.get("flight_epoch_present") is True and
                row.get("run_directory") and
                isinstance(row.get("evidence_sha256"), dict) and
                bool(row["evidence_sha256"]) for row in terminal) and
            all(index + 1 < len(records) and
                records[index]["case_id"] == records[index + 1].get("case_id") and
                records[index].get("attempt_index") == 0 and
                records[index + 1].get("attempt_index") == 1
                for index in retries))


def decide(root):
    root = Path(root).resolve()
    if root != EXPECTED_ROOT.resolve():
        raise ValueError("HD requires the dedicated v05c validation root")
    destination = root / "hd_decision.json"
    if destination.exists():
        raise ValueError("HD decision already exists; never overwrite")
    control_path = root / "control.json"
    control = read(control_path)
    if (control.get("version") != VALIDATION_VERSION or
            control.get("completed") is not True or control.get("stopped_reason") or
            control.get("active_attempt") is not None or
            control.get("planned_cases") != list(CASE_ORDER) or
            control.get("total_sitl_budget") != TOTAL_SITL_BUDGET or
            control.get("historical_attempts_consumed") != HISTORICAL_ATTEMPTS or
            control.get("max_attempts") != MAX_ATTEMPTS or
            control.get("max_extra_retries") != MAX_EXTRA_RETRIES or
            any(control.get("aggregate_av1", {}).get(intent, {}).get("pass") is not True
                for intent in ("patrol", "reconnaissance"))):
        raise ValueError("all six validation cases and pooled AV-1 must pass before HD")
    records = control.get("records")
    if not validation_attempts_clean(records):
        raise ValueError("six accepted v05c cases must fit the remaining seven SITL attempts")
    assert_historical_binding(control)
    assert_hashes(control["frozen_sha256"])
    for record in control["records"]:
        assert_hashes(record.get("evidence_sha256", {}))
    assert_protected()
    _bound_inputs(control["bundle"], control["review"], control["profile"])
    listing, _ = verify_generation(Path(control["bundle"]) / "mission_list.json")
    entries = {entry["validation_case_id"]: entry for entry in listing["missions"]}
    if set(entries) != set(CASE_ORDER):
        raise ValueError("v05c validation bundle has incomplete case IDs")
    selected = {}
    for case in ("VP1", "VP4"):
        matched = [item for item in records if item["case_id"] == case and
                   item.get("individual_pass") is True]
        if len(matched) != 1:
            raise ValueError(case + " has no unique accepted run")
        record = matched[0]
        entry = entries[case]
        scene = read(checked_path(control["bundle"], entry["scene"]))
        directory = Path(record["run_directory"])
        metadata, _, _ = _run_artifacts(directory, scene, entry, control)
        latest = read(directory / "analysis_latest.json")
        analysis = checked_path(directory, latest["directory"])
        fraction = terminal_fraction(scene, read(analysis / "phase_windows.json"),
                                     truth_rows(analysis / "truth.csv"))
        selected[case] = dict(run_directory=str(directory), run_id=metadata["run_id"],
                              elapsed_s=metadata.get("elapsed_s"), terminal_truth_stops=fraction,
                              assessment=record["assessment"])
    vp1, vp4 = selected["VP1"], selected["VP4"]
    prm1 = vp4["assessment"]["av6"].get("vp4_terminal_prm1")
    condition1 = (isinstance(prm1, list) and bool(prm1) and all(
        row.get("uploaded_param1") == 1 and row.get("onboard_param1") and
        all(value == 1 for value in row["onboard_param1"]) for row in prm1))
    a, b = vp1["terminal_truth_stops"], vp4["terminal_truth_stops"]
    same_denominator = same_terminal_denominator(a, b)
    condition2 = (a["window_count"] > 0 and a["unknown_count"] == 0 and
                  b["window_count"] > 0 and b["unknown_count"] == 0 and
                  same_denominator and
                  b["fraction"] >= .80 and b["fraction"] - a["fraction"] >= .30)
    condition3 = (finite(vp1["elapsed_s"]) and vp1["elapsed_s"] > 0 and
                  finite(vp4["elapsed_s"]) and vp4["elapsed_s"] <= 1.10 * vp1["elapsed_s"])
    condition4 = (vp4["assessment"]["individual_pass"] is True and
                  control["aggregate_av1"]["patrol"]["pass"] is True)
    conditions = dict(onboard_terminal_prm1_is_one=condition1,
        vp4_stopped_fraction_and_improvement=condition2,
        vp4_elapsed_within_ten_percent=condition3, vp4_all_av_pass=condition4)
    result = dict(version=VERSION, pass_=True, validation_completed=True,
        terminal_hold_s=1 if all(conditions.values()) else 0,
        conditions=conditions,
        same_phase_agent_denominator=same_denominator,
        thresholds=dict(vp4_stopped_fraction_min=.8, vp4_minus_vp1_fraction_min=.3,
                        vp4_elapsed_relative_max=1.1),
        vp1=dict(run_id=vp1["run_id"], run_directory=vp1["run_directory"],
                 elapsed_s=vp1["elapsed_s"],
                 terminal_truth_stops=vp1["terminal_truth_stops"]),
        vp4=dict(run_id=vp4["run_id"], run_directory=vp4["run_directory"],
                 elapsed_s=vp4["elapsed_s"],
                 terminal_truth_stops=vp4["terminal_truth_stops"],
                 terminal_prm1=prm1, av=vp4["assessment"]["checks"]),
        elapsed_ratio=vp4["elapsed_s"] / vp1["elapsed_s"] if condition3 or
            (finite(vp1["elapsed_s"]) and vp1["elapsed_s"] > 0 and finite(vp4["elapsed_s"])) else None,
        controller_sha256=file_hash(control_path),
        validation_control_path=str(control_path),
        validation_bundle=str(Path(control["bundle"]).resolve()),
        historical_v05b_control_sha256=control["historical_failed_attempt"]["source_control_sha256"],
        total_validation_attempts=HISTORICAL_ATTEMPTS + len(records),
        profile_file_sha256=control["profile_file_sha256"],
        profile_canonical_sha256=control["profile_canonical_sha256"],
        source_review_sha256=control["source_review_sha256"],
        evidence_sha256={case: read(Path(selected[case]["run_directory"]) /
            "analysis_latest.json")["manifest_sha256"] for case in ("VP1", "VP4")},
        evidence_paths={case: str(checked_path(selected[case]["run_directory"],
            read(Path(selected[case]["run_directory"]) / "analysis_latest.json")["directory"]) /
            "manifest.json") for case in ("VP1", "VP4")})
    result["pass"] = result.pop("pass_")
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    result = decide(args.root)
    print(json.dumps(dict(hold_s=result["terminal_hold_s"],
                          conditions=result["conditions"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
