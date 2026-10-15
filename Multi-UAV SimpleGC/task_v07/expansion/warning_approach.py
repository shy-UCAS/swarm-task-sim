"""Shared corridor entry into the target warning zone, before role deployment.

No timing, speed, role success rule or formation-width rule is changed here.
"""
from collections import defaultdict
import math
import numpy as np

from task_v07.geometry import geometry_facts
from task_v07.planning import clean_route
from .formation_corridors import offset_polyline, shared_reference_corridor, start_line


def warning_ingress(ctx, angle, spacing_m=None):
    from .formation_role_planners import contour_point
    approaches, references, blocks = {}, {}, []
    spacing = ctx.family['lateral_spacing_m'] if spacing_m is None else spacing_m
    relative = getattr(ctx, 'relative_bearings_rad', [i * math.pi for i in range(len(ctx.split))])
    for side, stock in enumerate(ctx.split):
        outward = np.array([math.cos(angle + relative[side]), math.sin(angle + relative[side])])
        direction = -outward
        normal = np.array([-direction[1], direction[0]])
        entries = defaultdict(list)
        for agent in stock:
            entries[ctx.states[agent].get('entry_id', 'none')].append(agent)
        ordered = sorted(entries.values(), key=lambda agents: float(np.mean([ctx.starts[a] for a in agents], axis=0) @ normal))
        layouts = []
        for agents in ordered:
            mean = np.mean([ctx.starts[a] for a in agents], axis=0)
            inward, _ = start_line(ctx.scene, mean)
            first_normal = np.array([-inward[1], inward[0]])
            entry_id = ctx.states[agents[0]].get('entry_id', 'none')
            anchor = np.mean([np.asarray(s['position_enu_m'][:2]) for s in ctx.states.values()
                              if s.get('entry_id', 'none') == entry_id], axis=0)
            scale = spacing / ctx.family['lateral_spacing_m']
            virtual = {a: ctx.starts[a] + (scale-1)*float((ctx.starts[a]-anchor) @ first_normal)*first_normal
                       for a in agents}
            mean = np.mean(list(virtual.values()), axis=0)
            offsets = {a: float((virtual[a] - mean) @ first_normal) for a in agents}
            half = max(abs(x) for x in offsets.values())
            layouts.append((agents, virtual, offsets, half))
        width = sum(2 * half for _, _, _, half in layouts) + spacing * (len(layouts) - 1)
        cursor = -width / 2
        for agents, virtual, offsets, half in layouts:
            hcenter = cursor + half
            cursor += 2 * half + spacing
            margin = 35. + 1.5 * half + 2.
            exterior = ctx.planner(margin, warnings=True)
            origin = ctx.center + hcenter * normal
            lead = None
            # Keep at least 150m of straight motion outside the warning boundary
            # before entry. The final measured 100m cannot include a prior turn.
            for distance in np.arange(200., 3500., 25.):
                point = origin + distance * outward
                clearance = float(geometry_facts(ctx.zones['warning']['geometry'], point)['signed_distance_m'])
                if clearance >= 150. + half and exterior.free(point.tolist()):
                    lead = point
                    break
            if lead is None:
                return None, 'warning_collection_unavailable'
            tail = contour_point(ctx.geometry, ctx.center, outward,
                                 ctx.zones['warning']['offset_m'] - 50., -hcenter)
            if tail is None:
                return None, 'warning_entry_block_does_not_fit'
            corridor, reason = shared_reference_corridor(ctx.scene, agents, virtual, lead, tail,
                exterior, ctx.planner(), form_up_depths=(max(100., 2 * half + 50.), 100., 150., 200., 60.))
            if reason:
                return None, reason
            try:
                reference = clean_route([p.tolist() for p in corridor['reference']], ctx.planner())
            except ValueError:
                return None, 'warning_reference_leg_invalid'
            for agent in agents:
                lane = offset_polyline(reference, offsets[agent])
                if lane is None:
                    return None, 'warning_lane_swallowtail'
                end = contour_point(ctx.geometry, ctx.center, outward,
                                    ctx.zones['warning']['offset_m'] - 50., -(hcenter + offsets[agent]))
                if end is None:
                    return None, 'warning_lane_entry_unavailable'
                lane[-1] = end
                try:
                    points = clean_route([ctx.starts[agent].tolist(), *[p.tolist() for p in lane[1:]]], ctx.planner())
                except ValueError:
                    return None, 'warning_lane_invalid'
                if not ctx.route_valid(points):
                    return None, 'warning_ingress_policy_or_clearance'
                # All route points before the final straight must be exterior;
                # exact segment checks prevent an earlier, accidental visit.
                warning = ctx.zones['warning']['geometry']
                if any(geometry_facts(warning, np.asarray([a, b]), footprint=True)['clearance_m'] <= 0
                       for a, b in zip(points[:-2], points[1:-1])):
                    return None, 'warning_entry_before_shared_straight'
                approaches[agent] = [np.asarray(p) for p in points]
                references[agent] = {'side': side, 'lane_offset_m': offsets[agent],
                    'warning_gate_enu_m': [*end.tolist(), ctx.altitude],
                    'collection_point_enu_m': [*lead.tolist(), ctx.altitude]}
            blocks.append({'side': side, 'members': sorted(agents), 'half_width_m': half,
                           'shared_route_margin_m': margin, 'collection_point_enu_m': [*lead.tolist(), ctx.altitude]})
    return {'routes': approaches, 'references': references, 'blocks': blocks}, None


def deploy_inside_warning(ctx, start, finish, planner=None):
    """Use the existing visibility route and require the whole convex-zone path inside."""
    path = (planner or ctx.planner()).path(np.asarray(start).tolist(), np.asarray(finish).tolist())
    if path is None:
        return None
    if np.any(geometry_facts(ctx.zones['warning']['geometry'], np.asarray(path))['signed_distance_m'] > 1e-6):
        return None
    return [np.asarray(p) for p in path]
