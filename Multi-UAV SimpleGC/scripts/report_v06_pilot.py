"""Read-only V06 audit, loader verification and v0.3 distribution comparison.

Never launch, reanalyze or mutate an episode. All output must be a new directory.
Legacy execution metrics come only from the already-created WP-E copies; their
observations are bound to the frozen v0.3 pilot export before use.
"""
import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.dataset_audit_v3 import COMMON_METRICS
from swarm_sim.episode_loader import FEATURE_COLUMNS, load_episode
from swarm_sim.execution_metrics import distribution
from swarm_sim.generation import canonical_hash, checked_path, file_hash

VERSION = "v06_pilot_distribution_report_v1"
LEGACY = ROOT / "verification/v03_pilot_final_20260930"
COPIES = ROOT / "tmp_v04/wp_e/legacy_regression/legacy_copies"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def summary(values, unit, basis):
    values = list(values)
    result = distribution(v for v in values if numeric(v))
    result.update(expected_count=len(values), unknown_count=len(values)-result["count"],
                  unit=unit, denominator_basis=basis)
    return result


def bind(path, bindings):
    path = Path(path).resolve()
    digest = file_hash(path)
    if str(path) in bindings and bindings[str(path)] != digest:
        raise ValueError("input changed during report: " + str(path))
    bindings[str(path)] = digest
    return path


def check_loaded(episode, *, allow_empty=False):
    """Check every feature and mask, not just the first row's apparent shape."""
    times, agents = episode["t_s"], episode["agent_ids"]
    x, mask = episode["x"], episode["mask"]
    checks = dict(nonempty_agents=bool(agents),
                  observation_population=bool(times) or allow_empty,
                  unique_agents=len(set(agents)) == len(agents),
                  matching_time_count=len(x) == len(mask) == len(times),
                  feature_columns=episode["metadata"]["feature_columns"] == list(FEATURE_COLUMNS),
                  strictly_increasing_times=all(b > a for a, b in zip(times, times[1:])),
                  full_shape=True, boolean_mask=True, finite_values=True, invalid_zero_filled=True)
    valid = 0
    for frame, frame_mask in zip(x, mask):
        if len(frame) != len(agents) or len(frame_mask) != len(agents):
            checks["full_shape"] = False
        for values, is_valid in zip(frame, frame_mask):
            checks["full_shape"] &= len(values) == 6
            checks["boolean_mask"] &= type(is_valid) is bool
            checks["finite_values"] &= all(numeric(v) for v in values)
            checks["invalid_zero_filled"] &= bool(is_valid) or all(v == 0 for v in values)
            valid += is_valid is True
    return dict(x_shape=[len(times), len(agents), 6], mask_shape=[len(times), len(agents)],
                valid_agent_frames=valid, total_agent_frames=len(times)*len(agents),
                has_observation_frames=bool(times), has_valid_observations=valid > 0,
                empty_export_allowed=allow_empty,
                checks=checks, passed=all(checks.values()))


def check_exported_episode(entry, episode):
    # A retained failed/ineligible attempt may legitimately contain no task
    # frames. Decoding [0,N,6] is valid; it is never evidence of usable data.
    allow_empty = entry.get("run_status") == "failed" and entry.get("episode_quality_eligible") is False
    return check_loaded(episode, allow_empty=allow_empty)


def audit_coverage(audit):
    """Presence/completeness of the required 6.9 contract, separate from quality."""
    required_top = ("counts", "rates", "clock_grades", "counterfactual_completeness",
                    "id_position_order", "duplicates", "family_split_leaks", "groups")
    checks = {"top:"+key: key in audit for key in required_top}
    checks["nonempty_groups"] = bool(audit.get("groups"))
    for index, group in enumerate(audit.get("groups", [])):
        prefix = f"group[{index}]:"
        checks[prefix+"intent_control_mode"] = bool(group.get("intent") and group.get("control_mode"))
        checks[prefix+"all_common_metrics"] = all(key in group.get("metrics", {}) for key in COMMON_METRICS)
        checks[prefix+"explicit_metric_denominators"] = all(
            all(key in value for key in ("count", "expected_values", "missing_values"))
            for value in group.get("metrics", {}).values())
        checks[prefix+"declared_intent_metrics"] = all(
            name in group.get("intent_metrics", {}) for name in group.get("required_audit_metrics", []))
        checks[prefix+"explicit_missing_metrics"] = all(key in group for key in ("missing_common_metrics", "missing_intent_metrics"))
        checks[prefix+"clock_counts_eligibility"] = all(key in group for key in ("clock_grades", "episode_count", "rates"))
        checks[prefix+"id_order_both_axes"] = all(axis in group.get("id_position_order", {}) for axis in ("east", "north"))
        checks[prefix+"topology_overlap"] = all(key in group.get("topology", {}) for key in
            ("signature_counts", "test_signature_seen_in_train", "distinct_test_signatures_seen_in_train"))
    return dict(checks=checks, passed=all(checks.values()), common_metric_names=list(COMMON_METRICS),
                note="Presence includes explicit unknowns; a present field with no usable values is not treated as zero.")


def selected_execution_copy(entry, frozen_episode, bindings, copies=COPIES):
    source_name = Path(entry["source_run"]).name
    copied = Path(copies) / source_name
    metadata = read(bind(copied/"metadata.json", bindings))
    if metadata.get("run_id") != entry["run_id"]:
        raise ValueError("legacy copy run identity mismatch")
    pointer = read(bind(copied/"analysis_latest.json", bindings))
    analysis = checked_path(copied, pointer["directory"])
    manifest_path = bind(analysis/"manifest.json", bindings)
    if file_hash(manifest_path) != pointer["manifest_sha256"]:
        raise ValueError("legacy copied analysis pointer hash mismatch")
    manifest = read(manifest_path)
    if manifest.get("run_id") != entry["run_id"]:
        raise ValueError("legacy analysis run identity mismatch")
    expected = manifest.get("artifact_sha256", {})
    for name in ("execution_metrics.json", "observations.csv", "task.json"):
        actual = file_hash(bind(analysis/name, bindings))
        if actual != expected.get(name):
            raise ValueError("legacy copied artifact hash mismatch: " + name)
        if name != "execution_metrics.json" and actual != file_hash(bind(frozen_episode/name, bindings)):
            raise ValueError("legacy copy differs from frozen pilot: " + name)
    return read(analysis/"execution_metrics.json"), analysis/"execution_metrics.json", metadata


def episode_row(entry, episode_root, metadata, execution, execution_path, bindings):
    manifest = read(bind(episode_root/"manifest.json", bindings))
    labels = read(bind(episode_root/"labels.json", bindings))
    task = read(bind(episode_root/"task.json", bindings))
    quality = read(bind(episode_root/"quality.json", bindings))
    windows = read(bind(episode_root/"phase_windows.json", bindings))
    for name in manifest.get("artifact_sha256", {}):
        bind(checked_path(episode_root, name), bindings)
    is_v3 = task.get("schema_version") == 3
    if execution.get("version") != "execution_artifacts_v1":
        raise ValueError("unsupported execution metrics version")
    agents = manifest["agent_ids"]
    bounds = execution.get("fraction_window_s")
    span = bounds[1]-bounds[0] if bounds and all(numeric(v) for v in bounds) else None
    timing = metadata.get("phase_timing", {})
    overheads = [value.get("upload_release_confirmation_overhead_s") for value in timing.values()]
    totals = [value.get("total_duration_s") for value in timing.values()]
    overhead = sum(overheads)/sum(totals) if overheads and all(numeric(x) for x in overheads+totals) and sum(totals)>0 else None
    stop_counts = {}
    for threshold in ("0.3", "0.5"):
        per_agent = execution.get("thresholds", {}).get(threshold, {}).get("per_agent", {})
        stop_counts[threshold] = {agent: (per_agent.get(agent, {}).get("stop_count")
            if per_agent.get(agent, {}).get("evidence_complete") is True
            and not per_agent.get(agent, {}).get("stop_count_is_lower_bound", False)
            else None) for agent in agents}
    per_channel = labels.get("mission_metrics", {})
    return dict(run_id=entry["run_id"], scenario_id=entry.get("scenario_id"),
        intent=task["mission"]["intent"], control_mode=task["execution"].get("control_mode", "waypoint_barrier_v1"),
        task_kind=manifest["task_kind"], family_id=entry["family_id"], split=entry["split"],
        run_status=entry["run_status"], episode_quality_eligible=quality.get("episode_quality_eligible") if is_v3 else None,
        legacy_benchmark_eligible=entry.get("benchmark_eligible") if not is_v3 else None,
        agents=len(agents), elapsed_s=metadata.get("elapsed_s"), task_span_s=span,
        region_dimensions_m=[next(r for r in task["scenario"]["regions"] if r["id"] == task["mission"]["target_region_id"])[k]
                             for k in ("width_m", "height_m")],
        partition_axis=task["planner"].get("params", task["planner"])["partition_axis"], return_required=task["mission"]["return_required"],
        speed_m_s=task["execution"]["speed_m_s"], execution_stage_count=len({w["phase"] for w in windows.get("windows", [])}),
        truth_coverage=per_channel.get("truth", {}).get("coverage", {}).get("global_coverage_ratio"),
        observation_coverage=per_channel.get("observation", {}).get("coverage", {}).get("global_coverage_ratio"),
        stop_counts=stop_counts, thresholds=execution.get("thresholds", {}),
        intermediate_waypoints=execution.get("intermediate_waypoints", {}),
        arrival_lag_s=execution.get("arrival_lag_s"),
        upload_release_confirmation_fraction=overhead,
        overhead_denominator="sum of metadata.phase_timing.total_duration_s; unavailable if absent in original metadata",
        execution_metrics_path=str(execution_path.resolve()), execution_metrics_version=execution["version"],
        observation_processing_versions={key: manifest.get(key) for key in
            ("observation_processing_version", "duplicate_policy_version", "timeline_policy_version", "clock_model_version")},
        clock_grade=quality.get("clock_quality", {}).get("overall"),
        note="v0.3 quality label remains original benchmark_eligible; not relabeled as v3 episode_quality_eligible" if not is_v3 else None)


def grouped_distributions(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["intent"], row["control_mode"]].append(row)
    output = []
    for (intent, mode), members in sorted(groups.items()):
        metrics = {}
        for threshold in ("0.3", "0.5"):
            prefix = "speed_lt_"+threshold+"_m_s"
            metrics[prefix+":stop_count_per_aircraft"] = summary(
                (v for row in members for v in row["stop_counts"][threshold].values()), "count", "aircraft-episodes, including unknown")
            for name in ("stationary_time_fraction", "synchronized_time_fraction"):
                metrics[prefix+":"+name] = summary((r["thresholds"].get(threshold, {}).get(name) for r in members),
                    "fraction", "episodes equally weighted; task-span time within each episode")
        for key, unit in (("task_span_s", "s"), ("elapsed_s", "s"), ("truth_coverage", "fraction"),
                          ("observation_coverage", "fraction"), ("upload_release_confirmation_fraction", "fraction"),
                          ("agents", "count"), ("speed_m_s", "m/s"), ("execution_stage_count", "count")):
            metrics[key] = summary((r[key] for r in members), unit, "episodes equally weighted")
        intermediate = [r["intermediate_waypoints"] for r in members]
        known_counts = all(numeric(m.get("total_count")) and numeric(m.get("stopped_count"))
                           and numeric(m.get("unknown_count")) for m in intermediate)
        total = sum(m["total_count"] for m in intermediate) if known_counts else None
        stopped = sum(m["stopped_count"] for m in intermediate) if known_counts else None
        unknown = sum(m["unknown_count"] for m in intermediate) if known_counts else None
        output.append(dict(intent=intent, control_mode=mode, episode_count=len(members), metrics=metrics,
            intermediate_stop=dict(stopped_count=stopped, total_count=total, unknown_count=unknown,
                rate=stopped/total if total and unknown == 0 else None,
                denominator_basis="all intermediate waypoints across episodes; rate unknown if any waypoint unknown")))
    return output


def passing_speed_groups(rows):
    groups = defaultdict(list)
    for row in rows:
        for waypoint in row["intermediate_waypoints"].get("records", []):
            length = waypoint.get("scan_line_length_m")
            key = (row["intent"], row["control_mode"], f"{length:.6f}" if numeric(length) else "unknown")
            groups[key].append(dict(run_id=row["run_id"], **waypoint))
    return [dict(intent=intent, control_mode=mode, scan_line_length_m=float(length) if length != "unknown" else None,
        total_waypoints=len(records), valid_waypoints=sum(numeric(r.get("minimum_passing_speed_m_s")) for r in records),
        unknown_waypoints=sum(not numeric(r.get("minimum_passing_speed_m_s")) for r in records),
        minimum_passing_speed=summary((r.get("minimum_passing_speed_m_s") for r in records), "m/s", "intermediate waypoint observations"),
        evidence_basis="FCU_horizontal_velocity", neighborhood_radius_m=2.0,
        execution_metrics_version="execution_artifacts_v1", records=records)
        for (intent, mode, length), records in sorted(groups.items())]


def sampled_composition(rows):
    return dict(episode_count=len(rows),
        categorical={key: dict(Counter(str(row[key]).lower() for row in rows))
                     for key in ("agents", "partition_axis", "return_required", "speed_m_s")},
        region_width_m=summary((row["region_dimensions_m"][0] for row in rows), "m", "episodes"),
        region_height_m=summary((row["region_dimensions_m"][1] for row in rows), "m", "episodes"),
        note="Actual samples, not the profile population distribution. Same seed across generator versions does not imply paired scenes.")


def profile_comparison(generation_manifest, generation, bindings):
    new_profile = read(bind(Path(generation_manifest).parent/"generation_profile.json", bindings))
    old_profile = read(bind(ROOT/"generated/recon_pilot_v03_20260930/generation_profile.json", bindings))
    sampler = new_profile["scene_sampler"]["params"]
    shared = new_profile["shared_mission_params"]
    keys = ("vehicle_counts", "partition_axes", "strip_width_m", "sweep_length_m", "region_east_m",
            "region_north_m", "entry_distance_m", "entry_sides", "speeds_m_s", "return_required", "variant_speed_factors")
    pairs = {}
    for key in keys:
        new = (sampler[key] if key in sampler else shared[key] if key in shared else
               new_profile["missions"][0][key])
        pairs[key] = dict(v03=old_profile[key], v04=new, equal=old_profile[key] == new)
    return dict(parameter_distributions=pairs, all_equal=all(v["equal"] for v in pairs.values()),
        profile_fingerprint_matches=canonical_hash(new_profile) == generation.get("profile_sha256"),
        requested_scene_count=new_profile["base_scene_count"],
        old_generation_pool_scene_count=old_profile["base_scene_count"],
        old_comparison_selected_count=10, profile_sha256=generation.get("profile_sha256"),
        seed_note="v0.3 pilot selected first 10 scenes of a 100-scene generation pool; new v2 profile generates 10 scenes with a changed hierarchical seed scheme.")


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def generate_report(dataset, generation_manifest, attempt_ledger, output, legacy=LEGACY, copies=COPIES):
    dataset, output, legacy = Path(dataset).resolve(), Path(output).resolve(), Path(legacy).resolve()
    if output.exists():
        raise ValueError("report output already exists; use a new directory")
    bindings = {}
    current = read(bind(dataset/"dataset_manifest.json", bindings))
    generation = read(bind(generation_manifest, bindings))
    profiles = profile_comparison(generation_manifest, generation, bindings)
    ledger = read(bind(attempt_ledger, bindings))
    if current.get("semantic_protocol", {}).get("task_kind") != "mission_v3":
        raise ValueError("V06 requires a v3 dataset")
    audit = audit_dataset(dataset, generation_manifest, attempt_ledger)
    coverage = audit_coverage(audit)
    rows, loaded = [], []
    for entry in current["episodes"]:
        ep = checked_path(dataset, entry["directory"])
        loaded.append(dict(run_id=entry["run_id"], **check_exported_episode(entry, load_episode(ep))))
        metadata = read(bind(Path(entry["source_run"])/"metadata.json", bindings))
        if metadata.get("run_id") != entry["run_id"]:
            raise ValueError("source metadata run identity mismatch")
        execution_path = bind(ep/"execution_metrics.json", bindings)
        rows.append(episode_row(entry, ep, metadata, read(execution_path), execution_path, bindings))
    old_dataset = legacy/"dataset"
    old_manifest = read(bind(old_dataset/"dataset_manifest.json", bindings))
    old_rows, old_loaded = [], []
    for entry in old_manifest["episodes"]:
        ep = checked_path(old_dataset, entry["directory"])
        old_loaded.append(dict(run_id=entry["run_id"], **check_loaded(load_episode(ep))))
        execution, execution_path, metadata = selected_execution_copy(entry, ep, bindings, copies)
        old_rows.append(episode_row(entry, ep, metadata, execution, execution_path, bindings))
    if len(old_rows) != 10 or {row["scenario_id"] for row in old_rows} != {f"recon_{i:04d}_v00" for i in range(10)}:
        raise ValueError("comparison must use all ten original v0.3 pilot episodes")
    attempts = [a for m in ledger.get("missions", []) for a in m.get("attempts", [])]
    attempt_ids = []
    for attempt in attempts:
        directory = attempt.get("run_directory")
        if not directory:
            attempt_ids.append(None)
            continue
        metadata = read(bind(Path(directory)/"metadata.json", bindings))
        if metadata.get("status") != attempt.get("run_status"):
            raise ValueError("attempt and run metadata status mismatch")
        attempt_ids.append(metadata.get("run_id"))
    exported_ids = {row["run_id"] for row in rows}
    successful = sum(r["run_status"] == "completed" and r["episode_quality_eligible"] is True for r in rows)
    checks = dict(ten_exported_scenes=len(rows) == 10 and len({r["family_id"] for r in rows}) == 10,
        at_most_ten_attempts=0 < len(attempts) <= 10,
        ledger_all_attempts_exported=bool(attempts) and None not in attempt_ids and len(set(attempt_ids)) == len(attempts) and set(attempt_ids) == exported_ids,
        at_least_eight_completed_and_quality_eligible=successful >= 8,
        matching_profile_parameter_distributions=profiles["all_equal"],
        new_profile_fingerprint_verified=profiles["profile_fingerprint_matches"],
        ten_generated_scenes=profiles["requested_scene_count"] == 10 and generation.get("counts", {}).get("accepted_bases") == 10,
        family_scheme=current.get("family_scheme") == "scene_content_v1",
        route_only=all(r["control_mode"] == "semantic_phase_route_v1" for r in rows),
        reconnaissance_only=all(r["intent"] == "reconnaissance" for r in rows),
        audit_69_fields=coverage["passed"], no_audit_issues=not audit["issues"],
        loader_all_pass=bool(loaded) and all(r["passed"] for r in loaded),
        legacy_loader_all_pass=all(r["passed"] for r in old_loaded),
        distribution_comparison=True)
    sources_unchanged = all(file_hash(Path(path)) == digest for path, digest in bindings.items())
    checks["source_files_unchanged"] = sources_unchanged
    result = dict(report_version=VERSION, accepted=all(checks.values()), checks=checks,
        completion=dict(completed_and_quality_eligible=successful, required_minimum=8, requested_scenes=10,
                        actual_attempts=len(attempts), denominator=10),
        profile_fingerprint=generation.get("profile_sha256"), profile_comparison=profiles, audit_field_coverage=coverage,
        sampled_composition=dict(v03=sampled_composition(old_rows), v04=sampled_composition(rows)),
        loader=dict(new=loaded, v03=old_loaded), distributions=dict(v03=grouped_distributions(old_rows), v04=grouped_distributions(rows)),
        passing_speed_groups=passing_speed_groups(rows), episodes=dict(v03=old_rows, v04=rows),
        sources_sha256=bindings, sources_unchanged=sources_unchanged,
        limitations=["Descriptive distribution comparison, not a paired experiment or causal estimate.",
            "Profiles share parameter distributions; sampled scenes/vehicle composition may differ.",
            "No inference of classification accuracy from a single intent.",
            "Legacy arrival_lag and nominal timing remain unavailable when not originally recorded.",
            "Stop count: FCU horizontal speed <0.3 m/s for >=0.2 s; 0.5 m/s is sensitivity diagnostic.",
            "Counts use the exported grid; stationary and synchronization fractions use the semantic task span.",
            "Passing speeds use existing resampled FCU evidence in 2 m neighborhoods, not raw packet minima.",
            "arrival_s definition is unchanged; fallback diagnostics are reported separately."])
    output.mkdir(parents=True, exist_ok=False)
    write_new(output/"audit.json", audit)
    write_new(output/"report.json", result)
    lines = ["# V06 试生产只读分布对照与数据审计", "", f"结论：{'PASS' if result['accepted'] else 'FAIL'}；完成且质量合格 {successful}/10；SITL 尝试 {len(attempts)}/10。", "",
             "数值是分布描述，不能解释为配对实验或单独由控制模式引起的因果变化。详细分母、未知值、逐集证据与文件哈希见 report.json；6.9 审计全文见 audit.json。", "",
             "| 指标 | v0.3 barrier：中位数 [最小, 最大] | v0.4 route：中位数 [最小, 最大] |", "|---|---:|---:|"]
    def fmt(value):
        if value["count"] == 0:
            return f"UNKNOWN ({value['unknown_count']}/{value['expected_count']})"
        return f"{value['median']:.4f} [{value['min']:.4f}, {value['max']:.4f}]；n={value['count']}"
    old_dist, new_dist = result["distributions"]["v03"][0], result["distributions"]["v04"][0]
    for key in old_dist["metrics"]:
        lines.append(f"| {key} | {fmt(old_dist['metrics'][key])} | {fmt(new_dist['metrics'][key])} |")
    lines += ["", "| 扫描线长度（m） | 有效/总点数 | 未知 | 最小 / P10 / 中位 / P90 / 最大（m/s） |", "|---:|---:|---:|---|"]
    for group in result["passing_speed_groups"]:
        d = group["minimum_passing_speed"]
        values = " / ".join(f"{d[k]:.4f}" if numeric(d[k]) else "UNKNOWN" for k in ("min", "p10", "median", "p90", "max"))
        lines.append(f"| {group['scan_line_length_m']} | {group['valid_waypoints']}/{group['total_waypoints']} | {group['unknown_waypoints']} | {values} |")
    lines += ["", "过点速度：FCU 水平速度，航点 2 m 邻域，execution_artifacts_v1；四个观测处理版本逐集保留于 report.json。", "", "所有检查："]
    lines += [f"- {key}: {'PASS' if value else 'FAIL'}" for key, value in checks.items()]
    (output/"report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--generation-manifest", required=True, type=Path)
    parser.add_argument("--attempt-ledger", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = generate_report(args.dataset, args.generation_manifest, args.attempt_ledger, args.output)
    print(json.dumps(dict(output=str(args.output), accepted=report["accepted"], checks=report["checks"]), indent=2))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
