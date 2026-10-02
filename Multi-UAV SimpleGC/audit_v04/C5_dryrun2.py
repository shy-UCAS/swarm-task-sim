"""C5 补充: (1) 强制满足初始间距后重测接受率 (2) 精确的进入路径交叉检测"""
import copy
import json
import math
import random
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_sim.generation import GENERATOR_VERSION, canonical_hash, _profile
from swarm_sim.mission_planning import lawnmower_route, partition_region
from swarm_sim.tasks import compile_task, segment_clearance

PROFILE = ROOT / "generation_profiles/recon_pilot_v03.json"
N = 200
LAYOUTS = ("baseline", "side_scatter", "outside_scatter", "compact_formation")
MAX_ATTEMPTS = 200


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
    if "outside world" in m:
        return "越出世界边界"
    return "其他: " + m[:70]


def raw_points(prof, rng, layout, count, axis, side, strip, sweep, east, north, entry):
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
                out.append((east + rng.uniform(0, width), north + outside + rng.uniform(-2.0, 2.0)))
            else:
                out.append((east + outside + rng.uniform(-2.0, 2.0), north + rng.uniform(0, height)))
    elif layout == "outside_scatter":
        cx, cy = east + width / 2, north + height / 2
        base_r = entry + max(width, height) / 2
        for i in range(count):
            ang, r = rng.uniform(0, 2 * math.pi), base_r + rng.uniform(0, 8.0)
            out.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    elif layout == "compact_formation":
        spacing = 2.0 * MIN_SEP
        theta, ang = rng.uniform(0, 2 * math.pi), rng.uniform(0, 2 * math.pi)
        r = entry + max(width, height) / 2 + rng.uniform(0, 8.0)
        cx, cy = east + width / 2 + r * math.cos(ang), north + height / 2 + r * math.sin(ang)
        for i in range(count):
            lx = (i - (count - 1) / 2.0) * spacing
            out.append((cx + lx * math.cos(theta), cy + lx * math.sin(theta)))
    return out, width, height


def sample(prof, bi, layout, attempt):
    seed = int(canonical_hash([GENERATOR_VERSION, prof["master_seed"], bi, 0, layout, attempt])[:16], 16) % (2**63)
    rng = random.Random(seed)
    spec = copy.deepcopy(prof["template_spec"])
    count = rng.choice(prof["vehicle_counts"])
    axis = rng.choice(prof["partition_axes"])
    side = rng.choice(prof["entry_sides"])
    strip = rng.uniform(*prof["strip_width_m"])
    sweep = rng.uniform(*prof["sweep_length_m"])
    east, north = (rng.uniform(*prof[key]) for key in ("region_east_m", "region_north_m"))
    entry = rng.uniform(*prof["entry_distance_m"])
    pts, width, height = raw_points(prof, rng, layout, count, axis, side, strip, sweep, east, north, entry)
    return seed, rng, spec, count, axis, side, strip, sweep, east, north, entry, pts, width, height


def in_world(pts):
    return all(WORLD["east_bounds_m"][0] <= e <= WORLD["east_bounds_m"][1] and
               WORLD["north_bounds_m"][0] <= n <= WORLD["north_bounds_m"][1] for e, n in pts)


def sep_ok(pts):
    return all(math.dist(a, b) >= MIN_SEP - 1e-9 for a, b in combinations(pts, 2))


prof = _profile(PROFILE)
WORLD = prof["template_spec"]["scenario"]["world"]
MIN_SEP = prof["template_spec"]["execution"]["min_separation_m"]

print("=" * 108)
print("C5-2b 强制满足初始间距(>= %.1f m)且在世界边界内后, 重测接受率" % MIN_SEP)
print("=" * 108)
print("说明: 上一轮 side_scatter 的拒绝主要来自随机散布本身会产生过近的点,")
print("      属于布局生成器的作用, 不是规划器的判定。本轮先做拒绝采样保证初始布局合法。")
print()
res = {}
for layout in LAYOUTS:
    acc, reasons, gen_fail = 0, Counter(), 0
    for bi in range(N):
        for attempt in range(MAX_ATTEMPTS):
            (seed, rng, spec, count, axis, side, strip, sweep,
             east, north, entry, pts, width, height) = sample(prof, bi, layout, attempt)
            if in_world(pts) and sep_ok(pts):
                break
        else:
            gen_fail += 1
            reasons["生成器未能生成合法初始布局"] += 1
            continue
        vehicles = [dict(id="uav_%02d" % (i + 1), sysid=i + 1, east_m=e, north_m=n, heading_deg=0.0)
                    for i, (e, n) in enumerate(pts)]
        region = dict(id="R1", type="rectangle", min_east_m=east, min_north_m=north,
                      width_m=width, height_m=height)
        spec.update(task_id="dry2_%04d" % bi, family_id="dry2_family_%04d" % bi, seed=seed)
        spec["scenario"].update(scene_id="base_%04d" % bi, regions=[region],
                                vehicles=vehicles, restricted_regions=[])
        spec["mission"].update(target_region_id="R1", return_required=rng.choice(prof["return_required"]))
        spec["planner"]["partition_axis"] = axis
        spec["execution"]["speed_m_s"] = rng.choice(prof["speeds_m_s"])
        try:
            compile_task(spec)
            acc += 1
        except (ValueError, TypeError, KeyError) as exc:
            reasons[classify(exc)] += 1
    res[layout] = dict(accepted=acc, reasons=dict(reasons))
    print("布局 %-20s 接受 %3d/%d = %.3f" % (layout, acc, N, acc / N))
    for r, c in reasons.most_common():
        print("      %-32s %3d/%d = %.3f" % (r, c, N, c / N))
    print()

print("=" * 108)
print("C5-3b 进入路径交叉检测 (精确线段相交)")
print("=" * 108)
print("进入路径 = spawn -> 该机条带 lane-0 中线起点 scan[0] (mission_planning.lawnmower_route 首个点)")
print()
for layout in LAYOUTS:
    n_cross = n_tot = n_pairs_cross = n_pairs = 0
    for bi in range(N):
        for attempt in range(MAX_ATTEMPTS):
            (seed, rng, spec, count, axis, side, strip, sweep,
             east, north, entry, pts, width, height) = sample(prof, bi, layout, attempt)
            if in_world(pts) and sep_ok(pts):
                break
        else:
            continue
        region = dict(id="R1", type="rectangle", min_east_m=east, min_north_m=north,
                      width_m=width, height_m=height)
        parts = partition_region(region, count, axis)
        cross_w = region["width_m" if axis == "east" else "height_m"] / count
        lanes = max(1, math.ceil(cross_w / spec["planner"]["lane_spacing_m"]))
        key = f"{axis}_m"
        order = sorted(range(count), key=lambda i: (pts[i][0 if axis == "east" else 1], i))
        starts = [lawnmower_route(parts[k], axis, lanes)[0] for k in range(count)]
        starts = [{ "east_m": s["east_m"], "north_m": s["north_m"]} for s in starts]
        n_tot += 1
        hit = False
        for i, j in combinations(range(count), 2):
            a, b = pts[order[i]], pts[order[j]]
            c = (starts[i]["east_m"], starts[i]["north_m"])
            d = (starts[j]["east_m"], starts[j]["north_m"])
            n_pairs += 1
            if segment_clearance(a, c, b, d) < 1e-9:
                n_pairs_cross += 1
                hit = True
        if hit:
            n_cross += 1
    print("布局 %-20s 存在交叉的样本: %3d/%d = %.3f   交叉机对: %d/%d = %.3f"
          % (layout, n_cross, n_tot, n_cross / n_tot if n_tot else 0,
             n_pairs_cross, n_pairs, n_pairs_cross / n_pairs if n_pairs else 0))

Path(ROOT / "audit_v04/C5_dryrun2.json").write_text(
    json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
