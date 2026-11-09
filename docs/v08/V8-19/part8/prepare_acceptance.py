"""Create the preset's descriptor only after all required artifacts exist."""
import json
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
RUN = ROOT / "run"
DOC = REPO / "docs/v08/V8-19"
read = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
manifest = read(DOC / "manifest.json")
gates = []
for phase in (2, 4):
    for intent in ("monitoring", "transit", "intrusion", "feint"):
        row = read(RUN / f"diagnostics/gates_{phase}_r1" / intent / "comparison.json")
        assert row["all_equal"] and row["equal_count"] == 20 and row["exclusions"] == []
        gates.append({k: row[k] for k in ("intent", "phase", "baseline", "repeat")})
for stage in ("quick", "full"):
    folder = RUN / f"out/{stage}_r1"
    summary = read(folder / "summary.json")
    assert summary["complete"] and not summary["checkpoint"]["triggered"]
    assert all(v["passed"] and not v["p0_violations"] for v in read(folder / "disk_verification.json").values())
assert read(RUN / "out/rerun_r1/reproduction.json")["all_equal"]
doc = {"devset": str(REPO / "docs/v08/V8-03/devset_v08.json"), "data_root": str(BASE / "SwarmData"),
       "cache": str(RUN / "cache"), "gates": gates,
       "outputs": [{"stage": s, "path": str(RUN / f"out/{s}_r1")} for s in ("quick", "full")],
       "rerun": str(RUN / "out/rerun_r1"), "frozen_files": manifest["frozen_files"], "frozen_symbols": manifest["frozen_symbols"]}
out = DOC / "acceptance.json"
assert not out.exists()
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"gates": len(gates), "outputs": 2, "rerun_keys": 5, "descriptor": str(out)}))
