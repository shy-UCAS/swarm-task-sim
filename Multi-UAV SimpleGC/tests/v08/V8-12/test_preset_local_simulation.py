"""仅第5部分运行；真实run_guided_segment、stitch、V8-11，不mock动力学。"""
import unittest
import numpy as np

from synth_v8_12 import fixture_plan
from v08.contract.monitoring import to_guided
from v08.config import load_config
from v08.sim.guided import run_guided_segment
from v08.sim.stitch import stitch
from v08.criteria.segment import SegmentTask, verify_segments
from v08.criteria.validity import visible_track, check_validity


class TestRealSimulation(unittest.TestCase):
    def test_full_chain_and_repeatability(self):
        ctx, group, task, states, plan = fixture_plan("loop")
        self.assertIsNone(plan.failure, "独立宽环带夹具应形成可仿真的完整计划")
        S = load_config("sim").values
        release = {
            m: int(round((S["initial_settle_s"] + plan.members[m].release_delay_s) * 10))
               * 100_000
            for m in group.member_ids
        }
        runs = []
        for _ in range(2):  # 两次是检验同键重复性的最小实验，不是生产参数。
            results = []
            for m in sorted(group.member_ids):
                result = run_guided_segment(to_guided(plan.members[m]), states[m], final=True)
                self.assertEqual(result.status, "ok",
                                 "V8-08真实终点停止完成；不能用伪造status替代")
                results.append(result)
            tracks = stitch(results)
            verdict = verify_segments(
                ctx.scene, tracks, release,
                [SegmentTask(0, "monitoring", task.target_id)])[0]
            valid = check_validity(
                ctx.scene, [visible_track(tracks[m], release[m]) for m in sorted(tracks)])
            self.assertIs(verdict.passed, True,
                          "独立预言机：V8-11段核验，含全窗口no_dwell和禁层")
            self.assertIs(valid.passed, True,
                          "独立预言机：V8-11同时可见采样间距与限制区")
            for m in sorted(tracks):
                self.assertTrue(np.all(np.diff(tracks[m].tau_us) == 100_000),
                                "r4 8.4：无重复帧、无空洞，10Hz整数网格")
            runs.append(tracks)
        for m in sorted(runs[0]):
            for field in ("tau_us", "p", "v", "a", "segment_index"):
                a = np.asarray(getattr(runs[0][m], field))
                b = np.asarray(getattr(runs[1][m], field))
                self.assertEqual((a.dtype.str, a.shape, a.tobytes()),
                                 (b.dtype.str, b.shape, b.tobytes()),
                                 "r4 13.5和上层D.5：同环境同键确定性载荷逐位相同")


if __name__ == "__main__":
    unittest.main()
