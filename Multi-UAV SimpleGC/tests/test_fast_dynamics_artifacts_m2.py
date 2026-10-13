"""Functional M2 data contracts, semantic windows, and the public data chain."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from swarm_sim.dataset import build_dataset
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.episode_loader import load_episode
from swarm_sim.fast_dynamics.adapter import analyze_semantics, observed_route_complete, valid_epoch_events
from swarm_sim.fast_dynamics.artifacts import write_episode, validate_episode
from swarm_sim.fast_dynamics.contracts import M2Config, ReferenceConfig, ExecutionConfig, FastDynamicsConfig
from swarm_sim.fast_dynamics.mission_executor import run_mission
from swarm_sim.generation import file_hash
from swarm_sim.language_v0 import describe_dataset
from swarm_sim.recording import write_json
from swarm_sim.tasks import compile_task
from swarm_sim.fast_dynamics import adapter


FIXTURE = Path(__file__).parent / "fixtures" / "fast_dynamics" / "rapid_passage_0000_v00.json"


def point(x, y=0):
    return dict(east_m=x, north_m=y, up_m=8.)


class M2WindowTests(unittest.TestCase):
    def test_real_tasks_plan_only_their_compiled_phases_even_before_execution(self):
        fixtures = Path(__file__).resolve().parents[1] / "verification/fast_dynamics_m2/m2_tasks"
        # Literal expectations from the two real TaskSpecs, not the adapter or registry.
        for count, required, expected in (
                (2, False, ["approach", "observe"]),
                (3, True, ["approach", "observe", "return"])):
            with self.subTest(agents=count):
                task = json.loads((fixtures / f"reconnaissance__equal_strip_lawnmower__n{count}.json").read_text(encoding="utf-8"))
                self.assertIs(task["mission"]["return_required"], required)
                scene = compile_task(task)
                labels, _, _ = analyze_semantics(scene, {v["id"]: [] for v in scene["vehicles"]}, [], 0., "timeout")
                self.assertEqual(labels["planned_phases"], expected)
                self.assertEqual(labels["planned_behaviors"], ["area_scan"])
                self.assertIsNone(labels["mission_success"])

    def test_semantic_reuse_is_scoped_exact_and_returns_independent_values(self):
        scene = compile_task(json.loads(FIXTURE.read_text(encoding="utf-8")))
        traces = {v["id"]: [] for v in scene["vehicles"]}
        args = (scene, traces, [], 0., "timeout")
        with patch.object(adapter, "_analyze_semantics", wraps=adapter._analyze_semantics) as calculate:
            with adapter.reuse_semantics() as stats:
                baseline = adapter.analyze_semantics(*args)
                repeated = adapter.analyze_semantics(*copy.deepcopy(args))
                self.assertEqual(json.dumps(baseline), json.dumps(repeated))
                repeated[0]["planned_phases"].append("fabricated")
                self.assertEqual(adapter.analyze_semantics(*args), baseline)
                self.assertEqual(calculate.call_count, 1)
                self.assertEqual(stats["hits"], 2)
                for changed in (dict(scene=copy.deepcopy(scene)), dict(traces=copy.deepcopy(traces)),
                                dict(events=[dict(event="different")]), dict(end_s=.01), dict(status="completed")):
                    if "scene" in changed:
                        changed["scene"]["task_spec"]["task_id"] += "_different"
                    if "traces" in changed:
                        changed["traces"][next(iter(traces))] = [(0., [0., 0., 8., 0., 0., 0.])]
                    kwargs = dict(zip(("scene", "traces", "events", "end_s", "status"), args))
                    kwargs.update(changed)
                    adapter.analyze_semantics(**kwargs)
                self.assertEqual(calculate.call_count, 6)
            adapter.analyze_semantics(*args)
            self.assertEqual(calculate.call_count, 7)

    def test_disabling_or_nesting_reuse_does_not_leak_results(self):
        scene = compile_task(json.loads(FIXTURE.read_text(encoding="utf-8")))
        args = (scene, {v["id"]: [] for v in scene["vehicles"]}, [], 0., "timeout")
        with patch.object(adapter, "_analyze_semantics", wraps=adapter._analyze_semantics) as calculate:
            with adapter.reuse_semantics():
                baseline = adapter.analyze_semantics(*args)
                with adapter.reuse_semantics(enabled=False):
                    self.assertEqual(adapter.analyze_semantics(*args), baseline)
                    self.assertEqual(adapter.analyze_semantics(*args), baseline)
                self.assertEqual(adapter.analyze_semantics(*args), baseline)
                with self.assertRaisesRegex(RuntimeError, "scope failure"):
                    with adapter.reuse_semantics():
                        adapter.analyze_semantics(*args)
                        raise RuntimeError("scope failure")
                self.assertEqual(adapter.analyze_semantics(*args), baseline)
                self.assertEqual(calculate.call_count, 4)

    def test_closed_loop_needs_actual_ordered_visits(self):
        route = [point(10), point(10, 10), point(0, 10), point(0)]
        stationary = [(float(t), [0., 0., 8.]) for t in range(5)]
        self.assertFalse(observed_route_complete(stationary, point(0), route, 0., 4.))
        actual = [(float(i), [p["east_m"], p["north_m"], 8.]) for i, p in enumerate([point(0), *route])]
        self.assertTrue(observed_route_complete(actual, point(0), route, 0., 4.))

    def test_later_lap_cannot_replace_missing_first_loop(self):
        route = [point(10), point(10, 10), point(0, 10), point(0)] * 2
        actual = [(float(i), [p["east_m"], p["north_m"], 8.]) for i, p in enumerate([point(0), *route[:4]])]
        self.assertFalse(observed_route_complete(actual, point(0), route, 0., 4.))

    def test_far_cross_track_point_is_not_route_completion(self):
        self.assertFalse(observed_route_complete([(0., [0., 0., 8.]), (3., [30., 100., 8.])],
                                                 point(0), [point(30)], 0., 3.))

    def test_only_consecutive_duplicate_points_are_cleaned(self):
        actual = [(0., [0., 0., 8.]), (1., [10., 0., 8.]), (2., [0., 0., 8.])]
        self.assertTrue(observed_route_complete(actual, point(0), [point(0), point(10), point(10), point(0)], 0., 2.))
        self.assertTrue(observed_route_complete(actual, point(0), [point(0)], 0., 2.))

    def test_same_tick_reset_revokes_previous_confirmation(self):
        events = [dict(event="phase_arrived", phase="p", agent_id="a", t_us=10, epoch=0),
                  dict(event="phase_confirmation_reset", phase="p", agent_id="a", t_us=10, epoch=1)]
        self.assertEqual([e["event"] for e in valid_epoch_events(events, "p", "a")], ["phase_confirmation_reset"])

    def test_m2_reference_bounds_and_legacy_config_remain_distinct(self):
        self.assertNotIn("reference", FastDynamicsConfig().to_dict())
        self.assertEqual(M2Config.from_dict(M2Config().to_dict()), M2Config())
        for value in (True, None, float("nan"), float("inf"), -.1, .3):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ReferenceConfig(corner_cut_max_m=value)
        with self.assertRaises(ValueError):
            FastDynamicsConfig.from_dict(M2Config().to_dict())


class M2PublicChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.result = run_mission(cls.task, M2Config())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, result=None, name="m2"):
        result = result or self.result
        path = self.root / name
        manifest = write_episode(result.scene, result, path, run_id=name,
            input_hashes={FIXTURE.name: file_hash(FIXTURE)}, config=result.config, seed=20261012)
        return path, manifest

    def mutate(self, run, manifest, name, change):
        obj = json.loads((run / "analysis" / name).read_text(encoding="utf-8"))
        change(obj)
        write_json(run / "analysis" / name, obj)
        manifest["artifact_sha256"][name] = file_hash(run / "analysis" / name)

    def test_actual_m2_public_export_load_audit_describe(self):
        run, manifest = self.write()
        self.assertIs(manifest["mission_success"], True)
        self.assertIs(manifest["episode_quality_eligible"], True)
        self.assertEqual(manifest["analysis_version"], "fast_dynamics_semantic_adapter_v2")
        dataset = self.root / "dataset"
        build_dataset([run], dataset)
        loaded = load_episode(dataset / "episodes" / "m2")
        self.assertEqual(loaded["metadata"]["execution_mode"], "normal")
        self.assertEqual(len(loaded["x"][0][0]), 6)
        self.assertEqual(audit_dataset(dataset)["issues"], [])
        language = describe_dataset(dataset, self.root / "language")
        self.assertEqual(language["descriptions"], 4)
        facts = json.loads((self.root / "language" / "facts" / "m2.json").read_text(encoding="utf-8"))
        self.assertEqual(facts["facts_version"], "observer_facts_fast_dynamics_v2")

    def test_timeout_is_retained_unknown_not_fake_success(self):
        result = run_mission(self.task, M2Config(execution=ExecutionConfig(max_duration_s=.03)))
        _, manifest = self.write(result)
        self.assertIsNone(manifest["mission_success"])
        self.assertFalse(manifest["episode_quality_eligible"])
        self.assertEqual(manifest["frames"], 1)

    def test_visible_facts_and_calibration_use_public_grid_not_dense_support(self):
        from swarm_sim import observer_facts_v0 as facts_module
        from swarm_sim.fast_dynamics.calibration import fast_summary

        run, _ = self.write()
        dataset = self.root / "dataset"
        build_dataset([run], dataset)
        episode = dataset / "episodes" / "m2"
        # This real export has both streams: ensure the test can distinguish
        # their cadence, then check the actual classifier inputs, not a flag.
        agents = json.loads((episode / "manifest.json").read_text(encoding="utf-8"))["agent_ids"]
        public = {channel: facts_module._traces(episode / name, agents)
                  for channel, name in (("truth", "truth.csv"), ("observation", "observations.csv"))}
        support = facts_module._traces(episode / "support_truth.csv", agents)
        self.assertGreater(len(support[agents[0]]), len(public["truth"][agents[0]]))
        times = [t for t, _ in public["truth"][agents[0]]]
        for i, t in enumerate(times):
            self.assertAlmostEqual(t, i / 10., places=9)
        with patch.object(facts_module, "_channel_facts", wraps=facts_module._channel_facts) as classify:
            facts = facts_module.extract_observer_facts(episode, file_hash(dataset / "dataset_manifest.json"))
            self.assertEqual([c.args[0] for c in classify.call_args_list], list(public.values()))
        self.assertEqual(facts["observed"]["observed_pattern"], "direct_passage")
        self.assertEqual(facts["provenance"]["versions"]["evidence_sampling"], "exported 10 Hz half-open grid")
        with patch.object(facts_module, "_channel_facts", wraps=facts_module._channel_facts) as classify:
            summary = fast_summary(run, "fixture")
            self.assertEqual([c.args[0] for c in classify.call_args_list], list(public.values()))
        self.assertEqual(summary["motion_slots"], {"truth": "direct_passage", "observation": "direct_passage"})

    def test_rehashed_false_label_is_recomputed_and_rejected(self):
        run, manifest = self.write()
        self.mutate(run, manifest, "labels.json", lambda obj: obj.update(mission_success=False))
        self.mutate(run, manifest, "semantic_validation.json", lambda obj: obj.update(mission_success=False))
        manifest["mission_success"] = False
        with self.assertRaises(ValueError):
            validate_episode(manifest, run / "analysis")

    def test_rehashed_wrong_planned_phases_is_rejected_even_on_reuse_hit(self):
        for reuse in (False, True):
            with self.subTest(reuse=reuse), adapter.reuse_semantics(enabled=reuse):
                run, manifest = self.write(name=f"tamper_{reuse}")
                self.mutate(run, manifest, "labels.json", lambda obj: obj["planned_phases"].append("fabricated"))
                with self.assertRaisesRegex(ValueError, "semantic claims"):
                    validate_episode(manifest, run / "analysis")

    def test_rehashed_missing_mode_or_confirmation_epoch_is_rejected(self):
        run, manifest = self.write()
        self.mutate(run, manifest, "source.json", lambda obj: obj.pop("execution_mode"))
        with self.assertRaisesRegex(ValueError, "execution mode"):
            validate_episode(manifest, run / "analysis")
        run, manifest = self.write(name="epoch")
        self.mutate(run, manifest, "events.json", lambda obj: obj["events"][0].pop("epoch"))
        with self.assertRaisesRegex(ValueError, "epoch"):
            validate_episode(manifest, run / "analysis")

    def test_rehashed_barrier_cannot_claim_a_revoked_confirmation(self):
        run, manifest = self.write()
        def revoke(obj):
            barrier = next(event for event in obj["events"] if event["event"] == "phase_completed")
            agent = next(iter(barrier["confirmed_epochs"]))
            barrier["confirmed_epochs"][agent] += 1
        self.mutate(run, manifest, "events.json", revoke)
        with self.assertRaisesRegex(ValueError, "barrier.*epochs"):
            validate_episode(manifest, run / "analysis")

    def test_m1_and_m2_cannot_silently_mix(self):
        first, _ = self.write()
        old = run_mission(self.task, FastDynamicsConfig())
        second, _ = self.write(old, name="legacy")
        with self.assertRaisesRegex(ValueError, "mixed|protocol"):
            build_dataset([first, second], self.root / "mixed")


if __name__ == "__main__":
    unittest.main()
