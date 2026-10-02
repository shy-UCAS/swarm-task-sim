"""Read-only WP-M AC4 v3 regression against the six frozen v0.4 route runs."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import verify_ac4_v2 as legacy
from swarm_sim.ac4_timing import evaluate_ac4_timing_v3
from swarm_sim.analysis import digest


V2_FINAL = ROOT / "tmp_v04/ac4_v2_20261002/final_acceptance.json"
V2_SPIKE = ROOT / "tmp_v04/ac4_v2_20261002/offline_review_final.json"
MAX_D_DELTA_S = .05


def _cases():
    spikes = legacy.read(V2_SPIKE)["wp_s_offline_reviews"]
    final = legacy.read(V2_FINAL)["records"]
    route = [r for r in final if r.get("validation_id") in ("V02", "V03", "V04")]
    if len(spikes) != 2 or [r["validation_id"] for r in route] != ["V02", "V02", "V03", "V04"]:
        raise ValueError("historical route ledger is incomplete")
    return [("WP-S", row, True) for row in spikes] + [(row["validation_id"], row["ac4_v2"], False) for row in route]


def _replay(label, baseline, spike):
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
    comparisons = []
    result = dict(label=label, run_id=baseline["run_id"], run_directory=str(directory),
                  source_sha256=before, adaptation=adaptation, channel_provenance=provenance,
                  comparisons=comparisons, pass_gate=True)
    for channel in ("truth", "observation"):
        starts, hover_evidence = legacy.terminal_hover_evidence(scene, channels[channel], events,
                                                                 metadata, epoch, channel, clocks)
        current = evaluate_ac4_timing_v3(scene, channels[channel], events, metadata, epoch,
                                         channel=channel, terminal_hover_starts=starts)
        result.setdefault("v3", {})[channel] = current
        result.setdefault("hover_evidence", {})[channel] = hover_evidence
        older = baseline["channels"][channel]
        for name, v2_phase in older["per_phase"].items():
            v3_phase = current["per_phase"].get(name)
            if v3_phase is None:
                raise ValueError(f"missing v3 phase: {name}")
            for mapping in ("primary", "crosscheck"):
                old_d = v2_phase[mapping]["D_s"]
                new_d = v3_phase[mapping]["D_s"]
                delta = abs(new_d - old_d) if old_d is not None and new_d is not None else None
                old_verdict = v2_phase[mapping]["within_tau"]
                new_verdict = v3_phase[mapping]["within_tau"]
                passed = delta is not None and delta <= MAX_D_DELTA_S and old_verdict == new_verdict
                comparisons.append(dict(channel=channel, phase=name, mapping=mapping,
                                        v2_D_s=old_d, v3_D_s=new_d, absolute_delta_s=delta,
                                        v2_within_tau=old_verdict, v3_within_tau=new_verdict,
                                        v3_issues=v3_phase.get("issues", []), pass_gate=passed))
                if not passed:
                    result["pass_gate"] = False
                    result["stop_reason"] = f"M03_regression_failed:{channel}:{name}:{mapping}"
                    break
            if not result["pass_gate"]:
                break
        if not result["pass_gate"]:
            break
        if older["within_tau"] != current["within_tau"] or older["crosscheck_within_tau"] != current["crosscheck_within_tau"]:
            result["pass_gate"] = False
            result["stop_reason"] = f"M03_run_verdict_failed:{channel}"
            break
    after = legacy.guarded_tree(directory)
    result["historical_sources_unchanged"] = before == after
    if not result["historical_sources_unchanged"]:
        result["pass_gate"] = False
        result["stop_reason"] = "historical_sources_changed"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    output = dict(version="wp_m_ac4_v3_history_review_v1", generated_utc=datetime.now(timezone.utc).isoformat(),
                  v2_baseline_sha256={str(path): digest(path) for path in (V2_FINAL, V2_SPIKE)},
                  max_D_delta_s=MAX_D_DELTA_S, new_sitl_runs=0, cases=[], pass_gate=True)
    for label, baseline, spike in _cases():
        result = _replay(label, baseline, spike)
        output["cases"].append(result)
        if not result["pass_gate"]:
            output["pass_gate"] = False
            output["stop_reason"] = result.get("stop_reason")
            break
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(dict(output=str(args.output), pass_gate=output["pass_gate"],
                          cases=[dict(label=r["label"], run_id=r["run_id"], pass_gate=r["pass_gate"],
                                      comparisons=len(r["comparisons"]), stop_reason=r.get("stop_reason"))
                                 for r in output["cases"]])))
    if not output["pass_gate"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
