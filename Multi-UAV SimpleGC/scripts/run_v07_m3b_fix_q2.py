"""User-authorized fresh M3b repair Q2 window; never starts Q3 or overwrites F0 sources."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys
import time
import traceback

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.run_v07_m3_checks import EVIDENCE
from scripts.run_v07_m3_trial import atomic, frozen_check
from scripts.run_v07_m3b_trial import q2_gate, run_stage, runtime_hashes
from scripts.run_v07_s2_expansion import descriptor_jobs, DEFAULT_DATA
from task_v07.expansion.contracts import P0ContractError
from task_v07.io import read_json, save_json, sha

SUMMARY = EVIDENCE / "m3b_fix_q2.json"
PHASE = "m3b_fix_q2"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", type=Path,
                        help="Repair reruns retain this fix attempt's original 900 s wall window")
    args = parser.parse_args()
    reg = read_json(EVIDENCE / "m3b_inputs.json")
    frozen = frozen_check(reg)
    selected = [r["skeleton_id"] for r in reg["selected"]]
    if (len(selected) != 20 or len(set(selected)) != 20
            or sum(bool(r["q3"]) for r in reg["selected"]) != 10
            or reg["q2_wall_limit_s"] != 900 or reg["max_workers"] != 8
            or len(reg["frozen_sha256"]) != 39):
        raise P0ContractError("Fixed M3b input/budget/frozen registration changed")
    if sha(Path(reg["descriptor_attempt"]) / "private_skeleton_descriptors.json") != reg["descriptor_sha256"]:
        raise P0ContractError("Fixed descriptor bytes changed")
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=PROJECT, text=True).strip()
    if branch != "review/m3b-q2-failure":
        raise ValueError("Repair Q2 must run on review/m3b-q2-failure")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=PROJECT, text=True).strip():
        raise ValueError("Repair Q2 requires all modifications committed before launch")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
    preserved = {name: sha(EVIDENCE / name) for name in
                 ("m3b_q2.json", "m3b_q2_diagnostics.json", "m3b_inputs.json")}
    hashes = runtime_hashes()
    stamp = datetime.now(timezone.utc)
    start = time.monotonic()
    origin = stamp.isoformat()
    if args.origin:
        original = read_json(args.origin / "registration.json")
        if original["phase"] != PHASE or original["selected"] != reg["selected"]:
            raise ValueError("Origin must be this repair Q2's fixed-input window")
        origin = original["budget_origin_utc"]
        if SUMMARY.exists():
            latest_reg = read_json(Path(read_json(SUMMARY)["attempt"]) / "registration.json")
            if latest_reg["budget_origin_utc"] != origin:
                raise ValueError("Origin must retain the already-started repair Q2 window")
    elif SUMMARY.exists():
        raise ValueError("Repair Q2 already started; use --origin without resetting its window")
    elapsed = (stamp - datetime.fromisoformat(origin)).total_seconds()
    remaining = 900. - elapsed
    if remaining <= 0:
        raise TimeoutError("Repair Q2's original 900 s window expired")
    out = DEFAULT_DATA / f"attempt_m3b_fix_q2_{stamp.strftime('%Y%m%dT%H%M%S%fZ')}"
    out.mkdir(exist_ok=False)
    registration = {**reg, "phase": PHASE, "branch": branch,
        "authorization": "User explicitly authorized a new 900 s full Q2 window after F1-F4; no Q3 in this round",
        "started_utc": stamp.isoformat(), "budget_origin_utc": origin,
        "workers": 8, "selected_skeletons": selected, "entry_commit": head,
        "runtime_sha256": hashes, "entry_sha256": sha(Path(__file__)),
        "geometry_config_sha256": sha(PROJECT / "configs/generator/geometry_v07_r1.json"),
        "prior_geometry_config_sha256": reg["geometry_config_sha256"],
        "fixed_input_registration_sha256": sha(EVIDENCE / "m3b_inputs.json"),
        "preserved_evidence_sha256": preserved, "backend": "unified",
        "available_wall_s": remaining, "wall_limit_s": 900, "q3_authorized": False}
    save_json(out / "registration.json", registration)
    # Persist the origin before any worker starts, including if the process is interrupted.
    atomic(SUMMARY, {"phase": PHASE, "status": "running", "attempt": str(out),
                     "budget_origin_utc": origin, "entry_commit": head, "rows": [],
                     "completed": [], "unfinished": selected})
    print(f"OUTPUT {out}", flush=True)
    rows = []; completed = []; status = "completed"; stop = None
    try:
        jobs = descriptor_jobs(Path(reg["descriptor_attempt"]), selected, out)
        run_stage("q2", jobs, out, start + remaining, completed, rows)
        if runtime_hashes() != hashes:
            raise P0ContractError("Runtime source changed during registered repair Q2")
        if any(sha(EVIDENCE / p) != h for p, h in preserved.items()):
            raise P0ContractError("Prior Q2 or fixed input evidence changed during repair Q2")
        frozen_check(reg)
    except BaseException as exc:
        status = ("TIME_LIMIT_STOP" if isinstance(exc, TimeoutError) else
                  "P0_STOP" if isinstance(exc, P0ContractError) else "ERROR_STOP")
        stop = {"reason": str(exc), "exception_type": type(exc).__name__, "traceback": traceback.format_exc()}
    gate = q2_gate(reg, rows)
    if status == "completed":
        status = "PASS" if gate["passed"] else "Q2_NOT_PASSED"
    try:
        final_frozen = frozen_check(reg)
    except P0ContractError as exc:
        final_frozen = {"status": "FAIL", "reason": str(exc)}
        status = "P0_STOP"
        if stop is None:
            stop = {"reason": str(exc), "exception_type": type(exc).__name__}
    unfinished = sorted(set(selected) - set(completed))
    summary = {"phase": PHASE, "status": status, "attempt": str(out), "entry_commit": head,
        "rows": rows, "completed": completed, "unfinished": unfinished,
        "wall_s": time.monotonic() - start, "cumulative_wall_s": elapsed + time.monotonic() - start,
        "wall_limit_s": 900, "budget_origin_utc": origin, "stop": stop,
        "frozen_check": final_frozen, "q2_gate": gate, "stages": [], "q3_started": False,
        "unfinished_evidence": {sid: read_json(out / sid / "progress.json") for sid in unfinished
                                if (out / sid / "progress.json").exists()}}
    save_json(out / "trial_result.json", summary)
    atomic(SUMMARY, summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("rows", "unfinished_evidence")}, ensure_ascii=False), flush=True)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
