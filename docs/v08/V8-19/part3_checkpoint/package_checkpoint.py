"""Preserve the failed checkpoint and unapplied review suggestions, without fixing or rerunning it."""
import ast
import difflib
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
CODE = REPO / "Multi-UAV SimpleGC"
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
DIAG = ROOT / "run/diagnostics"
DOC = REPO / "docs/v08/V8-19"
OUT = DOC / "part3_checkpoint"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def counts(text):
    ran = re.search(r"Ran (\d+) tests? in ([\d.]+)s", text)
    assert ran, "missing unittest result"
    skipped = re.search(r"skipped=(\d+)", text)
    failures = re.search(r"failures=(\d+)", text)
    errors = re.search(r"errors=(\d+)", text)
    n = int(ran[1])
    failed, error, skip = (int(x[1]) if x else 0 for x in (failures, errors, skipped))
    return {"run": n, "passed": n - failed - error - skip, "failures": failed, "errors": error, "skipped": skip,
            "unittest_wall_s": float(ran[2])}


manifest = read(DOC / "manifest.json")
diagnosis = read(DIAG / "part3_failed_fixture_diagnosis_r1.json")
test = CODE / "tests/v08/V8-19/test_extra_selected_curve_v19.py"
assert hashlib.sha256(test.read_bytes()).hexdigest() == diagnosis["test_sha256"], "failed test changed"
selected = counts((DIAG / "part3_selected_curve_unit_r1.log").read_text(encoding="utf-8"))
assert (selected["run"], selected["failures"], selected["errors"]) == (5, 1, 0)
independent = read(DIAG / "part3_independent_tests_r1/summary.json")
assert independent["all_zero_exit"]
independent_counts = [counts((DIAG / "part3_independent_tests_r1" / row["log"]).read_text(encoding="utf-8"))
                      for row in independent["rows"]]
assert sum(x["passed"] for x in independent_counts) == 16
old_rows, old_counts, old_wall = [], [], 0.
for name in ("part3_old_tests_r1", "part3_old_tests_remainder_r1"):
    data = read(DIAG / name / "results.json")
    old_wall += data["wall_s"]
    for row in data["rows"]:
        old_rows.append(row)
        old_counts.append(counts((DIAG / name / row["log"]).read_text(encoding="utf-8")))
assert len(old_rows) == 27
assert sum(x["run"] for x in old_counts) == 134
assert sum(x["errors"] for x in old_counts) == 2
assert sum(x["failures"] + x["skipped"] for x in old_counts) == 0
identity = read(DIAG / "part3_identity_audit_r1.json")
assert identity["all_legacy_equal"] and identity["all_new_isolated"]
presets_equal = all(hashlib.sha256((CODE / "tests/v08/V8-19" / name).read_bytes()).hexdigest() == row["sha256"]
                    for name, row in manifest["presets"].items())
assert presets_equal
for path, expected in manifest["frozen_files"].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
for row in manifest["frozen_symbols"]:
    text = Path(row["path"]).read_text(encoding="utf-8")
    node = next(n for n in ast.parse(text).body if getattr(n, "name", None) == row["qualname"])
    assert hashlib.sha256(ast.get_source_segment(text, node).encode()).hexdigest() == row["sha256"]
for path, expected in manifest["preserved_owner_files"].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
old_test = "Multi-UAV SimpleGC/tests/v08/V8-16/test_extra_local_v16.py"
old_raw = subprocess.check_output(["git", "show", f"6fe2e11:{old_test}"], cwd=REPO)
assert hashlib.sha256(old_raw.replace(b"\r\n", b"\n")).hexdigest() == hashlib.sha256((REPO / old_test).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
assert head == "aec7ca6d7c2b30087b8c67f5090299f9cee4fcf2"
new_files = ["v08/motion/intents/close_observation.py", "tests/v08/V8-19/test_extra_selected_curve_v19.py"]
changed_files = ["v08/motion/intents/transit.py", "v08/motion/transit_chords.py", "v08/runner/joint_intent.py"]
source_sha = {str(f.relative_to(CODE)): hashlib.sha256(f.read_bytes()).hexdigest()
              for root in (CODE / "v08", CODE / "tools/v08") for f in root.rglob("*.py")}
source_sha["tests/v08/V8-19/test_extra_selected_curve_v19.py"] = diagnosis["test_sha256"]
stop_time = datetime.fromtimestamp((DIAG / "part3_selected_curve_unit_r1.log").stat().st_mtime, timezone.utc)
start_stat = (ROOT / "part3_work/prepare_shared.py").stat()
start_time = datetime.fromtimestamp(getattr(start_stat, "st_birthtime", start_stat.st_ctime), timezone.utc)
now = datetime.now(timezone.utc)
summary = {"status": "stopped_at_part3_quick_checkpoint", "source_parent": head,
    "part3_first_prepare_utc": start_time.isoformat(), "first_failed_check_utc": stop_time.isoformat(),
    "first_prepare_to_failure_s": (stop_time - start_time).total_seconds(),
    "first_prepare_to_package_s": (now - start_time).total_seconds(),
    "selected_curve_tests": selected, "independent_tests": {"run": 16, "passed": 16, "wall_s": independent["wall_s"]},
    "old_tests": {"files": 27, "run": 134, "passed": 132, "errors": 2, "failures": 0, "wall_s": old_wall,
                  "errors_in": "V8-16/test_extra_local_v16.py", "unchanged_since_baseline": True},
    "identity_cases": 28, "all_old_identity_equal": True, "all_new_identity_isolated": True,
    "preset_sha_unchanged": presets_equal, "frozen_files_equal": 100, "frozen_symbols_equal": 5,
    "owner_files_unchanged": True, "modified_implementation": changed_files, "new_implementation_and_tests": new_files,
    "source_sha256": source_sha, "p0_triggered": [], "retained_close_observation_contracts": 0,
    "prewarm": {"measured_wall_s": None, "limit_s": 2700, "status": "not_started"},
    "skeleton200": {"measured_wall_s": None, "limit_s": 1800, "status": "not_started",
                    "successes": None, "population": 200, "required_successes": 190, "group_gap_limit": .10,
                    "successful_attempt_median": None, "limit_attempt_median": 1, "shape_failure_rate": None, "shape_failure_limit": .05},
    "quick20": {"successes": None, "population": 20, "required_successes": 16, "post_median": None,
                "post_limit": 0, "optimization_s_median": None, "optimization_s_limit": 60, "status": "not_started"},
    "full200_diversity100": {"success_rate": None, "required_rate": .8, "group_gap": None, "group_gap_limit": .2,
                             "post_median": None, "post_limit": 0, "frechet_median": None, "frechet_minimum": 1,
                             "comparable_pairs": None, "status": "not_started"},
    "serial5": {"identical": None, "expected_count": 5, "exclusions": [], "status": "not_started"},
    "not_run": diagnosis["not_run_after_checkpoint"], "artifact_9_3": "deferred; required results not generated",
    "checked_utc": now.isoformat()}
OUT.mkdir(exist_ok=False)
for name in ("part3_selected_curve_unit_r1.log", "part3_failed_fixture_diagnosis_r1.json", "part3_identity_audit_r1.json"):
    shutil.copyfile(DIAG / name, OUT / name)
for name in ("part3_independent_tests_r1", "part3_old_tests_r1", "part3_old_tests_remainder_r1"):
    shutil.copytree(DIAG / name, OUT / name)
for script in ("diagnose_checkpoint.py", "run_independent_presets.py", "run_related_tests_part3.py",
               "run_related_tests_part3_remainder.py", "identity_interface_audit_part3.py", "package_checkpoint.py"):
    shutil.copyfile(ROOT / "part3_work" / script, OUT / script)
write(OUT / "summary.json", summary)
write(DIAG / "part3_checkpoint_summary.json", summary)

# Concrete suggestions are deliberately un-applied. No test is executed against them.
test_text = test.read_text(encoding="utf-8")
old = '        self.assertTrue(result.witnesses["screen"]["m"]["passed"])'
new = '''        # This analytic fixture crosses the alert/protected disks; screening must reject its whole path.
        self.assertFalse(result.witnesses["screen"]["m"]["passed"])
        self.assertFalse(result.witnesses["screen"]["m"]["conditions"]["max_target_layer_one"])
        self.assertEqual(result.witnesses["screen"]["m"]["counts"]["max_target_layer"], 3)
        self.assertTrue(result.witnesses["screen"]["m"]["conditions"]["observation_dwell"])'''
assert test_text.count(old) == 1
(OUT / "PROPOSED_TEST_EXPECTATION.patch").write_text("".join(difflib.unified_diff(test_text.splitlines(True), test_text.replace(old, new).splitlines(True),
    fromfile="a/Multi-UAV SimpleGC/tests/v08/V8-19/test_extra_selected_curve_v19.py",
    tofile="b/Multi-UAV SimpleGC/tests/v08/V8-19/test_extra_selected_curve_v19.py")), encoding="utf-8", newline="\n")
transit_text = (CODE / "v08/motion/intents/transit.py").read_text(encoding="utf-8")
proposed = transit_text.replace('P = {"intent": task.intent, "theta_idx": int(ti)', 'P = {"intent": getattr(task, "intent", "transit"), "theta_idx": int(ti)')
proposed = proposed.replace('if task.intent == "close_observation" and plan.failure is None:', 'if P["intent"] == "close_observation" and plan.failure is None:')
assert proposed != transit_text
(OUT / "PROPOSED_LEGACY_STUB_COMPATIBILITY.patch").write_text("".join(difflib.unified_diff(transit_text.splitlines(True), proposed.splitlines(True),
    fromfile="a/Multi-UAV SimpleGC/v08/motion/intents/transit.py", tofile="b/Multi-UAV SimpleGC/v08/motion/intents/transit.py")), encoding="utf-8", newline="\n")

# The authority was corrected on disk after the original copy; preserve both versions and hashes.
ruling = ROOT / "V8-19_站点锚点裁定_20261108.md"
latest_sha = hashlib.sha256(ruling.read_bytes()).hexdigest()
if latest_sha != manifest["station_anchor_ruling"]["sha256"]:
    corrected = "V8-19_站点锚点裁定_20261108_依赖顺序更正.md"
    shutil.copyfile(ruling, DOC / "instructions" / corrected)
    manifest["station_anchor_ruling_corrected"] = {"source": str(ruling), "sha256": latest_sha,
        "copy": "instructions/" + corrected, "change": "section4 dependency order corrected; confirms user's explicit clarification"}
manifest["execution_status_at_part2_completion"] = manifest.pop("execution_status")
manifest["execution_status"] = {"part": 3, "status": summary["status"], "checkpoint": "part3_checkpoint/summary.json",
                                "p0_triggered": [], "retained_close_observation_contracts": 0}
for name, row in manifest["presets"].items():
    row["part1_status"] = row.pop("status")
    row["status"] = "通过8/8（本检查点）" if "numeric" in name else "通过3/3（本检查点）" if "geometry" in name else "后置：依赖产物未齐，历史setUpClass跳过不记通过"
write(DOC / "manifest.json", manifest)

report = (DOC / "REPORT.md").read_text(encoding="utf-8")
current = next(line for line in report.splitlines() if line.startswith("> **当前状态："))
report = report.replace(current, "> **当前状态：第2部分完成；第3部分快速检查停止：自加测试1项预期错误，旧回归2项桩接口错误。失败版本保留，代码及失败断言未修正；第3部分昂贵检查及第4–7部分未启动，P0未触发。**")
report += f'''

## 3. 实际曲线驻留构造——快速检查停止（当前）

第2部分门禁提交为`aec7ca6d7c2b30087b8c67f5090299f9cee4fcf2`，已推并ls-remote核对。从该版本接入缓存上层默认intent参数、新意图独立磁盘/内存身份、实际任务提案意图，以及原shape对象尾部追加驻留。新`close_observation.py`在已有完整成员映射上枚举5米站点，检查定义域、全部原语义闭区间、精确warning/alert/base余量；空集合直接普通失败，不换格。新预建分派只沿过境弦集合，不枚举LP或驻留格。白名单及诊断为初步实现，生产链尚未验证，不宣称第3部分完成。

### 首次失败及规则边界

[首轮自加日志](part3_checkpoint/part3_selected_curve_unit_r1.log)：5项实际执行，4通过、1失败，测试体耗时{selected['unittest_wall_s']:.3f}秒。失败是执行方新增`SelectedCurve.test_analytic_selected_point_and_two_tail_draws`中的全路径预筛通过断言。解析夹具为x=-450..450、y=0，alert半径160、protected半径100；它经过圆心，本来就违反原整段alert外10米约束。精确最小余量−170米，名义最大层3，所以`max_target_layer_one=False`，其他6项条件为True。**夹具预期错误由执行方引入；预筛拒绝该路径是正确行为。**

驻留本身选择参考/成员站点165米、Pd=(-285,0)、集合46点、200ticks（20秒）；warning SDF=-15、alert SDF=125米，驻留检测为True、进圈次数1，RNG仅调用(0,46)和(200,1201)。这不能证明整段有效，正是新增断言混淆了所选Pd和全路径。见[只读诊断](part3_checkpoint/part3_failed_fixture_diagnosis_r1.json)。

此失败不是≤1e-9的纯浮点表示问题，不能按站点裁定第3节直接修正。按用户“快速检查不过仍停”和主指令0.1.6的疑似预期错误流程，未改失败断言、阈值、抽样或源代码，未重跑失败测试。只读复算保留同一False条件，不作为修复后的通过证据。已附[未应用的自加预期修正建议](part3_checkpoint/PROPOSED_TEST_EXPECTATION.patch)：将该夹具明确作为负例，核对最大层3及驻留仍可检出；是否接受由审查方判断。原9.1–9.3预置未改。

### 独立检查结果与第二个问题

- 原样数值8/8、完整接口3/3、原自加参考5/5通过，合计16/16，独立检查墙钟{independent['wall_s']:.3f}秒。3份预置SHA仍逐项与原文一致。缓存接口通过只证明identity接口，不替代冷/热/1对2进程生产缓存审计。
- 28个identity用7b16f96原函数作oracle：旧默认与显式transit全同、新close全隔离。
- 相关旧测试27文件全部执行，共134项：132通过、2 error、0断言失败，墙钟两段合计{old_wall:.3f}秒。首段在第17文件发现错误后，另跑余下10文件，未重跑失败文件。旧SceneGate按此前已接受替代未重做；产物9.3按用户澄清后置，未记通过。
- 两项error均在未改的`V8-16/test_extra_local_v16.py`：`test_entry_route_failure_keeps_cell_and_formation`和`test_uniform_cell_index_single_draw_and_no_regrid`。测试原先向私有`T._build_with_cells`传`NS(target_id="t")`，新实现提案参数化直接取`task.intent`，因桩没有此属性抛AttributeError。已核对该旧测试与6fe2e11原文一致。不是旧合同bytes差异的证明，也不是浮点授权范围。代码和旧测试均未修；附[未应用的兼容建议](part3_checkpoint/PROPOSED_LEGACY_STUB_COMPATIBILITY.patch)，建议私有接口对缺省intent沿旧transit口径，生成入口的显式意图校验保持。

### 修改范围、冻结与耗时

本部分修改3共享文件：`v08/motion/intents/transit.py`、`v08/motion/transit_chords.py`、`v08/runner/joint_intent.py`；新增新意图模块`v08/motion/intents/close_observation.py`与自加文件`tests/v08/V8-19/test_extra_selected_curve_v19.py`。没有修改monitoring_turn.py、冻结函数/类、配置、criteria、sim、sampler、原始输入或旧测试。100冻结整文件、5冻结源码对象仍同；两owner原SHA仍同，不提交、不删除。首次准备文件至失败日志落盘{summary['first_prepare_to_failure_s']:.3f}秒；至本次证据打包{summary['first_prepare_to_package_s']:.3f}秒，包括诊断与独立回归，不把它冒充纯开发或生产耗时。原开发预计2小时尚未用尽，停止原因是快速检查失败。

第一轮四意图80/80是第2部分代码的证明；上述共享修改之后没有再跑旧快批，**第二轮4组仍未执行，当前失败版本不能宣称满足最终字节门禁**。两轮门禁外各合同树排除依旧[]。新意图合同保留0，三项P0触发清单[]。

原站点裁定第4节的依赖顺序已在交接源文更正，与用户答复一致；若源文SHA变化，instructions保留初版及依赖更正版，manifest同时登记，不覆盖历史依据。

### 八部分当前状态及止损项

| 部分 | 结论 | 实测/缺失 |
|---|---|---|
| 1 | 完成，e0ece96 | 登记至检查点562.622秒；原基线134通过 |
| 2 | 完成，7b16f96历史失败→6991b2c锚点修正→aec7ca6第一轮门禁 | 修正前后数值见上文；前置15/15；四组80/80、总门禁1177.780秒 |
| 3 | 快速检查失败停止；本次提交保全 | 自加4通过1失败；独立16通过；旧132通过2error；详见summary |
| 4 | 未执行 | 第二轮门禁、完整实测/序列化/runner未实现或未验证 |
| 5 | 未执行 | 最大查询、冷/热审计、两键完整几何smoke、预建和200只骨架未启动 |
| 6 | 未执行 | 新意图20快批及落盘复核未启动 |
| 7 | 未执行 | 主200/多样性100/5键串行复跑/五意图配对未启动 |
| 8 | 本次失败交付归档；完整验收未完成 | 仅推审查分支，远端回执另存run/diagnostics/part3_delivery.json |

预建墙钟为N/A（未启动），上限2700秒；200骨架派发墙钟为N/A，上限1800秒（不含预建）。骨架成功/200、人数档差、成功attempt中位数、shape失败率均未测，门槛仍为190、10个百分点、1、5%。快批成功/20、post中位数、优化耗时中位数均未测，门槛仍为16、0、60秒。全量成功率/分档差/post/Fréchet/可比较对数以及5键相同数均未测，门槛不变。不得用0、N/A或此前意图结果填成通过。[summary](part3_checkpoint/summary.json)中的缺实测值明确为null。

### 需要审查方判断的事项

1. 是否接受未应用的自加测试修正建议，把当前穿越深层的夹具改作明确负例；它不改变任何预置预期或业务阈值。正例和真实完整几何仍需后续原定检查。
2. 是否接受未应用的私有桩接口兼容建议，缺intent沿旧transit口径；不修改旧测试断言或生成意图白名单。
3. 获准恢复后，先按审定修正单独提交、重跑本检查点与相关旧测试，再完成第3部分缺失的几何/RNG、冷/热/进程审计和最大查询，最后按顺序进入第4–8部分；当前不能跳到200骨架。
'''
(DOC / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
print(json.dumps({"checkpoint": summary["status"], "selected": selected, "independent_passes": 16, "legacy_passes": 132,
                  "legacy_errors": 2, "frozen_files_equal": 100, "frozen_symbols_equal": 5,
                  "first_prepare_to_failure_s": summary["first_prepare_to_failure_s"]}, ensure_ascii=False))
