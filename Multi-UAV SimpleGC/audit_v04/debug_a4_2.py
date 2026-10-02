import json
from pathlib import Path

ep_dir = Path('verification/v03_pilot_final_20260930/dataset/episodes/20260930T153623Z_af3f4fcd')

# 读取task.json
with open(ep_dir / 'task.json') as f:
    task = json.load(f)

print("task.json中是否有phases:", "phases" in task)

if "phases" not in task:
    print("\n检查scenario是否有phases:")
    if "scenario" in task:
        print("  scenario中是否有phases:", "phases" in task["scenario"])
        if "phases" in task["scenario"]:
            print(f"  phases数量: {len(task['scenario']['phases'])}")

# 检查shared_scene
shared_scene_path = ep_dir / 'shared_scene.json'
if shared_scene_path.exists():
    with open(shared_scene_path) as f:
        shared = json.load(f)
    print(f"\nshared_scene.json顶层键: {list(shared.keys())}")

# 实际上phases应该在哪？从runs目录的scenario.json读取
print("\n尝试从原始runs目录读取...")
# 根据manifest找到source run
with open(ep_dir / 'manifest.json') as f:
    manifest = json.load(f)

print(f"run_directory: {manifest.get('run_directory', 'NOT FOUND')}")
