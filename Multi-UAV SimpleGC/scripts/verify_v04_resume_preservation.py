"""Protect prior WP evidence and the failed V01 without rewriting either."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"tmp_v04/wp_v_resume_20261002"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("baseline","preserve"))
    parser.add_argument("--name",default="preservation.json")
    args=parser.parse_args()
    if args.mode=="baseline":
        old=json.loads((ROOT/"tmp_v04/wp_e/baseline.json").read_text(encoding="utf-8"))
        protected=dict(old["protected"])
        for folder in ("tmp_v04/wp_e","tmp_v04/wp_v","verification/v04_v1_20261001"):
            for path in (ROOT/folder).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    protected[path.relative_to(ROOT).as_posix()]=sha(path)
        for name in ("v04_wp_e_milestone.md","v04_v1_milestone.md"):
            path=ROOT/"docs"/name
            protected[path.relative_to(ROOT).as_posix()]=sha(path)
        result=dict(protected=protected,created_utc=datetime.now(timezone.utc).isoformat())
        output=OUT/"baseline.json"
    else:
        baseline=json.loads((OUT/"baseline.json").read_text(encoding="utf-8"))
        changed=[name for name,value in baseline["protected"].items() if not (ROOT/name).is_file() or sha(ROOT/name)!=value]
        result=dict(protected_file_count=len(baseline["protected"]),unchanged=not changed,changed=changed)
        output=OUT/args.name
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x",encoding="utf-8") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!="protected"}))
    if args.mode=="preserve" and changed:
        raise RuntimeError("Protected evidence changed")


if __name__=="__main__": main()
