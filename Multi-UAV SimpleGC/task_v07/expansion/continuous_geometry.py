"""One continuous private geometry draw; no flights or role acceptance changes."""
from collections import defaultdict
import math
import random

import numpy as np

from task_v07.geometry import geometry_facts
from task_v07.planning import seed_for
from task_v07.execution import departure_delays
from .contracts import RouteBundle
from .formation_role_planners import Context, RadialFormationPlanner, core_path_length
from .role_planners import TransitPlanner, _Context, ray_point_at_clearance
from .area_search import AreaSearchPlanner, planned_core_distance


def nominal_core_distances(ctx, result):
    """Planning estimates only. Actual core events stay in labels.measure."""
    template = result['template']
    distances = {}
    for agent, path in result['routes'].items():
        points = np.asarray(path)[:, :2]
        ref = template['references'][agent]
        if ctx.role == 'monitoring':
            entry = np.asarray(ref['planned_orbit_entry_enu_m'][:2])
            index = int(np.argmin(np.linalg.norm(points-entry, axis=1)))
            distance = core_path_length(ctx, points, ref, 'monitoring', index)
        elif ctx.role == 'transit':
            distance = planned_core_distance(points, ctx.zones['warning']['geometry'])
        elif ctx.group['execution_method'] == 'area_search':
            distance = planned_core_distance(points, ref['scan_geometry'])
        else:
            kind = 'close_observation' if ctx.role == 'reconnaissance' else ctx.role
            distance = core_path_length(ctx, points, ref, kind)
        if distance is None or not math.isfinite(distance):
            return None
        distances[agent] = distance
    return distances


def random_phase_candidate(ctx, radius):
    """Continuous phases checked under both immutable timing patterns.

    Mix independent angles with stratified random angles/permutations. Neither
    method changes laps, radius bounds, timing assignments, or revisit criteria.
    """
    ids = sorted(ctx.group['members'])
    n = len(ids)
    nominal = 2*math.pi*radius/ctx.speed
    periods = nominal*1.10*np.array([.975, 1., 1.025])
    rotation = 1. if seed_for(ctx.family.get('sampling_seed', 0), f'monitoring-clock-slot:{ctx.slot}') % 2 else -1.
    plans = departure_delays({'members': ids, 'column_seed': ctx.params.get('column_seed', ctx.params['planning_seed']),
                              'sync_window_s': 10.}, {a: 0. for a in ids})
    times = np.array([[plans[mode]['target_event_times_s'][a] for a in ids]
                      for mode in ('synchronous', 'sequential')])
    times -= times.min(axis=1)[:, None]
    if ctx.rng.random() < .5:
        values = np.array([ctx.rng.uniform(0., 2*math.pi) for _ in ids])
        method = 'independent_uniform'
    else:
        positions = list(range(n))
        ctx.rng.shuffle(positions)
        shift = ctx.rng.uniform(0., 2*math.pi)
        values = np.array([shift+(k+ctx.rng.uniform(-.35, .35))*2*math.pi/n for k in positions])
        # Continuous blend of compensation for the two existing patterns.
        blend = ctx.rng.uniform(0., 1.)
        values += rotation*2*math.pi*((1-blend)*times[0]+blend*times[1])/(nominal*1.10)
        method = 'stratified_uniform_with_shared_timing_compensation'
    phase = np.sort((values[None, None, :]-rotation*2*math.pi*times[:, None, :]/periods[None, :, None])%(2*math.pi), axis=-1)
    gaps = np.diff(np.concatenate([phase, phase[..., :1]+2*math.pi], axis=-1), axis=-1)
    maximum = float((gaps*periods[None, :, None]/(2*math.pi)).max())
    minimum = float(gaps.min()*radius)
    # Identical planning safety penalty to the earlier phase candidate check.
    score = maximum+max(0., 20.-minimum)*10.
    return {'phases': dict(zip(ids, (values%(2*math.pi)).tolist())),
            'estimated_max_interval_s': score, 'estimated_period_range_s': periods.tolist(),
            'allowed_interval_s': 1.5*nominal/n, 'random_draw_method': method,
            'basis': 'planning estimate only; measured 10 Hz audit is required'}


def projection_support(geometry, center, direction):
    if geometry['type'] == 'Circle':
        return float((np.asarray(geometry['center_m'])-center) @ direction)+geometry['radius_m']
    return float(((np.asarray(geometry['vertices_m'])-center) @ direction).max())+geometry.get('buffer_m', 0.)


class ContinuousTransit(TransitPlanner):
    def _point_on_line(self, ctx, origin, direction, clearance, sign, planner):
        if sign < 0:
            clearance = max(clearance, ctx.collection_clearance_m)
        point = ray_point_at_clearance(ctx.warning, origin, sign*direction, clearance)
        return point if planner is None or planner.free(point.tolist()) else None

    def offsets(self, ctx, direction, normal, sigma, count, spacing, position_fraction):
        # Exact support bounds, followed by the existing chord predicates.
        # Bisection finds a bound; the actual block offset is a continuous draw.
        axis = sigma*normal
        low = projection_support(ctx.alert_keep, ctx.center, axis)+1e-4
        high = projection_support(ctx.warning, ctx.center, axis)-1e-4
        if high <= low or self._chord(ctx, direction, normal, sigma*low) is None:
            return None
        lower, upper = low, high
        for _ in range(32):
            mid = (lower+upper)/2
            if self._chord(ctx, direction, normal, sigma*mid) is None:
                upper = mid
            else:
                lower = mid
        width = (count-1)*spacing
        if lower-low < width:
            return None
        first = low+position_fraction*(lower-width-low)
        chords = [self._chord(ctx, direction, normal, sigma*(first+i*spacing)) for i in range(count)]
        return None if any(c is None for c in chords) else sorted(chords, key=lambda c: c['offset'])

    def draw(self, ctx, angle):
        transit = getattr(ctx, '_transit_context', None)
        if transit is None:
            transit = _Context(ctx.scene, ctx.group['target_id'], ctx.retreat_warning_minimum_m)
            ctx._transit_context = transit
        transit.collection_clearance_m = ctx.collection_clearance_m+(len(ctx.group['members'])-1)*ctx.family['lateral_spacing_m']/2
        transit.approach_clearance_m = ctx.approach_clearance_m
        relative = getattr(ctx, 'relative_bearings_rad', [i*math.pi for i in range(len(ctx.split))])
        routes, blocks = {}, []
        sigma = ctx.rng.choice((-1., 1.))
        for side, members in enumerate(ctx.split):
            # Public relative angles are preserved; the private global angle rotates all stocks.
            direction = np.array([math.cos(angle+relative[side]), math.sin(angle+relative[side])])
            normal = np.array([-direction[1], direction[0]])
            chords = self.offsets(transit, direction, normal, sigma, len(members), ctx.family['lateral_spacing_m'],
                                  ctx.transit_chord_position_fraction)
            if chords is None:
                return None, 'continuous_parallel_chord_block_unavailable'
            subgroups = defaultdict(list)
            for a in members:
                subgroups[ctx.states[a].get('entry_id', 'none')].append(a)
            ordered = sorted(subgroups.items(), key=lambda item: (float(np.mean([ctx.starts[a] for a in item[1]], axis=0) @ normal), item[0]))
            cursor = 0
            for entry, agents in ordered:
                selected = chords[cursor:cursor+len(agents)]
                cursor += len(agents)
                block, reason = self._block(transit, agents, selected, ctx.starts, direction, normal, side, entry)
                if reason:
                    return None, reason
                routes.update(block.pop('routes'))
                blocks.append(block)
        bundle, template = self._package(transit, sorted(ctx.group['members']), {'routes': routes, 'blocks': blocks},
                                          ctx.altitude, ctx.family['lateral_spacing_m'], ctx.multi, ctx.group['target_id'])
        template['transit']['side_count'] = len(ctx.split)
        first_stock = [r['chord'] for r in routes.values() if r['side'] == 0]
        midpoint = np.mean([(c['entry']+c['exit'])/2 for c in first_stock], axis=0)
        template['work_area_bearing_deg'] = math.degrees(math.atan2(*(midpoint-ctx.center)[::-1])) % 360
        template['transit']['planning']['candidate_sampling'] = 'continuous private bearing and exact-bound chord offset'
        return {'routes': bundle.waypoints_by_agent, 'template': template}, None


def draw_role(ctx, candidate_index):
    """Exactly one outer candidate; all subordinate draws use its private stream."""
    ctx.last_failure_evidence = []
    ctx.rng = random.Random(seed_for(ctx.params.get('geometry_seed', ctx.params['planning_seed']),
                                    f'continuous-candidate:{candidate_index}'))
    ctx.continuous_candidate = True
    ctx.approach_clearance_m = float(ctx.params.get('approach_clearance_m', 35.))
    angle = ctx.rng.uniform(0., 2*math.pi)
    ctx.work_angle = ctx.rng.uniform(0., 2*math.pi)
    ctx.collection_clearance_m = ctx.rng.uniform(150., 650.)
    ctx.station_lateral_shift_m = ctx.rng.uniform(-1., 1.)*ctx.family['lateral_spacing_m']
    draw = {'index': candidate_index, 'entry_rotation_rad': angle, 'work_rotation_rad': ctx.work_angle,
            'collection_clearance_m': ctx.collection_clearance_m, 'station_lateral_shift_m': ctx.station_lateral_shift_m,
            'approach_obstacle_clearance_m': ctx.approach_clearance_m}
    if ctx.role == 'transit':
        # One private position draw per group; each stock maps that common
        # quantile into its own angle-dependent feasible chord interval.
        ctx.transit_chord_position_fraction = ctx.rng.random()
        draw['transit_chord_position_fraction'] = ctx.transit_chord_position_fraction
        result, reason = ContinuousTransit().draw(ctx, angle)
    elif ctx.role == 'monitoring':
        from .monitoring_deployment import monitoring_candidate
        geometry = ctx.geometry
        extent = geometry['radius_m'] if geometry['type'] == 'Circle' else float(np.linalg.norm(np.asarray(geometry['vertices_m'])-ctx.center, axis=1).max())
        low = extent+ctx.zones['alert']['offset_m']+10.
        high = extent+ctx.zones['warning']['offset_m']-35.
        if high <= low:
            ctx.last_failure_evidence = [{'constraint':'original_orbit_radius_interval','lower_m':low,'upper_m':high}]
            return None, 'empty_original_orbit_radius_range', draw
        radius = ctx.rng.uniform(low, high)
        draw['orbit_radius_m'] = radius
        draw['original_orbit_radius_range_m'] = [low, high]
        draw['monitoring_laps'] = 2+(seed_for(ctx.family.get('sampling_seed', 0), f'monitoring-laps-slot:{ctx.slot}') % 2)
        draw['monitoring_rotation_sign'] = 1. if seed_for(ctx.family.get('sampling_seed', 0), f'monitoring-clock-slot:{ctx.slot}') % 2 else -1.
        samples = ctx.center+radius*np.c_[np.cos(np.linspace(0, 2*math.pi, 129)), np.sin(np.linspace(0, 2*math.pi, 129))]
        distances = geometry_facts(geometry, samples)['signed_distance_m']
        if np.any(distances <= ctx.zones['alert']['offset_m']+5.) or np.any(distances >= ctx.zones['warning']['offset_m']-5.) or not ctx.route_valid(samples):
            from .search_diagnostics import ring_evidence
            ctx.last_failure_evidence = ring_evidence(ctx, samples)
            return None, 'closed_orbit_cannot_clear_exact_restrictions_and_alert_policy', draw
        phases = random_phase_candidate(ctx, radius)
        draw['orbit_phases_rad'] = phases['phases']
        result, reason = monitoring_candidate(ctx, angle, radius, phase_diagnostic=phases)
    elif ctx.group['execution_method'] == 'area_search':
        span, area = ctx.rng.uniform(30., 90.), ctx.rng.uniform(200000., 600000.)
        ctx.strip_overlap_fraction = ctx.rng.uniform(.15, .30)
        draw.update(sector_angle_deg=span, sector_area_m2=area, strip_overlap_fraction=ctx.strip_overlap_fraction)
        result, reason = AreaSearchPlanner().candidate(ctx, ctx.work_angle, span, area_m2=area, ingress_angle=angle)
    else:
        planner = RadialFormationPlanner()
        planner.kind = 'close_observation' if ctx.role == 'reconnaissance' else ctx.role
        from .operation_parameters import draw_radial_parameters
        ctx.operation_parameters, reason = draw_radial_parameters(ctx, angle, planner.kind)
        draw.update(ctx.operation_parameters)
        if reason:
            return None, reason, draw
        result, reason = planner.attempt(ctx, angle)
    if reason:
        return None, reason, draw
    distances = nominal_core_distances(ctx, result)
    if distances is None:
        return None, 'nominal_original_core_event_unavailable', draw
    template = result['template']
    template['nominal_core_distances_m'] = distances
    template['planning_interval_warning_m'] = ctx.params.get('planning_interval_warning_m', 6.)
    template['continuous_geometry_draw'] = draw
    template['formation_split'] = getattr(ctx, 'public_shape', {'numeric_slot': ctx.slot, 'members': ctx.split,
                                                                'shared_between_timing_versions': True})
    template.setdefault('work_area_bearing_deg', math.degrees(ctx.work_angle) % 360)
    result['approach_length_m'] = sum(distances.values())
    return result, None, draw
