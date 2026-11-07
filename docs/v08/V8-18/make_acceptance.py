"""V8-18：生成预置测试 9.3 所需的合同目录外索引 acceptance.json（只读；路径不写进任何合同）。
frozen_files 取第 1 部分快照 snapshot_part1.json 中登记的冻结范围（task_v07/、v08/criteria/、v08/sim/、configs/）与整个
monitoring_turn.py 的 SHA256（登记值，不是现算值）。
用法：python -B make_acceptance.py <out.json> --quick <快批根> --full <全量根> --rerun <复跑根>"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
PROJ = ROOT / "Simulation-v08" / "Multi-UAV SimpleGC"
RUN = ROOT / "_handoff" / "2026-11-06_V8-18_feint" / "run"
FROZEN_PREFIXES = ("task_v07/", "v08/criteria/", "v08/sim/", "configs/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--quick", required=True)
    ap.add_argument("--full", required=True)
    ap.add_argument("--rerun", required=True)
    a = ap.parse_args()
    man = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    snap = json.loads((HERE / "snapshot_part1.json").read_text(encoding="utf-8"))
    frozen = {str(PROJ / rel): h for rel, h in sorted(snap["modules"].items()) if rel.startswith(FROZEN_PREFIXES)}
    for rel, h in snap["whole_frozen_files"].items():
        frozen[str(PROJ / rel)] = h
    base = {"monitoring": man["baselines"]["monitor_full_v14c"]["path"],
            "transit": man["baselines"]["transit_full_transit_r2"]["path"],
            "intrusion": man["baselines"]["intrusion_full_r1"]["path"]}
    gates = []
    for phase in (2, 4):
        for intent in ("monitoring", "transit", "intrusion"):
            rep = RUN / "out" / f"gates_{phase}" / intent
            gates.append({"intent": intent, "phase": phase, "baseline": base[intent],
                          "repeat": str(rep / "run" if intent == "monitoring" else rep)})
    doc = {"devset": man["devset"]["path"], "data_root": man["data_root"], "cache": str(RUN / "cache"),
           "gates": gates, "outputs": [{"stage": "quick", "path": a.quick}, {"stage": "full", "path": a.full}],
           "rerun": a.rerun, "frozen_files": frozen}
    Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"gates={len(gates)} frozen={len(frozen)}")


if __name__ == "__main__":
    main()
