"""Review the v05c dry run and prove its non-heading equivalence to v05b.

This is a read-only planning review. Its output paths are new; historical DR
reports and generated tasks are never rewritten.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.review_v05b_dr import review as base_review
from swarm_sim.generation import canonical_hash, checked_path, file_hash, verify_generation
from swarm_sim.generation_v2 import normalize_profile


V05B_PROFILE = ROOT / "generation_profiles/dual_intent_v05b.json"
V05B_GENERATED = ROOT / "tmp_v05/dr_v05b/generated_130"
PROFILE = ROOT / "generation_profiles/dual_intent_v05c.json"
GENERATED = ROOT / "tmp_v05/dr_v05c/generated_130"
OUTPUT = ROOT / "tmp_v05/dr_v05c/review.json"
REPORT = ROOT / "docs/v0.5c_dr_review.md"

DERIVED_ENTRY_KEYS = frozenset({"family_id", "base_scene_id", "base_scene_sha256",
    "scene_content_sha256", "task_sha256", "normalized_task_sha256", "scene_sha256"})
DERIVED_CANDIDATE_KEYS = frozenset({"family_id", "scene_content_sha256"})


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def without_heading_and_family(value):
    """Normalize semantic task/scene content, retaining every planner field."""
    if isinstance(value, dict):
        return {key: without_heading_and_family(item) for key, item in value.items()
                if key not in ("heading_deg", "family_id")}
    if isinstance(value, list):
        return [without_heading_and_family(item) for item in value]
    return value


def sampled_without_heading(sampled):
    clean = without_heading_and_family(sampled)
    if clean is not None:
        clean.get("sampler_params", {}).pop("heading_policy", None)
    return clean


def candidate_without_derived(candidate):
    clean = {key: value for key, value in candidate.items()
             if key not in DERIVED_CANDIDATE_KEYS and key != "sampled_parameters"}
    clean["sampled_parameters"] = sampled_without_heading(candidate.get("sampled_parameters"))
    clean["attempts"] = [{key: value for key, value in attempt.items()
                          if key != "task_sha256"}
                         for attempt in candidate.get("attempts", [])]
    return clean


def entry_without_derived(entry):
    clean = {key: value for key, value in entry.items()
             if key not in DERIVED_ENTRY_KEYS and key != "sampled_parameters"}
    clean["sampled_parameters"] = sampled_without_heading(entry.get("sampled_parameters"))
    return clean


def invariance(v05b_profile=V05B_PROFILE, v05b_generated=V05B_GENERATED,
               v05c_profile=PROFILE, v05c_generated=GENERATED):
    """Compare all candidate draws, accepted tasks, and compiled planner output."""
    v05b_profile, v05c_profile = Path(v05b_profile).resolve(), Path(v05c_profile).resolve()
    v05b_generated, v05c_generated = Path(v05b_generated).resolve(), Path(v05c_generated).resolve()
    before, after = normalize_profile(v05b_profile), normalize_profile(v05c_profile)
    params = after["scene_sampler"]["params"]
    without_policy = dict(params)
    policy = without_policy.pop("heading_policy", None)
    expected = dict(after)
    expected["scene_sampler"] = dict(after["scene_sampler"], params=without_policy)
    profile_only_heading = (policy == "fixed_zero" and before == expected)
    old_list, old_manifest = verify_generation(v05b_generated / "mission_list.json")
    new_list, new_manifest = verify_generation(v05c_generated / "mission_list.json")
    errors = []
    def require(condition, description):
        if not condition:
            errors.append(description)

    require(profile_only_heading, "profile differs beyond heading_policy=fixed_zero")
    old_candidates, new_candidates = old_manifest["candidates"], new_manifest["candidates"]
    old_bases, new_bases = old_manifest["bases"], new_manifest["bases"]
    old_entries, new_entries = old_list["missions"], new_list["missions"]
    require(len(old_candidates) == len(new_candidates), "candidate draw count differs")
    require(len(old_bases) == len(new_bases), "base scene count differs")
    require(len(old_entries) == len(new_entries), "accepted mission count differs")
    old_rejections = [without_heading_and_family(row) for row in old_manifest["rejections"]]
    new_rejections = [without_heading_and_family(row) for row in new_manifest["rejections"]]
    old_rejections = [{key: value for key, value in row.items()
                       if key != "scene_content_sha256"} for row in old_rejections]
    new_rejections = [{key: value for key, value in row.items()
                       if key != "scene_content_sha256"} for row in new_rejections]
    require(old_rejections == new_rejections,
            "candidate/intent rejection order or planning reasons differ")
    checked_candidates = checked_candidate_tasks = checked_scenes = 0
    family_changed = 0
    for index, (left, right) in enumerate(zip(old_candidates, new_candidates)):
        prefix = f"candidate[{index}] {left.get('candidate_id')}"
        require(candidate_without_derived(left) == candidate_without_derived(right),
                prefix + " sequence, sampled non-heading parameters or attempt result differs")
        require(left.get("candidate_id") == right.get("candidate_id") and
                left.get("base_index") == right.get("base_index") and
                left.get("candidate_index") == right.get("candidate_index") and
                left.get("scene_seed") == right.get("scene_seed"),
                prefix + " draw identity differs")
        old_sampled, new_sampled = left.get("sampled_parameters"), right.get("sampled_parameters")
        if old_sampled is not None and new_sampled is not None:
            left_slots, right_slots = old_sampled["spatial_slots"], new_sampled["spatial_slots"]
            require(len(left_slots) == len(right_slots) and
                    all(slot.get("heading_deg") == 0 for slot in right_slots),
                    prefix + " v05c headings are not all zero")
            require(left.get("family_id") != right.get("family_id") and
                    left.get("scene_content_sha256") != right.get("scene_content_sha256"),
                    prefix + " family identity did not change with heading")
            family_changed += left.get("family_id") != right.get("family_id")
        for left_attempt, right_attempt in zip(left.get("attempts", []), right.get("attempts", [])):
            if left_attempt.get("task") and right_attempt.get("task"):
                left_task = read(checked_path(v05b_generated, left_attempt["task"]))
                right_task = read(checked_path(v05c_generated, right_attempt["task"]))
                require(without_heading_and_family(left_task) ==
                        without_heading_and_family(right_task),
                        prefix + " candidate task content differs beyond heading/family_id")
                checked_candidate_tasks += 1
        checked_candidates += 1
    for index, (left, right) in enumerate(zip(old_bases, new_bases)):
        require({key: value for key, value in left.items() if key not in DERIVED_CANDIDATE_KEYS}
                == {key: value for key, value in right.items() if key not in DERIVED_CANDIDATE_KEYS},
                f"base[{index}] selected candidate or acceptance differs")
        require(left.get("family_id") != right.get("family_id") and
                left.get("scene_content_sha256") != right.get("scene_content_sha256"),
                f"base[{index}] family identity did not change")
    for index, (left, right) in enumerate(zip(old_entries, new_entries)):
        prefix = f"mission[{index}] {left.get('mission_id')}"
        require(entry_without_derived(left) == entry_without_derived(right),
                prefix + " mission selection or non-heading metadata differs")
        require(left.get("family_id") != right.get("family_id"),
                prefix + " family_id did not change")
        for field in ("task", "scene"):
            left_content = read(checked_path(v05b_generated, left[field]))
            right_content = read(checked_path(v05c_generated, right[field]))
            require(without_heading_and_family(left_content) ==
                    without_heading_and_family(right_content),
                    prefix + f" compiled {field} content differs beyond heading/family_id")
            if field == "scene":
                require(left_content["planning"] == right_content["planning"] and
                        left_content["phases"] == right_content["phases"] and
                        left_content["semantic_plan"] == right_content["semantic_plan"],
                        prefix + " actual planning/routes/phases differ")
                require(all(vehicle["heading_deg"] == 0
                            for vehicle in right_content["vehicles"]),
                        prefix + " v05c compiled headings are not zero")
                checked_scenes += 1
    return dict(pass_gate=not errors, errors=errors,
        profile_only_heading_policy=profile_only_heading,
        candidate_draws_compared=checked_candidates,
        candidate_tasks_compared=checked_candidate_tasks,
        accepted_bases_compared=min(len(old_bases), len(new_bases)),
        accepted_missions_compared=min(len(old_entries), len(new_entries)),
        compiled_scenes_compared=checked_scenes,
        candidate_families_changed=family_changed,
        v05b_profile_file_sha256=file_hash(v05b_profile),
        v05b_profile_canonical_sha256=canonical_hash(before),
        v05b_manifest_sha256=file_hash(v05b_generated / "generation_manifest.json"),
        v05c_profile_file_sha256=file_hash(v05c_profile),
        v05c_profile_canonical_sha256=canonical_hash(after),
        v05c_manifest_sha256=file_hash(v05c_generated / "generation_manifest.json"))


def review(profile=PROFILE, generated=GENERATED):
    result = base_review(profile, generated)
    comparison = invariance(v05c_profile=profile, v05c_generated=generated)
    result["review_version"] = "dual_intent_dr_review_v05c_r1"
    result["v05b_invariance"] = comparison
    result["gate"]["v05c_v05b_invariant"] = comparison["pass_gate"]
    result["gate"]["pass"] = all(value is True for key, value in result["gate"].items()
                                  if key != "pass")
    return result


def render(result):
    gate, comparison = result["gate"], result["v05b_invariance"]
    lines = ["# v0.5 r1.1 v05c DR 与 v05b 逐项核对", "",
        f"结论：**{'PASS' if gate['pass'] else 'FAIL'}**。仅执行纯规划；"
        f"候选抽取 {result['counts']['candidates']} 次、接受基础场景 "
        f"{result['counts']['accepted_bases']}/130、联合可行率 "
        f"{result['rates']['both']['fraction']:.2%}。", "",
        "| 门禁 | 结果 |", "| --- | --- |"]
    lines.extend(f"| {name} | {'PASS' if passed else 'FAIL'} |"
                 for name, passed in gate.items() if name != "pass")
    lines += ["", "## 候选和规划结果不变性", "",
        f"候选序列逐项比较 {comparison['candidate_draws_compared']} 项；"
        f"候选任务 {comparison['candidate_tasks_compared']} 项；"
        f"接受场景 {comparison['compiled_scenes_compared']} 项。"
        "除固定零航向及由此派生的 family_id/哈希外，采样参数、"
        "候选接受情况、任务种子、规划结果、航段和阶段均逐项相同。", "",
        f"不一致项：{len(comparison['errors'])}；详见 "
        "[review.json](../tmp_v05/dr_v05c/review.json)。", "",
        "## 指纹与后续边界", "",
        f"v05b profile 文件 SHA256：`{comparison['v05b_profile_file_sha256']}`；"
        f"规范化指纹：`{comparison['v05b_profile_canonical_sha256']}`。", "",
        f"v05c profile 文件 SHA256：`{comparison['v05c_profile_file_sha256']}`；"
        f"规范化指纹：`{comparison['v05c_profile_canonical_sha256']}`。", "",
        "[v05b DR 报告](v0.5b_dr_review.md)与其全部运行产物保持原样。"
        "本报告通过且选择器绑定该 JSON 后，才可进入 v05c 验证；"
        "历史 VP1 失败仍占验证预算 1/8。", ""]
    if comparison["errors"]:
        lines += ["", "### 不一致摘要", ""] + [f"- {item}" for item in comparison["errors"][:30]]
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
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    with args.report.open("x", encoding="utf-8") as stream:
        stream.write(render(result))
    print(json.dumps({"gate": result["gate"], "rates": result["rates"]},
                     ensure_ascii=False))
    return 0 if result["gate"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
