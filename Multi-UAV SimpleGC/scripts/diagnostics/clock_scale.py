"""Read frozen eligible-run clocks; write diagnostics only to a new external directory."""
import argparse
import json
import math
from pathlib import Path
import statistics
import sys

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from swarm_sim.generation import canonical_hash, file_hash
from swarm_sim.mission_evaluation import source_time
from swarm_sim.parallel_batch import read, resolve_data_root
from swarm_sim.truth import percentile
from scripts.diagnostics.v06_offline_checks import no_flight, write_guard


def distribution(values):
    return dict(count=len(values), median=statistics.median(values),
                p5=percentile(values, .05), p95=percentile(values, .95),
                min=min(values), max=max(values)) if values else dict(count=0)


def diagnose(root):
    root = Path(root).resolve()
    control_path = root / "control.json"
    inputs = {str(control_path): file_hash(control_path)}
    control = read(control_path)
    eligible = [a for a in control["attempts"] if a.get("result", {}).get("episode_quality_eligible") is True]
    rows, missing, per_run = [], [], []
    run_ids = set()
    for attempt in eligible:
        result = attempt["result"]
        run_id = result["run_id"]
        if run_id in run_ids:
            raise ValueError("duplicate eligible run_id")
        run_ids.add(run_id)
        directory = Path(result["analysis_directory"]).resolve()
        if not directory.is_relative_to(root):
            raise ValueError("analysis evidence outside the requested batch")
        artifacts = {}
        for name in ("quality.json", "clock_models.json", "manifest.json"):
            path = directory / name
            digest = file_hash(path)
            if result["evidence_sha256"].get(str(path)) != digest:
                raise ValueError(f"ledger-bound evidence changed: {path}")
            inputs[str(path)] = digest
            artifacts[name] = read(path)
        manifest = artifacts["manifest.json"]
        if (artifacts["quality.json"].get("episode_quality_eligible") is not True
                or manifest.get("episode_quality_eligible") is not True or manifest["run_id"] != run_id):
            raise ValueError("quality eligibility/run identity disagrees with ledger")
        slopes = []
        for agent in manifest["agent_ids"]:
            model = artifacts["clock_models.json"].get(agent, {})
            slope = model.get("slope")
            if (model.get("available") is not True or type(slope) not in (int, float)
                    or not math.isfinite(slope) or slope <= 0):
                missing.append(dict(run_id=run_id, agent_id=agent, reason="source clock slope unavailable"))
                continue
            duration = manifest["duration_s"]
            start, end = source_time(0.0, model), source_time(duration, model)
            source_duration = end-start if start is not None and end is not None and end > start else None
            rows.append(dict(run_id=run_id, mission_id=attempt["mission_id"], agent_id=agent,
                slope_host_per_source=slope, host_duration_excess_pct=100*(slope-1),
                source_duration_relative_to_host_pct=100*(1/slope-1),
                host_duration_s=duration, mapped_source_duration_s=source_duration,
                mapped_window_host_excess_pct=100*(duration/source_duration-1) if source_duration else None))
            slopes.append(slope)
        if slopes:
            per_run.append(statistics.median(slopes))
    for path, digest in inputs.items():
        if file_hash(path) != digest:
            raise ValueError(f"source evidence changed during read-only diagnosis: {path}")
    slope_values = [r["slope_host_per_source"] for r in rows]
    return dict(source_batch=root.name, source_directory=str(root), control_sha256=inputs[str(control_path)],
        attempts=len(control["attempts"]), quality_eligible_runs=len(eligible), models=len(rows),
        missing_models=missing, denominator="one vote per eligible run/agent clock model; no mission-success filtering",
        quantiles="linear interpolation at (n-1)*q, identical to swarm_sim.truth.percentile",
        slope_host_per_source=distribution(slope_values),
        run_median_slope_host_per_source=distribution(per_run),
        host_duration_excess_pct=distribution([r["host_duration_excess_pct"] for r in rows]),
        source_duration_relative_to_host_pct=distribution([r["source_duration_relative_to_host_pct"] for r in rows]),
        mapped_window_host_excess_pct=distribution([r["mapped_window_host_excess_pct"] for r in rows
                                                   if r["mapped_window_host_excess_pct"] is not None]),
        formulas=dict(host_duration_excess_pct="100*(a-1)", source_duration_relative_to_host_pct="100*(1/a-1)",
                      position_derivative_over_fcu_velocity="approximately 1/a; clock scale only",
                      mapped_window="D_host / (inverse_clock(D_host)-inverse_clock(0)) - 1; no extrapolation"),
        input_files=len(inputs), input_hashes_canonical_sha256=canonical_hash(inputs),
        input_files_unchanged=True, input_sha256=inputs, rows=rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root, output = args.batch.resolve(), resolve_data_root(args.output.absolute())
    if output.exists() or output.is_relative_to(root) or root.is_relative_to(output):
        parser.error("output must be new and outside the source batch")
    sys.addaudithook(no_flight)
    sys.addaudithook(write_guard(output))
    report = diagnose(root)
    output.mkdir(parents=True)
    for name, value in (("clock_scale_full.json", report),
                        ("clock_scale_summary.json", {k: v for k, v in report.items() if k not in ("rows", "input_sha256")})):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("rows", "input_sha256")}, indent=2))


if __name__ == "__main__":
    main()
