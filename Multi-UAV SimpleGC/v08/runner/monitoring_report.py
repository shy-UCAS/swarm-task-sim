"""第 4 部分的统计与止损检查点（V8-12；指令 4.2、4.4，附录补充裁定）。

止损是诊断性的，不是 P0 门禁；任一触发就停在第 4 部分。比较一律严格：
  80% 本身不触发；比总成功率低恰好 20 个百分点不触发（整数计数的 Fraction 相减，与 Fraction("0.20") 比较）；
  规划中位数 30 s 不触发；Fréchet 比值中位数等于 1 不触发。
缺失或待决的测量返回"检查未完成"（complete=False），不把缺失当成 False，也不新增数值阈值。

Fréchet（附录补充裁定，取代指令 4.4 的"逐族任一触发"）：每一对路径的"离散 Fréchet ÷ 该族 lateral_spacing_m"
合并后的中位数 < 1 才触发 `frechet`；逐族数值照常报告，作为诊断。条目里有 pair_ratios（逐对比值）时用它；
只有 median_frechet_m 时，以该族中位数比值代表该族一个点。
"""
import math
from dataclasses import dataclass
from fractions import Fraction

import numpy as np

SUCCESS_FLOOR = Fraction(4, 5)       # 上层 D.4：总成功率严格小于 80%
FACILITY_GAP = Fraction("0.20")      # 不用 Fraction(0.20)，避免二进制浮点误差
PLANNING_MEDIAN_S = 30.0
REQUIRED_SEEDS = 10


@dataclass(frozen=True)
class CheckpointResult:
    triggers: tuple
    complete: bool
    incomplete_reasons: tuple
    values: dict


def _rate(successes, contracts):
    return Fraction(int(successes), int(contracts))


def checkpoint(summary) -> CheckpointResult:
    triggers, reasons, values = [], [], {}
    if not summary.get("completed", False):
        reasons.append("批次未完成（completed 不为真）")
    contracts, successes = summary.get("contracts"), summary.get("successes")
    if not contracts:
        reasons.append("缺少合同总数")
    elif successes is None:
        reasons.append("缺少规划成功数")
    else:
        total = _rate(successes, contracts)
        values["success_rate"] = {"successes": int(successes), "contracts": int(contracts), "rate": float(total)}
        if total < SUCCESS_FLOOR:
            triggers.append("success_rate")
        gaps = {}
        for k, v in sorted((summary.get("by_facilities") or {}).items(), key=lambda kv: str(kv[0])):
            if not v.get("contracts"):
                reasons.append(f"设施数 {k} 档没有合同")
                continue
            r = _rate(v["successes"], v["contracts"])
            gap = total - r
            gaps[str(k)] = {"successes": int(v["successes"]), "contracts": int(v["contracts"]), "rate": float(r),
                            "gap_to_total": float(gap)}
            if gap > FACILITY_GAP:
                if "facility_gap" not in triggers:
                    triggers.append("facility_gap")
        if not gaps:
            reasons.append("缺少按设施数的统计")
        values["facility_gap"] = gaps
    med = summary.get("planning_median_s")
    if med is None or (isinstance(med, float) and np.isnan(med)):
        reasons.append("缺少规划耗时中位数")
    else:
        values["planning_median_s"] = float(med)
        if float(med) > PLANNING_MEDIAN_S:
            triggers.append("planning_time")
    bad = []
    for f in summary.get("failures") or []:
        if f.get("code") != "proven_infeasible":
            continue
        no_witness = not f.get("witness")
        nonempty = f.get("exact_nonempty") is True
        invalid = f.get("certificate_valid") is False
        if no_witness or nonempty or invalid:
            bad.append({"no_witness": no_witness, "exact_nonempty": nonempty, "certificate_invalid": invalid,
                        "family_id": f.get("family_id"), "draw_index": f.get("draw_index")})
    values["failure_evidence"] = {"bad_proven_infeasible": bad}
    if bad:
        triggers.append("failure_evidence")
    ratios, per_family = [], []
    div = summary.get("diversity")
    if not div:
        reasons.append("缺少多样性测量")
    else:
        for d in div:
            fam = d.get("family_id")
            ok = d.get("successful_seeds") == REQUIRED_SEEDS and (d.get("pair_ratios") or d.get("median_frechet_m") is not None)
            if not ok:
                reasons.append(f"族 {fam} 未取得 {REQUIRED_SEEDS} 个成功种子或缺少 Fréchet 距离")
                continue
            sp = d.get("lateral_spacing_m")
            if not sp or sp <= 0:
                reasons.append(f"族 {fam} 缺少横向间距")
                continue
            if d.get("pair_ratios"):
                ratios.extend(float(x) for x in d["pair_ratios"])
            else:
                ratios.append(float(d["median_frechet_m"]) / float(sp))
            per_family.append({"family_id": fam, "median_ratio": float(np.median(
                d["pair_ratios"] if d.get("pair_ratios") else [float(d["median_frechet_m"]) / float(sp)]))})
        if ratios:
            pooled = float(np.median(ratios))
            values["frechet"] = {"pooled_median_ratio": pooled, "pairs": len(ratios), "per_family": per_family}
            if pooled < 1.0:
                triggers.append("frechet")
    complete = not reasons
    return CheckpointResult(tuple(triggers), complete, tuple(reasons), values)


# ======================================================================================================
# 统计辅助（指令 4.2、4.3）：全部是纯函数，输入是运行器写出的记录，不读文件。
# ======================================================================================================

def quantile_summary(values):
    """min/q25/median/q75/p95/max，NumPy quantile 的 linear 方法；空输入返回 None（不填 NaN）。"""
    v = np.asarray([x for x in values if x is not None], float)
    if v.size == 0:
        return None
    q = np.quantile(v, [0.0, 0.25, 0.5, 0.75, 0.95, 1.0], method="linear")
    return {"n": int(v.size), "min": float(q[0]), "q25": float(q[1]), "median": float(q[2]), "q75": float(q[3]),
            "p95": float(q[4]), "max": float(q[5])}


# 四点 Gauss–Legendre：对三次样条的 ρ² （节点段内六次多项式）精确，2n−1 = 7 ≥ 6。四点是积分代数要求，不是形态常数。
_GL_X, _GL_W = np.polynomial.legendre.leggauss(4)


def rho_moments(rho0_m, coefficients_m, phi_lo, phi_hi):
    """半径曲线 ρ(φ) 在方位区间 [phi_lo, phi_hi]（弧度，可跨周期，phi_hi>phi_lo）上按方位均匀测度的
    均值与方差：在 B 样条节点 φ_j = 2πj/K 处分段，每段用四点 Gauss–Legendre 精确积分 ρ 与 ρ²。"""
    from ..motion.path import periodic_radius

    K = len(coefficients_m)
    if not phi_hi > phi_lo:
        raise ValueError("方位区间必须 phi_hi > phi_lo")
    step = 2.0 * math.pi / K
    k0, k1 = math.floor(phi_lo / step), math.ceil(phi_hi / step)
    cuts = [phi_lo] + [k * step for k in range(k0 + 1, k1) if phi_lo < k * step < phi_hi] + [phi_hi]
    s1 = s2 = 0.0
    for a, b in zip(cuts[:-1], cuts[1:]):
        x = 0.5 * (b - a) * _GL_X + 0.5 * (a + b)
        r = periodic_radius(x, rho0_m, coefficients_m)
        w = 0.5 * (b - a) * _GL_W
        s1 += float(np.sum(w * r))
        s2 += float(np.sum(w * r * r))
    length = phi_hi - phi_lo
    mean = s1 / length
    var = max(s2 / length - mean * mean, 0.0)
    return mean, var, len(cuts) - 1


def rho_cv(rho0_m, coefficients_m, phi_lo, phi_hi):
    mean, var, segments = rho_moments(rho0_m, coefficients_m, phi_lo, phi_hi)
    return {"mean_m": mean, "std_m": math.sqrt(var), "cv": math.sqrt(var) / mean, "segments": segments}


def rho_cv_discrete(rho0_m, coefficients_m, phi_lo, phi_hi, samples=720):
    """等权等方位样本上用 V8-05 coefficient_of_variation 得到的离散近似（与精确积分并列报告）。"""
    from ..diagnostics.diversity import coefficient_of_variation
    from ..motion.path import periodic_radius

    phi = phi_lo + (phi_hi - phi_lo) * (np.arange(samples) + 0.5) / samples
    return coefficient_of_variation(periodic_radius(phi, rho0_m, coefficients_m))


def pair_ratios_from_matrix(matrix, spacing_m):
    """非对角上三角（C(k,2) 对）的距离及其除以 lateral_spacing_m 的比值。"""
    k = matrix.shape[0]
    iu = np.triu_indices(k, k=1)
    d = np.asarray(matrix)[iu]
    return [float(x) for x in d], [float(x) / float(spacing_m) for x in d]


# ======================================================================================================
# 汇总（指令 4.2）：输入是运行器写出的合同记录（字典），输出是可序列化的统计。
# 每个比例都同时给出分子、分母和缺失数；缺失（内部错误、未读入）不从分母里删除。
# ======================================================================================================

def _count(items):
    out = {}
    for x in items:
        out[str(x)] = out.get(str(x), 0) + 1
    return dict(sorted(out.items()))


def _ratio(num, den):
    return {"numerator": int(num), "denominator": int(den), "rate": (float(num) / den) if den else None}


def build_summary(records, diversity, *, families=(), expected_contracts, expected_families, diversity_expected=True):
    errors = [r for r in records if "error" in r]
    done = [r for r in records if "error" not in r]
    ok = [r for r in done if r["success"]]
    bad = [r for r in done if not r["success"]]
    missing = expected_contracts - len(done)
    completed = missing == 0 and not errors and len(records) == expected_contracts

    by_fac = {}
    for r in records:
        k = r.get("facility_count")
        d = by_fac.setdefault(k, {"contracts": 0, "successes": 0})
        d["contracts"] += 1
        d["successes"] += 1 if r.get("success") else 0
    by_n = {}
    for r in done:
        d = by_n.setdefault(r["group_size"], {"contracts": 0, "successes": 0})
        d["contracts"] += 1
        d["successes"] += 1 if r["success"] else 0

    final_codes = _count(r["failure"]["code"] for r in bad)
    final_reasons = {}
    for r in bad:
        f = r["failure"]
        stages = sorted({a["stage"] for a in r["attempt_log"] if not a["ok"]}, key=str)
        key = f"{f['code']} | {f['feasible_set']}"
        e = final_reasons.setdefault(key, {"count": 0, "attempt_stages": {}})
        e["count"] += 1
        for a in r["attempt_log"]:
            if not a["ok"]:
                e["attempt_stages"][str(a["stage"])] = e["attempt_stages"].get(str(a["stage"]), 0) + 1

    attempts = [a for r in done for a in r["attempt_log"]]
    attempt_stage = _count(a["stage"] for a in attempts if not a["ok"])
    attempt_by_outcome = {"success_contracts": _count(a["stage"] for r in ok for a in r["attempt_log"] if not a["ok"]),
                          "failed_contracts": _count(a["stage"] for r in bad for a in r["attempt_log"] if not a["ok"])}

    net = [r["planning"]["net_s"] for r in done]
    total = [r["planning"]["total_s"] for r in done]
    planning = {"net_s": quantile_summary(net), "total_incl_cold_s": quantile_summary(total),
                "net_success_s": quantile_summary([r["planning"]["net_s"] for r in ok]),
                "net_failure_s": quantile_summary([r["planning"]["net_s"] for r in bad]),
                "cold_cache": {"prewarm_s_sum": sum(r["planning"]["prewarm_s"] for r in done),
                               "cold_in_planning_s_sum": sum(r["planning"]["cold_in_planning_s"] for r in done),
                               "family_load_s_sum": sum(f.get("load_s", 0.0) for f in families),
                               "family_cold_s_sum": sum(f.get("cold_s_total", 0.0) for f in families),
                               "cache_hits": sum(f.get("cache", {}).get("hits", 0) for f in families),
                               "cache_misses": sum(f.get("cache", {}).get("misses", 0) for f in families)},
                "median_definition": "每合同从第一次规划到终局的耗时，成功与失败都计，扣除惰性缓存首次构建时间；"
                                     "分位数用 NumPy quantile(method='linear')"}

    nontarget = {"contracts": _ratio(sum(1 for r in ok if r["metrics"]["nontarget_warning_entered"]), len(ok)),
                 "contracts_with_nontarget_facility": _ratio(
                     sum(1 for r in ok if r["metrics"]["nontarget_warning_entered"] and r["metrics"]["nontarget_facilities"] > 0),
                     sum(1 for r in ok if r["metrics"]["nontarget_facilities"] > 0)),
                 "by_facility_count": {str(k): _ratio(
                     sum(1 for r in ok if r["facility_count"] == k and r["metrics"]["nontarget_warning_entered"]),
                     sum(1 for r in ok if r["facility_count"] == k)) for k in sorted(by_fac, key=str)},
                 "members_entering": sum(len(v) for r in ok for v in r["metrics"]["nontarget_warning_by_facility"].values()),
                 "members_total": sum(r["group_size"] for r in ok)}
    formation = {"differs_from_prior": _ratio(sum(1 for r in ok if r["metrics"]["formation_differs_from_prior"]), len(ok)),
                 "retreated_from_mapped_start": _ratio(sum(1 for r in ok if r["metrics"]["formation_retreated"]), len(ok)),
                 "prior_counts": _count(r["metrics"]["formation_prior"] for r in ok),
                 "realized_counts": _count(r["metrics"]["formation_realized"] for r in ok),
                 "retreat_chains": [{"contract_id": r["contract_id"], "prior": r["metrics"]["formation_prior"],
                                     "start": r["metrics"]["formation_start"], "realized": r["metrics"]["formation_realized"],
                                     "chain": r["metrics"]["retreat_chain"]} for r in ok if r["metrics"]["formation_retreated"]
                                    or r["metrics"]["formation_differs_from_prior"]]}

    def kinds(reps):
        return _count(x["kind"] for x in reps)

    built = [a for a in attempts if a.get("built_candidate") or a["ok"]]
    rep_attempts = [a for a in built if a["repairs"]]
    all_repairs = [x for a in built for x in a["repairs"]]

    def vals(kind, field):
        return [float(x[field]) for x in all_repairs if x["kind"] == kind and x.get(field) is not None]

    repairs = {"contracts": _ratio(sum(1 for r in ok if r["metrics"]["repair_kinds"]), len(ok)),
               "attempts_with_candidate": _ratio(len(rep_attempts), len(built)),
               "kinds_in_success_contracts": _count(k for r in ok for k in r["metrics"]["repair_kinds"]),
               "kinds_all_attempts": kinds(all_repairs),
               "alpha": quantile_summary(vals("alpha_scaling", "alpha")),
               "echelon_lateral_step_ratio": quantile_summary(
                   [x["to_m"] / x["from_m"] for x in all_repairs if x["kind"] == "echelon_lateral_step"]),
               "radius_shift_delta_m": quantile_summary(vals("radius_shift_budget", "delta_m")),
               "radius_shift_fraction_of_max": quantile_summary(
                   [x["delta_m"] / x["max_shift_m"] for x in all_repairs
                    if x["kind"] == "radius_shift_budget" and x.get("max_shift_m")]),
               "laps_drawn_vs_used": [{"drawn": x["drawn"], "used": x["used"]} for x in all_repairs
                                      if x["kind"] == "laps_budget_cap"],
               "traversals_drawn_vs_used": [{"drawn": x["drawn"], "used": x["used"]} for x in all_repairs
                                            if x["kind"] == "traversals_budget_cap"]}

    queries = []
    for r in bad:
        w = (r["failure"].get("witness") or {})
        if isinstance(w, dict) and w.get("query"):
            queries.append({"contract_id": r["contract_id"], **w["query"], "final_code": r["failure"]["code"]})
    n_rechecked = sum(1 for q in queries if q["field_empty"] and q["exact_recheck_executed"])
    n_exact_nonempty = sum(1 for q in queries if q["field_empty"] and q["exact_recheck_executed"] and q["exact_nonempty"])
    recheck = {"queries": queries, "field_empty_and_rechecked": n_rechecked, "exact_nonempty_found": n_exact_nonempty,
               "ratio": _ratio(n_exact_nonempty, n_rechecked),
               "proven_infeasible": sum(1 for r in bad if r["failure"]["code"] == "proven_infeasible"),
               "unknown_or_not_rechecked": len(queries) - n_rechecked,
               "note": "距离场保守集非空而环/弧构造失败的查询只计入 unknown_or_not_rechecked，不当作空"}

    crossings = [sum(v for v in r["metrics"]["boundary_crossings_per_member"].values()) for r in ok]
    semantics = {"crossings_per_contract": quantile_summary(crossings),
                 "crossings_per_member": quantile_summary([v for r in ok for v in r["metrics"]["boundary_crossings_per_member"].values()]),
                 "attempt_rejections": {k: attempt_stage.get(k, 0) for k in
                                        ("boundary_crossing", "nominal_dwell", "nominal_revisit", "nominal_layers",
                                         "separation", "terminal_clearance", "duration_budget")},
                 "dwell_rejections": [{"contract_id": r["contract_id"], "attempt": a["attempt"],
                                       "witness": a["witness"]} for r in done for a in r["attempt_log"]
                                      if a["stage"] == "nominal_dwell"],
                 "note": "边界穿越/驻留/重访为诊断证据；驻留拒绝称'疑似误报'需另行判断，不在此处结论"}

    topology = {"prior_draw": _count(r["metrics"]["topology_prior_draw"] for r in ok),
                "forced": _count(r["metrics"]["topology_forced"] for r in ok),
                "final": _count(r["metrics"]["topology"] for r in ok)}

    failure_list = [{"contract_id": r["contract_id"], "family_id": r["family_id"], "draw_index": r["draw_index"],
                     "group_id": r["group_id"], "target_id": r["target_id"], "group_size": r["group_size"],
                     "facility_count": r["facility_count"], "attempts": r["attempts"], "code": r["failure"]["code"],
                     "reason": r["failure"]["reason"], "feasible_set": r["failure"]["feasible_set"],
                     "evidence_path": f"contracts/{r['contract_id']}.json"} for r in bad]
    ckpt_failures = [{"code": r["failure"]["code"], "witness": r["failure"].get("witness"),
                      "exact_nonempty": r["failure"].get("exact_nonempty"),
                      "certificate_valid": r["failure"].get("certificate_valid"), "family_id": r["family_id"],
                      "draw_index": r["draw_index"]} for r in bad if r["failure"]["code"] == "proven_infeasible"]
    div = [{"family_id": d["family_id"], "order": d["order"], "successful_seeds": d["successful_seeds"],
            "median_frechet_m": d.get("median_frechet_m"), "lateral_spacing_m": d["lateral_spacing_m"],
            "pair_ratios": d.get("pair_ratios")} for d in diversity]

    return {
        "completed": completed, "contracts": expected_contracts, "successes": len(ok),
        "records": len(records), "done": len(done), "missing": missing,
        "errors": [{"contract_id": r["contract_id"], "error": r["error"]["message"]} for r in errors],
        "families_expected": expected_families, "families_loaded": len([f for f in families if "error" not in f]),
        "by_facilities": {str(k): v for k, v in sorted(by_fac.items(), key=lambda kv: str(kv[0]))},
        "by_group_size": {str(k): v for k, v in sorted(by_n.items())},
        "final_failure_codes": final_codes, "final_failure_reasons": final_reasons,
        "attempt_failure_stages": attempt_stage, "attempt_failure_stages_by_contract_outcome": attempt_by_outcome,
        "attempts_total": len(attempts), "planning": planning,
        "planning_median_s": None if not net else float(np.quantile(np.asarray(net, float), 0.5, method="linear")),
        "nontarget_warning": nontarget, "formation": formation, "repairs": repairs, "exact_recheck": recheck,
        "semantics": semantics, "topology_success_contracts": topology,
        "failure_list": failure_list, "failures": ckpt_failures, "diversity": div if diversity_expected else None,
        "diversity_detail_file": "diversity.json",
        "diversity_summary": [{"family_id": d["family_id"], "order": d["order"], "facility_count": d["facility_count"],
                               "successful_seeds": d["successful_seeds"], "pairs": d["frechet"]["pairs"],
                               "frechet_summary_m": d["frechet"]["summary"], "patrol_frechet_summary_m": d["patrol_frechet"]["summary"],
                               "lateral_spacing_m": d["lateral_spacing_m"], "rho_cv_summary": d["rho_cv_summary"],
                               "topology_counts": d["topology_counts"], "frechet_seconds": d["frechet"]["seconds"]}
                              for d in diversity],
    }
