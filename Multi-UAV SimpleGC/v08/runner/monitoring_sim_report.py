"""V8-12 第 5 部分汇总（指令 5.2、5.3 与第 10 节第 5 条的数字）。纯函数：输入是运行器写出的合同记录，不读文件。

分母和缺失数一同输出；没有测到的量写 None，不填 NaN，也不当作通过。速度不设新阈值：用速度剖面的原始浮点值和分位数。
"""
import numpy as np

from .monitoring_report import quantile_summary


def _ratio(num, den):
    return {"numerator": int(num), "denominator": int(den), "rate": (float(num) / den) if den else None}


def _count(items):
    out = {}
    for x in items:
        out[str(x)] = out.get(str(x), 0) + 1
    return dict(sorted(out.items()))


def _final_attempt(r):
    fa = r.get("final_attempt")
    if fa is None:
        return None
    return next((a for a in r["attempts"] if a["attempt"] == fa), None)


def _stratum(rows, key):
    """按 key 分层：合同数、有失败 attempt 的合同数、attempt 数、失败 attempt 数。"""
    out = {}
    for r in rows:
        d = out.setdefault(str(r.get(key)), {"contracts": 0, "contracts_with_failed_attempt": 0, "attempts": 0,
                                             "failed_attempts": 0, "retained": 0, "failed": 0})
        failed = sum(1 for a in r["attempts"] if not a["accepted"])
        d["contracts"] += 1
        d["attempts"] += len(r["attempts"])
        d["failed_attempts"] += failed
        d["contracts_with_failed_attempt"] += 1 if failed else 0
        d["retained"] += 1 if r["status"] == "retained" else 0
        d["failed"] += 1 if r["status"] == "failed" else 0
    return dict(sorted(out.items()))


def _quartile_bins(entries):
    """entries: [(期望速度档, 帧数, 超管帧数, 最大误差)]；按档位值的分位数分 4 个等计数区间（不设无来源阈值）。"""
    if not entries:
        return None
    lv = np.array([e[0] for e in entries])
    edges = np.quantile(lv, [0.0, 0.25, 0.5, 0.75, 1.0], method="linear")
    out = []
    for i in range(4):
        lo, hi = edges[i], edges[i + 1]
        sel = [e for e in entries if (e[0] >= lo and (e[0] < hi or (i == 3 and e[0] <= hi)))]
        out.append({"speed_range_m_s": [float(lo), float(hi)], "entries": len(sel), "frames": int(sum(e[1] for e in sel)),
                    "over_frames": int(sum(e[2] for e in sel)),
                    "max_m": float(max((e[3] for e in sel), default=0.0)) if sel else None})
    return out


def build_sim_summary(*, stage, queue, results, not_run, p0, quick_results, selection, successes, wall_s, budget_s, subset):
    allr = list(quick_results) + list(results)
    executed = [r for r in allr if r["status"] in ("retained", "failed")]
    retained = [r for r in allr if r["status"] == "retained"]
    failed = [r for r in allr if r["status"] == "failed"]
    interrupted = [r for r in allr if r["status"] == "interrupted"]
    rerun_equal = [r for r in retained if r["rerun"]["status"] == "equal"]
    rerun_mismatch = [r for r in allr if r["rerun"]["status"] == "mismatch"]
    pending_rerun = [r for r in retained if r["rerun"]["status"] == "pending"]
    attempts = [(r, a) for r in executed for a in r["attempts"]]
    bad_att = [(r, a) for r, a in attempts if not a["accepted"]]
    first_errors = []
    for r in allr:
        for a in r["attempts"]:
            if not a["accepted"]:
                first_errors.append({"contract_id": r["contract_id"], "attempt": a["attempt"], "codes": a["codes"],
                                     "failures": a["failures"][:10]})
                break

    cond = {}
    for r, a in bad_att:
        for f in a["failures"]:
            k = f"{f[1]}|{f[2]}"
            cond[k] = cond.get(k, 0) + 1
    dwell = [dict(d, contract_id=r["contract_id"], attempt=a["attempt"]) for r, a in attempts for d in a.get("dwell", [])]

    fin = [(r, _final_attempt(r)) for r in retained]
    fin = [(r, a) for r, a in fin if a is not None]
    seps = [a["validity"]["min_separation_m"] for _, a in fin]
    iseps = [a["validity"]["interp_min_separation_m"] for _, a in fin]
    all_seps = [a["validity"]["min_separation_m"] for _, a in attempts if "validity" in a]
    all_iseps = [a["validity"]["interp_min_separation_m"] for _, a in attempts if "validity" in a]
    tube_max, tube_p95, tube_entries, tube_over = [], [], [], []
    over_speed, d_abs, d_vec, d_abs_w, d_vec_w, speed_max = [], [], [], [], [], []
    bexcess, balert = [], 0
    worst_over = []
    for r, a in fin:
        for m, d in a["members"].items():
            t = d["tracking"]
            tube_max.append(t["max_m"])
            tube_p95.append(t["p95_m"])
            for lv, e in t["over_by_expected_speed"].items():
                tube_entries.append((float(lv), e["frames"], e["over_frames"], e["max_m"]))
            if t["over_frames"]:
                tube_over.append({"contract_id": r["contract_id"], "member": m, "over_frames": t["over_frames"],
                                  "max_m": t["max_m"], "first_over": t["first_over"], "max_at": t["max_at"]})
            s = d["speed"]
            over_speed.append(s["max_positive_over_m_s"])
            speed_max.append(s["speed_max_m_s"])
            af = s["adjacent_frame"]
            d_abs.append(af["max_abs_speed_diff_m_s"])
            d_vec.append(af["max_velocity_vector_diff_m_s"])
            d_abs_w.append(af["max_abs_speed_diff_in_station_windows_m_s"])
            d_vec_w.append(af["max_velocity_vector_diff_in_station_windows_m_s"])
            if s["worst"] is not None:
                worst_over.append({"contract_id": r["contract_id"], "member": m, **s["worst"]})
            b = d["boundary"]
            bexcess.append(b["excess"])
            balert += b["alert_transitions"]
    tube_over.sort(key=lambda x: -x["max_m"])
    worst_over.sort(key=lambda x: -x["over_m_s"])
    nt = [v for _, a in fin for v in a["nontarget"].values()]

    def split(key, rows):
        has = [r[key] for r in rows if any(not a["accepted"] for a in r["attempts"])]
        no = [r[key] for r in rows if all(a["accepted"] for a in r["attempts"])]
        return {"with_failed_attempt": quantile_summary(has), "without_failed_attempt": quantile_summary(no),
                "raw_with_failed_attempt": sorted(has)}

    walls = [r["timing"]["total_wall_s"] for r in allr if "total_wall_s" in r["timing"]]
    summary = {
        "stage": stage, "queue": list(queue), "subset": bool(subset), "p0_stop": p0,
        "wall_s": wall_s, "wall_budget_s": budget_s, "wall_budget_exceeded": bool(wall_s >= budget_s),
        "part4_successes": len(successes),
        "counts": {"stage_queue": len(queue), "stage_executed": len(results), "not_run": len(not_run),
                   "all_executed": len(executed), "retained": len(retained), "failed": len(failed),
                   "interrupted": len(interrupted), "rerun_equal": len(rerun_equal),
                   "rerun_mismatch": len(rerun_mismatch), "pending_rerun": len(pending_rerun),
                   "verified_retained": len(rerun_equal)},
        "not_run_ids": list(not_run),
        "incomplete": bool(not_run or interrupted or pending_rerun or p0 or subset),
        "retained_ratio_of_executed": _ratio(len(retained), len(executed)),
        "verified_ratio_of_part4_successes": _ratio(len(rerun_equal), len(successes)),
        "quick_selection": selection,
        "quick_coverage": None if not quick_results and stage != "quick" else {
            "facility_counts": _count(r["facility_count"] for r in (results if stage == "quick" else quick_results)),
            "group_sizes": _count(r["group_size"] for r in (results if stage == "quick" else quick_results)),
            "topologies": _count(r["topology"] for r in (results if stage == "quick" else quick_results)),
            "formations": _count(r["formation_realized"] for r in (results if stage == "quick" else quick_results))},
        "first_errors": first_errors,
        "attempt_failure": {"attempts": len(attempts), "failed_attempts": len(bad_att),
                            "rate": _ratio(len(bad_att), len(attempts)),
                            "contracts_with_failed_attempt": _ratio(
                                len({r["contract_id"] for r, _ in bad_att}), len(executed)),
                            "by_primary_code": _count(a["primary_code"] for _, a in bad_att),
                            "by_condition_and_code": dict(sorted(cond.items())),
                            "sim_timeouts": sum(1 for _, a in bad_att if "sim_timeout" in a["codes"])},
        "final_failures": [{"contract_id": r["contract_id"], "failure": r["failure"]} for r in failed],
        "strata": {"facility_count": _stratum(executed, "facility_count"),
                   "n_restricted_zones": _stratum(executed, "n_restricted_zones"),
                   "group_size": _stratum(executed, "group_size"), "topology": _stratum(executed, "topology"),
                   "formation_realized": _stratum(executed, "formation_realized")},
        "by_expected_speed": {"initial_speed_m_s": split("initial_speed_m_s", executed),
                              "plan_nominal_duration_s": split("plan_nominal_duration_s", executed)},
        "dwell_rejections": {"count": len(dwell), "items": dwell,
                             "meets_preset_min_radius": _count(d["meets_preset_min_radius"] for d in dwell)},
        "separation": {"retained_final_attempts": len(fin),
                       "min_sampled_m": quantile_summary(seps), "min_interpolated_m": quantile_summary(iseps),
                       "all_attempts_min_sampled_m": quantile_summary(all_seps),
                       "all_attempts_min_interpolated_m": quantile_summary(all_iseps),
                       "retained_below_2m": sum(1 for s in seps if s is not None and s < 2.0)},
        "restricted_and_layers": {
            "restricted_frames_total_retained": int(sum(sum(a["validity"]["restricted_frames"].values()) for _, a in fin)),
            "outside_world_frames_total_retained": int(sum(sum(a["validity"]["outside_world_frames"].values())
                                                          for _, a in fin)),
            "nontarget_max_level_retained": _count(v["max_level_nontarget"] for v in nt),
            "nontarget_frames_ge2_total_retained": int(sum(v["frames_ge2_nontarget"] for v in nt)),
            "target_max_level_retained": _count(v["max_level_target"] for v in nt)},
        "tracking_tube": {"members": len(tube_max), "max_m": quantile_summary(tube_max), "p95_m": quantile_summary(tube_p95),
                          "members_with_over_frames": len(tube_over), "worst_members": tube_over[:5],
                          "by_expected_speed_quartile": _quartile_bins(tube_entries)},
        "speed_overshoot": {"max_positive_over_m_s": quantile_summary(over_speed),
                            "members_with_positive_over": sum(1 for x in over_speed if x > 0),
                            "worst": worst_over[:3], "speed_max_m_s": quantile_summary(speed_max),
                            "adjacent_frame_max_abs_speed_diff_m_s": quantile_summary(d_abs),
                            "adjacent_frame_max_velocity_vector_diff_m_s": quantile_summary(d_vec),
                            "adjacent_frame_max_abs_speed_diff_in_station_windows_m_s": quantile_summary(d_abs_w),
                            "adjacent_frame_max_velocity_vector_diff_in_station_windows_m_s": quantile_summary(d_vec_w),
                            "v8_10_reference_m_s": 0.277},
        "boundary": {"members": len(bexcess), "excess_transitions": quantile_summary(bexcess),
                     "members_with_excess": sum(1 for x in bexcess if x > 0), "alert_transitions_total": balert},
        "timing": {"contract_total_wall_s": quantile_summary(walls),
                   "sum_first_run_wall_s": float(sum(r["timing"]["first_run_wall_s"] for r in allr)),
                   "sum_sim_wall_s": float(sum(r["timing"]["sim_wall_s"] for r in allr)),
                   "sum_replan_wall_s": float(sum(r["timing"]["replan_wall_s"] for r in allr)),
                   "sum_rerun_wall_s": float(sum(r["rerun"].get("wall_s", 0.0) for r in allr)),
                   "per_contract": {r["contract_id"]: {"first_s": r["timing"]["first_run_wall_s"],
                                                       "rerun_s": r["rerun"].get("wall_s", 0.0),
                                                       "attempts": len(r["attempts"]), "group_size": r["group_size"],
                                                       "plan_nominal_duration_s": r["plan_nominal_duration_s"]}
                                    for r in allr}},
        "rerun": {"equal": [r["contract_id"] for r in rerun_equal],
                  "mismatch": [{"contract_id": r["contract_id"], "mismatches": r["rerun"]["mismatches"]}
                               for r in rerun_mismatch],
                  "pending": [r["contract_id"] for r in pending_rerun],
                  "compared_components": ["plan_chain_sha256", "accepted_plan_digest", "attempts_json_sha256",
                                          "tracks", "verdict_json_sha256"],
                  "excluded": ["wall_s", "sim_wall_s", "diag_wall_s", "member_wall_s", "seconds", "planned_by",
                               "replan_wall_s", "路径名", "日志时间戳"]},
        "retained_attempt_index": _count(r["final_attempt"] for r in retained),
    }
    return summary
