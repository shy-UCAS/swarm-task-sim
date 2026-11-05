"""第 3 部分原型核对（out/prototype）：真实合同上跑 plan_attempt（≤ 预算 20），对成功骨架按 8.7 同口径独立核对
成员映射与精确约束；统计掉头集合规模。只构造骨架。"""
import sys, time, json
from pathlib import Path
from dataclasses import replace
import numpy as np
sys.path.insert(0, str(Path.cwd()))
from v08.runner.monitoring import load_entries, jsonable
from v08.scene.context import load_context
from v08.scene.exact import polyline_clearance
from v08.contract.monitoring import initial_states, monitoring_mission
from v08.sampler.common import sample_common
from v08.sampler.keys import RngKey
from v08.motion.plan import plan_attempt
from v08.motion.intents.monitoring import monitoring_constraints, last_attempt_timing

R = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
entries = load_entries(str(R / "Simulation-v08/docs/v08/V8-03/devset_v08.json"))
cache = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=False)
orders = [int(x) for x in sys.argv[3].split(",")]; draws = [int(x) for x in sys.argv[4].split(",")]
by = {int(e["order"]): e for e in entries}
rows = []


def cut_by_arclength(xy, a, b):
    ds = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    s = np.r_[0., np.cumsum(ds)]
    inner = (s > a) & (s < b)
    start = [np.interp(a, s, xy[:, k]) for k in range(2)]
    end = [np.interp(b, s, xy[:, k]) for k in range(2)]
    return np.vstack([start, xy[inner], end])


for o in orders:
    ctx = load_context(by[o], data_root=R / "SwarmData", cache_dir=cache)
    for d in draws:
        common = sample_common(ctx.family, d)
        mission = monitoring_mission(ctx, common)
        group, task = mission.groups[0], mission.tasks[0]
        states = initial_states(ctx.family, group.member_ids)
        key0 = RngKey(ctx.family.family_id, d, "shape", mission=0, branch=None, group=group.group_id, segment=0)
        log = []
        plan = None
        for a in range(20):
            p = plan_attempt(ctx, group, task, states, (), replace(key0, attempt=a))
            tm = last_attempt_timing()
            w = (p.failure.witness or {}) if p.failure else p.witnesses
            log.append({"ok": p.failure is None, "stage": None if p.failure is None else w.get("stage", p.failure.feasible_set),
                        "t": round(tm.get("attempt_s", 0), 2), "turn_s": round(tm.get("turn_query_s", 0), 2),
                        "audit": (w.get("audit") or {}).get("reasons")})
            if p.failure is None:
                plan = p
                break
        row = {"cid": f"o{o:02d}_d{d}", "n": len(group.member_ids), "attempts": len(log), "log": log}
        if plan is not None:
            row.update(formation=plan.formation["realized"], topology=plan.topology["final"],
                       turns=[{k: t.get(k) for k in ("kind", "side", "radius_m", "merge_distance_m")} for t in (plan.topology.get("turns") or plan.proposal.get("topology_info", {}).get("turns") or [])])
            cons = monitoring_constraints(ctx, task.target_id)
            mapping = plan.witnesses["member_map_v14"]
            bad = []
            for mid, mp in plan.members.items():
                xy = np.asarray(mp.curve_xy, float)
                mm = mapping["members"][mid]
                for k in ("reference_s", "shifted_reference_s", "member_s"):
                    if not np.all(np.diff(mm[k]) > 0):
                        bad.append((mid, "monotone", k))
                dl = np.asarray(mm["lateral_m"]); mk = np.asarray(mm["turn_mask"], bool)
                if np.any(dl[mk] != 0):
                    bad.append((mid, "lateral_in_turn"))
                a_, b_ = mm["patrol_member_s"]
                patrol = cut_by_arclength(xy, a_, b_)
                for cs, pts in ((cons["base"], xy), (cons["patrol"], patrol)):
                    for c in cs:
                        mg = float(np.min(polyline_clearance(c.geometry, pts, sense=c.sense, minimum_m=c.minimum_m)))
                        if not mg >= 0:
                            bad.append((mid, c.name, mg))
            row["map_check_failures"] = bad
            row["turn_mask_rows"] = int(sum(sum(m["turn_mask"]) for m in mapping["members"].values()))
        rows.append(row)
        print(json.dumps(jsonable(row), ensure_ascii=False)[:600], flush=True)
(out / "verify_turns.json").write_text(json.dumps(jsonable(rows), ensure_ascii=False, indent=1), encoding="utf-8")
