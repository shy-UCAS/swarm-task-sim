"""Reproducible, no-flight checks for the v0.6 pause-A review.

All generated evidence goes into a new, explicit directory outside Git and the
frozen archive. Importing this module does not run a check or write any files.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import csv
import json
import os
from pathlib import Path
import statistics
import sys

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")


def no_flight(event, args):
    if event in ("subprocess.Popen", "os.system", "os.spawn", "os.exec"):
        raise RuntimeError("pause-A diagnostics forbid subprocesses and simulation")


def write_guard(output):
    def guard(event, args):
        paths = []
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            _, mode, flags = args
            if (mode and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                paths.append(args[0])
        elif event in ("os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime"):
            paths.append(args[0])
        elif event in ("os.rename", "os.link", "os.symlink"):
            paths.extend(args[:2])
        for path in paths:
            resolved = Path(os.fsdecode(path)).resolve()
            if resolved != output and not resolved.is_relative_to(output):
                raise PermissionError("offline check write outside its new output directory: " + str(resolved))
    return guard


def golden(output):
    """Compare all 260 generated tasks/plans against the pre-change DR130."""
    from swarm_sim.generation import canonical_hash, generate, verify_generation
    fixture = read(PROJECT / "tests/fixtures/intent_registry_DR130_golden.json")
    generated = output / "generated_DR130"
    generate(PROJECT / "generation_profiles/dual_intent_v05c.json", generated)
    listing, _ = verify_generation(generated / "mission_list.json")
    differences = []
    if canonical_hash(listing) != fixture["listing_canonical_sha256"]:
        differences.append(dict(subject="full mission_list", expected=fixture["listing_canonical_sha256"],
                                actual=canonical_hash(listing)))
    by_id = {entry["mission_id"]: entry for entry in listing["missions"]}
    if len(by_id) != fixture["task_count"]:
        differences.append(dict(subject="task count", expected=fixture["task_count"], actual=len(by_id)))
    checked = []
    for expected in fixture["tasks"]:
        entry = by_id.get(expected["mission_id"])
        if entry is None:
            differences.append(dict(subject=expected["mission_id"], missing=True))
            continue
        actual = dict(entry_sha256=canonical_hash(entry),
                      task_sha256=canonical_hash(read(generated / entry["task"])),
                      plan_sha256=canonical_hash(read(generated / entry["scene"])))
        passed = all(actual[key] == expected[key] for key in actual)
        checked.append(dict(mission_id=expected["mission_id"], passed=passed, **actual))
        if not passed:
            differences.append(dict(subject=expected["mission_id"], actual=actual,
                                    expected={key: expected[key] for key in actual}))
    result = dict(check="v05_DR130_frozen_generation", expected=260, checked=len(checked),
                  passed=sum(row["passed"] for row in checked), differences=differences,
                  pass_all=not differences and len(checked) == 260,
                  metadata_exclusions=[], fixture=str(PROJECT / "tests/fixtures/intent_registry_DR130_golden.json"),
                  rows=checked)
    save(output / "golden_report.json", result)
    return result


def distribution(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return dict(n=0, minimum=None, median=None, maximum=None)
    return dict(n=len(values), minimum=values[0], median=statistics.median(values), maximum=values[-1])


def planning(output, profile):
    """Record all accepted/rejected plans; do not turn infeasibility into a GO."""
    from swarm_sim.generation import generate
    generated = output / "generated_v06"
    summary = generate(profile, generated)
    listing = read(generated / "mission_list.json")
    groups = defaultdict(list)
    for entry in listing["missions"]:
        if entry.get("status") != "planned":
            spec = read(generated / entry["task"])
            groups[(entry["intent"], spec.get("flight_pattern"))].append(dict(
                mission_id=entry["mission_id"], family_id=entry["family_id"], intent=entry["intent"],
                flight_pattern=spec.get("flight_pattern"), status=entry.get("status"),
                reason=entry.get("reason"), nominal_min_clearance_m=None,
                nominal_time_estimate_s=None, world_bounds_pass=None))
            continue
        scene = read(generated / entry["scene"])
        spec = scene["task_spec"]
        pattern = spec.get("flight_pattern")
        row = dict(mission_id=entry["mission_id"], family_id=entry["family_id"], status="planned",
                   intent=entry["intent"], flight_pattern=pattern,
                   nominal_min_clearance_m=scene["planning"]["nominal_min_clearance_m"],
                   nominal_time_estimate_s=scene["planning"]["nominal_time_estimate_s"],
                   world_bounds_pass=scene["planning"]["feasibility_checks"]["command_limits"]["world_bounds_pass"])
        groups[(entry["intent"], pattern)].append(row)
    result_groups = []
    for (intent, pattern), rows in sorted(groups.items(), key=lambda item: str(item[0])):
        clearance = [row["nominal_min_clearance_m"] for row in rows]
        result_groups.append(dict(intent=intent, flight_pattern=pattern, tasks=len(rows),
            planned=sum(row["status"] == "planned" for row in rows),
            rejected=sum(row["status"] != "planned" for row in rows),
            clearance_m=distribution(clearance), below_10m=sum(value is not None and value < 10 for value in clearance),
            world_bounds_pass=sum(row["world_bounds_pass"] is True for row in rows),
            nominal_duration_s=distribution([row["nominal_time_estimate_s"] for row in rows])))
    result = dict(check="v06_offline_planning", profile=str(Path(profile).resolve()),
                  counts=summary["counts"], expected_families=300, expected_tasks=900,
                  task_entries=len(listing["missions"]),
                  accepted_tasks=sum(e.get("status") == "planned" for e in listing["missions"]),
                  groups=result_groups, rejections=summary.get("rejections", []),
                  rejection_reasons=dict(Counter(row["reason"] for row in summary.get("rejections", []))),
                  simulation_runs=0, rows=[row for rows in groups.values() for row in rows])
    save(output / "planning_report.json", result)
    return result


def cross_negative(output, archive):
    """Apply the real passage geometry to both channels of every v0.5 episode.

    Relabel the existing main-task window as transit, so a negative result
    cannot be manufactured by a missing role, an intent name, or flight metadata.
    No archived scene, trajectory, window, label, or hash is modified.
    """
    from swarm_sim.rapid_passage import evaluate_channel, THRESHOLDS, THRESHOLD_BASIS
    from swarm_sim.route_windows import service_window_view
    dataset = Path(archive) / "Multi-UAV SimpleGC/verification/v05_batch_20261002/dataset"
    manifest = read(dataset / "dataset_manifest.json")
    rows = []
    for entry in manifest["episodes"]:
        episode = dataset / entry["directory"]
        spec = read(episode / "task.json")
        original_intent = spec["mission"]["intent"]
        original_role = "observe" if original_intent == "reconnaissance" else "patrol"
        window_artifact = read(episode / "phase_windows.json")
        scene = dict(task_spec=spec, vehicles=spec["scenario"]["vehicles"], max_gap_s=spec["execution"]["max_gap_s"])
        for channel, filename in (("truth", "truth.csv"), ("observation", "observations.csv")):
            traces = defaultdict(list)
            with (episode / filename).open(encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    xyz = tuple(float(row[key]) for key in ("east_m", "north_m", "up_m")) if row["valid"] == "1" else None
                    traces[row["agent_id"]].append((float(row["t_s"]), xyz))
            windows = copy.deepcopy(service_window_view(window_artifact["channels"][channel]))
            for window in windows:
                if window["semantic_phase"] == original_role:
                    window["semantic_phase"] = "transit"
                    window["role"] = "transit"
            result = evaluate_channel(scene, traces, windows, {})
            evidence = result["metrics"]["rapid_passage"]
            rows.append(dict(run_id=entry["run_id"], original_intent=original_intent,
                             channel=channel, success=evidence["success"],
                             evidence_complete=evidence["evidence_complete"], conditions=result["conditions"]))
    positives = [row for row in rows if row["success"] is True]
    groups = []
    for intent in ("reconnaissance", "patrol"):
        for channel in ("truth", "observation"):
            selected = [row for row in rows if row["original_intent"] == intent and row["channel"] == channel]
            groups.append(dict(intent=intent, channel=channel, total=len(selected),
                               positive=sum(row["success"] is True for row in selected),
                               negative=sum(row["success"] is False for row in selected),
                               unknown=sum(row["success"] is None for row in selected)))
    result = dict(check="v05_all_episodes_cross_negative", episodes=len(manifest["episodes"]),
                  channel_checks=len(rows), positives=positives, pass_all=not positives,
                  groups=groups, thresholds=THRESHOLDS, threshold_basis=THRESHOLD_BASIS,
                  adaptation="original service bounds and actual trajectories; observe/patrol relabeled transit only",
                  rows=rows)
    save(output / "cross_negative_report.json", result)
    return result


def archive_check(output, archive, baseline):
    before = read(baseline)
    after = {}
    for path in Path(archive).rglob("*"):
        if path.is_file():
            stat = path.stat()
            after[path.relative_to(archive).as_posix()] = [stat.st_size, stat.st_mtime_ns]
    changed = [name for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)]
    result = dict(check="archive_file_inventory", files_before=len(before), files_after=len(after),
                  changed=changed, pass_all=not changed,
                  method="complete path/size/mtime_ns inventory including .git; not a full content rehash")
    save(output / "archive_check.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("golden", "planning", "cross-negative", "archive-check"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args(argv)
    from swarm_sim.parallel_batch import resolve_data_root
    output = resolve_data_root(str(args.output))
    if output.exists():
        parser.error("output must be a new directory")
    if args.action == "planning" and args.profile is None:
        parser.error("planning requires --profile")
    if args.action == "archive-check" and (args.archive is None or args.baseline is None):
        parser.error("archive-check requires --archive and --baseline")
    if args.action == "cross-negative" and args.archive is None:
        parser.error("cross-negative requires --archive")
    sys.addaudithook(no_flight)
    output.mkdir(parents=True)
    sys.addaudithook(write_guard(output))
    result = (golden(output) if args.action == "golden" else
              planning(output, args.profile) if args.action == "planning" else
              cross_negative(output, args.archive) if args.action == "cross-negative" else
              archive_check(output, args.archive, args.baseline))
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("rows", "rejections", "rejection_reasons")}, ensure_ascii=False, indent=2))
    return int(result.get("pass_all") is False)


if __name__ == "__main__":
    raise SystemExit(main())
