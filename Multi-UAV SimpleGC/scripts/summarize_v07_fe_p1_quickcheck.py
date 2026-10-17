"""FE-P1 planning-only comparison; historical inputs are never modified."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
import json
import math
from pathlib import Path
import subprocess

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "docs/v07/evidence/fe"
CODES = ("terminal_endpoint_spacing", "retreat_endpoint_invalid", "inward_rotation_skipped")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def walk(node, path=""):
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}/{index}")


def journal(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def rates(new, old):
    rows = []
    for role, method in sorted(set(new) | set(old)):
        n, o = new[(role, method)], old[(role, method)]
        rows.append({"role": role, "execution_method": method,
                     "new_accepted": n["accepted"], "new_proposals": n["total"],
                     "old_accepted": o["accepted"], "old_proposals": o["total"],
                     "new_rate": n["accepted"]/n["total"] if n["total"] else None,
                     "old_rate": o["accepted"]/o["total"] if o["total"] else None})
    return rows


def summarize(new, descriptors_dir, old_dirs):
    ids = read(OUT / "p1_quickcheck_skeletons.json")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate quick-check skeleton IDs")
    descriptors = {d["skeleton_id"]: d for d in read(descriptors_dir / "private_skeleton_descriptors.json")}
    registration = read(new / "registration.json")
    undeclared = set(ids) - set(registration["selected_skeletons"])
    if undeclared:
        raise ValueError(f"New run does not declare requested skeletons: {sorted(undeclared)}")
    result = read(new / "run_result.json")
    table_a, table_b, diagnostics = [], [], []
    counts = {side: defaultdict(Counter) for side in ("new", "old", "new_completed", "old_completed")}
    triggers = defaultdict(Counter)
    stops = []
    for sid in ids:
        descriptor = descriptors[sid]
        groups = {g["group_id"]: g for g in descriptor["task_groups"]}
        owners = [directory/sid for directory in old_dirs if (directory/sid/"planning_result.json").exists()]
        if len(owners) != 1:
            raise ValueError(f"Expected one historical completed result for {sid}, found {len(owners)}")
        old_root, new_root = owners[0], new/sid
        historical = read(old_root/"planning_result.json")
        complete = (new_root/"planning_result.json").exists()
        current = read(new_root/"planning_result.json") if complete else None
        table_a.append({"skeleton_id": sid, "completed": complete,
                        "status": current["status"] if complete else "UNFINISHED",
                        "eligible_combinations": current["eligible_combinations"] if complete else None,
                        "old_eligible_combinations": historical["eligible_combinations"],
                        "old_attempt": str(old_root.parent)})
        if complete and historical["eligible_combinations"] > 0 and current["eligible_combinations"] == 0:
            stops.append({"condition": 1, "skeleton_id": sid, "reason": "previously_nonempty_now_empty"})
        selected = new_root/"selected_skeleton.json"
        if selected.exists():
            skeleton = read(selected)
            for gid, group in skeleton["group_skeletons"].items():
                meta = groups[gid]
                members = group["members"]
                endpoints = [group["references"][a]["endpoint_enu_m"][:2] for a in members]
                minimum = min((math.dist(a, b) for a, b in combinations(endpoints, 2)), default=None)
                spacing = descriptor["family_conditions"]["lateral_spacing_m"]
                rotations = [{"path": path, "rotation_deg": node["rotation_deg"]}
                             for path, node in walk(group.get("geometry_provenance", {}))
                             if "rotation_deg" in node]
                row = {"skeleton_id": sid, "group_id": gid, "role": meta["role"],
                       "execution_method": meta["execution_method"], "member_count": len(members),
                       "minimum_endpoint_distance_m": minimum, "lateral_spacing_m": spacing}
                table_b.append(row)
                if meta["role"] == "monitoring" and minimum is not None and minimum < .99*spacing:
                    diagnostics.append({**row, "rotation_evidence": rotations})
        for side, root in (("new", new_root), ("old", old_root)):
            for record in journal(root/"proposals.jsonl"):
                meta = groups[record["group_id"]]
                key = (meta["role"], meta["execution_method"])
                accepted = record["reason"] is None
                counts[side][key].update(total=1, accepted=int(accepted))
                if complete:
                    counts[side+"_completed"][key].update(total=1, accepted=int(accepted))
                if side != "new" or accepted:
                    continue
                hits = Counter()
                for _, node in walk(record):
                    for code in CODES:
                        if node.get("code") == code or node.get("reason") == code:
                            hits[code] += 1
                triggers[key]["rejected_proposals"] += 1
                for code in CODES:
                    triggers[key][code+"_proposals"] += int(hits[code] > 0)
                    triggers[key][code+"_occurrences"] += hits[code]
    completed_rates = rates(counts["new_completed"], counts["old_completed"])
    for row in completed_rates:
        if (row["role"], row["execution_method"]) == ("monitoring", "monitoring"):
            if row["new_rate"] is not None and row["old_rate"] is not None and row["new_rate"] < .5*row["old_rate"]:
                stops.append({"condition": 2, "reason": "monitoring_acceptance_below_half", **row})
    table_d = []
    for key in sorted(set(counts["new"]) | set(triggers)):
        role, method = key
        row = {"role": role, "execution_method": method,
               "rejected_proposals": triggers[key]["rejected_proposals"],
               **{code+suffix: triggers[key][code+suffix] for code in CODES
                  for suffix in ("_proposals", "_occurrences")}}
        table_d.append(row)
        if role != "monitoring" and row["terminal_endpoint_spacing_proposals"] > 0:
            stops.append({"condition": 3, "reason": "non_monitoring_terminal_spacing", **row})
    unfinished = [row["skeleton_id"] for row in table_a if not row["completed"]]
    if result["status"] not in ("completed", "TIME_LIMIT_STOP"):
        stops.append({"condition": "run_status", "status": result["status"]})
    return {"schema": "traj2language.fe_p1_quickcheck/1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "provenance": {"new": str(new), "descriptors": str(descriptors_dir),
                           "old": [str(p) for p in old_dirs], "run_status": result["status"],
                           "entry_commit": registration.get("entry_commit"),
                           "summary_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()},
            "spacing_source": "descriptor.family_conditions.lateral_spacing_m",
            "table_a": table_a, "table_b": table_b,
            "table_c": rates(counts["new"], counts["old"]),
            "completed_cohort_rates_for_gate": completed_rates, "table_d": table_d,
            "table_e": unfinished, "diagnostics": diagnostics, "stop_conditions": stops,
            "decision": "STOP" if stops else ("PARTIAL_NO_STOP" if unfinished else "PASS"),
            "scope": "Planning only; no episode solo rehearsal or joint simulation. Test suite fixtures are separate."}


def table(rows, columns):
    def fmt(value):
        if value is None:
            return "-"
        if isinstance(value, float):
            return f"{value:.6f}"
        return str(value).replace("|", "\\|")
    return "\n".join(["| " + " | ".join(columns) + " |",
                      "| " + " | ".join("---" for _ in columns) + " |",
                      *["| " + " | ".join(fmt(row.get(key)) for key in columns) + " |" for row in rows]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--descriptors", type=Path, required=True)
    parser.add_argument("--old", type=Path, nargs="+", action="extend", required=True)
    args = parser.parse_args()
    summary = summarize(args.new.resolve(), args.descriptors.resolve(), [p.resolve() for p in args.old])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"p1_monitoring_quickcheck.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    sections = ["# FE-P1 监视撤离规划快速检查", "",
                f"判定：**{summary['decision']}**；运行状态：{summary['provenance']['run_status']}。",
                "", "仅覆盖七个指定骨架的规划，不代表飞行时序或完整仿真验收。",
                "", "## A：骨架状态", "",
                table(summary["table_a"], ["skeleton_id", "completed", "status", "eligible_combinations", "old_eligible_combinations"]),
                "", "## B：所选候选的组内终点间距", "",
                "lateral_spacing_m 来源：descriptor.family_conditions.lateral_spacing_m；单成员距离记为 -。", "",
                table(summary["table_b"], ["skeleton_id", "group_id", "role", "execution_method", "member_count", "minimum_endpoint_distance_m", "lateral_spacing_m"]),
                "", "## C：七个骨架的提案接受率", "",
                table(summary["table_c"], ["role", "execution_method", "new_accepted", "new_proposals", "new_rate", "old_accepted", "old_proposals", "old_rate"]),
                "", "停止条件 2 仅比较本次已完成骨架的相同新旧集合：", "",
                table(summary["completed_cohort_rates_for_gate"], ["role", "execution_method", "new_accepted", "new_proposals", "new_rate", "old_accepted", "old_proposals", "old_rate"]),
                "", "## D：新运行拒绝提案中的触发统计", "",
                "proposals 为含该原因的去重提案数；occurrences 为整条记录递归出现次数（可包含重复证据）。", "",
                table(summary["table_d"], ["role", "execution_method", *[code+suffix for code in CODES for suffix in ("_proposals", "_occurrences")]]),
                "", "## E：未完成骨架", "", *([f"- {sid}" for sid in summary["table_e"]] or ["无。"]),
                "", "## 停止条件与诊断", "",
                "停止条件：" + json.dumps(summary["stop_conditions"], ensure_ascii=False), "",
                "低于 0.99 倍编队间距的监视组及旋转证据：" + json.dumps(summary["diagnostics"], ensure_ascii=False),
                "", "## 来源", "", *[f"- {key}: {value}" for key, value in summary["provenance"].items()]]
    (OUT/"p1_monitoring_quickcheck.md").write_text("\n".join(sections)+"\n", encoding="utf-8")
    print(json.dumps({"decision": summary["decision"], "completed": sum(r["completed"] for r in summary["table_a"]),
                      "stop_conditions": summary["stop_conditions"], "diagnostic_groups": len(summary["diagnostics"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
