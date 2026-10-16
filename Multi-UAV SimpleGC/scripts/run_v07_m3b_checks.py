"""Full M3b input registration and short frozen-capability checks."""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import subprocess
import sys
import time
import unittest
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from task_v07.io import read_json,sha
from scripts.run_v07_m3_checks import EVIDENCE
from scripts.run_v07_m3_trial import atomic,frozen_check


def register():
    old=read_json(EVIDENCE/"m3_inputs.json"); frozen_check(old)
    source=Path(old["descriptor_attempt"])
    if sha(source/"private_skeleton_descriptors.json")!=old["descriptor_sha256"]:
        raise ValueError("Fixed descriptor source changed")
    qd=read_json(PROJECT/"docs/v07/evidence/m2/qd_summary.json")
    descriptors=read_json(source/"private_skeleton_descriptors.json"); by_id={d["skeleton_id"]:d for d in descriptors}
    selected=[]
    for row in qd["rows"]:
        sid=row["skeleton_id"]; d=by_id[sid]; intent=d["base_intent"]; approach=d["common_draw"]["approach_mode"]
        other=sorted(r["skeleton_id"] for r in descriptors if r["subset"]=="regular" and r["base_intent"]==intent
                     and r["common_draw"]["approach_mode"]==approach and r["skeleton_id"]!=sid)
        if not other: raise ValueError(f"输入不足: {intent}/{approach}")
        for candidate in (sid,other[0]):
            selected.append({"skeleton_id":candidate,"intent":intent,"approach_mode":approach,"q3":candidate==sid})
    if len(selected)!=20 or len({r["skeleton_id"] for r in selected})!=20: raise ValueError("Expected 20 distinct fixed inputs")
    for asset in old["source_assets"]:
        if sha(Path(asset["path"]))!=asset["sha256"]: raise ValueError("Public scene source changed")
    result={**deepcopy(old),"selected":selected,"baseline":subprocess.check_output(["git","rev-parse","HEAD"],cwd=PROJECT,text=True).strip(),
        "geometry_config_sha256":sha(PROJECT/"configs/generator/geometry_v07_r1.json"),
        "q2_wall_limit_s":900,"q3_wall_limit_s":5400,"q3_step1_wall_limit_s":1800,"max_workers":8,
        "q2_gate":"all 10 cells nonempty AND all 10 fixed Q3 skeletons eligible, on final geometry",
        "q3_step1_skeletons":["family_s12_4d13d93f9171c446_ext_006_regular","family_s12_4d13d93f9171c446_ext_007_regular"],
        "approved_patrol_change":"group-unique radius blocks by split_index; continuous offset entry; fixed lane on reversal",
        "additional_branches":"Register missing observation/arc frozen-fastsim integration only if fixed Q3 does not cover it"}
    atomic(EVIDENCE/"m3b_inputs.json",result)
    print(json.dumps({"registered":selected,"frozen":frozen_check(result)},ensure_ascii=False))


def unit():
    sys.path.insert(0,str(PROJECT/"tests"))
    names=["test_v07_m3_geometry","test_v07_m3_integration","test_v07_m3b_geometry","test_v07_m1_criteria","test_v07_m2_timing_rehearsal",
        "test_v07_s2_search_revision.SearchEvidenceTests.test_empty_first_group_does_not_censor_other_group_budgets",
        "test_v07_s2_revision_continuous.ContinuousRevisionTests.test_every_registered_candidate_is_counted_without_calibration"]
    start=time.perf_counter(); frozen=frozen_check(read_json(EVIDENCE/"m3_inputs.json"))
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
    atomic(EVIDENCE/"m3b_checks.json",{"status":"PASS" if result.wasSuccessful() else "FAIL","tests_run":result.testsRun,
        "failures":[(str(t),s) for t,s in result.failures],"errors":[(str(t),s) for t,s in result.errors],"skipped":result.skipped,
        "test_entries":names,"wall_s":time.perf_counter()-start,"frozen_check":frozen,
        "legacy_backend_selection_changed_in_m3b":[],
        "capability_test_update":"G11 unsupported request uses unsupported_method because monitoring is now implemented"})
    return 0 if result.wasSuccessful() else 1


if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("action",choices=("register","unit")); args=parser.parse_args()
    if args.action=="register": register()
    else: raise SystemExit(unit())
