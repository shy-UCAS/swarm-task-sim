"""V8-01 §3.4 补充：进入 C 的骨架在 episodes/<sk>/candidate_search.json 中逐候选拒绝的子原因（只读）。

- connection_search_budget_exhausted：证据是 10 次衔接尝试，各有自己的失败原因
- shape_search_budget_exhausted：证据是 20 次形态尝试，各有自己的失败原因
- whole_route_check：证据是整航线检查的问题清单（code）
用法: python -B v8_01_scan_subreasons.py <输出md>
"""
import collections
import json
import os
import sys

FE_ROOT = r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_first_edition"
INTENTS = ["transit", "reconnaissance", "monitoring", "feint", "penetration"]


def main():
    dst = sys.argv[1]
    attempts = collections.defaultdict(collections.Counter)   # (intent, reason) -> 子原因 -> 尝试次数
    candidates = collections.defaultdict(collections.Counter)  # (intent, reason) -> 子原因 -> 含该子原因的候选数
    n_files = 0
    for run in sorted(os.listdir(FE_ROOT)):
        ep = os.path.join(FE_ROOT, run, "episodes")
        for sk in sorted(os.listdir(ep)):
            path = os.path.join(ep, sk, "candidate_search.json")
            if not os.path.exists(path):
                continue
            with open(os.path.join(FE_ROOT, run, "planning", sk, "planning_result.json"), encoding="utf-8") as f:
                intent = json.load(f)["intent"]
            with open(path, encoding="utf-8") as f:
                cs = json.load(f)
            n_files += 1
            for c in cs.get("candidates", []):
                rej = c.get("rejection")
                if not rej:
                    continue
                reason = rej["reason"]
                seen = set()
                for ev in rej.get("geometric_evidence") or []:
                    sub = ev.get("reason") or ev.get("code") or ev.get("constraint") or "?"
                    attempts[(intent, reason)][sub] += 1
                    seen.add(sub)
                for sub in seen:
                    candidates[(intent, reason)][sub] += 1
    out = ["# V8-01 §3.4 补充：逐候选拒绝的子原因（只覆盖进入 C 的骨架）", "",
           f"来源：全部 9 批 `episodes/<sk>/candidate_search.json` 共 {n_files} 个文件（`scripts/v8_01_scan_subreasons.py`）。"
           " B 为 REJECT 的骨架没有这类文件，见 failures.md §1。", "",
           "- `connection_search_budget_exhausted`：每个被拒提案有 10 次衔接尝试（`route.py:164` / `operation_routes.py:35`），子原因是每次尝试抛出的 `GeometryRejected.reason`。",
           "- `shape_search_budget_exhausted`：每个被拒提案有 20 次形态尝试（`shapes.py:21` / `operation_shapes.py:165`）。",
           "- `whole_route_check`：子原因是 `plan_checks` 问题清单中的 `code`（`checks.py:68-186`），一个候选可同时有多个。", ""]
    for reason in sorted({r for _, r in attempts}):
        out += [f"## {reason}", "", "| 子原因 | " + " | ".join(f"{i} 尝试数 / 候选数" for i in INTENTS) + " |",
                "|---|" + "---|" * len(INTENTS)]
        subs = sorted({s for (i, r), c in attempts.items() if r == reason for s in c},
                      key=lambda s: -sum(attempts[(i, reason)][s] for i in INTENTS))
        for s in subs:
            out.append(f"| {s} | " + " | ".join(f"{attempts[(i, reason)][s]} / {candidates[(i, reason)][s]}" for i in INTENTS) + " |")
        out.append("")
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(n_files)


if __name__ == "__main__":
    main()
