"""Single-process prescribed cost query; no trajectory attempt or random draw."""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

BASE=Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO=BASE/"Simulation-v08";CODE=REPO/"Multi-UAV SimpleGC"
TASK=BASE/"_handoff/2026-11-09_V8-20_area_search";RUN=TASK/"run"
sys.path.insert(0,str(CODE))

from v08.contract.single_intent import area_search_mission
from v08.motion.area_search_geometry import feasible_sector_cells,write_sector_cache,sector_identity
from v08.runner.monitoring import load_entries,write_json
from v08.sampler.common import sample_common
from v08.scene.context import load_context

def dump(p,data):
    with p.open("x",encoding="utf-8",newline="\n") as f:
        json.dump(data,f,ensure_ascii=False,indent=1);f.write("\n");f.flush();os.fsync(f.fileno())

def main():
    out=RUN/"cost_ruling_r1/sector_o34_d3"
    out.mkdir(exist_ok=False)
    sources={str(p.relative_to(CODE)):hashlib.sha256(p.read_bytes()).hexdigest()
             for root in (CODE/"v08",CODE/"tools/v08") for p in root.rglob("*.py")}
    dump(out/"source_sha256.json",sources)
    entry=next(e for e in load_entries(REPO/"docs/v08/V8-03/devset_v08.json") if int(e["order"])==34)
    ctx=load_context(entry,data_root=BASE/"SwarmData",cache_dir=RUN/"cache")
    mission=area_search_mission(ctx,sample_common(ctx.family,3))
    group,task=mission.groups[0],mission.tasks[0]
    assert len(group.member_ids)==12
    qid,_=sector_identity(ctx,task.target_id,12,ctx.family.task_altitude_m)
    cache=RUN/"cache/area_search_v20/sector_sets"/(qid+".json")
    assert not cache.exists(),"Required cold query already cached"
    started=time.perf_counter()
    cells=feasible_sector_cells(ctx,task.target_id,12,ctx.family.task_altitude_m)
    wall=time.perf_counter()-started
    result={"order":34,"draw":3,"members":12,"target_id":task.target_id,"query_id":qid,
            "wall_s":wall,"previous_sector_wall_s":417.8906156000003,
            "projected_wall_s":wall*151/24,"registered_unique_queries":151,"projection_workers":24,
            "maximum_feasible_span_deg":max((c["span_deg"] for c in cells),default=None),
            "sector_cells":len(cells),"c_choices":sum(len(c["choices"]) for c in cells),
            "passed":wall*151/24<=1800.,"single_process":True}
    dump(out/"result.json",result)
    cachefact=write_sector_cache(ctx,task.target_id,12,ctx.family.task_altitude_m)
    dump(out/"cache.json",cachefact)
    print(json.dumps(result),flush=True)
    return 0 if result["passed"] else 2

if __name__=="__main__":
    raise SystemExit(main())
