"""S15 stage 2 step 1: register frozen-baseline families and sample regular skeleton descriptors.

Reads the frozen S1.5 baseline, re-verifies the selected maps' SHA256, applies the registered
layered selection rule, samples descriptors with the existing sampler, and writes a new
external registration directory that scripts/run_v07_s2_expansion.py::descriptor_jobs can read.
Nothing under task_v07/, configs/ or scene_v07/ is written.
"""
import argparse
from datetime import datetime, timezone
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scripts.run_v07_s2_expansion import DEFAULT_DATA, descriptor_jobs
from task_v07.expansion.contracts import P0ContractError
from task_v07.expansion.sampling import INTENTS, sample_family_descriptors
from task_v07.io import read_json, save_json, sha

BASELINE = PROJECT / "docs/v07/s15/S15_frozen_baseline.json"
LAYERS = ("single", "isolated", "clustered", "linear")
PER_LAYER = 6
ATTEMPTS = 2
DESCRIPTOR_FILES = ("public_scene.json", "family_initial.json")
SELECTION_RULE = (
    "读取基线 external_attempt_path 下的 candidates.json；只取 accepted == true 且 vehicle_count >= 6 的记录。"
    "按 layout 分为四层：single、isolated、clustered、linear。每层按 candidate_index 升序，取前 6 个，"
    "共 24 个 family。某层不足 6 个时，取该层全部，并在登记中写明实际数量。"
)


def entry_commit():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()


def select_families(baseline):
    """Deterministic layer selection; planning outcomes are never consulted."""
    attempt = Path(baseline["external_attempt_path"])
    candidates = read_json(attempt / "candidates.json")
    eligible = [row for row in candidates if row["accepted"] and row["vehicle_count"] >= 6]
    unknown = sorted({row["layout"] for row in eligible if row["layout"] not in LAYERS})
    layers, below = {}, {}
    for layer in LAYERS:
        pool = sorted((row for row in eligible if row["layout"] == layer), key=lambda r: r["candidate_index"])
        layers[layer] = pool[:PER_LAYER]
        if len(pool) < PER_LAYER:
            below[layer] = len(pool)
    return attempt, candidates, layers, below, unknown, {row["candidate_index"]: row for row in baseline["families"]}


def build_selection(layers, candidates, families):
    """Verify map digests, then emit one registration row and one loaded map per selected family."""
    by_index = {row["candidate_index"]: row for row in candidates}
    selected, maps, anomalies = [], {}, []
    for layer in LAYERS:
        for candidate in layers[layer]:
            index = candidate["candidate_index"]
            if index not in families:
                raise P0ContractError(f"Selected candidate {index} is absent from the frozen baseline")
            record = families[index]
            directory = Path(record["directory"])
            digests = {}
            for name in DESCRIPTOR_FILES:
                if name not in record["sha256"]:
                    raise P0ContractError(f"Baseline row {index} lacks a digest for {name}")
                actual = sha(directory / name)
                if actual != record["sha256"][name]:
                    raise P0ContractError(f"Frozen map changed since the baseline: {directory / name}")
                digests[name] = actual
            family = read_json(directory / "family_initial.json")
            scene = read_json(directory / "public_scene.json")
            facilities = sum(1 for entity in scene["entities"] if entity["type"] == "facility")
            linked = len(family.get("facility_sampling", {}).get("links", [])) + 1
            if not facilities == candidate["facility_count"] == linked:
                anomalies.append({"candidate_index": index,
                                  "facility_count_scene_candidate_links": [facilities, candidate["facility_count"], linked]})
            if layer != candidate["layout"] or layer != family["layout"]:
                anomalies.append({"candidate_index": index, "layout_selected_candidate_family": [layer, candidate["layout"], family["layout"]]})
            if candidate["vehicle_count"] != len(family["initial_states"]):
                anomalies.append({"candidate_index": index,
                                  "vehicle_count_candidate_family": [candidate["vehicle_count"], len(family["initial_states"])]})
            if candidate["family_id"] != family["family_id"]:
                anomalies.append({"candidate_index": index, "family_id_candidate_family": [candidate["family_id"], family["family_id"]]})
            selected.append({"candidate_index": index, "family_id": family["family_id"], "layout": layer,
                             "facility_count": facilities, "vehicle_count": candidate["vehicle_count"],
                             "map_side_m": family["map_side_m"], "source_sha256": digests})
            maps[family["family_id"]] = (family, scene)
    return selected, maps, anomalies


def sample_descriptors(selected, maps):
    """Two common slots x five intents per family; aborted descriptions are discarded."""
    descriptors, counts = [], {}
    for row in selected:
        family, scene = maps[row["family_id"]]
        records = sample_family_descriptors((scene, family, ATTEMPTS))
        regular = [record for record in records if record["subset"] == "regular"]
        if len(regular) != ATTEMPTS * len(INTENTS):
            raise P0ContractError(f"Unexpected regular descriptor count for {row['family_id']}")
        for record in regular:
            if record["family_id"] != row["family_id"]:
                raise P0ContractError("Descriptor family identity disagrees with its registration row")
        descriptors.extend(regular)
        counts[row["family_id"]] = {"regular": len(regular), "discarded_aborted": len(records) - len(regular)}
    descriptors.sort(key=lambda record: record["skeleton_id"])
    if len({record["skeleton_id"] for record in descriptors}) != len(descriptors):
        raise P0ContractError("Duplicate skeleton_id in sampled descriptors")
    return descriptors, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    args = parser.parse_args()
    baseline = read_json(args.baseline)
    attempt, candidates, layers, below, unknown, families = select_families(baseline)
    selected, maps, anomalies = build_selection(layers, candidates, families)
    descriptors, counts = sample_descriptors(selected, maps)
    stamp = datetime.now(timezone.utc)
    out = DEFAULT_DATA / f"attempt_s15desc_{stamp.strftime('%Y%m%dT%H%M%SZ')}"
    out.mkdir(parents=True, exist_ok=False)
    save_json(out / "private_skeleton_descriptors.json", descriptors)
    skeleton_ids = [record["skeleton_id"] for record in descriptors]
    registration = {"schema": "traj2language.s15_stage2_registration/1", "source_attempt": str(attempt),
                    "selected": selected, "selection_rule": SELECTION_RULE, "baseline": str(args.baseline),
                    "baseline_sha256": sha(args.baseline), "entry_commit": entry_commit(),
                    "per_layout_counts": {layer: len(layers[layer]) for layer in LAYERS},
                    "layers_below_quota": below, "unrecognised_layouts": unknown,
                    "descriptor_attempt": str(out), "descriptor_count": len(descriptors),
                    "private_skeleton_descriptors_sha256": sha(out / "private_skeleton_descriptors.json"),
                    "skeleton_ids": skeleton_ids, "intents": list(INTENTS),
                    "sampling": {"attempts_per_family": ATTEMPTS, "subset": "regular",
                                 "descriptors_per_family": ATTEMPTS * len(INTENTS),
                                 "discarded_aborted": sum(v["discarded_aborted"] for v in counts.values())},
                    "descriptor_counts_by_family": counts, "cross_checks": anomalies,
                    "created_utc": stamp.isoformat(), "script": "scripts/run_v07_s15_descriptors.py",
                    "script_sha256": sha(Path(__file__))}
    save_json(out / "registration.json", registration)
    with tempfile.TemporaryDirectory() as temporary:
        jobs = descriptor_jobs(out, skeleton_ids, Path(temporary))
    if len(jobs) != len(descriptors):
        raise P0ContractError(f"descriptor_jobs returned {len(jobs)} jobs for {len(descriptors)} descriptors")
    if [job["descriptor"]["skeleton_id"] for job in jobs] != skeleton_ids:
        raise P0ContractError("descriptor_jobs reordered the registered skeleton list")
    print(f"OUTPUT {out}", flush=True)
    print({"descriptor_count": len(descriptors), "per_layout_counts": registration["per_layout_counts"],
           "cross_check_anomalies": len(anomalies),
           "private_skeleton_descriptors_sha256": registration["private_skeleton_descriptors_sha256"]}, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
