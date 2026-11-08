"""从独立磁盘核验的原始JSON派生汇总；最小间距只在非None数值上取min。"""
import json
from pathlib import Path

ROOT = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-06_V8-18_feint\run")
out = {}
for stage in ("quick", "full"):
    doc = json.loads((ROOT / "diagnostics" / f"{stage}_disk_validation_r1.json").read_text(encoding="utf-8"))
    records = doc["results"]
    members = [m for r in records for m in r["members"].values()]
    separation = [r for r in records if r.get("min_separation_m") is not None]
    lowest = min(separation, key=lambda r: float(r["min_separation_m"]))
    out[stage] = {"checked": len(records), "retained": doc["retained"], "members": len(members),
        "min_separation_m": float(lowest["min_separation_m"]), "min_separation_key": lowest["contract_id"],
        "min_separation_scope": lowest["scope"],
        "min_protected_sdf_m": min(float(m["min_protected_sdf_m"]) for m in members),
        "p0": doc["p0_contracts"], "incomplete": doc["incomplete"],
        "payload_violations": len(doc["payload_violations"])}
out["aggregation"] = "Python min over raw JSON non-None numeric fields; no changes to trajectories or acceptance."
path = ROOT / "diagnostics" / "validation_metrics_r1.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(json.dumps(out, ensure_ascii=False))
