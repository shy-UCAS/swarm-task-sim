"""Replay frozen VP1 sources into a new external r1.2 analysis, without SITL."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_sim.analysis_v3 import analyze_run_v3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp_v05/r12/vp1_analysis_v2")
    args = parser.parse_args()
    control = json.loads((ROOT / "verification/v05c_validation_20261002/control.json").read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output, quality, labels = analyze_run_v3(control["records"][0]["run_directory"], control["quality_policy"],
        progress_mapping_version="ordered_route_progress_v2", acceptance_policy="v05_acceptance_r1_2",
        acceptance_stage="validation", output_directory=args.output, update_latest=False)
    print(json.dumps(dict(output=str(output), episode_quality_eligible=quality["episode_quality_eligible"],
        assessment=quality["validation_policy"], laps={ch: labels["mission_metrics"][ch].get("per_agent_laps_observed")
        for ch in ("truth", "observation")}), ensure_ascii=False))
    return int(not quality["validation_policy"]["individual_pass"])


if __name__ == "__main__":
    raise SystemExit(main())
