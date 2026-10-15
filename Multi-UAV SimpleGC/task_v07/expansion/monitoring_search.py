"""Bounded local repairs retain the sampled radius and successful ingress."""
import math
import time
from collections import Counter
import numpy as np
from task_v07.expansion.geometry_checks import check_retreat_point
from .monitoring_phases import shared_phase_candidates
from .warning_approach import warning_ingress

INGRESS_BUDGET=8
ROTATION_BUDGET=4
RETREAT_DIRECTION_BUDGET=16
RETREAT_DISTANCE_BUDGET=24


def local_monitoring(ctx,angle,radius,draw):
    from .monitoring_deployment import monitoring_candidate
    ctx._deployment_planners={}
    trace={'radius_m':radius,'phase_search':{},'ingress_attempts':[], 'deployment_attempts':[],
           'budgets':{'ingress':INGRESS_BUDGET,'phase_variants':4,'rotations_per_variant':ROTATION_BUDGET,
                      'retreat_directions_per_agent':RETREAT_DIRECTION_BUDGET,'retreat_distances_per_direction':RETREAT_DISTANCE_BUDGET}}
    ctx.local_search_trace=trace
    phases=shared_phase_candidates(ctx,radius,staged=True,diagnostics=trace['phase_search'])
    feasible=[p for p in phases if p['estimated_max_interval_s']<=p['allowed_interval_s']]
    if not feasible:return None,'monitoring_phase_search_budget_exhausted'
    # Every nuisance proposal uses the original unconditional uniform range.
    # No clipped feasible-radius interval or conditional parameter sampler.
    ingress=None
    for attempt in range(INGRESS_BUDGET):
        if attempt:
            angle=ctx.rng.uniform(0.,2*math.pi)
            ctx.collection_clearance_m=ctx.rng.uniform(*ctx.params.get('collection_range_m',(150.,650.)))
        start=time.perf_counter()
        ingress,reason=warning_ingress(ctx,angle)
        trace['ingress_attempts'].append({'index':attempt,'entry_rotation_rad':angle,
            'collection_clearance_m':ctx.collection_clearance_m,'reason':reason,'wall_s':time.perf_counter()-start})
        if ingress is not None:break
    if ingress is None:return None,'monitoring_ingress_search_budget_exhausted'
    # Keep ingress when changing the coupled group phase/rotation component.
    first_rotation=ctx.work_angle
    for variant,phase in enumerate(feasible):
        for rotation in range(ROTATION_BUDGET):
            ctx.work_angle=first_rotation if variant==rotation==0 else ctx.rng.uniform(0.,2*math.pi)
            start=time.perf_counter()
            result,reason=monitoring_candidate(ctx,angle,radius,phase_diagnostic=phase,ingress_override=ingress)
            trace['deployment_attempts'].append({'phase_variant':variant,'rotation_index':rotation,
                'work_rotation_rad':ctx.work_angle,'reason':reason,'wall_s':time.perf_counter()-start})
            if result is not None:
                draw.update(entry_rotation_rad=angle,work_rotation_rad=ctx.work_angle,
                            collection_clearance_m=ctx.collection_clearance_m,orbit_phases_rad=phase['phases'])
                return result,None
    return None,'monitoring_deployment_search_budget_exhausted'


def local_retreat(ctx,point,phi,planner):
    """Do not discard a complete member route because its first retreat fails."""
    directions=[phi+x for x in (0.,math.pi/6,-math.pi/6,math.pi/3,-math.pi/3,math.pi/2,-math.pi/2,math.pi)]
    directions += [ctx.rng.uniform(0.,2*math.pi) for _ in range(RETREAT_DIRECTION_BUDGET-len(directions))]
    attempts=0;reasons=Counter();started=time.perf_counter()
    for angle in directions:
        outward=np.array([math.cos(angle),math.sin(angle)])
        for _ in range(RETREAT_DISTANCE_BUDGET):
            attempts+=1
            q=np.asarray(point)+ctx.rng.uniform(100.,3500.)*outward
            if not check_retreat_point(ctx.scene,q,warning_clearance_m=ctx.retreat_warning_minimum_m)['valid']:
                reasons['retreat_all_warning_clearance']+=1;continue
            departure=planner.path(np.asarray(point).tolist(),q.tolist())
            if departure is None or not ctx.route_valid([np.asarray(p) for p in departure]):
                reasons['retreat_route_clearance_or_policy']+=1;continue
            ctx.local_search_trace.setdefault('retreat_searches',[]).append({'attempts':attempts,'wall_s':time.perf_counter()-started,'reasons':dict(reasons),'success':True})
            return q,departure
    ctx.local_search_trace.setdefault('retreat_searches',[]).append({'attempts':attempts,'wall_s':time.perf_counter()-started,'reasons':dict(reasons),'success':False})
    return None,None
