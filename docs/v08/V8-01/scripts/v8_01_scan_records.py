"""V8-01 §3.2/§3.4: 扫描 v07_first_edition 全部 9 个批次的现有记录（只读）。

输出（均在 <out_dir> 下）：
  timing_records.csv   每行一个“骨架 × 阶段（× 方式）”
  scan_raw.json        失败细节、候选级环节计数、输出体积等中间结果，供 v8_01_summarize.py 使用
用法: python -B v8_01_scan_records.py <out_dir>
"""
import collections
import csv
import json
import os
import sys
import time

DATA_ROOT = r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData"
FE_ROOT = os.path.join(DATA_ROOT, "v07_first_edition")
BATCHES = ["pilot_f000_005", "pilot_f005_020d", "prod_f020_060", "prod_f060_100", "prod_f100_140",
           "prod_f140_180", "prod_f180_220", "prod_f220_260", "prod_f260_300"]
MODES = ("synchronous", "sequential")

COLUMNS = [
    "run_id", "code_commit", "skeleton_id", "draw_key", "intent", "stage", "mode", "status", "draw_status",
    # B：status/B__*.json 与 planning_result.json
    "planning_wall_s",
    # B：episodes/<sk>/candidate_search.json（仅进入 C 的骨架才有该文件；各组求和）
    "b_group_search_wall_s_sum", "b_geometry_wall_s_sum", "b_phase_search_wall_s_sum",
    "b_combination_search_wall_s", "b_attempted_candidates",
    # C：status/C__*.json（骨架级，两个方式行都填同一个值）
    "c_skeleton_elapsed_wall_s",
    # C：rows[]（按方式）
    "simulation_wall_s", "amortized_skeleton_setup_s", "episode_postprocess_wall_s",
    "sim_duration_s", "execution_status", "row_state", "row_reason",
    "episode_dir_bytes",
    "n_agents", "n_groups", "n_task_groups",
]


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def rel(p):
    return os.path.relpath(p, DATA_ROOT).replace("\\", "/")


def dir_bytes(path):
    total = 0
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                if e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
                else:
                    total += e.stat(follow_symlinks=False).st_size
    return total


def main():
    out_dir = sys.argv[1]
    t0 = time.time()
    rows = []
    raw = {"b_reject": [], "c_not_paired": [], "candidate_stage_counts": {}, "volume": {},
           "stats_total_wall_s": {}, "workers": {}, "code_commit": {}, "c_rows_without_timing": []}
    cand_stage = collections.defaultdict(collections.Counter)
    for run in BATCHES:
        rd = os.path.join(FE_ROOT, run)
        manifest = load(os.path.join(rd, "manifest.json"))
        stats = load(os.path.join(rd, "stats.json"))
        raw["stats_total_wall_s"][run] = stats["timing_and_size"]["total_wall_s"]
        raw["workers"][run] = manifest["workers"]
        commit = manifest["code_commit"][:8]
        raw["code_commit"][run] = commit
        draw_status = {d["draw_key"]: d["status"] for d in manifest["draws"]}
        descriptors = load(os.path.join(rd, "descriptors", "descriptors.json"))
        vol = collections.Counter()
        for desc in descriptors:
            sid = desc["skeleton_id"]
            intent = desc["base_intent"]
            draw_key = f"{desc['family_id']}:{desc['common_draw']['slot']}"
            base = {"run_id": run, "code_commit": commit, "skeleton_id": sid, "draw_key": draw_key,
                    "intent": intent, "draw_status": draw_status.get(draw_key),
                    "n_agents": len(desc["agent_ids"]),
                    "n_groups": desc["common_draw"]["actual_unit_count"],
                    "n_task_groups": len(desc["task_groups"])}
            b = load(os.path.join(rd, "status", f"B__{sid}.json"))
            brow = dict(base, stage="B", mode="", status=b["status"], planning_wall_s=b.get("planning_wall_s"))
            pr_path = os.path.join(rd, "planning", sid, "planning_result.json")
            pr = load(pr_path) if os.path.exists(pr_path) else None
            cs_path = os.path.join(rd, "episodes", sid, "candidate_search.json")
            if os.path.exists(cs_path):
                cs = load(cs_path)
                gm = cs.get("group_search_metrics", {})
                brow["b_group_search_wall_s_sum"] = sum(v.get("wall_s", 0.) for v in gm.values())
                brow["b_geometry_wall_s_sum"] = sum(v.get("geometry_wall_s", 0.) for v in gm.values())
                brow["b_phase_search_wall_s_sum"] = sum(v.get("phase_search", {}).get("wall_s", 0.) for v in gm.values())
                brow["b_combination_search_wall_s"] = cs.get("combination_search", {}).get("wall_s")
                brow["b_attempted_candidates"] = cs.get("attempted_candidates")
                for c in cs.get("candidates", []):
                    cand_stage[intent][f"{c.get('stage')}|{c.get('reason')}"] += 1
            rows.append(brow)
            if b["status"] != "PASS":
                raw["b_reject"].append({
                    "run_id": run, "skeleton_id": sid, "intent": intent, "status": b["status"],
                    "draw_status": base["draw_status"], "planning_result": pr, "status_detail": b.get("detail"),
                    "planning_result_path": rel(pr_path) if pr else None,
                    "n_agents": base["n_agents"], "n_task_groups": base["n_task_groups"],
                    "planning_wall_s": b.get("planning_wall_s")})
            # 输出体积：planning/<sk>
            pdir = os.path.join(rd, "planning", sid)
            if os.path.isdir(pdir):
                vol[f"planning|{intent}"] += dir_bytes(pdir)
            c_path = os.path.join(rd, "status", f"C__{sid}.json")
            if not os.path.exists(c_path):
                continue
            c = load(c_path)
            det = c.get("detail") or {}
            elapsed = det.get("elapsed_wall_s", c.get("elapsed_wall_s"))
            ep_root = os.path.join(rd, "episodes", sid)
            for r in det.get("rows", []):
                mode = r.get("mode")
                crow = dict(base, stage="C", mode=mode, status=c["status"], c_skeleton_elapsed_wall_s=elapsed,
                            simulation_wall_s=r.get("simulation_wall_s"),
                            amortized_skeleton_setup_s=r.get("amortized_skeleton_setup_s"),
                            episode_postprocess_wall_s=r.get("episode_postprocess_wall_s"),
                            sim_duration_s=r.get("duration_s"), execution_status=r.get("execution_status"),
                            row_state=r.get("state"), row_reason=r.get("reason") if not isinstance(r.get("reason"), (dict, list)) else json.dumps(r.get("reason"))[:200])
                mdir = os.path.join(ep_root, mode)
                if r.get("path") and os.path.isdir(mdir):
                    nb = dir_bytes(mdir)
                    crow["episode_dir_bytes"] = nb
                    vol[f"episode_mode_dir|{intent}"] += nb
                if r.get("simulation_wall_s") is None:
                    raw["c_rows_without_timing"].append({"run_id": run, "skeleton_id": sid, "mode": mode,
                                                         "state": r.get("state"), "reason": r.get("reason")})
                rows.append(crow)
            # 输出体积：episodes/<sk> 中方式目录以外的部分（geometry_XX、骨架级 json）
            if os.path.isdir(ep_root):
                total = dir_bytes(ep_root)
                mode_bytes = sum(dir_bytes(os.path.join(ep_root, m)) for m in MODES if os.path.isdir(os.path.join(ep_root, m)))
                vol[f"episode_skeleton_aux|{intent}"] += total - mode_bytes
            qc = os.path.join(rd, "qc", f"{sid}.json")
            if os.path.exists(qc):
                vol[f"qc|{intent}"] += os.path.getsize(qc)
            if c["status"] != "PAIRED":
                fails = []
                for r in det.get("rows", []):
                    item = {"mode": r.get("mode"), "state": r.get("state"), "category": r.get("category"),
                            "reason": r.get("reason"), "execution_status": r.get("execution_status"),
                            "all_groups_complete": r.get("all_groups_complete"),
                            "quality_status": r.get("quality_status"), "task_result": r.get("task_result"),
                            "rejection_detail": r.get("rejection_detail"),
                            "geometry_attempt_categories": [h.get("category") for h in r.get("geometry_attempts", [])]}
                    if r.get("all_groups_complete") is False:
                        item["failed_groups"] = {g: v.get("result") for g, v in (r.get("groups") or {}).items()
                                                 if (v.get("result") or {}).get("status") != "success"}
                    fails.append(item)
                ff = det.get("first_failure")
                raw["c_not_paired"].append({
                    "run_id": run, "skeleton_id": sid, "intent": intent, "status": c["status"],
                    "status_path": rel(c_path),
                    "first_failure": {k: ff.get(k) for k in ("stage", "reason", "final_detail")} if isinstance(ff, dict) else ff,
                    "rows": fails, "n_agents": base["n_agents"], "n_task_groups": base["n_task_groups"],
                    "elapsed_wall_s": elapsed})
        raw["volume"][run] = dict(vol)
        print(f"{run}: done ({time.time() - t0:.0f}s)", flush=True)
    raw["candidate_stage_counts"] = {k: dict(v) for k, v in cand_stage.items()}
    with open(os.path.join(out_dir, "timing_records.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="raise")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") if r.get(k) is not None else "" for k in COLUMNS})
    with open(os.path.join(out_dir, "rerun", "scan_raw.json"), "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=1)
    print(f"rows={len(rows)} elapsed={time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
