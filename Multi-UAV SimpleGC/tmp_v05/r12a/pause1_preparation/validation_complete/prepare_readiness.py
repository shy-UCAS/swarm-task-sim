import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.build_v05_pause1_report import *

folder = ROOT / "tmp_v05/r12a/pause1_preparation/validation_complete"
d = read(folder / "diagnostics/report.json")
v = read(VAL / "control.json")
vr2 = next(r for r in d["runs"] if r["case_id"] == "VR2")
a = Path(vr2["analysis_directory"])
e = read(a / "execution_metrics.json")
fallbacks = [dict(case_id=r["case_id"], agent_id=x["agent_id"], channel=c,
                  arrival_s=w["arrival_s"], source=w["arrival_source"],
                  verified=w["arrival_verified"], reason=w.get("arrival_reason"))
             for r in d["runs"] for x in r["approach"] for c, w in x["channels"].items()
             if w["arrival_source"] != "trajectory_stop"]
readiness = dict(
    scope="validation complete; pilot in progress; NOT Pause 1 acceptance",
    validation_completed=v["completed"], validation_budget_consumed=v["sitl_attempts_consumed"],
    validation_run_count=len(d["runs"]),
    all_validation_hard_pass=all(r["validation_policy"]["individual_pass"] for r in d["runs"]),
    all_validation_quality_eligible=all(r["episode_quality_eligible"] for r in d["runs"]),
    approach_agents=sum(len(r["approach"]) for r in d["runs"]),
    approach_rows_by_channel=sum(len(x["channels"]) for r in d["runs"] for x in r["approach"]),
    all_headings_zero=all(x["initial_heading_deg"] == 0 for r in d["runs"] for x in r["approach"]),
    missing_approach_numeric=[dict(case_id=r["case_id"], agent_id=x["agent_id"], channel=c, field=k)
        for r in d["runs"] for x in r["approach"] for c, w in x["channels"].items()
        for k in ["start_s", "arrival_s", "sampled_horizontal_path_length_m"] if w.get(k) is None],
    approach_arrival_fallbacks=fallbacks,
    soft_flags_by_case={r["case_id"]: r["validation_policy"]["soft_flags"] for r in d["runs"]},
    vr2_no_soft_flags_confirmed=vr2["validation_policy"]["soft_flags"] == [],
    vr2_detail=dict(run_id=vr2["run_id"], hard_checks=vr2["validation_policy"]["hard_checks"],
        AV1={k: e["intermediate_waypoints"][k] for k in ["total_count", "stopped_count", "unknown_count", "stop_rate"]},
        AV2=vr2["AV2_episode"], phase_metrics=vr2["phase_metrics"]),
    ready_evidence=["M0 including issue 6 source binding", "H/R/T/M/P/L offline evidence",
        "r1.2a M03 reassessment and original 0.05s exceedance evidence",
        "v05/v05b/v05c DR and selection bias", "five validation acceptance rows",
        "16-agent approach diagnostics / 32 channel arrivals",
        "intent/phase/source AC4 and AV1/AV2/laps distributions for validation",
        "1000-sample historical numbering audit and accepted130 / first10 scene Wilson intervals"],
    awaiting_actual_pilot_completion=["20-run acceptance and 10-pair eligibility",
        "dataset export and audit", "describe completeness and consistency", "loader checks",
        "pilot execution distributions and approach diagnostics",
        "combined validation/pilot soft metrics distributions",
        "five actual descriptions spanning intents and template partitions; include failure/unclear if exists",
        "fact channel disagreement counts", "disk/runtime extrapolation based on actual20"],
    source_sha256={str(p.resolve()): file_hash(p) for p in [VAL / "control.json",
        folder / "diagnostics/report.json", folder / "ac4_sources.json", a / "quality.json",
        a / "execution_metrics.json", Path(__file__)]})
save(folder / "evidence_readiness.json", readiness)
print(json.dumps(dict(validation_run_count=readiness["validation_run_count"],
    approach_agents=readiness["approach_agents"], arrival_fallbacks=fallbacks,
    vr2_no_soft_flags_confirmed=readiness["vr2_no_soft_flags_confirmed"]), ensure_ascii=False))
