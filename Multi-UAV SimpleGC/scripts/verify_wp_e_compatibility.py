"""Real v2 mixed-analysis export compatibility using new copies only."""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from swarm_sim.dataset import build_dataset
from swarm_sim.episode_loader import load_episode
from swarm_sim.recording import write_json


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True,type=Path)
    output=parser.parse_args().output.resolve(); output.mkdir(parents=True,exist_ok=False)
    original=read(ROOT/"verification/v03_integration_20260930/dataset_final/dataset_manifest.json")["episodes"][0]
    updated=read(ROOT/"tmp_v04/wp_g/final_regression/legacy_regression.json")["R05"]["runs"][1]
    cases=[("pre_metrics_v03",Path(original["source_run"])),("post_metrics_v04",Path(updated["copy"]))]
    sources=[]; expected={}; presence={}
    for name,source in cases:
        destination=output/name
        shutil.copytree(source,destination)
        analysis=destination/read(destination/"analysis_latest.json")["directory"]
        expected[name]=load_episode(analysis)
        presence[name]=(analysis/"execution_metrics.json").is_file()
        sources.append(destination)
    assert presence=={"pre_metrics_v03":False,"post_metrics_v04":True},presence
    dataset=build_dataset(sources,output/"mixed_dataset")
    results=[]
    for (name,_),entry in zip(cases,dataset["episodes"]):
        actual=load_episode(output/"mixed_dataset"/entry["directory"])
        compared={key:actual[key]==expected[name][key] for key in ("x","mask","t_s","agent_ids","targets")}
        assert all(compared.values()),compared
        results.append(dict(case=name,run_id=entry["run_id"],analysis_version=entry["analysis_version"],
                            has_execution_metrics=presence[name],unchanged_after_export=compared))
    report=dict(status="PASS",evidence_class="existing_SITL_copies_offline_export_no_reanalysis",new_sitl_runs=0,
                episodes=results,semantic_protocol=dataset["semantic_protocol"],
                compatibility="optional versioned diagnostic attachment; same semantic and quality policy protocol; loader still takes six features")
    write_json(output/"compatibility.json",report)
    print(json.dumps(report))


if __name__=="__main__": main()
