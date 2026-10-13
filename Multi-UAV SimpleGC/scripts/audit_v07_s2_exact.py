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


def audit_episode(root):
    root=Path(root)
    scene=_read(root/"public_scene.json")
    labels=_read(root/"labels.json")
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
    event_errors=[]
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
            strip=Polygon(task["references"][a]["scan_vertices_m"])
            valid=shapely.covers(strip,shapely.points(p[:,i,:2]))
            valid&=(np.linalg.norm(v[:,i],axis=1)>=task["survey"]["effective_speed_min_m_s"])&(expected[:,i,target_j]==1)
            for obstacle in (e for e in scene["entities"] if e["type"]=="hard_constraint_obstacle"):
                g=obstacle["geometry"]
                forbidden=(np.linalg.norm(p[:,i,:2]-g["center_m"],axis=1)<=g["radius_m"]) if g["type"]=="Circle" else shapely.covers(Polygon(g["vertices_m"]),shapely.points(p[:,i,:2]))
                valid&=~forbidden
        indexes=np.flatnonzero(valid)
        first=float(t[indexes[0]]/1e6) if len(indexes) else None
        if actual["core_event"]["t_s"]!=first:
            event_errors.append({"agent_id":a,"field":"core_event"})
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
