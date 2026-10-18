"""展示样例：同一设施"先监视、再佯动、再突入"的分阶段突防（仅供 PPT，不进数据集）。

复用 v0.7 first_edition 冻结代码（只导入、不修改）：沿用一个已保留抽签的场景、飞机与初始状态，
把编组改为 监视 / 佯动 / 突入 三组且目标为同一设施；规划 → 单机试飞 → 按指定先后倒推出发延迟
→ 一次联合仿真 → 一遍标签核对。输出写到 SwarmData\\ppt_media\\showcase\\，不写入任何数据集目录。
合成数据：点质量运动学模型，抽象场景，不控制真实无人机。

用法（在 Simulation-viz\\Multi-UAV SimpleGC 下）：
  python -B scripts/viz/showcase_staged_penetration.py --run pilot_f005_020d --draw <family_id>:<slot>
      [--target facility_01] [--gap-feint-frac 0.33] [--gap-intrusion-s 60] [--name staged_demo]
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from scripts.run_v07_fe_production import _descriptor_for, _family_for, _load_family  # noqa: E402
from task_v07.execution import execute  # noqa: E402
from task_v07.expansion.candidate_search import episode_candidate_pool  # noqa: E402
from task_v07.expansion.sampling import derive_intent, merge_units  # noqa: E402
from task_v07.expansion.solo_spacing import solo_interval_check  # noqa: E402
from task_v07.io import write_episode  # noqa: E402
from task_v07.labels import measure  # noqa: E402
from task_v07.unified.config import load_generator  # noqa: E402
from task_v07.unified.rehearsal import joint_budget, rehearse  # noqa: E402
from task_v07.unified.timing import episode_plan  # noqa: E402

DATA_ROOT = PROJECT.parents[1] / "SwarmData" / "v07_first_edition"
OUT_ROOT = PROJECT.parents[1] / "SwarmData" / "ppt_media" / "showcase"
STAGES = ("monitoring", "feint", "intrusion")  # 出场顺序
SCOPE = "SHOWCASE_ONLY: illustration for slides; not a dataset sample; never used for training or evaluation"


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=float)


def read(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def source_descriptor(run, draw):
    run_dir = DATA_ROOT / run
    family_id, slot = draw.rsplit(":", 1)
    manifest = read(run_dir / "manifest.json")
    entry = next((e for e in manifest["retained_episodes"] if e["family_id"] == family_id
                  and str(e["slot"]) == slot and e["intent"] == "penetration"), None)
    if entry is None:
        raise SystemExit(f"在 {run} 中找不到 {draw} 的突防样本（只能用 RETAINED 抽签）")
    registration = read(run_dir / "registration.json")
    descriptor = _descriptor_for(read(run_dir / "descriptors" / "descriptors.json"), entry["skeleton_id"])
    scene, family = _load_family(_family_for(registration, family_id))
    return descriptor, scene, family, entry


def staged_descriptor(descriptor, target):
    """同一批飞机重新分为 监视/佯动/突入 三组，目标相同；只改编组，不改场景与初始状态。"""
    ids = sorted(descriptor["agent_ids"])
    if len(ids) < 6:
        raise SystemExit(f"该抽签只有 {len(ids)} 架飞机，三组每组至少 2 架，需要不少于 6 架")
    base, extra = divmod(len(ids), 3)
    sizes = [base + (1 if i < extra else 0) for i in range(3)]  # 多出的飞机先给监视、佯动
    units, cursor = [], 0
    for i, (role, size) in enumerate(zip(STAGES, sizes)):
        units.append({"unit_id": f"unit_{i + 1:02d}", "target_id": target, "members": ids[cursor:cursor + size],
                      "between_group_offset_s": 0.0, "role": role, "execution_method": role})
        cursor += size
    new = deepcopy(descriptor)
    new["skeleton_id"] = descriptor["skeleton_id"] + "_showcase_staged"
    new["units"] = units
    new["task_groups"] = merge_units(deepcopy(units))
    new["main_unit_id"] = "unit_03"
    new["common_draw"] = deepcopy(descriptor["common_draw"])
    new["common_draw"]["units"] = deepcopy(units)
    if derive_intent(new["task_groups"]) != "penetration" or len(new["task_groups"]) != 3:
        raise SystemExit("编组构成不符合 监视+佯动+突入 三组")
    return new


def staged_offsets(sk, rehearsal, gap_feint_frac, gap_intrusion_s):
    """按出场顺序给三组指定核心事件目标时刻，换算成编组错开量（均 >= 0）。"""
    lead = load_generator()["timing"]["first_batch_lead_s"]
    core, done = rehearsal["core_times_s"], rehearsal["completion_times_s"]
    groups = {g["role"]: (gid, g) for gid, g in sk["group_skeletons"].items()}
    center = {role: max(core[a] for a in groups[role][1]["members"]) + lead for role in STAGES}
    mon = groups["monitoring"][1]["members"]
    mon_work = float(np.median([done[a] - core[a] for a in mon]))  # 监视作业时长（单机实测）
    target = {"monitoring": center["monitoring"]}
    target["feint"] = target["monitoring"] + gap_feint_frac * mon_work
    target["intrusion"] = target["feint"] + gap_intrusion_s
    raw = {role: target[role] - center[role] for role in STAGES}
    shift = -min(raw.values())
    offsets = {role: round(raw[role] + shift, 1) for role in STAGES}
    for role in STAGES:
        sk["group_skeletons"][groups[role][0]]["between_group_offset_s"] = offsets[role]
    return offsets, {"monitoring_work_s": mon_work, "target_core_s": target}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--draw", required=True)
    ap.add_argument("--target", help="目标设施 id；默认用原突防样本中突入编组的目标")
    ap.add_argument("--gap-feint-frac", type=float, default=0.33, help="佯动在监视作业进行到该比例时开始")
    ap.add_argument("--gap-intrusion-s", type=float, default=60.0, help="突入比佯动晚多少秒开始执行任务")
    ap.add_argument("--name", default="staged_penetration")
    ap.add_argument("--max-candidates", type=int, default=5)
    args = ap.parse_args(argv)

    t_all = time.perf_counter()
    descriptor, scene, family, entry = source_descriptor(args.run, args.draw)
    target = args.target
    if target is None:
        intr = [g for g in descriptor["task_groups"] if g["role"] == "intrusion"]
        target = intr[0]["target_id"]
    out = OUT_ROOT / args.name
    if out.exists():
        raise SystemExit(f"输出目录已存在：{out}（换一个 --name）")
    staged = staged_descriptor(descriptor, target)
    report = {"scope": SCOPE, "source": {"run": args.run, "draw": args.draw, "skeleton_id": entry["skeleton_id"]},
              "target": target, "groups": {g["group_id"]: {"role": g["role"], "members": g["members"]}
                                           for g in staged["task_groups"]},
              "parameters": {"gap_feint_frac": args.gap_feint_frac, "gap_intrusion_s": args.gap_intrusion_s},
              "attempts": [], "wall_s": {}}

    t0 = time.perf_counter()
    log("规划中（只规划）……")
    pool, search = episode_candidate_pool(scene, staged, backend="unified")
    report["wall_s"]["planning"] = time.perf_counter() - t0
    log(f"规划完成：{len(pool)} 个可行候选，用时 {report['wall_s']['planning']:.0f} s")
    if not pool:
        report["result"] = "PLANNING_FAILED"
        report["planning_rejections"] = search.get("rejection_reasons")
        save(out / "showcase_report.json", report)
        raise SystemExit(f"该设施周围三组规划失败，详见 {out / 'showcase_report.json'}；可换 --target 或换抽签")

    for candidate in pool[:args.max_candidates]:
        sk = deepcopy(candidate["skeleton"])
        attempt = {"candidate_index": candidate["index"]}
        t0 = time.perf_counter()
        log(f"候选 {candidate['index']}：单机试飞……")
        rehearsal, solo = rehearse(scene, sk, reference_version="r3")
        attempt["rehearsal_wall_s"] = time.perf_counter() - t0
        if rehearsal["status"] == "rejected":
            attempt["result"] = "REHEARSAL_REJECTED"
            report["attempts"].append(attempt)
            continue
        gap_i = args.gap_intrusion_s
        plan = None
        for _ in range(6):  # 空中间距不够时，把突入再往后推 30 s
            offsets, basis = staged_offsets(sk, rehearsal, args.gap_feint_frac, gap_i)
            trial = episode_plan(sk, rehearsal["core_times_s"], "synchronous", 0)
            overlay = solo_interval_check(solo, {"synchronous": trial})["synchronous"]
            if not overlay["below_warning"]:
                plan = trial
                break
            gap_i += 30.0
        attempt.update(offsets_s=offsets, timing_basis=basis, gap_intrusion_used_s=gap_i)
        if plan is None:
            attempt["result"] = "SPACING_CONFLICT"
            report["attempts"].append(attempt)
            continue
        t0 = time.perf_counter()
        log("联合仿真……")
        delays = plan["departure_delays_s"]
        run = execute(sk, delays, time_budget=joint_budget(sk, delays, rehearsal["completion_times_s"]),
                      reference_version="r3")
        attempt["joint_wall_s"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        log("标签核对……")
        labels, frame = measure(scene, sk, run, "synchronous", timing_plan=plan)
        attempt["labels_wall_s"] = time.perf_counter() - t0
        core_t = {gid: [labels["agents"][a]["observed"]["core_event"]["t_s"] for a in g["members"]]
                  for gid, g in sk["group_skeletons"].items()}
        role_of = {gid: g["role"] for gid, g in sk["group_skeletons"].items()}
        starts = {role_of[gid]: (None if any(t is None for t in ts) else float(min(ts))) for gid, ts in core_t.items()}
        quality = labels["generation_quality"]
        checks = {
            "execution_completed": run["execution_status"] == "completed",
            "physically_valid": bool(quality.get("retained")),
            "minimum_separation_m": quality.get("minimum_separation_m"),
            "group_results": {role_of[gid]: g["result"]["status"] for gid, g in labels["task_groups"].items()},
            "stage_start_s": starts,
            "order_monitoring_feint_intrusion": None not in starts.values()
                and starts["monitoring"] < starts["feint"] < starts["intrusion"],
        }
        checks["all_pass"] = (checks["execution_completed"] and checks["physically_valid"]
                              and all(v == "success" for v in checks["group_results"].values())
                              and checks["order_monitoring_feint_intrusion"])
        attempt.update(checks=checks, result="PASS" if checks["all_pass"] else "CHECK_FAILED")
        report["attempts"].append(attempt)
        if not checks["all_pass"]:
            log(f"核对未通过：{checks}")
            continue
        out.mkdir(parents=True, exist_ok=True)
        write_episode(out / "episode", scene, family, sk, run, labels, frame, delays, "synchronous",
                      rehearsal["core_times_s"], timing_plan=plan, scope=SCOPE)
        report["result"] = "PASS"
        report["wall_s"]["total"] = time.perf_counter() - t_all
        save(out / "showcase_report.json", report)
        log(f"完成：{out / 'episode'}；各组开始执行任务时刻 {starts}；总用时 {report['wall_s']['total']:.0f} s")
        log("下一步：python -B scripts/viz/animate_v07.py single --episode \"" + str(out / "episode") + "\" --name " + args.name)
        return 0
    report["result"] = "NO_CANDIDATE_PASSED"
    report["wall_s"]["total"] = time.perf_counter() - t_all
    save(out / "showcase_report.json", report)
    raise SystemExit(f"前 {args.max_candidates} 个候选都未通过，详见 {out / 'showcase_report.json'}")


if __name__ == "__main__":
    sys.exit(main())
