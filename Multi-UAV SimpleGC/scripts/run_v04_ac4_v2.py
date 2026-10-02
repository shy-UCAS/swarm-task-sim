"""Four authorized remaining V1 attempts, with immutable historical ledgers."""
import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_v04_v1 import check_offline_gate, historical_evidence, read
from scripts.verify_ac4_v2 import VERSION, verify_records_v2, write_new
from swarm_sim.analysis import digest
from swarm_sim.recording import write_json
from swarm_sim.tasks import validate_task_binding

KEYS = ["V02_r2", "V03_r1", "V04_r1", "V05_r1"]


def assert_hashes(hashes):
    changed = [name for name, sha in hashes.items() if not Path(name).is_file() or digest(Path(name)) != sha]
    if changed:
        raise ValueError("bound evidence changed: " + ", ".join(changed))


def failures(review, rows=None):
    problems = []
    if not review["source_files_unchanged"] or review.get("issues"):
        problems.append("source integrity failed")
    for row in rows if rows is not None else review["records"]:
        if not row["cleanup"]["complete"] or not row["evidence_integrity_pass"] or row["issues"]:
            problems.append(row["run_id"] + ": cleanup/integrity failed")
        if row["validation_id"] == "V05":
            if not row["expected_failure"] or row["expected_failure"].get("as_expected") is not True:
                problems.append("V05 did not match the injected phase timeout")
        else:
            if row["run_status"] != "completed" or row["exit_code"] != 0:
                problems.append(row["run_id"] + ": execution/quality failed")
            if row["acceptance_criteria_applicable"]:
                problems.extend(row["run_id"] + ": " + k + "=" + str(v)
                                for k, v in row["criteria"].items() if k != "AC1" and v is not True)
    if review["ac1_pooled"]["matrix_complete"] and review["observed_route_criteria"]["AC1"] is not True:
        problems.append("pooled AC1=" + str(review["observed_route_criteria"]["AC1"]))
    return problems


def prepare(root, prior_path, review_path, gate_path, diagnostics_path):
    """Adopt successful evidence, never erase the v1 stopped_reason."""
    prior_path, review_path = prior_path.resolve(), review_path.resolve()
    prior, assessment = read(prior_path), read(review_path)
    if (prior.get("attempts_started") != 2 or prior.get("new_sitl_runs") != 2 or prior.get("budget") != 7
            or prior.get("stopped_reason") != "V02_r1: AC4=False"
            or [r.get("key") for r in prior.get("records", [])] != ["V01_r1", "V02_r1"]
            or any(r.get("state") != "finished" for r in prior["records"])):
        raise ValueError("authorization requires the exact two-attempt AC4-stopped predecessor")
    history = historical_evidence(prior["historical_evidence"]["path"], prior["historical_evidence"]["sha256"])
    if (assessment.get("acceptance_policy_version") != VERSION
            or Path(assessment["input_records_path"]).resolve() != prior_path
            or assessment["input_sha256"].get(str(prior_path)) != digest(prior_path)):
        raise ValueError("AC4 v2 assessment does not bind the preserved predecessor")
    if failures(assessment):
        raise ValueError("offline v2 re-evaluation did not pass: " + str(failures(assessment)))
    spikes = assessment.get("wp_s_offline_reviews", [])
    if (len(spikes) != 2 or any(not row.get("source_files_unchanged") for row in spikes)
            or {row.get("run_id") for row in spikes} != {"20261001T153235Z_5eddb7ae", "20261001T153806Z_42150c31"}):
        raise ValueError("both read-only WP-S re-evaluations must be present and immutable")
    diagnostics = read(diagnostics_path)
    if (not diagnostics.get("inputs_unchanged") or len(diagnostics.get("fallback_windows", [])) != 11
            or diagnostics.get("run_id") != prior["records"][1]["run_id"]
            or diagnostics.get("fallback_count") != {"truth": 7, "observation": 4}
            or not diagnostics.get("arrival_definition_unchanged")):
        raise ValueError("arrival/segment offline diagnostic has incomplete integrity evidence")
    check_offline_gate(gate_path)
    assert_hashes(assessment["input_sha256"])
    immutable_inputs = dict(assessment["input_sha256"])
    for row in spikes:
        assert_hashes(row["input_sha256"])
        immutable_inputs.update(row["input_sha256"])
    diagnostic_inputs = {str((ROOT / name).resolve()): sha for name, sha in diagnostics["source_sha256"].items()}
    assert_hashes(diagnostic_inputs)
    immutable_inputs.update(diagnostic_inputs)
    root.mkdir(parents=True, exist_ok=False)
    plans = root / "plans"
    plans.mkdir()
    jobs = []
    for old in prior["jobs"][2:]:
        job = copy.deepcopy(old)
        for kind in ("task", "scene"):
            source = Path(job[kind])
            if digest(source) != job[kind + "_sha256"]:
                raise ValueError("frozen planned input changed")
            destination = plans / source.name
            destination.write_bytes(source.read_bytes())
            job[kind] = str(destination)
        validate_task_binding(read(Path(job["scene"])))
        jobs.append(job)
    if [job["key"] for job in jobs] != KEYS:
        raise ValueError("remaining budget is limited to V02 repeat 2, V03, V04, V05")
    adopted = [dict(copy.deepcopy(r), adopted_from_immutable_ledger=str(prior_path)) for r in prior["records"]]
    supporting = {str(prior_path): digest(prior_path), str(Path(history["path"])): history["sha256"],
                  str(review_path): digest(review_path), str(diagnostics_path.resolve()): digest(diagnostics_path),
                  str(gate_path.resolve()): digest(gate_path)}
    script_hashes = {str(p.resolve()): digest(p) for folder in ("scripts", "swarm_sim")
                     for p in (ROOT / folder).glob("*.py")}
    ledger = dict(schema_version=3, acceptance_policy_version=VERSION, budget=7, prior_attempts=3,
        prior_sitl_runs=3, attempts_started=0, new_sitl_runs=0, jobs=jobs, records=adopted,
        adopted_validation_keys=["V01_r1", "V02_r1"], historical_failed_run_ids=history["run_ids"],
        historical_stopped_reason=prior["stopped_reason"], immutable_supporting_sha256=supporting,
        immutable_input_sha256=immutable_inputs,
        acceptance_source_sha256=script_hashes, offline_gate=str(gate_path.resolve()),
        authorization="2026-10-02 user: AC4 v2 offline review; retain original v1 stop; adopt V02 r1 only if pass; four remaining attempts, stop on any failure; pause after V05; no V06",
        prepared_utc=datetime.now(timezone.utc).isoformat())
    write_new(root / "records.json", ledger)
    print(json.dumps(dict(prepared=str(root), acceptance_policy_version=VERSION, prior_attempts=3,
                          new_attempts=0, budget=7, remaining_jobs=KEYS)))


def run_one(root, key):
    path = root / "records.json"
    ledger = read(path)
    if ledger.get("stopped_reason"):
        raise ValueError("validation stopped: " + ledger["stopped_reason"])
    if (ledger.get("acceptance_policy_version") != VERSION or ledger.get("budget") != 7
            or ledger.get("prior_attempts") != 3 or ledger.get("prior_sitl_runs") != 3
            or [job["key"] for job in ledger["jobs"]] != KEYS):
        raise ValueError("authorization/budget policy changed")
    assert_hashes(ledger["immutable_supporting_sha256"])
    assert_hashes(ledger["immutable_input_sha256"])
    assert_hashes(ledger["acceptance_source_sha256"])
    gate = check_offline_gate(ledger["offline_gate"])
    index = ledger["attempts_started"]
    if index >= 4 or index + ledger["prior_attempts"] >= ledger["budget"]:
        raise ValueError("V1 seven-attempt budget exhausted; V06 not authorized")
    if key != KEYS[index] or len(ledger["records"]) != index + 2:
        raise ValueError("next authorized attempt is " + KEYS[index])
    if any(row["state"] != "finished" for row in ledger["records"]):
        raise ValueError("unfinished attempt; never retry silently")
    for previous in ledger["records"]:
        assert_hashes({str(Path(previous["run_directory"]) / (kind + ".json")): previous[kind + "_sha256"]
                       for kind in ("metadata", "quality")})
        if previous.get("acceptance_record"):
            attachment = previous["acceptance_record"]
            assert_hashes({attachment["path"]: attachment["sha256"]})
    review = verify_records_v2(path)
    problems = failures(review)
    if problems:
        ledger["stopped_reason"] = "; ".join(problems)
        write_json(path, ledger)
        raise ValueError("previous acceptance failed; no SITL: " + ledger["stopped_reason"])
    job = ledger["jobs"][index]
    for kind in ("task", "scene"):
        assert_hashes({job[kind]: job[kind + "_sha256"]})
    scene = read(Path(job["scene"]))
    validate_task_binding(scene)
    record = dict(job, state="started", acceptance_policy_version=VERSION,
                  started_utc=datetime.now(timezone.utc).isoformat(), offline_gate=gate)
    ledger["records"].append(record)
    ledger["attempts_started"] += 1
    write_json(path, ledger)
    from swarm_sim.runner import run_scene
    try:
        run, metadata, quality = run_scene(scene, root / "runs", ROOT / "ArducopterSITL/arducopter.exe", ROOT / "ArducopterSITL/copter.parm")
    except BaseException as exc:
        record.update(state="interrupted_without_final_result", error=f"{type(exc).__name__}: {exc}")
        ledger["stopped_reason"] = key + ": interrupted; budget consumed, no silent retry"
        write_json(path, ledger)
        raise
    code = 0 if quality.get("usable") else 1
    launched = bool(metadata.get("sitl", {}).get("instances"))
    ledger["new_sitl_runs"] += int(launched)
    record.update(state="finished", run_directory=str(run), run_id=metadata["run_id"], exit_code=code,
        run_status=metadata["status"], launched_sitl=launched, finished_utc=datetime.now(timezone.utc).isoformat(),
        metadata_sha256=digest(run / "metadata.json"), quality_sha256=digest(run / "quality.json"))
    write_json(path, ledger)
    try:
        review = verify_records_v2(path)
        problems = failures(review)
        report_path = root / "acceptance" / (key + ".json")
        write_new(report_path, review)
        record["acceptance_record"] = dict(path=str(report_path), sha256=digest(report_path), version=VERSION,
            criteria=review["records"][-1]["criteria"], passed=not problems)
    except BaseException as exc:
        ledger["stopped_reason"] = key + ": acceptance could not be completed: " + str(exc)
        write_json(path, ledger)
        raise
    if problems:
        ledger["stopped_reason"] = key + ": " + "; ".join(problems)
    if key == "V05_r1" and not problems:
        ledger["completed_authorized_v1"] = True
    write_json(path, ledger)
    print(json.dumps(dict(validation=key, run_id=metadata["run_id"], run_status=metadata["status"],
        run_exit_code=code, acceptance_exit_code=1 if problems else 0,
        cumulative_attempts=ledger["prior_attempts"] + ledger["attempts_started"], budget=7,
        stopped_reason=ledger.get("stopped_reason"), paused_after_v05=ledger.get("completed_authorized_v1", False))))
    return 1 if problems else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--run")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prior-records", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--offline-gate", type=Path)
    parser.add_argument("--diagnostics", type=Path)
    args = parser.parse_args()
    if args.prepare:
        if any(v is None for v in (args.prior_records, args.review, args.offline_gate, args.diagnostics)):
            parser.error("prepare requires prior records, review, offline gate, and diagnostics")
        prepare(args.output.resolve(), args.prior_records, args.review, args.offline_gate, args.diagnostics)
        return 0
    return run_one(args.output.resolve(), args.run)


if __name__ == "__main__":
    sys.exit(main())
