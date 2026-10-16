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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptors", type=Path, required=True)
    parser.add_argument("--yield", type=Path, required=True, dest="yield_dir")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    descriptors_dir, yield_dir = args.descriptors.resolve(), args.yield_dir.resolve()
    anomaly_note = []
    descriptors = {record["skeleton_id"]: record
                   for record in read_json(descriptors_dir / "private_skeleton_descriptors.json")}
    registration = read_json(descriptors_dir / "registration.json")
    candidates = {row["candidate_index"]: row
                  for row in read_json(Path(registration["source_attempt"]) / "candidates.json")}
    run_result = read_json(yield_dir / "run_result.json")
    yield_registration = read_json(yield_dir / "registration.json")
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
    selected = yield_registration["selected_skeletons"]
    proposal_rows, rejected_rows, anomalies = [], [], list(anomaly_note)
    unparseable = 0
    for skeleton_id in selected:
        descriptor = descriptors[skeleton_id]
        family, scene, placements, facilities = maps[descriptor["family_id"]]
        directory = yield_dir / skeleton_id
        result_file = directory / "planning_result.json"
        result = read_json(result_file) if result_file.exists() else None
        success = None if result is None else int(result["eligible_combinations"] > 0)
        wall = None if result is None else result.get("planning_wall_s")
        if wall is None:
            wall = run_result.get("planning_wall_s", {}).get(skeleton_id)
        scan = (skeleton_warning_scan(directory / "selected_skeleton.json", descriptor, scene, anomalies)
                if result is not None else {"status": "not_counted"})
        groups = {group["group_id"]: group for group in descriptor["task_groups"]}
        proposals, accepted = 0, 0
        journal = directory / "proposals.jsonl"
        if journal.exists():
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
        rows.append({"skeleton_id": skeleton_id, "descriptor": descriptor, "family_id": descriptor["family_id"],
                     "intent": descriptor["base_intent"], "approach_mode": descriptor["common_draw"]["approach_mode"],
                     "layout": family["layout"], "facility_count": len(facilities), "map_side_m": family["map_side_m"],
                     "success": success, "planning_wall_s": wall, "proposals": proposals, "accepted": accepted,
                     "warning_scan": scan})
    measured = [row for row in rows if row["success"] is not None]
    rate = unparseable / len(rejected_rows) if rejected_rows else 0.0
    if rate > 0.05:
        raise P0ContractError(f"Rejected proposals without a rejection subtree: {unparseable}/{len(rejected_rows)}")

    def success_table(row_key, keys, rows_source):
        grid = {}
        for row in rows_source:
            cell = grid.setdefault((row_key(row), keys(row)), [0, 0])
            cell[1] += 1
            cell[0] += row["success"]
        return grid

    def render_success(grid, row_labels, col_labels, ratio=False):
        body, ratios = {}, {}
        for row_label in row_labels:
            body[row_label] = {column: rate_cell(*grid.get((row_label, column), [0, 0])) for column in col_labels}
        for column in col_labels:
            rates = [grid[(row_label, column)][0] / grid[(row_label, column)][1]
                     for row_label in row_labels if grid.get((row_label, column), [0, 0])[1]]
            if not rates:
                ratios[column] = "n/a"
            else:
                ratios[column] = "inf" if min(rates) == 0 else f"{max(rates)/min(rates):.4f}"
        if ratio:
            body["各布局内五意图成功率最大值/最小值之比"] = ratios
        return body

    t1 = render_success(
        success_table(lambda row: row["intent"], lambda row: row["layout"], measured), INTENTS, LAYERS, ratio=True)
    modes = sorted({row["approach_mode"] for row in measured})
    t2a = render_success(success_table(lambda row: row["intent"], lambda row: row["approach_mode"], measured), INTENTS, modes)
    counts = sorted({row["facility_count"] for row in measured})
    t2b = render_success(success_table(lambda row: row["intent"], lambda row: row["facility_count"], measured), INTENTS, counts)
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
            subset = [row for row in measured if row["intent"] == intent and row["layout"] == layer]
            if not subset:
                t5[intent][layer] = "n/a"
                continue
            multi = [row for row in subset if row["facility_count"] > 1]
            if not multi:
                t5[intent][layer] = "not_applicable"
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
    t6 = {intent: distribution([row["planning_wall_s"] for row in measured if row["intent"] == intent])
          for intent in INTENTS}
    t6["all"] = distribution([row["planning_wall_s"] for row in measured])
    # Section 5 keeps the tables on the completed part; the wider population stays in the evidence.
    t6_all = {intent: distribution([row["planning_wall_s"] for row in rows if row["intent"] == intent])
              for intent in INTENTS}
    t6_all["all"] = distribution([row["planning_wall_s"] for row in rows])
    summary = {"schema": "traj2language.s15_stage2_yield_summary/1",
               "generated_utc": datetime.now(timezone.utc).isoformat(),
               "provenance": {"descriptors": str(descriptors_dir), "yield": str(yield_dir),
                              "baseline_sha256": registration.get("baseline_sha256"),
                              "private_skeleton_descriptors_sha256": sha(descriptors_dir / "private_skeleton_descriptors.json"),
                              "yield_run_result_sha256": sha(yield_dir / "run_result.json"),
                              "yield_registration_sha256": sha(yield_dir / "registration.json"),
                              "script_sha256": sha(Path(__file__))},
               "yield": {"status": run_result["status"], "planned_count": run_result["planned_count"],
                         "completed_count": run_result["completed_count"], "unfinished": run_result["unfinished"],
                         "wall_s": run_result["wall_s"], "limit": run_result.get("limit"),
                         "wall_limit_s": run_result.get("wall_limit_s"),
                         "runtime_sha256_stable": run_result.get("runtime_sha256_stable")},
               "counts": {"skeletons_registered": len(selected), "skeletons_with_planning_result": len(measured),
                          "skeletons_without_planning_result": len(rows) - len(measured),
                          "skeletons_successful": sum(row["success"] for row in measured),
                          "skeletons_with_selected_skeleton": sum(row["warning_scan"]["status"] == "measured"
                                                                  for row in rows),
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
               "unparseable_rejections": {"count": unparseable, "rate": rate},
               "proposal_field_note": "one proposals.jsonl line is one group proposal; accepted means record['reason'] is None",
               "anomalies": anomalies,
               "tables": {"T1": t1, "T2_approach_mode": t2a, "T2_facility_count": t2b, "T3": t3, "T4": t4,
                          "T5": t5, "T6": t6},
               "T6_population": "T6 counts skeletons that have a planning_result.json (section 5: completed part); "
                                "t6_all_registered additionally covers unfinished skeletons' recorded wall clock",
               "t6_all_registered": t6_all,
               "skeletons": [{"skeleton_id": row["skeleton_id"], "family_id": row["family_id"], "intent": row["intent"],
                              "approach_mode": row["approach_mode"], "layout": row["layout"],
                              "facility_count": row["facility_count"], "map_side_m": row["map_side_m"],
                              "success": row["success"], "planning_wall_s": row["planning_wall_s"],
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
             f"- 描述目录：`{descriptors_dir}`", f"- 规划目录：`{yield_dir}`",
             f"- 运行状态：`{run_result['status']}`；完成 {run_result['completed_count']}/"
             f"{run_result['planned_count']}；总墙钟 {run_result['wall_s']:.1f} s"
             + (f"；未完成 {len(run_result['unfinished'])}" if run_result["unfinished"] else ""),
             f"- 有 `planning_result.json` 的骨架：{len(measured)}/{len(rows)}；"
             f"其中成功 {summary['counts']['skeletons_successful']}",
             f"- 组提案 {len(proposal_rows)} 条，接受 {summary['counts']['group_proposals_accepted']} 条；"
             f"被拒 {len(rejected_rows)} 条，无法按 4.3 解析 {unparseable} 条（{100*rate:.4f}%）",
             f"- 1 设施地图（T5 记 `not_applicable`）：{summary['counts']['warnings_not_applicable']} 个骨架", ""]
    lines += ["## T1 骨架成功率：意图 × 布局", "", markdown_table(list(t1.items()), LAYERS, row_label="intent"), ""]
    lines += ["## T2a 骨架成功率：意图 × 接近方式", "", markdown_table(list(t2a.items()), modes, row_label="intent"), ""]
    lines += ["## T2b 骨架成功率：意图 × 设施数", "", markdown_table(list(t2b.items()), counts, row_label="intent"), ""]
    lines += ["## T3 组提案接受率", "", "### T3a：role/execution_method × 布局", "",
              markdown_table(list(t3["by_layout"].items()), LAYERS, row_label="role/execution_method"), "",
              "### T3b：role/execution_method × 成员数分桶", "",
              markdown_table(list(t3["by_member_count"].items()), BUCKET_ORDER, row_label="role/execution_method"), ""]
    lines += ["## T4 被拒提案归因（多标签计数）", "", "### T4a：role/execution_method × 类别", "",
              markdown_table(list(t4["by_role"].items()), categories + ["total"], row_label="role/execution_method"), "",
              "### T4b：layout × 类别", "",
              markdown_table(list(t4["by_layout"].items()), categories + ["total"], row_label="layout"), "",
              "### T4c：互斥签名前 15 名（类别集合排序后以 + 连接）", "", markdown_table(
                  [(entry["signature"], {"count": entry["count"]}) for entry in t4["signatures_top15"]],
                  ["count"], row_label="signature"), ""]
    lines += ["## T5 作业段进入非目标预警区：意图 × 布局（仅多设施布局）", "",
              markdown_table(list(t5.items()), LAYERS, row_label="intent"), "",
              "分母为有 `selected_skeleton.json` 且可测的骨架数；`not_applicable` 为单设施地图；"
              "`[not_counted n]` 为无 `selected_skeleton.json` 因而按第 4.4 条不统计的骨架数；"
              "`[not_available n]` 为找不到 `references` 或 `work_points_enu_m` 的骨架数。", ""]
    lines += ["## T6 每骨架规划墙钟（s）：按意图", "",
              markdown_table([(intent, t6[intent]) for intent in list(INTENTS) + ["all"]],
                             ["count", "min", "p50", "p90", "max"], row_label="intent"), ""]
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
    print({"skeletons": len(rows), "measured": len(measured), "proposals": len(proposal_rows),
           "rejected": len(rejected_rows), "unparseable": unparseable, "anomalies": len(anomalies),
           "success": summary["counts"]["skeletons_successful"]}, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
