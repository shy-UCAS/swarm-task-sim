import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from swarm_sim.analysis import analyze_run, assess_separation, digest
from swarm_sim.dataset import build_dataset, family_split
from swarm_sim.evaluation import coverage_ratio, evaluate_task, longest_dwell
from swarm_sim.recording import write_json
from swarm_sim.tasks import compile_task, segment_clearance, validate_task_binding
from swarm_sim.truth import clock_to_host, fit_clock
from swarm_sim.vehicle import Vehicle

ROOT = Path(__file__).resolve().parents[1]


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT / "tasks/point_visit_3uav.json").read_text())

    def test_all_three_task_types_compile_and_preserve_family(self):
        for name, count in (("point_visit_3uav", 1), ("patrol_3uav", 5), ("coverage_3uav", 6)):
            spec = json.loads((ROOT / f"tasks/{name}.json").read_text())
            scene = compile_task(spec)
            self.assertEqual(len(scene["phases"]), count)
            self.assertEqual(scene["family_id"], spec["family_id"])
            validate_task_binding(scene)

    def test_missing_family_and_mismatched_labels_rejected(self):
        missing = copy.deepcopy(self.spec)
        del missing["family_id"]
        with self.assertRaises(ValueError):
            compile_task(missing)
        scene = compile_task(self.spec)
        scene["phases"][0]["targets"]["uav_01"]["north_m"] += 1
        with self.assertRaisesRegex(ValueError, "differs"):
            validate_task_binding(scene)

    def test_crossing_and_arbitrary_progress_clearance(self):
        self.assertEqual(segment_clearance((-1, 0), (1, 0), (0, -1), (0, 1)), 0)
        self.assertEqual(segment_clearance((0, 0), (1, 0), (2, 0), (3, 0)), 1)
        self.spec["task"]["point"]["east_m"] = 12
        self.spec["task"]["point"]["north_m"] = 0
        with self.assertRaisesRegex(ValueError, "paths too close"):
            compile_task(self.spec)

    def test_unreachable_timeout_and_bad_coverage_rejected(self):
        self.spec["timeout_s"] = 60
        with self.assertRaisesRegex(ValueError, "lower bound"):
            compile_task(self.spec)
        spec = json.loads((ROOT / "tasks/coverage_3uav.json").read_text())
        spec["task"]["footprint_radius_m"] = 0.5
        with self.assertRaisesRegex(ValueError, "diameter"):
            compile_task(spec)

    def test_unsupported_constraint_is_not_silently_ignored(self):
        self.spec["task"]["forbidden_regions"] = ["zone1"]
        with self.assertRaisesRegex(ValueError, "unsupported"):
            compile_task(self.spec)


class ClockTests(unittest.TestCase):
    def test_known_affine_offset_and_rate_recovered(self):
        pairs = [(i / 10, 2 + 1.01 * i / 10 + (0.001 if i % 2 else -0.001)) for i in range(300)]
        model = fit_clock(pairs)
        self.assertTrue(model["available"])
        self.assertAlmostEqual(model["slope"], 1.01, places=4)
        # Even/odd deterministic jitter deliberately leaves a measurable held-out error.
        self.assertAlmostEqual(model["offset_s"], 2, delta=0.0021)
        self.assertAlmostEqual(model["receive_residual_abs_p95_s"], 0.002, places=5)
        self.assertFalse(model["transport_delay_identified"])
        self.assertIsNone(model["absolute_alignment_bound_s"])

    def test_insufficient_data_and_source_reset_are_unknown(self):
        self.assertFalse(fit_clock([(0, 1), (1, 2)])["available"])
        self.assertFalse(fit_clock([(i, i) for i in range(30)] + [(0, 31)])["available"])

    def test_variable_simulation_rate_and_no_clock_extrapolation(self):
        pairs = [(i / 10, 5 + i / 10 + 0.001 * (i / 10) ** 2) for i in range(300)]
        model = fit_clock(pairs)
        self.assertGreater(model["affine_receive_residual_abs_p95_s"], 0.05)
        self.assertLess(model["receive_residual_abs_p95_s"], 0.005)
        self.assertGreater(model["heldout_samples"], 100)
        with self.assertRaisesRegex(ValueError, "extrapolate"):
            clock_to_host(-1, model)

    def test_clock_evidence_gaps_are_not_hidden_by_interpolation(self):
        self.assertFalse(fit_clock([(i / 10, i / 10) for i in range(50)] +
                                   [(10 + i / 10, 10 + i / 10) for i in range(50)])["available"])


class SemanticTests(unittest.TestCase):
    def test_online_dwell_restarts_after_source_gap(self):
        events = []
        vehicle = Vehicle(dict(id="uav", sysid=1), Path("unused"), threading.Event(),
                          lambda *args, **kw: events.append(kw))
        origin = dict(lat=37, lon=122, alt_msl_m=12)
        consumed = []
        stamps = iter([1000, 1400, 2000, 2500, 3000])
        def receive(*args, **kwargs):
            stamp = next(stamps)
            consumed.append(stamp)
            msg = SimpleNamespace(lat=370000000, lon=1220000000, alt=20000, time_boot_ms=stamp)
            with vehicle.condition:
                vehicle.sequence += 1
                vehicle.latest["GLOBAL_POSITION_INT"] = (time.perf_counter(), msg)
            return msg
        with patch.object(vehicle, "wait_message", side_effect=receive):
            vehicle.confirm_target(dict(east_m=0, north_m=0, up_m=8), origin, 1, 1, "leg")
        self.assertEqual(consumed, [1000, 1400, 2000, 2500, 3000])
        self.assertEqual(events[0]["source_dwell_s"], 1)

    def test_dwell_does_not_bridge_invalid_samples(self):
        rows = [(0, [0, 0, 8]), (0.5, [0, 0, 8]), (1, None), (1.5, [0, 0, 8]), (2, [0, 0, 8])]
        self.assertEqual(longest_dwell(rows, [0, 0, 8], 1, 0.6)[0], 0.5)

    def test_coverage_does_not_draw_across_gaps_or_wrong_altitude(self):
        task = dict(width_m=10, height_m=2, grid_m=1, footprint_radius_m=0.6)
        vehicle = dict(east_m=0, north_m=0)
        sparse = [(0, [0, 1, 8]), (10, [10, 1, 8])]
        self.assertEqual(coverage_ratio(sparse, vehicle, task, 8, 1, 0.5)["ratio"], 0)
        dense = [(0, [0, 1, 8]), (0.1, [10, 1, 8])]
        self.assertEqual(coverage_ratio(dense, vehicle, task, 8, 1, 0.5)["ratio"], 1)
        self.assertEqual(coverage_ratio([(0, [5, 1, 0])], vehicle, task, 8, 1, 0.5)["ratio"], 0)

    def test_assignment_survives_failed_or_unknown_execution(self):
        scene = compile_task(json.loads((ROOT / "tasks/point_visit_3uav.json").read_text()))
        meta = dict(status="failed", run_epoch_monotonic_s=100)
        traces = {v["id"]: [] for v in scene["vehicles"]}
        labels = evaluate_task(scene, traces, [], meta, 100)
        self.assertEqual(labels["assigned_intent"], "point_visit")
        self.assertIsNone(labels["mission_success"])
        self.assertTrue(labels["failure_reason"])

    def test_complete_evidence_can_disprove_assignment_success(self):
        scene = compile_task(json.loads((ROOT / "tasks/point_visit_3uav.json").read_text()))
        traces = {v["id"]: [(i / 10, [v["east_m"], 0, 8]) for i in range(21)] for v in scene["vehicles"]}
        events = [dict(event=kind, agent_id=v["id"], phase="leg_000", t=t)
                  for v in scene["vehicles"] for kind, t in (("phase_start_sent", 0), ("phase_finished", 2))]
        labels = evaluate_task(scene, traces, events, dict(status="completed", run_epoch_monotonic_s=0), 0)
        self.assertIs(labels["mission_success"], False)
        self.assertEqual(labels["assigned_intent"], "point_visit")


class OfflineTests(unittest.TestCase):
    def test_missing_separation_is_unknown_and_inter_sample_collision_detected(self):
        traces = dict(a=[(0, [-1, 0, 8]), (1, [1, 0, 8])], b=[(0, [1, 0, 8]), (1, [-1, 0, 8])])
        self.assertEqual(assess_separation(traces, 1)["status"], "risk")
        traces["b"][1] = (1, None)
        self.assertEqual(assess_separation(traces, 1)["status"], "unknown")

    def test_failed_run_exports_unknown_truth_and_is_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "run"
            run.mkdir()
            scene = compile_task(json.loads((ROOT / "tasks/point_visit_3uav.json").read_text()))
            metadata = dict(run_id="example", scenario=scene, run_epoch_monotonic_s=100, elapsed_s=1, status="failed")
            write_json(run / "metadata.json", metadata)
            write_json(run / "scenario.json", scene)
            (run / "events.jsonl").write_text("")
            with patch("swarm_sim.analysis.read_truth", return_value=([], {}, dict(available=False))):
                out, quality, labels = analyze_run(run)
            self.assertEqual(quality["separation_status"], "unknown")
            self.assertFalse(quality["benchmark_eligible"])
            self.assertIsNone(labels["mission_success"])
            retry = Path(temp) / "retry"
            retry.mkdir()
            write_json(retry / "metadata.json", dict(metadata, run_id="example_retry"))
            write_json(retry / "scenario.json", scene)
            (retry / "events.jsonl").write_text("")
            with patch("swarm_sim.analysis.read_truth", return_value=([], {}, dict(available=False))):
                analyze_run(retry)
            dataset = build_dataset([run, retry], Path(temp) / "dataset")
            self.assertEqual(dataset["counts"]["failed_runs"], 2)
            self.assertEqual(dataset["episodes"][0]["family_id"], scene["family_id"])
            self.assertEqual(dataset["episodes"][0]["split"], dataset["episodes"][1]["split"])
            with self.assertRaisesRegex(ValueError, "outside"):
                build_dataset([run], out / "recursive_copy")
            (out / "labels.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                build_dataset([run], Path(temp) / "tampered")

if __name__ == "__main__":
    unittest.main()
