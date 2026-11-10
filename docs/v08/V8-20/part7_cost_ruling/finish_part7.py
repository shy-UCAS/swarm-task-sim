"""Archive final part-seven evidence after the independent artifact preset."""
import datetime
import shutil
from evidence_utils import *

full = ROOT / "full/area_cost_ruling_r1"
rerun = ROOT / "rerun/area_cost_ruling_r1"
analysis = ROOT / "part7_analysis_cost_ruling_r1"
out = DOC / "part7_cost_ruling"
assert not out.exists()
summary = read(full / "summary.json")
rows = read(full / "records.json")
div = read(full / "diversity/records.json")
rep = read(rerun / "reproduction.json")
artifacts = read(ROOT / "artifact_preset_cost_ruling_r1.json")
assert summary["complete"] and summary["diversity_complete"] and not summary["checkpoint"]["triggered"]
assert not summary["retained_p0_violations"] and rep["all_equal"] and rep["exclusions"] == []
assert artifacts["exit_code"] == 0 and artifacts["tests_run"] == 3 and artifacts["skipped"] == 0
assert read(analysis / "complete.json")["complete"]
changes = audit()
assert not changes, changes
stats = read(analysis / "diagnostics.json")
pairs = read(analysis / "six_intent_pairing.json")
watch = read(ROOT / "full_watchdog_cost_ruling_r1.json")
serial = read(ROOT / "rerun_watchdog_cost_ruling_r1.json")
elapsed = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(watch["started_utc"])).total_seconds()
disk = read(full / "disk_verification.json")
assert not any(value["p0_violations"] for value in disk.values())
checkpoint = {"part": 7, "passed": True, "main": len(rows), "main_success": sum(r["success"] for r in rows),
    "diversity": len(div), "diversity_success": sum(r["success"] for r in div), "checkpoint": summary["checkpoint"],
    "full_wrapper_wall_s_including_disk_reverification": watch["wall_s"], "serial_five_wall_s": serial["wall_s"],
    "artifact_preset_wall_s": artifacts["wall_s"], "part7_elapsed_s": elapsed,
    "serial_five_all_equal": rep["all_equal"], "contract_exclusions": [], "artifact_preset": artifacts,
    "audit_changes": changes, "public_pairing_difference_contracts": pairs["public_difference_contracts"],
    "public_pairing_missing_contracts": pairs["public_missing_contracts"],
    "owner_independent_final_acceptance": "pending_planning_reviewer_rerun"}
out.mkdir()
for source, name in ((full / "summary.json", "full_summary.json"), (full / "records.json", "full_records.json"),
    (full / "rerun_keys.json", "predeclared_five.json"), (full / "disk_verification.json", "disk_verification.json"),
    (rerun / "reproduction.json", "reproduction.json"), (rerun / "records.json", "rerun_records.json"),
    (analysis / "diagnostics.json", "diagnostics.json"), (analysis / "six_intent_pairing.json", "six_intent_pairing.json"),
    (ROOT / "artifact_preset_cost_ruling_r1.log", "artifact_preset.log"),
    (ROOT / "precheck_full_cost_ruling_r1.json", "precheck.json"),
    (ROOT / "full_watchdog_cost_ruling_r1.json", "full_watchdog.json"),
    (ROOT / "rerun_watchdog_cost_ruling_r1.json", "rerun_watchdog.json")):
    shutil.copyfile(source, out / name)
dump(out / "evidence_index.json", index(full) + index(rerun) + index(analysis))
elapsed = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(watch["started_utc"])).total_seconds()
checkpoint["part7_elapsed_s"] = elapsed
dump(out / "checkpoint.json", checkpoint)
for name in ("evidence_utils.py", "precheck_formal.py", "run_formal_stage.py", "analyze_part7.py", "run_artifact_preset.py", "finish_part7.py"):
    shutil.copyfile(TASK / name, out / name)
a = read(DOC / "acceptance.json")
assert len(a["outputs"]) == 2 and a["rerun"] == str(rerun)
a["part7_checkpoint"] = str(out / "checkpoint.json")
a["status"] = "execution_checks_passed_part8_delivery_pending_owner_acceptance"
dump(DOC / "acceptance.json", a)
with (DOC / "REPORT.md").open("a", encoding="utf-8", newline="\n") as f:
    f.write("\n\n## 第 7 部分：主批、多样性、复跑与配对——执行检查通过\n\n")
    f.write(f"固定主批完成 {len(rows)}/200，成功 {checkpoint['main_success']}/200；多样性完成 {len(div)}/100，成功 {checkpoint['diversity_success']}/100。主批/多样性共用原派发，无预登记剔除；总派发墙钟 {summary['dispatch_wall_s']:.6f} s，含完整磁盘复核的运行器墙钟 {watch['wall_s']:.6f} s，不含已单列预建。完整原检查点：{json.dumps(summary['checkpoint'], ensure_ascii=False)}。\n\n")
    f.write(f"Fréchet scope 为 area_search_warning_entry_to_last_exit_v20：共同绝对时刻的成员名义平均与优化位移平均，各自最早入圈至最晚出圈，独立按几何弧长 5 m 重采样、保留端点。可比较对 {stats['frechet_pair_count']}，合并所有有效对后、除原公共横向间距一次的 before/after 中位数为 {stats['frechet_before']} / {stats['frechet_after']}。逐 branch 端点、窗口和 N/A 原因均保存；该分开后平均指标只作继承诊断，P3⑥仍需重定义。\n\n")
    f.write(f"全量开始前已保存 o01_d0..d4，单进程同环境同缓存复跑 {serial['wall_s']:.6f} s，完整合同 5/5 原始字节相同，成功和失败均比较，排除 []。原样完整产物预置 3/3、skip 0，墙钟 {artifacts['wall_s']:.6f} s；该测试独立读取所有快批/主批/多样性轨迹、S、事件和冻结核验，并复核全部 10 门禁与固定五键。日志原始字节保留，不做代码空白修整。\n\n")
    f.write(f"六意图同 (order,draw) 外连接 {pairs['outer_join_count']} 行，七个公共字段差异合同 {pairs['public_difference_contracts']}、缺字段合同 {pairs['public_missing_contracts']}，各意图获胜 attempt 单列。area/transit 都有胜出几何 {pairs['both_winning_geometry_count']} 行，其中同 theta/h {pairs['equal_theta_h_count']}，同队形及 slots {pairs['equal_formation_slots_count']}；没有强制同格或改变均匀抽样。transit 原合同无 Q/beta，额外诊断仅用其既有弦在对应区域 S 外轮廓求交，明确独立命名；原字段无值保留 N/A。\n\n")
    f.write(f"主批所有失败尝试 {stats['failed_attempt_count']}，唯一主 stage 与 stage/reason 交叉表、可重叠子条件按 attempt 去重及成员出现次数另列；每合同首次失败表包括最终成功前失败，无失败记 none。五段逐成员闭合与释放/保持分布、全可见 201 帧同窗 A/B 最近驻留余量、实际覆盖（可算失败也保留）、最短覆盖弧和最小间距成员对/整数微秒帧/双成员相位全部见 diagnostics.json。\n\n")
    f.write(f"保留覆盖率分布 {json.dumps(stats['coverage_fraction_retained'], ensure_ascii=False)}；驻留余量分布 {json.dumps(stats['closest_dwell_margin_m'], ensure_ascii=False)}；实测方位跨度分布 {json.dumps(stats['azimuth_span_deg'], ensure_ascii=False)}，超过 110° {stats['measured_azimuth_over_110_diagnostic_only']} 人只作诊断。最小实测间距分布 {json.dumps(stats['separation_m'], ensure_ascii=False)}，采用冻结 quality 阈值，不替换为优化 3 m 或条带 40 m。\n\n")
    f.write(f"本部分截至证据收集共 {elapsed:.6f} s；所有保留段独立磁盘复算通过，冻结/owner/输入/预置/配置与门禁后源码差异 0。按人数/队形的几何分布、径向/偶数 c/最小 inner 与 N 的相关局限列 P3⑥，不新增时长/路程/几何拒绝条件。当前为执行检查通过，最终研究接受仍需规划审查方独立复跑 P0 证据。\n")
with (DOC / "RUNNING.md").open("a", encoding="utf-8", newline="\n") as f:
    f.write(f"\n第 7 部分完成：full+div 运行器 {watch['wall_s']:.6f}s；serial5 {serial['wall_s']:.6f}s；原样产物预置3/3、skip0。各阶段输出和完整合同 SHA 索引见 part7_cost_ruling/。使用 --prewarm-from 复用第 5 部分 prewarm.json，预建不重复计入 skeleton/quick/full。\n")
print(json.dumps(checkpoint, ensure_ascii=False), flush=True)
