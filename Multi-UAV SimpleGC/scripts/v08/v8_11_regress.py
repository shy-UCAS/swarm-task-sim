"""V8-11 第 2 部分：窗口版判据对 v0.7 数据的回归门禁（r4 9.1，P0：标签正确性）。

规划审查方编写，实现方不得修改（预置脚本，与预置测试同等对待）。
对 V8-03 登记的 200 条 v0.7 训练集样本（docs/v08/V8-03/sample_episodes.json），窗口取整条样本，
用窗口版判据与实测有效性检查重算，与 labels.json 逐项比较。只读样本文件，不写数据目录。

用法（在 Multi-UAV SimpleGC 目录下）:
    python -B scripts/v08/v8_11_regress.py --data-root <SwarmData 目录> --stage quick|full --out <输出目录>
退出码：0 = 全部样本读到且零差异；2 = 有差异；3 = 有样本读不到或清单不符；
4 = 运行前后样本目录的文件清单、大小或修改时间有变化（只读约定被破坏，P0）。
"""
import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT))

from task_v07.criteria import load_criteria  # noqa: E402
from task_v07.labels import role_kind  # noqa: E402
from v08.criteria.validity import VisibleTrack, check_validity  # noqa: E402
from v08.criteria.window import group_window, measure_member_window, scene_geometry  # noqa: E402

LIST_PATH = PROJECT.parent / "docs" / "v08" / "V8-03" / "sample_episodes.json"
LIST_SHA = {"full": "6f05e38ee49e14ddeb9cf4917569b0cd934be6ca42b18135ea4aa7b9667af16a",
            "quick": "37c0318a6a851773f10653500205f8b5fe0fe5cb6aec7a47e129739ee14d43c6"}


def norm(x):
    return json.loads(json.dumps(x))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


class Recorder:
    def __init__(self, episode):
        self.episode = episode
        self.counts = {}
        self.mismatches = []

    def check(self, scope, field, recorded, computed):
        self.counts[field] = self.counts.get(field, 0) + 1
        if norm(recorded) != norm(computed):
            self.mismatches.append({"episode_id": self.episode, "scope": scope, "field": field,
                                    "recorded": json.dumps(norm(recorded), ensure_ascii=False)[:500],
                                    "computed": json.dumps(norm(computed), ensure_ascii=False)[:500]})


def regress_episode(ep_dir, episode_id, cfg=None):
    """返回 (Recorder, 摘要)。窗口 = 整条样本；settled = execution_status ∈ {completed, timeout}（同 v0.7 complete）。"""
    cfg = cfg if cfg is not None else load_criteria()
    ep_dir = Path(ep_dir)
    with np.load(ep_dir / "truth_10hz.npz", allow_pickle=False) as z:
        t = z["time_us"].astype(np.int64)
        p, v = z["p"].astype(float), z["v"].astype(float)
        ids = [str(a) for a in z["agent_ids"].tolist()]
    labels = read_json(ep_dir / "labels.json")
    task = read_json(ep_dir / "task.json")
    scene = read_json(ep_dir / "public_scene.json")
    source = read_json(ep_dir / "source.json")
    settled = source["execution_status"] in ("completed", "timeout")
    geom = scene_geometry(scene)
    rec = Recorder(episode_id)
    groups = task["group_skeletons"] if "group_skeletons" in task else {task["group_id"]: task}
    kinds = []
    for gid in sorted(groups):
        group = groups[gid]
        if group.get("abort_observation"):
            raise ValueError(f"{episode_id}/{gid}: 含 abort_observation，不在本回归范围内")
        kind = role_kind(group)
        kinds.append(kind)
        ws = []
        for a in group["members"]:
            i = ids.index(a)
            w = measure_member_window(
                geom, a, t, p[:, i], v[:, i], kind=kind, target_id=group["target_id"], settled=settled,
                max_target_layer=cfg["exclusion_max_layer"][group["role"]],
                max_other_layer=cfg["exclusion_max_layer"]["other_facilities"],
                survey=group["survey"] if kind == "area_search" else None, criteria=cfg)
            ws.append(w)
            lab = labels["agents"][a]
            sc = f"{gid}/{a}"
            rec.check(sc, "conditions", lab["result"]["conditions"], w.conditions)
            rec.check(sc, "status", lab["result"]["status"], w.status)
            ce = lab["observed"]["core_event"]
            rec.check(sc, "core_event", {k: ce[k] for k in ("raw_event_type", "t_s", "frame_index", "t_confirm", "confirm_frame_index")},
                      {k: w.core_event[k] for k in ("raw_event_type", "t_s", "frame_index", "t_confirm", "confirm_frame_index")})
            contrib = lab["observed"]["contribution"]
            rec.check(sc, "dwell", contrib["dwell"], w.dwell)
            rec.check(sc, "revisit", contrib["revisit"], w.revisit)
            if kind == "close_observation":
                rec.check(sc, "observation_dwell", contrib["observation_dwell"], w.observation_dwell)
            if kind == "area_search":
                rec.check(sc, "coverage_member",
                          [contrib["covered_group_grid_points"], contrib["group_grid_point_count"],
                           contrib["effective_observation_duration_s"]],
                          [int(w.coverage["covered_mask"].sum()), w.coverage["grid_point_count"],
                           float(w.coverage["effective_mask"].sum()) / 10])
            rec.check(sc, "work_end_s", lab["observed"]["work_end_s"], w.work_end_s)
            rec.check(sc, "regions_by_facility", lab["observed"]["regions_by_facility"], w.regions_by_facility)
            rec.check(sc, "obstacle_outside_counts",
                      [lab["observed"]["hard_obstacle_sample_count"], lab["observed"]["outside_world_sample_count"]],
                      [int(w.obstacle.sum()), int(w.outside_world.sum())])
            rec.check(sc, "approach_heading_deg",
                      labels["task_groups"][gid]["observed"]["approach_headings_deg"][a], w.approach_heading_deg)
        g = group_window(ws, settled=settled, criteria=cfg)
        lg = labels["task_groups"][gid]
        rec.check(gid, "group_conditions", lg["result"]["conditions"], g["conditions"])
        rec.check(gid, "group_status", lg["result"]["status"], g["status"])
        if kind == "area_search":
            shared = lg["observed"]["shared_coverage"]
            rec.check(gid, "shared_coverage",
                      {k: shared[k] for k in ("grid_point_count", "covered_grid_point_count", "coverage_fraction", "required_fraction")},
                      g["shared_coverage"])
    r = check_validity(scene, [VisibleTrack(a, t, p[:, i]) for i, a in enumerate(ids)], criteria=cfg)
    rec.check("cluster", "minimum_separation_m", labels["cluster"]["observed"]["minimum_separation_m"], r.min_separation_m)
    rec.check("cluster", "member_min_separation_m",
              {a: labels["agents"][a]["observed"]["minimum_separation_m"] for a in ids}, r.member_min_separation_m)
    rec.check("cluster", "hard_obstacle_sample_count",
              labels["generation_quality"]["hard_obstacle_sample_count"], sum(r.restricted_frames.values()))
    return rec, {"members": len(ids), "groups": len(groups), "kinds": kinds, "settled": settled}


def snapshot(dirs):
    """样本目录内各文件的 (大小, 修改时间)；读文件不改变这两项（访问时间不计）。"""
    snap = {}
    for d in dirs:
        if d.is_dir():
            for f in sorted(d.iterdir()):
                st = f.stat()
                snap[str(f)] = (st.st_size, st.st_mtime_ns)
    return snap


def load_list(stage):
    items = read_json(LIST_PATH)
    if stage == "quick":
        items = [e for e in items if (e["order"] - 1) % 20 == 0]
    digest = hashlib.sha256("\n".join(e["episode_id"] for e in items).encode("utf-8")).hexdigest()
    return items, digest


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--stage", choices=("quick", "full"), required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    root = Path(args.data_root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    items, digest = load_list(args.stage)
    summary = {"stage": args.stage, "list_sha256": digest, "list_ok": digest == LIST_SHA[args.stage],
               "samples": len(items), "verified": 0, "load_errors": [], "members": 0, "groups": 0,
               "by_kind": {}, "unsettled_samples": 0, "compared": {}, "mismatch_count": 0}
    if not summary["list_ok"]:
        (out / f"regress_{args.stage}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print("清单 SHA256 不符", digest)
        return 3
    cfg = load_criteria()
    dirs = [root / "v07_first_edition" / e["run_id"] / "episodes" / e["skeleton_id"] / e["mode"] for e in items]
    before = snapshot(dirs)
    started = time.perf_counter()
    mismatches = []
    progress = out / f"regress_{args.stage}_progress.txt"
    for n, (e, ep) in enumerate(zip(items, dirs), 1):
        try:
            rec, info = regress_episode(ep, e["episode_id"], cfg)
        except (OSError, KeyError, ValueError) as exc:
            summary["load_errors"].append({"episode_id": e["episode_id"], "error": f"{type(exc).__name__}: {exc}"})
            continue
        summary["verified"] += 1
        summary["members"] += info["members"]
        summary["groups"] += info["groups"]
        summary["unsettled_samples"] += 0 if info["settled"] else 1
        for k in info["kinds"]:
            summary["by_kind"][k] = summary["by_kind"].get(k, 0) + 1
        for f, c in rec.counts.items():
            summary["compared"][f] = summary["compared"].get(f, 0) + c
        mismatches += rec.mismatches
        if n % 20 == 0 or n == len(items):
            with progress.open("a", encoding="utf-8") as fh:
                fh.write(f"{n}/{len(items)} 已完成，累计差异 {len(mismatches)}，{time.perf_counter() - started:.0f} s\n")
    summary["data_unchanged"] = snapshot(dirs) == before
    summary["files_checked"] = len(before)
    summary["mismatch_count"] = len(mismatches)
    summary["mismatch_fields"] = sorted({m["field"] for m in mismatches})
    summary["wall_s"] = round(time.perf_counter() - started, 1)
    (out / f"regress_{args.stage}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / f"regress_{args.stage}_mismatches.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["episode_id", "scope", "field", "recorded", "computed"])
        w.writeheader()
        w.writerows(mismatches)
    print(json.dumps({k: summary[k] for k in ("stage", "samples", "verified", "mismatch_count", "data_unchanged", "wall_s")}))
    if not summary["data_unchanged"]:
        return 4
    if summary["load_errors"]:
        return 3
    return 0 if not mismatches else 2


if __name__ == "__main__":
    sys.exit(main())
