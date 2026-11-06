"""V8-17 冻结/输入/基线快照（只读）。沿用 V8-16 snapshot 工具（导入其 main 的同一套五项与细粒度不变量），
另加：V8-16 过境关键函数与 V8-16 预置测试 SHA256、full_transit_r2 基线全部文件。
用法：python -B snapshot.py <out.json> [--baseline]"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V16 = HERE.parent / "V8-16" / "snapshot.py"
spec = importlib.util.spec_from_file_location("snap16", V16)
snap16 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snap16)

TBASE = snap16.ROOT / "_handoff" / "2026-11-05_V8-16_transit" / "run" / "out" / "full_transit_r2"
EXTRA_FINE = [("v08/motion/optimize_checks.py", "check_transit"),
              ("v08/motion/nominal_checks.py", "screen_transit_member"),
              ("v08/motion/transit_numeric.py", "curve_lp"),
              ("v08/motion/transit_numeric.py", "exact_curve_audit"),
              ("v08/motion/formation.py", "derive_members"),
              ("v08/motion/shared_routes.py", "route_to_slot"),
              ("v08/motion/skeleton.py", "references_from_skeleton"),
              ("v08/motion/connect.py", "crossing_analysis")]


def main():
    out = Path(sys.argv[1])
    snap16.FINE = list(snap16.FINE) + EXTRA_FINE
    snap16.main()                                   # 写 out（V8-16 同一格式与内容）
    doc = json.loads(out.read_text(encoding="utf-8"))
    doc["v16_preset_tests"] = {k: v for k, v in doc["modules"].items()
                               if k.startswith("tests/v08/V8-16/")}
    if "--baseline" in sys.argv:
        doc["transit_baseline_root"] = str(TBASE)
        doc["transit_baseline"] = {p.relative_to(TBASE).as_posix(): snap16.ident(p)
                                   for p in sorted(TBASE.rglob("*")) if p.is_file()}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"v16_tests={len(doc['v16_preset_tests'])} transit_baseline_files={len(doc.get('transit_baseline', {}))} "
          f"fine={sum(v is not None for v in doc['fine_invariants'].values())}/{len(doc['fine_invariants'])}")


if __name__ == "__main__":
    main()
