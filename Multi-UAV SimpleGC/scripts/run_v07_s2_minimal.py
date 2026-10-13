"""Generate the requested two-map, two-task, paired S2 vertical slice only."""
import argparse
from datetime import datetime, timezone
from itertools import combinations
import json
from pathlib import Path
import random
import sys
import time
import uuid

import numpy as np

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))

from scene_v07.geometry import to_shape
from task_v07.execution import execute, departure_delays, CONFIG_PATH, FROZEN_SHA256
from task_v07.io import read_json, save_json, write_episode, load_episode, load_pair, sha
from task_v07.labels import measure
from task_v07.planning import build_skeleton, seed_for
from scripts.v07_s2_plotting import plot_episode, plot_pair

DEFAULT_DATA=PROJECT.parent.parent/"SwarmData"/"v07_dataset"


def audit_episode(scene,sk,run,labels,mode,batches,root):
    # Re-read the exact exported grid; no internal support trajectory is available here.
    with np.load(root/"truth_10hz.npz",allow_pickle=False) as data:
        reloaded={**run,**{k:data[k] for k in ("time_us","p","v","a")},"agent_ids":data["agent_ids"].tolist()}
    observed,frames=measure(scene,sk,reloaded,mode,batches)
    if observed!=labels:
        raise ValueError("P0: labels disagree with exported truth")
    order=list(reversed(range(len(run["agent_ids"]))))
    alternate={**reloaded,"agent_ids":[run["agent_ids"][i] for i in order],
               "p":run["p"][:,order],"v":run["v"][:,order],"a":run["a"][:,order]}
    aligned,_=measure(scene,sk,alternate,mode,batches)
    for key in ("agents","task_groups","cluster"):
        if aligned[key]!=labels[key]:
            raise ValueError("P0: ID-aligned labels changed under column permutation")
    model=load_episode(root)
    permuted=load_episode(root,agent_ids=alternate["agent_ids"])
    if not np.array_equal(permuted["x"],model["x"][:,order]):
        raise ValueError("P0: model columns do not follow physical agent IDs")
    times=[a["observed"]["core_event"]["t_s"] for a in labels["agents"].values()]
    known=[x for x in times if x is not None and x>.2]
    cutoff=min(known)-.1 if known else 1.0
    prefix,_=measure(scene,sk,reloaded,mode,batches,cutoff_s=cutoff)
    if any(a["observed"]["core_event"]["t_s"] is not None for a in prefix["agents"].values()):
        raise ValueError("P0: truncated prefix claims a future core event")
    save_json(root/"prefix_labels.json",prefix)
    ends=[r["endpoint_enu_m"] for r in sk["references"].values()]
    endpoint_min=min(np.linalg.norm(np.array(a)-b) for a,b in combinations(ends,2))
    if endpoint_min<sk["planning_min_separation_m"] or endpoint_min<15 and sk["cruise_speed_m_s"]>7:
        raise ValueError("Independent endpoint spacing contract violated")
    minimum_waypoint=min(np.linalg.norm(np.diff(r["points_enu_m"],axis=0),axis=1).min() for r in sk["references"].values())
    if minimum_waypoint<1:
        raise ValueError("Sub-metre adjacent waypoint")
    return {"labels_recomputed_from_saved_10hz":True,"id_aligned_permutation_invariant":True,
            "input_whitelist_passed":True,"prefix_without_future_core_events":True,
            "independent_endpoint_minimum_m":float(endpoint_min),"minimum_adjacent_waypoint_m":float(minimum_waypoint)}


def probes(out):
    rows=[]
    for speed in (4.,7.,10.):
        sk={"agent_ids":["probe"],"initial_states":[{"agent_id":"probe","position_enu_m":[0,0,100],
            "velocity_enu_m_s":[0,0,0],"acceleration_enu_m_s2":[0,0,0]}],
            "references":{"probe":{"points_enu_m":[[0,0,100],[30,0,100],[30,30,100]]}},
            "cruise_speed_m_s":speed,"initial_settle_s":20,"terminal_radius_m":1,
            "terminal_speed_m_s":.15,"terminal_hold_s":2}
        run=execute(sk,{"probe":0})
        p=run["p"][:,0,:2]
        from shapely.geometry import LineString
        import shapely
        line=LineString([[0,0],[30,0],[30,30]])
        row={"speed_m_s":speed,"execution_status":run["execution_status"],
             "maximum_track_deviation_m":float(shapely.distance(shapely.points(p),line).max()),
             "observed_maximum_speed_m_s":float(np.linalg.norm(run["v"][:,0],axis=1).max()),
             "duration_s":run["end_us"]/1e6,"wall_s":run["wall_s"],"metric_source":"exported 10 Hz truth only"}
        np.savez_compressed(out/f"probe_{int(speed)}mps.npz",time_us=run["time_us"],p=run["p"],v=run["v"],a=run["a"])
        rows.append(row)
    save_json(out/"kinematic_probes.json",rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-attempt",type=Path,required=True)
    parser.add_argument("--candidates",nargs=2,type=int,default=[226,209])
    parser.add_argument("--output-root",type=Path,default=DEFAULT_DATA)
    args=parser.parse_args()
    root=args.output_root.resolve()
    if root!=DEFAULT_DATA.resolve():
        raise ValueError("This slice writes only to the requested external v07_dataset root")
    out=root/("attempt_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False)
    started=time.perf_counter()
    save_json(out/"frozen_config.json",read_json(CONFIG_PATH))
    save_json(out/"registration.json",{"scope":"S2 section 14 steps 1-2 only","scene_attempt":str(args.scene_attempt),
              "candidates":args.candidates,"required_episodes":8,"config_sha256":FROZEN_SHA256,
              "selection":"Accepted unchanged four-agent families; one/ two facilities. Development feasibility sample, no population claims.",
              "facts_source":"10 Hz half-open exported truth","future_events_used":False})
    print(f"OUTPUT {out}",flush=True)
    probes(out)
    candidates=read_json(args.scene_attempt/"candidates.json")
    selected=[candidates[i] for i in args.candidates]
    if [r["facility_count"] for r in selected]!=[1,2] or any(not r["accepted"] or r["vehicle_count"]!=4 for r in selected):
        raise ValueError("Selection must be one accepted single-facility and one two-facility four-agent family")
    rows=[];pairs=[]
    for map_index,record in enumerate(selected,1):
        source=Path(record["directory"])
        scene=read_json(source/"public_scene.json");family=read_json(source/"family_initial.json")
        if family["sampling_revision"]!="s1.2":
            raise ValueError("S2 source map must be S1.2")
        target=random.Random(seed_for(family["sampling_seed"],"task_unit_target")).choice(
               sorted(e["id"] for e in scene["entities"] if e["type"]=="facility"))
        for index,intent in enumerate(("penetration","reconnaissance")):
            planning_started=time.perf_counter()
            sk=build_skeleton(scene,family,intent,index,target)
            skroot=out/sk["skeleton_id"];skroot.mkdir()
            save_json(skroot/"skeleton.json",sk)
            measured={};drywall=0
            for a in sk["members"]:
                run=execute(sk,{a:0 for a in sk["members"]},only_agent=a)
                drywall+=run["wall_s"]
                raw,_=measure(scene,sk,run,"unassigned_measurement")
                measured[a]=raw["agents"][a]["observed"]["core_event"]["t_s"]
                np.savez_compressed(skroot/f"single_agent_{a}.npz",time_us=run["time_us"],p=run["p"],v=run["v"],agent_ids=np.array(run["agent_ids"]))
                print(f"MEASURE map{map_index} {intent} {a}: {measured[a]} s ({run['wall_s']:.2f}s)",flush=True)
            schedules,batch_indices=departure_delays(sk,measured)
            preflight_s=time.perf_counter()-planning_started
            save_json(skroot/"timing_calibration.json",{"source":"single-agent independent fastsim execution, exported 10 Hz",
                      "core_times_s":measured,"delays_s":schedules,"sequential_batches":batch_indices,
                      "single_flight_wall_s":drywall,"geometry_and_single_flights_wall_s":preflight_s})
            pairrows=[]
            for mode in ("synchronous","sequential"):
                episode_started=time.perf_counter()
                batches={a:0 for a in sk["members"]} if mode=="synchronous" else batch_indices
                run=execute(sk,schedules[mode])
                labels,frame=measure(scene,sk,run,mode,batches)
                dest=skroot/mode
                write_episode(dest,scene,family,sk,run,labels,frame,schedules[mode],mode,measured)
                audit=audit_episode(scene,sk,run,labels,mode,batches,dest)
                plot_episode(scene,run,labels,dest/"topdown.png",f"Map {map_index} | {intent} | assigned {mode}")
                group=next(iter(labels["task_groups"].values()));coord=group["observed"]["coordination"]
                row={"map_candidate":record["candidate_index"],"facility_count":record["facility_count"],
                     "skeleton_id":sk["skeleton_id"],"intent":intent,"mode":mode,"directory":str(dest),
                     "execution_status":run["execution_status"],"observed_coordination":coord["classification"],
                     "coordination_matches":coord["classification"]==mode,"event_times_s":coord["event_times_s"],
                     "event_range_s":coord["event_range_s"],"minimum_separation_m":labels["cluster"]["observed"]["minimum_separation_m"],
                     "task_result":group["result"]["status"],"task_conditions":group["result"]["conditions"],
                     "duration_s":run["end_us"]/1e6,"episode_execution_export_label_plot_audit_s":time.perf_counter()-episode_started,
                     "amortized_skeleton_setup_s":preflight_s/2,"audit":audit}
                row["end_to_end_wall_s"]=row["episode_execution_export_label_plot_audit_s"]+preflight_s/2
                save_json(dest/"metrics.json",row)
                rows.append(row);pairrows.append(row)
                print(f"EPISODE {intent} {mode}: observed={coord['classification']} range={coord['event_range_s']} min_sep={row['minimum_separation_m']:.3f} result={row['task_result']} time={row['end_to_end_wall_s']:.2f}s",flush=True)
            load_pair(*(Path(r["directory"]) for r in pairrows))
            plot_pair(pairrows,skroot/"timing_pair.png",f"Map {map_index} / {intent}")
            pairs.append({"skeleton_id":sk["skeleton_id"],"timing_plot":str(skroot/"timing_pair.png"),
                          "non_timing_inputs_identical":True,"same_column_order":True,
                          "both_modes_match":all(r["coordination_matches"] for r in pairrows),
                          "both_task_results_success":all(r["task_result"]=="success" for r in pairrows)})
    # Full, unabridged labels are delivered as a single reviewable companion.
    save_json(out/"all_episode_labels.json",{f"{r['skeleton_id']}/{r['mode']}":read_json(Path(r["directory"])/"labels.json") for r in rows})
    with (out/"labels_full.md").open("x",encoding="utf-8") as f:
        f.write("# S2 最小竖切：8 个 episode 标签 JSON 全文\n\n")
        for r in rows:
            f.write(f"## {r['skeleton_id']} / {r['mode']}\n\n")
            f.write("```json\n"+(Path(r["directory"])/"labels.json").read_text(encoding="utf-8")+"\n```\n\n")
    with (out/"gallery.md").open("x",encoding="utf-8") as f:
        f.write("# S2 实际轨迹与核心事件时序\n\n")
        for r in rows:
            f.write(f"## {r['intent']} / {r['mode']} / map {r['map_candidate']}\n\n![Actual trajectory](<{(Path(r['directory'])/'topdown.png').as_posix()}>)\n\n")
        for p in pairs:
            f.write(f"![Core event times](<{Path(p['timing_plot']).as_posix()}>)\n\n")
    summary={"schema_version":"traj2language.s2_minimal_attempt/0.7-s2.1","directory":str(out),
             "episodes":rows,"pairs":pairs,"episode_count":len(rows),"total_wall_s":time.perf_counter()-started,
             "timing_scope":"Per episode includes execution, labels, CSV/NPZ, loading, audit and topdown; half shared skeleton construction and four single-agent calibrations. Attempt total additionally includes 3 probes, pair plots and aggregate files.",
             "config_sha256":sha(CONFIG_PATH),"status":"completed","training_eligible":False}
    save_json(out/"summary.json",summary)
    print(f"COMPLETE {out} total={summary['total_wall_s']:.2f}s",flush=True)


if __name__=="__main__":
    main()

