"""C5: 场景采样器核查 + 随机起点干跑实验
保持区域参数分布不变, 把飞机生成点替换为与意图无关的随机布局, 在内存中调用
compile_task (不启动 SITL), 统计接受率与拒绝原因分布。
"""
import copy
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_sim.generation import GENERATOR_VERSION, canonical_hash, _profile
from swarm_sim.tasks import compile_task

PROFILE = ROOT / "generation_profiles/recon_pilot_v03.json"
N = 200
LAYOUTS = ("baseline", "side_scatter", "outside_scatter", "compact_formation")
WORLD = None
MIN_SEP = None
MAX_ATTEMPTS = 30


def classify(exc):
    m = str(exc)
    if "spawn clearance" in m or "Initial separation too small" in m:
        return "初始间距不足"
    if "nominal phase paths too close" in m:
        return "同阶段路径间距不足/交叉"
    if "shared route exceeds backend limit" in m:
        return "执行阶段数超限(>100)"
    if "max_path_length_m" in m:
        return "路径预算超限"
    if "max_airborne_time_s" in m:
        return "续航预算超限"
    if "timeout_s below nominal" in m:
        return "timeout 预算不足"
    if "responsibility strip too small" in m:
        return "条带小于到达容差"
    if "below required coverage" in m:
        return "名义覆盖率不足"
    if "lane spacing exceeds" in m:
        return "lane_spacing 大于观测直径"
    if "outside world" in m:
        return "越出世界边界"
    if "region too small for declared arrival tolerance" in m:
        return "区域小于到达容差"
    if "coverage grid exceeds" in m:
        return "覆盖网格超限"
    return "其他: " + m[:60]


def place(prof, rng, layout, count, axis, side, strip, sweep, east, north, entry):
    width, height = (count * strip, sweep) if axis == "east" else (sweep, count * strip)
    out = []
    if layout == "baseline":
        for i in range(count):
            lane = (i + 0.5) * strip
            outside = -entry if side == "low" else sweep + entry
            e, n = (east + lane, north + outside) if axis == "east" else (east + outside, north + lane)
            out.append((e, n))
    elif layout == "side_scatter":
        outside = -entry if side == "low" else (sweep if axis == "east" else width) + entry
        for i in range(count):
            if axis == "east":
                e = east + rng.uniform(0, width)
                n = north + outside + rng.uniform(-2.0, 2.0)
            else:
                e = east + outside + rng.uniform(-2.0, 2.0)
                n = north + rng.uniform(0, height)
            out.append((e, n))
    elif layout == "outside_scatter":
        cx, cy = east + width / 2, north + height / 2
        base_r = entry + max(width, height) / 2
        for i in range(count):
            ang = rng.uniform(0, 2 * math.pi)
            r = base_r + rng.uniform(0, 8.0)
            out.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    elif layout == "compact_formation":
        spacing = 2.0 * MIN_SEP
        theta = rng.uniform(0, 2 * math.pi)
        ang = rng.uniform(0, 2 * math.pi)
        r = entry + max(width, height) / 2 + rng.uniform(0, 8.0)
        cx = east + width / 2 + r * math.cos(ang)
        cy = north + height / 2 + r * math.sin(ang)
        for i in range(count):
            lx = (i - (count - 1) / 2.0) * spacing
            out.append((cx + lx * math.cos(theta), cy + lx * math.sin(theta)))
    return out, width, height


def build(prof, base_index, candidate_index, layout, attempt):
    seed = int(canonical_hash([GENERATOR_VERSION, prof["master_seed"], base_index,
                               candidate_index, layout, attempt])[:16], 16) % (2**63)
    rng = random.Random(seed)
    spec = copy.deepcopy(prof["template_spec"])
    count = rng.choice(prof["vehicle_counts"])
    axis = rng.choice(prof["partition_axes"])
    side = rng.choice(prof["entry_sides"])
    strip = rng.uniform(*prof["strip_width_m"])
    sweep = rng.uniform(*prof["sweep_length_m"])
    east, north = (rng.uniform(*prof[key]) for key in ("region_east_m", "region_north_m"))
    entry = rng.uniform(*prof["entry_distance_m"])
    pts, width, height = place(prof, rng, layout, count, axis, side, strip, sweep, east, north, entry)
    vehicles = [dict(id="uav_%02d" % (i + 1), sysid=i + 1, east_m=e, north_m=n, heading_deg=0.0)
                for i, (e, n) in enumerate(pts)]
    region = dict(id="R1", type="rectangle", min_east_m=east, min_north_m=north,
                  width_m=width, height_m=height)
    spec.update(task_id="dry_%04d" % base_index, family_id="dry_family_%04d" % base_index, seed=seed)
    spec["scenario"].update(scene_id="base_%04d" % base_index, regions=[region],
                            vehicles=vehicles, restricted_regions=[])
    spec["mission"].update(target_region_id="R1", return_required=rng.choice(prof["return_required"]))
    spec["planner"]["partition_axis"] = axis
    spec["execution"]["speed_m_s"] = rng.choice(prof["speeds_m_s"])
    in_world = all(WORLD["east_bounds_m"][0] <= e <= WORLD["east_bounds_m"][1] and
                   WORLD["north_bounds_m"][0] <= n <= WORLD["north_bounds_m"][1] for e, n in pts)
    return spec, in_world, count, axis, side


prof = _profile(PROFILE)
WORLD = prof["template_spec"]["scenario"]["world"]
MIN_SEP = prof["template_spec"]["execution"]["min_separation_m"]

print("=" * 104)
print("C5-1 采样器核查 (swarm_sim/generation.py:_sample)")
print("=" * 104)
print("区域尺寸由飞机数决定 (count x strip_width):")
print("  源码 generation.py:97  ->  width, height = (count * strip, sweep) if axis == \"east\" else (sweep, count * strip)")
print("生成点位于各自未来条带中线上:")
print("  源码 generation.py:101 ->  lane = (i + 0.5) * strip   (第 i 条带 [i*strip,(i+1)*strip] 的中点)")
print("entry_sides 默认值: _profile 默认 [\"low\"]; 本 profile 实际取值 %s" % prof["entry_sides"])
print("heading_deg 是否固定: 是, generation.py:103 硬编码 heading_deg=0.0, 无采样")

print()
print("=" * 104)
print("C5-2 干跑实验 (%d 样本/布局, 内存 compile_task, 不启动 SITL)" % N)
print("=" * 104)

summary = {}
for layout in LAYOUTS:
    accepted, reasons = 0, Counter()
    placement_fail = 0
    for bi in range(N):
        ok = False
        spec = None
        for attempt in range(MAX_ATTEMPTS):
            spec, in_world, count, axis, side = build(prof, bi, 0, layout, attempt)
            if in_world:
                ok = True
                break
        if not ok:
            placement_fail += 1
            reasons["生成器未能放入世界边界(非规划器拒绝)"] += 1
            continue
        try:
            compile_task(spec)
            accepted += 1
        except (ValueError, TypeError, KeyError) as exc:
            reasons[classify(exc)] += 1
        except Exception as exc:                                    # noqa: BLE001
            reasons["未预期异常: " + type(exc).__name__] += 1
    summary[layout] = dict(accepted=accepted, reasons=dict(reasons), placement_fail=placement_fail)
    print()
    print("布局 %-20s 接受 %3d/%d = %.3f" % (layout, accepted, N, accepted / N))
    for r, c in reasons.most_common():
        print("      %-34s %3d/%d = %.3f" % (r, c, N, c / N))

Path(ROOT / "audit_v04/C5_dryrun.json").write_text(
    json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

# monotone_entry_order 交叉分析
print()
print("=" * 104)
print("C5-3 monotone_entry_order 在随机布局下的进入路径交叉")
print("=" * 104)
print("分配规则 (mission_planning.py:128): ordering = sorted(vehicles, key=lambda v: (v[axis+'_m'], v['id']))")
print("即按剖分轴坐标排序后, 第 k 个飞机拿到第 k 个条带。")
print()
cross = Counter()
for layout in LAYOUTS:
    n_cross = 0
    n_tot = 0
    for bi in range(N):
        spec, in_world, count, axis, side = build(prof, bi, 0, layout, 0)
        if not in_world:
            continue
        region = spec["scenario"]["regions"][0]
        key = f"{axis}_m"
        ordering = sorted(spec["scenario"]["vehicles"], key=lambda v: (v[key], v["id"]))
        strip = region["width_m" if axis == "east" else "height_m"] / count
        origin = region["min_east_m" if axis == "east" else "min_north_m"]
        n_tot += 1
        # 条带按剖分轴坐标排序; 若飞机到其条带起点的位移在剖分轴上方向不一致, 视为潜在交叉
        signs = []
        for k, v in enumerate(ordering):
            lane_center = origin + (k + 0.5) * strip
            signs.append(1 if lane_center >= v[key] else -1)
        if any(signs[i] != signs[j] for i in range(len(signs)) for j in range(i + 1, len(signs))):
            n_cross += 1
    cross[layout] = (n_cross, n_tot)
    print("  布局 %-20s 出现方向不一致(潜在交叉)的样本: %d/%d = %.3f"
          % (layout, n_cross, n_tot, (n_cross / n_tot) if n_tot else 0.0))
