"""FE-P0 isolated replay/planning workers; baseline code and archives stay read-only."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
DATA = PROJECT.parent.parent / "SwarmData/v07_dataset"
ARCHIVE = DATA / "attempt_s15sim_20261016T191411Z"
DESCRIPTORS = DATA / "attempt_s15desc_20261016T154909Z"
FAMILY = "family_s15_1c267d4d7000043d"
R0_ID = FAMILY + "_ext_005_regular"
PLAN_IDS = [R0_ID, FAMILY+"_ext_009_regular", "family_s15_1b876e6b8b6f70c6_ext_006_regular"]
REPLAY_IDS = [R0_ID, FAMILY+"_ext_006_regular", "family_s15_38bedc9d791d547b_ext_008_regular",
              FAMILY+"_ext_009_regular", FAMILY+"_ext_007_regular"]
PLAN_FILES = ("candidate_pool.json", "proposals.jsonl", "selected_skeleton.json",
              "selected_checks.json", "planning_result.json")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n",
                    encoding="utf-8", newline="\n")


def normalized(node, removed):
    if isinstance(node, dict):
        result = {}
        for key, value in node.items():
            if key in ("wall_s", "planning_wall_s") or key.endswith("_wall_s"):
                removed.add(key)
            else:
                result[key] = normalized(value, removed)
        return result
    if isinstance(node, list):
        return [normalized(value, removed) for value in node]
    return node


def first_difference(a, b, path="$"):
    if type(a) is not type(b):
        return {"path": path, "old": a, "new": b}
    if isinstance(a, dict):
        if set(a) != set(b):
            return {"path": path, "old_keys": sorted(a), "new_keys": sorted(b)}
        for key in sorted(a):
            difference = first_difference(a[key], b[key], f"{path}.{key}")
            if difference:
                return difference
    elif isinstance(a, list):
        if len(a) != len(b):
            return {"path": path, "old_length": len(a), "new_length": len(b)}
        for index, (x, y) in enumerate(zip(a, b)):
            difference = first_difference(x, y, f"{path}[{index}]")
            if difference:
                return difference
    elif a != b:
        return {"path": path, "old": a, "new": b}
    return None


def compare_plans(left, right):
    removed = set()
    rows = []
    for name in PLAN_FILES:
        a, b = left/name, right/name
        if a.exists() != b.exists():
            difference = {"path": name, "old_exists": a.exists(), "new_exists": b.exists()}
        elif not a.exists():
            # A genuinely empty pool has no selected candidate on either side.
            difference = None
        else:
            if name.endswith(".jsonl"):
                x = [json.loads(line) for line in a.read_text(encoding="utf-8").splitlines() if line.strip()]
                y = [json.loads(line) for line in b.read_text(encoding="utf-8").splitlines() if line.strip()]
            else:
                x, y = read(a), read(b)
            difference = first_difference(normalized(x, removed), normalized(y, removed), name)
        rows.append({"file": name, "equal": difference is None, "first_difference": difference})
        if difference:
            break
    return {"equal": all(row["equal"] for row in rows), "files": rows, "removed_keys": sorted(removed)}


def worker(project, task):
    project = project.resolve()
    # Replace the script-directory entry; never import perf packages for a base run.
    sys.path[0] = str(project)
    import numpy as np
    import task_v07
    import task_v07.execution as execution
    from task_v07.unified.rehearsal import joint_budget
    if not Path(task_v07.__file__).resolve().is_relative_to(project):
        raise SystemExit(3)
    out = Path(task["out"]); out.mkdir(parents=True, exist_ok=False)
    meta = {"project": str(project), "task_v07_file": task_v07.__file__,
            "execution_file": execution.__file__, "task": task}
    if task["kind"] == "plan":
        from scripts.run_v07_s2_expansion import descriptor_jobs
        from scripts.run_v07_m3_trial import planning_job
        jobs = descriptor_jobs(Path(task["descriptors"]), [task["skeleton_id"]], out)
        assert len(jobs) == 1
        started = time.perf_counter()
        result = planning_job(jobs[0])
        meta.update(wall_s=time.perf_counter()-started, planning_result=result)
    else:
        root = Path(task["archive"])/task["skeleton_id"]
        skeleton = read(root/"skeleton.json")
        geometry = root/f"geometry_{int(read(root/'timing_calibration.json')['calibration_round'])-1:02d}"
        if task["kind"] == "solo":
            agent = task["agent"]
            group = next(g for g in skeleton["group_skeletons"].values() if agent in g["members"])
            args = (group, {a: 0. for a in group["members"]})
            kwargs = {"only_agent": agent}
            reference = geometry/f"single_agent_{agent}.npz"
            compare_keys = ("time_us", "p", "v", "execution_status")
        else:
            plan = read(root/"timing_selection.json")["plans"][task["mode"]]
            delays = plan["departure_delays_s"]
            budget = joint_budget(skeleton, delays, read(geometry/"rehearsal.json")["completion_times_s"])
            args, kwargs = (skeleton, delays), {"time_budget": budget}
            reference = root/task["mode"]/"truth_10hz.npz"
            compare_keys = ("time_us", "p", "v", "a", "agent_ids")
        started = time.perf_counter()
        run = execution.execute(*args, **kwargs)
        meta["wall_s"] = time.perf_counter()-started
        meta["transaction_stats"] = dict(getattr(execution, "_TRANSACTION_STATS", {}))
        np.savez_compressed(out/"run.npz", **{key: run[key] for key in ("time_us", "p", "v", "a", "agent_ids", "execution_status")})
        meta["run"] = {key: value for key, value in run.items() if key not in ("time_us", "p", "v", "a", "wall_s")}
        with np.load(reference, allow_pickle=False) as expected:
            checks = {key: bool(np.array_equal(np.asarray(run[key]), expected[key])) for key in compare_keys}
            details = {}
            for key, equal in checks.items():
                if not equal:
                    actual = np.asarray(run[key]); old = expected[key]
                    details[key] = {"actual_shape": list(actual.shape), "archive_shape": list(old.shape),
                                    "actual_dtype": str(actual.dtype), "archive_dtype": str(old.dtype)}
                    if actual.shape == old.shape and actual.dtype.kind in "fiu":
                        indices = np.argwhere(actual != old)
                        if len(indices):
                            index = tuple(indices[0])
                            details[key].update(first_index=list(map(int, index)),
                                                actual=actual[index].item(), archived=old[index].item())
        meta["parity"] = {"reference": str(reference), "equal": all(checks.values()), "checks": checks, "differences": details}
    for name, module in list(sys.modules.items()):
        if name.split(".")[0] in ("task_v07", "swarm_sim", "scene_v07", "scripts"):
            file = getattr(module, "__file__", None)
            if file and not Path(file).resolve().is_relative_to(project):
                raise RuntimeError(f"Wrong project import: {name}: {file}")
    save(out/"metadata.json", meta)
    print(json.dumps({"out": str(out), "wall_s": meta["wall_s"], "parity": meta.get("parity")}), flush=True)
    return 0 if meta.get("parity", {}).get("equal", True) else 2


def launch(project, task, root, timeout=1200):
    taskfile = root/(Path(task["out"]).name+"_task.json")
    save(taskfile, task)
    env = dict(os.environ, PYTHONPATH="", PYTHONDONTWRITEBYTECODE="1")
    run = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "_worker",
                          "--project", str(project), "--task", str(taskfile)], cwd=project, env=env,
                         timeout=timeout)
    meta_path = Path(task["out"])/"metadata.json"
    meta = read(meta_path) if meta_path.exists() else {"worker_returncode": run.returncode}
    if run.returncode:
        save(root/"STOP.json", {"worker_returncode": run.returncode, "task": task, "metadata": meta})
        raise RuntimeError(f"Worker stopped ({run.returncode}); see {root/'STOP.json'}")
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("_worker", "r0", "replay", "plan"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--task", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--ids", nargs="+")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    if args.command == "_worker":
        return worker(args.project, read(args.task))
    root = args.out or DATA/("perf_fe_p0_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    root = root.resolve(); root.mkdir(parents=True, exist_ok=False)
    rows = []
    save(root/"registration.json", {"command": args.command, "project": str(args.project.resolve()),
                                   "started_utc": datetime.now(timezone.utc).isoformat()})
    if args.command in ("r0", "replay"):
        ids = args.ids or ([R0_ID] if args.command == "r0" else REPLAY_IDS)
        for sid in ids:
            sk = read(ARCHIVE/sid/"skeleton.json")
            tasks = [{"kind": "solo", "agent": agent} for agent in sorted(sk["agent_ids"])]
            tasks += [{"kind": "joint", "mode": mode} for mode in
                      (("synchronous", "sequential") if args.command == "replay" and sid == R0_ID else ("synchronous",))]
            for task in tasks:
                label = sid+"_"+task.get("agent", task.get("mode"))
                task.update(skeleton_id=sid, archive=str(ARCHIVE), out=str(root/label))
                rows.append(launch(args.project, task, root))
                save(root/"results.json", rows)
    else:
        for repeat in range(args.repeat):
            for sid in args.ids or PLAN_IDS:
                out = root/f"repeat_{repeat}_{sid}"
                task = {"kind": "plan", "skeleton_id": sid, "descriptors": str(DESCRIPTORS), "out": str(out)}
                row = launch(args.project, task, root)
                comparison = args.compare/f"repeat_{repeat}_{sid}"/sid if args.compare else (
                    root/f"repeat_0_{sid}"/sid if repeat else None)
                if comparison:
                    row["comparison"] = compare_plans(comparison, out/sid)
                rows.append(row); save(root/"results.json", rows)
                if not row.get("comparison", {}).get("equal", True):
                    save(root/"STOP.json", row)
                    raise RuntimeError("Planning equality failed")
    save(root/"summary.json", {"status": "PASS", "rows": len(rows), "results": str(root/"results.json")})
    print(f"RESULT {root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
