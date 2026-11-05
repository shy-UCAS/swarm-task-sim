"""V8-15 第 3 部分：从已存确定性 JSON/NPY 恢复只读对象（指令 3.1）；重算诊断，不调用规划、优化、仿真。

恢复规则（指令 3.1）：
- MemberPlan：skeleton.json.members[m] 原字段，curve_xy 由 arrays[member.<m>.curve_xy] 放回；reference_xy 同样恢复；
  SegmentPlan 其余字段按原名装配，failure=None。JSON 中的元组被存成列表，speed_breaks/stops 还原为元组的元组。
- SplineTrajectory：只用 optimized.json 的 release_s/end_s/altitude_m/knots/controls。
- MemberTrack：tracks/<m>/{tau_us,p,v,a,segment_index}.npy，allow_pickle=False、dtype 保留；单段 switch 元组为空。
- 名义参考与映射：references_from_skeleton，使用与 optimize_segment 相同的 warnings/target/band/align 参数
  （对存储骨架的确定性解释，不是重新规划或求解）。基线输入只读，不写回。
"""
import json
from pathlib import Path

import numpy as np

PHASES = ("collect_ingress", "patrol", "egress")
PHASE_CODES = {"unclassified": 0, "collect_ingress": 1, "patrol": 2, "egress": 3, "hold": 4}
CODE_NAMES = {v: k for k, v in PHASE_CODES.items()}


def _tuples(x):
    if isinstance(x, list):
        return tuple(_tuples(v) for v in x)
    return x


def _read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def load_retained(contract_dir, ctx):
    """从确定性JSON/NPY恢复 plan、样条、名义参考、tracks、release及原始记录；不重新生成。"""
    from v08.contract.monitoring import MemberPlan, SegmentPlan
    from v08.motion.intents.monitoring import monitoring_constraints
    from v08.motion.optimize import SplineTrajectory
    from v08.motion.skeleton import references_from_skeleton
    from v08.sim.types import MemberTrack
    d = Path(contract_dir)
    contract, result = _read(d / "contract.json"), _read(d / "result.json")
    if not result.get("success"):
        raise ValueError(f"{d.name} 不是保留合同（success=false）")
    sk, op = _read(d / "skeleton.json"), _read(d / "optimized.json")
    arrays = sk["arrays"]
    members = {}
    for m, rec in sorted(sk["members"].items()):
        xy = np.asarray(arrays[rec["curve_xy"]["npz"]], dtype=np.float64).reshape(-1, 2)
        members[m] = MemberPlan(member_id=rec["member_id"], segment_index=int(rec["segment_index"]),
                                curve_xy=tuple(map(tuple, xy)), altitude_m=float(rec["altitude_m"]),
                                end_s=float(rec["end_s"]), release_delay_s=float(rec["release_delay_s"]),
                                speed_breaks=_tuples(rec["speed_breaks"]), stops=_tuples(rec.get("stops") or []))
    ref_xy = np.asarray(arrays[sk["reference_xy"]["npz"]], dtype=np.float64).reshape(-1, 2)
    plan = SegmentPlan(members=members, reference_xy=tuple(map(tuple, ref_xy)),
                       nominal_duration_s=sk["nominal_duration_s"], anchors=sk["anchors"],
                       repairs=_tuples(sk["repairs"]), failure=None, proposal=sk["proposal"],
                       formation=sk["formation"], topology=sk["topology"], business_key=sk["business_key"],
                       member_nominal_s=sk["member_nominal_s"], witnesses=sk["witnesses"])
    trajs = {m: SplineTrajectory(m, float(r["release_s"]), float(r["end_s"]), float(r["altitude_m"]),
                                 np.asarray(r["knots"], dtype=np.float64), np.asarray(r["controls"], dtype=np.float64))
             for m, r in sorted(op["members"].items())}
    tracks = {}
    for m in sorted(members):
        td = d / "tracks" / m
        arr = {n: np.load(td / f"{n}.npy", allow_pickle=False) for n in ("tau_us", "p", "v", "a", "segment_index")}
        tracks[m] = MemberTrack(m, arr["tau_us"], arr["p"], arr["v"], arr["a"], arr["segment_index"], ())
    target = plan.witnesses["target_id"]
    cons = monitoring_constraints(ctx, target)
    refs, lines, maps = references_from_skeleton(plan, warnings=cons["warnings"], target_id=target,
                                                 band_m=ctx.params["pre_entry_warning_clearance_m"],
                                                 align_m=ctx.params["alignment_length_m"])
    return {"contract_id": d.name, "contract": contract, "result": result, "plan": plan, "splines": trajs,
            "tracks": tracks, "release_us": {m: int(v) for m, v in result["release_us"].items()},
            "references": {r.member_id: r for r in refs}, "maps": maps, "lines": lines,
            "formation": (result.get("formation") or {}).get("realized"),
            "topology": (result.get("topology") or {}).get("final")}


def phase_bounds(bundle, member_id):
    """逐成员阶段边界（沿用 phase_diagnostics）与掉头区间（沿用 optimize_segment 的插值映射；只取有下界键的行，
    即 V8-14 掉头核心与接回，不含收拢/展开）。"""
    ref = bundle["references"][member_id]
    maps = bundle["maps"][member_id]
    cs, ta = np.asarray(maps["curve_s"], float), np.asarray(maps["t_abs"], float)
    mm = ((bundle["plan"].witnesses or {}).get("member_map_v14") or {}).get("members") or {}
    mp = mm.get(member_id)
    out = {"release_s": float(ref.release_s), "end_s": float(ref.end_s), "t_patrol_a_s": None, "t_patrol_b_s": None,
           "turns": [], "error": None}
    if mp is None:
        out["error"] = "missing member_map_v14"
    else:
        pa, pb = mp["patrol_member_s"]
        out["t_patrol_a_s"] = float(np.interp(pa, cs, ta))
        out["t_patrol_b_s"] = float(np.interp(pb, cs, ta))
    nom = maps["nominal"]
    for kind, s_a, s_b, key_ in (bundle["plan"].witnesses.get("turn_ranges") or {}).get(member_id, []):
        if key_ is None:
            continue
        t_a = float(np.interp(s_a, nom.curve.s, nom.t_nodes)) + float(nom.release_s)
        t_b = float(np.interp(s_b, nom.curve.s, nom.t_nodes)) + float(nom.release_s)
        out["turns"].append((kind, t_a, t_b))
    return out


def phase_codes_at(bounds, t_s):
    """连续时刻 → (阶段代码数组, 掉头布尔数组)。汇合/进入 [release, t_a)、巡逻 [t_a, t_b)、撤离 [t_b, end]、
    end 之后为 hold、release 之前或缺边界为 unclassified。掉头为闭区间 [t_a, t_b] 的并（巡逻的重叠子分档）。"""
    t = np.asarray(t_s, float)
    code = np.zeros(t.shape, np.int8)
    r, e = bounds["release_s"], bounds["end_s"]
    a, b = bounds["t_patrol_a_s"], bounds["t_patrol_b_s"]
    if a is not None and b is not None:
        code[(t >= r) & (t < a)] = PHASE_CODES["collect_ingress"]
        code[(t >= a) & (t < b)] = PHASE_CODES["patrol"]
        code[(t >= b) & (t <= e)] = PHASE_CODES["egress"]
    code[t > e] = PHASE_CODES["hold"]
    turn = np.zeros(t.shape, bool)
    for _, ta, tb in bounds["turns"]:
        turn |= (t >= ta) & (t <= tb)
    return code, turn


def member_phase_masks(bundle, member_id, time_us):
    """返回三阶段、turn、hold/unclassified掩码及原始边界；不改标签。"""
    bounds = phase_bounds(bundle, member_id)
    code, turn = phase_codes_at(bounds, np.asarray(time_us, float) / 1e6)
    out = {name: code == c for name, c in PHASE_CODES.items()}
    out["turn"] = turn
    out["bounds"] = bounds
    return out


def boundary_times(bounds):
    """该成员全部阶段/掉头边界时刻（秒），用于把插值区间切成小区间。"""
    ts = [bounds["release_s"], bounds["end_s"]]
    ts += [x for x in (bounds["t_patrol_a_s"], bounds["t_patrol_b_s"]) if x is not None]
    for _, ta, tb in bounds["turns"]:
        ts += [ta, tb]
    return sorted(set(float(x) for x in ts))


def phase_res(bundle):
    """组装 phase_diagnostics 所需的 res 字典（只读对象），用于复核已存 phase_metrics。"""
    from types import SimpleNamespace as NS
    refs = [bundle["references"][m] for m in sorted(bundle["references"])]
    return {"plan": bundle["plan"], "tracks": bundle["tracks"], "release_us": bundle["release_us"],
            "opt": {"references": refs, "solution": NS(references=bundle["splines"]), "maps": bundle["maps"]}}
