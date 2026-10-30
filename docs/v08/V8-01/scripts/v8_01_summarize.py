"""V8-01 §3.2/§3.4：由 timing_records.csv 与 rerun/scan_raw.json 生成汇总（只读，纯统计）。

输出：timing_summary.md、rejection_skeleton_level.md、rejection_samples.md、sim_failures.md
用法: python -B v8_01_summarize.py <out_dir>
"""
import collections
import csv
import json
import math
import os
import statistics
import sys

INTENTS = ["transit", "reconnaissance", "monitoring", "feint", "penetration"]
BUCKETS = [("4–5", 4, 5), ("6–8", 6, 8), ("9–12", 9, 12)]
DATA_ROOT = r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData"


def f(x):
    return float(x) if x not in ("", None) else None


def pct(values, q):
    v = sorted(values)
    if not v:
        return None
    k = (len(v) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def fmt(x, nd=1):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:,.{nd}f}"
    return str(x)


def stat_row(values):
    if not values:
        return ["0", "—", "—", "—", "—", "—"]
    return [str(len(values)), fmt(statistics.median(values)), fmt(pct(values, .9)), fmt(pct(values, .99)),
            fmt(max(values)), fmt(sum(values) / 3600, 2)]


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main():
    out_dir = sys.argv[1]
    rows = list(csv.DictReader(open(os.path.join(out_dir, "timing_records.csv"), encoding="utf-8")))
    raw = json.load(open(os.path.join(out_dir, "rerun", "scan_raw.json"), encoding="utf-8"))
    B = [r for r in rows if r["stage"] == "B"]
    C = [r for r in rows if r["stage"] == "C"]
    c_skel = {}
    for r in C:
        c_skel[(r["run_id"], r["skeleton_id"])] = r
    md = ["# V8-01 §3.2 耗时汇总", "",
          "由 `scripts/v8_01_scan_records.py`（扫描）与 `scripts/v8_01_summarize.py`（统计）生成；逐条记录见 `timing_records.csv`。",
          "范围：`v07_first_edition` 下 9 个批次全部记录（含 `pilot_f000_005`，其代码提交为 `debfadf6`，其余为 `641a9b3a`；单独列出见 §6）。"
          " 不含 `prod_f060_100/_aborted`、`prod_f100_140/_aborted` 中被续跑挪走的半成品（这两个目录里的耗时没有进入任何 status 文件）。", "",
          "## 0. 口径", "",
          "- **规划耗时**：`status/B__*.json` 的 `planning_wall_s`（秒，按骨架；`time.monotonic`，`run_v07_fe_production.py:323-342`）。",
          "- **仿真耗时按方式分开记录**，因此没有合并为 `both`：`status/C__*.json` 的 `detail.rows[]` 对每个方式记 `simulation_wall_s`"
          "（联合仿真 `execute` 本身）、`amortized_skeleton_setup_s`（骨架级准备耗时的一半，`run_v07_s2_episode_batch.py:154` 写死 `setup_s / 2`）、"
          "`episode_postprocess_wall_s`（判定+写盘+审计，`write_result`）。骨架级另有 `elapsed_wall_s`（整个 C 进程任务，含两个方式、配对检查与 QC）。",
          "- **本文的\"同步仿真耗时\"** = 同步方式行的 `simulation_wall_s`（只含联合仿真）。§5.2 选样即用此值；§5.2 的时间上限另用"
          "\"B + 同步方式的仿真 + 2×摊分准备 + 后处理\"，原因见报告。",
          "- **C 阶段全部耗时** = 骨架级 `elapsed_wall_s`；它与两个方式三项之和的差，是配对检查 `pair_result` 与 `qc_episode` 等（见 §5）。",
          "- 所有耗时都是 14 个进程并行时的单进程墙钟。", ""]
    # ---- 1. 按意图 × 阶段
    md += ["## 1. 按意图 × 阶段（全部记录，单位秒；合计为小时）", ""]
    hdr = ["意图", "阶段/字段", "条数", "中位数", "p90", "p99", "最大", "合计 h"]
    trs = []
    for intent in INTENTS:
        b = [f(r["planning_wall_s"]) for r in B if r["intent"] == intent and f(r["planning_wall_s"]) is not None]
        trs.append([intent, "B 规划 planning_wall_s", *stat_row(b)])
        for mode in ("synchronous", "sequential"):
            sim = [f(r["simulation_wall_s"]) for r in C if r["intent"] == intent and r["mode"] == mode and f(r["simulation_wall_s"]) is not None]
            trs.append([intent, f"C {mode} simulation_wall_s", *stat_row(sim)])
            post = [f(r["episode_postprocess_wall_s"]) for r in C if r["intent"] == intent and r["mode"] == mode and f(r["episode_postprocess_wall_s"]) is not None]
            trs.append([intent, f"C {mode} episode_postprocess_wall_s", *stat_row(post)])
        setup = [2 * f(r["amortized_skeleton_setup_s"]) for r in C if r["intent"] == intent and r["mode"] == "synchronous" and f(r["amortized_skeleton_setup_s"]) is not None]
        trs.append([intent, "C 骨架准备 2×amortized_skeleton_setup_s", *stat_row(setup)])
        el = [f(r["c_skeleton_elapsed_wall_s"]) for (k, r) in c_skel.items() if r["intent"] == intent and f(r["c_skeleton_elapsed_wall_s"]) is not None]
        trs.append([intent, "C 骨架合计 elapsed_wall_s", *stat_row(el)])
    md += [table(hdr, trs), "",
           "说明：C 行只包括进入仿真阶段的骨架（抽签 5 个意图都 B 通过才进入 C，`run_v07_fe_production.py:497-515`）。"
           " 三项方式级耗时只在进入联合仿真的行上有记录（几何/预演/时刻阶段耗尽的行缺这三项，见 §5）。", ""]
    # 准备/仿真/后处理占比
    md += ["### 1.1 仿真阶段内部占比（按意图，全部有三项记录的骨架之和）", ""]
    rs = []
    for intent in INTENTS:
        sims = posts = setups = el = 0.
        n = 0
        for (k, r) in c_skel.items():
            if r["intent"] != intent:
                continue
            rows2 = [x for x in C if (x["run_id"], x["skeleton_id"]) == k]
            if any(f(x["simulation_wall_s"]) is None for x in rows2) or len(rows2) != 2:
                continue
            n += 1
            sims += sum(f(x["simulation_wall_s"]) for x in rows2)
            posts += sum(f(x["episode_postprocess_wall_s"]) for x in rows2)
            setups += sum(f(x["amortized_skeleton_setup_s"]) for x in rows2)
            el += f(rows2[0]["c_skeleton_elapsed_wall_s"])
        other = el - sims - posts - setups
        rs.append([intent, n, fmt(el / 3600, 2), f"{setups / el:.1%}", f"{sims / el:.1%}", f"{posts / el:.1%}", f"{other / el:.1%}"])
    md += [table(["意图", "骨架数", "C 合计 h", "准备（预演+时刻+候选池载入+写盘）", "联合仿真（两方式）", "后处理（两方式）", "其余（配对检查、QC 等）"], rs), ""]
    # 规划内部：group geometry vs combination
    md += ["### 1.2 规划阶段内部（只有进入 C 的骨架在 `episodes/<sk>/candidate_search.json` 留有分项，单位秒）", ""]
    rs = []
    for intent in INTENTS:
        sub = [r for r in B if r["intent"] == intent and f(r["b_group_search_wall_s_sum"]) is not None]
        pw = sum(f(r["planning_wall_s"]) for r in sub)
        gw = sum(f(r["b_group_search_wall_s_sum"]) for r in sub)
        cw = sum(f(r["b_combination_search_wall_s"]) or 0. for r in sub)
        ph = sum(f(r["b_phase_search_wall_s_sum"]) or 0. for r in sub)
        rs.append([intent, len(sub), fmt(pw / 3600, 2), f"{gw / pw:.1%}", f"{cw / pw:.2%}", f"{ph / pw:.1%}", f"{(pw - gw - cw) / pw:.1%}"])
    md += [table(["意图", "骨架数", "planning_wall_s 合计 h", "各组提案池 wall_s", "组合搜索 wall_s", "phase_search（unified 后端恒为 0）", "其余（场景加载、pickle 写盘等）"], rs), "",
           "`group_search_metrics.*.wall_s` 与 `geometry_wall_s` 在 unified 后端是同一个值（`task_v07/unified/adapter.py:58-61`），"
           "其中形态、衔接、整航线检查各占多少没有分别记录。", ""]
    # ---- 2. 机数分档
    md += ["## 2. 按机数分档 × 意图：同步仿真耗时中位数（`simulation_wall_s`，秒；括号内为条数）", ""]
    rs = []
    for intent in INTENTS:
        row = [intent]
        for name, lo, hi in BUCKETS:
            v = [f(r["simulation_wall_s"]) for r in C if r["intent"] == intent and r["mode"] == "synchronous"
                 and f(r["simulation_wall_s"]) is not None and lo <= int(r["n_agents"]) <= hi]
            row.append(f"{fmt(statistics.median(v)) if v else '—'} ({len(v)})")
        rs.append(row)
    md += [table(["意图", *[b[0] for b in BUCKETS]], rs), ""]
    rs = []
    for intent in INTENTS:
        row = [intent]
        for name, lo, hi in BUCKETS:
            v = [f(r["planning_wall_s"]) for r in B if r["intent"] == intent and lo <= int(r["n_agents"]) <= hi]
            row.append(f"{fmt(statistics.median(v)) if v else '—'} ({len(v)})")
        rs.append(row)
    md += ["同一分档的规划耗时中位数（秒）：", "", table(["意图", *[b[0] for b in BUCKETS]], rs), ""]
    # ---- 3. 白费的时间
    md += ["## 3. 白费的时间", "",
           "全部记录耗时 = Σ`planning_wall_s` + Σ骨架级 C `elapsed_wall_s`。三类（同一条耗时只计一次，取并集）：",
           "(a) B 为 REJECT/TIMEOUT/ERROR 的规划耗时；(b) 抽签最终未保留（`draw_status` ≠ RETAINED）的骨架的全部规划与仿真耗时；"
           "(c) C 为 NOT_PAIRED/TIMEOUT/ERROR 的仿真耗时。全部批次中没有 TIMEOUT 或 ERROR 状态。", ""]
    rs = []
    tot_all = tot_waste = 0.
    agg = collections.Counter()
    for intent in INTENTS + ["合计"]:
        tot = a = b = c = u = 0.
        for r in B:
            if intent != "合计" and r["intent"] != intent:
                continue
            w = f(r["planning_wall_s"]) or 0.
            tot += w
            ina = r["status"] != "PASS"
            inb = r["draw_status"] != "RETAINED"
            a += w if ina else 0.
            b += w if inb else 0.
            u += w if (ina or inb) else 0.
        for (k, r) in c_skel.items():
            if intent != "合计" and r["intent"] != intent:
                continue
            w = f(r["c_skeleton_elapsed_wall_s"]) or 0.
            tot += w
            inb = r["draw_status"] != "RETAINED"
            inc = r["status"] != "PAIRED"
            b += w if inb else 0.
            c += w if inc else 0.
            u += w if (inb or inc) else 0.
        rs.append([intent, fmt(tot / 3600, 1), f"{a / tot:.1%}", f"{b / tot:.1%}", f"{c / tot:.1%}", f"{u / tot:.1%}", fmt(u / 3600, 1)])
    md += [table(["意图", "全部记录耗时 h", "(a) B 拒绝的规划", "(b) 未保留抽签的全部", "(c) C 未配对的仿真", "并集占比", "并集 h"], rs), "",
           "(a) 与 (c) 的骨架所在抽签必然未保留，因此并集等于 (b)。", ""]
    # 细分 (b)
    rs = []
    for intent in INTENTS:
        parts = collections.Counter()
        for r in B:
            if r["intent"] == intent and r["draw_status"] != "RETAINED":
                parts[f"B {r['status']} / 抽签 {r['draw_status']}"] += f(r["planning_wall_s"]) or 0.
        for (k, r) in c_skel.items():
            if r["intent"] == intent and r["draw_status"] != "RETAINED":
                parts[f"C {r['status']} / 抽签 {r['draw_status']}"] += f(r["c_skeleton_elapsed_wall_s"]) or 0.
        for key, v in sorted(parts.items()):
            rs.append([intent, key, fmt(v / 3600, 2)])
    md += ["(b) 的组成（小时）：", "", table(["意图", "记录类别", "耗时 h"], rs), ""]
    # ---- 4. 口径对账
    md += ["## 4. 口径对账（诊断项）", ""]
    rs = []
    s_rec = s_stats = 0.
    for run in raw["stats_total_wall_s"]:
        rec = sum(f(r["planning_wall_s"]) or 0. for r in B if r["run_id"] == run)
        rec += sum(f(r["c_skeleton_elapsed_wall_s"]) or 0. for (k, r) in c_skel.items() if r["run_id"] == run)
        st = raw["stats_total_wall_s"][run]
        s_rec += rec
        s_stats += st
        rs.append([run, raw["workers"][run], fmt(rec / 3600, 2), fmt(rec / raw["workers"][run] / 3600, 2), fmt(st / 3600, 2),
                   f"{rec / raw['workers'][run] / st:.3f}"])
    rs.append(["合计", 14, fmt(s_rec / 3600, 2), fmt(s_rec / 14 / 3600, 2), fmt(s_stats / 3600, 2), f"{s_rec / 14 / s_stats:.3f}"])
    md += [table(["批次", "并行数", "记录耗时之和 h", "÷ 并行数 h", "stats.json total_wall_s h", "比值"], rs), "",
           "`total_wall_s` 由 `scripts/v07_fe_production_core.py` 的 `build_stats` 计算（未进一步核对其定义）。不一致不作解释。", ""]
    # ---- 5. 有记录缺失的 C 行
    md += ["## 5. 无仿真耗时字段的 C 行", "",
           f"共 {len(raw['c_rows_without_timing'])} 行（均为 `state` = infeasible 的方式行：几何/预演/时刻阶段耗尽，未进入联合仿真，"
           "`run_v07_s2_episode_batch.py:32-42` 的 `rejected()` 不写耗时字段）。这些骨架只有骨架级 `elapsed_wall_s`。", ""]
    cnt = collections.Counter((x["state"], x["reason"]) for x in raw["c_rows_without_timing"])
    md += [table(["state", "reason", "行数"], [[k[0], k[1], v] for k, v in sorted(cnt.items())]), ""]
    # ---- 6. pilot_f000_005
    md += ["## 6. `pilot_f000_005`（代码提交 debfadf6）单列", ""]
    rs = []
    for intent in INTENTS:
        b = [f(r["planning_wall_s"]) for r in B if r["intent"] == intent and r["run_id"] == "pilot_f000_005"]
        s = [f(r["simulation_wall_s"]) for r in C if r["intent"] == intent and r["run_id"] == "pilot_f000_005" and r["mode"] == "synchronous" and f(r["simulation_wall_s"]) is not None]
        rs.append([intent, len(b), fmt(statistics.median(b)) if b else "—", len(s), fmt(statistics.median(s)) if s else "—"])
    md += [table(["意图", "B 条数", "B 中位数 s", "同步仿真条数", "同步仿真中位数 s"], rs), "",
           "以上 §1–§4 的统计都包含该批。", ""]
    # ---- 7. 输出体积
    md += ["## 7. 输出体积（字节，按意图，全部批次合计）", ""]
    vol = collections.Counter()
    for run, d in raw["volume"].items():
        for k, v in d.items():
            vol[k] += v
    rs = []
    for intent in INTENTS:
        n_mode = sum(1 for r in C if r["intent"] == intent and f(r["episode_dir_bytes"]) is not None)
        md_bytes = vol.get(f"episode_mode_dir|{intent}", 0)
        rs.append([intent, fmt(vol.get(f"planning|{intent}", 0) / 1e9, 2), fmt(vol.get(f"episode_skeleton_aux|{intent}", 0) / 1e9, 2),
                   fmt(md_bytes / 1e9, 2), n_mode, fmt(md_bytes / max(n_mode, 1) / 1e6, 1), fmt(vol.get(f"qc|{intent}", 0) / 1e6, 1)])
    md += [table(["意图", "planning/ GB", "episodes/<sk> 方式目录以外 GB（geometry_XX、candidate_search.json 等）",
                  "方式目录 GB", "方式目录数", "每个方式目录 MB", "qc/ MB"], rs), ""]
    with open(os.path.join(out_dir, "timing_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    # ================= §3.4 失败细节
    rej = raw["b_reject"]
    md = ["# V8-01 §3.4 失败细节", "", "数据：`status/B__*.json`、`planning/<sk>/planning_result.json`、`status/C__*.json`（全部 9 批，只读）。", "",
          "## 1. 规划失败：骨架级最终原因", "",
          "B 为 REJECT 的骨架都只有 `planning_result.json`（候选池为空时 `worker_b` 不写 `candidate_pool.pkl`，"
          "`run_v07_fe_production.py:328`），其中只有按原因计数的汇总（`rejection_reasons` = 组提案级 + 组合级），没有逐候选记录。"
          " 每个骨架的终止分类都在 `termination`。", ""]
    by_int = collections.defaultdict(collections.Counter)
    term = collections.defaultdict(collections.Counter)
    dominant = collections.defaultdict(collections.Counter)
    allzero = collections.defaultdict(collections.Counter)
    for x in rej:
        pr = x["planning_result"] or {}
        gr = pr.get("group_rejection_reasons", {})
        cr = pr.get("combination_rejection_reasons", {})
        for k, v in gr.items():
            by_int[x["intent"]][("组提案", k)] += v
        for k, v in cr.items():
            by_int[x["intent"]][("组合", k)] += v
        t = pr.get("termination") or {}
        term[x["intent"]][f"{t.get('classification')}/{t.get('reason')}"] += 1
        allr = {**{("组提案", k): v for k, v in gr.items()}, **{("组合", k): v for k, v in cr.items()}}
        if allr:
            top = max(allr.items(), key=lambda kv: kv[1])[0]
            dominant[x["intent"]][f"{top[0]}:{top[1]}"] += 1
        # REJECT 且没有任何组合级记录 ⇒ 组合笛卡尔积为 0 ⇒ 至少一个组的提案池为空
        zero_group = not cr
        allzero[x["intent"]]["存在提案池为空的组（组合次数 0）" if zero_group else "各组均有可行提案，组合阶段被拒"] += 1
    rs = []
    for intent in INTENTS:
        n = sum(1 for x in rej if x["intent"] == intent)
        rs.append([intent, n, "; ".join(f"{k} {v}" for k, v in term[intent].most_common()),
                   "; ".join(f"{k} {v}" for k, v in dominant[intent].most_common()),
                   "; ".join(f"{k} {v}" for k, v in allzero[intent].most_common())])
    md += [table(["意图", "B REJECT 骨架数", "termination（分类/原因）", "骨架内计数最多的原因（骨架数）", "失败层级"], rs), "",
           "失败层级的判定：REJECT 且 `combination_rejection_reasons` 为空，说明没有做过任何组合（组合笛卡尔积为 0，"
           "`group_candidate_pool.py:108` 的 `combination_indices` 返回空），即至少一个组的 200 个提案全部被拒；否则为组合阶段被拒。", "",
           "### 1.1 骨架级拒绝原因计数（REJECT 骨架内的候选/组合尝试次数之和，按意图）", "",
           "与验收报告第 5 节的候选级统计并列使用：这里只统计 B 为 REJECT 的骨架；验收报告的候选级统计覆盖全部骨架。", ""]
    reasons = sorted({k for i in INTENTS for k in by_int[i]})
    rs = [[f"{lvl}:{r}", *[by_int[i].get((lvl, r), 0) for i in INTENTS]] for lvl, r in reasons]
    md += [table(["层级:原因", *INTENTS], rs), ""]
    # 候选级环节计数（进入 C 的骨架）
    md += ["### 1.2 参照：进入 C 的骨架（B 为 PASS）在 `candidate_search.json` 中的逐候选环节/原因计数", "",
           "`stage` 是 `task_v07/unified/adapter.py:23-50` 写入的构造环节：shape（作业形态）→ connection（衔接段）→ whole_route（整航线检查）→ group_feasible。", ""]
    keys = sorted({k for i in INTENTS for k in raw["candidate_stage_counts"].get(i, {})})
    rs = [[k.replace("|", " / "), *[raw["candidate_stage_counts"].get(i, {}).get(k, 0) for i in INTENTS]] for k in keys]
    md += [table(["stage / reason", *INTENTS], rs), ""]
    # 抽样
    md += ["## 2. 抽样细看", "", "见 `rejection_samples.md`。", ""]
    # C 失败
    md += ["## 3. 仿真阶段失败（全部 C 为 NOT_PAIRED 的骨架）", ""]
    cnp = raw["c_not_paired"]
    cnt = collections.Counter()
    for x in cnp:
        ff = x["first_failure"] or {}
        failing = [r for r in x["rows"] if r["state"] != "generated" or r["execution_status"] != "completed" or r["all_groups_complete"] is not True]
        modes = "+".join(r["mode"] for r in failing) or "—"
        cnt[(x["intent"], ff.get("stage"), str(ff.get("reason")) if not isinstance(ff.get("reason"), (dict, list)) else "M1 组条件未满足", modes)] += 1
    rs = [[k[0], k[1], k[2], k[3], v] for k, v in sorted(cnt.items())]
    md += [f"共 {len(cnp)} 个骨架。`first_failure` 由 `scripts/run_m3_r3_r4.py:68-87` 的 `pair_result` 按行顺序（同步在前）取第一处失败。"
           " \"失败方式\"列出该骨架中所有未成功的方式行。", "",
           table(["意图", "first_failure.stage", "first_failure.reason", "失败方式", "骨架数"], rs), "",
           "逐骨架明细：", ""]
    rs = []
    for x in sorted(cnp, key=lambda x: (x["intent"], x["skeleton_id"])):
        ff = x["first_failure"] or {}
        detail = []
        for r in x["rows"]:
            bits = [r["mode"], f"state={r['state']}", f"exec={r['execution_status']}", f"groups_complete={r['all_groups_complete']}"]
            if r.get("geometry_attempt_categories"):
                bits.append("geometry_attempts=" + ",".join(str(c) for c in r["geometry_attempt_categories"]))
            if r.get("failed_groups"):
                conds = []
                for g, res in r["failed_groups"].items():
                    bad = [k for k, v in ((res or {}).get("conditions") or {}).items() if v is not True]
                    conds.append(f"{g}:{'/'.join(bad) or (res or {}).get('status')}")
                bits.append("failed=" + ";".join(conds))
            detail.append(" ".join(bits))
        reason = ff.get("reason")
        reason = "M1 组条件未满足" if isinstance(reason, (dict, list)) else reason
        rs.append([x["intent"], x["status_path"], x["n_agents"], x["n_task_groups"], ff.get("stage"), reason, fmt(f(x["elapsed_wall_s"])), "<br>".join(detail)])
    md += [table(["意图", "status 文件", "机数", "组数", "stage", "reason", "C 耗时 s", "各方式"], rs), ""]
    with open(os.path.join(out_dir, "failures.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    # ================= §3.4.2 抽样
    md = ["# V8-01 §3.4.2 规划拒绝抽样", "",
          "每个意图取 10 个 B 为 REJECT 的骨架：全部批次合并，按 `skeleton_id` 排序后等间隔抽取（下标 round(i·(n−1)/9)，i=0..9）。", "",
          "**文件中没有逐候选的环节信息**：REJECT 骨架只留下 `planning_result.json`（逐候选的 `candidates[]` 只写在 `candidate_search` 报告里，"
          "该报告只随 `candidate_pool.pkl` 保存，而候选池为空时不写 pickle）。因此\"每个候选失败在哪个构造环节\"一栏记为\"未记录\"；"
          "下表给出文件中实际有的按原因计数，并按 §4.2 的代码对应关系注明每个原因所属的构造环节。", "",
          "原因 → 环节（代码位置见 code_map.md §4.2）：`shape_search_budget_exhausted`/`patrol_band_too_narrow` → 作业形态；"
          "`connection_search_budget_exhausted` → 衔接段（进场/撤离/作业段连接）；`whole_route_check`/`existing_output_precheck` → 整航线检查；"
          "`same_target_work_area_bearing` → 多组组合（同目标方位）；`approach_length_ratio_exceeded` → 同向长度比筛选。", "",
          "搜索预算（代码常量，记录中的 `candidate_budget` 不存在于 planning_result.json）：每组 200 个提案（`candidate_search.py:18` CANDIDATE_BUDGET）、"
          "组合 1000（`group_candidate_pool.py:14`）、每个提案内形态 20 次（`shape_attempts`）、衔接 10 次（`connection_attempts`）。", ""]
    rs = []
    for intent in INTENTS:
        items = sorted((x for x in rej if x["intent"] == intent), key=lambda x: x["skeleton_id"])
        n = len(items)
        picks = sorted({round(i * (n - 1) / 9) for i in range(10)}) if n >= 10 else list(range(n))
        for idx in picks:
            x = items[idx]
            pr = x["planning_result"] or {}
            gr = pr.get("group_rejection_reasons", {})
            cr = pr.get("combination_rejection_reasons", {})
            attempts = sum(gr.values()) + sum(cr.values())
            rs.append([intent, x["run_id"], x["skeleton_id"], x["n_agents"], x["n_task_groups"], sum(gr.values()), sum(cr.values()),
                       "; ".join(f"{k} {v}" for k, v in gr.items()) or "—", "; ".join(f"{k} {v}" for k, v in cr.items()) or "—",
                       "未记录", (pr.get("termination") or {}).get("reason"), fmt(f(x["planning_wall_s"]))])
    md += [table(["意图", "批次", "skeleton_id", "机数", "组数", "组提案被拒数", "组合被拒数", "组提案原因计数", "组合原因计数",
                  "逐候选环节", "termination.reason", "规划耗时 s"], rs), "",
           "\"组提案被拒数\"即尝试过的提案数中被拒的部分；REJECT 骨架的可行提案数 = 组数×200 − 组提案被拒数（若大于 0，则失败在组合阶段）。", ""]
    with open(os.path.join(out_dir, "rejection_samples.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    print("ok")


if __name__ == "__main__":
    main()
