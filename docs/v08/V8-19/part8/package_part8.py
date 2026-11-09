import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
DOC = BASE / "Simulation-v08/docs/v08/V8-19"
DIAG = ROOT / "run/diagnostics"
OUT = DOC / "part8"
read = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
audit, tests, snap = read(DIAG / "final_audit.json"), read(DIAG / "artifact_tests_r1_watch.json"), read(DIAG / "snapshot_final_watch.json")
log = (DIAG / "artifact_tests_r1.log").read_text(encoding="utf-8")
assert audit["complete"] and tests["exit_code"] == snap["exit_code"] == 0
assert re.search(r"Ran 3 tests in", log) and "skipped" not in log and "FAILED" not in log and re.search(r"\nOK\s*$", log)
assert read(DOC / "part7/summary.json")["complete"]
OUT.mkdir(exist_ok=False)
for name in ("artifact_tests_r1.log", "artifact_tests_r1_watch.json", "snapshot_final.json", "snapshot_final.log", "snapshot_final_watch.json", "final_audit.json", "final_audit.log", "final_audit_initial_expectation.json"):
    shutil.copyfile(DIAG / name, OUT / name)
for name in ("run_artifact_tests.ps1", "run_final_snapshot.ps1", "final_audit.py", "final_audit_before_scope_correction.py", "prepare_acceptance.py", "package_part8.py"):
    shutil.copyfile(ROOT / name, OUT / name)
summary = {"part": 8, "complete": True, "artifact_tests_passed": 3, "artifact_skipped": 0,
           "artifact_wall_s": tests["wall_s"], "snapshot_wall_s": snap["wall_s"], "final_audit_passed": True,
           "branch": audit["branch"], "fixed_key_counts": {"quick": 20, "main": 200, "diversity": 100, "rerun": 5},
           "old_gates_equal": 160, "serial_keys_equal": 5, "all_contract_exclusions": [],
           "reviewer_independent_rerun": "not performed by this executor", "p0_triggered": [],
           "checked_utc": datetime.now(timezone.utc).isoformat()}
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
manifest = read(DOC / "manifest.json")
manifest["execution_status_at_part7"] = manifest.pop("execution_status")
manifest["execution_status"] = {"part": 8, "status": "complete", "evidence": "part8/summary.json", "p0_triggered": [], "pending_rule_decisions": []}
(DOC / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
report = (DOC / "REPORT.md").read_text(encoding="utf-8")
line = next(x for x in report.splitlines() if x.startswith("> **当前状态："))
report = report.replace(line, "> **当前状态：八部分完成。原样产物预置9.3三项全部通过、无跳过；最终冻结/输入/owner/旧缓存审计通过。两轮旧意图160/160、主200/200、多样性100/100、串行5/5均通过，全部止损未触发，P0清单[]。仅交付审查分支，独立审查复跑和合并未执行。**")
report = report.replace("依次为[r,t_in]、[t_in,t_a]、[t_a,t_b]、[t_b,t_out]、[t_out,e]", r"依次为\([r,t_{\mathrm{in}}]\)、\([t_{\mathrm{in}},t_a]\)、\([t_a,t_b]\)、\([t_b,t_{\mathrm{out}}]\)、\([t_{\mathrm{out}},e]\)")
report += f'''

## 8. 独立产物验收、最终冻结审计与交付——完成

在两轮8组门禁、正式20/200/100及固定5键结果齐全后生成[acceptance.json](acceptance.json)，设置V8_19_ACCEPTANCE原样运行9.3：**3/3通过，0跳过、0失败**，测试体与包装器实测见[原日志](part8/artifact_tests_r1.log)、[watch](part8/artifact_tests_r1_watch.json)；包装器{tests['wall_s']:.6f}秒。预置没有修改断言、独立预期、阈值或字面内容。此前依赖不齐的setUpClass跳过仍只算历史未运行，本轮完整通过才算验收。

预置独立检查了8组160个合同的全部原bytes、所有正式快批20/主200/多样性100的固定名单与合同字段、成功轨迹10Hz/有限性/圈层/间距/冻结段判定、首个False退出和冻结首个驻留窗口、两条正交等式控制点，以及5键串行全部文件。没有以生成器自身过滤器或success字段代替独立预期，所有合同树排除[]。最终快速测试33＋真实注入1＋产物3共37项新测试通过，相关旧27文件134项通过；旧SceneGate仍沿已接受替代，未重复运行，不算本轮通过。

最终只读快照包装器{snap['wall_s']:.6f}秒，[首尾审计](part8/final_audit.json)确认：100冻结整文件、5冻结函数/类源码、160输入、22个v07目录统计、两冻结工作树HEAD/clean、monitoring_turn.py整文件、全部登记旧预置及本轮3份预置、29族155旧佯动存在性文件SHA/大小/mtime、两owner文件SHA均保持。两owner仍未跟踪，不提交、不删除。所有模块改动/新增均在主指令0.2授权清单内；生产阶段源码与第二轮门禁完整一致，最终唯一后续源码变化是第7部分专用分析CLI的统计修正，其前后SHA与快速检查已归档，不改变合同或旧意图路径。

### 自加最终审计预期修正

首次自加审计错误地要求初始24项细粒度散列全不变，因此在主指令2.3明确允许编辑的references_from_skeleton处失败。只读核对发现唯一差异是函数文档后新增的4行非空dwell_windows分派，原无驻留主体没有改动；它不是冻结NominalPVA，也不是预置9.3失败。依据第3部分裁定第2节自加预期修正授权，修正审计脚本：其余23项仍逐SHA核对，此获准项从6fe2e11原Git对象提取函数，移除当前唯一新增if分派后与原函数源码逐字相同。重跑首尾审计通过，100文件和5冻结对象的严格SHA比较没有放宽，生产代码没有再改。首次预期/脚本和修正后脚本、数值及原始log全部保留于part8。

### 八部分结论与实测耗时

以下是实测登记/运行分项；开发时间没有完整独立计时，不把分项相加冒称总开发墙钟。历史失败/恢复的原始用时和证据仍保留在前文。

| 部分 | 最终结论 | 实测分项秒 |
|---|---|---|
| 1 | 登记、冻结、基线；旧134通过 | 登记至检查点562.622 |
| 2 | 锚点/等式通过；第一轮80/80 | 四门禁1177.780 |
| 3 | LP结构、几何/RNG、冷/热/进程及最大查询通过 | 几何41.766、缓存54.822、最大查询26.419；单车道冷1.370另列 |
| 4 | 新33＋真实注入1、旧134通过；第二轮80/80；5键smoke通过 | 门禁566.509；两smoke包装器193.114＋53.902 |
| 5 | 预建、200骨架及全部止损通过 | 预建454.082；骨架派发36.018（不含预建） |
| 6 | 20/20快批及独立磁盘复核通过 | 包装器103.717；全20优化中位数6.855 |
| 7 | 主200/200、多样性100/100；串行5/5、配对通过 | 全量含独立复核722.452；串行61.716；初版分析25.525，修正后另见watch |
| 8 | 原样产物3/3及最终冻结审计通过 | 产物包装器{tests['wall_s']:.3f}；快照{snap['wall_s']:.3f} |

### 所有止损项最终取值

| 检查点 | 取值 | 原触发线 | 结果 |
|---|---|---|---|
| 预建 | 454.082秒 | >2700秒 | 未触发 |
| 骨架成功 | 200/200 | <190/200 | 未触发 |
| 骨架人数档差 | 0个百分点 | >10个百分点 | 未触发 |
| 成功骨架attempt中位数 | 1 | >1 | 未触发 |
| 形状复核失败 | 0/208 | >5% | 未触发 |
| 骨架派发 | 36.018秒 | >1800秒 | 未触发 |
| 快批成功 | 20/20 | <16/20 | 未触发 |
| 快批post失败中位数 | 0 | >0 | 未触发 |
| 全20优化耗时中位数 | 6.854912400秒 | >60秒 | 未触发 |
| 全量主批成功 | 100% | <80% | 未触发 |
| 全量设施/速度/人数档差 | 0/0/0个百分点 | 任一>20个百分点 | 未触发 |
| 全量post失败中位数 | 0 | >0 | 未触发 |
| 合并归一Fréchet | 88.256086970，450有效对 | <1或无有效对 | 未触发 |
| 三项P0 | 旧160/160；保留违规0；串行5/5 | 任一违规/不一致 | [] |

新意图完整正式20/200/100/5名单无例外，o17_d1/d4与o34_d3正常计分母。各部分分开提交，失败历史也已推送；仅推review/v08/V8-19-close-observation并逐次ls-remote核对，不推main、不强推、不合并dev。最终完整SHA与远端回执另存本地run/diagnostics/delivery_part8.json，以本报告所属Git提交为准，避免文档自引用SHA。

原始缓存、合同轨迹、机器相关遥测继续留本地run，Git保存实现、原样预置、脚本、汇总、诊断与逐文件SHA索引。报告中的执行方复核不冒称审查方独立复跑；RUNNING给出新目录复现方式。

### 需要审查方判断的事项

1. 无剩余定义冲突或待裁定修复。请审查实现、证据及两次明确记录的统计/自加审计修正是否接受；它们没有改变生产行为、阈值、抽样或预置。
2. 成员到达跨度最大28.600801秒、首个20秒驻留窗口在名义到达前约5.904–9.048秒开始，均按既有裁定仅作诊断，没有新加同步或偏差上限。研究解释由审查方评估。
3. 后续独立复跑及是否合并dev由审查方决定，本任务只交付审查分支。原始大数据留本机；跨机审查可依RUNNING复现并核对索引。
'''
(DOC / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
running = (DOC / "RUNNING.md").read_text(encoding="utf-8")
running += '''

本轮已完成全部阶段，固定20/200/100/5与两轮8组门禁均通过，最终原样9.3为3/3无跳过。第7部分专用分析CLI仅修正合同级到达跨度重复计数；生产源码/轨迹与第二轮门禁没有变化。结果字段和修正前后证明见part7/analysis/arrival_span_fix.json。

五意图分析可按以下参数用新输出目录重现；数据根应指向要审查的那一次全量，例如上文owner_r1：

```powershell
$taskBase = 'F:\\CASIA\\Drone Swarm Situational Awareness Algorithm'
$analysisArgs = @('run','-n','llm','--no-capture-output','python','-B','tools/v08/analyze_close_observation_v19.py',
    '--monitoring',(Join-Path $taskBase '_handoff/2026-11-04_V8-14_skeleton/out/full_v14c'),
    '--transit',(Join-Path $taskBase '_handoff/2026-11-05_V8-16_transit/run/out/full_transit_r2'),
    '--intrusion',(Join-Path $taskBase '_handoff/2026-11-06_V8-17_intrusion/run/out/full/full_r1'),
    '--feint',(Join-Path $taskBase '_handoff/2026-11-06_V8-18_feint/run/out/full_lazy_r1'),
    '--close-observation',(Join-Path $runRoot 'out/full_owner_r1'),
    '--out',(Join-Path $runRoot 'diagnostics/analysis_owner_r1'))
& $condaExe @analysisArgs
```

最终只读快照/审计和产物测试的实际命令、日志与脚本位于part8。大轨迹留本地run；任何复现请用全新目录，不覆盖原结果或历史失败。
'''
(DOC / "RUNNING.md").write_text(running, encoding="utf-8", newline="\n")
print(json.dumps(summary, ensure_ascii=False))
