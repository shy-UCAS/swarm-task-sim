"""Real bundle copies and frozen assignments; no SITL or archived-data writes."""
import copy
import os
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from swarm_sim import parallel_batch as batch
from swarm_sim import parallel_subset as subset
from swarm_sim.generation import file_hash, generate, verify_generation
from test_parallel_batch import small_profile


class ParallelSubsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_temp = tempfile.TemporaryDirectory()
        cls.source = Path(cls.source_temp.name).resolve() / "bundle"
        generate(small_profile(4), cls.source)
        (cls.source / "unregistered.txt").write_bytes(b"all files, not just JSON\r\n")
        cls.listing, _ = verify_generation(cls.source / "mission_list.json")
        families = list(dict.fromkeys(e["family_id"] for e in cls.listing["missions"]))
        cls.ids = [e["mission_id"] for e in cls.listing["missions"] if e["family_id"] in families[1:3]]
        cls.hashes = subset.tree_hashes(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.source_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name).resolve()
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, SIM_DATA_ROOT=str(self.data)))
        stack.enter_context(patch.object(batch, "verify_preflight_files", return_value={"actual": {}}))
        stack.enter_context(patch.object(batch, "_protected_files", return_value={}))
        self.probe = stack.enter_context(patch.object(batch, "probe_ports"))

    def prepare(self, ids=None, **options):
        return subset.prepare_subset(self.source, self.ids if ids is None else ids, "pilot",
            shards=4, max_attempts=8, storage_bytes_per_attempt=1, export_reserve_bytes=1, **options)

    def test_import_all_bytes_without_generation_and_keep_exact_source_tasks(self):
        with patch.object(batch, "generate", side_effect=AssertionError("must not regenerate")):
            plan = self.prepare(list(reversed(self.ids)))
        self.assertEqual(subset.tree_hashes(plan["bundle"]), self.hashes)
        self.assertEqual(subset.tree_hashes(self.source), self.hashes)
        self.assertEqual(plan["subset"]["source_bundle_sha256"], self.hashes)
        source_tasks = batch.assign_tasks(self.listing, self.source, 2)
        self.assertEqual([t["global_index"] for t in plan["tasks"]], list(range(4)))
        self.assertEqual(plan["subset"]["source_global_indices"], [t["global_index"] for t in source_tasks
                                                                  if t["mission_id"] in self.ids])
        for task, original in zip(plan["tasks"], [t for t in source_tasks if t["mission_id"] in self.ids]):
            for field in ("mission_id", "family_id", "seed", "split", "entry"):
                self.assertEqual(task[field], original[field])
        self.assertEqual(plan["purpose"], "pilot")
        self.assertIs(plan["training_data"], False)
        self.assertEqual(batch.read(Path(plan["root"]) / "control.json")["attempts"], [])
        self.assertEqual(plan["ports"][-1]["end_port"], 19499)
        self.probe.assert_called_once_with(plan["ports"])
        batch.integrity(plan)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.prepare()

    def test_invalid_or_partial_selection_rejected_before_creating_batch(self):
        for ids in ([], [self.ids[0]], self.ids + [self.ids[0]], ["unknown"], "all", [None]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.prepare(ids)
            self.assertFalse((self.data / "parallel_batch/pilot").exists())

    def test_custom_ports_are_frozen_probed_and_rechecked_on_load(self):
        plan = self.prepare(base_port=20100)
        self.assertEqual(plan["base_port"], 20100)
        self.assertEqual(plan["ports"], batch.port_blocks(4, 1, 20100))
        self.probe.assert_called_once_with(plan["ports"])
        batch.integrity(plan)
        self.assertEqual(subset.tree_hashes(plan["bundle"]), self.hashes)
        plan["ports"][0]["base_port"] = 19100
        root = Path(plan["root"])
        batch.save_atomic(root / "plan.json", plan)
        (root / "plan.sha256").write_text(file_hash(root / "plan.json"), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "port blocks"):
            batch.load_plan(root)

    def test_production_default_and_custom_port_plans_keep_identical_tasks(self):
        plans = [batch.prepare(small_profile(2), name, shards=4, max_attempts=8,
                              storage_bytes_per_attempt=1, export_reserve_bytes=1, **options)
                 for name, options in (("default", {}), ("custom", {"base_port": 20100}))]
        self.assertNotIn("base_port", plans[0])
        self.assertEqual(plans[0]["ports"], batch.port_blocks(4, 1))
        self.assertEqual(plans[1]["base_port"], 20100)
        self.assertEqual(plans[1]["ports"], batch.port_blocks(4, 1, 20100))
        self.assertEqual(plans[0]["tasks"], plans[1]["tasks"])
        self.assertEqual(subset.tree_hashes(plans[0]["bundle"]), subset.tree_hashes(plans[1]["bundle"]))
        for plan in plans:
            batch.integrity(plan)

    def test_changed_non_json_imported_file_is_rejected(self):
        plan = self.prepare()
        (Path(plan["bundle"]) / "unregistered.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "hash changed"):
            batch.integrity(plan)
        self.assertEqual(subset.tree_hashes(self.source), self.hashes)

    def test_added_imported_file_is_rejected(self):
        plan = self.prepare()
        (Path(plan["bundle"]) / "extra.txt").write_text("added")
        with self.assertRaisesRegex(ValueError, "file set or hash changed"):
            batch.integrity(plan)

    def test_pilot_and_non_training_markers_are_required(self):
        plan = self.prepare()
        for field, value in (("purpose", "production"), ("training_data", True)):
            changed = copy.deepcopy(plan)
            changed[field] = value
            with self.assertRaisesRegex(ValueError, "pilot and non-training"):
                subset.verify_subset(changed, self.listing)

    def test_audit_scope_excludes_unselected_families_and_does_not_modify_bundle(self):
        plan = self.prepare()
        derived = batch.read(subset.audit_manifest(plan))
        self.assertEqual({b["family_id"] for b in derived["bases"]},
                         {t["family_id"] for t in plan["tasks"]})
        self.assertEqual(derived["counts"], {"base_scenes": 2})
        self.assertEqual(subset.tree_hashes(plan["bundle"]), self.hashes)
        ordinary = {"bundle": plan["bundle"]}
        self.assertEqual(subset.audit_manifest(ordinary), Path(plan["bundle"]) / "generation_manifest.json")

    def test_production_prepare_still_generates_entire_list_and_uses_original_contract(self):
        with patch.object(subset, "select_listing", side_effect=AssertionError("production must not select")), \
                patch.object(batch, "generate", wraps=batch.generate) as generator:
            plan = batch.prepare(small_profile(4), "production", shards=2, max_attempts=16,
                                 storage_bytes_per_attempt=1, export_reserve_bytes=1)
            batch.integrity(plan)
        generator.assert_called_once()
        self.assertEqual(len(plan["tasks"]), 8)
        self.assertNotIn("subset", plan)
        self.assertNotIn("purpose", plan)
        self.assertNotIn("training_data", plan)
        listing, _ = verify_generation(Path(plan["bundle"]) / "mission_list.json")
        self.assertEqual(plan["tasks"], batch.assign_tasks(listing, plan["bundle"], 2))


if __name__ == "__main__":
    unittest.main()
