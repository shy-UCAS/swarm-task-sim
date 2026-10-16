"""S15 stage 2 step 3: read-only yield statistics for the frozen S1.5 maps.

Reads the step 1 descriptor directory, the step 2 yield attempt and the S1.5 map files, then
writes docs/v07/evidence/s15/s15_yield_summary.json and s15_yield_tables.md. Numbers only:
T1-T6 follow the registered definitions; no interpretation, no repair suggestion.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scene_v07.geometry import to_shape
from task_v07.expansion.contracts import P0ContractError
from task_v07.io import read_json, save_json, sha

OUT_DIR = PROJECT / "docs/v07/evidence/s15"
INTENTS = ("transit", "reconnaissance", "monitoring", "feint", "penetration")
LAYERS = ("single", "isolated", "clustered", "linear")
MODES = ("same_direction", "multi_direction")
BUCKET_ORDER = ("2–3", "4–5", "≥6", "<2")
FIXED_CATEGORIES = ("target_facility", "other_facility_inner", "other_facility_warning", "world_boundary")
TOL = 1e-6


def read_lines(path):
    records = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                records.append(json.loads(line))
    return records


def bucket(member_count):
    if member_count < 2:
        return "<2"
    if member_count <= 3:
        return "2–3"
    if member_count <= 5:
        return "4–5"
    return "≥6"


def distribution(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return {"count": 0, "min": None, "p50": None, "p90": None, "max": None}

    def quantile(p):
        index = (len(values) - 1) * p
        low = int(index)
        return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (index - low)

    return {"count": len(values), "min": round(values[0], 6), "p50": round(quantile(.5), 6),
            "p90": round(quantile(.9), 6), "max": round(values[-1], 6)}


def numbers(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def collect_entities(node, entities):
    """Walk only the terminal rejection subtree; key names are fixed by the registered rule."""
    if isinstance(node, dict):
        entity = node.get("entity_id")
        if isinstance(entity, str):
            entities.add(entity)
        clearances, required = node.get("clearances_m"), node.get("required_m")
        if isinstance(clearances, dict) and numbers(required):
            for key, clearance in clearances.items():
                if numbers(clearance) and clearance < required:
                    entities.add(key)
        for child in node.values():
            collect_entities(child, entities)
    elif isinstance(node, list):
        for child in node:
            collect_entities(child, entities)


def classify(entity_id, target_id, placements, anomalies):
    if entity_id == target_id or entity_id.startswith(target_id + "_"):
        return "target_facility"
    if entity_id.startswith("facility_") and (entity_id.endswith("_alert") or entity_id.endswith("_protected")):
        return "other_facility_inner"
    if entity_id.startswith("facility_") and entity_id.endswith("_warning"):
        return "other_facility_warning"
    if entity_id.startswith("obstacle_"):
        placement = placements.get(entity_id)
        if placement is None:
            anomalies.append({"kind": "obstacle_placement_missing", "entity_id": entity_id})
            return "obstacle:<not_found>"
        return f"obstacle:{placement}"
    if entity_id == "world":
        return "world_boundary"
    return f"other:{entity_id}"


def category_order(categories):
    fixed = [name for name in FIXED_CATEGORIES if name in categories]
    obstacles = sorted(name for name in categories if name.startswith("obstacle:"))
    others = sorted(name for name in categories if name.startswith("other:"))
    unattributed = sorted(name for name in categories if name.startswith("unattributed:"))
    return fixed + obstacles + others + unattributed


def collect_references(node, merged, anomalies, trail=""):
    """Every "references" mapping in the file; identical duplicates collapse to one entry."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "references" and isinstance(value, dict):
                for agent, info in value.items():
                    if agent not in merged:
                        merged[agent] = info
                    elif merged[agent] != info:
                        anomalies.append({"kind": "reference_conflict", "agent_id": agent, "path": trail})
            else:
                collect_references(value, merged, anomalies, f"{trail}/{key}")
    elif isinstance(node, list):
        for index, child in enumerate(node):
            collect_references(child, merged, anomalies, f"{trail}[{index}]")


def warning_geometry(scene, facility_id):
    for entity in scene["entities"]:
        if entity.get("facility_id") == facility_id and entity.get("layer") == "warning":
            return entity["geometry"]
    return None


def work_polyline(points):
    """A one-point work set has zero length, so the registered length test can never fire."""
    coords = [(point[0], point[1]) for point in points]
    return LineString(coords if len(coords) > 1 else [coords[0], coords[0]])


def enters_warning(points, geometry):
    line = work_polyline(points)
    shape = to_shape(geometry, 64)
    if not line.intersects(shape):
        return False
    return bool(line.intersection(shape).length > TOL)


def skeleton_warning_scan(skeleton_file, descriptor, scene, anomalies):
    """Per-skeleton non-target warning entry; only members of this descriptor are considered."""
    if not skeleton_file.exists():
        return {"status": "not_available", "reason": "selected_skeleton.json_absent"}
    merged = {}
    collect_references(read_json(skeleton_file), merged, anomalies)
    if not merged:
        return {"status": "not_available", "reason": "references_absent"}
    facilities = sorted(entity["id"] for entity in scene["entities"] if entity["type"] == "facility")
    targets = {group["group_id"]: group["target_id"] for group in descriptor["task_groups"]}
    members = {agent: group["group_id"] for group in descriptor["task_groups"] for agent in group["members"]}
    if len(facilities) <= 1:
        # Registered rule: a single-facility map has no non-target warning zone to scan.
        return {"status": "not_applicable", "reason": "single_facility_map", "members": len(members)}
    entered, unavailable, degenerate, degenerate_inside, details = 0, 0, 0, 0, []
    for agent in sorted(members):
        info = merged.get(agent)
        points = info.get("work_points_enu_m") if isinstance(info, dict) else None
        if not isinstance(points, list) or not points:
            unavailable += 1
            continue
        target = targets[members[agent]]
        rings = []
        for facility in facilities:
            if facility == target:
                continue
            geometry = warning_geometry(scene, facility)
            if geometry is None:
                anomalies.append({"kind": "warning_layer_missing", "facility_id": facility})
                continue
            rings.append((facility, geometry))
        hit = any(enters_warning(points, geometry) for _, geometry in rings)
        if len(points) == 1:
            # Recorded diagnostic only: the registered test sees length 0 here, never an entry.
            degenerate += 1
            inside = [facility for facility, geometry in rings
                      if Point(points[0][0], points[0][1]).within(to_shape(geometry, 64))]
            if inside:
                degenerate_inside += 1
            anomalies.append({"kind": "single_point_work_set", "skeleton_id": descriptor["skeleton_id"],
                              "agent_id": agent, "inside_non_target_warning": inside})
        entered += int(hit)
        details.append({"agent_id": agent, "group_id": members[agent], "target_id": target,
                        "work_point_count": len(points), "entered": hit})
    if unavailable == len(members):
        return {"status": "not_available", "reason": "work_points_enu_m_absent", "members": len(members)}
    return {"status": "measured", "entered_members": entered, "total_members": len(members),
            "unavailable_members": unavailable, "degenerate_members": degenerate,
            "degenerate_inside_non_target_warning": degenerate_inside, "entered": entered > 0,
            "details": details}


def markdown_table(rows, columns, row_label=""):
    lines = ["| " + " | ".join([str(row_label or "-")] + [str(column) for column in columns]) + " |",
             "|" + "---|" * (len(columns) + 1)]
    for key, cells in rows:
        lines.append("| " + " | ".join([str(key)] + [str(cells.get(column, "")) for column in columns]) + " |")
    return "\n".join(lines)


def rate_cell(hits, total):
    return f"{hits}/{total}" + (f" ({100*hits/total:.2f}%)" if total else "")


CORE_PREFIXES = ("task_v07/", "configs/")


def compare_runtime_sources(attempts):
    """Planner geometry, wiring and configuration must be byte-identical across attempts.

    scripts/ may differ between a batch and its resume: the resume entry point is newer code.
    Those differences are recorded, not fatal, and are reported separately.
    """
    reference = None
    absent = [str(attempt["dir"]) for attempt in attempts if not attempt["registration"].get("runtime_sha256")]
    for attempt in attempts:
        hashes = attempt["registration"].get("runtime_sha256") or {}
        subset = {path: digest for path, digest in hashes.items() if path.startswith(CORE_PREFIXES)}
        if reference is None:
            reference = (attempt["dir"], subset)
            continue
        paths = sorted(set(subset) | set(reference[1]))
        differing = [path for path in paths if subset.get(path) != reference[1].get(path)]
        if differing:
            raise P0ContractError(f"task_v07/ or configs/ sources differ between attempts "
                                  f"({reference[0]} and {attempt['dir']}): {differing}")
    differences = []
    baseline = attempts[0]["registration"].get("runtime_sha256") or {}
    for attempt in attempts[1:]:
        hashes = attempt["registration"].get("runtime_sha256") or {}
        for path in sorted(set(baseline) | set(hashes)):
            if path.startswith(CORE_PREFIXES) or baseline.get(path) == hashes.get(path):
                continue
            differences.append({"path": path, "first_attempt": baseline.get(path),
                                "other_attempt": hashes.get(path), "other": str(attempt["dir"])})
    return differences, absent


def load_attempts(directories, descriptors):
    """Combine yield attempts without silently merging them.

    A skeleton_id may be declared by several attempts (the formal batch declares the whole set,
    the resume declares only what it picked up) but may COMPLETE in at most one: two competing
    results are a contract error. Completed evidence that no attempt declares is also an error.
    The population under test is the union of the declared sets, so a limited run stays valid
    while the final run covers every registered skeleton.
    """
    attempts, result_owner, scope = [], {}, set()
    for directory in directories:
        directory = directory.resolve()
        for required in ("registration.json", "run_result.json"):
            if not (directory / required).exists():
                raise P0ContractError(f"{directory} has no {required}; an attempt that has not finished "
                                      "cannot be summarised")
        yield_registration = read_json(directory / "registration.json")
        run_result = read_json(directory / "run_result.json")
        selected = list(yield_registration["selected_skeletons"])
        completed = [skeleton_id for skeleton_id in selected
                     if (directory / skeleton_id / "planning_result.json").exists()]
        on_disk = sorted(path.name for path in directory.iterdir()
                         if path.is_dir() and (path / "planning_result.json").exists())
        undeclared = sorted(set(on_disk) - set(selected))
        if undeclared:
            raise P0ContractError(f"{directory} holds completed evidence that it does not declare: {undeclared}")
        attempts.append({"dir": directory, "registration": yield_registration, "result": run_result,
                         "selected": selected, "completed": completed})
        for skeleton_id in selected:
            if skeleton_id not in descriptors:
                raise P0ContractError(f"{directory} selects an unregistered skeleton_id: {skeleton_id}")
            scope.add(skeleton_id)
        for skeleton_id in completed:
            if skeleton_id in result_owner:
                raise P0ContractError(f"skeleton_id completed in more than one attempt: {skeleton_id} "
                                      f"({result_owner[skeleton_id]['dir']} and {directory})")
            result_owner[skeleton_id] = attempts[-1]
    if not scope:
        raise P0ContractError("No yield attempt declares any skeleton_id")
    return attempts, result_owner, scope


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptors", type=Path, required=True)
    parser.add_argument("--yield", type=Path, required=True, dest="yield_dirs", action="append",
                        help="Yield attempt directory; repeat the option for a resumed batch")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    descriptors_dir = args.descriptors.resolve()
    anomaly_note = []
    descriptors = {record["skeleton_id"]: record
                   for record in read_json(descriptors_dir / "private_skeleton_descriptors.json")}
    registration = read_json(descriptors_dir / "registration.json")
    candidates = {row["candidate_index"]: row
                  for row in read_json(Path(registration["source_attempt"]) / "candidates.json")}
    registered = sorted(descriptors)
    attempts, result_owner, scope = load_attempts(args.yield_dirs, descriptors)
    runtime_differences, runtime_absent = compare_runtime_sources(attempts)
    population = sorted(scope)
    unfinished = sorted(scope - set(result_owner))
    outside_scope = sorted(set(registered) - scope)
    for attempt in attempts:
        declared, on_disk = attempt["result"].get("completed"), set(attempt["completed"])
        if declared is not None and set(declared) != on_disk:
            anomaly_note.append({"kind": "attempt_completion_disagreement", "attempt": str(attempt["dir"]),
                                 "only_in_run_result": sorted(set(declared) - on_disk),
                                 "only_on_disk": sorted(on_disk - set(declared))})
    maps, rows = {}, []
    for row in registration["selected"]:
        directory = Path(candidates[row["candidate_index"]]["directory"])
        family = read_json(directory / "family_initial.json")
        scene = read_json(directory / "public_scene.json")
        facilities = sum(1 for entity in scene["entities"] if entity["type"] == "facility")
        if facilities != row["facility_count"]:
            anomaly_note.append({"kind": "facility_count_mismatch", "family_id": row["family_id"],
                                 "scene": facilities, "registration": row["facility_count"]})
        if family["layout"] != row["layout"] or family["map_side_m"] != row["map_side_m"]:
            anomaly_note.append({"kind": "map_attribute_mismatch", "family_id": row["family_id"]})
        maps[row["family_id"]] = (family, scene, {entry["obstacle_id"]: entry["placement"]
                                                  for entry in family["obstacle_placements"]},
                                  sorted(entity["id"] for entity in scene["entities"]
                                         if entity["type"] == "facility"))
    proposal_rows, rejected_rows, anomalies = [], [], list(anomaly_note)
    unparseable = 0
    for skeleton_id in population:
        descriptor = descriptors[skeleton_id]
        family, scene, placements, facilities = maps[descriptor["family_id"]]
        owner = result_owner.get(skeleton_id)
        directory = None if owner is None else owner["dir"] / skeleton_id
        result_file = None if directory is None else directory / "planning_result.json"
        result = read_json(result_file) if result_file is not None and result_file.exists() else None
        success = None if result is None else int(result["eligible_combinations"] > 0)
        wall = result.get("planning_wall_s") if result is not None else None
        if wall is None:
            for attempt in attempts:
                recorded = attempt["result"].get("planning_wall_s", {}).get(skeleton_id)
                if recorded is not None:
                    wall = recorded
                    break
        scan = (skeleton_warning_scan(directory / "selected_skeleton.json", descriptor, scene, anomalies)
                if result is not None else {"status": "not_counted"})
        groups = {group["group_id"]: group for group in descriptor["task_groups"]}
        proposals, accepted = 0, 0
        rejected_categories = set()
        journal = None if directory is None else directory / "proposals.jsonl"
        if journal is not None and journal.exists():
            for record in read_lines(journal):
                group = groups.get(record["group_id"])
                if group is None:
                    raise P0ContractError(f"Unknown group_id {record['group_id']} in {skeleton_id}")
                proposals += 1
                accepted += int(record["reason"] is None)
                proposal_rows.append({"skeleton_id": skeleton_id, "intent": descriptor["base_intent"],
                                      "layout": family["layout"], "role": group["role"],
                                      "execution_method": group["execution_method"],
                                      "member_count": len(group["members"]), "bucket": bucket(len(group["members"])),
                                      "accepted": record["reason"] is None})
                if record["reason"] is None:
                    continue
                if "rejection" not in record:
                    unparseable += 1
                    categories = {f"unattributed:{record['reason']}"}
                else:
                    entities = set()
                    collect_entities(record["rejection"], entities)
                    categories = ({classify(entity, group["target_id"], placements, anomalies) for entity in entities}
                                  if entities else {f"unattributed:{record['reason']}"})
                rejected_rows.append({"skeleton_id": skeleton_id, "layout": family["layout"], "intent": descriptor["base_intent"],
                                      "role": group["role"], "execution_method": group["execution_method"],
                                      "reason": record["reason"], "categories": sorted(categories),
                                      "signature": "+".join(sorted(categories))})
                rejected_categories.update(categories)
        rows.append({"skeleton_id": skeleton_id, "descriptor": descriptor, "family_id": descriptor["family_id"],
                     "intent": descriptor["base_intent"], "approach_mode": descriptor["common_draw"]["approach_mode"],
                     "layout": family["layout"], "facility_count": len(facilities), "map_side_m": family["map_side_m"],
                     "success": success, "planning_wall_s": wall, "proposals": proposals, "accepted": accepted,
                     "rejection_reasons": {} if result is None else result.get("rejection_reasons", {}),
                     "combination_reasons": {} if result is None else result.get("combination_rejection_reasons", {}),
                     "rejected_categories": rejected_categories, "warning_scan": scan})
    measured = [row for row in rows if row["success"] is not None]
    completed_ids = {row["skeleton_id"] for row in measured}
    unfinished_rows = [row for row in rows if row["success"] is None]
    rate = unparseable / len(rejected_rows) if rejected_rows else 0.0
    if rate > 0.05:
        raise P0ContractError(f"Rejected proposals without a rejection subtree: {unparseable}/{len(rejected_rows)}")

    def unfinished_breakdown(source, row_key):
        table = {}
        for row in source:
            table[row_key(row)] = table.get(row_key(row), 0) + 1
        return table

    unfinished_by_intent = unfinished_breakdown(unfinished_rows, lambda row: row["intent"])
    unfinished_by_layout = unfinished_breakdown(unfinished_rows, lambda row: row["layout"])
    joint_labels = {intent: {layer: 0 for layer in LAYERS} for intent in INTENTS}
    for row in unfinished_rows:
        joint_labels[row["intent"]][row["layout"]] += 1
    t6b = [{"skeleton_id": row["skeleton_id"], "intent": row["intent"], "layout": row["layout"],
            "approach_mode": row["approach_mode"], "facility_count": row["facility_count"],
            "group_count": len(row["descriptor"]["task_groups"]),
            "member_counts": [len(group["members"]) for group in row["descriptor"]["task_groups"]],
            "roles": [group["role"] for group in row["descriptor"]["task_groups"]],
            "planning_wall_s": row["planning_wall_s"], "completed": row["skeleton_id"] in completed_ids}
           for row in rows]

    # Appendix: the five intents of one (family, slot) share a single common draw, so a draw
    # is the independent unit. This never replaces T1-T6; it is reported alongside them.
    draws = {}
    for row in rows:
        draws.setdefault((row["family_id"], row["descriptor"]["common_draw"]["slot"]), []).append(row)
    draw_records = []
    for (family_id, slot), group_members in sorted(draws.items()):
        group_members.sort(key=lambda item: INTENTS.index(item["intent"]))
        head = group_members[0]
        results = {item["intent"]: (None if item["success"] is None else bool(item["success"]))
                   for item in group_members}
        in_scope = set(results) == set(INTENTS)
        if not in_scope:
            classification = "范围不全"
        elif any(value is None for value in results.values()):
            classification = "未完成"
        elif all(results.values()):
            classification = "全成功"
        elif not any(results.values()):
            classification = "全失败"
        else:
            classification = "部分成功"
        draw_records.append({"family_id": family_id, "slot": slot, "layout": head["layout"],
                             "facility_count": head["facility_count"], "approach_mode": head["approach_mode"],
                             "group_count": len(head["descriptor"]["task_groups"]),
                             "member_counts": [len(g["members"]) for g in head["descriptor"]["task_groups"]],
                             "results": results, "classification": classification,
                             "skeletons": [item["skeleton_id"] for item in group_members]})
    failing_ids = [item["skeleton_id"] for record in draw_records
                   if record["classification"] in ("部分成功", "全失败")
                   for item in rows if item["skeleton_id"] in record["skeletons"] and item["success"] == 0]
    terminal_reasons = {}
    for skeleton_id in failing_ids:
        attempt = result_owner.get(skeleton_id)
        pool_file = None if attempt is None else attempt["dir"] / skeleton_id / "candidate_pool.json"
        if pool_file is not None and pool_file.exists():
            terminal = read_json(pool_file).get("termination") or {}
            terminal_reasons[skeleton_id] = terminal.get("reason")
    for record in draw_records:
        if record["classification"] not in ("部分成功", "全失败"):
            continue
        record["failing"] = [{"intent": item["intent"], "skeleton_id": item["skeleton_id"],
                              "terminal_reason": terminal_reasons.get(item["skeleton_id"]),
                              "group_rejection_reasons": item["rejection_reasons"],
                              "combination_rejection_reasons": item["combination_reasons"],
                              "categories": sorted(item["rejected_categories"]),
                              "signature": "+".join(sorted(item["rejected_categories"]))}
                             for item in rows if item["skeleton_id"] in record["skeletons"]
                             and item["success"] == 0]
    draw_classes = ("全成功", "全失败", "部分成功", "未完成", "范围不全")

    def draw_summary(field):
        table = {}
        for record in draw_records:
            table.setdefault(record[field], Counter())[record["classification"]] += 1
        return {key: {name: value.get(name, 0) for name in draw_classes} for key, value in sorted(table.items())}

    draw_yield = {}
    for layer in LAYERS:
        subset = [record for record in draw_records if record["layout"] == layer]
        if not subset:
            continue
        full = sum(record["classification"] == "全成功" for record in subset)
        complete = sum(record["classification"] in ("全成功", "全失败", "部分成功") for record in subset)
        draw_yield[layer] = {"full_success_draws": full, "draws": len(subset), "completed_draws": complete,
                             "rate_of_all_draws": full / len(subset),
                             "rate_of_completed_draws": (full / complete) if complete else None}
    total_full = sum(record["classification"] == "全成功" for record in draw_records)
    total_complete = sum(record["classification"] in ("全成功", "全失败", "部分成功") for record in draw_records)
    draw_yield["all"] = {"full_success_draws": total_full, "draws": len(draw_records),
                         "completed_draws": total_complete,
                         "rate_of_all_draws": total_full / len(draw_records) if draw_records else None,
                         "rate_of_completed_draws": (total_full / total_complete) if total_complete else None}

    def success_table(row_key, keys, rows_source):
        """[successes, denominator, unfinished]; the denominator keeps every registered skeleton."""
        grid = {}
        for row in rows_source:
            cell = grid.setdefault((row_key(row), keys(row)), [0, 0, 0])
            cell[1] += 1
            if row["success"] is None:
                cell[2] += 1
            else:
                cell[0] += row["success"]
        return grid

    def render_success(grid, row_labels, col_labels, ratio=False):
        columns = list(col_labels) + ["未完成"]
        body, ratios = {}, {}
        for row_label in row_labels:
            body[row_label] = {column: rate_cell(*grid.get((row_label, column), [0, 0, 0])[:2])
                               for column in col_labels}
            body[row_label]["未完成"] = sum(grid.get((row_label, column), [0, 0, 0])[2] for column in col_labels)
        for column in col_labels:
            rates = [grid[(row_label, column)][0] / grid[(row_label, column)][1]
                     for row_label in row_labels if grid.get((row_label, column), [0, 0, 0])[1]]
            if not rates:
                ratios[column] = "n/a"
            else:
                ratios[column] = "inf" if min(rates) == 0 else f"{max(rates)/min(rates):.4f}"
        if ratio:
            body["各布局内五意图成功率最大值/最小值之比"] = ratios
        return body, columns

    t1, t1_columns = render_success(
        success_table(lambda row: row["intent"], lambda row: row["layout"], rows), INTENTS, LAYERS, ratio=True)
    modes = sorted({row["approach_mode"] for row in rows})
    t2a, t2a_columns = render_success(
        success_table(lambda row: row["intent"], lambda row: row["approach_mode"], rows), INTENTS, modes)
    counts = sorted({row["facility_count"] for row in rows})
    t2b, t2b_columns = render_success(
        success_table(lambda row: row["intent"], lambda row: row["facility_count"], rows), INTENTS, counts)
    role_key = lambda row: f"{row['role']}/{row['execution_method']}"
    roles = sorted({role_key(row) for row in proposal_rows})
    t3 = {}
    for label, columns, field in (("by_layout", LAYERS, "layout"), ("by_member_count", BUCKET_ORDER, "bucket")):
        table = {}
        for role in roles:
            cells = {}
            for column in columns:
                subset = [row for row in proposal_rows if role_key(row) == role and row[field] == column]
                cells[column] = rate_cell(sum(row["accepted"] for row in subset), len(subset))
            table[role] = cells
        t3[label] = table
    categories = category_order({name for row in rejected_rows for name in row["categories"]})
    t4 = {}
    for label, field, order in (("by_role", None, roles), ("by_layout", "layout", LAYERS)):
        table = {}
        for row_label in order:
            subset = [row for row in rejected_rows if (role_key(row) if field is None else row[field]) == row_label]
            table[row_label] = {column: sum(column in row["categories"] for row in subset) for column in categories}
            table[row_label]["total"] = len(subset)
        t4[label] = table
    t4["signatures_top15"] = [{"signature": signature, "count": count}
                              for signature, count in Counter(row["signature"] for row in rejected_rows).most_common(15)]
    t5 = {}
    for intent in INTENTS:
        t5[intent] = {}
        for layer in LAYERS:
            subset = [row for row in rows if row["intent"] == intent and row["layout"] == layer]
            multi = [row for row in subset if row["facility_count"] > 1]
            if not multi:
                t5[intent][layer] = "not_applicable" if subset else "n/a"
                continue
            applicable = [row for row in multi if row["warning_scan"]["status"] == "measured"]
            absent = [row for row in multi if row["warning_scan"].get("reason") == "selected_skeleton.json_absent"]
            missing = [row for row in multi if row["warning_scan"]["status"] == "not_available"
                       and row["warning_scan"].get("reason") != "selected_skeleton.json_absent"]
            cell = f"{sum(row['warning_scan']['entered'] for row in applicable)}/{len(applicable)}"
            if absent:
                cell += f" [not_counted {len(absent)}]"
            if missing:
                cell += f" [not_available {len(missing)}]"
            t5[intent][layer] = cell
        t5[intent]["未完成"] = sum(1 for row in unfinished_rows if row["intent"] == intent
                                   and row["facility_count"] > 1)
    t6 = {intent: distribution([row["planning_wall_s"] for row in measured if row["intent"] == intent])
          for intent in INTENTS}
    t6["all"] = distribution([row["planning_wall_s"] for row in measured])
    t6 = {intent: {**value, "未完成": unfinished_by_intent.get(intent, 0) if intent != "all" else len(unfinished_rows)}
          for intent, value in t6.items()}
    t6_all = {intent: distribution([row["planning_wall_s"] for row in rows if row["intent"] == intent])
              for intent in INTENTS}
    t6_all["all"] = distribution([row["planning_wall_s"] for row in rows])
    summary = {"schema": "traj2language.s15_stage2_yield_summary/1",
               "generated_utc": datetime.now(timezone.utc).isoformat(),
               "provenance": {"descriptors": str(descriptors_dir),
                              "baseline_sha256": registration.get("baseline_sha256"),
                              "private_skeleton_descriptors_sha256": sha(descriptors_dir / "private_skeleton_descriptors.json"),
                              "script_sha256": sha(Path(__file__)),
                              "attempts": [{"attempt": str(attempt["dir"]),
                                            "run_result_sha256": sha(attempt["dir"] / "run_result.json"),
                                            "registration_sha256": sha(attempt["dir"] / "registration.json"),
                                            "selected_count": len(attempt["selected"]),
                                            "completed_count": len(attempt["completed"]),
                                            "skeletons_file": attempt["registration"].get("skeletons_file")}
                                           for attempt in attempts]},
               "yield": {"statuses": [attempt["result"]["status"] for attempt in attempts],
                         "planned_count": sum(len(attempt["selected"]) for attempt in attempts),
                         "completed_count": len(result_owner), "unfinished_count": len(unfinished),
                         "total_wall_s": sum(attempt["result"]["wall_s"] for attempt in attempts),
                         "wall_limit_s": [attempt["result"].get("wall_limit_s") for attempt in attempts],
                         "runtime_sha256_stable": all(attempt["result"].get("runtime_sha256_stable")
                                                      for attempt in attempts)},
               "counts": {"skeletons_registered": len(registered),
                          "skeletons_in_scope": len(population),
                          "skeletons_registered_outside_scope": len(outside_scope),
                          "skeletons_with_planning_result": len(measured),
                          "skeletons_unfinished": len(unfinished),
                          "skeletons_successful": sum(row["success"] for row in measured),
                          "skeletons_with_selected_skeleton": sum(
                              row["warning_scan"]["status"] in ("measured", "not_applicable") for row in rows),
                          "warnings_not_applicable": sum(row["facility_count"] == 1 for row in rows),
                          "group_proposals": len(proposal_rows),
                          "group_proposals_accepted": sum(row["accepted"] for row in proposal_rows),
                          "rejected_proposals": len(rejected_rows), "unattributed": sum(
                              row["signature"].startswith("unattributed:") for row in rejected_rows),
                          "warning_members_scanned": sum(row["warning_scan"].get("total_members", 0) for row in rows),
                          "warning_members_unavailable": sum(row["warning_scan"].get("unavailable_members", 0) for row in rows),
                          "members_single_point_work_set": sum(row["warning_scan"].get("degenerate_members", 0) for row in rows),
                          "members_single_point_inside_non_target_warning": sum(
                              row["warning_scan"].get("degenerate_inside_non_target_warning", 0) for row in rows)},
               "scripts_runtime_differences": runtime_differences,
               "runtime_sha256_absent_attempts": runtime_absent,
               "scripts_runtime_note": "task_v07/ and configs/ entries must match across attempts and are "
                                       "enforced; scripts/ entries may differ because the resume entry point "
                                       "is newer code, so they are listed here",
               "unfinished": {"count": len(unfinished), "skeletons": unfinished,
                              "by_intent": unfinished_by_intent, "by_layout": unfinished_by_layout,
                              "by_intent_layout": joint_labels,
                              "note": "unfinished skeletons stay in every skeleton-level denominator and are "
                                      "listed in the 未完成 column; they contribute no group proposals"},
               "scope": {"attempts_declare": len(population), "registered": len(registered),
                         "registered_outside_scope": outside_scope,
                         "note": "tables cover the union of the attempts' declared skeleton_id sets; "
                                 "the final batch declares all registered skeletons, so this list is then empty"},
               "unparseable_rejections": {"count": unparseable, "rate": rate},
               "proposal_field_note": "one proposals.jsonl line is one group proposal; accepted means record['reason'] is None",
               "anomalies": anomalies,
               "tables": {"T1": t1, "T2_approach_mode": t2a, "T2_facility_count": t2b, "T3": t3, "T4": t4,
                          "T5": t5, "T6": t6, "T6b_skeleton_composition": t6b},
               "draw_appendix": {
                   "note": "one row per common draw (family x slot); the five intents of a draw share one "
                           "common_draw, so a draw is the independent unit. Appendix only: T1-T6 are unchanged. "
                           "未完成 is a fourth class for draws whose five intents are not all measured; such draws "
                           "stay in every denominator.",
                   "draws": draw_records, "by_layout": draw_summary("layout"),
                   "by_approach_mode": draw_summary("approach_mode"),
                   "yield_by_layout": draw_yield},
               "T6_population": "T6 distribution covers skeletons that have a planning_result.json; "
                                "t6_all_registered additionally covers unfinished skeletons' recorded wall clock",
               "t6_all_registered": t6_all,
               "skeletons": [{"skeleton_id": row["skeleton_id"], "family_id": row["family_id"], "intent": row["intent"],
                              "approach_mode": row["approach_mode"], "layout": row["layout"],
                              "facility_count": row["facility_count"], "map_side_m": row["map_side_m"],
                              "success": row["success"], "completed": row["skeleton_id"] in completed_ids,
                              "planning_wall_s": row["planning_wall_s"],
                              "attempt": None if result_owner.get(row["skeleton_id"]) is None
                                         else str(result_owner[row["skeleton_id"]]["dir"]),
                              "group_count": len(row["descriptor"]["task_groups"]),
                              "member_counts": [len(group["members"]) for group in row["descriptor"]["task_groups"]],
                              "group_proposals": row["proposals"], "group_proposals_accepted": row["accepted"],
                              "warning_scan_status": row["warning_scan"]["status"],
                              "warning_scan_reason": row["warning_scan"].get("reason"),
                              "warning_entered": row["warning_scan"].get("entered"),
                              "warning_entered_members": row["warning_scan"].get("entered_members"),
                              "warning_total_members": row["warning_scan"].get("total_members"),
                              "warning_unavailable_members": row["warning_scan"].get("unavailable_members"),
                              "warning_single_point_members": row["warning_scan"].get("degenerate_members")}
                             for row in rows]}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    save_json(args.out_dir / "s15_yield_summary.json", summary)
    lines = ["# S1.5 阶段 2 纯规划产额统计表", "",
             f"- 描述目录：`{descriptors_dir}`",
             f"- 规划目录（{len(attempts)} 个 attempt，每个 skeleton_id 只来自其中一个）：",
             *[f"  - `{attempt['dir']}`：状态 `{attempt['result']['status']}`，选中 {len(attempt['selected'])}，"
               f"落盘完成 {len(attempt['completed'])}，墙钟 {attempt['result']['wall_s']:.1f} s"
               for attempt in attempts],
             f"- 注册骨架 {len(registered)} 个；本次统计范围（各 attempt 声明并集）{len(population)} 个，"
             f"其中有 `planning_result.json` 的 {len(measured)} 个"
             f"（成功 {summary['counts']['skeletons_successful']}）；未完成 **{len(unfinished)}** 个"
             + (f"；注册但不在本次范围内的 {len(outside_scope)} 个" if outside_scope else ""),
             f"- 组提案 {len(proposal_rows)} 条，接受 {summary['counts']['group_proposals_accepted']} 条；"
             f"被拒 {len(rejected_rows)} 条，无法按 4.3 解析 {unparseable} 条（{100*rate:.4f}%）",
             f"- 1 设施地图（T5 记 `not_applicable`）：{summary['counts']['warnings_not_applicable']} 个骨架",
             "- 骨架级表格（T1、T2a、T2b、T5、T6）的分母一律包含未完成骨架，并在末列单列 `未完成` 数量；"
             "T3、T4 的分母是组提案，未完成骨架不产生提案，故不在其分母内。", ""]
    lines += ["## 未完成骨架计数：意图 × 布局", "",
              markdown_table([(intent, joint_labels[intent]) for intent in INTENTS], LAYERS, row_label="intent"), ""]
    lines += ["## T1 骨架成功率：意图 × 布局", "",
              markdown_table(list(t1.items()), t1_columns, row_label="intent"), ""]
    lines += ["## T2a 骨架成功率：意图 × 接近方式", "",
              markdown_table(list(t2a.items()), t2a_columns, row_label="intent"), ""]
    lines += ["## T2b 骨架成功率：意图 × 设施数", "",
              markdown_table(list(t2b.items()), t2b_columns, row_label="intent"), ""]
    lines += ["## T3 组提案接受率", "",
              f"分母为组提案数；{len(unfinished)} 个未完成骨架没有 `proposals.jsonl`，不产生提案。", "",
              "### T3a：role/execution_method × 布局", "",
              markdown_table(list(t3["by_layout"].items()), LAYERS, row_label="role/execution_method"), "",
              "### T3b：role/execution_method × 成员数分桶", "",
              markdown_table(list(t3["by_member_count"].items()), BUCKET_ORDER, row_label="role/execution_method"), ""]
    lines += ["## T4 被拒提案归因（多标签计数）", "",
              f"分母为被拒提案数；{len(unfinished)} 个未完成骨架不产生提案。", "",
              "### T4a：role/execution_method × 类别", "",
              markdown_table(list(t4["by_role"].items()), categories + ["total"], row_label="role/execution_method"), "",
              "### T4b：layout × 类别", "",
              markdown_table(list(t4["by_layout"].items()), categories + ["total"], row_label="layout"), "",
              "### T4c：互斥签名前 15 名（类别集合排序后以 + 连接）", "", markdown_table(
                  [(entry["signature"], {"count": entry["count"]}) for entry in t4["signatures_top15"]],
                  ["count"], row_label="signature"), ""]
    lines += ["## T5 作业段进入非目标预警区：意图 × 布局（仅多设施布局）", "",
              markdown_table(list(t5.items()), list(LAYERS) + ["未完成"], row_label="intent"), "",
              "分母为有 `selected_skeleton.json` 且可测的骨架数（第 4.4 条只统计有该文件的骨架）；`not_applicable` 为单设施地图；"
              "`[not_counted n]` 为无 `selected_skeleton.json` 因而按第 4.4 条不统计的骨架数；"
              "`[not_available n]` 为找不到 `references` 或 `work_points_enu_m` 的骨架数；"
              "`未完成` 列为该意图下未完成的多设施骨架数。", ""]
    lines += ["## T6 每骨架规划墙钟（s）：按意图", "",
              markdown_table([(intent, t6[intent]) for intent in list(INTENTS) + ["all"]],
                             ["count", "min", "p50", "p90", "max", "未完成"], row_label="intent"), "",
              "分布只统计有 `planning_result.json` 的骨架；未完成骨架的墙钟是中止时的快照，不进入分布，"
              "其数量单列在 `未完成` 列，并在 summary JSON 的 `t6_all_registered` 中另附。", ""]
    lines += ["## T6b 每骨架规划耗时与组构成（意图 / 组数 / 各组成员数）", "",
              markdown_table([(entry["skeleton_id"],
                               {"intent": entry["intent"], "layout": entry["layout"],
                                "approach_mode": entry["approach_mode"],
                                "facility_count": entry["facility_count"], "group_count": entry["group_count"],
                                "member_counts": "/".join(str(v) for v in entry["member_counts"]),
                                "roles": "/".join(entry["roles"]),
                                "planning_wall_s": entry["planning_wall_s"],
                                "completed": entry["completed"]})
                              for entry in t6b],
                             ["intent", "layout", "approach_mode", "facility_count", "group_count",
                              "member_counts", "roles", "planning_wall_s", "completed"],
                             row_label="skeleton_id"), ""]
    lines += ["## 附录 A：按公共抽签（family × slot）聚合", "",
              "同一 `(family, slot)` 的 5 个意图共享同一次公共抽签，因此抽签才是独立单元；本附录不替换 T1–T6。"
              "成=成功，败=拒绝，待=在范围内但未测到，-=不在本次范围内。"
              "`未完成`（5 个意图都在范围内但未全部测到）与 `范围不全`（少于 5 个意图在范围内，只出现在限定范围的运行中）"
              "是第四、第五类，仍留在各分母内。", "",
              "### A1 每个抽签一行", "",
              markdown_table([(f"{record['family_id'][-12:]}#slot{record['slot']}",
                               {"layout": record["layout"], "facility_count": record["facility_count"],
                                "approach_mode": record["approach_mode"], "group_count": record["group_count"],
                                "member_counts": "/".join(str(v) for v in record["member_counts"]),
                                **{intent: ("成" if record["results"].get(intent) else
                                            "待" if intent in record["results"] else "-")
                                   for intent in INTENTS},
                                "结果": record["classification"]})
                              for record in draw_records],
                             ["layout", "facility_count", "approach_mode", "group_count", "member_counts",
                              *INTENTS, "结果"], row_label="family#slot"), "",
              "### A2 按 layout / approach_mode 的三类抽签数量", "",
              markdown_table([(key, value) for key, value in summary["draw_appendix"]["by_layout"].items()],
                             list(draw_classes), row_label="layout"), "",
              markdown_table([(key, value) for key, value in summary["draw_appendix"]["by_approach_mode"].items()],
                             list(draw_classes), row_label="approach_mode"), "",
              "### A3 抽签口径产量（全成功抽签数 / 抽签总数）", "",
              markdown_table([(key, {"全成功抽签": value["full_success_draws"], "抽签总数": value["draws"],
                                     "其中已测完": value["completed_draws"],
                                     "全成功/全部抽签": f"{value['rate_of_all_draws']:.4f}",
                                     "全成功/已测完抽签": ("n/a" if value["rate_of_completed_draws"] is None
                                                          else f"{value['rate_of_completed_draws']:.4f}")})
                              for key, value in summary["draw_appendix"]["yield_by_layout"].items()],
                             ["全成功抽签", "抽签总数", "其中已测完", "全成功/全部抽签", "全成功/已测完抽签"],
                             row_label="layout"), ""]
    for label, key in (("A4 部分成功抽签中失败的意图", "部分成功"), ("A5 全失败抽签", "全失败")):
        rows_out = []
        for record in draw_records:
            if record["classification"] != key:
                continue
            rows_out.append((f"{record['family_id'][-12:]}#slot{record['slot']}",
                             {"layout": record["layout"], "approach_mode": record["approach_mode"],
                              "groups": record["group_count"],
                              "members": "/".join(str(v) for v in record["member_counts"]),
                              "失败意图": ", ".join(entry["intent"] for entry in record.get("failing", [])),
                              "终止拒绝原因": "; ".join(sorted({str(entry["terminal_reason"])
                                                                 for entry in record.get("failing", [])})),
                              "组层拒绝原因": "; ".join(f"{k}={v}" for entry in record.get("failing", [])
                                                        for k, v in sorted(entry["group_rejection_reasons"].items())),
                              "组合层拒绝原因": "; ".join(f"{k}={v}" for entry in record.get("failing", [])
                                                          for k, v in sorted(entry["combination_rejection_reasons"].items())),
                              "4.3 归因签名": "; ".join(sorted({entry["signature"]
                                                                for entry in record.get("failing", [])}))}))
        lines += [f"### {label}" + ("（用户口径只要求部分成功抽签；全失败抽签仅 1 个，一并列出以免不可读）" if key == "全失败" else ""),
                  "", markdown_table(rows_out, ["layout", "approach_mode", "groups", "members", "失败意图",
                                                "终止拒绝原因", "组层拒绝原因", "组合层拒绝原因", "4.3 归因签名"],
                                     row_label="family#slot"), ""]
    if anomalies:
        kinds = Counter(item["kind"] for item in anomalies)
        lines += ["## 异常记录（逐条见 summary JSON 的 anomalies）", "",
                  markdown_table([(kind, {"count": count}) for kind, count in sorted(kinds.items())],
                                 ["count"], row_label="kind"), "",
                  f"- 作业段扫描覆盖成员 {summary['counts']['warning_members_scanned']} 名，"
                  f"其中 work_points_enu_m 缺失 {summary['counts']['warning_members_unavailable']} 名；"
                  f"单点作业段 {summary['counts']['members_single_point_work_set']} 名，"
                  f"其中该点落在非目标预警区内 {summary['counts']['members_single_point_inside_non_target_warning']} 名"
                  "（单点集合按登记的交集长度 > 1e-6 m 口径判为未进入，仅记录此诊断）。", ""]
    (args.out_dir / "s15_yield_tables.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print({"skeletons": len(rows), "completed": len(measured), "unfinished": len(unfinished),
           "proposals": len(proposal_rows), "rejected": len(rejected_rows), "unparseable": unparseable,
           "anomalies": len(anomalies), "success": summary["counts"]["skeletons_successful"]}, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
