"""只读导出两张失败表与同键同成员观测配对；L=0按指令定义为无真实形变，不改原合同。"""
import csv
import json
from pathlib import Path

from collect_lazy_evidence import distribution

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
RUN = BASE / "_handoff/2026-11-06_V8-18_feint/run"
FULL = RUN / "out/full_lazy_r1"
INTRUSION = BASE / "_handoff/2026-11-06_V8-17_intrusion/run/out/full/full_r1"
OUT = RUN / "diagnostics/observables_paired_lazy_r1"
OUT.mkdir(parents=True, exist_ok=False)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(name, rows):
    with (OUT / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


report = read(RUN / "diagnostics/four_intent_lazy_r1/feint_report.json")
fail = report["feint_subreasons"]
write_csv("all_failed_attempt_subreasons.csv", [
    {"subreason": k, "attempts": v, "denominator_all_failed_attempts": fail["table1_denominator_failed_attempts"],
     "optimize_feint_failed_attempts": fail["table1_optimize_feint_attempts"], "nonexclusive": True}
    for k, v in fail["table1_kinds"].items()])
write_csv("first_failed_attempt_per_contract.csv", [
    {"first_failed_stage_or_subreason": k, "contracts": v,
     "denominator_contracts_with_failure": fail["table2_denominator_contracts_with_failure"], "nonexclusive": True}
    for k, v in fail["table2_first_failed"].items()])

intrusion_records = {r["contract_id"]: r for r in read(INTRUSION / "records.json")}
rows, zero_contracts, raw_false_flags, raw_zero_times = [], set(), 0, 0
for record in read(FULL / "records.json"):
    cid = record["contract_id"]
    saved = read(FULL / "contracts" / cid / "result.json")
    skeleton = read(FULL / "contracts" / cid / "skeleton.json")
    length = float(skeleton["proposal"]["L_m"])
    zero = length == 0.0
    if zero:
        zero_contracts.add(cid)
    old = read(INTRUSION / "contracts" / cid / "result.json")
    old_record = intrusion_records[cid]
    for member in record["member_ids"]:
        raw = (saved.get("phase_metrics") or {}).get(member, {}).get("deformation") or {}
        deform = dict(raw)
        if zero:
            raw_false_flags += int(not raw.get("no_deformation", False))
            raw_zero_times += int(raw.get("lateral_start_t_s") is not None or raw.get("longitudinal_start_t_s") is not None)
            for field in ("support_start_member_s", "support_start_alert_sdf_m", "deform_to_core_s",
                          "lateral_start_t_s", "longitudinal_start_t_s"):
                deform[field] = None
        release = ((record.get("phase_durations") or {}).get(member) or {}).get("release_s")
        old_release = ((old_record.get("phase_durations") or {}).get(member) or {}).get("release_s")
        terminal = ((old.get("phase_metrics") or {}).get(member) or {}).get("terminal_deceleration") or {}
        nominal, optimized, measured = (terminal.get(k) or {} for k in ("nominal", "optimized", "measured"))
        lateral, longitudinal = deform.get("lateral_start_t_s"), deform.get("longitudinal_start_t_s")
        start = nominal.get("t_start_s")
        rows.append({"contract_id": cid, "member_id": member, "group_size": record["group_size"],
            "feint_success": True, "intrusion_success": old["success"], "feint_L_m": length,
            "feint_group_has_deformation": not zero,
            "feint_support_start_alert_sdf_m": deform.get("support_start_alert_sdf_m"),
            "feint_deform_to_core_s": deform.get("deform_to_core_s"),
            "feint_lateral_start_t_s": lateral, "feint_longitudinal_start_t_s": longitudinal,
            "feint_lateral_start_since_release_s": None if lateral is None or release is None else lateral - release,
            "feint_longitudinal_start_since_release_s": None if longitudinal is None or release is None else longitudinal - release,
            "feint_lateral_minus_longitudinal_s": None if lateral is None or longitudinal is None else lateral - longitudinal,
            "raw_no_deformation": raw.get("no_deformation"),
            "raw_lateral_start_t_s": raw.get("lateral_start_t_s"),
            "raw_longitudinal_start_t_s": raw.get("longitudinal_start_t_s"),
            "intrusion_terminal_sigma": (old.get("intrusion") or {}).get("sigma"),
            "intrusion_nominal_decel_start_t_s": start,
            "intrusion_nominal_decel_start_since_release_s": None if start is None or old_release is None else start - old_release,
            "intrusion_nominal_decel_duration_s": nominal.get("duration_s"),
            "intrusion_optimized_decel_start_t_s": optimized.get("t_start_s"),
            "intrusion_optimized_decel_layer": optimized.get("layer"),
            "intrusion_optimized_decel_protected_sdf_m": optimized.get("protected_signed_m"),
            "intrusion_measured_decel_start_t_s": measured.get("t_start_s"),
            "intrusion_measured_decel_layer": measured.get("layer"),
            "intrusion_measured_decel_protected_sdf_m": measured.get("protected_signed_m"),
            "intrusion_missing_reason": None if old["success"] else (old.get("failure") or {}).get("code")})
write_csv("member_observables_paired.csv", rows)
summary = {"rows": len(rows), "contracts": 200, "L_zero_contracts": len(zero_contracts),
    "L_zero_members": sum(not r["feint_group_has_deformation"] for r in rows),
    "raw_L_zero_no_deformation_false_members": raw_false_flags,
    "raw_L_zero_nonnull_start_time_members": raw_zero_times,
    "feint_real_deformation": {key: distribution(r[key] for r in rows) for key in (
        "feint_support_start_alert_sdf_m", "feint_deform_to_core_s", "feint_lateral_minus_longitudinal_s")},
    "intrusion_paired_success_members": sum(r["intrusion_success"] for r in rows),
    "intrusion_nominal_decel_since_release_s": distribution(r["intrusion_nominal_decel_start_since_release_s"] for r in rows),
    "scope": "同cid/member outer pairing；feint L=0真实形变观测为None；原合同字段保留raw列，未改生产数据；突入沿原sigma及terminal_deceleration定义，不新增起点阈值。",
    "review_required": "原phase_metrics在L=0时仍有形式时刻，且部分no_deformation标志为False；本CSV按指令规范化，是否统一生产合同字段交审查方裁定。"}
(OUT / "observables_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False))
