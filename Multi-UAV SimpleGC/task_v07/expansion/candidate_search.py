"""Finite continuous geometry pools, filtered before single-agent calibration."""
from collections import Counter
from copy import deepcopy
import random
import time

from task_v07.planning import seed_for
from task_v07.unified.config import load_generator
from .contracts import RouteBundle, P0ContractError
from .formation_role_planners import Context
from .continuous_geometry import draw_role
from .pipeline import plan_group, role_parameters, COMMON_CONSTANTS, timing_plans
from .candidate_constraints import bearing_allowed
from .geometry_checks import planning_layer_interval_check
from .role_planners import PlanningInfeasible
from .search_diagnostics import rejection, summarize

CANDIDATE_BUDGET = 200
MAX_CALIBRATION_ROUNDS = load_generator()["calibration"]["max_rounds"]


class DrawnPlanner:
    legacy_vertical_slice = False

    def __init__(self, result):
        self.result = result

    def plan_with_template(self, scene, group, parameters):
        return RouteBundle(self.result['routes'], {a: 0. for a in group['members']}), self.result['template']


def choose_eligible(candidates, same_direction, rng):
    ratio = load_generator()["combination"]["same_direction_length_ratio_max"]
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
        return all(cost/bounds[g] <= ratio if bounds[g] else cost == 0 for g, cost in costs.items())
    eligible = [c for c in candidates if not same_direction or within_bound(c)]
    rng.shuffle(eligible)
    return eligible, {'minimum_approach_length_m': minimum, 'maximum_ratio': ratio if same_direction else None,
                      'minimum_approach_length_by_group_m': minima,
                      'ratio_scope': 'each task group independently within whole-episode feasible pool',
                      'feasible_candidates': len(candidates), 'eligible_candidates': len(eligible),
                      'selection_order': 'feasible candidates -> configured same-direction length ratio -> private random order -> bounded solo rehearsals'}


def _candidate_record(index, stage, reason, draws, evidence=None):
    return {'candidate_index': index, 'stage': stage, 'reason': reason, 'draws_by_group': draws,
            'rejection': rejection(reason, evidence=evidence) if reason else None}


def episode_candidate_pool(scene, descriptor, budget=CANDIDATE_BUDGET):
    from .group_candidate_pool import independent_episode_pool
    return independent_episode_pool(scene, descriptor, budget)

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
