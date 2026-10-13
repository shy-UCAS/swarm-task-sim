"""External, append-only attempt output; no plotting dependency."""
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import time
import uuid

import shapely

from .checks import check_family
from .contract import GENERATOR_VERSION, SCHEMA_VERSION, SceneConfig, canonical_json
from .sampling import family_seed, sample_family

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
            "angle_span_used_as_rejection_gate": False}


def select_representatives(records, count=16):
    selected = []
    reasons = set()
    rejected = [r for r in records if not r["accepted"]]
    for r in sorted(rejected, key=lambda x: (-len(x["issue_codes"]), x["candidate_index"])):
        if set(r["issue_codes"]) - reasons:
            selected.append(r)
            reasons.update(r["issue_codes"])
        if len(selected) == min(4, len(rejected)):
            break
    for r in rejected:
        if len(selected) >= min(4, len(rejected)):
            break
        if r not in selected:
            selected.append(r)
    accepted = [r for r in records if r["accepted"]]
    categories = set()
    for r in sorted(accepted, key=lambda x: (-max(x["detour_ratios"], default=1), x["candidate_index"])):
        tags = {f"layout:{r['layout']}", f"facilities:{r['facility_count']}", f"obstacles:{r['obstacle_count']}",
                f"vehicles:{r['vehicle_count']}", *[f"shape:{s}" for s in r["facility_shapes"]]}
        if tags - categories:
            selected.append(r)
            categories.update(tags)
        if len(selected) >= count:
            break
    for r in sorted(accepted, key=lambda x: (min(x["approach_spans_deg"], default=360), x["candidate_index"])):
        if len(selected) >= min(count, len(records)):
            break
        if r not in selected:
            selected.append(r)
    for r in records:
        if len(selected) >= min(count, len(records)):
            break
        if r not in selected:
            selected.append(r)
    return selected[:count]


def generate_attempt(candidate_count=300, master_seed=2026101307, output_root=DEFAULT_OUTPUT_ROOT,
                     attempt_name=None, config=None, plotter=None, progress=None, single_family_seed=None):
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
        public, family = sample_family(seed, config)
        checks = check_family(public, family)
        sampling_s += time.perf_counter() - sample_started
        output_started = time.perf_counter()
        directory = attempt / family["family_id"]
        directory.mkdir(exist_ok=False)
        _write(directory / "public_scene.json", public)
        _write(directory / "family_initial.json", family)
        _write(directory / "check_results.json", checks)
        _write(directory / "provenance.json", {"master_seed": master_seed, "candidate_index": index,
                                               "sampling_seed": seed, "generator_version": GENERATOR_VERSION,
                                               "seed_derivation": "sha256(v07_scene_s1:master:index) first 8 bytes, big endian"})
        output_s += time.perf_counter() - output_started
        if plotter:
            plot_started = time.perf_counter()
            plotter(public, family, checks, directory / "topdown.png", index)
            plotting_s += time.perf_counter() - plot_started
        entities = public["entities"]
        record = {"candidate_index": index, "family_id": family["family_id"], "sampling_seed": seed,
                  "directory": str(directory), "accepted": checks["accepted"],
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
    summary.update({"schema_version": "traj2language.s1_attempt_summary/0.7-s1.1",
                    "public_scene_schema_version": SCHEMA_VERSION, "generator_version": GENERATOR_VERSION,
                    "attempt_directory": str(attempt), "master_seed": master_seed, "config": asdict(config),
                    "environment": {"python": platform.python_version(), "shapely": shapely.__version__,
                                    "geos": shapely.geos_version_string},
                    "plot_count": len(records) if plotter else 0,
                    "representative_families": [r["family_id"] for r in representatives]})
    _write(attempt / "candidates.json", records)
    _write(attempt / "representatives.json", representatives)
    with (attempt / "gallery.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("# S1 representative scenes\n\n")
        for r in representatives:
            stream.write(f"## Candidate {r['candidate_index']:03d}: {'accepted' if r['accepted'] else 'rejected'}\n\n")
            stream.write(f"Seed: {r['sampling_seed']}; layout: {r['layout']}; issues: {', '.join(r['issue_codes']) or 'none'}\n\n")
            if plotter:
                stream.write(f"![Top-down scene]({r['family_id']}/topdown.png)\n\n")
    summary["timing_s"] = {"sampling_and_checks": sampling_s, "plotting": plotting_s,
                           "sampling_and_plotting": sampling_s + plotting_s,
                           "family_json_output": output_s, "total_wall": time.perf_counter() - started,
                           "total_wall_excludes": "only the final summary.json write"}
    _write(attempt / "summary.json", summary)
    return summary
