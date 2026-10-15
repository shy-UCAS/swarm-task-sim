"""Private execution-geometry draws; role acceptance constants stay unchanged."""
from collections import defaultdict
import math
import numpy as np

from task_v07.geometry import geometry_facts
from .formation_corridors import start_line


def work_point_spacing(references, kind, speed):
    """Existing role geometry limits, independent of later retreat endpoints."""
    from itertools import combinations
    fields = {'observation_point': ('observation_point_enu_m', 6.)} if kind == 'close_observation' else {
        'depth_point': ('planned_depth_point_enu_m', 15. if speed > 7. else 6.),
        'turn_point': ('planned_turn_point_enu_m', 15. if speed > 7. else 6.)}
    report = {}
    for name, (field, required) in fields.items():
        points = [np.asarray(ref[field], float) for ref in references.values()]
        minimum = min(float(np.linalg.norm(a-b)) for a,b in combinations(points, 2))
        report[name] = {'minimum_m': minimum, 'required_m': required, 'valid': minimum >= required}
    return report


def station_layouts(ctx, angle, spacing):
    """The existing entry-block offsets and width rule, without placing stations."""
    relative = getattr(ctx, 'relative_bearings_rad', [i*math.pi for i in range(len(ctx.split))])
    placements = []
    for side, stock in enumerate(ctx.split):
        theta = getattr(ctx, 'work_angle', angle)+relative[side]
        outward = np.array([math.cos(theta), math.sin(theta)])
        direction = -outward
        normal = np.array([-direction[1], direction[0]])
        entry_blocks = defaultdict(list)
        for a in stock:
            entry_blocks[ctx.states[a].get('entry_id', 'none')].append(a)
        ordered = sorted(entry_blocks.values(), key=lambda agents: float(np.mean([ctx.starts[a] for a in agents], axis=0)@normal))
        layouts = []
        for agents in ordered:
            actual_mean = np.mean([ctx.starts[a] for a in agents], axis=0)
            inward, _ = start_line(ctx.scene, actual_mean)
            first_normal = np.array([-inward[1], inward[0]])
            entry_id = ctx.states[agents[0]].get('entry_id', 'none')
            all_entry = [np.asarray(s['position_enu_m'][:2]) for s in ctx.states.values() if s.get('entry_id', 'none') == entry_id]
            anchor_mean = np.mean(all_entry, axis=0)
            scale = spacing/ctx.family['lateral_spacing_m']
            virtual = {a: ctx.starts[a]+(scale-1)*float((ctx.starts[a]-anchor_mean)@first_normal)*first_normal for a in agents}
            mean = np.mean(list(virtual.values()), axis=0)
            offsets = {a: float((virtual[a]-mean)@first_normal) for a in agents}
            half = max(abs(x) for x in offsets.values())
            layouts.append((agents, offsets, half))
        whole = sum(2*x[2] for x in layouts)+spacing*(len(layouts)-1)
        cursor = -whole/2+getattr(ctx, 'station_lateral_shift_m', 0.)
        for agents, offsets, half in layouts:
            center = cursor+half
            cursor += 2*half+spacing
            placements.extend((a, outward, center+offsets[a]) for a in agents)
    return placements


def draw_radial_parameters(ctx, angle, kind):
    rng = ctx.rng
    if kind == 'feint':
        fraction = rng.uniform(.35, .65)
        return {'feint_group_depth_fraction': fraction,
                'feint_depth_fraction_by_agent': {a: fraction+rng.uniform(-.03, .03) for a in sorted(ctx.group['members'])}}, None
    if kind == 'close_observation':
        return {'observation_alert_clearance_m': rng.uniform(40., 65.),
                'planned_observation_dwell_s': rng.uniform(25., 55.),
                'observation_dwell_method': rng.choice(('hover', 'small_circle'))}, None
    limits = []
    for _, outward, lateral in station_layouts(ctx, angle, float(ctx.family['lateral_spacing_m'])):
        normal = np.array([-outward[1], outward[0]])
        origin = ctx.center-lateral*normal
        limits.append(ctx.zones['protected']['offset_m']-float(geometry_facts(ctx.geometry, origin)['signed_distance_m']))
    maximum = min(limits)
    if maximum-10. <= 25.:
        return {'intrusion_feasible_max_depth_m': maximum}, 'empty_intrusion_depth_interval'
    return {'intrusion_feasible_max_depth_m': maximum, 'intrusion_endpoint_depth_m': rng.uniform(25., maximum-10.),
            'intrusion_depth_range_m': [25., maximum-10.],
            'intrusion_depth_bound_basis': 'maximum common depth reachable from every assigned lateral origin on its outward ray'}, None


def dwell_circle(station, outward, radius, speed, duration):
    """Polygonal arc of nominal duration, within the unchanged observation disk."""
    length = speed*duration
    steps = max(1, math.ceil(length/(2*radius*math.sin(math.pi/6))))
    delta = 2*math.asin(length/(steps*2*radius))
    alpha = math.atan2(outward[1], outward[0])
    return [station+radius*np.array([math.cos(alpha+k*delta), math.sin(alpha+k*delta)]) for k in range(1, steps+1)]
