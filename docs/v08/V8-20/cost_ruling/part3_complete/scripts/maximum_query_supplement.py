"""Registered attempt-key stress query; never a production retained contract."""
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path

from part3_remaining_checks import BASE,CODE,ROOT,OUT,setup,save,raw,A,T,TC
from v08.motion.area_search_geometry import feasible_sector_cells,filter_entry_cells
from v08.motion.area_search_numeric import draw_hierarchy
from v08.motion.formation import formation_slots,mapped_start,retreat_chain
from v08.sampler.keys import RngKey,rng_for
from v08.contract.monitoring import initial_states


def preview(ctx,group,task,key):
    seq=T.formation_probe_sequence(ctx,group,task,key,chord_intent="area_search")
    if not seq:
        return None
    fkey=replace(key,purpose="formation")
    name,step,_=seq[-1]
    original=formation_slots(group,ctx.family,fkey,formation=retreat_chain(mapped_start(group.formation_prior))[0]).order
    slots=formation_slots(group,ctx.family,fkey,formation=name,lateral_step_m=step,order=original)
    doc=TC.load_chord_set(ctx,task.target_id,slots,ctx.cache_dir,intent="area_search")
    sectors=feasible_sector_cells(ctx,task.target_id,len(group.member_ids),ctx.family.task_altitude_m)
    ao=float(ctx.facility_by_id[task.target_id].offsets["warning"])-12.5-.4*ctx.family.task_altitude_m
    entries=filter_entry_cells(ctx,task.target_id,doc["cells"],sectors,ao,offsets=slots.offsets)
    if not entries:
        return None
    chord,sector,c=draw_hierarchy(entries,rng_for(key))
    return {"theta_idx":int(chord["cell"][0]),"h_m":float(chord["cell"][1]),"mu_deg":sector["mu_deg"],
            "span_deg":sector["span_deg"],"c":c,"beta_deg":chord["beta_deg"]}


def main():
    out=ROOT/"cost_ruling_r1/maximum_supplement_r1"
    out.mkdir(exist_ok=False)
    started=time.perf_counter()
    old=[]
    for p in sorted(OUT.glob("preview_*.json")):
        old.append(json.loads(p.read_text(encoding="utf-8")))
    save(out/"self_test_expectation_fix.json",{
        "category":"self_added_test_expectation_wrong","original_assertion":"some registered N12 attempt0 must draw span90",
        "counterexamples":old,"original_script_sha256":hashlib.sha256((Path(__file__).parent/"part3_remaining_checks.py").read_bytes()).hexdigest(),
        "fix":"diagnostic request may use the unchanged registered attempt keys 0..19; no production sampling or success selection changes",
        "production_code_modified":False,"previous_cache_and_process_checks_rerun":False})
    previews=[]
    ctx,g,t,k0=setup(34,3,OUT/"cold_cache")
    maximum=None
    for attempt in range(20):
        key=replace(k0,attempt=attempt)
        selection=preview(ctx,g,t,key)
        row={"order":34,"draw":3,"attempt":attempt,"selection":selection,"diagnostic_only":True}
        previews.append(row)
        save(out/f"preview_a{attempt:02d}.json",row)
        if selection is None or selection["span_deg"]!=90:
            continue
        begin=time.perf_counter()
        plan=A.propose_and_build(ctx,g,t,initial_states(ctx.family,g.member_ids),key)
        build_wall=time.perf_counter()-begin
        save(out/"plan.json",plan)
        assert all(plan.proposal[field]==selection[field] for field in selection)
        maximum={**row,"wall_s":build_wall,"failure":plan.failure,"timing":A.last_attempt_timing(),
                 "constructed_independent_members":len((plan.witnesses or {}).get("independent_members",{}))}
        break
    assert maximum is not None,"no maximum-sector request found in the original 20 keys"
    save(out/"result.json",{"passed":True,"maximum":maximum,"wall_s":time.perf_counter()-started,"previews":previews,
                            "production_retained":False,"no_retry_inside_any_attempt":True})
    print(raw(maximum).decode(),flush=True)


if __name__=="__main__":
    main()
