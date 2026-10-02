"""Offline checks for the v05c-v05b equivalence comparator."""

import copy
import unittest

from scripts.review_v05c_dr import (candidate_without_derived,
    entry_without_derived, sampled_without_heading, without_heading_and_family)


class V05CEquivalenceTests(unittest.TestCase):
    def test_heading_policy_and_headings_are_the_only_ignored_sampling_fields(self):
        before = dict(region_width_m=30.0, entry_side="east",
            sampler_params=dict(line_spacing_m=[8, 12]),
            spatial_slots=[dict(id="uav_01", east_m=1.0, heading_deg=71.6)])
        after = copy.deepcopy(before)
        after["sampler_params"]["heading_policy"] = "fixed_zero"
        after["spatial_slots"][0]["heading_deg"] = 0.0
        self.assertEqual(sampled_without_heading(before), sampled_without_heading(after))
        after["spatial_slots"][0]["east_m"] = 2.0
        self.assertNotEqual(sampled_without_heading(before), sampled_without_heading(after))

    def test_candidate_sequence_and_planning_status_remain_strict(self):
        before = dict(candidate_id="base_0000_candidate_00", base_index=0,
            candidate_index=0, scene_seed=42, status="accepted", family_id="old",
            scene_content_sha256="old_hash", shared_mission_params=dict(speed_m_s=2.0),
            sampled_parameters=dict(sampler_params={}, spatial_slots=[
                dict(id="uav_01", east_m=1.0, heading_deg=81.2)]),
            attempts=[dict(intent="patrol", status="planned", task_seed=7,
                           task_sha256="old_task_hash")])
        after = copy.deepcopy(before)
        after.update(family_id="new", scene_content_sha256="new_hash")
        after["sampled_parameters"]["spatial_slots"][0]["heading_deg"] = 0
        after["sampled_parameters"]["sampler_params"]["heading_policy"] = "fixed_zero"
        after["attempts"][0]["task_sha256"] = "new_task_hash"
        self.assertEqual(candidate_without_derived(before), candidate_without_derived(after))
        after["attempts"][0]["status"] = "planning_rejected"
        self.assertNotEqual(candidate_without_derived(before), candidate_without_derived(after))

    def test_family_hash_changes_do_not_hide_route_changes(self):
        before = dict(family_id="old", base_scene_id="old", scene_sha256="old",
            sampled_parameters=dict(sampler_params={}, spatial_slots=[
                dict(id="uav_01", heading_deg=60, east_m=0)]),
            mission_id="patrol_0000_v00", task_seed=123)
        after = copy.deepcopy(before)
        after.update(family_id="new", base_scene_id="new", scene_sha256="new")
        after["sampled_parameters"]["spatial_slots"][0]["heading_deg"] = 0
        after["sampled_parameters"]["sampler_params"]["heading_policy"] = "fixed_zero"
        self.assertEqual(entry_without_derived(before), entry_without_derived(after))
        plan_before = dict(family_id="old", vehicles=[dict(heading_deg=60, east_m=0)],
                           planning=dict(route=[1, 2, 3]))
        plan_after = copy.deepcopy(plan_before)
        plan_after["family_id"] = "new"
        plan_after["vehicles"][0]["heading_deg"] = 0
        self.assertEqual(without_heading_and_family(plan_before),
                         without_heading_and_family(plan_after))
        plan_after["planning"]["route"][1] = 99
        self.assertNotEqual(without_heading_and_family(plan_before),
                            without_heading_and_family(plan_after))


if __name__ == "__main__":
    unittest.main()
