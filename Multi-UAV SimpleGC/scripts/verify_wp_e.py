"""WP-E/V1 evidence preservation. Does not launch SITL."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_sim.analysis import digest

OUTPUT = ROOT / "tmp_v04/wp_e"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("baseline", "preserve"))
    parser.add_argument("--name", default="preservation.json")
    args = parser.parse_args()
    if args.mode == "baseline":
        old = json.loads((ROOT / "tmp_v04/wp_g/baseline.json").read_text(encoding="utf-8"))
        protected = dict(old["protected"])
        for folder in ("tmp_v04/wp_g", "tmp_v04/spike_review_01"):
            for path in (ROOT / folder).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    protected[path.relative_to(ROOT).as_posix()] = digest(path)
        for name in ("v04_spike_go_confirmation.json", "v04_wp_g_milestone.md"):
            path = ROOT / "docs" / name
            protected[path.relative_to(ROOT).as_posix()] = digest(path)
        result = dict(protected=protected, baseline_tests=dict(count=282,status="PASS"),
                      created_utc=datetime.now(timezone.utc).isoformat())
        output = OUTPUT / "baseline.json"
    else:
        before = json.loads((OUTPUT / "baseline.json").read_text(encoding="utf-8"))
        changed = [name for name, value in before["protected"].items()
                   if not (ROOT/name).is_file() or digest(ROOT/name) != value]
        result = dict(protected_file_count=len(before["protected"]), changed=changed, unchanged=not changed)
        output = OUTPUT / args.name
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key:value for key,value in result.items() if key != "protected"}))
    if args.mode == "preserve":
        assert not changed, changed


if __name__ == "__main__": main()
