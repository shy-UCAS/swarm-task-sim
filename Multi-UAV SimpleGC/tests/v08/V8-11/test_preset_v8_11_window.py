"""V8-11 第 2 部分预置测试：窗口版判据（规划审查方编写，实现方不得修改或删除）。

运行（在 Multi-UAV SimpleGC 目录下，conda 环境 llm）:
    python -B -m unittest discover -s tests/v08/V8-11 -p "test_preset_v8_11_window.py" -v

独立预期的来源：
- v0.7 冻结代码的输出：task_v07.criteria_labels.measure_criteria（641a9b3）在同一合成轨迹上的结果，
  整段（complete）与前缀（cutoff_s）两种情形；窗口取整条轨迹时，窗口版的每一项都必须与它相同（r4 9.1）；
- 数学性质：整体平移时间轴，条件与帧号不变，时刻平移同一常数；
- 规格本身：输入不合法时抛 ValueError。
"""
import json
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from task_v07.criteria import load_criteria  # noqa: E402
from task_v07.criteria_labels import measure_criteria  # noqa: E402
from v08.criteria.window import group_window, measure_member_window, scene_geometry  # noqa: E402
import synth_v8_11 as syn  # noqa: E402

CFG = load_criteria()
SCENE = syn.scene()
GEOM = scene_geometry(SCENE)
ROLE = {"transit": "transit", "area_search": "reconnaissance", "close_observation": "reconnaissance",
        "monitoring": "monitoring", "feint": "feint", "intrusion": "intrusion"}

# 每个用例：意图、成员 [(编号, 起点, 分段, 速度)]
CASES = {
    "transit_ok": ("transit", [("u1", (-900, 350), [("line", (900, 350))], 8.0),
                               ("u2", (-900, 370), [("line", (900, 370))], 8.0)]),
    "transit_dwell": ("transit", [("u1", (-900, 350), [("line", (0, 350)), ("hold", 30), ("line", (900, 350))], 8.0)]),
    "transit_other_alert": ("transit", [("u1", (-900, 350), [("line", (900, 350)), ("line", (1500, 100)),
                                                             ("line", (1500, 900))], 8.0)]),
    "monitoring": ("monitoring", [("u1", (-1000, 0), [("line", (-425, 0)), ("arc", (0, 0), -540),
                                                      ("line", (1000, 0))], 8.0)]),
    "monitoring_short": ("monitoring", [("u1", (-1000, 0), [("line", (-425, 0)), ("arc", (0, 0), -90),
                                                            ("line", (-1000, -425))], 8.0)]),
    "close_observation": ("close_observation", [("u1", (-1000, 0), [("line", (-425, 0)), ("hold", 30), ("line", (-1000, 0))], 8.0),
                                                ("u2", (-1000, 40), [("line", (-425, 40)), ("hold", 30), ("line", (-1000, 40))], 8.0)]),
    "close_observation_short": ("close_observation", [("u1", (-1000, 0), [("line", (-425, 0)), ("hold", 10), ("line", (-1000, 0))], 8.0)]),
    "feint": ("feint", [("u1", (-1000, 0), [("line", (-230, 0)), ("line", (-1000, 0))], 8.0)]),
    "feint_twice": ("feint", [("u1", (-1000, 0), [("line", (-230, 0)), ("line", (-400, 0)), ("line", (-230, 0)),
                                                  ("line", (-1000, 0))], 8.0)]),
    "intrusion": ("intrusion", [("u1", (-1000, 10), [("line", (-130, 10)), ("hold", 2)], 8.0),
                                ("u2", (-1000, -10), [("line", (-130, -10)), ("hold", 2)], 8.0)]),
    "area_search": ("area_search", [("u1", (-1000, 380), [("line", (1000, 380))], 8.0),
                                    ("u2", (1000, 460), [("line", (-1000, 460))], 8.0)]),
    "area_search_partial": ("area_search", [("u1", (-1000, 380), [("line", (1000, 380))], 8.0)]),
}


def norm(x):
    return json.loads(json.dumps(x))


def build(name):
    kind, members = CASES[name]
    paths = syn.common_grid([syn.sample_path(s, pcs, spd) for _, s, pcs, spd in members])
    ids = [m[0] for m in members]
    t = paths[0][0]
    P = np.stack([p for _, p, _ in paths], axis=1)
    V = np.stack([v for _, _, v in paths], axis=1)
    sk = {"skeleton_id": "syn", "group_id": "g0", "role": ROLE[kind], "execution_method": kind,
          "base_intent": ROLE[kind], "target_id": "fac_a", "members": ids,
          "references": {a: {"endpoint_enu_m": [0.0, 0.0, syn.ALT]} for a in ids},
          "terminal_radius_m": 1.0, "terminal_speed_m_s": 0.15}
    srv = syn.survey() if kind == "area_search" else None
    if srv is not None:
        sk["survey"] = srv
    run = {"agent_ids": ids, "time_us": t, "p": P, "v": V, "execution_status": "completed"}
    return kind, ids, t, P, V, sk, run, srv


def windows(kind, ids, t, P, V, srv, *, settled, k=None, offset_us=0):
    k = len(t) if k is None else k
    return [measure_member_window(GEOM, a, t[:k] + offset_us, P[:k, i], V[:k, i], kind=kind, target_id="fac_a",
                                  settled=settled, max_target_layer=CFG["exclusion_max_layer"][ROLE[kind]],
                                  max_other_layer=CFG["exclusion_max_layer"]["other_facilities"], survey=srv)
            for i, a in enumerate(ids)]


class TestWindowMatchesV07(unittest.TestCase):
    """窗口取整条轨迹（或 t=0 起的前缀）时，与 v0.7 measure_criteria 逐项相同。"""

    def _compare(self, labels, ws, kind):
        group = labels["task_groups"]["g0"]
        for w in ws:
            lab = labels["agents"][w.member_id]
            with self.subTest(member=w.member_id):
                self.assertEqual(norm(lab["result"]["conditions"]), norm(w.conditions))
                self.assertEqual(lab["result"]["status"], w.status)
                ce = lab["observed"]["core_event"]
                for key in ("raw_event_type", "t_s", "frame_index", "t_confirm", "confirm_frame_index"):
                    self.assertEqual(ce[key], w.core_event[key], key)
                contrib = lab["observed"]["contribution"]
                self.assertEqual(norm(contrib["dwell"]), norm(w.dwell))
                self.assertEqual(norm(contrib["revisit"]), norm(w.revisit))
                if kind == "close_observation":
                    self.assertEqual(norm(contrib["observation_dwell"]), norm(w.observation_dwell))
                if kind == "area_search":
                    self.assertEqual(contrib["covered_group_grid_points"], int(w.coverage["covered_mask"].sum()))
                    self.assertEqual(contrib["group_grid_point_count"], w.coverage["grid_point_count"])
                    self.assertEqual(contrib["effective_observation_duration_s"],
                                     float(w.coverage["effective_mask"].sum()) / 10)
                self.assertEqual(lab["observed"]["work_end_s"], w.work_end_s)
                self.assertEqual(norm(lab["observed"]["regions_by_facility"]), norm(w.regions_by_facility))
                self.assertEqual(lab["observed"]["hard_obstacle_sample_count"], int(w.obstacle.sum()))
                self.assertEqual(lab["observed"]["outside_world_sample_count"], int(w.outside_world.sum()))
                self.assertEqual(group["observed"]["approach_headings_deg"][w.member_id], w.approach_heading_deg)
        g = group_window(ws, settled=labels["evidence"]["complete_observation"])
        self.assertEqual(norm(group["result"]["conditions"]), norm(g["conditions"]))
        self.assertEqual(group["result"]["status"], g["status"])
        if kind == "area_search":
            sc = group["observed"]["shared_coverage"]
            for key in ("grid_point_count", "covered_grid_point_count", "coverage_fraction", "required_fraction"):
                self.assertEqual(sc[key], g["shared_coverage"][key], key)

    def test_full_windows(self):
        seen = set()
        for name in CASES:
            with self.subTest(case=name):
                kind, ids, t, P, V, sk, run, srv = build(name)
                labels, _ = measure_criteria(SCENE, sk, run, "synchronous")
                ws = windows(kind, ids, t, P, V, srv, settled=True)
                self._compare(labels, ws, kind)
                seen.add((kind, labels["task_groups"]["g0"]["result"]["status"]))
        # 用例须同时覆盖六个意图，且既有成功也有失败（否则比较没有意义）
        self.assertEqual({k for k, _ in seen}, set(ROLE))
        self.assertIn(("transit", "failure"), seen)
        self.assertIn(("transit", "success"), seen)
        for kind in ROLE:
            self.assertIn((kind, "success"), seen, kind)

    def test_prefix_windows(self):
        for name, cutoff_s in (("transit_ok", 60.0), ("monitoring", 150.0), ("feint", 100.0),
                               ("close_observation", 95.0), ("area_search", 120.0), ("intrusion", 50.0)):
            with self.subTest(case=name):
                kind, ids, t, P, V, sk, run, srv = build(name)
                labels, _ = measure_criteria(SCENE, sk, run, "synchronous", cutoff_s=cutoff_s)
                k = int(np.count_nonzero(t < round(cutoff_s * 1e6)))
                ws = windows(kind, ids, t, P, V, srv, settled=False, k=k)
                self._compare(labels, ws, kind)


class TestWindowProperties(unittest.TestCase):

    def test_time_shift(self):
        """整体平移时间轴：条件、帧号不变，时刻平移同一常数（窗口不要求从 0 开始）。"""
        off = 4321 * syn.FRAME_US
        for name in ("transit_ok", "monitoring", "close_observation", "area_search"):
            with self.subTest(case=name):
                kind, ids, t, P, V, sk, run, srv = build(name)
                a = windows(kind, ids, t, P, V, srv, settled=True)
                b = windows(kind, ids, t, P, V, srv, settled=True, offset_us=off)
                for wa, wb in zip(a, b):
                    self.assertEqual(norm(wa.conditions), norm(wb.conditions))
                    self.assertEqual(wa.core_event["frame_index"], wb.core_event["frame_index"])
                    self.assertEqual(wa.dwell["union_frame_intervals"], wb.dwell["union_frame_intervals"])
                    self.assertEqual(wa.revisit["frame_index"], wb.revisit["frame_index"])
                    if wa.core_event["t_s"] is not None:
                        self.assertAlmostEqual(wb.core_event["t_s"] - wa.core_event["t_s"], off / 1e6, places=6)
                    self.assertTrue(np.array_equal(wa.levels, wb.levels))

    def test_dwell_anywhere(self):
        """v0.8 用的"全窗口驻留"：预警圈外的停留也算（v0.7 只看作业区间）。"""
        kind, ids, t, P, V, sk, run, srv = build("transit_ok")
        w = windows(kind, ids, t, P, V, srv, settled=True)[0]
        self.assertFalse(w.dwell_anywhere["detected"])
        t2, p2, v2 = syn.sample_path((-900, 350), [("hold", 25), ("line", (900, 350))], 8.0)
        w2 = measure_member_window(GEOM, "u1", t2, p2, v2, kind="transit", target_id="fac_a", settled=True,
                                   max_target_layer=1, max_other_layer=1)
        self.assertTrue(w2.dwell_anywhere["detected"])      # 圈外停 25 s
        self.assertTrue(w2.conditions["no_dwell"])          # v0.7 口径只看作业区间，仍为真

    def test_invalid_inputs(self):
        t, p, v = syn.sample_path((-900, 350), [("line", (900, 350))], 8.0)
        kw = dict(kind="transit", target_id="fac_a", settled=True, max_target_layer=1, max_other_layer=1)
        bad_t = t.copy()
        bad_t[5] += 1
        with self.assertRaises(ValueError):
            measure_member_window(GEOM, "u1", bad_t, p, v, **kw)
        with self.assertRaises(ValueError):
            measure_member_window(GEOM, "u1", t.astype(float), p, v, **kw)
        with self.assertRaises(ValueError):
            measure_member_window(GEOM, "u1", t, p[:, :2], v, **kw)
        with self.assertRaises(ValueError):
            measure_member_window(GEOM, "u1", t, p, v, **{**kw, "target_id": "nope"})
        with self.assertRaises(ValueError):
            measure_member_window(GEOM, "u1", t, p, v, **{**kw, "kind": "detour"})
        with self.assertRaises(ValueError):
            measure_member_window(GEOM, "u1", t, p, v, **{**kw, "kind": "area_search"})   # 缺 survey
        with self.assertRaises(ValueError):
            measure_member_window(GEOM, "u1", t, p, v, **kw, survey=syn.survey())       # 非侦察给了 survey


if __name__ == "__main__":
    unittest.main()
