"""S15 simulation pilot: run the existing q3 chain on registered S1.5 skeletons.

Reuses scripts/run_v07_s2_expansion.py::descriptor_jobs for the task list and
scripts/run_v07_m3b_trial.py::run_stage("q3", ...) for the 8-process execution, which internally
runs run_episode_job: planning -> M2 solo rehearsal and timing -> synchronous/sequential joint
fastsim -> M1 judgement -> audit. No planner, M1, M2 or fastsim source is modified.
"""
import argparse
from datetime import datetime, timezone
import json
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
from task_v07.expansion.views import _paired
from task_v07.io import read_json, save_json, sha

WORKERS = 8
STATUSES = ("completed", "TIME_LIMIT_STOP", "ERROR_STOP", "P0_STOP")
DESCRIPTOR_ATTEMPT = "attempt_s15desc_20261016T154909Z"
SUMMARY = PROJECT / "docs/v07/evidence/s15/s15_yield_summary.json"
DRAWS_PER_MODE = 3
SELECTION_RULE = (
    "读取 docs/v07/evidence/s15/s15_yield_summary.json 的 draw_appendix：在 classification == '全成功' 的抽签里，"
    "按 approach_mode 分两组（组序按 approach_mode 字符串升序），每组按 'family#slot' 字符串升序取前 3 次，"
    "共 6 次抽签；每次抽签的 5 个意图全部纳入，共 30 个骨架。"
)


def entry_commit():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()


def working_tree_clean():
    status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"],
                                     cwd=PROJECT, text=True)
    return [line for line in status.splitlines() if line.strip()]


def select_draws(summary_path, per_mode=DRAWS_PER_MODE):
    """Deterministic draw selection; planning success is the registered entry condition."""
    appendix = read_json(summary_path)["draw_appendix"]
    complete = [record for record in appendix["draws"] if record["classification"] == "全成功"]
    grouped = {}
    for record in complete:
        grouped.setdefault(record["approach_mode"], []).append(record)
    chosen = []
    for mode in sorted(grouped):
        ordered = sorted(grouped[mode], key=lambda record: f"{record['family_id']}#slot{record['slot']}")
        if len(ordered) < per_mode:
            raise P0ContractError(f"approach_mode {mode} has only {len(ordered)} all-success draws")
        chosen.extend(ordered[:per_mode])
    skeletons = sorted({skeleton_id for record in chosen for skeleton_id in record["skeletons"]})
    if len(skeletons) != 5 * len(chosen):
        raise P0ContractError("A selected draw does not carry five distinct skeletons")
    return chosen, skeletons


def draw_manifest(chosen):
    return [{"family_id": record["family_id"], "slot": record["slot"],
             "draw_key": f"{record['family_id']}#slot{record['slot']}",
             "approach_mode": record["approach_mode"], "layout": record["layout"],
             "facility_count": record["facility_count"], "group_count": record["group_count"],
             "member_counts": record["member_counts"], "skeletons": record["skeletons"]}
            for record in chosen]


def read_skeleton_request(path):
    """A JSON list, a {"skeletons": [...]} object, or one ID per line."""
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


def skeleton_wall(rows):
    """Per-skeleton work time from the row fields that exist; see the report for the split."""
    return sum((row.get("amortized_skeleton_setup_s") or 0.0)
               + (row.get("simulation_wall_s") or 0.0)
               + (row.get("episode_postprocess_wall_s") or 0.0) for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptors", type=Path, default=DEFAULT_DATA / DESCRIPTOR_ATTEMPT)
    parser.add_argument("--skeletons-file", type=Path, help="Skeleton list to run in this attempt")
    parser.add_argument("--wall-limit-s", type=float, default=None)
    parser.add_argument("--select-out", type=Path,
                        help="Write the registered deterministic selection to this file and exit")
    parser.add_argument("--select-from", type=Path, default=SUMMARY)
    args = parser.parse_args()
    if args.select_out is not None:
        chosen, skeletons = select_draws(args.select_from)
        save_json(args.select_out, {"selection_rule": SELECTION_RULE, "source": str(args.select_from),
                                    "draws": draw_manifest(chosen), "skeletons": skeletons})
        print(json.dumps({"draws": len(chosen), "skeletons": len(skeletons),
                          "select_out": str(args.select_out)}, ensure_ascii=False), flush=True)
        return 0
    if args.skeletons_file is None or args.wall_limit_s is None:
        raise SystemExit("--skeletons-file and --wall-limit-s are required to run the pilot")
    dirty = working_tree_clean()
    if dirty:
        raise SystemExit(f"Refusing to run: the working tree is not clean ({len(dirty)} entries, first: {dirty[0]})")
    descriptors_dir = args.descriptors.resolve()
    descriptors = read_json(descriptors_dir / "private_skeleton_descriptors.json")
    known = sorted(record["skeleton_id"] for record in descriptors)
    request = read_skeleton_request(args.skeletons_file)
    if len(set(request)) != len(request):
        raise P0ContractError("Duplicate skeleton_id in the requested list")
    unknown = sorted(set(request) - set(known))
    if unknown:
        raise P0ContractError(f"Requested skeleton_id values are absent from the descriptor directory: {unknown}")
    selected = sorted(request)
    chosen, _ = select_draws(args.select_from)
    manifest = draw_manifest(chosen)
    manifest_skeletons = sorted({skeleton_id for record in chosen for skeleton_id in record["skeletons"]})
    if set(selected) - set(manifest_skeletons):
        raise P0ContractError("Requested skeletons are outside the registered pilot selection")
    hashes = runtime_hashes()
    stamp = datetime.now(timezone.utc)
    out = DEFAULT_DATA / f"attempt_s15sim_{stamp.strftime('%Y%m%dT%H%M%SZ')}"
    out.mkdir(parents=True, exist_ok=False)
    registration = {"schema": "traj2language.s15_sim_pilot_registration/1", "phase": "q3",
                    "descriptors": str(descriptors_dir), "descriptor_count": len(known),
                    "descriptors_sha256": sha(descriptors_dir / "private_skeleton_descriptors.json"),
                    "selection_rule": SELECTION_RULE, "selection_source": str(args.select_from),
                    "draws": manifest, "selected_skeletons": selected, "selected_count": len(selected),
                    "skeletons_file": str(args.skeletons_file.resolve()),
                    "skeletons_file_sha256": sha(args.skeletons_file),
                    "wall_limit_s": args.wall_limit_s, "workers": WORKERS,
                    "chain": "planning -> M2 solo rehearsal and timing -> synchronous/sequential joint fastsim "
                             "-> M1 judgement -> audit; max 5 calibration rounds per skeleton",
                    "entry_commit": entry_commit(), "runtime_sha256": hashes,
                    "script": "scripts/run_v07_s15_sim_pilot.py", "script_sha256": sha(Path(__file__)),
                    "created_utc": stamp.isoformat(), "backend": "unified"}
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
        run_stage("q3", jobs, out, deadline, completed, rows)
    except BaseException as exc:
        status = ("TIME_LIMIT_STOP" if isinstance(exc, TimeoutError) else
                  "P0_STOP" if isinstance(exc, P0ContractError) else "ERROR_STOP")
        stop = {"reason": str(exc), "exception_type": type(exc).__name__, "traceback": traceback.format_exc()}
    stable = runtime_hashes() == hashes
    if not stable:
        status = "P0_STOP"
        stop = {"reason": "Runtime sources changed during the pilot", "exception_type": "P0ContractError",
                "traceback": None}
    if status not in STATUSES:
        raise P0ContractError(f"Unregistered status {status}")
    unfinished = sorted(set(selected) - set(completed))
    per_skeleton = {}
    for skeleton_id in selected:
        subset = [row for row in rows if row["skeleton_id"] == skeleton_id]
        paired = None
        try:
            paired = _paired(subset)
        except P0ContractError as exc:
            paired = f"P0:{exc}"
        per_skeleton[skeleton_id] = {"rows": len(subset), "strict_pair": paired,
                                     "wall_s": skeleton_wall(subset)}
    summary = {"schema": "traj2language.s15_sim_pilot_result/1", "phase": "q3", "status": status,
               "attempt": str(out), "draws": manifest, "selected_count": len(selected),
               "completed": sorted(completed), "unfinished": unfinished,
               "completed_count": len(set(completed)), "wall_s": time.monotonic() - started,
               "wall_limit_s": args.wall_limit_s, "workers": WORKERS,
               "strict_pairs": sum(1 for value in per_skeleton.values() if value["strict_pair"] is True),
               "per_skeleton": per_skeleton, "runtime_sha256_stable": stable,
               "entry_commit": registration["entry_commit"],
               "descriptors_sha256": registration["descriptors_sha256"], "stop": stop}
    save_json(out / "run_result.json", summary)
    print({key: summary[key] for key in ("status", "completed_count", "selected_count", "strict_pairs",
                                         "wall_s", "runtime_sha256_stable", "unfinished")}, flush=True)
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
