"""Write reproducible WP-R sampling, numbering, and V06 hash evidence (no SITL)."""

import argparse
import json
import math
import random
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import NormalDist

from swarm_sim.generation import file_hash, generate
from swarm_sim.generation_v2 import scene_seed
from swarm_sim.scene_samplers import get_sampler


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "generation_profiles/recon_pilot_v04_v06.json"
GOLDEN = ROOT / "generated/recon_pilot_v04_v06_20261002"


def _wilson(successes, count, z):
    proportion = successes / count
    denominator = 1 + z * z / count
    center = (proportion + z * z / (2 * count)) / denominator
    half = z * math.sqrt(proportion * (1 - proportion) / count + z * z / (4 * count * count)) / denominator
    return [max(0, center - half), min(1, center + half)]


def review_sampling():
    template = json.loads((ROOT / "missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
    scenario_template = template["scenario"]
    sampler = get_sampler("random_spawn_v1")
    params = sampler.normalize_params({})
    rows = defaultdict(lambda: dict(samples=0, first_rank_matches=0, full_permutation_matches=0))
    categories = Counter()
    measurements = defaultdict(list)
    violations = []
    for index in range(1000):
        seed = scene_seed(2026100205, index, 0)
        try:
            scenario, sampled = sampler.sample_scene(scenario_template, params, random.Random(seed))
        except ValueError as exc:
            violations.append(dict(index=index, seed=seed, reason=f"sampling: {exc}"))
            continue
        count = len(scenario["vehicles"])
        side, formation = sampled["entry_side"], sampled["formation"]
        categories[(count, side, formation)] += 1
        rank_fields = (("east_m", "north_m") if side in ("north", "south")
                       else ("north_m", "east_m"))
        ranked = sorted(scenario["vehicles"], key=lambda vehicle: (
            vehicle[rank_fields[0]], vehicle[rank_fields[1]], vehicle["heading_deg"]))
        row = rows[count]
        row["samples"] += 1
        row["first_rank_matches"] += int(ranked[0]["id"] == "uav_01")
        row["full_permutation_matches"] += int([vehicle["id"] for vehicle in ranked] ==
                                               [f"uav_{i:02d}" for i in range(1, count + 1)])
        region = scenario["regions"][0]
        width, height = region["width_m"], region["height_m"]
        center_east = region["min_east_m"] + width / 2
        center_north = region["min_north_m"] + height / 2
        measurements["region_width_m"].append(width)
        measurements["region_height_m"].append(height)
        measurements["region_center_east_m"].append(center_east)
        measurements["region_center_north_m"].append(center_north)
        measurements["entry_distance_m"].append(sampled["entry_distance_m"])
        measurements["entry_lateral_offset_fraction"].append(sampled["entry_lateral_offset_fraction"])
        measurements["heading_deg"].extend(v["heading_deg"] for v in scenario["vehicles"])
        world = scenario["world"]
        if not (30 <= width <= 50 and 20 <= height <= 35 and
                -10 <= center_east <= 10 and -10 <= center_north <= 10 and
                world["east_bounds_m"][0] <= region["min_east_m"] and
                region["min_east_m"] + width <= world["east_bounds_m"][1] and
                world["north_bounds_m"][0] <= region["min_north_m"] and
                region["min_north_m"] + height <= world["north_bounds_m"][1]):
            violations.append(dict(index=index, seed=seed, reason="region or world bounds"))
        for vehicle in scenario["vehicles"]:
            if not (world["east_bounds_m"][0] <= vehicle["east_m"] <= world["east_bounds_m"][1] and
                    world["north_bounds_m"][0] <= vehicle["north_m"] <= world["north_bounds_m"][1] and
                    0 <= vehicle["heading_deg"] < 360):
                violations.append(dict(index=index, seed=seed, reason="vehicle bounds or heading"))
        for i, left in enumerate(scenario["vehicles"]):
            for right in scenario["vehicles"][i + 1:]:
                distance = math.dist((left["east_m"], left["north_m"]),
                                     (right["east_m"], right["north_m"]))
                measurements["initial_separation_m"].append(distance)
                if distance + 1e-9 < max(8.0, template["execution"]["min_separation_m"]):
                    violations.append(dict(index=index, seed=seed, reason="initial separation"))
    z = NormalDist().inv_cdf(1 - 0.05 / (2 * 6))
    confidence = 1 - 0.05 / 6
    numbering = []
    for count in sorted(rows):
        row = rows[count]
        for name, expected in (("first_rank_matches", 1 / count),
                               ("full_permutation_matches", 1 / math.factorial(count))):
            interval = _wilson(row[name], row["samples"], z)
            numbering.append(dict(vehicle_count=count, metric=name, samples=row["samples"],
                matches=row[name], observed=row[name] / row["samples"], random_baseline=expected,
                confidence_level=confidence, wilson_interval=interval,
                baseline_inside_interval=interval[0] <= expected <= interval[1]))
    return dict(seed_scheme="hierarchical_scene_mission_v1", master_seed=2026100205,
        base_indices=[0, 999], candidate_index=0, requested_samples=1000,
        sampled_count=sum(row["samples"] for row in rows.values()),
        sampler="random_spawn_v1", sampler_params=params,
        numbering_rank_rule="N/S: east,north,heading; E/W: north,east,heading; never ID",
        numbering=numbering,
        categories=[dict(vehicle_count=n, entry_side=side, formation=formation, samples=value)
                    for (n, side, formation), value in sorted(categories.items())],
        measurements={name: dict(min=min(values), max=max(values))
                      for name, values in sorted(measurements.items())},
        violations=violations,
        passed=(not violations and sum(row["samples"] for row in rows.values()) == 1000 and
                set(rows) == {2, 3, 4} and all(item["baseline_inside_interval"] for item in numbering)))


def review_v06_hashes():
    golden = {path.relative_to(GOLDEN).as_posix(): file_hash(path)
              for path in GOLDEN.rglob("*.json")}
    with tempfile.TemporaryDirectory() as directory:
        replay = Path(directory) / "v06_replay"
        generate(PROFILE, replay)
        generated = {path.relative_to(replay).as_posix(): file_hash(path)
                     for path in replay.rglob("*.json")}
    names = sorted(set(golden) | set(generated))
    files = [dict(path=name, golden_sha256=golden.get(name), replay_sha256=generated.get(name),
                  match=golden.get(name) is not None and golden.get(name) == generated.get(name))
             for name in names]
    return dict(profile=PROFILE.relative_to(ROOT).as_posix(),
                golden=GOLDEN.relative_to(ROOT).as_posix(), expected_file_count=33,
                golden_file_count=len(golden), replay_file_count=len(generated),
                golden_manifest_sha256=golden.get("generation_manifest.json"),
                replay_manifest_sha256=generated.get("generation_manifest.json"),
                files=files, passed=len(golden) == len(generated) == 33 and all(f["match"] for f in files))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = dict(version="wp_r_offline_review_v1", sampling=review_sampling(),
                  v06_hash_replay=review_v06_hashes())
    result["passed"] = result["sampling"]["passed"] and result["v06_hash_replay"]["passed"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(dict(output=str(args.output), passed=result["passed"],
                          sampled_count=result["sampling"]["sampled_count"],
                          violations=len(result["sampling"]["violations"]),
                          replayed_files=result["v06_hash_replay"]["replay_file_count"])))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
