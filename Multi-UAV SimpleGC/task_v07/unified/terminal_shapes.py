"""Continuous feint turns and contour-relative intrusion endpoints."""
import math
import numpy as np
from task_v07.geometry import geometry_facts, offset_geometry
from .route import GeometryRejected, line_interval
from .operation_shapes import gate_slots


def feint_shape(spec,free,rng,draw):
    p=spec["params"]; band=free.offsets["alert"]-free.offsets["protected"]
    maximum=min(p["q_max"],1-p["protected_clearance_m"]/band)
    if maximum<p["q_min"]: raise GeometryRejected("feint_depth_band_empty")
    q=rng.uniform(p["q_min"],maximum); rho=free.offsets["alert"]-q*band
    radius=spec["family"]["lateral_spacing_m"]/2
    pieces=max(2,math.ceil(math.pi/(2*math.acos(1-min(1.,free.cfg["chord_error_m"]/radius)))))
    angles=np.linspace(-math.pi/2,math.pi/2,pieces+1)
    warning=offset_geometry(free.target["geometry"],free.offsets["warning"])
    slots=gate_slots(spec,free,draw["direction_deg"])
    for slot in slots:
        heading=np.asarray(slot["direction"]); normal=np.array([-heading[1],heading[0]])
        origin=np.asarray(slot["entry"])
        hit=line_interval(offset_geometry(free.target["geometry"],rho),origin,heading)
        if hit is None: raise GeometryRejected("feint_depth_unavailable")
        curve=radius*(np.cos(angles)[:,None]*heading+np.sin(angles)[:,None]*normal)
        low,high=hit[0]-2*radius,hit[0]+2*radius
        # Translate this continuous semicircle to the drawn deepest clearance.
        # This solves geometry only; it does not change q or a checking margin.
        for _ in range(36):
            mid=(low+high)/2
            value=geometry_facts(free.target["geometry"],origin+mid*heading+curve,footprint=True)["clearance_m"]
            if value>rho: low=mid
            else: high=mid
        work=origin+(low+high)/2*heading+curve
        gate_hit=line_interval(warning,work[0],heading)
        if gate_hit is None or gate_hit[0]>=0: raise GeometryRejected("feint_gate_unavailable")
        slot.update(entry=(work[0]+gate_hit[0]*heading).tolist(),work=work.tolist(),
                    exit_direction=(-heading).tolist(),entry_to_work="straight_parallel_lane",
                    reference_fields={"feint_depth_fraction":q,"feint_turn_radius_m":radius,
                                      "feint_drawn_contour_clearance_m":rho})
    draw.update(q=q,deepest_contour_clearance_m=rho,turn_radius_m=radius,planned_dwell=False)
    return {"kind":"feint","slots":slots,"draw":draw,"template_fields":{}}


def intrusion_shape(spec,free,rng,draw):
    slots=gate_slots(spec,free,draw["direction_deg"]); distances=[]
    base=free.target["geometry"]
    for slot in slots:
        signed=rng.uniform(*spec["params"]["endpoint_distance_m"]); distances.append(signed)
        origin=np.asarray(slot["entry"]); heading=np.asarray(slot["direction"])
        if signed>=0:
            hit=line_interval(offset_geometry(base,signed),origin,heading)
            if hit is None: raise GeometryRejected("intrusion_contour_unavailable")
            depth=hit[0]
        else:
            hit=line_interval(base,origin,heading)
            if hit is None: raise GeometryRejected("intrusion_interior_unavailable")
            low,high=hit[0],(hit[0]+hit[1])/2
            if float(geometry_facts(base,origin+high*heading)["signed_distance_m"])>signed:
                raise GeometryRejected("intrusion_interior_unavailable")
            # Exact signed-distance solve also supports negative polygon offsets.
            for _ in range(40):
                mid=(low+high)/2
                if float(geometry_facts(base,origin+mid*heading)["signed_distance_m"])>signed: low=mid
                else: high=mid
            depth=(low+high)/2
        point=origin+depth*heading
        slot.update(work=[point.tolist()],entry_to_work="straight_parallel_lane",
                    reference_fields={"intrusion_endpoint_drawn_distance_m":signed})
    ends=[np.asarray(s["work"][0]) for s in slots]
    spacing=spec["family"]["lateral_spacing_m"]
    if any(np.linalg.norm(a-b)<spacing-1e-6 for i,a in enumerate(ends) for b in ends[i+1:]):
        raise GeometryRejected("intrusion_endpoint_spacing")
    draw["endpoint_signed_distances_m"]=distances
    return {"kind":"intrusion","slots":slots,"draw":draw,
            "template_fields":{"intrusion_endpoint_min_spacing_m":spacing}}
