"""Thin V8-19 CLI using the shared native runners and their single 20-attempt budget."""
import argparse
import json
import os
import re
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[2]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

INTENT = "close_observation"
SMOKE_KEYS = ((1, 0), (2, 0), (11, 0), (1, 1))
QUICK_KEYS = tuple((o, d) for o in (*range(1, 10), 11) for d in (0, 1))


def build_parser():
    from v08.runner.runtime_defaults import DEFAULT_WORKERS
    parser = argparse.ArgumentParser(description="V8-19 抵近观察单段")
    parser.add_argument("--stage", required=True, choices=("smoke", "prewarm", "skeleton", "quick", "full", "rerun"))
    for key in ("devset", "data-root", "cache", "out"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--keys")
    parser.add_argument("--compare-to")
    parser.add_argument("--prewarm-from", help="existing native prewarm.json; allows separate 45-minute prewarm checkpoint")
    parser.add_argument("--contract-keys", help="smoke only: comma-separated oNN_dN keys; default fixed four keys")
    return parser


def status_code(summary):
    if summary.get("retained_p0_violations"):
        return 4
    if not summary.get("complete", True) or not summary.get("diversity_complete", True):
        return 3
    if (summary.get("checkpoint") or {}).get("triggered"):
        return 2
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    from v08.runner import joint_intent as JI
    from v08.runner.close_observation_report import verify_saved_outputs
    from v08.runner.monitoring import PathRejected, guard_path, load_entries, write_json
    try:
        if not all(os.environ.get(k) == "1" for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")):
            raise ValueError("all four thread variables must be set to 1")
        data_root = Path(args.data_root)
        cache = guard_path(args.cache, label="缓存", data_root=data_root)
        out = guard_path(args.out, label="输出", data_root=data_root, must_not_exist=True)
        if args.workers < 1:
            raise ValueError("workers must be positive")
        pw = None if args.prewarm_from is None else json.loads(Path(args.prewarm_from).read_text(encoding="utf-8"))
        entries = load_entries(args.devset)
        out.mkdir(parents=True, exist_ok=False)
        if pw is not None and (pw.get("intent") != INTENT or pw["families"] != len(entries) or pw["wall_s"] > 2700.):
            write_json(out / "summary.json", {"complete": False, "checkpoint": {"triggered": ["prewarm_wall_or_identity"]}}, indent=1)
            return 2
        if args.stage == "prewarm":
            pw = JI.prewarm_all(entries, data_root=data_root, cache_dir=cache, workers=args.workers, intent=INTENT)
            pw["intent"] = INTENT
            write_json(out / "prewarm.json", pw, indent=1)
            summary = {"stage": "prewarm", "intent": INTENT, "complete": pw["families"] == len(entries),
                       "wall_s": pw["wall_s"], "workers": args.workers, "checkpoint": {"triggered": ["prewarm_wall"] if pw["wall_s"] > 2700. else []}}
            write_json(out / "summary.json", summary, indent=1)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            return status_code(summary)
        if args.stage == "rerun":
            if not args.keys or not args.compare_to:
                raise ValueError("rerun requires --keys and --compare-to")
            summary = JI.rerun_stage(entries, data_root=data_root, cache_dir=cache, out_dir=out, keys_path=args.keys,
                                     compare_to=args.compare_to, intent=INTENT)
            return 0 if summary["all_equal"] else 4
        if args.stage == "skeleton":
            from v08.runner.skeleton_transit import run_intent_skeleton_batch
            summary = run_intent_skeleton_batch(entries, intent=INTENT, data_root=data_root, cache_dir=cache,
                                                out_dir=out, workers=args.workers, prewarm_doc=pw)
        elif args.stage == "full":
            summary = JI.full_stage(entries, data_root=data_root, cache_dir=cache, out_dir=out, workers=args.workers,
                                    intent=INTENT, prewarm_doc=pw)
        else:
            keys = SMOKE_KEYS if args.stage == "smoke" else QUICK_KEYS
            if args.contract_keys:
                if args.stage != "smoke":
                    raise ValueError("--contract-keys is allowed only for smoke")
                matches = [re.fullmatch(r"o(\d+)_d(\d+)", x.strip()) for x in args.contract_keys.split(",")]
                if not all(matches):
                    raise ValueError("invalid smoke key")
                keys = tuple((int(m[1]), int(m[2])) for m in matches)
            write_json(out / "selection.json", {"keys": keys, "rule": "V8-19 preregistered keys; smoke explicit keys are diagnostic"}, indent=1)
            summary = JI.run_selected(entries, keys, intent=INTENT, data_root=data_root, cache_dir=cache, out_dir=out,
                                      workers=1 if args.stage == "smoke" else args.workers, stage=args.stage,
                                      prewarm=args.stage != "smoke", prewarm_doc=pw)
        code = status_code(summary)
        if args.stage in ("smoke", "quick", "full") and code != 4 and summary.get("complete"):
            verifications = {"main": verify_saved_outputs(out, entries, data_root, cache)}
            if args.stage == "full":
                verifications["diversity"] = verify_saved_outputs(out / "diversity", entries, data_root, cache)
            write_json(out / "disk_verification.json", verifications, indent=1)
            if any(v["p0_violations"] for v in verifications.values()):
                code = 4
        print(json.dumps({"stage": args.stage, "complete": summary.get("complete"), "checkpoint": summary.get("checkpoint"), "exit_code": code}, ensure_ascii=False), flush=True)
        return code
    except (PathRejected, ValueError, KeyError) as exc:
        print(f"V8-19 error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
