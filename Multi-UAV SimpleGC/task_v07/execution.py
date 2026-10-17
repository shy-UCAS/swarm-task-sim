"""Frozen fastsim plant/tracker orchestration; labels consume only exported 10 Hz states."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
from swarm_sim.fast_dynamics.contracts import M2Config, PlantState
from swarm_sim.fast_dynamics.engine import SynchronousEngine
from swarm_sim.fast_dynamics.references import endpoint_velocity
from swarm_sim.fast_dynamics.route_tracker import RouteTracker

FROZEN_SHA256="94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193"
CONFIG_PATH=Path(__file__).resolve().parents[1]/"configs/fast_dynamics/m3_r2_20261013_v1.json"


_LEGACY_DEEPCOPY_TRANSACTIONS = False
_TRANSACTION_STATS = {"steps": 0, "rollbacks": 0}


def _snapshot_tracker(tracker):
    from .dwell import DwellRouteTracker
    if type(tracker) is RouteTracker:
        return ("route", tracker, dict(tracker.__dict__), len(tracker.witnesses), len(tracker.events))
    if type(tracker) is DwellRouteTracker:
        return ("dwell", tracker, dict(tracker.__dict__), len(tracker.events), _snapshot_tracker(tracker.tracker))
    raise TypeError(f"Unsupported tracker type for transaction snapshot: {type(tracker)!r}")


def _restore_tracker(snap):
    kind, obj, attrs = snap[0], snap[1], snap[2]
    obj.__dict__.clear()
    obj.__dict__.update(attrs)
    if kind == "route":
        n_witnesses, n_events = snap[3], snap[4]
        del obj.witnesses[n_witnesses:]
        del obj.events[n_events:]
    else:
        n_events, inner = snap[3], snap[4]
        del obj.events[n_events:]
        _restore_tracker(inner)


def frozen_config():
    raw=CONFIG_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=FROZEN_SHA256:
        raise ValueError("Frozen M3 configuration hash mismatch")
    return M2Config.from_dict(json.loads(raw.decode("utf-8-sig")))


def execute(skeleton, delays_s, *, only_agent=None, time_budget=None, route_switch=None):
    started=time.perf_counter()
    cfg=frozen_config()
    ids=[only_agent] if only_agent else list(skeleton["agent_ids"])
    states={s["agent_id"]:s for s in skeleton["initial_states"]}
    routes=[np.array(skeleton["references"][a]["points_enu_m"]) for a in ids]
    if route_switch is not None:
        if only_agent is not None or route_switch['time_us'] % 100000 or route_switch['time_us'] <= 0:
            raise ValueError('A route switch requires a positive full-episode 10 Hz boundary')
        if set(route_switch['initial_routes_by_agent']) != set(ids) or not set(route_switch['routes_by_agent']) <= set(ids):
            raise ValueError('Route switch changed physical identities')
        routes=[np.asarray(route_switch['initial_routes_by_agent'][a],float) for a in ids]
    initial=PlantState(*[np.array([states[a][key] for a in ids]) for key in
                        ("position_enu_m","velocity_enu_m_s","acceleration_enu_m_s2")])
    engine=SynchronousEngine(cfg,initial)
    trackers=[RouteTracker(r,skeleton["cruise_speed_m_s"],cfg.vehicle_profile,cfg.controller,
                           cfg.reference,cfg.engine.step_us) for r in routes]
    dwell_trackers=[]
    for i,a in enumerate(ids):
        dwell=skeleton["references"][a].get("intermediate_dwell")
        if dwell:
            from .dwell import DwellRouteTracker
            trackers[i]=DwellRouteTracker(routes[i],skeleton["cruise_speed_m_s"],cfg,dwell,
                                          skeleton["terminal_radius_m"],skeleton["terminal_speed_m_s"])
            dwell_trackers.append(i)
    release=np.array([round((skeleton["initial_settle_s"]+delays_s[a])*1e6) for a in ids],dtype=np.int64)
    if np.any(release<0) or np.any(release%100000):
        raise ValueError("Release delays must lie on the nonnegative 10 Hz grid")
    budget=time_budget or completion_budget(skeleton,delays_s)
    limit=round(budget["max_duration_s"]*1e6)
    end_points=np.array([r[-1] for r in routes])
    stop_radius=skeleton.get("stop_radius_m",skeleton["terminal_radius_m"])
    stop_speed=skeleton.get("stop_speed_m_s",skeleton["terminal_speed_m_s"])
    stop_hold=skeleton.get("stop_hold_s",skeleton["terminal_hold_s"])
    hold_counts=np.zeros(len(ids),int)
    cursor=cycle_end=0
    status="timeout"
    switched=False
    while engine.time_us<limit:
        if route_switch is not None and not switched and engine.time_us==route_switch['time_us']:
            for a,points in route_switch['routes_by_agent'].items():
                i=ids.index(a);route=np.asarray(points,float)
                if np.linalg.norm(route[0]-engine.state.p[i])>1e-6:
                    from .expansion.contracts import P0ContractError
                    raise P0ContractError('Observed abort branch state differs from referenced replay')
                trackers[i]=RouteTracker(route,skeleton['cruise_speed_m_s'],cfg.vehicle_profile,cfg.controller,
                                         cfg.reference,cfg.engine.step_us)
                end_points[i]=route[-1]
                hold_counts[i]=0
            switched=True
        if engine.time_us==cycle_end:
            cycle_end=min(limit,cycle_end+cfg.engine.step_us)
        future=release[(release>engine.time_us)&(release<cycle_end)]
        boundary=min(cycle_end,int(future.min())) if len(future) else cycle_end
        active=engine.time_us>=release
        desired=endpoint_velocity(engine.state.p,initial.p,skeleton["cruise_speed_m_s"],
                                  cfg.controller.velocity_response_time_s)
        for i,t in enumerate(trackers):
            if active[i]:
                desired[i]=t.command(engine.state.p[i],engine.state.v[i],engine.state.a[i])
        _TRANSACTION_STATS["steps"] += 1
        if _LEGACY_DEEPCOPY_TRANSACTIONS:
            original=deepcopy(trackers)
        else:
            snapshots=[_snapshot_tracker(t) for t in trackers]
        engine.step(desired,dt_us=boundary-engine.time_us)
        events=[(i,e) for i,t in enumerate(trackers) if active[i]
                for e in t.observe_segment(engine.last_segment,agent_index=i)]
        controls=[e for _,e in events if e["event"] in ("route_primitive_advanced","route_corner_stopped","route_completed")
                  or e["event"]=="route_node_witnessed" and e["node_index"]==0]
        if controls:
            event_boundary=min(e["t_us"] for e in controls)
            if event_boundary<engine.time_us:
                engine.truncate_last_step(event_boundary)
                _TRANSACTION_STATS["rollbacks"] += 1
                if _LEGACY_DEEPCOPY_TRANSACTIONS:
                    trackers=original
                else:
                    for snap in snapshots:
                        _restore_tracker(snap)
                for i,t in enumerate(trackers):
                    if active[i]:
                        t.observe_segment(engine.last_segment,agent_index=i)
        # Runtime stopping uses the same observable 10 Hz samples, never dense semantic events.
        for sample in engine.samples[cursor:]:
            for i in dwell_trackers:
                if sample.t_us>=release[i] and hasattr(trackers[i],'observe_sample'):
                    trackers[i].observe_sample(sample,i)
            ok=(np.linalg.norm(sample.p-end_points,axis=1)<=stop_radius)
            ok&=np.linalg.norm(sample.v,axis=1)<=stop_speed
            ok&=sample.t_us>=release
            hold_counts=np.where(ok,hold_counts+1,0)
        cursor=len(engine.samples)
        if np.all(hold_counts>=round(stop_hold*10)+1) and all(t.complete for t in trackers):
            status="completed"
            break
    samples=engine.samples
    result={"agent_ids":ids,"time_us":np.array([s.t_us for s in samples],dtype=np.int64),
            "p":np.array([s.p for s in samples]),"v":np.array([s.v for s in samples]),
            "a":np.array([s.a for s in samples]),"end_us":engine.time_us,
            "execution_status":status,"wall_s":time.perf_counter()-started,
            "release_s":{a:float(release[i]/1e6) for i,a in enumerate(ids)},
            "config_sha256":FROZEN_SHA256,"time_budget":budget}
    if route_switch is not None:
        result['route_switch_applied']=switched
    return result


def completion_budget(skeleton, delays_s, measured_completion_s=None):
    """Episode deadline from per-agent planned completion, plus 120 s or 20%.

    The bootstrap is only a conservative single-flight runtime guard. Schedules
    use measured 10 Hz core events; paired deadlines use measured 10 Hz finishes.
    """
    if measured_completion_s is None:
        base={}
        for a,reference in skeleton["references"].items():
            points=np.asarray(reference["points_enu_m"])
            length=float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum())
            base[a]=(skeleton["initial_settle_s"]+2*length/skeleton["cruise_speed_m_s"]
                     +10*(len(points)-1)+skeleton.get("stop_hold_s",skeleton["terminal_hold_s"]))
            if "intermediate_dwell" in reference:
                base[a]+=reference["intermediate_dwell"]["duration_s"]
        source="conservative bootstrap: settle + 2*route_length/speed + 10s/leg + hold"
    else:
        if set(measured_completion_s)!=set(delays_s) or any(t is None for t in measured_completion_s.values()):
            raise ValueError("Complete single-agent finish measurements required")
        base=measured_completion_s
        source="single-agent completed endpoint hold on exported 10 Hz truth"
    planned={a:float(base[a]+delays_s[a]) for a in delays_s}
    latest=max(planned.values())
    margin=max(120.,.2*latest)
    return {"basis":source,"single_agent_completion_s":dict(base),
            "planned_completion_times_s":planned,"latest_planned_completion_s":latest,
            "margin_s":margin,"max_duration_s":math.ceil((latest+margin)*10)/10}


def departure_delays(skeleton, measured_event_s):
    if set(measured_event_s)!=set(skeleton["members"]) or any(t is None for t in measured_event_s.values()):
        raise ValueError("Missing measured core event: no schedule may be inferred")
    from .planning import seed_for
    import random
    ids=sorted(skeleton["members"])
    seed=seed_for(skeleton["column_seed"],"timing_schedule_v2")
    rng=random.Random(seed)
    halfwidth=skeleton.get("timing_jitter_halfwidth_s",3.0)
    gap_low,gap_high=skeleton.get("sequential_gap_range_s",[40.0,90.0])
    if not 0<=2*halfwidth<=skeleton["sync_window_s"] or not 40<=gap_low<=gap_high<=90:
        raise ValueError("Invalid jitter/window/gap configuration")
    latest=max(measured_event_s.values())+halfwidth+2.0
    sequential_ids=ids[:]
    rng.shuffle(sequential_ids)
    count=rng.randint(2,len(ids))
    cuts=[0,*sorted(rng.sample(range(1,len(ids)),count-1)),len(ids)]
    groups=[sequential_ids[a:b] for a,b in zip(cuts,cuts[1:])]
    gaps=[rng.uniform(gap_low,gap_high) for _ in range(count-1)]
    centers=[latest]
    for gap in gaps:
        centers.append(centers[-1]+gap)
    plans={}
    for mode in ("synchronous","sequential"):
        batches={a:0 for a in ids} if mode=="synchronous" else {a:i for i,g in enumerate(groups) for a in g}
        nominal=[latest] if mode=="synchronous" else centers
        jitter={a:rng.uniform(-halfwidth,halfwidth) for a in ids}
        targets={a:nominal[batches[a]]+jitter[a] for a in ids}
        delays={a:round(targets[a]-measured_event_s[a],1) for a in ids}
        # Independent uniforms are preserved in supervision; realizable releases
        # are quantized once to the common 0.1 s grid (at most 0.05 s error).
        grid_targets={a:round(measured_event_s[a]+delays[a],1) for a in ids}
        plans[mode]={"schema_version":"v07_timing_plan_v2","random_seed":seed,
                     "batch_by_agent":batches,"batch_count":len(nominal),
                     "batch_sizes":[sum(b==i for b in batches.values()) for i in range(len(nominal))],
                     "batch_centers_s":nominal,"inter_batch_gaps_s":[] if mode=="synchronous" else gaps,
                     "jitter_s":jitter,"jitter_halfwidth_s":halfwidth,
                     "target_event_times_s":targets,"target_event_times_grid_s":grid_targets,
                     "departure_delays_s":delays,"single_agent_measured_core_times_s":dict(measured_event_s),
                     "quantization_s":0.1,"maximum_quantization_error_s":0.05,
                     "basis":"single-agent actual core event on 10 Hz exported truth"}
        for i in range(len(nominal)):
            times=[grid_targets[a] for a in ids if batches[a]==i]
            if max(times)-min(times)>skeleton["sync_window_s"]:
                raise ValueError("Quantized within-batch target spread exceeds sync window")
    return plans
