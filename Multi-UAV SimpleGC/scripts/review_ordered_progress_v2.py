"""Offline r1.2 ordered-route v2 tests and all-phase frozen-history regression.

Writes a new evidence directory; never changes historical runs or analyses.
Exit status is nonzero when a test or the requested 0.05 s regression fails.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import review_wp_m as review
from swarm_sim.ac4_timing import ORDERED_ROUTE_PROGRESS_V2_VERSION, evaluate_ac4_timing_v3
from swarm_sim.analysis import digest


def regression_case(label, baseline, spike):
    legacy = review.legacy
    directory = Path(baseline["run_directory"]).resolve()
    before = legacy.guarded_tree(directory)
    metadata = legacy.read(directory / "metadata.json")
    scene = legacy.read(directory / "scenario.json")
    events = legacy.lines(directory / "events.jsonl")
    if spike:
        channels, clocks, epoch, provenance = legacy.spike_channels(directory, metadata, scene, events)
        scene, events, adaptation = legacy.adapt_spike(directory, metadata, scene, events)
    else:
        channels, clocks, epoch, provenance = legacy.v3_channels(directory, metadata, scene)
        adaptation = None
    result = dict(label=label, run_id=baseline["run_id"], run_directory=str(directory),
                  source_sha256=before, adaptation=adaptation, channel_provenance=provenance,
                  comparisons=[], channels={}, pass_gate=True)
    for channel in ("truth", "observation"):
        starts, hover = legacy.terminal_hover_evidence(scene, channels[channel], events,
                                                      metadata, epoch, channel, clocks)
        current = evaluate_ac4_timing_v3(scene, channels[channel], events, metadata, epoch,
            channel=channel, terminal_hover_starts=starts,
            progress_mapping_version=ORDERED_ROUTE_PROGRESS_V2_VERSION)
        result["channels"][channel] = current
        result.setdefault("hover_evidence", {})[channel] = hover
        older = baseline["channels"][channel]
        for name, prior_phase in older["per_phase"].items():
            phase = current["per_phase"][name]
            for mapping in ("primary", "crosscheck"):
                old_d, new_d = prior_phase[mapping]["D_s"], phase[mapping]["D_s"]
                delta = abs(new_d - old_d) if old_d is not None and new_d is not None else None
                verdict_same = prior_phase[mapping]["within_tau"] == phase[mapping]["within_tau"]
                passed = delta is not None and delta <= review.MAX_D_DELTA_S and verdict_same
                result["comparisons"].append(dict(channel=channel, phase=name, mapping=mapping,
                    AC4_v2_D_s=old_d, ordered_v2_D_s=new_d, absolute_delta_s=delta,
                    verdict_same=verdict_same, pass_gate=passed, issues=phase["issues"]))
                result["pass_gate"] &= passed
        run_verdict_same = (older["within_tau"] == current["within_tau"] and
                           older["crosscheck_within_tau"] == current["crosscheck_within_tau"])
        result.setdefault("run_verdict_same", {})[channel] = run_verdict_same
        result["pass_gate"] &= run_verdict_same
    result["historical_sources_unchanged"] = before == legacy.guarded_tree(directory)
    result["pass_gate"] &= result["historical_sources_unchanged"]
    return result


def write_new(path, content):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(content, handle, ensure_ascii=False, indent=2, allow_nan=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_files = [Path(__file__), ROOT / "swarm_sim/ac4_timing.py",
                    ROOT / "tests/test_ordered_route_progress_v2.py",
                    ROOT / "tests/test_wp_m_progress.py", ROOT / "tests/test_ac4_timing.py"]
    report = dict(version="r12_ordered_route_progress_v2_review_v1",
        generated_utc=datetime.now(timezone.utc).isoformat(),
        mapping_version=ORDERED_ROUTE_PROGRESS_V2_VERSION, entry_tolerance_m=3., exit_tolerance_m=3.5,
        maximum_allowed_D_delta_s=review.MAX_D_DELTA_S, new_sitl_runs=0,
        code_sha256={str(path): digest(path) for path in source_files},
        baseline_sha256={str(path): digest(path) for path in (review.V2_FINAL, review.V2_SPIKE)},
        tests=[], cases=[], pass_gate=True)
    for pattern in ("test*progress*.py", "test_ac4*.py"):
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"]
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        log = output / ("progress_tests.log" if "progress" in pattern else "ac4_tests.log")
        with log.open("x", encoding="utf-8") as handle:
            handle.write(process.stdout + process.stderr)
        report["tests"].append(dict(command=command, returncode=process.returncode,
                                     log=str(log), log_sha256=digest(log)))
        report["pass_gate"] &= process.returncode == 0
    # Deliberately inspect every phase and channel after a failure. This is
    # read-only diagnosis, not permission to continue validation flights.
    for label, baseline, spike in review._cases():
        result = regression_case(label, baseline, spike)
        report["cases"].append(result)
        report["pass_gate"] &= result["pass_gate"]
        print(json.dumps(dict(run_id=result["run_id"], pass_gate=result["pass_gate"],
                              comparisons=len(result["comparisons"]))), flush=True)
    report_path = output / "review.json"
    write_new(report_path, report)
    comparisons = [row for case in report["cases"] for row in case["comparisons"]]
    summary = dict(report=str(report_path), report_sha256=digest(report_path),
        pass_gate=report["pass_gate"], tests_pass=all(t["returncode"] == 0 for t in report["tests"]),
        total_comparisons=len(comparisons), passed_comparisons=sum(row["pass_gate"] for row in comparisons),
        all_verdicts_same=all(row["verdict_same"] for row in comparisons),
        all_historical_sources_unchanged=all(c["historical_sources_unchanged"] for c in report["cases"]),
        failures=[dict(run_id=case["run_id"], **row) for case in report["cases"]
                  for row in case["comparisons"] if not row["pass_gate"]])
    write_new(output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if not report["pass_gate"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
