"""Shared phase-1 formation corridors and exact parallel lane joins."""
import math
import numpy as np

def offset_polyline(points, offset, max_turn_deg=150.0, arc_step_deg=30.0):
    """Parallel lane at signed left offset of a shared route.

    Inside of a turn: miter join (both offset lines meet). Outside of a turn
    sharper than arc_step_deg: round join (points every <= arc_step_deg at
    radius |offset| about the vertex), so the outer lane stays >= |offset| x
    cos(arc_step/2) from the centre lane's corner; a bevel would cut in to
    |offset| x cos(turn/2). Returns None if a lane leg would reverse
    (swallowtail) or an inside turn is too sharp for a miter.
    """
    P = np.asarray(points, float)
    if offset == 0:
        return [p.copy() for p in P]
    d = np.diff(P, axis=0)
    u = d / np.linalg.norm(d, axis=1)[:, None]
    n = np.stack([-u[:, 1], u[:, 0]], axis=1)
    joints = [[P[0] + offset * n[0]]]
    for i in range(1, len(P) - 1):
        cross = u[i-1, 0] * u[i, 1] - u[i-1, 1] * u[i, 0]
        cos = float(np.clip(u[i-1] @ u[i], -1, 1))
        turn = math.degrees(math.acos(cos))
        if abs(cross) < 1e-12 and cos > 0:
            joints.append([P[i] + offset * n[i]])
        elif offset * cross > 0 or turn <= arc_step_deg:
            if turn > max_turn_deg:
                return None
            joints.append([P[i] + offset * (n[i-1] + n[i]) / (1 + cos)])
        else:
            start = math.atan2(n[i-1, 1], n[i-1, 0])
            sweep = (math.atan2(n[i, 1], n[i, 0]) - start + math.pi) % (2 * math.pi) - math.pi
            steps = math.ceil(abs(math.degrees(sweep)) / arc_step_deg)
            joints.append([P[i] + offset * np.array([math.cos(start + k * sweep / steps), math.sin(start + k * sweep / steps)])
                           for k in range(steps + 1)])
    joints.append([P[-1] + offset * n[-1]])
    for i in range(len(P) - 1):
        leg = joints[i + 1][0] - joints[i][-1]
        if float(leg @ u[i]) < 1.0:
            return None
    return [p for joint in joints for p in joint]

def start_line(scene, point):
    vertices=np.asarray(scene["world"]["geometry"]["vertices_m"],float)
    if np.array_equal(vertices[0],vertices[-1]):vertices=vertices[:-1]
    best=None
    for a,b in zip(vertices,np.roll(vertices,-1,axis=0)):
        edge=b-a;s=np.clip((point-a)@edge/(edge@edge),0,1)
        distance=float(np.linalg.norm(point-(a+s*edge)))
        if best is None or distance<best[0]:
            best=(distance,edge/np.linalg.norm(edge),a)
    _,tangent,a=best
    inward=np.array([-tangent[1],tangent[0]])
    if (vertices.mean(axis=0)-a)@inward<0:inward=-inward
    return inward,tangent


def shared_reference_corridor(scene, agents, starts, lead, tail, planner, clearance_planner, *, form_up_depths=(100.0,60.0,150.0,200.0)):
    """Phase-1 form-up and visibility reference, unchanged numerical operations."""
    shared_start=np.mean([starts[a] for a in agents],axis=0)
    inward,_=start_line(scene,shared_start)
    form_up=next((shared_start+depth*inward for depth in form_up_depths
                  if planner.free((shared_start+depth*inward).tolist())
                  and clearance_planner.visible(shared_start.tolist(),(shared_start+depth*inward).tolist())),None)
    if form_up is None:return None,"form_up_leg_blocked"
    approach=planner.path(form_up.tolist(),lead.tolist())
    if approach is None:return None,"no_shared_route"
    centre=[shared_start]+[np.array(p,float) for p in approach]+[tail]
    first=centre[1]-centre[0]
    first_normal=np.array([-first[1],first[0]])/np.linalg.norm(first)
    return {"reference":centre,"approach":approach,"first_normal":first_normal},None
