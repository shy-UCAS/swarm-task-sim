"""Immutable Q0 answers from M1 instruction 8, including approved T5 erratum."""
from copy import deepcopy
from pathlib import Path
import json
import math
import time
import unittest
import numpy as np
from v07_m1_fixtures import scene, tracks, skeleton, trajectory, polyline, combine, fast_corner
from task_v07.labels import measure
from task_v07.detectors import dwell, revisit, coverage, work_mask
from task_v07.geometry import geometry_facts
from task_v07.criteria_labels import approach_classification
from task_v07.expansion.views import _paired, make_views
from scripts.audit_v07_m1 import audit_data
from scripts.audit_v07_m1_detectors import independent_dwell, independent_revisit, independent_coverage
from scripts.cross_v07_m1 import cross_group

EVIDENCE = {}
ROLES = ("transit", "area_search", "close_observation", "monitoring", "feint", "intrusion")
# None = not tested, exactly as the guidance table.
EXPECTED = {
    "T1": (False, False, (True, None, False, False, False, False)),
    "T2": (False, False, (True, None, False, False, False, False)),
    "T3": (True, False, (False, None, True, False, False, False)),
    "T4": (True, False, (False, None, True, False, False, False)),
    "T5": (False, True, (False, None, False, True, False, False)),
    "T6": (False, True, (False, None, False, True, False, False)),
    "T7": (False, False, (True, None, False, False, False, False)),
    "T8": (False, False, (True, True, False, False, False, False)),
    "T9_10": (False, False, (True, None, False, False, False, False)),
    "T9_4": (False, False, (True, None, False, False, False, False)),
    "T9c": (False, False, (True, None, False, False, False, False)),
    "T10": (None, None, (False, None, False, False, True, False)),
    "T11": (None, None, (False, None, False, False, False, False)),
    "T12": (None, None, (False, None, False, False, False, True)),
}


class CriteriaQ0(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.public = scene(); cls.runs = tracks()
        cls.runs.update(T9_10=fast_corner(10.), T9_4=fast_corner(4.))

    def check_audit(self, sk, run, labels, frame):
        prefix = {**run, **{k: run[k][:len(frame["time_us"])] for k in ("time_us", "p", "v")}}
        if len(frame["time_us"]) < len(run["time_us"]): prefix["execution_status"] = "running"
        report = audit_data(self.public, sk, prefix, labels, frame)
        self.assertEqual(report["status"], "PASS", report["event_or_metric_witnesses"])
        return report

    def test_T1_T13_role_matrix_and_audit(self):
        for name, (has_dwell, has_revisit, answers) in EXPECTED.items():
            print("Q0 matrix:", name, flush=True)
            run = self.runs[name]; EVIDENCE[name] = {}
            for role, success in zip(ROLES, answers):
                if success is None: continue
                with self.subTest(trajectory=name, role=role):
                    sk = skeleton(role, run); labels, frame = measure(self.public, sk, run, "synchronous")
                    self.check_audit(sk, run, labels, frame)
                    a = labels["agents"]["a"]; c = a["observed"]["contribution"]
                    self.assertEqual(a["result"]["status"], "success" if success else "failure", a["result"])
                    if has_dwell is not None: self.assertEqual(c["dwell"]["detected"], has_dwell)
                    if has_revisit is not None: self.assertEqual(c["revisit"]["detected"], has_revisit)
                    EVIDENCE[name][role] = {"result": a["result"]["status"], "core_event": a["observed"]["core_event"],
                        "dwell": c["dwell"], "revisit": c["revisit"], "reversal_count": c["work_reversal_count"]}
        run = self.runs["T13"]; sk = skeleton("transit", run)
        labels, frame = measure(self.public, sk, run, "synchronous"); self.check_audit(sk, run, labels, frame)
        self.assertEqual(labels["generation_quality"]["status"], "constraint_violation")
        self.assertFalse(labels["generation_quality"]["retained"])
        EVIDENCE["T13"] = labels["generation_quality"]

    def test_event_times_and_diagnostics(self):
        for name, role in (("T1", "transit"), ("T3", "close_observation"), ("T5", "monitoring"), ("T7", "transit")):
            run = self.runs[name]; labels, _ = measure(self.public, skeleton(role, run), run, "synchronous")
            observed = labels["agents"]["a"]["observed"]; core = observed["core_event"]; con = observed["contribution"]
            if name == "T1":
                exact = (1500 - math.sqrt(890 ** 2 - 600 ** 2)) / 4
                self.assertGreaterEqual(core["t_s"], exact); self.assertLess(core["t_s"] - exact, .1 + 1e-9)
            elif name == "T3":
                lead = 1000 / 6 - core["t_s"]
                self.assertGreaterEqual(lead, 4.8); self.assertLessEqual(lead, 5.)
                self.assertAlmostEqual(core["t_confirm"] - core["t_s"], 20.)
            elif name == "T5":
                self.assertAlmostEqual(core["t_s"], math.ceil((1500 - 890) / 8 * 10) / 10)
                self.assertEqual(core["t_s"], core["t_confirm"])
                self.assertLessEqual(abs(con["revisit"]["t_confirm"] - 580.1), .1 + 1e-8)
            else: self.assertGreaterEqual(con["work_reversal_count"], 1)
        for name in ("T9_10", "T9_4"):
            run = self.runs[name]; xy = run["p"][:, 0, :2]
            corner = int(np.argmin(np.linalg.norm(xy - [500, 600], axis=1)))
            starts = np.arange(max(0, corner - 200), min(corner + 1, len(xy) - 200))
            span = np.linalg.norm(xy[starts + 200] - xy[starts], axis=1)
            speed = np.linalg.norm(run["v"][starts[0]:starts[-1] + 201, 0], axis=1)
            self.assertGreater(float(span.min()), 30.)
            EVIDENCE[name + "_corner"] = {"corner_frame": corner, "corner_time_s": corner / 10,
                "minimum_speed_m_s": float(speed.min()), "minimum_window_start_end_m": float(span.min()),
                "window_start_frame_range": [int(starts[0]), int(starts[-1])], "fastsim_wall_s": run["wall_s"], "config_sha256": run["config_sha256"]}

    def test_P1_P3_prefixes(self):
        cases = [("P1", "T3", "close_observation", 1000 / 6 + 10, "observation_dwell"),
                 ("P2", "T5", "monitoring", 112.5 + 300, "revisit"),
                 ("P3", "T1", "transit", 375., None)]
        for name, track, role, cutoff, detector in cases:
            with self.subTest(case=name):
                run = self.runs[track]; sk = skeleton(role, run)
                labels, frame = measure(self.public, sk, run, "synchronous", cutoff_s=cutoff)
                self.check_audit(sk, run, labels, frame)
                a = labels["agents"]["a"]
                self.assertEqual(a["result"]["status"], "unknown")
                if detector: self.assertFalse(a["observed"]["contribution"][detector]["detected"])
                if name == "P1": self.assertIsNone(a["observed"]["core_event"]["t_s"])
                if name == "P2": self.assertIsNotNone(a["observed"]["core_event"]["t_s"])
                EVIDENCE[name] = {"result": a["result"], "core_event": a["observed"]["core_event"]}

    def test_G1_shared_coverage(self):
        a = trajectory(polyline([(-200, 1500), (-200, 830), (200, 830), (200, 760), (-200, 760), (-200, 690), (200, 690), (200, 1500)], 8), "a")
        b = trajectory(polyline([(200, 1500), (200, 620), (-200, 620), (-200, 550), (200, 550), (200, 480), (-200, 480), (-200, 1500)], 8), "b")
        run = combine([a, b]); sk = skeleton("area_search", run)
        labels, frame = measure(self.public, sk, run, "synchronous"); self.check_audit(sk, run, labels, frame)
        group = labels["task_groups"]["g"]
        self.assertEqual(group["result"]["status"], "success")
        self.assertGreaterEqual(group["observed"]["shared_coverage"]["coverage_fraction"], .8)
        EVIDENCE["G1"] = group["observed"]["shared_coverage"]

    def test_G2_G3_groups_and_G4_G5_views_approach(self):
        main = deepcopy(self.runs["T12"]); aux = deepcopy(self.runs["T1"]); aux["agent_ids"] = ["b"]
        run = combine([main, aux]); first = skeleton("intrusion", main, "main"); second = skeleton("feint", aux, "aux")
        task = {"base_intent": "penetration", "members": run["agent_ids"], "main_group_id": "main", "group_skeletons": {"main": first, "aux": second}}
        labels, frame = measure(self.public, task, run, "synchronous"); self.check_audit(task, run, labels, frame)
        result = labels["cluster"]["result"]
        self.assertEqual(result["status"], "success"); self.assertTrue(result["primary_task_success"]); self.assertFalse(result["all_groups_complete"])
        EVIDENCE["G2"] = result
        def rows(all_groups=True, second_status="completed"):
            return [{"episode_id": "e_" + mode, "family_id": "f", "skeleton_id": "s", "intent": "penetration", "mode": mode,
                "state": "generated", "quality_valid": True, "audit_passed": True, "task_result": "success", "path": mode,
                "agent_ids": ["a", "b"], "condition_digest": "d", "scene_digest": "s", "all_groups_complete": all_groups,
                "execution_status": "completed" if mode == "synchronous" else second_status, "coordination_by_group": {"g": mode}}
                for mode in ("synchronous", "sequential")]
        for name, pair in (("G2_views", rows(False)), ("G4", rows(True, "timeout"))):
            self.assertFalse(_paired(pair)); view = make_views(pair); self.assertEqual(view["counts"]["extended"], 2); EVIDENCE[name] = view["counts"]
        self.assertTrue(_paired(rows()))
        first = skeleton("transit", main, "main"); second = skeleton("transit", aux, "aux")
        task = {"base_intent": "transit", "members": run["agent_ids"], "group_skeletons": {"main": first, "aux": second}}
        labels, frame = measure(self.public, task, run, "synchronous"); self.check_audit(task, run, labels, frame)
        self.assertEqual(labels["cluster"]["result"]["status"], "failure"); EVIDENCE["G3"] = labels["cluster"]["result"]
        expected = ["same_direction", "multi_direction", "intermediate", "unknown"]
        self.assertEqual([approach_classification(s) for s in (20, 75, 45, None)], expected); EVIDENCE["G5"] = dict(zip(("20", "75", "45", "missing"), expected))

    def test_performance_and_cross_negation(self):
        run = self.runs["T5"]; xy = run["p"][:, 0, :2]; vel = run["v"][:, 0]; t = run["time_us"]
        layers = geometry_facts(self.public["entities"][0]["geometry"], xy, layer_offsets={"protected": 100, "alert": 350, "warning": 850})["layer"]
        start = time.perf_counter()
        d = dwell(xy, t, work_mask(layers)); r = revisit(xy, vel, t, layers, work_mask(layers), np.array([0., 0.]))
        c = coverage(xy, np.linalg.norm(vel, axis=1), layers, np.zeros(len(t), bool), skeleton("area_search", run)["survey"])
        elapsed = time.perf_counter() - start
        self.assertLessEqual(elapsed, 2.); EVIDENCE["performance"] = {"frames": len(t), "three_detectors_wall_s": elapsed}
        independent = independent_coverage(xy, np.linalg.norm(vel, axis=1), layers, np.zeros(len(t), bool), skeleton("area_search", run)["survey"])
        np.testing.assert_array_equal(c["covered_mask"], independent["covered_mask"])
        results = []
        for name, role in (("T1", "transit"), ("T3", "close_observation"), ("T5", "monitoring"), ("T8", "area_search"), ("T10", "feint"), ("T12", "intrusion")):
            checks = cross_group(self.public, skeleton(role, self.runs[name]), self.runs[name]); results.extend(checks)
            self.assertFalse(any(r["status"] == "FAIL" for r in checks), checks)
        EVIDENCE["cross"] = results

    def test_G5_measured_headings_do_not_gate_success(self):
        rows = []
        for angle, classification in zip((20, 75, 45, None), ("same_direction", "multi_direction", "intermediate", "unknown")):
            first = self.runs["T1"]; second = deepcopy(first); second["agent_ids"] = ["b"]
            if angle is None:
                second = trajectory(polyline([(0, 600), (1500, 600)], 4), "b")
            else:
                radians = math.radians(angle); rotation = np.array([[math.cos(radians), -math.sin(radians)], [math.sin(radians), math.cos(radians)]])
                second["p"][:, :, :2] = second["p"][:, :, :2] @ rotation.T
                second["v"][:, :, :2] = second["v"][:, :, :2] @ rotation.T
            run = combine([first, second]); sk = skeleton("transit", run)
            # Deliberately disagree with measured categories; assignment cannot gate the result.
            sk["approach_mode"] = "multi_direction" if angle == 20 else "same_direction"
            labels, frame = measure(self.public, sk, run, "synchronous"); self.check_audit(sk, run, labels, frame)
            group = labels["task_groups"]["g"]
            self.assertEqual(group["observed"]["approach_classification"], classification)
            self.assertEqual(group["result"]["status"], "success")
            rows.append({"angle": angle, "measured_span": group["observed"]["approach_span_deg"], "classification": classification, "result": group["result"]})
            permuted = {**run, "agent_ids": run["agent_ids"][::-1], "p": run["p"][:, ::-1], "v": run["v"][:, ::-1]}
            alternate, _ = measure(self.public, sk, permuted, "synchronous")
            for key in ("agents", "task_groups", "cluster"): self.assertEqual(alternate[key], labels[key])
        EVIDENCE["G5_measured"] = rows

    def test_dwell_erratum_and_audit_rejects_mutations(self):
        run = self.runs["T9c"]; xy = run["p"][:, 0, :2]
        corner = int(np.argmin(np.linalg.norm(xy - [500, 600], axis=1)))
        window = xy[corner - 100:corner + 101]
        self.assertLessEqual(np.linalg.norm(window - window.mean(axis=0), axis=1).max(), 30.)
        self.assertGreater(np.linalg.norm(window[0] - window[-1]), 30.)
        sk = skeleton("transit", run); labels, frame = measure(self.public, sk, run, "synchronous")
        bad = deepcopy(labels); bad["agents"]["a"]["observed"]["core_event"]["t_confirm"] += 1.1
        self.assertEqual(audit_data(self.public, sk, run, bad, frame)["status"], "P0_STOP")
        bad = deepcopy(labels); bad["agents"]["a"]["result"]["conditions"]["no_dwell"] = False
        self.assertEqual(audit_data(self.public, sk, run, bad, frame)["status"], "P0_STOP")
        bad = deepcopy(labels); bad["generation_quality"]["retained"] = False
        self.assertEqual(audit_data(self.public, sk, run, bad, frame)["status"], "P0_STOP")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CriteriaQ0)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    root = Path(__file__).resolve().parents[1] / "docs/v07/evidence/m1"; root.mkdir(parents=True, exist_ok=True)
    (root / "q0_results.json").write_text(json.dumps({"passed": result.wasSuccessful(), "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors), "results": EVIDENCE}, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
