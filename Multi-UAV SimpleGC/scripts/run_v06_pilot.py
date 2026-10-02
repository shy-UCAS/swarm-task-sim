"""Ten frozen V06 scenes, one attempt each; preserve ordinary failed episodes."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_mission_list import _save_atomic, run_mission_list
from scripts.verify_ac4_v2 import write_new
from swarm_sim.generation import canonical_hash, file_hash, verify_generation
from swarm_sim.generation_v2 import normalize_profile
from swarm_sim.tasks import validate_task_binding

VERSION = "v06_bounded_pilot_v1"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def assert_hashes(hashes):
    changed = [p for p, sha in hashes.items() if not Path(p).is_file() or file_hash(p) != sha]
    if changed:
        raise ValueError("frozen V06 inputs changed: " + str(changed))


def continuation(control, attempt_count):
    if control.get("version") != VERSION or control.get("budget") != 10:
        raise ValueError("invalid V06 budget/version")
    if control.get("stopped_reason"):
        raise ValueError("V06 stopped: " + control["stopped_reason"])
    if control.get("active_attempt") is not None:
        raise ValueError("unfinished reserved attempt; no automatic retry")
    if attempt_count != len(control["records"]) or attempt_count >= 10:
        raise ValueError("attempt ledger mismatch or ten-attempt budget exhausted")
    if any(r["qualified"] is not True for r in control["records"]) and sum(
            r["qualified"] is not True for r in control["records"]) > 2:
        raise ValueError("8/10 acceptance is no longer attainable")


def assess(metadata, quality, attempt):
    """Quality eligibility is independent of mission success/benchmark status."""
    hard = []
    if attempt.get("status") in ("interrupted", "runner_exception", "running"):
        hard.append("interrupted/incomplete runner")
    if metadata.get("run_provenance", {}).get("status") != "verified_before_takeoff":
        hard.append("parameter/firmware provenance gate failed")
    if metadata.get("run_provenance", {}).get("parameter_comparison_version") != "wp_s_parameter_comparison_v2":
        hard.append("parameter comparison version mismatch")
    agents = [v["id"] for v in metadata["scenario"]["vehicles"]]
    cleanup = metadata.get("cleanup", {})
    if set(cleanup) != set(agents) or any(cleanup[a] is None for a in agents):
        hard.append("owned process cleanup incomplete")
    if quality.get("analysis_error") or not attempt.get("selected_analysis"):
        hard.append("analysis evidence incomplete")
    evidence = metadata.get("run_provenance", {}).get("parameter_evidence", {}).get("per_agent", {})
    if set(evidence) != set(agents) or any(not evidence[a].get("complete") or
            evidence[a].get("received_count") != evidence[a].get("parameter_count") or
            evidence[a].get("missing_indices") for a in agents):
        hard.append("partial parameter readback")
    return dict(qualified=metadata.get("status") == "completed" and
                quality.get("episode_quality_eligible") is True, hard_failures=hard,
                episode_quality_eligible=quality.get("episode_quality_eligible"),
                run_status=metadata.get("status"), mission_success=quality.get("mission_success"),
                benchmark_eligible=quality.get("benchmark_eligible"), cleanup=cleanup)


def prepare(root, profile, mission_list):
    listing, manifest = verify_generation(mission_list)
    normalized = normalize_profile(profile)
    prior = read(ROOT / "generation_profiles/recon_pilot_v03.json")
    if normalized["scene_sampler"]["name"] != "strip_aligned_v1" or any(
            normalized["scene_sampler"]["params"][k] != prior[k] for k in normalized["scene_sampler"]["params"]):
        raise ValueError("v0.3 physical sampling distribution changed")
    if any(normalized["shared_mission_params"][k] != prior[k] for k in normalized["shared_mission_params"]):
        raise ValueError("v0.3 shared sampling distribution changed")
    if len(normalized["missions"]) != 1 or normalized["missions"][0]["variant_speed_factors"] != [1.0]:
        raise ValueError("V06 requires exactly one reconnaissance variant")
    if normalized["base_scene_count"] != 10 or len(listing["missions"]) != 10 or manifest["counts"]["accepted_bases"] != 10:
        raise ValueError("V06 requires ten accepted physical scenes")
    if manifest["profile_sha256"] != canonical_hash(normalized):
        raise ValueError("generation profile binding mismatch")
    for entry in listing["missions"]:
        if entry["status"] != "planned" or entry["intent"] != "reconnaissance" or entry["control_mode"] != "semantic_phase_route_v1":
            raise ValueError("unexpected planned intent/control mode")
        scene = read(mission_list.parent / entry["scene"])
        if scene["schema_version"] != 2:
            raise ValueError("V06 requires schema 2")
        validate_task_binding(scene)
    v1_path = ROOT / "tmp_v04/ac4_v2_20261002/final_acceptance.json"
    v1 = read(v1_path)
    if not v1["matrix_complete"] or not all(v is True for v in v1["final_route_criteria"].values()):
        raise ValueError("V1 acceptance not complete")
    frozen = [profile, v1_path, ROOT / "quality_policies/default_v022.json",
              ROOT / "ArducopterSITL/arducopter.exe", ROOT / "ArducopterSITL/copter.parm",
              ROOT / "docs/v04_spike_go_confirmation.json", ROOT / "scripts/run_mission_list.py",
              Path(__file__)] + list((ROOT / "swarm_sim").glob("*.py")) + list(mission_list.parent.rglob("*.json"))
    root.mkdir(parents=True, exist_ok=False)
    control = dict(version=VERSION, budget=10, records=[], active_attempt=None,
        authorization="2026-10-02 user: V1 accepted; V06 ten scenes, at most ten SITL attempts; >=8 completed and quality eligible; no stage 2",
        stop_policy="integrity/provenance/cleanup/runner interruption: stop; third ordinary nonqualified attempt: stop; no retries",
        v1_criteria_applicability="AC1-AC6 are V02-V04 criteria, not additional V06 gates",
        mission_list=str(mission_list.resolve()), profile=str(profile.resolve()),
        profile_source_sha256=file_hash(profile), profile_sha256=canonical_hash(normalized),
        prior_profile_sha256=canonical_hash(normalize_profile(ROOT / "generation_profiles/recon_pilot_v04.json")),
        profile_distribution_equal_v03=True, frozen_sha256={str(p.resolve()): file_hash(p) for p in frozen},
        prepared_utc=datetime.now(timezone.utc).isoformat())
    write_new(root / "control.json", control)
    print(json.dumps({k: control[k] for k in ("version", "budget", "profile_source_sha256", "profile_sha256", "prior_profile_sha256")}))


def run_one(root):
    control_path = root / "control.json"
    control = read(control_path)
    ledger_path = root / "execution/attempt_ledger.json"
    previous = read(ledger_path) if ledger_path.exists() else None
    count = sum(len(m["attempts"]) for m in previous["missions"]) if previous else 0
    continuation(control, count)
    assert_hashes(control["frozen_sha256"])
    for row in control["records"]:
        assert_hashes(row["evidence_sha256"])
    control["active_attempt"] = dict(index=count, reserved_utc=datetime.now(timezone.utc).isoformat())
    _save_atomic(control_path, control)
    try:
        ledger = run_mission_list(control["mission_list"], max_runs=1, resume=previous is not None,
            output_root=root / "execution", quality_policy=read(ROOT / "quality_policies/default_v022.json"),
            max_environment_retries=0, retryable_errors=())
        attempts = [(m, a) for m in ledger["missions"] for a in m["attempts"]]
        if len(attempts) != count + 1 or any(len(m["attempts"]) > 1 for m in ledger["missions"]):
            raise ValueError("unexpected attempt count/retry")
        mission, attempt = attempts[-1]
        directory = Path(attempt["run_directory"])
        metadata, quality = read(directory / "metadata.json"), read(directory / "quality.json")
        result = assess(metadata, quality, attempt)
        row = dict(index=count, mission_id=mission["mission_id"], run_id=metadata["run_id"],
            run_directory=str(directory), **result,
            evidence_sha256={str((directory / p).resolve()): file_hash(directory / p)
                             for p in ("metadata.json", "quality.json", "analysis_latest.json", "firmware_parameters.json")})
        write_new(root / "checks" / f"{count:02d}.json", row)
        control["records"].append(row)
        control["active_attempt"] = None
        if result["hard_failures"]:
            control["stopped_reason"] = "; ".join(result["hard_failures"])
        elif sum(not r["qualified"] for r in control["records"]) > 2:
            control["stopped_reason"] = "8/10 acceptance is no longer attainable"
        control["attempts_started"] = len(attempts)
        control["qualified_count"] = sum(r["qualified"] for r in control["records"])
        control["runs_complete"] = len(attempts) == 10
    except BaseException as exc:
        control["stopped_reason"] = f"attempt stopped: {type(exc).__name__}: {exc}"
        _save_atomic(control_path, control)
        raise
    _save_atomic(control_path, control)
    print(json.dumps(dict(attempts=control["attempts_started"], qualified=control["qualified_count"],
        latest=row, stopped_reason=control.get("stopped_reason")), ensure_ascii=False))
    return int(bool(control.get("stopped_reason")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "next"))
    parser.add_argument("--root", type=Path, default=ROOT / "verification/v04_v06_20261002")
    parser.add_argument("--profile", type=Path, default=ROOT / "generation_profiles/recon_pilot_v04_v06.json")
    parser.add_argument("--mission-list", type=Path, default=ROOT / "generated/recon_pilot_v04_v06_20261002/mission_list.json")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.root.resolve(), args.profile.resolve(), args.mission_list.resolve())
        return 0
    return run_one(args.root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
