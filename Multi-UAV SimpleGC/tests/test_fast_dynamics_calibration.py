import copy
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from swarm_sim.fast_dynamics.calibration import (
    SPLIT_ID, SPLIT_SEED, aggregate_pairs, agreement, interpolate_positions, minimum_separation,
    pair_lateral, partition_families, phase_durations, position_speeds,
    reference_summary, route_diagnostics, tuning_tasks,
)
from swarm_sim.time_contract import CommonTimeAxis


class CalibrationTests(unittest.TestCase):
    def test_family_split_is_fixed_and_order_duplicate_invariant(self):
        families = [f"f{i:03d}" for i in range(300)]
        development = families[:14]
        a = partition_families(families, development)
        b = partition_families(families[::-1] * 2, development[::-1])
        self.assertEqual(a, b)
        self.assertEqual({k: len(v) for k, v in a.items()},
                         dict(development_reference=14, tuning=200, internal_holdout=86))
        self.assertFalse(set(a['tuning']) & set(a['internal_holdout']))
        self.assertFalse(set(development) & set(a['tuning']))

    def test_clock_inverse_uses_knots_not_global_scale(self):
        axis = CommonTimeAxis({'uav_01': dict(available=True, knots=[[-1., -2.], [0., 0.], [2., 4.], [4., 5.]])})
        self.assertEqual([axis.host(t) for t in (0., 2., 4., 4.5, 5.)], [0., 1., 2., 3., 4.])
        self.assertIsNone(axis.host(5.01))

    def test_clock_natural_order_and_invalid_fallback(self):
        model = dict(available=True, knots=[[-1., -1.], [10., 10.]])
        axis = CommonTimeAxis({'uav_10': model, 'uav_2': model, 'uav_1': dict(available=False)})
        self.assertEqual(axis.reference_agent_id, 'uav_2')
        self.assertEqual(axis.metadata['rejected_reference_candidates'], ['uav_1'])

    def test_holdout_gate_rejects_before_any_file_open(self):
        split = dict(split_id=SPLIT_ID, seed=SPLIT_SEED, groups=dict(tuning=['a'], internal_holdout=['b'], development_reference=[]),
                     tasks=[dict(family_id='a',mission_id='a',group='tuning')])
        row = dict(task=dict(family_id='b',mission_id='b'),status='ELIGIBLE',attempt={})
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(ValueError, 'only eligible tuning'):
                reference_summary(row,split,Path('unused'))

    def test_m2_02b_split_rejected(self):
        with self.assertRaisesRegex(ValueError, 'M2-02B'):
            tuning_tasks(dict(split_id='split_2026101202_m2_02b_v1',seed=SPLIT_SEED))

    def test_unknown_is_not_agreement(self):
        self.assertIsNone(agreement(None,None))
        self.assertIsNone(agreement('unclear','unclear',unclear_unknown=True))
        self.assertTrue(agreement(False,False))
        self.assertFalse(agreement(True,False))

    def test_interpolation_respects_missing_and_gaps(self):
        rows=[(0.,[0,0,0]),(.1,None),(.2,[.2,0,0]),(1.,[1,0,0])]
        result=interpolate_positions(rows,[0.,.05,.1,.5,2.])
        self.assertEqual(result[0].tolist(),[0.,0.,0.])
        self.assertTrue(np.isnan(result[1:]).all())

    def test_speed_from_positions_and_mapped_seconds(self):
        rows=[(i/10,[2*i/10,0,8]) for i in range(31)]
        self.assertTrue(np.allclose(position_speeds(rows,[.5,1.,2.5]),[2,2,2]))
        self.assertTrue(math.isnan(position_speeds(rows,[.1])[0]))

    def test_speed_does_not_bridge_internal_missing_point(self):
        rows=[(i/10,[i/10,0,8]) for i in range(21)]
        rows[10]=(1.,None)
        self.assertTrue(math.isnan(position_speeds(rows,[1.])[0]))

    def test_synchronous_minimum_detects_between_samples(self):
        traces={'a':[(0,[-1,0,0]),(.5,[1,0,0])], 'b':[(0,[0,1,0]),(.5,[0,-1,0])]}
        self.assertAlmostEqual(minimum_separation(traces)['minimum_m'],0.)

    def test_synchronous_minimum_does_not_align_individual_progress(self):
        traces={'a':[(0,[0,0,0]),(.5,[1,0,0])], 'b':[(0,[3,0,0]),(.5,[4,0,0])]}
        self.assertAlmostEqual(minimum_separation(traces)['minimum_m'],3.)

    def test_synchronous_minimum_does_not_bridge_long_gap(self):
        traces={'a':[(0,[-1,0,0]),(2,[1,0,0])], 'b':[(0,[0,1,0]),(2,[0,-1,0])]}
        self.assertIsNone(minimum_separation(traces)['minimum_m'])
        self.assertEqual(minimum_separation(traces)['valid_pair_intervals'],0)

    def test_empty_speed_support_is_unavailable(self):
        self.assertTrue(np.isnan(position_speeds([], [1.,2.])).all())

    def test_same_leg_arc_alignment_known_lateral_offset(self):
        a=dict(planned_length_m=10.,routes={'p|a':dict(legs=[dict(index=0,length_m=10.,along_m=[0,10],lateral_m=[0,0])])})
        b=copy.deepcopy(a)
        b['routes']['p|a']['legs'][0]['lateral_m']=[.4,.4]
        value=pair_lateral(a,b)
        self.assertAlmostEqual(value['median'],.4)
        self.assertEqual(value['matched_fraction'],1.)
        b['routes']['p|a']['legs'][0]['index']=1
        self.assertEqual(pair_lateral(a,b)['n'],0)

    def test_later_loop_not_matched_to_previous_leg(self):
        a=dict(planned_length_m=20.,routes={'patrol|a':dict(legs=[dict(index=4,length_m=10.,along_m=[0,10],lateral_m=[0,0])])})
        b=copy.deepcopy(a)
        b['routes']['patrol|a']['legs'][0]['index']=0
        self.assertEqual(pair_lateral(a,b)['matched_fraction'],0)

    def test_phase_duration_uses_barrier_and_reports_missing(self):
        rows=[dict(phase='p',phase_release_s=1,start_s=1.1,end_s=5),
              dict(phase='p',phase_release_s=1,start_s=1.2,end_s=6)]
        self.assertEqual(phase_durations(rows),{'p':5})
        rows[1]['end_s']=None
        self.assertEqual(phase_durations(rows),{'p':None})

    def test_route_extraction_preserves_two_laps_and_native_numbers(self):
        point=lambda x,y: dict(east_m=x,north_m=y,up_m=8.)
        targets=[point(x,y) for _ in range(2) for x,y in ((10.,0.),(10.,10.),(0.,10.),(0.,0.))]
        scene=dict(max_gap_s=.5,phases=[dict(name='p',semantic_phase='patrol',speed_m_s=1.,routes={'a':targets})],
                   semantic_plan=dict(execution_phases={'p':dict(agents={'a':dict(start_point=point(0.,0.))})}))
        rows=[]
        points=[(0.,0.),*[(p['east_m'],p['north_m']) for p in targets]]
        for leg,(a,b) in enumerate(zip(points,points[1:])):
            for i in range(100):
                rows.append((leg*10.+i/10,[a[0]+i/100*(b[0]-a[0]),a[1]+i/100*(b[1]-a[1]),8.]))
        rows.append((80.,[0.,0.,8.]))
        value=route_diagnostics(scene,{'a':rows},[dict(phase='p',agent_id='a',start_s=0.,end_s=80.)])
        route=value['routes']['p|a']
        self.assertEqual(route['matched_nodes'],8)
        self.assertEqual(route['laps_observed'],2)
        self.assertEqual([r['index'] for r in route['legs']],list(range(8)))
        self.assertAlmostEqual(value['cruise_speed']['median'],1.)

    def test_aggregation_does_not_treat_unknown_or_frames_as_success(self):
        row=dict(family_id='a',success_agreement=True,observation_success_agreement=True,candidate_quality=True,
            motion_slots={c:dict(agree=True,reference='parallel_strips',candidate='parallel_strips') for c in ('truth','observation')},duration_relative_error=.1,
            lateral_m=dict(p95=.2,matched_fraction=.9),truth_minimum_separation_difference_m=.3,
            phase_duration_relative_error={'p':.1},cruise_speed_m_s=[3.,3.1],turn_minimum_speed_m_s=[1.,.5],
            condition_pairs={c:dict(coverage=dict(agree=True)) for c in ('truth','observation')})
        b=copy.deepcopy(row)
        b.update(family_id='b',success_agreement=None)
        b['motion_slots']={c:dict(agree=None,reference='parallel_strips',candidate='unclear') for c in ('truth','observation')}
        b['phase_duration_relative_error']={}
        b['condition_pairs']={c:{} for c in ('truth','observation')}
        value=aggregate_pairs([row,copy.deepcopy(row),b])
        self.assertEqual(value['success']['agree'],2)
        self.assertEqual(value['success']['unknown'],1)
        self.assertEqual(value['success']['all_task_rate'],2/3)
        self.assertEqual(value['duration_relative_error']['task']['n'],3)
        self.assertEqual(value['duration_relative_error']['family_median']['n'],2)
        self.assertEqual(value['conditions']['truth']['coverage']['total'],2)
        self.assertEqual(value['conditions']['truth']['coverage']['not_applicable'],1)
        self.assertEqual(value['motion_reference_known']['truth']['total'],3)
        self.assertEqual(value['motion_reference_known']['truth']['all_task_rate'],2/3)
        self.assertEqual(value['phase_absolute_relative_error']['p']['missing'],0)
        self.assertEqual(value['phase_absolute_relative_error']['p']['not_applicable'],1)

    def test_half_open_last_phase_is_measured_on_recorded_support(self):
        point=lambda x: dict(east_m=float(x),north_m=0.,up_m=8.)
        scene=dict(max_gap_s=.5,phases=[dict(name='p',semantic_phase='transit',speed_m_s=1.,routes={'a':[point(10)]})],
            semantic_plan=dict(execution_phases={'p':dict(agents={'a':dict(start_point=point(0))})}))
        rows=[(i/10,[i/10,0.,8.]) for i in range(101)]
        windows=[dict(phase='p',agent_id='a',start_s=0.,end_s=10.1)]
        before=copy.deepcopy(windows)
        value=route_diagnostics(scene,{'a':rows},windows)['routes']['p|a']
        self.assertEqual(value['matched_nodes'],1)
        self.assertEqual(value['recorded_domain_s'],[0.,10.])
        self.assertAlmostEqual(value['unrecorded_boundary_s'][1],.1)
        self.assertEqual(windows,before)
        windows[0]['end_s']=11.
        value=route_diagnostics(scene,{'a':rows},windows)['routes']['p|a']
        self.assertEqual(value['issues'],['unsupported_phase_boundary_gap'])
        self.assertEqual(value['matched_length_m'],0.)


if __name__=='__main__':
    unittest.main()
