from copy import deepcopy
import unittest
from task_v07.expansion.public_approach_shape import public_approach_shape
from task_v07.expansion.pipeline import role_parameters


class PublicApproachTests(unittest.TestCase):
    def test_live_planner_context_uses_public_slot_not_private_extended_ordinal(self):
        from task_v07.expansion.formation_role_planners import Context
        from test_v07_s2_expansion import scene
        ids=[f'a{i}' for i in range(7)]
        family={'family_id':'f','sampling_seed':123,'cruise_speed_m_s':5.,'task_altitude_m':100.,
                'lateral_spacing_m':30.,'initial_states':[{'agent_id':a,'position_enu_m':[100.,500.+i*30.,100.]} for i,a in enumerate(ids)]}
        slot=next(s for s in range(100) if public_approach_shape(family,s,ids)['split_count']==3)
        params={'family':family,'common_slot':slot,'geometry_slot':999,'planning_seed':87,'approach_mode':'multi_direction'}
        ctx=Context(scene(),{'target_id':'f','role':'feint','members':ids},params)
        expected=public_approach_shape(family,slot,ids)
        self.assertEqual(ctx.split,expected['members'])
        self.assertEqual(ctx.relative_bearings_rad,expected['relative_bearings_rad'])
        self.assertEqual(len(ctx.split),3)

    def test_key_excludes_intent_role_target_column_and_extended_ordinal(self):
        family={'family_id':'f','sampling_seed':123}
        members=['a','b','c','d','e','f','g']
        reference=public_approach_shape(family,4,members)
        for index,intent in enumerate(('transit','reconnaissance','monitoring','feint','penetration')):
            descriptor={'skeleton_id':f'f_ext_{index:03d}_regular','role_seed':index,
                'column_seed':index*8,'family_conditions':deepcopy(family),'base_intent':intent,
                'cruise_speed_m_s':7.,'task_altitude_m':100.,
                'common_draw':{'slot':4,'approach_mode':'multi_direction'}}
            params=role_parameters(descriptor,{'group_id':f'g{index}','target_id':f't{index}'})
            shape=public_approach_shape(params['family'],params['common_slot'],list(reversed(members)))
            self.assertEqual(shape,reference)
            self.assertEqual(public_approach_shape(params['family'],params['common_slot'],members),reference)

    def test_allowed_counts_angles_and_full_member_partition(self):
        counts=set();two=[];three=[]
        for n in range(2,11):
            ids=[f'a{i}' for i in range(n)]
            for slot in range(100):
                shape=public_approach_shape({'family_id':'f','sampling_seed':13},slot,ids)
                count=shape['split_count'];counts.add(count)
                self.assertEqual(sorted(a for group in shape['members'] for a in group),ids)
                self.assertTrue(all(shape['members']))
                self.assertTrue(count==2 if n<=5 else count in (2,3))
                delta=shape['adjacent_differences_deg']
                if count==2:
                    self.assertTrue(100<=delta[0]<=180);two.extend(delta)
                else:
                    self.assertTrue(all(50<=d<=120 for d in delta))
                    self.assertGreaterEqual(sum(delta),100);three.extend(delta)
        self.assertEqual(counts,{2,3})
        self.assertGreater(max(two)-min(two),70)
        self.assertGreater(max(three)-min(three),60)

    def test_member_set_and_slot_change_stream_and_same_direction_has_one_stock(self):
        family={'family_id':'f','sampling_seed':1}
        shape=public_approach_shape(family,0,['a','b','c'])
        self.assertNotEqual(shape['seed'],public_approach_shape(family,1,['a','b','c'])['seed'])
        self.assertNotEqual(shape['seed'],public_approach_shape(family,0,['a','b','d'])['seed'])
        same=public_approach_shape(family,0,['a','b','c'],False)
        self.assertEqual(same['split_count'],1)
        self.assertEqual(same['relative_bearings_deg'],[0.])


if __name__=='__main__':unittest.main()
