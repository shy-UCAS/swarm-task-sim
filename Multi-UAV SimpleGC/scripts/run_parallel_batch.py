"""v0.6 prepare / run / status / finalize; SIM_DATA_ROOT is always required."""
import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from swarm_sim.parallel_batch import (Controller, FileLock, _validate_state, batch_directory,
    finalize, integrity, load_plan, prepare, read, resolve_data_root, save_atomic)


def worker(root, attempt_id):
    from swarm_sim.parallel_worker import execute_attempt

    plan = load_plan(root)
    state = read(root / "control.json")
    _validate_state(plan, state)
    matches = [a for a in state["attempts"] if a["attempt_id"] == attempt_id]
    if len(matches) != 1:
        raise ValueError("worker requires one controller-reserved attempt")
    attempt = matches[0]
    shard = root / "shards" / f"shard_{attempt['shard_id']:02d}"
    with FileLock(shard / "writer.lock"):
        path = Path(attempt["attempt_directory"]) / "result.json"
        if attempt["status"] != "running" or path.exists():
            raise ValueError("attempt already executed; no automatic reflight")
        # A crash before result.json must never turn a manual duplicate worker
        # invocation into a second flight, even after the OS lock is released.
        marker = Path(attempt["attempt_directory"]) / "started.json"
        with marker.open("x", encoding="utf-8") as stream:
            json.dump(dict(attempt_id=attempt_id), stream)
        try:
            integrity(plan)
            result = execute_attempt(plan, attempt)
        except Exception as exc:
            result = dict(attempt_id=attempt_id, global_index=attempt["global_index"],
                          shard_id=attempt["shard_id"], retryable_pre_takeoff=False,
                          infrastructure_error=f"worker infrastructure: {type(exc).__name__}: {exc}")
        save_atomic(path, result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare", help="generate and freeze the complete task list; no SITL")
    prep.add_argument("--batch-id", required=True)
    prep.add_argument("--profile", required=True, type=Path)
    prep.add_argument("--shards", type=int, default=2)
    prep.add_argument("--max-attempts", type=int, required=True)
    prep.add_argument("--storage-bytes-per-attempt", type=int, required=True)
    prep.add_argument("--export-reserve-bytes", type=int, required=True)
    prep.add_argument("--split-salt", default="simplegc-v02")
    prep.add_argument("--binary", type=Path)
    prep.add_argument("--parameters", type=Path)
    prep.add_argument("--quality-policy", type=Path)
    for action in ("run", "status", "finalize", "_worker"):
        command = sub.add_parser(action)
        command.add_argument("--batch-id", required=True)
        if action == "run":
            command.add_argument("--resume", action="store_true",
                help="resume a manually paused batch with its existing budget/window; rule stops cannot resume")
        elif action == "_worker":
            command.add_argument("--attempt-id", required=True)
    args = parser.parse_args(argv)
    try:
        root = batch_directory(resolve_data_root(), args.batch_id)
        if args.action == "prepare":
            policy = read(args.quality_policy) if args.quality_policy else None
            plan = prepare(args.profile, args.batch_id, shards=args.shards,
                max_attempts=args.max_attempts, storage_bytes_per_attempt=args.storage_bytes_per_attempt,
                export_reserve_bytes=args.export_reserve_bytes, split_salt=args.split_salt,
                binary=args.binary, parameters=args.parameters, quality_policy=policy)
            result = dict(batch_directory=str(root), tasks=len(plan["tasks"]), shards=plan["shards"])
        elif args.action == "run":
            state = Controller(root).run(resume=args.resume)
            result = {k: state[k] for k in ("completed", "stopped_reason", "rolling")}
            result.update(paused=state.get("paused", False), status=state.get("status"))
        elif args.action == "status":
            plan = load_plan(root)
            state = read(root / "control.json")
            _validate_state(plan, state)
            result = dict(tasks=len(plan["tasks"]), attempts=len(state["attempts"]),
                registered=len(state["completion_order"]), completed=state["completed"],
                finalized=state["finalized"], paused=state.get("paused", False), status=state.get("status"),
                stopped_reason=state["stopped_reason"], rolling=state["rolling"])
        elif args.action == "finalize":
            result = finalize(root)
        else:
            result = worker(root, args.attempt_id)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(result.get("stopped_reason") or result.get("infrastructure_error")))


if __name__ == "__main__":
    raise SystemExit(main())
