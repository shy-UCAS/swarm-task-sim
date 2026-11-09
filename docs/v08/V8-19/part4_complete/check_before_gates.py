import ast
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
DIAG = ROOT / "run/diagnostics"
CODE = REPO / "Multi-UAV SimpleGC"
read = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
manifest = read(REPO / "docs/v08/V8-19/manifest.json")
totals = {}
for folder, index, expected in (("part4_unit_tests_r2", "summary.json", 33),
                                ("part4_old_tests_r2", "results.json", 134)):
    doc = read(DIAG / folder / index)
    assert doc["all_zero_exit"]
    count = 0
    for row in doc["rows"]:
        log = (DIAG / folder / row["log"]).read_text(encoding="utf-8")
        assert row["exit_code"] == 0 and "skipped" not in log, row
        count += int(re.search(r"Ran (\d+) tests? in", log)[1])
    assert count == expected, (folder, count)
    totals[folder] = {"passed": count, "files": len(doc["rows"]), "wall_s": doc["wall_s"]}
for path, expected in manifest["frozen_files"].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
for row in manifest["frozen_symbols"]:
    text = Path(row["path"]).read_text(encoding="utf-8")
    node = next(n for n in ast.parse(text).body if getattr(n, "name", None) == row["qualname"])
    assert hashlib.sha256(ast.get_source_segment(text, node).encode()).hexdigest() == row["sha256"], row
for name, row in manifest["presets"].items():
    assert hashlib.sha256((CODE / "tests/v08/V8-19" / name).read_bytes()).hexdigest() == row["sha256"], name
for path, expected in manifest["preserved_owner_files"].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
doc = {"complete": True, "tests": totals, "frozen_files_equal": len(manifest["frozen_files"]),
       "frozen_symbols_equal": len(manifest["frozen_symbols"]), "presets_equal": True,
       "owners_equal": True, "checked_utc": datetime.now(timezone.utc).isoformat()}
(DIAG / "part4_before_gates.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(doc))
