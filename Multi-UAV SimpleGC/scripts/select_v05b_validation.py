"""Select six v0.5 r1.1 validation cases from the accepted v05b DR set.

This module only compiles plans and writes a separate, versioned selection
bundle. It never starts SITL and never edits the source generation directory.
"""

import argparse
import copy
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swarm_sim.generation import canonical_hash, checked_path, file_hash, save_json, verify_generation
from swarm_sim.generation_v2 import normalize_profile
from swarm_sim.tasks import compile_task, validate_task_binding


VERSION = "v05b_validation_selection_v1"
CASE_ORDER = ("VP1", "VP2", "VP3", "VP4", "VR1", "VR2")
RELAXATION_ORDER = ("entry_sides", "laps", "return_required")
REQUIREMENTS = {
    "VP1": dict(vehicle_count=3, entry_sides=None, laps=2, return_required=True, intent="patrol"),
    "VP2": dict(vehicle_count=4, entry_sides=None, laps=None, return_required=None, intent="patrol"),
    "VP3": dict(vehicle_count=2, entry_sides=None, laps=3, return_required=False, intent="patrol"),
    "VR1": dict(vehicle_count=3, entry_sides=("east", "west"), laps=None,
                return_required=None, intent="reconnaissance"),
    "VR2": dict(vehicle_count=4, entry_sides=None, laps=None,
                return_required=None, intent="reconnaissance"),
}


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _matches(row, constraints):
    return (row["vehicle_count"] == constraints["vehicle_count"]
            and (constraints["entry_sides"] is None or row["entry_side"] in constraints["entry_sides"])
            and (constraints["laps"] is None or row["laps"] == constraints["laps"])
            and (constraints["return_required"] is None
                 or row["return_required"] is constraints["return_required"]))


def choose_case(rows, case_id):
    """Apply prescribed relaxations one at a time; never relax vehicle count."""
    if case_id not in REQUIREMENTS:
        raise ValueError(f"unknown validation case {case_id}")
    constraints = copy.deepcopy(REQUIREMENTS[case_id])
    available = [row for row in rows if row["vehicle_count"] == constraints["vehicle_count"]]
    trace = []
    relaxed = []
    for criterion in (None,) + RELAXATION_ORDER:
        if criterion is not None:
            original = constraints[criterion]
            if original is None:
                continue
            constraints[criterion] = None
            relaxed.append(dict(criterion=criterion, original=original, applied_order=len(relaxed) + 1))
        eligible = [row for row in available if _matches(row, constraints)]
        trace.append(dict(after_relaxation=criterion, eligible_count=len(eligible)))
        if eligible:
            if case_id == "VP2":
                # The old r1 P/N stress case is a preference, not a new gate.
                key = lambda row: (row["patrol_prefilter_margin_m"], row["base_index"])
            else:
                key = lambda row: row["base_index"]
            selected = min(eligible, key=key)
            return dict(case_id=case_id, selected_base_index=selected["base_index"],
                        selected_candidate=selected["candidate_id"],
                        selected_mission_id=selected["entries"][constraints["intent"]]["mission_id"],
                        selected_criteria=dict(vehicle_count=selected["vehicle_count"],
                                               entry_side=selected["entry_side"], laps=selected["laps"],
                                               return_required=selected["return_required"]),
                        original_criteria=REQUIREMENTS[case_id], relaxed=relaxed,
                        filter_trace=trace,
                        patrol_prefilter_margin_m=selected["patrol_prefilter_margin_m"]
                            if constraints["intent"] == "patrol" else None)
    raise ValueError(f"{case_id}: no accepted N={constraints['vehicle_count']} scene even after ordered relaxation")


def choose_cases(rows):
    selected = {case: choose_case(rows, case) for case in REQUIREMENTS}
    selected["VP4"] = dict(case_id="VP4", source_case="VP1",
        selected_base_index=selected["VP1"]["selected_base_index"],
        selected_candidate=selected["VP1"]["selected_candidate"],
        selected_mission_id=selected["VP1"]["selected_mission_id"] + "_hold1",
        selected_criteria=selected["VP1"]["selected_criteria"],
        original_criteria=dict(REQUIREMENTS["VP1"], terminal_hold_s=1),
        relaxed=copy.deepcopy(selected["VP1"]["relaxed"]),
        derivation="same normalized VP1 task except execution.terminal_hold_s: 0 -> 1")
    return {case: selected[case] for case in CASE_ORDER}


def derive_vp4(task):
    """Compile the VP1 task with only its terminal dwell changed to one second."""
    if task["mission"]["intent"] != "patrol" or task["execution"]["terminal_hold_s"] != 0:
        raise ValueError("VP4 requires an original patrol task with terminal_hold_s=0")
    derived = copy.deepcopy(task)
    derived["execution"]["terminal_hold_s"] = 1.0
    scene = compile_task(derived)
    if scene["task_spec"] != derived:
        raise ValueError("VP4 normalization changed more than terminal_hold_s")
    stripped = copy.deepcopy(derived)
    stripped["execution"]["terminal_hold_s"] = 0.0
    if stripped != task:
        raise ValueError("VP4 unexpectedly changed task sampling or other execution fields")
    validate_task_binding(scene)
    return derived, scene


def validate_dr_review(review_path, profile_path, profile, generated):
    """Require every predeclared DR gate and bind the review to exact inputs."""
    review = _read(review_path)
    gate = review.get("gate")

    def all_pass(value):
        if type(value) is bool:
            return value
        return isinstance(value, dict) and bool(value) and all(all_pass(v) for v in value.values())

    if not isinstance(gate, dict) or gate.get("pass") is not True or not all_pass(gate):
        raise ValueError("v05b DR review has a failed or incomplete gate")
    expected = dict(generation_manifest_file_sha256=file_hash(generated / "generation_manifest.json"),
                    profile_file_sha256=file_hash(profile_path),
                    profile_canonical_sha256=canonical_hash(profile))
    for key, digest in expected.items():
        if review.get(key) != digest:
            raise ValueError(f"v05b DR review {key} does not bind this generated/profile input")
    return review


def accepted_views(profile_path, generated, review_path):
    """Validate the new DR gate and expose only complete accepted scene pairs."""
    profile_path, generated = Path(profile_path).resolve(), Path(generated).resolve()
    profile = normalize_profile(profile_path)
    if (profile["scene_sampler"]["name"] != "random_spawn_v2"
            or profile["base_scene_count"] != 130 or profile["max_candidates_per_base"] != 20):
        raise ValueError("validation source must be the fixed 130-base, 20-draw random_spawn_v2 profile")
    listing, manifest = verify_generation(generated / "mission_list.json")
    if manifest["profile_sha256"] != canonical_hash(profile):
        raise ValueError("v05b profile fingerprint does not match generated DR")
    if manifest["scene_sampler"] != dict(name="random_spawn_v2", intent_agnostic=True):
        raise ValueError("source DR sampler/provenance differs from random_spawn_v2")
    review = validate_dr_review(Path(review_path).resolve(), profile_path, profile, generated)
    bases, candidates = manifest["bases"], manifest["candidates"]
    if len(bases) != 130 or any(b["base_index"] != index or b["status"] != "accepted"
                                for index, b in enumerate(bases)):
        raise ValueError("v05b DR must accept all 130 ordered bases before verification")
    if len(candidates) != manifest["counts"]["candidates"] or not candidates:
        raise ValueError("DR candidate ledger is incomplete")
    if (sum(c["status"] == "accepted" for c in candidates) / len(candidates)) < .30:
        raise ValueError("v05b DR joint feasibility below 30 percent")
    selected = {c["candidate_id"]: c for c in candidates if c["status"] == "accepted"}
    by_base = defaultdict(dict)
    for entry in listing["missions"]:
        if entry["status"] != "planned" or entry["intent"] in by_base[entry["base_index"]]:
            raise ValueError("accepted DR must have one planned entry per intent and base")
        by_base[entry["base_index"]][entry["intent"]] = entry
    views = []
    for base in bases:
        index, candidate_id = base["base_index"], base["selected_candidate"]
        candidate = selected.get(candidate_id)
        entries = by_base[index]
        if (candidate is None or candidate["base_index"] != index or
                set(entries) != {"patrol", "reconnaissance"} or
                any(e["candidate_id"] != candidate_id or e["family_id"] != base["family_id"]
                    for e in entries.values())):
            raise ValueError(f"base {index} lacks a matching accepted two-intent pair")
        patrol_entry, recon_entry = entries["patrol"], entries["reconnaissance"]
        patrol_task = _read(checked_path(generated, patrol_entry["task"]))
        recon_task = _read(checked_path(generated, recon_entry["task"]))
        patrol_scene = _read(checked_path(generated, patrol_entry["scene"]))
        prefilter = patrol_scene["planning"]["patrol_spacing_prefilter"]
        if not prefilter["passed"]:
            raise ValueError("accepted patrol scene fails its recorded prefilter")
        sampled = candidate["sampled_parameters"]
        count = len(patrol_task["scenario"]["vehicles"])
        if (count != (2, 3, 4)[index % 3] or count != sampled["vehicle_count"]
                or len(recon_task["scenario"]["vehicles"]) != count
                or recon_task["planner"]["params"]["partition_axis"] != "auto"
                or patrol_task["scenario"] != recon_task["scenario"]):
            raise ValueError(f"base {index} violates fixed N or shared-scene conditions")
        margin = prefilter["nominal_spacing_m"] - prefilter["minimum_spacing_m"]
        views.append(dict(base_index=index, candidate_id=candidate_id, entries=entries,
            vehicle_count=count, entry_side=sampled["entry_side"],
            laps=patrol_task["mission"]["intent_params"]["laps"],
            return_required=patrol_task["mission"]["return_required"],
            patrol_prefilter_margin_m=margin))
    if Counter(view["vehicle_count"] for view in views) != Counter({2: 44, 3: 43, 4: 43}):
        raise ValueError("accepted N strata differ from 44/43/43")
    return profile, listing, manifest, views, review


def write_bundle(profile_path, generated, review_path, output):
    """Create a new six-entry bundle suitable for run_mission_list after DR gates."""
    profile, _, manifest, rows, review = accepted_views(profile_path, generated, review_path)
    generated, output = Path(generated).resolve(), Path(output).resolve()
    cases = choose_cases(rows)
    by_index = {row["base_index"]: row for row in rows}
    vp1_row = by_index[cases["VP1"]["selected_base_index"]]
    vp1_task = _read(checked_path(generated, vp1_row["entries"]["patrol"]["task"]))
    vp4_task, vp4_scene = derive_vp4(vp1_task)
    if output.exists():
        raise ValueError("validation bundle output already exists; never overwrite an earlier selection")
    output.mkdir(parents=True)
    (output / "missions").mkdir()
    (output / "scenes").mkdir()
    (output / "generation_profile.json").write_bytes((generated / "generation_profile.json").read_bytes())
    selection = dict(version=VERSION, source_generation_directory=str(generated),
        source_manifest_sha256=file_hash(generated / "generation_manifest.json"),
        source_review_sha256=file_hash(review_path), source_review_gate=review["gate"],
        source_profile_file_sha256=file_hash(profile_path),
        source_profile_canonical_sha256=canonical_hash(profile),
        accepted_base_count=130, candidate_count=len(manifest["candidates"]),
        joint_feasible_fraction=130 / len(manifest["candidates"]),
        accepted_by_vehicle_count={str(n): sum(r["vehicle_count"] == n for r in rows) for n in (2, 3, 4)},
        case_order=list(CASE_ORDER), cases=cases,
        policy="accepted v05b DR scenes only; relax entry side, then K, then return; N never relaxed")
    save_json(output / "selection.json", selection)
    entries = []
    for case_id in CASE_ORDER:
        case = cases[case_id]
        row = by_index[case["selected_base_index"]]
        intent = "reconnaissance" if case_id.startswith("VR") else "patrol"
        source_entry = row["entries"][intent]
        entry = copy.deepcopy(source_entry)
        mission_id = (case["selected_mission_id"] if case_id == "VP4"
                      else source_entry["mission_id"])
        # A physical base may serve two intent cases; mission IDs remain unique.
        if any(previous["mission_id"] == mission_id for previous in entries):
            raise ValueError("selection repeats an intent task; choose a distinct accepted base")
        entry.update(mission_id=mission_id, validation_case_id=case_id,
                     source_manifest_sha256=selection["source_manifest_sha256"],
                     source_mission_id=source_entry["mission_id"],
                     task=f"missions/{mission_id}.json", scene=f"scenes/{mission_id}.json")
        if case_id == "VP4":
            save_json(output / entry["task"], vp4_task)
            save_json(output / entry["scene"], vp4_scene)
            entry.update(derived_from_case="VP1", derivation="terminal_hold_s_0_to_1_only_v1",
                original_task_sha256=source_entry["task_sha256"],
                normalized_task_sha256=canonical_hash(vp4_scene["task_spec"]))
        else:
            (output / entry["task"]).write_bytes(checked_path(generated, source_entry["task"]).read_bytes())
            (output / entry["scene"]).write_bytes(checked_path(generated, source_entry["scene"]).read_bytes())
        entry.update(task_sha256=file_hash(output / entry["task"]),
                     scene_sha256=file_hash(output / entry["scene"]))
        entries.append(entry)
    source_listing = _read(generated / "mission_list.json")
    source_listing["missions"] = entries
    save_json(output / "mission_list.json", source_listing)
    bundle_manifest = dict(schema_version=2, generator_version="v05b_validation_bundle_v1",
        source_manifest_sha256=selection["source_manifest_sha256"],
        source_review_sha256=selection["source_review_sha256"],
        profile_sha256=canonical_hash(profile), selection_version=VERSION,
        case_order=list(CASE_ORDER), counts=dict(missions=len(entries)),
        artifact_sha256={item.relative_to(output).as_posix(): file_hash(item)
                         for item in sorted(output.rglob("*.json"))})
    save_json(output / "generation_manifest.json", bundle_manifest)
    verify_generation(output / "mission_list.json")
    return selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True,
                        help="new v05b DR review.json with every gate passed")
    parser.add_argument("--output", type=Path, required=True,
                        help="new, empty directory for six-case validation bundle")
    args = parser.parse_args()
    result = write_bundle(args.profile, args.generated, args.review, args.output)
    print(json.dumps(dict(version=result["version"], candidate_count=result["candidate_count"],
        case_bases={key: value["selected_base_index"] for key, value in result["cases"].items()},
        relaxations={key: value["relaxed"] for key, value in result["cases"].items()}), ensure_ascii=False))


if __name__ == "__main__":
    main()
