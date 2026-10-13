"""Frozen-parameter synthetic geometry diagnostics; no task semantics or SITL."""
from __future__ import annotations
import argparse, copy, json, math, sys, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
from numpy.polynomial import polynomial as poly
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from swarm_sim.fast_dynamics.contracts import M2Config,PlantState
from swarm_sim.fast_dynamics.engine import SynchronousEngine
from swarm_sim.fast_dynamics.route_tracker import RouteTracker
from swarm_sim.fast_dynamics.calibration import read_json,sha256
from swarm_sim.fast_dynamics.output_policy import resolve_output_root,assert_new_attempt_path,assert_created_within
from scripts.baseline_fast_dynamics_m3 import save

def scenarios():
    result=[]
    def add(name,points,**meta):
        for speed in (4.,7.,10.):
            result.append(dict(id=f"{name}_{int(speed)}mps",speed=speed,routes=points,**meta))
    for angle in (30,60,90,120,180):
        rad=np.radians(angle)
        add(f"turn_{angle}",[[[0,0,8],[100,0,8],[100+100*np.cos(rad),100*np.sin(rad),8]]],kind="turn",angle_deg=angle)
    for length in (10,20,30):
        add(f"short_{length}",[[[0,0,8],[length,0,8],[length,length,8],[2*length,length,8]]],kind="short",leg_m=length)
    for radius in (50,100,200):
        t=np.linspace(0,2*np.pi,73)
        route=np.c_[radius*np.cos(t),radius*np.sin(t),np.full(len(t),8)].tolist()
        add(f"circle_{radius}",[route],kind="circle",radius_m=radius,angular_step_deg=5)
    add("terminal_hover",[[[0,0,8],[300,0,8]]],kind="straight")
    routes=[]
    for offset in np.arange(4)*np.pi/2:
        t=np.linspace(offset,offset+2*np.pi,73)
        routes.append(np.c_[100*np.cos(t),100*np.sin(t),np.full(len(t),8)].tolist())
    add("four_same_ring",routes,kind="circle",radius_m=100,angular_step_deg=5)
    routes=[]
    for t in np.arange(4)*np.pi/2:
        direction=np.array([np.cos(t),np.sin(t)])
        routes.append([np.r_[direction*106,8].tolist(),np.r_[direction*6,8].tolist()])
    add("four_simultaneous_convergence",routes,kind="convergence",target_separation_m=float(6*np.sqrt(2)))
    return result

def segment_max_speed(segment):
    maxima=[]
    dt=(segment.end_us-segment.start_us)/1e6
    for v,a,j in zip(segment.state.v,segment.state.a,segment.jerk):
        coeff=np.array([v[:2],a[:2],j[:2]/2])
        squared=np.zeros(5)
        for axis in (0,1):squared=poly.polyadd(squared,poly.polymul(coeff[:,axis],coeff[:,axis]))
        roots=poly.polyroots(poly.polyder(squared))
        ts=[0.,dt]+[r.real for r in roots if abs(r.imag)<1e-9 and 0<r.real<dt]
        maxima.append(max(math.sqrt(max(0,poly.polyval(t,squared))) for t in ts))
    return max(maxima)

def segment_minimum_separation(segment):
    duration=(segment.end_us-segment.start_us)/1e6
    answer=None
    for i in range(segment.state.num_agents):
        for j in range(i+1,segment.state.num_agents):
            coeff=np.stack((segment.state.p[i]-segment.state.p[j],segment.state.v[i]-segment.state.v[j],
                (segment.state.a[i]-segment.state.a[j])/2,(segment.jerk[i]-segment.jerk[j])/6))
            squared=np.zeros(7)
            for axis in (0,1,2):squared=poly.polyadd(squared,poly.polymul(coeff[:,axis],coeff[:,axis]))
            roots=poly.polyroots(poly.polyder(squared))
            ts=[0.,duration]+[r.real for r in roots if abs(r.imag)<1e-9 and 0<r.real<duration]
            distance=math.sqrt(max(0,min(poly.polyval(t,squared) for t in ts)))
            answer=distance if answer is None else min(answer,distance)
    return answer

def maneuver_diagnostics(route,witnesses,times,positions,velocities):
    """Sampled motion diagnostics; delayed braking must not fall outside a time window."""
    turns=[]
    by_node={w["node_index"]:w["t_us"]/1e6 for w in witnesses}
    for node in range(1,len(route)-1):
        if not all(k in by_node for k in (node-1,node,node+1)):continue
        radius=.25*min(np.linalg.norm(route[node,:2]-route[node-1,:2]),
                       np.linalg.norm(route[node+1,:2]-route[node,:2]))
        mask=(times>=by_node[node-1])&(times<=by_node[node+1])
        mask &= np.linalg.norm(positions[:,:2]-route[node,:2],axis=1)<=radius
        turns.append(dict(node=node,neighborhood_radius_m=float(radius),samples=int(mask.sum()),
            minimum_speed_m_s=float(np.linalg.norm(velocities[mask,:2],axis=1).min()) if mask.any() else None))
    terminal=None
    if len(route)-1 in by_node:
        direction=route[-1,:2]-route[-2,:2];direction=direction/np.linalg.norm(direction)
        mask=times>=by_node[len(route)-1]
        progress=(positions[mask,:2]-route[-1,:2])@direction
        speed=velocities[mask,:2]@direction
        signs=np.sign(speed[np.abs(speed)>.001])
        terminal=dict(maximum_overshoot_m=float(max(0.,progress.max())),
            return_distance_m=float(-np.minimum(np.diff(progress),0.).sum()),
            velocity_direction_reversals=int(np.count_nonzero(np.diff(signs))),
            reversal_speed_deadband_m_s=.001)
    return dict(turn_neighborhoods=turns,terminal=terminal,
        method="committed endpoint samples; turn radius = quarter of shorter adjacent leg, between neighboring original-node witnesses; terminal diagnostics start at final-node witness")

def execute(job):
    case,config,root=job;cfg=M2Config.from_dict(config)
    routes=[np.array(r,float) for r in case["routes"]]
    p=np.stack([r[0] for r in routes]);state=PlantState(p,np.zeros_like(p),np.zeros_like(p))
    engine=SynchronousEngine(cfg,state)
    trackers=[RouteTracker(r,case["speed"],cfg.vehicle_profile,cfg.controller,cfg.reference,cfg.engine.step_us) for r in routes]
    length=max(np.linalg.norm(np.diff(r[:,:2],axis=0),axis=1).sum() for r in routes)
    limit_s=max(600.,8*length/case["speed"]+120)
    clock=[];positions=[];velocities=[];accelerations=[];jerks=[];events=[];arrival=[None]*len(routes)
    maxima=dict(speed_m_s=0.,acceleration_m_s2=0.,jerk_m_s3=0.)
    cycle_end=0;hold_start=None;minimum_separation=None
    reverse_distance=np.zeros(len(routes));progress_sign=np.zeros(len(routes));oscillations=np.zeros(len(routes),dtype=int)
    while engine.time_us<int(limit_s*1e6):
        if engine.time_us==cycle_end:cycle_end+=cfg.engine.step_us
        original=copy.deepcopy(trackers)
        desired=np.stack([t.command(engine.state.p[i],engine.state.v[i],engine.state.a[i]) for i,t in enumerate(trackers)])
        engine.step(desired,dt_us=cycle_end-engine.time_us)
        step_events=[(i,e) for i,t in enumerate(trackers) for e in t.observe_segment(engine.last_segment,agent_index=i)]
        controls=[e for _,e in step_events if e["event"] in ("route_primitive_advanced","route_corner_stopped","route_completed") or e["event"]=="route_node_witnessed" and e["node_index"]==0]
        if controls:
            boundary=min(e["t_us"] for e in controls)
            if boundary<engine.time_us:
                engine.truncate_last_step(boundary);trackers=original
                step_events=[(i,e) for i,t in enumerate(trackers) for e in t.observe_segment(engine.last_segment,agent_index=i)]
        events.extend(dict(agent=i,**e) for i,e in step_events)
        for i,(before,after) in enumerate(zip(original,trackers)):
            if not before.complete and before.primitive_index==after.primitive_index:
                primitive=before.primitives[before.primitive_index]
                start_progress=primitive.project(engine.last_segment.state.p[i,:2])[0]
                end_progress=primitive.project(engine.state.p[i,:2])[0]
                delta=end_progress-start_progress
                if abs(delta)>0.001:
                    sign=np.sign(delta)
                    if progress_sign[i] and sign!=progress_sign[i]:oscillations[i]+=1
                    progress_sign[i]=sign
                    reverse_distance[i]+=max(0,-delta)
            elif before.primitive_index!=after.primitive_index:
                progress_sign[i]=0
        distance=segment_minimum_separation(engine.last_segment)
        if distance is not None:minimum_separation=distance if minimum_separation is None else min(minimum_separation,distance)
        maxima["speed_m_s"]=max(maxima["speed_m_s"],segment_max_speed(engine.last_segment))
        maxima["acceleration_m_s2"]=max(maxima["acceleration_m_s2"],float(np.linalg.norm(engine.state.a[:,:2],axis=1).max()))
        maxima["jerk_m_s3"]=max(maxima["jerk_m_s3"],float(np.linalg.norm(engine.last_jerk,axis=1).max()))
        clock.append(engine.time_us/1e6);positions.append(engine.state.p.copy());velocities.append(engine.state.v.copy())
        accelerations.append(engine.state.a.copy());jerks.append(engine.last_jerk.copy())
        done=[]
        for i,t in enumerate(trackers):
            ok=t.complete and np.linalg.norm(engine.state.p[i]-routes[i][-1])<=.1 and np.linalg.norm(engine.state.v[i])<=.05
            done.append(ok)
            if ok and arrival[i] is None:arrival[i]=engine.time_us/1e6
        if all(done):
            if hold_start is None:hold_start=engine.time_us
            if engine.time_us-hold_start>=2_000_000:break
        else:hold_start=None
    times=np.array(clock);p=np.array(positions);v=np.linalg.norm(np.array(velocities)[:,:,:2],axis=2)
    per_agent=[]
    for i,(route,t) in enumerate(zip(routes,trackers)):
        witnesses=t.witnesses
        # Independent ordered spatial witness check on committed endpoints.
        cursor=0;visits=[]
        for target in route:
            possible=np.flatnonzero(np.linalg.norm(p[cursor:,i,:2]-target[:2],axis=1)<=.5)
            if not len(possible):break
            cursor+=int(possible[0]);visits.append(float(times[cursor]))
        a=route[:-1,:2];delta=np.diff(route[:,:2],axis=0);squared=(delta**2).sum(axis=1)
        error=[]
        # Chunked geometry avoids an unbounded time x waypoint array.
        for chunk in np.array_split(p[:,i,:2],max(1,len(p)//1000)):
            fraction=np.clip(((chunk[:,None,:]-a)*delta).sum(axis=2)/squared,0,1)
            distance=np.linalg.norm(chunk[:,None,:]-(a+fraction[:,:,None]*delta),axis=2)
            error.extend(distance.min(axis=1))
        maneuver=maneuver_diagnostics(route,witnesses,times,p[:,i],np.array(velocities)[:,i])
        turn_speeds=[r["minimum_speed_m_s"] for r in maneuver["turn_neighborhoods"] if r["minimum_speed_m_s"] is not None]
        turn_spaces=[];leg_peaks=[]
        for w in witnesses:
            node=w["node_index"]
            if 0<node<len(route)-1:
                previous=witnesses[node-1]["t_us"]/1e6
                following=witnesses[node+1]["t_us"]/1e6 if node+1<len(witnesses) else times[-1]
                incoming=np.flatnonzero((times>=previous)&(times<=w["t_us"]/1e6)&(v[:,i]>=.95*case["speed"]))
                outgoing=np.flatnonzero((times>=w["t_us"]/1e6)&(times<=following)&(v[:,i]>=.95*case["speed"]))
                turn_spaces.append(dict(node=node,
                    incoming_braking_m=None if not len(incoming) else float(np.linalg.norm(p[incoming[-1],i,:2]-route[node,:2])),
                    outgoing_acceleration_m=None if not len(outgoing) else float(np.linalg.norm(p[outgoing[0],i,:2]-route[node,:2]))))
        for left,right in zip(witnesses,witnesses[1:]):
            window=(times>=left["t_us"]/1e6)&(times<=right["t_us"]/1e6)
            if window.any():leg_peaks.append(float(v[window,i].max()))
        radial=None
        if case["kind"]=="circle":radial=float(np.abs(np.linalg.norm(p[:,i,:2],axis=1)-case["radius_m"]).max())
        # Backtracking around a turn can be intended; report separately from missed ordered visits.
        path_length=float(np.linalg.norm(np.diff(p[:,i,:2],axis=0),axis=1).sum())
        route_length=float(np.linalg.norm(np.diff(route[:,:2],axis=0),axis=1).sum())
        per_agent.append(dict(ordered_endpoint_visits=len(visits),expected_nodes=len(route),all_nodes= len(visits)==len(route),
            maneuver_diagnostics=maneuver,
            route_complete=t.complete,arrival_s=arrival[i],turn_minimum_speeds_m_s=turn_speeds,turn_spaces=turn_spaces,
            leg_peak_speeds_m_s=leg_peaks,nominal_speed_on_every_leg=bool(leg_peaks) and len(leg_peaks)==len(route)-1 and min(leg_peaks)>=.95*case["speed"],
            actual_path_length_m=path_length,planned_path_length_m=route_length,
            reverse_distance_on_current_primitive_m=float(reverse_distance[i]),progress_direction_reversals=int(oscillations[i]),
            maximum_polyline_deviation_m=float(max(error)),maximum_radius_error_m=radial,
            terminal_error_m=float(np.linalg.norm(p[-1,i]-route[-1])),terminal_speed_m_s=float(v[-1,i]),
            cruise_maximum_m_s=float(v[:,i].max()),witnesses=witnesses))
    separation=None
    for i in range(len(routes)):
        for j in range(i+1,len(routes)):
            d=float(np.linalg.norm(p[:,i]-p[:,j],axis=1).min())
            separation=d if separation is None else min(separation,d)
    targets=np.stack([r[-1] for r in routes])
    result=dict(case=case,config_unchanged=True,complete=all(r["route_complete"] and r["all_nodes"] for r in per_agent) and hold_start is not None,
        simulated_s=engine.time_us/1e6,limit_s=limit_s,maxima=maxima,
        within_limits=maxima["speed_m_s"]<=cfg.vehicle_profile.max_speed_xy_m_s+1e-8 and maxima["acceleration_m_s2"]<=cfg.vehicle_profile.max_accel_xy_m_s2+1e-8 and maxima["jerk_m_s3"]<=cfg.vehicle_profile.max_jerk_m_s3+1e-8,
        agents=per_agent,minimum_separation_m=minimum_separation,minimum_separation_sampled_m=separation,
        arrival_spread_s=max(arrival)-min(arrival) if all(x is not None for x in arrival) else None,
        geometric_metric_sampling="committed step endpoints, at most 20 ms; engineering sampled maxima, not continuous extrema; speed exact polynomial extrema",
        terminal_hold_s=0 if hold_start is None else (engine.time_us-hold_start)/1e6)
    dest=Path(root)/case["id"];dest.mkdir(exist_ok=False)
    save(dest/"result.json",result);save(dest/"events.json",events)
    np.savez_compressed(dest/"state.npz",time=times,p=p,v=np.array(velocities),a=np.array(accelerations),jerk=np.array(jerks),speed=v)
    return result

def safe_execute(job):
    try:
        return execute(job)
    except Exception as exc:
        case,_,root=job
        error=dict(status="P0_STOP",case=case,error=repr(exc),traceback=traceback.format_exc())
        dest=Path(root)/case["id"];dest.mkdir(exist_ok=True)
        save(dest/"P0_error.json",error)
        return error

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-record",type=Path,required=True);parser.add_argument("--internal-report",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True);parser.add_argument("--workers",type=int,default=4)
    args=parser.parse_args()
    if not 1<=args.workers<=4:parser.error("workers must be 1..4")
    freeze=read_json(args.freeze_record);internal=read_json(args.internal_report)
    if freeze["status"]!="FROZEN" or not freeze["tiers"]["hard"]["passed"] or sha256(freeze["config_path"])!=freeze["config_sha256"]:parser.error("valid parameter freeze required")
    if internal["status"] not in ("COMPLETE","FALLBACK_DEFAULT") or internal["config_sha256"]!=freeze["config_sha256"]:parser.error("one-time internal comparison not completed")
    root=resolve_output_root()["root"];out=assert_new_attempt_path(args.output,root,kind="synthetic high-speed diagnostics")
    out.mkdir();assert_created_within(out,root);config=read_json(freeze["config_path"]);cases=scenarios()
    save(out/"registration.json",dict(cases=cases,config_sha256=freeze["config_sha256"],criterion="all ordered nodes, 0.1 m / 0.05 m/s stop held 2 s, capability limits; report nominal speed attainment separately; sampled geometric tolerances 0.5 m; simultaneous spread <= 0.02 s"))
    rows=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(safe_execute,(c,config,str(out))) for c in cases]
        for future in as_completed(futures):
            if future.cancelled():continue
            row=future.result();rows.append(row);rows.sort(key=lambda r:r["case"]["id"])
            if row.get("status")=="P0_STOP":
                for pending in futures:pending.cancel()
                save(out/"STOP.json",row)
            save(out/"summary.json",dict(rows=rows,config_sha256=freeze["config_sha256"]))
            print(json.dumps(dict(case=row["case"]["id"],done=len(rows),total=len(cases),complete=row.get("complete"),status=row.get("status","COMPLETE"))),flush=True)
    return int(any(row.get("status")=="P0_STOP" for row in rows))

if __name__=="__main__":raise SystemExit(main())
