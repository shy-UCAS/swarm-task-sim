"""A1: 规划编译 - 一个航点是否等于一个执行阶段"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from swarm_sim.mission_planning import compile_shared_mission_v2

missions = [
    "missions/recon_shared_3uav.json",
    "missions/recon_smoke_3uav.json",
    "missions/recon_smoke_2uav_north.json",
    "missions/recon_smoke_6uav.json",
]

results = []
for mission_path in missions:
    with open(mission_path) as f:
        spec = json.load(f)
    
    scene = compile_shared_mission_v2(spec)
    
    # 基本统计
    phase_count = len(scene["phases"])
    semantic_map = scene["planning"]["semantic_to_execution_phase_map"]
    approach_count = len(semantic_map["approach"])
    observe_count = len(semantic_map["observe"])
    return_count = len(semantic_map["return"])
    
    # 检查 approach 和 observe 第一个点是否相同
    routes = scene["planning"]["per_agent_reference_routes"]
    zero_length_segments = 0
    
    for agent, route in routes.items():
        if route["approach"] and route["observe"]:
            approach_last = route["approach"][-1]  # approach只有1个点，就是scan[0]
            observe_first = route["observe"][0]
            
            dist = math.hypot(
                approach_last["east_m"] - observe_first["east_m"],
                approach_last["north_m"] - observe_first["north_m"]
            )
            
            if dist < 1e-6:  # 实际相同
                zero_length_segments += 1
    
    results.append({
        "mission": mission_path,
        "vehicle_count": len(spec["scenario"]["vehicles"]),
        "execution_phase_count": phase_count,
        "approach_phases": approach_count,
        "observe_phases": observe_count,
        "return_phases": return_count,
        "lanes": observe_count,  # observe阶段数即扫描线数
        "zero_length_approach_to_observe": zero_length_segments,
        "routes": {
            agent: {
                "approach_waypoints": len(route["approach"]),
                "observe_waypoints": len(route["observe"]),
                "return_waypoints": len(route["return"]),
            }
            for agent, route in routes.items()
        }
    })

with open("audit_v04/A1_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("A1 编译分析完成\n")
for r in results:
    print(f"{r['mission']}:")
    print(f"  飞机数: {r['vehicle_count']}")
    print(f"  执行阶段总数: {r['execution_phase_count']}")
    print(f"    approach: {r['approach_phases']}")
    print(f"    observe: {r['observe_phases']}")
    print(f"    return: {r['return_phases']}")
    print(f"  零长度approach→observe: {r['zero_length_approach_to_observe']}/{r['vehicle_count']}")
    
    # 显示第一个agent的航点数
    first_agent = list(r['routes'].keys())[0]
    route_info = r['routes'][first_agent]
    print(f"  {first_agent}路线航点数: approach={route_info['approach_waypoints']}, "
          f"observe={route_info['observe_waypoints']}, return={route_info['return_waypoints']}")
    print()
