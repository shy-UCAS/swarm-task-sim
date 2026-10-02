"""Seal actual offline evidence; never launch SITL or overwrite an acceptance."""
import hashlib
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"tmp_v04/wp_e"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=OUT)
    parser.add_argument("--prior-evidence",type=Path,default=OUT)
    args=parser.parse_args()
    output=args.output_dir.resolve(); prior=args.prior_evidence.resolve()
    tests_path=output/"unit_test_results_final.json"
    tests=read(tests_path)
    assert tests["status"]=="PASS" and tests["R01"]["status"]=="PASS"
    assert tests["tests_run"]==len(tests["tests"])==tests["outcomes"].get("PASS")
    assert all(sha(ROOT/name)==value for name,value in tests["source_sha256"].items())
    regression=read(prior/"legacy_regression/legacy_regression.json")
    compatibility=read(prior/"v2_mixed_analysis/compatibility.json")
    preservation=read(output/"pre_sitl_preservation.json")
    assert preservation["unchanged"] and compatibility["status"]=="PASS"
    checks={}; evidence={}
    for key in [f"E{i:02d}" for i in range(1,11)]+["R06"]:
        matches=[row for row in tests["tests"] if key in row["id"]]
        assert matches and all(row["status"]=="PASS" for row in matches),key
        checks[key]="PASS"; evidence[key]=[row["id"] for row in matches]
    checks["R01"]="PASS"; evidence["R01"]=tests["R01"]
    for key in ("R02","R03","R04","R05"):
        assert regression[key]["status"]=="PASS",key
        checks[key]="PASS"; evidence[key]={k:v for k,v in regression[key].items() if k in ("status","count","dataset_count")}
    required_modules=("test_analysis_v3","test_route_analysis_integration","test_run_provenance","test_route_timing")
    assert all(tests["modules"].get(name,{}).get("PASS",0)>0 for name in required_modules)
    supporting=[prior/"legacy_regression/legacy_regression.json",prior/"v2_mixed_analysis/compatibility.json",output/"pre_sitl_preservation.json"]
    result=dict(status="PASS",checks=checks,evidence=evidence,created_utc=datetime.now(timezone.utc).isoformat(),
        evidence_class="offline_only; logical, mock, hand-built trajectories, existing historical copies",
        new_sitl_runs=0,tests_path=tests_path.relative_to(ROOT).as_posix(),tests_sha256=sha(tests_path),
        supporting_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in supporting})
    if output!=OUT:
        from sys import path
        path.insert(0,str(ROOT))
        from swarm_sim.run_provenance import PARAMETER_COMPARISON_VERSION
        assert PARAMETER_COMPARISON_VERSION=="wp_s_parameter_comparison_v2"
        assert tests["modules"].get("test_parameter_comparison_v2",{}).get("PASS",0)>0
        result["parameter_comparison_version"]=PARAMETER_COMPARISON_VERSION
    with (output/"offline_acceptance.json").open("x",encoding="utf-8") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(status=result["status"],checks=checks,tests=tests["tests_run"],new_sitl_runs=0)))


if __name__=="__main__": main()
