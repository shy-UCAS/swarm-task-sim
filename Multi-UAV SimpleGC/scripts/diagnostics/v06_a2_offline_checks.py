"""Pause A2 offline acceptance and distribution evidence; never launch SITL."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

from v06_offline_checks import (PROJECT, distribution, no_flight, planning,
                               read, save, write_guard)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def archive_snapshot(output, archive):
    inventory = {}
    for path in Path(archive).rglob("*"):
        if path.is_file():
            stat = path.stat()
            inventory[path.relative_to(archive).as_posix()] = [stat.st_size, stat.st_mtime_ns]
    save(output / "archive_inventory_before.json", inventory)
    return dict(files=len(inventory), method="path, size, mtime_ns, including .git")


def echelon_gate(output, reference):
    """Predeclare first 300 raw A candidates, without filtering their status."""
    from swarm_sim.generation_v2 import apply_flight_pattern
    from swarm_sim.rapid_passage import echelon_candidate_registration
    from swarm_sim.tasks import compile_task
    reference = Path(reference).resolve()
    candidates = read(reference)["candidates"][:300]
    if len(candidates) != 300:
        raise ValueError("echelon gate requires exactly 300 frozen raw candidates")
    rows = []
    with echelon_candidate_registration():
        for candidate in candidates:
            attempts = [a for a in candidate["attempts"] if a["intent"] == "rapid_passage"]
            if len(attempts) != 1:
                raise ValueError("reference candidate must contain one rapid passage task")
            attempt = attempts[0]
            source = reference.parent / attempt["task"]
            if digest(source) != attempt["task_sha256"]:
                raise ValueError("frozen gate input task hash mismatch")
            task = apply_flight_pattern(read(source), "echelon")
            save(output / (candidate["candidate_id"] + "_echelon_task.json"), task)
            row = dict(candidate_id=candidate["candidate_id"], family_id=candidate["family_id"],
                       original_family_status=candidate["status"], source_task=str(source),
                       source_task_sha256=digest(source), planned=False)
            try:
                scene = compile_task(task)
                row.update(planned=True, clearance_m=scene["planning"]["nominal_min_clearance_m"],
                           duration_s=scene["planning"]["nominal_time_estimate_s"],
                           world_bounds_pass=scene["planning"]["feasibility_checks"]["command_limits"]["world_bounds_pass"])
                save(output / (candidate["candidate_id"] + "_echelon_scene.json"), scene)
            except (ValueError, TypeError, KeyError, NotImplementedError) as exc:
                row["reason"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
    passed = sum(row["planned"] for row in rows)
    report = dict(check="echelon_registration_gate", reference=str(reference),
        reference_sha256=digest(reference), denominator="first 300 raw candidates in frozen pause-A manifest, including rejected families",
        candidates=300, planned=passed, rejected=300-passed, planning_rate=passed/300,
        required_rate=.9, required_passes=270, enable=passed >= 270,
        longitudinal_step_m=2.0, parameter_retuning=False,
        original_status_counts=dict(Counter(c["status"] for c in candidates)),
        clearance_m=distribution([r.get("clearance_m") for r in rows]),
        below_10m=sum(r.get("clearance_m", 10) < 10 for r in rows),
        simulation_runs=0, rows=rows)
    save(output / "echelon_gate.json", report)
    return report


def a2_planning(output, profile):
    from swarm_sim.generation import canonical_hash, verify_generation
    report = planning(output, profile)
    generated = output / "generated_v06"
    listing, manifest = verify_generation(generated / "mission_list.json")
    candidates = manifest["candidates"]
    groups = defaultdict(list)
    for candidate in candidates:
        for attempt in candidate["attempts"]:
            groups[(attempt["intent"], attempt["selected_flight_pattern"])].append(
                dict(candidate_id=candidate["candidate_id"], family_id=candidate["family_id"],
                     family_accepted=candidate["status"] == "accepted", **attempt))
    candidate_groups = []
    for (intent, pattern), rows in sorted(groups.items()):
        rejected = sum(r["status"] != "planned" for r in rows)
        candidate_groups.append(dict(intent=intent, flight_pattern=pattern, candidates=len(rows),
            planned=len(rows)-rejected, planning_rejected=rejected, rejection_rate=rejected/len(rows),
            family_rejected=sum(not r["family_accepted"] for r in rows),
            published=sum(r["family_accepted"] for r in rows)))
    shared = defaultdict(list)
    families = defaultdict(list)
    for entry in listing["missions"]:
        spec = read(generated / entry["task"])
        sampled = entry["sampled_parameters"]
        values = dict(vehicle_count=len(spec["scenario"]["vehicles"]),
            speed_m_s=spec["execution"]["speed_m_s"], return_required=spec["mission"]["return_required"],
            entry_side=sampled["entry_side"], **{key: sampled[key] for key in (
                "region_width_m", "region_height_m", "region_center_east_m", "region_center_north_m",
                "entry_distance_m", "entry_lateral_offset_fraction", "line_spacing_m", "line_rotation_deg")})
        row = dict(family_id=entry["family_id"], scene_seed=entry["scene_seed"],
                   scenario=spec["scenario"], sampled_parameters=sampled, **values)
        shared[entry["intent"]].append(row)
        families[entry["family_id"]].append(entry)
    joint_hashes = {intent: canonical_hash(sorted(rows, key=lambda r: r["family_id"]))
                    for intent, rows in shared.items()}
    categorical = ("vehicle_count", "speed_m_s", "return_required", "entry_side")
    numeric = ("region_width_m", "region_height_m", "region_center_east_m", "region_center_north_m",
               "entry_distance_m", "entry_lateral_offset_fraction", "line_spacing_m", "line_rotation_deg")
    distributions = {intent: dict(tasks=len(rows),
        categorical={key: dict(sorted(Counter(str(row[key]) for row in rows).items())) for key in categorical},
        numeric={key: distribution([row[key] for row in rows]) for key in numeric})
        for intent, rows in sorted(shared.items())}
    accepted_ids = {c["candidate_id"] for c in candidates if c["status"] == "accepted"}
    expected_intents = {"reconnaissance", "patrol", "rapid_passage"}
    invariants = dict(
        all_selected_patterns_pass_before_family_accept=all(
            (c["status"] == "accepted") == (bool(c["attempts"]) and all(a["status"] == "planned" for a in c["attempts"]))
            for c in candidates),
        no_rejected_task_published=all(e["status"] == "planned" and e["scene"] is not None for e in listing["missions"]),
        only_accepted_candidates_published=all(e["candidate_id"] in accepted_ids for e in listing["missions"]),
        all_families_have_exact_three_intents=all(len(rows) == 3 and {e["intent"] for e in rows} == expected_intents
                                                for rows in families.values()),
        shared_joint_distributions_identical=len(joint_hashes) == 3 and len(set(joint_hashes.values())) == 1,
        full_size=len(families) == 300 and len(listing["missions"]) == 900)
    report.update(check="v06_a2_offline_planning", candidate_groups=candidate_groups,
        family_acceptance=dict(accepted=len(accepted_ids), attempted=len(candidates),
            rejected=len(candidates)-len(accepted_ids), exhausted_bases=sum(b["status"] != "accepted" for b in manifest["bases"])),
        accepted_shared_distributions=distributions, accepted_shared_joint_sha256=joint_hashes,
        invariants=invariants, pass_all=all(invariants.values()))
    save(output / "accepted_shared_parameters.json", shared)
    save(output / "a2_planning_report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("archive-snapshot", "echelon-gate", "planning"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()
    required = {"archive-snapshot": args.archive, "echelon-gate": args.reference, "planning": args.profile}
    if required[args.action] is None:
        parser.error("missing input for action")
    from swarm_sim.parallel_batch import resolve_data_root
    output = resolve_data_root(str(args.output))
    if output.exists():
        parser.error("output must be a new directory")
    sys.addaudithook(no_flight)
    output.mkdir(parents=True)
    sys.addaudithook(write_guard(output))
    report = (archive_snapshot(output, args.archive) if args.action == "archive-snapshot" else
              echelon_gate(output, args.reference) if args.action == "echelon-gate" else a2_planning(output, args.profile))
    print(json.dumps({k: v for k, v in report.items() if k not in ("rows", "rejections", "rejection_reasons")},
                     ensure_ascii=False, indent=2))
    return int(report.get("pass_all") is False)


if __name__ == "__main__":
    raise SystemExit(main())
