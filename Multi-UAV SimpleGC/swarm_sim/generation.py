"""Deterministic, bounded mission sampling. This module never launches SITL."""

import copy
import hashlib
import json
import math
import random
from pathlib import Path

GENERATOR_VERSION = "shared_rectangle_generator_v1"
PROJECT = Path(__file__).resolve().parents[1]


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                                    allow_nan=False) + "\n", encoding="utf-8")


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _profile(source):
    base = PROJECT
    if isinstance(source, (str, Path)):
        source = Path(source).resolve()
        base = source.parent
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    else:
        data = copy.deepcopy(source)
    allowed = {"schema_version", "master_seed", "base_scene_count", "max_candidates_per_base",
               "vehicle_counts", "partition_axes", "strip_width_m", "sweep_length_m",
               "region_east_m", "region_north_m", "entry_distance_m", "entry_sides",
               "speeds_m_s", "return_required", "variant_speed_factors", "template", "template_spec"}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError("unknown generation profile fields")
    for key, low, high, default in (("schema_version", 1, 1, 1), ("master_seed", 0, 2**63 - 1, 42),
                                  ("base_scene_count", 1, 1000, 100), ("max_candidates_per_base", 1, 10, 3)):
        value = data.setdefault(key, default)
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            raise ValueError(f"{key} must be an integer in [{low}, {high}]")
    for key, default, valid in (
            ("vehicle_counts", [2, 3, 6], lambda v: isinstance(v, int) and not isinstance(v, bool) and 2 <= v <= 6),
            ("partition_axes", ["east", "north"], lambda v: v in ("east", "north")),
            ("entry_sides", ["low"], lambda v: v in ("low", "high")),
            ("speeds_m_s", [2.0, 2.5, 3.0], lambda v: _number(v) and v > 0),
            ("return_required", [True, False], lambda v: isinstance(v, bool)),
            ("variant_speed_factors", [1.0], lambda v: _number(v) and v > 0)):
        values = data.setdefault(key, default)
        if not isinstance(values, list) or not 1 <= len(values) <= 20 or not all(valid(v) for v in values):
            raise ValueError(f"invalid nonempty choices: {key}")
        if len({canonical_hash(v) for v in values}) != len(values):
            raise ValueError(f"duplicate generation choices: {key}")
    for key, default, positive in (("strip_width_m", [12.0, 18.0], True),
                                  ("sweep_length_m", [8.0, 14.0], True),
                                  ("entry_distance_m", [10.0, 16.0], True),
                                  ("region_east_m", [-20.0, 10.0], False),
                                  ("region_north_m", [-20.0, 10.0], False)):
        values = data.setdefault(key, default)
        if (not isinstance(values, list) or len(values) != 2 or not all(_number(v) for v in values)
                or values[0] > values[1] or (positive and values[0] <= 0)):
            raise ValueError(f"invalid range: {key}")
    if "template" in data and "template_spec" in data:
        raise ValueError("provide template or template_spec, not both")
    if "template_spec" not in data:
        template = Path(data.pop("template", str(PROJECT / "missions/recon_shared_3uav.json")))
        if not template.is_absolute():
            template = base / template
        data["template_spec"] = json.loads(template.read_text(encoding="utf-8-sig"))
    if data["template_spec"].get("schema_version") != 2:
        raise ValueError("generation template must be TaskSpec v2")
    return data


def _sample(profile, base_index, candidate_index, family):
    seed = int(canonical_hash([GENERATOR_VERSION, profile["master_seed"], base_index, candidate_index])[:16], 16) % (2**63)
    rng = random.Random(seed)
    spec = copy.deepcopy(profile["template_spec"])
    count = rng.choice(profile["vehicle_counts"])
    axis = rng.choice(profile["partition_axes"])
    side = rng.choice(profile["entry_sides"])
    strip = rng.uniform(*profile["strip_width_m"])
    sweep = rng.uniform(*profile["sweep_length_m"])
    east, north = (rng.uniform(*profile[key]) for key in ("region_east_m", "region_north_m"))
    entry = rng.uniform(*profile["entry_distance_m"])
    width, height = (count * strip, sweep) if axis == "east" else (sweep, count * strip)
    region = dict(id="R1", type="rectangle", min_east_m=east, min_north_m=north,
                  width_m=width, height_m=height)
    vehicles = []
    for i in range(count):
        lane = (i + 0.5) * strip
        outside = -entry if side == "low" else sweep + entry
        e, n = (east + lane, north + outside) if axis == "east" else (east + outside, north + lane)
        vehicles.append(dict(id=f"uav_{i + 1:02d}", sysid=i + 1, east_m=e, north_m=n, heading_deg=0.0))
    spec.update(task_id=f"recon_{base_index:04d}", family_id=family, seed=seed)
    spec["scenario"].update(scene_id=f"base_{base_index:04d}", regions=[region], vehicles=vehicles,
                            restricted_regions=[])
    spec["mission"].update(target_region_id="R1", return_required=rng.choice(profile["return_required"]))
    spec["planner"]["partition_axis"] = axis
    spec["execution"]["speed_m_s"] = rng.choice(profile["speeds_m_s"])
    return spec, dict(vehicle_count=count, partition_axis=axis, entry_side=side, strip_width_m=strip,
                      sweep_length_m=sweep, region_east_m=east, region_north_m=north,
                      entry_distance_m=entry, speed_m_s=spec["execution"]["speed_m_s"],
                      return_required=spec["mission"]["return_required"])


def generate(profile, output):
    """Freeze profile/template, sample bounded candidates and compile accepted variants."""
    from .tasks import compile_task

    profile = _profile(profile)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("generation output already exists; select a new directory")
    output.mkdir(parents=True)
    (output / "missions").mkdir()
    (output / "scenes").mkdir()
    (output / "candidates").mkdir()
    save_json(output / "generation_profile.json", profile)
    entries, candidates, bases = [], [], []
    family_namespace = canonical_hash({key: value for key, value in profile.items()
        if key not in ("base_scene_count", "max_candidates_per_base", "variant_speed_factors")})
    for base_index in range(profile["base_scene_count"]):
        base_id = canonical_hash([GENERATOR_VERSION, family_namespace, profile["master_seed"], base_index])[:20]
        family = f"recon_{base_id}"
        base_record = dict(base_scene_id=base_id, family_id=family, base_index=base_index, status="rejected")
        for candidate_index in range(profile["max_candidates_per_base"]):
            spec, sampled = _sample(profile, base_index, candidate_index, family)
            candidate_id = f"base_{base_index:04d}_candidate_{candidate_index:02d}"
            candidate_file = f"candidates/{candidate_id}.json"
            save_json(output / candidate_file, spec)
            record = dict(candidate_id=candidate_id, base_scene_id=base_id, family_id=family,
                          sampled_parameters=sampled, task=candidate_file, task_sha256=file_hash(output / candidate_file))
            try:
                base_scene = compile_task(spec)
            except (ValueError, TypeError, KeyError) as exc:
                record.update(status="planning_rejected", reason=f"{type(exc).__name__}: {exc}")
                candidates.append(record)
                continue
            record["status"] = "accepted"
            candidates.append(record)
            base_record.update(status="accepted", selected_candidate=candidate_id,
                               base_scene_sha256=canonical_hash(base_scene["task_spec"]["scenario"]))
            for variant_index, factor in enumerate(profile["variant_speed_factors"]):
                variant = copy.deepcopy(spec)
                variant_id = f"v{variant_index:02d}"
                mission_id = f"recon_{base_index:04d}_{variant_id}"
                variant["task_id"] = mission_id
                variant["execution"]["speed_m_s"] *= factor
                task_file, scene_file = f"missions/{mission_id}.json", f"scenes/{mission_id}.json"
                save_json(output / task_file, variant)
                entry = dict(mission_id=mission_id, base_scene_id=base_id, family_id=family,
                             base_scene_sha256=base_record["base_scene_sha256"], variant_id=variant_id,
                             planner_template_id=variant["planner"]["name"], task=task_file,
                             task_sha256=file_hash(output / task_file),
                             sampled_parameters=sampled)
                try:
                    scene = compile_task(variant)
                    save_json(output / task_file, scene["task_spec"])
                    save_json(output / scene_file, scene)
                    entry.update(status="planned", scene=scene_file, scene_sha256=file_hash(output / scene_file),
                                 task_sha256=file_hash(output / task_file),
                                 normalized_task_sha256=canonical_hash(scene["task_spec"]))
                except (ValueError, TypeError, KeyError) as exc:
                    entry.update(status="planning_rejected", reason=f"{type(exc).__name__}: {exc}")
                entries.append(entry)
            break
        bases.append(base_record)
    mission_list = dict(schema_version=1, generator_version=GENERATOR_VERSION,
                        generation_profile_sha256=file_hash(output / "generation_profile.json"), missions=entries)
    save_json(output / "mission_list.json", mission_list)
    manifest = dict(schema_version=1, generator_version=GENERATOR_VERSION, profile_sha256=canonical_hash(profile),
                    bases=bases, candidates=candidates, counts=dict(base_scenes=len(bases),
                        accepted_bases=sum(b["status"] == "accepted" for b in bases), candidates=len(candidates),
                        accepted_candidates=sum(c["status"] == "accepted" for c in candidates),
                        rejected_candidates=sum(c["status"] != "accepted" for c in candidates),
                        planned_missions=sum(e["status"] == "planned" for e in entries),
                        rejected_variants=sum(e["status"] != "planned" for e in entries)),
                    artifact_sha256={p.relative_to(output).as_posix(): file_hash(p)
                        for p in sorted(output.rglob("*.json"))},
                    limitation="planning only; no SITL execution, no classification accuracy")
    save_json(output / "generation_manifest.json", manifest)
    return dict(output=str(output), mission_list=str(output / "mission_list.json"), **manifest)


def checked_path(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError(f"path escapes evidence directory: {name}")
    return path


def verify_generation(mission_list_path):
    """Validate the frozen generation bundle before any run or resumed skip."""
    path = Path(mission_list_path).resolve()
    root = path.parent
    manifest = json.loads((root / "generation_manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["artifact_sha256"].items():
        if file_hash(checked_path(root, name)) != expected:
            raise ValueError(f"generation artifact changed: {name}")
    if path.name not in manifest["artifact_sha256"]:
        raise ValueError("mission list is not part of the generation manifest")
    listing = json.loads(path.read_text(encoding="utf-8"))
    if file_hash(root / "generation_profile.json") != listing["generation_profile_sha256"]:
        raise ValueError("generation profile changed")
    identities = [e["mission_id"] for e in listing["missions"]]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate mission identity in generation list")
    for entry in listing["missions"]:
        for key in ("task", "scene"):
            if key in entry and file_hash(checked_path(root, entry[key])) != entry[key + "_sha256"]:
                raise ValueError(f"{key} hash differs from mission list")
    return listing, manifest
