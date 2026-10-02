import json
from pathlib import Path

ep_dir = Path('verification/v03_pilot_final_20260930/dataset/episodes/20260930T153623Z_af3f4fcd')

# 读取phase_windows
with open(ep_dir / 'phase_windows.json') as f:
    pw = json.load(f)

# 读取allocation
with open(ep_dir / 'allocation.json') as f:
    alloc = json.load(f)

# 显示第一个observe窗口
observe_windows = [w for w in pw['windows'] if w['semantic_phase'] == 'observe']
print(f'总observe窗口: {len(observe_windows)}')
print(f'\n第一个observe窗口:')
print(f"  agent: {observe_windows[0]['agent_id']}")
print(f"  start: {observe_windows[0]['start_s']:.2f}s")
print(f"  end: {observe_windows[0]['end_s']:.2f}s")
print(f"  duration: {observe_windows[0]['end_s'] - observe_windows[0]['start_s']:.2f}s")

# 显示对应的路线
agent = observe_windows[0]['agent_id']
route = alloc['per_agent_reference_routes'][agent]['observe']
print(f'\n{agent} observe路线航点数: {len(route)}')
print(f'前3个航点:')
for i, pt in enumerate(route[:3]):
    print(f'  {i}: east={pt["east_m"]:.2f}, north={pt["north_m"]:.2f}')

# 检查问题：窗口是单个observe阶段，还是整个observe语义的合并？
print(f'\nwindow_source: {pw["source"]}')
