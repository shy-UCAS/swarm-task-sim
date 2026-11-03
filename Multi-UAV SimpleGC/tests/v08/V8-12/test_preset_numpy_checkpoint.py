"""止损边界的独立预期逐字来自上层D.4；不是新增门禁。"""
import copy
import unittest
from v08.runner.monitoring_report import checkpoint


def baseline():
    return {
        "completed": True, "contracts": 200, "successes": 160,
        "by_facilities": {
            1: {"contracts": 85, "successes": 68},
            2: {"contracts": 85, "successes": 68},
            3: {"contracts": 30, "successes": 24},
        },
        "planning_median_s": 30.0,
        "failures": [],
        "diversity": [
            {"family_id": str(i), "successful_seeds": 10,
             "median_frechet_m": 20.0, "lateral_spacing_m": 20.0}
            for i in range(10)
        ],
    }


class TestCheckpoint(unittest.TestCase):
    def test_equality_is_not_trigger(self):
        answer = checkpoint(baseline())
        self.assertIs(answer.complete, True,
                      "手工汇总完整：200合同，10族各10种子")
        self.assertEqual(tuple(answer.triggers), (),
                         "上层D.4严格不等号：80%、30s、Fréchet=间距均不触发")
        item = baseline()
        item["by_facilities"] = {
            1: {"contracts": 85, "successes": 51},
            2: {"contracts": 85, "successes": 79},
            3: {"contracts": 30, "successes": 30},
        }
        self.assertNotIn("facility_gap", checkpoint(item).triggers,
                         "手算：160/200-51/85=0.20，未超过20个百分点")

    def test_each_diagnostic_threshold(self):
        item = baseline()
        item["successes"] = 159
        item["by_facilities"][1]["successes"] = 67
        self.assertIn("success_rate", checkpoint(item).triggers,
                      "手算：159/200=79.5%<80%")
        item = baseline()
        item["by_facilities"] = {
            1: {"contracts": 85, "successes": 50},
            2: {"contracts": 85, "successes": 80},
            3: {"contracts": 30, "successes": 30},
        }
        self.assertIn("facility_gap", checkpoint(item).triggers,
                      "手算：0.8-50/85>0.20")
        item = baseline()
        item["planning_median_s"] = 31.0  # 测试反例，不是生产阈值
        self.assertIn("planning_time", checkpoint(item).triggers,
                      "上层D.4：31>30")
        item = baseline()
        item["diversity"][0]["median_frechet_m"] = 19.0
        self.assertIn("frechet", checkpoint(item).triggers,
                      "上层D.4：同条件中位数19<场景间距20")

    def test_false_proof_triggers(self):
        item = baseline()
        item["failures"] = [{"code": "proven_infeasible", "witness": None,
                             "exact_nonempty": None}]
        self.assertIn("failure_evidence", checkpoint(item).triggers,
                      "上层D.4：proven_infeasible必须附几何见证")
        item = baseline()
        item["failures"] = [{"code": "proven_infeasible",
                             "witness": {"constraint": "claimed_empty"},
                             "exact_nonempty": True}]
        self.assertIn("failure_evidence", checkpoint(item).triggers,
                      "上层D.4：精确非空时不能称proven_infeasible")

    def test_missing_measurements_are_not_pass(self):
        item = copy.deepcopy(baseline())
        item["diversity"][0]["successful_seeds"] = 9
        item["diversity"][0]["median_frechet_m"] = None
        answer = checkpoint(item)
        self.assertIs(answer.complete, False,
                      "测量协议：未取得10种子不能冒充完成；不是第六个数值止损")
        self.assertTrue(bool(answer.incomplete_reasons),
                        "规程只报事实：指出缺失项，而不是让NaN比较为False")


if __name__ == "__main__":
    unittest.main()
