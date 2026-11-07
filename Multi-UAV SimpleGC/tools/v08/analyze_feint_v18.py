"""V8-18 只读统计（指令 7.2–7.3；本项新增）。不规划、不优化、不仿真，不写任何输入目录。

以原始 200 键 outer join 监视（full_v14c / skeleton_v14b）、过境（full_transit_r2 / skeleton_transit_r3）、突入（V8-17
full_r1 / 骨架）、佯动（本次全量 / 骨架）：成功/失败/缺记录、attempts、实现队形逐格列出；人数/设施/初速分档；倾向与实现
队形分开。突入 o34_d3 的旧证书行照常保留。另给 optimize_feint 子原因两张表：
  表 1：全部失败 attempt，同一 attempt 内同子类只计一次；
  表 2：每个合同时间顺序第一个失败 attempt；它是 optimize_feint 才列全部子类，其他首败阶段也列。
各表写分母；子类非互斥。另给阶段时长、种类/侧向（按非空组合分层）、A 与最深 protected SDF 分布（裁定 2 诊断）、L、
形变可观测量与 Fréchet 块。
用法：python -B tools/v08/analyze_feint_v18.py --out <新目录> --monitor-skeleton ... --transit-skeleton ...
      --intrusion-skeleton ... --feint-skeleton ... --monitor-full ... --transit-full ... --intrusion-full ... --feint-full <根>
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

INTENTS = ("monitoring", "transit", "intrusion", "feint")
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
    rows = _load(p)
    root = Path(p).parent
    for r in rows or []:
        f = root / "contracts" / r["contract_id"] / "result.json"
        if f.is_file():
            res = json.loads(f.read_text(encoding="utf-8"))
            r["attempt_log"] = res.get("attempt_log") or r.get("attempt_log")
            for k in ("intrusion", "feint"):
                if k in res:
                    r[k] = res[k]
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
    opt = a.get("optimize") or {}
    key = "monitoring_failures" if intent == "monitoring" else "semantic_failures"
    if key not in opt:
        return None
    return sorted({f.get("kind") for f in (opt.get(key) or []) if isinstance(f, dict)})


def joined(paths):
    from v08.runner.joint_report import group_bin, speed_bin
    sk = {i: _idx(_load(paths[f"{i}_skeleton"])) for i in INTENTS}
    fu = {i: _idx(_load_full(paths[f"{i}_full"])) for i in INTENTS}
    keys = sorted(set().union(*[set(d) for d in list(sk.values()) + list(fu.values())]))
    rows = []
    for k in keys:
        base = next((d[k] for d in list(fu.values()) + list(sk.values()) if k in d), {})
        row = {"family_id": k[0], "draw_index": k[1], "contract_id": base.get("contract_id"),
               "group_size": base.get("group_size"), "facility_count": base.get("facility_count"),
               "initial_speed_m_s": base.get("initial_speed_m_s"), "formation_prior": base.get("formation_prior")}
        row["group_bin"] = None if row["group_size"] is None else group_bin(row["group_size"])
        row["speed_bin"] = None if row["initial_speed_m_s"] is None else speed_bin(row["initial_speed_m_s"])
        diffs, missing = [], []
        for f in COMMON:
            vals = []
            for i in INTENTS:
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
        ff = fu["feint"].get(k) or {}
        turn = (ff.get("feint") or {}).get("turn") or {}
        row["feint_turn_kind"], row["feint_turn_side"], row["feint_radius_m"] = (turn.get("kind"), turn.get("side"),
                                                                                turn.get("radius_m"))
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
    for axis in ("group_bin", "facility_count", "speed_bin", "formation_prior"):
        bins = {}
        for r in rows:
            bins.setdefault(str(r.get(axis)), []).append(r)
        out[axis] = {b: {i: [sum(1 for x in rs if x[f"{i}_{kind}_success"]), len(rs)] for i in INTENTS}
                     for b, rs in sorted(bins.items())}
    return out


def feint_subreasons(full_rows):
    """表 1：全部失败 attempt（同一 attempt 同子类只计一次）；表 2：每合同时间顺序第一个失败 attempt。"""
    t1, n_att, n_opt = Counter(), 0, 0
    for r in full_rows:
        for a in r.get("attempt_log") or []:
            if a.get("ok"):
                continue
            n_att += 1
            if a.get("stage") == "optimize_feint":
                n_opt += 1
                ks = _kinds(a, "feint")
                t1.update(ks if ks is not None else [NOT_RECORDED])
    t2, n_fail = Counter(), 0
    for r in full_rows:
        st, a = _first_fail(r)
        if a is None:
            continue
        n_fail += 1
        if a.get("stage") == "optimize_feint":
            ks = _kinds(a, "feint")
            for k in (ks if ks is not None else [NOT_RECORDED]):
                t2[f"optimize_feint|{k}"] += 1
        else:
            t2[str(st)] += 1
    return {"table1_kinds": dict(t1.most_common()), "table1_denominator_failed_attempts": n_att,
            "table1_optimize_feint_attempts": n_opt,
            "table2_first_failed": dict(t2.most_common()), "table2_denominator_contracts_with_failure": n_fail,
            "note": "子类非互斥，合计可大于 attempt 数"}


def _skeleton_turns(feint_skel_root):
    """成功骨架的掉头选择与名义可观测量：读骨架 contracts/<id>/skeleton.json（只读）。"""
    out = []
    root = Path(feint_skel_root).parent
    for r in _load(feint_skel_root) or []:
        if not r.get("success"):
            continue
        p = root / "contracts" / r["contract_id"] / "skeleton.json"
        if not p.is_file():
            continue
        sk = json.loads(p.read_text(encoding="utf-8"))
        P = sk.get("proposal") or {}
        w = sk.get("witnesses") or {}
        out.append({"contract_id": r["contract_id"], "group_size": r.get("group_size"),
                    "realized": (r.get("formation") or {}).get("realized"), "turn": P.get("turn"),
                    "nonempty_combos": P.get("nonempty_combos"), "combos_found": P.get("combos_found"),
                    "L_m": P.get("L_m"), "l_star_m": P.get("l_star_m"),
                    "min_protected_sdf_m": min((v.get("min_protected_sdf_m") for v in (w.get("screen") or {}).values()
                                                if v.get("min_protected_sdf_m") is not None), default=None),
                    "curved": P.get("curved"), "fallback_reason": P.get("fallback_reason")})
    return out


def feint_details(full, div, summ, skel_turns):
    succ = [r for r in full if r.get("success")]
    pdur = [v for r in succ for v in (r.get("phase_durations") or {}).values() if isinstance(v, dict)]
    ph, deform = {}, {"support_start_alert_sdf_m": [], "deform_to_core_s": [], "lateral_minus_longitudinal_s": []}
    for r in succ:
        for v in (r.get("phase_metrics") or {}).values():
            if not isinstance(v, dict):
                continue
            for name, rec in (v.get("phases") or {}).items():
                ph.setdefault(name, []).append(rec)
            d = v.get("deformation") or {}
            deform["support_start_alert_sdf_m"].append(d.get("support_start_alert_sdf_m"))
            deform["deform_to_core_s"].append(d.get("deform_to_core_s"))
            if d.get("lateral_start_t_s") is not None and d.get("longitudinal_start_t_s") is not None:
                deform["lateral_minus_longitudinal_s"].append(d["lateral_start_t_s"] - d["longitudinal_start_t_s"])
    ent, meas_sdf = Counter(), []
    for r in succ:
        for m in ((r.get("feint") or {}).get("members") or {}).values():
            ent[json.dumps(m["entry_counts"], sort_keys=True)] += 1
            meas_sdf.append(m.get("min_protected_sdf_m"))
    strata = {}
    for t in skel_turns:
        k = str(t.get("nonempty_combos"))
        strata.setdefault(k, Counter())[f"{(t.get('turn') or {}).get('kind')}:{(t.get('turn') or {}).get('side')}"] += 1
    L_by = {}
    for t in skel_turns:
        L_by.setdefault(f"{t['realized']}|n{t['group_size']}", []).append(t.get("L_m"))
    doc = {"successes": len(succ), "members": len(pdur),
           "phase_durations": {k: qd(v[k] for v in pdur) for k in ("feint_ingress_s", "feint_work_s", "feint_egress_s",
                                                                    "travel_s", "release_delay_s")},
           "closure_residual_abs_max_s": max((abs(v["closure_residual_s"]) for v in pdur), default=None),
           "nominal_duration_s": qd(r.get("nominal_duration_s") for r in succ),
           "phase_speed": {n: {k: qd(x.get(k) for x in recs) for k in (
               "reference_min_m_s", "optimized_ratio", "measured_ratio", "optimized_along_max_m",
               "measured_along_max_m")} for n, recs in sorted(ph.items())},
           "deformation": {k: qd(v) for k, v in deform.items()},
           "measured_entry_counts": dict(ent), "measured_min_protected_sdf_m": qd(meas_sdf),
           "realized_by_prior": dict(Counter(f"{(r.get('formation') or {}).get('prior')}->"
                                             f"{(r.get('formation') or {}).get('realized')}" for r in succ)),
           "curved": dict(Counter(str((r.get("topology") or {}).get("curved")) for r in succ)),
           "optimization_s": qd(r.get("optimization_s") for r in full),
           "skeleton_turns": {"n": len(skel_turns),
                              "kind_side": dict(Counter(f"{(t.get('turn') or {}).get('kind')}:"
                                                        f"{(t.get('turn') or {}).get('side')}" for t in skel_turns)),
                              "kind_side_by_nonempty_combos": {k: dict(c) for k, c in sorted(strata.items())},
                              "A_m": qd((t.get("turn") or {}).get("A_m") for t in skel_turns),
                              "radius_m": qd((t.get("turn") or {}).get("radius_m") for t in skel_turns),
                              "min_protected_sdf_m": qd(t.get("min_protected_sdf_m") for t in skel_turns),
                              "L_m_by_formation_size": {k: qd(v) for k, v in sorted(L_by.items())},
                              "note": "裁定 2：只作诊断，不声称 A 或种类边缘分布严格均匀"}}
    blocks = summ.get("frechet_blocks_after") or []
    doc["frechet"] = {"pooled_after": summ.get("frechet_after_pooled"), "pooled_before": summ.get("frechet_before_pooled"),
                      "pairs": sum(len(b["distances_m"]) for b in blocks),
                      "families": [{k: b.get(k) for k in ("family_id", "attempted", "success", "comparable", "spacing_m",
                                                          "na_reasons", "scope")} | {"pairs": len(b["distances_m"])}
                                   for b in blocks]}
    doc["diversity"] = {"rows": len(div), "success": sum(1 for r in div if r.get("success")),
                        "errors": [r["contract_id"] for r in div if r.get("error")],
                        "incomplete": [r["contract_id"] for r in div if r.get("incomplete")],
                        "frechet_na": dict(Counter(str(r.get("frechet_na")) for r in div
                                                   if r.get("success") and r.get("curve_after") is None))}
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    for i in INTENTS:
        ap.add_argument(f"--{i}-skeleton", required=True, help="骨架 records.json")
        ap.add_argument(f"--{i}-full", required=True, help="全量 records.json（佯动给全量根）")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    froot = Path(args.feint_full)
    paths = {f"{i}_{k}": getattr(args, f"{i}_{k}") for i in INTENTS for k in ("skeleton", "full")}
    paths["feint_full"] = str(froot / "records.json")
    rows = joined(paths)
    with open(out / "four_intent_contracts.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in r.items()})
    full = _load_full(paths["feint_full"]) or []
    summ = _load(froot / "summary.json")
    div = _load(froot / "diversity" / "records.json")
    doc = {"keys": len(rows), "common_field_diff_rows": [r["contract_id"] for r in rows if r["common_field_diffs"]],
           "missing_field_rows": [r["contract_id"] for r in rows if r["missing_fields"]],
           "pattern_full": {by or "all": pattern_counts(rows, "full", by) for by in (None, "group_bin", "facility_count",
                                                                                    "speed_bin")},
           "pattern_skeleton": pattern_counts(rows, "skeleton"),
           "success_by_bin_full": success_by_bin(rows, "full"),
           "attempts": {i: qd(r[f"{i}_full_attempts"] for r in rows) for i in INTENTS},
           "first_failed_stage": {i: dict(Counter(str(r[f"{i}_first_failed_stage"]) for r in rows)) for i in INTENTS},
           "feint_subreasons": feint_subreasons(full),
           "special_rows": [r for r in rows if r["contract_id"] in ("o34_d3", "o17_d1", "o17_d4")],
           "nominal_duration_s": {i: qd(r[f"{i}_nominal_duration_s"] for r in rows if r[f"{i}_full_success"])
                                  for i in INTENTS},
           "feint": feint_details(full, div or [], summ or {}, _skeleton_turns(paths["feint_skeleton"]))}
    (out / "feint_report.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n",
                                           encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("keys", "common_field_diff_rows", "missing_field_rows", "pattern_skeleton")},
                     ensure_ascii=False))
    print(json.dumps(doc["pattern_full"]["all"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
