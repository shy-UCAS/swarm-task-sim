"""Reanalyze existing evidence without flying or replacing historical analyses."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_sim import __version__
from swarm_sim.analysis import analyze_run, digest
from swarm_sim.dataset import build_dataset
from swarm_sim.quality import resolve_policy
from swarm_sim.recording import write_json


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new dataset/report directory")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a fresh directory")
    summary = read(ROOT / "verification_v02.json")
    runs = [ROOT / "runs" / entry["run"] for entry in summary["attempts"]]
    runs.append(ROOT / "runs/timeout_check_20260925T091007Z_bed8783b")
    comparisons = []
    for run in runs:
        old_pointer = read(run / "analysis_latest.json")
        old_directory = run / old_pointer["directory"]
        old_quality = read(old_directory / "quality.json")
        # Byte hashes cover raw telemetry, SIM logs and immutable execution metadata.
        evidence = [run / name for name in ("metadata.json", "scenario.json", "events.jsonl")]
        evidence.extend((run / "raw").glob("*.jsonl"))
        evidence.extend((run / "sitl").glob("*/logs/*.BIN"))
        evidence.extend(old_directory.glob("*"))
        before = {str(path.relative_to(run)): digest(path) for path in evidence if path.is_file()}
        output, quality, labels = analyze_run(run)
        unchanged = all(digest(run / name) == expected for name, expected in before.items())
        if not unchanged:
            raise RuntimeError(f"historical evidence changed: {run}")
        meta = read(run / "metadata.json")
        counts = quality["observation_filter"]
        comparisons.append(dict(run=run.name, old_analysis=old_directory.name, analysis=output.name,
            simulator_version=meta.get("version"), analysis_version=__version__, evidence_unchanged=unchanged,
            previous_threshold_s=old_quality.get("timing_residual_threshold_s"),
            previous_eligible=old_quality["benchmark_eligible"], benchmark_eligible=quality["benchmark_eligible"],
            strict_benchmark_eligible=quality["strict_benchmark_eligible"], clock_quality=quality["clock_quality"],
            mission_success=labels["mission_success"], observation_valid_fraction=quality["observation_valid_fraction"],
            truth_valid_fraction=quality["truth_valid_fraction"], observation_timeline_errors=quality["observation_timeline_errors"],
            whole_run_rejections={agent: stats["whole_run"]["dropped"] for agent, stats in counts.items()},
            evaluation_window_rejections={agent: stats["evaluation_window"]["dropped"] for agent, stats in counts.items()}))
        print(f"{run.name}: {quality['clock_quality']['overall']}, eligible={quality['benchmark_eligible']}, "
              f"strict={quality['strict_benchmark_eligible']}, mission={labels['mission_success']}", flush=True)
    dataset = build_dataset(runs, args.output)
    report = dict(version=__version__, quality_policy=resolve_policy(), counts=dataset["counts"], comparisons=comparisons,
                  verification_scope="offline historical evidence; no new SITL integration run")
    write_json(args.output / "verification_report.json", report)
    print(json.dumps(dict(output=str(args.output.resolve()), counts=dataset["counts"]), indent=2))


if __name__ == "__main__":
    main()
