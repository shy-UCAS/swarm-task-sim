"""T1-T12 for the v0.7 first_edition production harness."""
import json
import pickle
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scripts import run_v07_fe_production as prod
from scripts import v07_fe_production_core as core
from scripts.run_v07_s2_episode_batch import run_episode_job
from scripts.run_v07_s2_expansion import EXPANSION_SCOPE
from scripts.run_m3_r3_r4 import pair_result
from task_v07.execution import FROZEN_SHA256
from task_v07.expansion.contracts import P0ContractError
from task_v07.io import read_json
from task_v07.unified import rehearsal as rehearsal_module
from swarm_sim.fast_dynamics.reference_r3 import CONFIG_SHA256


def descriptor(sid="sid", intent="transit", slot=0, family="family"):
    return {"skeleton_id": sid, "family_id": family, "base_intent": intent,
            "common_draw": {"slot": slot, "approach_mode": "same_direction",
                            "actual_unit_count": 2},
            "task_groups": [{"group_id": "g", "members": ["a", "b"]}],
            "subset": "regular"}


def five_descriptors(family="family", slot=0):
    return [descriptor(f"{family}_{intent}", intent, slot, family) for intent in core.INTENTS]


def fake_run():
    return {"agent_ids": ["a"], "time_us": np.array([0, 100000]),
            "p": np.zeros((2, 1, 3)), "v": np.zeros((2, 1, 3)),
            "a": np.zeros((2, 1, 3)), "execution_status": "completed",
            "wall_s": 0.1, "config_sha256": "x", "end_us": 100000,
            "time_budget": 100}


def fake_sk(sid="sid"):
    return {"skeleton_id": sid, "members": ["a"], "group_id": "g", "agent_ids": ["a"],
            "group_skeletons": {"g": {"members": ["a"], "execution_method": "transit"}},
            "approach_mode": "same_direction"}


def fake_search():
    return {"candidate_budget": 200, "attempted_candidates": 200,
            "actual_single_agent_calibration_rounds": 0, "solo_flights_run": 0,
            "rejection_reasons": {}, "group_rejection_reasons": {},
            "combination_rejection_reasons": {}, "rejection_class_counts": {},
            "termination": None, "selection": {}}


def fake_timing():
    plan = {"departure_delays_s": {"a": 0.}}
    return {"status": "PASS",
            "plans": {"synchronous": plan, "sequential": dict(plan)},
            "versions": {"synchronous": {"attempts": []}, "sequential": {"attempts": []}},
            "overlay": {"synchronous": {}, "sequential": {}},
            "failed_versions": []}


def fake_rehearsal():
    return {"status": "passed", "core_times_s": {"a": 1.},
            "completion_times_s": {"a": 2.}, "failures": []}


def run_fake_job(tmp, reference_version="r3", candidate_pool_pickle=None,
                 candidate_pool_sha256=None, episode_scope=None, pool=None,
                 search=None, pool_mock=None):
    """Drive the real run_episode_job through rehearse with heavy internals faked."""
    sid = "sid"
    pool = pool if pool is not None else [{"index": 0, "skeleton": fake_sk(sid),
                                           "bundle": None, "checks": {}}]
    search = search if search is not None else fake_search()
    solo_calls, joint_calls, write_calls = [], [], []
    payload = {"scene": {}, "descriptor": descriptor(sid), "out": str(tmp),
               "planner": ["role"], "geometry_backend": "unified"}
    if reference_version is not None:
        payload["reference_version"] = reference_version
    if candidate_pool_pickle is not None:
        payload["candidate_pool_pickle"] = str(candidate_pool_pickle)
        payload["candidate_pool_sha256"] = candidate_pool_sha256
    if episode_scope is not None:
        payload["episode_scope"] = episode_scope
    payload["scope"] = "WRONG"

    def solo(group, delays, **kwargs):
        solo_calls.append(kwargs)
        return fake_run()

    def joint(skeleton, delays, **kwargs):
        joint_calls.append(kwargs)
        return fake_run()

    def write(*args, **kwargs):
        write_calls.append(kwargs)
        return {"episode_id": "fake", "path": None}

    pool_patch = pool_mock if pool_mock is not None else patch(
        "task_v07.expansion.candidate_search.episode_candidate_pool",
        return_value=(pool, search))
    with pool_patch as pool_control, \
         patch.object(rehearsal_module, "execute", side_effect=solo), \
         patch.object(rehearsal_module, "evaluate_solos", return_value=fake_rehearsal()), \
         patch.object(rehearsal_module, "joint_budget", return_value=100.), \
         patch("task_v07.unified.timing.select_timing", return_value=fake_timing()), \
         patch("scripts.run_v07_s2_episode_batch.execute", side_effect=joint), \
         patch("scripts.run_v07_s2_episode_batch.write_result", side_effect=write), \
         patch("scripts.run_v07_s2_episode_batch.save_json"), \
         patch("scripts.run_v07_s2_episode_batch.condition_digest", return_value="d"), \
         patch("scripts.run_v07_s2_episode_batch.prediction_error", return_value={}), \
         patch("scripts.run_v07_s2_episode_batch.validate_pair"), \
         patch("scripts.run_v07_s2_episode_batch.load_pair"):
        rows = run_episode_job(payload)
    return rows, solo_calls, joint_calls, write_calls, pool_control


class ProductionCoreTests(unittest.TestCase):
    def test_T1_reference_version_r3_reaches_solo_and_joint_execute(self):
        sk = fake_sk()
        calls = []
        def solo(group, delays, **kwargs):
            calls.append(kwargs)
            return fake_run()
        with patch.object(rehearsal_module, "execute", side_effect=solo), \
             patch.object(rehearsal_module, "evaluate_solos", return_value=fake_rehearsal()):
            rehearsal_module.rehearse({}, sk, reference_version="r3")
        self.assertTrue(calls and all(call["reference_version"] == "r3" for call in calls))
        with tempfile.TemporaryDirectory() as tmp:
            _rows, solo_calls, joint_calls, _writes, _pool = run_fake_job(tmp, "r3")
            self.assertTrue(solo_calls and all(call["reference_version"] == "r3" for call in solo_calls))
            self.assertTrue(joint_calls and all(call["reference_version"] == "r3" for call in joint_calls))

    def test_T1_worker_cli_does_not_require_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(prod, "worker_b", return_value=0) as worker:
                code = prod.main(["--worker-stage", "B", "--run-dir", tmp,
                                  "--skeleton", "sid"])
            self.assertEqual(code, 0)
            worker.assert_called_once()

    def test_T2_reference_version_defaults_to_r2(self):
        sk = fake_sk()
        calls = []
        def solo(group, delays, **kwargs):
            calls.append(kwargs)
            return fake_run()
        with patch.object(rehearsal_module, "execute", side_effect=solo), \
             patch.object(rehearsal_module, "evaluate_solos", return_value=fake_rehearsal()):
            rehearsal_module.rehearse({}, sk)
        self.assertTrue(calls and all(call["reference_version"] == "r2" for call in calls))
        with tempfile.TemporaryDirectory() as tmp:
            _rows, solo_calls, joint_calls, _writes, _pool = run_fake_job(tmp, None)
            self.assertTrue(solo_calls and all(call["reference_version"] == "r2" for call in solo_calls))
            self.assertTrue(joint_calls and all(call["reference_version"] == "r2" for call in joint_calls))

    def test_T3_cached_candidate_pool_and_corruptions(self):
        sid = "sid"
        candidate = {"index": 0, "skeleton": fake_sk(sid), "bundle": None, "checks": {}}
        payload = {"skeleton_id": sid, "pool": [candidate], "search": fake_search()}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cached = root / "candidate_pool.pkl"
            with cached.open("wb") as stream:
                pickle.dump(payload, stream, protocol=5)
            digest = core.sha256_file(cached)
            (root / "run").mkdir()
            pool_mock = patch("task_v07.expansion.candidate_search.episode_candidate_pool",
                              side_effect=AssertionError("must not call"))
            _rows, _solo, _joint, writes, control = run_fake_job(
                root / "run", candidate_pool_pickle=cached,
                candidate_pool_sha256=digest, pool_mock=pool_mock)
            control.assert_not_called()
            self.assertTrue(writes)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cached = root / "candidate_pool.pkl"
            with cached.open("wb") as stream:
                pickle.dump(payload, stream, protocol=5)
            (root / "a").mkdir()
            (root / "b").mkdir()
            (root / "c").mkdir()
            with self.assertRaises(P0ContractError):
                run_episode_job({"scene": {}, "descriptor": descriptor(sid),
                                 "out": str(root / "a"),
                                 "candidate_pool_pickle": str(cached),
                                 "candidate_pool_sha256": "0" * 64})
            bad_top = {"skeleton_id": "other", "pool": [candidate], "search": fake_search()}
            with cached.open("wb") as stream:
                pickle.dump(bad_top, stream, protocol=5)
            with self.assertRaises(P0ContractError):
                run_episode_job({"scene": {}, "descriptor": descriptor(sid),
                                 "out": str(root / "b"),
                                 "candidate_pool_pickle": str(cached),
                                 "candidate_pool_sha256": core.sha256_file(cached)})
            bad_pool = {"skeleton_id": sid,
                        "pool": [{"index": 0, "skeleton": fake_sk("other"),
                                  "bundle": None, "checks": {}}],
                        "search": fake_search()}
            with cached.open("wb") as stream:
                pickle.dump(bad_pool, stream, protocol=5)
            with self.assertRaises(P0ContractError):
                run_episode_job({"scene": {}, "descriptor": descriptor(sid),
                                 "out": str(root / "c"),
                                 "candidate_pool_pickle": str(cached),
                                 "candidate_pool_sha256": core.sha256_file(cached)})
        with tempfile.TemporaryDirectory() as tmp:
            pool = [{"index": 0, "skeleton": fake_sk(sid), "bundle": None, "checks": {}}]
            pool_mock = patch("task_v07.expansion.candidate_search.episode_candidate_pool",
                              return_value=(pool, fake_search()))
            _rows, _solo, _joint, _writes, control = run_fake_job(tmp, pool_mock=pool_mock)
            control.assert_called_once()
            args, kwargs = control.call_args
            self.assertEqual(kwargs.get("backend"), "unified")

    def test_T4_episode_scope_reaches_source_json_and_payload_scope_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            _rows, _solo, _joint, writes, _pool = run_fake_job(tmp, "r3")
            self.assertTrue(writes and writes[0]["scope"] == EXPANSION_SCOPE)
        with tempfile.TemporaryDirectory() as tmp:
            _rows, _solo, _joint, writes, _pool = run_fake_job(
                tmp, "r3", episode_scope="TEST_SCOPE")
            self.assertTrue(writes and writes[0]["scope"] == "TEST_SCOPE")
        labels = {"schema_version": "x", "generation_quality": {"retained": True, "status": "valid",
                  "exclusion_reasons": [], "minimum_separation_m": 10.},
                  "cluster": {"result": {"status": "success", "primary_task_success": True,
                                         "all_groups_complete": True},
                              "observed": {"minimum_separation_m": 10.}},
                  "task_groups": {}, "agents": {}}
        run = fake_run()
        skeleton = {"skeleton_id": "sid", "agent_ids": ["a"], "approach_mode": "same_direction",
                    "group_skeletons": {}}
        descriptor_row = descriptor("sid")
        descriptor_row["family_conditions"] = {}
        packet = []
        with tempfile.TemporaryDirectory() as tmp:
            from scripts import run_v07_s2_episode_batch as batch
            out = Path(tmp)
            dest = out / "sid" / "synchronous"
            dest.mkdir(parents=True)
            with patch.object(batch, "measure", return_value=(labels, {})), \
                 patch.object(batch, "write_episode", side_effect=lambda *a, **k: packet.append(k)), \
                 patch.object(batch, "audit_episode", return_value={}), \
                 patch.object(batch, "group_truncations", return_value={}), \
                 patch.object(batch, "save_json"), \
                 patch.object(batch, "condition_digest", return_value="d"), \
                 patch.object(batch, "scene_digest", return_value="s"):
                batch.write_result({}, descriptor_row, skeleton, None, run,
                                   {"departure_delays_s": {"a": 0.}}, {}, "synchronous",
                                   out, 1., scope="TEST_SCOPE")
            self.assertEqual(packet[0]["scope"], "TEST_SCOPE")
        with tempfile.TemporaryDirectory() as tmp:
            from task_v07 import io as task_io
            out = Path(tmp)
            skeleton = {"skeleton_id": "sid", "agent_ids": ["a"]}
            with patch.object(task_io, "validate_public_scene"), \
                 patch.object(task_io, "observations",
                              return_value=(run["p"].copy(), run["v"].copy())), \
                 patch.object(task_io, "load_episode",
                              return_value={"x": np.concatenate((run["p"], run["v"]), axis=2)}):
                task_io.write_episode(out / "episode", {}, {}, skeleton, run, labels, {},
                                      {"a": 0.}, "synchronous", {}, scope="TEST_SCOPE")
            self.assertEqual(read_json(out / "episode" / "source.json")["scope"], "TEST_SCOPE")

    def test_T5_draw_retention_is_all_or_nothing(self):
        draws = core.group_draws(five_descriptors())
        draw = draws[0]
        b = {d["skeleton_id"]: {"status": "PASS"} for d in draw["descriptors"]}
        rows = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for d in draw["descriptors"]:
                for mode in core.MODES:
                    episode = root / "episodes" / d["skeleton_id"] / mode
                    episode.mkdir(parents=True)
                    (episode / "manifest.json").write_text("{}")
                    (episode / "labels.json").write_text("{}")
                    rows.append({"episode_id": f"{d['skeleton_id']}_{mode}",
                                 "path": f"{d['skeleton_id']}/{mode}", "mode": mode})
            c = {d["skeleton_id"]: {"status": "PAIRED", "rows": [row for row in rows
                                                                 if row["path"].startswith(d["skeleton_id"] + "/")]}
                 for d in draw["descriptors"]}
            b_intent = core.intent_statuses(draw, {"B": b, "C": c}, "B")
            c_intent = core.intent_statuses(draw, {"B": b, "C": c}, "C")
            self.assertEqual(core.classify_draw(draw, b_intent, c_intent), "RETAINED")
            retained, non, _details = core.manifest_rows(root, draw["descriptors"],
                                                        {"B": b, "C": c})
            self.assertEqual(len(retained), 10)
            self.assertEqual(non, [])
            broken = dict(c)
            broken[draw["descriptors"][0]["skeleton_id"]] = {
                "status": "NOT_PAIRED",
                "rows": [row for row in rows
                         if row["path"].startswith(draw["descriptors"][0]["skeleton_id"] + "/")]}
            self.assertEqual(core.classify_draw(
                draw, core.intent_statuses(draw, {"B": b, "C": broken}, "B"),
                core.intent_statuses(draw, {"B": b, "C": broken}, "C")), "C_NOT_PAIRED")
            retained, non, _details = core.manifest_rows(root, draw["descriptors"],
                                                        {"B": b, "C": broken})
            self.assertEqual(retained, [])
            self.assertEqual(len(non), 10)

    def test_T6_b_reject_or_timeout_never_enqueues_c(self):
        draws = core.group_draws(five_descriptors())
        draw = draws[0]
        for bad in ("REJECT", "TIMEOUT"):
            b = {d["skeleton_id"]: {"status": "PASS"} for d in draw["descriptors"]}
            b[draw["descriptors"][0]["skeleton_id"]] = {"status": bad}
            self.assertEqual(core.classify_draw(
                draw, core.intent_statuses(draw, {"B": b, "C": {}}, "B"), {}), "B_REJECT")
            queue, c_tasks, c_sids, c_draws = [], [], set(), set()
            prod._enqueue_c_tasks(draws, {"B": b, "C": {}}, queue, c_tasks,
                                  c_sids, c_draws, None)
            self.assertEqual(c_tasks, [])
        b = {d["skeleton_id"]: {"status": "PASS"} for d in draw["descriptors"]}
        queue, c_tasks, c_sids, c_draws = [], [], set(), set()
        prod._enqueue_c_tasks(draws, {"B": b, "C": {}}, queue, c_tasks,
                              c_sids, c_draws, None)
        self.assertEqual(len(c_tasks), 5)
        self.assertEqual(queue[:5], c_tasks)

    def test_T7_resume_moves_residuals_and_reinterrupt_does_not_write_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            (run_dir / "status").mkdir(parents=True)
            (run_dir / "planning" / "done").mkdir(parents=True)
            (run_dir / "planning" / "done" / "keep.txt").write_text("keep")
            (run_dir / "planning" / "resid").mkdir(parents=True)
            (run_dir / "planning" / "resid" / "partial.txt").write_text("partial")
            (run_dir / "episodes" / "resid").mkdir(parents=True)
            (run_dir / "episodes" / "resid" / "partial.txt").write_text("episode")
            (run_dir / "status" / "B__done.json").write_text("{}")
            (run_dir / "status" / "B__resid.json.tmp").write_text("tmp")
            descriptors = [{"skeleton_id": "done"}, {"skeleton_id": "resid"}]
            result = prod.prepare_resume(run_dir, descriptors)
            self.assertTrue((run_dir / "planning" / "done" / "keep.txt").exists())
            self.assertFalse((run_dir / "planning" / "resid").exists())
            self.assertFalse((run_dir / "episodes" / "resid").exists())
            self.assertFalse((run_dir / "status" / "B__resid.json.tmp").exists())
            aborted = run_dir / "_aborted" / result["timestamp"]
            self.assertEqual((aborted / "B" / "resid" / "partial.txt").read_text(), "partial")
            self.assertEqual((aborted / "C" / "resid" / "partial.txt").read_text(), "episode")
            self.assertTrue((aborted / "status_tmp" / "B__resid.json.tmp").exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            (run_dir / "status").mkdir(parents=True)
            (run_dir / "planning").mkdir(parents=True)
            (run_dir / "episodes").mkdir(parents=True)
            (run_dir / "logs").mkdir(parents=True)
            descriptors = five_descriptors()
            (run_dir / "descriptors").mkdir()
            (run_dir / "descriptors" / "descriptors.json").write_text(json.dumps(descriptors))
            (run_dir / "registration.json").write_text(json.dumps({"run_id": "run"}))
            (run_dir / "code_hashes.json").write_text("{}")
            stop_event = threading.Event()
            result = {}
            def sleepy(task, directory):
                if task["stage"] == "B":
                    script = ("import pathlib,sys,time;"
                              "p=pathlib.Path(sys.argv[1]);p.mkdir(parents=True,exist_ok=True);"
                              "(p/'partial.txt').write_text('x');time.sleep(30)")
                    return [sys.executable, "-c", script,
                            str(Path(directory) / "planning" / task["sid"])]
                return [sys.executable, "-c", "import time;time.sleep(30)"]
            def run():
                with patch.object(prod, "code_hashes", return_value={}):
                    result["code"] = prod.run_scheduler(
                        run_dir, {}, descriptors, 1, 1., 1.,
                        single_skeletons={descriptors[0]["skeleton_id"]},
                        worker_command=sleepy, poll_s=0.05, stop_event=stop_event)
            thread = threading.Thread(target=run)
            thread.start()
            deadline = time.time() + 10
            while time.time() < deadline and not (run_dir / "planning" / descriptors[0]["skeleton_id"]).exists():
                time.sleep(0.05)
            stop_event.set()
            thread.join(timeout=15)
            self.assertEqual(result.get("code"), 130)
            sid = descriptors[0]["skeleton_id"]
            self.assertFalse((run_dir / "status" / f"B__{sid}.json").exists())
            prod.prepare_resume(run_dir, descriptors)
            self.assertFalse((run_dir / "planning" / sid).exists())

            def status_worker(task, directory):
                sid = task["sid"]
                stage = task["stage"]
                payload = {"stage": stage, "skeleton_id": sid,
                           "status": "PASS" if stage == "B" else "PAIRED",
                           "detail": {}, "rows": [] if stage == "C" else None,
                           "paired": True if stage == "C" else None,
                           "first_failure": None if stage == "C" else None,
                           "elapsed_wall_s": 0. if stage == "C" else None}
                (Path(directory) / "status" / f"{stage}__{sid}.json").write_text(json.dumps(payload))
                return [sys.executable, "-c", "pass"]
            with patch.object(prod, "code_hashes", return_value={}):
                code = prod.run_scheduler(run_dir, {}, descriptors, 1, 1., 1.,
                                          single_skeletons={sid},
                                          worker_command=status_worker, poll_s=0.05)
            self.assertEqual(code, 0)
            self.assertTrue((run_dir / "status" / f"B__{sid}.json").exists())

    def test_T8_worker_p0_kills_other_workers_and_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            for name in ("status", "planning", "episodes", "logs", "descriptors"):
                (run_dir / name).mkdir(parents=True)
            descriptors = five_descriptors()
            (run_dir / "descriptors" / "descriptors.json").write_text(json.dumps(descriptors))
            (run_dir / "registration.json").write_text(json.dumps({"run_id": "run"}))
            (run_dir / "code_hashes.json").write_text("{}")
            p0_sid = sorted(d["skeleton_id"] for d in descriptors)[0]
            def worker(task, directory):
                if task["sid"] == p0_sid and task["stage"] == "B":
                    payload = {"stage": "B", "skeleton_id": task["sid"],
                               "status": "P0_STOP", "detail": "forced"}
                    (Path(directory) / "status" / f"B__{task['sid']}.json").write_text(json.dumps(payload))
                    return [sys.executable, "-c", "pass"]
                return [sys.executable, "-c", "import time;time.sleep(30)"]
            with patch.object(prod, "code_hashes", return_value={}):
                code = prod.run_scheduler(run_dir, {}, descriptors, 2, 30., 30.,
                                          worker_command=worker, poll_s=0.05)
            self.assertEqual(code, 2)
            self.assertTrue((run_dir / "P0_STOP.json").exists())
            self.assertEqual(read_json(run_dir / "P0_STOP.json")["reason"], "WORKER_P0_STOP")

    def test_T9_r2_config_fails_hard_audit_and_writes_p0(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "episodes"
            sid = "sid"
            rows = []
            for mode in core.MODES:
                episode = out / sid / mode
                episode.mkdir(parents=True)
                (episode / "labels.json").write_text(json.dumps({
                    "schema_version": "x",
                    "generation_quality": {"retained": True, "minimum_separation_m": 10.},
                    "cluster": {"result": {"status": "success"}},
                    "task_groups": {}}))
                (episode / "source.json").write_text(json.dumps({
                    "config_sha256": FROZEN_SHA256, "execution_status": "completed"}))
                (episode / "independent_exact_audit.json").write_text(json.dumps({"status": "PASS"}))
                (episode / "policy_geometry_audit.json").write_text(json.dumps({
                    "infrastructure_report": {"forbidden_policy_checked": True,
                                              "forbidden_region_sample_count": 0,
                                              "hard_obstacle_sample_count": 0,
                                              "outside_world_sample_count": 0},
                    "independent": {"status": "PASS"}}))
                (episode / "task.json").write_text("{}")
                (episode / "metrics.json").write_text("{}")
                (episode / "truth_10hz.npz").write_bytes(b"placeholder")
                rows.append({"episode_id": f"{sid}_{mode}", "path": f"{sid}/{mode}", "mode": mode,
                             "state": "generated", "quality_valid": True, "audit_passed": True,
                             "task_result": "success", "all_groups_complete": True,
                             "execution_status": "completed",
                             "coordination_by_group": {"g": mode},
                             "condition_digest": "d", "agent_ids": ["a"], "scene_digest": "s"})
            result = pair_result(out, sid, rows, CONFIG_SHA256)
            self.assertFalse(result["hard_physical_audit_passed"])
            self.assertTrue(result["paired"])
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "status").mkdir()
            (run_dir / "descriptors").mkdir()
            (run_dir / "planning" / "sid").mkdir(parents=True)
            (run_dir / "episodes").mkdir()
            (run_dir / "qc").mkdir()
            (run_dir / "descriptors" / "descriptors.json").write_text(json.dumps([descriptor("sid")]))
            (run_dir / "registration.json").write_text(json.dumps({
                "family_rows": [{"family_id": "family"}], "FE_SCOPE": "scope"}))
            (run_dir / "status" / "B__sid.json").write_text(json.dumps({"status": "PASS"}))
            (run_dir / "planning" / "sid" / "planning_result.json").write_text(json.dumps({
                "candidate_pool_sha256": "x"}))
            with patch.object(prod, "_load_family", return_value=({}, {})), \
                 patch.object(prod, "run_episode_job", return_value=[]), \
                 patch.object(prod, "pair_result", return_value={
                     "hard_physical_audit_passed": False, "paired": False,
                     "first_failure": {"stage": "config"}, "episodes": []}):
                code = prod.worker_c(run_dir, "sid")
            self.assertEqual(code, 2)
            self.assertEqual(read_json(run_dir / "status" / "C__sid.json")["status"], "P0_STOP")

    def test_T10_stage_a_determinism_and_error_classes(self):
        if not prod.BASELINE_PATH.exists():
            self.skipTest("S1.5 baseline is not available")
        baseline = read_json(prod.BASELINE_PATH)
        record = None
        for row in baseline["families"]:
            if Path(row["directory"]).exists():
                record = row
                break
        if record is None:
            self.skipTest("no external family directory")
        start = int(record["candidate_index"])
        base = {field: "x" for field in core.VERSION_FIELDS}
        with tempfile.TemporaryDirectory() as tmp:
            one, two = Path(tmp) / "one", Path(tmp) / "two"
            one.mkdir()
            two.mkdir()
            first, descriptors_one, _ = prod.stage_a(one, start, start + 1, base)
            second, descriptors_two, _ = prod.stage_a(two, start, start + 1, base)
            self.assertEqual(descriptors_one, descriptors_two)
            self.assertEqual(first["descriptor_count"], second["descriptor_count"])
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "value"
            run_dir.mkdir()
            with patch.object(prod, "sample_family_descriptors", side_effect=ValueError("too few")):
                registration, descriptors, _ = prod.stage_a(run_dir, start, start + 1, base)
            self.assertEqual(len(registration["family_unsampleable"]), 1)
            self.assertEqual(descriptors, [])
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "other"
            run_dir.mkdir()
            with patch.object(prod, "sample_family_descriptors", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    prod.stage_a(run_dir, start, start + 1, base)

    def test_T11_startup_refusals_and_version_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "existing").mkdir()
            with self.assertRaises(core.ProductionError) as caught:
                prod._new_run(root, "existing", 0, 1, 1, 1., 1., True)
            self.assertEqual(caught.exception.code, 3)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "quiet").mkdir()
            (root / "quiet" / "registration.json").write_text(json.dumps({
                "family_rows": [{"candidate_index": 5}]}))
            with self.assertRaises(core.ProductionError) as caught:
                prod._new_run(root, "new", 5, 6, 1, 1., 1., True)
            self.assertEqual(caught.exception.code, 3)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def fake_git(*args):
                if args == ("rev-parse", "HEAD"):
                    return "abc"
                if args == ("status", "--porcelain"):
                    return " M file"
                raise AssertionError(args)
            with patch.object(prod, "git", side_effect=fake_git):
                with self.assertRaises(core.ProductionError) as caught:
                    prod._new_run(root, "dirty", 0, 1, 1, 1., 1., True)
            self.assertEqual(caught.exception.code, 3)
        registration = {field: "x" for field in core.VERSION_FIELDS}
        registration["family_rows"] = []
        with tempfile.TemporaryDirectory() as tmp:
            manifest = core.build_manifest(tmp, registration, [], {"B": {}, "C": {}})
        for field in core.VERSION_FIELDS:
            self.assertIn(field, manifest)

    def test_T12_timeout_writes_timeout_and_drops_draw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            for name in ("status", "planning", "episodes", "logs", "descriptors"):
                (run_dir / name).mkdir(parents=True)
            descriptors = five_descriptors()
            sid = descriptors[0]["skeleton_id"]
            (run_dir / "descriptors" / "descriptors.json").write_text(json.dumps(descriptors))
            (run_dir / "registration.json").write_text(json.dumps({"run_id": "run"}))
            (run_dir / "code_hashes.json").write_text("{}")
            def sleepy(task, directory):
                return [sys.executable, "-c", "import time;time.sleep(10)"]
            with patch.object(prod, "code_hashes", return_value={}):
                code = prod.run_scheduler(run_dir, {}, descriptors, 1, 0.3, 0.3,
                                          single_skeletons={sid}, worker_command=sleepy,
                                          poll_s=0.05)
            self.assertNotEqual(code, 2)
            status = read_json(run_dir / "status" / f"B__{sid}.json")
            self.assertEqual(status["status"], "TIMEOUT")
            draw = core.group_draws(descriptors)[0]
            b = {descriptor["skeleton_id"]: {"status": "PASS"} for descriptor in draw["descriptors"]}
            b[sid] = status
            self.assertEqual(core.classify_draw(
                draw, core.intent_statuses(draw, {"B": b, "C": {}}, "B"), {}), "B_REJECT")


if __name__ == "__main__":
    unittest.main()
