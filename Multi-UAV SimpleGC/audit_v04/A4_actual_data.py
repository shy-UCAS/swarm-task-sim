"""A4: 实测验证 - 用已有数据量化停靠"""
import json
import math
from pathlib import Path

# 读取两个dataset的manifest获取episode列表
datasets = {
    "v03_pilot_final": Path("verification/v03_pilot_final_20260930/dataset"),
    "v03_integration": Path("verification/v03_integration_20260930/dataset_final"),
}

all_episodes = []
for dataset_name, dataset_path in datasets.items():
    manifest_path = dataset_path / "dataset_manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    for ep_info in manifest["episodes"]:
        run_id = ep_info["run_id"]
        all_episodes.append({
            "dataset": dataset_name,
            "episode_id": run_id,
            "scenario_id": ep_info.get("scenario_id"),
            "episode_dir": dataset_path / "episodes" / run_id,
        })

print(f"找到 {len(all_episodes)} 个episode")

# 分析每个episode的phase窗口
segment_stats = []

for ep in all_episodes:
    ep_dir = ep["episode_dir"]
    
    # 读取phase_windows
    phase_windows_path = ep_dir / "phase_windows.json"
    if not phase_windows_path.exists():
        continue
    
    with open(phase_windows_path) as f:
        phase_windows = json.load(f)
    
    # 读取manifest获取run_directory
    manifest_path = ep_dir / "manifest.json"
    with open(manifest_path) as f:
        ep_manifest = json.load(f)
    
    run_dir = Path(ep_manifest.get("run_directory", ""))
    if not run_dir.exists():
        print(f"警告: {ep['episode_id']} 的run_directory不存在: {run_dir}")
        continue
    
    # 从run_directory读取scenario.json
    scenario_path = run_dir / "scenario.json"
    if not scenario_path.exists():
        print(f"警告: {ep['episode_id']} 缺少scenario.json")
        continue
    
    with open(scenario_path) as f:
        scenario = json.load(f)
    
    if "phases" not in scenario:
        print(f"警告: {ep['episode_id']} scenario中没有phases")
        continue
    
    phases = scenario["phases"]
    phase_map = {p["name"]: p for p in phases}
    
    # 分析每个窗口
    for window in phase_windows["windows"]:
        agent = window["agent_id"]
        phase_name = window["phase"]
        semantic = window["semantic_phase"]
        role = window["role"]
        start = window["start_s"]
        end = window["end_s"]
        
        if start is None or end is None:
            continue
        
        duration = end - start
        
        # 获取该phase的目标点
        phase_info = phase_map.get(phase_name)
        if not phase_info:
            continue
        
        target = phase_info["targets"][agent]
        
        segment_stats.append({
            "episode_id": ep["episode_id"],
            "agent": agent,
            "phase": phase_name,
            "semantic_phase": semantic,
            "role": role,
            "duration_s": duration,
            "target": target,
        })

print(f"收集到 {len(segment_stats)} 个窗口")

# 计算相邻phase间的路径长度
for ep in all_episodes:
    ep_dir = ep["episode_dir"]
    
    manifest_path = ep_dir / "manifest.json"
    with open(manifest_path) as f:
        ep_manifest = json.load(f)
    
    run_dir = Path(ep_manifest.get("run_directory", ""))
    if not run_dir.exists():
        continue
    
    scenario_path = run_dir / "scenario.json"
    if not scenario_path.exists():
        continue
    
    with open(scenario_path) as f:
        scenario = json.load(f)
    
    if "phases" not in scenario:
        continue
    
    phases = scenario["phases"]
    
    # 按agent分组计算路径长度
    agents = {}
    for phase in phases:
        for agent, target in phase["targets"].items():
            if agent not in agents:
                agents[agent] = []
            agents[agent].append({
                "phase": phase["name"],
                "target": target,
            })
    
    # 计算每个航段的长度
    for agent, phase_list in agents.items():
        for i in range(len(phase_list)):
            if i == 0:
                path_length = None  # 第一个航段，无法计算
            else:
                prev_target = phase_list[i-1]["target"]
                curr_target = phase_list[i]["target"]
                path_length = math.hypot(
                    curr_target["east_m"] - prev_target["east_m"],
                    curr_target["north_m"] - prev_target["north_m"]
                )
            
            # 更新segment_stats
            for s in segment_stats:
                if s["episode_id"] == ep["episode_id"] and s["agent"] == agent and s["phase"] == phase_list[i]["phase"]:
                    s["path_length_m"] = path_length
                    s["avg_speed_m_s"] = path_length / s["duration_s"] if path_length and s["duration_s"] > 0 else None
                    break

# 保存原始数据
with open("audit_v04/A4_segment_data.json", "w") as f:
    json.dump(segment_stats, f, indent=2)

print(f"\n总航段数: {len(segment_stats)}")

# 分类统计
segments_with_length = [s for s in segment_stats if s.get("path_length_m") is not None]
scan_segments = [s for s in segments_with_length if s.get("path_length_m", 0) >= 5.0]
short_segments = [s for s in segments_with_length if s.get("path_length_m", 0) < 5.0]
zero_segments = [s for s in short_segments if s.get("path_length_m", 0) < 0.1]

print(f"\n有路径长度的航段: {len(segments_with_length)}")

print(f"\n扫描线航段 (≥5m): {len(scan_segments)}")
if scan_segments:
    speeds = [s["avg_speed_m_s"] for s in scan_segments if s["avg_speed_m_s"]]
    durations = [s["duration_s"] for s in scan_segments]
    lengths = [s["path_length_m"] for s in scan_segments]
    print(f"  平均速度: {sum(speeds)/len(speeds):.3f} m/s")
    print(f"  平均时长: {sum(durations)/len(durations):.2f} s")
    print(f"  平均长度: {sum(lengths)/len(lengths):.2f} m")

print(f"\n短航段/换线 (<5m): {len(short_segments)}")
if short_segments:
    speeds = [s["avg_speed_m_s"] for s in short_segments if s.get("avg_speed_m_s")]
    durations = [s["duration_s"] for s in short_segments]
    lengths = [s["path_length_m"] for s in short_segments]
    print(f"  平均速度: {sum(speeds)/len(speeds):.3f} m/s" if speeds else "  平均速度: N/A")
    print(f"  平均时长: {sum(durations)/len(durations):.2f} s")
    print(f"  平均长度: {sum(lengths)/len(lengths):.2f} m")

print(f"\n零长度航段 (<0.1m): {len(zero_segments)}")
if zero_segments:
    durations = [s["duration_s"] for s in zero_segments]
    print(f"  平均停靠时长: {sum(durations)/len(durations):.2f} s")
    print(f"  时长范围: [{min(durations):.2f}, {max(durations):.2f}] s")
    
    # 按语义分类
    by_semantic = {}
    for s in zero_segments:
        sem = s["semantic_phase"]
        by_semantic[sem] = by_semantic.get(sem, 0) + 1
    print(f"  按语义分布: {by_semantic}")

print("\nA4分析完成")
