"""Assemble the two frozen v0.3 pilot contexts; never launch or reanalyze runs."""

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_sim.analysis import digest
from swarm_sim.dataset import build_dataset
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.episode_loader import load_episode
from swarm_sim.protocol import validate_artifact_protocol
from swarm_sim.recording import write_json


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    ledger_paths = [ROOT / "verification" / name / "attempt_ledger.json" for name in
        ("v03_pilot_20260930", "v03_pilot_remaining_20260930")]
    ledgers = [read(path) for path in ledger_paths]
    missions, rows, run_paths = [], [], []
    for context, ledger in enumerate(ledgers):
        for item in ledger["missions"]:
            if not item["attempts"]:
                continue
            copied = copy.deepcopy(item)
            copied["audit_source_context"] = context
            missions.append(copied)
            for attempt in copied["attempts"]:
                if attempt["status"] in ("running", "interrupted"):
                    raise ValueError("pilot attempt is not terminal")
                run = Path(attempt["run_directory"])
                metadata = read(run / "metadata.json")
                pointer = read(run / "analysis_latest.json")
                analysis = run / pointer["directory"]
                manifest = read(analysis / "manifest.json")
                validate_artifact_protocol(manifest, analysis)
                labels, quality = read(analysis / "labels.json"), read(analysis / "quality.json")
                task = metadata["scenario"]["task_spec"]
                attempt["dataset_selected_analysis"] = pointer
                run_paths.append(run)
                rows.append(dict(mission_id=item["mission_id"], family_id=item["family_id"], context=context,
                    attempt_id=attempt["attempt_id"], run_id=metadata["run_id"], run_directory=str(run),
                    selected_analysis=pointer, vehicle_count=len(task["scenario"]["vehicles"]),
                    partition_axis=task["planner"]["partition_axis"], return_required=task["mission"]["return_required"],
                    elapsed_s=metadata["elapsed_s"], run_status=metadata["status"], cleanup=metadata["cleanup"],
                    mission_success=labels["mission_success"], mission_success_observation=labels["mission_success_observation"],
                    semantic_consistency=labels["semantic_consistency"],
                    truth_coverage=labels["mission_metrics"]["truth"]["coverage"]["global_coverage_ratio"],
                    observation_coverage=labels["mission_metrics"]["observation"]["coverage"]["global_coverage_ratio"],
                    benchmark_eligible=quality["benchmark_eligible"], strict_benchmark_eligible=quality["strict_benchmark_eligible"],
                    clock_quality=quality["clock_quality"]["overall"], manifest_sha256=digest(analysis / "manifest.json"),
                    firmware_sha256=metadata.get("sitl", {}).get("sha256"), scenario_sha256=metadata["scenario_sha256"]))
    if {row["mission_id"] for row in rows} != {f"recon_{i:04}_v00" for i in range(10)}:
        raise ValueError("all ten preselected independent pilot missions must have terminal evidence")
    output.mkdir(parents=True, exist_ok=False)
    combined = dict(audit_only=True, not_a_resumable_execution_ledger=True,
        source_ledgers=[dict(path=str(path), sha256=digest(path), execution_context=ledger["execution_context"])
                        for path, ledger in zip(ledger_paths, ledgers)], missions=missions,
        analysis_note="Original attempts are preserved; dataset_selected_analysis names the explicit current analysis. No original ledger was rewritten.")
    write_json(output / "attempts_for_audit.json", combined)
    dataset = build_dataset(run_paths, output / "dataset")
    audit = audit_dataset(output / "dataset", ROOT / "generated/recon_pilot_v03_20260930/generation_manifest.json",
                          output / "attempts_for_audit.json")
    write_json(output / "dataset_audit.json", audit)
    shapes = []
    for entry in dataset["episodes"]:
        episode = load_episode(output / "dataset" / entry["directory"])
        shapes.append(dict(run_id=entry["run_id"], x_shape=[len(episode["x"]), len(episode["agent_ids"]), 6],
                           mask_shape=[len(episode["mask"]), len(episode["agent_ids"])],
                           valid=sum(sum(frame) for frame in episode["mask"])))
    before = read(ROOT / "verification/v03_pilot_resume_before.json")
    after_by_id = {item["mission_id"]: item for item in ledgers[1]["missions"]}
    resumed = {item["mission_id"]: item["attempts"] == after_by_id[item["mission_id"]]["attempts"]
               for item in before["missions"] if item["status"] == "succeeded"}
    summary = dict(schema_version=1, episodes=rows, dataset_counts=dataset["counts"], audit_issues=audit["issues"],
        loader_shapes=shapes, unique_missions=len({row["mission_id"] for row in rows}),
        total_attempts=len(rows), execution_contexts=len(ledgers),
        resume_completed_attempts_unchanged=resumed,
        all_processes_reaped=all(all(value is not None for value in row["cleanup"].values()) for row in rows),
        first_three_reanalysis=read(ROOT / "verification/v03_pilot_first3_reanalysis.json"),
        data_note="Ten independent generated inputs; three earlier flights explicitly reanalyzed after version alignment, seven flights under the final frozen runtime. All outcomes retained.")
    write_json(output / "verification.json", summary)
    print(json.dumps(dict(output=str(output), counts=dataset["counts"], issues=audit["issues"], resume=resumed), indent=2))
    return int(bool(audit["issues"]) or not all(resumed.values()) or not summary["all_processes_reaped"])


if __name__ == "__main__":
    raise SystemExit(main())
