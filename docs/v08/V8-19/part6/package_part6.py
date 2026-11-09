import hashlib
import json
import math
import shutil
import statistics
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
RUN = ROOT / "run"
DOC = BASE / "Simulation-v08/docs/v08/V8-19"
OUT = DOC / "part6"
read = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
folder = RUN / "out/quick_r1"
native, disk, watch = read(folder / "summary.json"), read(folder / "disk_verification.json"), read(RUN / "diagnostics/quick_r1/watchdog.json")
rows = read(folder / "records.json")
manifest = read(DOC / "manifest.json")
assert len(rows) == 20 and {r["contract_id"] for r in rows} == set(manifest["keys"]["quick20"])
assert native["complete"] and not native["checkpoint"]["triggered"] and not native["retained_p0_violations"]
assert disk["main"]["passed"] and disk["main"]["all_checked"] == 20 and not disk["main"]["p0_violations"]
assert watch["exit_code"] == 0 and watch["source_sha256"] == read(RUN / "diagnostics/gates_4_r1/feint/watchdog.json")["source_sha256"]
members, details = 0, []
for row in rows:
    cid = row["contract_id"]
    result, tele = read(folder / "contracts" / cid / "result.json"), read(folder / "telemetry" / (cid + ".json"))
    assert all(isinstance(a.get("optimization_entered"), bool) for a in result["attempt_log"])
    post = sum(a["optimization_entered"] and not a["ok"] for a in result["attempt_log"])
    assert post == result["post_optimization_failures"] == row["post_optimization_failures"]
    assert math.isclose(tele["optimization_s"], row["optimization_s"], rel_tol=0, abs_tol=1e-9)
    if result["success"]:
        for info in result["close_observation"]["members"].values():
            assert info["warning_entry_count"] == 1 and info["ended_outside_all_warning"]
            members += 1
    details.append({"contract_id": cid, "success": row["success"], "attempts": row["attempts"],
                    "post_failures": post, "optimization_s_all_attempts": tele["optimization_s"]})
metrics = native["checkpoint"]["metrics"]
assert statistics.median(r["optimization_s"] for r in rows) == metrics["optimization_s_median"]
OUT.mkdir(exist_ok=False)
for name in ("summary.json", "records.json", "disk_verification.json", "selection.json", "dispatch_order.json", "prewarm.json"):
    if (folder / name).exists():
        shutil.copyfile(folder / name, OUT / name)
for name in ("watchdog.json", "stdout.log", "stderr.log"):
    shutil.copyfile(RUN / "diagnostics/quick_r1" / name, OUT / name)
shutil.copyfile(ROOT / "package_part6.py", OUT / "package_part6.py")
index = [{"path": str(p), "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in folder.rglob("*") if p.is_file()]
(OUT / "raw_evidence_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
audit = {"complete": True, "same_source_as_second_gate": True, "all_20_time_denominator": True,
         "attempt_flags_known": True, "measured_members_single_entry": members, "details": details, "p0_triggered": []}
(OUT / "counter_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
manifest["execution_status_at_part5"] = manifest.pop("execution_status")
manifest["execution_status"] = {"part": 6, "status": "complete", "evidence": "part6/summary.json", "next": "full200 and diversity100, fixed five serial, paired diagnostics"}
(DOC / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
report = (DOC / "REPORT.md").read_text(encoding="utf-8")
line = next(x for x in report.splitlines() if x.startswith("> **当前状态："))
report = report.replace(line, "> **当前状态：第1–6部分完成。快批20/20成功、post失败中位数0、全20合同优化耗时中位数6.855秒，独立落盘复核通过且无P0。全量200＋多样性100及固定5键复跑待执行。**")
report += f'''

## 6. 20合同快批——完成

第5部分提交`6a16950caed02e0c03fd31816dff48fc8b7c2d47`已推并ls-remote核对。开跑前确认骨架/预建止损全部通过、第二轮门禁源码相同、固定20键和全新目录；本部分没有修改生产源码或测试。单独24进程运行前后均通知用户。原生派发墙钟{native['dispatch_wall_s']:.6f}秒，含启动及独立磁盘复核的包装器墙钟{watch['wall_s']:.6f}秒。

| 止损项 | 实测 | 原触发线 | 结论 |
|---|---|---|---|
| 成功数 | {metrics['successes']}/20 | <16/20 | 通过 |
| 成功合同优化后失败次数中位数 | {metrics['post_optimization_failures_median']} | >0 | 通过 |
| 全20合同各自全部attempt优化耗时之和的中位数 | {metrics['optimization_s_median']:.9f}秒 | >60秒 | 通过 |
| 已保留违规/段核验与落盘不一致 | 0 | >0为P0 | 通过 |

全部attempt的optimization_entered均为明确bool，逐合同重算post失败与保存计数相同，合同外telemetry优化总耗时与records一致；没有把未进入优化或正常骨架失败误计入post，也没有按成功子集改变20个耗时分母。成功attempts中位数1；骨架普通失败总数2，仅诊断，不新增止损。

20个保留结果已全部从磁盘重新加载轨迹，独立复算冻结段判定/有效性、首次warning进入/首个False退出、冻结驻留frame_index/confirm_frame_index、驻留两条等式及控制点。{members}个成员实测warning进入恰1次、段末全设施圈外；P0清单[]，合同树排除[]。9.3仍按原依赖顺序等全量与5键结果齐全后完整运行，未把本轮生成器内检查冒充独立预置通过。

证据[part6/summary.json](part6/summary.json)、[disk_verification](part6/disk_verification.json)、[逐attempt计数审计](part6/counter_audit.json)，附命令/源码SHA、全部20records和原始轨迹文件SHA索引。原始轨迹留本地`run/out/quick_r1`，后续全量仍使用原固定200/100/5名单，无豁免或补抽。
'''
(DOC / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
print(json.dumps({"part6_complete": True, "metrics": metrics, "disk_checked": 20, "members": members, "wall_s": watch["wall_s"]}))
