"""V8-01 §5.2：把 out/rerun/s52_*_r3/stage_timing.json（主）与 s52_*/stage_timing.json（重复测量）整理为 stage_timing.md。

用法: python -B v8_01_stage_report.py <out_dir>
"""
import csv
import json
import os
import sys

INTENTS = ["transit", "reconnaissance", "monitoring", "feint", "penetration"]


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def inc(stats, label, parents=None):
    s = stats.get(label)
    if not s:
        return 0.
    if parents is None:
        return s["inclusive_s"]
    bp = s.get("by_parent", {})
    return sum(v["inclusive_s"] for p, v in bp.items() if p in parents)


def calls(stats, label):
    return stats.get(label, {}).get("calls", 0)


B_ROWS = [
    ("可行空间/TaskSpec", ["B 可行空间 free_space", "B 作业区域 work_region", "B TaskSpec/公开分股 build_spec"]),
    ("作业形态生成", ["B 作业形态 draw_shape"]),
    ("衔接段（进场+撤离+作业段连接）", ["B 衔接段 route_group"]),
    ("  其中 进场 _approaches", ["B 进场 _approaches"]),
    ("  其中 撤离点 retreat_endpoint（非过境）", ["B 撤离点 retreat_endpoint"]),
    ("  其中 作业段内连接 connect（非过境）", ["B 作业段内连接 connect"]),
    ("整航线检查 plan_checks", ["B 整航线检查 plan_checks"]),
    ("既有输出预检 precheck", ["B 既有输出预检 precheck"]),
    ("骨架装配 assemble_skeleton", ["B 骨架装配 assemble_skeleton"]),
    ("多组组合（方位+装配+长度比）", ["B 多股协调-同目标方位 bearing_allowed", "B 多组装配 assemble_episode", "B 同向长度比筛选 choose_eligible"]),
    ("写盘（planning_result/status）", ["B 写盘 write_json", "B 写状态 _write_status"]),
]
B_TOP = ["B 规划入口 episode_candidate_pool", "B 写盘 write_json", "B 写状态 _write_status"]


def b_rows(stats, total):
    rows = []
    for name, labels in B_ROWS:
        t = sum(inc(stats, l) for l in labels)
        n = sum(calls(stats, l) for l in labels)
        rows.append((name, t, n))
    covered = sum(inc(stats, l) for l in B_TOP)
    rows.append(("其余（场景加载、pickle 写盘、提案池循环本身等）", total - covered, None))
    return rows


def c_rows(stats, total):
    audit = "C 独立审计 audit_episode"
    wr = "C 判定+写盘+审计 write_result"
    top = [None]
    rows = [
        ("单机预演 rehearse", inc(stats, "C 单机预演 rehearse"), calls(stats, "C 单机预演 rehearse")),
        ("  其中 单机仿真 execute(solo)", inc(stats, "C 单机仿真 execute(solo)"), calls(stats, "C 单机仿真 execute(solo)")),
        ("  其中 单机判定 measure(solo)", inc(stats, "C 单机判定 measure(solo)"), calls(stats, "C 单机判定 measure(solo)")),
        ("时刻安排 select_timing（含 2 m 间距检查）", inc(stats, "C 时刻安排 select_timing"), calls(stats, "C 时刻安排 select_timing")),
        ("联合仿真 execute(joint)", inc(stats, "C 联合仿真 execute(joint)"), calls(stats, "C 联合仿真 execute(joint)")),
        ("判定与标签 measure（labels.json）", inc(stats, "C 判定与标签 measure", [wr]), None),
        ("独立审计 audit_episode（含复算/列置换/前缀标签 3 次 measure）", inc(stats, audit), calls(stats, audit)),
        ("  其中 审计内 measure", inc(stats, "C 判定与标签 measure", [audit]), None),
        ("  其中 audit_groups（independent_exact_audit）", inc(stats, "C 独立审计 audit_groups"), calls(stats, "C 独立审计 audit_groups")),
        ("  其中 回读 load_episode", inc(stats, "C 回读 load_episode"), calls(stats, "C 回读 load_episode")),
        ("半程截断检查 group_truncations", inc(stats, "C 半程截断检查 group_truncations"), None),
        ("写盘 write_episode（csv/npz/json）", inc(stats, "C 写盘 write_episode"), None),
        ("写盘 save_json（审计外）", inc(stats, "C 写盘 save_json", ["None", wr]), calls(stats, "C 写盘 save_json")),
        ("速度剖面 QC qc_episode", inc(stats, "C 速度剖面QC qc_episode"), None),
        ("叠加预测误差 prediction_error", inc(stats, "C 叠加预测误差 prediction_error"), None),
    ]
    covered = sum(inc(stats, l, ["None"]) for l in ["C 单机预演 rehearse", "C 时刻安排 select_timing", "C 联合时限 joint_budget",
                                                     "C 联合仿真 execute(joint)", "C 叠加预测误差 prediction_error", wr,
                                                     "C 写盘 save_json", "C 速度剖面QC qc_episode"])
    rows.append(("其余（候选池载入、单机 npz 写盘、目录创建等）", total - covered, None))
    return rows


def main():
    out = sys.argv[1]
    rerun = os.path.join(out, "rerun")
    rec = {}
    for r in csv.DictReader(open(os.path.join(out, "timing_records.csv"), encoding="utf-8")):
        rec[(r["run_id"], r["skeleton_id"], r["stage"], r["mode"])] = r
    md = ["# V8-01 §5.2 分环节计时", "",
          "驱动：`scripts/v8_01_driver.py sample`（规划阶段直接调用 `worker_b`；仿真阶段按 `run_episode_job` 步骤只跑同步方式）；"
          "并行：`scripts/v8_01_orchestrate.py`。计时包装装在调用方查找函数的模块命名空间上（清单见各样本 `stage_timing.json` 的 `installed`）。",
          "主数据为第 3 轮（r3，`out/rerun/s52_<意图>_r3/`，按调用方拆分耗时）；第 2 轮（r2，`out/rerun/s52_<意图>/`）作为重复测量只列合计。"
          " 第 1 轮因隔离目录缺 `qc/` 子目录在最后一步报错，未计入（`out/rerun/_attempt1_qc_dir_bug/`）。",
          "运行环境：5 个样本进程同时运行（r2 时另有 1–2 个剖析进程），每进程单线程（OMP/OPENBLAS/MKL=1）；原记录是 14 进程并行时的耗时。", ""]
    summary = []
    details = []
    for intent in INTENTS:
        d3 = load(os.path.join(rerun, f"s52_{intent}_r3", "stage_timing.json"))
        d2 = load(os.path.join(rerun, f"s52_{intent}", "stage_timing.json"))
        d = d3 or d2
        if d is None:
            summary.append([intent, "未运行"] + [""] * 12)
            continue
        run, sid = d["run_id"], d["skeleton_id"]
        b_rec = rec.get((run, sid, "B", ""), {})
        s_rec = rec.get((run, sid, "C", "synchronous"), {})
        b = (d.get("B") or {}).get("planning_wall_s")
        c = d.get("C_synchronous") or {}
        ctot = c.get("c_stage_wall_s")
        joint = (d.get("extra") or {}).get("joint_execute", [{}])[-1] if (d.get("extra") or {}).get("joint_execute") else {}
        solo = (d.get("extra") or {}).get("solo_execute", {})
        orig_setup = 2 * float(s_rec["amortized_skeleton_setup_s"]) if s_rec.get("amortized_skeleton_setup_s") else None
        orig_c = (float(s_rec["simulation_wall_s"]) + orig_setup + float(s_rec["episode_postprocess_wall_s"])) if orig_setup is not None else None
        b2 = ((d2 or {}).get("B") or {}).get("planning_wall_s")
        c2 = ((d2 or {}).get("C_synchronous") or {}).get("c_stage_wall_s")
        summary.append([intent, f"{run}/{sid}", c.get("n_agents", s_rec.get("n_agents")), c.get("n_task_groups", s_rec.get("n_task_groups")),
                        f"{b:.1f}" if b else "—", f"{float(b_rec['planning_wall_s']):.1f}" if b_rec else "—",
                        f"{ctot:.1f}" if ctot else "—", f"{orig_c:.1f}" if orig_c else "—",
                        f"{c.get('simulation_wall_s', 0):.1f}", f"{float(s_rec['simulation_wall_s']):.1f}" if s_rec else "—",
                        f"{c.get('setup_s', 0):.1f}", f"{orig_setup:.1f}" if orig_setup else "—",
                        f"{b2:.1f} / {c2:.1f}" if b2 and c2 else "—",
                        f"{d.get('output_bytes', {}).get('episode_synchronous_dir', 0) / 1e6:.1f}"])
        stats = d["stats"]
        details += [f"## {intent}：`{run}` / `{sid}`", "",
                    f"机数 {c.get('n_agents')}，任务组数 {c.get('n_task_groups')}；选中候选 {c.get('selected_candidate_index')}，"
                    f"试过 {c.get('geometry_variants_tried')} 个候选；仿真时长 {c.get('sim_duration_s')} s；执行状态 {c.get('execution_status')}；"
                    f"任务结果 {c.get('task_result')}；是否完整结束：{d.get('complete')}。", "",
                    "### 规划阶段（占 B 合计 `planning_wall_s` 的比例）", "",
                    "| 环节 | 耗时 s | 占比 | 调用次数 |", "|---|---|---|---|"]
        for name, t, n in b_rows(stats, b or 0.):
            details.append(f"| {name} | {t:.2f} | {t / b:.1%} | {'' if n is None else n} |" if b else f"| {name} | — | — | |")
        details += ["", "### 仿真阶段（同步方式；占 C 合计的比例）", "",
                    "| 环节 | 耗时 s | 占比 | 调用次数 |", "|---|---|---|---|"]
        for name, t, n in c_rows(stats, ctot or 0.):
            details.append(f"| {name} | {t:.2f} | {t / ctot:.1%} | {'' if n is None else n} |" if ctot else f"| {name} | — | — | |")
        uncalled = sorted({i["label"] for i in d["installed"]} - set(stats))
        details += ["", f"联合仿真：{joint.get('steps')} 步 × {joint.get('agents')} 机，{joint.get('rollbacks')} 次回滚，"
                        f"{joint.get('wall_s', 0):.2f} s → 每步每机 {joint.get('wall_s', 0) / max(1, (joint.get('steps') or 1) * (joint.get('agents') or 1)) * 1e6:.1f} µs。"
                        f" 单机预演：{solo.get('calls')} 次单机仿真共 {solo.get('steps')} 步，{solo.get('wall_s', 0):.2f} s → 每步 "
                        f"{solo.get('wall_s', 0) / max(1, solo.get('steps') or 1) * 1e6:.1f} µs。",
                    f"写盘字节数：planning {d.get('output_bytes', {}).get('planning')}，episodes 合计 {d.get('output_bytes', {}).get('episodes')}"
                    f"（其中同步方式目录 {d.get('output_bytes', {}).get('episode_synchronous_dir')}），qc {d.get('output_bytes', {}).get('qc')}。",
                    f"调用次数为 0（未计时成功）的包装：{', '.join(uncalled) if uncalled else '无'}"
                    "（均为该样本执行方式用不到的分支函数）。", ""]
    md += ["## 1. 每个样本一行", "",
           "| 意图 | 批次/骨架 | 机数 | 组数 | B 重跑 s | B 原记录 s | C同步 重跑合计 s | C同步 原记录 s（仿真+2×摊分准备+后处理） | 联合仿真 重跑 s | 联合仿真 原记录 s | 准备 重跑 s | 准备 原记录 s | r2 重复：B / C 合计 s | 同步方式目录 MB |",
           "|" + "---|" * 14, *["| " + " | ".join(str(x) for x in r) + " |" for r in summary], "",
           "原记录列取自 `timing_records.csv`（`planning_wall_s`、同步行 `simulation_wall_s`、`2×amortized_skeleton_setup_s`、`episode_postprocess_wall_s`）。"
           " 重跑的\"C同步合计\"含候选池载入、单机预演、时刻安排、同步方式联合仿真、判定/审计/写盘与 qc；不含递次方式。", "",
           *details]
    with open(os.path.join(out, "stage_timing.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print("ok")


if __name__ == "__main__":
    main()
