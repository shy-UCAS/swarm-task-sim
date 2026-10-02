import json
from pathlib import Path

ep_dir = Path('verification/v03_pilot_final_20260930/dataset/episodes/20260930T153623Z_af3f4fcd')

# 检查manifest结构
with open(ep_dir / 'manifest.json') as f:
    manifest = json.load(f)

print("manifest顶层键:", list(manifest.keys()))

# 检查scenario位置
if "scenario" in manifest:
    print("\nscenario在manifest顶层")
    scenario = manifest["scenario"]
elif "task_spec" in manifest:
    print("\ntask_spec在manifest顶层")
    if "scenario" in manifest["task_spec"]:
        print("scenario在task_spec内")
        scenario = manifest["task_spec"]["scenario"]
    else:
        print("task_spec内没有scenario")
        scenario = manifest["task_spec"]
else:
    print("\n未找到scenario或task_spec")
    scenario = None

if scenario and "phases" in scenario:
    print(f"\nphases数量: {len(scenario['phases'])}")
    print(f"第一个phase: {scenario['phases'][0]['name']}")
else:
    print("\nscenario中没有phases")
    
# 检查是否在其他文件
task_path = ep_dir / 'task.json'
if task_path.exists():
    with open(task_path) as f:
        task = json.load(f)
    print(f"\ntask.json顶层键: {list(task.keys())}")
    if "phases" in task:
        print(f"phases在task.json中，数量: {len(task['phases'])}")
