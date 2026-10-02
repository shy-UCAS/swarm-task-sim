"""A5: 每个运行的时间构成"""
import json
from pathlib import Path

# 读取dataset获取前5个episode
dataset_path = Path("verification/v03_pilot_final_20260930/dataset")
manifest_path = dataset_path / "dataset_manifest.json"
with open(manifest_path) as f:
    manifest = json.load(f)

all_episodes = []
for ep_info in manifest["episodes"][:5]:
    run_id = ep_info["run_id"]
    all_episodes.append({
        "episode_id": run_id,
        "episode_dir": dataset_path / "episodes" / run_id,
    })

print(f"分析 {len(all_episodes)} 个episode\n")

time_breakdown = []

for ep in all_episodes:
    ep_dir = ep["episode_dir"]
    
    # 读取manifest获取run_directory
    manifest_path = ep_dir / "manifest.json"
    with open(manifest_path) as f:
        ep_manifest = json.load(f)
    
    run_dir = Path(ep_manifest["run_directory"])
    
    # 读取events.jsonl
    events_path = run_dir / "events.jsonl"
    
    events = []
    with open(events_path) as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    
    # 提取关键时间点
    first_armed = None
    first_phase_start = None
    last_phase_end = None
    first_land = None
    
    for event in events:
        if event["event"] == "armed_confirmed" and first_armed is None:
            first_armed = event["t"]
        elif event["event"] == "phase_start_sent" and first_phase_start is None:
            first_phase_start = event["t"]
        elif event["event"] == "phase_finished":
            last_phase_end = event["t"]  # 不断更新
        elif event["event"] == "landed" and first_land is None:
            first_land = event["t"]
    
    if first_armed and first_phase_start and last_phase_end and first_land:
        startup_time = first_phase_start - first_armed
        mission_time = last_phase_end - first_phase_start
        shutdown_time = first_land - last_phase_end
        total_time = first_land - first_armed
        
        time_breakdown.append({
            "episode_id": ep["episode_id"],
            "arm_to_first_phase_s": startup_time,
            "first_to_last_phase_s": mission_time,
            "last_phase_to_land_s": shutdown_time,
            "total_armed_time_s": total_time,
            "mission_ratio": mission_time / total_time if total_time > 0 else 0,
        })
        
        print(f"{ep['episode_id']}:")
        print(f"  武装到第一阶段: {startup_time:.2f} s")
        print(f"  任务执行(第一到最后阶段): {mission_time:.2f} s")
        print(f"  最后阶段到降落: {shutdown_time:.2f} s")
        print(f"  总时长: {total_time:.2f} s")
        print(f"  任务占比: {mission_time/total_time*100:.1f}%\n")

# 保存数据
with open("audit_v04/A5_time_breakdown.json", "w") as f:
    json.dump(time_breakdown, f, indent=2)

# 统计
if time_breakdown:
    startup_times = [t["arm_to_first_phase_s"] for t in time_breakdown]
    mission_times = [t["first_to_last_phase_s"] for t in time_breakdown]
    shutdown_times = [t["last_phase_to_land_s"] for t in time_breakdown]
    total_times = [t["total_armed_time_s"] for t in time_breakdown]
    
    print(f"总体统计 (n={len(time_breakdown)}):")
    print(f"  启动平均: {sum(startup_times)/len(startup_times):.2f} s ({sum(startup_times)/sum(total_times)*100:.1f}%)")
    print(f"  任务平均: {sum(mission_times)/len(mission_times):.2f} s ({sum(mission_times)/sum(total_times)*100:.1f}%)")
    print(f"  关闭平均: {sum(shutdown_times)/len(shutdown_times):.2f} s ({sum(shutdown_times)/sum(total_times)*100:.1f}%)")
    print(f"  总时长平均: {sum(total_times)/len(total_times):.2f} s")

print("\nA5分析完成")
