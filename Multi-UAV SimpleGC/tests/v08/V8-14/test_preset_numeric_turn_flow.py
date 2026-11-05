import unittest
from v08.motion.monitoring_turn import certify_joint_candidates, choose_joint_turn


class JointFlowPreset(unittest.TestCase):
    def test_certifies_whole_set_before_any_draw(self):
        candidates = [
            dict(kind="u", side=1, radius_m=15.75, merge_phi=0.,
                 primitives=("collapse", "core", "bad_connector", "expand"),
                 schedule={}, certificate={}, id=0),
            dict(kind="u", side=1, radius_m=17.75, merge_phi=1.,
                 primitives=("collapse", "core", "connector", "expand"),
                 schedule={}, certificate={}, id=1),
            dict(kind="oblique", side=-1, radius_m=8.4, merge_phi=2.,
                 primitives=("collapse", "core", "bad_connector", "expand"),
                 schedule={}, certificate={}, id=2),
            dict(kind="oblique", side=-1, radius_m=10.4, merge_phi=3.,
                 primitives=("collapse", "core", "connector", "expand"),
                 schedule={}, certificate={}, id=3),
        ]
        visited = []
        def certify(item):
            visited.append(item["id"])
            return "bad_connector" not in item["primitives"]
        feasible = certify_joint_candidates(candidates, certify)
        self.assertEqual(visited, [0, 1, 2, 3],
                         "四格小规模穷举；不能遇到第一次核心可行就停止查询")
        self.assertEqual([x["id"] for x in feasible], [1, 3],
                         "只有整体包含可行接回的两个格，核心本身可行不充分")
        class Rng:
            def integers(inner, low, high=None, size=None):
                self.assertEqual(len(visited), 4,
                                 "第一次随机选择必须发生在完整集合查询以后")
                return 0
        chosen = choose_joint_turn(feasible, Rng())
        self.assertIs(chosen, feasible[0],
                      "选中的就是已认证完整记录，不能抽完再造连接")
        self.assertEqual(chosen["primitives"],
                         ("collapse", "core", "connector", "expand"),
                         "独立完整整体四组成部分，接回不是后补步骤")
        self.assertIsNone(choose_joint_turn([], Rng()),
                          "空可行集合如实返回，不在选择器中重试")


if __name__ == "__main__":
    unittest.main()
