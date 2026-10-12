"""New runtime contracts preserve source bundles, geometry and legacy inputs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_mission_list as runner
from swarm_sim.generation import generate, verify_generation
from swarm_sim.generation_v2 import normalize_profile
from swarm_sim.language_templates_v0 import generate_descriptions, validate_description
from swarm_sim.parallel_subset import tree_hashes
from swarm_sim.protocol import apply_execution_override, semantic_protocol, task_metadata, V061_SEMANTIC_VERSION
from swarm_sim.registry import component_versions
from swarm_sim.tasks import compile_task
from test_v06_data_contract import _v06_facts

PROJECT = Path(__file__).resolve().parents[1]


def source_scene():
    task = json.loads((PROJECT / "missions/v3/recon_route_v05.json").read_text(encoding="utf-8"))
    task["execution"].update(protocol_version="v0.6", final_hold_s=2., firmware_version_timeout_s=10.)
    task.update(flight_pattern="equal_strip_lawnmower",
                component_versions=component_versions("reconnaissance", "equal_strip_lawnmower"))
    return compile_task(task)


class TimeProtocolTests(unittest.TestCase):
    def test_override_changes_only_explicit_runtime_contract_and_is_reproducible(self):
        source = source_scene()
        original = copy.deepcopy(source)
        for speed in (1, 2, 4):
            runtime = apply_execution_override(source, dict(protocol_version="v0.6.1", sim_speedup=speed))
            self.assertEqual(source, original)
            self.assertEqual({k: v for k, v in runtime.items() if k != "task_spec"},
                             {k: v for k, v in source.items() if k != "task_spec"})
            self.assertEqual(compile_task(runtime["task_spec"]), runtime)
            self.assertEqual(semantic_protocol(runtime)["semantic_validation_version"], V061_SEMANTIC_VERSION)
            self.assertEqual(task_metadata(runtime["task_spec"])["time_base"], "sim_source")
            self.assertEqual(task_metadata(runtime["task_spec"])["sim_speedup"], speed)
        default = apply_execution_override(source, dict(protocol_version="v0.6.1"))
        self.assertEqual(default["task_spec"]["execution"]["sim_speedup"], 1)

    def test_invalid_speed_or_geometry_override_cannot_enter_new_contract(self):
        source = source_scene()
        for value in (0, -1, True, "2", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                apply_execution_override(source, dict(protocol_version="v0.6.1", sim_speedup=value))
        with self.assertRaises(ValueError):
            apply_execution_override(source, dict(protocol_version="v0.6.1", speed_m_s=9))
        task = copy.deepcopy(source["task_spec"])
        task["execution"]["sim_speedup"] = 2
        with self.assertRaisesRegex(ValueError, "requires explicit"):
            compile_task(task)

    def test_runner_freezes_override_in_ledger_without_rewriting_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = normalize_profile(PROJECT / "generation_profiles/tri_intent_v06_production.json")
            profile["base_scene_count"] = 1
            generate(profile, root / "bundle")
            listing, _ = verify_generation(root / "bundle/mission_list.json")
            hashes = tree_hashes(root / "bundle")
            for name in ("binary", "params"):
                (root / name).write_text("fixture", encoding="utf-8")
            def fake_run(scene, output, binary, parameters, base_port, policy, generation_context):
                self.assertEqual(scene["task_spec"]["execution"]["sim_speedup"], 2)
                self.assertEqual(generation_context["generation_entry"], listing["missions"][0])
                run = output / "failed_fixture"
                run.mkdir()
                return run, dict(status="failed"), dict(benchmark_eligible=False)
            args = dict(mission_list_path=root / "bundle/mission_list.json", output_root=root / "execution",
                        binary=root / "binary", parameters=root / "params", max_runs=1,
                        mission_ids=[listing["missions"][0]["mission_id"]],
                        execution_override=dict(protocol_version="v0.6.1", sim_speedup=2))
            with patch.object(runner, "run_scene", side_effect=fake_run) as run:
                ledger = runner.run_mission_list(**args)
                self.assertEqual(run.call_count, 1)
            self.assertEqual(ledger["execution_context"]["execution_override"], args["execution_override"])
            self.assertEqual(tree_hashes(root / "bundle"), hashes)
            args["execution_override"]["sim_speedup"] = 4
            with self.assertRaisesRegex(ValueError, "configuration changed"):
                runner.run_mission_list(**args, resume=True)

    def test_existing_wordings_are_reused_for_new_time_facts(self):
        for intent in ("reconnaissance", "patrol", "rapid_passage"):
            old = _v06_facts(intent)
            new = copy.deepcopy(old)
            new["facts_version"] = "observer_facts_v061"
            new["provenance"]["versions"]["semantic_validation_version"] = V061_SEMANTIC_VERSION
            a = generate_descriptions(old, intent, "validation", 11)
            b = generate_descriptions(new, intent, "validation", 11)
            self.assertEqual([d["text"] for d in a], [d["text"] for d in b])
            self.assertTrue(all(validate_description(d, new)[0] for d in b))


if __name__ == "__main__":
    unittest.main()
