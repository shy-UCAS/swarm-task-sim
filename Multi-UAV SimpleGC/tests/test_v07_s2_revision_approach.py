"""Known-answer checks for warning-entry measurement and separate deployment."""
import math
import unittest
import numpy as np

from task_v07.labels import approach_heading_deg, heading_span_deg, measure
from task_v07.geometry import geometry_facts
from task_v07.expansion.pipeline import COMMON_CONSTANTS, exclusion_policy
from task_v07.expansion.formation_role_planners import Context
from task_v07.expansion.warning_approach import warning_ingress, deploy_inside_warning
from task_v07.expansion.area_search import planned_core_distance, heading_before_distance
from scripts.audit_v07_s2_roles import _approach_heading_deg, _heading_span_deg
from test_v07_s2_expansion import scene


class WarningApproachMeasurementTests(unittest.TestCase):
    def test_exact_hundred_metres_interpolates_the_backtrack_endpoint(self):
        # The last 100m contain 20m east and 80m north, not the full 60m leg.
        xy = np.array([[0., 0.], [60., 0.], [60., 80.]])
        expected = math.degrees(math.atan2(80., 20.))
        self.assertAlmostEqual(approach_heading_deg(xy, 2), expected, places=12)
        self.assertAlmostEqual(_approach_heading_deg(xy, 2), expected, places=12)

    def test_missing_member_makes_whole_group_span_unknown(self):
        self.assertIsNone(heading_span_deg([0., 180., None]))
        self.assertIsNone(_heading_span_deg([0., 180., None]))
        self.assertAlmostEqual(heading_span_deg([350., 10., 100.]), 110.)

    def test_insufficient_observed_path_is_unknown(self):
        xy = np.array([[0., 0.], [20., 0.]])
        for helper in (approach_heading_deg, _approach_heading_deg):
            self.assertIsNone(helper(xy, 1))
            self.assertIsNone(helper(xy, None))

    def build_tracks(self, missing=False):
        # Both enter the warning boundary from the east, then spread inside it.
        # Their later protected-zone core headings differ; those must not be used.
        paths = {'a': [[3000., 2010.], [2600., 2010.], [2050., 2090.]],
                 'b': [[3000., 1990.], [2600., 1990.], [2050., 1910.]]}
        if missing:
            paths['c'] = [[3100., 2100.], [3100., 2110.]]
        ids = sorted(paths)
        distance = np.arange(2401) * .5
        p = np.zeros((len(distance), len(ids), 3))
        for i, agent in enumerate(ids):
            points = np.asarray(paths[agent])
            cumulative = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
            for axis in range(2):
                p[:, i, axis] = np.interp(distance, cumulative, points[:, axis])
        p[:, :, 2] = 100.
        v = np.gradient(p, .1, axis=0)
        sk = {**COMMON_CONSTANTS, 'base_intent': 'penetration', 'role': 'intrusion',
              'execution_method': 'intrusion', 'target_id': 'f', 'group_id': 'g',
              'members': ids, 'agent_ids': ids, 'approach_mode': 'multi_direction',
              'required_intrusion_depth_m': 20., 'cruise_speed_m_s': 5.,
              'exclusion_policy': exclusion_policy(scene(), 'intrusion', 'f', ids),
              'references': {a: {'endpoint_enu_m': p[-1, i].tolist(), 'retreat_required': False}
                             for i, a in enumerate(ids)}}
        run = {'agent_ids': ids, 'time_us': np.arange(len(p), dtype=np.int64)*100000,
               'p': p, 'v': v, 'execution_status': 'completed'}
        return sk, run

    def test_warning_entry_is_separate_from_role_core_event(self):
        sk, run = self.build_tracks()
        labels, _ = measure(scene(), sk, run, 'synchronous')
        group = labels['task_groups']['g']
        self.assertAlmostEqual(group['observed']['approach_span_deg'], 0., places=10)
        self.assertFalse(group['result']['conditions']['multi_direction_span'])
        for agent in run['agent_ids']:
            observed = labels['agents'][agent]['observed']
            self.assertEqual(observed['core_event']['raw_event_type'], 'enter_protected_zone')
            self.assertGreater(observed['core_event']['t_s'], observed['regions_by_facility']['f']['warning']['first_entry_s'])

    def test_one_missing_warning_entry_does_not_use_known_subset(self):
        sk, run = self.build_tracks(missing=True)
        labels, _ = measure(scene(), sk, run, 'synchronous', cutoff_s=150.)
        group = labels['task_groups']['g']
        self.assertIsNone(group['observed']['approach_headings_deg']['c'])
        self.assertIsNone(group['observed']['approach_span_deg'])
        self.assertIsNone(group['result']['conditions']['multi_direction_span'])


class WarningIngressGeometryTests(unittest.TestCase):
    def test_same_side_corridor_precedes_free_deployment(self):
        ids = ['a', 'b', 'c']
        family = {'sampling_seed': 41, 'cruise_speed_m_s': 5., 'task_altitude_m': 100.,
                  'lateral_spacing_m': 20., 'initial_states': [
                      {'agent_id': a, 'position_enu_m': [60., 1980.+20*i, 100.]}
                      for i, a in enumerate(ids)]}
        group = {'role': 'monitoring', 'target_id': 'f', 'members': ids}
        ctx = Context(scene(), group, {'family': family, 'approach_mode': 'same_direction',
                                      'planning_seed': 10, 'geometry_slot': 0})
        ingress, reason = warning_ingress(ctx, math.pi)
        self.assertIsNotNone(ingress, reason)
        headings = []
        for path in ingress['routes'].values():
            points = np.asarray(path)
            entry = planned_core_distance(points, ctx.zones['warning']['geometry'])
            headings.append(heading_before_distance(points, entry))
            self.assertLess(float(geometry_facts(ctx.zones['warning']['geometry'], points[-1])['signed_distance_m']), 0.)
        self.assertLess(heading_span_deg(headings), 1e-8)
        for block in ingress['blocks']:
            self.assertEqual(block['shared_route_margin_m'], 35.+1.5*block['half_width_m']+2.)
        path = deploy_inside_warning(ctx, ingress['routes']['a'][-1], np.array([2000., 2500.]))
        self.assertIsNotNone(path)
        self.assertTrue(ctx.route_valid(path))
        self.assertTrue(np.all(geometry_facts(ctx.zones['warning']['geometry'], np.asarray(path))['signed_distance_m'] <= 1e-6))


if __name__ == '__main__':
    unittest.main()
