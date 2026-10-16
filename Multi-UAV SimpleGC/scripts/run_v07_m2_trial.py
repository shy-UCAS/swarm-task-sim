"""Q-D: fixed quick-B ten skeletons, eight workers, one run with a 60-minute cap."""
import argparse
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.run_v07_s2_episode_batch import run_episode_job
from scripts.run_v07_s2_expansion import DEFAULT_DATA, descriptor_jobs
from task_v07.execution import FROZEN_SHA256, frozen_config
from task_v07.expansion.contracts import P0ContractError
from task_v07.io import read_json, save_json, sha
from task_v07.unified.outcome import FAILURE_CATEGORIES

SOURCE = DEFAULT_DATA / "attempt_s2_search_quick_b_20261015T090658Z_5ac915b5"
WORKERS = 8
WALL_LIMIT_S = 3600.


def replace_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                         encoding="utf-8", newline="\n")
    temporary.replace(path)


def check_block(skeleton_id, rows):
    if len(rows) != 2 or {r["mode"] for r in rows} != {"synchronous", "sequential"}:
        raise P0ContractError("Trial result is not a complete timing pair")
    if any(r["skeleton_id"] != skeleton_id for r in rows):
        raise P0ContractError("Trial returned an unregistered skeleton")
    if all(r["path"] is None for r in rows):
        for row in rows:
            if row["category"] not in FAILURE_CATEGORIES or not row["exhausted"]:
                raise P0ContractError("Rejected trial result has an invalid category or exhaustion flag")
            history = row["geometry_attempts"]
            if not history or any(h["category"] not in FAILURE_CATEGORIES for h in history):
                raise P0ContractError("Rejected trial result lacks valid per-round history")
            if row["category"] != history[-1]["category"]:
                raise P0ContractError("Top rejection category differs from the last round")
    elif all(r["path"] is not None for r in rows):
        if rows[0]["condition_digest"] != rows[1]["condition_digest"]:
            raise P0ContractError("Trial pair condition digests differ")
        for row in rows:
            if row["audit_passed"] is not True or row["audit"]["input_whitelist_passed"] is not True:
                raise P0ContractError("Trial audit or model input whitelist failed")
    else:
        raise P0ContractError("Trial returned only half a pair")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate fixed inputs without simulation or new attempt")
    args = parser.parse_args()
    registration = read_json(SOURCE / "registration.json")
    selected = [row["skeleton_id"] for row in registration["selected"]]
    if len(selected) != 10 or len(set(selected)) != 10:
        raise ValueError("Q-D requires exactly the ten unique quick-B registered skeletons")
    frozen_config()
    if args.check:
        jobs = descriptor_jobs(Path(registration["source_attempt"]), selected, DEFAULT_DATA)
        if any(j["descriptor"].get("subset") == "aborted" for j in jobs):
            raise ValueError("Abort samples are outside Q-D")
        print(json.dumps({"status": "PASS", "workers": WORKERS, "wall_limit_s": WALL_LIMIT_S,
                          "selected": selected, "simulation_count": 0}, ensure_ascii=False))
        return 0

    started = time.perf_counter()
    started_utc = datetime.now(timezone.utc)
    out = DEFAULT_DATA / f"attempt_m2_trial_{started_utc.strftime('%Y%m%dT%H%M%S%fZ')}"
    out.mkdir(exist_ok=False)
    print(f"OUTPUT {out}", flush=True)
    save_json(out / "registration.json", {
        "scope": "Q-D fixed quick-B ten skeletons; existing geometry and M2 pipeline; no rerun",
        "source_attempt": str(SOURCE), "descriptor_attempt": registration["source_attempt"],
        "source_registration_sha256": sha(SOURCE / "registration.json"), "selected": selected,
        "workers": WORKERS, "wall_limit_s": WALL_LIMIT_S, "started_utc": started_utc.isoformat(),
        "deadline_utc": (started_utc + timedelta(seconds=WALL_LIMIT_S)).isoformat(),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
        "entry_script_sha256": sha(Path(__file__)), "config_sha256": FROZEN_SHA256,
        "generator_config_sha256": sha(PROJECT / "configs/generator/generator_v07_r1.json")})
    jobs = descriptor_jobs(Path(registration["source_attempt"]), selected, out)
    rows, completed = [], []
    pool = ProcessPoolExecutor(max_workers=WORKERS)
    futures = {pool.submit(run_episode_job, job): job["descriptor"]["skeleton_id"] for job in jobs}
    pending = set(futures)
    status, stop = "completed", None
    last_progress = 0.
    try:
        while pending:
            remaining = WALL_LIMIT_S - (time.perf_counter() - started)
            if remaining <= 0:
                raise TimeoutError("Q-D reached its 60-minute wall-clock limit; do not rerun")
            done, pending = wait(pending, timeout=min(1., remaining), return_when=FIRST_COMPLETED)
            for future in sorted(done, key=lambda item: futures[item]):
                block = future.result()
                check_block(futures[future], block)
                rows.extend(block)
                completed.append(futures[future])
                replace_json(out / "episode_records.json", sorted(rows, key=lambda r: r["episode_id"]))
                print(json.dumps({"stage": "skeleton_complete", "skeleton_id": futures[future],
                                  "completed": len(completed), "wall_s": round(time.perf_counter() - started, 2)},
                                 ensure_ascii=False), flush=True)
            elapsed = time.perf_counter() - started
            if done or elapsed - last_progress >= 30:
                replace_json(out / "progress.json", {"status": "running", "completed": sorted(completed),
                    "pending": sorted(futures[f] for f in pending), "wall_s": elapsed})
                last_progress = elapsed
        if time.perf_counter() - started > WALL_LIMIT_S:
            raise TimeoutError("Q-D result collection exceeded the 60-minute wall-clock limit")
    except BaseException as exc:
        status = "TIME_LIMIT_STOP" if isinstance(exc, TimeoutError) else (
            "P0_STOP" if isinstance(exc, P0ContractError) else "ERROR_STOP")
        stop = {"status": status, "reason": str(exc), "exception_type": type(exc).__name__,
                "traceback": traceback.format_exc(), "wall_s": time.perf_counter() - started,
                "completed": sorted(completed), "pending": sorted(set(selected) - set(completed)),
                "rerun_allowed": False, "partial_files_preserved": True}
        save_json(out / f"{status}.json", stop)
        for future in futures:
            future.cancel()
        # Terminate only workers belonging to this trial, never unrelated Python processes.
        for process in list(pool._processes.values()):
            if process.is_alive():
                process.terminate()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    replace_json(out / "episode_records.json", sorted(rows, key=lambda r: r["episode_id"]))
    summary = {"status": status, "selected": selected, "completed": sorted(completed),
               "unfinished": sorted(set(selected) - set(completed)), "episode_records": len(rows),
               "wall_s": time.perf_counter() - started, "workers": WORKERS, "wall_limit_s": WALL_LIMIT_S,
               "stop": stop, "output_directory": str(out)}
    save_json(out / "trial_result.json", summary)
    replace_json(out / "progress.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
