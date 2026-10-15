"""Independent audit: GEOS original-contour distance, never the label query."""
import argparse
import csv
import hashlib
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Polygon


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))



def _signed_distance(g, xy):
    if g["type"]=="Circle":
        return np.linalg.norm(xy-np.asarray(g["center_m"]),axis=-1)-g["radius_m"]
    polygon=Polygon(g["vertices_m"]);points=shapely.points(xy)
    return np.where(shapely.covers(polygon,points),-shapely.distance(polygon.boundary,points),
                    shapely.distance(polygon,points))-g.get("buffer_m",0)


def _inside(g, xy):
    if g["type"]!="ContourAnnularSector":
        return _signed_distance(g,xy)<=0
    d=_signed_distance(g["base_geometry"],xy)
    relative=xy-np.asarray(g["center_m"])
    angle=(np.arctan2(relative[...,1],relative[...,0])-g["start_angle_rad"])%(2*np.pi)
    result=(d>=g["inner_offset_m"])&(d<=g["outer_offset_m"])&(angle<=g["angle_span_rad"])
    if "lateral_interval_m" in g:
        lateral=relative@np.asarray(g["lateral_axis"])
        result&=(lateral>=g["lateral_interval_m"][0])&(lateral<=g["lateral_interval_m"][1])
    return result

def audit_episode(root):
    root=Path(root)
    scene=_read(root/"public_scene.json")
    labels=_read(root/"labels.json")
    if labels.get("evidence", {}).get("criteria_version") == "criteria/0.7-r1":
        from scripts.audit_v07_m1 import audit_episode as criteria_audit
        return criteria_audit(root)
    task=_read(root/"task.json")
    with np.load(root/"truth_10hz.npz",allow_pickle=False) as data:
        ids=data["agent_ids"].tolist();t=data["time_us"];p=data["p"];v=data["v"]
    with np.load(root/"frame_labels.npz",allow_pickle=False) as data:
        fids=data["facility_ids"].tolist()
        stored=data["region_all_facilities"];target_stored=data["region_assigned_target"]
        label_ids=data["agent_ids"].tolist();label_t=data["time_us"]
    if ids!=label_ids or not np.array_equal(t,label_t):
        raise ValueError("P0: independent audit found label/trajectory axes mismatch")
    # CSV is the declared evidence source: check NPZ and CSV agree row for row.
    columns=("east_m","north_m","up_m","ve_m_s","vn_m_s","vu_m_s")
    with (root/"truth.csv").open(encoding="utf-8",newline="") as stream:
        reader=csv.DictReader(stream);count=0
        for row in reader:
            k,i=divmod(count,len(ids))
            if k>=len(t) or row["agent_id"]!=ids[i] or row["valid"]!="1" or float(row["t_s"])!=t[k]/1e6:
                raise ValueError("P0: truth CSV time/ID/validity mismatch")
            if not np.array_equal(np.array([float(row[c]) for c in columns]),np.r_[p[k,i],v[k,i]]):
                raise ValueError("P0: truth CSV and NPZ states differ")
            count+=1
    if count!=len(t)*len(ids):
        raise ValueError("P0: missing truth CSV rows")
    expected=np.zeros_like(stored)
    signed={}
    for j,fid in enumerate(fids):
        facility=next(e for e in scene["entities"] if e["id"]==fid)
        geometry=facility["geometry"]
        xy=p[:,:,:2]
        if geometry["type"]=="Circle":
            distance=np.linalg.norm(xy-np.array(geometry["center_m"]),axis=-1)-geometry["radius_m"]
        else:
            polygon=Polygon(geometry["vertices_m"])
            points=shapely.points(xy)
            distance=shapely.distance(polygon,points)
            inside=shapely.covers(polygon,points)
            # Independent signed depth inside the original polygon.
            distance=np.where(inside,-shapely.distance(polygon.boundary,points),distance)
        signed[fid]=distance
        for name,level in (("warning",1),("alert",2),("protected",3)):
            zone=next(e for e in scene["entities"] if e.get("facility_id")==fid and e.get("layer")==name)
            expected[:,:,j][distance<=zone["offset_m"]]=level
    mismatch=np.argwhere(expected!=stored)
    target_j=fids.index(task["target_id"])
    target_mismatch=int(np.count_nonzero(expected[:,:,target_j]!=target_stored))
    witnesses=[{"frame_index":int(k),"t_s":float(t[k]/1e6),"agent_id":ids[i],"facility_id":fids[j],
                "expected":int(expected[k,i,j]),"stored":int(stored[k,i,j])} for k,i,j in mismatch[:20]]
    event_errors=[];coverage_by_agent=[]
    if task["base_intent"]=="reconnaissance":
        survey=task["survey"]
        region=survey.get("geometry",{"type":"Polygon","vertices_m":survey.get("vertices_m",[])})
        if "bounds_m" in survey:
            x0,y0,x1,y1=survey["bounds_m"]
        else:
            points=np.asarray(survey["vertices_m"]);x0,y0=points.min(axis=0);x1,y1=points.max(axis=0)
        step=survey["grid_spacing_m"]
        xx,yy=np.meshgrid(np.arange(x0+step/2,x1,step),np.arange(y0+step/2,y1,step))
        grid=np.c_[xx.ravel(),yy.ravel()];grid=grid[_inside(region,grid)]

    for i,a in enumerate(ids):
        actual=labels["agents"][a]["observed"]
        for j,fid in enumerate(fids):
            for name,level in (("warning",1),("alert",2),("protected",3)):
                indexes=np.flatnonzero(expected[:,i,j]>=level)
                first=float(t[indexes[0]]/1e6) if len(indexes) else None
                saved=actual["regions_by_facility"][fid][name]
                if saved["first_entry_s"]!=first or saved["sample_count"]!=len(indexes):
                    event_errors.append({"agent_id":a,"facility_id":fid,"layer":name})
        if task["base_intent"]=="penetration":
            valid=expected[:,i,target_j]==3
            depth=float(np.maximum(next(e["offset_m"] for e in scene["entities"]
                                       if e.get("facility_id")==task["target_id"] and e.get("layer")=="protected")
                                   -signed[task["target_id"]][:,i],0).max())
            if abs(actual["contribution"]["maximum_protected_depth_m"]-depth)>1e-8:
                event_errors.append({"agent_id":a,"field":"maximum_protected_depth_m"})
        else:
            reference=task["references"][a]
            strip=reference.get("scan_geometry",{"type":"Polygon","vertices_m":reference.get("scan_vertices_m",[])})
            xy=p[:,i,:2]
            valid=_inside(strip,xy)
            valid&=(np.linalg.norm(v[:,i],axis=1)>=task["survey"]["effective_speed_min_m_s"])&(expected[:,i,target_j]==1)
            for obstacle in (e for e in scene["entities"] if e["type"]=="hard_constraint_obstacle"):
                valid&=~_inside(obstacle["geometry"],xy)
            cursor=0;visits=[]
            for point in reference["scan_lane_endpoints_m"]:
                selected=np.flatnonzero(np.linalg.norm(xy[cursor:]-point,axis=1)<=survey["lane_endpoint_radius_m"])
                if not len(selected):
                    break
                cursor+=int(selected[0]);visits.append(float(t[cursor]/1e6))
            complete=len(visits)==len(reference["scan_lane_endpoints_m"])
            end=visits[-1] if complete else None
            if end is not None:
                valid &= t/1e6<=end
            observed=actual["contribution"]
            if observed["ordered_lane_endpoint_times_s"]!=visits or observed["scan_pattern_observed"]!=complete:
                event_errors.append({"agent_id":a,"field":"ordered_scan_endpoints"})
            if "scan_end_s" in observed and observed["scan_end_s"]!=end:
                event_errors.append({"agent_id":a,"field":"scan_end_s"})
            selected=np.flatnonzero(valid);first=float(t[selected[0]]/1e6) if len(selected) else None
            duration=round(end-first,6) if end is not None and first is not None else None
            if "scan_segment_duration_s" in observed and observed["scan_segment_duration_s"]!=duration:
                event_errors.append({"agent_id":a,"field":"scan_segment_duration_s"})
            covered=np.zeros(len(grid),bool)
            # Independent nearest-point search in grid blocks.
            if valid.any():
                samples=xy[valid]
                for begin in range(0,len(grid),64):
                    points=grid[begin:begin+64]
                    covered[begin:begin+64]=(np.sum((points[:,None,:]-samples[None,:,:])**2,axis=2).min(axis=1)
                                             <=survey["footprint_radius_m"]**2)
            coverage_by_agent.append(covered)
            if int(covered.sum())!=observed["covered_group_grid_points"]:
                event_errors.append({"agent_id":a,"field":"covered_group_grid_points"})
            if reference.get("retreat_required"):
                distance=np.linalg.norm(p[:,i]-reference["endpoint_enu_m"],axis=1)
                after=np.zeros(len(t),bool) if end is None else t/1e6>=end
                arrivals=np.flatnonzero((distance<=task["terminal_radius_m"])&after)
                arrival=float(t[arrivals[0]]/1e6) if len(arrivals) else None
                if actual["retreat_event"]["t_s"]!=arrival:
                    event_errors.append({"agent_id":a,"field":"retreat_event"})
                dwell=(distance<=task["terminal_radius_m"])&(np.linalg.norm(v[:,i],axis=1)<=task["terminal_speed_m_s"])&after
                changes=np.flatnonzero(np.diff(np.r_[False,dwell,False].astype(int)))
                hold=max([0,*((changes[1::2]-changes[::2]-1)/10).tolist()])
                if actual["endpoint_hold_s"]!=hold:
                    event_errors.append({"agent_id":a,"field":"retreat_hold"})
                required=labels["agents"][a]["result"]["conditions"]["reached_retreat_point"]
                if required!=(arrival is not None):
                    event_errors.append({"agent_id":a,"field":"reached_retreat_point"})
        indexes=np.flatnonzero(valid)
        first=float(t[indexes[0]]/1e6) if len(indexes) else None
        if actual["core_event"]["t_s"]!=first:
            event_errors.append({"agent_id":a,"field":"core_event"})
    if coverage_by_agent:
        shared=next(iter(labels["task_groups"].values()))["observed"]["shared_coverage"]
        covered=np.logical_or.reduce(coverage_by_agent)
        if shared["grid_point_count"]!=len(grid) or shared["covered_grid_point_count"]!=int(covered.sum()):
            event_errors.append({"field":"shared_coverage"})
    minimum=min(float(np.linalg.norm(p[:,i]-p[:,j],axis=1).min()) for i,j in combinations(range(len(ids)),2))
    if minimum!=labels["cluster"]["observed"]["minimum_separation_m"]:
        event_errors.append({"field":"minimum_separation_m"})
    quality=labels["generation_quality"]
    if quality["retained"]!=(minimum>=2) or quality["separation_affects_task_result"] is not False:
        event_errors.append({"field":"separation_quality_policy"})
    row={"directory":str(root),"frames":len(t),"agents":len(ids),"facilities":len(fids),
         "all_facility_frame_comparisons":int(expected.size),"assigned_target_frame_comparisons":int(target_stored.size),
         "region_difference_count":len(mismatch),"target_difference_count":target_mismatch,
         "event_or_metric_difference_count":len(event_errors),"first_witnesses":witnesses,
         "event_or_metric_witnesses":event_errors,
         "truth_csv_sha256":hashlib.sha256((root/"truth.csv").read_bytes()).hexdigest(),
         "frame_labels_sha256":hashlib.sha256((root/"frame_labels.npz").read_bytes()).hexdigest()}
    row["status"]="PASS" if not (len(mismatch) or target_mismatch or event_errors) else "P0_STOP"
    return row


def audit_attempt(attempt):
    attempt=Path(attempt)
    roots=sorted(p.parent for p in attempt.glob("*/*/manifest.json"))
    rows=[audit_episode(root) for root in roots]
    return {"status":"PASS" if rows and all(r["status"]=="PASS" for r in rows) else "P0_STOP",
            "method":"Independent original polygon GEOS distance / analytic circle; no task_v07.geometry or label extraction calls",
            "sample_hz":10,"episode_count":len(rows),
            "all_facility_frame_comparisons":sum(r["all_facility_frame_comparisons"] for r in rows),
            "assigned_target_frame_comparisons":sum(r["assigned_target_frame_comparisons"] for r in rows),
            "region_difference_count":sum(r["region_difference_count"] for r in rows),
            "target_difference_count":sum(r["target_difference_count"] for r in rows),
            "event_or_metric_difference_count":sum(r["event_or_metric_difference_count"] for r in rows),"episodes":rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=audit_attempt(args.attempt)
    with args.output.open("x",encoding="utf-8") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!="episodes"},ensure_ascii=False))
    return 0 if result["status"]=="PASS" else 1


if __name__=="__main__":
    raise SystemExit(main())
