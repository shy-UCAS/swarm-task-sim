"""Branch a referenced regular episode at an observed, seeded alert-band frame."""
from copy import deepcopy
import math
import random
import numpy as np

from task_v07.geometry import geometry_facts
from task_v07.planning import clean_route, seed_for
from .contracts import RouteBundle, P0ContractError
from .formation_role_planners import Context
from .geometry_checks import check_retreat_point, check_polyline
from .pipeline import role_parameters
from .role_planners import PlanningInfeasible


def prefix_route(points, position):
    points = np.asarray(points, float)
    legs = np.diff(points, axis=0)
    fractions = np.clip(np.sum((position - points[:-1]) * legs, axis=1) / np.sum(legs * legs, axis=1), 0., 1.)
    projected = points[:-1] + fractions[:, None] * legs
    index = int(np.argmin(np.linalg.norm(projected - position, axis=1)))
    result = points[:index + 1].tolist()
    if np.linalg.norm(np.asarray(result[-1]) - position) < 1.:
        result[-1] = position.tolist()
    else:
        result.append(position.tolist())
    return result


def plan_abort(scene, source_descriptor, source_task, source_run, abort_descriptor):
    task = deepcopy(source_task)
    gid = task['main_group_id']
    if gid is None or task['group_skeletons'][gid]['role'] != 'intrusion':
        raise P0ContractError('Referenced main task group is not intrusion')
    group = task['group_skeletons'][gid]
    ids = list(source_run['agent_ids'])
    columns = [ids.index(a) for a in group['members']]
    facility = next(e for e in scene['entities'] if e['id'] == group['target_id'])
    offsets = {e['layer']: e['offset_m'] for e in scene['entities'] if e.get('facility_id') == group['target_id']}
    distance = geometry_facts(facility['geometry'], source_run['p'][:, columns, :2])['signed_distance_m']
    # A finite geometric planning pad leaves space for the frozen point-mass
    # model to turn; this does not change the observed abort predicates.
    pad = max(50., source_task['cruise_speed_m_s'] ** 2 / 3.75 + 15.)
    candidate = (distance < offsets['alert'] - 5.) & (distance > offsets['protected'] + pad)
    before_any_protected = np.logical_and.accumulate(~(distance <= offsets['protected']).any(axis=1))
    frames = np.flatnonzero(candidate.all(axis=1) & before_any_protected)
    if not len(frames):
        raise PlanningInfeasible('kinematic_infeasible', 'No common observed main-group frame after alert entry and with turn clearance before protected entry')
    seed = seed_for(abort_descriptor['role_seed'], 'abort-observed-frame')
    rng = random.Random(seed)
    frame = int(rng.choice(frames.tolist()))
    stamp = int(source_run['time_us'][frame])
    registered = next(g for g in source_descriptor['task_groups'] if g['group_id'] == gid)
    context = Context(scene, {**registered, 'role': 'feint'}, role_parameters(source_descriptor, registered))
    branch_routes, merged_routes = {}, {}
    chosen_ends = []
    for a in group['members']:
        position = source_run['p'][frame, ids.index(a)]
        outward = position[:2] - context.center
        outward /= np.linalg.norm(outward)
        angle = math.atan2(outward[1], outward[0])
        endpoint, departure = None, None
        for shift in [0., *[sign * k * .05 for k in range(1, 8) for sign in (1, -1)]]:
            direction = np.array([math.cos(angle + shift), math.sin(angle + shift)])
            end = context.retreat(position[:2], direction)
            if end is None or any(np.linalg.norm(end - old) < 35. for old in chosen_ends):
                continue
            route = context.planner().path(position[:2].tolist(), end.tolist())
            if route is not None:
                endpoint, departure = end, route
                break
        if endpoint is None:
            raise PlanningInfeasible('geometry_infeasible', f'Abort retreat unavailable: {a}')
        points = clean_route(departure, context.planner())
        route = [[*p, task['task_altitude_m']] for p in points]
        route[0] = position.tolist()
        if not check_retreat_point(scene, endpoint)['valid'] or not check_polyline(scene, route, margin_m=35.)['valid']:
            raise PlanningInfeasible('geometry_infeasible', f'Abort retreat clearance: {a}')
        branch_routes[a] = route
        merged_routes[a] = prefix_route(task['references'][a]['points_enu_m'], position) + route[1:]
        chosen_ends.append(endpoint)
        ref = group['references'][a]
        ref.update(points_enu_m=merged_routes[a], endpoint_enu_m=route[-1], retreat_required=True, retreat_warning_clearance_m=200.)
        task['references'][a] = deepcopy(ref)
        group['exclusion_policy'][a][group['target_id']] = 'protected'
        task['exclusion_policy'][a][group['target_id']] = 'protected'
    registration = {'source_skeleton_id': source_task['skeleton_id'],
                    'source_episode_id': source_task['skeleton_id'] + '_synchronous',
                    'main_group_id': gid, 'branch_time_us': stamp, 'branch_frame': frame,
                    'random_seed': seed, 'eligible_observed_frame_count': len(frames),
                    'planning_turn_clearance_m': pad,
                    'observed_predicate': 'alert entered, protected never entered, observed turn followed by warning exit and own retreat arrival'}
    group['abort_observation'] = deepcopy(registration)
    task['abort_observation'] = registration
    task['route_switch'] = {'time_us': stamp, 'routes_by_agent': branch_routes,
                            'initial_routes_by_agent': {a: source_task['references'][a]['points_enu_m'] for a in ids}}
    task['skeleton_id'] = abort_descriptor['skeleton_id']
    for sub in task['group_skeletons'].values():
        sub['skeleton_id'] = task['skeleton_id']
    paths = {a: task['references'][a]['points_enu_m'] for a in ids}
    return task, RouteBundle(paths, {a: 0. for a in ids}), registration


def verify_abort_prefix(source_run, aborted_run, branch_time_us):
    if source_run['agent_ids'] != aborted_run['agent_ids']:
        raise P0ContractError('Abort changed physical ID columns')
    left = source_run['time_us'] < branch_time_us
    right = aborted_run['time_us'] < branch_time_us
    for key in ('time_us', 'p', 'v', 'a'):
        if not np.array_equal(source_run[key][left], aborted_run[key][right]):
            raise P0ContractError(f'Abort diverged before observed branch: {key}')
    return {'status': 'PASS', 'prefix_frames': int(left.sum()), 'branch_time_us': int(branch_time_us),
            'checked_exact_arrays': ['time_us', 'p', 'v', 'a']}
