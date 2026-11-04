import unittest
from types import SimpleNamespace
import numpy as np
from v08.sim.tracking import (
    TimeReference, reference_velocity, run_tracking_segment, select_jerk_plan,
)
from v08.sim.types import MemberBoundaryState
from v08.sim.stitch import stitch


def constant_reference(member="m", release=20.0, end=20.3):
    point = np.array([5.0, 7.0])  # 合成夹具，不是生产常数
    def pva(t):
        shape = np.asarray(t).shape + (2,)
        return (np.broadcast_to(point, shape).copy(),
                np.zeros(shape), np.zeros(shape))
    return TimeReference(member, release, end, 100.0, pva)


class TrackingPreset(unittest.TestCase):
    def test_control_law(self):
        # 独立预期：U C.2 的代数式，故意使用非零 p/v/a/z 误差。
        def pva(t):
            return np.array([10., 20.]), np.array([3., 4.]), np.array([.2, .4])
        ref = TimeReference("m", 20., 30., 100., pva)
        state = SimpleNamespace(p=np.array([[9., 18., 90.]]))
        got = reference_velocity(ref, 22_000_000, state, tau=.475, k_pos=1.)
        want = np.array([[3. + .475*.2 + 1., 4. + .475*.4 + 2., 10.]])
        # 来源：上述手算；只留浮点四则运算误差。
        np.testing.assert_allclose(got, want, rtol=0.,
                                   atol=np.finfo(float).eps * np.max(want))

    def test_stationary_hold_and_stitch(self):
        ref = constant_reference()
        state = MemberBoundaryState("m", 0, 0, (5., 7., 100.), (0., 0., 0.),
                                    (0., 0., 0.))
        result = run_tracking_segment(ref, state, final=True)
        self.assertEqual(result.status, "ok", "D.1：恒定可行参考应正常完成")
        self.assertIsNone(result.end_state, "固定 guided：final 的 end_state 为 None")
        self.assertIsNone(result.executed_switch_tau_us, "final 无后续切换")
        # 来源：20.3s 移动参考结束 + 冻结2s保持；engine输出 t<step_end。
        expected_t = np.arange(0, 22_300_000, 100_000, dtype=np.int64)
        np.testing.assert_array_equal(result.tau_us, expected_t)
        # 来源：零初始误差、零v/a，冻结核心的静止不变解。
        np.testing.assert_array_equal(result.p,
                                      np.tile([5., 7., 100.], (len(expected_t), 1)))
        np.testing.assert_array_equal(result.v, np.zeros_like(result.v))
        np.testing.assert_array_equal(result.a, np.zeros_like(result.a))
        tracks = stitch([result])  # 已核对：接收结果序列，不是dict
        np.testing.assert_array_equal(tracks["m"].tau_us, expected_t)

    def test_jerk_choice_nonmonotone_and_boundary(self):
        # 来源：D.1 最大“合格扫描J”，不假定误差单调；恰好0.5也合格。
        js = [2., 4., 6., 8., 10., 14.]
        es = [.5, .49, .51, .45, .60, .80]
        rows = [dict(jerk=j, max_error_m=e, complete=True) for j, e in zip(js, es)]
        got = select_jerk_plan(rows)
        self.assertFalse(got["triggered"], "J2=.5，不触发检查点1")
        self.assertEqual(got["j_plan"], 8., "最大合格J是8，不是第一个失败之前的4")
        rows[0]["max_error_m"] = np.nextafter(.5, np.inf)
        got = select_jerk_plan(rows)
        self.assertTrue(got["triggered"], "D.1.4：J2>.5即停，不能借J8通过")
        self.assertIsNone(got["j_plan"], "检查点1失败，不发生产J")

    def test_incomplete_measurement_is_not_a_pass(self):
        got = select_jerk_plan([dict(jerk=2., max_error_m=.1, complete=False)])
        self.assertIsNone(got["j_plan"], "来源：未覆盖不是测量定值")
        self.assertEqual(got["reason"], "incomplete", "来源：0.6只报事实")


if __name__ == "__main__":
    unittest.main()
