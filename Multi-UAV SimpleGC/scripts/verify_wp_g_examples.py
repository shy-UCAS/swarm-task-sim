"""Persist offline CLI and measured family examples for the WP-G milestone."""
import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from swarm_sim.dataset import build_dataset, family_split
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.families import family_metadata
from swarm_sim.generation import canonical_hash, verify_generation
from swarm_sim.mission_v3 import normalize_v3
from swarm_sim.recording import write_json
from swarm_sim.registry import registered_intents, temporary_registration
from swarm_sim.tasks import compile_task


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=False)
    original=json.loads((ROOT/"missions/v3/recon_shared_3uav_barrier.json").read_text(encoding="utf-8"))
    mutations=[("baseline",lambda s:None,True),
        ("coverage_0_8",lambda s:s["mission"]["intent_params"].update(coverage_required=.8),True),
        ("without_return",lambda s:s["mission"].update(return_required=False),True),
        ("lane_spacing_3",lambda s:s["planner"]["params"].update(lane_spacing_m=3),True),
        ("speed_2_5",lambda s:s["execution"].update(speed_m_s=2.5),True),
        ("rename_task_and_seed",lambda s:s.update(task_id="renamed_task",seed=9),True),
        ("region_width_55",lambda s:s["scenario"]["regions"][0].update(width_m=55),False),
        ("spawn_east_9_5",lambda s:s["scenario"]["vehicles"][0].update(east_m=9.5),False),
        ("heading_90",lambda s:s["scenario"]["vehicles"][0].update(heading_deg=90),False)]
    def renumber(spec):
        spec["scenario"]["vehicles"].reverse()
        for index,vehicle in enumerate(spec["scenario"]["vehicles"]):
            vehicle.update(id=f"agent_{index}",sysid=101+index)
    mutations.append(("renumber_and_reorder",renumber,True))
    measured=[]
    for name,mutation,same in mutations:
        task=copy.deepcopy(original); task.pop("family_id"); mutation(task)
        task=normalize_v3(task); compiled=compile_task(task)
        metadata=family_metadata(task)
        actual_same=metadata["family_id"]==original["family_id"]
        assert actual_same is same,name
        task_path=output/(name+".task.json"); write_json(task_path,task)
        measured.append(dict(case=name,**metadata,split=family_split(metadata["family_id"]),
                             task_sha256=canonical_hash(task),expected_same_family=same,
                             same_family=actual_same,compiled_phase_count=len(compiled["phases"]),
                             normalized_and_compiled=True,task_path=task_path.name))
    commands=[]
    for name in ("recon_shared_3uav", "recon_smoke_2uav_north", "recon_smoke_6uav"):
        destination=output/(name+".scene.json")
        steps=[(["plan",f"missions/v3/{name}_barrier.json","--output",str(destination)],0),
               (["validate",str(destination)],0)]
        for argv,expected in steps:
            result=subprocess.run([sys.executable,str(ROOT/"main.py"),*argv],cwd=ROOT,text=True,capture_output=True)
            commands.append(dict(argv=argv,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,expected=expected))
            assert result.returncode==expected,commands[-1]
    route_destination=output/"route_not_produced.json"
    result=subprocess.run([sys.executable,str(ROOT/"main.py"),"plan","missions/v3/recon_shared_3uav_route.json",
                           "--output",str(route_destination)],cwd=ROOT,text=True,capture_output=True)
    commands.append(dict(argv=["plan","missions/v3/recon_shared_3uav_route.json"],returncode=result.returncode,
                         stdout=result.stdout,stderr=result.stderr,expected="refusal until WP-E E1"))
    assert result.returncode!=0 and "WP-E E1" in result.stderr+result.stdout and not route_destination.exists()
    # Persist only measured summaries of the synthetic contract; fixture episodes are temporary.
    sys.path.insert(0,str(ROOT/"tests"))
    from v3_artifact_fixture import fixture_intent,make_run
    with tempfile.TemporaryDirectory() as tmp,temporary_registration(fixture_intent()):
        temp=Path(tmp); a,_=make_run(temp/"recon"); b,_=make_run(temp/"fixture",intent="test_fixture")
        data=build_dataset([a,b],temp/"dataset"); audit=audit_dataset(temp/"dataset")
        pair=[{k:e[k] for k in ("intent","family_id","split","episode_quality_eligible","mission_success")}
              for e in data["episodes"]]
        counterfactual=dict(evidence_class="synthetic_contract_only",episodes=pair,
                            family_split_leaks=audit["family_split_leaks"],
                            counterfactual_completeness=audit["counterfactual_completeness"])
        assert len({e["family_id"] for e in pair})==1 and len({e["split"] for e in pair})==1
        assert not audit["family_split_leaks"] and audit["counterfactual_completeness"]["complete"]
    assert registered_intents()==("reconnaissance",)
    listing,manifest=verify_generation(ROOT/"tmp_v04/wp_g/generated_v04_barrier/mission_list.json")
    generated=dict(task_count=len(listing["missions"]),family_count=len({e["family_id"] for e in listing["missions"]}),
                   artifact_count=len(manifest["artifact_sha256"]),all_hashes_valid=True,
                   evidence_class="planning_only_no_SITL")
    report=dict(status="PASS",new_sitl_runs=0,family_examples=measured,cli_checks=commands,
                synthetic_counterfactual=counterfactual,generated=generated)
    write_json(output/"examples_report.json",report)
    print(json.dumps(dict(status="PASS",family_examples=len(measured),cli_checks=len(commands),generated=generated)))


if __name__=="__main__": main()
