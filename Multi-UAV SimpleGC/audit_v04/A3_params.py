"""A3: 提取任务文件与模板中的参数实际值"""
import json

FILES = [
    "missions/recon_shared_3uav.json",
    "missions/recon_smoke_3uav.json",
    "missions/recon_smoke_2uav_north.json",
    "missions/recon_smoke_6uav.json",
    "generation_profiles/recon_pilot_v03.json",
]

KEYS_EXEC = ["waypoint_hold_s", "confirmation_dwell_s", "arrival_tolerance_m", "speed_m_s"]
KEYS_PLAN = ["lane_spacing_m"]

def walk(obj, path=""):
    """Yield (path, key, value) for every dict entry at any depth."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            yield (p, k, v)
            yield from walk(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")

for path in FILES:
    print(f"\n{'='*70}")
    print(f"文件: {path}")
    print('='*70)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    print(f"顶层键: {list(data.keys())}")
    for p, k, v in walk(data):
        if k in KEYS_EXEC + KEYS_PLAN:
            if isinstance(v, (int, float, str, bool)) or v is None:
                print(f"  {p} = {v!r}")
            elif isinstance(v, dict):
                print(f"  {p} = <dict, keys={list(v.keys())}>")
            elif isinstance(v, list):
                print(f"  {p} = <list, len={len(v)}>")
            else:
                print(f"  {p} = {v!r}")
