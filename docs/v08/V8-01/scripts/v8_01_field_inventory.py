"""V8-01 §3.1: 以 prod_f020_060 为例打印各记录文件的键结构（只读）。

嵌套键全部列出；数组只展开第一个元素；形如 uav_01 / facility_01 / task_group_01 的
同类编号键只展开第一个，并注明同类键个数。
用法: python -B v8_01_field_inventory.py <输出md>
"""
import json
import os
import re
import sys

DATA_ROOT = r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData"
BATCH = os.path.join(DATA_ROOT, "v07_first_edition", "prod_f020_060")
ID_KEY = re.compile(r"^(uav|facility|task_group|group|agent|ring|zone)_\d+$|^\d+$")


def rel(p):
    return os.path.relpath(p, DATA_ROOT).replace("\\", "/")


def short(v):
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= 60 else s[:57] + "..."


def walk(obj, prefix, lines):
    if isinstance(obj, dict):
        keys = list(obj.keys())
        groups = {}
        for k in keys:
            m = ID_KEY.match(str(k))
            pat = re.sub(r"\d+", "#", str(k)) if m else None
            groups.setdefault(pat, []).append(k)
        seen_pat = set()
        for k in keys:
            m = ID_KEY.match(str(k))
            pat = re.sub(r"\d+", "#", str(k)) if m else None
            if pat is not None:
                if pat in seen_pat:
                    continue
                seen_pat.add(pat)
                n = len(groups[pat])
                name = f"{prefix}.{k}" if prefix else str(k)
                lines.append(f"{name}  (同类键 `{pat}` 共 {n} 个，只展开第一个) : {typ(obj[k])}")
            else:
                key = str(k) if len(str(k)) <= 80 else str(k)[:77] + "...（键为序列化的长字典，已截断）"
                name = f"{prefix}.{key}" if prefix else key
                lines.append(f"{name} : {typ(obj[k])}{val(obj[k])}")
            walk(obj[k], name, lines)
    elif isinstance(obj, list):
        if obj:
            walk(obj[0], prefix + "[0]", lines)


def typ(v):
    if isinstance(v, dict):
        return f"dict({len(v)})"
    if isinstance(v, list):
        return f"list({len(v)})"
    return type(v).__name__


def val(v):
    if isinstance(v, (dict, list)):
        return ""
    return f" = {short(v)}"


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def section(title, path, out):
    out.append(f"\n### {title}\n\n文件：`{rel(path)}`\n\n```")
    lines = []
    walk(load(path), "", lines)
    out.extend(lines)
    out.append("```")


def main():
    dst = sys.argv[1]
    st_dir = os.path.join(BATCH, "status")
    b_by, c_by = {}, {}
    for fn in sorted(os.listdir(st_dir)):
        d = load(os.path.join(st_dir, fn))
        tgt = b_by if fn.startswith("B__") else c_by
        tgt.setdefault(d.get("status"), os.path.join(st_dir, fn))
    out = ["# V8-01 §3.1 字段清点（prod_f020_060）", "",
           "由 `scripts/v8_01_field_inventory.py` 生成。数组只展开第一个元素；同类编号键只展开第一个。", "",
           f"B 状态取值（本批）：{sorted(b_by)}；C 状态取值（本批）：{sorted(c_by)}"]
    section("stats.json", os.path.join(BATCH, "stats.json"), out)
    for s, p in sorted(b_by.items()):
        section(f"status/B__*.json — {s}", p, out)
    for s, p in sorted(c_by.items()):
        section(f"status/C__*.json — {s}", p, out)
    plan_dir = os.path.join(BATCH, "planning")
    for s in ("PASS", "REJECT"):
        if s in b_by:
            sk = os.path.basename(b_by[s])[3:-5]
            p = os.path.join(plan_dir, sk, "planning_result.json")
            if os.path.exists(p):
                section(f"planning/<skeleton>/planning_result.json — B {s}", p, out)
            else:
                out.append(f"\n### planning_result.json — B {s}\n\n`{rel(p)}` 不存在。")
    # metrics.json
    ep_dir = os.path.join(BATCH, "episodes")
    for sk in sorted(os.listdir(ep_dir)):
        p = os.path.join(ep_dir, sk, "synchronous", "metrics.json")
        if os.path.exists(p):
            section("episodes/<skeleton>/<mode>/metrics.json", p, out)
            # 补充：规划阶段的分项耗时只在这里（仅进入 C 的骨架有该文件）
            section("补充：episodes/<skeleton>/candidate_search.json（规划阶段 search 报告的副本）",
                    os.path.join(ep_dir, sk, "candidate_search.json"), out)
            break
    # logs
    log_dir = os.path.join(BATCH, "logs")
    files = sorted(os.listdir(log_dir))
    nonempty = [f for f in files if os.path.getsize(os.path.join(log_dir, f)) > 0]
    nb = sum(1 for f in nonempty if f.startswith("B__"))
    nc = sum(1 for f in nonempty if f.startswith("C__"))
    out.append(f"\n### logs/\n\n文件总数 {len(files)}（B {sum(1 for f in files if f.startswith('B__'))}，"
               f"C {sum(1 for f in files if f.startswith('C__'))}）；非空 {len(nonempty)}（B {nb}，C {nc}）。")
    for pre in ("B__", "C__"):
        cand = [f for f in nonempty if f.startswith(pre)]
        if cand:
            p = os.path.join(log_dir, cand[0])
            with open(p, encoding="utf-8", errors="replace") as f:
                head = [next(f, "") for _ in range(30)]
            out.append(f"\n`{rel(p)}` 前 30 行：\n\n```")
            out.extend(line.rstrip("\n") for line in head)
            out.append("```")
    out += SUMMARY
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


SUMMARY = """
## 记录了耗时的字段

单位均为秒（墙钟）。

| 文件 | 键 | 含义 | 粒度 |
|---|---|---|---|
| `status/B__<sk>.json` | `planning_wall_s`（顶层与 `detail.planning_wall_s` 同值） | `worker_b` 内 `time.monotonic` 计时：候选池搜索 + pickle 写盘（`run_v07_fe_production.py:323-342`） | 按骨架 |
| `planning/<sk>/planning_result.json` | `planning_wall_s` | 同上 | 按骨架 |
| `status/C__<sk>.json` | `detail.elapsed_wall_s`（顶层同值） | `worker_c` 整个仿真阶段（两个方式 + 配对检查 + QC，`:392-417`） | 按骨架 |
| `status/C__<sk>.json` 的 `detail.rows[]`，`episodes/<sk>/<mode>/metrics.json` | `simulation_wall_s` | 该方式联合仿真 `execute` 的 `wall_s`（`execution.py:161`） | **按方式** |
| 同上 | `amortized_skeleton_setup_s` | 骨架级准备耗时（候选池载入、单机预演、时刻安排、相关写盘）的一半（`run_v07_s2_episode_batch.py:154` 写死 `setup_s / 2`） | 按方式（两方式相同） |
| 同上 | `episode_postprocess_wall_s` | 该方式 `write_result`：判定、写盘、独立审计、截断检查 | 按方式 |
| `episodes/<sk>/candidate_search.json`（仅进入 C 的骨架） | `group_search_metrics.<g>.wall_s`、`.geometry_wall_s`（unified 后端两者相同）、`.phase_search.wall_s`（unified 恒 0）、`combination_search.wall_s` | 规划阶段每组提案池耗时、组合搜索耗时 | 按骨架×任务组 |
| `stats.json` | `timing_and_size.by_intent.<i>.b_wall_s/c_wall_s`（count/median/p90/max）、`timing_and_size.total_wall_s` | 批次汇总 | 按批次 |
| `logs/C__<sk>.txt` | 无耗时字段（只有 rehearsal / episode_complete 事件行）；`logs/B__*.txt` 全部为空 | | |

`rows[]` 中没有进入联合仿真的方式行（state = infeasible）不含上述三项方式级耗时。`duration_s`、`time_budget.*`、`event_times_s` 等是**仿真时钟**时刻/时长，不是计算耗时。

## 记录了失败原因的字段

| 文件 | 键 | 内容 |
|---|---|---|
| `status/B__<sk>.json` | `status`；`detail.rejection_reasons`（原因→次数）；`detail.termination`（classification/scope/reason/geometric_evidence/global_infeasibility_claimed） | B 结论与按原因计数（组提案级 + 组合级合并） |
| `planning/<sk>/planning_result.json` | `rejection_reasons`、`group_rejection_reasons`、`combination_rejection_reasons`、`rejection_class_counts`、`termination`、`selection` | 同上，并分开组提案级与组合级 |
| `episodes/<sk>/candidate_search.json`（仅进入 C 的骨架） | `candidates[].stage`、`.reason`、`.rejection.geometric_evidence`（衔接/形态的逐次尝试原因、整航线检查的问题 code）；`combination_records[]`；`group_terminations` | 逐候选的构造环节与子原因 |
| `status/C__<sk>.json` | `status`、`detail.first_failure`（stage/reason，及 first_attempt/final_detail）、`detail.rows[].state/reason/category/execution_status/all_groups_complete/rejection_detail/geometry_attempts` | 仿真阶段失败的环节、原因、方式 |
| `episodes/<sk>/geometry_XX/planning_rejection.json`、`geometry_history.json` | 每个候选的预演/时刻失败类别 | |
| `stats.json` | `intents.<i>.b_rejection_top5`、`c_first_failure_top5` | 批次汇总（只列前 5） |
""".splitlines()


if __name__ == "__main__":
    main()
