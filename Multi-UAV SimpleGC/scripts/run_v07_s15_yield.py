"""S15 stage 2 step 2: planning-only yield run over registered skeleton descriptors.

Reuses scripts/run_v07_s2_expansion.py::descriptor_jobs for the task list and
scripts/run_v07_m3b_trial.py::run_stage("q2", ...) for the 8-process execution. No planner,
config or scene source is modified; results go to a new external attempt directory.
"""
import argparse
from datetime import datetime, timezone
import subprocess
import sys
import time
import traceback
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scripts.run_v07_m3b_trial import run_stage, runtime_hashes
from scripts.run_v07_s2_expansion import DEFAULT_DATA, descriptor_jobs
from task_v07.expansion.contracts import P0ContractError
from task_v07.io import read_json, save_json, sha

WORKERS = 8
BUDGET_NOTE = "每组 200 提案、组合预算 1000（规划器内置值，未改）"
STATUSES = ("completed", "TIME_LIMIT_STOP", "ERROR_STOP", "P0_STOP")


def working_tree_clean():
    status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"],
                                     cwd=PROJECT, text=True)
    return [line for line in status.splitlines() if line.strip()]


def wall_clock(out, skeleton_id):
    """Completed skeletons report their own summary; unfinished ones keep the last snapshot."""
    progress = out / skeleton_id / "progress.json"
    if progress.exists():
        value = read_json(progress)
        if isinstance(value, dict) and value.get("planning_wall_s") is not None:
            return value["planning_wall_s"]
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptors", type=Path, required=True, help="Step 1 attempt directory")
    parser.add_argument("--limit", type=int, default=None, help="Only the first N skeleton_id values")
    parser.add_argument("--wall-limit-s", type=float, required=True)
    args = parser.parse_args()
    dirty = working_tree_clean()
    if dirty:
        raise SystemExit(f"Refusing to run: the working tree is not clean ({len(dirty)} entries, first: {dirty[0]})")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be a positive integer")
    descriptors_dir = args.descriptors.resolve()
    descriptors = read_json(descriptors_dir / "private_skeleton_descriptors.json")
    ordered = sorted(record["skeleton_id"] for record in descriptors)
    if len(set(ordered)) != len(ordered):
        raise P0ContractError("Duplicate skeleton_id in the descriptor directory")
    selected = ordered[:args.limit] if args.limit else ordered
    hashes = runtime_hashes()
    stamp = datetime.now(timezone.utc)
    out = DEFAULT_DATA / f"attempt_s15yield_{stamp.strftime('%Y%m%dT%H%M%SZ')}"
    out.mkdir(parents=True, exist_ok=False)
    registration = {"schema": "traj2language.s15_stage2_yield_registration/1", "phase": "q2",
                    "descriptors": str(descriptors_dir), "descriptor_count": len(ordered),
                    "descriptors_sha256": sha(descriptors_dir / "private_skeleton_descriptors.json"),
                    "registration_sha256": sha(descriptors_dir / "registration.json"),
                    "selected_skeletons": selected, "selected_count": len(selected), "limit": args.limit,
                    "wall_limit_s": args.wall_limit_s, "workers": WORKERS,
                    "search_budget": BUDGET_NOTE, "entry_commit": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
                    "runtime_sha256": hashes, "script": "scripts/run_v07_s15_yield.py",
                    "script_sha256": sha(Path(__file__)), "created_utc": stamp.isoformat(),
                    "backend": "unified"}
    save_json(out / "registration.json", registration)
    print(f"OUTPUT {out}", flush=True)
    started = time.monotonic()
    deadline = started + args.wall_limit_s
    rows, completed, stop = [], [], None
    status = "completed"
    try:
        jobs = descriptor_jobs(descriptors_dir, selected, out)
        if len(jobs) != len(selected):
            raise P0ContractError(f"descriptor_jobs returned {len(jobs)} jobs for {len(selected)} skeletons")
        run_stage("q2", jobs, out, deadline, completed, rows)
    except BaseException as exc:
        status = ("TIME_LIMIT_STOP" if isinstance(exc, TimeoutError) else
                  "P0_STOP" if isinstance(exc, P0ContractError) else "ERROR_STOP")
        stop = {"reason": str(exc), "exception_type": type(exc).__name__, "traceback": traceback.format_exc()}
    stable = runtime_hashes() == hashes
    if not stable:
        status = "P0_STOP"
        stop = {"reason": "Runtime sources changed during the yield run", "exception_type": "P0ContractError",
                "traceback": None}
    if status not in STATUSES:
        raise P0ContractError(f"Unregistered status {status}")
    unfinished = sorted(set(selected) - set(completed))
    measured = {row["skeleton_id"]: row.get("planning_wall_s") for row in rows}
    summary = {"schema": "traj2language.s15_stage2_yield_result/1", "phase": "q2", "status": status,
               "attempt": str(out), "descriptors": str(descriptors_dir), "limit": args.limit,
               "wall_limit_s": args.wall_limit_s, "workers": WORKERS, "search_budget": BUDGET_NOTE,
               "planned_count": len(selected), "completed": sorted(completed), "unfinished": unfinished,
               "completed_count": len(set(completed)), "wall_s": time.monotonic() - started,
               "planning_wall_s": {sid: (measured.get(sid) if sid in measured else wall_clock(out, sid))
                                   for sid in selected},
               "runtime_sha256_stable": stable, "entry_commit": registration["entry_commit"],
               "descriptors_sha256": registration["descriptors_sha256"], "stop": stop}
    save_json(out / "run_result.json", summary)
    print({key: summary[key] for key in ("status", "completed_count", "planned_count", "wall_s",
                                         "runtime_sha256_stable", "unfinished")}, flush=True)
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
