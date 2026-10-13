"""External, append-only attempt output; no plotting dependency."""
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import time
import uuid

import shapely

from .checks import check_family
from .contract import SCHEMA_VERSION, SceneConfig, canonical_json
from .sampling import family_seed, sample_family
from .sampling_s11 import MAP_SIDES_M, SamplingRejected

DEFAULT_OUTPUT_ROOT = Path("F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_scene")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _write(path, value):
    with path.open("xb") as stream:
        stream.write(canonical_json(value))


def new_attempt(output_root=DEFAULT_OUTPUT_ROOT, name=None):
    root = Path(output_root).resolve()
    if root == REPOSITORY_ROOT or REPOSITORY_ROOT in root.parents:
        raise ValueError("Scene output must be outside the repository")
    root.mkdir(parents=True, exist_ok=True)
    name = name or ("attempt_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    if not name.startswith("attempt_") or Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("Attempt name must be a single attempt_* directory")
    attempt = root / name
    attempt.mkdir(exist_ok=False)
    return attempt


def _counts(values):
    return dict(sorted(Counter(map(str, values)).items()))


def _distribution(values):
    values = sorted(values)
    if not values:
        return {"count": 0, "min": None, "p25": None, "median": None, "p75": None, "p90": None, "max": None}
    def quantile(p):
        index = (len(values) - 1) * p
        low = int(index)
        return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (index - low)
    return {"count": len(values), "min": values[0], "p25": quantile(.25), "median": quantile(.5),
            "p75": quantile(.75), "p90": quantile(.9), "max": values[-1]}


def _cohort(records):
    return {"families": len(records),
            "facility_count": _counts(r["facility_count"] for r in records),
            "layout": _counts(r["layout"] for r in records),
            "map_side_m": _counts(r.get("map_side_m", 4000) for r in records),
            "obstacle_count": _counts(r["obstacle_count"] for r in records),
            "vehicle_count": _counts(r["vehicle_count"] for r in records),
            "radar_count": _counts(r["radar_count"] for r in records),
            "facility_shape": _counts(shape for r in records for shape in r["facility_shapes"]),
            "obstacle_placement": _counts(p for r in records for p in r["obstacle_placements"])}


def summarize(records):
    accepted = [r for r in records if r["accepted"]]
    rejected = [r for r in records if not r["accepted"]]
    geometric = [r for r in records if r["geometry_issue_codes"]]
    connectivity = [r for r in records if r["connectivity_issue_codes"]]
    ratios = [v for r in accepted for v in r["detour_ratios"]]
    spans = [v for r in accepted for v in r["approach_spans_deg"]]
    route_rows = [row for r in accepted for row in r.get("route_diagnostics", [])]
    detours = [row["max_lateral_deviation_m"] for row in route_rows
               if row["detour_ratio"] is not None and row["detour_ratio"] > 1+1e-9]
    slots = [slot for r in records for slot in r.get("obstacle_sampling", {}).get("slots", [])]
    total = len(records)
    return {"candidate_count": total, "accepted_count": len(accepted), "rejected_count": len(rejected),
            "rejection_rate": len(rejected) / total if total else 0,
            "geometry_rejected_count": len(geometric), "geometry_rejection_rate": len(geometric) / total if total else 0,
            "connectivity_rejected_count": len(connectivity),
            "rejection_reason_counts": _counts(code for r in records for code in r["issue_codes"]),
            "reason_count_unit": "number of candidate families; each code counted at most once per family",
            "candidate_distributions": _cohort(records), "accepted_distributions": _cohort(accepted),
            "rejected_distributions": _cohort(rejected),
            "accepted_route_detour_ratio": _distribution(ratios),
            "detoured_accepted_route_count": sum(v > 1 + 1e-9 for v in ratios),
            "accepted_route_detour_histogram": {
                "[1.0,1.05)": sum(1 - 1e-9 <= v < 1.05 for v in ratios),
                "[1.05,1.10)": sum(1.05 <= v < 1.10 for v in ratios),
                "[1.10,1.25)": sum(1.10 <= v < 1.25 for v in ratios),
                "[1.25,1.50)": sum(1.25 <= v < 1.50 for v in ratios),
                "[1.50,infinity)": sum(v >= 1.50 for v in ratios)},
            "accepted_approach_span_deg": _distribution(spans),
            "accepted_facilities_below_60deg": sum(v < 60 for v in spans),
            "angle_span_used_as_rejection_gate": False,
            "sampling_rejected_count": sum(bool(r.get("sampling_issue_codes")) for r in records),
            "accepted_straight_blocked_fraction": {
                "blocked": sum(row["straight_blocked_by_obstacle"] for row in route_rows),
                "routes": len(route_rows),
                "fraction": sum(row["straight_blocked_by_obstacle"] for row in route_rows)/len(route_rows) if route_rows else None},
            "accepted_straight_margin_blocked_fraction": {
                "blocked": sum(row["straight_blocked_with_margin"] for row in route_rows),
                "routes": len(route_rows),
                "fraction": sum(row["straight_blocked_with_margin"] for row in route_rows)/len(route_rows) if route_rows else None},
            "accepted_entry_blocker_blocked_route_count": sum(row["straight_blocked_by_entry_blocker"] for row in route_rows),
            "accepted_detour_max_lateral_deviation_m": _distribution(detours),
            "obstacle_placement_sampling": {
                "requested_slots": len(slots), "placed_slots": sum(slot["placed"] for slot in slots),
                "skipped_slots": sum(not slot["placed"] for slot in slots),
                "families_with_skipped_slots": sum(r.get("obstacle_sampling", {}).get("skipped_count",0)>0 for r in records),
                "skipped_slot_types": _counts(slot["placement"] for slot in slots if not slot["placed"]),
                "placement_attempts": _distribution([slot["attempts"] for slot in slots])},
            "route_diagnostic_used_as_rejection_gate": False}


def select_representatives(records, count=16):
    selected = []
    accepted = [r for r in records if r["accepted"]]
    rank = lambda r: (-max((row.get("max_lateral_deviation_m") or 0 for row in r.get("route_diagnostics",[])),default=0),r["candidate_index"])
    def pick(pool, required):
        for r in sorted(pool,key=rank):
            if sum(record in pool for record in selected) >= required or len(selected)>=count:
                break
            if r not in selected:
                selected.append(r)
    for facilities in (2,3):
        pick([r for r in accepted if r["facility_count"]==facilities],3)
    pick([r for r in accepted if any(row["straight_blocked_by_entry_blocker"] for row in r.get("route_diagnostics",[]))],3)
    rejected = [r for r in records if not r["accepted"]]
    pick(rejected,2)
    for layout in ("single","isolated","clustered","linear"):
        pick([r for r in accepted if r["layout"]==layout],1)
    for r in sorted(accepted,key=rank)+rejected:
        if len(selected)>=min(count,len(records)):
            break
        if r not in selected:
            selected.append(r)
    return selected[:count]


def representative_coverage(records):
    return {"count": len(records),
            "two_facility_accepted": sum(r["accepted"] and r["facility_count"]==2 for r in records),
            "three_facility_accepted": sum(r["accepted"] and r["facility_count"]==3 for r in records),
            "entry_blocker_straight_blocked_accepted": sum(r["accepted"] and any(
                row["straight_blocked_by_entry_blocker"] for row in r.get("route_diagnostics",[])) for r in records)}


def generate_attempt(candidate_count=300, master_seed=2026101307, output_root=DEFAULT_OUTPUT_ROOT,
                     attempt_name=None, config=None, plotter=None, progress=None, single_family_seed=None, sampling_revision="s1.1", sampling_policy=None):
    if isinstance(candidate_count, bool) or not isinstance(candidate_count, int) or candidate_count < 1:
        raise ValueError("candidate_count must be a positive integer")
    if single_family_seed is not None and candidate_count != 1:
        raise ValueError("Single-seed reconstruction requires one candidate")
    # Validate seed before creating an output directory.
    family_seed(master_seed, 0)
    if single_family_seed is not None and (isinstance(single_family_seed, bool)
                                          or not isinstance(single_family_seed, int) or single_family_seed < 0):
        raise ValueError("Invalid reconstruction seed")
    started = time.perf_counter()
    config = config or SceneConfig()
    attempt = new_attempt(output_root, attempt_name)
    records = []
    sampling_s = plotting_s = output_s = 0.0
    for index in range(candidate_count):
        seed = family_seed(master_seed, index) if single_family_seed is None else single_family_seed
        sample_started = time.perf_counter()
        sampling_failure = None
        try:
            public, family = sample_family(seed, config, revision=sampling_revision, policy=sampling_policy)
        except SamplingRejected as failure:
            public, family, sampling_failure = failure.scene, failure.family, failure.code
        if sampling_failure:
            checks = {"schema_version": "traj2language.scene_checks/0.7-s1.2", "accepted": False,
                      "issues": [{"code": sampling_failure,"entity_ids": [],"category": "sampling"}],
                      "routes": [],"approaches": []}
        else:
            checks = check_family(public, family)
        sampling_s += time.perf_counter() - sample_started
        output_started = time.perf_counter()
        directory = attempt / family["family_id"]
        directory.mkdir(exist_ok=False)
        if sampling_failure:
            draft = {**public,"schema_version": "traj2language.incomplete_scene_proposal/0.7-s1.1"}
            _write(directory / "candidate_geometry.json", draft)
        else:
            _write(directory / "public_scene.json", public)
        _write(directory / "family_initial.json", family)
        _write(directory / "check_results.json", checks)
        _write(directory / "provenance.json", {"master_seed": master_seed, "candidate_index": index,
                                               "sampling_seed": seed, "generator_version": family["generator_version"],
                                               "sampling_revision": sampling_revision,
                                               "seed_derivation": "sha256(v07_scene_s1:master:index) first 8 bytes, big endian"})
        output_s += time.perf_counter() - output_started
        if plotter:
            plot_started = time.perf_counter()
            plotter(public, family, checks, directory / "topdown.png", index)
            plotting_s += time.perf_counter() - plot_started
        entities = public["entities"]
        record = {"candidate_index": index, "family_id": family["family_id"], "sampling_seed": seed,
                  "directory": str(directory), "accepted": checks["accepted"],
                  "public_scene_published": sampling_failure is None,
                  "map_side_m": family["config"]["map_side_m"],
                  "sampling_issue_codes": [sampling_failure] if sampling_failure else [],
                  "obstacle_sampling": family.get("obstacle_sampling", {}),
                  "route_diagnostics": [{key: route[key] for key in ["entry_id","facility_id","detour_ratio",
                      "straight_blocked_by_obstacle","straight_blocked_with_margin","straight_blocked_by_entry_blocker",
                      "blocking_obstacle_ids","max_lateral_deviation_m"]} for route in checks["routes"]],
                  "issue_codes": sorted({i["code"] for i in checks["issues"]}),
                  "geometry_issue_codes": sorted({i["code"] for i in checks["issues"] if i["category"] == "geometry"}),
                  "connectivity_issue_codes": sorted({i["code"] for i in checks["issues"] if i["category"] == "connectivity"}),
                  "facility_count": sum(e["type"] == "facility" for e in entities),
                  "facility_shapes": [e["geometry"]["type"] for e in entities if e["type"] == "facility"],
                  "layout": family["layout"], "obstacle_count": sum(e["type"] == "hard_constraint_obstacle" for e in entities),
                  "obstacle_placements": [p["placement"] for p in family["obstacle_placements"]],
                  "radar_count": sum(e["type"] == "radar" for e in entities), "vehicle_count": family["vehicle_count"],
                  "detour_ratios": [r["detour_ratio"] for r in checks["routes"] if r["detour_ratio"] is not None],
                  "approach_spans_deg": [a["available_span_deg"] for a in checks["approaches"]]}
        records.append(record)
        if progress:
            progress(index + 1, candidate_count, record)
    summary = summarize(records)
    representatives = select_representatives(records)
    summary.update({"schema_version": "traj2language.s1_attempt_summary/0.7-s1.2",
                    "public_scene_schema_version": SCHEMA_VERSION, "generator_version": family["generator_version"],
                    "sampling_revision": sampling_revision,
                    "map_side_by_facility_count_m": MAP_SIDES_M if sampling_revision in ("s1.1", "s1.2") else None,
                    "public_scene_count": sum(r["public_scene_published"] for r in records),
                    "representative_coverage": representative_coverage(representatives),
                    "attempt_directory": str(attempt), "master_seed": master_seed, "config": asdict(config),
                    "environment": {"python": platform.python_version(), "shapely": shapely.__version__,
                                    "geos": shapely.geos_version_string},
                    "plot_count": len(records) if plotter else 0,
                    "representative_families": [r["family_id"] for r in representatives]})
    _write(attempt / "candidates.json", records)
    _write(attempt / "representatives.json", representatives)
    gallery_directory = attempt / "代表图库"
    if plotter:
        gallery_directory.mkdir(exist_ok=False)
        for record in representatives:
            name = f"candidate_{record['candidate_index']:03d}_{'accepted' if record['accepted'] else 'rejected'}.png"
            destination = gallery_directory / name
            with (Path(record["directory"])/"topdown.png").open("rb") as source, destination.open("xb") as target:
                shutil.copyfileobj(source,target)
    with (attempt / "gallery.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("# S1 representative scenes\n\n")
        for r in representatives:
            stream.write(f"## Candidate {r['candidate_index']:03d}: {'accepted' if r['accepted'] else 'rejected'}\n\n")
            stream.write(f"Seed: {r['sampling_seed']}; layout: {r['layout']}; issues: {', '.join(r['issue_codes']) or 'none'}\n\n")
            if plotter:
                stream.write(f"![Top-down scene](<{(Path(r['directory'])/'topdown.png').as_posix()}>)\n\n")
    summary["timing_s"] = {"sampling_and_checks": sampling_s, "plotting": plotting_s,
                           "sampling_and_plotting": sampling_s + plotting_s,
                           "family_json_output": output_s, "total_wall": time.perf_counter() - started,
                           "total_wall_excludes": "only the final summary.json write"}
    _write(attempt / "summary.json", summary)
    return summary
