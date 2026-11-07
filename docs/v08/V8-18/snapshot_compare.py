"""V8-18：比较两份快照的冻结范围（只读）。用法：python -B snapshot_compare.py <a.json> <b.json> <out.json>"""
import json, sys
from pathlib import Path
FROZEN = ("task_v07/", "v08/criteria/", "v08/sim/", "configs/")
a, b = (json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[1:3])
ma, mb = a["modules"], b["modules"]
changed = sorted(k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k))
doc = {"inputs_equal": a["inputs"] == b["inputs"], "v07_dirs_equal": a["v07_dirs"] == b["v07_dirs"],
       "frozen_worktrees_equal": a["frozen_worktrees"] == b["frozen_worktrees"],
       "fine_invariants_equal": {k: a["fine_invariants"].get(k) == b["fine_invariants"].get(k) for k in a["fine_invariants"]},
       "whole_frozen_files_equal": a["whole_frozen_files"] == b["whole_frozen_files"],
       "frozen_modules_changed": [k for k in changed if k.startswith(FROZEN)],
       "old_preset_tests_changed": [k for k in changed if k.startswith("tests/v08/") and "/V8-18/" not in k],
       "modules_changed": changed}
for k in ("intrusion_baseline", "baseline", "transit_baseline"):
    if k in a and k in b:
        doc[k + "_equal"] = a[k] == b[k]
doc["all_frozen_ok"] = (doc["inputs_equal"] and doc["v07_dirs_equal"] and doc["frozen_worktrees_equal"]
                        and all(doc["fine_invariants_equal"].values()) and doc["whole_frozen_files_equal"]
                        and not doc["frozen_modules_changed"] and not doc["old_preset_tests_changed"]
                        and all(doc.get(k + "_equal", True) for k in ("intrusion_baseline", "baseline", "transit_baseline")))
Path(sys.argv[3]).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in doc.items() if k not in ("fine_invariants_equal",)}, ensure_ascii=False))
print("fine all equal:", all(doc["fine_invariants_equal"].values()))
