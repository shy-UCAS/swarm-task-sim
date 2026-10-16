"""S15 stage 2 step 2: planning-only yield run over registered skeleton descriptors.

Reuses scripts/run_v07_s2_expansion.py::descriptor_jobs for the task list and
scripts/run_v07_m3b_trial.py::run_stage("q2", ...) for the 8-process execution. No planner,
config or scene source is modified; results go to a new external attempt directory.
"""
import argparse
import cProfile
from datetime import datetime, timezone
import io
import json
import pstats
import subprocess
import sys
import time
import traceback
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scripts.run_v07_m3_trial import planning_job
from scripts.run_v07_m3b_trial import run_stage, runtime_hashes
from scripts.run_v07_s2_expansion import DEFAULT_DATA, descriptor_jobs
from task_v07.expansion.contracts import P0ContractError
from task_v07.io import read_json, save_json, sha

WORKERS = 8
BUDGET_NOTE = "每组 200 提案、组合预算 1000（规划器内置值，未改）"
STATUSES = ("completed", "TIME_LIMIT_STOP", "ERROR_STOP", "P0_STOP")
PROFILE_TOP = 25
PROFILE_OUT = PROJECT / "docs/v07/evidence/s15/s15_planning_profile.txt"


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


def read_skeleton_request(path):
    """A JSON list, a {"skeletons": [...]} / {"skeleton_ids": [...]} object, or one ID per line."""
    text = Path(path).read_text(encoding="utf-8-sig")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return [line.strip() for line in text.splitlines() if line.strip()]
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("skeletons", "skeleton_ids", "selected_skeletons"):
            if isinstance(value.get(key), list):
                return value[key]
    raise SystemExit(f"Unsupported skeleton request format: {path}")


def median_target(directory, completed):
    """The completed skeleton whose planning wall clock is closest to the median of the set."""
    walls = {skeleton_id: read_json(Path(directory) / skeleton_id / "planning_result.json")["planning_wall_s"]
             for skeleton_id in completed}
    values = sorted(walls.values())
    count = len(values)
    median = values[count // 2] if count % 2 else (values[count // 2 - 1] + values[count // 2]) / 2
    chosen = min(sorted(walls), key=lambda skeleton_id: (abs(walls[skeleton_id] - median), skeleton_id))
    return chosen, median, walls


def run_profile(args):
    """One registered skeleton, one process, profiled; never part of any batch statistic."""
    source = args.profile_from.resolve()
    registration = read_json(source / "registration.json")
    completed = [skeleton_id for skeleton_id in registration["selected_skeletons"]
                 if (source / skeleton_id / "planning_result.json").exists()]
    if not completed:
        raise SystemExit(f"No completed skeleton to profile in {source}")
    target, median, walls = median_target(source, completed)
    descriptors_dir = args.descriptors.resolve()
    hashes = runtime_hashes()
    stamp = datetime.now(timezone.utc)
    out = DEFAULT_DATA / f"attempt_s15profile_{stamp.strftime('%Y%m%dT%H%M%SZ')}"
    out.mkdir(parents=True, exist_ok=False)
    jobs = descriptor_jobs(descriptors_dir, [target], out)
    if len(jobs) != 1:
        raise P0ContractError(f"descriptor_jobs returned {len(jobs)} jobs for the profile target")
    save_json(out / "registration.json", {
        "schema": "traj2language.s15_stage2_profile_registration/1", "phase": "q2",
        "descriptors": str(descriptors_dir), "profile_from": str(source), "target": target,
        "completed_pool": len(completed), "median_planning_wall_s": median,
        "target_planning_wall_s": walls[target], "workers": 1, "search_budget": BUDGET_NOTE,
        "entry_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
        "runtime_sha256": hashes, "created_utc": stamp.isoformat(), "script": "scripts/run_v07_s15_yield.py",
        "script_sha256": sha(Path(__file__)), "profile_top": PROFILE_TOP, "backend": "unified"})
    print(f"OUTPUT {out}", flush=True)
    started = time.monotonic()
    listing = io.StringIO()
    profiler = cProfile.Profile()
    profiler.enable()
    result = planning_job(jobs[0])
    profiler.disable()
    wall = time.monotonic() - started
    stable = runtime_hashes() == hashes
    stats = pstats.Stats(profiler, stream=listing)
    stats.strip_dirs().sort_stats("cumulative")
    stats.print_stats(PROFILE_TOP)
    header = [f"# S1.5 阶段 2 单骨架规划 cProfile（top {PROFILE_TOP} by cumulative time）", "",
              f"- 来源批次：{source}",
              f"- 该批已完成骨架：{len(completed)} 个；规划墙钟中位数：{median!r} s",
              f"- 选中骨架：{target}（该骨架规划墙钟 {walls[target]!r} s，最接近中位数）",
              f"- 单进程运行 planning_job；进程数 1；每组 200 提案、组合预算 1000（规划器内置值，未改）",
              f"- planning_result 状态：{result['status']}；eligible_combinations={result['eligible_combinations']}；"
              f"planning_wall_s={result.get('planning_wall_s')!r}",
              f"- 本次观测墙钟（含导入与写出）：{wall:.3f} s",
              f"- 运行前后 runtime_sha256 一致：{stable}",
              f"- 本表只用于判断耗时来源，未据此优化规划器。", ""]
    Path(args.profile_out).write_text("\n".join(header) + listing.getvalue(), encoding="utf-8", newline="\n")
    save_json(out / "profile_result.json", {
        "target": target, "completed_pool": len(completed), "median_planning_wall_s": median,
        "target_planning_wall_s": walls[target], "observed_wall_s": wall,
        "planning_result": result, "runtime_sha256_stable": stable, "profile_out": str(args.profile_out),
        "profile_top": PROFILE_TOP})
    print({"target": target, "median": median, "wall_s": round(wall, 3), "stable": stable,
           "status": result["status"], "profile_out": str(args.profile_out)}, flush=True)
    return 0 if stable else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptors", type=Path, required=True, help="Step 1 attempt directory")
    parser.add_argument("--limit", type=int, default=None, help="Only the first N skeleton_id values")
    parser.add_argument("--skeletons-file", type=Path,
                        help="Only the skeleton_id values listed in this file (resume entry point)")
    parser.add_argument("--wall-limit-s", type=float, default=None)
    parser.add_argument("--profile", action="store_true",
                        help="Profile one median-cost completed skeleton instead of running a batch")
    parser.add_argument("--profile-from", type=Path, help="Yield attempt whose completed pool picks the target")
    parser.add_argument("--profile-out", type=Path, default=PROFILE_OUT)
    args = parser.parse_args()
    dirty = working_tree_clean()
    if dirty:
        raise SystemExit(f"Refusing to run: the working tree is not clean ({len(dirty)} entries, first: {dirty[0]})")
    if args.profile:
        if args.profile_from is None:
            raise SystemExit("--profile requires --profile-from")
        if args.limit is not None or args.skeletons_file is not None or args.wall_limit_s is not None:
            raise SystemExit("--profile cannot be combined with --limit, --skeletons-file or --wall-limit-s")
        return run_profile(args)
    if args.wall_limit_s is None:
        raise SystemExit("--wall-limit-s is required unless --profile is used")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be a positive integer")
    if args.limit is not None and args.skeletons_file is not None:
        raise SystemExit("--limit and --skeletons-file are mutually exclusive")
    descriptors_dir = args.descriptors.resolve()
    descriptors = read_json(descriptors_dir / "private_skeleton_descriptors.json")
    ordered = sorted(record["skeleton_id"] for record in descriptors)
    if len(set(ordered)) != len(ordered):
        raise P0ContractError("Duplicate skeleton_id in the descriptor directory")
    if args.skeletons_file is not None:
        request = read_skeleton_request(args.skeletons_file)
        if len(set(request)) != len(request):
            raise P0ContractError("Duplicate skeleton_id in the requested list")
        unknown = sorted(set(request) - set(ordered))
        if unknown:
            raise P0ContractError(f"Requested skeleton_id values are absent from the descriptor directory: {unknown}")
        selected = sorted(request)
    else:
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
                    "skeletons_file": None if args.skeletons_file is None else str(args.skeletons_file.resolve()),
                    "skeletons_file_sha256": None if args.skeletons_file is None else sha(args.skeletons_file),
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
