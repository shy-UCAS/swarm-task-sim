"""FE-P2 fixed inputs: unchanged non-search semantics and genuine routed recovery."""
from copy import deepcopy
import random
import hashlib
import json
import unittest
from unittest.mock import patch
import numpy as np

from test_v07_m3b_geometry import role_request
from task_v07.unified.spec import build_spec, proposal_seed
from task_v07.unified.free_space import free_space, work_region
from task_v07.unified.shapes import draw_shape
from task_v07.unified.patrol_shape import patrol_shape
from task_v07.unified.construction import ingress_issues
from task_v07.unified.route import route_group
from task_v07.unified.checks import plan_checks
from task_v07.expansion.group_candidate_pool import build_group_pool
from task_v07.expansion.pipeline import assemble_skeleton, exclusion_policy, precheck

# Reference copied from 92068b95416a53d8e84a90488d06112d367f0c09.
# Only the function name changes; all original statements are retained.
def ref_ingress_issues(spec, free, slots):
    """Check the complete reserved ingress, including both sides of the gate."""
    evidence = []
    for side in sorted({s["split_index"] for s in slots}):
        block = [s for s in slots if s["split_index"] == side]
        heading = np.asarray(block[0]["direction"], float)
        normal = np.array([-heading[1], heading[0]])
        lateral = np.asarray([s["entry"] for s in block]) @ normal
        half = float(np.ptp(lateral))/2
        for slot in block:
            gate = np.asarray(slot["entry"], float)
            direction = np.asarray(slot["direction"], float)
            start = gate-(free.cfg["alignment_length_m"]+half)*direction
            for phase, a, b in (("ingress_line_outside_entry", start, gate),
                                ("entry_to_work_start", gate, slot["work"][0])):
                for issue in free.segment_issues(a, b):
                    evidence.append(dict(slot=slot["slot_id"], phase=phase,
                                         start_m=a.tolist(), end_m=np.asarray(b).tolist(), **issue))
    return evidence

class AreaSearchPrecheckTests(unittest.TestCase):
    def shapes(self):
        for method,form in [('monitoring','full'),('monitoring','arc'),('close_observation',None),('feint',None),('intrusion',None)]:
            scene,d,g=role_request(method,multi=(method=='monitoring'),count=4 if method=='monitoring' else 2)
            spec=build_spec(d,g);free=free_space(scene,spec)
            shape=(patrol_shape(spec,free,random.Random(4),{'direction_deg':37.},force_form=form) if form else
                   draw_shape(spec,work_region(scene,spec,free),random.Random(3),free))
            yield method,form,spec,free,shape['slots']

    def test_non_area_real_geometry_exact_equality(self):
        for method,form,spec,free,slots in self.shapes():
            with self.subTest(method=method,form=form):
                self.assertEqual(ingress_issues(spec,free,slots),ref_ingress_issues(spec,free,slots))

    def test_non_area_populated_evidence_exact_order(self):
        for method,form,spec,free,slots in self.shapes():
            with self.subTest(method=method,form=form):
                issues=[{'code':'fixture_constraint','kind':'obstacle','entity_id':'fixture','clearance_m':-3.},
                        {'code':'fixture_second','kind':'world_boundary','entity_id':'world'}]
                with patch.object(free,'segment_issues',return_value=issues):
                    actual=ingress_issues(spec,free,slots);expected=ref_ingress_issues(spec,free,slots)
                self.assertTrue(actual)
                self.assertEqual(actual,expected)
                self.assertIn('entry_to_work_start',{r['phase'] for r in actual})

    def segment_case(self,multi,alignment=None):
        scene,d,g=role_request('area_search',multi=multi,count=4)
        spec=build_spec(d,g);free=free_space(scene,spec)
        if alignment is not None:
            # Override only this isolated fixture object to prove configuration lookup.
            free.cfg=deepcopy(free.cfg);free.cfg['alignment_length_m']=alignment
        directions=([1.,0.],[0.,1.]) if multi else ([1.,0.],)
        slots=[]
        for side,direction in enumerate(directions):
            for lane in range(2):
                slots.append({'split_index':side,'slot_id':f'{side}:{lane}',
                    'entry':[700.+side*20,30.*lane], 'direction':direction,'work':[[333.,444.]]})
        # Deliberately reverse input to test preserved split ordering and within-split ordering.
        slots.reverse(); before=deepcopy(slots)
        issue={'code':'fixture_issue','kind':'obstacle','entity_id':'fixture'}
        with patch.object(free,'segment_issues',return_value=[issue]) as spy:
            actual=ingress_issues(spec,free,slots)
            calls=[(np.asarray(c.args[0]).copy(),np.asarray(c.args[1]).copy()) for c in spy.call_args_list]
        with patch.object(free,'segment_issues',return_value=[issue]) as spy:
            reference=ref_ingress_issues(spec,free,slots)
            old=[(np.asarray(c.args[0]).copy(),np.asarray(c.args[1]).copy()) for c in spy.call_args_list]
        self.assertEqual(len(calls),2*len(slots));self.assertEqual(slots,before)
        ordered=[s for side in sorted({s['split_index'] for s in slots}) for s in slots if s['split_index']==side]
        for i,slot in enumerate(ordered):
            for x,y in zip(calls[2*i],old[2*i]):np.testing.assert_array_equal(x,y)
            self.assertEqual(actual[2*i],reference[2*i])
            gate=np.asarray(slot['entry']);end=gate+free.cfg['alignment_length_m']*np.asarray(slot['direction'])
            np.testing.assert_array_equal(calls[2*i+1][0],gate)
            np.testing.assert_array_equal(calls[2*i+1][1],end)
            self.assertEqual(actual[2*i+1]['phase'],'entry_alignment_inner')
            self.assertEqual(actual[2*i+1]['slot'],slot['slot_id'])
            self.assertEqual(actual[2*i+1]['end_m'],end.tolist())
            self.assertEqual(reference[2*i+1]['phase'],'entry_to_work_start')
        self.assertNotIn('entry_to_work_start',{r['phase'] for r in actual})

    def test_area_single_split_actual_segment_endpoints(self):self.segment_case(False)
    def test_area_multiple_splits_actual_segment_endpoints(self):self.segment_case(True)
    def test_area_uses_configured_alignment(self):self.segment_case(True,137.)

    def test_small_multi_fixture_pool_contracts(self):
        scene,d,g=role_request('area_search',multi=True,count=4)
        pool,report=build_group_pool(scene,d,g,budget=20)
        self.assertTrue(pool,report['rejection_reasons'])
        for candidate in pool:
            self.assertEqual(candidate['checks']['status'],'PASS')
            self.assertEqual(candidate['checks']['existing_precheck']['status'],'PASS')

    def test_real_multi_pool_and_deterministic_recovery(self):
        # The generic fixture's 20 valid shapes are also clear under the old
        # precheck. Use the explicitly permitted, unmodified G1 real input to
        # exercise a genuine old rejection; keep the same 20-proposal test cap.
        data=deepcopy(REGISTERED_RECOVERY_FIXTURE)
        self.assertEqual(hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),REGISTERED_RECOVERY_SHA256)
        scene=data['scene'];d=data['descriptor']
        g=next(g for g in d['task_groups'] if g['group_id']==data['group_id'])
        pool,report=build_group_pool(scene,d,g,budget=20)
        self.assertTrue(pool,{'functional_validation':'INCOMPLETE','rejections':report['rejection_reasons']})
        for candidate in pool:
            self.assertEqual(candidate['checks']['status'],'PASS')
            self.assertEqual(candidate['checks']['existing_precheck']['status'],'PASS')
        spec=build_spec(d,g);free=free_space(scene,spec)
        for candidate in pool:
            rng=random.Random(proposal_seed(spec,candidate['index']))
            shape=draw_shape(spec,work_region(scene,spec,free),rng,free)
            old=ref_ingress_issues(spec,free,shape['slots'])
            conflicts=[x for x in old if x['phase']=='entry_to_work_start' and x.get('kind')=='forbidden_layer' and (x.get('entity_id')==g['target_id'] or x.get('entity_id','').startswith(g['target_id']+'_'))]
            if not conflicts:continue
            self.assertEqual(ingress_issues(spec,free,shape['slots']),[])
            from task_v07.unified.operation_routes import route_operation
            with patch('task_v07.unified.operation_routes.route_operation',wraps=route_operation) as original:
                bundle,template=route_group(scene,spec,shape,free,d['family_conditions']['initial_states'],rng)
            self.assertEqual(original.call_count,1)
            checks=plan_checks(scene,spec,bundle,template,free,d['family_conditions']['initial_states'])
            self.assertEqual(checks['status'],'PASS',checks['issues'])
            template['task_spec']=spec
            skeleton=assemble_skeleton(d,g,bundle,template,False)
            policy=exclusion_policy(scene,g['role'],g['target_id'],g['members'])
            skeleton['exclusion_policy']=policy
            existing=precheck(scene,skeleton,bundle,policy)
            self.assertEqual(existing['status'],'PASS',existing)
            print('P2_DETERMINISTIC_RECOVERY',{'candidate_index':candidate['index'],
                'proposal_seed':proposal_seed(spec,candidate['index']),'old_conflicts':len(conflicts),
                'plan_checks':checks['status'],'existing_precheck':existing['status']})
            return
        self.fail('FUNCTIONAL_VALIDATION_INCOMPLETE: no deterministic forbidden-layer recovery witness in fixed 20-proposal fixture')


# Immutable G1 fixture snapshot: no scene, descriptor, seed, or constraint edits.
REGISTERED_RECOVERY_PROVENANCE = {'skeleton_id': 'family_s15_1b876e6b8b6f70c6_ext_006_regular',
 'group_id': 'task_group_01',
 'descriptor_file_sha256': '1e5e0be6332ee3edba613b024bf4ce2dfc7ba0271949860ed16fa7695782a128',
 'source': 'G1 fixed 32-cohort; first registered multi-direction area_search case with target entry conflict '
           'and a nonempty A candidate pool'}
REGISTERED_RECOVERY_SHA256 = '11a859e98915f25607a9029d84a4671e780ecb8ee22859d5d4c80f5818f23057'
REGISTERED_RECOVERY_FIXTURE = {'scene': {'coordinate_system': 'ENU',
           'entities': [{'geometry': {'center_m': [1749.4526425241024, 1955.6884826938424],
                                      'radius_m': 53.5325386355617,
                                      'type': 'Circle'},
                         'id': 'facility_01',
                         'type': 'facility'},
                        {'facility_id': 'facility_01',
                         'geometry': {'center_m': [1749.4526425241024, 1955.6884826938424],
                                      'radius_m': 195.82017491114698,
                                      'type': 'Circle'},
                         'id': 'facility_01_protected',
                         'layer': 'protected',
                         'offset_m': 142.28763627558527,
                         'type': 'protection_zone'},
                        {'facility_id': 'facility_01',
                         'geometry': {'center_m': [1749.4526425241024, 1955.6884826938424],
                                      'radius_m': 470.55882245802525,
                                      'type': 'Circle'},
                         'id': 'facility_01_alert',
                         'layer': 'alert',
                         'offset_m': 417.02628382246354,
                         'type': 'protection_zone'},
                        {'facility_id': 'facility_01',
                         'geometry': {'center_m': [1749.4526425241024, 1955.6884826938424],
                                      'radius_m': 1177.7436032280684,
                                      'type': 'Circle'},
                         'id': 'facility_01_warning',
                         'layer': 'warning',
                         'offset_m': 1124.2110645925068,
                         'type': 'protection_zone'},
                        {'geometry': {'type': 'Polygon',
                                      'vertices_m': [[1976.580681624889, 2807.881896786833],
                                                     [1744.0528041442954, 3122.2739425574878],
                                                     [2129.044436050389, 3132.082224108697]]},
                         'id': 'obstacle_01',
                         'type': 'hard_constraint_obstacle'},
                        {'geometry': {'center_m': [386.2705557142975, 2585.4117431538607],
                                      'radius_m': 241.8425955073856,
                                      'type': 'Circle'},
                         'id': 'obstacle_02',
                         'type': 'hard_constraint_obstacle'},
                        {'geometry': {'center_m': [3220.523473630879, 2434.8126273891203],
                                      'radius_m': 127.94443890471122,
                                      'type': 'Circle'},
                         'id': 'obstacle_03',
                         'type': 'hard_constraint_obstacle'},
                        {'geometry': {'position_m': [1975.111505619773, 1957.172869076576], 'type': 'Point'},
                         'id': 'radar_01',
                         'type': 'radar'}],
           'entry_zones': [{'geometry': {'type': 'Polygon',
                                         'vertices_m': [[0, 2560.752245930475],
                                                        [100.0, 2560.752245930475],
                                                        [100.0, 2920.752245930475],
                                                        [0, 2920.752245930475]]},
                            'id': 'entry_01'},
                           {'geometry': {'type': 'Polygon',
                                         'vertices_m': [[3900.0, 2492.40133445969],
                                                        [4000.0, 2492.40133445969],
                                                        [4000.0, 2852.40133445969],
                                                        [3900.0, 2852.40133445969]]},
                            'id': 'entry_02'}],
           'schema_version': 'traj2language.public_scene/0.7-s1.1',
           'units': {'acceleration': 'm/s^2', 'angle': 'rad', 'length': 'm', 'speed': 'm/s'},
           'world': {'geometry': {'type': 'Polygon',
                                  'vertices_m': [[0, 0], [4000.0, 0], [4000.0, 4000.0], [0, 4000.0]]},
                     'id': 'world'}},
 'descriptor': {'schema_version': 'traj2language.s2_infrastructure/0.7.1',
                'skeleton_id': 'family_s15_1b876e6b8b6f70c6_ext_006_regular',
                'family_id': 'family_s15_1b876e6b8b6f70c6',
                'map_id': 'map_s15_1b876e6b8b6f70c6',
                'base_intent': 'reconnaissance',
                'subset': 'regular',
                'status': 'awaiting_role_planner',
                'common_draw': {'seed': 4670704955796861560,
                                'slot': 1,
                                'requested_unit_count': 1,
                                'actual_unit_count': 1,
                                'unit_count_capped': False,
                                'approach_mode': 'multi_direction',
                                'multi_direction_min_span_deg': 90.0,
                                'units': [{'unit_id': 'unit_01',
                                           'target_id': 'facility_01',
                                           'members': ['uav_01',
                                                       'uav_02',
                                                       'uav_03',
                                                       'uav_04',
                                                       'uav_05',
                                                       'uav_06',
                                                       'uav_07',
                                                       'uav_08',
                                                       'uav_09',
                                                       'uav_10'],
                                           'between_group_offset_s': 58.9}],
                                'distribution': {'unit_count': 'uniform 1..3 then cap at floor(N/2)',
                                                 'approach': 'Bernoulli(0.5); same common draw across '
                                                             'intents',
                                                 'target': 'first uniform; later p=0.5 first, else uniform '
                                                           'among others',
                                                 'member_allocation': 'two each, remaining agents uniform '
                                                                      'among units',
                                                 'between_group_offset_s': 'uniform [0,90], first unit '
                                                                           'survives merge'}},
                'units': [{'unit_id': 'unit_01',
                           'target_id': 'facility_01',
                           'members': ['uav_01',
                                       'uav_02',
                                       'uav_03',
                                       'uav_04',
                                       'uav_05',
                                       'uav_06',
                                       'uav_07',
                                       'uav_08',
                                       'uav_09',
                                       'uav_10'],
                           'between_group_offset_s': 58.9,
                           'role': 'reconnaissance',
                           'execution_method': 'area_search'}],
                'task_groups': [{'group_id': 'task_group_01',
                                 'target_id': 'facility_01',
                                 'role': 'reconnaissance',
                                 'execution_method': 'area_search',
                                 'between_group_offset_s': 58.9,
                                 'members': ['uav_01',
                                             'uav_02',
                                             'uav_03',
                                             'uav_04',
                                             'uav_05',
                                             'uav_06',
                                             'uav_07',
                                             'uav_08',
                                             'uav_09',
                                             'uav_10'],
                                 'source_units': ['unit_01']}],
                'main_unit_id': None,
                'agent_ids': ['uav_09',
                              'uav_08',
                              'uav_03',
                              'uav_10',
                              'uav_04',
                              'uav_05',
                              'uav_02',
                              'uav_07',
                              'uav_06',
                              'uav_01'],
                'column_seed': 8692899516927555059,
                'role_seed': 38945434813316095,
                'cruise_speed_m_s': 4.632649197420282,
                'task_altitude_m': 140.65441869946758,
                'family_conditions': {'config': {'altitude_max_m': 150.0,
                                                 'altitude_min_m': 100.0,
                                                 'angle_step_deg': 5,
                                                 'approach_standoff_m': 30.0,
                                                 'checking_quad_segs': 64,
                                                 'entry_depth_m': 100.0,
                                                 'entry_width_m': 360.0,
                                                 'map_side_m': 4000.0,
                                                 'planning_quad_segs': 8,
                                                 'safety_margin_m': 30.0},
                                      'cruise_speed_m_s': 4.632649197420282,
                                      'facility_sampling': {'anchor_attempts': 1,
                                                            'anchor_retries': 0,
                                                            'attempts': 1,
                                                            'exhausted': False,
                                                            'links': [],
                                                            'map_side_m': 4000.0,
                                                            'rejected_attempt_reasons': {'warning_near_entry': 0}},
                                      'family_id': 'family_s15_1b876e6b8b6f70c6',
                                      'generator_version': 'traj2language.scene_sampler/0.7-s1.5',
                                      'initial_states': [{'acceleration_enu_m_s2': [0.0, 0.0, 0.0],
                                                          'agent_id': 'uav_04',
                                                          'entry_id': 'entry_01',
                                                          'position_enu_m': [50.0,
                                                                             2704.9727928626858,
                                                                             140.65441869946758],
                                                          'velocity_enu_m_s': [0.13812007212001431,
                                                                               -0.017142617216881578,
                                                                               0.0]},
                                                         {'acceleration_enu_m_s2': [0.0, 0.0, 0.0],
                                                          'agent_id': 'uav_05',
                                                          'entry_id': 'entry_01',
                                                          'position_enu_m': [50.0,
                                                                             2722.8625193965804,
                                                                             140.65441869946758],
                                                          'velocity_enu_m_s': [0.19257919881173965,
                                                                               -0.0017635916169207537,
                                                                               0.0]},
                                                         {'acceleration_enu_m_s2': [0.0, 0.0, 0.0],
                                                          'agent_id': 'uav_10',
                                                          'entry_id': 'entry_01',
                                                          'position_enu_m': [50.0,
                                                                             2776.5316989982643,
                                                                             140.65441869946758],
                                                          'velocity_enu_m_s': [0.7189888765720489,
                                                                               -0.016045405075847664,
                                                                               0.0]},
                                                         {'acceleration_enu_m_s2': [0.0, 0.0, 0.0],
                                                          'agent_id': 'uav_09',
                                                          'entry_id': 'entry_02',
                                                          'position_enu_m': [3950.0,
                                                                             2636.621881391901,
                                                                             140.65441869946758],
                                                          'velocity_enu_m_s': [-0.8365047760328135,
                                                                               0.10938597824497809,
                                                                               0.0]},
                                                         {'acceleration_enu_m_s2': [0.0, 0.0, 0.0],
                                                          'agent_id': 'uav_07',
                                                          'entry_id': 'entry_02',
                                                          'position_enu_m': [3950.0,
                                                                             2690.291060993585,
                                                                             140.65441869946758],
                                                          'velocity_enu_m_s': [-0.9122047181925367,
                                                                               0.03307501301914211,
                                                                               0.0]},
                                                         {'acceleration_enu_m_s2': [0.0, 0.0, 0.0],
                                                          'agent_id': 'uav_01',
                                                          'entry_id': 'entry_02',
                                                          'position_enu_m': [3950.0,
                                                                             2654.5116079257955,
                                                                             140.65441869946758],
                                                          'velocity_enu_m_s': [-0.8612836733105624,
                                                                               -0.024190341297869622,
                                                                               0.0]},
                                                         {'acceleration_enu_m_s2': [0.0, 0.0, 0.0],
                                                          'agent_id': 'uav_08',
                                                          'entry_id': 'entry_01',
                                                          'position_enu_m': [50.0,
                                                                             2758.6419724643697,
                                                                             140.65441869946758],
                                                          'velocity_enu_m_s': [0.28592263587458,
                                                                               -0.03790803593189442,
                                                                               0.0]},
                                                         {'acceleration_enu_m_s2': [0.0, 0.0, 0.0],
                                                          'agent_id': 'uav_06',
                                                          'entry_id': 'entry_01',
                                                          'position_enu_m': [50.0,
                                                                             2740.752245930475,
                                                                             140.65441869946758],
                                                          'velocity_enu_m_s': [0.8793535165133064,
                                                                               -0.11281510810816736,
                                                                               0.0]},
                                                         {'acceleration_enu_m_s2': [0.0, 0.0, 0.0],
                                                          'agent_id': 'uav_02',
                                                          'entry_id': 'entry_02',
                                                          'position_enu_m': [3950.0,
                                                                             2672.40133445969,
                                                                             140.65441869946758],
                                                          'velocity_enu_m_s': [-0.2707416203079873,
                                                                               -0.012842563193906385,
                                                                               0.0]},
                                                         {'acceleration_enu_m_s2': [0.0, 0.0, 0.0],
                                                          'agent_id': 'uav_03',
                                                          'entry_id': 'entry_02',
                                                          'position_enu_m': [3950.0,
                                                                             2708.1807875274794,
                                                                             140.65441869946758],
                                                          'velocity_enu_m_s': [-1.1089041231193315,
                                                                               0.04767785150646358,
                                                                               0.0]}],
                                      'lateral_spacing_m': 17.889726533894603,
                                      'layout': 'single',
                                      'layout_config_sha256': 'ae76fd9ee1680bad89697c21d82783b0e9e79ecd3535f796b12d2a84c1b59cbb',
                                      'layout_s15': {'anchor_attempts': 1,
                                                     'anchor_retries': 0,
                                                     'attempts': 1,
                                                     'exhausted': False,
                                                     'links': [],
                                                     'map_side_m': 4000.0,
                                                     'rejected_attempt_reasons': {'warning_near_entry': 0}},
                                      'map_id': 'map_s15_1b876e6b8b6f70c6',
                                      'map_side_m': 4000.0,
                                      'observation_profile': {'position_sigma0_m': 0.2640017997064793,
                                                              'position_slope_m_per_km': 0.16492244585467458,
                                                              'velocity_sigma0_m_s': 0.0494369159138211,
                                                              'velocity_slope_m_s_per_km': 0.01997276474414092},
                                      'obstacle_placements': [{'obstacle_id': 'obstacle_01',
                                                               'placement': 'facility_side',
                                                               'placement_attempts': 1,
                                                               'reference_facility_id': 'facility_01'},
                                                              {'entry_id': 'entry_01',
                                                               'obstacle_id': 'obstacle_02',
                                                               'placement': 'entry_blocking',
                                                               'placement_attempts': 1,
                                                               'reference_facility_id': 'facility_01'},
                                                              {'entry_id': 'entry_02',
                                                               'obstacle_id': 'obstacle_03',
                                                               'placement': 'entry_blocking',
                                                               'placement_attempts': 1,
                                                               'reference_facility_id': 'facility_01'}],
                                      'obstacle_sampling': {'placed_count': 3,
                                                            'requested_count': 3,
                                                            'skipped_count': 0,
                                                            'slots': [{'attempts': 1,
                                                                       'initial_placement': 'facility_side',
                                                                       'placed': True,
                                                                       'placement': 'facility_side',
                                                                       'rejected_attempt_reasons': {},
                                                                       'slot': 1,
                                                                       'tried_types': ['facility_side']},
                                                                      {'attempts': 1,
                                                                       'initial_placement': 'entry_blocking',
                                                                       'placed': True,
                                                                       'placement': 'entry_blocking',
                                                                       'rejected_attempt_reasons': {},
                                                                       'slot': 2,
                                                                       'tried_types': ['entry_blocking']},
                                                                      {'attempts': 1,
                                                                       'initial_placement': 'entry_blocking',
                                                                       'placed': True,
                                                                       'placement': 'entry_blocking',
                                                                       'rejected_attempt_reasons': {},
                                                                       'slot': 3,
                                                                       'tried_types': ['entry_blocking']}]},
                                      'radar_placements': [{'placement': 'facility_side',
                                                            'placement_attempts': 1,
                                                            'radar_id': 'radar_01',
                                                            'reference_facility_id': 'facility_01'}],
                                      'sampling_policy': {'facility_attempts': 128,
                                                          'obstacle_attempts': 48,
                                                          'radar_attempts': 80},
                                      'sampling_revision': 's1.5',
                                      'sampling_seed': 1983675569059885254,
                                      'schema_version': 'traj2language.family_initial/0.7-s1.2',
                                      'task_altitude_m': 140.65441869946758,
                                      'vehicle_count': 10},
                'role_parameters': {},
                'planned_geometry': None,
                'evidence_status': 'not_executed'},
 'group_id': 'task_group_01'}
