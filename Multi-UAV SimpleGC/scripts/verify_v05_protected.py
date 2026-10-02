"""Verify the immutable v0.4 evidence snapshot before and after v0.5 runs."""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tmp_v05/m0/protected_baseline.json"


def sha256(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify_baseline(path=BASELINE):
    baseline = json.loads(Path(path).read_text(encoding="utf-8"))
    protected = baseline["protected"]
    if len(protected) != baseline["protected_file_count"]:
        raise ValueError("protected baseline count is inconsistent")
    missing, changed = [], []
    for name, expected in protected.items():
        item = Path(name)
        if not item.is_file():
            missing.append(name)
        elif sha256(item) != expected:
            changed.append(name)
    return dict(version=baseline["version"], baseline_git_head=baseline["git_head"],
                protected_file_count=len(protected), missing=missing, changed=changed,
                unchanged=not (missing or changed))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--output", type=Path, help="New JSON result path; never overwrite")
    args = parser.parse_args()
    result = verify_baseline(args.baseline)
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
