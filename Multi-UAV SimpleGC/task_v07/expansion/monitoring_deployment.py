"""One shared orbit direction; deployment follows the warning-zone ingress."""
import math
import numpy as np

from task_v07.planning import clean_route, seed_for
from task_v07.visibility import ExactVisibilityPlanner
from .warning_approach import warning_ingress, deploy_inside_warning
from .monitoring_phases import shared_phase_candidates


def monitoring_candidate(ctx, angle, radius, phase_variant=0, *, phase_diagnostic=None, ingress_override=None):
    from .formation_role_planners import core_path_length, VERSION
    role_planner = ctx.planner()
    if phase_diagnostic is None:
        if not hasattr(ctx, '_phase_candidates'):
            ctx._phase_candidates = {}
        if radius not in ctx._phase_candidates:
            ctx._phase_candidates[radius] = shared_phase_candidates(ctx, radius)
        phase_diagnostic = ctx._phase_candidates[radius][phase_variant]
    if phase_diagnostic['estimated_max_interval_s'] > phase_diagnostic['allowed_interval_s']:
        return None, 'nominal_revisit_geometry_infeasible'
    phases = {a: getattr(ctx,'work_angle',angle) + value for a, value in phase_diagnostic['phases'].items()}
    if not hasattr(ctx, '_warning_ingresses'):
        ctx._warning_ingresses = {}
    if ingress_override is not None:
        ingress,reason=ingress_override,None
    elif angle not in ctx._warning_ingresses:
        ctx._warning_ingresses[angle] = warning_ingress(ctx, angle)
        ingress,reason=ctx._warning_ingresses[angle]
    else:
        ingress,reason=ctx._warning_ingresses[angle]
    if reason:
        return None, reason
    laps = 2 + (seed_for(ctx.family.get('sampling_seed', 0), f'monitoring-laps-slot:{ctx.slot}') % 2)
    rotation = 1. if seed_for(ctx.family.get('sampling_seed', 0), f'monitoring-clock-slot:{ctx.slot}') % 2 else -1.
    steps = max(24, int(math.ceil(math.pi/math.acos(1.-min(10./radius, 1.)))))
    deployment_scene = {'world': ctx.scene['world'], 'entities': [
        {'type': 'hard_constraint_obstacle', 'geometry': g} for g in role_planner.obstacles]}
    deployment_scene['entities'].append({'type': 'hard_constraint_obstacle', 'geometry': {
        'type': 'Circle', 'center_m': ctx.center.tolist(), 'radius_m': radius+40.}})
    # Continuous local rotations share the same radius and exact obstacles.
    cache=getattr(ctx,'_deployment_planners',{})
    if not hasattr(ctx,'_deployment_planners'):ctx._deployment_planners=cache
    if radius not in cache:cache[radius]=ExactVisibilityPlanner(deployment_scene,0.)
    deployment=cache[radius]
    tangent_length = math.sqrt((radius+50.)**2-radius**2)
    routes, refs, total = {}, {}, 0.
    for agent in sorted(ctx.group['members']):
        phi = phases[agent]
        entry = ctx.center + radius*np.array([math.cos(phi), math.sin(phi)])
        tangent = rotation*np.array([-math.sin(phi), math.cos(phi)])
        target = entry - tangent_length*tangent
        points = list(ingress['routes'][agent])
        branch = deploy_inside_warning(ctx, points[-1], target, deployment)
        if branch is None:
            return None, 'inside_warning_orbit_phase_deployment_unavailable'
        points.extend(branch[1:])
        points.append(entry)
        ring = [ctx.center + radius*np.array([math.cos(phi+rotation*k*2*math.pi/steps),
                                              math.sin(phi+rotation*k*2*math.pi/steps)])
                for k in range(1, steps*laps+1)]
        points.extend(ring)
        exit_lead = points[-1] + tangent_length*tangent
        if role_planner.visible(points[-1].tolist(), exit_lead.tolist()):
            points.append(exit_lead)
        retreat = None
        if ingress_override is not None:
            from .monitoring_search import local_retreat
            retreat,departure=local_retreat(ctx,points[-1],phi,deployment)
        for delta in (() if ingress_override is not None else (0., math.pi/6, -math.pi/6, math.pi/3, -math.pi/3, math.pi/2, -math.pi/2, math.pi)):
            retreat = ctx.retreat(points[-1], np.array([math.cos(phi+delta), math.sin(phi+delta)]))
            if retreat is not None and deployment.path(points[-1].tolist(), retreat.tolist()) is not None:
                break
            retreat = None
        if retreat is None:
            return None, 'monitoring_retreat_unavailable'
        departure = deployment.path(points[-1].tolist(), retreat.tolist())
        points.extend(np.asarray(p) for p in departure[1:])
        try:
            points = [np.asarray(p) for p in clean_route([p.tolist() for p in points], role_planner)]
        except ValueError:
            return None, 'monitoring_route_leg_invalid'
        if not ctx.route_valid(points):
            return None, 'monitoring_full_route_policy_or_clearance'
        core_index = int(np.argmin(np.linalg.norm(np.asarray(points)-entry, axis=1)))
        total += core_path_length(ctx, points, {}, 'monitoring', core_index)
        routes[agent] = [[*p.tolist(), ctx.altitude] for p in points]
        refs[agent] = {'endpoint_enu_m': [*retreat.tolist(), ctx.altitude], 'retreat_required': True,
                       'retreat_warning_clearance_m': ctx.retreat_warning_minimum_m, 'planned_orbit_entry_enu_m': [*entry.tolist(), ctx.altitude],
                       'planned_orbit_phase_rad': phi, 'orbit_tangent_lead_enu_m': [*target.tolist(), ctx.altitude],
                       'formation_lane': ingress['references'][agent]}
    template = {'role': 'monitoring', 'execution_method': 'monitoring', 'target_id': ctx.group['target_id'],
                'planning_version': VERSION, 'references': refs, 'formation': {'blocks': ingress['blocks']},
                'retreat_warning_minimum_m': ctx.retreat_warning_minimum_m,
                'phase_geometry_estimate': phase_diagnostic,
                'monitoring': {'orbit_center_enu_m': ctx.center.tolist(), 'orbit_radius_m': radius,
                               'track_tolerance_m': 30., 'effective_speed_min_m_s': .5, 'min_loop_duration_s': 5.,
                               'planned_laps': float(laps), 'rotation_sign': rotation,
                               'approach_mode': ctx.params['approach_mode']}}
    return {'routes': routes, 'template': template, 'approach_length_m': total}, None
