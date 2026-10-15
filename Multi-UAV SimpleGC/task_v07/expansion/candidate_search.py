"""Finite continuous geometry pools, filtered before single-agent calibration."""
from collections import Counter
from copy import deepcopy
import random
import time

from task_v07.planning import seed_for
from .contracts import RouteBundle, P0ContractError
from .formation_role_planners import Context
from .continuous_geometry import draw_role
from .pipeline import plan_group, role_parameters, COMMON_CONSTANTS, timing_plans
from .candidate_constraints import bearing_allowed
from .geometry_checks import planning_layer_interval_check
from .role_planners import PlanningInfeasible
from .search_diagnostics import rejection, summarize

CANDIDATE_BUDGET = 200
MAX_CALIBRATION_ROUNDS = 5


class DrawnPlanner:
    legacy_vertical_slice = False

    def __init__(self, result):
        self.result = result

    def plan_with_template(self, scene, group, parameters):
        return RouteBundle(self.result['routes'], {a: 0. for a in group['members']}), self.result['template']


def choose_eligible(candidates, same_direction, rng):
    if not candidates:
        return [], {'minimum_approach_length_m': None, 'feasible_candidates': 0, 'eligible_candidates': 0}
    minimum = min(c['cost'] for c in candidates)
    group_ids = set(candidates[0].get('cost_by_group', {}))
    if any(set(c.get('cost_by_group', {})) != group_ids for c in candidates):
        raise P0ContractError('Candidate task-group cost axes differ')
    minima = {g: min(c['cost_by_group'][g] for c in candidates) for g in sorted(group_ids)}
    def within_bound(candidate):
        costs = candidate.get('cost_by_group', {'single_group': candidate['cost']})
        bounds = minima or {'single_group': minimum}
        return all(cost/bounds[g] <= 1.15 if bounds[g] else cost == 0 for g, cost in costs.items())
    eligible = [c for c in candidates if not same_direction or within_bound(c)]
    rng.shuffle(eligible)
    return eligible, {'minimum_approach_length_m': minimum, 'maximum_ratio': 1.15 if same_direction else None,
                      'minimum_approach_length_by_group_m': minima,
                      'ratio_scope': 'each task group independently within whole-episode feasible pool',
                      'feasible_candidates': len(candidates), 'eligible_candidates': len(eligible),
                      'selection_order': 'all geometry -> nominal whole-route separation -> same-direction 115% -> private random order -> at most 5 actual calibration rounds'}


def _candidate_record(index, stage, reason, draws, evidence=None):
    return {'candidate_index': index, 'stage': stage, 'reason': reason, 'draws_by_group': draws,
            'rejection': rejection(reason, evidence=evidence) if reason else None}


def episode_candidate_pool(scene, descriptor, budget=CANDIDATE_BUDGET):
    from .episode_pipeline import assemble_episode, compose_timing_plans, episode_interval_check
    from .sampling import derive_intent
    if budget < 200:
        raise ValueError('Every skeleton requires at least 200 private geometry candidates')
    if derive_intent(descriptor['task_groups']) != descriptor['base_intent']:
        raise P0ContractError('Public sampling roles disagree with assigned intent')
    order = sorted(descriptor['task_groups'], key=lambda g: (g['role'] == 'monitoring', g['group_id']))
    contexts = {g['group_id']: Context(scene, g, role_parameters(descriptor, g)) for g in order}
    candidates, records, reasons = [], [], Counter()
    group_attempts = Counter()
    group_wall = {g['group_id']:0. for g in order}
    for index in range(budget):
        groups, bundles, checks, bearings, draws = {}, {}, {}, {}, {}
        cost = 0.
        cost_by_group = {}
        rejected = None
        failure_evidence = None
        local_searches = {}
        for group in order:
            gid = group['group_id']
            ctx = contexts[gid]
            group_attempts[gid] += 1
            started = time.perf_counter()
            result, reason, draw = draw_role(ctx, index)
            group_wall[gid] += time.perf_counter()-started
            draws[gid] = draw
            if getattr(ctx,'local_search_trace',None):local_searches[gid]=ctx.local_search_trace
            if result is None:
                failure_evidence = getattr(ctx, 'last_failure_evidence', [])
                rejected = ('geometry:'+gid, reason)
                break
            angle = result['template']['work_area_bearing_deg']
            import math
            if not bearing_allowed(math.radians(angle), {'excluded_work_area_bearings_deg': bearings.get(group['target_id'], []),
                                                        'minimum_group_bearing_difference_deg': 60.}):
                rejected = ('geometry:'+gid, 'same_target_work_area_bearing')
                break
            try:
                skeleton, bundle, pre = plan_group(scene, descriptor, group, DrawnPlanner(result))
            except PlanningInfeasible as exc:
                rejected = ('geometry:'+gid, exc.detail)
                break
            if pre['status'] != 'PASS':
                rejected = ('geometry:'+gid, ';'.join(pre['failures']))
                break
            skeleton['agent_ids'] = [a for a in descriptor['agent_ids'] if a in group['members']]
            skeleton['between_group_offset_s'] = group['between_group_offset_s']
            groups[gid], bundles[gid], checks[gid] = skeleton, bundle, pre
            bearings.setdefault(group['target_id'], []).append(angle)
            cost += result['approach_length_m']
            cost_by_group[gid] = result['approach_length_m']
        if rejected:
            stage, reason = rejected
            reasons[reason] += 1
            record=_candidate_record(index, stage, reason, draws, failure_evidence)
            record['local_searches']=local_searches
            if reason.endswith('_search_budget_exhausted'):
                record['rejection']=rejection(reason,scope='local_component_search',exhausted=True)
            records.append(record)
            continue
        skeleton, bundle = assemble_episode(descriptor, groups, bundles, index)
        nominal = {gid: {a: COMMON_CONSTANTS['initial_settle_s']+distance/skeleton['cruise_speed_m_s']
                         for a, distance in group['nominal_core_distances_m'].items()}
                   for gid, group in groups.items()}
        plans = compose_timing_plans(skeleton, nominal)
        interval = episode_interval_check(skeleton, bundle, plans)
        if any(interval[mode]['below_warning'] for mode in ('synchronous', 'sequential')):
            reason = 'nominal_whole_episode_spacing'
            reasons[reason] += 1
            record = _candidate_record(index, 'nominal_spacing', reason, draws)
            record['interval'] = interval
            record['local_searches']=local_searches
            records.append(record)
            continue
        checks = {**checks, 'nominal_whole_episode_interval': interval}
        candidates.append({'index': index, 'cost': cost, 'cost_by_group': cost_by_group,
                           'skeleton': skeleton, 'bundle': bundle, 'checks': checks})
        record = _candidate_record(index, 'feasible', None, draws)
        record.update(approach_length_m=cost, approach_length_by_group_m=cost_by_group)
        record['local_searches']=local_searches
        records.append(record)
    rng = random.Random(seed_for(descriptor['role_seed'], 'continuous-feasible-pool-order'))
    eligible, selection = choose_eligible(candidates, descriptor['common_draw']['approach_mode'] == 'same_direction', rng)
    eligible_ids = {c['index'] for c in eligible}
    for record in records:
        if record['stage'] == 'feasible' and record['candidate_index'] not in eligible_ids:
            record.update(stage='same_direction_115_percent', reason='task_group_approach_length_exceeds_115_percent')
            record['rejection'] = rejection(record['reason'])
            reasons[record['reason']] += 1
    for item in eligible:
        item['skeleton']['candidate_selection'] = {**selection, 'candidate_index': item['index'],
                                                   'selected_approach_length_m': item['cost'],
                                                   'selected_approach_length_by_group_m': item['cost_by_group']}
    report = {'candidate_budget': budget, 'attempted_candidates': len(records),
              'group_attempt_counts': dict(group_attempts), 'rejection_reasons': dict(reasons),
              'group_search_metrics': {gid:{'attempts':group_attempts[gid], 'geometry_wall_s':group_wall[gid]} for gid in group_wall},
              'rejection_class_counts': summarize(records),
              'termination': rejection('no_eligible_candidate_in_registered_budget', scope='skeleton_search', exhausted=True) if not eligible else None,
              'selection': selection, 'eligible_candidate_order': [c['index'] for c in eligible],
              'max_single_agent_calibration_rounds': MAX_CALIBRATION_ROUNDS,
              'solo_flights_run': 0, 'candidates': records}
    return eligible, report


def plan_continuous_group(scene, group, params):
    """Standalone role API uses the same draw and filtering order as the batch."""
    budget = params.get('candidate_budget', CANDIDATE_BUDGET)
    if budget < 200:
        raise ValueError('At least 200 candidates are required')
    ctx = Context(scene, group, params)
    candidates, reasons = [], Counter()
    for index in range(budget):
        result, reason, _ = draw_role(ctx, index)
        if result is None:
            reasons[reason] += 1
            continue
        bundle = RouteBundle(result['routes'], {a: 0. for a in group['members']})
        nominal = {a: 20.+d/ctx.speed for a, d in result['template']['nominal_core_distances_m'].items()}
        plans = timing_plans({**COMMON_CONSTANTS, 'members': group['members'],
                              'column_seed': params.get('column_seed', params['planning_seed'])}, nominal)
        interval = planning_layer_interval_check(bundle, plans, ctx.speed, warning_m=params.get('planning_interval_warning_m', 6.),
            dwells_by_agent={a:r['intermediate_dwell'] for a,r in result['template']['references'].items() if 'intermediate_dwell' in r})
        if any(interval[m]['below_warning'] for m in ('synchronous', 'sequential')):
            reasons['nominal_full_group_spacing'] += 1
            continue
        result['template']['planning_nominal_interval'] = interval
        candidates.append({'index': index, 'cost': result['approach_length_m'], 'bundle': bundle, 'template': result['template']})
    eligible, selection = choose_eligible(candidates, not ctx.multi, ctx.rng)
    if not eligible:
        raise PlanningInfeasible('geometry_infeasible', f'continuous candidates: {dict(reasons)}')
    chosen = eligible[0]
    chosen['template']['direction_selection'] = {**selection, 'selected_approach_length_m': chosen['cost'],
                                                'attempted_candidates': budget, 'rejection_reasons': dict(reasons)}
    return chosen['bundle'], chosen['template']
