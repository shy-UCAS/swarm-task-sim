import unittest
import numpy as np
from numpy.polynomial import Polynomial
from scipy.interpolate import BSpline, PPoly
from v08.config import load_config
from v08.sim.tracking import TimeReference
from v08.motion.optimize import (
    JointProblem, load_settings, prepare_problem, solve_joint,
)
from v08.scene.field import Clearance, build_distance_field

EPS = np.finfo(float).eps


def rest_move(member, start, finish, duration, release=20.):
    """独立合成参考：五次smoothstep；不是优化器样条实现。"""
    start, finish = np.asarray(start, float), np.asarray(finish, float)
    delta = finish - start
    def pva(t):
        raw = (np.asarray(t, float) - release) / duration
        u = np.clip(raw, 0., 1.)
        f = 10*u**3 - 15*u**4 + 6*u**5
        df = (30*u**2 - 60*u**3 + 30*u**4) / duration
        ddf = (60*u - 180*u**2 + 120*u**3) / duration**2
        active = (raw >= 0.) & (raw <= 1.)
        return (start + f[..., None]*delta,
                (df*active)[..., None]*delta,
                (ddf*active)[..., None]*delta)
    return TimeReference(member, release, release+duration, 100., pva)


def frames(ref):
    # 来源：D.2按绝对10Hz时钟；包含释放后至移动末端前的完整帧。
    a = int(np.ceil(ref.release_s*10))
    b = int(np.floor(ref.end_s*10))
    return np.arange(a, b+1, dtype=np.int64) / 10.


def min_radius_exact(tr, center):
    """独立圆距预期：每区间距离平方为六次多项式，极值在端点或导数实根。"""
    px = PPoly.from_spline((tr.knots, np.asarray(tr.controls)[:, 0], 3))
    py = PPoly.from_spline((tr.knots, np.asarray(tr.controls)[:, 1], 3))
    end = tr.end_s - tr.release_s
    best = np.inf
    for k, (a, b) in enumerate(zip(px.x[:-1], px.x[1:])):
        lo, hi = max(a, 0.), min(b, end)
        if hi <= lo:
            continue
        x, y = Polynomial(px.c[:, k][::-1]), Polynomial(py.c[:, k][::-1])
        x, y = x-center[0], y-center[1]
        d2 = x*x + y*y
        values = [lo-a, hi-a]
        for r in d2.deriv().roots():
            # 来源：float64根求解的数值筛选；并非距离门禁容差。
            if abs(r.imag) <= np.sqrt(EPS)*max(1., abs(r.real)):
                if lo-a <= r.real <= hi-a:
                    values.append(float(r.real))
        best = min(best, min(float(d2(q)) for q in values))
    return float(np.sqrt(max(best, 0.)))


def independent_dynamics(tr):
    """区间极值独立检查；不用优化器的 passed 结论。"""
    px = PPoly.from_spline((tr.knots, np.asarray(tr.controls)[:, 0], 3))
    py = PPoly.from_spline((tr.knots, np.asarray(tr.controls)[:, 1], 3))
    end = tr.end_s-tr.release_s
    worst = dict(speed=0., tangential=0., normal=0., jerk=0.)
    for k, (a, b) in enumerate(zip(px.x[:-1], px.x[1:])):
        lo, hi = max(a, 0.)-a, min(b, end)-a
        if hi <= lo:
            continue
        x, y = Polynomial(px.c[:, k][::-1]), Polynomial(py.c[:, k][::-1])
        vx, vy, ax, ay = x.deriv(), y.deriv(), x.deriv(2), y.deriv(2)
        s2 = vx*vx + vy*vy
        dot, cross = vx*ax+vy*ay, vx*ay-vy*ax
        # 极值：有理函数N/D导数的分子 N'D-ND' 为零。
        candidates = [lo, hi]
        polys = [s2.deriv(),
                 (dot*dot).deriv()*s2-(dot*dot)*s2.deriv(),
                 (cross*cross).deriv()*s2-(cross*cross)*s2.deriv()]
        for poly in polys:
            for r in poly.roots():
                if abs(r.imag) <= np.sqrt(EPS)*max(1., abs(r.real)):
                    if lo < r.real < hi:
                        candidates.append(float(r.real))
        for t in candidates:
            v = np.array([vx(t), vy(t)], float)
            acc = np.array([ax(t), ay(t)], float)
            speed = np.linalg.norm(v)
            at = abs(v@acc)/speed if speed else np.linalg.norm(acc)
            an = abs(v[0]*acc[1]-v[1]*acc[0])/speed if speed else 0.
            jerk = np.linalg.norm([x.deriv(3)(t), y.deriv(3)(t)])
            for name, value in zip(worst, [speed, at, an, jerk]):
                worst[name] = max(worst[name], float(value))
    return worst


class OptimizerPreset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = load_settings()  # 前提：第2、3部分测得，不能在测试里猜权重
        # 独立门限来源：冻结loader读取测量配置，不从待测求解器的诊断取预期。
        cls.j_limit = load_config("joint_opt").values["jerk_plan_m_s3"]

    def endpoints(self, original, tr):
        # 来源：D.2起终点p/v/a钳定；sqrt(eps)仅为独立数值比较界。
        bound = np.sqrt(EPS) * max(1., np.max(np.abs(tr.controls)))
        for t in [original.release_s, original.end_s]:
            want = original.pva(t)[0]
            np.testing.assert_allclose(tr.evaluate(t, 0), want, rtol=0., atol=bound)
            np.testing.assert_allclose(tr.evaluate(t, 1), [0., 0.], rtol=0., atol=bound)
            np.testing.assert_allclose(tr.evaluate(t, 2), [0., 0.], rtol=0., atol=bound)
        self.assertEqual(tr.release_s, original.release_s, "来源：固定时间分配")
        self.assertEqual(tr.end_s, original.end_s, "来源：非整秒T也不能舍入")

    def test_feasible_constant_reference_has_zero_discretization_error(self):
        ref = rest_move("a", (6.25, -2.5), (6.25, -2.5), 8.3)
        for h in [1., .5]:
            with self.subTest(knot_s=h):
                sol = solve_joint(JointProblem((ref,)), self.settings, knot_s=h)
                self.assertTrue(sol.ok, "解析：常值参考、零jerk是目标全局最小值")
                tr = sol.references["a"]
                got = tr.evaluate(frames(ref), 0)
                # 常值属于样条空间，离散化误差为0；此界仅覆盖浮点求值。
                bound = np.sqrt(EPS)*max(1., np.max(np.abs(ref.pva(20.)[0])))
                self.assertLessEqual(float(np.max(np.linalg.norm(
                    got-ref.pva(frames(ref))[0], axis=1))), bound,
                    "独立预期：常值再现与零平滑能量")
                self.endpoints(ref, tr)


    def test_physical_solver_has_no_legacy_duration_cap(self):
        # 合成常值轨迹只验证物理求解器，不声称满足监视无驻留语义。
        ref = rest_move("a", (6.25, -2.5), (6.25, -2.5), 2000.3)
        sol = solve_joint(JointProblem((ref,)), self.settings)
        self.assertTrue(sol.ok, "决定50：>1800s不能单因时长被物理求解器拒绝")
        self.endpoints(ref, sol.references["a"])

    def test_head_on_swap(self):
        # 夹具±30m、60.3s给绕行留出时间；3m来自D.2，不来自实现输出。
        refs = (rest_move("a", (-30., 0.), (30., 0.), 60.3),
                rest_move("b", (30., 0.), (-30., 0.), 60.3))
        for h in [1., .5]:
            with self.subTest(knot_s=h):
                sol = solve_joint(JointProblem(refs), self.settings, knot_s=h)
                self.assertTrue(sol.ok, "D.2.6互换构造要求：应成功且不能在重合处停住")
                a, b = sol.references["a"], sol.references["b"]
                t = frames(refs[0])
                d = np.linalg.norm(a.evaluate(t)-b.evaluate(t), axis=1)
                self.assertGreaterEqual(float(d.min()), 3., "U D.2：10Hz间距≥3，零放宽")
                for ref in refs:
                    self.endpoints(ref, sol.references[ref.member_id])

    def test_circle_obstacle_exact_clearance(self):
        # 圆半径10m是合成夹具；独立预期：到圆心至少10+35=45m。
        circle = {"type": "Circle", "center_m": [0., 0.], "radius_m": 10.}
        cs = (Clearance("obstacle:c", circle, 1, 35.),)
        field = build_distance_field(cs, (-200., -200., 200., 200.), spacing_m=5.)
        ref = rest_move("a", (-100., 0.), (100., 0.), 120.3)
        for h in [1., .5]:
            with self.subTest(knot_s=h):
                sol = solve_joint(JointProblem((ref,), cs, field), self.settings, knot_s=h)
                self.assertTrue(sol.ok, "D.2.6：圆障碍挡直线的构造用例应成功")
                tr = sol.references["a"]
                self.assertGreaterEqual(min_radius_exact(tr, (0., 0.))-10., 35.,
                                        "手算圆距离；连续区间极值；不减容差")
                self.endpoints(ref, tr)

    def test_excess_normal_acceleration_cannot_silently_pass(self):
        # 半径1m，下面smoothstep在u=.5时角速度18.75，a_n=351.5625>3（手算）。
        def pva(t):
            t = np.asarray(t, float)-20.
            u = np.clip(t/8., 0., 1.)
            theta = 80.*(10*u**3-15*u**4+6*u**5)
            w = 10.*(30*u**2-60*u**3+30*u**4)
            aa = (80./64.)*(60*u-180*u**2+120*u**3)
            er = np.stack([np.cos(theta), np.sin(theta)], axis=-1)
            et = np.stack([-np.sin(theta), np.cos(theta)], axis=-1)
            return er, w[..., None]*et, aa[..., None]*et-w[..., None]**2*er
        ref = TimeReference("a", 20., 28., 100., pva)
        sol = solve_joint(JointProblem((ref,)), self.settings)
        if not sol.ok:
            self.assertTrue(sol.reason.startswith("optimize_"),
                            "D.2.5：必须显式失败原因，不能返回假成功")
        else:
            tr = sol.references["a"]
            got = independent_dynamics(tr)
            # 数学独立求根的浮点比较界，按每项物理尺度乘sqrt(eps)；
            # 生产仍必须给出更细的3.5后向误差界，不能使用此测试界放行。
            caps = dict(speed=12., tangential=2., normal=3.,
                        jerk=self.j_limit)
            for name, cap in caps.items():
                self.assertLessEqual(got[name], cap*(1.+np.sqrt(EPS)),
                                     "U D.2动态硬限："+name)
            self.endpoints(ref, tr)


    def test_semantic_line_is_an_equality(self):
        # 合成直线；独立来源是D.2的法向硬钳定，不读取求解器的line_pass。
        ref = rest_move("a", (0., 0.), (20., 0.), 30.3)
        lines = (("a", ref.release_s, ref.end_s, (0., 0.), (1., 0.)),)
        sol = solve_joint(JointProblem((ref,), lines=lines), self.settings)
        self.assertTrue(sol.ok, "可行直线与端点等式相容")
        tr = sol.references["a"]
        bound = np.sqrt(EPS)*max(1., np.max(np.abs(tr.controls)))
        self.assertLessEqual(float(np.max(np.abs(tr.controls[:, 1]))), bound,
                             "独立几何：支撑控制点法向y=0则整个样条共线")
        self.endpoints(ref, tr)

    def test_gradient_matches_central_difference(self):
        # 非对称且故意不可行的夹具，仅验证数学梯度，不要求solve成功。
        cs = (Clearance("obstacle:c",
                        {"type": "Circle", "center_m": [2.37, .41], "radius_m": 1.},
                        1, 35.),)
        field = build_distance_field(cs, (-200., -200., 200., 200.), spacing_m=5.)
        refs = (rest_move("a", (0., .13), (5., .23), 8.3),
                rest_move("b", (.17, 1.13), (5.17, 1.23), 8.3))
        prepared = prepare_problem(JointProblem(refs, cs, field), self.settings)
        x = prepared.x0.copy()
        x += 10.*np.sin(np.arange(len(x))+np.sqrt(2.))  # 合成扰动，不是业务参数
        value, grad = prepared.value_grad(x)
        self.assertTrue(np.isfinite(value), "代价是定义良好的实函数")
        self.assertTrue(np.isfinite(grad).all(), "解析梯度不得含NaN/inf")
        for k in range(len(x)):
            d = EPS**(1./3.)*max(1., abs(x[k]))
            xp, xm = x.copy(), x.copy()
            xp[k] += d
            xm[k] -= d
            fd = (prepared.value_grad(xp)[0]-prepared.value_grad(xm)[0])/(2*d)
            bound = EPS**(1./3.)*(1.+abs(fd)+abs(grad[k]))
            self.assertLessEqual(abs(fd-grad[k]), bound,
                                 "中心差分数学一致性，坐标%d" % k)


if __name__ == "__main__":
    unittest.main()
