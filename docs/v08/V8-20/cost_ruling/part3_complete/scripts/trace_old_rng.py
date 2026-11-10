"""Observe old builders' real Generator calls and final PCG64 states."""
import argparse
import copy
import dataclasses
import json
import os
import sys
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument("--code",required=True)
parser.add_argument("--out",required=True)
args=parser.parse_args()
code=Path(args.code);out=Path(args.out);out.mkdir(exist_ok=False)
sys.path.insert(0,str(code))

import numpy as np
from v08.contract.monitoring import initial_states
from v08.contract.single_intent import mission_for_intent
from v08.motion.plan import plan_attempt
from v08.runner.monitoring import load_entries,jsonable
from v08.sampler.common import sample_common
from v08.sampler.keys import RngKey
from v08.scene.context import load_context

BASE=Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
ROOT=BASE/"_handoff/2026-11-09_V8-20_area_search/run"
entries=load_entries(BASE/"Simulation-v08/docs/v08/V8-03/devset_v08.json")
entry=next(e for e in entries if int(e["order"])==1)
original=np.random.Generator
observed=[]


class TraceGenerator(original):
    def __init__(self,bit_generator=None):
        super().__init__(bit_generator)
        frame=sys._getframe(1)
        key=frame.f_locals.get("key")
        self.record={"key":dataclasses.asdict(key) if dataclasses.is_dataclass(key) else None,
                     "initial_state":copy.deepcopy(self.bit_generator.state),"calls":[]}
        observed.append(self)


def logged(name):
    method=getattr(original,name)
    def invoke(self,*aa,**kw):
        before=jsonable(copy.deepcopy((aa,kw)))
        result=method(self,*aa,**kw)
        self.record["calls"].append({"method":name,"arguments":before,"result":jsonable(result)})
        return result
    return invoke


for name in ("integers","choice","permutation","shuffle","uniform","normal","random","standard_normal",
             "poisson","exponential","standard_exponential","multinomial","beta","dirichlet"):
    setattr(TraceGenerator,name,logged(name))
np.random.Generator=TraceGenerator


def save(path,obj):
    with path.open("x",encoding="utf-8",newline="\n") as f:
        json.dump(jsonable(obj),f,sort_keys=True,separators=(",",":"),ensure_ascii=False)
        f.write("\n");f.flush();os.fsync(f.fileno())


try:
    for intent in ("monitoring","transit","intrusion","feint","close_observation"):
        observed.clear()
        ctx=load_context(entry,data_root=BASE/"SwarmData",cache_dir=ROOT/"cache")
        mission=mission_for_intent(ctx,sample_common(ctx.family,1),intent)
        group,task=mission.groups[0],mission.tasks[0]
        key=RngKey(ctx.family.family_id,1,"shape",mission=0,branch=None,group=group.group_id,segment=0,attempt=0)
        plan=plan_attempt(ctx,group,task,initial_states(ctx.family,group.member_ids),(),key)
        streams=[]
        for generator in observed:
            streams.append({**generator.record,"final_state":copy.deepcopy(generator.bit_generator.state)})
        assert all(s["key"] is not None for s in streams),"Unattributed generator construction"
        save(out/(intent+".json"),{"intent":intent,"order":1,"draw":1,"attempt":0,
                                  "failure":jsonable(plan.failure),"streams":streams})
        print(json.dumps({"intent":intent,"generators":len(streams),"calls":sum(len(s["calls"]) for s in streams)}),flush=True)
finally:
    np.random.Generator=original
