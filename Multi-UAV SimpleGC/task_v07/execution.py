"""Frozen fastsim plant/tracker orchestration; labels consume only exported 10 Hz states."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from swarm_sim.fast_dynamics.contracts import M2Config, PlantState
from swarm_sim.fast_dynamics.engine import SynchronousEngine
from swarm_sim.fast_dynamics.references import endpoint_velocity
from swarm_sim.fast_dynamics.route_tracker import RouteTracker

FROZEN_SHA256="94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193"
CONFIG_PATH=Path(__file__).resolve().parents[1]/"configs/fast_dynamics/m3_r2_20261013_v1.json"


def frozen_config():
    raw=CONFIG_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=FROZEN_SHA256:
        raise ValueError("Frozen M3 configuration hash mismatch")
    return M2Config.from_dict(json.loads(raw.decode("utf-8-sig")))


def execute(skeleton, delays_s, *, only_agent=None):
    started=time.perf_counter()
    cfg=frozen_config()
    ids=[only_agent] if only_agent else list(skeleton["agent_ids"])
    states={s["agent_id"]:s for s in skeleton["initial_states"]}
    routes=[np.array(skeleton["references"][a]["points_enu_m"]) for a in ids]
    initial=PlantState(*[np.array([states[a][key] for a in ids]) for key in
                        ("position_enu_m","velocity_enu_m_s","acceleration_enu_m_s2")])
    engine=SynchronousEngine(cfg,initial)
    trackers=[RouteTracker(r,skeleton["cruise_speed_m_s"],cfg.vehicle_profile,cfg.controller,
                           cfg.reference,cfg.engine.step_us) for r in routes]
    release=np.array([round((skeleton["initial_settle_s"]+delays_s[a])*1e6) for a in ids],dtype=np.int64)
    if np.any(release<0) or np.any(release%100000):
        raise ValueError("Release delays must lie on the nonnegative 10 Hz grid")
    limit=round(cfg.execution.max_duration_s*1e6)
    end_points=np.array([r[-1] for r in routes])
    hold_counts=np.zeros(len(ids),int)
    cursor=cycle_end=0
    status="timeout"
    while engine.time_us<limit:
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
        original=deepcopy(trackers)
        engine.step(desired,dt_us=boundary-engine.time_us)
        events=[(i,e) for i,t in enumerate(trackers) if active[i]
                for e in t.observe_segment(engine.last_segment,agent_index=i)]
        controls=[e for _,e in events if e["event"] in ("route_primitive_advanced","route_corner_stopped","route_completed")
                  or e["event"]=="route_node_witnessed" and e["node_index"]==0]
        if controls:
            event_boundary=min(e["t_us"] for e in controls)
            if event_boundary<engine.time_us:
                engine.truncate_last_step(event_boundary)
                trackers=original
                for i,t in enumerate(trackers):
                    if active[i]:
                        t.observe_segment(engine.last_segment,agent_index=i)
        # Runtime stopping uses the same observable 10 Hz samples, never dense semantic events.
        for sample in engine.samples[cursor:]:
            ok=(np.linalg.norm(sample.p-end_points,axis=1)<=skeleton["terminal_radius_m"])
            ok&=np.linalg.norm(sample.v,axis=1)<=skeleton["terminal_speed_m_s"]
            ok&=sample.t_us>=release
            hold_counts=np.where(ok,hold_counts+1,0)
        cursor=len(engine.samples)
        if np.all(hold_counts>=round(skeleton["terminal_hold_s"]*10)+1) and all(t.complete for t in trackers):
            status="completed"
            break
    samples=engine.samples
    return {"agent_ids":ids,"time_us":np.array([s.t_us for s in samples],dtype=np.int64),
            "p":np.array([s.p for s in samples]),"v":np.array([s.v for s in samples]),
            "a":np.array([s.a for s in samples]),"end_us":engine.time_us,
            "execution_status":status,"wall_s":time.perf_counter()-started,
            "release_s":{a:float(release[i]/1e6) for i,a in enumerate(ids)},
            "config_sha256":FROZEN_SHA256}


def departure_delays(skeleton, measured_event_s):
    if set(measured_event_s)!=set(skeleton["members"]) or any(t is None for t in measured_event_s.values()):
        raise ValueError("Missing measured core event: no schedule may be inferred")
    # Event times come from independent single-agent exported truth, including settle.
    latest=max(measured_event_s.values())+5.0
    ids=list(skeleton["members"])
    from .planning import seed_for
    import random
    random.Random(seed_for(skeleton["column_seed"],"batch_assignment")).shuffle(ids)
    batch={a:i//2 for i,a in enumerate(ids)}
    return {mode:{a:round(latest+(0 if mode=="synchronous" else batch[a]*skeleton["sequential_gap_s"])
                                 -measured_event_s[a],1) for a in skeleton["members"]}
            for mode in ("synchronous","sequential")},batch

