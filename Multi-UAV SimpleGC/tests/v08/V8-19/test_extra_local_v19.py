"""Real-input V8-19 failure propagation; deliberately rejected attempts are test-only diagnostics."""
import copy
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from v08.contract.monitoring import initial_states
from v08.contract.single_intent import close_observation_mission
from v08.motion import optimize_checks as OC
from v08.motion.optimize import load_settings
from v08.runner import joint_intent as JI
from v08.runner.close_observation_report import verify_saved_outputs
from v08.runner.monitoring import load_entries, write_json
from v08.sampler.common import sample_common
from v08.scene.context import load_context


class RealFailurePropagation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = ("V8_19_DATA_ROOT", "V8_19_DEVSET", "V8_19_CACHE", "V8_19_CHAIN_TEST_OUT")
        if not all(os.environ.get(k) for k in names):
            raise unittest.SkipTest("real-input V8-19 environment not supplied")
        cls.data_root, cls.devset, cls.cache, cls.out = (Path(os.environ[k]) for k in names)
        cls.out.mkdir(parents=True, exist_ok=False)

    def test_semantic_rejection_keeps_entered_flag_and_next_attempt(self):
        entry = next(e for e in load_entries(self.devset) if int(e["order"]) == 1)
        ctx = load_context(entry, data_root=self.data_root, cache_dir=self.cache)
        original = OC.check_close_observation
        calls = []
        def reject_first(*args, **kwargs):
            value = original(*args, **kwargs)
            calls.append({"original_passed": value["passed"], "injected": len(calls) == 0})
            if len(calls) == 1:
                value = copy.deepcopy(value)
                mid = sorted(value["nominal_members"])[0]
                value["passed"] = False
                value["nominal_members"][mid]["passed"] = False
                value["nominal_members"][mid]["conditions"]["no_revisit_window"] = False
                value["failures"].append({"kind": "nominal_revisit", "member": mid, "conditions": ["no_revisit_window"]})
            return value
        out = self.out / "injected_semantic_failure"
        with patch.object(OC, "check_close_observation", side_effect=reject_first):
            rec = JI.run_contract(ctx, entry, 0, intent="close_observation", settings=load_settings(), out_dir=out)
        self.assertTrue(rec["success"])
        self.assertGreaterEqual(rec["attempts"], 2)
        self.assertLessEqual(rec["attempts"], 20)
        self.assertEqual(rec["attempt_log"][0]["stage"], "optimize_close_observation")
        self.assertFalse(rec["attempt_log"][0]["ok"])
        self.assertIs(rec["attempt_log"][0]["optimization_entered"], True)
        self.assertEqual(rec["attempt_log"][1]["attempt"], 1)
        self.assertGreaterEqual(rec["post_optimization_failures"], 1)
        expected = sum(not a["ok"] and a["optimization_entered"] is True for a in rec["attempt_log"])
        self.assertEqual(rec["post_optimization_failures"], expected)
        skeleton = json.loads((out / "contracts/o01_d0/skeleton.json").read_text(encoding="utf-8"))
        self.assertEqual(skeleton["business_key"]["attempt"], rec["attempts"] - 1)
        write_json(out / "records.json", [JI.record_row(rec)], indent=1)
        verification = verify_saved_outputs(out, [entry], self.data_root, self.cache)
        self.assertTrue(verification["passed"])
        write_json(self.out / "injection.json", {"test_only": True, "calls": calls, "attempts": rec["attempts"],
            "post_failures": rec["post_optimization_failures"], "disk_verification": verification}, indent=1)


if __name__ == "__main__":
    unittest.main()
