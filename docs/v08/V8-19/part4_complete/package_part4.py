import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
CODE = REPO / "Multi-UAV SimpleGC"
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
DIAG = ROOT / "run/diagnostics"
DOC = REPO / "docs/v08/V8-19"
OUT = DOC / "part4_complete"
read = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
before = read(DIAG / "part4_before_gates.json")
assert before["complete"]
source = {str(p.relative_to(CODE)): hashlib.sha256(p.read_bytes()).hexdigest()
          for sub in ("v08", "tools/v08") for p in (CODE / sub).rglob("*.py")}
gates = []
for intent in ("monitoring", "transit", "intrusion", "feint"):
    folder = DIAG / "gates_4_r1" / intent
    compare, watch = read(folder / "comparison.json"), read(folder / "watchdog.json")
    assert compare["all_equal"] and compare["equal_count"] == compare["total"] == 20 and compare["exclusions"] == []
    assert watch["exit_code"] == 0 and watch["source_sha256"] == source
    gates.append({"intent": intent, "equal": 20, "total": 20, "wall_s": watch["wall_s"],
                  "files": sum(r["n_files"] for r in compare["comparisons"]), "exclusions": []})
smokes = []
for name in ("smoke_r1", "smoke_max_r1"):
    folder = ROOT / "run/out" / name
    summary, disk = read(folder / "summary.json"), read(folder / "disk_verification.json")
    assert summary["complete"] and not summary["retained_p0_violations"] and disk["main"]["passed"]
    assert all(r["success"] for r in read(folder / "records.json"))
    smokes.append({"name": name, "summary": summary, "disk_verification": disk,
                   "watchdog_wall_s": read(DIAG / name / "watchdog.json")["wall_s"],
                   "records": [{k: r[k] for k in ("contract_id", "success", "attempts", "group_size", "optimization_s", "post_optimization_failures")}
                               for r in read(folder / "records.json")]})
injection = read(DIAG / "part4_injection_r1/injection.json")
assert injection["attempts"] == 2 and injection["post_failures"] == 1 and injection["disk_verification"]["passed"]
OUT.mkdir(exist_ok=False)
for name in ("part4_unit_tests_r2", "part4_old_tests_r2", "gates_4_r1"):
    shutil.copytree(DIAG / name, OUT / name)
for name in ("part4_before_gates.json", "part4_injection_r1.log", "part4_dry_payload_r1.log"):
    shutil.copyfile(DIAG / name, OUT / name)
shutil.copyfile(DIAG / "part4_injection_r1/injection.json", OUT / "injection.json")
for name in ("run_units_r2.py", "run_old_tests_r2.py", "check_before_gates.py", "package_part4.py"):
    shutil.copyfile(ROOT / "part4_work" / name, OUT / name)
for name in ("smoke_r1", "smoke_max_r1"):
    target = OUT / name
    target.mkdir()
    for filename in ("summary.json", "disk_verification.json", "selection.json", "dispatch_order.json"):
        shutil.copyfile(ROOT / "run/out" / name / filename, target / filename)
    for filename in ("watchdog.json", "stdout.log", "stderr.log"):
        shutil.copyfile(DIAG / name / filename, target / filename)
shutil.copyfile(ROOT / "run_stage.ps1", DOC / "run_stage.ps1")
shutil.copyfile(ROOT / "part4_work/RUNNING_current.md", DOC / "RUNNING.md")
summary = {"part": 4, "complete": True, "gates": gates, "gates_wall_s": sum(g["wall_s"] for g in gates),
           "preflight": before, "smokes": smokes, "injection": injection, "source_sha256": source,
           "source_frozen_during_gates": True, "p0_triggered": [], "checked_utc": datetime.now(timezone.utc).isoformat()}
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
raw = [p for name in ("smoke_r1", "smoke_max_r1") for p in (ROOT / "run/out" / name).rglob("*") if p.is_file()]
index = [{"path": str(p), "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in raw]
(OUT / "raw_evidence_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
manifest = read(DOC / "manifest.json")
manifest["execution_status_at_part3"] = manifest.pop("execution_status")
manifest["execution_status"] = {"part": 4, "status": "complete", "evidence": "part4_complete/summary.json", "next": "separate chord prewarm then skeleton200 checkpoint"}
(DOC / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
report = (DOC / "REPORT.md").read_text(encoding="utf-8")
current = next(line for line in report.splitlines() if line.startswith("> **当前状态："))
report = report.replace(current, "> **当前状态：第1–4部分完成。第二轮四意图80/80逐字节一致，两个轮次共160/160；四键生产smoke及最大查询全部通过独立磁盘复核。生产预建/200骨架及后续批次尚未启动。**")
table = "\n".join(f"| {g['intent']} | {g['equal']}/{g['total']} | {g['files']} | {g['wall_s']:.3f} | [] |" for g in gates)
report += f'''

## 4. 完整链路、序列化与第二轮门禁——完成

补齐新意图优化语义检查、无skip_ranges的全边界复核、全窗名义预筛、冻结段/有效性核验后的实测1次进入检查，以及落盘后的独立复算。首个驻留窗口直接取冻结检测器frame_index/confirm_frame_index，退出取首个False实测帧；空轨迹/缺成员返回失败。递归白名单覆盖proposal/witness、LP三子键、attempt/failure/phase和结果，合同内无计时/缓存/PID/路径。业务释放、驻留和五段时长保留。遥测独立留合同外。新意图的预建、骨架、保存、多样性、Fréchet分侧时间映射、五意图外连接和薄CLI均已接入；旧路径无新空字段。

### 测试与生产最小验证

最终快速测试33/33通过（预置数值8、完整接口3、参考自加5、选点/LP自加7、链路自加10），墙钟{before['tests']['part4_unit_tests_r2']['wall_s']:.3f}秒。27旧文件134/134通过，墙钟{before['tests']['part4_old_tests_r2']['wall_s']:.3f}秒；旧SceneGate继续沿已接受替代，其他实际执行项无跳过。另一个真实输入失败注入测试1/1通过：原第一次语义检查本可通过，仅测试桩强制失败，正常消耗一次attempt并进入第二次，成功attempt索引1、post失败计数1，磁盘复核通过；测试体18.193秒。注入产物仅在diagnostics，不计入固定数据集。当前9.3产物预置仍按已澄清依赖后置，未记通过。

四键smoke o01_d0/o02_d0/o11_d0/o01_d1均成功、attempts=1、post=0，优化耗时分别3.615/16.308/22.964/7.030秒；包装器墙钟{smokes[0]['watchdog_wall_s']:.3f}秒。最大实际o17_d1（12成员/abreast/最大横向偏移133.82077373324597米）亦成功、attempts=1、post=0，优化11.910秒、包装器墙钟{smokes[1]['watchdog_wall_s']:.3f}秒；全实测最小间距4.233197535米，名义驻留期间实测最小约24.33081587米，名义到达跨度8.876780056秒，仅作诊断。全部5个保留结果独立磁盘复核通过，预警进入均1，P0清单[]。不增加成员驻留同步或Pd间距拒绝。

### 第二轮四意图门禁

| 意图 | 合同bytes一致 | 文件数 | 24进程墙钟秒 | 排除 |
|---|---|---|---|---|
{table}

本轮合计{sum(g['wall_s'] for g in gates):.3f}秒。四次watchdog的全部v08/tools源码SHA集合与当前源码完全一致；第3、4部分共享修改均已包含。第一轮80/80与本轮80/80合为两轮8组160/160，差异0，合同排除[]。每次24进程运行前后均通知用户。源码/冻结检查：100冻结整文件、5冻结源码对象、预置3SHA、两owner SHA全同。

### 共享修改及测试传播清单

本部分共享文件仅5个：v08/motion/optimize_checks.py新增检查；runner/joint_monitoring.py新增实测保留前分支；runner/joint_intent.py新增运行/保存/完整性/多样性分派；runner/skeleton_transit.py新增骨架/预建分派及本意图检查点；runner/transit_report.py新增五段及分侧时间映射分派。另新增专用close_observation_report、两个薄CLI和两份自加测试，共10个实现/测试文件。未修改monitoring_turn.py、冻结对象、旧测试或预置。

| 影响面 | 验证证据 |
|---|---|
| references/lines及无驻留旧路径 | 预置数值8、参考自加5、旧V8-13～18相关27文件及四旧意图字节门禁 |
| 七意图圈层/crossing与入口白名单 | 完整接口3、链路零次/多次进入负例、134旧回归、真实5键全约束复核 |
| runner预建/保存/多样性/worker默认 | 新分派显式声明，四旧意图门禁；新意图24/1及正式200/100/5留后续实测 |
| 缓存身份/命中/进程数 | 第3部分原oracle、冷/热/1对2进程审计；本轮旧门禁缓存全树bytes一致 |
| 递归字段与未知子键/路径 | 新自加结构反例、LP原输出集合一致、真实合同保存前窄白名单及磁盘复核；9.3后置独立扫描 |
| 五段闭合/测量首窗口/配对失败保留 | 链路自加10；真实smoke；200/100汇总与五意图外连接留第7部分 |

证据[part4_complete/summary.json](part4_complete/summary.json)，含全部测试原日志、四份门禁comparison/watchdog、smoke汇总、注入记录和原始合同/轨迹SHA索引。大轨迹留本地run，并未推送。生产预建只做过境式弦集合，下一步先执行2700秒止损，再执行不含预建的1800秒200骨架止损；任何未过均停，不进入快批。
'''
(DOC / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
print(json.dumps({"part4_complete": True, "gates": gates, "smoke_contracts": 5, "p0": []}))
