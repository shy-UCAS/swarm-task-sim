"""The revision clearance is explicit; old callers retain the 200m default."""
from copy import deepcopy
import unittest

from task_v07.expansion.geometry_checks import check_retreat_point
from task_v07.expansion.pipeline import role_parameters
from task_v07.unified.config import load_generator
from test_v07_s2_expansion import scene


class RevisionRetreatTests(unittest.TestCase):
    def test_hundred_metre_boundary_and_legacy_default(self):
        target = scene()
        self.assertTrue(check_retreat_point(target, [2800., 2000.], warning_clearance_m=100.)['valid'])
        self.assertFalse(check_retreat_point(target, [2799.99, 2000.], warning_clearance_m=100.)['valid'])
        self.assertFalse(check_retreat_point(target, [2800., 2000.])['valid'])
        self.assertTrue(check_retreat_point(target, [2900., 2000.])['valid'])

    def test_other_warnings_and_obstacle_margin_still_apply(self):
        target = scene()
        target['entities'].append({'id': 'other_warning', 'type': 'protection_zone', 'layer': 'warning',
                                   'geometry': {'type': 'Circle', 'center_m': [2900., 2000.], 'radius_m': 25.}})
        self.assertFalse(check_retreat_point(target, [2800., 2000.], warning_clearance_m=100.)['valid'])
        target = scene()
        target['entities'].append({'id': 'restriction', 'type': 'hard_constraint_obstacle',
                                   'geometry': {'type': 'Circle', 'center_m': [2859.99, 2000.], 'radius_m': 25.}})
        self.assertFalse(check_retreat_point(target, [2800., 2000.], warning_clearance_m=100.)['valid'])

    def test_expanded_request_selects_minimum_without_mutating_descriptor(self):
        descriptor = {'skeleton_id': 'family_ext_001_regular', 'column_seed': 1, 'role_seed': 2,
                      'family_conditions': {'sampling_seed': 3}, 'cruise_speed_m_s': 5., 'task_altitude_m': 100.,
                      'common_draw': {'approach_mode': 'same_direction'}}
        original = deepcopy(descriptor)
        parameters = role_parameters(descriptor, {'group_id': 'g'})
        self.assertEqual(parameters['retreat_warning_minimum_m'],
                         load_generator()['retreat']['warning_clearance_m'])
        self.assertEqual(descriptor, original)


if __name__ == '__main__':
    unittest.main()
