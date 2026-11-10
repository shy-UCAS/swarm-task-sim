"""Part-3 cache/sorting/registered maximum-sector diagnostics, not production."""
import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

BASE=Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO=BASE/"Simulation-v08";CODE=REPO/"Multi-UAV SimpleGC"
TASK=BASE/"_handoff/2026-11-09_V8-20_area_search";ROOT=TASK/"run";OUT=ROOT/"cost_ruling_r1/remaining"
sys.path.insert(0,str(CODE))

from v08.contract.monitoring import initial_states
from v08.contract.single_intent import area_search_mission
from v08.motion import transit_chords as TC
from v08.motion.area_search_geometry import feasible_sector_cells,filter_entry_cells,write_sector_cache
from v08.motion.area_search_numeric import draw_hierarchy
from v08.motion.formation import formation_slots,mapped_start,retreat_chain
from v08.motion.intents import area_search as A,transit as T
from v08.runner.monitoring import load_entries,jsonable
from v08.sampler.common import sample_common
from v08.sampler.keys import RngKey,rng_for
from v08.scene.context import load_context


def raw(value):
    return (json.dumps(jsonable(value),sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()


def save(p,value):
    with Path(p).open("xb") as f:
        f.write(raw(value));f.flush();os.fsync(f.fileno())


def setup(order,draw,cache):
    entry=next(e for e in load_entries(REPO/"docs/v08/V8-03/devset_v08.json") if int(e["order"])==order)
    ctx=load_context(entry,data_root=BASE/"SwarmData",cache_dir=cache)
    mission=area_search_mission(ctx,sample_common(ctx.family,draw))
    group,task=mission.groups[0],mission.tasks[0]
    key=RngKey(ctx.family.family_id,draw,"shape",mission=0,branch=None,group=group.group_id,segment=0,attempt=0)
    return ctx,group,task,key


def select(ctx,group,task,key):
    # Exactly the production width probe; no shape draws inside it.
    seq=T.formation_probe_sequence(ctx,group,task,key,chord_intent="area_search")
    if not seq:
        return None,None,seq
    name,step,_=seq[-1]
    fkey=RngKey(key.family_id,key.draw,"formation",mission=0,branch=None,group=group.group_id,segment=0,attempt=0)
    initial_order=formation_slots(group,ctx.family,fkey,formation=retreat_chain(mapped_start(group.formation_prior))[0]).order
    slots=formation_slots(group,ctx.family,fkey,formation=name,lateral_step_m=step,order=initial_order)
    doc=TC.load_chord_set(ctx,task.target_id,slots,ctx.cache_dir,intent="area_search")
    sectors=feasible_sector_cells(ctx,task.target_id,len(group.member_ids),ctx.family.task_altitude_m)
    ao=float(ctx.facility_by_id[task.target_id].offsets["warning"])-12.5-.4*ctx.family.task_altitude_m
    entries=filter_entry_cells(ctx,task.target_id,doc["cells"],sectors,ao,offsets=slots.offsets)
    if not entries:
        return None,slots,seq
    chord,sector,c=draw_hierarchy(entries,rng_for(key))
    selection={"theta_idx":int(chord["cell"][0]),"h_m":float(chord["cell"][1]),"mu_deg":sector["mu_deg"],"span_deg":sector["span_deg"],"c":c,
               "beta_deg":chord["beta_deg"],"formation":slots.realized,"members":len(group.member_ids)}
    return selection,slots,seq


def packet_worker(arg):
    order,draw,cache=arg
    ctx,group,task,key=setup(order,draw,cache)
    selection,slots,_=select(ctx,group,task,key)
    doc=TC.load_chord_set(ctx,task.target_id,slots,ctx.cache_dir,intent="area_search")
    sectors=feasible_sector_cells(ctx,task.target_id,len(group.member_ids),ctx.family.task_altitude_m)
    packet={"chords":{k:doc[k] for k in ("cells","reasons","n_cells")},"sectors":sectors,"selection":selection}
    return {"order":order,"draw":draw,"sha256":hashlib.sha256(raw(packet)).hexdigest(),"selection":selection}


def main():
    OUT.mkdir(exist_ok=False)
    sources={str(p.relative_to(CODE)):hashlib.sha256(p.read_bytes()).hexdigest()
             for root in (CODE/"v08",CODE/"tools/v08") for p in root.rglob("*.py")}
    save(OUT/"source_sha256.json",sources)
    started=time.perf_counter()
    # Cold means a new geometry/chord-cache directory; hot is the main-process prebuild.
    cold=OUT/"cold_cache";cold.mkdir()
    ctx,g,t,k=setup(34,3,cold)
    s0=time.perf_counter();plan=A.propose_and_build(ctx,g,t,initial_states(ctx.family,g.member_ids),k)
    save(OUT/"o34_d3_cold_plan.json",plan)
    cold_wall=time.perf_counter()-s0
    cold_timing=A.last_attempt_timing()
    _,slots,seq=select(ctx,g,t,k)
    offsets=[slots.offsets[m] for m in slots.order]
    memo=TC.assess_formation(ctx,t.target_id,offsets,intent="area_search")
    direct=TC.assess_formation(ctx,t.target_id,offsets,memo=False,intent="area_search")
    transit=TC.assess_formation(ctx,t.target_id,offsets,intent="transit")
    fields=("cells","reasons","n_cells")
    hashes=[hashlib.sha256(raw({x:d[x] for x in fields})).hexdigest() for d in (memo,direct,transit)]
    area_qid,area_ident=TC.query_identity(ctx,t.target_id,offsets,intent="area_search")
    old_qid,old_ident=TC.query_identity(ctx,t.target_id,offsets,intent="transit")
    assert len(set(hashes))==1,"combined/direct/transit chord bytes differ"
    assert area_qid!=old_qid and area_ident["version"]=="area_search-v20"
    chord_cache=TC.prewarm_transit(ctx,[(t.target_id,offs) for _,_,offs in seq],cold,intent="area_search")
    sector_cache=write_sector_cache(ctx,t.target_id,len(g.member_ids),ctx.family.task_altitude_m)
    ctx2,g2,t2,k2=setup(34,3,cold)
    s0=time.perf_counter();hot=A.propose_and_build(ctx2,g2,t2,initial_states(ctx2.family,g2.member_ids),k2)
    hot_wall=time.perf_counter()-s0;hot_timing=A.last_attempt_timing()
    save(OUT/"o34_d3_hot_plan.json",hot)
    assert raw(plan)==raw(hot),"cold/hot full plan bytes differ"
    save(OUT/"cache_proof.json",{"passed":True,"chord_hashes":dict(zip(("memo","direct","transit"),hashes)),
         "area_query_id":area_qid,"transit_query_id":old_qid,"cold_full_plan_wall_s":cold_wall,"hot_full_plan_wall_s":hot_wall,
         "cold_timing":cold_timing,"hot_timing":hot_timing,"full_plan_sha256":hashlib.sha256(raw(plan)).hexdigest(),
         "chord_cache":chord_cache,"sector_cache":sector_cache})
    print("PASS combined/direct/transit and cold/hot complete plan",flush=True)
    requests=[(34,3,cold),(11,0,ROOT/"cache")]
    one=[packet_worker(arg) for arg in requests]
    with ProcessPoolExecutor(max_workers=2) as pool:
        two=list(pool.map(packet_worker,requests))
    assert one==two,"1/2 process order or packet bytes differ"
    save(OUT/"one_two_process.json",{"passed":True,"single":one,"two":two})
    print("PASS one/two process packets",flush=True)
    # Verify the preview against already-completed production-builder selections.
    previews=[]
    for order,draw in ((11,0),(17,1)):
        cc,gg,tt,kk=setup(order,draw,ROOT/"cache")
        selection,_,_=select(cc,gg,tt,kk)
        real=json.loads((ROOT/f"cost_ruling_r1/real12_r1/o{order:02d}_d{draw}/plan.json").read_text())
        for field in ("theta_idx","h_m","mu_deg","span_deg","c","beta_deg"):
            assert selection[field]==real["proposal"][field],field
        previews.append({"order":order,"draw":draw,"selection":selection,"matches_full_builder":True})
    # Maximum-sector diagnostic uses the first registered N12 attempt-0 key whose
    # unchanged production shape selection has span90; no forced draw or retry.
    public=json.loads((ROOT/"snapshot/part1_r1/public_metadata.json").read_text())
    candidates=sorted((int(r["order"]),int(r["draw_index"])) for r in public if r["group_size"]==12)
    maximum=None
    for order,draw in candidates:
        cc,gg,tt,kk=setup(order,draw,ROOT/"cache")
        selection,_,seq=select(cc,gg,tt,kk)
        previews.append({"order":order,"draw":draw,"selection":selection})
        save(OUT/f"preview_{order:02d}_{draw}.json",previews[-1])
        if selection is not None and selection["span_deg"]==90:
            begin=time.perf_counter();full=A.propose_and_build(cc,gg,tt,initial_states(cc.family,gg.member_ids),kk)
            save(OUT/"maximum_n12_span90_plan.json",full)
            maximum={"order":order,"draw":draw,"selection":selection,"wall_s":time.perf_counter()-begin,
                     "failure":jsonable(full.failure),"timing":A.last_attempt_timing()}
            assert full.proposal["span_deg"]==90 and len(gg.member_ids)==12
            break
    assert maximum is not None,"no maximum-sector example completed"
    save(OUT/"maximum_query.json",maximum)
    save(OUT/"selection_previews.json",previews)
    save(OUT/"summary.json",{"passed":True,"wall_s":time.perf_counter()-started,"maximum":maximum,
                             "rng_proof":"separate script still required"})
    print(json.dumps({"remaining_geometry_passed":True,"maximum":maximum}),flush=True)

if __name__=="__main__":
    main()
