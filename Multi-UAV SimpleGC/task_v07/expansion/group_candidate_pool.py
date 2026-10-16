"""Independent group proposals, then bounded random compatible combinations."""
from collections import Counter
import math,random,time
from task_v07.planning import seed_for
from .contracts import P0ContractError
from .formation_role_planners import Context
from .continuous_geometry import draw_role
from .pipeline import plan_group,role_parameters
from .candidate_constraints import bearing_allowed
from .role_planners import PlanningInfeasible
from .search_diagnostics import rejection,summarize

COMBINATION_BUDGET=1000


def combination_indices(sizes,budget,rng):
    """Uniform, without replacement over the full Cartesian product."""
    if budget<1:raise ValueError('Positive combination budget required')
    total=math.prod(sizes)
    if not sizes or total==0:return []
    encoded=rng.sample(range(total),min(total,budget))
    result=[]
    for value in encoded:
        indices=[]
        for size in reversed(sizes):
            indices.append(value%size);value//=size
        result.append(tuple(reversed(indices)))
    return result


def build_group_pool(scene,descriptor,group,budget):
    from .candidate_search import DrawnPlanner,_candidate_record
    gid=group['group_id'];ctx=Context(scene,group,role_parameters(descriptor,group))
    records=[];pool=[];reasons=Counter();started=time.perf_counter()
    geometry_wall=0.;phase_evaluations=0;phase_wall=0.
    for index in range(budget):
        start=time.perf_counter()
        result,reason,draw=draw_role(ctx,index)
        geometry_wall+=time.perf_counter()-start
        local=getattr(ctx,'local_search_trace',None)
        if local:
            phase=local.get('phase_search',{})
            phase_evaluations+=phase.get('evaluations',0);phase_wall+=phase.get('wall_s',0.)
        evidence=getattr(ctx,'last_failure_evidence',[])
        skeleton=bundle=pre=None
        if result is not None:
            try:
                skeleton,bundle,pre=plan_group(scene,descriptor,group,DrawnPlanner(result))
                if pre['status']!='PASS':
                    reason=';'.join(pre['failures'])
                    evidence=[{'constraint':kind, 'agent_id':a, **issue}
                              for kind in ('polylines','semantic_polylines')
                              for a,v in pre.get(kind,{}).items() for issue in v['issues']]
                    evidence.extend({'constraint':'retreat_point','agent_id':a,**value}
                                    for a,value in pre.get('retreat_points',{}).items() if not value['valid'])
                    if pre.get('endpoint_spacing') and not pre['endpoint_spacing']['valid']:
                        evidence.append({'constraint':'endpoint_spacing',**pre['endpoint_spacing']})
            except PlanningInfeasible as exc:reason=exc.detail
        stage='group_geometry:'+gid if reason else 'group_feasible'
        record=_candidate_record(index,stage,reason,{gid:draw},evidence)
        record.update(proposal_id=f'{gid}:{index}',group_id=gid)
        if local:record['local_searches']={gid:local}
        if reason:
            reasons[reason]+=1
            if reason.endswith('_search_budget_exhausted'):
                record['rejection']=rejection(reason,scope='local_component_search',exhausted=True)
        else:
            skeleton['agent_ids']=[a for a in descriptor['agent_ids'] if a in group['members']]
            skeleton['between_group_offset_s']=group['between_group_offset_s']
            cost=result['approach_length_m']
            pool.append({'index':index,'cost':cost,'skeleton':skeleton,'bundle':bundle,'checks':pre,
                         'bearing_deg':result['template']['work_area_bearing_deg'],'target_id':group['target_id']})
            record['approach_length_m']=cost
        records.append(record)
    return pool,{'records':records,'rejection_reasons':dict(reasons),
        'metrics':{'attempts':len(records),'budget':budget,'feasible_candidates':len(pool),
                   'wall_s':time.perf_counter()-started,'geometry_wall_s':geometry_wall,
                   'phase_search':{'evaluations':phase_evaluations,'wall_s':phase_wall}},
        'termination':rejection('group_pool_empty_after_registered_budget',scope='group_search',exhausted=True) if not pool else None}


def independent_episode_pool(scene,descriptor,budget=200,combination_budget=COMBINATION_BUDGET):
    from .sampling import derive_intent
    from .candidate_search import choose_eligible,MAX_CALIBRATION_ROUNDS
    from .episode_pipeline import assemble_episode
    if budget<200:raise ValueError('Every task group requires at least 200 proposals')
    if derive_intent(descriptor['task_groups'])!=descriptor['base_intent']:
        raise P0ContractError('Public sampling roles disagree with assigned intent')
    order=sorted(descriptor['task_groups'],key=lambda g:g['group_id'])
    pools={};group_reports={};records=[];group_reasons=Counter()
    # No early return: even an empty first pool cannot censor later groups.
    for group in order:
        gid=group['group_id']
        pools[gid],group_reports[gid]=build_group_pool(scene,descriptor,group,budget)
        records.extend(group_reports[gid]['records']);group_reasons.update(group_reports[gid]['rejection_reasons'])
    gids=[g['group_id'] for g in order]
    combination_seed=seed_for(descriptor['role_seed'],'independent-group-combination-order')
    choices=combination_indices([len(pools[g]) for g in gids],combination_budget,random.Random(combination_seed))
    combinations=[];feasible=[];combination_reasons=Counter();started=time.perf_counter()
    for index,indices in enumerate(choices):
        selected={gid:pools[gid][i] for gid,i in zip(gids,indices)}
        proposal_ids={g:c['index'] for g,c in selected.items()}
        record={'candidate_index':index,'group_candidate_indices':proposal_ids,'stage':'combination','reason':None,'rejection':None}
        bearings={};reason=None
        for gid,c in selected.items():
            if not bearing_allowed(math.radians(c['bearing_deg']),{'excluded_work_area_bearings_deg':bearings.get(c['target_id'],[]),
                                                                  'minimum_group_bearing_difference_deg':60.}):
                reason='same_target_work_area_bearing';break
            bearings.setdefault(c['target_id'],[]).append(c['bearing_deg'])
        if not reason:
            groups={g:c['skeleton'] for g,c in selected.items()};bundles={g:c['bundle'] for g,c in selected.items()}
            skeleton,bundle=assemble_episode(descriptor,groups,bundles,index)
            costs={g:c['cost'] for g,c in selected.items()}
            feasible.append({'index':index,'cost':sum(costs.values()),'cost_by_group':costs,
                'group_candidate_indices':proposal_ids,'skeleton':skeleton,'bundle':bundle,
                'checks':{g:c['checks'] for g,c in selected.items()}})
            record.update(stage='feasible',approach_length_by_group_m=costs)
        if reason:
            record.update(reason=reason,rejection=rejection(reason,scope='combination'))
            combination_reasons[reason]+=1
        combinations.append(record)
    eligible,selection=choose_eligible(feasible,descriptor['common_draw']['approach_mode']=='same_direction',
                                     random.Random(seed_for(descriptor['role_seed'],'continuous-feasible-pool-order')))
    eligible_ids={c['index'] for c in eligible}
    for record in combinations:
        if record['stage']=='feasible' and record['candidate_index'] not in eligible_ids:
            reason='task_group_approach_length_exceeds_115_percent'
            record.update(stage='same_direction_115_percent',reason=reason,rejection=rejection(reason,scope='combination'))
            combination_reasons[reason]+=1
    for c in eligible:
        c['skeleton']['candidate_selection']={**selection,'candidate_index':c['index'],'group_candidate_indices':c['group_candidate_indices'],
            'selected_approach_length_m':c['cost'],'selected_approach_length_by_group_m':c['cost_by_group']}
    reasons=group_reasons+combination_reasons
    report={'candidate_budget':budget,'candidate_budget_scope':'each task group independently','attempted_candidates':len(records),
        'group_attempt_counts':{g:group_reports[g]['metrics']['attempts'] for g in gids},
        'group_search_metrics':{g:group_reports[g]['metrics'] for g in gids},
        'group_terminations':{g:group_reports[g]['termination'] for g in gids},
        'group_feasible_candidate_indices':{g:[c['index'] for c in pools[g]] for g in gids},
        'group_eligible_candidate_indices':{g:sorted({c['group_candidate_indices'][g] for c in eligible}) for g in gids},
        'combination_search':{'budget':combination_budget,'total_possible':math.prod(len(pools[g]) for g in gids),
            'attempts':len(choices),'random_seed':combination_seed,'sampling':'uniform without replacement over independent pool Cartesian product',
            'wall_s':time.perf_counter()-started},
        'group_rejection_reasons':dict(group_reasons),'combination_rejection_reasons':dict(combination_reasons),
        'rejection_reasons':dict(reasons),'rejection_class_counts':summarize(records+combinations),
        'rejection_count_units':'group proposals and episode combinations; see separate counts, do not interpret aggregate as a single rate',
        'termination':rejection('no_eligible_combination_in_registered_budgets',scope='skeleton_search',exhausted=True) if not eligible else None,
        'selection':selection,'eligible_candidate_order':[c['index'] for c in eligible],
        'max_single_agent_calibration_rounds':MAX_CALIBRATION_ROUNDS,'solo_flights_run':0,
        'candidates':records,'combination_records':combinations}
    return eligible,report
