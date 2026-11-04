"""执行方自加测试（第 5 部分）：仿真运行器的纯逻辑。不跑真实仿真（预置的 test_preset_local_simulation 与
冒烟/正式运行负责真实链）；这里用桩替换 run_attempt / plan_segment，检查预算接续、选择规则、比较与诊断。"""
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from v08.contract.monitoring import GroupSpec, MemberPlan, SegmentPlan, SpeedProfilePrior, TaskSpec  # noqa: E402
from v08.runner import monitoring_sim as S  # noqa: E402
from v08.runner import monitoring_sim_report as SR  # noqa: E402


def _ctx():
    fam = SimpleNamespace(family_id="fam", initial_states={"a": {"position_enu_m": [0.0, 0.0, 50.0]}})
    return SimpleNamespace(params={"shape_attempts": 20}, family=fam)


def _mission():
    group = GroupSpec("g0", ("a",), SpeedProfilePrior(6.0, 0.0), "abreast")
    task = TaskSpec("t0", "monitoring", "fac")
    return SimpleNamespace(family_id="fam", draw_index=0, groups=(group,), tasks=(task,),
                           business_key={"contract_id": "fam_d0"})


def _plan(log):
    return SegmentPlan(members={}, reference_xy=(), nominal_duration_s=100.0, anchors={}, repairs=(),
                       attempt_log=tuple(log))


def _log(n_ok_at):
    return [{"attempt": i, "ok": i == n_ok_at, "stage": None if i == n_ok_at else "patrol_shape", "code": None,
             "seconds": 0.1} for i in range(n_ok_at + 1)]


def _rec(accepted, a, codes=()):
    return {"attempt": a, "accepted": accepted, "codes": list(codes), "primary_code": codes[0] if codes else None,
            "failures": [["a", "x", c] for c in codes], "sim_wall_s": 1.0, "diag_wall_s": 0.5}


class TestRetryBudget(unittest.TestCase):
    def test_failed_sim_continues_from_next_attempt_with_prior_log(self):
        seen = {}

        def fake_plan_segment(ctx, group, task, states, occupied, key0, *, attempt_start, prior_log):
            seen["start"], seen["prior"] = attempt_start, list(prior_log)
            return _plan(list(prior_log) + [{"attempt": attempt_start + 2, "ok": True, "stage": None}])

        recs = iter([(_rec(False, 2, ["separation_violation"]), None), (_rec(True, 5), None)])
        with mock.patch.object(S, "run_attempt", side_effect=lambda *a, **k: next(recs)), \
                mock.patch.object(S, "plan_segment", side_effect=fake_plan_segment):
            run = S.try_segment(_ctx(), _mission(), _plan(_log(2)), attempt_start=2, quick=True, out_dir=None)
        self.assertEqual(run.status, "retained")
        self.assertEqual(seen["start"], 3, "仿真失败后从 a+1 接着用同一份 20 次预算")
        self.assertEqual(len(seen["prior"]), 4, "此前三次规划记录 + 第 2 次的仿真失败记录")
        self.assertEqual(seen["prior"][-1]["stage"], "simulation")
        self.assertEqual(seen["prior"][-1]["code"], "separation_violation")
        self.assertEqual([a["attempt"] for a in run.attempts], [2, 5], "失败版本留在 attempts 里，不被重试盖掉")
        self.assertEqual(run.final_attempt, 5)

    def test_budget_exhausted_keeps_every_underlying_code(self):
        recs = iter([(_rec(False, 19, ["sim_timeout"]), None)])
        with mock.patch.object(S, "run_attempt", side_effect=lambda *a, **k: next(recs)), \
                mock.patch.object(S, "plan_segment", side_effect=AssertionError("预算用完后不应再规划")):
            run = S.try_segment(_ctx(), _mission(), _plan(_log(19)), attempt_start=19, quick=False, out_dir=None)
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.failure.code, "budget_exhausted")
        under = run.failure.witness["underlying_codes"]
        self.assertEqual(under[-1], {"attempt": 19, "stage": "simulation", "code": "sim_timeout"})
        self.assertEqual(len(under), 20, "19 次规划失败 + 1 次仿真失败，原因链不被覆盖")

    def test_wall_budget_between_attempts_interrupts_without_calling_it_failure(self):
        clock = S.WallClock(1.0, used_s=5.0)
        recs = iter([(_rec(False, 0, ["semantic_ambiguous"]), None)])
        with mock.patch.object(S, "run_attempt", side_effect=lambda *a, **k: next(recs)):
            run = S.try_segment(_ctx(), _mission(), _plan(_log(0)), attempt_start=0, quick=False, out_dir=None,
                                clock=clock)
        self.assertEqual(run.status, "interrupted")
        self.assertIsNone(run.failure)

    def test_plan_segment_attempt_start_uses_remaining_budget_only(self):
        from v08.motion import plan as P
        from v08.sampler.keys import RngKey

        calls = []

        def fake_attempt(ctx, group, task, states, occupied, key):
            calls.append(key.attempt)
            return SegmentPlan(members={}, reference_xy=(), nominal_duration_s=0.0, anchors={}, repairs=(),
                               failure=SimpleNamespace(code="candidate_rejected", witness={"stage": "patrol_shape"},
                                                       feasible_set="x", reason="r"), proposal=None)

        ctx = SimpleNamespace(params={"shape_attempts": 20})
        key0 = RngKey("fam", 0, "shape", mission=0, group="g0", segment=0)
        prior = [{"attempt": i, "ok": False, "stage": "simulation"} for i in range(17)]
        with mock.patch.object(P, "plan_attempt", side_effect=fake_attempt):
            plan = P.plan_segment(ctx, SimpleNamespace(member_ids=("a",)), None, None, (), key0, attempt_start=17,
                                  prior_log=prior)
        self.assertEqual(calls, [17, 18, 19])
        self.assertEqual(plan.failure.code, "budget_exhausted")
        self.assertEqual(len(plan.attempt_log), 20)


class TestSelection(unittest.TestCase):
    def _rows(self):
        rows = []
        for order in range(1, 9):
            for d in range(2):
                rows.append({"contract_id": f"o{order:02d}_d{d}", "order": order, "draw_index": d,
                             "facility_count": 1 + (order % 3), "vehicle_count": 4 + order, "group_size": 1 + (order * 3 + d) % 5})
        return rows

    def test_quick_selection_covers_facilities_and_maxima_and_is_deterministic(self):
        rows = self._rows()
        ids, info = S.select_quick(rows, 10)
        self.assertEqual(len(ids), 10)
        self.assertEqual(len(set(ids)), 10)
        by = {r["contract_id"]: r for r in rows}
        self.assertEqual({by[i]["facility_count"] for i in ids}, {1, 2, 3})
        self.assertEqual(max(by[i]["vehicle_count"] for i in ids), info["max_vehicle_count"])
        self.assertEqual(max(by[i]["group_size"] for i in ids), info["max_group_size"])
        self.assertEqual(ids, S.select_quick(list(reversed(rows)), 10)[0], "与输入顺序无关")

    def test_full_queue_excludes_quick_and_round_robins_over_draws(self):
        rows = self._rows()
        q = S.full_queue(rows, ["o01_d0"])
        self.assertNotIn("o01_d0", q)
        draws = [next(r["draw_index"] for r in rows if r["contract_id"] == c) for c in q]
        self.assertEqual(draws, sorted(draws), "先 draw 0 的各族，再 draw 1")


class TestCompare(unittest.TestCase):
    def test_strip_timing_and_component_compare(self):
        a = {"x": 1, "wall_s": 3.0, "n": [{"seconds": 1, "k": 2}]}
        b = {"x": 1, "wall_s": 9.0, "n": [{"seconds": 7, "k": 2}]}
        self.assertEqual(S.strip_timing(a), S.strip_timing(b))
        self.assertEqual(S.compare_components({"p": 1, "t": {"a": 1}}, {"p": 1, "t": {"a": 2}}), ["t"])
        self.assertEqual(S.compare_components({"p": 1}, {"p": 1}), [])

    def test_track_digest_changes_with_one_bit(self):
        t1 = SimpleNamespace(tau_us=np.arange(3, dtype=np.int64), p=np.zeros((3, 3)), v=np.zeros((3, 3)),
                             a=np.zeros((3, 3)), segment_index=np.zeros(3, np.int64))
        t2 = SimpleNamespace(tau_us=t1.tau_us.copy(), p=t1.p.copy(), v=t1.v.copy(), a=t1.a.copy(),
                             segment_index=t1.segment_index.copy())
        self.assertEqual(S.tracks_digest({"a": t1}), S.tracks_digest({"a": t2}))
        t2.p[2, 1] = np.nextafter(0.0, 1.0)
        self.assertNotEqual(S.tracks_digest({"a": t1}), S.tracks_digest({"a": t2}))


class TestDiagnostics(unittest.TestCase):
    G = {"max_chord_m": 1.0, "max_turn_per_chord_rad": 0.2, "projection_window_m": 5.0}

    def _line_plan(self, speed_breaks):
        xy = tuple((float(x), 0.0) for x in np.arange(0.0, 101.0, 1.0))
        return MemberPlan("a", 0, xy, 50.0, 100.0, 0.0, speed_breaks)

    def test_tracking_tube_counts_frames_beyond_tube_with_local_projection(self):
        mp = self._line_plan(((0.0, 5.0),))
        n = 200
        x = np.linspace(0.0, 100.0, n)
        y = np.zeros(n)
        y[50:60] = 0.7
        track = SimpleNamespace(tau_us=np.arange(n, dtype=np.int64) * 100_000, p=np.stack([x, y, np.full(n, 50.0)], 1))
        diag, lo, sarr, level, _ = S.tracking_diagnostic(mp, track, 0, self.G, 0.5)
        self.assertEqual(lo, 0)
        self.assertEqual(diag["over_frames"], 10)
        self.assertAlmostEqual(diag["max_m"], 0.7, places=9)
        self.assertEqual(diag["first_over"]["frame"], 50)
        self.assertTrue(np.all(np.diff(sarr) >= 0.0), "进度只向前（局部窗口顺序投影）")
        self.assertEqual(set(level), {5.0})

    def test_release_frames_are_excluded(self):
        mp = self._line_plan(((0.0, 5.0),))
        n = 20
        track = SimpleNamespace(tau_us=np.arange(n, dtype=np.int64) * 100_000,
                                p=np.stack([np.linspace(0, 10, n), np.full(n, 3.0), np.full(n, 50.0)], 1))
        diag, lo, *_ = S.tracking_diagnostic(mp, track, 500_000, self.G, 0.5)
        self.assertEqual(lo, 5)
        self.assertEqual(diag["frames"], n - 5)

    def test_speed_overshoot_is_positive_part_over_adjacent_levels(self):
        mp = self._line_plan(((0.0, 4.0), (50.0, 8.0)))
        n = 100
        s = np.linspace(0.0, 100.0, n)
        v = np.zeros((n, 3))
        v[:, 0] = np.where(s < 50.0, 4.0, 8.0)
        v[60, 0] = 8.5
        track = SimpleNamespace(v=v)
        d = S.speed_diagnostic(mp, track, 0, s)
        self.assertEqual(d["stations"], 1)
        self.assertAlmostEqual(d["max_positive_over_m_s"], 0.5, places=12)
        self.assertEqual(d["worst"]["expected_max_m_s"], 8.0)
        self.assertGreaterEqual(d["adjacent_frame"]["max_abs_speed_diff_m_s"], 0.5)

    def test_boundary_counts_every_transition_and_excess_over_plan(self):
        lv = np.zeros((10, 2), np.int8)
        lv[2:4, 0] = 1
        lv[6:7, 0] = 1
        lv[3:5, 1] = 1
        b = S.boundary_diagnostic(lv, 2)
        self.assertEqual(b["warning_transitions"], 6)
        self.assertEqual(b["warning_entries"], 3)
        self.assertEqual(b["excess"], 4)
        self.assertEqual(b["alert_transitions"], 0)


class TestSummary(unittest.TestCase):
    def _result(self, cid, status, rerun, accepted_list):
        atts = []
        for i, ok in enumerate(accepted_list):
            a = {"attempt": i, "accepted": ok, "codes": [] if ok else ["separation_violation"],
                 "primary_code": None if ok else "separation_violation",
                 "failures": [] if ok else [["a|b", "min_separation", "separation_violation"]]}
            if ok:
                a.update(validity={"min_separation_m": 3.0, "interp_min_separation_m": 2.9, "restricted_frames": {"a": 0},
                                   "outside_world_frames": {"a": 0}},
                         nontarget={"a": {"max_level_nontarget": 1, "frames_ge2_nontarget": 0, "max_level_target": 1}},
                         members={"a": {"tracking": {"max_m": 0.1, "p95_m": 0.01, "over_frames": 0, "first_over": None,
                                                     "max_at": None, "over_by_expected_speed": {"5.0": {"frames": 10, "over_frames": 0, "max_m": 0.1}}},
                                        "speed": {"max_positive_over_m_s": 0.0, "speed_max_m_s": 5.0, "worst": None,
                                                  "adjacent_frame": {"max_abs_speed_diff_m_s": 0.1, "max_velocity_vector_diff_m_s": 0.1,
                                                                     "max_abs_speed_diff_in_station_windows_m_s": 0.0,
                                                                     "max_velocity_vector_diff_in_station_windows_m_s": 0.0}},
                                        "boundary": {"excess": 0, "alert_transitions": 0}}}, dwell=[])
            atts.append(a)
        return {"contract_id": cid, "status": status, "facility_count": 1, "group_size": 1, "n_restricted_zones": 0,
                "topology": "loop", "formation_realized": "abreast", "initial_speed_m_s": 5.0, "plan_nominal_duration_s": 100.0,
                "attempts": atts, "final_attempt": (len(atts) - 1) if status == "retained" else None,
                "failure": None, "rerun": {"status": rerun, "wall_s": 1.0},
                "timing": {"first_run_wall_s": 1.0, "sim_wall_s": 1.0, "replan_wall_s": 0.0, "total_wall_s": 2.0}}

    def test_counts_distinguish_verified_pending_failed_and_not_run(self):
        res = [self._result("c1", "retained", "equal", [True]), self._result("c2", "retained", "pending", [False, True]),
               self._result("c3", "failed", "not_applicable", [False])]
        s = SR.build_sim_summary(stage="full", queue=["c1", "c2", "c3", "c4"], results=res, not_run=["c4"], p0=None,
                                 quick_results=[], selection=None, successes=[{}] * 4, wall_s=10.0, budget_s=7200.0,
                                 subset=False)
        c = s["counts"]
        self.assertEqual((c["retained"], c["failed"], c["not_run"], c["rerun_equal"], c["pending_rerun"]), (2, 1, 1, 1, 1))
        self.assertEqual(c["verified_retained"], 1, "只有复跑一致的才算已验证保留")
        self.assertTrue(s["incomplete"])
        self.assertEqual(s["attempt_failure"]["failed_attempts"], 2)
        self.assertEqual(s["attempt_failure"]["contracts_with_failed_attempt"]["numerator"], 2)
        self.assertEqual(s["first_errors"][0]["contract_id"], "c2")


if __name__ == "__main__":
    unittest.main()
