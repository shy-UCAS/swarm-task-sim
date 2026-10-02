"""Hash-protect all previous milestones and runs; never launch a simulator."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from verify_v04_resume_preservation import sha

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tmp_v04/ac4_v2_20261002"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("baseline", "preserve"))
    parser.add_argument("--name", default="preservation.json")
    args = parser.parse_args()
    if args.mode == "baseline":
        old = json.loads((ROOT / "tmp_v04/wp_v_resume_20261002/baseline.json").read_text(encoding="utf-8"))
        protected = dict(old["protected"])
        for folder in ("tmp_v04/wp_v_resume_20261002", "verification/v04_v1_resume_20261002"):
            for path in (ROOT / folder).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    protected[path.relative_to(ROOT).as_posix()] = sha(path)
        for name in ("v04_v1_resume_milestone.md", "v04_v01_cancellation_review.md", "wp_s_parameter_comparison_v2.md"):
            path = ROOT / "docs" / name
            protected[path.relative_to(ROOT).as_posix()] = sha(path)
        result = dict(created_utc=datetime.now(timezone.utc).isoformat(), protected=protected)
        output = OUT / "baseline.json"
    else:
        before = json.loads((OUT / "baseline.json").read_text(encoding="utf-8"))
        changed = [name for name, value in before["protected"].items()
                   if not (ROOT / name).is_file() or sha(ROOT / name) != value]
        result = dict(protected_file_count=len(before["protected"]), unchanged=not changed, changed=changed)
        output = OUT / args.name
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != "protected"}))
    if args.mode == "preserve" and changed:
        raise RuntimeError("Historical evidence changed")


if __name__ == "__main__":
    main()
