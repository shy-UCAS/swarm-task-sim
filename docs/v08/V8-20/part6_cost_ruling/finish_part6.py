"""Archive the fixed twenty; stop remains governed by the unmodified checkpoint."""
import collections
import shutil
from evidence_utils import *

stage = ROOT / "quick/area_cost_ruling_r1"
out = DOC / "part6_cost_ruling"
assert not out.exists()
summary = read(stage / "summary.json")
rows = read(stage / "records.json")
disk = read(stage / "disk_verification.json")
changes = audit()
assert not changes, changes
expected = set(read(DOC / "manifest.json")["lists"]["quick"])
assert len(rows) == 20 and {r["contract_id"] for r in rows} == expected
from v08.runner.area_search_serialization import assert_contract_payload
for p in (stage / "contracts").rglob("*.json"):
    assert_contract_payload(read(p))
details = {r["contract_id"]: read(stage / "contracts" / r["contract_id"] / "result.json") for r in rows}
failed = [{"contract_id": cid, **a} for cid, detail in details.items() for a in detail["attempt_log"] if not a["ok"]]
first = [{"contract_id": cid, "first_failure": next((a for a in detail["attempt_log"] if not a["ok"]), None)} for cid, detail in details.items()]
stats = {"attempt_failures_primary_stage": dict(collections.Counter(a["stage"] for a in failed)),
    "failed_attempts": failed, "first_failure_per_contract": first,
    "all_twenty_optimization_s": quantiles(r["optimization_s"] for r in rows),
    "successful_post_optimization_failures": quantiles(r["post_optimization_failures"] for r in rows if r["success"]),
    "successful_winning_attempts_one_based": quantiles(r["attempts"] for r in rows if r["success"]),
    "excluded_from_rate": []}
passed = summary["complete"] and not summary["checkpoint"]["triggered"] and not disk["main"]["p0_violations"]
out.mkdir()
for name in ("summary.json", "records.json", "selection.json", "disk_verification.json"):
    shutil.copyfile(stage / name, out / name)
dump(out / "checkpoint.json", {"part": 6, "passed": passed, "checkpoint": summary["checkpoint"],
    "complete": summary["complete"], "disk": disk, "audit_changes": changes})
dump(out / "diagnostics.json", stats)
dump(out / "evidence_index.json", index(stage))
shutil.copyfile(ROOT / "quick_watchdog_cost_ruling_r1.json", out / "watchdog.json")
shutil.copyfile(ROOT / "precheck_quick_cost_ruling_r1.json", out / "precheck.json")
shutil.copyfile(ROOT / "precheck_quick_fixed20_cost_ruling_r1.json", out / "fixed20_precheck.json")
for name in ("evidence_utils.py", "precheck_formal.py", "run_formal_stage.py", "finish_part6.py"):
    shutil.copyfile(TASK / name, out / name)
p = DOC / "acceptance.json"
a = read(p)
assert not a["outputs"]
a["outputs"] = [{"stage": "quick", "path": str(stage)}]
a["part6_checkpoint"] = str(out / "checkpoint.json")
a["status"] = "part6_passed_full_pending" if passed else "part6_failed_dependent_full_not_run"
dump(p, a)
watch = read(ROOT / "quick_watchdog_cost_ruling_r1.json")
with (DOC / "REPORT.md").open("a", encoding="utf-8", newline="\n") as f:
    f.write("\n\n## 第 6 部分：固定快批 20——" + ("通过" if passed else "检查点未过，停止依赖全量") + "\n\n")
    f.write(f"固定 20 合同全部完成，无补抽/剔除；成功 {sum(r['success'] for r in rows)}/20，整体墙钟 {watch['wall_s']:.6f} s（包含落盘复核，不含预建）。完整原检查点 {json.dumps(summary['checkpoint'], ensure_ascii=False)}。\n\n")
    f.write(f"全部 20 合同的累计优化耗时分布 {json.dumps(stats['all_twenty_optimization_s'], ensure_ascii=False)}；成功合同进入优化后失败次数分布 {json.dumps(stats['successful_post_optimization_failures'], ensure_ascii=False)}。保留段磁盘核验 {json.dumps(disk, ensure_ascii=False)}。未把 solver success 当接受条件；骨架失败仍在尝试序号内，优化后名义预筛失败按 post-optimization 计数。\n\n")
    f.write("每次失败的唯一主 stage 与完整子条件、每合同首次失败（最终成功前失败也保留）见 part6_cost_ruling/diagnostics.json，子条件可重叠。全部合同递归白名单及禁止字段扫描完成，冻结/owner/输入/配置/预置与源码散列差异 0。原始产物在外部、逐文件 SHA 索引和检查点在本目录；24 进程已前后通知，监控继续。\n")
with (DOC / "RUNNING.md").open("a", encoding="utf-8", newline="\n") as f:
    f.write(f"\n第 6 部分快批 20 完成，墙钟 {watch['wall_s']:.6f} s，passed={passed}；检查点见 acceptance.part6_checkpoint。\n")
print(json.dumps({"part": 6, "passed": passed, "wall_s": watch["wall_s"], "checkpoint": summary["checkpoint"]}, ensure_ascii=False), flush=True)
