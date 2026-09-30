"""Explicit, bounded five-run v0.3 integration matrix (starts local SITL)."""

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_sim.analysis import analyze_run, digest
from swarm_sim.dataset import build_dataset
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.episode_loader import load_episode
from swarm_sim.quality import policy_hash, resolve_policy
from swarm_sim.recording import write_json
from swarm_sim.runner import run_scene
from swarm_sim.tasks import compile_task
from scripts.run_mission_list import _verify_result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true", help="verify and retain completed matrix cases before continuing")
    parser.add_argument("--reanalyze-existing", action="store_true", help="explicitly append current analysis for completed cases")
    parser.add_argument("--dataset-output", type=Path, help="new dataset destination when preserving an earlier frozen export")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not args.resume:
        output.mkdir(parents=True, exist_ok=False)
    policy = resolve_policy(json.loads((ROOT / "quality_policies/default_v022.json").read_text(encoding="utf-8")))
    base = json.loads((ROOT / "missions/recon_shared_3uav.json").read_text(encoding="utf-8"))
    controlled = copy.deepcopy(base)
    controlled["task_id"] += "_ready_timeout"
    controlled["execution"]["ready_timeout_s"] = 10.0
    cases = [("three_primary", base), ("three_repeat", base)]
    for name, filename in (("two_north", "recon_smoke_2uav_north.json"), ("six_small", "recon_smoke_6uav.json")):
        cases.append((name, json.loads((ROOT / "missions" / filename).read_text(encoding="utf-8"))))
    cases.append(("controlled_ready_timeout", controlled))
    compiled = {name: compile_task(spec) for name, spec in cases}
    report = (json.loads((output / "verification.json").read_text(encoding="utf-8")) if args.resume
              else dict(scope="five local SITL attempts; no automatic retry; failures retained", cases=[]))
    run_paths = []
    for name, spec in cases:
        scene = compiled[name]
        previous = next((row for row in report["cases"] if row["case"] == name), None)
        if previous:
            if args.reanalyze_existing:
                analysis, aq, labels = analyze_run(previous["run_directory"], policy)
                previous.setdefault("previous_analysis_results", []).append({key: previous[key] for key in
                    ("analysis_directory", "passed", "mission_success", "mission_success_observation", "semantic_consistency", "benchmark_eligible")})
                previous.update(analysis_directory=str(analysis), mission_success=labels["mission_success"],
                    mission_success_observation=labels["mission_success_observation"], semantic_consistency=labels["semantic_consistency"],
                    mission_metrics=labels["mission_metrics"], execution_constraints_pass=aq["execution_constraints_pass"],
                    benchmark_eligible=aq["benchmark_eligible"], strict_benchmark_eligible=aq["strict_benchmark_eligible"],
                    clock_quality=aq["clock_quality"]["overall"],
                    passed=(previous["run_status"] == "failed" and labels["mission_success"] is not True and not aq["benchmark_eligible"])
                           if previous["expected_failure"] else aq["benchmark_eligible"])
                previous["reanalyzed_cli_equivalent_exit_code"] = 0 if aq["benchmark_eligible"] else 1
                write_json(output / "verification.json", report)
            _verify_result(previous["run_directory"], scene, policy_hash(policy))
            run_paths.append(Path(previous["run_directory"]))
            continue
        write_json(output / (name + "_task.json"), spec)
        write_json(output / (name + "_scene.json"), scene)
        directory, metadata, quality = run_scene(scene, output / "runs", ROOT / "ArducopterSITL/arducopter.exe",
            ROOT / "ArducopterSITL/copter.parm", quality_policy=policy)
        run_paths.append(directory)
        pointer = json.loads((directory / "analysis_latest.json").read_text(encoding="utf-8"))
        analysis = directory / pointer["directory"]
        labels = json.loads((analysis / "labels.json").read_text(encoding="utf-8"))
        aq = json.loads((analysis / "quality.json").read_text(encoding="utf-8"))
        expected_failure = name == "controlled_ready_timeout"
        passed = (metadata["status"] == "failed" and labels["mission_success"] is not True
                  and not quality["usable"]) if expected_failure else quality["usable"]
        row = dict(case=name, expected_failure=expected_failure, passed=bool(passed),
            task_file_sha256=digest(output / (name + "_task.json")), scenario_sha256=metadata["scenario_sha256"],
            run_id=metadata["run_id"], run_directory=str(directory), analysis_directory=str(analysis),
            elapsed_s=metadata["elapsed_s"], run_status=metadata["status"], error=metadata.get("error"),
            cli_equivalent_exit_code=0 if quality["usable"] else 1, cleanup=metadata["cleanup"],
            simulator_version=metadata["version"], source_sha256=metadata["source_sha256"],
            firmware_sha256=metadata.get("sitl", {}).get("sha256"),
            mission_success=labels["mission_success"], mission_success_observation=labels["mission_success_observation"],
            semantic_consistency=labels["semantic_consistency"], mission_metrics=labels["mission_metrics"],
            execution_constraints_pass=aq["execution_constraints_pass"], clock_quality=aq["clock_quality"]["overall"],
            benchmark_eligible=aq["benchmark_eligible"], strict_benchmark_eligible=aq["strict_benchmark_eligible"])
        report["cases"].append(row)
        write_json(output / "verification.json", report)
        print(json.dumps(dict(case=name, passed=passed, run_id=metadata["run_id"], usable=quality["usable"])), flush=True)
    dataset_output = args.dataset_output or output / "dataset"
    dataset = build_dataset(run_paths, dataset_output)
    report["dataset_directory"] = str(dataset_output.resolve())
    report["dataset_counts"] = dataset["counts"]
    report["loader"] = []
    for episode in dataset["episodes"]:
        loaded = load_episode(dataset_output / episode["directory"])
        report["loader"].append(dict(run_id=episode["run_id"], shape=[len(loaded["x"]), len(loaded["agent_ids"]), 6],
            mask_shape=[len(loaded["mask"]), len(loaded["agent_ids"])],
            valid=sum(sum(frame) for frame in loaded["mask"])))
    audit = audit_dataset(dataset_output)
    audit_path = output / (dataset_output.name + "_audit.json")
    if audit_path.exists():
        raise ValueError("audit export already exists; choose a new dataset destination")
    write_json(audit_path, audit)
    report["audit_path"] = str(audit_path.resolve())
    report["audit_issues"] = audit["issues"]
    report["all_cases_passed"] = all(row["passed"] for row in report["cases"])
    report["all_processes_reaped"] = all(all(code is not None for code in row["cleanup"].values()) for row in report["cases"])
    write_json(output / "verification.json", report)
    return int(not report["all_cases_passed"] or not report["all_processes_reaped"] or bool(audit["issues"]))


if __name__ == "__main__":
    raise SystemExit(main())
