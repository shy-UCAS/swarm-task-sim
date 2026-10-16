"""M3a registered Q2 (900 s) and Q3 (1800 s); diagnostics never become gates."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.run_v07_m3_checks import EVIDENCE
from scripts.run_v07_s2_expansion import descriptor_jobs, DEFAULT_DATA
from scripts.run_v07_s2_episode_batch import run_episode_job
from task_v07.io import read_json, save_json, sha
from task_v07.expansion.contracts import P0ContractError
from task_v07.expansion.group_candidate_pool import independent_episode_pool


def atomic(path, value):
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def rank(record):
    return ({"whole_route": 0, "connection": 1, "shape": 2}.get(record["stage"], -1),
            len(record.get("whole_route_checks", {}).get("issues", [])), record["candidate_index"])


def planning_job(payload):
    started = time.perf_counter()
    descriptor = payload["descriptor"]; sid = descriptor["skeleton_id"]
    out = Path(payload["out"])/sid; out.mkdir()
    counts = Counter(); by_group = Counter(); best = {}; accepted = Counter()
    journal = out/"proposals.jsonl"
    def snapshot():
        return {"skeleton_id": sid, "status": "running", "planning_wall_s": time.perf_counter()-started,
                "attempted_proposals": sum(by_group.values()), "group_attempts": dict(by_group),
                "accepted_by_group": dict(accepted), "rejection_reasons": dict(counts),
                "closest_proposals_by_group": best}
    with journal.open("w", encoding="utf-8") as stream:
        def progress(record):
            gid = record["group_id"]; by_group[gid] += 1
            if record["reason"]:
                counts[record["reason"]] += 1
                if gid not in best or rank(record) < rank(best[gid]): best[gid] = record
            else:
                accepted[gid] += 1
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False)+"\n"); stream.flush()
            if sum(by_group.values()) % 10 == 0:
                atomic(out/"progress.json", snapshot())
        pool, report = independent_episode_pool(payload["scene"], descriptor, on_record=progress)
    save_json(out/"candidate_pool.json", report)
    chosen = pool[0] if pool else None
    result = {**snapshot(), "status": "PASS" if pool else "REJECT", "eligible_combinations": len(pool),
              "multi_max_pairwise_ingress_heading_deg": None, "planned_heading_by_group_deg": {},
              "observed_minimum_separation_m": None, "spacing_source": "not_measured_Q2_has_no_simulation",
              "combination_rejection_reasons": report["combination_rejection_reasons"],
              "whole_route_pass": bool(pool) and all(c["status"] == "PASS" for c in chosen["checks"].values())}
    if chosen:
        save_json(out/"selected_skeleton.json", chosen["skeleton"])
        save_json(out/"selected_checks.json", chosen["checks"])
        angles = {g: c["multi_max_pairwise_ingress_heading_deg"] for g, c in chosen["checks"].items()}
        result["planned_heading_by_group_deg"] = angles
        result["multi_max_pairwise_ingress_heading_deg"] = max((a for a in angles.values() if a is not None), default=None)
        result["selected_candidate_index"] = chosen["index"]
        result["closest_proposals_by_group"] = {}  # Full proposal records remain in the journal.
    result["planning_wall_s"] = time.perf_counter()-started
    save_json(out/"planning_result.json", result)
    atomic(out/"progress.json", result)
    return result


def frozen_check(registration):
    differences = [p for p, expected in registration["frozen_sha256"].items() if sha(PROJECT/p) != expected]
    if differences:
        raise P0ContractError(f"Frozen files changed: {differences}")
    return {"status": "PASS", "file_count": len(registration["frozen_sha256"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("q2", "q3"))
    parser.add_argument("--q2-origin", type=Path, help="Original Q2 attempt: repairs share its original 900 s wall window")
    args = parser.parse_args()
    registration = read_json(EVIDENCE/"m3_inputs.json")
    frozen = frozen_check(registration)
    if args.phase == "q3":
        q2 = read_json(EVIDENCE/"m3a_q2.json")
        if q2["status"] != "PASS" or len(q2["rows"]) != 4 or not all(r["whole_route_pass"] for r in q2["rows"]):
            raise ValueError("Q3 requires all four fixed Q2 whole-route plans to pass")
    selected = [r["skeleton_id"] for r in registration["selected"] if args.phase == "q2" or r["q3"]]
    limit = registration[args.phase+"_wall_limit_s"]
    start = time.perf_counter(); stamp = datetime.now(timezone.utc)
    origin = None
    if args.q2_origin:
        if args.phase != "q2": parser.error("--q2-origin only applies to Q2")
        origin = read_json(args.q2_origin/"registration.json")["started_utc"]
        limit -= (stamp-datetime.fromisoformat(origin)).total_seconds()
        if limit <= 0: raise TimeoutError("Original Q2 900 s window already expired; no rerun allowed")
    out = DEFAULT_DATA/f"attempt_m3a_{args.phase}_{stamp.strftime('%Y%m%dT%H%M%S%fZ')}"
    out.mkdir(exist_ok=False)
    save_json(out/"registration.json", {**registration, "phase": args.phase, "selected_skeletons": selected,
        "started_utc": stamp.isoformat(), "wall_limit_s": limit, "workers": min(8, len(selected)),
        "entry_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
        "entry_sha256": sha(Path(__file__)), "backend": "unified", "q2_budget_origin": origin,
        "runtime_source_sha256": {p.relative_to(PROJECT).as_posix(): sha(p) for p in (PROJECT/"task_v07/unified").glob("*.py")}})
    print(f"OUTPUT {out}", flush=True)
    jobs = descriptor_jobs(Path(registration["descriptor_attempt"]), selected, out)
    pool = ProcessPoolExecutor(max_workers=min(8, len(jobs)))
    futures = {pool.submit(planning_job if args.phase == "q2" else run_episode_job, job): job["descriptor"]["skeleton_id"] for job in jobs}
    pending = set(futures); rows = []; completed = []; stop = None; last_progress = 0.
    status = "completed"
    try:
        while pending:
            remaining = limit-(time.perf_counter()-start)
            if remaining <= 0: raise TimeoutError(f"{args.phase} wall-clock cap reached")
            done, pending = wait(pending, timeout=min(1., remaining), return_when=FIRST_COMPLETED)
            for future in done:
                result = future.result()
                if args.phase == "q2": rows.append(result)
                else: rows.extend(result)
                completed.append(futures[future])
                atomic(out/("planning_records.json" if args.phase == "q2" else "episode_records.json"), rows)
                print(json.dumps({"completed": futures[future], "wall_s": time.perf_counter()-start}), flush=True)
            if time.perf_counter()-last_progress >= 20:
                atomic(out/"progress.json", {"status": "running", "completed": completed,
                    "pending": [futures[f] for f in pending], "wall_s": time.perf_counter()-start})
                last_progress = time.perf_counter()
        if time.perf_counter()-start > limit: raise TimeoutError(f"{args.phase} result collection exceeded cap")
    except BaseException as exc:
        status = "TIME_LIMIT_STOP" if isinstance(exc, TimeoutError) else "P0_STOP" if isinstance(exc, P0ContractError) else "ERROR_STOP"
        stop = {"reason": str(exc), "exception_type": type(exc).__name__, "traceback": traceback.format_exc()}
        for future in futures: future.cancel()
        for process in list(pool._processes.values()):
            if process.is_alive(): process.terminate()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    if args.phase == "q2" and status == "completed":
        status = "PASS" if len(rows) == 4 and all(r["whole_route_pass"] for r in rows) else "Q2_NOT_PASSED"
    summary = {"phase": args.phase, "status": status, "attempt": str(out), "rows": rows,
               "completed": completed, "unfinished": sorted(set(selected)-set(completed)),
               "wall_s": time.perf_counter()-start, "wall_limit_s": limit, "stop": stop, "frozen_check": frozen}
    if args.phase == "q2":
        summary["unfinished_evidence"] = {sid: read_json(out/sid/"progress.json") for sid in summary["unfinished"] if (out/sid/"progress.json").exists()}
    save_json(out/"trial_result.json", summary)
    atomic(EVIDENCE/("m3a_q2.json" if args.phase == "q2" else "m3a_trial.json"), summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("rows", "unfinished_evidence")}, ensure_ascii=False), flush=True)
    return 0 if status in ("PASS", "completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
