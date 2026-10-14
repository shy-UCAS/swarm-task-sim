"""User-required invariants for shared phase-2 geometry."""
from copy import deepcopy
import unittest
from task_v07.expansion.formation_role_planners import Context,stable_split
from test_v07_s2_expansion import scene


class FormationSplitInvariantTests(unittest.TestCase):
    def family(self,n):
        return {'sampling_seed':915,'cruise_speed_m_s':8.,'task_altitude_m':100.,
                'initial_states':[{'agent_id':f'u{i}','position_enu_m':[60.,1500.+25*i,100.]} for i in range(n)]}

    def test_numeric_slot_split_ignores_role_column_and_batch(self):
        family=self.family(9);members=[s['agent_id'] for s in family['initial_states']]
        expected=stable_split(family,members,2,True)
        for role in ('transit','reconnaissance','monitoring','feint','intrusion'):
            permuted=deepcopy(family);permuted['initial_states'].reverse()
            group={'members':members[::-1],'target_id':'f','role':role}
            params={'family':permuted,'approach_mode':'multi_direction','geometry_slot':2,
                    'planning_seed':7543,'column_seed':112,'batch_by_agent':{a:i%3 for i,a in enumerate(members)}}
            self.assertEqual(Context(scene(),group,params).split,expected)

    def test_two_members_form_two_singletons(self):
        family=self.family(2);members=['u0','u1'];split=stable_split(family,members,4,True)
        self.assertEqual([len(stock) for stock in split],[1,1])
        self.assertEqual(sorted(a for stock in split for a in stock),members)


class DiagnosticIsolationTests(unittest.TestCase):
    def test_diagnostics_never_enter_any_view_or_success_statistics(self):
        from test_v07_s2_infrastructure import ViewTests
        from task_v07.expansion.views import make_views,diagnostic_summary
        normal=ViewTests().records()
        diagnostics=[{**row,'diagnostic_only':True,'episode_id':'diag-'+row['episode_id'],
                      'skeleton_id':'diag-'+row['skeleton_id']} for row in normal]
        self.assertEqual(make_views(normal+diagnostics),make_views(normal))
        self.assertEqual(diagnostic_summary([],normal+diagnostics),diagnostic_summary([],normal))

    def test_diagnostics_are_excluded_on_both_sides_of_cross_negation(self):
        from task_v07.expansion.evaluation import cross_negation
        templates=[{'family_id':'f','intent':'transit','template_id':'normal','parameters':{}},
                   {'family_id':'f','intent':'monitoring','template_id':'diag','parameters':{'diagnostic_only':True}}]
        episodes=[{'family_id':'f','intent':'feint','episode_id':'normal'},
                  {'family_id':'f','intent':'intrusion','episode_id':'diag','diagnostic_only':True}]
        report=cross_negation(templates,episodes,{})
        self.assertEqual([(r['template_id'],r['episode_id']) for r in report['rows']],[('normal','normal')])


if __name__=='__main__':unittest.main()
