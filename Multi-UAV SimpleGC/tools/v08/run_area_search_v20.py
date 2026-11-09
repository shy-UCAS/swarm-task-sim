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
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    raise NotImplementedError("V8-20 production execution requires completed parts 3/4")


if __name__ == "__main__":
    main()
