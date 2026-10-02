"""Summarize and cross-check the exhaustive DR reconnaissance diagnosis."""

import csv
import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from mechanism_diagnostic import GENERATED, diagnose_candidate
from swarm_sim.reconnaissance import plan_routes
from swarm_sim.registry import get_intent
from swarm_sim.route_planning import compile_route_phases, time_aware_phase_clearance


HERE = Path(__file__).resolve().parent
diagnostic = json.loads((HERE / "mechanism_diagnostic.json").read_text(encoding="utf-8"))
rows = diagnostic["rows"]
manifest = json.loads((GENERATED / "generation_manifest.json").read_text(encoding="utf-8"))
candidates = {c["candidate_id"]: c for c in manifest["candidates"]}


def _rank(row, agent):
    return int(row["assignments"][agent].rsplit("_", 1)[-1])


def _distance_summary(values):
    values = list(values)
    if not values:
        return None
    return dict(count=len(values), minimum_m=min(values), median_m=statistics.median(values),
                maximum_m=max(values))


crosscheck = Counter()
first_rejection_pairs = Counter()
source_first_distances = []
for row in rows:
    candidate = candidates[row["candidate_id"]]
    attempt = next(a for a in candidate["attempts"] if a["intent"] == "reconnaissance")
    task = GENERATED / attempt["task"]
    if hashlib.sha256(task.read_bytes()).hexdigest() != attempt["task_sha256"]:
        raise AssertionError(f"frozen candidate task hash differs: {row['candidate_id']}")
    crosscheck["candidate_task_sha256_matched"] += 1
    spec = json.loads(task.read_text(encoding="utf-8"))
    plan = plan_routes(spec)
    phases, semantic, _by_semantic, _no_ops, _removed = compile_route_phases(
        spec, plan, get_intent("reconnaissance"))
    source_phase, source_exception = None, None
    for phase in phases:
        starts = {agent: role["start_point"] for agent, role in
                  semantic["execution_phases"][phase["name"]]["agents"].items()}
        try:
            production = time_aware_phase_clearance(
                starts, phase["routes"], phase["speed_m_s"], 7.0,
                spec["execution"]["async_timing_tolerance"], phase["terminal_hold_s"],
                spec["execution"]["confirmation_dwell_s"])
        except ValueError as exc:
            source_phase, source_exception = phase["semantic_phase"], str(exc)
            break
        expected = row["phases"][phase["semantic_phase"]]["nominal_min_distance_m"]
        if abs(expected - production["nominal_min_clearance_m"]) > 1e-7:
            raise AssertionError(f"planned phase minimum mismatch: {row['candidate_id']}")
        crosscheck["nonrejecting_phase_minima_matched"] += 1
    if source_phase != row["first_violation_phase"]:
        raise AssertionError(f"first phase disagreement: {row['candidate_id']}")
    crosscheck["first_phase_matched"] += 1
    if source_exception:
        original = row["original_reason"]
        if not original or original != "ValueError: " + source_exception:
            raise AssertionError(f"original manifest rejection differs: {row['candidate_id']}")
        match = re.search(r"(uav_\d+)/(uav_\d+) ([\d.]+) m", source_exception)
        if match is None:
            raise AssertionError(f"source exception cannot be parsed: {row['candidate_id']}")
        left, right, displayed = match.groups()
        first_rejection_pairs[(source_phase, left, right)] += 1
        source_first_distances.append(float(displayed))
        phase = row["phases"][source_phase]
        if phase["nominal_min_distance_m"] > float(displayed) + .001:
            raise AssertionError(f"exhaustive minimum exceeds first sample: {row['candidate_id']}")
        crosscheck["exact_manifest_reason_matched"] += 1
    else:
        crosscheck["planned_candidates_matched"] += 1


groups = defaultdict(list)
first_phase_counts = defaultdict(Counter)
all_phase_counts = defaultdict(Counter)
all_violating_pairs_by_rank = Counter()
phase_minima = defaultdict(list)
phase_violation_minima = defaultdict(list)
for row in rows:
    group = (row["n"], row["formation"])
    groups[group].append(row)
    first_phase_counts[group][row["first_violation_phase"] or "none"] += 1
    for name, phase in row["phases"].items():
        phase_minima[(group, name)].append(phase["nominal_min_distance_m"])
        if phase["violating_pairs"]:
            all_phase_counts[group][name] += 1
            phase_violation_minima[(group, name)].append(phase["nominal_min_distance_m"])
        for pair in phase["violating_pairs"]:
            separation = abs(_rank(row, pair["agents"][0]) - _rank(row, pair["agents"][1]))
            all_violating_pairs_by_rank[(name, separation)] += 1


observe = []
for row in rows:
    phase = row["phases"]["observe"]
    observed_min = phase["nominal_min_distance_m"]
    predicted = row["strip_width_minus_configured_spacing_m"]
    rank_difference = abs(_rank(row, phase["nominal_min_pair"][0]) -
                          _rank(row, phase["nominal_min_pair"][1]))
    if rank_difference != 1:
        raise AssertionError(f"observe minimum is not adjacent strip pair: {row['candidate_id']}")
    multiple = observed_min / row["actual_lane_spacing_m"]
    if abs(multiple - round(multiple)) > 1e-8:
        raise AssertionError(f"observe minimum not lane-center multiple: {row['candidate_id']}")
    observe.append(dict(candidate_id=row["candidate_id"], n=row["n"],
                        formation=row["formation"], axis=row["resolved_axis"],
                        strip_width_m=row["strip_width_m"],
                        actual_lane_spacing_m=row["actual_lane_spacing_m"],
                        predicted_width_minus_configured_m=predicted,
                        predicted_width_minus_actual_m=row["strip_width_minus_actual_spacing_m"],
                        measured_observe_min_m=observed_min,
                        lanes_per_strip=row["lanes_per_strip"],
                        lane_center_spacing_multiple=round(multiple),
                        configured_prediction_violation=predicted + 1e-9 < 7,
                        actual_prediction_violation=row["strip_width_minus_actual_spacing_m"] + 1e-9 < 7,
                        actual_violation=bool(phase["violating_pairs"])))

configured_confusion = Counter((item["configured_prediction_violation"], item["actual_violation"])
                               for item in observe)
actual_confusion = Counter((item["actual_prediction_violation"], item["actual_violation"])
                           for item in observe)
diff = [abs(item["measured_observe_min_m"] - item["predicted_width_minus_configured_m"])
        for item in observe]
actual_diff = [abs(item["measured_observe_min_m"] - item["predicted_width_minus_actual_m"])
               for item in observe]
multiple_counts = Counter(item["lane_center_spacing_multiple"] for item in observe)

result = dict(version="read_only_recon_mechanism_summary_v1", source_rows=len(rows),
    source_checker_crosscheck=dict(crosscheck),
    group_counts={f"N{n}_{formation}": len(values) for (n, formation), values in sorted(groups.items())},
    first_violation_counts={f"N{n}_{formation}": dict(counter)
                            for (n, formation), counter in sorted(first_phase_counts.items())},
    any_phase_violation_counts={f"N{n}_{formation}": dict(counter)
                                for (n, formation), counter in sorted(all_phase_counts.items())},
    phase_minimum_distance_m={f"N{n}_{formation}_{phase}": _distance_summary(values)
                              for ((n, formation), phase), values in sorted(phase_minima.items())},
    violating_phase_minimum_distance_m={f"N{n}_{formation}_{phase}": _distance_summary(values)
                                        for ((n, formation), phase), values in sorted(phase_violation_minima.items())},
    violating_pair_counts_by_partition_rank={f"{phase}_rank_delta_{delta}": count
                                             for (phase, delta), count in sorted(all_violating_pairs_by_rank.items())},
    original_first_reject_distance_m=_distance_summary(source_first_distances),
    observe_geometry=dict(
        original_hypothesis="nominal_min_observe_distance = strip_width - scan_line_spacing",
        configured_lane_spacing_m=4.0,
        interpretation_configured_lane_spacing=dict(
            formula="strip_width - configured_lane_spacing_m (4 m)",
            exact_within_1um=sum(error <= 1e-6 for error in diff),
            absolute_error_m=_distance_summary(diff),
            threshold_confusion={f"prediction_{prediction}_actual_{actual}": count
                                 for (prediction, actual), count in sorted(configured_confusion.items())}),
        interpretation_actual_lane_center_spacing=dict(
            formula="strip_width - strip_width / ceil(strip_width / configured_lane_spacing_m)",
            exact_within_1um=sum(error <= 1e-6 for error in actual_diff),
            absolute_error_m=_distance_summary(actual_diff),
            threshold_confusion={f"prediction_{prediction}_actual_{actual}": count
                                 for (prediction, actual), count in sorted(actual_confusion.items())}),
        matches_actual_adjacent_lane_center_gap_within_1um=sum(
            abs(item["measured_observe_min_m"] - item["actual_lane_spacing_m"]) <= 1e-6
            for item in observe),
        matches_lanes_minus_one_times_actual_spacing_within_1um=sum(
            abs(item["measured_observe_min_m"] -
                (item["lanes_per_strip"] - 1) * item["actual_lane_spacing_m"]) <= 1e-6
            for item in observe),
        actual_min_as_multiple_of_center_lane_spacing={str(k): v for k, v in sorted(multiple_counts.items())},
        rows=observe))
(HERE / "mechanism_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")

fieldnames = ["candidate_id", "N", "formation", "entry_side", "resolved_axis", "joint_status", "recon_status",
              "first_violation_phase", "all_violating_phases", "approach_min_pair",
              "approach_min_distance_m", "observe_min_pair", "observe_min_distance_m",
              "return_min_pair", "return_min_distance_m", "strip_width_m",
              "configured_lane_spacing_m", "actual_lane_spacing_m"]
with (HERE / "mechanism_candidates.csv").open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        record = dict(candidate_id=row["candidate_id"], N=row["n"],
                      formation=row["formation"], entry_side=row["entry_side"],
                      resolved_axis=row["resolved_axis"], joint_status=row["joint_status"],
                      recon_status=row["recon_status"],
                      first_violation_phase=row["first_violation_phase"],
                      all_violating_phases="|".join(row["violating_phases"]),
                      strip_width_m=row["strip_width_m"],
                      configured_lane_spacing_m=row["configured_lane_spacing_m"],
                      actual_lane_spacing_m=row["actual_lane_spacing_m"])
        for phase in ("approach", "observe", "return"):
            detail = row["phases"].get(phase)
            record[f"{phase}_min_pair"] = "|".join(detail["nominal_min_pair"]) if detail else ""
            record[f"{phase}_min_distance_m"] = detail["nominal_min_distance_m"] if detail else ""
        writer.writerow(record)
print(json.dumps({key: result[key] for key in (
    "source_checker_crosscheck", "group_counts", "first_violation_counts",
    "any_phase_violation_counts", "violating_pair_counts_by_partition_rank")},
    ensure_ascii=False, indent=2))
print(json.dumps({key: value for key, value in result["observe_geometry"].items() if key != "rows"},
                 ensure_ascii=False, indent=2))
