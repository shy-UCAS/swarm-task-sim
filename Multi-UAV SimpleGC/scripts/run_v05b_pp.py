"""Bounded v0.5 r1.1 pilot: prepare, one SITL attempt per next, then finalize.

Prepare is offline and writes only a new PP directory. Only the explicit next
action starts SITL. Neither action edits the v05/v05b DR or shared templates.
"""

import argparse
import copy
import json
import math
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.review_v05b_dr import review as review_dr
from scripts.run_mission_list import _save_atomic, _verify_result, run_mission_list
from scripts.run_v05b_validation import preflight_retry_reason
from scripts.verify_v05_protected import verify_baseline
from swarm_sim.dataset import build_dataset
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.episode_loader import load_episode, load_public_scene
from swarm_sim.families import family_metadata
from swarm_sim.generation import canonical_hash, checked_path, file_hash, save_json, verify_generation
from swarm_sim.generation_v2 import (TASK_SEMANTICS_SEED_SCHEME, mission_seed,
                                     normalize_profile, scene_seed, semantic_template_id)
from swarm_sim.language_v0 import describe_dataset
from swarm_sim.quality import policy_hash, resolve_policy
from swarm_sim.run_provenance import PARAMETER_COMPARISON_VERSION, verify_preflight_files
from swarm_sim.scene_samplers import get_sampler

VERSION = "v05b_pilot_controller_v1"
ROOT_OUTPUT = ROOT / "verification/v05b_pp_20261002"
DR_PROFILE = ROOT / "generation_profiles/dual_intent_v05b.json"
DR_GENERATED = ROOT / "tmp_v05/dr_v05b/generated_130"
DR_REVIEW = ROOT / "tmp_v05/dr_v05b/review.json"
HD_DECISION = ROOT / "verification/v05b_validation_20261002/hd_decision.json"
HOLD1_PROFILE = ROOT / "generation_profiles/dual_intent_v05b_hd1.json"
HOLD1_GENERATED = ROOT / "tmp_v05/pp_v05b/generated_hd1"
QUALITY_POLICY = ROOT / "quality_policies/default_v022.json"
BINARY = ROOT / "ArducopterSITL/arducopter.exe"
PARAMETERS = ROOT / "ArducopterSITL/copter.parm"
INTENT_ORDER = ("reconnaissance", "patrol")
LOGICAL_RUNS = 20
MAX_ATTEMPTS = 22
MAX_EXTRA_RETRIES = 2
TIMING_UNKNOWN_LIMIT = .10


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def utc():
    return datetime.now(timezone.utc).isoformat()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def all_true(value):
    if type(value) is bool:
        return value
    return isinstance(value, dict) and bool(value) and all(all_true(item) for item in value.values())


def assert_hashes(hashes):
    changed = [path for path, digest in hashes.items()
               if not Path(path).is_file() or file_hash(path) != digest]
    if changed:
        raise ValueError("frozen PP input/evidence changed: " + str(changed))


def assert_protected():
    result = verify_baseline()
    if result["unchanged"] is not True:
        raise ValueError("protected v0.4 evidence changed: " +
                         str(result["missing"] + result["changed"]))
    return result["protected_file_count"]


def assert_post_run_integrity(control):
    """Recheck every frozen pilot input after SITL has returned."""
    assert_hashes(control["frozen_sha256"])
    assert_protected()


def _formal_profile(hold):
    return (DR_PROFILE, DR_GENERATED) if hold == 0 else (HOLD1_PROFILE, HOLD1_GENERATED)


def _hd_check(hd_path):
    hd_path = Path(hd_path).resolve()
    hd = read(hd_path)
    hold = hd.get("terminal_hold_s")
    if (hd.get("pass") is not True or hd.get("validation_completed") is not True
            or type(hold) not in (int, float) or hold not in (0, 1)):
        raise ValueError("HD decision is incomplete or unaccepted")
    evidence = hd.get("evidence_sha256")
    if (not isinstance(evidence, dict) or
            not all(isinstance(evidence.get(case), str) and len(evidence[case]) == 64
                    for case in ("VP1", "VP4"))):
        raise ValueError("HD decision must contain VP1 and VP4 evidence fingerprints")
    validation_control_path = hd_path.parent / "control.json"
    validation = read(validation_control_path)
    if (hd.get("controller_sha256") != file_hash(validation_control_path)
            or validation.get("completed") is not True
            or validation.get("stopped_reason")
            or validation.get("active_attempt") is not None
            or any(validation.get("aggregate_av1", {}).get(intent, {}).get("pass") is not True
                   for intent in INTENT_ORDER)
            or validation.get("profile_canonical_sha256") != hd.get("profile_canonical_sha256")
            or validation.get("source_review_sha256") != hd.get("source_review_sha256")
            or file_hash(DR_PROFILE) != validation.get("profile_file_sha256")
            or canonical_hash(normalize_profile(DR_PROFILE)) != hd.get("profile_canonical_sha256")
            or file_hash(DR_REVIEW) != hd.get("source_review_sha256")):
        raise ValueError("HD decision is not bound to completed validation/profile/review evidence")
    conditions = hd.get("conditions")
    if (not isinstance(conditions, dict) or set(conditions) != {
            "onboard_terminal_prm1_is_one", "vp4_stopped_fraction_and_improvement",
            "vp4_elapsed_within_ten_percent", "vp4_all_av_pass"}
            or any(type(value) is not bool for value in conditions.values())
            or (hold == 1) is not all(conditions.values())):
        raise ValueError("HD hold decision disagrees with the four registered conditions")
    paths = hd.get("evidence_paths")
    if not isinstance(paths, dict) or set(paths) != {"VP1", "VP4"}:
        raise ValueError("HD decision lacks VP1/VP4 analysis evidence paths")
    for case in ("VP1", "VP4"):
        matches = [row for row in validation.get("records", [])
                   if row.get("case_id") == case and row.get("individual_pass") is True
                   and row.get("retryable_pre_takeoff") is not True]
        if len(matches) != 1 or not matches[0].get("run_directory"):
            raise ValueError("HD VP1/VP4 run is not uniquely accepted in validation control")
        directory = Path(matches[0]["run_directory"]).resolve()
        latest = read(directory / "analysis_latest.json")
        manifest_path = checked_path(directory, latest["directory"]) / "manifest.json"
        if (Path(paths[case]).resolve() != manifest_path.resolve()
                or Path(hd.get(case.lower(), {}).get("run_directory", "")).resolve() != directory
                or evidence[case] != latest.get("manifest_sha256")
                or evidence[case] != file_hash(manifest_path)
                or matches[0].get("evidence_sha256", {}).get(str(manifest_path.resolve())) != evidence[case]):
            raise ValueError("HD VP1/VP4 analysis manifest fingerprint or path differs")
    return hd, int(hold)


def _profiles_equal_except_hold(source, formal, hold):
    if source.get("seed_scheme") != TASK_SEMANTICS_SEED_SCHEME:
        raise ValueError("PP requires task_semantics_only_v1 seed scheme")
    source_copy = copy.deepcopy(source)
    formal_copy = copy.deepcopy(formal)
    for item in source_copy["missions"]:
        if item["template_spec"]["execution"]["terminal_hold_s"] != 0:
            raise ValueError("original v05b template terminal_hold_s is not zero")
    for item in formal_copy["missions"]:
        if item["template_spec"]["execution"]["terminal_hold_s"] != hold:
            raise ValueError("finalized template terminal_hold_s disagrees with HD")
        item["template_spec"]["execution"]["terminal_hold_s"] = 0.0
    if canonical_hash(source_copy) != canonical_hash(formal_copy):
        raise ValueError("formal profile differs from DR profile beyond terminal_hold_s")
    for original, final in zip(source["missions"], formal["missions"]):
        if (original["intent"] != final["intent"] or
                semantic_template_id(original["template_spec"]) !=
                semantic_template_id(final["template_spec"])):
            raise ValueError("HD changed mission semantic seed identity")


def _candidate_invariance(source, formal, source_manifest, formal_manifest):
    """Recompute each formal draw from the original sampler and scene seed."""
    sampler = get_sampler(source["scene_sampler"]["name"])
    template_scenario = source["missions"][0]["template_spec"]["scenario"]
    source_candidates = {c["candidate_id"]: c for c in source_manifest["candidates"]}
    source_templates = {item["intent"]: item for item in source["missions"]}
    matched, different_selections = 0, []
    for candidate in formal_manifest["candidates"]:
        base, draw = candidate["base_index"], candidate["candidate_index"]
        seed = scene_seed(source["master_seed"], base, draw)
        if candidate["scene_seed"] != seed:
            raise ValueError("HD changed physical scene seed")
        try:
            scenario, sampled = sampler.sample_scene(
                template_scenario, source["scene_sampler"]["params"],
                random.Random(seed), base_index=base)
        except ValueError:
            if candidate["status"] != "sampling_rejected":
                raise ValueError("HD changed physical sampler acceptance")
            continue
        scenario["scene_id"] = f"base_{base:04d}"
        family = family_metadata(scenario)
        if (canonical_hash(sampled) != canonical_hash(candidate["sampled_parameters"])
                or candidate["scene_content_sha256"] != family["scene_content_sha256"]
                or candidate["family_id"] != family["family_id"]):
            raise ValueError("HD changed a candidate physical scene")
        for attempt in candidate["attempts"]:
            template = source_templates[attempt["intent"]]
            identifier = semantic_template_id(template["template_spec"])
            expected_seed = mission_seed(seed, attempt["intent"], identifier,
                                         attempt["variant_index"], scheme=TASK_SEMANTICS_SEED_SCHEME)
            if (attempt["task_seed"] != expected_seed or
                    attempt.get("semantic_template_id") != identifier):
                raise ValueError("HD changed task semantic seed")
        original = source_candidates.get(candidate["candidate_id"])
        if original:
            matched += 1
            if (original.get("scene_seed") != seed or
                    canonical_hash(original.get("sampled_parameters")) != canonical_hash(sampled)):
                raise ValueError("overlapping DR candidate changed physical sample")
            for attempt in candidate["attempts"]:
                old = next((item for item in original.get("attempts", [])
                            if (item["intent"], item["variant_index"]) ==
                            (attempt["intent"], attempt["variant_index"])), None)
                if old is None or old["task_seed"] != attempt["task_seed"]:
                    raise ValueError("overlapping DR candidate changed semantic seed")
    for original, final in zip(source_manifest["bases"], formal_manifest["bases"]):
        if original["base_index"] != final["base_index"]:
            raise ValueError("formal base order differs from original DR")
        if original.get("selected_candidate") != final.get("selected_candidate"):
            different_selections.append(dict(base_index=original["base_index"],
                original_candidate=original.get("selected_candidate"),
                finalized_candidate=final.get("selected_candidate")))
    return dict(formal_candidate_draws_checked=len(formal_manifest["candidates"]),
                overlapping_original_draws_checked=matched,
                changed_selected_candidates=different_selections)


def _dr_inputs(source_profile_path, source_generated, source_review_path,
               formal_profile_path, formal_generated, hold):
    source_profile = normalize_profile(source_profile_path)
    formal_profile = normalize_profile(formal_profile_path)
    _profiles_equal_except_hold(source_profile, formal_profile, hold)
    source_list, source_manifest = verify_generation(source_generated / "mission_list.json")
    formal_list, formal_manifest = verify_generation(formal_generated / "mission_list.json")
    source_review = read(source_review_path)
    if not all_true(source_review.get("gate")):
        raise ValueError("original v05b DR gate is not fully passing")
    expected = dict(generation_manifest_file_sha256=file_hash(source_generated / "generation_manifest.json"),
                    profile_file_sha256=file_hash(source_profile_path),
                    profile_canonical_sha256=canonical_hash(source_profile))
    if any(source_review.get(key) != value for key, value in expected.items()):
        raise ValueError("original v05b DR review is not hash-bound to its source")
    if hold == 0:
        if formal_generated != source_generated or formal_profile_path != source_profile_path:
            raise ValueError("HD hold=0 must use the original v05b DR profile and generation")
        formal_review = source_review
        invariance = dict(formal_candidate_draws_checked=len(formal_manifest["candidates"]),
                          overlapping_original_draws_checked=len(formal_manifest["candidates"]),
                          changed_selected_candidates=[])
    else:
        invariance = _candidate_invariance(
            source_profile, formal_profile, source_manifest, formal_manifest)
        formal_review = review_dr(formal_profile_path, formal_generated)
        if not all_true(formal_review.get("gate")):
            raise ValueError("HD hold=1 finalized generation fails v05b DR gates: " +
                             str([key for key, value in formal_review["gate"].items() if value is False]))
    bases = formal_manifest["bases"]
    if (len(bases) != 130 or
            any(base["base_index"] != index or base["status"] != "accepted"
                for index, base in enumerate(bases))):
        raise ValueError("finalized generation did not accept all 130 ordered bases")
    entries_by_base = {}
    for entry in formal_list["missions"]:
        entries_by_base.setdefault(entry["base_index"], {})[entry["intent"]] = entry
    if any(set(entries_by_base.get(index, {})) != set(INTENT_ORDER)
           for index in range(10)):
        raise ValueError("first ten finalized bases lack a two-intent pair")
    return formal_list, formal_manifest, formal_review, invariance, entries_by_base


def prepare(root=ROOT_OUTPUT, hd_path=HD_DECISION,
            binary=BINARY, parameters=PARAMETERS, quality_policy=QUALITY_POLICY):
    root, hd_path = Path(root).resolve(), Path(hd_path).resolve()
    binary, parameters, quality_policy = (Path(item).resolve()
                                           for item in (binary, parameters, quality_policy))
    if root.exists():
        raise ValueError("PP output directory already exists; never overwrite a prior pilot")
    hd, hold = _hd_check(hd_path)
    formal_profile_path, formal_generated = _formal_profile(hold)
    source_profile_path, source_generated, source_review_path = (
        DR_PROFILE.resolve(), DR_GENERATED.resolve(), DR_REVIEW.resolve())
    formal_profile_path, formal_generated = formal_profile_path.resolve(), formal_generated.resolve()
    listing, manifest, formal_review, invariance, entries_by_base = _dr_inputs(
        source_profile_path, source_generated, source_review_path,
        formal_profile_path, formal_generated, hold)
    protected_count = assert_protected()
    provenance = verify_preflight_files(binary, parameters)
    policy = resolve_policy(read(quality_policy))
    root.mkdir(parents=True, exist_ok=False)
    bundle = root / "bundle"
    (bundle / "missions").mkdir(parents=True)
    (bundle / "scenes").mkdir()
    (bundle / "generation_profile.json").write_bytes(
        (formal_generated / "generation_profile.json").read_bytes())
    save_json(root / "formal_dr_review.json", formal_review)
    plan = []
    for base in range(10):
        for intent in INTENT_ORDER:
            entry = copy.deepcopy(entries_by_base[base][intent])
            if entry["candidate_id"] != manifest["bases"][base]["selected_candidate"]:
                raise ValueError("PP entry differs from finalized selected candidate")
            entry["pilot_index"] = len(plan)
            entry["task"] = f"missions/{entry['mission_id']}.json"
            entry["scene"] = f"scenes/{entry['mission_id']}.json"
            source_entry = entries_by_base[base][intent]
            (bundle / entry["task"]).write_bytes(
                checked_path(formal_generated, source_entry["task"]).read_bytes())
            (bundle / entry["scene"]).write_bytes(
                checked_path(formal_generated, source_entry["scene"]).read_bytes())
            entry["task_sha256"] = file_hash(bundle / entry["task"])
            entry["scene_sha256"] = file_hash(bundle / entry["scene"])
            plan.append(entry)
    selection = dict(version=VERSION, hold_s=hold, prepared_utc=utc(),
        source_profile_file_sha256=file_hash(source_profile_path),
        source_manifest_sha256=file_hash(source_generated / "generation_manifest.json"),
        source_review_sha256=file_hash(source_review_path),
        hd_decision_sha256=file_hash(hd_path),
        formal_profile_file_sha256=file_hash(formal_profile_path),
        formal_profile_canonical_sha256=canonical_hash(normalize_profile(formal_profile_path)),
        formal_manifest_sha256=file_hash(formal_generated / "generation_manifest.json"),
        formal_review_sha256=file_hash(root / "formal_dr_review.json"),
        candidate_invariance=invariance,
        accepted_first_ten=[dict(base_index=base, candidate_id=manifest["bases"][base]["selected_candidate"],
                                 family_id=manifest["bases"][base]["family_id"])
                            for base in range(10)],
        order=[dict(pilot_index=entry["pilot_index"], base_index=entry["base_index"],
                    intent=entry["intent"], mission_id=entry["mission_id"])
               for entry in plan])
    save_json(bundle / "selection.json", selection)
    subset = copy.deepcopy(listing)
    subset["missions"] = plan
    save_json(bundle / "mission_list.json", subset)
    subset_candidates = [c for c in manifest["candidates"] if c["base_index"] < 10]
    subset_manifest = dict(schema_version=2, generator_version="v05b_pilot_bundle_v1",
        source_generation_manifest_sha256=selection["formal_manifest_sha256"],
        source_dr_review_sha256=selection["formal_review_sha256"],
        hd_decision_sha256=selection["hd_decision_sha256"],
        profile_sha256=selection["formal_profile_canonical_sha256"],
        bases=manifest["bases"][:10], candidates=subset_candidates,
        counts=dict(base_scenes=10, accepted_bases=10, candidates=len(subset_candidates),
                    accepted_candidates=sum(c["status"] == "accepted" for c in subset_candidates),
                    planned_missions=20),
        artifact_sha256={item.relative_to(bundle).as_posix(): file_hash(item)
                         for item in sorted(bundle.rglob("*.json"))})
    save_json(bundle / "generation_manifest.json", subset_manifest)
    verify_generation(bundle / "mission_list.json")
    frozen = list(bundle.rglob("*.json")) + [root / "formal_dr_review.json",
        hd_path, hd_path.parent / "control.json",
        *(Path(path) for path in hd["evidence_paths"].values()),
        source_profile_path, source_generated / "generation_manifest.json",
        source_review_path, formal_profile_path, formal_generated / "generation_manifest.json",
        ROOT / "generation_profiles/dual_intent_v05.json",
        ROOT / "tmp_v05/dr/generated_130/generation_manifest.json",
        ROOT / "docs/v0.5_dr_composition_diagnosis.md",
        quality_policy, binary, parameters, ROOT / "tmp_v05/m0/protected_baseline.json",
        ROOT / "docs/v04_spike_go_confirmation.json",
        ROOT / "scripts/run_mission_list.py", ROOT / "scripts/verify_v05_protected.py",
        ROOT / "scripts/run_v05b_validation.py", Path(__file__),
    ] + list((ROOT / "swarm_sim").glob("*.py"))
    frozen_sha = {str(path.resolve()): file_hash(path) for path in frozen}
    control = dict(version=VERSION, prepared_utc=utc(), bundle=str(bundle),
        formal_profile=str(formal_profile_path), formal_generation=str(formal_generated),
        formal_review_sha256=selection["formal_review_sha256"],
        hd_decision=str(hd_path), hd_decision_sha256=selection["hd_decision_sha256"],
        hold_s=hold, binary=str(binary), parameters=str(parameters),
        firmware=provenance["actual"]["firmware"], parameters_sha256=file_hash(parameters),
        quality_policy=policy, quality_policy_sha256=policy_hash(policy),
        protected_file_count=protected_count, frozen_sha256=frozen_sha,
        planned_missions=[item["mission_id"] for item in plan], records=[],
        active_attempt=None, stopped_reason=None, completed=False, finalized=False,
        max_attempts=MAX_ATTEMPTS, max_extra_retries=MAX_EXTRA_RETRIES,
        timing_unknown_limit=TIMING_UNKNOWN_LIMIT)
    _save_atomic(root / "control.json", control)
    return control


def next_mission(control):
    if (control.get("version") != VERSION or control.get("max_attempts") != MAX_ATTEMPTS
            or control.get("stopped_reason") or control.get("completed")
            or control.get("active_attempt") is not None):
        raise ValueError("PP controller stopped, complete, or has an unresolved attempt")
    records = control["records"]
    if len(records) >= MAX_ATTEMPTS:
        raise ValueError("22-attempt PP budget exhausted")
    if records and records[-1].get("retryable_pre_takeoff") is True:
        last = records[-1]
        retries = len(records) - len({row["logical_index"] for row in records})
        if retries >= MAX_EXTRA_RETRIES or sum(
                row["logical_index"] == last["logical_index"] for row in records) >= 2:
            raise ValueError("pre-takeoff retry budget exhausted")
        return last["logical_index"], 1
    completed = len({row["logical_index"] for row in records})
    if completed >= LOGICAL_RUNS:
        raise ValueError("all 20 PP missions have already been attempted")
    return completed, 0


def _event_rows(directory):
    path = Path(directory) / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()] if path.is_file() else []


def _analysis_artifacts(directory, scene, control):
    directory = Path(directory)
    metadata = read(directory / "metadata.json")
    if not (directory / "analysis_latest.json").is_file():
        return metadata, None
    latest = read(directory / "analysis_latest.json")
    analysis = checked_path(directory, latest["directory"])
    generation = {name: read(directory / (name + ".json")) for name in
                  ("generation_profile", "generation_manifest", "generation_entry")}
    _verify_result(directory, scene, control["quality_policy_sha256"],
                   selected=latest, generation_context=generation)
    return metadata, {name: read(analysis / (name + ".json")) for name in
                      ("quality", "labels", "ac4_timing_v3", "onboard_mission_param_check")}


def assess_run(scene, metadata, artifacts, control):
    """Report hard stops separately from quality and ordinary task failure."""
    hard = []
    agents = {vehicle["id"] for vehicle in scene["vehicles"]}
    provenance = metadata.get("run_provenance", {})
    readback = provenance.get("parameter_evidence", {}).get("per_agent", {})
    binary = metadata.get("binary_firmware", {})
    if (provenance.get("status") != "verified_before_takeoff" or
            provenance.get("parameter_comparison_version") != PARAMETER_COMPARISON_VERSION or
            metadata.get("parameter_comparison_version") != PARAMETER_COMPARISON_VERSION or
            binary.get("sha256") != control["firmware"]["sha256"] or
            binary.get("version_string") != control["firmware"]["version_string"] or
            metadata.get("parameters_sha256") != control["parameters_sha256"] or
            set(readback) != agents or any(
                value.get("complete") is not True or value.get("status") != "complete"
                or value.get("received_count") != value.get("parameter_count")
                or value.get("missing_indices") != [] for value in readback.values())):
        hard.append("parameter/firmware/readback gate failed")
    if artifacts is None:
        return dict(qualified=False, accepted_for_pp=False,
                    episode_quality_eligible=None,
                    timing_unknown=True, timing_status="unknown_no_analysis",
                    mission_success=None, semantic_consistency=None,
                    run_status=metadata.get("status"), onboard_status="unknown",
                    onboard_known_pass=False, truth_separation_known_clear=False,
                    hard_failures=hard)
    quality, labels, ac4, onboard = (artifacts[key] for key in
        ("quality", "labels", "ac4_timing_v3", "onboard_mission_param_check"))
    onboard_status = onboard.get("status")
    if onboard_status == "mismatch":
        hard.append("onboard mission parameter mismatch")
    separation = quality.get("truth_separation", {})
    observed_min, required = separation.get("minimum_m"), scene.get("min_separation_m")
    if finite(observed_min) and finite(required):
        if observed_min + 1e-9 < required:
            hard.append("truth minimum inter-UAV separation below requirement")
    timing_rows, known_violation, unknown = [], False, False
    for channel in ("truth", "observation"):
        evidence = ac4.get("channels", {}).get(channel, {})
        phase_rows = evidence.get("per_phase", {})
        if not phase_rows:
            unknown = True
        for phase in scene["phases"]:
            name = phase["name"]
            row = phase_rows.get(name, {})
            primary, cross = row.get("primary", {}), row.get("crosscheck", {})
            comparisons = ((primary, "primary"), (cross, "event_crosscheck"))
            for comparison, source in comparisons:
                D, tau = comparison.get("D_s"), comparison.get("tau_s")
                if finite(D) and finite(tau) and D > tau + 1e-9:
                    known_violation = True
                if not finite(D) or not finite(tau) or comparison.get("complete") is not True:
                    unknown = True
                timing_rows.append(dict(channel=channel, phase=name, source=source,
                                        D_s=D, tau_s=tau,
                                        complete=comparison.get("complete")))
            if row.get("within_tau") is False or row.get("crosscheck_within_tau") is False:
                known_violation = True
            if (row.get("complete") is not True or row.get("within_tau") is None
                    or row.get("crosscheck_within_tau") is None):
                unknown = True
        if (evidence.get("complete") is not True or evidence.get("within_tau") is None
                or evidence.get("crosscheck_within_tau") is None):
            unknown = True
        if evidence.get("within_tau") is False or evidence.get("crosscheck_within_tau") is False:
            known_violation = True
    if known_violation:
        hard.append("AC4 v3 phase D exceeds tau")
    timing_status = "violation" if known_violation else "unknown" if unknown else "within_tau"
    raw_quality = quality.get("episode_quality_eligible") is True
    onboard_pass = (onboard.get("required") is True and onboard_status == "pass"
                    and onboard.get("pass_gate") is True)
    truth_known_clear = finite(observed_min) and finite(required) and observed_min + 1e-9 >= required
    return dict(qualified=raw_quality,
                accepted_for_pp=raw_quality and timing_status == "within_tau"
                    and onboard_pass and truth_known_clear and not hard,
                episode_quality_eligible=quality.get("episode_quality_eligible"),
                mission_success=labels.get("mission_success"),
                semantic_consistency=labels.get("semantic_consistency"),
                run_status=metadata.get("status"), timing_unknown=unknown and not known_violation,
                timing_status=timing_status, timing_rows=timing_rows,
                truth_minimum_separation_m=observed_min,
                required_separation_m=required,
                onboard_status=onboard.get("status"),
                onboard_known_pass=onboard_pass,
                truth_separation_known_clear=truth_known_clear,
                hard_failures=hard)


def rolling_unknown(records):
    window = records[-20:]
    count = sum(row.get("timing_unknown") is True for row in window)
    return dict(unknown=count, attempts=len(window),
                fraction=count / len(window) if window else 0.0,
                limit=TIMING_UNKNOWN_LIMIT,
                stop=bool(window and count / len(window) > TIMING_UNKNOWN_LIMIT))


def terminal_rows(records):
    """Exclude superseded pre-takeoff attempts; keep every attempt in records."""
    by_index = {}
    for row in records:
        if row.get("retryable_pre_takeoff") is not True:
            by_index[row["logical_index"]] = row
    return [by_index[index] for index in sorted(by_index)]


def aggregate_status(records):
    terminal = terminal_rows(records)
    qualified = sum(row.get("qualified") is True for row in terminal)
    accepted = sum(row.get("accepted_for_pp") is True for row in terminal)
    raw_pairs, accepted_pairs = 0, 0
    for base in range(10):
        pair = [row for row in terminal if row["logical_index"] in (2 * base, 2 * base + 1)]
        raw_pairs += len(pair) == 2 and all(row.get("qualified") is True for row in pair)
        accepted_pairs += len(pair) == 2 and all(
            row.get("accepted_for_pp") is True for row in pair)
    by_intent = {}
    for intent in INTENT_ORDER:
        subset = [row for row in terminal if row["intent"] == intent]
        raw_eligible = [row for row in subset if row.get("qualified") is True]
        accepted_eligible = [row for row in subset if row.get("accepted_for_pp") is True]
        raw_success = sum(row.get("mission_success") is True for row in raw_eligible)
        accepted_success = sum(row.get("mission_success") is True for row in accepted_eligible)
        by_intent[intent] = dict(attempted=len(subset), qualified=len(raw_eligible),
                                 accepted_for_pp=len(accepted_eligible),
                                 success_given_quality=raw_success,
                                 success_fraction_given_quality=(raw_success / len(raw_eligible)
                                                                 if raw_eligible else None),
                                 success_given_pp_acceptance=accepted_success,
                                 success_fraction_given_pp_acceptance=(
                                     accepted_success / len(accepted_eligible)
                                     if accepted_eligible else None))
    return dict(logical_completed=len(terminal), attempts=len(records),
                qualified=qualified, accepted_for_pp=accepted,
                pair_qualified=raw_pairs, pair_accepted_for_pp=accepted_pairs,
                by_intent=by_intent)


def run_next(root=ROOT_OUTPUT):
    root = Path(root).resolve()
    control_path = root / "control.json"
    control = read(control_path)
    logical_index, attempt_index = next_mission(control)
    try:
        assert_hashes(control["frozen_sha256"])
        for previous in control["records"]:
            assert_hashes(previous.get("evidence_sha256", {}))
        assert_protected()
    except Exception as exc:
        control["stopped_reason"] = f"pre-run integrity failure: {type(exc).__name__}: {exc}"
        _save_atomic(control_path, control)
        raise
    listing, _ = verify_generation(Path(control["bundle"]) / "mission_list.json")
    entry = listing["missions"][logical_index]
    if entry["mission_id"] != control["planned_missions"][logical_index]:
        raise ValueError("pilot mission order changed")
    scene = read(checked_path(control["bundle"], entry["scene"]))
    run_root = root / "execution" / f"{logical_index:02d}_{entry['intent']}" / f"attempt_{attempt_index}"
    reservation = dict(logical_index=logical_index, attempt_index=attempt_index,
                       run_root=str(run_root), reserved_utc=utc())
    control["active_attempt"] = reservation
    _save_atomic(control_path, control)
    row = dict(**reservation, mission_id=entry["mission_id"], base_index=entry["base_index"],
               intent=entry["intent"], evidence_sha256={})
    try:
        ledger = run_mission_list(Path(control["bundle"]) / "mission_list.json",
            max_runs=1, resume=False, output_root=run_root, mission_ids=[entry["mission_id"]],
            binary=control["binary"], parameters=control["parameters"],
            quality_policy=control["quality_policy"],
            max_environment_retries=0, retryable_errors=())
        attempt = ledger["missions"][0]["attempts"][0]
        row.update(runner_status=attempt["status"], runner_error=attempt.get("error"),
                   run_directory=attempt.get("run_directory"))
        if not row["run_directory"]:
            row.update(qualified=False, accepted_for_pp=False, timing_unknown=None,
                       retryable_pre_takeoff=False,
                       hard_failures=["runner returned no run directory; flight status unproven"])
        else:
            directory = Path(row["run_directory"])
            metadata = read(directory / "metadata.json")
            parameter_path = directory / "firmware_parameters.json"
            param_evidence = read(parameter_path) if parameter_path.is_file() else {}
            retry_reason = preflight_retry_reason(
                metadata, param_evidence, _event_rows(directory))
            row["retryable_pre_takeoff"] = retry_reason is not None
            row["retry_reason"] = retry_reason
            row["run_id"] = metadata.get("run_id")
            if retry_reason:
                row.update(qualified=False, accepted_for_pp=False, timing_unknown=False,
                           timing_status="not_applicable_pre_takeoff", hard_failures=[])
            else:
                metadata, artifacts = _analysis_artifacts(directory, scene, control)
                row.update(assess_run(scene, metadata, artifacts, control))
            evidence = [run_root / "attempt_ledger.json",
                        directory / "metadata.json", directory / "quality.json",
                        directory / "firmware_parameters.json",
                        directory / "analysis_latest.json"]
            if (directory / "analysis_latest.json").is_file():
                latest = read(directory / "analysis_latest.json")
                analysis = checked_path(directory, latest["directory"])
                evidence.extend(analysis / (name + ".json") for name in
                    ("manifest", "quality", "labels", "ac4_timing_v3",
                     "onboard_mission_param_check"))
            row["evidence_sha256"] = {str(path.resolve()): file_hash(path)
                                      for path in evidence if path.is_file()}
        assert_post_run_integrity(control)
        row["finished_utc"] = utc()
    except BaseException as exc:
        row.update(qualified=False, accepted_for_pp=False, timing_unknown=None,
                   retryable_pre_takeoff=False,
                   hard_failures=[f"unresolved attempt: {type(exc).__name__}: {exc}"],
                   finished_utc=utc())
        control["stopped_reason"] = row["hard_failures"][0]
        control["records"].append(row)
        control["active_attempt"] = None
        _save_atomic(control_path, control)
        raise
    control["records"].append(row)
    control["active_attempt"] = None
    aggregate = aggregate_status(control["records"])
    control["aggregate"] = aggregate
    control["rolling_timing_unknown"] = rolling_unknown(control["records"])
    if row["hard_failures"]:
        control["stopped_reason"] = "; ".join(row["hard_failures"])
    elif row["retryable_pre_takeoff"]:
        used_extra = sum(item["attempt_index"] == 1 for item in control["records"])
        if (used_extra >= MAX_EXTRA_RETRIES or len(control["records"]) >= MAX_ATTEMPTS
                or sum(item["logical_index"] == logical_index
                       for item in control["records"]) >= 2):
            control["stopped_reason"] = "pre-takeoff retry budget exhausted"
    elif control["rolling_timing_unknown"]["stop"]:
        control["stopped_reason"] = "rolling timing_unknown exceeds 10 percent"
    elif aggregate["logical_completed"] - aggregate["qualified"] > 2:
        control["stopped_reason"] = "18/20 quality gate is no longer attainable"
    elif aggregate["logical_completed"] - aggregate["accepted_for_pp"] > 2:
        control["stopped_reason"] = "18/20 strict PP acceptance gate is no longer attainable"
    elif (sum(all(index in {item["logical_index"] for item in terminal_rows(control["records"])}
                  for index in (2 * base, 2 * base + 1))
              for base in range(10)) - aggregate["pair_accepted_for_pp"] > 1):
        control["stopped_reason"] = "9/10 two-intent pair gate is no longer attainable"
    elif aggregate["logical_completed"] >= LOGICAL_RUNS:
        control["completed"] = True
    _save_atomic(control_path, control)
    print(json.dumps(dict(attempts=len(control["records"]), aggregate=aggregate,
                          latest=row, stopped_reason=control["stopped_reason"]),
                     ensure_ascii=False))
    return int(bool(control["stopped_reason"]))


def _audit_ledger(control, path):
    by_mission = {}
    for mission_id in control["planned_missions"]:
        by_mission[mission_id] = dict(mission_id=mission_id, attempts=[])
    for row in control["records"]:
        by_mission[row["mission_id"]]["attempts"].append(dict(
            run_directory=row.get("run_directory"), run_status=row.get("run_status"),
            status=row.get("runner_status"), intent=row["intent"],
            timing_unknown=row.get("timing_unknown"),
            episode_quality_eligible=row.get("episode_quality_eligible")))
    save_json(path, dict(schema_version=1, source="v05b_pilot_controller_v1",
                         missions=list(by_mission.values())))


def _description_gate(dataset, output):
    dataset_manifest = read(dataset / "dataset_manifest.json")
    description_manifest = read(output / "language_manifest.json")
    payload = read(output / "descriptions.json")
    expected = {
        entry["run_id"] for entry in dataset_manifest["episodes"]
        if entry["episode_quality_eligible"] is True
        and entry["semantic_consistency"] == "agree"}
    grouped = Counter(item["episode_id"] for item in payload["descriptions"])
    hash_ok = (description_manifest["dataset_manifest_sha256"]
               == file_hash(dataset / "dataset_manifest.json")
               and all(file_hash(checked_path(output, name)) == digest
                       for name, digest in description_manifest["artifact_sha256"].items()))
    completeness = (set(grouped) == expected and all(grouped[episode] == 4 for episode in expected)
                    and description_manifest["eligible_agree_episodes"] == len(expected)
                    and description_manifest["descriptions"] == 4 * len(expected)
                    and len(payload["skipped"]) == len(dataset_manifest["episodes"]) - len(expected))
    return dict(expected_eligible_agree=len(expected), descriptions=len(payload["descriptions"]),
                skipped=len(payload["skipped"]), hash_binding_pass=hash_ok,
                completeness_pass=completeness,
                consistency_pass=hash_ok and completeness)


def pilot_acceptance_gates(aggregate, dataset_manifest, audit, descriptions, loaded):
    """Keep r1 raw-quality gates and the stricter no-unknown acceptance distinct."""
    gates = dict(
        twenty_terminal_runs=aggregate["logical_completed"] == LOGICAL_RUNS,
        episode_quality_18_of_20=aggregate["qualified"] >= 18,
        paired_quality_9_of_10=aggregate["pair_qualified"] >= 9,
        strict_accepted_18_of_20=aggregate["accepted_for_pp"] >= 18,
        paired_strict_accepted_9_of_10=aggregate["pair_accepted_for_pp"] >= 9,
        reconnaissance_success_given_quality=(
            aggregate["by_intent"]["reconnaissance"]["success_fraction_given_quality"] is not None
            and aggregate["by_intent"]["reconnaissance"]["success_fraction_given_quality"] >= .90),
        patrol_success_given_quality=(
            aggregate["by_intent"]["patrol"]["success_fraction_given_quality"] is not None
            and aggregate["by_intent"]["patrol"]["success_fraction_given_quality"] >= .90),
        dataset_export_twenty_episodes=len(dataset_manifest["episodes"]) == 20,
        dataset_audit_no_issues=not audit.get("issues"),
        descriptions_complete_and_consistent=descriptions["consistency_pass"],
        loader_reads_all_episodes=len(loaded) == 20 and all(
            row["corner_count"] == 4 and row["corner_dimensions"] == [2, 2, 2, 2]
            for row in loaded),
        protected_files_intact=True,
    )
    gates["pass"] = all(gates.values())
    return gates


def finalize(root=ROOT_OUTPUT):
    root = Path(root).resolve()
    path = root / "control.json"
    control = read(path)
    if (control.get("version") != VERSION or control.get("stopped_reason")
            or control.get("completed") is not True or control.get("finalized")
            or control.get("active_attempt") is not None):
        raise ValueError("PP is not complete and clean, or was already finalized")
    if (root / "acceptance.json").exists():
        raise ValueError("PP acceptance already exists; never overwrite")
    try:
        assert_hashes(control["frozen_sha256"])
        for row in control["records"]:
            assert_hashes(row.get("evidence_sha256", {}))
        assert_protected()
        terminal = terminal_rows(control["records"])
        if len(terminal) != LOGICAL_RUNS or [row["logical_index"] for row in terminal] != list(range(20)):
            raise ValueError("PP must have exactly twenty terminal mission attempts")
        if any(not row.get("run_directory") or not Path(row["run_directory"]).is_dir()
               for row in terminal):
            raise ValueError("a terminal PP attempt has no run directory")
        ledger_path = root / "audit_attempt_ledger.json"
        _audit_ledger(control, ledger_path)
        dataset = root / "dataset"
        build_dataset([row["run_directory"] for row in terminal], dataset)
        audit = audit_dataset(dataset,
                              generation_manifest=Path(control["bundle"]) / "generation_manifest.json",
                              attempt_ledger=ledger_path)
        save_json(root / "dataset_audit.json", audit)
        language = root / "dataset_language_zh_v0"
        describe_dataset(dataset, language)
        descriptions = _description_gate(dataset, language)
        dataset_manifest = read(dataset / "dataset_manifest.json")
        loaded = []
        for entry in dataset_manifest["episodes"]:
            episode_path = checked_path(dataset, entry["directory"])
            episode = load_episode(episode_path, verify_hashes=True)
            corners = load_public_scene(episode_path)
            loaded.append(dict(run_id=entry["run_id"], frames=len(episode["t_s"]),
                               agents=len(episode["agent_ids"]),
                               corner_count=len(corners), corner_dimensions=[len(c) for c in corners],
                               valid_frames=sum(sum(frame) for frame in episode["mask"])))
        aggregate = aggregate_status(control["records"])
        gates = pilot_acceptance_gates(aggregate, dataset_manifest, audit, descriptions, loaded)
        result = dict(version="v05b_pilot_acceptance_v1", gate=gates,
                      aggregate=aggregate, rolling_timing_unknown=rolling_unknown(control["records"]),
                      description_check=descriptions, loaded=loaded,
                      dataset_manifest_sha256=file_hash(dataset / "dataset_manifest.json"),
                      audit_sha256=file_hash(root / "dataset_audit.json"),
                      language_manifest_sha256=file_hash(language / "language_manifest.json"),
                      audit_issues=audit.get("issues", []),
                      source_control_sha256=file_hash(path), completed_utc=utc())
        save_json(root / "acceptance.json", result)
        summary = [
            "# v0.5 r1.1 试生产 PP 验收", "",
            f"结论：**{'PASS' if gates['pass'] else 'FAIL'}**。"
            f"共 {aggregate['attempts']} 次 SITL 尝试、20 个终态任务；"
            f"原始质量合格 {aggregate['qualified']}/20，严格 PP 接受 "
            f"{aggregate['accepted_for_pp']}/20；原始双意图均合格 "
            f"{aggregate['pair_qualified']}/10，严格双意图均接受 "
            f"{aggregate['pair_accepted_for_pp']}/10。", "",
            "| 门禁 | 判定 |", "| --- | --- |",
        ]
        summary.extend(f"| {name} | {'PASS' if passed else 'FAIL'} |"
                       for name, passed in gates.items() if name != "pass")
        summary += ["", "完整证据位于 acceptance.json、dataset_audit.json、"
                    "audit_attempt_ledger.json、dataset/ 和 dataset_language_zh_v0/；"
                    "控制台账为 control.json。失败时按 r1 第 0 节停止。", ""]
        (root / "pp_report.md").write_text("\n".join(summary), encoding="utf-8")
        control["finalized"] = True
        control["final_gate_pass"] = gates["pass"]
        if not gates["pass"]:
            control["stopped_reason"] = "PP final acceptance gate failed"
        _save_atomic(path, control)
        return result
    except BaseException as exc:
        control["stopped_reason"] = f"PP finalization stopped: {type(exc).__name__}: {exc}"
        _save_atomic(path, control)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "next", "finalize"))
    parser.add_argument("--root", type=Path, default=ROOT_OUTPUT)
    parser.add_argument("--hd-decision", type=Path, default=HD_DECISION)
    parser.add_argument("--sitl", type=Path, default=BINARY)
    parser.add_argument("--parameters", type=Path, default=PARAMETERS)
    parser.add_argument("--quality-policy", type=Path, default=QUALITY_POLICY)
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(args.root, args.hd_decision,
                         args.sitl, args.parameters, args.quality_policy)
        print(json.dumps(dict(version=result["version"], hold_s=result["hold_s"],
                              planned_missions=result["planned_missions"],
                              max_attempts=result["max_attempts"]), ensure_ascii=False))
        return 0
    if args.action == "next":
        return run_next(args.root)
    result = finalize(args.root)
    print(json.dumps(dict(gate=result["gate"], aggregate=result["aggregate"]),
                     ensure_ascii=False))
    return 0 if result["gate"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
