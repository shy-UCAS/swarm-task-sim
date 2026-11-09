"""V8-19 executor tests: measured events, semantic rejection, report mapping and payload structure."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np

from v08.motion.optimize_checks import check_close_observation
from v08.runner import close_observation_report as R
from v08.runner.transit_report import phase_durations
from v08.sim.types import MemberTrack


def circle(r):
    return {"type": "Circle", "center_m": [0., 0.], "radius_m": float(r)}


def context(warning=100., alert=50., protected=20.):
    fac = NS(id="t", center=(0., 0.), geometry=circle(20), offsets={"warning": warning - 20., "alert": alert - 20., "protected": protected - 20.},
             layers={"warning": circle(warning), "alert": circle(alert), "protected": circle(protected)})
    return NS(facility_by_id={"t": fac}, facilities=[fac], world=circle(2000), obstacles=[], extra={},
              params={"world_margin_m": 35., "obstacle_margin_m": 35., "forbidden_margin_m": 10.,
                      "pre_entry_warning_clearance_m": 10., "alignment_length_m": 100.})


def track():
    f = np.arange(701)
    x = np.full(len(f), 120.)
    entering = (f >= 200) & (f <= 300)
    dwell = (f > 300) & (f <= 550)
    leaving = (f > 550) & (f <= 650)
    x[entering] = 120. - .5 * (f[entering] - 200)
    x[dwell] = 70.
    x[leaving] = 70. + .5 * (f[leaving] - 550)
    p = np.column_stack((x, np.zeros(len(f)), np.full(len(f), 100.)))
    v = np.zeros_like(p)
    v[entering, 0], v[leaving, 0] = -5., 5.
    return MemberTrack("m", f * 100_000, p, v, np.zeros_like(p), np.zeros(len(f), int), ())


class MeasuredAndPayload(unittest.TestCase):
    def test_first_false_exit_and_original_detector_frame_indices(self):
        from task_v07.detectors import dwell
        ctx, tr = context(), track()
        got = R.measured_members(ctx, {"m": tr}, {"m": 20_000_000}, "t")
        self.assertTrue(got["all_single"])
        m = got["members"]["m"]
        self.assertEqual((m["warning_entry_count"], m["warning_exit_count"]), (1, 1))
        self.assertEqual(m["first_warning_entry_us"], 24_000_000)
        self.assertEqual(m["first_warning_exit_us"], 61_100_000)
        mask = tr.tau_us >= 20_000_000
        tt, xy = tr.tau_us[mask], tr.p[mask, :2]
        observation = dwell(xy, tt, (xy[:, 0] <= 100.) & (xy[:, 0] > 50.))
        self.assertEqual(m["observation_first_start_us"], int(tt[observation["frame_index"]]))
        self.assertEqual(m["observation_first_confirm_us"], int(tt[observation["confirm_frame_index"]]))
        self.assertTrue(m["ended_outside_all_warning"])

    def test_missing_and_empty_tracks_cannot_report_all_single(self):
        self.assertFalse(R.measured_members(context(), {}, {}, "t")["all_single"])
        self.assertFalse(R.measured_members(context(), {"m": track()}, {"m": 20_000_000, "missing": 0}, "t")["all_single"])
        tr = track()
        empty = MemberTrack("m", tr.tau_us[:0], tr.p[:0], tr.v[:0], tr.a[:0], tr.segment_index[:0], ())
        self.assertFalse(R.measured_members(context(), {"m": empty}, {"m": 0}, "t")["all_single"])

    def test_second_warning_entry_is_rejected(self):
        tr = track()
        p = tr.p.copy()
        p[520:526, 0] = 120.
        tr = MemberTrack("m", tr.tau_us, p, tr.v, tr.a, tr.segment_index, ())
        measured = R.measured_members(context(), {"m": tr}, {"m": 20_000_000}, "t")
        self.assertFalse(measured["all_single"])
        self.assertEqual(measured["members"]["m"]["warning_entry_count"], 2)
        self.assertEqual(measured["members"]["m"]["first_warning_exit_us"], 52_000_000)

    def test_nonempty_never_entered_window_is_rejected(self):
        tr = track()
        p = tr.p.copy()
        p[:, 0] = 120.
        tr = MemberTrack("m", tr.tau_us, p, tr.v, tr.a, tr.segment_index, ())
        measured = R.measured_members(context(), {"m": tr}, {"m": 20_000_000}, "t")
        self.assertFalse(measured["all_single"])
        self.assertEqual(measured["members"]["m"]["warning_entry_count"], 0)

    def test_result_block_uses_reference_arrival_and_exact_allowed_children(self):
        meas = R.measured_members(context(), {"m": track()}, {"m": 20_000_000}, "t")
        plan = NS(members={"m": None}, proposal={"dwell": {"reference_station_m": 100., "set_size": 5, "index": 0, "duration_ticks": 250}},
                  witnesses={"dwell_diagnostics": {"members": {"m": {"member_station_m": 200., "point_xy": (70., 0.),
                      "warning_sdf_m": -30., "alert_sdf_m": 20., "base_min_margin_m": 10.}}}})
        result = R.result_block(plan, {"m": {"dwell_reference": NS(arrival_s=30., dwell_s=25.)}}, meas)
        self.assertEqual(set(result), {"reference_station_m", "set_size", "duration_ticks", "members"})
        self.assertEqual(set(result["members"]["m"]), set(R.RESULT_MEMBER))
        self.assertEqual(result["members"]["m"]["nominal_arrival_s"], 30.)

    def test_unknown_nested_child_and_runtime_path_are_rejected(self):
        payload = {"success": True, "attempt_log": [], "close_observation": {"members": {"m": {"unexpected": 1}}}}
        with self.assertRaisesRegex(ValueError, r"close_observation\.members\.m\.unexpected"):
            R.assert_contract_payload(payload)
        with self.assertRaisesRegex(ValueError, "forbidden contract field"):
            R.assert_contract_payload({"success": True, "attempt_log": [], "phase_durations": {"m": {"dwell_set_s": 1.}}})
        with self.assertRaisesRegex(ValueError, "filesystem string"):
            R.assert_contract_payload({"success": False, "attempt_log": [], "failure": {"reason": "../cache/a.json"}})

    def test_new_five_phase_dispatch_uses_sided_time_mapping(self):
        nom = NS(release_s=20., arrival_s=24., departure_s=44., end_s=48.,
                 time_at_s=lambda s: 20. + s if s <= 4 else 44. + s - 4.)
        plan = NS(members={"m": NS(release_delay_s=0.)}, witnesses={"member_map_transit": {"members": {"m": {"entry_member_s": 2., "exit_member_s": 6.}}}})
        res = {"plan": plan, "opt": {"maps": {"m": {"dwell_reference": nom}}}}
        got = phase_durations(res, intent="close_observation")["m"]
        self.assertEqual([got[name + "_s"] for name in R.PHASES], [2., 2., 20., 2., 2.])
        self.assertEqual(got["travel_s"], 28.)
        self.assertEqual(got["closure_residual_s"], 0.)

    def test_outer_join_keeps_failed_contract(self):
        roots = {}
        with tempfile.TemporaryDirectory() as directory:
            for name in ("monitoring", "transit", "intrusion", "feint", "close_observation"):
                folder = Path(directory) / name
                folder.mkdir()
                rows = [{"contract_id": "o34_d3", "success": name != "intrusion", "attempts": 0 if name == "intrusion" else 1,
                         "group_id": "g0", "member_ids": ["m"], "target_id": "t", "initial_speed_m_s": 6.,
                         "formation_prior": "column", "group_size": 1, "facility_count": 1}]
                (folder / "records.json").write_text(json.dumps(rows), encoding="utf-8")
                roots[name] = folder
            pairs = R.five_intent_pairs(roots)
        self.assertEqual(pairs["contracts"], 1)
        self.assertEqual(pairs["common_differences"], [])
        self.assertFalse(pairs["rows"][0]["intents"]["intrusion"]["success"])
        self.assertEqual(pairs["excluded"], [])


class SemanticCheck(unittest.TestCase):
    def test_zero_entries_is_not_silently_accepted(self):
        ctx = context(300., 160., 100.)
        class Outside:
            release_s, end_s, altitude_m = 20., 50., 100.
            def evaluate(self, t, derivative=0):
                t = np.asarray(t)
                shape = t.shape + (2,)
                return np.broadcast_to([450., 225.], shape).copy() if derivative == 0 else np.zeros(shape)
        plan = NS(witnesses={"target_id": "t"})
        from v08.motion.optimize import load_settings
        with patch("v08.motion.connect.crossing_analysis", return_value=([], [])) as crossing:
            out = check_close_observation(ctx, plan, {"m": Outside()}, load_settings())
        self.assertFalse(out["passed"])
        self.assertIn("nominal_not_entered", {f["kind"] for f in out["failures"]})
        self.assertNotIn("skip_ranges", crossing.call_args.kwargs)
        self.assertIn("observation_dwell", out["nominal_members"]["m"])

    def test_first_failed_attempt_table_is_not_first_semantic_failure(self):
        path = Path(__file__).resolve().parents[3] / "tools/v08/analyze_close_observation_v19.py"
        spec = importlib.util.spec_from_file_location("v19_analysis_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = [{"attempt_log": [{"attempt": 0, "ok": False, "stage": "skeleton", "optimize": None},
                                  {"attempt": 1, "ok": False, "stage": "optimize_close_observation", "optimize": {"semantic_failures": [{"kind": "a"}, {"kind": "a"}]}}]}]
        result = module.failure_tables(rows)
        self.assertEqual(result["all_failed_attempt_semantic_once_per_subclass"], {"a": 1})
        self.assertEqual(result["first_failed_attempt_per_contract_if_semantic"], {})


if __name__ == "__main__":
    unittest.main()
