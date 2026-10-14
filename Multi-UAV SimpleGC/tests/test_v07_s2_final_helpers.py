"""Known-answer cross-template correspondence and final view exclusions."""
from copy import deepcopy
import unittest

from scripts.evaluate_v07_s2_cross import corresponding_groups
from scripts.v07_s2_final_reporting import final_views
from test_v07_s2_infrastructure import successful_record


def template(groups):
    return {'group_skeletons': {gid: {'members': members, 'agent_ids': list(reversed(members)),
            'references': {a: {'marker': a} for a in members},
            'exclusion_policy': {a: {} for a in members}} for gid, members in groups.items()}}


class FinalHelperTests(unittest.TestCase):
    def test_all_missing_skeletons_keep_exact_960_not_run_items(self):
        from unittest.mock import patch
        from pathlib import Path
        from scripts.evaluate_v07_s2_cross import cross_report
        from task_v07.expansion.sampling import INTENTS
        descriptors=[{'skeleton_id':f'f{family}_s{slot}_{intent}','family_id':f'f{family}',
                      'common_draw':{'slot':slot},'base_intent':intent,'subset':'regular'}
                     for family in range(6) for slot in range(2) for intent in INTENTS]
        def load(path):
            return descriptors if Path(path).name=='private_skeleton_descriptors.json' else []
        with patch('scripts.evaluate_v07_s2_cross.read_json',side_effect=load):
            result=cross_report(Path('unused'))
        self.assertEqual(result['expected_items'],960)
        self.assertEqual(result['counts'],{'PASS':0,'FAIL':0,'not_run':960})
        self.assertEqual(result['status'],'INCOMPLETE')

    def test_abort_view_requires_observed_withdrawal(self):
        base = successful_record('f', 'penetration', 0, 'synchronous')
        rows = [{**base, 'episode_id': 'abort_good', 'aborted': True, 'task_result': 'failure', 'abort_observation_valid': True},
                {**base, 'episode_id': 'abort_bad', 'aborted': True, 'task_result': 'failure', 'abort_observation_valid': False}]
        views = final_views(rows)['views']
        self.assertEqual([r['episode_id'] for r in views['aborted']], ['abort_good'])
        self.assertEqual([r['episode_id'] for r in views['failed']], ['abort_bad'])

    def test_member_identity_takes_precedence_over_group_name(self):
        a = template({'g1': ['a', 'b'], 'g2': ['c', 'd']})
        b = template({'g1': ['c', 'd'], 'g2': ['a', 'b']})
        rows = corresponding_groups(a, b)
        self.assertEqual([(r['template_group_id'], r['trajectory_group_id']) for r in rows], [('g1', 'g2'), ('g2', 'g1')])
        self.assertTrue(all(r['membership_match'] == 'exact' for r in rows))

    def test_partial_members_are_intersected_and_not_silently_merged(self):
        a = template({'g1': ['a', 'b'], 'g2': ['c', 'd']})
        b = template({'h1': ['a', 'c'], 'h2': ['b', 'd']})
        saved = deepcopy(a)
        rows = corresponding_groups(a, b)
        self.assertEqual(len(rows), 4)
        self.assertEqual(a, saved)
        for row in rows:
            self.assertEqual(len(row['evaluated_members']), 1)
            self.assertEqual(row['membership_match'], 'intersection')
            self.assertEqual(set(row['parameters']['references']), set(row['evaluated_members']))

    def test_rejects_errors_and_diagnostics_never_enter_training_views(self):
        base = successful_record('f', 'transit', 0, 'synchronous')
        records = [{**base, 'episode_id': 'valid'},
                   {**base, 'episode_id': 'failed', 'skeleton_id': 'fail', 'task_result': 'failure'},
                   {**base, 'episode_id': 'reject', 'state': 'infeasible', 'path': None, 'task_result': None},
                   {**base, 'episode_id': 'error', 'state': 'generation_error', 'quality_valid': False},
                   {**base, 'episode_id': 'abort_error', 'state': 'generation_error', 'quality_valid': False, 'aborted': True},
                   {**base, 'episode_id': 'diagnostic', 'diagnostic_only': True}]
        report = final_views(records)
        self.assertEqual({r['episode_id'] for rows in report['views'].values() for r in rows}, {'valid', 'failed'})
        self.assertEqual(report['counts']['failed'], 1)
        self.assertEqual(report['exclusion_counts']['planning_rejections'], 1)
        self.assertEqual(report['exclusion_counts']['generation_errors'], 2)


if __name__ == '__main__':
    unittest.main()
