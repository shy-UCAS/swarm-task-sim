"""Physical-scene families and atomic, deterministic multi-intent planning.

No SITL execution. Profiles freeze template content and produce a candidate
audit even when one intent makes the whole candidate family infeasible.
"""

import copy
import json
import math
import random
import re
from pathlib import Path

from .families import FAMILY_SCHEME, family_metadata
from .generation import PROJECT, canonical_hash, file_hash, save_json
from .scene_samplers import get_sampler


GENERATOR_VERSION = "scene_mission_generator_v2"
SEED_SCHEME = "hierarchical_scene_mission_v1"


def _object(value, allowed, name):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(f"unknown or invalid {name} fields")


def _positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _choices(values, name, check):
    if not isinstance(values, list) or not 1 <= len(values) <= 20 or not all(check(v) for v in values):
        raise ValueError(f"invalid nonempty choices: {name}")
    if len({canonical_hash(v) for v in values}) != len(values):
        raise ValueError(f"duplicate choices: {name}")


def scene_seed(master_seed, base_index, candidate_index):
    return int(canonical_hash([SEED_SCHEME, master_seed, base_index, candidate_index])[:16], 16) % 2**63


def mission_seed(source_seed, intent, template_id, variant_index):
    return int(canonical_hash([SEED_SCHEME, source_seed, intent, template_id, variant_index])[:16], 16) % 2**63


def normalize_profile(source):
    from .registry import get_intent

    base = PROJECT
    if isinstance(source, (str, Path)):
        path = Path(source).resolve()
        base = path.parent
        profile = json.loads(path.read_text(encoding="utf-8-sig"))
    else:
        profile = copy.deepcopy(source)
    _object(profile, ("schema_version", "master_seed", "base_scene_count", "max_candidates_per_base",
                     "scene_sampler", "shared_mission_params", "missions", "require_all_missions_feasible"),
            "generation profile v2")
    for key, default, low, high in (("schema_version", 2, 2, 2), ("master_seed", 42, 0, 2**63-1),
                                  ("base_scene_count", 10, 1, 1000), ("max_candidates_per_base", 3, 1, 10)):
        value = profile.setdefault(key, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} must be integer in [{low}, {high}]")
    if profile.setdefault("require_all_missions_feasible", True) is not True:
        raise ValueError("profile v2 requires require_all_missions_feasible=true")
    sampler_config = profile.get("scene_sampler")
    _object(sampler_config, ("name", "params"), "scene_sampler")
    sampler = get_sampler(sampler_config.get("name"))
    sampler_config["params"] = sampler.normalize_params(sampler_config.get("params", {}))
    shared = profile.setdefault("shared_mission_params", {})
    _object(shared, ("speeds_m_s", "return_required"), "shared_mission_params")
    shared.setdefault("speeds_m_s", [2.0, 2.5, 3.0])
    shared.setdefault("return_required", [True, False])
    _choices(shared["speeds_m_s"], "shared speeds_m_s", _positive)
    _choices(shared["return_required"], "shared return_required", lambda v: type(v) is bool)
    shared["speeds_m_s"] = [float(v) for v in shared["speeds_m_s"]]
    missions = profile.get("missions")
    if not isinstance(missions, list) or not 1 <= len(missions) <= 20:
        raise ValueError("missions must be a nonempty list of at most 20 intents")
    names = set()
    for mission in missions:
        _object(mission, ("intent", "template", "template_spec", "template_id", "variant_speed_factors"), "mission")
        intent = mission.get("intent")
        get_intent(intent)
        if intent in names:
            raise ValueError("profile v2 configures each intent exactly once")
        names.add(intent)
        if "template" in mission and "template_spec" in mission:
            raise ValueError("provide template or template_spec, not both")
        if "template_spec" not in mission:
            if not isinstance(mission.get("template"), str):
                raise ValueError("mission requires a v3 template or template_spec")
            path = Path(mission.pop("template"))
            if not path.is_absolute():
                path = base / path
            mission["template_spec"] = json.loads(path.read_text(encoding="utf-8-sig"))
        template = mission["template_spec"]
        if not isinstance(template, dict) or type(template.get("schema_version")) is not int or template["schema_version"] != 3:
            raise ValueError("generation profile v2 requires TaskSpec v3 templates")
        if template.get("mission", {}).get("intent") != intent:
            raise ValueError("profile intent does not match template intent")
        mission.setdefault("template_id", "template_" + canonical_hash(template)[:20])
        if not isinstance(mission["template_id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", mission["template_id"]):
            raise ValueError("template_id must be a safe identifier")
        factors = mission.setdefault("variant_speed_factors", [1.0])
        _choices(factors, "variant_speed_factors", _positive)
        mission["variant_speed_factors"] = [float(v) for v in factors]
    if len(names) > 1 and not sampler.intent_agnostic:
        raise ValueError("non-intent-agnostic sampler cannot generate a multi-intent profile")
    if len({canonical_hash(m["variant_speed_factors"]) for m in missions}) != 1:
        raise ValueError("all intents must share variant_speed_factors to avoid intent-specific speed shortcuts")
    # A sampler replaces geometry, but inherits the common physical frame and
    # platform. Reject ambiguous per-intent world/platform choices up front.
    frames = [{key: m["template_spec"]["scenario"][key] for key in ("origin", "world", "platform")} for m in missions]
    if len({canonical_hash(frame) for frame in frames}) != 1:
        raise ValueError("mission templates must share origin, world and platform")
    profile["missions"] = sorted(missions, key=lambda m: m["intent"])
    return profile


def generate_v2(profile, output):
    from .tasks import compile_task

    profile = normalize_profile(profile)
    sampler = get_sampler(profile["scene_sampler"]["name"])
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("generation output already exists; select a new directory")
    output.mkdir(parents=True)
    for name in ("missions", "scenes", "candidates"):
        (output / name).mkdir()
    save_json(output / "generation_profile.json", profile)
    entries, candidates, bases, rejections = [], [], [], []
    template_scenario = profile["missions"][0]["template_spec"]["scenario"]
    for base_index in range(profile["base_scene_count"]):
        base_record = dict(base_index=base_index, status="rejected")
        for candidate_index in range(profile["max_candidates_per_base"]):
            seed = scene_seed(profile["master_seed"], base_index, candidate_index)
            scenario, sampled = sampler.sample_scene(template_scenario, profile["scene_sampler"]["params"], random.Random(seed))
            scenario["scene_id"] = f"base_{base_index:04d}"
            family = family_metadata(scenario)
            # Geometry-identical candidates (including retries/base indices)
            # are one family. Derive shared choices from that family rather
            # than resampling them when the candidate scene seed changes.
            shared_rng = random.Random(int(canonical_hash(
                [SEED_SCHEME, profile["master_seed"], family["family_id"], "shared_mission_params"])[:16], 16))
            shared = dict(speed_m_s=shared_rng.choice(profile["shared_mission_params"]["speeds_m_s"]),
                          return_required=shared_rng.choice(profile["shared_mission_params"]["return_required"]))
            candidate_id = f"base_{base_index:04d}_candidate_{candidate_index:02d}"
            record = dict(candidate_id=candidate_id, base_index=base_index, candidate_index=candidate_index,
                          scene_seed=seed, **family, sampled_parameters=sampled,
                          shared_mission_params=shared, attempts=[])
            staged = []
            for mission in profile["missions"]:
                intent = mission["intent"]
                for variant_index, factor in enumerate(mission["variant_speed_factors"]):
                    spec = copy.deepcopy(mission["template_spec"])
                    mission_id = f"{intent}_{base_index:04d}_v{variant_index:02d}"
                    spec.update(task_id=mission_id, family_id=family["family_id"], family_scheme=FAMILY_SCHEME,
                                seed=mission_seed(seed, intent, mission["template_id"], variant_index),
                                scenario=copy.deepcopy(scenario))
                    spec["mission"].update(target_region_id=scenario["regions"][0]["id"],
                                            return_required=shared["return_required"])
                    spec["planner"]["params"].update(sampled.get("planner_hints", {}).get(intent, {}))
                    spec["execution"]["speed_m_s"] = shared["speed_m_s"] * factor
                    candidate_file = f"candidates/{candidate_id}_{intent}_v{variant_index:02d}.json"
                    save_json(output / candidate_file, spec)
                    attempt = dict(intent=intent, variant_id=f"v{variant_index:02d}", variant_index=variant_index,
                                   template_id=mission["template_id"], task_seed=spec["seed"], task=candidate_file,
                                   task_sha256=file_hash(output / candidate_file), control_mode=spec["execution"]["control_mode"])
                    try:
                        scene = compile_task(spec)
                        if scene["task_spec"]["family_id"] != family["family_id"]:
                            raise ValueError("compiled task family disagrees with sampled physical scene")
                        attempt["status"] = "planned"
                        staged.append((mission_id, spec, scene, attempt))
                    except (ValueError, TypeError, KeyError, NotImplementedError) as exc:
                        attempt.update(status="planning_rejected", reason=f"{type(exc).__name__}: {exc}")
                        rejections.append(dict(candidate_id=candidate_id, **family, intent=intent,
                                               variant_index=variant_index, reason=attempt["reason"]))
                    record["attempts"].append(attempt)
            record["status"] = "accepted" if all(a["status"] == "planned" for a in record["attempts"]) else "planning_rejected"
            candidates.append(record)
            if record["status"] != "accepted":
                # Nothing is published as runnable until every intent/variant
                # succeeds. Successful siblings remain visible in the audit.
                continue
            base_record.update(status="accepted", selected_candidate=candidate_id, **family)
            for mission_id, spec, scene, attempt in staged:
                task_file, scene_file = f"missions/{mission_id}.json", f"scenes/{mission_id}.json"
                save_json(output / task_file, scene["task_spec"])
                save_json(output / scene_file, scene)
                entries.append(dict(mission_id=mission_id, base_scene_id=family["scene_content_sha256"][:20],
                    base_index=base_index, candidate_id=candidate_id, **family,
                    base_scene_sha256=family["scene_content_sha256"], variant_id=attempt["variant_id"],
                    variant_index=attempt["variant_index"], intent=attempt["intent"],
                    template_id=attempt["template_id"], planner_template_id=spec["planner"]["name"],
                    scene_seed=seed, task_seed=spec["seed"], control_mode=spec["execution"]["control_mode"],
                    shared_mission_params=shared, variant_speed_factor=mission_factor(profile, attempt),
                    sampled_parameters=sampled, status="planned", task=task_file, scene=scene_file,
                    task_sha256=file_hash(output / task_file), scene_sha256=file_hash(output / scene_file),
                    normalized_task_sha256=canonical_hash(scene["task_spec"])))
            break
        bases.append(base_record)
    listing = dict(schema_version=2, generator_version=GENERATOR_VERSION, family_scheme=FAMILY_SCHEME,
                   seed_scheme=SEED_SCHEME, generation_profile_sha256=file_hash(output / "generation_profile.json"),
                   missions=entries)
    save_json(output / "mission_list.json", listing)
    manifest = dict(schema_version=2, generator_version=GENERATOR_VERSION, family_scheme=FAMILY_SCHEME,
        seed_scheme=SEED_SCHEME, profile_sha256=canonical_hash(profile),
        scene_sampler=dict(name=sampler.name, intent_agnostic=sampler.intent_agnostic),
        bases=bases, candidates=candidates, rejections=rejections,
        counts=dict(base_scenes=len(bases), accepted_bases=sum(b["status"] == "accepted" for b in bases),
            candidates=len(candidates), accepted_candidates=sum(c["status"] == "accepted" for c in candidates),
            rejected_candidates=sum(c["status"] != "accepted" for c in candidates),
            planned_missions=len(entries), rejected_variants=len(rejections)),
        artifact_sha256={p.relative_to(output).as_posix(): file_hash(p) for p in sorted(output.rglob("*.json"))},
        limitation="planning only; no SITL execution; continuous-route execution deferred to WP-E")
    save_json(output / "generation_manifest.json", manifest)
    return dict(output=str(output), mission_list=str(output / "mission_list.json"), **manifest)


def mission_factor(profile, attempt):
    return next(m["variant_speed_factors"][attempt["variant_index"]]
                for m in profile["missions"] if m["intent"] == attempt["intent"])
