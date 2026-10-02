"""Read-only review of the fixed v0.5 dual-intent planning dry run."""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_sim.generation import canonical_hash, file_hash
from swarm_sim.generation_v2 import normalize_profile


PROFILE = ROOT / "generation_profiles/dual_intent_v05.json"
GENERATED = ROOT / "tmp_v05/dr/generated_130"
OUTPUT = ROOT / "tmp_v05/dr/review.json"
REPORT = ROOT / "docs/v0.5_dr_review.md"


def _distribution(rows, key):
    values = [row[key] for row in rows]
    counts = Counter(str(value) for value in values)
    return {value: {"count": count, "fraction": count / len(values)}
            for value, count in sorted(counts.items())} if values else {}


def _continuous(rows, key):
    values = sorted(float(row[key]) for row in rows)
    if not values:
        return None
    midpoint = len(values) // 2
    median = values[midpoint] if len(values) % 2 else (values[midpoint-1] + values[midpoint]) / 2
    return dict(count=len(values), minimum=values[0], mean=sum(values)/len(values),
                median=median, maximum=values[-1])


def _selection(rows):
    return dict(discrete={key: _distribution(rows, key) for key in
        ("vehicle_count", "entry_side", "formation", "speed_m_s")},
        continuous={key: _continuous(rows, key) for key in
        ("region_width_m", "region_height_m")})


def _row(candidate):
    sampled = candidate.get("sampled_parameters") or {}
    shared = candidate.get("shared_mission_params") or {}
    return dict(vehicle_count=sampled["vehicle_count"], entry_side=sampled["entry_side"],
                formation=sampled["formation"], region_width_m=sampled["region_width_m"],
                region_height_m=sampled["region_height_m"], speed_m_s=shared["speed_m_s"])


def _verify_artifacts(generated, manifest):
    missing, changed = [], []
    for relative, expected in manifest["artifact_sha256"].items():
        item = generated / relative
        if not item.is_file():
            missing.append(relative)
        elif file_hash(item) != expected:
            changed.append(relative)
    return dict(hashed_files=len(manifest["artifact_sha256"]), missing=missing,
                changed=changed, unchanged=not (missing or changed))


def review(profile_path=PROFILE, generated=GENERATED):
    profile = normalize_profile(profile_path)
    manifest = json.loads((generated / "generation_manifest.json").read_text(encoding="utf-8"))
    if manifest["profile_sha256"] != canonical_hash(profile):
        raise ValueError("generated profile fingerprint differs from current fixed profile")
    candidates = manifest["candidates"]
    bases = manifest["bases"]
    if len(candidates) != manifest["counts"]["candidates"] or len(bases) != 130:
        raise ValueError("generation manifest candidate or base count mismatch")
    intents = ("patrol", "reconnaissance")
    attempt_counts = Counter()
    planned_counts = Counter()
    rejection_reasons = defaultdict(Counter)
    full_checker_assignment_counts = defaultdict(Counter)
    full_checker_candidate_counts = defaultdict(Counter)
    all_rows, accepted_rows = [], []
    for candidate in candidates:
        all_rows.append(_row(candidate))
        if candidate["status"] == "accepted":
            accepted_rows.append(_row(candidate))
        for attempt in candidate.get("attempts", []):
            intent = attempt["intent"]
            attempt_counts[intent] += 1
            if attempt["status"] == "planned":
                planned_counts[intent] += 1
            else:
                raw = attempt.get("reason", "")
                reason = raw.split(":", 1)[1].strip().split(":", 1)[0] if ":" in raw else raw
                rejection_reasons[intent][reason] += 1
                for phase, count in re.findall(
                        r"(approach|patrol|return):time-aware nominal routes too close=(\d+)", raw):
                    full_checker_assignment_counts[intent][phase] += int(count)
                    full_checker_candidate_counts[intent][phase] += 1
    total = len(candidates)
    both = sum(candidate["status"] == "accepted" for candidate in candidates)
    rates = {intent: dict(planned=planned_counts[intent], attempted=attempt_counts[intent],
                           fraction=planned_counts[intent]/total) for intent in intents}
    rates["both"] = dict(planned=both, attempted=total, fraction=both/total)
    artifact_check = _verify_artifacts(generated, manifest)
    accepted = sum(base["status"] == "accepted" for base in bases)
    gate = dict(joint_feasible_at_least_30_percent=both/total >= .30,
                accepted_bases_130_of_130=accepted == 130,
                generated_artifacts_intact=artifact_check["unchanged"])
    gate["pass"] = all(gate.values())
    return dict(review_version="dual_intent_dr_review_v1", profile_file_sha256=file_hash(profile_path),
        profile_canonical_sha256=canonical_hash(profile),
        generation_manifest_file_sha256=file_hash(generated / "generation_manifest.json"),
        template_canonical_sha256={m["intent"]: canonical_hash(m["template_spec"]) for m in profile["missions"]},
        counts=manifest["counts"], candidate_status=dict(Counter(c["status"] for c in candidates)),
        rates=rates, rejection_reasons={k: dict(v) for k, v in rejection_reasons.items()},
        full_checker_rejections=dict(assignment_counts={k: dict(v) for k, v in full_checker_assignment_counts.items()},
                                     candidate_counts={k: dict(v) for k, v in full_checker_candidate_counts.items()}),
        selection_bias=dict(all_draws=_selection(all_rows), accepted_scenes=_selection(accepted_rows)),
        artifact_integrity=artifact_check, gate=gate,
        scope="pure planning only; no SITL execution or measured flight capability")


def _render(result):
    counts = result["counts"]
    rates = result["rates"]
    selection = result["selection_bias"]
    lines = ["# v0.5 双意图规划干跑 DR 复核", "",
        f"门禁：**{'PASS' if result['gate']['pass'] else 'FAIL'}**。固定正式 profile 共抽取 {counts['candidates']} 个候选，"
        f"接受 {counts['accepted_bases']}/130 个基础场景，规划成功 {counts['planned_missions']} 份双意图任务。"
        "本次仅执行纯规划，没有启动 SITL。", "",
        "| 意图/联合 | 规划可行 | 候选数 | 可行率 |", "| --- | ---: | ---: | ---: |"]
    for intent in ("reconnaissance", "patrol", "both"):
        row = rates[intent]
        lines.append(f"| {intent} | {row['planned']} | {row['attempted']} | {row['fraction']:.2%} |")
    lines.extend(["", "联合可行率门禁为至少 30%，基础场景门禁为 130/130。两项判定和所有原始计数见"
        "[DR 明细](../tmp_v05/dr/review.json)。", "",
        "## 拒绝原因", "",
        "| 意图 | 原因 | 候选数 |", "| --- | --- | ---: |"])
    for intent, reasons in sorted(result["rejection_reasons"].items()):
        for reason, count in sorted(reasons.items()):
            lines.append(f"| {intent} | `{reason}` | {count} |")
    lines.extend(["", "`patrol_spacing_prefilter` 是弧长预筛选；`patrol_assignment_infeasible` 是全部分配"
        "经过通用时距判据后不可行。后者内含接近、巡逻、返航各阶段失败的分配次数，"
        "详见 DR JSON 的 `full_checker_rejections`；两类拒绝分别保留，没有互相替代。", "",
        "## 选择偏差", "",
        "以下比较全部候选抽取与每个基础场景最终被接受的一个候选。完整离散频数、比例与尺寸统计见 DR JSON。", "",
        "| 变量 | 全部抽取 | 被接受 |", "| --- | --- | --- |"])
    for key in ("vehicle_count", "entry_side", "formation", "speed_m_s"):
        all_d = selection["all_draws"]["discrete"][key]
        accepted_d = selection["accepted_scenes"]["discrete"][key]
        all_text = ", ".join(f"{name}: {v['fraction']:.1%}" for name, v in all_d.items())
        accepted_text = ", ".join(f"{name}: {v['fraction']:.1%}" for name, v in accepted_d.items())
        lines.append(f"| {key} | {all_text} | {accepted_text} |")
    for key in ("region_width_m", "region_height_m"):
        all_v = selection["all_draws"]["continuous"][key]
        accepted_v = selection["accepted_scenes"]["continuous"][key]
        lines.append(f"| {key} | 均值 {all_v['mean']:.2f} m，范围 {all_v['minimum']:.2f}–{all_v['maximum']:.2f} m | "
                     f"均值 {accepted_v['mean']:.2f} m，范围 {accepted_v['minimum']:.2f}–{accepted_v['maximum']:.2f} m |")
    lines.extend(["", f"Profile 文件 SHA256：`{result['profile_file_sha256']}`；规范化指纹："
        f"`{result['profile_canonical_sha256']}`。生成器登记的 {result['artifact_integrity']['hashed_files']} 份文件"
        f"哈希{'全部一致' if result['artifact_integrity']['unchanged'] else '出现异常'}。"
        "历史保护复核见 [protected_recheck.json](../tmp_v05/dr/protected_recheck.json)。", "",
        "DR 只证明两种任务在同一物理场景中的名义规划可行；实际轨迹、AC4、机载参数与质量"
        "仍需后续验证运行逐项验收。", ""])
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
        stream.write(_render(result))
    print(json.dumps({"gate": result["gate"], "rates": result["rates"]}, ensure_ascii=False))
    return 0 if result["gate"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
