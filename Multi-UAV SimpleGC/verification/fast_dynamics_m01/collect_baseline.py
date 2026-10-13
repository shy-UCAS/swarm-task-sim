"""Read-only historical checks and M0 source index; never start a flight.

Run from the project with its configured Conda environment. This evidence helper
writes only its own directory and a newly-created external DR130 temp directory.
"""
from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False) + "\n", encoding="utf-8")


def reject_flight(event, args):
    if event in ("subprocess.Popen", "os.system", "os.spawn", "os.exec"):
        raise RuntimeError("M0 baseline checks forbid subprocesses and SITL")


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT,
        help="new evidence directory; previous result files cannot be overwritten")
    args = parser.parse_args()
    OUTPUT = args.output.resolve()
    products = ("baseline_dr130.json", "baseline_v05_loader.json", "m0_source_index.json",
        "m0_evaluation_split.json", "baseline_checks.json")
    if any((OUTPUT / name).exists() for name in products):
        parser.error("existing evidence would be overwritten; use --output with a new directory")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    import numpy
    from scripts.diagnostics.v06_offline_checks import golden
    from swarm_sim.episode_loader import load_episode
    from swarm_sim.families import scene_content_hash

    sys.addaudithook(reject_flight)
    source_files = [PROJECT / "../.github/workflows/unit-tests.yml",
        PROJECT / "tests/fixtures/intent_registry_DR130_golden.json",
        PROJECT / "examples/v05_episodes/sample_index.json"]
    source_files += sorted((PROJECT / "swarm_sim").glob("*.py"))
    source_hashes = {str(p.resolve()): digest(p) for p in source_files}
    temporary = Path(tempfile.mkdtemp(prefix="fast_dynamics_m01_dr130_"))
    golden_result = golden(temporary)
    save("baseline_dr130.json", golden_result)

    samples = read(PROJECT / "examples/v05_episodes/sample_index.json")
    loaded_rows = []
    for sample in samples["samples"]:
        episode_path = PROJECT.parent / sample["path"]
        before = {name: digest(episode_path / name) for name in sample["files_sha256"]}
        loaded = load_episode(episode_path, verify_hashes=True)
        after = {name: digest(episode_path / name) for name in sample["files_sha256"]}
        assert before == after == sample["files_sha256"]
        assert loaded["metadata"]["episode_quality_eligible"] == sample["episode_quality_eligible"]
        assert loaded["metadata"]["family_id"] == sample["family_id"]
        normalized = dict(loaded)
        normalized["metadata"] = {k: v for k, v in loaded["metadata"].items() if k != "source_directory"}
        canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode("utf-8")
        loaded_rows.append(dict(plan_id=sample["plan_id"], run_id=sample["run_id"],
            frames=len(loaded["t_s"]), agents=len(loaded["agent_ids"]),
            episode_quality_eligible=sample["episode_quality_eligible"],
            unchanged=True, family_id=sample["family_id"], original_split=sample["original_split"],
            loaded_canonical_sha256=hashlib.sha256(canonical).hexdigest()))
    save("baseline_v05_loader.json", dict(passed=len(loaded_rows), expected=4,
        pass_all=len(loaded_rows) == 4, canonical_exclusions=["metadata.source_directory"], rows=loaded_rows))

    archive = PROJECT.parents[1] / "SwarmData/parallel_batch"
    rows, batch_rows = [], []
    for batch_id in ("v061_T1_k2_s1_seed2026100812", "v061_T4_k4_s1_seed2026100812"):
        batch = archive / batch_id
        listing_path = batch / "bundle/mission_list.json"
        manifest_path = batch / "dataset/dataset_manifest.json"
        listing, manifest = read(listing_path), read(manifest_path)
        lookup = {entry["mission_id"]: entry for entry in listing["missions"]}
        batch_rows.append(dict(batch_id=batch_id, source_root=str(batch),
            mission_list_sha256=digest(listing_path), dataset_manifest_sha256=digest(manifest_path),
            purpose=manifest["purpose"], training_data=manifest["training_data"],
            counts=manifest["counts"]))
        for episode in manifest["episodes"]:
            entry = lookup[episode["scenario_id"]]
            task_path = batch / "bundle" / entry["task"]
            scene_path = batch / "bundle" / entry["scene"]
            task = read(task_path)
            content_sha = scene_content_hash(task)
            assert digest(task_path) == entry["task_sha256"]
            assert digest(scene_path) == entry["scene_sha256"]
            assert content_sha == entry["scene_content_sha256"]
            assert episode["family_id"] == task["family_id"] == "scene_" + content_sha[:20]
            ep = batch / "dataset" / episode["directory"]
            available = {name: (ep / name).is_file() for name in
                ("truth.csv", "observations.csv", "phase_windows.json", "execution_metrics.json",
                 "semantic_validation.json", "quality.json", "time_contract.json")}
            common_time_available = episode.get("common_time_axis", {}).get("available") is True
            rows.append(dict(source_batch=batch_id, source_run=episode["run_id"],
                source_episode=str(ep), task_path=str(task_path), scene_path=str(scene_path),
                task_id=entry["mission_id"], intent=entry["intent"], flight_pattern=entry["flight_pattern"],
                task_sha256=entry["task_sha256"], scene_sha256=entry["scene_sha256"],
                scene_content_sha256=content_sha, family_id=episode["family_id"],
                repeated_measurement_group=entry["task_sha256"],
                protocol=episode["protocol_version"], time_base=episode["time_base"],
                episode_quality_eligible=episode["episode_quality_eligible"],
                mission_success=episode["mission_success"], semantic_consistency=episode["semantic_consistency"],
                agents=len(episode["agent_ids"]), original_export_split=episode["split"],
                development_group="development_reference", final_test_eligible=False,
                prior_use="v0.6.1 time/scale diagnostics; already reviewed before fast-engine development",
                artifact_available=available,
                common_time_available=common_time_available,
                calibration_candidate=episode["episode_quality_eligible"] and common_time_available,
                metric_readiness="candidate groups only; inspect each channel's valid interval before computing",
                computable_metric_groups=["trajectory_shape", "common_time_duration", "phase_timing",
                    "minimum_separation", "position_velocity_residual", "semantic_conditions"] if common_time_available else [],
                derivative_limitation="SIM truth is position-only; derivatives require registered estimator and error analysis"))
    task_groups = Counter(row["repeated_measurement_group"] for row in rows)
    family_groups = Counter(row["family_id"] for row in rows)
    assert len(rows) == 84 and len(task_groups) == 42 and len(family_groups) == 14
    assert set(task_groups.values()) == {2} and set(family_groups.values()) == {6}
    assert {row["protocol"] for row in rows} == {"v0.6.1"}
    assert {row["time_base"] for row in rows} == {"sim_source"}
    save("m0_source_index.json", dict(schema_version=1,
        scope="Read-only T1/T4 first development sources; r1/r2 inventory not performed here",
        source_batches=batch_rows, runs=84, unique_tasks=42, unique_families=14,
        aircraft_executions=sum(row["agents"] for row in rows),
        all_development_reference=True, rows=rows))
    save("m0_evaluation_split.json", dict(schema_version=1, status="M0 development reservation; M3 split not frozen",
        unit="canonical scene_content_v1 family; include all intents/backends/variants/repeated runs",
        development_reference=sorted(family_groups), calibration=[], development_validation=[], final_test=[],
        reason="All 14 T1/T4 families are previously reviewed development evidence, never blind test.",
        aggregation="First aggregate repeated runs within task, then equal task or family weighting; family bootstrap only.",
        future_source_admission="Union r1/r2 and other historical/algorithm-use identities before any split; exact family/scene-hash disjointness is required.",
        near_duplicate_rule="Before new family admission, canonicalize region/vehicle geometry under consistent agent and region renaming; flag matching platform/count and region dimensions plus vehicle relative offsets within 1e-6 m as same leakage group even if world translation or scene IDs differ. Broader similarity thresholds must be preregistered before new-source selection.",
        final_test_status="pending unseen family acquisition; no SITL run authorized"))
    source_after = {str(p.resolve()): digest(p) for p in source_files}
    changed = [name for name in source_hashes if source_hashes[name] != source_after[name]]
    save("baseline_checks.json", dict(environment="llm", python=sys.version, numpy=numpy.__version__,
        executable=sys.executable, checks=dict(dr130=dict(checked=golden_result["checked"],
            passed=golden_result["passed"], pass_all=golden_result["pass_all"]),
            v05_loader=dict(checked=4, passed=len(loaded_rows)),
            source_index=dict(runs=84, tasks=42, families=14)),
        dr130_new_output=str(temporary), source_files_sha256=source_hashes,
        source_changed_during_check=changed, no_subprocess_audit_hook=True))
    print(json.dumps(dict(dr130=golden_result["pass_all"], v05_loader=len(loaded_rows),
        source_runs=84, source_tasks=42, source_families=14, source_changed=changed), ensure_ascii=False))
    return int(not golden_result["pass_all"])


if __name__ == "__main__":
    raise SystemExit(main())
