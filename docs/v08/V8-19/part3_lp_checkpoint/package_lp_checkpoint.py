"""Archive the new real-input checkpoint failure. Do not alter implementation or rerun it."""
import ast
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
CODE = REPO / "Multi-UAV SimpleGC"
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
DIAG = ROOT / "run/diagnostics"
DOC = REPO / "docs/v08/V8-19"
OUT = DOC / "part3_lp_checkpoint"
sys.path.insert(0, str(CODE))
from v08.motion.intents import close_observation as C


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


manifest = read(DOC / "manifest.json")
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
assert head == "bb7a6ce9d7a523549454ae92cb19bab4a5afa5f1"
old = read(DIAG / "part3_old_tests_r2/results.json")
independent = read(DIAG / "part3_independent_tests_r2/summary.json")
assert old["all_zero_exit"] and len(old["rows"]) == 27 and independent["all_zero_exit"]
old_count = 0
for row in old["rows"]:
    text = (DIAG / "part3_old_tests_r2" / row["log"]).read_text(encoding="utf-8")
    assert row["exit_code"] == 0 and "skipped" not in text
    old_count += int(re.search(r"Ran (\d+) tests? in", text)[1])
assert old_count == 134
selected = (DIAG / "part3_selected_curve_unit_r2.log").read_text(encoding="utf-8")
assert "Ran 6 tests" in selected and "\nOK" in selected
failure = read(DIAG / "part3_geometry_rng_r1/failure.json")
assert "plan.proposal.lp.max_residual" in failure["error"]
baseline = ROOT / "run/out/gates_2_r1/transit/contracts/o01_d0/skeleton.json"
skeleton = read(baseline)
actual = skeleton["proposal"]["lp"]["max_residual"]
assert set(actual) == {"slope", "curvature_per_m", "corridor_m"}
assert C.LP["max_residual"] is C.DATA
proof = {"error_field": "plan.proposal.lp.max_residual", "actual_type": type(actual).__name__, "actual_value": actual,
    "baseline_artifact": str(baseline), "artifact_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
    "producer": "v08/motion/transit_numeric.py:curve_lp", "consumer": "v08/motion/intents/close_observation.py:LP/project",
    "declared_new_schema": "DATA (scalar/sequence only; dictionaries rejected)",
    "diagnosis": "The new whitelist incorrectly declares an existing nested residual object as scalar. This is an implementation error, outside authorized self-added expectation/legacy-default/floating-point repairs.",
    "raw_reason": failure["error"], "implementation_changed_after_failure": False, "failed_audit_rerun": False}
frozen = {}
for path, expected in manifest["frozen_files"].items():
    frozen[path] = hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
assert all(frozen.values())
symbols = []
for row in manifest["frozen_symbols"]:
    source = Path(row["path"]).read_text(encoding="utf-8")
    node = next(n for n in ast.parse(source).body if getattr(n, "name", None) == row["qualname"])
    equal = hashlib.sha256(ast.get_source_segment(source, node).encode()).hexdigest() == row["sha256"]
    assert equal
    symbols.append({"qualname": row["qualname"], "equal": equal})
for name, row in manifest["presets"].items():
    assert hashlib.sha256((CODE / "tests/v08/V8-19" / name).read_bytes()).hexdigest() == row["sha256"]
for path, expected in manifest["preserved_owner_files"].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
enumeration = read(DIAG / "part3_query_enumeration_r1/summary.json")
summary = {"status": "stopped_at_part3_real_geometry_lp_whitelist", "source_commit": head,
    "accepted_corrections": {"selected_curve_tests": {"passed": 6, "total": 6, "unittest_wall_s": .199},
        "independent_tests": {"passed": 16, "total": 16, "wall_s": independent["wall_s"]},
        "old_tests": {"files": 27, "passed": 134, "total": 134, "wall_s": old["wall_s"], "scene_gate": "accepted replacement unchanged"}},
    "real_geometry_audit": {"complete": False, "first_key": "o01_d0", "second_key": "not_started", "wall_s": failure["wall_s"],
        "comparison_assertions_reached": False, "error": failure["error"]},
    "query_identity_enumeration": {"queries": enumeration["query_count"], "maximum": enumeration["maximum"], "wall_s": enumeration["wall_s"],
        "scope": "diagnostic re-derivation of prior transit probe identities only; not production prewarm or existence certification"},
    "cache_cold_hot_workers_audit": "not_started", "maximum_query_timing": "not_started", "second_round_gates": "not_started",
    "prewarm_wall_s": None, "prewarm_limit_s": 2700, "skeleton200_wall_s": None, "skeleton_limit_s": 1800,
    "later_stages": "parts4-7 not_started; full part8 acceptance incomplete", "retained_new_contracts": 0, "p0_triggered": [],
    "frozen_files_checked": len(frozen), "frozen_files_equal": all(frozen.values()), "frozen_symbols": symbols,
    "preset_sha_equal": True, "owner_sha_equal": True,
    "source_sha256": {str(f.relative_to(CODE)): hashlib.sha256(f.read_bytes()).hexdigest()
                      for root in (CODE / "v08", CODE / "tools/v08") for f in root.rglob("*.py")},
    "checked_utc": datetime.now(timezone.utc).isoformat()}
OUT.mkdir(exist_ok=False)
for name in ("part3_independent_tests_r2", "part3_old_tests_r2", "part3_geometry_rng_r1", "part3_query_enumeration_r1"):
    shutil.copytree(DIAG / name, OUT / name)
for name in ("part3_selected_curve_unit_r2.log", "part3_geometry_rng_r1.log", "part3_query_enumeration_r1.log"):
    shutil.copyfile(DIAG / name, OUT / name)
for name in ("audit_geometry_cache.py", "run_independent_r2.py", "run_old_tests_r2.py", "package_lp_checkpoint.py"):
    shutil.copyfile(ROOT / "part3_resume" / name, OUT / name)
dump(OUT / "lp_schema_evidence.json", proof)
dump(OUT / "summary.json", summary)
dump(DIAG / "part3_lp_checkpoint_summary.json", summary)

# Narrow child whitelist, with a regression-test suggestion; neither is applied or run.
relative = "v08/motion/intents/close_observation.py"
text = (CODE / relative).read_text(encoding="utf-8")
anchor = 'CURVE_AUDIT = {'
assert text.count(anchor) == 1
proposed = text.replace(anchor, 'LP["max_residual"] = dict.fromkeys(("slope", "curvature_per_m", "corridor_m"), DATA)\n' + anchor)
patch_text = "".join(difflib.unified_diff(text.splitlines(True), proposed.splitlines(True),
    fromfile="a/Multi-UAV SimpleGC/" + relative, tofile="b/Multi-UAV SimpleGC/" + relative))
relative = "tests/v08/V8-19/test_extra_selected_curve_v19.py"
text = (CODE / relative).read_text(encoding="utf-8")
anchor = "    def test_unknown_nested_fields_are_reported_with_location(self):"
new = '''    def test_existing_lp_residual_object_has_explicit_child_whitelist(self):
        residual = {"slope": 0., "curvature_per_m": 0., "corridor_m": 0.}
        self.assertEqual(C.project({"max_residual": residual}, C.LP, "plan.proposal.lp"),
                         {"max_residual": residual})
        with self.assertRaisesRegex(ValueError, r"plan\\.proposal\\.lp\\.max_residual\\.cache_hit"):
            C.project({"max_residual": {**residual, "cache_hit": 1}}, C.LP, "plan.proposal.lp")

'''
assert text.count(anchor) == 1
patch_text += "".join(difflib.unified_diff(text.splitlines(True), text.replace(anchor, new + anchor).splitlines(True),
    fromfile="a/Multi-UAV SimpleGC/" + relative, tofile="b/Multi-UAV SimpleGC/" + relative))
(OUT / "PROPOSED_LP_RESIDUAL_SCHEMA.patch").write_text(patch_text, encoding="utf-8", newline="\n")
manifest["execution_status_after_accepted_corrections"] = manifest.pop("execution_status")
manifest["execution_status"] = {"part": 3, "status": summary["status"], "source_commit": head,
    "evidence": "part3_lp_checkpoint/summary.json", "p0_triggered": [], "retained_close_observation_contracts": 0}
dump(DOC / "manifest.json", manifest)
report = (DOC / "REPORT.md").read_text(encoding="utf-8")
current = next(line for line in report.splitlines() if line.startswith("> **当前状态："))
report = report.replace(current, "> **当前状态：两项裁定修正已单独提交并推送bb7a6ce；重跑6/6、16/16、134/134通过。真实几何检查首键因新LP嵌套白名单实现错误停止，未自行修复重跑。第3部分未完成，第4–7部分未启动，P0未触发。**")
report = report.replace("## 3. 实际曲线驻留构造——快速检查停止（当前）", "## 3. 实际曲线驻留构造——9c9352f快速检查停止（历史）")
report = report.replace("### 八部分当前状态及止损项", "### 9c9352f检查点的八部分状态及止损项（历史）")
report = report.replace("### 需要审查方判断的事项", "### 9c9352f待审事项（已获第3部分裁定）")
report += f'''

## 第3部分恢复测试与真实几何检查——当前停止

两项修正已在9c9352f上单独提交`bb7a6ce9d7a523549454ae92cb19bab4a5afa5f1`，推送指定review分支并ls-remote核对，未重置。新增负例核对最大层3、预筛拒绝且所选Pd仍有驻留，RNG仍仅(0,46)、(200,1201)；新增y=225米正例核对整条弦不进alert且预筛通过。私有接口缺intent默认transit，入口校验和旧测试不变。

重跑日志见[part3_lp_checkpoint](part3_lp_checkpoint/)：选点自加**6/6**通过，测试体0.199秒；独立数值/完整接口/原参考自加**16/16**通过，墙钟{independent['wall_s']:.3f}秒；相关旧测试27文件**134/134**通过，墙钟{old['wall_s']:.3f}秒，SceneGate继续沿用已接受替代证据。三份预置SHA、100冻结整文件、5冻结对象、两owner原SHA全同。本轮未修改旧断言或生成入口。

### 新失败：既有LP字段被新白名单错误声明

真实同attempt几何/RNG审计以6fe2e11的transit和transit_chords原始Git源码作oracle，首键o01_d0在新意图路径抛`ValueError: unexpected non-scalar contract value at plan.proposal.lp.max_residual`。审计墙钟{failure['wall_s']:.3f}秒。第二键未开始，完整几何/RNG比较断言尚未执行，所以不记任何配对检查通过。

**原因是执行方新白名单实现错误。** 原`curve_lp`的`max_residual`是已有字典，子键固定为`slope/curvature_per_m/corridor_m`；当前新LP schema却将其当DATA标量/序列。原成功LP和原过境合同均保留该嵌套对象，主指令4.4也允许max_residual字段。只读查看既有门禁o01_d0/skeleton.json得到原始值`{json.dumps(actual, ensure_ascii=False)}`，producer源码和合同散列在[lp_schema_evidence.json](part3_lp_checkpoint/lp_schema_evidence.json)。失败先发生于成功计划投影，异常处理尝试构造普通失败时又遇到同一字段；没有合同被错误保留。

这不是自加测试预期、旧桩缺省值或≤1e-9浮点表示问题，超出第3部分裁定第2节三类自修授权。按用户“其余仍按规则停报”，**实现保持bb7a6ce原样，未修复、未重跑真实几何审计**。原日志和完整traceback只留诊断目录，不入合同。P0触发清单[]，新意图保留合同0。

附[未应用修正建议](part3_lp_checkpoint/PROPOSED_LP_RESIDUAL_SCHEMA.patch)：仅在新LP schema中为max_residual声明上述三个数值子键，proposal/witness复用同一窄白名单；另补自加结构测试及未知子键拒绝反例。该建议不改原LP、值、阈值、随机数、旧合同或预置，但属于生产适配修正，留审查裁定；当前没有验证其通过。

### 独立查询登记、剩余工作与止损实测

仅继续了无弦/LP/驻留计算的独立身份枚举：依据第一轮过境40族×5draw的实际probe记录，重新派生目标、组员和实际offsets/qid，共**178个唯一查询**，耗时{enumeration['wall_s']:.3f}秒；最大实际查询为**o17_d1、12成员、abreast、最大绝对横向偏移133.82077373324597米、地图5000米**，新qid为`6ba2810fd055145d7f378857fe3acc08`。这是诊断身份清单，不是读取旧弦作为新生产结果，也不是新意图预建、判空或最大查询成本实测。

缓存冷/热/1对2进程审计、最大查询冷/热/LP/驻留/整骨架试测未启动；新意图生产预建墙钟N/A（上限2700秒）、200骨架墙钟N/A（不含预建，上限1800秒），其余骨架成功/档差/attempt/shape、快批、全量、Fréchet、5键值全部未测，门槛不变。第二轮四意图门禁未运行，必须待第3、4部分共享修改全部完成后执行，不能用第一轮80/80覆盖当前共享代码。

当前第1–2部分完成；第3部分两项修正和指定重跑完成，但真实几何检查失败，整部分未完成；第4–7部分未启动；本次只完成第8部分的失败版本保全与推送，完整验收未完成。未启动24进程运行。

**需要审查方判断：** 是否按未应用patch修正新LP嵌套白名单并补结构测试；获准后先重跑相关快速检查与同attempt审计，再补本部分其余项目，不能跳到200骨架。
'''
(DOC / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
print(json.dumps({"status": summary["status"], "tests": [6, 16, 134], "error": failure["error"],
                  "queries": 178, "max_query": enumeration["maximum"], "frozen_equal": True}, ensure_ascii=False))
