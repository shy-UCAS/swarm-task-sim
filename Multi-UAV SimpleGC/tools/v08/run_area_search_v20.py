"""V8-20 single-intent CLI. Part 2 exposes parameters; production awaits parts 3/4."""
import argparse
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[2]
if str(PROJ) not in sys.path:
    sys.path.insert(0,str(PROJ))
STAGES = ("skeleton","quick","full","rerun","chord-gate","smoke")


def build_parser():
    from v08.runner.runtime_defaults import DEFAULT_WORKERS
    ap = argparse.ArgumentParser(description="V8-20 区域侦察单段")
    ap.add_argument("--stage",choices=STAGES,required=True)
    for name in ("devset","data-root","cache","out"):
        ap.add_argument("--"+name,required=True)
    ap.add_argument("--workers",type=int,default=DEFAULT_WORKERS)
    ap.add_argument("--keys")
    ap.add_argument("--compare-to")
    ap.add_argument("--contract-keys", help="smoke only: registered oNN_dN keys")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.stage == "smoke":
        import re
        from v08.runner.monitoring import guard_path,load_entries
        from v08.runner.area_search_report import smoke_geometry
        data=Path(args.data_root)
        cache=guard_path(args.cache,label="缓存",data_root=data)
        out=guard_path(args.out,label="输出",data_root=data,must_not_exist=True)
        if args.workers != 1:
            raise ValueError("maximum-query smoke is single process")
        keys=((1,1),(34,3),(17,1))
        if args.contract_keys:
            values=[re.fullmatch(r"o(\d+)_d(\d+)",x.strip()) for x in args.contract_keys.split(",")]
            if not all(values):
                raise ValueError("invalid registered smoke keys")
            keys=tuple((int(m[1]),int(m[2])) for m in values)
        entries=load_entries(args.devset)
        if any(o not in {int(e["order"]) for e in entries} or not 0<=d<5 for o,d in keys):
            raise ValueError("smoke key outside registered public draws")
        out.mkdir(parents=True,exist_ok=False)
        summary=smoke_geometry(entries,keys=keys,data_root=data,cache_dir=cache,out_dir=out)
        return 2 if summary["checkpoint"]["triggered"] else 0
    raise NotImplementedError("V8-20 production execution requires completed parts 3/4")


if __name__ == "__main__":
    raise SystemExit(main())
