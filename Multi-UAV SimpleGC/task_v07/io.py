"""v0.7 episode files retain fastsim CSV conventions with a strict new input loader."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from scene_v07.contract import validate_public_scene
from .planning import seed_for

FEATURES=("east_m","north_m","up_m","ve_m_s","vn_m_s","vu_m_s")
INPUT_KEYS={"x","mask","t_s","agent_ids","scene"}


def save_json(path,value):
    with Path(path).open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write("\n")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_csv(path,ids,time_us,p,v):
    with Path(path).open("x",encoding="utf-8",newline="") as stream:
        writer=csv.writer(stream)
        writer.writerow(("t_s","agent_id","valid",*FEATURES))
        for k,stamp in enumerate(time_us):
            for i,a in enumerate(ids):
                writer.writerow((f"{int(stamp)/1e6:.6f}",a,1,*p[k,i].tolist(),*v[k,i].tolist()))


def observations(scene,family,skeleton,run):
    radars=np.array([e["geometry"]["position_m"] for e in scene["entities"] if e["type"]=="radar"])
    distance=np.linalg.norm(run["p"][:,:,:2,None]-radars.T[None,None,:,:],axis=2).min(axis=2)/1000
    profile=family["observation_profile"]
    sigma_p=profile["position_sigma0_m"]+profile["position_slope_m_per_km"]*distance
    sigma_v=profile["velocity_sigma0_m_s"]+profile["velocity_slope_m_s_per_km"]*distance
    p=run["p"].copy();v=run["v"].copy()
    for i,a in enumerate(run["agent_ids"]):
        for dest,sigma,kind in ((p,sigma_p,"position"),(v,sigma_v,"velocity")):
            rng=np.random.default_rng(seed_for(skeleton["column_seed"],f"measurement:{a}:{kind}"))
            dest[:,i]+=rng.normal(size=(len(dest),3))*sigma[:,i,None]
    return p,v


def write_episode(root,scene,family,skeleton,run,labels,frame,delays,mode,measurement,timing_plan=None):
    root=Path(root);root.mkdir(exist_ok=False)
    validate_public_scene(scene)
    obs_p,obs_v=observations(scene,family,skeleton,run)
    write_csv(root/"truth.csv",run["agent_ids"],run["time_us"],run["p"],run["v"])
    write_csv(root/"observations.csv",run["agent_ids"],run["time_us"],obs_p,obs_v)
    np.savez_compressed(root/"truth_10hz.npz",time_us=run["time_us"],p=run["p"],v=run["v"],a=run["a"],
                        agent_ids=np.array(run["agent_ids"]))
    np.savez_compressed(root/"model_input.npz",x=np.concatenate((obs_p,obs_v),axis=2),
                        mask=np.ones(obs_p.shape[:2],bool),t_s=run["time_us"]/1e6,
                        agent_ids=np.array(run["agent_ids"]))
    np.savez_compressed(root/"frame_labels.npz",**frame)
    save_json(root/"public_scene.json",scene)
    save_json(root/"labels.json",labels)
    save_json(root/"task.json",skeleton)
    save_json(root/"source.json",{"source":"fastsim","simulation_backend":"fast_dynamics",
             "config_sha256":run["config_sha256"],"family_initial":family,"skeleton_id":skeleton["skeleton_id"],
             "departure_delays_s":delays,"planned_coordination":mode,"timing_plan":timing_plan,
             "single_agent_measured_core_times_s":measurement,"sampling_rate_hz":10,
             "high_frequency_semantic_evidence_used":False,"execution_status":run["execution_status"],
             "simulation_wall_s":run["wall_s"],"end_us":run["end_us"],
             "scope":"S2 minimal development slice; 4–10 m/s synthetic extrapolation, no SITL qualification"})
    artifacts={p.name:sha(p) for p in root.iterdir() if p.is_file()}
    save_json(root/"manifest.json",{"protocol_version":"swarm_defense_v07a","source":"fastsim",
             "simulation_backend":"fast_dynamics","agent_ids":run["agent_ids"],"end_us":run["end_us"],
             "time_base":"sim_clock","time_policy":"integer_sim_clock_half_open_v1","sample_hz":10,
             "feature_columns":list(FEATURES),"artifact_sha256":artifacts,
             "label_schema_version":labels["schema_version"],"training_eligible":False,
             "loader":"task_v07.io.load_episode","default_input_keys":sorted(INPUT_KEYS),
             "generation_quality":labels["generation_quality"]})
    loaded=load_episode(root)
    if not np.array_equal(loaded["x"],np.concatenate((obs_p,obs_v),axis=2)):
        raise ValueError("P0: observation CSV reconstruction mismatch")
    return loaded


def load_episode(root,agent_ids=None):
    root=Path(root);manifest=read_json(root/"manifest.json")
    if manifest["protocol_version"]!="swarm_defense_v07a":
        raise ValueError("Unsupported v0.7 episode")
    for name,digest in manifest["artifact_sha256"].items():
        if Path(name).name!=name or sha(root/name)!=digest:
            raise ValueError("Episode artifact hash or relative path mismatch")
    ids=list(manifest["agent_ids"] if agent_ids is None else agent_ids)
    if len(ids)!=len(set(ids)) or set(ids)!=set(manifest["agent_ids"]):
        raise ValueError("Requested IDs are not an exact column permutation")
    scene=read_json(root/"public_scene.json")
    validate_public_scene(scene)
    records={};ticks=set()
    with (root/"observations.csv").open(encoding="utf-8",newline="") as stream:
        reader=csv.DictReader(stream)
        if reader.fieldnames!=["t_s","agent_id","valid",*FEATURES]:
            raise ValueError("Observation feature whitelist violated")
        for row in reader:
            tick=round(float(row["t_s"])*1e6);a=row["agent_id"]
            if a not in ids or (tick,a) in records or row["valid"]!="1":
                raise ValueError("Invalid sample identity or mask")
            records[tick,a]=[float(row[f]) for f in FEATURES]
            ticks.add(tick)
    t=np.array(sorted(ticks),np.int64)
    from swarm_sim.fast_dynamics.engine import integer_output_grid
    if not np.array_equal(t,integer_output_grid(manifest["end_us"])):
        raise ValueError("Invalid common half-open 10 Hz grid")
    x=np.array([[records[tick,a] for a in ids] for tick in t])
    if not np.isfinite(x).all():
        raise ValueError("Nonfinite model input")
    result={"x":x,"mask":np.ones(x.shape[:2],bool),"t_s":t/1e6,"agent_ids":ids,"scene":scene}
    if set(result)!=INPUT_KEYS:
        raise ValueError("P0: model input whitelist violation")
    return result


def load_pair(left,right):
    inputs=[load_episode(p) for p in (left,right)]
    tasks=[read_json(Path(p)/"task.json") for p in (left,right)]
    if tasks[0]!=tasks[1] or inputs[0]["agent_ids"]!=inputs[1]["agent_ids"] or inputs[0]["scene"]!=inputs[1]["scene"]:
        raise ValueError("Pair does not share all non-comparison conditions")
    return {"inputs":inputs,"labels":[read_json(Path(p)/"labels.json") for p in (left,right)],
            "skeleton_id":tasks[0]["skeleton_id"]}

