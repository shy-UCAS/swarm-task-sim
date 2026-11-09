import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
RUN = ROOT / "run"
DOC = BASE / "Simulation-v08/docs/v08/V8-19"
OUT = DOC / "part5"
read = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
pw, bone = read(RUN / "out/prewarm_r1/prewarm.json"), read(RUN / "out/skeleton_r1/summary.json")
diag = read(RUN / "diagnostics/part5_diagnostics_r1.json")
assert pw["families"] == 40 and pw["queries_total"] == 178 and pw["wall_s"] <= 2700
assert bone["complete"] and not bone["checkpoint"]["triggered"] and not bone["errors"] and bone["exceptions_attempts"] == 0
assert diag["same_source_as_second_gate"] and not diag["selected_point_violations"] and not diag["nominal_screen_violations"]
OUT.mkdir(exist_ok=False)
for name in ("prewarm_r1", "skeleton_r1"):
    target = OUT / name
    target.mkdir()
    for filename in ("summary.json", "prewarm.json", "dispatch_order.json", "by_bin.csv"):
        source = RUN / "out" / name / filename
        if source.exists():
            shutil.copyfile(source, target / filename)
    for filename in ("watchdog.json", "stdout.log", "stderr.log"):
        shutil.copyfile(RUN / "diagnostics" / name / filename, target / filename)
shutil.copyfile(RUN / "diagnostics/part5_diagnostics_r1.json", OUT / "dwell_diagnostics.json")
for filename in ("part5_diagnostics.py", "package_part5.py"):
    shutil.copyfile(ROOT / filename, OUT / filename)
index = []
for name in ("prewarm_r1", "skeleton_r1"):
    for p in (RUN / "out" / name).rglob("*"):
        if p.is_file():
            index.append({"path": str(p), "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
(OUT / "raw_evidence_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
summary = {"part": 5, "complete": True, "prewarm_wall_s": pw["wall_s"], "prewarm_limit_s": 2700,
           "prewarm_queries": pw["queries_total"], "dispatch_wall_s": bone["dispatch_wall_s"], "dispatch_limit_s": 1800,
           "checkpoint": bone["checkpoint"], "same_source_as_second_gate": True,
           "selected_point_violations": [], "nominal_screen_violations": [], "p0_triggered": [],
           "checked_utc": datetime.now(timezone.utc).isoformat()}
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
manifest = read(DOC / "manifest.json")
manifest["execution_status_at_part4"] = manifest.pop("execution_status")
manifest["execution_status"] = {"part": 5, "status": "complete", "evidence": "part5/summary.json", "next": "quick20 checkpoint"}
(DOC / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
report = (DOC / "REPORT.md").read_text(encoding="utf-8")
line = next(x for x in report.splitlines() if x.startswith("> **当前状态："))
report = report.replace(line, "> **当前状态：第1–5部分完成。两轮四意图160/160字节一致；生产预建454.082秒、200骨架200/200通过，全部止损未触发。20快批及全量/复跑尚未启动。**")
report += f'''

## 5. 弦集合预建与200合同只骨架——完成

第4部分提交`f3ce54744a743a84f881d8b0e4a8551e3120faf7`已推并ls-remote核对。完整四键smoke及最大实际查询、数值/接口/自加测试先通过；本部分没有改生产源码、阈值、抽样或测试预期。正式预建、骨架两次24进程分别通知后启动，源码SHA与第二轮门禁相同。预建不是全格驻留认证。

预建40族、178查询全部新写，原生墙钟{pw['wall_s']:.6f}秒，包装器456.032832秒，2700秒限未触发。实际最大族o11为404.116001秒，最大宽度来源o17为303.703036秒；各查询构建耗时累加7780.973315秒属于并发工作量，不是墙钟。第3部分单查询乘查询数/24约158秒只是估计，不是上界；正式454秒与原参考约7分钟及过境448秒同量级，真实族差异/并发调度以本次明细为准。smoke缺失查询只在进程内计算、不写盘，本次日志新写178才是正式缓存写入数。

| 止损项 | 实测 | 原门槛 | 结论 |
|---|---|---|---|
| 预建墙钟 | {pw['wall_s']:.6f}秒 | >2700秒 | 通过 |
| 成功数 | 200/200 | <190/200 | 通过 |
| 实际人数三档相对总体差 | 0；各110/110、56/56、34/34 | >10个百分点 | 通过 |
| 成功骨架尝试中位数 | 1 | >1 | 通过 |
| shape_audit_failed率 | 0/208 | >5% | 通过 |
| 骨架派发墙钟（不含预建） | {bone['dispatch_wall_s']:.6f}秒 | >1800秒 | 通过 |

骨架包装器38.548326秒；原生总墙钟{bone['wall_s']:.6f}秒。全部200记录和唯一键齐全，无异常/缺失/重复，不可行名单[]。208次尝试由200成功＋边界穿越普通失败4＋进场路由失败3＋驻留空集1组成；失败后仍沿原20次唯一预算，没有换格内重抽。o17_d1/o17_d4/o34_d3均成功、attempts=1并正常进入分母。直线回退0/200，仅诊断，不新增回退止损。

成功合同骨架耗时分布：min0.684634、p10=1.444325、p50=3.403495、p90=7.971408、max20.655529秒。驻留集合201次扫描含1次空集；非空集合min38、p50=322、p90=676、max1089。时长ticks min201、p50=680、p90=1111、max1197，全部在200..1200合法域内；不要求样本命中端点或直方图恰均匀。

969个成员的选中点warning SDF最大−13.341925米、alert最小53.170285米、base余量最小37.740920米；语义闭区间命中0、最小终点距离114.691763米（定义下界62.5米）。名义预筛全部通过，warning进入每成员恰1次。成员ta跨度p50=2.804569、p90=11.489692、最大28.600801秒；Pd两两最小距离的全局最小15.087243米。两者仅作诊断，不加同步等待/间距筛选。时长总和舍入差范围±2.273737e−13秒，原严格结束时刻解码等式未放宽。

全attempt成本p50/p90/max（秒）：LP 0.020635/0.946590/1.534885；驻留扫描0.347495/1.455130/4.593784；名义切分/组装0.299804/0.752636/2.640280。冷/热最大单车道/弦集合另见第3部分，不能与已命中预建的本批混称。骨架200次缓存命中、缺失计算0；这些计数与成本全部在合同外。

证据[part5/summary.json](part5/summary.json)、[驻留诊断](part5/dwell_diagnostics.json)，包括两阶段完整命令/源码散列、预建逐查询/逐族结果、人数等分档表、原始输出SHA索引。骨架大计划与缓存留本地run；Git未推轨迹。当前P0清单[]，快批20检查点尚未测，不将本次骨架通过替代快批。
'''
(DOC / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
print(json.dumps(summary, ensure_ascii=False))
