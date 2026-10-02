"""Read-only v0.5 DR composition audit against the frozen 383 candidate draws.

Writes only new diagnostic artifacts beside this script. It never invokes a
planner, changes the profile, or starts SITL.
"""

from collections import Counter
import csv
import hashlib
import itertools
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
GENERATED = PROJECT / "tmp_v05" / "dr" / "generated_130"
MANIFEST_PATH = GENERATED / "generation_manifest.json"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolved_recon_axis(task):
    """Mirror reconnaissance.plan_routes' auto axis rule, without planning."""
    requested = task["planner"]["params"]["partition_axis"]
    if requested != "auto":
        return requested, None
    vehicles = task["scenario"]["vehicles"]
    region_id = task["mission"]["target_region_id"]
    region = next(r for r in task["scenario"]["regions"] if r["id"] == region_id)
    centroid_east = sum(v["east_m"] for v in vehicles) / len(vehicles)
    centroid_north = sum(v["north_m"] for v in vehicles) / len(vehicles)
    center_east = region["min_east_m"] + region["width_m"] / 2
    center_north = region["min_north_m"] + region["height_m"] / 2
    delta_east = centroid_east - center_east
    delta_north = centroid_north - center_north
    north_south = abs(delta_north) >= abs(delta_east)
    axis = "east" if north_south else "north"
    side = (("north" if delta_north >= 0 else "south") if north_south
            else ("east" if delta_east >= 0 else "west"))
    return axis, side


def main():
    manifest = read_json(MANIFEST_PATH)
    candidates = manifest["candidates"]
    assert len(candidates) == 383
    accepted = [c for c in candidates if c["status"] == "accepted"]
    assert len(accepted) == 130
    candidate_rows = []
    scene_axis_checks = []
    requested_axes = Counter()
    inferred_side_mismatches = []
    for candidate in candidates:
        sample = candidate["sampled_parameters"]
        recon = next(a for a in candidate["attempts"] if a["intent"] == "reconnaissance")
        task = read_json(GENERATED / recon["task"])
        requested_axes[task["planner"]["params"]["partition_axis"]] += 1
        axis, inferred_side = resolved_recon_axis(task)
        row = {
            "candidate_id": candidate["candidate_id"],
            "base_index": candidate["base_index"],
            "accepted": candidate["status"] == "accepted",
            "N": sample["vehicle_count"],
            "formation": sample["formation"],
            "entry_side": sample["entry_side"],
            "recon_partition_axis_resolved": axis,
            "recon_partition_axis_requested": task["planner"]["params"]["partition_axis"],
            "recon_inferred_entry_side": inferred_side,
        }
        candidate_rows.append(row)
        if inferred_side is not None and inferred_side != sample["entry_side"]:
            inferred_side_mismatches.append(candidate["candidate_id"])
        if row["accepted"]:
            scene_path = GENERATED / "scenes" / f"reconnaissance_{candidate['base_index']:04d}_v00.json"
            scene = read_json(scene_path)
            compiled_axis = scene["planning"]["partition_axis"]
            compiled_side = scene["planning"]["partition_axis_resolution"]["inferred_entry_side"]
            assert axis == compiled_axis, (candidate["candidate_id"], axis, compiled_axis)
            assert inferred_side == compiled_side, (candidate["candidate_id"], inferred_side, compiled_side)
            assert scene["family_id"] == candidate["family_id"]
            scene_axis_checks.append(candidate["candidate_id"])

    categories = itertools.product((2, 3, 4), ("line", "cluster"),
                                   ("north", "east", "south", "west"), ("east", "north"))
    counts_all = Counter((r["N"], r["formation"], r["entry_side"], r["recon_partition_axis_resolved"])
                         for r in candidate_rows)
    counts_accepted = Counter((r["N"], r["formation"], r["entry_side"], r["recon_partition_axis_resolved"])
                              for r in candidate_rows if r["accepted"])
    table = []
    for N, formation, side, axis in categories:
        key = (N, formation, side, axis)
        drawn, kept = counts_all[key], counts_accepted[key]
        table.append({
            "N": N, "formation": formation, "entry_side": side,
            "recon_partition_axis_resolved": axis,
            "candidate_draws": drawn, "accepted_scenes": kept,
            "rejected_candidates": drawn - kept,
            "acceptance_rate": kept / drawn if drawn else None,
        })
    assert sum(r["candidate_draws"] for r in table) == 383
    assert sum(r["accepted_scenes"] for r in table) == 130

    def margin(fields):
        groups = {}
        for row in table:
            key = tuple(row[f] for f in fields)
            values = groups.setdefault(key, [0, 0])
            values[0] += row["candidate_draws"]
            values[1] += row["accepted_scenes"]
        return [dict(zip(fields, key), candidate_draws=v[0], accepted_scenes=v[1],
                     acceptance_rate=v[1] / v[0] if v[0] else None)
                for key, v in sorted(groups.items())]

    output = {
        "source_manifest": str(MANIFEST_PATH.relative_to(PROJECT)).replace("\\", "/"),
        "source_manifest_sha256": sha256(MANIFEST_PATH),
        "candidate_draws": len(candidates),
        "accepted_scenes": len(accepted),
        "requested_recon_axes": dict(requested_axes),
        "accepted_scene_axis_crosschecks": len(scene_axis_checks),
        "sampled_vs_inferred_entry_side_mismatches": inferred_side_mismatches,
        "full_four_way_table": table,
        "margins": {
            "N_formation": margin(("N", "formation")),
            "N_formation_entry_side": margin(("N", "formation", "entry_side")),
            "N_formation_axis": margin(("N", "formation", "recon_partition_axis_resolved")),
            "N": margin(("N",)),
            "formation": margin(("formation",)),
            "entry_side": margin(("entry_side",)),
            "axis": margin(("recon_partition_axis_resolved",)),
        },
        "zero_candidate_cells": sum(r["candidate_draws"] == 0 for r in table),
        "zero_accepted_cells": sum(r["accepted_scenes"] == 0 for r in table),
    }
    (HERE / "composition_counts.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (HERE / "composition_four_way.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    with (HERE / "composition_candidate_rows.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(candidate_rows[0]))
        writer.writeheader()
        writer.writerows(candidate_rows)
    print(json.dumps({key: output[key] for key in (
        "candidate_draws", "accepted_scenes", "requested_recon_axes",
        "accepted_scene_axis_crosschecks", "sampled_vs_inferred_entry_side_mismatches",
        "zero_candidate_cells", "zero_accepted_cells")}, ensure_ascii=False, indent=2))
    print("N × formation:", output["margins"]["N_formation"])


if __name__ == "__main__":
    main()
