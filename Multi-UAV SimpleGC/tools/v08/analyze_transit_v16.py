"""V8-16 只读统计（指令 7.3、7.4、8.1；本项新增）。不规划、不优化、不仿真，不写任何输入目录。

  --mode monitor-durations：既有 full_v14c 的保留监视合同（v15_artifacts.load_retained/phase_bounds 恢复），逐成员
      汇合/进入 = [release, 首巡逻站点)、巡逻 = [首, 末巡逻站点)、撤离 = [末巡逻站点, 移动结束]（member_map_v14 映射，
      不按最低速度猜）；三段相加 = ref.end_s − ref.release_s；另列 2 s 末端保持、release delay 与合同含保持跨度。
  --mode transit-report：监视/过境的骨架与全链路 records 做 200 键外连接（transit_report.paired_rows）；四格计数与
      人数/设施数/初速分档；attempts 分布（全部合同、双方成功两个口径）；过境三阶段时长与阶段速度；穿越段 Fréchet。
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

PROJ = Path(__file__).resolve().parents[2]
for p in (PROJ, PROJ / "tools" / "v08"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def qd(xs):
    xs = sorted(float(x) for x in xs if x is not None)
    if not xs:
        return None
    q = np.quantile(xs, [0.0, 0.1, 0.5, 0.9, 1.0])
    return {"n": len(xs), "min": float(q[0]), "p10": float(q[1]), "median": float(q[2]), "p90": float(q[3]),
            "max": float(q[4])}


def monitor_durations(args):
    import v15_artifacts as VA
    from v08.motion.optimize import load_settings, physical_limits
    from v08.runner.joint_report import group_bin, speed_bin
    from v08.runner.monitoring import load_entries
    from v08.scene.context import load_context
    hold = physical_limits(load_settings())["hold_s"]
    entries = {int(e["order"]): e for e in load_entries(args.devset)}
    recs = json.loads((Path(args.baseline) / "records.json").read_text(encoding="utf-8"))
    rows, contracts = [], []
    ctx = None
    for r in sorted(recs, key=lambda x: x["contract_id"]):
        if not r.get("success"):
            continue
        o = int(r["order"])
        if ctx is None or ctx.family.family_id != r["family_id"]:
            ctx = load_context(entries[o], data_root=Path(args.data_root), cache_dir=Path(args.cache))
        b = VA.load_retained(Path(args.baseline) / "contracts" / r["contract_id"], ctx)
        spans = []
        for m in sorted(b["plan"].members):
            pb = VA.phase_bounds(b, m)
            rel, end, a, bb = pb["release_s"], pb["end_s"], pb["t_patrol_a_s"], pb["t_patrol_b_s"]
            row = {"contract_id": r["contract_id"], "member": m, "group_size": r["group_size"],
                   "facility_count": r["facility_count"], "initial_speed_m_s": r["initial_speed_m_s"],
                   "collect_ingress_s": a - rel, "patrol_s": bb - a, "egress_s": end - bb, "travel_s": end - rel,
                   "closure_residual_s": (a - rel) + (bb - a) + (end - bb) - (end - rel),
                   "release_delay_s": float(b["plan"].members[m].release_delay_s), "hold_s": hold,
                   "error": pb["error"]}
            rows.append(row)
            spans.append((rel, end))
        contracts.append({"contract_id": r["contract_id"], "group_size": r["group_size"],
                          "facility_count": r["facility_count"], "initial_speed_m_s": r["initial_speed_m_s"],
                          "nominal_duration_s_with_hold": float(b["plan"].nominal_duration_s),
                          "group_motion_span_s": max(e for _, e in spans) - min(s for s, _ in spans),
                          "members": len(spans)})
    out = Path(args.out)
    with open(out / "monitor_member_phase_durations.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    keys = ("collect_ingress_s", "patrol_s", "egress_s", "travel_s", "release_delay_s")
    doc = {"contracts": len(contracts), "members": len(rows), "hold_s": hold,
           "member": {k: qd(r[k] for r in rows) for k in keys},
           "contract": {k: qd(c[k] for c in contracts) for k in ("nominal_duration_s_with_hold", "group_motion_span_s")},
           "closure_residual_abs_max_s": float(max(abs(r["closure_residual_s"]) for r in rows)),
           "negative_phase_members": sum(1 for r in rows if min(r[k] for k in keys[:3]) < 0),
           "over_1800_s": {"member_travel": sum(1 for r in rows if r["travel_s"] > 1800.0),
                           "contract_span_with_hold": sum(1 for c in contracts if c["nominal_duration_s_with_hold"] > 1800.0)},
           "by_bin": {}}
    for axis, f in (("group", lambda r: group_bin(r["group_size"])), ("facility", lambda r: int(r["facility_count"])),
                    ("speed", lambda r: speed_bin(r["initial_speed_m_s"]))):
        bins = {}
        for r in rows:
            bins.setdefault(str(f(r)), []).append(r)
        doc["by_bin"][axis] = {b: {k: qd(x[k] for x in rs) for k in keys[:4]} for b, rs in sorted(bins.items())}
    return doc


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8")) if p else None


def transit_report(args):
    from v08.runner.transit_report import four_cell, paired_rows
    ms, ts, mf, tf = (_load(args.monitor_skeleton), _load(args.transit_skeleton), _load(args.monitor_full),
                      _load(args.transit_full))
    rows = paired_rows(ms, ts, mf, tf)
    out = Path(args.out)
    with open(out / "paired_contracts.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in r.items()})
    both = [r for r in rows if r["monitor_full_success"] and r["transit_full_success"]]
    doc = {"keys": len(rows), "common_field_diff_rows": sum(1 for r in rows if r["common_field_diffs"]),
           "missing_field_rows": sum(1 for r in rows if r["missing_fields"]),
           "four_cell_full": {by or "all": four_cell(rows, by=by) for by in (None, "group_bin", "facility_count",
                                                                             "speed_bin")},
           "four_cell_skeleton": four_cell(rows, "monitor_skeleton_success", "transit_skeleton_success"),
           "attempts": {"all": {"monitor": qd(r["monitor_full_attempts"] for r in rows),
                                "transit": qd(r["transit_full_attempts"] for r in rows)},
                        "both_success": {"monitor": qd(r["monitor_full_attempts"] for r in both),
                                         "transit": qd(r["transit_full_attempts"] for r in both)}},
           "first_failed_stage": {"monitor": _count(r["monitor_first_failed_stage"] for r in rows),
                                  "transit": _count(r["transit_first_failed_stage"] for r in rows)},
           "group12_transit_failures": [r["contract_id"] for r in rows if (r["group_size"] or 0) >= 12
                                        and r["transit_full_success"] is False]}
    if tf:
        durs = [m for r in tf if r.get("success") for m in (r.get("phase_durations") or {}).values()
                if isinstance(m, dict) and "travel_s" in m]
        doc["transit_phase_durations"] = {k: qd(m[k] for m in durs) for k in (
            "transit_ingress_s", "transit_crossing_s", "transit_egress_s", "travel_s", "release_delay_s")}
        doc["transit_closure_residual_abs_max_s"] = float(max(abs(m["closure_residual_s"]) for m in durs)) if durs else None
        doc["transit_nominal_duration_s"] = qd(r.get("nominal_duration_s") for r in tf if r.get("success"))
        ph = {}
        for r in tf:
            for m, v in (r.get("phase_metrics") or {}).items():
                if not isinstance(v, dict) or "phases" not in v:
                    continue
                for name, rec in v["phases"].items():
                    ph.setdefault(name, []).append(rec)
        doc["transit_phase_speed"] = {name: {k: qd(x.get(k) for x in recs) for k in (
            "reference_min_m_s", "optimized_ratio", "measured_ratio", "optimized_along_max_m", "measured_along_max_m")}
            for name, recs in sorted(ph.items())}
        doc["transit_low_ratio_members"] = sorted(
            ({"contract_id": r["contract_id"], "member": m, "phase": name, "measured_ratio": rec.get("measured_ratio")}
             for r in tf for m, v in (r.get("phase_metrics") or {}).items() if isinstance(v, dict) and "phases" in v
             for name, rec in v["phases"].items() if rec.get("measured_ratio") is not None),
            key=lambda x: x["measured_ratio"])[:15]
    return doc


def _count(xs):
    out = {}
    for x in xs:
        out[str(x)] = out.get(str(x), 0) + 1
    return dict(sorted(out.items()))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("monitor-durations", "transit-report"), required=True)
    ap.add_argument("--out", required=True)
    for k in ("--baseline", "--devset", "--data-root", "--cache", "--monitor-skeleton", "--transit-skeleton",
              "--monitor-full", "--transit-full"):
        ap.add_argument(k)
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    doc = monitor_durations(args) if args.mode == "monitor-durations" else transit_report(args)
    (out / f"{args.mode}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in list(doc)[:4]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
