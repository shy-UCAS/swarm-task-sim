import json
from pathlib import Path

ep_dir = Path('verification/v03_pilot_final_20260930/dataset/episodes/20260930T153623Z_af3f4fcd')

with open(ep_dir / 'manifest.json') as f:
    manifest = json.load(f)

run_dir_str = manifest.get('run_directory', '')
print(f"run_directory字符串: {run_dir_str}")

run_dir = Path(run_dir_str)
print(f"run_dir.exists(): {run_dir.exists()}")

if run_dir.exists():
    print(f"\n目录内容:")
    for item in run_dir.iterdir():
        print(f"  {item.name}")
else:
    print("\n尝试相对路径...")
    # 可能是相对路径
    rel_run_dir = Path(run_dir_str)
    if rel_run_dir.exists():
        print(f"相对路径存在")
