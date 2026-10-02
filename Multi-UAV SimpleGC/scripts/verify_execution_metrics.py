"""Read-only A4 regression: copy 15 episode inputs, compare new diagnostics.

The original audit scripts are never imported/executed because their module
body overwrites audit evidence. Reference data and scripts are hash recorded.
"""

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from swarm_sim.execution_metrics import compute_execution_metrics


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def verify(output):
    output = Path(output).resolve()
    if not output.is_relative_to((PROJECT / "tmp_v04").resolve()) or output.exists():
        raise ValueError("output must be a fresh directory below tmp_v04")
    reference_paths = [PROJECT / "audit_v04" / name for name in ("A4_final.py", "A4_dwell.json", "A4_sync.json")]
    guarded = {str(path): digest(path) for path in reference_paths}
    dwell = {r["episode"]: r for r in json.loads(reference_paths[1].read_text(encoding="utf-8"))}
    sync = {r["episode"]: r for r in json.loads(reference_paths[2].read_text(encoding="utf-8"))}
    rows = []
    datasets = [PROJECT / "verification/v03_pilot_final_20260930/dataset",
                PROJECT / "verification/v03_integration_20260930/dataset_final"]
    for dataset in datasets:
        manifest_path = dataset / "dataset_manifest.json"
        guarded[str(manifest_path)] = digest(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for episode in manifest["episodes"]:
            run_id = episode["run_id"]
            source = dataset / "episodes" / run_id
            target = output / "inputs" / run_id
            if target.exists():
                raise ValueError(f"duplicate run in datasets: {run_id}")
            target.mkdir(parents=True)
            for name in ("observations.csv", "phase_windows.json", "allocation.json", "manifest.json"):
                guarded[str(source / name)] = digest(source / name)
                shutil.copy2(source / name, target / name)
            item_manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            scene_path = Path(item_manifest["run_directory"]) / "scenario.json"
            guarded[str(scene_path)] = digest(scene_path)
            shutil.copy2(scene_path, target / "scenario.json")
            scene = json.loads((target / "scenario.json").read_text(encoding="utf-8"))
            windows = json.loads((target / "phase_windows.json").read_text(encoding="utf-8"))
            traces = {}
            with (target / "observations.csv").open(encoding="utf-8", newline="") as stream:
                for row in csv.DictReader(stream):
                    values = [float(row[key]) for key in ("east_m", "north_m", "up_m", "ve_m_s", "vn_m_s", "vu_m_s")] if row["valid"] == "1" else None
                    traces.setdefault(row["agent_id"], []).append((float(row["t_s"]), values))
            metrics = compute_execution_metrics(scene, traces, windows)
            write(output / "metrics" / f"{run_id}.json", metrics)
            result = dict(run_id=run_id, dataset=str(dataset.relative_to(PROJECT)), agent_count=len(traces), thresholds={})
            if run_id not in dwell or run_id not in sync:
                result.update(passed=None, reference_available=False,
                              reason="original A4 script skipped episode without available semantic windows",
                              actual_fraction_window_s=metrics["fraction_window_s"],
                              invalid_agents=metrics["invalid_agents"])
                rows.append(result)
                continue
            result["reference_available"] = True
            for threshold, key in (("0.3", "loose03"), ("0.5", "loose05")):
                actual = {agent: report["stop_count"] for agent, report in metrics["thresholds"][threshold]["per_agent"].items()}
                expected = dwell[run_id][key]
                result["thresholds"][threshold] = dict(actual_stop_counts=actual, reference_stop_counts=expected,
                                                       stop_counts_equal=actual == expected)
            actual_sync = metrics["thresholds"]["0.3"]["synchronized_time_fraction"]
            expected_sync = sync[run_id]["sync_frac"]
            result.update(actual_sync_fraction=actual_sync, reference_sync_fraction=expected_sync,
                          sync_absolute_difference=abs(actual_sync - expected_sync),
                          sync_pass=abs(actual_sync - expected_sync) <= 1e-6,
                          actual_common_events=metrics["thresholds"]["0.3"]["common_overlap_event_count"],
                          reference_common_events=sync[run_id]["common_events"])
            result["passed"] = result["sync_pass"] and all(r["stop_counts_equal"] for r in result["thresholds"].values())
            rows.append(result)
    changed = [path for path, original in guarded.items() if digest(Path(path)) != original]
    comparable = [r for r in rows if r["reference_available"]]
    report = dict(schema_version=1, evidence_class="existing_SITL_offline_copies", new_sitl_runs=0,
        status="IMPLEMENTED_AND_TESTED" if all(r["passed"] for r in comparable) and not changed else "PARTIAL",
        episode_count=len(rows), agent_count=sum(r["agent_count"] for r in rows),
        comparable_episode_count=len(comparable), no_reference_episode_count=len(rows) - len(comparable),
        comparable_agent_count=sum(r["agent_count"] for r in comparable),
        passed_episodes=sum(r["passed"] is True for r in rows), source_files_unchanged=not changed,
        maximum_sync_absolute_difference=max((r["sync_absolute_difference"] for r in comparable), default=None),
        comparison_scope="A4_final.py: per-agent stop counts at 0.3/0.5 m/s for >=0.2s; sampled 0.3 sync fraction",
        common_event_note="exact simultaneous intersections; legacy envelope-only count also retained in per-run metrics",
        original_sha256=guarded, changed_sources=changed, episodes=rows)
    write(output / "execution_metrics_regression.json", report)
    if changed or not all(r["passed"] for r in comparable):
        raise AssertionError("A4 migration comparison failed; inspect preserved report")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(PROJECT / "tmp_v04/wp_g/execution_metrics"))
    args = parser.parse_args()
    result = verify(args.output)
    print(json.dumps({key: result[key] for key in ("status", "episode_count", "agent_count", "passed_episodes", "maximum_sync_absolute_difference", "source_files_unchanged")}))
