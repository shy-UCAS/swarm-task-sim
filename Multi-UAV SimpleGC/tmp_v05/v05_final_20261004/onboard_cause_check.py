"""Read-only classification of the 7 quality-ineligible runs' onboard-parameter check.

For each run it reports whether the onboard mission parameter check failed because
(A) parameters were read and differ from the plan (mismatch), or
(B) they could not be verified (unknown: clock mapping unavailable / log alignment).

Writes tmp_v05/v05_final_20261004/onboard_cause_check.json.
"""
import collections
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BATCH = ROOT / "verification/v05_batch_20261002"

LABELS = ["B037", "B085", "B125", "B135", "B156", "B190", "B201"]
RUN_IDS = {
    "B037": "20261003T105214Z_fc0da71d", "B085": "20261003T183204Z_d8dab159",
    "B125": "20261004T142817Z_6fe3345d", "B135": "20261004T151251Z_6cfa3d43",
    "B156": "20261004T165156Z_a0d985eb", "B190": "20261004T191528Z_e277e726",
    "B201": "20261004T200803Z_7c34aa26"}
control = json.load(open(BATCH / "control.json", encoding="utf-8"))
by_id = {r["run_id"]: r for r in control["records"]}

out = {}
for label in LABELS:
    rid = RUN_IDS[label]
    rec = by_id[rid]
    adir = Path(rec["analysis_directory"])
    onboard = json.load(open(adir / "onboard_mission_param_check.json", encoding="utf-8"))
    quality = json.load(open(adir / "quality.json", encoding="utf-8"))
    clocks = json.load(open(adir / "clock_models.json", encoding="utf-8"))
    reasons = collections.Counter(r.get("reason") for r in onboard["rows"])
    statuses = collections.Counter(r.get("status") for r in onboard["rows"])
    agent_clocks = {}
    for agent, model in (clocks.get("agents") or clocks.get("per_agent") or {}).items():
        if isinstance(model, dict):
            agent_clocks[agent] = {k: model.get(k) for k in
                                   ("available", "grade", "reason", "source_range_s", "speedup") if k in model}
    out[label] = dict(
        run_id=rid, scenario=rec["mission_id"], intent=rec["intent"],
        analysis_directory=str(adir),
        onboard_status=onboard["status"], onboard_pass_gate=onboard["pass_gate"],
        counts=onboard["counts"], read_errors=onboard["read_errors"],
        row_statuses={str(k): v for k, v in statuses.items()},
        row_reasons={str(k): v for k, v in reasons.items()},
        classification=("A_mismatch" if onboard["counts"]["mismatch_count"] else
                        "B_unverifiable" if onboard["counts"]["unknown_count"] else "pass"),
        clock_quality=quality.get("clock_quality"),
        observation_valid_fraction=quality.get("observation_valid_fraction"),
        truth_valid_fraction=quality.get("truth_valid_fraction"),
        frames=quality.get("frames"),
        data_quality_pass=quality.get("data_quality_pass"),
        truth_available_pass=quality.get("truth_available_pass"),
        timing_diagnostic_pass=quality.get("timing_diagnostic_pass"),
        truth_separation_status=(quality.get("truth_separation") or {}).get("status"),
        observation_window=quality.get("observation_window"),
        clock_models_keys=sorted(clocks.keys()),
        clock_models_agents=agent_clocks,
        clock_models_top={k: v for k, v in clocks.items() if not isinstance(v, (dict, list))},
    )
print(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True))
(HERE / "onboard_cause_check.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
print("written:", HERE / "onboard_cause_check.json")
