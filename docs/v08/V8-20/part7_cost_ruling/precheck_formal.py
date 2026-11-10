"""Fast immutable checkpoint before a formal expensive stage."""
import argparse
import datetime
from evidence_utils import *

ap = argparse.ArgumentParser()
ap.add_argument("stage", choices=("skeleton", "quick", "full"))
args = ap.parse_args()
out = ROOT / ("precheck_" + args.stage + "_cost_ruling_r1.json")
assert not out.exists()
changes = audit()
pw = read(ROOT / "prewarm/area_cost_ruling_r1/prewarm.json")
checks = {
    "frozen_owners_inputs_presets_sources_unchanged": not changes,
    "part4_passed": read(DOC / "part4/checkpoint.json")["passed"],
    "combined_prewarm_complete": pw["complete"] and not pw["hard_stop"],
    "combined_prewarm_wall_le_2700": pw["wall_s"] <= 2700.,
    "combined_prewarm_40_families_200_draws": len(pw["rows"]) == 40 and len(pw["group_size"]) == 200,
    "maximum_single_query_projection_le_1800": read(ROOT / "smoke/prewarm_runtime_max_r1/result.json")["passed"],
    "ten_legacy_gates": len(read(DOC / "acceptance.json")["gates"]) == 10,
}
if args.stage in ("quick", "full"):
    checks["skeleton_checkpoint_passed"] = read(ROOT / "skeleton/area_cost_ruling_r1/summary.json")["checkpoint"]["passed"]
    preflight = read(ROOT / "part4_r1/full_preflight_r2/disk_verification.json")
    checks["final_format_retained_preflight_disk_verified"] = preflight["passed"] and preflight["checked_successes"] == 1 and not preflight["p0_violations"]
    from v08.runner.area_search_serialization import assert_contract_payload
    count = 0
    for p in (ROOT / "part4_r1/full_preflight_r2/contracts").rglob("*.json"):
        assert_contract_payload(read(p))
        count += 1
    checks["retained_preflight_recursive_scan"] = count >= 3
if args.stage == "full":
    q = read(ROOT / "quick/area_cost_ruling_r1/summary.json")
    checks["quick_checkpoint_passed"] = q["complete"] and not q["checkpoint"]["triggered"]
    checks["quick_disk_passed"] = not read(ROOT / "quick/area_cost_ruling_r1/disk_verification.json")["main"]["p0_violations"]
    lists = read(DOC / "manifest.json")["lists"]
    checks["fixed_200_100_5_lists"] = len(lists["full"]) == 200 and len(lists["diversity"]) == 100 and len(lists["rerun"]) == 5
result = {"stage": args.stage, "passed": all(checks.values()), "checks": checks,
          "audit_changes": changes, "excluded_contracts": [],
          "utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
dump(out, result, exclusive=True)
print(json.dumps(result, ensure_ascii=False), flush=True)
raise SystemExit(0 if result["passed"] else 2)
