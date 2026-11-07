"""V8-18 冻结/输入/基线快照（只读）。沿用 V8-17 snapshot（其内部沿用 V8-16 的五项与细粒度不变量），另加：
整个 monitoring_turn.py 的 SHA256（指令 0.1-1，只可调用）、V8-17 突入关键函数体、V8-17 预置测试 SHA256，
以及 --baseline 时 V8-17 full_r1 全部文件。用法：python -B snapshot.py <out.json> [--baseline]"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V17 = HERE.parent / "V8-17" / "snapshot.py"
spec = importlib.util.spec_from_file_location("snap17", V17)
snap17 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snap17)
snap16 = snap17.snap16

IBASE = snap16.ROOT / "_handoff" / "2026-11-06_V8-17_intrusion" / "run" / "out" / "full" / "full_r1"
EXTRA_FINE = [("v08/motion/intents/intrusion.py", "finish_candidate"),
              ("v08/motion/intents/intrusion.py", "propose_and_build"),
              ("v08/motion/intrusion_chords.py", "assess_cell"),
              ("v08/motion/optimize_checks.py", "check_intrusion"),
              ("v08/motion/nominal_checks.py", "screen_intrusion_member"),
              ("v08/motion/intents/monitoring.py", "_turns_v14"),
              ("v08/motion/intents/monitoring.py", "_turn_ranges_v14"),
              ("v08/motion/intents/monitoring.py", "teardrop_primitives"),
              ("v08/motion/intents/monitoring.py", "_turn_arcs")]
WHOLE = ["v08/motion/monitoring_turn.py"]


def main():
    out = Path(sys.argv[1])
    snap17.EXTRA_FINE = list(snap17.EXTRA_FINE) + EXTRA_FINE
    snap17.main()                                    # 写 out（V8-17 同一格式与内容）
    doc = json.loads(out.read_text(encoding="utf-8"))
    doc["v17_preset_tests"] = {k: v for k, v in doc["modules"].items() if k.startswith("tests/v08/V8-17/")}
    doc["whole_frozen_files"] = {rel: snap16.sha(snap16.PROJ / rel) for rel in WHOLE}
    if "--baseline" in sys.argv:
        doc["intrusion_baseline_root"] = str(IBASE)
        doc["intrusion_baseline"] = {p.relative_to(IBASE).as_posix(): snap16.ident(p)
                                     for p in sorted(IBASE.rglob("*")) if p.is_file()}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"v17_tests={len(doc['v17_preset_tests'])} whole={doc['whole_frozen_files']} "
          f"intrusion_baseline_files={len(doc.get('intrusion_baseline', {}))} "
          f"fine={sum(v is not None for v in doc['fine_invariants'].values())}/{len(doc['fine_invariants'])}")


if __name__ == "__main__":
    main()
