"""Read-only protection of all pre-V06 evidence, including the original project."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_sim.analysis import digest
from scripts.verify_ac4_v2 import write_new

OUT = ROOT / "tmp_v04/v06_20261002"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("baseline", "check"))
    parser.add_argument("--name", default="preservation.json")
    args = parser.parse_args()
    if args.mode == "baseline":
        files = set()
        for folder in ("runs", "datasets", "generated", "verification", "audit_v04", "docs", "tmp_v04"):
            files.update(p for p in (ROOT / folder).rglob("*") if p.is_file()
                         and "__pycache__" not in p.parts and OUT not in p.parents)
        files.update(p for p in (ROOT.parent / "SimpleGC").rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and ".git" not in p.parts)
        files.update((ROOT / "generation_profiles").glob("*.json"))
        protected = {str(p.resolve()): digest(p) for p in sorted(files)}
        write_new(OUT / "baseline.json", dict(created_utc=datetime.now(timezone.utc).isoformat(), protected=protected))
        print(json.dumps(dict(protected_file_count=len(protected))))
    else:
        protected = json.loads((OUT / "baseline.json").read_text(encoding="utf-8"))["protected"]
        changed = [name for name, sha in protected.items() if not Path(name).is_file() or digest(name) != sha]
        write_new(OUT / args.name, dict(protected_file_count=len(protected), unchanged=not changed, changed=changed))
        print(json.dumps(dict(protected_file_count=len(protected), unchanged=not changed, changed=changed)))
        return int(bool(changed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
