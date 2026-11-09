import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from audit_geometry_cache_r2 import RUN, C, F, TC, setup, write

row = json.loads((RUN / "diagnostics/part3_query_enumeration_r1/summary.json").read_text(encoding="utf-8"))["maximum"]
cache = RUN / "cache/part3_max_single_lane_r1"
assert not cache.exists()
ctx, group, task, states, key = setup(row["order"], row["draw"], C.INTENT, cache)
slots = F.formation_slots(group, ctx.family, key, formation=row["formation"], lateral_step_m=row["lateral_step_m"])
mid = max(sorted(slots.order), key=lambda m: abs(slots.offsets[m][1]))
y = slots.offsets[mid][1]
start = time.perf_counter()
lanes = TC.get_lanes(ctx, task.target_id, 0, [y], intent=C.INTENT)
analytic = time.perf_counter() - start
start = time.perf_counter()
TC._sample_lanes(ctx, task.target_id, lanes, intent=C.INTENT)
sample = time.perf_counter() - start
start = time.perf_counter()
TC._sample_lanes(ctx, task.target_id, TC.get_lanes(ctx, task.target_id, 0, [y], intent=C.INTENT), intent=C.INTENT)
hot = time.perf_counter() - start
doc = {"maximum_query_source": row, "member": mid, "theta_idx": 0, "h_m": 0., "lane_offset_m": y,
       "analytic_cold_s": analytic, "sampling_with_cold_geometry_field_s": sample, "cold_total_s": analytic + sample,
       "hot_s": hot, "sample_points": len(lanes[0].xs), "legal_runs": lanes[0].runs,
       "scope": "one actual extreme-offset lane from the maximum actual formation; separate from 12-lane batch cost"}
write(RUN / "diagnostics/part3_max_single_lane_r1.json", doc)
print(json.dumps(doc), flush=True)
