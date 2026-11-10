"""Analyze every fixed main contract and all available diversity diagnostics."""
import collections
import datetime
import math
import numpy as np
from evidence_utils import *
from v08.criteria.validity import check_validity, visible_track
from v08.scene.context import load_context
from v08.sim.types import MemberTrack
from v08.motion.area_search_geometry import member_split_points
from v08.runner.area_search_report import PHASES
from v08.runner.transit_report import COMMON_FIELDS

full = ROOT / "full/area_cost_ruling_r1"
rerun = ROOT / "rerun/area_cost_ruling_r1"
out = ROOT / "part7_analysis_cost_ruling_r1"
assert not out.exists()
assert not audit()
summary = read(full / "summary.json")
assert summary["complete"] and summary["diversity_complete"] and not summary["checkpoint"]["triggered"]
assert not summary["retained_p0_violations"]
assert read(rerun / "reproduction.json")["all_equal"]
rows = read(full / "records.json")
diversity = read(full / "diversity/records.json")
m = read(DOC / "manifest.json")
assert {r["contract_id"] for r in rows} == set(m["lists"]["full"])
assert {r["contract_id"] for r in diversity} == set(m["lists"]["diversity"])
entries = read(Path(m["devset"]))
if isinstance(entries, dict):
    entries = entries["families"]
entries = {e["family_id"]: e for e in entries}
out.mkdir()
job = {"phase": 7, "stage": "diagnostics", "intent": "area_search", "round": "cost_ruling_r1",
       "workers": 1, "root_pid": os.getpid(), "out": str(out), "status": "running",
       "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
dump(ROOT / "system_monitor/current_job.json", job)
failures, first_failures, phase_rows, measured_rows, separation_rows, geometry = [], [], [], [], [], []
coverage_attempts = []
ctx = None
for i, r in enumerate(rows):
    cid = r["contract_id"]
    folder = full / "contracts" / cid
    saved = read(folder / "result.json")
    first = None
    for a in saved["attempt_log"]:
        if not a["ok"]:
            fact = {"contract_id": cid, **a}
            failures.append(fact)
            if first is None:
                first = fact
        measured = a.get("measured_area_search")
        if measured is not None:
            coverage_attempts.append({"contract_id": cid, "attempt": a["attempt"], "ok": a["ok"],
                                      "coverage": measured["coverage"]})
    first_failures.append({"contract_id": cid, "first_failure": first})
    if r["success"]:
        plan = read(folder / "skeleton.json")
        p, w = plan["proposal"], plan["witnesses"]
        n = r["group_size"]
        geometry.append({"contract_id": cid, "group_size": n,
            "group_bin": "1-4" if n <= 4 else "5-8" if n <= 8 else "9-12",
            "formation": plan["formation"]["realized"],
            **{k: p[k] for k in ("beta_deg", "span_deg", "c", "K", "inner_offset_m")},
            "area_m2": w["survey"]["area_m2"], "strip_lengths_m": w["area_geometry"]["strip_lengths_m"]})
        for mid, d in sorted(saved["phase_durations"].items()):
            phase_rows.append({"contract_id": cid, "member": mid, **d})
        measured = saved["attempt_log"][-1]["measured_area_search"]
        for mid, d in sorted(measured["members"].items()):
            measured_rows.append({"contract_id": cid, "member": mid, **d})
        if ctx is None or ctx.family.family_id != r["family_id"]:
            ctx = None
            ctx = load_context(entries[r["family_id"]], data_root=Path(m["data_root"]), cache_dir=Path(m["cache"]))
        tracks = {}
        for mid in r["member_ids"]:
            arrays = {k: np.load(folder / "tracks" / mid / (k + ".npy"), allow_pickle=False)
                      for k in ("tau_us", "p", "v", "a", "segment_index")}
            tracks[mid] = MemberTrack(mid, *(arrays[k] for k in ("tau_us", "p", "v", "a", "segment_index")), ())
        valid = check_validity(ctx.scene, [visible_track(tracks[mid], saved["release_us"][mid]) for mid in sorted(tracks)])
        assert valid.passed
        pair = valid.closest_pair
        fact = {"contract_id": cid, "min_separation_m": valid.min_separation_m,
                "closest_pair": pair, "phase_i": None, "phase_j": None,
                "na_reason": "single_member_or_no_common_visible_frame" if pair is None else None}
        if pair is not None:
            for key, mid in (("phase_i", pair[0]), ("phase_j", pair[1])):
                t = pair[2] / 1e6
                times = saved["phase_metrics"][mid]["nominal_times_s"]
                if t < times[0]:
                    phase = "pre_release"
                elif t > times[-1]:
                    phase = "terminal_hold"
                else:
                    phase = PHASES[min(4, max(0, int(np.searchsorted(times, t, side="right") - 1)))]
                fact[key] = phase
        separation_rows.append(fact)
        del plan, tracks
    if (i + 1) % 20 == 0:
        dump(out / "progress.json", {"stage": "member_diagnostics", "completed": i + 1, "total": 200})


def primary(a):
    return "skeleton:" + str(a.get("skeleton_stage")) if a["stage"] == "skeleton" else a["stage"]


sub = collections.Counter()
sub_attempts = collections.Counter()
for a in failures:
    labels = []
    w = a.get("witness") or {}
    if w.get("constraint"):
        labels.append("skeleton:" + str(w["constraint"]))
    for f in (a.get("optimize") or {}).get("semantic_failures") or []:
        for c in f.get("conditions") or [f.get("kind", "unknown")]:
            labels.append("semantic:" + str(c))
    for f in (a.get("optimize") or {}).get("physical_failures") or []:
        label = f.get("kind", f.get("constraint", f.get("code", "unknown"))) if isinstance(f, dict) else str(f)
        labels.append("physical:" + str(label))
    for code in (a.get("validity") or {}).get("codes") or []:
        labels.append("validity:" + str(code))
    for group in a.get("segment_failures") or []:
        for f in group:
            labels.append("frozen_segment:" + str(f[1] if isinstance(f, (list, tuple)) and len(f) > 1 else f))
    sub.update(labels)
    sub_attempts.update(set(labels))


def geodist(rs):
    return {**{k: quantiles(r[k] for r in rs) for k in
        ("beta_deg", "span_deg", "c", "K", "inner_offset_m", "area_m2")},
        "strip_lengths_m": quantiles(x for r in rs for x in r["strip_lengths_m"])}


stats = {"failed_attempt_count": len(failures), "failed_attempt_primary_stage": dict(collections.Counter(map(primary, failures))),
    "failed_subconditions_overlapping_attempt_counts": dict(sub_attempts),
    "failed_subconditions_member_occurrences_can_repeat_within_attempt": dict(sub),
    "failed_attempt_stage_reason": dict(collections.Counter(primary(a) + "/" + str(a.get("reason")) for a in failures)),
    "failed_attempts": failures,
    "first_failure_per_contract": first_failures,
    "first_failure_counts": dict(collections.Counter("none" if r["first_failure"] is None else primary(r["first_failure"]) for r in first_failures)),
    "phase_rows": phase_rows, "phase_distribution_s": {k: quantiles(r[k] for r in phase_rows) for k in
        [*(p + "_s" for p in PHASES), "travel_s", "closure_residual_s", "pre_release_hold_s", "terminal_hold_s", "release_delay_s", "pure_scan_s"]},
    "phase_total_rule": "sum the five durations for each same member; holds reported separately",
    "measured_rows": measured_rows,
    "azimuth_span_deg": quantiles(r["azimuth_span_deg"] for r in measured_rows),
    "measured_azimuth_over_110_diagnostic_only": sum(r["azimuth_span_deg"] > 110. for r in measured_rows),
    "closest_dwell_margin_m": quantiles(r["dwell_margin_m"] for r in measured_rows if r["dwell_margin_m"] is not None),
    "dwell_na_members": sum(r["dwell_margin_m"] is None for r in measured_rows),
    "dwell_rule": "201 frames; min_windows max(A,B), with A/B/start/end from the same window; full visible interval",
    "coverage_all_measured_attempts": coverage_attempts,
    "coverage_fraction_all_measured_attempts": quantiles(r["coverage"]["coverage_fraction"] for r in coverage_attempts),
    "coverage_fraction_retained": quantiles(r["coverage"]["coverage_fraction"] for r in coverage_attempts if r["ok"]),
    "separation_rows": separation_rows,
    "separation_m": quantiles(r["min_separation_m"] for r in separation_rows if r["min_separation_m"] is not None),
    "separation_phase_pairs": dict(collections.Counter(str(r["phase_i"]) + "/" + str(r["phase_j"]) for r in separation_rows)),
    "geometry_rows": geometry, "geometry_all": geodist(geometry),
    "geometry_by_n_bin": {k: geodist([r for r in geometry if r["group_bin"] == k]) for k in ("1-4", "5-8", "9-12")},
    "geometry_by_formation": {k: geodist([r for r in geometry if r["formation"] == k]) for k in sorted({r["formation"] for r in geometry})},
    "geometry_by_n_bin_and_formation": {k: geodist([r for r in geometry if r["group_bin"] + "/" + r["formation"] == k])
         for k in sorted({r["group_bin"] + "/" + r["formation"] for r in geometry})},
    "geometry_population": "winning retained main contracts; failures remain in all success denominators and failure tables",
    "frechet_scope": "area_search_warning_entry_to_last_exit_v20",
    "frechet_pair_count": summary["checkpoint"]["metrics"]["frechet_pairs"],
    "frechet_before": summary["frechet_before_pooled"], "frechet_after": summary["frechet_after_pooled"],
    "frechet_branch_endpoints": [{"contract_id": r["contract_id"], "success": r["success"],
         "info": r.get("frechet_info"), "na_reason": r.get("frechet_na")} for r in diversity],
    "p3_backlog": ["non-radial strips", "diversity definition after members separate", "N/sector/inner correlation", "duration and distance remain unbounded by design"],
    "excluded_from_rate": []}
dump(out / "diagnostics.json", stats)

# The six-intent outer join uses public fields even when a contract failed.
roots = {intent: Path(fact["path"]) for intent, fact in m["baselines"].items()}
roots["area_search"] = full
tables = {intent: {r["contract_id"]: r for r in read(root / "records.json") if r.get("branch") is None} for intent, root in roots.items()}
keys = sorted(set().union(*(set(t) for t in tables.values())))
paired = []
for i, cid in enumerate(keys):
    items = {intent: table.get(cid) for intent, table in tables.items()}
    contracts = {intent: read(roots[intent] / "contracts" / cid / "contract.json") for intent, r in items.items() if r is not None}
    public = {intent: {k: contracts[intent].get(k, r.get(k)) for k in COMMON_FIELDS} for intent, r in items.items() if r is not None}
    differences, missing = [], []
    for field in COMMON_FIELDS:
        vals = [public.get(intent, {}).get(field) for intent in roots]
        if any(v is None for v in vals):
            missing.append(field)
        if any(v != vals[0] for v in vals[1:]):
            differences.append(field)
    fact = {"contract_id": cid, "common_fields": public, "differences": differences, "missing": missing,
            "outcomes": {intent: None if r is None else {"success": r["success"], "attempts": r.get("attempts")}
                         for intent, r in items.items()}}
    geometry_pair = {}
    plans = {}
    for intent in ("area_search", "transit"):
        r = items[intent]
        if r is None or not r["success"]:
            geometry_pair[intent] = {"na_reason": "no_winning_skeleton"}
            continue
        plans[intent] = read(roots[intent] / "contracts" / cid / "skeleton.json")
        p, f = plans[intent]["proposal"], plans[intent]["formation"]
        geometry_pair[intent] = {"theta_idx": p["theta_idx"], "h_m": p["h_m"], "formation": f["realized"],
            "slots": f["offsets"], "Q": p.get("Q"), "beta_deg": p.get("beta_deg"),
            "original_cells": p["cells_feasible"], "filtered_cells": p.get("filtered_cells"),
            "filter_ratio": None if not p.get("cells_feasible") or p.get("filtered_cells") is None else 1. - p["filtered_cells"] / p["cells_feasible"]}
    if len(plans) == 2:
        a, t = plans["area_search"], plans["transit"]
        tp = t["proposal"]
        survey = a["witnesses"]["survey"]["geometry"]
        try:
            q = member_split_points(survey["base_geometry"], survey["center_m"], survey["outer_offset_m"],
                tp["u"], tp["h_m"], {"center": (0., 0.)}, x_min=tp["x_c"], x_max=tp["x_t"])["center"]
            radial = np.asarray(survey["center_m"]) - q
            u = np.asarray(tp["u"])
            beta = math.degrees(math.atan2(float(u[0] * radial[1] - u[1] * radial[0]), float(u @ radial)))
            geometry_pair["transit"]["Q_at_area_outer_diagnostic"] = q.tolist()
            geometry_pair["transit"]["beta_at_area_outer_diagnostic_deg"] = beta
        except ValueError:
            geometry_pair["transit"]["Q_at_area_outer_na"] = "no_forward_intersection_with_area_outer"
        geometry_pair["equal_theta_h"] = all(geometry_pair["area_search"][k] == geometry_pair["transit"][k] for k in ("theta_idx", "h_m"))
        geometry_pair["equal_formation_slots"] = all(geometry_pair["area_search"][k] == geometry_pair["transit"][k] for k in ("formation", "slots"))
    fact["area_transit_geometry"] = geometry_pair
    paired.append(fact)
    if (i + 1) % 20 == 0:
        dump(out / "progress.json", {"stage": "six_intent_outer_join", "completed": i + 1, "total": len(keys)})
pairs = [r["area_transit_geometry"] for r in paired if "equal_theta_h" in r["area_transit_geometry"]]
pair_summary = {"outer_join_count": len(paired), "public_difference_contracts": sum(bool(r["differences"]) for r in paired),
    "public_missing_contracts": sum(bool(r["missing"]) for r in paired), "both_winning_geometry_count": len(pairs),
    "equal_theta_h_count": sum(r["equal_theta_h"] for r in pairs),
    "equal_formation_slots_count": sum(r["equal_formation_slots"] for r in pairs),
    "old_transit_Q_note": "original transit has no Q/beta; diagnostic intersection uses the winning area's outer contour, without resampling or acceptance changes",
    "rows": paired}
dump(out / "six_intent_pairing.json", pair_summary)
assert not audit()
dump(out / "complete.json", {"complete": True, "main": len(rows), "diversity": len(diversity),
                            "public_differences": pair_summary["public_difference_contracts"], "audit_changes": []})
a = read(DOC / "acceptance.json")
assert len(a["outputs"]) == 1 and a["outputs"][0]["stage"] == "quick"
a["outputs"].append({"stage": "full", "path": str(full)})
a["rerun"] = str(rerun)
a["status"] = "part7_artifact_preset_pending"
dump(DOC / "acceptance.json", a)
job.update(status="finished", ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
dump(ROOT / "system_monitor/current_job.json", job)
print(json.dumps({"analysis_complete": True, "failed_attempts": len(failures), "public_pairing": {k:v for k,v in pair_summary.items() if k != "rows"},
                  "dwell_margin": stats["closest_dwell_margin_m"], "coverage": stats["coverage_fraction_retained"]}, ensure_ascii=False), flush=True)
