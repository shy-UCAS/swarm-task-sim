"""Export only completed first-edition runs; never launches a generator."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

# Direct CLI use and module imports both use this worktree's project.
PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from task_v07.s3 import S3_SCHEMA
from task_v07.s3._common import (DATA_ROOT, EXPORT_ROOT, TEMPLATE_PATH, P0ContractError,
                                 RunNotReady, dumps, inside, read_json, read_run,
                                 sha256, verify_episode_manifest, write_json)
from task_v07.s3.describe import description_variants, render_description
from task_v07.s3.facts import extract_facts
from task_v07.s3.loader import load_index, load_inputs, load_targets
from task_v07.s3.normalize import compute_anchors
from task_v07.s3.split import SPLIT_RULE, family_split
from task_v07.s3.verify import load_templates, verify_description

INTENTS = ("transit", "reconnaissance", "monitoring", "feint", "penetration")
MODES = ("synchronous", "sequential")
REVIEW_PINS = {
    ("reconnaissance", "sequential"): "family_s15_79c93b22d09e8a7a_ext_001_regular",
    ("penetration", "sequential"): "family_s15_38bedc9d791d547b_ext_009_regular",
}


def audit_inputs(run_ids, data_root):
    """Q0 completes before any anchors or descriptions are generated."""
    rows, runs, counts = [], [], {}
    for run_id in sorted(set(run_ids)):
        run, manifest = read_run(data_root, run_id)
        retained_draws = {(d["family_id"], d["slot"]): d["draw_key"]
                          for d in manifest["draws"] if d["status"] == "RETAINED"}
        draw_pairs = defaultdict(list)
        for entry in manifest["retained_episodes"]:
            root = inside(run, entry["path"])
            verify_episode_manifest(root, entry["episode_manifest_sha256"])
            draw = (entry["family_id"], entry["slot"])
            if draw not in retained_draws:
                raise P0ContractError("Episode does not belong to a retained draw")
            row = {k: entry[k] for k in ("family_id", "skeleton_id", "intent", "mode", "episode_manifest_sha256")}
            row.update(episode_key=run_id + "/" + entry["episode_id"], run_id=run_id,
                       path=root.relative_to(Path(data_root).resolve()).as_posix(),
                       draw_key=retained_draws[draw], split=family_split(entry["family_id"]))
            load_inputs(row, data_root, "raw")
            rows.append(row)
            draw_pairs[draw].append((entry["intent"], entry["mode"]))
        wanted = sorted((i, m) for i in INTENTS for m in MODES)
        if set(draw_pairs) != set(retained_draws) or any(sorted(pairs) != wanted for pairs in draw_pairs.values()):
            raise P0ContractError(f"Retained draw is not five intents x two modes: {run_id}")
        counts[run_id] = {"retained_episodes": len(manifest["retained_episodes"]),
                          "draws": len(draw_pairs),
                          "families": len({r["family_id"] for r in manifest["retained_episodes"]})}
        runs.append({"run_id": run_id, "manifest_sha256": sha256(run / "manifest.json"),
                     "registration_sha256": sha256(run / "registration.json")})
    if len({r["episode_key"] for r in rows}) != len(rows):
        raise P0ContractError("Duplicate episode keys")
    return sorted(rows, key=lambda r: r["episode_key"]), runs, counts


def _truth_anchors(root):
    task, source = read_json(root / "task.json"), read_json(root / "source.json")
    with np.load(root / "truth_10hz.npz", allow_pickle=False) as truth:
        return compute_anchors(task, source, truth)


def _write_lines(path, rows):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(dumps(row) + "\n")


def _quantiles(values):
    return {"median": float(np.median(values)), "p90": float(np.percentile(values, 90))}


def normalization_diagnostics(member_records):
    grouped = defaultdict(list)
    for record in member_records:
        grouped[(record["intent"], record["mode"])].append(record)
    output = []
    for (intent, mode), records in sorted(grouped.items()):
        output.append({
            "intent": intent, "mode": mode, "members": len(records),
            "episodes": len({r["episode_key"] for r in records}),
            "stop_hold_s": sorted({r["stop_hold_s"] for r in records}),
            **{name: _quantiles([r[name] for r in records]) for name in
               ("raw_endpoint_wait_s", "normalized_post_tc_s", "visible_duration_s", "episode_duration_s")},
        })
    return output


def write_review(out, rows, data_root, templates):
    selected = []
    for intent in INTENTS:
        for mode in MODES:
            candidates = [r for r in rows if r["intent"] == intent and r["mode"] == mode]
            pin = REVIEW_PINS.get((intent, mode))
            if pin and any(r["run_id"] == "pilot_f000_005" for r in rows):
                candidates = [r for r in candidates if r["run_id"] == "pilot_f000_005" and r["skeleton_id"] == pin]
            if not candidates:
                raise P0ContractError(f"Required Q3 sample missing: {intent}/{mode}")
            selected.append(min(candidates, key=lambda r: r["episode_key"]))
    lines = ["# 中文描述审阅样例", "", "每个意图同步、递次各一条；下列 A/B 为审阅文本，不改变评估划分。", ""]
    for row in selected:
        root = inside(data_root, row["path"])
        verify_episode_manifest(root, row["episode_manifest_sha256"])
        labels, scene = read_json(root / "labels.json"), read_json(root / "public_scene.json")
        lines += ["## " + row["episode_key"], "", "| 事实 | 值 |", "|---|---|"]
        for key in ("n_agents", "n_groups", "cluster_intent", "cluster_status"):
            lines.append(f"| {key} | {row['facts'][key]} |")
        for group in row["facts"]["groups"]:
            for key, value in group.items():
                if key != "fact_refs":
                    lines.append(f"| {group['group_id']}.{key} | {value} |")
        for group in ("A", "B"):
            review = render_description(row["facts"], row["episode_key"], group, 0, templates)
            verify_description(review, labels, scene, templates)
            lines += ["", f"**{group} 组描述**", "", review["text"]]
        lines += [""]
    (out / "samples_for_review.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return [r["episode_key"] for r in selected]


def smoke_load(out, data_root):
    """Q4 checks all exported views and all targets, recomputing truth anchors."""
    started = time.perf_counter()
    rows = load_index(out)
    target_count = 0
    for row in rows:
        raw, normal = load_inputs(row, data_root, "raw"), load_inputs(row, data_root)
        root = inside(data_root, row["path"])
        if _truth_anchors(root) != row["anchors"]:
            raise P0ContractError("Recomputed anchors differ from the index")
        start, end = row["anchors"]["keep_start_index"], row["anchors"]["keep_end_index"]
        original = raw["x"][start:end + 1]
        if (normal["x"].shape[:2] != normal["mask"].shape
                or len(normal["t_s"]) != len(normal["x"])
                or normal["x"].shape[1:] != raw["x"].shape[1:]
                or not np.array_equal(normal["x"][normal["mask"]], original[normal["mask"]])
                or np.any(normal["x"][~normal["mask"]] != 0)
                or normal["scene"] != raw["scene"] or normal["agent_ids"] != raw["agent_ids"]):
            raise P0ContractError("Q4 normalized input correspondence failed")
        raw_ticks = np.rint(raw["t_s"][start:end + 1] * 1e6).astype(np.int64)
        restored = np.rint((normal["t_s"] + row["anchors"]["t0"]) * 1e6).astype(np.int64)
        if not np.array_equal(raw_ticks, restored):
            raise P0ContractError("Q4 normalized clock does not map to raw")
        choices = [("A", i) for i in range(3)] if row["split"] != "test" else [("B", 0), ("A", 0)]
        for group, variant in choices:
            target = load_targets(row, out, group, variant)
            if set(target) != {"text", "slots", "intent", "family_id", "split"}:
                raise P0ContractError("Q4 target fields differ")
            target_count += 1
    return {"status": "PASS", "episodes": len(rows), "views_loaded": 2 * len(rows),
            "targets_loaded": target_count, "wall_s": time.perf_counter() - started}


def write_stats(out, rows, descriptions, diagnostics, q4):
    counts = Counter((r["split"], r["intent"]) for r in rows)
    lines = ["# S3 统计", "", "| split | intent | episodes |", "|---|---|---:|"]
    lines += [f"| {split} | {intent} | {counts[split, intent]} |"
              for split in ("train", "val", "test") for intent in INTENTS]
    lines += ["", "## Q2 归一化诊断", "",
              "单位为秒；各列为中位数 / p90。成员级统计；episode 长度按成员加权，另列独立 episode 数。",
              "", "| intent | mode | 成员 | episode | stop_hold | raw末端 | 归一化末端 | 可见时长 | episode长度 |",
              "|---|---|---:|---:|---|---|---|---|---|"]
    for record in diagnostics:
        cells = [f"{record[k]['median']:.6f} / {record[k]['p90']:.6f}" for k in
                 ("raw_endpoint_wait_s", "normalized_post_tc_s", "visible_duration_s", "episode_duration_s")]
        lines.append("| " + " | ".join(map(str, [record["intent"], record["mode"], record["members"],
                     record["episodes"], record["stop_hold_s"], *cells])) + " |")
    lines += ["", f"描述数：{len(descriptions)}。禁用词：0；独立事实绑定不一致：0。",
              f"Q4：{q4['episodes']} episode，{q4['views_loaded']} 输入视图，{q4['targets_loaded']} 目标，{q4['wall_s']:.3f} s。",
              "", "限制：仅完整 episode；family 数量小，不足以评估划分；出发前等待通过可见起点和共同时间轴保留协调语义。", ""]
    (out / "stats.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def export_runs(run_ids, export_id, data_root=DATA_ROOT, export_root=EXPORT_ROOT):
    data_root, export_root = Path(data_root), Path(export_root)
    out = inside(export_root, export_id)
    if out.exists():
        raise RunNotReady(f"Export already exists: {out}")
    rows, runs, q0 = audit_inputs(run_ids, data_root)
    print("Q0 PASS " + dumps(q0), flush=True)
    templates = load_templates()
    out.mkdir(parents=True, exist_ok=False)
    descriptions, members = [], []
    current = None
    try:
        for row in rows:
            current = row["episode_key"]
            root = inside(data_root, row["path"])
            raw = load_inputs(row, data_root, "raw")
            labels, scene = read_json(root / "labels.json"), read_json(root / "public_scene.json")
            row["anchors"] = _truth_anchors(root)
            row.update(extract_facts(labels, scene))
            if row["facts"]["cluster_intent"] != row["intent"]:
                raise P0ContractError("Registry intent differs from labels")
            for record in description_variants(row["facts"], current, row["split"], templates):
                verify_description(record, labels, scene, templates)
                descriptions.append(record)
            for agent, anchor in row["anchors"]["members"].items():
                members.append({"episode_key": current, "agent_id": agent, "intent": row["intent"], "mode": row["mode"],
                                "stop_hold_s": row["anchors"]["stop_hold_s"],
                                "raw_endpoint_wait_s": float(raw["t_s"][-1]) - anchor["t_c"],
                                "normalized_post_tc_s": anchor["visible_end"] - anchor["t_c"],
                                "visible_duration_s": anchor["visible_end"] - anchor["release_s"],
                                "episode_duration_s": row["anchors"]["t1"] - row["anchors"]["t0"]})
        descriptions.sort(key=lambda r: (r["episode_key"], r["diagnostic_template_A"], r["variant"]))
        _write_lines(out / "episodes.jsonl", rows)
        _write_lines(out / "descriptions.jsonl", descriptions)
        diagnostics = normalization_diagnostics(members)
        samples = write_review(out, rows, data_root, templates)
        q4 = smoke_load(out, data_root)
        for run in runs:
            directory = inside(data_root, run["run_id"])
            if (sha256(directory / "manifest.json") != run["manifest_sha256"]
                    or sha256(directory / "registration.json") != run["registration_sha256"]):
                raise P0ContractError("Input registry changed during export")
        commit = subprocess.check_output(["git", "-C", str(PROJECT.parent), "rev-parse", "HEAD"], text=True).strip()
        manifest = {"schema": S3_SCHEMA, "code_commit": commit, "templates_sha256": sha256(TEMPLATE_PATH),
                    "runs": runs, "split_rule": SPLIT_RULE, "episodes": len(rows), "descriptions": len(descriptions),
                    "families": len({r["family_id"] for r in rows}), "split_counts": dict(Counter(r["split"] for r in rows)),
                    "q0": q0, "q2": diagnostics, "q3_samples": samples, "q4": q4,
                    "forbidden_word_count": 0, "binding_mismatch_count": 0,
                    "source_sha256": {str(p.relative_to(PROJECT)).replace("\\", "/"): sha256(p)
                                      for p in sorted((PROJECT / "task_v07" / "s3").glob("*.py"))}}
        manifest["source_sha256"]["scripts/run_v07_s3_export.py"] = sha256(Path(__file__))
        write_stats(out, rows, descriptions, diagnostics, q4)
        write_json(out / "export_manifest.json", manifest)
        print("EXPORT PASS " + str(out), flush=True)
        return manifest
    except Exception as exc:
        write_json(out / "S3_STOP.json", {"episode_key": current, "error_type": type(exc).__name__,
                                         "message": str(exc), "q0": q0})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--export-id", required=True)
    args = parser.parse_args(argv)
    try:
        export_runs(args.runs, args.export_id)
    except RunNotReady as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except P0ContractError as exc:
        print("P0: " + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
