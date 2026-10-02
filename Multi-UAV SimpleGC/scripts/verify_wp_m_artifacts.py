"""M04 read-only replay against archived v0.4 execution_metrics.json attachments.

The two WP-S spike runs predate this attachment and are reported as not
applicable rather than misrepresented as numeric v1/v2 comparisons. No SITL,
analysis rerun, or write to any historical run is performed.
"""

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swarm_sim.execution_metrics import compute_execution_metrics, compute_execution_metrics_v2
from swarm_sim.route_timing import nominal_arrival_evidence


HISTORICAL = {
    "V02_r1": ROOT / "verification/v04_v1_resume_20261002/runs/recon_shared_demo_3uav_20261002T083751Z_3874072a",
    "V02_r2": ROOT / "verification/v04_ac4_v2_20261002/runs/recon_shared_demo_3uav_20261002T092201Z_3bc79cde",
    "V03_r1": ROOT / "verification/v04_ac4_v2_20261002/runs/recon_smoke_2uav_north_20261002T092554Z_f5457bbb",
    "V04_r1": ROOT / "verification/v04_ac4_v2_20261002/runs/recon_smoke_6uav_20261002T092830Z_f3b2d69b",
}
SPIKES = {
    "WP-S_r1": ROOT / "runs/spike_v04_20261001T153235Z_5eddb7ae",
    "WP-S_r2": ROOT / "runs/spike_v04_20261001T153806Z_42150c31",
}
PROCESSING = ("observation_processing_version", "duplicate_policy_version",
              "timeline_policy_version", "clock_model_version")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def first_difference(left, right, path="$"):
    if type(left) is not type(right):
        return f"{path}: {type(left).__name__} != {type(right).__name__}"
    if isinstance(left, dict):
        if set(left) != set(right):
            return f"{path}: keys {sorted(set(left) ^ set(right))}"
        for key in left:
            found = first_difference(left[key], right[key], f"{path}.{key}")
            if found:
                return found
    elif isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: length {len(left)} != {len(right)}"
        for index, (a, b) in enumerate(zip(left, right)):
            found = first_difference(a, b, f"{path}[{index}]")
            if found:
                return found
    elif left != right:
        return f"{path}: {left!r} != {right!r}"
    return None


def replay(name, run):
    analyses = list(run.glob("analysis_v*/execution_metrics.json"))
    if len(analyses) != 1:
        raise ValueError(f"{name}: expected exactly one archived v1 attachment, found {len(analyses)}")
    metric_path = analyses[0]
    analysis = metric_path.parent
    input_paths = [run / "metadata.json", run / "scenario.json", run / "events.jsonl",
                   analysis / "observations.csv", analysis / "phase_windows.json", metric_path]
    original_hashes = {str(p.relative_to(ROOT)): digest(p) for p in input_paths}
    metadata, scene, windows, stored = (read_json(input_paths[0]), read_json(input_paths[1]),
                                        read_json(input_paths[4]), read_json(input_paths[5]))
    events = [json.loads(line) for line in input_paths[2].read_text(encoding="utf-8").splitlines() if line.strip()]
    traces = {}
    with input_paths[3].open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            values = ([float(row[key]) for key in ("east_m", "north_m", "up_m", "ve_m_s", "vn_m_s", "vu_m_s")]
                      if row["valid"] == "1" else None)
            traces.setdefault(row["agent_id"], []).append((float(row["t_s"]), values))
    epoch = windows["time_epoch_host_s"]
    nominal = nominal_arrival_evidence(scene, events, metadata, epoch)
    kwargs = dict(events=events, metadata=metadata, time_epoch=epoch, nominal_arrivals=nominal["records"])
    old = compute_execution_metrics(scene, traces, windows, **kwargs)
    new = compute_execution_metrics_v2(scene, traces, windows, **kwargs)
    old["nominal_timing_deviation_s"]["assessment"] = nominal
    new["nominal_timing_deviation_s"]["assessment"] = nominal
    old, new = (json.loads(json.dumps(value, allow_nan=False)) for value in (old, new))
    stripped = dict(stored)
    for key in PROCESSING:
        stripped.pop(key, None)
    archive_difference = first_difference(stripped, old)
    new["version"] = old["version"]
    version_only_difference = first_difference(old, new)
    unchanged = all(digest(ROOT / path) == value for path, value in original_hashes.items())
    return dict(name=name, run_id=metadata["run_id"], run_directory=str(run.relative_to(ROOT)),
                archived_attachment=str(metric_path.relative_to(ROOT)), aircraft_count=len(traces),
                observation_rows=sum(len(rows) for rows in traces.values()),
                archived_v1_replay_equal=archive_difference is None,
                archived_v1_first_difference=archive_difference,
                v2_equal_except_top_level_version=version_only_difference is None,
                v2_first_difference=version_only_difference,
                archived_sources_unchanged=unchanged, archived_source_sha256=original_hashes)


def verify(output):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / "tmp_v05").resolve()):
        raise ValueError("M04 report output must be under tmp_v05")
    if output.exists():
        raise ValueError("M04 report output already exists; historical evidence is append-only")
    v06_root = ROOT / "verification/v04_v06_20261002/execution/attempts"
    v06 = {f"V06_{index:02d}": run for index, run in enumerate(sorted(
        run for attempt in v06_root.iterdir() for run in attempt.iterdir() if (run / "metadata.json").is_file()), 1)}
    if len(v06) != 10:
        raise ValueError(f"expected 10 archived V06 runs, found {len(v06)}")
    comparisons = [replay(name, run) for name, run in {**HISTORICAL, **v06}.items()]
    not_applicable = [dict(name=name, run_directory=str(path.relative_to(ROOT)),
        archived_v1_attachment_available=bool(list(path.glob("analysis_v*/execution_metrics.json"))),
        applicable=False, reason="WP-S used leg-by-leg mode before execution_metrics.json existed; no v1 attachment or v3 semantic window")
        for name, path in SPIKES.items()]
    passed = all(row["archived_v1_replay_equal"] and row["v2_equal_except_top_level_version"]
                 and row["archived_sources_unchanged"] for row in comparisons)
    result = dict(schema_version=1, verification="M04_execution_artifacts_v2_historical_replay",
                  status="PASS" if passed else "FAIL", new_sitl_runs=0,
                  comparison_count=len(comparisons), inapplicable_wp_s=not_applicable,
                  repeated_visit_synthetic_test="tests/test_wp_m_artifacts.py",
                  note="Actual archived v1 attachments are compared field by field to v1 replay, then v2; only the top-level version differs. The phase passage window ends at the next scheduled release and is half-open for stop assignment; arrival_s service semantics are unchanged.",
                  comparisons=comparisons)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    if not passed:
        raise AssertionError(f"M04 historical replay failed; inspect {output}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "tmp_v05/wp_m/m04_artifacts_regression.json"))
    args = parser.parse_args()
    report = verify(args.output)
    print(json.dumps({key: report[key] for key in ("status", "comparison_count", "new_sitl_runs")}, ensure_ascii=False))
