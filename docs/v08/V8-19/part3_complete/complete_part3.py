import ast
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
CODE = REPO / "Multi-UAV SimpleGC"
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
DIAG = ROOT / "run/diagnostics"
DOC = REPO / "docs/v08/V8-19"
OUT = DOC / "part3_complete"
read = lambda p: json.loads(p.read_text(encoding="utf-8"))
manifest = read(DOC / "manifest.json")
prefix = read(DIAG / "part3_geometry_rng_r2/summary.json")
cache = read(DIAG / "part3_cache_audit_r1/summary.json")
maximum = read(DIAG / "part3_maximum_r1/summary.json")
lane = read(DIAG / "part3_max_single_lane_r1.json")
unit = read(DIAG / "part3_independent_tests_r3/summary.json")
assert prefix["complete"] and cache["complete"] and maximum["complete"] and unit["all_zero_exit"]
assert all(row["failure"] is None for row in prefix["rows"]) and maximum["failure"] is None
passes = 0
for row in unit["rows"]:
    text = (DIAG / "part3_independent_tests_r3" / row["log"]).read_text(encoding="utf-8")
    assert row["exit_code"] == 0 and "skipped" not in text
    passes += int(re.search(r"Ran (\d+) tests? in", text)[1])
assert passes == 23
selected = []
for source in (DIAG / "part3_geometry_rng_r2/o01_d0_plan.json", DIAG / "part3_geometry_rng_r2/o02_d0_plan.json",
               DIAG / "part3_maximum_r1/plan.json"):
    rec = read(source)["record"]
    diag = rec["witnesses"]["dwell_diagnostics"]
    members = list(diag["members"].values())
    for member in members:
        assert member["warning_sdf_m"] <= -12.5 and member["alert_sdf_m"] >= 12.5 and member["base_min_margin_m"] >= 0.
        sd = member["member_station_m"]
        assert not any(a <= sd <= b for a, b in member["semantic_ranges_m"])
        assert member["endpoint_distance_m"] >= 62.5
    assert all(s["passed"] and s["counts"]["visits"] == 1 for s in rec["witnesses"]["screen"].values())
    selected.append({"source": str(source), "members": len(members), "dwell": rec["proposal"]["dwell"],
        "min_warning_sdf_m": min(m["warning_sdf_m"] for m in members), "max_warning_sdf_m": max(m["warning_sdf_m"] for m in members),
        "min_alert_sdf_m": min(m["alert_sdf_m"] for m in members), "min_base_margin_m": min(m["base_min_margin_m"] for m in members),
        "min_endpoint_distance_m": min(m["endpoint_distance_m"] for m in members),
        "member_arrival_span_s": diag["member_arrival_span_s"], "pd_min_pair_distance_m": diag["pd_min_pair_distance_m"]})
for path, expected in manifest["frozen_files"].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
for row in manifest["frozen_symbols"]:
    text = Path(row["path"]).read_text(encoding="utf-8")
    node = next(n for n in ast.parse(text).body if getattr(n, "name", None) == row["qualname"])
    assert hashlib.sha256(ast.get_source_segment(text, node).encode()).hexdigest() == row["sha256"]
for name, row in manifest["presets"].items():
    assert hashlib.sha256((CODE / "tests/v08/V8-19" / name).read_bytes()).hexdigest() == row["sha256"]
for path, expected in manifest["preserved_owner_files"].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
OUT.mkdir(exist_ok=False)
for name in ("part3_independent_tests_r3", "part3_geometry_rng_r2", "part3_cache_audit_r1", "part3_maximum_r1"):
    target = OUT / name
    target.mkdir()
    for source in (DIAG / name).rglob("*"):
        if source.is_file() and not source.name.endswith("_plan.json") and source.name != "plan.json":
            shutil.copyfile(source, target / source.name)
for name in ("part3_geometry_rng_r2.log", "part3_cache_audit_r1.log", "part3_maximum_r1.log", "part3_max_single_lane_r1.json"):
    shutil.copyfile(DIAG / name, OUT / name)
for name in ("audit_geometry_cache_r2.py", "single_lane_cost.py", "complete_part3.py", "run_units_r3.py"):
    shutil.copyfile(ROOT / "part3_lp_resume" / name, OUT / name)
raw = [p for folder in ("part3_geometry_rng_r2", "part3_cache_audit_r1", "part3_maximum_r1", "part3_independent_tests_r3")
       for p in (DIAG / folder).rglob("*") if p.is_file()]
index = [{"path": str(p), "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in raw]
summary = {"part": 3, "complete": True, "source_commit": "d297cc363156dc4a9e34e12773d53be1a24e43dc", "quick_tests_passed": passes,
    "prefix_audit_wall_s": prefix["wall_s"], "cache_audit_wall_s": cache["wall_s"], "maximum_audit_wall_s": maximum["wall_s"],
    "selected_curve_diagnostics": selected, "maximum_query": maximum["source"], "estimated_prewarm_div24_s": maximum["estimated_total_divided_by24_s"],
    "estimated_max_family_s": maximum["estimated_max_family_work_s"], "estimate_is_measured_upper_bound": False,
    "frozen_files_equal": 100, "frozen_symbols_equal": 5, "preset_sha_equal": True, "owner_sha_equal": True,
    "production_prewarm_status": "not_started; 2700s stop unchanged", "full_chain_smoke_status": "part4/5 before skeleton200",
    "p0_triggered": [], "raw_evidence": index, "checked_utc": datetime.now(timezone.utc).isoformat()}
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
manifest["execution_status_at_lp_fix"] = manifest.pop("execution_status")
manifest["execution_status"] = {"part": 3, "status": "complete", "evidence": "part3_complete/summary.json", "next": "part4 checks, measured events, recursive serialization, runner and final shared-code gate"}
(DOC / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
report = (DOC / "REPORT.md").read_text(encoding="utf-8")
current = next(line for line in report.splitlines() if line.startswith("> **当前状态："))
report = report.replace(current, "> **当前状态：第3部分完成。获准LP子键修正后23项快速检查、两键几何/RNG、冷/热/1对2进程缓存审计及最大查询均通过。第4部分待完整接入；第二轮门禁尚未运行。历史失败证据保留。**")
report = report.replace("## 第3部分恢复测试与真实几何检查——当前停止", "## 第3部分恢复测试与真实几何检查——5525894停止记录（历史）")
report += f'''

## 3. 驻留构造与成本审计——完成

LP修正单独提交`d297cc363156dc4a9e34e12773d53be1a24e43dc`并推送核对。结构测试直接调用原curve_lp，对照原输出子键集合和值；相关快速检查23/23通过（原独立16＋选点7）。现象/原因/改动沿上一节记录，重跑真实o01_d0/o02_d0均成功，无额外抽样、定义、阈值或预置变化。

- 同attempt对照：原6fe2e11的transit及transit_chords从Git对象原样载入，与当前transit完整计划/曲线数组及全部purpose调用/状态相同。新意图在加驻留前同样一致，只列意图与缓存身份字段作为几何对照的身份差异；这不是合同树排除，合同比较仍[]。shape原对象末尾恰追加索引、ticks两次integers；connect/speed/formation调用及状态完全相同。两键总墙钟{prefix['wall_s']:.3f}秒。原空集不消费RNG的自加反例仍通过。
- 缓存审计：两个真实键各自冷缺失计算、热磁盘读取、1进程与2进程输出的完整计划JSON＋几何数组SHA全部相同，失败均None，墙钟{cache['wall_s']:.3f}秒。该审计不替代后续5键完整轨迹合同复跑；新缓存身份/目录/内存键独立，旧默认不改。
- 最大实际查询为o17_d1、12成员abreast、绝对横向最大133.82077373324597米、地图5000米；登记178个查询，每族最多5个。单条极端偏移车道冷{lane['cold_total_s']:.6f}秒、热{lane['hot_s']:.8f}秒；12车道批冷{maximum['lane_cold_s']:.6f}秒另列，不混称单车道。
- 弦集合冷{maximum['chord_cold_s']:.6f}秒、热{maximum['chord_hot_s']:.6f}秒，8870格/1172可行；冷/热及旧transit格几何逐项相同。最大实际整骨架{maximum['whole_skeleton_s']:.6f}秒，LP {maximum['attempt_timing']['lp_s']:.6f}秒、驻留扫描{maximum['attempt_timing']['dwell_set_s']:.6f}秒、切分参考{maximum['attempt_timing']['dwell_reference_s']:.6f}秒，失败None。只检查已选LP曲线，没有全格驻留预建。
- 按该单查询实测乘登记查询数，总负载/24约{maximum['estimated_total_divided_by24_s']:.3f}秒，最大单族约{maximum['estimated_max_family_work_s']:.3f}秒；地图/几何差异与调度开销尚在，明确不是实测上界或新的止损线。生产预建尚未启动，正式执行仍以2700秒止损；200骨架另限1800秒，不含预建。

三个实际计划（两键及最大查询）的所有成员选中点均满足warning≤−12.5、alert≥12.5、base≥0、原语义闭区间命中0、终点距离≥62.5，名义screen通过且进入1次；原始值和ta跨度/Pd距离见[part3_complete/summary.json](part3_complete/summary.json)。100冻结文件/5对象、预置3SHA、owner2SHA全同。原始大计划留run，Git仅保存SHA索引、RNG状态、计时和汇总，不把骨架审计冒称优化/仿真验证。

第3部分按主指令提交3验收完成。第4部分将补check_close_observation、实测、严格递归序列化、运行器/报告/CLI和测试；所有共享代码完成后再第二轮四意图门禁。完整4键生产链smoke在200骨架前执行，当前未执行。
'''
(DOC / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
print(json.dumps({"part3_complete": True, "tests_passed": passes, "walls_s": [prefix["wall_s"], cache["wall_s"], maximum["wall_s"]]}, ensure_ascii=False))
