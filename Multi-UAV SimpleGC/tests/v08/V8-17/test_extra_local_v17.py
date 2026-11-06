"""V8-17 自加测试（执行方编写，不替代预置测试）。依赖真实登记输入；缺 V8_17_DATA_ROOT/V8_17_TEST_CACHE/V8_17_DEVSET
时 skip，报告须写"未执行"。"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

TIMER_KEYS = {"seconds", "wall_s", "wall_time", "elapsed_s", "elapsed_seconds", "prepare_s", "solve_s", "check_s",
              "optimization_s", "timing", "stage_timing", "skeleton_detail", "build_seconds", "attempt_wall_s",
              "skeleton_s", "optimize_s", "simulation_s", "verify_s", "lp_s", "chord_set_s", "chord_exact_s",
              "corridor_s", "route_s", "candidate_s", "cache_hits", "cache_misses_computed", "traceback", "tracebacks",
              "pid"}


def _env(name):
    v = os.environ.get(name)
    if not v:
        raise unittest.SkipTest(f"{name} 未设置；该测试未执行")
    return Path(v)


def _ctx(order):
    from v08.runner.monitoring import load_entries
    from v08.scene.context import load_context
    e = {int(x["order"]): x for x in load_entries(str(_env("V8_17_DEVSET")))}[order]
    return e, load_context(e, data_root=_env("V8_17_DATA_ROOT"), cache_dir=_env("V8_17_TEST_CACHE"))


def _keys(v, out):
    if isinstance(v, dict):
        for k, x in v.items():
            out.add(k)
            _keys(x, out)
    elif isinstance(v, list):
        for x in v:
            _keys(x, out)
    return out


class ExtraLocal(unittest.TestCase):
    def test_limit1_crossing_table_is_warnings(self):
        """上限 1 的意图：crossing_boundaries 与 warnings 同键、同序、同一几何对象（is）；监视/过境不新增边界。"""
        from v08.contract.monitoring import TaskSpec
        from v08.motion.layer_limits import constraints_for_task, crossing_layer_keys
        _, ctx = _ctx(2)
        for f in ctx.facilities:
            for intent in ("monitoring", "transit"):
                c = constraints_for_task(ctx, TaskSpec("task0", intent, f.id))
                self.assertEqual(list(c["crossing_boundaries"]), list(c["warnings"]))
                for k in c["warnings"]:
                    self.assertIs(c["crossing_boundaries"][k], c["warnings"][k])
                self.assertEqual(crossing_layer_keys(c), {})
            c = constraints_for_task(ctx, TaskSpec("task0", "intrusion", f.id))
            self.assertEqual(list(crossing_layer_keys(c).values()), ["alert", "protected"])
            self.assertIs(list(c["crossing_boundaries"].values())[-1], f.layers["protected"])

    def test_transit_cache_keys_unchanged(self):
        """过境默认分支仍用原进程内缓存键；突入用独立键（不混用）。"""
        from v08.motion import transit_chords as TC
        _, ctx = _ctx(1)
        t = ctx.facilities[0].id
        a = TC.transit_base(ctx, t)
        b = TC.transit_base(ctx, t, intent="intrusion")
        self.assertIs(ctx.extra[("transit_base", t)], a)
        self.assertIs(ctx.extra[("intrusion_base", t)], b)
        self.assertNotEqual([c.name for c in a["base"]], [c.name for c in b["base"]])

    def test_downstream_failure_single_draw(self):
        """控制流注入：build_candidate 故意失败时，一次 attempt 中格/σ/终点只抽一次、LP 至多一次、队形 probe 不在失败后
        重做；下一 attempt 只有 attempt 键递增，且同样只抽一次。"""
        from v08.contract.monitoring import Failure, SegmentPlan, initial_states
        from v08.contract.single_intent import intrusion_mission
        from v08.motion import intrusion_chords as IC
        from v08.motion import intrusion_numeric as IN
        from v08.motion.intents import intrusion as I
        from v08.motion.intents import transit as T
        from v08.motion.plan import plan_attempt
        from v08.runner.joint_monitoring import run_attempts
        from v08.sampler.common import sample_common
        from v08.sampler.keys import RngKey
        e, ctx = _ctx(1)
        m = intrusion_mission(ctx, sample_common(ctx.family, 0))
        g, task = m.groups[0], m.tasks[0]
        states = initial_states(ctx.family, g.member_ids)
        calls = {"draw": [], "lp": 0, "probe": 0, "build": []}
        real_draw, real_lp, real_load = IN.draw_feasible, I.curve_lp, IC.load_chord_set

        def draw(cells, rng):
            out = real_draw(cells, rng)
            calls["draw"].append((out["cell_index"], out["sigma"], out["x_e"], out["collect_D_m"]))
            return out

        def lp(*a, **k):
            calls["lp"] += 1
            return real_lp(*a, **k)

        def load(*a, **k):
            calls["probe"] += 1
            return real_load(*a, **k)

        def build(ctx_, group, task_, states_, key, P):
            calls["build"].append(key)
            return SegmentPlan(members={}, reference_xy=(), nominal_duration_s=float("nan"), anchors={}, repairs=(),
                               failure=Failure("candidate_rejected", "注入失败", "injected", {"stage": "injected"}, None),
                               proposal=P)

        key0 = RngKey(ctx.family.family_id, 0, "shape", mission=0, branch=None, group=g.group_id, segment=0)
        seq = I.formation_probe_sequence(ctx, g, task, key0)
        with patch.object(IN, "draw_feasible", draw), patch.object(I, "curve_lp", lp), \
                patch.object(IC, "load_chord_set", load), patch.object(T, "build_candidate", build):
            res = run_attempts(key0, lambda k: {"ok": plan_attempt(ctx, g, task, states, (), k).failure is None,
                                                "stage": "x"}, budget=2)
        self.assertFalse(res["success"])
        self.assertEqual(len(calls["draw"]), 2)                      # 每 attempt 一次
        self.assertLessEqual(calls["lp"], 2)                         # 每 attempt 至多一次
        self.assertEqual(calls["probe"], 2 * len(seq))               # 只有确定性选队形 probe，失败后不再 probe
        self.assertEqual([k.attempt for k in calls["build"]], [0, 1])
        k0, k1 = calls["build"]
        self.assertEqual((k0.family_id, k0.draw, k0.purpose, k0.group, k0.segment),
                         (k1.family_id, k1.draw, k1.purpose, k1.group, k1.segment))

    def test_save_reread_and_no_timers(self):
        """o01_d0 全链路保存后从磁盘重读：实测三层进入次数与首次进入帧与 result.json 一致；合同 JSON 无计时键。"""
        from v08.motion.optimize import load_settings
        from v08.runner.intrusion_report import measured_members
        from v08.runner.joint_intent import run_contract
        from v08.sim.types import MemberTrack
        e, ctx = _ctx(1)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            rec = run_contract(ctx, e, 0, intent="intrusion", settings=load_settings(), out_dir=out)
            d = out / "contracts" / rec["contract_id"]
            saved = json.loads((d / "result.json").read_text(encoding="utf-8"))
            for f in d.rglob("*.json"):
                self.assertFalse(_keys(json.loads(f.read_text(encoding="utf-8")), set()) & TIMER_KEYS, f.name)
            self.assertEqual(saved["intent"], "intrusion")
            if not saved["success"]:
                self.skipTest("o01_d0 未保留；重读检查未执行")
            tracks = {}
            for m in rec["member_ids"]:
                td = d / "tracks" / m
                a = {k: np.load(td / f"{k}.npy", allow_pickle=False) for k in ("tau_us", "p", "v", "a", "segment_index")}
                tracks[m] = MemberTrack(m, a["tau_us"], a["p"], a["v"], a["a"], a["segment_index"], ())
            meas = measured_members(ctx, tracks, saved["release_us"], rec["target_id"])
            self.assertTrue(meas["all_single"])
            for m, v in meas["members"].items():
                for k in ("entry_counts", "first_entry_us", "end_contour_m", "min_contour_m"):
                    self.assertEqual(v[k], saved["intrusion"]["members"][m][k], (m, k))
            self.assertTrue(saved["retained_p0_ok"])


if __name__ == "__main__":
    unittest.main()
