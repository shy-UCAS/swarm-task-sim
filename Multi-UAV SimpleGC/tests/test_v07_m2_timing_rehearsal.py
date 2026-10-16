"""M2 guidance Q-A, with real short simulations only for A5--A7."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import random
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import types
import unittest
from unittest.mock import patch
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from v07_m1_fixtures import scene, tracks, skeleton
from scene_v07.contract import canonical_json
from task_v07.execution import execute, completion_budget
from task_v07.io import read_json, write_csv
from task_v07.labels import measure
from task_v07.expansion.contracts import condition_digest, validate_pair
from task_v07.expansion.solo_spacing import solo_interval_check, prediction_error, shifted_positions
from task_v07.unified.config import load_generator, stop_fields
from task_v07.unified.rehearsal import evaluate_solos, joint_budget
from task_v07.unified.timing import group_plan, episode_plan, select_timing
from scripts.audit_v07_m1 import audit_episode

EVIDENCE = {}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def trajectory_bytes(run):
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **{key: run[key] for key in ("time_us", "p", "v", "a")})
    return buffer.getvalue()


def short_vertical():
    path = PROJECT.parent.parent / "SwarmData/v07_dataset/attempt_20261014T014017Z_15a6bf38/family_s12_b0c036776dcaff71_s2r3_sk00/skeleton.json"
    sk = read_json(path)
    for state in sk["initial_states"]:
        point = np.array(state["position_enu_m"])
        endpoint = point + [-120., 0., 0.]
        sk["references"][state["agent_id"]].update(points_enu_m=[point.tolist(), endpoint.tolist()], endpoint_enu_m=endpoint.tolist())
    return sk


class M2Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.public = scene(); cls.analytic = tracks()

    def test_A1_random_schedules(self):
        rng = random.Random(20261015); maximum = 0.; count = 0
        for index in range(200):
            ids = [f"a{i}" for i in range(rng.randint(2, 12))]
            measured = {a: rng.uniform(10., 1500.) for a in ids}
            group = {"group_id": "g", "members": ids, "column_seed": index}
            for mode in ("synchronous", "sequential"):
                plan = group_plan(group, measured, mode)
                self.assertTrue(all(d >= 0 and abs(d * 10 - round(d * 10)) < 1e-7 for d in plan["departure_delays_s"].values()))
                self.assertLessEqual(max(plan["batch_spans_s"]), 10. + 1e-9)
                if mode == "synchronous":
                    span = max(plan["target_event_times_grid_s"].values()) - min(plan["target_event_times_grid_s"].values())
                    self.assertLessEqual(span, 6.1 + 1e-9); maximum = max(maximum, span)
                else:
                    self.assertTrue(2 <= plan["batch_count"] <= len(ids))
                    self.assertTrue(all(40. <= gap <= 90. for gap in np.diff(plan["batch_centers_s"])))
                count += 1
        EVIDENCE["A1"] = {"groups": 200, "plans": count, "maximum_sync_span_s": maximum}

    def test_A2_A3_independent_draws_and_pair_conditions(self):
        group = {"group_id": "g", "members": ["a", "b", "c"], "column_seed": 71, "between_group_offset_s": 13.4}
        whole = {"group_skeletons": {"g": group}, "members": group["members"], "agent_ids": ["c", "a", "b"], **stop_fields()}
        measured = {"a": 13., "b": 50., "c": 71.2}; original = deepcopy(whole)
        initial = {mode: canonical_json(episode_plan(whole, measured, mode)) for mode in ("synchronous", "sequential")}
        for draw in range(20):
            for mode, other in (("synchronous", "sequential"), ("sequential", "synchronous")):
                self.assertEqual(canonical_json(episode_plan(whole, measured, mode, draw)), canonical_json(episode_plan(whole, measured, mode, draw)))
                self.assertEqual(initial[other], canonical_json(episode_plan(whole, measured, other)))
                self.assertEqual(validate_pair(whole, original), condition_digest(original))
        EVIDENCE["A2"] = {"draws_per_version": 20, "byte_identical_repeats": True, "other_version_unchanged": True}
        EVIDENCE["A3"] = {"digest": condition_digest(whole), "skeleton_unchanged": whole == original}

    def test_A4_overlay_threshold(self):
        result = {}
        for distance in (1.9, 2.1):
            solos = {a: {"agent_ids": [a], "time_us": np.arange(21) * 100000,
                         "p": np.tile([0., y, 120.], (21, 1))[:, None, :]} for a, y in (("a", 0.), ("b", distance))}
            report = solo_interval_check(solos, {"synchronous": {"departure_delays_s": {"a": 0., "b": 0.}}})
            self.assertEqual(report["synchronous"]["below_warning"], distance < 2.)
            result[str(distance)] = report["synchronous"]
        EVIDENCE["A4"] = result

    @classmethod
    def short_runs(cls):
        if not hasattr(cls, "short_result"):
            sk = short_vertical(); delays = {a: 0. for a in sk["members"]}
            baseline = types.ModuleType("task_v07._m2_baseline_execution")
            baseline.__file__ = str(PROJECT / "task_v07/execution.py")
            baseline.__package__ = "task_v07"
            code = subprocess.check_output(["git", "show", "e1fca53:Multi-UAV SimpleGC/task_v07/execution.py"], cwd=PROJECT, text=True, encoding="utf-8")
            exec(compile(code, baseline.__file__, "exec"), baseline.__dict__)
            old = baseline.execute(sk, delays)
            current = execute(sk, delays)
            expanded = deepcopy(sk); expanded.update(stop_fields(), exclusion_policy={a: {} for a in sk["members"]})
            relaxed = execute(expanded, delays)
            cls.short_result = (sk, old, current, relaxed)
        return cls.short_result

    def test_A5_vertical_default_is_exact_baseline(self):
        sk, old, current, _ = self.short_runs()
        self.assertEqual(old["execution_status"], "completed")
        self.assertEqual(trajectory_bytes(old), trajectory_bytes(current))
        self.assertEqual(old["end_us"], current["end_us"])
        EVIDENCE["A5"] = {"baseline": "e1fca53", "frames": len(old["time_us"]), "status": current["execution_status"],
                          "trajectory_sha256": hashlib.sha256(trajectory_bytes(current)).hexdigest(), "npz_byte_identical": True}

    def test_A6_relaxed_stop_is_exact_prefix(self):
        sk, _, old, new = self.short_runs(); n = len(new["time_us"])
        self.assertLessEqual(n, len(old["time_us"]))
        for key in ("time_us", "p", "v", "a"): np.testing.assert_array_equal(new[key], old[key][:n])
        endpoints = np.array([sk["references"][a]["endpoint_enu_m"] for a in new["agent_ids"]])
        distance = np.linalg.norm(new["p"][-1] - endpoints, axis=1); speed = np.linalg.norm(new["v"][-1], axis=1)
        self.assertEqual(new["execution_status"], "completed")
        self.assertTrue(np.all(distance <= 15.) and np.all(speed <= 1.5))
        EVIDENCE["A6"] = {"old_frames": len(old["time_us"]), "new_frames": n, "prefix_exact": True,
                          "final_distances_m": distance.tolist(), "final_speeds_m_s": speed.tolist()}

    def test_A7_observation_hold_unchanged(self):
        from task_v07.dwell import DwellRouteTracker
        sk = short_vertical(); agent = sk["members"][0]
        state = next(s for s in sk["initial_states"] if s["agent_id"] == agent)
        origin = np.array(state["position_enu_m"])
        points = [origin.tolist(), (origin + [-100., 0., 0.]).tolist(), (origin + [-100., -100., 0.]).tolist()]
        sk.update(members=[agent], agent_ids=[agent], initial_states=[state], role="reconnaissance", execution_method="close_observation")
        sk["references"] = {agent: {"points_enu_m": points, "endpoint_enu_m": points[-1],
                                    "intermediate_dwell": {"waypoint_index": 1, "duration_s": 25.}}}
        observe = DwellRouteTracker.observe_sample; receipts = []
        for relaxed in (False, True):
            current = deepcopy(sk)
            if relaxed: current.update(stop_fields())
            events = []
            def capture(tracker, sample, index):
                before = len(tracker.events); observe(tracker, sample, index)
                events.extend(deepcopy(tracker.events[before:]))
            with patch.object(DwellRouteTracker, "observe_sample", capture):
                run = execute(current, {agent: 0.})
            self.assertEqual(run["execution_status"], "completed")
            self.assertEqual(len(events), 1)
            receipts.append(events[0])
        self.assertEqual(receipts[0], receipts[1]); EVIDENCE["A7"] = {"old": receipts[0], "new": receipts[1]}

    def test_A8_partial_finish_uses_conservative_budget(self):
        sk = short_vertical(); delays = {a: 0. for a in sk["members"]}; finished = dict.fromkeys(delays, 100.)
        finished[sk["members"][0]] = None
        actual = joint_budget(sk, delays, finished)
        self.assertEqual(actual, completion_budget(sk, delays))
        EVIDENCE["A8"] = actual

    def test_A9_last_failure_and_history(self):
        from scripts.run_v07_s2_episode_batch import run_episode_job
        run = self.analytic["T1"]; sk = skeleton("transit", run)
        descriptor = {"skeleton_id": "qa_history", "family_id": "family", "base_intent": "transit",
                      "common_draw": {"slot": 0, "approach_mode": "same_direction"}, "task_groups": [{}]}
        failed = {"status": "rejected", "core_times_s": {"a": 1.}, "completion_times_s": {"a": 2.},
                  "failures": [{"agent_id": "a", "conditions": ["observation_dwell"]}]}
        passed = {**failed, "status": "passed", "failures": []}
        timing = {"status": "rejected", "plans": {}, "failed_versions": ["synchronous"],
                  "versions": {"synchronous": {"attempts": [{"draw": 19, "minimum_m": 1.9, "closest_pair": {"agents": ["a", "b"]}}]}}}
        pool = [{"index": i, "skeleton": sk, "bundle": None, "checks": {}} for i in range(3)]
        search = {"candidate_budget": 200, "attempted_candidates": 200, "rejection_reasons": {}}
        with TemporaryDirectory() as tmp, patch("task_v07.expansion.candidate_search.episode_candidate_pool", return_value=(pool, search)), \
             patch("task_v07.unified.rehearsal.rehearse", side_effect=[(failed, {"a": run}), (passed, {"a": run}), (failed, {"a": run})]), \
             patch("task_v07.unified.timing.select_timing", return_value=timing), \
             patch("scripts.run_v07_s2_episode_batch.execute") as joint:
            rows = run_episode_job({"scene": self.public, "descriptor": descriptor, "out": tmp})
            result = read_json(Path(tmp) / "qa_history/planning_rejection.json")
            joint.assert_not_called()
            self.assertEqual(result["category"], "rehearsal_failure"); self.assertTrue(result["exhausted"])
            self.assertEqual([r["category"] for r in result["history"]], ["rehearsal_failure", "timing_conflict", "rehearsal_failure"])
            self.assertTrue(all(r["category"] == "rehearsal_failure" for r in rows))
            EVIDENCE["A9"] = {"category": result["category"], "exhausted": True, "history_categories": [r["category"] for r in result["history"]]}

    def test_A10_rehearsal_observed_roles(self):
        results = []
        for name, role, wanted in (("T1", "transit", "passed"), ("T3", "close_observation", "passed"),
                                  ("T12", "intrusion", "passed"), ("T1", "close_observation", "rejected")):
            run = self.analytic[name]; report = evaluate_solos(self.public, skeleton(role, run), {"a": run})
            self.assertEqual(report["status"], wanted)
            if wanted == "rejected": self.assertIn("observation_dwell", report["failures"][0]["conditions"])
            results.append({"trajectory": name, "role": role, "status": report["status"], "failures": report["failures"]})
        EVIDENCE["A10"] = results

    def test_A11_independent_completeness_and_frame_count(self):
        run = self.analytic["T1"]; sk = skeleton("transit", run); labels, frame = measure(self.public, sk, run, "synchronous")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in (("public_scene", self.public), ("task", sk), ("labels", labels), ("source", {"execution_status": "completed"})):
                save(root / (name + ".json"), value)
            np.savez(root / "truth_10hz.npz", **{k: run[k] for k in ("time_us", "p", "v", "agent_ids")})
            np.savez(root / "frame_labels.npz", **frame)
            write_csv(root / "truth.csv", run["agent_ids"], run["time_us"], run["p"], run["v"])
            self.assertEqual(audit_episode(root)["status"], "PASS")
            save(root / "source.json", {"execution_status": "running"})
            running = audit_episode(root); self.assertEqual(running["status"], "P0_STOP")
            self.assertTrue(any(e["field"] == "evidence.complete_observation" for e in running["event_or_metric_witnesses"]))
            save(root / "source.json", {"execution_status": "timeout"})
            self.assertEqual(audit_episode(root)["status"], "PASS")
            wrong = deepcopy(labels); wrong["evidence"]["frame_count"] -= 1; save(root / "labels.json", wrong)
            self.assertEqual(audit_episode(root)["status"], "P0_STOP")
            save(root / "labels.json", labels)
            np.savez(root / "truth_10hz.npz", **{k: run[k][:-1] for k in ("time_us", "p", "v")}, agent_ids=run["agent_ids"])
            self.assertEqual(audit_episode(root)["status"], "P0_STOP")
            EVIDENCE["A11"] = {"completed": "PASS", "running_with_complete_label": "P0_STOP", "timeout_complete": "PASS",
                               "wrong_label_frame_count": "P0_STOP", "deleted_truth_frame": "P0_STOP"}


if __name__ == "__main__":
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(M2Checks))
    destination = PROJECT / "docs/v07/evidence/m2"; destination.mkdir(parents=True, exist_ok=True)
    save(destination / "qa_results.json", {"status": "PASS" if result.wasSuccessful() else "FAIL", "test_methods": result.testsRun,
        "wall_s": time.perf_counter() - started, "cases": EVIDENCE,
        "failures": [{"test": str(test), "traceback": trace} for test, trace in result.failures + result.errors]})
    raise SystemExit(0 if result.wasSuccessful() else 1)
