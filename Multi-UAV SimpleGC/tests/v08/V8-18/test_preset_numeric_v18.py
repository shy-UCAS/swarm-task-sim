"""V8-18预置测试，未经运行；不依赖shapely。"""
import math
import unittest
from types import SimpleNamespace as NS
import numpy as np

from v08.motion.monitoring_turn import (
    _core, collapse_length_m, derive_deforming_members)
from v08.motion.path import sample_primitives
from v08.motion.feint_turn import (
    clearance_passes, deformation_passes, sample_turn_grid)
from v08.motion.optimize import turns_from_skeleton
from v08.motion.nominal_checks import screen_feint_member
from v08.scene.field import Clearance, build_distance_field
from v08.runner.feint_report import skeleton_checkpoint


def circle(r):
    return {"type": "Circle", "center_m": [0.0, 0.0], "radius_m": float(r)}


def facility():
    return NS(id="t", center=(0.0, 0.0), geometry=circle(20),
              offsets={"warning": 280.0, "alert": 140.0, "protected": 80.0},
              layers={"warning": circle(300), "alert": circle(160),
                      "protected": circle(100)})


def trace(xs):
    x = np.asarray(xs, float)
    t = np.arange(len(x), dtype=np.int64) * 100_000
    p = np.c_[x, np.zeros(len(x)), np.full(len(x), 100.0)]
    v = np.c_[np.gradient(x) * 10.0, np.zeros((len(x), 2))]
    return t, p, v


def deform_fixture(ax):
    # 完整MT接口字段；两个横排槽位l=0,d=±10，列队l=±10。
    A = np.array([float(ax), 0.0])
    B = A + [100.0, 0.0]
    core, D, heading = _core("u", B, 0.0, 20.0, 1)
    E = np.asarray(D) + 100.0 * np.array([math.cos(heading), math.sin(heading)])
    prims = [("line", (-450.0, 0.0), tuple(A)),
             ("line", tuple(A), tuple(B))] + list(core)
    prims += [("line", tuple(D), tuple(E)), ("line", tuple(E), (-450.0, 40.0))]
    smp = sample_primitives(prims, 0.5)
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(smp.xy, axis=0), axis=1))]
    ref = NS(xy=smp.xy, theta=smp.theta, s=s)
    marks = [int(np.argmin(np.linalg.norm(smp.xy - p, axis=1))) for p in (A, B, D, E)]
    ev = dict(zip(("s_A", "s_B", "s_D", "s_E"), (float(s[i]) for i in marks)))
    ev.update(L=100.0, l_star=10.0)
    slots = NS(order=("a", "b"), offsets={"a": (0.0, -10.0), "b": (0.0, 10.0)},
               spacing_m=20.0, prior="abreast", start="abreast", realized="abreast",
               mapped_from_loose=False, lateral_step_m=20.0)
    lanes, _, _ = derive_deforming_members(ref, slots, [ev], (0.0, float(s[-1])), spacing_m=0.5)
    return lanes, [ev]


class NumericPreset(unittest.TestCase):
    def test_collapse_strict_rounding(self):
        # 独立公式夹具：v_perp=3,D=8,Δl=5；三项最大值16，严格上取2m应18。
        args = dict(spacing_m=10, speed_max_m_s=5, command_max_m_s=4,
                    dynamic_factor=1, curvature_limit=10)
        self.assertEqual(collapse_length_m([(0, -8), (0, 8)], **args), 18.0)
        # 已是纵列：r5/MT规定无需形变。
        self.assertEqual(collapse_length_m([(-5, 0), (5, 0)], **args), 0.0)

    def test_circle_core_analytic_oracle(self):
        cons = [Clearance("inside", circle(200), -1, 10),
                Clearance("outside", circle(50), 1, 10)]
        prims, _, _ = _core("u", np.array([-120.0, 0.0]), 0.0, 20.0, 1)
        xy = sample_primitives(prims, 0.5).xy
        # 解析：r²=14800−4800sinφ−800cosφ，φ∈[0,π]。
        # min r>99、max r=sqrt(16000)<127；合法环带[60,190]有充足余量。
        self.assertTrue(clearance_passes(cons, xy, mode="exact"))
        prims, _, _ = _core("u", np.array([-120.0, 0.0]), 0.0, 80.0, 1)
        # R=80末点(-120,160)，半径恰200>190，独立反例。
        self.assertFalse(clearance_passes(cons, sample_primitives(prims, 0.5).xy, mode="exact"))
        cons[1] = Clearance("outside", circle(100), 1, 10)
        # 原R=20最小半径sqrt(14800−sqrt(4800²+800²))<110，保护余量不足。
        self.assertFalse(clearance_passes(cons, xy, mode="exact"))

    def test_full_deformation_support(self):
        boundaries = {"t": circle(400), "__crossing__t::alert": circle(300)}
        lanes, schedule = deform_fixture(-240)
        # 独立几何界：形变支持横坐标绝对值≤260、|y|≤50，半径<265<290；
        # 靠内端半径至少130>60。因此警戒/保护10m与warning带均通过。
        self.assertTrue(deformation_passes(lanes, schedule, circle(300), circle(50),
                                          boundaries, band_m=10.0))
        lanes, schedule = deform_fixture(-300)
        # A处成员(-300,±10)在alert外，不能把收拢跨带忽略。
        self.assertFalse(deformation_passes(lanes, schedule, circle(300), circle(50),
                                           boundaries, band_m=10.0))

    def test_nominal_single_and_double_entries(self):
        f = facility()
        t, p, v = trace([-400, -250, -140, -250, -400])
        good = screen_feint_member([f], "t", t, p, v)
        # 圆半径300/160/100：层序列0,1,2,1,0，短窗不足20s，不会驻留。
        self.assertTrue(good["passed"])
        self.assertEqual(good["counts"]["entries"], {"warning": 1, "alert": 1})
        # 首个内帧/首个后继外帧的手算整数微秒，不以实现输出作预期。
        self.assertEqual(good["first_entry_us"], {"warning": 100_000, "alert": 200_000})
        self.assertEqual(good["first_exit_us"], {"warning": 400_000, "alert": 300_000})
        self.assertEqual(good["min_protected_sdf_m"], 40.0)
        for xs, expected in [
            ([-400, -250, -140, -250, -140, -250, -400], {"warning": 1, "alert": 2}),
            ([-400, -250, -400, -250, -140, -250, -400], {"warning": 2, "alert": 1}),
        ]:
            with self.subTest(expected=expected):
                t, p, v = trace(xs)
                bad = screen_feint_member([f], "t", t, p, v)
                # U D.4：两层任何一次计数不为1都拒绝，不依赖冻结器只查alert。
                self.assertFalse(bad["passed"])
                self.assertEqual(bad["counts"]["entries"], expected)

    def test_turn_time_mapping(self):
        nom = NS(curve=NS(s=np.array([0., 10., 30.])),
                 t_nodes=np.array([0., 2., 6.]), release_s=20.0)
        sk = NS(witnesses={"turn_ranges": {"m": [("u", 5., 20., "turn_u_min_m"),
                                                 ("none", 0., 1., None)]}})
        got = turns_from_skeleton(sk, {"m": {"nominal": nom}}, {"turn_u_min_m": 15.0})
        # S监视公式：5m→1s、20m→4s，加release20，R取原下界15而非15.75。
        self.assertEqual(got, (("m", 21.0, 24.0, 15.0),))
        # U D.2：旧意图没有表/空表都不得产生伪约束。
        self.assertEqual(turns_from_skeleton(NS(witnesses={}), {}, {}), ())
        self.assertEqual(turns_from_skeleton(NS(witnesses={"turn_ranges": {}}), {}, {}), ())

    def test_sampling_protocol(self):
        class RNG:
            def __init__(self):
                self.calls = []
            def permutation(self, n):
                self.calls.append(("permutation", n))
                return np.arange(n - 1, -1, -1)
            def integers(self, low, high):
                self.calls.append(("integers", low, high))
                return high - 1
        def row(i, kind, side):
            return {"id": i, "kind": kind, "side": side}
        grids = {("teardrop", 1): [row(i, "teardrop", 1) for i in (0, 1, 2)],
                 ("u", -1): [row(i, "u", -1) for i in (3, 4)]}
        seen = []
        def certify(c):
            seen.append(c["id"])
            return c if c["id"] in (0, 2, 3) else None
        rng = RNG()
        got = sample_turn_grid(grids, certify, rng)
        # C14协议手工展开：第一组逆序先2通过即停；第二组4败3过；均匀组选后一组。
        self.assertEqual(seen, [2, 4, 3])
        self.assertEqual(got["id"], 3)
        self.assertEqual(rng.calls, [("permutation", 3), ("permutation", 2),
                                     ("integers", 0, 2), ("integers", 0, 1)])

    def test_negative_lower_bound_is_not_infeasibility(self):
        cons = [Clearance("c", circle(4), 1, 0)]
        field = build_distance_field(cons, (-5, -5, 10, 10), spacing_m=5)
        xy = np.array([[5.0, 0.0]])
        lower = float(field.min_lower_clearance(xy)[0])
        # 网格顶点精确距离=5−4=1；场下界=1−sqrt(50)/2<0。解析反例。
        self.assertAlmostEqual(lower, 1.0 - math.sqrt(50.0) / 2.0, places=14)
        self.assertLess(lower, 0.0)
        self.assertTrue(clearance_passes(cons, xy, mode="exact"))
        # 本断言验证U字面规则的已知误拒，不宣称该规则与exact等价；见12.1。
        self.assertFalse(clearance_passes(cons, xy, mode="upper_literal", field=field))

    def test_no_intrusion_exclusion_and_no_fallback_gate(self):
        rows = []
        for o in range(1, 41):
            for d in range(5):
                cid = f"o{o:02d}_d{d}"
                rows.append(dict(contract_id=cid, success=(cid != "o34_d3"), attempts=1,
                                 group_size=2, facility_count=1, initial_speed_m_s=5.0,
                                 shape_audit_failed_attempts=0, curved=False))
        got = skeleton_checkpoint(rows)
        # U D.5：无预登记排除；199/200=0.995，全部直线也无>50%回退门槛。
        self.assertTrue(got["complete"])
        self.assertEqual(got["metrics"]["success_rate_fraction"], "199/200")
        self.assertEqual(got["metrics"]["skeleton_attempts_total"], 200)
        self.assertEqual(got["triggered"], [])


if __name__ == "__main__":
    unittest.main()
