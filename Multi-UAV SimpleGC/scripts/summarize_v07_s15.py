"""Read-only scene comparison; write new S15 summaries/gallery, never sources."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time

from shapely.geometry import Point, Polygon

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scene_v07.batch import _distribution, select_representatives
from scene_v07.contract import canonical_json
from scene_v07.geometry import center_of
from scene_v07.layout_s15 import base_distance


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def distribution(values):
    result = _distribution(values)
    return {**result, "p50": result["median"]}


def gap_summary(rows):
    bins = {"overlap_gt_50pct": 0, "overlap_0_to_50pct": 0, "gap_0_to_200m": 0, "gap_gt_200m": 0}
    for gap, width in rows:
        key = ("overlap_gt_50pct" if -gap/width > .5 else "overlap_0_to_50pct") if gap < 0 else (
            "gap_0_to_200m" if gap <= 200 else "gap_gt_200m")
        bins[key] += 1
    return {"gap_m": distribution([gap for gap, _ in rows]),
            "gap_over_width": distribution([gap/width for gap, width in rows]), "diagnostic_bins": bins}


def measure_attempt(attempt):
    attempt = Path(attempt)
    records, summary = read(attempt / "candidates.json"), read(attempt / "summary.json")
    all_pairs, linked_pairs = defaultdict(list), defaultdict(list)
    r1, r1_ratios, r1_residuals, entry_distances, center_distances = [], [], [], [], []
    side_by_count = defaultdict(list)
    sampling_failures, candidate_failures = Counter(), Counter()
    anchors = anchor_retries = r1_bad = r1_bad_unordered = r2_bad = 0
    link_errors, edge_clearances = [], []
    per_candidate, source_hashes, provenances = [], {}, []
    for row in records:
        directory = attempt / row["family_id"]
        family_path = directory / "family_initial.json"
        family, provenance = read(family_path), read(directory / "provenance.json")
        provenances.append(provenance)
        source_hashes[str(family_path)] = sha(family_path)
        source_hashes[str(directory / "provenance.json")] = sha(directory / "provenance.json")
        source_hashes[str(directory / "check_results.json")] = sha(directory / "check_results.json")
        candidate_failures.update(set(row["issue_codes"]))
        layout_record = family.get("layout_s15", {})
        sampling_failures.update(layout_record.get("rejected_attempt_reasons", {}))
        anchors += layout_record.get("anchor_attempts", 0)
        anchor_retries += layout_record.get("anchor_retries", 0)
        side_by_count[row["facility_count"]].append(row["map_side_m"])
        public_path = directory / "public_scene.json"
        if not public_path.exists():
            continue
        scene = read(public_path)
        source_hashes[str(public_path)] = sha(public_path)
        facilities = [e for e in scene["entities"] if e["type"] == "facility"]
        layers = {f["id"]: {e["layer"]: e for e in scene["entities"] if e.get("facility_id") == f["id"]}
                  for f in facilities}
        pairs, candidate_r1 = {}, []
        for i, a in enumerate(facilities):
            d1a, d2a = (layers[a["id"]][layer]["offset_m"] for layer in ("warning", "alert"))
            geometry = a["geometry"]
            if geometry["type"] == "Circle":
                x, y = geometry["center_m"]
                radius = geometry["radius_m"]
                bounds = x-radius, y-radius, x+radius, y+radius
            else:
                bounds = Polygon(geometry["vertices_m"]).bounds
            side = row["map_side_m"]
            edge_clearances.append(min(bounds[0], bounds[1], side-bounds[2], side-bounds[3])-d1a)
            for j, b in enumerate(facilities[:i]):
                d1b, d2b = (layers[b["id"]][layer]["offset_m"] for layer in ("warning", "alert"))
                distance = base_distance(a["geometry"], b["geometry"])
                gap, width = distance-d1a-d1b, min(d1a-d2a, d1b-d2b)
                pairs[j, i] = gap, width
                all_pairs[family["layout"]].append((gap, width))
                r2_bad += gap < -.2*width-1e-6
                r1_bad_unordered += min(distance-d2a-d1b, distance-d2b-d1a) <= 0
                for margin, own_width in ((distance-d2a-d1b, d1a-d2a), (distance-d2b-d1a, d1b-d2b)):
                    r1.append(margin)
                    candidate_r1.append(margin)
                    r1_ratios.append(margin/own_width)
                    r1_residuals.append(margin-.8*own_width)
                    r1_bad += margin <= 0
            for entry in scene["entry_zones"]:
                entry_distances.append(max(0.0, base_distance(entry["geometry"], a["geometry"])-d1a))
                point, geometry = center_of(entry["geometry"]), a["geometry"]
                distance = (max(0.0, math.dist(point, geometry["center_m"])-geometry["radius_m"])
                            if geometry["type"] == "Circle" else Point(point).distance(Polygon(geometry["vertices_m"])))
                center_distances.append(max(0.0, distance-d1a))
        for link in layout_record.get("links", []):
            pair = pairs[tuple(sorted((link["parent"], link["child"])))]
            linked_pairs[family["layout"]].append(pair)
            link_errors.append(abs(pair[0]-link["target_gap_m"]))
        per_candidate.append({"candidate_index": row["candidate_index"], "sampling_seed": provenance["sampling_seed"],
                              "layout": row["layout"], "facility_count": len(facilities), "accepted": row["accepted"],
                              "r1_min_m": min(candidate_r1, default=None), "map_side_m": row["map_side_m"],
                              "pair_gap_over_width": [g/w for g, w in pairs.values()]})
    source_hashes[str(attempt / "candidates.json")] = sha(attempt / "candidates.json")
    source_hashes[str(attempt / "summary.json")] = sha(attempt / "summary.json")
    is_s15 = summary["sampling_revision"] == "s1.5"
    # Old batch histograms stringify 6000 and 6000.0 separately. Combine the
    # same numeric side here without modifying original external summaries.
    candidate_distributions = {**summary["candidate_distributions"], "map_side_m":
                              dict(sorted(Counter(f"{r['map_side_m']:g}" for r in records).items()))}
    accepted_distributions = {**summary["accepted_distributions"], "map_side_m":
                             dict(sorted(Counter(f"{r['map_side_m']:g}" for r in records if r["accepted"]).items()))}
    return {"attempt": str(attempt), "sampling_revision": summary["sampling_revision"],
            "candidates": len(records), "accepted": summary["accepted_count"], "rejected": summary["rejected_count"],
            "candidate_rejection_reasons": dict(candidate_failures),
            "sampling_layout_s15_exhausted": candidate_failures["sampling_layout_s15_exhausted"],
            "layout_exceeds_max_map": sampling_failures["layout_exceeds_max_map"],
            "layout_proposal_rejection_counts": dict(sampling_failures),
            "anchor_attempts": anchors if is_s15 else None, "anchor_retries": anchor_retries if is_s15 else None,
            "candidate_distributions": candidate_distributions,
            "accepted_distributions": accepted_distributions,
            "gaps_by_layout": {layout: {"all_pairs": gap_summary(all_pairs[layout]),
                "attachment_pairs": gap_summary(linked_pairs[layout]) if is_s15 else None}
                for layout in ("single", "isolated", "clustered", "linear")},
            "r1": {"ordered_pairs": len(r1), "margin_m": distribution(r1), "margin_over_own_width": distribution(r1_ratios),
                   "margin_minus_0_8_own_width_m": distribution(r1_residuals), "violations": r1_bad,
                   "violating_unordered_pairs": r1_bad_unordered},
            "r2_violating_unordered_pairs": r2_bad,
            "link_target_error_m": distribution(link_errors), "warning_edge_clearance_m": distribution(edge_clearances),
            "map_side_m_by_facility_count": {str(count): {"values": dict(sorted(Counter(f"{v:g}" for v in values).items())),
                "distribution": distribution(values)} for count, values in sorted(side_by_count.items())},
            "entry_region_to_warning_boundary_m": distribution(entry_distances),
            "entry_center_to_warning_boundary_m": distribution(center_distances),
            "accepted_route_detour_ratio": summary["accepted_route_detour_ratio"],
            "accepted_approach_span_deg": summary["accepted_approach_span_deg"],
            "timing_s": summary["timing_s"], "per_candidate": per_candidate,
            "source_sha256": source_hashes, "provenances": provenances}, records


def copy_gallery(attempt, records, destination):
    selected = select_representatives(records)
    accepted = [r for r in records if r["accepted"]]
    for field, value in (("layout", "isolated"), ("layout", "clustered"), ("layout", "linear"), ("facility_count", 3)):
        pool = [r for r in accepted if r[field] == value]
        for row in sorted(pool, key=lambda r: r["candidate_index"]):
            if sum(r["accepted"] and r[field] == value for r in selected) >= 3:
                break
            if row not in selected:
                selected.append(row)
        if sum(r["accepted"] and r[field] == value for r in selected) < 3:
            raise ValueError(f"Insufficient representative quota: {field}={value}")
    images = [Path(attempt) / row["family_id"] / "topdown.png" for row in selected]
    total_bytes = sum(path.stat().st_size for path in images)
    thumbnails = total_bytes > 20*1024*1024
    destination.mkdir(parents=True, exist_ok=True)
    manifest, markdown = [], ["# S1.5 代表图库", "", "仅含静态场景与原有路线诊断，等待人工审查。", ""]
    for row, source in zip(selected, images):
        name = f"candidate_{row['candidate_index']:03d}_{row['layout']}_{row['facility_count']}fac.png"
        target = destination / name
        if thumbnails:
            from PIL import Image
            with Image.open(source) as original:
                original.thumbnail((1000, 800))
                original.save(target)
        else:
            shutil.copyfile(source, target)
        manifest.append({"candidate_index": row["candidate_index"], "family_id": row["family_id"],
                         "layout": row["layout"], "facility_count": row["facility_count"],
                         "source": str(source), "source_sha256": sha(source), "file": name, "sha256": sha(target)})
        markdown += [f"## 候选 {row['candidate_index']:03d} · {row['layout']} · {row['facility_count']} 设施", "",
                     f"![候选 {row['candidate_index']:03d}]({name})", ""]
    (destination / "README.md").write_text("\n".join(markdown), encoding="utf-8", newline="\n")
    return {"count": len(manifest), "thumbnails": thumbnails, "original_png_bytes": total_bytes,
            "submitted_png_bytes": sum((destination / row["file"]).stat().st_size for row in manifest),
            "layout_counts": dict(Counter(row["layout"] for row in manifest)),
            "facility_counts": dict(Counter(row["facility_count"] for row in manifest)), "images": manifest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--quick", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=PROJECT / "docs/v07/evidence/s15/s15_scene_summary.json")
    args = parser.parse_args()
    for source in (args.attempt, args.reference, args.quick):
        if args.output.resolve().is_relative_to(source.resolve()):
            raise ValueError("Summary/gallery output must not modify source attempts")
    started = time.perf_counter()
    s15, records = measure_attempt(args.attempt)
    s12, _ = measure_attempt(args.reference)
    new = {p["candidate_index"]: p for p in s15.pop("provenances")}
    old = {p["candidate_index"]: p for p in s12.pop("provenances")}
    if set(new) != set(range(300)) or set(old) != set(range(300)):
        raise ValueError("Expected original candidate indices 0..299 on both sides")
    paired = [{"candidate_index": index, "same_master_seed": p["master_seed"] == old[index]["master_seed"],
               "same_family_seed": p["sampling_seed"] == old[index]["sampling_seed"]} for index, p in sorted(new.items())]
    if not all(p["same_master_seed"] and p["same_family_seed"] for p in paired):
        raise ValueError("Candidate seed alignment changed")
    if s15["r1"]["violations"] or s15["r2_violating_unordered_pairs"]:
        raise RuntimeError("S15 P0: exact independent statistics found R1/R2 violation")
    if s15["link_target_error_m"]["max"] > 1e-3 or s15["warning_edge_clearance_m"]["min"] < 350-1e-6:
        raise RuntimeError("S15 exact geometry audit failed")
    measured = time.perf_counter()
    gallery = copy_gallery(args.attempt, records, args.output.parent / "gallery")
    regression = read(args.output.parent / "regression_checks.json")
    quick = read(args.quick / "summary.json")
    if quick["candidate_count"] != 30 or quick["accepted_count"]/quick["candidate_count"] < .7:
        raise RuntimeError("Quick acceptance below 70%")
    reconstruction = []
    for row in read(args.quick / "candidates.json"):
        for filename in ("public_scene.json", "family_initial.json"):
            before, after = args.quick / row["family_id"] / filename, args.attempt / row["family_id"] / filename
            if before.exists():
                equal = before.read_bytes() == after.read_bytes()
                reconstruction.append({"candidate_index": row["candidate_index"], "file": filename, "byte_identical": equal})
                if not equal:
                    raise ValueError("Quick/full reconstruction differs")
    result = {"generated_utc": datetime.now(timezone.utc).isoformat(), "s15": s15, "s12": s12,
              "candidate_alignment": paired, "quick_full_reconstruction": reconstruction,
              "quick": {"attempt": str(args.quick), "summary": quick},
              "gallery": gallery, "regression_status": regression["status"],
              "definitions": {"geometry_population": "all published public scenes, including rejected checks; incomplete proposals excluded",
                  "route_population": "accepted families, original check_family diagnostics; no re-planning",
                  "r1": "all ordered pairs: base_distance-d2_i-d1_j; compare with 0.8*W_i per pair",
                  "entry_distance": "exact distance from entire entry polygon to warning boundary; center distances also reported",
                  "bins": "g<0: overlap >50% or (0,50%]; g>=0: [0,200]m or >200m",
                  "s12_attachment_pairs": "null: S1.2 has no parent-child attachment construction/records; no invented links",
                  "sampling_r2_rejections": "rejected local proposals only, not invalid output scenes"},
              "timing_s": {"regression": regression["wall_s"], "quick": quick["timing_s"], "full": s15["timing_s"],
                           "read_only_statistics": measured-started, "gallery_copy": time.perf_counter()-measured,
                           "summary_total": time.perf_counter()-started}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(result))
    print(json.dumps({"accepted": s15["accepted"], "rejected": s15["rejected"], "r1_min_m": s15["r1"]["margin_m"]["min"],
                      "gallery_count": gallery["count"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
