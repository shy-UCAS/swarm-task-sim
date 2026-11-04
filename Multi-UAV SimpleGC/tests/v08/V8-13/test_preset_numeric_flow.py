import ast
import inspect
import unittest
from dataclasses import replace
from unittest.mock import Mock, call
from v08.motion.skeleton import width_then_build
from v08.motion.intents import monitoring
from v08.motion import plan
from v08.runner.joint_monitoring import run_attempts
from v08.sampler.keys import RngKey


class FlowPreset(unittest.TestCase):
    def test_downstream_failure_does_not_change_formation(self):
        candidates = ["abreast", "echelon", "column"]
        probe = Mock(return_value={"width_ok": True})
        failure = {"ok": False, "stage": "start_route"}
        build = Mock(return_value=failure)
        result = width_then_build(candidates, probe, build)
        self.assertIs(result, failure, "D.3：宽度选定后的失败须原样返回")
        self.assertEqual(probe.call_args_list, [call("abreast")],
                         "D.3：不能因下游失败再查询下一队形")
        self.assertEqual(build.call_count, 1, "D.3：本次骨架只构造一次")

    def test_only_width_can_select_next_formation(self):
        probe = Mock(side_effect=[None, {"width_ok": True}])
        build = Mock(return_value="built")
        got = width_then_build(["abreast", "echelon", "column"], probe, build)
        self.assertEqual(got, "built", "r4 6.7.1：宽度不足才按顺序退让")
        self.assertEqual(build.call_args.args[0], "echelon", "第一项宽度不可行，选择第二项")
        self.assertEqual(build.call_count, 1, "找到宽度以后只造一次")

    def test_production_source_removes_obsolete_gates(self):
        tree = ast.parse(inspect.getsource(monitoring))
        calls = {n.func.id for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        obsolete = {"_budget_ok", "_repair_budget", "_is_budget",
                    "_shift_spec", "_delta_for_mean", "continuous_minimum"}
        self.assertFalse(calls & obsolete, "J50、D.3：生产骨架不能调用旧预算/间距拒绝")
        defs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        self.assertFalse(defs & (obsolete-{"continuous_minimum"}),
                         "D.3：预算修复函数应删除，不只是藏在未用开关后")
        fn = ast.parse(inspect.getsource(monitoring.propose_and_build))
        used = {n.func.id for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertIn("width_then_build", used, "动态测试的控制函数必须用于真实生产入口")
        self.assertNotIn("duration_only", inspect.signature(monitoring.build_candidate).parameters,
                         "J50：不再有预算试造占位入口")
        bad_text = {"duration_budget", "budget_region", "nominal_budget_s"}
        for module in (monitoring, plan):
            t = ast.parse(inspect.getsource(module))
            strings = {n.value for n in ast.walk(t)
                       if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            self.assertFalse(strings & bad_text, "J50：旧时长失败代码不留在骨架控制流")
        # 此静态检查是删除证据的一部分，不替代报告中的逐处diff审查。

    def test_shared_twenty_attempts_and_one_based_reporting(self):
        base = RngKey("fixture", 0, "shape", mission=0, group="g", segment=0)
        seen = []
        def fail(k):
            seen.append(k)
            return {"ok": False, "stage": "simulation"}
        out = run_attempts(base, fail)
        self.assertFalse(out["success"], "20次普通失败不伪装成功")
        self.assertEqual(out["attempts"], 20, "U D.3：全链路共享20")
        self.assertEqual([k.attempt for k in seen], list(range(20)),
                         "r4 13.5：只递增attempt，不能嵌套20×20")
        self.assertTrue(all(replace(k, attempt=0) == base for k in seen),
                        "公共业务键不因失败改变")
        done = run_attempts(base, lambda k: {"ok": True, "stage": "verified"})
        self.assertEqual(done["attempts"], 1, "首次成功的报告次数是1")
        self.assertTrue(done["success"], "只有完整成功才保留")


if __name__ == "__main__":
    unittest.main()
