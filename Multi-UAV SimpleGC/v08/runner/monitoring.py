"""V8-12 第 4 部分运行器：只规划检查（指令 4.1–4.3）。

单进程，无仿真、无动力学预演。每个合同：一个族只构建一次上下文；第 0 组；目标由独立 sequence 键抽取；
20 次 attempt 预算由 plan_segment 管理。每个合同写一个排序 JSON 加（成功时）一个无 pickle 的 NPZ。

本模块不在 import 时创建目录、读真实数据或启动任何批量任务。输出与缓存路径在创建任何文件之前，
按 Path.resolve() 后的实际路径（和原路径）检查：拒绝仓库、冻结工作树、数据根，以及任何祖先组件为 v07_* 的路径
（包含通过 junction/symlink 指向它们的路径）。
"""
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
import traceback
from dataclasses import fields, is_dataclass
from pathlib import Path

import numpy as np

from ..contract.monitoring import initial_states, monitoring_mission
from ..diagnostics.diversity import pairwise_discrete_frechet, resample_polyline
from ..motion.feasible import certificate_valid
from ..motion.plan import plan_segment
from ..sampler.common import sample_common
from ..sampler.keys import RngKey
from ..scene.context import load_context
from ..scene.exact import polyline_clearance
from . import monitoring_report as R

REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN_TREE_NAMES = ("Simulation-fe-prod-r3", "Simulation-fe-s3")
DRAWS_PER_FAMILY = 5
DIVERSITY_FAMILIES = 10
DIVERSITY_SEEDS = 10
FRECHET_SPACING_M = 5.0      # 附录裁定 7：测量离散化，只作诊断，不进入生成
FAR_M = 5.0


class PathRejected(ValueError):
    """输出或缓存路径落在不允许的位置。"""


# ---------------------------------------------------------------- 入口保护

def guard_path(path, *, label, repo_root=None, frozen_roots=None, data_root=None, must_not_exist=False):
    raw = Path(os.path.abspath(str(path)))
    resolved = raw.resolve()
    repo = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT.resolve()
    if frozen_roots is None:
        frozen_roots = [repo.parent / n for n in FROZEN_TREE_NAMES]
    forbidden = [("仓库", repo)] + [("冻结工作树", Path(f).resolve()) for f in frozen_roots]
    if data_root is not None:
        forbidden.append(("数据根", Path(data_root).resolve()))
    for how, q in (("原路径", raw), ("解析后路径", resolved)):
        for part in q.parts:
            if part.lower().startswith("v07_"):
                raise PathRejected(f"{label}的{how}含 v07_* 组件 {part!r}：{q}")
        for what, root in forbidden:
            if q == root or root in q.parents:
                raise PathRejected(f"{label}的{how}位于{what}内：{q}（{what}：{root}）")
    if must_not_exist and os.path.lexists(str(raw)):
        raise PathRejected(f"{label}已存在，不得覆盖：{raw}")
    return resolved


# ---------------------------------------------------------------- 序列化

def jsonable(x):
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        x = float(x)
        if math.isfinite(x):
            return x
        return "nan" if math.isnan(x) else ("inf" if x > 0 else "-inf")
    if x is None or isinstance(x, str):
        return x
    if isinstance(x, np.ndarray):
        return jsonable(x.tolist())
    if is_dataclass(x) and not isinstance(x, type):
        return {f.name: jsonable(getattr(x, f.name)) for f in fields(x)}
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (set, frozenset)):
        return [jsonable(v) for v in sorted(x, key=str)]
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    return repr(x)


def canonical_json(obj):
    return json.dumps(jsonable(obj), sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def write_json(path, obj, *, indent=None):
    if indent is None:
        data = canonical_json(obj)
    else:
        data = json.dumps(jsonable(obj), sort_keys=True, ensure_ascii=False, allow_nan=False,
                          indent=indent).encode("utf-8")
    Path(path).write_bytes(data + b"\n")
    return hashlib.sha256(data + b"\n").hexdigest()


def plan_to_record(plan):
    """成功计划 → (JSON 字典, 数组字典)。大数组进 NPZ，JSON 里只留引用。"""
    arrays = {"reference_xy": np.asarray(plan.reference_xy, float).reshape(-1, 2)}
    members = {}
    for m, mp in sorted(plan.members.items()):
        key = f"member.{m}.curve_xy"
        arrays[key] = np.asarray(mp.curve_xy, float).reshape(-1, 2)
        d = {f.name: jsonable(getattr(mp, f.name)) for f in fields(mp) if f.name != "curve_xy"}
        d["curve_xy"] = {"npz": key, "shape": list(arrays[key].shape), "dtype": "float64"}
        members[m] = d
    rec = {"members": members,
           "reference_xy": {"npz": "reference_xy", "shape": list(arrays["reference_xy"].shape), "dtype": "float64"},
           "nominal_duration_s": plan.nominal_duration_s, "anchors": plan.anchors, "repairs": plan.repairs,
           "proposal": plan.proposal, "formation": plan.formation, "topology": plan.topology,
           "business_key": plan.business_key, "member_nominal_s": plan.member_nominal_s,
           "witnesses": plan.witnesses}
    return jsonable(rec), arrays


def failure_record(failure):
    if failure is None:
        return None
    out = {"code": failure.code, "reason": failure.reason, "feasible_set": failure.feasible_set,
           "witness": jsonable(failure.witness), "exact_nonempty": failure.exact_nonempty}
    if failure.code == "proven_infeasible":
        out["certificate_valid"] = bool(certificate_valid(failure))
    return out


# ---------------------------------------------------------------- 单合同

def _attempt_summary(r):
    return {"attempt": r["attempt"], "ok": r["ok"], "seconds": r["seconds"], "stage": r["stage"], "code": r["code"],
            "reason": r["reason"], "feasible_set": r["feasible_set"], "witness": jsonable(r["witness"]),
            "repairs": jsonable(r["repairs"]), "built_candidate": r.get("built_candidate", False)}


def plan_metrics(ctx, group, task, plan):
    """成功计划的派生统计（不属于计划本身，不参与任何构造决定）。"""
    from ..motion.intents.monitoring import FAR_M as FAR

    enters, member_hits = {}, {}
    for m, mp in sorted(plan.members.items()):
        xy = np.asarray(mp.curve_xy, float)
        for f in ctx.facilities:
            if f.id == task.target_id:
                continue
            mar = polyline_clearance(f.layers["warning"], xy, sense=1, minimum_m=0.0, fast_far_m=FAR)
            if float(np.min(mar)) < 0.0:
                enters.setdefault(f.id, []).append(m)
                member_hits[m] = member_hits.get(m, 0) + 1
    crossings = {m: len(c) for m, c in (plan.witnesses or {}).get("crossings", {}).items()}
    form = plan.formation
    return {"nontarget_warning_entered": bool(enters), "nontarget_warning_by_facility": enters,
            "nontarget_facilities": len([f for f in ctx.facilities if f.id != task.target_id]),
            "formation_prior": group.formation_prior, "formation_start": form["start"],
            "formation_realized": form["realized"], "formation_differs_from_prior": form["realized"] != group.formation_prior,
            "formation_retreated": form["realized"] != form["start"], "retreat_chain": form["retreat_chain"],
            "repair_kinds": [r["kind"] for r in plan.repairs], "boundary_crossings_per_member": crossings,
            "topology": plan.topology["final"], "topology_prior_draw": plan.topology.get("prior_draw"),
            "topology_forced": plan.topology.get("forced"), "nominal_duration_s": plan.nominal_duration_s}


def rho_record(proposal):
    """巡逻段半径曲线 ρ 的 CV：按方位均匀测度的精确积分（四点 Gauss–Legendre）和等权离散近似；
    修复（α 缩放）前后各一份。拓扑为折返时，区间是有效折返方位弧。"""
    from ..motion.path import interpolating_coefficients

    if proposal is None or "rho0_m" not in proposal:
        return None
    topo = proposal["topology"]
    lo, hi = (0.0, 2.0 * math.pi) if topo == "loop" else (float(proposal["phi_a"]), float(proposal["phi_b"]))
    rho0, coef = float(proposal["rho0_m"]), np.asarray(proposal["coefficients_m"], float)
    out = {"domain_rad": [lo, hi], "alpha": proposal.get("alpha", 1.0),
           "post": R.rho_cv(rho0, coef, lo, hi), "post_discrete": R.rho_cv_discrete(rho0, coef, lo, hi), "pre": None,
           "pre_discrete": None}
    pre = None
    if proposal.get("sampled_radii_m"):
        c = interpolating_coefficients(np.asarray(proposal["sampled_radii_m"], float))
        pre = (float(np.mean(c)), c - float(np.mean(c)))
    elif proposal.get("alpha", 1.0) > 0:
        pre = (rho0, coef / float(proposal["alpha"]))
    if pre is not None:
        out["pre"] = R.rho_cv(pre[0], pre[1], lo, hi)
        out["pre_discrete"] = R.rho_cv_discrete(pre[0], pre[1], lo, hi)
    return out


def plan_contract(ctx, entry, draw, *, branch=None):
    """规划一个合同，返回 (记录, 计划)。内部异常由调用方记录，不在这里吞掉。"""
    from ..motion.intents.monitoring import prewarm

    common = sample_common(ctx.family, draw)
    mission = monitoring_mission(ctx, common)
    group, task = mission.groups[0], mission.tasks[0]
    states = initial_states(ctx.family, group.member_ids)
    key = RngKey(ctx.family.family_id, draw, "shape", mission=0, branch=branch, group=group.group_id, segment=0)
    t0 = time.perf_counter()
    prewarm(ctx, group, task, states, key)
    prewarm_s = time.perf_counter() - t0
    cold0 = ctx.timings.get("cold_s", 0.0)
    t1 = time.perf_counter()
    plan = plan_segment(ctx, group, task, states, (), key)
    total_s = time.perf_counter() - t1
    cold_in = ctx.timings.get("cold_s", 0.0) - cold0
    cid = f"o{entry['order']:02d}_d{draw}" + ("" if branch is None else f"_b{branch}")
    rec = {"contract_id": cid, "family_id": ctx.family.family_id, "order": entry["order"],
           "directory_rel": entry["directory_rel"], "facility_count": entry["facility_count"],
           "vehicle_count": ctx.family.vehicle_count, "lateral_spacing_m": ctx.family.lateral_spacing_m,
           "map_side_m": entry.get("map_side_m"), "draw_index": draw, "branch": branch, "group_id": group.group_id,
           "member_ids": list(group.member_ids), "group_size": len(group.member_ids), "target_id": task.target_id,
           "intent": task.intent, "formation_prior": group.formation_prior,
           "speed_profile": {"initial_speed_m_s": group.speed_profile.initial_speed_m_s,
                             "change_rate_per_min": group.speed_profile.change_rate_per_min},
           "common_groups": [{"group_id": g.group_id, "member_ids": list(g.member_ids),
                              "initial_speed_m_s": g.speed_profile.initial_speed_m_s,
                              "change_rate_per_min": g.speed_profile.change_rate_per_min,
                              "formation_prior": g.formation_prior} for g in common.groups],
           "mission_business_key": jsonable(mission.business_key),
           "success": plan.failure is None, "attempts": len(plan.attempt_log),
           "attempt_log": [_attempt_summary(r) for r in plan.attempt_log],
           "planning": {"prewarm_s": prewarm_s, "total_s": total_s, "cold_in_planning_s": cold_in,
                        "net_s": total_s - cold_in},
           "failure": failure_record(plan.failure)}
    if plan.failure is None:
        rec["metrics"] = plan_metrics(ctx, group, task, plan)
        rec["rho"] = rho_record(plan.proposal)
    return rec, plan


def finalize_record(rec, plan):
    """填入 rec 的 plan / arrays_sha256 / plan_sha256，返回数组字典。save_contract 与第 5 部分复跑比较共用。"""
    arrays = {}
    if plan is not None and plan.failure is None:
        rec["plan"], arrays = plan_to_record(plan)
    rec["plan_sha256"] = None
    if arrays:
        rec["arrays_sha256"] = {k: hashlib.sha256(np.ascontiguousarray(v).tobytes()).hexdigest()
                                for k, v in sorted(arrays.items())}
    # 复现比较用的摘要：计划、失败、数组摘要和逐 attempt 记录；耗时字段（seconds、planning）不参与
    rec["plan_sha256"] = hashlib.sha256(canonical_json({
        "plan": rec.get("plan"), "failure": rec.get("failure"), "arrays": rec.get("arrays_sha256"),
        "attempts": [{k: v for k, v in a.items() if k != "seconds"} for a in rec.get("attempt_log", [])],
        "common_groups": rec.get("common_groups"), "target_id": rec.get("target_id")})).hexdigest()
    return arrays


def save_contract(out_dir, rec, plan):
    sub = Path(out_dir) / "contracts"
    sub.mkdir(parents=True, exist_ok=True)
    arrays = finalize_record(rec, plan)
    base = sub / rec["contract_id"]
    if arrays:
        np.savez_compressed(str(base) + ".npz", **arrays)
    write_json(str(base) + ".json", rec)


# ---------------------------------------------------------------- 200 合同

def load_entries(path):
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    return sorted(entries, key=lambda e: e["order"])


def plan_devset(entries, *, data_root, cache_dir, out_dir, draws=DRAWS_PER_FAMILY, log=None):
    """顺序规划所有族 × draw。返回 (记录列表, 族级信息)。单合同内部异常记为 error 记录，批次标为不完整。"""
    log = log or (lambda s: None)
    out = Path(out_dir)
    records, families = [], []
    for e in sorted(entries, key=lambda x: x["order"]):
        t0 = time.perf_counter()
        try:
            ctx = load_context(e, data_root=data_root, cache_dir=cache_dir)
        except Exception as exc:                                           # 输入错误：该族全部合同缺失
            log(f"[{e['order']:02d}] 读入失败：{exc!r}")
            for d in range(draws):
                records.append({"contract_id": f"o{e['order']:02d}_d{d}", "family_id": e["family_id"],
                                "order": e["order"], "draw_index": d, "facility_count": e["facility_count"],
                                "success": False, "error": {"kind": "context", "message": repr(exc),
                                                            "trace": traceback.format_exc()}})
            families.append({"family_id": e["family_id"], "order": e["order"], "error": repr(exc)})
            continue
        load_s = time.perf_counter() - t0
        fam = {"family_id": e["family_id"], "order": e["order"], "facility_count": e["facility_count"],
               "vehicle_count": ctx.family.vehicle_count, "load_s": load_s}
        for d in range(draws):
            try:
                rec, plan = plan_contract(ctx, e, d)
            except Exception as exc:
                rec, plan = {"contract_id": f"o{e['order']:02d}_d{d}", "family_id": e["family_id"],
                             "order": e["order"], "draw_index": d, "facility_count": e["facility_count"],
                             "success": False, "error": {"kind": "planning", "message": repr(exc),
                                                         "trace": traceback.format_exc()}}, None
            save_contract(out, rec, plan)
            records.append(rec)
            if "error" in rec:
                log(f"[{e['order']:02d}] d{d} 内部错误 {rec['error']['message']}")
            else:
                p = rec["planning"]
                tag = "OK  " if rec["success"] else "FAIL"
                extra = "" if rec["success"] else f" {rec['failure']['code']}"
                log(f"[{e['order']:02d}] d{d} {tag}{extra} n={rec['group_size']} fac={rec['facility_count']} "
                    f"att={rec['attempts']} net={p['net_s']:.1f}s prewarm={p['prewarm_s']:.1f}s")
        fam["cache"] = ctx.cache_stats()
        fam["cold_s_total"] = ctx.timings.get("cold_s", 0.0)
        fam["cold_builds"] = ctx.timings.get("cold_builds", 0)
        families.append(fam)
    return records, families


# ---------------------------------------------------------------- 多样性

def select_diversity_families(entries, count=DIVERSITY_FAMILIES):
    """按 order 取覆盖 1/2/3 设施的最早各一族，再按 order 补足；不按结果好坏挑选。"""
    ordered = sorted(entries, key=lambda e: e["order"])
    chosen = []
    for k in (1, 2, 3):
        for e in ordered:
            if e["facility_count"] == k:
                chosen.append(e)
                break
    for e in ordered:
        if len(chosen) >= count:
            break
        if e not in chosen:
            chosen.append(e)
    return sorted(chosen, key=lambda e: e["order"])


def _patrol_slice(ref, anchors):
    cum = np.r_[0.0, np.cumsum(np.hypot(*np.diff(ref, axis=0).T))]
    lo = anchors["patrol_start_s"] - anchors["collect_s"]
    hi = anchors["patrol_end_s"] - anchors["collect_s"]
    i0 = int(np.searchsorted(cum, lo, side="left"))
    i1 = int(np.searchsorted(cum, hi, side="right"))
    return ref[max(i0 - 1, 0):min(i1 + 1, len(ref))]


def _frechet_block(paths, spacing_m):
    t0 = time.perf_counter()
    if len(paths) < 2:
        return {"pairs": 0, "distances_m": [], "ratios": [], "summary": None, "seconds": 0.0, "resampled_points": [
            len(p) for p in paths]}
    mat = pairwise_discrete_frechet(paths)
    d, r = R.pair_ratios_from_matrix(mat, spacing_m)
    return {"pairs": len(d), "distances_m": d, "ratios": r, "summary": R.quantile_summary(d),
            "ratio_summary": R.quantile_summary(r), "seconds": time.perf_counter() - t0,
            "resampled_points": [len(p) for p in paths]}


def run_diversity(entries, *, data_root, cache_dir, out_dir, seeds=DIVERSITY_SEEDS, log=None):
    """每族 draw=0 的同一 common 与目标，shape/formation/connect/speed 的 branch=0..seeds-1；失败也报告，不补第 11 个种子。"""
    log = log or (lambda s: None)
    out = Path(out_dir)
    result = []
    for e in select_diversity_families(entries):
        ctx = load_context(e, data_root=data_root, cache_dir=cache_dir)
        spacing = float(ctx.family.lateral_spacing_m)
        seeds_rec, refs, ref_ids = [], [], []
        patrol_refs = []
        for b in range(seeds):
            try:
                rec, plan = plan_contract(ctx, e, 0, branch=b)
            except Exception as exc:
                rec, plan = {"contract_id": f"o{e['order']:02d}_d0_b{b}", "family_id": e["family_id"], "branch": b,
                             "success": False, "error": {"kind": "planning", "message": repr(exc),
                                                         "trace": traceback.format_exc()}}, None
            save_contract(Path(out_dir) / "diversity", rec, plan)
            seeds_rec.append({k: rec.get(k) for k in ("contract_id", "branch", "success", "attempts", "planning",
                                                      "failure", "error", "metrics", "rho", "target_id", "group_size",
                                                      "formation_prior")})
            if plan is not None and plan.failure is None:
                ref = np.asarray(plan.reference_xy, float)
                refs.append(resample_polyline(ref, FRECHET_SPACING_M))
                patrol_refs.append(resample_polyline(_patrol_slice(ref, plan.anchors), FRECHET_SPACING_M))
                ref_ids.append(b)
            log(f"  多样性 族{e['order']:02d} b{b} {'OK' if rec.get('success') else 'FAIL'} att={rec.get('attempts')}")
        full = _frechet_block(refs, spacing)
        patrol = _frechet_block(patrol_refs, spacing)
        ok = [s for s in seeds_rec if s.get("success")]
        pre_post = [{"branch": s["branch"], "pre_cv": (s["rho"] or {}).get("pre", {}) and s["rho"]["pre"]["cv"],
                     "post_cv": s["rho"]["post"]["cv"], "post_cv_discrete": s["rho"]["post_discrete"]}
                    for s in ok if s.get("rho")]
        topo = {"prior_draw": {}, "forced_final": {}, "final": {}}
        for s in ok:
            m = s["metrics"]
            topo["prior_draw"][m["topology_prior_draw"]] = topo["prior_draw"].get(m["topology_prior_draw"], 0) + 1
            topo["final"][m["topology"]] = topo["final"].get(m["topology"], 0) + 1
            topo["forced_final"][str(m["topology_forced"])] = topo["forced_final"].get(str(m["topology_forced"]), 0) + 1
        result.append({"family_id": e["family_id"], "order": e["order"], "facility_count": e["facility_count"],
                       "lateral_spacing_m": spacing, "successful_seeds": len(ok), "seeds": seeds_rec,
                       "seeds_in_pairs": ref_ids,
                       "median_frechet_m": None if not full["distances_m"] else float(np.median(full["distances_m"])),
                       "pair_ratios": full["ratios"], "frechet": full, "patrol_frechet": patrol,
                       "rho_cv": pre_post, "topology_counts": topo,
                       "rho_cv_summary": R.quantile_summary([p["post_cv"] for p in pre_post])})
    return result


# ---------------------------------------------------------------- 总控

def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def environment_report(repo_root=None):
    repo = Path(repo_root) if repo_root is not None else REPO_ROOT
    env = {"python": sys.version, "platform": platform.platform(), "numpy": np.__version__}
    for mod in ("scipy", "shapely"):
        try:
            env[mod] = __import__(mod).__version__
        except Exception as exc:                                           # 可选依赖，只报告
            env[mod] = f"不可用：{exc!r}"
    try:
        env["git_head"] = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                                         timeout=30).stdout.strip()
        env["git_dirty"] = bool(subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True,
                                               text=True, timeout=60).stdout.strip())
    except Exception as exc:
        env["git_head"] = f"不可用：{exc!r}"
    src = {}
    base = Path(__file__).resolve().parents[1]
    for sub in ("contract", "sampler", "scene", "motion", "runner"):
        for p in sorted((base / sub).rglob("*.py")):
            src[str(p.relative_to(base.parent)).replace("\\", "/")] = _sha256_file(p)
    cfg = base.parent / "configs" / "v08" / "monitoring.json"
    src["configs/v08/monitoring.json"] = _sha256_file(cfg)
    env["source_sha256"] = src
    return env


def plan_stage(entries, *, data_root, cache_dir, out_dir, devset_path=None, with_diversity=True, draws=DRAWS_PER_FAMILY,
               log=print):
    """第 4 部分：200 合同只规划，加多样性。返回 (summary, checkpoint)。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    started = time.time()
    logf = (out / "progress.log").open("a", encoding="utf-8", newline="\n")

    def say(s):
        logf.write(s + "\n")
        logf.flush()
        log(s)

    t0 = time.perf_counter()
    records, families = plan_devset(entries, data_root=data_root, cache_dir=cache_dir, out_dir=out, draws=draws, log=say)
    plan_wall = time.perf_counter() - t0
    diversity = []
    div_wall = 0.0
    if with_diversity:
        t1 = time.perf_counter()
        diversity = run_diversity(entries, data_root=data_root, cache_dir=cache_dir, out_dir=out, log=say)
        div_wall = time.perf_counter() - t1
    summary = R.build_summary(records, diversity, families=families, expected_contracts=len(entries) * draws,
                              expected_families=len(entries), diversity_expected=with_diversity)
    summary["timing_wall_s"] = {"plan_stage": plan_wall, "diversity_stage": div_wall}
    summary["meta"] = {"started_unix": started, "devset_path": None if devset_path is None else str(devset_path),
                       "devset_sha256": None if devset_path is None else _sha256_file(devset_path),
                       "data_root": str(data_root), "cache_dir": str(cache_dir), "out_dir": str(out),
                       "environment": environment_report(), "argv": sys.argv}
    chk = R.checkpoint(summary)
    summary["checkpoint"] = {"triggers": list(chk.triggers), "complete": chk.complete,
                             "incomplete_reasons": list(chk.incomplete_reasons), "values": chk.values}
    write_json(out / "summary.json", summary, indent=2)
    write_json(out / "failures.json", [r for r in records if not r.get("success")], indent=2)
    write_json(out / "diversity.json", diversity, indent=2)
    logf.close()
    return summary, chk
