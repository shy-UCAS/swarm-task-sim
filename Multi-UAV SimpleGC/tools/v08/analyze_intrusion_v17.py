"""V8-17 只读统计（指令 7.2–7.4；本项新增）。不规划、不优化、不仿真，不写任何输入目录。

以原始 200 键 outer join 监视（full_v14c / skeleton_v14b）、过境（full_transit_r2 / skeleton_transit_r3）、突入（本次全量 /
骨架）：每键公共字段、三意图骨架与全链成功、attempts、首失败阶段与子原因、实现队形、σ、时长；人数/设施/初速分档。
o34_d3、o17_d1/d4 原样留行。另给突入 optimize_intrusion 失败两张表（全部失败 attempt 的 kind 出现次数；每合同第一次
失败 attempt），物理/语义/仿真与冻结核验失败分开；旧证据没有某项时记"旧证据未记录"。
用法：python -B tools/v08/analyze_intrusion_v17.py --out <新目录> --monitor-skeleton ... --transit-skeleton ...
      --intrusion-skeleton ... --monitor-full ... --transit-full ... --intrusion-full <全量根>
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

PROJ = Path(__file__).resolve().parents[2]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

INTENTS = ("monitoring", "transit", "intrusion")
COMMON = ("group_id", "member_ids", "target_id", "initial_speed_m_s", "formation_prior", "group_size", "facility_count")
NOT_RECORDED = "旧证据未记录"


def qd(xs):
    xs = sorted(float(x) for x in xs if x is not None)
    if not xs:
        return None
    q = np.quantile(xs, [0.0, 0.1, 0.5, 0.9, 1.0])
    return {"n": len(xs), "min": float(q[0]), "p10": float(q[1]), "median": float(q[2]), "p90": float(q[3]),
            "max": float(q[4])}


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8")) if p else None


def _load_full(p):
    """全量 records.json 的 attempt_log 是精简版；完整确定性 attempt_log（含 optimize.semantic_failures /
    monitoring_failures）在同根 contracts/<id>/result.json，逐合同读入替换（只读）。"""
    rows = _load(p)
    root = Path(p).parent
    for r in rows or []:
        f = root / "contracts" / r["contract_id"] / "result.json"
        if f.is_file():
            res = json.loads(f.read_text(encoding="utf-8"))
            r["attempt_log"] = res.get("attempt_log") or r.get("attempt_log")
            if "intrusion" in res:
                r["intrusion"] = res["intrusion"]
            r["_attempt_log_source"] = "contracts/result.json"
    return rows


def _idx(rows):
    return {(r["family_id"], int(r["draw_index"])): r for r in rows or [] if r.get("branch") is None}


def _first_fail(r):
    if r is None:
        return None, None
    for a in r.get("attempt_log") or []:
        if not a.get("ok"):
            st = a.get("stage")
            if st == "skeleton" and a.get("skeleton_stage"):
                st = f"skeleton:{a['skeleton_stage']}"
            return st, a
    return None, None


def _kinds(a, intent):
    """一个失败 attempt 的语义 kind 集合；旧监视证据字段为 monitoring_failures，缺字段返回 None（未记录）。"""
    opt = a.get("optimize") or {}
    key = "monitoring_failures" if intent == "monitoring" else "semantic_failures"
    if key not in opt:
        return None
    return sorted({f.get("kind") for f in (opt.get(key) or []) if isinstance(f, dict)})


def _category(a):
    st = a.get("stage") or ""
    if st == "skeleton":
        return "skeleton"
    if st == "optimize":
        return "optimize_physical"
    if st.startswith("optimize_"):
        return "optimize_semantic"
    if st in ("simulation", "verify_segments", "validity", "measured_intrusion_entries"):
        return "post_simulation"
    return st or "unknown"


def joined(args):
    from v08.runner.joint_report import group_bin, speed_bin
    sk = {i: _idx(_load(p)) for i, p in zip(INTENTS, (args.monitor_skeleton, args.transit_skeleton,
                                                      args.intrusion_skeleton))}
    fu = {i: _idx(_load_full(p)) for i, p in zip(INTENTS, (args.monitor_full, args.transit_full, args.intrusion_full))}
    keys = sorted(set().union(*[set(d) for d in list(sk.values()) + list(fu.values())]))
    rows = []
    for k in keys:
        base = next((d[k] for d in list(fu.values()) + list(sk.values()) if k in d), {})
        row = {"family_id": k[0], "draw_index": k[1], "contract_id": base.get("contract_id"),
               "group_size": base.get("group_size"), "facility_count": base.get("facility_count"),
               "initial_speed_m_s": base.get("initial_speed_m_s")}
        row["group_bin"] = None if row["group_size"] is None else group_bin(row["group_size"])
        row["speed_bin"] = None if row["initial_speed_m_s"] is None else speed_bin(row["initial_speed_m_s"])
        diffs, missing = [], []
        for f in COMMON:
            vals = []
            for i in INTENTS:                       # 全量记录优先；全量行没有该字段（如 group_id）时取同意图骨架记录
                v = (fu[i].get(k) or {}).get(f)
                vals.append(v if v is not None else (sk[i].get(k) or {}).get(f))
            if any(v is None for v in vals):
                missing.append(f)
            elif any(v != vals[0] for v in vals[1:]):
                diffs.append(f)
        row["common_field_diffs"], row["missing_fields"] = diffs, missing
        for i in INTENTS:
            s, f = sk[i].get(k), fu[i].get(k)
            row[f"{i}_skeleton_success"] = None if s is None else bool(s.get("success"))
            row[f"{i}_full_success"] = None if f is None else bool(f.get("success"))
            row[f"{i}_skeleton_attempts"] = None if s is None else s.get("attempts")
            row[f"{i}_full_attempts"] = None if f is None else f.get("attempts")
            row[f"{i}_post_opt_failures"] = None if f is None else f.get("post_optimization_failures")
            st, a = _first_fail(f)
            row[f"{i}_first_failed_stage"] = st
            row[f"{i}_first_failed_kinds"] = None if a is None else _kinds(a, i)
            row[f"{i}_failure_code"] = None if f is None else (f.get("failure") or {}).get("code")
            row[f"{i}_realized"] = None if f is None else (f.get("formation") or {}).get("realized")
            row[f"{i}_nominal_duration_s"] = None if f is None else f.get("nominal_duration_s")
        fi = fu["intrusion"].get(k) or {}
        row["intrusion_sigma"] = (fi.get("topology") or {}).get("sigma")
        pd = [v for v in (fi.get("phase_durations") or {}).values() if isinstance(v, dict)]
        row["intrusion_ingress_s_median"] = qd(v["intrusion_ingress_s"] for v in pd)["median"] if pd else None
        row["intrusion_inside_s_median"] = qd(v["intrusion_inside_s"] for v in pd)["median"] if pd else None
        rows.append(row)
    return rows


def pattern_counts(rows, kind="full", by=None):
    out = {}
    for r in rows:
        g = "all" if by is None else str(r.get(by))
        pat = "".join("?" if r[f"{i}_{kind}_success"] is None else ("S" if r[f"{i}_{kind}_success"] else "F")
                      for i in INTENTS)
        out.setdefault(g, Counter())[pat] += 1
    return {g: dict(sorted(c.items())) for g, c in sorted(out.items())}


def success_by_bin(rows, kind="full"):
    out = {}
    for axis in ("group_bin", "facility_count", "speed_bin"):
        bins = {}
        for r in rows:
            bins.setdefault(str(r.get(axis)), []).append(r)
        out[axis] = {b: {i: [sum(1 for x in rs if x[f"{i}_{kind}_success"]), len(rs)] for i in INTENTS}
                     for b, rs in sorted(bins.items())}
    return out


def subreasons(full_rows, intent):
    """表 1：全部失败 attempt 中各 semantic kind 出现次数（同 attempt 同 kind 只计一次，可多 kind）；
    表 2：每个合同第一次失败 attempt 的阶段及全部 kind（分母为有失败的合同数）。另给失败类别（物理/语义/仿真后）计数。"""
    t1, cat, unrec = Counter(), Counter(), 0
    for r in full_rows:
        for a in r.get("attempt_log") or []:
            if a.get("ok"):
                continue
            cat[_category(a)] += 1
            ks = _kinds(a, intent)
            if _category(a) == "optimize_semantic":
                if ks is None:
                    unrec += 1
                else:
                    t1.update(ks)
    t2, n_fail = Counter(), 0
    for r in full_rows:
        st, a = _first_fail(r)
        if a is None:
            continue
        n_fail += 1
        if _category(a) != "optimize_semantic":
            t2[f"{st}|（非语义失败，无 kind）"] += 1
            continue
        ks = _kinds(a, intent)
        t2[f"{st}|{','.join(ks) if ks else ('-' if ks is not None else NOT_RECORDED)}"] += 1
    return {"table1_failed_attempt_kinds": dict(t1.most_common()), "table1_semantic_attempts_unrecorded": unrec,
            "failure_categories": dict(cat.most_common()),
            "table2_first_failed_attempt": dict(t2.most_common()), "table2_denominator_contracts_with_failure": n_fail}


def intrusion_details(full, div, summ):
    succ = [r for r in full if r.get("success")]
    pdur = [v for r in succ for v in (r.get("phase_durations") or {}).values() if isinstance(v, dict)]
    ph, br_layer, br_signed, nom = {}, Counter(), [], []
    for r in succ:
        for v in (r.get("phase_metrics") or {}).values():
            if not isinstance(v, dict):
                continue
            for name, rec in (v.get("phases") or {}).items():
                ph.setdefault(name, []).append(rec)
            td = v.get("terminal_deceleration") or {}
            o = td.get("optimized")
            if o:
                br_layer[str(o.get("layer"))] += 1
                br_signed.append(o.get("protected_signed_m"))
            if td.get("nominal"):
                nom.append(td["nominal"]["duration_s"])
    ent = Counter()
    for r in succ:
        for m in ((r.get("intrusion") or {}).get("members") or {}).values():
            ent[json.dumps(m["entry_counts"], sort_keys=True)] += 1
    doc = {"successes": len(succ), "members": len(pdur),
           "phase_durations": {k: qd(v[k] for v in pdur) for k in ("intrusion_ingress_s", "intrusion_inside_s",
                                                                    "travel_s", "release_delay_s")},
           "closure_residual_abs_max_s": max((abs(v["closure_residual_s"]) for v in pdur), default=None),
           "nominal_duration_s": qd(r.get("nominal_duration_s") for r in succ),
           "phase_speed": {n: {k: qd(x.get(k) for x in recs) for k in (
               "reference_min_m_s", "optimized_ratio", "measured_ratio", "optimized_along_max_m",
               "measured_along_max_m")} for n, recs in sorted(ph.items())},
           "nominal_terminal_decel_duration_s": qd(nom),
           "optimized_brake_start_layer": dict(br_layer),
           "optimized_brake_start_protected_signed_m": qd(br_signed),
           "measured_entry_counts": dict(ent),
           "realized_by_prior": dict(Counter(f"{(r.get('formation') or {}).get('prior')}->"
                                             f"{(r.get('formation') or {}).get('realized')}" for r in succ)),
           "sigma_hist": dict(Counter(str((r.get("topology") or {}).get("sigma")) for r in succ)),
           "curved": dict(Counter(str((r.get("topology") or {}).get("curved")) for r in succ)),
           "optimization_s": qd(r.get("optimization_s") for r in full)}
    blocks = summ.get("frechet_blocks_after") or []
    doc["frechet"] = {"pooled_after": summ.get("frechet_after_pooled"), "pooled_before": summ.get("frechet_before_pooled"),
                      "pairs": sum(len(b["distances_m"]) for b in blocks),
                      "families": [{k: b.get(k) for k in ("family_id", "attempted", "success", "comparable", "spacing_m",
                                                          "na_reasons", "scope")} | {"pairs": len(b["distances_m"])}
                                   for b in blocks],
                      "endpoint_m": qd(x for b in blocks for e in b.get("endpoint_m") or []
                                       for x in (e.values() if isinstance(e, dict) else [e]))}
    doc["diversity"] = {"rows": len(div), "success": sum(1 for r in div if r.get("success")),
                        "errors": [r["contract_id"] for r in div if r.get("error")],
                        "incomplete": [r["contract_id"] for r in div if r.get("incomplete")],
                        "frechet_na": dict(Counter(str(r.get("frechet_na")) for r in div
                                                   if r.get("success") and r.get("curve_after") is None))}
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    for k in ("--monitor-skeleton", "--transit-skeleton", "--intrusion-skeleton", "--monitor-full", "--transit-full"):
        ap.add_argument(k, required=True)
    ap.add_argument("--intrusion-full", required=True, help="突入全量根（含 records.json、diversity/、summary.json）")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    froot = Path(args.intrusion_full)
    args.intrusion_full = str(froot / "records.json")
    rows = joined(args)
    with open(out / "three_intent_contracts.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in r.items()})
    fulls = {i: _load_full(p) for i, p in zip(INTENTS, (args.monitor_full, args.transit_full, args.intrusion_full))}
    summ = _load(froot / "summary.json")
    div = _load(froot / "diversity" / "records.json")
    doc = {"keys": len(rows), "common_field_diff_rows": [r["contract_id"] for r in rows if r["common_field_diffs"]],
           "missing_field_rows": [r["contract_id"] for r in rows if r["missing_fields"]],
           "pattern_full": {by or "all": pattern_counts(rows, "full", by) for by in (None, "group_bin", "facility_count",
                                                                                    "speed_bin")},
           "pattern_skeleton": pattern_counts(rows, "skeleton"),
           "success_by_bin_full": success_by_bin(rows, "full"),
           "attempts": {i: {"all": qd(r[f"{i}_full_attempts"] for r in rows),
                            "all_three_success": qd(r[f"{i}_full_attempts"] for r in rows
                                                    if all(r[f"{j}_full_success"] for j in INTENTS))}
                        for i in INTENTS},
           "first_failed_stage": {i: dict(Counter(str(r[f"{i}_first_failed_stage"]) for r in rows)) for i in INTENTS},
           "subreasons": {i: subreasons(fulls[i] or [], i) for i in INTENTS},
           "special_rows": [r for r in rows if r["contract_id"] in ("o34_d3", "o17_d1", "o17_d4")],
           "nominal_duration_s": {i: qd(r[f"{i}_nominal_duration_s"] for r in rows if r[f"{i}_full_success"])
                                  for i in INTENTS},
           "intrusion": intrusion_details(fulls["intrusion"], div, summ)}
    (out / "intrusion_report.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n",
                                               encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("keys", "common_field_diff_rows", "missing_field_rows", "pattern_skeleton")},
                     ensure_ascii=False))
    print(json.dumps(doc["pattern_full"]["all"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
