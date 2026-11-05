"""第 6 部分只骨架批次结果分析（只读 out/skeleton 产物）。"""
import json, sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
from statistics import median

out = Path(sys.argv[1])
recs = json.loads((out / "records.json").read_text(encoding="utf-8"))
summ = json.loads((out / "summary.json").read_text(encoding="utf-8"))
att = [json.loads(l) for l in (out / "attempts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
chk = summ["checkpoint"]
P = print
P("complete", chk["complete"], "triggered", chk["triggered"])
m = chk["metrics"]
P("successes", m["successes"], "/", m["contracts"], m.get("success_rate_fraction"))
P("success attempts median", m["success_attempts_median"])
P("shape audit", m["shape_audit_failed_attempts"], "/", m["skeleton_attempts_total"], m.get("shape_audit_rate"))
for ax in ("group", "facility", "speed"):
    P(ax, json.dumps(m[f"{ax}_bins"], ensure_ascii=False))
# 成功合同尝试次数分布
sa = Counter(r["attempts"] for r in recs if r["success"])
P("success attempts hist", sorted(sa.items()))
# 失败阶段（attempt 级）
P("attempt stages", Counter(a["stage"] for a in att).most_common())
P("final failure codes", Counter((r.get("failure") or {}).get("code") for r in recs if not r["success"]).most_common())
P("shape reasons", summ["shape_audit_reasons"])
# 曲率失败：参考最大曲率半径 vs 车道半跨 D
rows = []
for a in att:
    if a.get("shape_audit_failed") and a.get("shape_audit_kappa") and a.get("certificate"):
        k = a["shape_audit_kappa"]
        kmax = max(k["kpos"], -k["kneg"])
        D = a["certificate"]["half_span_m"]
        rows.append((D, 1.0 / kmax if kmax > 0 else float("inf"), a["formation"]))
P("curvature fails with kappa info", len(rows))
if rows:
    beyond = sum(1 for D, r, _ in rows if r <= D)
    P(" min curvature radius <= D (lane crosses curvature centre):", beyond, "/", len(rows))
    P(" median D", median(x[0] for x in rows), "median min radius", median(x[1] for x in rows))
    P(" by formation", Counter(x[2] for x in rows))
# 形状复核失败按队形、按 D=0
by_form = defaultdict(lambda: [0, 0])
for a in att:
    if a.get("shape_audit_entered"):
        by_form[a.get("formation")][1] += 1
        by_form[a.get("formation")][0] += bool(a.get("shape_audit_failed"))
P("shape audit fail / entered by formation", {k: tuple(v) for k, v in by_form.items()})
# 按人数档的形状复核失败率
gs = {r["contract_id"]: r["group_size"] for r in recs}
gb = lambda n: 0 if n <= 4 else (1 if n <= 8 else 2)
shp = defaultdict(lambda: [0, 0])
for a in att:
    b = gb(gs[a["contract_id"]])
    shp[b][1] += 1
    shp[b][0] += bool(a.get("shape_audit_failed"))
P("shape audit fail / all attempts by group bin", {k: tuple(v) for k, v in sorted(shp.items())})
# 起始队形 → 实际队形
P("formation retreat (success)", summ["formation_retreat"])
P("topology (success)", summ["topology_final"])
P("echelon steps", summ["echelon_steps_m"])
P("certificate", json.dumps(summ["certificate"]))
P("turns", json.dumps(summ["turns"]))
P("timing", json.dumps(summ["timing"]))
P("contract wall", summ["contract_wall_s"], "batch wall", summ["wall_s"])
# 掉头集合为空
tq = [a for a in att if a["stage"] == "turns"]
P("turn_joint_set_empty attempts", len(tq), Counter((a.get("turn_query") or {}).get("collapse_ok") for a in tq))
P("errors", summ["errors"], "exceptions", summ["exceptions_attempts"])
