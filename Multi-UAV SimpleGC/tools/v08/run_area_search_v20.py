"""V8-20 CLI; all production paths use the original 20-attempt native backend."""
import argparse
import json
import os
import re
import sys
from pathlib import Path

PROJ=Path(__file__).resolve().parents[2]
if str(PROJ) not in sys.path:sys.path.insert(0,str(PROJ))
QUICK_KEYS=tuple((order,draw) for order in (*range(1,10),11) for draw in (0,1))


def build_parser():
    from v08.runner.runtime_defaults import DEFAULT_WORKERS
    ap=argparse.ArgumentParser(description="V8-20 区域侦察单段")
    ap.add_argument("--stage",required=True,choices=("smoke","prewarm","skeleton","quick","full","rerun","chord-gate"))
    for key in ("devset","data-root","cache","out"):
        ap.add_argument("--"+key,required=True)
    ap.add_argument("--workers",type=int,default=DEFAULT_WORKERS)
    ap.add_argument("--keys")
    ap.add_argument("--compare-to")
    ap.add_argument("--contract-keys",help="geometry smoke only: registered oNN_dN keys")
    ap.add_argument("--prewarm-from",help="combined area-search prewarm.json; separates the 45/30 minute clocks")
    return ap


def status_code(summary):
    if summary.get("retained_p0_violations"):return 4
    if not summary.get("complete",True) or not summary.get("diversity_complete",True):return 3
    if (summary.get("checkpoint") or {}).get("triggered"):return 2
    return 0


def main(argv=None):
    args=build_parser().parse_args(argv)
    from v08.runner import joint_intent as JI,area_search_report as R
    from v08.runner.monitoring import PathRejected,guard_path,load_entries,write_json
    from v08.motion.area_search_geometry import SECTOR_RULE
    try:
        if not all(os.environ.get(k)=="1" for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS")):
            raise ValueError("all four numerical thread variables must be 1")
        data=Path(args.data_root);cache=guard_path(args.cache,label="缓存",data_root=data)
        out=guard_path(args.out,label="输出",data_root=data,must_not_exist=True)
        if args.workers<1:raise ValueError("positive workers required")
        entries=load_entries(args.devset)
        pw=None if args.prewarm_from is None else json.loads(Path(args.prewarm_from).read_text(encoding="utf-8"))
        if pw is not None:
            pairs={(int(r["order"]),r["family_id"]) for r in pw["rows"]}
            if (pw.get("intent")!="area_search" or pw.get("sector_rule")!=SECTOR_RULE or not pw.get("complete") or pw["wall_s"]>2700.
                or pairs!={(int(e["order"]),e["family_id"]) for e in entries}
                or pw.get("cache_root")!=str(cache.resolve()) or pw.get("data_root")!=str(data.resolve())):
                raise ValueError("combined prewarm identity/checkpoint mismatch")
        if args.stage=="prewarm":
            pw=R.prewarm_all(entries,data_root=data,cache_dir=cache,workers=args.workers,out_dir=out)
            summary={"stage":"prewarm","intent":"area_search","complete":pw["complete"],"workers":args.workers,
                "wall_s":pw["wall_s"],"checkpoint":{"triggered":["prewarm_wall"] if pw["hard_stop"] or pw["wall_s"]>2700. else []}}
            write_json(out/"summary.json",summary,indent=1)
            print(json.dumps(summary),flush=True);return status_code(summary)
        if args.stage=="smoke":
            if args.workers!=1:raise ValueError("geometry smoke must use one process")
            keys=((1,1),(34,3),(17,1))
            if args.contract_keys:
                values=[re.fullmatch(r"o(\d+)_d(\d+)",x.strip()) for x in args.contract_keys.split(",")]
                if not all(values):raise ValueError("invalid registered smoke keys")
                keys=tuple((int(m[1]),int(m[2])) for m in values)
            if any(o not in {int(e["order"]) for e in entries} or not 0<=d<5 for o,d in keys):
                raise ValueError("smoke key outside registered public draws")
            out.mkdir(parents=True,exist_ok=False)
            summary=R.smoke_geometry(entries,keys=keys,data_root=data,cache_dir=cache,out_dir=out)
            return status_code(summary)
        if args.contract_keys:raise ValueError("--contract-keys is geometry smoke only")
        if args.stage=="chord-gate":
            out.mkdir(parents=True,exist_ok=False)
            summary=R.chord_gate(entries,data_root=data,cache_dir=cache,out_dir=out)
            return status_code(summary)
        if args.stage=="rerun":
            if not args.keys or not args.compare_to:raise ValueError("rerun requires --keys and --compare-to")
            out.mkdir(parents=True,exist_ok=False)
            summary=JI.rerun_stage(entries,data_root=data,cache_dir=cache,out_dir=out,keys_path=args.keys,compare_to=args.compare_to,intent="area_search")
            return 0 if summary["all_equal"] else 4
        if pw is None:
            pw=R.prewarm_all(entries,data_root=data,cache_dir=cache,workers=args.workers,out_dir=out.with_name(out.name+"_prewarm"))
            if not pw["complete"] or pw["wall_s"]>2700.:return 2
        if args.stage=="skeleton":
            summary=R.run_skeleton_batch(entries,data_root=data,cache_dir=cache,out_dir=out,workers=args.workers,prewarm_doc=pw)
        else:
            out.mkdir(parents=True,exist_ok=False)
            if args.stage=="quick":
                write_json(out/"selection.json",{"keys":QUICK_KEYS,"rule":"registered fixed20; no exclusions"},indent=1)
                summary=JI.run_selected(entries,QUICK_KEYS,intent="area_search",data_root=data,cache_dir=cache,out_dir=out,
                    workers=args.workers,stage="quick",prewarm_doc=pw)
            else:
                summary=JI.full_stage(entries,data_root=data,cache_dir=cache,out_dir=out,workers=args.workers,intent="area_search",prewarm_doc=pw)
        code=status_code(summary)
        if args.stage in ("quick","full") and summary.get("complete"):
            verification={"main":R.verify_saved_outputs(out,entries,data,cache)}
            if args.stage=="full":verification["diversity"]=R.verify_saved_outputs(out/"diversity",entries,data,cache)
            write_json(out/"disk_verification.json",verification,indent=1)
            if any(v["p0_violations"] for v in verification.values()):code=4
        print(json.dumps({"stage":args.stage,"complete":summary.get("complete"),"checkpoint":summary.get("checkpoint"),"exit_code":code}),flush=True)
        return code
    except (PathRejected,ValueError) as error:
        print(str(error),file=sys.stderr);return 3


if __name__=="__main__":
    raise SystemExit(main())
