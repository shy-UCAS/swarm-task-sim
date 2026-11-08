"""V8-19 extends the V8-18 read-only snapshot, adding frozen symbols and the fourth baseline."""
import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("v19_previous_snapshot", HERE.parent / "V8-18/snapshot.py")
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
REPO = old.snap16.REPO
PROJ = old.snap16.PROJ
ROOT = old.snap16.ROOT
FROZEN_SYMBOLS = (("v08/motion/nominal.py", "member_nominal"),
                  ("v08/motion/skeleton.py", "NominalPVA"),
                  ("v08/motion/optimize.py", "Prepared"),
                  ("v08/motion/optimize.py", "_eliminate"),
                  ("v08/motion/optimize.py", "solve_joint"))


def main():
    out = Path(sys.argv[1])
    if out.exists():
        raise FileExistsError(out)
    old.main()
    doc = json.loads(out.read_text(encoding="utf-8"))
    symbols = []
    for rel, name in FROZEN_SYMBOLS:
        path = PROJ / rel
        text = path.read_text(encoding="utf-8")
        node = next(node for node in ast.parse(text).body if getattr(node, "name", None) == name)
        symbols.append({"path": str(path), "qualname": name,
                        "sha256": hashlib.sha256(ast.get_source_segment(text, node).encode("utf-8")).hexdigest()})
    doc["frozen_symbols"] = symbols
    doc["v18_preset_tests"] = {key: value for key, value in doc["modules"].items() if key.startswith("tests/v08/V8-18/")}
    doc["preserved_owner_files"] = {str(REPO / f"docs/v08/{v}/owner_rerun.json"): old.snap16.sha(REPO / f"docs/v08/{v}/owner_rerun.json") for v in ("V8-17", "V8-18")}
    cache = ROOT / "_handoff/2026-11-06_V8-18_feint/run/cache/feint_v18"
    doc["preserved_feint_existence_cache"] = {path.relative_to(cache).as_posix(): old.snap16.ident(path) for path in sorted(cache.rglob("*")) if path.is_file()}
    if "--baseline" in sys.argv:
        root = ROOT / "_handoff/2026-11-06_V8-18_feint/run/out/full_lazy_r1"
        doc["feint_baseline_root"] = str(root)
        doc["feint_baseline"] = {path.relative_to(root).as_posix(): old.snap16.ident(path) for path in sorted(root.rglob("*")) if path.is_file()}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"frozen_symbols": len(symbols), "feint_baseline_files": len(doc.get("feint_baseline", {})), "preserved_feint_cache_files": len(doc["preserved_feint_existence_cache"]) }))


if __name__ == "__main__":
    main()
