import unittest
from types import SimpleNamespace as NS
import numpy as np

from v08.config import load_config
from v08.motion.detour_config import load_detour_candidate
from v08.motion.detour_geometry import lane_sweep_window
from v08.motion.detour_checks import verify_detour_candidate


class RulingV21(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C = load_detour_candidate().values
        cls.G = load_config("detour").values
        cls.D = cls.C["near_band_width_m"]
        cls.T = cls.C["min_sweep_deg"]

    @staticmethod
    def circle(r):
        return {"type": "Circle", "center_m": [0.0, 0.0], "radius_m": float(r)}

    def lane(self, deg):
        # 半径 1000 + D/2 的圆弧，全程在近距离带内；0.05° 采样，首尾恰在 0 与 deg
        r = 1000.0 + self.D / 2
        phi = np.radians(np.linspace(0.0, deg, int(round(deg * 20)) + 1))
        return np.c_[r * np.cos(phi), r * np.sin(phi)]

    def test_lane_sweep_window_bounds(self):
        # 独立预期：圆弧的扫角等于其圆心角；下限 Θ+5 含等号，上限 350 不含（裁定 1）
        lo = self.T + self.G["nominal_sweep_margin_deg"]
        hi = self.G["construction_sweep_cap_deg"]
        for deg, ok in ((lo + 1.0, True), (lo - 1.0, False), (hi - 1.0, True), (hi, False), (hi + 5.0, False)):
            w = lane_sweep_window({"a": self.lane(deg)}, (0.0, 0.0), self.circle(1000), self.C, self.G)
            self.assertAlmostEqual(w["spans_deg"]["a"], deg, delta=1e-6)
            self.assertEqual(w["ok"], ok, deg)
        # 多车道：任一车道越过上限即不通过
        w = lane_sweep_window({"a": self.lane(lo + 1.0), "b": self.lane(hi + 5.0)},
                              (0.0, 0.0), self.circle(1000), self.C, self.G)
        self.assertFalse(w["ok"])

    def scene(self):
        e = [{"id": "world", "type": "world",
              "geometry": {"type": "Polygon", "vertices_m": [[-5000, -5000], [5000, -5000], [5000, 5000], [-5000, 5000]]}},
             {"id": "F", "type": "facility", "geometry": self.circle(100)}]
        for name, r in (("warning", 1000), ("alert", 600), ("protected", 300)):
            e.append({"id": "F_" + name, "type": "protection_zone", "facility_id": "F", "layer": name,
                      "geometry": self.circle(r)})
        return {"entities": e}

    def track(self, distances):
        d = np.asarray(distances, float)
        p = np.c_[1000.0 + d, np.zeros(len(d)), np.zeros(len(d))]
        return NS(member_id="u", tau_us=np.arange(len(d), dtype=np.int64) * 100000,
                  segment_index=np.zeros(len(d), dtype=np.int64), p=p, v=np.zeros_like(p), a=np.zeros_like(p))

    def test_ended_outside_near_band(self):
        # 独立预期：末帧到预警边界的距离 > D 才算离开（裁定 4）；只断言这一条件
        inside_end = verify_detour_candidate(self.scene(), {"u": self.track([self.D + 20, self.D / 2, self.D / 2])},
                                             {"u": 0}, "F")
        self.assertFalse(inside_end["member_conditions"]["u"]["ended_outside_near_band"])
        on_edge = verify_detour_candidate(self.scene(), {"u": self.track([self.D + 20, self.D / 2, self.D])},
                                          {"u": 0}, "F")
        self.assertFalse(on_edge["member_conditions"]["u"]["ended_outside_near_band"])
        outside_end = verify_detour_candidate(self.scene(), {"u": self.track([self.D + 20, self.D / 2, self.D + 20])},
                                              {"u": 0}, "F")
        self.assertTrue(outside_end["member_conditions"]["u"]["ended_outside_near_band"])


if __name__ == "__main__":
    unittest.main()
