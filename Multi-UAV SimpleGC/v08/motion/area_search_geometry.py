"""V8-20 exact radial intervals and complete finite sector sets (appendix rules 1/2).

The 0.5 m scan is vectorized across angle cells, never replaced by a root or an
approximate spacing formula. Geometry routines consume no random numbers.
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from task_v07.geometry import offset_geometry, radial_points_exact
from task_v07.survey import sector_area
from ..scene.exact import signed_distance
from . import transit_chords as TC
from .area_search_numeric import first_grid_inner, strip_angles

VERSION = "area_search-v20"
MU_DEG = tuple(range(0,360,5))
SPAN_DEG = tuple(range(10,91,5))
RAY_DEG = np.arange(720)*.5


def minimum_inner_offset(base_geometry, center, angles_rad, outer_offset_m,
                         inner_lower_m, *, min_gap_m=40., min_length_m=60.):
    angles = np.asarray(angles_rad,float)
    center = np.asarray(center,float)
    outer = radial_points_exact(offset_geometry(base_geometry,outer_offset_m),center,angles)
    unit = np.c_[np.cos(angles),np.sin(angles)]
    radius = np.linalg.norm(outer-center,axis=1)
    upper_points = center+(radius-min_length_m)[:,None]*unit
    upper = float(np.min(signed_distance(base_geometry,upper_points)))
    return first_grid_inner(inner_lower_m,upper,outer,
        lambda a:radial_points_exact(offset_geometry(base_geometry,a),center,angles),
        min_gap_m=min_gap_m,min_length_m=min_length_m)


def _intersect(left,right):
    return [(max(a,c),min(b,d)) for a,b in left for c,d in right if max(a,c)<=min(b,d)]


def _outside(interval):
    if interval is None:
        return [(-math.inf,math.inf)]
    a,b = interval
    return [(-math.inf,a),(b,math.inf)]


def _margin(c,points):
    sdf=np.asarray(signed_distance(c.geometry,points),float)
    return (abs(sdf) if c.sense==0 else c.sense*sdf)-c.minimum_m


def _endpoint(base,origin,u,x,towards):
    """Choose the legal adjacent representation of an analytic closed endpoint."""
    original=float(x)
    for _ in range(1024):
        if all(float(_margin(c,origin+x*u))>=0. for c in base):
            return float(x)
        x=float(np.nextafter(x,towards))
        if abs(x-original)>1e-9:
            break
    raise ValueError("closed base interval endpoint has no certified representation")


def legal_ray_intervals(base,center,u):
    """All base-legal connected ray intervals, including their certified endpoints."""
    center,u=np.asarray(center,float),np.asarray(u,float)
    intervals=[(0.,math.inf)]
    for c in base:
        if c.sense==-1:
            sub=TC.line_sublevel(c.geometry,center,u,-c.minimum_m)
            parts=[] if sub is None else [sub]
        elif c.sense==1:
            parts=_outside(TC.line_sublevel(c.geometry,center,u,c.minimum_m))
        elif c.sense==0:
            inside=TC.line_sublevel(c.geometry,center,u,-c.minimum_m)
            parts=([inside] if inside is not None else [])+_outside(TC.line_sublevel(c.geometry,center,u,c.minimum_m))
        else:
            raise ValueError("unknown base sense")
        intervals=_intersect(intervals,parts)
    out=[]
    for a,b in sorted(intervals):
        if not np.isfinite([a,b]).all():
            raise ValueError("world must give a finite legal ray bound")
        mid=(a+b)/2
        a=_endpoint(base,center,u,a,mid)
        b=_endpoint(base,center,u,b,mid)
        if a<=b:
            if out and a<=out[-1][1]:
                out[-1]=(out[-1][0],max(out[-1][1],b))
            else:
                out.append((a,b))
    return out


def radial_record(ctx,target_id,angle_rad,outer_offset_m,rho_m,*,outer_xy=None):
    f=ctx.facility_by_id[target_id]
    center=np.asarray(f.center,float)
    u=np.array([math.cos(angle_rad),math.sin(angle_rad)])
    outer=(radial_points_exact(offset_geometry(f.geometry,outer_offset_m),center,np.array([angle_rad]))[0]
           if outer_xy is None else np.asarray(outer_xy,float))
    radius=float(np.linalg.norm(outer-center))
    base=TC.transit_base(ctx,target_id,intent="area_search")["base"]
    intervals=legal_ray_intervals(base,center,u)
    component=next(((a,b) for a,b in intervals if a<=radius and radius+rho_m<=b),None)
    exit_xy=None
    if component is not None:
        last=math.floor((component[1]-radius)/TC.X_STEP_M)
        for tick in range(last+1):
            point=outer+(tick*TC.X_STEP_M)*u
            if all(float(signed_distance(g,point))>=55. for g in TC.transit_base(ctx,target_id,intent="area_search")["warnings"].values()):
                if all(float(_margin(c,point))>=0. for c in base):
                    exit_xy=point
                break
    return {"angle_rad":float(angle_rad),"unit":u,"outer_xy":outer,"outer_radius_m":radius,
            "legal_intervals":intervals,"component":component,"exit_xy":exit_xy,
            "corridor_ok":bool(component is not None and exit_xy is not None)}


def radial_legal_table(ctx,target_id,*,outer_offset_m,rho_m):
    key=(VERSION,"radial",target_id,float(outer_offset_m),float(rho_m))
    if key not in ctx.extra:
        f=ctx.facility_by_id[target_id]
        angles=np.radians(RAY_DEG)
        outer=radial_points_exact(offset_geometry(f.geometry,outer_offset_m),f.center,angles)
        ctx.extra[key]=[radial_record(ctx,target_id,float(a),outer_offset_m,rho_m,outer_xy=p) for a,p in zip(angles,outer)]
    return ctx.extra[key]


def outer_perimeter(base,offset):
    if base["type"]=="Circle":
        return 2*math.pi*(base["radius_m"]+offset)
    p=np.asarray(base["vertices_m"],float)
    if np.array_equal(p[0],p[-1]):
        p=p[:-1]
    return float(np.linalg.norm(np.roll(p,-1,axis=0)-p,axis=1).sum())+2*math.pi*(base.get("buffer_m",0.)+offset)


def bounding_radius(base,center,offset):
    if base["type"]=="Circle":
        return float(base["radius_m"]+offset)
    return float(np.linalg.norm(np.asarray(base["vertices_m"],float)-np.asarray(center,float),axis=1).max())+base.get("buffer_m",0.)+offset


def sector_identity(ctx,target_id,member_count,altitude_m):
    from ..config import load_config
    f=ctx.facility_by_id[target_id]
    doc={"version":VERSION,"intent":"area_search","context":ctx.cache_key,"target":target_id,
         "N":int(member_count),"altitude_m":float(altitude_m),"geometry":f.geometry,"center":f.center,"offsets":f.offsets,
         "mu_deg":MU_DEG,"span_deg":SPAN_DEG,"radial_step_deg":.5,"inner_step_m":.5,
         "min_gap_m":40.,"min_length_m":60.,"outer_gap_footprint_factor":1.6,
         "rho_footprint_factor":.8,"footprint_height_factor":.5,"layer_inset_m":12.5,
         "exit_m":55.,"exit_step_m":TC.X_STEP_M,"configs":{n:load_config(n).sha256 for n in ("monitoring","joint_opt","guidance","criteria_segment")}}
    raw=json.dumps(doc,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode()).hexdigest(),doc


def _scan_angle_cells(base,center,n,c,ao,lower,rf):
    """Shared exact endpoint evaluations; each cell still takes its first grid tick."""
    pairs=[(mu,span) for mu in MU_DEG for span in SPAN_DEG]
    angles=np.asarray([strip_angles(mu,span,n,c) for mu,span in pairs])
    unique,indices=np.unique(angles,return_inverse=True)
    indices=indices.reshape(angles.shape)
    outer_unique=radial_points_exact(offset_geometry(base,ao),center,unique)
    outer=outer_unique[indices]
    outer_gaps=np.linalg.norm(np.diff(outer,axis=1),axis=2)
    radius=np.linalg.norm(outer-np.asarray(center),axis=2)
    unit=np.stack([np.cos(angles),np.sin(angles)],axis=-1)
    upper=np.min(signed_distance(base,np.asarray(center)+(radius-60.)[...,None]*unit),axis=1)
    pending=np.all(outer_gaps<=1.6*rf,axis=1)&(upper>=lower)
    found={}
    if not np.any(pending):
        return found
    for tick in range(math.floor((float(upper[pending].max())-lower)/.5)+1):
        offset=lower+.5*tick
        rows=np.flatnonzero(pending&(offset<=upper))
        if not len(rows):
            break
        # Frozen evaluator, on the original float angles; no contour approximation.
        inner_unique=radial_points_exact(offset_geometry(base,offset),center,unique)
        inner=inner_unique[indices[rows]]
        gaps=np.linalg.norm(np.diff(inner,axis=1),axis=2)
        lengths=np.linalg.norm(outer[rows]-inner,axis=2)
        good=np.all(gaps>=40.,axis=1)&np.all(lengths>=60.,axis=1)
        for j in np.flatnonzero(good):
            idx=int(rows[j]);mu,span=pairs[idx]
            found[(mu,span)]={"inner_offset_m":float(offset),"inner_xy":inner[j].tolist(),"outer_xy":outer[idx].tolist(),
                             "angles_rad":angles[idx].tolist(),"inner_gaps_m":gaps[j].tolist(),
                             "outer_gaps_m":outer_gaps[idx].tolist(),"strip_lengths_m":lengths[j].tolist()}
            pending[idx]=False
        pending &= offset<upper
        if not np.any(pending):
            break
    return found


def feasible_sector_cells(ctx,target_id,member_count,altitude_m):
    qid,identity=sector_identity(ctx,target_id,member_count,altitude_m)
    memory_key=(VERSION,"sectors",qid)
    if memory_key in ctx.extra:
        return ctx.extra[memory_key]
    cache=None if ctx.cache_dir is None else Path(ctx.cache_dir)/"area_search_v20"/"sector_sets"/(qid+".json")
    if cache is not None and cache.is_file():
        doc=json.loads(cache.read_text(encoding="utf-8"))
        if doc["identity"]!=json.loads(json.dumps(identity)):
            raise ValueError("sector cache identity mismatch")
        cells=doc["cells"]
        for cell in cells:
            cell["choices"]={int(k):v for k,v in cell["choices"].items()}
        ctx.extra[memory_key]=cells
        return cells
    f=ctx.facility_by_id[target_id]
    rf=.5*float(altitude_m);rho=.8*rf
    ao=float(f.offsets["warning"])-12.5-rho
    lower=float(f.offsets["alert"])+12.5+rho
    table=radial_legal_table(ctx,target_id,outer_offset_m=ao,rho_m=rho)
    limit=math.floor(outer_perimeter(f.geometry,ao)/40.)+1
    by_cell={}
    inner_rays={}
    ray_angles=np.radians(RAY_DEG)
    for c in range(2,limit//int(member_count)+1,2):
        choices=_scan_angle_cells(f.geometry,f.center,int(member_count),c,ao,lower,rf)
        for (mu,span),choice in sorted(choices.items()):
            ai=choice["inner_offset_m"]
            if ai not in inner_rays:
                points=radial_points_exact(offset_geometry(f.geometry,ai),f.center,ray_angles)
                inner_rays[ai]=np.linalg.norm(points-np.asarray(f.center),axis=1)
            start=int(round((mu-span/2)/.5))
            rays=[j%720 for j in range(start,start+int(span/.5)+1)]
            if not all(table[j]["corridor_ok"] and table[j]["component"][0]<=inner_rays[ai][j]-rho for j in rays):
                continue
            by_cell.setdefault((mu,span),{})[c]=choice
    cells=[{"mu_deg":mu,"span_deg":span,"choices":choices} for (mu,span),choices in sorted(by_cell.items())]
    ctx.extra[memory_key]=cells
    return cells


def write_sector_cache(ctx,target_id,member_count,altitude_m):
    qid,identity=sector_identity(ctx,target_id,member_count,altitude_m)
    cells=feasible_sector_cells(ctx,target_id,member_count,altitude_m)
    p=Path(ctx.cache_dir)/"area_search_v20"/"sector_sets"/(qid+".json")
    p.parent.mkdir(parents=True,exist_ok=True)
    if not p.exists():
        with p.open("x",encoding="utf-8",newline="\n") as out:
            json.dump({"identity":identity,"cells":cells},out,sort_keys=True,separators=(",",":"))
            out.write("\n")
    return {"query_id":qid,"cells":len(cells),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}


def member_split_points(base_geometry,center,outer_offset_m,u,h_m,offsets,*,x_min=-math.inf,x_max=math.inf):
    """Rule 1: longitudinal offsets affect certified travel bounds, never the line."""
    center,u=np.asarray(center,float),np.asarray(u,float)
    normal=np.array([-u[1],u[0]])
    result={}
    for mid,(longitudinal,lateral) in offsets.items():
        origin=center+(h_m+lateral)*normal
        interval=TC.line_sublevel(base_geometry,origin,u,outer_offset_m)
        if interval is None or not x_min+longitudinal<=interval[0]<=x_max+longitudinal:
            raise ValueError("member entry line cannot reach the first outer contour intersection")
        result[mid]=origin+interval[0]*u
    return result


def filter_entry_cells(ctx,target_id,chord_cells,sector_cells,outer_offset_m,*,offsets=None):
    if offsets is None:
        raise ValueError("all actual member offsets required for entry filtering")
    f=ctx.facility_by_id[target_id]
    entries=[];seen=set()
    for index,cell in sorted(enumerate(chord_cells),key=lambda t:(t[1][0],t[1][1])):
        ti,h,xt,xin,ds=cell
        identity=(int(ti),float(h))
        if identity in seen:
            continue
        seen.add(identity)
        u,normal=TC.frame(TC.thetas()[int(ti)])
        try:
            q=member_split_points(f.geometry,f.center,outer_offset_m,u,h,{"center":(0.,0.)},x_min=xin-max(ds),x_max=xt)["center"]
            splits=member_split_points(f.geometry,f.center,outer_offset_m,u,h,offsets,x_min=xin-max(ds),x_max=xt)
        except ValueError:
            continue
        radial=np.asarray(f.center)-q
        beta=math.degrees(math.atan2(float(u[0]*radial[1]-u[1]*radial[0]),float(u@radial)))
        if abs(beta)>45.:
            continue
        alpha=math.degrees(math.atan2(q[1]-f.center[1],q[0]-f.center[0]))
        sectors=[]
        for sector in sector_cells:
            wrapped=(alpha-sector["mu_deg"]+180.)%360.-180.
            if abs(wrapped)<=.4*sector["span_deg"]:
                sectors.append((sector,tuple(sorted(sector["choices"]))))
        if sectors:
            entries.append(({"cell":cell,"cell_index":index,"Q":q,"beta_deg":beta,"splits":splits},sectors))
    return entries


def make_survey(base,center,outer_offset,mu_deg,span_deg,n,c,choice,altitude_m):
    radius=bounding_radius(base,center,outer_offset)
    center=np.asarray(center,float)
    g={"type":"ContourAnnularSector","base_geometry":base,"center_m":center.tolist(),
       "inner_offset_m":choice["inner_offset_m"],"outer_offset_m":float(outer_offset),
       "start_angle_rad":math.radians(mu_deg-span_deg/2),"angle_span_rad":math.radians(span_deg),"bounding_radius_m":radius}
    area=float(sector_area(g,32));rf=.5*float(altitude_m)
    return {"geometry":g,"bounds_m":[float(center[0]-radius),float(center[1]-radius),float(center[0]+radius),float(center[1]+radius)],
            "footprint_radius_m":rf,"grid_spacing_m":min(rf/2,math.sqrt(area)/50),
            "strip_count":int(n*c),"strips_per_member":int(c),"area_m2":area}


def _circle_line_angles(center,radius,normal,constant):
    norm=float(np.linalg.norm(normal))
    if norm==0.:
        return []
    value=(constant-float(np.asarray(normal)@center))/(radius*norm)
    if not -1.<=value<=1.:
        return []
    angle=math.atan2(normal[1],normal[0]);delta=math.acos(value)
    return [angle-delta,angle+delta]


def _circle_circle_angles(center,radius,other,other_radius):
    v=np.asarray(other,float)-center;distance=float(np.linalg.norm(v))
    if distance==0.:
        return []
    value=(radius*radius+distance*distance-other_radius*other_radius)/(2*radius*distance)
    if not -1.<=value<=1.:
        return []
    a=math.atan2(v[1],v[0]);d=math.acos(value)
    return [a-d,a+d]


def arc_extreme_points(primitive,geometry):
    """Endpoints, stationary features and inside-edge switches of an exact arc."""
    _,center,radius,start,sweep=primitive
    center=np.asarray(center,float);radius=float(radius)
    angles=[float(start),float(start+sweep)]
    if geometry["type"]=="Circle":
        v=np.asarray(geometry["center_m"])-center
        a=math.atan2(v[1],v[0]);angles.extend((a,a+math.pi))
        angles.extend(_circle_circle_angles(center,radius,geometry["center_m"],geometry["radius_m"]))
    else:
        vertices=np.asarray(geometry["vertices_m"],float)
        if np.array_equal(vertices[0],vertices[-1]):
            vertices=vertices[:-1]
        edges=np.roll(vertices,-1,axis=0)-vertices
        length=np.linalg.norm(edges,axis=1)
        orientation=1 if np.sum(vertices[:,0]*np.roll(vertices[:,1],-1)-vertices[:,1]*np.roll(vertices[:,0],-1))>0 else -1
        normals=orientation*np.c_[edges[:,1],-edges[:,0]]/length[:,None]
        buffer=float(geometry.get("buffer_m",0.))
        for vertex,edge,L,normal in zip(vertices,edges,length,normals):
            a=math.atan2(vertex[1]-center[1],vertex[0]-center[0])
            b=math.atan2(normal[1],normal[0]);angles.extend((a,a+math.pi,b,b+math.pi))
            tangent=edge/L
            for point in (vertex,vertex+edge):
                angles.extend(_circle_line_angles(center,radius,tangent,float(tangent@point)))
            angles.extend(_circle_line_angles(center,radius,normal,float(normal@vertex)+buffer))
            if buffer>=0.:
                angles.extend(_circle_circle_angles(center,radius,vertex,buffer))
        for i in range(len(vertices)):
            for j in range(i):
                angles.extend(_circle_line_angles(center,radius,normals[i]-normals[j],
                    float(normals[i]@vertices[i]-normals[j]@vertices[j])))
    selected=[start,start+sweep]
    for a in angles[2:]:
        phase=(a-start)%(2*math.pi) if sweep>0 else (start-a)%(2*math.pi)
        if phase<=abs(sweep):
            selected.append(a)
    a=np.asarray(selected,float)
    return center+radius*np.c_[np.cos(a),np.sin(a)]


def audit_complete_curve(base,xy,primitives):
    from ..scene.exact import polyline_clearance
    minima={}
    for c in base:
        chords=polyline_clearance(c.geometry,xy,sense=c.sense,minimum_m=c.minimum_m,fast_far_m=5.)
        minima[c.name]=float(np.min(chords))
        if minima[c.name]<0.:
            return {"passed":False,"constraint":c.name,"margin_m":minima[c.name],"chord_index":int(np.argmin(chords)),"minima":minima}
        for primitive in primitives:
            if primitive[0]=="arc":
                margin=float(np.min(_margin(c,arc_extreme_points(primitive,c.geometry))))
                minima[c.name]=min(minima[c.name],margin)
                if margin<0.:
                    return {"passed":False,"constraint":c.name,"margin_m":margin,"chord_index":None,"minima":minima}
    return {"passed":True,"minima":minima}
