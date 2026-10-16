"""Registered M3a inputs and bounded checks; never replace a fixed skeleton."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from task_v07.io import read_json, save_json, sha
from task_v07.unified.geometry_config import PATH as GEOMETRY_CONFIG

EVIDENCE = PROJECT / "docs/v07/evidence/m3"


def register_inputs():
    qd = read_json(PROJECT / "docs/v07/evidence/m2/qd_summary.json")
    qd_registration = Path(qd["attempt"]) / "registration.json"
    source = Path(read_json(qd_registration)["descriptor_attempt"])
    descriptors = read_json(source / "private_skeleton_descriptors.json")
    fixed = [r["skeleton_id"] for r in qd["rows"] if r["intent"] == "transit"]
    by_id = {r["skeleton_id"]: r for r in descriptors}
    selected = []
    for sid in fixed:
        d = by_id[sid]
        approach = d["common_draw"]["approach_mode"]
        other = sorted(r["skeleton_id"] for r in descriptors if r["subset"] == "regular"
                       and r["base_intent"] == "transit" and r["common_draw"]["approach_mode"] == approach
                       and r["skeleton_id"] != sid)
        if not other:
            raise ValueError(f"Fixed-input cell lacks second skeleton: {approach}")
        for candidate in (sid, other[0]):
            selected.append({"skeleton_id": candidate, "approach_mode": approach, "q3": candidate == sid})
    if len(fixed) != 2 or len(selected) != 4:
        raise ValueError("M3a requires exactly two Q3 and four Q2 skeletons")
    source_registration = read_json(source / "registration.json")
    candidates = {r["candidate_index"]: r for r in read_json(Path(source_registration["source_attempt"]) / "candidates.json")}
    source_hashes = []
    families = {by_id[r["skeleton_id"]]["family_id"] for r in selected}
    for row in source_registration["selected"]:
        if row["family_id"] not in families:
            continue
        directory = Path(candidates[row["candidate_index"]]["directory"])
        for name, expected in row["source_sha256"].items():
            path = directory / name
            if sha(path) != expected:
                raise ValueError(f"Source hash mismatch: {path}")
            source_hashes.append({"path": str(path), "sha256": expected})
    frozen = ["task_v07/geometry.py", "task_v07/visibility.py", "task_v07/execution.py",
              "task_v07/labels.py", "task_v07/criteria_labels.py", "task_v07/criteria_diagnostics.py",
              "task_v07/detectors.py", "task_v07/expansion/multi_labels.py", "task_v07/io.py",
              "task_v07/expansion/contracts.py", "task_v07/expansion/sampling.py",
              "task_v07/expansion/public_approach_shape.py", "task_v07/expansion/views.py",
              "task_v07/unified/rehearsal.py", "task_v07/unified/timing.py", "task_v07/unified/config.py",
              "configs/generator/generator_v07_r1.json", "configs/criteria/criteria_v07_r1.json",
              "configs/fast_dynamics/m3_r2_20261013_v1.json"]
    frozen += [p.relative_to(PROJECT).as_posix() for p in (PROJECT / "swarm_sim/fast_dynamics").rglob("*.py")]
    frozen += [p.relative_to(PROJECT).as_posix() for p in (PROJECT / "scripts").glob("audit_v07_m1*.py")]
    record = {"baseline": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
              "branch": "v07-scene", "python_environment": "llm", "python_version": sys.version,
              "qd_registration": str(qd_registration), "descriptor_attempt": str(source),
              "descriptor_sha256": sha(source / "private_skeleton_descriptors.json"),
              "source_registration_sha256": sha(source / "registration.json"), "source_assets": source_hashes,
              "geometry_config_sha256": sha(GEOMETRY_CONFIG), "selected": selected,
              "q2_wall_limit_s": 900, "q3_wall_limit_s": 1800, "max_workers": 8,
              "q2_gate": "all four fixed skeletons have eligible whole-route-checked plans",
              "frozen_sha256": {p: sha(PROJECT / p) for p in sorted(set(frozen))},
              "diagnostics_only": ["multi_max_pairwise_ingress_heading_deg", "observed_minimum_separation_m",
                                   "planning_wall_s", "attempted_proposals"],
              "additional_branches": "synthetic circle/polygon, blocked/empty domains, segment counterexamples; no extra flight batch"}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    save_json(EVIDENCE / "m3_inputs.json", record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    if args.register:
        result = register_inputs()
        print(json.dumps({"registered": result["selected"], "simulation_count": 0}, ensure_ascii=False))
    else:
        parser.error("select --register")


if __name__ == "__main__":
    main()
