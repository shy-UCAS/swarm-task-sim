"""A3: 统计100个已生成任务中的参数分布"""
import json
from pathlib import Path
from collections import Counter

missions_dir = Path("generated/recon_pilot_v03_20260930/missions")
files = sorted(missions_dir.glob("*.json"))
print(f"任务文件数: {len(files)}")

counters = {
    "waypoint_hold_s": Counter(),
    "confirmation_dwell_s": Counter(),
    "arrival_tolerance_m": Counter(),
    "speed_m_s": Counter(),
    "lane_spacing_m": Counter(),
}

for fp in files:
    with open(fp, encoding="utf-8") as f:
        data = json.load(f)
    ex = data["execution"]
    pl = data["planner"]
    counters["waypoint_hold_s"][ex["waypoint_hold_s"]] += 1
    counters["confirmation_dwell_s"][ex["confirmation_dwell_s"]] += 1
    counters["arrival_tolerance_m"][ex["arrival_tolerance_m"]] += 1
    counters["speed_m_s"][ex["speed_m_s"]] += 1
    counters["lane_spacing_m"][pl["lane_spacing_m"]] += 1

for key, c in counters.items():
    print(f"\n{key}:")
    for value, n in sorted(c.items(), key=lambda kv: (kv[0] is None, kv[0])):
        print(f"  {value!r}: {n}/{len(files)}")
