"""A1 (修正): 执行阶段构成、扫描线数 lanes、idle_padding_steps"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from swarm_sim.mission_planning import compile_shared_mission_v2

MISSIONS = [
    "missions/recon_shared_3uav.json",
    "missions/recon_smoke_3uav.json",
    "missions/recon_smoke_2uav_north.json",
    "missions/recon_smoke_6uav.json",
]

out = []
for mp in MISSIONS:
    spec = json.loads(Path(mp).read_text(encoding="utf-8"))
    scene = compile_shared_mission_v2(spec)
    plan = scene["planning"]
    smap = plan["semantic_to_execution_phase_map"]

    axis = plan["partition_axis"]
    region = next(r for r in spec["scenario"]["regions"] if r["id"] == spec["mission"]["target_region_id"])
    count = len(spec["scenario"]["vehicles"])
    cross_dim = "width_m" if axis == "east" else "height_m"
    sweep_dim = "height_m" if axis == "east" else "width_m"
    cross_width = region[cross_dim] / count
    lane_spacing = spec["planner"]["lane_spacing_m"]
    lanes = max(1, math.ceil(cross_width / lane_spacing))

    row = dict(
        mission=mp,
        vehicles=count,
        partition_axis=axis,
        region_width_m=region["width_m"],
        region_height_m=region["height_m"],
        strip_cross_width_m=cross_width,
        sweep_length_m=region[sweep_dim],
        lane_spacing_m=lane_spacing,
        lanes=lanes,
        approach_phases=len(smap["approach"]),
        observe_phases=len(smap["observe"]),
        return_phases=len(smap["return"]),
        observe_phases_expected=2 * lanes,
        execution_phase_count=plan["execution_phase_count"],
        execution_phase_count_expected=1 + 2 * lanes + len(smap["return"]),
        idle_padding_steps=plan["idle_padding_steps"],
    )

    # approach 首个目标点 vs observe 首个目标点
    routes = plan["per_agent_reference_routes"]
    same = 0
    for agent, r in routes.items():
        a_pts = r["approach"]
        o_pts = r["observe"]
        if a_pts and o_pts:
            d = math.hypot(a_pts[0]["east_m"] - o_pts[0]["east_m"],
                           a_pts[0]["north_m"] - o_pts[0]["north_m"])
            if d < 1e-9:
                same += 1
    row["approach_eq_observe_first"] = f"{same}/{count}"
    out.append(row)

Path("audit_v04/A1_corrected.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

print("A1 修正结果\n")
for r in out:
    print(f"{r['mission']}")
    print(f"  飞机数={r['vehicles']}  剖分轴={r['partition_axis']}")
    print(f"  区域 {r['region_width_m']:.2f}m(east) x {r['region_height_m']:.2f}m(north)")
    print(f"  条带横向宽度={r['strip_cross_width_m']:.2f}m  扫描线长度={r['sweep_length_m']:.2f}m")
    print(f"  lane_spacing_m={r['lane_spacing_m']}  -> lanes={r['lanes']}")
    print(f"  阶段: approach={r['approach_phases']} observe={r['observe_phases']} return={r['return_phases']} "
          f"合计={r['execution_phase_count']} (预期={r['execution_phase_count_expected']})")
    print(f"  observe阶段数 == 2*lanes ? {r['observe_phases']==r['observe_phases_expected']}")
    print(f"  idle_padding_steps={r['idle_padding_steps']}")
    print(f"  approach目标==observe首目标: {r['approach_eq_observe_first']}")
    print()
