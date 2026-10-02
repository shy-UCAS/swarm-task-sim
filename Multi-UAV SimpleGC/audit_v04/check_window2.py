import json
from pathlib import Path

ep_dir = Path('verification/v03_pilot_final_20260930/dataset/episodes/20260930T153623Z_af3f4fcd')

with open(ep_dir / 'phase_windows.json') as f:
    pw = json.load(f)

print("第一个窗口的所有字段:")
print(json.dumps(pw['windows'][0], indent=2))
