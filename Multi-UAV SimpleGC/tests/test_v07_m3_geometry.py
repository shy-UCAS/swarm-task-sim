"""M3a G1-G6/G8/G10: geometry is a prefilter, not a replacement for M1."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from v07_m3_fixtures import request
from task_v07.expansion.contracts import P0ContractError
from task_v07.unified.spec import build_spec, validate_spec, proposal_seed


class SpecTests(unittest.TestCase):
    def test_G1_spec_without_geometry_or_execution(self):
        scene, descriptor, group = request()
        with patch("task_v07.geometry.geometry_facts", side_effect=AssertionError("geometry called")), \
             patch("task_v07.execution.execute", side_effect=AssertionError("execution called")):
            spec = build_spec(descriptor, group)
            self.assertEqual(spec, build_spec(descriptor, group))
            self.assertEqual(validate_spec(spec, descriptor, group), spec)
        self.assertNotIn("initial_states", spec)
        self.assertNotIn("references", spec)
        for field, value in (("target_id", "changed"), ("members", ["other"]), ("geometry_seed", 0)):
            changed = deepcopy(spec); changed[field] = value
            with self.assertRaises(P0ContractError):
                validate_spec(changed, descriptor, group)
        self.assertNotEqual(proposal_seed(spec, 0), proposal_seed(spec, 1))

    def test_G1_registered_group_not_reassigned(self):
        _, descriptor, group = request()
        other = {**group, "target_id": "another"}
        with self.assertRaises(P0ContractError):
            build_spec(descriptor, other)

    def test_G2_column_permutation_does_not_change_spec(self):
        _, descriptor, group = request(multi=True)
        changed = deepcopy(descriptor)
        changed["agent_ids"] = list(reversed(changed["agent_ids"]))
        changed["column_seed"] += 1
        self.assertEqual(build_spec(descriptor, group), build_spec(changed, changed["task_groups"][0]))


if __name__ == "__main__":
    unittest.main()
