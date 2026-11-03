"""V8-11 第 2 部分预置测试：回归脚本自检（规划审查方编写，实现方不得修改或删除）。

运行（在 Multi-UAV SimpleGC 目录下，conda 环境 llm）:
    python -B -m unittest discover -s tests/v08/V8-11 -p "test_preset_v8_11_regress.py" -v

做法：在临时目录（仓库与数据目录之外）按 v0.7 样本的文件格式写两条合成样本，标签由 v0.7 冻结代码
task_v07.labels.measure（多编组，经 multi_labels.measure_groups）生成；回归脚本对它们必须零差异；
把 labels.json 中任意一项改掉，脚本必须报出差异。独立预期：v0.7 冻结代码的输出。
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from task_v07.labels import measure  # noqa: E402
import synth_v8_11 as syn  # noqa: E402

spec = importlib.util.spec_from_file_location("v8_11_regress", os.path.join(ROOT, "scripts", "v08", "v8_11_regress.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

POLICY = {"other_facilities": 1}


def group(gid, role, method, members, survey=None):
    g = {"group_id": gid, "role": role, "execution_method": method, "base_intent": role, "target_id": "fac_a",
         "members": members, "references": {a: {"endpoint_enu_m": [0.0, 0.0, syn.ALT]} for a in members},
         "terminal_radius_m": 1.0, "terminal_speed_m_s": 0.15, "exclusion_policy": POLICY}
    if survey is not None:
        g["survey"] = survey
    return g


def write_episode(root, groups, paths, base_intent, main=None, status="completed"):
    ids = [a for _, a, _, _, _ in paths]
    grid = syn.common_grid([syn.sample_path(s, pcs, spd) for _, _, s, pcs, spd in paths])
    t = grid[0][0]
    P = np.stack([p for _, p, _ in grid], axis=1)
    V = np.stack([v for _, _, v in grid], axis=1)
    sk = {"skeleton_id": "syn", "members": sorted(ids), "base_intent": base_intent, "exclusion_policy": POLICY,
          "group_skeletons": {g["group_id"]: g for g in groups}}
    if main:
        sk["main_group_id"] = main
    run = {"agent_ids": ids, "time_us": t, "p": P, "v": V, "execution_status": status}
    labels, _ = measure(syn.scene(), sk, run, "synchronous")
    root.mkdir(parents=True)
    np.savez_compressed(root / "truth_10hz.npz", time_us=t, p=P, v=V, a=np.zeros_like(P), agent_ids=np.array(ids))
    for name, obj in (("labels.json", labels), ("task.json", sk), ("public_scene.json", syn.scene()),
                      ("source.json", {"execution_status": status})):
        (root / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


class TestRegressScript(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.pen = base / "pen"
        write_episode(cls.pen, [group("g_int", "intrusion", "intrusion", ["u1", "u2"]),
                                group("g_feint", "feint", "feint", ["u3"]),
                                group("g_mon", "monitoring", "monitoring", ["u4"])],
                      [("g_int", "u1", (-1000, 10), [("line", (-130, 10)), ("hold", 2)], 8.0),
                       ("g_int", "u2", (-1000, -10), [("line", (-130, -10)), ("hold", 2)], 8.0),
                       ("g_feint", "u3", (0, -1000), [("line", (0, -230)), ("line", (0, -1000))], 8.0),
                       ("g_mon", "u4", (1000, 300), [("line", (0, 425)), ("arc", (0, 0), 540), ("line", (0, -1000))], 7.0)],
                      "penetration", main="g_int")
        cls.rec = base / "rec"
        write_episode(cls.rec, [group("g_s", "reconnaissance", "area_search", ["u1", "u2"], syn.survey())],
                      [("g_s", "u1", (-1000, 380), [("line", (1000, 380))], 8.0),
                       ("g_s", "u2", (1000, 460), [("line", (-1000, 460))], 8.0)], "reconnaissance")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_zero_mismatch(self):
        for ep, kinds in ((self.pen, {"intrusion", "feint", "monitoring"}), (self.rec, {"area_search"})):
            with self.subTest(ep=ep.name):
                rec, info = R.regress_episode(ep, ep.name)
                self.assertEqual(rec.mismatches, [])
                self.assertEqual(set(info["kinds"]), kinds)
                for field in ("conditions", "status", "core_event", "dwell", "revisit", "work_end_s",
                              "regions_by_facility", "group_conditions", "minimum_separation_m"):
                    self.assertGreater(rec.counts.get(field, 0), 0, field)

    def test_detects_tampering(self):
        labels = json.loads((self.rec / "labels.json").read_text(encoding="utf-8"))
        cases = [("agents", "u1", "result", "conditions", "no_revisit"),
                 ("agents", "u2", "observed", "core_event", "t_s"),
                 ("task_groups", "g_s", "observed", "shared_coverage", "coverage_fraction"),
                 ("cluster", "observed", "minimum_separation_m")]
        for path in cases:
            with self.subTest(path=path):
                bad = json.loads(json.dumps(labels))
                node = bad
                for key in path[:-1]:
                    node = node[key]
                old = node[path[-1]]
                node[path[-1]] = (not old) if isinstance(old, bool) else old + 0.1
                d = Path(self.tmp.name) / ("bad_" + "_".join(path))
                d.mkdir()
                for f in self.rec.iterdir():
                    (d / f.name).write_bytes(f.read_bytes())
                (d / "labels.json").write_text(json.dumps(bad), encoding="utf-8")
                rec, _ = R.regress_episode(d, d.name)
                self.assertGreaterEqual(len(rec.mismatches), 1)

    def test_list(self):
        for stage, n in (("quick", 10), ("full", 200)):
            items, digest = R.load_list(stage)
            self.assertEqual(len(items), n)
            self.assertEqual(digest, R.LIST_SHA[stage])


if __name__ == "__main__":
    unittest.main()
