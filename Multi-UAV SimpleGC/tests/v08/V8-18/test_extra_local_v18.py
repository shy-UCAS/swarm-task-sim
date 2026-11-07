"""V8-18 执行方自加测试（非预置）：screened 与 exact 在随机折线上逐个相同、支撑裁切端点、抽样协议空组合不耗 RNG、
名义预筛边界、实测事件复算、白名单字段。预期均由独立构造或解析给出，不以实现输出作预期。"""
import math
import unittest
from types import SimpleNamespace as NS

import numpy as np

from v08.motion import feint_turn as FT
from v08.scene.field import Clearance, build_distance_field


def circle(r, c=(0.0, 0.0)):
    return {"type": "Circle", "center_m": [float(c[0]), float(c[1])], "radius_m": float(r)}


class ScreenedEqualsExact(unittest.TestCase):
    def test_random_polylines(self):
        # 裁定 1：两种直接判定都可靠 ⇒ 与 exact 逐个相同；含贴边、穿越、栅格外点
        cons = [Clearance("in", circle(300), -1, 10.0), Clearance("out", circle(100), 1, 10.0),
                Clearance("band", circle(200), 0, 10.0)]
        field = build_distance_field(cons, (-320, -320, 320, 320), spacing_m=5.0)
        rng = np.random.default_rng(18)
        n_diff = n_pass = 0
        for _ in range(400):
            k = int(rng.integers(2, 40))
            r0 = rng.uniform(80, 330)
            a0 = rng.uniform(0, 2 * math.pi)
            steps = np.cumsum(rng.normal(0, 3.0, (k, 2)), axis=0)
            xy = np.array([r0 * math.cos(a0), r0 * math.sin(a0)]) + steps
            ex = FT.clearance_passes(cons, xy, mode="exact")
            sc = FT.clearance_passes(cons, xy, mode="screened", field=field)
            n_diff += int(ex != sc)
            n_pass += int(ex)
        self.assertEqual(n_diff, 0)
        self.assertGreater(n_pass, 0)

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            FT.clearance_passes([], np.zeros((2, 2)), mode="upper_literal")

    def test_empty_path_rejected(self):
        self.assertFalse(FT.clearance_passes([Clearance("c", circle(1), 1, 0)], np.zeros((0, 2))))


class Clip(unittest.TestCase):
    def test_clip_inserts_endpoints(self):
        xy = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]])
        got = FT._clip(xy, 0.25, 2.5)
        # 独立：端点在弦上线性插值 0.25 → (0.25, 0)，2.5 → (2.5, 0)，中间保留顶点 1、2
        np.testing.assert_allclose(got, [[0.25, 0], [1, 0], [2, 0], [2.5, 0]])
        np.testing.assert_allclose(FT._clip(xy, 1.0, 1.0), [[1.0, 0.0]])

    def test_t_interval_and_union(self):
        arr = np.array([0.0, 10.0, 20.0, 30.0])
        self.assertEqual(FT._t_interval(arr, 5.0, 15.0), (0.5, 1.5))
        self.assertIsNone(FT._t_interval(arr, 31.0, 40.0))
        self.assertEqual(FT._union([(0.0, 1.0), (0.5, 2.0), (3.0, 4.0)]), [(0.0, 2.0), (3.0, 4.0)])


class Sampling(unittest.TestCase):
    def test_empty_combos_consume_no_rng(self):
        calls = []

        class R:
            def permutation(self, n):
                calls.append(("p", n))
                return np.arange(n)

            def integers(self, lo, hi):
                calls.append(("i", lo, hi))
                return lo
        grids = {("u", 1): [], ("oblique", -1): [{"id": 1, "kind": "oblique", "side": -1}]}
        got = FT.sample_turn_grid(grids, lambda c: c, R())
        self.assertEqual(got["id"], 1)
        # 空组合不调用 RNG：只一次 permutation(1)，组选 integers(0,1)、组内 integers(0,1)
        self.assertEqual(calls, [("p", 1), ("i", 0, 1), ("i", 0, 1)])
        self.assertIsNone(FT.sample_turn_grid({}, lambda c: c, R()))


class NominalScreen(unittest.TestCase):
    def _fac(self):
        return NS(id="t", center=(0.0, 0.0), geometry=circle(20),
                  offsets={"warning": 280.0, "alert": 140.0, "protected": 80.0},
                  layers={"warning": circle(300), "alert": circle(160), "protected": circle(100)})

    def _trace(self, xs):
        x = np.asarray(xs, float)
        t = np.arange(len(x), dtype=np.int64) * 100_000
        return t, np.c_[x, np.zeros(len(x)), np.full(len(x), 100.0)], np.c_[np.gradient(x) * 10.0,
                                                                             np.zeros((len(x), 2))]

    def test_empty_window_false(self):
        from v08.motion.nominal_checks import screen_feint_member
        t, p, v = (np.zeros(0, np.int64), np.zeros((0, 3)), np.zeros((0, 3)))
        got = screen_feint_member([self._fac()], "t", t, p, v)
        for k in ("started_outside_target_warning", "single_warning_entry", "single_alert_entry",
                  "max_target_layer_two", "ended_outside_all_warning"):
            self.assertFalse(got["conditions"][k], k)

    def test_protected_entry_and_not_exited(self):
        from v08.motion.nominal_checks import screen_feint_member
        # 进入 protected（层 3）→ max_target_layer_two 失败；末帧仍在 warning 内 → ended 失败；无虚构退出
        got = screen_feint_member([self._fac()], "t", *self._trace([-400, -250, -140, -60, -140]))
        self.assertFalse(got["conditions"]["max_target_layer_two"])
        self.assertFalse(got["conditions"]["ended_outside_all_warning"])
        self.assertIsNone(got["first_exit_us"]["warning"])


class Measured(unittest.TestCase):
    def test_measured_members_frames(self):
        from v08.runner.feint_report import measured_members
        f = NS(id="t", center=(0.0, 0.0), geometry=circle(20),
               offsets={"warning": 280.0, "alert": 140.0, "protected": 80.0},
               layers={"warning": circle(300), "alert": circle(160), "protected": circle(100)})
        ctx = NS(facility_by_id={"t": f}, facilities=[f])
        xs = np.array([-500, -400, -250, -140, -250, -400, -500], float)
        tr = NS(tau_us=np.arange(len(xs), dtype=np.int64) * 100_000, p=np.c_[xs, np.zeros(len(xs)), np.zeros(len(xs))],
                segment_index=np.zeros(len(xs), np.int64))
        got = measured_members(ctx, {"m": tr}, {"m": 100_000}, "t")
        m = got["members"]["m"]
        # 释放后窗口从第 1 帧起：warning 入帧 2、出帧 5；alert 入帧 3、出帧 4（手算）
        self.assertEqual(m["entry_counts"], {"warning": 1, "alert": 1})
        self.assertEqual(m["first_entry_us"], {"warning": 200_000, "alert": 300_000})
        self.assertEqual(m["first_exit_us"], {"warning": 500_000, "alert": 400_000})
        self.assertEqual(m["min_protected_sdf_m"], 40.0)
        self.assertTrue(got["all_single"])

    def test_result_block_whitelist(self):
        from v08.runner.feint_report import formation_block, result_block
        P = {"turn": {"kind": "u", "side": 1, "radius_m": 20.0, "A_m": 5.0}, "x": 1}
        meas = {"members": {"m": {"entry_counts": {}, "first_entry_us": {}, "first_exit_us": {},
                                  "min_protected_sdf_m": 1.0, "frames": 3, "exit_counts": {}}}}
        got = result_block(P, meas)
        self.assertEqual(set(got), {"turn", "members"})
        self.assertEqual(set(got["turn"]), {"kind", "side", "radius_m"})
        self.assertEqual(set(got["members"]["m"]), {"entry_counts", "first_entry_us", "first_exit_us",
                                                    "min_protected_sdf_m"})
        fb = formation_block({"prior": "loose", "start": "abreast", "realized": "abreast", "lateral_step_m": 10.0,
                              "mapped_from_loose": True}, ())
        # loose → abreast 映射本身不算退让
        self.assertFalse(fb["retreated"])
        fb = formation_block({"realized": "echelon"}, ({"kind": "echelon_lateral_step"},))
        self.assertTrue(fb["retreated"])


if __name__ == "__main__":
    unittest.main()
