"""Approved group-unique parallel patrol lines; reversals never exchange lanes."""
import math
import numpy as np
from scene_v07.geometry import center_of
from task_v07.geometry import geometry_facts, offset_geometry
from .free_space import offset_curve, quantile_interval, TOL
from .route import GeometryRejected, line_interval, clean_joints


def normal_frame(base, point):
    point = np.asarray(point)
    if base["type"] == "Circle":
        normal = point-np.asarray(base["center_m"]); normal /= np.linalg.norm(normal)
        return np.asarray(base["center_m"])+base["radius_m"]*normal, normal
    vertices = np.asarray(base["vertices_m"])
    if np.array_equal(vertices[0],vertices[-1]): vertices = vertices[:-1]
    edges = np.roll(vertices,-1,axis=0)-vertices
    fractions = np.clip(np.sum((point-vertices)*edges,axis=1)/np.sum(edges*edges,axis=1),0,1)
    candidates = vertices+fractions[:,None]*edges
    q = candidates[np.argmin(np.linalg.norm(candidates-point,axis=1))]
    normal = point-q; normal /= np.linalg.norm(normal)
    return q+base.get("buffer_m",0.)*normal, normal


def frame_at_angle(base, rho, angle):
    center = np.asarray(center_of(base)); direction = np.array([math.cos(angle),math.sin(angle)])
    interval = line_interval(offset_geometry(base,rho),center,direction)
    if interval is None: raise GeometryRejected("patrol_contour_unavailable")
    return normal_frame(base,center+interval[1]*direction)


def parallel_paths(base, radii, reference_rho, start, sweep, error):
    """Sample the outer exact contour; corresponding inner offsets have <= error."""
    center = np.asarray(center_of(base))
    frames = [normal_frame(base,p) for p in offset_curve(base,max(radii),error)]
    # Remove the duplicate closing frame; unwrapped polar order is monotone.
    if np.linalg.norm(frames[0][0]+max(radii)*frames[0][1]-frames[-1][0]-max(radii)*frames[-1][1]) < 1e-7:
        frames.pop()
    angles = np.unwrap([math.atan2(*(q+reference_rho*n-center)[::-1]) for q,n in frames])
    low, high = sorted((start,start+sweep)); interior = []
    for k in range(math.floor((low-float(angles[-1]))/(2*math.pi)),math.ceil((high-float(angles[0]))/(2*math.pi))+1):
        for angle,frame in zip(angles,frames):
            value = float(angle)+k*2*math.pi
            if low+1e-10 < value < high-1e-10: interior.append((value,frame))
    interior.sort(key=lambda item:item[0],reverse=sweep<0)
    selected = [frame_at_angle(base,reference_rho,start),*[frame for _,frame in interior],frame_at_angle(base,reference_rho,start+sweep)]
    return [clean_joints([q+rho*n for q,n in selected]) for rho in radii], selected[0][1], selected[-1][1]


def common_arcs(spec,free,radii_by_split,*,ingress_sign=None):
    from .construction import ingress_issues
    base = free.target["geometry"]; center = np.asarray(center_of(base))
    outer = offset_curve(base,max(r for block in radii_by_split for r in block),free.cfg["chord_error_m"])
    radius = max(np.linalg.norm(p-center) for p in outer)
    count = max(8,math.ceil(2*math.pi/(2*math.acos(1-min(1.,free.cfg["chord_error_m"]/radius)))))
    step = 2*math.pi/count; all_points = []; frames_by_split=[]
    for side,block in enumerate(radii_by_split):
        mid = (block[0]+block[-1])/2
        frames=[]
        for i in range(count):
            angle = i*step+spec["public_split"]["relative_bearings_rad"][side]
            q,n = frame_at_angle(base,mid,angle)
            frames.append((q,n))
            all_points.extend(q+rho*n for rho in block)
        frames_by_split.append(frames)
    points = np.asarray(all_points); valid = geometry_facts(free.world,points)["signed_distance_m"] <= -free.cfg["world_margin_m"]+TOL
    for constraint in free.constraints:
        valid &= geometry_facts(constraint["geometry"],points)["signed_distance_m"] >= constraint["margin_m"]-TOL
    good = np.ones(count,bool); cursor = 0
    for block in radii_by_split:
        good &= valid[cursor:cursor+count*len(block)].reshape(count,len(block)).all(axis=1)
        cursor += count*len(block)
    if ingress_sign is not None:
        warning=offset_geometry(base,free.offsets["warning"])
        for i in np.flatnonzero(good):
            slots=[]
            for side,block in enumerate(radii_by_split):
                q,n=frames_by_split[side][i]; heading=ingress_sign*np.array([-n[1],n[0]])
                for j,rho in enumerate(block):
                    point=q+rho*n; hit=line_interval(warning,point,heading)
                    if hit is None or hit[0]>=0:
                        good[i]=False; break
                    slots.append({"split_index":side,"slot_id":f"{side}:{j}",
                        "entry":(point+hit[0]*heading).tolist(),"direction":heading.tolist(),"work":[point.tolist()]})
                if not good[i]: break
            if good[i] and ingress_issues(spec,free,slots): good[i]=False
    if good.all(): return [(0.,2*math.pi)],True
    if not good.any(): return [],False
    first_bad = int(np.flatnonzero(~good)[0]); arcs=[]; start=None
    for k in range(1,count+1):
        i=(first_bad+k)%count; angle=(first_bad+k)*step
        if good[i] and start is None: start=angle
        if not good[i] and start is not None:
            if angle-step>start: arcs.append((start,angle-step))
            start=None
    return arcs,False


def patrol_shape(spec,free,rng,draw,*,force_form=None):
    p=spec["params"]; spacing=spec["family"]["lateral_spacing_m"]; n=len(spec["members"])
    lower=free.offsets["alert"]+p["alert_clearance_m"]
    upper=free.offsets["warning"]-p["warning_inset_m"]-(n-1)*spacing
    draw.update(member_count=n,innermost_interval_m=[lower,upper],narrowed_interval_width_m=upper-lower)
    if upper < lower: raise GeometryRejected("patrol_band_too_narrow",[draw.copy()])
    rho=rng.uniform(lower,upper); radii_by_split=[]; cursor=0
    for stock in spec["public_split"]["members"]:
        radii_by_split.append([rho+(cursor+j)*spacing for j in range(len(stock))]);cursor+=len(stock)
    arcs,complete=common_arcs(spec,free,radii_by_split)
    full=complete and rng.random()<p["full_probability"]
    if force_form is not None:
        if force_form not in ("full","arc"): raise ValueError("Unknown test branch")
        if force_form=="full" and not complete: raise GeometryRejected("full_patrol_unavailable")
        full=force_form=="full"
    sign=rng.choice((-1,1)); laps=rng.uniform(*p["laps"]) if full else None
    traversals=None if full else rng.choice(p["traversals"])
    # Keep the original form/rotation/lap draws. Feasibility is then checked for
    # that sampled rotation, rather than requiring both directions to be clear.
    work_arcs,work_complete=arcs,complete
    arcs,complete=common_arcs(spec,free,radii_by_split,ingress_sign=sign)
    if full and not complete:
        raise GeometryRejected("ingress_line_blocked",[{"rotation_sign":sign,"reason":"full_patrol_entry_domain"}])
    start=math.radians(draw["direction_deg"])
    if full: span=2*math.pi*laps
    else:
        maximum=max((b-a for a,b in arcs),default=0.)
        if math.degrees(maximum)<p["arc_min_deg"]:
            reason="ingress_line_blocked" if max((b-a for a,b in work_arcs),default=0.)>=math.radians(p["arc_min_deg"]) else "patrol_arc_too_short"
            raise GeometryRejected(reason,[{"available_deg":math.degrees(maximum),"rotation_sign":sign}])
        span=rng.uniform(math.radians(p["arc_min_deg"]),maximum)
        if not complete:
            starts=[(a,b-span) for a,b in arcs if b-a>=span]
            start=quantile_interval(starts,rng.random())+(span if sign<0 else 0.)
    draw.update(patrol_form="full" if full else "arc",innermost_offset_m=rho,
                member_offsets_by_split_m=radii_by_split,rotation_sign=sign,planned_laps=laps,
                arc_span_deg=None if full else math.degrees(span),traversals=traversals,
                accepted_start_direction_deg=math.degrees(start)%360)
    base=free.target["geometry"]; warning=offset_geometry(base,free.offsets["warning"])
    slots=[]; ordinal=0
    for side,block in enumerate(radii_by_split):
        angle=start+spec["public_split"]["relative_bearings_rad"][side]
        paths,normal,last_normal=parallel_paths(base,block,(block[0]+block[-1])/2,angle,sign*span,free.cfg["chord_error_m"])
        heading=sign*np.array([-normal[1],normal[0]])
        for j,(radius,path) in enumerate(zip(block,paths)):
            forward=[p.tolist() for p in path]
            work=list(path)
            if not full:
                for turn in range(1,traversals): work.extend((path[::-1] if turn%2 else path)[1:])
            hit=line_interval(warning,path[0],heading)
            if hit is None or hit[0]>=0: raise GeometryRejected("patrol_tangent_gate_unavailable")
            gate=path[0]+hit[0]*heading
            outward=normal if not full and traversals%2==0 else last_normal
            fields={"patrol_lane_index":ordinal,"patrol_offset_m":radius,"patrol_rotation_sign":sign,
                    "patrol_form":draw["patrol_form"],"patrol_forward_points_m":forward,
                    "patrol_reference_offset_m":(block[0]+block[-1])/2,
                    "patrol_reference_lane_offset_m":-sign*(radius-(block[0]+block[-1])/2)}
            slots.append({"split_index":side,"slot_id":f"{side}:{j}","entry":gate.tolist(),
                          "direction":heading.tolist(),"work":[p.tolist() for p in work],
                          "exit_direction":outward.tolist(),"entry_to_work":"shared_tangent_parallel_lane",
                          "reference_fields":fields});ordinal+=1
    return {"kind":"monitoring","slots":slots,"draw":draw,
            "template_fields":{"monitoring":{"form":draw["patrol_form"],"planned_laps":laps,
                "arc_span_deg":draw["arc_span_deg"],"traversals":traversals,"lane_policy":p["lane_policy"]}}}
