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
TASK_SEMANTICS_SEED_SCHEME = "task_semantics_only_v1"


def flight_pattern_choice(master_seed, base_index, intent, variant_index, mode="random"):
    """A task-identity substream: never touches scene/shared or candidate RNGs."""
    from .registry import FLIGHT_PATTERNS
    if mode not in ("random", "first"):
        raise ValueError("flight_pattern_mode must be random or first")
    choices = FLIGHT_PATTERNS[intent]
    seed = int(canonical_hash(["flight_pattern_v06", master_seed, base_index, intent, variant_index])[:16], 16)
    return choices[0] if mode == "first" else random.Random(seed).choice(choices)


def apply_flight_pattern(spec, pattern):
    from .registry import component_versions
    spec = copy.deepcopy(spec)
    spec["flight_pattern"] = pattern
    spec["component_versions"] = component_versions(spec["mission"]["intent"], pattern)
    spec["planner"]["name"] = f"{pattern}_v1"
    if spec["mission"]["intent"] == "patrol":
        if pattern == "bidirectional_lanes":
            spec["planner"]["params"]["lane_offset_m"] = 6.0
        else:
            spec["planner"]["params"].pop("lane_offset_m", None)
    return spec


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


def mission_seed(source_seed, intent, template_id, variant_index, *, scheme=SEED_SCHEME):
    if scheme not in (SEED_SCHEME, TASK_SEMANTICS_SEED_SCHEME):
        raise ValueError("unknown task seed scheme")
    return int(canonical_hash([scheme, source_seed, intent, template_id, variant_index])[:16], 16) % 2**63


def sample_patrol_laps(task_seed, choices, region, speed_m_s):
    """Resolve a seed-only K draw to a concrete task K with the 180 s cap."""
    if choices != [2, 3] or type(task_seed) is not int or not 0 <= task_seed < 2**63:
        raise ValueError("patrol lap sampling requires [2, 3] and a valid task seed")
    if not _positive(speed_m_s):
        raise ValueError("patrol lap sampling requires positive speed")
    lap_rng_seed = int(canonical_hash(["patrol_laps_sampling_v1", task_seed])[:16], 16)
    selected_by_seed = random.Random(lap_rng_seed).choice(choices)
    perimeter = 2 * (region["width_m"] + region["height_m"])
    three_lap_nominal_s = 3 * perimeter / speed_m_s
    downgraded = selected_by_seed == 3 and three_lap_nominal_s > 180
    return dict(version="patrol_laps_sampling_v1", sampled_laps=selected_by_seed,
        selected_laps=2 if downgraded else selected_by_seed,
        three_lap_nominal_s=three_lap_nominal_s,
        downgraded_to_two=downgraded,
        reason="three_laps_nominal_over_180s" if downgraded else "seed_sample_retained")


def semantic_template_id(template):
    """Identify only normalized mission/planner semantics, independent of execution."""
    from .mission_v3 import normalize_v3

    normalized = normalize_v3(template)
    return "semantic_" + canonical_hash({key: normalized[key] for key in ("mission", "planner")})[:20]


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
                     "scene_sampler", "shared_mission_params", "missions", "require_all_missions_feasible",
                     "seed_scheme", "flight_pattern_mode"),
            "generation profile v2")
    if "flight_pattern_mode" in profile and profile["flight_pattern_mode"] not in ("random", "first"):
        raise ValueError("flight_pattern_mode must be random or first")
    if "seed_scheme" in profile and profile["seed_scheme"] != TASK_SEMANTICS_SEED_SCHEME:
        raise ValueError(f"seed_scheme must be {TASK_SEMANTICS_SEED_SCHEME} when supplied")
    for key, default, low, high in (("schema_version", 2, 2, 2), ("master_seed", 42, 0, 2**63-1),
                                  ("base_scene_count", 10, 1, 1000), ("max_candidates_per_base", 3, 1, 20)):
        value = profile.setdefault(key, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} must be integer in [{low}, {high}]")
    if profile.setdefault("require_all_missions_feasible", True) is not True:
        raise ValueError("profile v2 requires require_all_missions_feasible=true")
    sampler_config = profile.get("scene_sampler")
    _object(sampler_config, ("name", "params"), "scene_sampler")
    sampler = get_sampler(sampler_config.get("name"))
    if profile["max_candidates_per_base"] > 10 and sampler.name != "random_spawn_v2":
        raise ValueError("max_candidates_per_base above 10 requires random_spawn_v2")
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
        _object(mission, ("intent", "template", "template_spec", "template_id", "variant_speed_factors",
                          "sample_laps", "sample_exit_margin_m"), "mission")
        intent = mission.get("intent")
        get_intent(intent)
        if "sample_laps" in mission and (intent != "patrol" or mission["sample_laps"] != [2, 3]):
            raise ValueError("sample_laps is supported only for patrol with [2, 3]")
        if "sample_exit_margin_m" in mission:
            bounds = mission["sample_exit_margin_m"]
            if (intent != "rapid_passage" or not isinstance(bounds, list) or len(bounds) != 2
                    or not all(_positive(v) for v in bounds) or not 4 <= bounds[0] <= bounds[1] <= 30):
                raise ValueError("rapid passage exit margin requires [low, high] within [4, 30]")
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


def _shared_choice_family_id(sampler, template_scenario, params, seed, base_index,
                             scenario, sampled, actual_family_id):
    """Keep v05c's shared mission draws tied to the matching v05b scene.

    The original shared-choice seed uses a family ID that includes headings.
    With fixed-zero headings, reconstruct the original random-heading scene
    from the *same* seed, then verify that only headings changed. The actual
    fixed-zero family ID remains the published physical-scene identity.
    """
    if sampler.name != "random_spawn_v2" or params.get("heading_policy") != "fixed_zero":
        return actual_family_id
    original_params = {key: value for key, value in params.items() if key != "heading_policy"}
    original_scenario, original_sampled = sampler.sample_scene(
        template_scenario, original_params, random.Random(seed), base_index=base_index)
    original_scenario["scene_id"] = scenario["scene_id"]
    actual_without_heading = copy.deepcopy(scenario)
    original_without_heading = copy.deepcopy(original_scenario)
    for value in (actual_without_heading, original_without_heading):
        for vehicle in value["vehicles"]:
            vehicle.pop("heading_deg")
    if actual_without_heading != original_without_heading:
        raise ValueError("fixed-zero scene differs from original beyond heading")
    actual_sampled = copy.deepcopy(sampled)
    actual_sampled["sampler_params"].pop("heading_policy")
    for value in (actual_sampled, original_sampled):
        for slot in value["spatial_slots"]:
            slot.pop("heading_deg")
    if actual_sampled != original_sampled:
        raise ValueError("fixed-zero sample differs from original beyond heading policy")
    return family_metadata(original_scenario)["family_id"]


def generate_v2(profile, output):
    from .tasks import compile_task

    profile = normalize_profile(profile)
    seed_scheme = profile.get("seed_scheme", SEED_SCHEME)
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
    semantic_ids = ({m["intent"]: semantic_template_id(m["template_spec"]) for m in profile["missions"]}
                    if seed_scheme == TASK_SEMANTICS_SEED_SCHEME else {})
    for base_index in range(profile["base_scene_count"]):
        base_record = dict(base_index=base_index, status="rejected")
        for candidate_index in range(profile["max_candidates_per_base"]):
            seed = scene_seed(profile["master_seed"], base_index, candidate_index)
            candidate_id = f"base_{base_index:04d}_candidate_{candidate_index:02d}"
            try:
                sample_args = (template_scenario, profile["scene_sampler"]["params"], random.Random(seed))
                if sampler.base_index_dependent:
                    scenario, sampled = sampler.sample_scene(*sample_args, base_index=base_index)
                else:
                    scenario, sampled = sampler.sample_scene(*sample_args)
            except ValueError as exc:
                reason = f"{type(exc).__name__}: {exc}"
                candidates.append(dict(candidate_id=candidate_id, base_index=base_index,
                    candidate_index=candidate_index, scene_seed=seed, status="sampling_rejected",
                    sampled_parameters=None, attempts=[], reason=reason))
                rejections.append(dict(candidate_id=candidate_id, intent=None, variant_index=None,
                                       reason=reason))
                continue
            scenario["scene_id"] = f"base_{base_index:04d}"
            family = family_metadata(scenario)
            shared_family_id = _shared_choice_family_id(
                sampler, template_scenario, profile["scene_sampler"]["params"], seed,
                base_index, scenario, sampled, family["family_id"])
            # Geometry-identical candidates (including retries/base indices)
            # are one family. Derive shared choices from that family rather
            # than resampling them when the candidate scene seed changes. For
            # fixed-zero v0.5 headings, use the corresponding original-heading
            # family to preserve v05b speed/return choices exactly.
            shared_rng = random.Random(int(canonical_hash(
                [SEED_SCHEME, profile["master_seed"], shared_family_id, "shared_mission_params"])[:16], 16))
            shared = dict(speed_m_s=shared_rng.choice(profile["shared_mission_params"]["speeds_m_s"]),
                          return_required=shared_rng.choice(profile["shared_mission_params"]["return_required"]))
            record = dict(candidate_id=candidate_id, base_index=base_index, candidate_index=candidate_index,
                          scene_seed=seed, **family, sampled_parameters=sampled,
                          shared_mission_params=shared, attempts=[])
            staged = []
            for mission in profile["missions"]:
                intent = mission["intent"]
                for variant_index, factor in enumerate(mission["variant_speed_factors"]):
                    spec = copy.deepcopy(mission["template_spec"])
                    mission_id = f"{intent}_{base_index:04d}_v{variant_index:02d}"
                    seed_identifier = (semantic_ids[intent] if seed_scheme == TASK_SEMANTICS_SEED_SCHEME
                                       else mission["template_id"])
                    spec.update(task_id=mission_id, family_id=family["family_id"], family_scheme=FAMILY_SCHEME,
                                seed=mission_seed(seed, intent, seed_identifier, variant_index, scheme=seed_scheme),
                                scenario=copy.deepcopy(scenario))
                    spec["mission"].update(target_region_id=scenario["regions"][0]["id"],
                                            return_required=shared["return_required"])
                    spec["planner"]["params"].update(sampled.get("planner_hints", {}).get(intent, {}))
                    spec["execution"]["speed_m_s"] = shared["speed_m_s"] * factor
                    selected_pattern = None
                    if "flight_pattern_mode" in profile:
                        from .registry import FLIGHT_PATTERNS
                        selected_pattern = flight_pattern_choice(profile["master_seed"], base_index, intent,
                            variant_index, profile["flight_pattern_mode"])
                        # Select the common family solely using each intent's
                        # first pattern. Sampled-pattern failure never changes
                        # family/shared draws or silently substitutes a pattern.
                        spec = apply_flight_pattern(spec, FLIGHT_PATTERNS[intent][0])
                    if intent == "rapid_passage":
                        spec["planner"]["params"]["entry_side"] = sampled["entry_side"]
                        if "sample_exit_margin_m" in mission:
                            margin_seed = int(canonical_hash(["rapid_exit_margin_v1", spec["seed"]])[:16], 16)
                            spec["planner"]["params"]["exit_margin_m"] = random.Random(margin_seed).uniform(*mission["sample_exit_margin_m"])
                    lap_sampling = None
                    if "sample_laps" in mission:
                        region = next(region for region in spec["scenario"]["regions"]
                                      if region["id"] == spec["mission"]["target_region_id"])
                        lap_sampling = sample_patrol_laps(spec["seed"], mission["sample_laps"],
                                                         region, spec["execution"]["speed_m_s"])
                        spec["mission"]["intent_params"]["laps"] = lap_sampling["selected_laps"]
                    candidate_file = f"candidates/{candidate_id}_{intent}_v{variant_index:02d}.json"
                    save_json(output / candidate_file, spec)
                    attempt = dict(intent=intent, variant_id=f"v{variant_index:02d}", variant_index=variant_index,
                                   template_id=mission["template_id"], task_seed=spec["seed"], task=candidate_file,
                                   task_sha256=file_hash(output / candidate_file), control_mode=spec["execution"]["control_mode"])
                    if seed_scheme == TASK_SEMANTICS_SEED_SCHEME:
                        attempt.update(task_seed_scheme=seed_scheme, semantic_template_id=seed_identifier)
                    if lap_sampling is not None:
                        attempt["lap_sampling"] = lap_sampling
                    if selected_pattern is not None:
                        attempt["selected_flight_pattern"] = selected_pattern
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
                selected_error = None
                if "selected_flight_pattern" in attempt:
                    spec = apply_flight_pattern(spec, attempt["selected_flight_pattern"])
                    try:
                        scene = compile_task(spec)
                    except (ValueError, TypeError, KeyError, NotImplementedError) as exc:
                        from .mission_v3 import normalize_v3
                        selected_error = f"{type(exc).__name__}: {exc}"
                        scene = dict(task_spec=normalize_v3(spec))
                task_file, scene_file = f"missions/{mission_id}.json", f"scenes/{mission_id}.json"
                save_json(output / task_file, scene["task_spec"])
                if selected_error is None:
                    save_json(output / scene_file, scene)
                entry = dict(mission_id=mission_id, base_scene_id=family["scene_content_sha256"][:20],
                    base_index=base_index, candidate_id=candidate_id, **family,
                    base_scene_sha256=family["scene_content_sha256"], variant_id=attempt["variant_id"],
                    variant_index=attempt["variant_index"], intent=attempt["intent"],
                    template_id=attempt["template_id"], planner_template_id=spec["planner"]["name"],
                    scene_seed=seed, task_seed=spec["seed"], control_mode=spec["execution"]["control_mode"],
                    shared_mission_params=shared, variant_speed_factor=mission_factor(profile, attempt),
                    sampled_parameters=sampled, status="planned" if selected_error is None else "planning_rejected",
                    task=task_file, scene=scene_file if selected_error is None else None,
                    task_sha256=file_hash(output / task_file), scene_sha256=file_hash(output / scene_file) if selected_error is None else None,
                    normalized_task_sha256=canonical_hash(scene["task_spec"]))
                if "selected_flight_pattern" in attempt:
                    entry.update(flight_pattern=spec["flight_pattern"], component_versions=spec["component_versions"])
                    if selected_error is not None:
                        entry["reason"] = selected_error
                if seed_scheme == TASK_SEMANTICS_SEED_SCHEME:
                    entry.update(task_seed_scheme=seed_scheme,
                                 semantic_template_id=attempt["semantic_template_id"])
                if "lap_sampling" in attempt:
                    entry["lap_sampling"] = attempt["lap_sampling"]
                entries.append(entry)
            break
        bases.append(base_record)
    listing = dict(schema_version=2, generator_version=GENERATOR_VERSION, family_scheme=FAMILY_SCHEME,
                   seed_scheme=seed_scheme, generation_profile_sha256=file_hash(output / "generation_profile.json"),
                   missions=entries)
    save_json(output / "mission_list.json", listing)
    manifest = dict(schema_version=2, generator_version=GENERATOR_VERSION, family_scheme=FAMILY_SCHEME,
        seed_scheme=seed_scheme, profile_sha256=canonical_hash(profile),
        scene_sampler=dict(name=sampler.name, intent_agnostic=sampler.intent_agnostic),
        bases=bases, candidates=candidates, rejections=rejections,
        counts=dict(base_scenes=len(bases), accepted_bases=sum(b["status"] == "accepted" for b in bases),
            candidates=len(candidates), accepted_candidates=sum(c["status"] == "accepted" for c in candidates),
            rejected_candidates=sum(c["status"] != "accepted" for c in candidates),
            planned_missions=sum(e["status"] == "planned" for e in entries), rejected_variants=len(rejections)),
        artifact_sha256={p.relative_to(output).as_posix(): file_hash(p) for p in sorted(output.rglob("*.json"))},
        limitation="planning only; no SITL execution; continuous-route execution deferred to WP-E")
    save_json(output / "generation_manifest.json", manifest)
    return dict(output=str(output), mission_list=str(output / "mission_list.json"), **manifest)


def mission_factor(profile, attempt):
    return next(m["variant_speed_factors"][attempt["variant_index"]]
                for m in profile["missions"] if m["intent"] == attempt["intent"])
