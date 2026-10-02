"""Freeze v0.4 normalization and V06 generator outputs before v0.5 edits."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swarm_sim.generation import canonical_hash
from swarm_sim.mission_v3 import normalize_v3


def relative(path):
    return path.relative_to(ROOT).as_posix()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


tasks = list(sorted((ROOT / "missions/v3").glob("*.json")))
tasks += list(sorted((ROOT / "generated/recon_pilot_v04_v06_20261002/missions").glob("*.json")))
normalized = {}
for path in tasks:
    source = json.loads(path.read_text(encoding="utf-8-sig"))
    normalized[relative(path)] = canonical_hash(normalize_v3(source))

generated_root = ROOT / "generated/recon_pilot_v04_v06_20261002"
generated = {relative(path): sha256(path) for path in sorted(generated_root.rglob("*.json"))}
result = {
    "purpose": "v0.5 H02/R06 immutable v0.4 compatibility baseline",
    "normalization_count": len(normalized),
    "normalized_task_sha256": normalized,
    "v06_generated_json_count": len(generated),
    "v06_generated_file_sha256": generated,
}
target = ROOT / "tmp_v05/m0/v04_compatibility_baseline.json"
with target.open("x", encoding="utf-8") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
    stream.write("\n")
print(json.dumps({"normalization_count": len(normalized), "v06_generated_json_count": len(generated)}))
