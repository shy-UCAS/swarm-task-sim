"""Read-only, exclusive-output review of the v0.5 r1.1 planning dry run."""

import argparse
import bisect
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_sim.generation import canonical_hash, file_hash
from swarm_sim.generation_v2 import normalize_profile

PROFILE = ROOT / "generation_profiles/dual_intent_v05b.json"
GENERATED = ROOT / "tmp_v05/dr_v05b/generated_130"
OUTPUT = ROOT / "tmp_v05/dr_v05b/review.json"
REPORT = ROOT / "docs/v0.5b_dr_review.md"
OLD_PROFILE = ROOT / "generation_profiles/dual_intent_v05.json"
OLD_REVIEW = ROOT / "tmp_v05/dr/review.json"
OLD_COMPOSITION = ROOT / "tmp_v05/dr_composition_diagnosis/composition_counts.json"
SIDES = ("east", "north", "south", "west")
AXES = ("east", "north")
EXPECTED_N = {2: 44, 3: 43, 4: 43}
REQUIRED_M = 7.0
LANE_LIMIT_M = 4.0
TOLERANCE_M = 1e-6


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def quantile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return values[low] + (values[high] - values[low]) * (index - low)


def continuous(rows, key):
    values = sorted(float(row[key]) for row in rows if row.get(key) is not None)
    if not values:
        return None
    return dict(count=len(values), minimum=values[0], p10=quantile(values, .1),
                median=quantile(values, .5), mean=sum(values) / len(values),
                p90=quantile(values, .9), maximum=values[-1])


def categorical(rows, key):
    counts = Counter(str(row[key]) for row in rows if row.get(key) is not None)
    total = sum(counts.values())
    return {name: dict(count=count, fraction=count / total)
            for name, count in sorted(counts.items())}


def histogram(rows, key, edges):
    counts = [0] * (len(edges) - 1)
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        index = bisect.bisect_right(edges, value) - 1
        if value == edges[-1]:
            index -= 1
        if not 0 <= index < len(counts):
            raise ValueError(f"{key} outside declared range: {value}")
        counts[index] += 1
    total = sum(counts)
    return [dict(lower=lo, upper=hi, count=count,
                 fraction=count / total if total else None)
            for lo, hi, count in zip(edges[:-1], edges[1:], counts)]


def selection(rows):
    return dict(count=len(rows), categorical={key: categorical(rows, key)
        for key in ("vehicle_count", "entry_side", "speed_m_s")},
        continuous={key: continuous(rows, key) for key in
            ("line_rotation_deg", "region_width_m", "region_height_m", "speed_m_s")},
        histograms={
            "line_rotation_deg": histogram(rows, "line_rotation_deg", [-20, -10, 0, 10, 20]),
            "region_unit_width_m": histogram(rows, "region_unit_width_m", [11, 12, 13, 14, 15, 16]),
            "region_unit_height_m": histogram(rows, "region_unit_height_m", [11, 12, 13, 14, 15, 16]),
        },
        region_by_n={str(n): {key: continuous(
            [row for row in rows if row["vehicle_count"] == n], key)
            for key in ("region_width_m", "region_height_m")} for n in EXPECTED_N})


def selection_difference(all_draws, accepted):
    categorical_delta = {}
    for key in ("vehicle_count", "entry_side", "speed_m_s"):
        left, right = all_draws["categorical"][key], accepted["categorical"][key]
        categorical_delta[key] = {
            value: right.get(value, {}).get("fraction", 0.0)
                   - left.get(value, {}).get("fraction", 0.0)
            for value in sorted(set(left) | set(right))}
    continuous_delta = {}
    for key in ("line_rotation_deg", "region_width_m", "region_height_m", "speed_m_s"):
        left, right = all_draws["continuous"][key], accepted["continuous"][key]
        continuous_delta[key] = right["mean"] - left["mean"] if left and right else None
    return dict(categorical_fraction_delta=categorical_delta,
                continuous_mean_delta=continuous_delta)


def resolved_axis(sampled):
    """Mirror reconnaissance's dominant-centroid-displacement auto rule."""
    east = sampled["formation_center_east_m"] - sampled["region_center_east_m"]
    north = sampled["formation_center_north_m"] - sampled["region_center_north_m"]
    if abs(north) >= abs(east):
        return "east", "north" if north >= 0 else "south"
    return "north", "east" if east >= 0 else "west"


def candidate_row(candidate):
    sampled = candidate.get("sampled_parameters")
    if sampled is None:
        return None
    axis, inferred_side = resolved_axis(sampled)
    return dict(candidate_id=candidate["candidate_id"], base_index=candidate["base_index"],
                accepted=candidate["status"] == "accepted",
                vehicle_count=sampled["vehicle_count"], entry_side=sampled["entry_side"],
                inferred_entry_side=inferred_side, resolved_axis=axis,
                formation=sampled["formation"], line_rotation_deg=sampled["line_rotation_deg"],
                region_width_m=sampled["region_width_m"],
                region_height_m=sampled["region_height_m"],
                region_unit_width_m=sampled["region_unit_width_m"],
                region_unit_height_m=sampled["region_unit_height_m"],
                speed_m_s=candidate["shared_mission_params"]["speed_m_s"])


def composition(rows):
    draws = Counter((r["vehicle_count"], r["entry_side"], r["resolved_axis"]) for r in rows)
    accepted = Counter((r["vehicle_count"], r["entry_side"], r["resolved_axis"])
                       for r in rows if r["accepted"])
    return [dict(vehicle_count=n, entry_side=side, resolved_axis=axis,
                 candidate_draws=draws[n, side, axis],
                 accepted_scenes=accepted[n, side, axis],
                 acceptance_rate=(accepted[n, side, axis] / draws[n, side, axis]
                                  if draws[n, side, axis] else None))
            for n in EXPECTED_N for side in SIDES for axis in AXES]


def artifact_integrity(generated, manifest):
    registered = manifest["artifact_sha256"]
    missing, changed, unsafe = [], [], []
    for relative, expected in registered.items():
        path = (generated / relative).resolve()
        if not path.is_relative_to(generated):
            unsafe.append(relative)
        elif not path.is_file():
            missing.append(relative)
        elif file_hash(path) != expected:
            changed.append(relative)
    actual = {path.relative_to(generated).as_posix() for path in generated.rglob("*.json")
              if path.name != "generation_manifest.json"}
    unregistered = sorted(actual - set(registered))
    return dict(registered_files=len(registered), actual_json_files=len(actual),
                missing=missing, changed=changed, unsafe=unsafe,
                unregistered=unregistered,
                pass_gate=not (missing or changed or unsafe or unregistered))


def reason_class(raw):
    if not raw:
        return "unspecified"
    return (raw.split(": ", 1)[1] if ": " in raw else raw).split(":", 1)[0].strip()


def rejection_counts(candidates):
    reasons = defaultdict(Counter)
    status = Counter()
    for candidate in candidates:
        if candidate["status"] == "accepted":
            continue
        status[candidate["status"]] += 1
        if candidate["status"] == "sampling_rejected":
            reasons["sampling"][reason_class(candidate.get("reason"))] += 1
        for attempt in candidate.get("attempts", []):
            if attempt["status"] != "planned":
                reasons[attempt["intent"]][reason_class(attempt.get("reason"))] += 1
    return dict(candidate_status=dict(sorted(status.items())),
                by_intent={name: dict(sorted(count.items()))
                           for name, count in sorted(reasons.items())})


def observe_geometry(candidate, row, scene):
    """Compare d = W - W / ceil(W / 4) with the production checker result."""
    task, planning = scene["task_spec"], scene["planning"]
    stages = planning["feasibility_checks"]["nominal_phase_timing"]
    observe = [value for name, value in stages.items() if name.endswith("_observe")]
    if len(observe) != 1:
        raise ValueError(f"one observe stage required: {candidate['candidate_id']}")
    stage = observe[0]
    n = row["vehicle_count"]
    width = (row["region_width_m"] if row["resolved_axis"] == "east"
             else row["region_height_m"]) / n
    spacing_limit = task["planner"]["params"]["lane_spacing_m"]
    lanes = math.ceil(width / LANE_LIMIT_M)
    delta = width / lanes
    geometric_min = width - delta
    production_min = stage["nominal_min_clearance_m"]
    required = stage["required_clearance_m"]
    return dict(candidate_id=candidate["candidate_id"], base_index=candidate["base_index"],
                vehicle_count=n, resolved_axis=row["resolved_axis"], strip_width_m=width,
                lane_spacing_limit_m=spacing_limit, lanes_per_strip=lanes,
                actual_scanline_spacing_m=delta, geometric_min_m=geometric_min,
                production_observe_min_m=production_min,
                difference_m=production_min - geometric_min, required_clearance_m=required,
                geometry_pass=geometric_min + TOLERANCE_M >= REQUIRED_M,
                production_pass=production_min + TOLERANCE_M >= required,
                crosscheck_pass=abs(production_min - geometric_min) <= TOLERANCE_M,
                axis_matches=planning["partition_axis"] == row["resolved_axis"],
                side_matches=(planning["partition_axis_resolution"]["inferred_entry_side"]
                              == row["inferred_entry_side"] == row["entry_side"]),
                fixed_model_matches=(abs(spacing_limit - LANE_LIMIT_M) <= 1e-12
                                     and abs(required - REQUIRED_M) <= 1e-12))


def old_comparison():
    review, table = read_json(OLD_REVIEW), read_json(OLD_COMPOSITION)
    old_file = file_hash(OLD_PROFILE)
    old_canonical = canonical_hash(normalize_profile(OLD_PROFILE))
    return dict(profile_file_sha256=old_file, profile_canonical_sha256=old_canonical,
                archived_review_profile_matches=(
                    review["profile_file_sha256"] == old_file
                    and review["profile_canonical_sha256"] == old_canonical),
                candidate_draws=table["candidate_draws"],
                accepted_scenes=table["accepted_scenes"],
                accepted_by_n={str(row["N"]): row["accepted_scenes"]
                               for row in table["margins"]["N"]},
                accepted_by_entry_side={row["entry_side"]: row["accepted_scenes"]
                                        for row in table["margins"]["entry_side"]},
                accepted_by_axis={row["recon_partition_axis_resolved"]: row["accepted_scenes"]
                                  for row in table["margins"]["axis"]},
                accepted_by_formation={row["formation"]: row["accepted_scenes"]
                                       for row in table["margins"]["formation"]})


def review(profile_path=PROFILE, generated=GENERATED):
    profile_path, generated = Path(profile_path).resolve(), Path(generated).resolve()
    profile = normalize_profile(profile_path)
    if (profile["scene_sampler"]["name"] != "random_spawn_v2"
            or profile["base_scene_count"] != 130
            or profile["max_candidates_per_base"] != 20):
        raise ValueError("v05b review requires fixed random_spawn_v2 / 130 / 20 profile")
    manifest_path = generated / "generation_manifest.json"
    manifest = read_json(manifest_path)
    listing = read_json(generated / "mission_list.json")
    candidates, bases = manifest["candidates"], manifest["bases"]
    integrity = artifact_integrity(generated, manifest)
    profile_canonical = canonical_hash(profile)
    bound_profile = (read_json(generated / "generation_profile.json") == profile
                     and manifest["profile_sha256"] == profile_canonical
                     and listing["generation_profile_sha256"]
                     == file_hash(generated / "generation_profile.json"))
    structure = (len(bases) == 130
                 and {base["base_index"] for base in bases} == set(range(130))
                 and len(candidates) == manifest["counts"]["candidates"]
                 and len(listing["missions"]) == manifest["counts"]["planned_missions"]
                 and manifest["counts"]["accepted_candidates"]
                 == sum(c["status"] == "accepted" for c in candidates)
                 and manifest["counts"]["accepted_bases"]
                 == sum(b["status"] == "accepted" for b in bases))
    rows_by_candidate = {c["candidate_id"]: candidate_row(c) for c in candidates}
    missing_sampled = [cid for cid, row in rows_by_candidate.items() if row is None]
    rows = [row for row in rows_by_candidate.values() if row is not None]
    accepted_rows = [row for row in rows if row["accepted"]]
    candidates_by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
    accepted_n = Counter((2, 3, 4)[base["base_index"] % 3]
                         for base in bases if base["status"] == "accepted")
    sampler_consistent = all(
        row["vehicle_count"] == (2, 3, 4)[row["base_index"] % 3]
        and row["formation"] == "line"
        and row["entry_side"] == row["inferred_entry_side"]
        for row in rows)
    recon_entries = {entry["candidate_id"]: entry for entry in listing["missions"]
                     if entry["intent"] == "reconnaissance"}
    geometry = []
    for row in accepted_rows:
        candidate_id = row["candidate_id"]
        if candidate_id not in recon_entries:
            raise ValueError(f"missing accepted reconnaissance scene: {candidate_id}")
        entry = recon_entries[candidate_id]
        scene_file = generated / entry["scene"]
        if file_hash(scene_file) != entry["scene_sha256"]:
            raise ValueError(f"accepted reconnaissance scene changed: {scene_file}")
        geometry.append(observe_geometry(
            candidates_by_id[candidate_id], row, read_json(scene_file)))
    total = len(candidates)
    both = sum(c["status"] == "accepted" for c in candidates)
    attempted, planned = Counter(), Counter()
    for candidate in candidates:
        for attempt in candidate.get("attempts", []):
            attempted[attempt["intent"]] += 1
            planned[attempt["intent"]] += attempt["status"] == "planned"
    rates = {name: dict(planned=planned[name], attempted=attempted[name],
                        fraction=planned[name] / total if total else None)
             for name in ("reconnaissance", "patrol")}
    rates["both"] = dict(planned=both, attempted=total,
                         fraction=both / total if total else None)
    gate = dict(
        profile_binding=bound_profile,
        generated_structure_consistent=structure,
        generated_artifacts_intact=integrity["pass_gate"],
        joint_feasible_rate_ge_30_percent=bool(total and both / total >= .30),
        accepted_bases_130_of_130=sum(b["status"] == "accepted" for b in bases) == 130,
        stratified_accepted_44_43_43=all(accepted_n[n] == expected
                                         for n, expected in EXPECTED_N.items()),
        sampler_strata_and_line_only=sampler_consistent,
        no_missing_sampled_parameters=not missing_sampled,
        accepted_observe_geometry_clear=(
            len(geometry) == 130 and all(item["geometry_pass"] for item in geometry)),
        production_observe_crosscheck=(
            len(geometry) == 130 and all(
                item["production_pass"] and item["crosscheck_pass"]
                and item["axis_matches"] and item["side_matches"]
                and item["fixed_model_matches"] for item in geometry)),
    )
    gate["pass"] = all(gate.values())
    all_selection, accepted_selection = selection(rows), selection(accepted_rows)
    return dict(review_version="dual_intent_dr_review_v05b_r1", scope="planning only; no SITL",
                profile_file_sha256=file_hash(profile_path),
                profile_canonical_sha256=profile_canonical,
                generation_manifest_file_sha256=file_hash(manifest_path),
                old_profile_comparison=old_comparison(), counts=manifest["counts"],
                accepted_by_n={str(n): accepted_n[n] for n in EXPECTED_N},
                missing_sampled_parameters=missing_sampled, rates=rates,
                rejection_reasons=rejection_counts(candidates),
                composition_n_entry_axis=composition(rows),
                selection_bias=dict(all_draws=all_selection,
                                    accepted_scenes=accepted_selection,
                                    difference=selection_difference(all_selection, accepted_selection)),
                accepted_observe_geometry=geometry, artifact_integrity=integrity, gate=gate)


def categorical_text(data):
    return ", ".join(f"{name}: {item['count']} ({item['fraction']:.1%})"
                     for name, item in data.items()) or "无"


def continuous_text(data, unit=""):
    if data is None:
        return "无"
    return (f"均值 {data['mean']:.2f}{unit}，P10/P50/P90 "
            f"{data['p10']:.2f}/{data['median']:.2f}/{data['p90']:.2f}{unit}，"
            f"范围 {data['minimum']:.2f}–{data['maximum']:.2f}{unit}")


def categorical_delta_text(data):
    return ", ".join(f"{name}: {value * 100:+.1f} pp"
                     for name, value in data.items()) or "无"


def render(result):
    gate, rates = result["gate"], result["rates"]
    selection_bias = result["selection_bias"]
    old = result["old_profile_comparison"]
    lines = [
        "# v0.5 r1.1 双意图规划干跑 DR 复核（v05b）", "",
        f"门禁：**{'PASS' if gate['pass'] else 'FAIL'}**。共抽取 "
        f"{result['counts']['candidates']} 个候选，接受 "
        f"{result['counts']['accepted_bases']}/130 个基础场景。本次只有纯规划，没有启动 SITL。", "",
        "## 预先写定的门禁", "", "| 项目 | 判定 |", "| --- | --- |",
    ]
    for name, passed in gate.items():
        if name != "pass":
            lines.append(f"| {name} | {'PASS' if passed else 'FAIL'} |")
    lines += ["", "| 意图/联合 | 规划可行 | 候选数 | 可行率 |",
              "| --- | ---: | ---: | ---: |"]
    for name in ("reconnaissance", "patrol", "both"):
        value = rates[name]
        lines.append(f"| {name} | {value['planned']} | {value['attempted']} | "
                     f"{value['fraction']:.2%} |")
    lines += ["", "按基础场景编号轮流分层后的接受数：" +
              "、".join(f"N={n}: {result['accepted_by_n'][str(n)]}/{expected}"
                       for n, expected in EXPECTED_N.items()) + "。", "",
              "## 抽取与接受构成", "",
              "每格写作接受/抽取；剖分轴是侦察规划器按机群质心相对区域中心推得的方向。", "",
              "| N | 进场方向 | east 剖分轴 | north 剖分轴 |",
              "| ---: | --- | ---: | ---: |"]
    cells = {(x["vehicle_count"], x["entry_side"], x["resolved_axis"]): x
             for x in result["composition_n_entry_axis"]}
    for n in EXPECTED_N:
        for side in SIDES:
            east, north = cells[n, side, "east"], cells[n, side, "north"]
            lines.append(f"| {n} | {side} | {east['accepted_scenes']}/{east['candidate_draws']} | "
                         f"{north['accepted_scenes']}/{north['candidate_draws']} |")
    lines += ["", "## 拒绝原因", "",
              "候选拒绝与逐意图规划拒绝分别计数；一个候选可在两个意图上都被拒。", "",
              "| 意图/采样 | 原因类别 | 次数 |", "| --- | --- | ---: |"]
    for intent, reasons in result["rejection_reasons"]["by_intent"].items():
        for reason, count in reasons.items():
            lines.append(f"| {intent} | {reason} | {count} |")
    lines += ["", "## 选择偏差", "",
              "抽取集按每次尝试计数，接受集按每个基础场景最终选中的一个候选计数；"
              "候选重抽具有顺序条件，下列比例是描述性分布。", "",
              "| 变量 | 全部抽取 | 被接受 | 接受 − 抽取 |",
              "| --- | --- | --- | --- |"]
    for key in ("entry_side", "speed_m_s"):
        lines.append(f"| {key} | {categorical_text(selection_bias['all_draws']['categorical'][key])} | "
                     f"{categorical_text(selection_bias['accepted_scenes']['categorical'][key])} | "
                     f"{categorical_delta_text(selection_bias['difference']['categorical_fraction_delta'][key])} |")
    for key, unit in (("line_rotation_deg", "°"), ("region_width_m", " m"),
                      ("region_height_m", " m")):
        shift = selection_bias["difference"]["continuous_mean_delta"][key]
        shift_text = f"{shift:+.2f}{unit}" if shift is not None else "无"
        lines.append(f"| {key} | {continuous_text(selection_bias['all_draws']['continuous'][key], unit)}"
                     f" | {continuous_text(selection_bias['accepted_scenes']['continuous'][key], unit)}"
                     f" | 均值 {shift_text} |")
    lines += ["", "区域宽高由 N 倍独立的单位尺寸生成，也按相同 N 层比较：", "",
              "| N | 变量 | 全部抽取均值 | 接受均值 |",
              "| ---: | --- | ---: | ---: |"]
    for n in EXPECTED_N:
        for key in ("region_width_m", "region_height_m"):
            a = selection_bias["all_draws"]["region_by_n"][str(n)][key]
            b = selection_bias["accepted_scenes"]["region_by_n"][str(n)][key]
            all_mean = f"{a['mean']:.2f} m" if a is not None else "无"
            accepted_mean = f"{b['mean']:.2f} m" if b is not None else "无"
            lines.append(f"| {n} | {key} | {all_mean} | {accepted_mean} |")
    lines += ["", "旋转角和单位区域尺寸的分箱频数及全部统计量见 "
              "[v05b DR JSON](../tmp_v05/dr_v05b/review.json)。"
              f"几何参数缺失的采样拒绝候选有 {len(result['missing_sampled_parameters'])} 个，"
              "计入联合可行率分母，不进入几何分布。", "",
              "## observe 阶段间距核对", "",
              r"每个接受场景按实际条带宽 \(W\) 和 4 m 扫描线间距上限计算 "
              r"\(L=\lceil W/(4\,\mathrm{m})\rceil\)、\(\delta=W/L\)、\(d=W-\delta\)。"
              "与生产规划器的完整时间感知间距检查所记录的 observe 最小距离逐个比较，"
              f"容差 {TOLERANCE_M:g} m。"
              rf"接受集最小 \(d\) 为 {min(x['geometric_min_m'] for x in result['accepted_observe_geometry']):.3f} m；"
              f"最大交叉核对差值为 {max(abs(x['difference_m']) for x in result['accepted_observe_geometry']):.3g} m。"
              f"几何违规 {sum(not x['geometry_pass'] for x in result['accepted_observe_geometry'])} 个；"
              f"生产检查交叉不一致 {sum(not x['crosscheck_pass'] for x in result['accepted_observe_geometry'])} 个。", "",
              "## 旧 profile 对照与指纹", "",
              "| 项目 | 原 v05 | 新 v05b |", "| --- | ---: | ---: |",
              f"| 候选抽取 | {old['candidate_draws']} | {result['counts']['candidates']} |",
              f"| 接受基础场景 | {old['accepted_scenes']} | {result['counts']['accepted_bases']} |"]
    for n in EXPECTED_N:
        lines.append(f"| 接受 N={n} | {old['accepted_by_n'][str(n)]} | "
                     f"{result['accepted_by_n'][str(n)]} |")
    new_side = selection_bias["accepted_scenes"]["categorical"]["entry_side"]
    for side in SIDES:
        lines.append(f"| 接受进场 {side} | {old['accepted_by_entry_side'][side]} | "
                     f"{new_side.get(side, {}).get('count', 0)} |")
    new_axis = Counter()
    for cell in result["composition_n_entry_axis"]:
        new_axis[cell["resolved_axis"]] += cell["accepted_scenes"]
    for axis in AXES:
        lines.append(f"| 接受剖分轴 {axis} | {old['accepted_by_axis'][axis]} | "
                     f"{new_axis[axis]} |")
    lines += ["", f"新 profile 文件 SHA256：{result['profile_file_sha256']}；规范化指纹："
              f"{result['profile_canonical_sha256']}。原 profile 文件 SHA256："
              f"{old['profile_file_sha256']}；规范化指纹："
              f"{old['profile_canonical_sha256']}。归档指纹"
              f"{'一致' if old['archived_review_profile_matches'] else '不一致'}。", "",
              f"生成目录登记 {result['artifact_integrity']['registered_files']} 份附件，"
              f"哈希及附件清单{'完整' if result['artifact_integrity']['pass_gate'] else '不完整'}。"
              "原 v05 profile、DR 结果和诊断均未覆盖。DR 只证明纯规划可行；"
              "只有门禁全通过才可进入后续验证运行。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=PROFILE)
    parser.add_argument("--generated", type=Path, default=GENERATED)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    result = review(args.profile, args.generated)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    with args.report.open("x", encoding="utf-8") as stream:
        stream.write(render(result))
    print(json.dumps({"gate": result["gate"], "rates": result["rates"]}, ensure_ascii=False))
    return 0 if result["gate"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
