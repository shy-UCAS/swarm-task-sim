"""Verify the M0 protected-file hashes without touching protected inputs."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
baseline = json.loads((ROOT / "tmp_v05/m0/protected_baseline.json").read_text(encoding="utf-8"))
missing, changed = [], []
for name, expected in baseline["protected"].items():
    path = Path(name)
    if not path.is_file():
        missing.append(name)
        continue
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        changed.append(name)
result = dict(baseline_version=baseline["version"], protected_file_count=len(baseline["protected"]),
              missing=missing, changed=changed, **{"pass": not missing and not changed})
target = ROOT / "tmp_v05/h/protected_check.json"
with target.open("x", encoding="utf-8") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(dict(protected_file_count=result["protected_file_count"],
                      missing_count=len(missing), changed_count=len(changed),
                      passed=result["pass"], output=str(target)), ensure_ascii=False))
