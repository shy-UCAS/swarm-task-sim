"""Summarize retained v0.2 task attempts and their current versioned analyses."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_sim.recording import write_json


def main():
    rows = []
    for run in sorted((ROOT / "runs").iterdir()):
        if not (run / "metadata.json").exists() or not (run / "analysis_latest.json").exists():
            continue
        meta = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
        if "task_spec" not in meta["scenario"]:
            continue
        pointer = json.loads((run / "analysis_latest.json").read_text(encoding="utf-8"))
        analysis = run / pointer["directory"]
        def read(name):
            return json.loads((analysis / name).read_text(encoding="utf-8"))
        quality, labels, clocks, params = map(read, ("quality.json", "labels.json", "clock_models.json", "logged_parameters.json"))
        rows.append(dict(run=run.name, analysis=analysis.name, status=meta["status"],
            task=labels["assigned_intent"], family_id=meta["scenario"]["family_id"], elapsed_s=meta["elapsed_s"],
            mission_success=labels["mission_success"], failure_reason=labels["failure_reason"],
            eligible=quality["benchmark_eligible"], frames=quality["frames"],
            minimum_separation_m=quality["minimum_separation_m"],
            observation_valid_fraction=quality["observation_valid_fraction"], truth_valid_fraction=quality["truth_valid_fraction"],
            receive_fit_heldout_p95_ms={a: c["receive_residual_abs_p95_s"] * 1000 if c["available"] else None for a, c in clocks.items()},
            estimation_rms_m={a: e["rms_m"] for a, e in quality["estimation_error"].items()},
            geometry_coverage={a: b["coverage"]["ratio"] for a, b in labels["observed_behavior"].items() if "coverage" in b},
            logged_parameters={a: dict(count=len(p), SYSID_THISMAV=p.get("SYSID_THISMAV")) for a, p in params.items()},
            cleanup=meta["cleanup"]))
    write_json(ROOT / "verification_v02.json", dict(attempts=rows,
        note="All task attempts retained, including semantic failures; synchronization residuals are not absolute error bounds."))
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
