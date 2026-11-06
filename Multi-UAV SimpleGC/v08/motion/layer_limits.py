"""每段允许的最深圈层表与通用 base 约束（V8-16 指令 2.2；本项新增）。

唯一取值来源是冻结配置 configs/v08/criteria_segment.json：目标取 max_target_layer_<intent>，其他设施取
max_other_facility_layer。缺键立即报错，不默认 1；detour 在固定配置中没有键，冻结核验也拒绝，因此这里抛 ValueError，
不补造目标上限（指令第 12 节第 1 项）。

几何禁止集合由上限推出：上限 1 → 该设施 alert 外 forbidden_margin_m；上限 2 → protected 外 forbidden_margin_m；
上限 3 → 不加该设施的圈层禁止项。base 次序与旧 monitoring_constraints 完全相同：world、ctx.obstacles 原序、
ctx.facilities 原序（指令 2.2 第 1–3 步）。监视的 base 由本模块构造后，旧 monitoring_constraints 只在其后追加
patrol/warnings，函数返回结构与运算次序不变。

本模块导入时不读配置、不读场景。
"""
from ..scene.field import Clearance

LAYER_FOR_LIMIT = {1: "alert", 2: "protected"}     # 上限 3：不加目标圈层禁止项
CROSSING_LAYERS = ("alert", "protected")           # V8-17 指令 2.1：上限 2 追加 alert，上限 3 再追加 protected


def _segment_values():
    from ..config import load_config
    return load_config("criteria_segment").values


def layer_limits(intent, target_id, facility_ids, *, values=None):
    """按传入设施顺序返回 {facility_id: 最深允许圈层}。values 为 criteria_segment 的完整取值（测试可注入）。"""
    vals = _segment_values() if values is None else values
    tk = f"max_target_layer_{intent}"
    ok = "max_other_facility_layer"
    if tk not in vals:
        raise ValueError(f"criteria_segment 没有 {tk}：意图 {intent!r} 在固定配置中未配置/不支持（不补造取值）")
    if ok not in vals:
        raise ValueError(f"criteria_segment 缺少 {ok}")
    out = {}
    for fid in facility_ids:
        v = vals[tk] if fid == target_id else vals[ok]
        if float(v) != int(v) or int(v) not in (0, 1, 2, 3):
            raise ValueError(f"圈层上限必须是 0–3 的整数：{fid} -> {v!r}")
        out[fid] = int(v)
    return out


def constraints_for_task(ctx, task):
    """返回 {"base": list[Clearance], "warnings": {facility_id: warning 几何},
    "crossing_boundaries": {键: 几何}}。
    base：world（内 world_margin_m）、障碍（外 obstacle_margin_m，原序）、各设施按上限的 alert/protected（外
    forbidden_margin_m，原序）；上限 0 的设施没有可用几何表示（warning 外）——固定配置不出现，明确报错。
    V8-17 指令 2.1：crossing_boundaries 以 dict(warnings) 开头（键、顺序、几何对象与 warnings 完全相同），目标上限 2
    追加 alert，上限 3 依次追加 alert、protected；深层键为 "__crossing__<target_id>::<layer>"，与已有键冲突时在
    末尾加 "#" 直到不冲突（确定性转义，不用 RNG）。base/warnings 的构造、顺序与对象不变。"""
    P = ctx.params
    limits = layer_limits(task.intent, task.target_id, [f.id for f in ctx.facilities])
    base = [Clearance("world", ctx.world, -1, P["world_margin_m"])]
    base += [Clearance("obstacle:" + i, g, 1, P["obstacle_margin_m"]) for i, g in ctx.obstacles]
    for f in ctx.facilities:
        lim = limits[f.id]
        if lim == 3:
            continue
        if lim not in LAYER_FOR_LIMIT:
            raise ValueError(f"设施 {f.id} 的圈层上限 {lim} 没有对应的几何禁止项")
        layer = LAYER_FOR_LIMIT[lim]
        base.append(Clearance(layer + ":" + f.id, f.layers[layer], 1, P["forbidden_margin_m"]))
    warnings = {f.id: f.layers["warning"] for f in ctx.facilities}
    crossing = dict(warnings)
    tgt = next(f for f in ctx.facilities if f.id == task.target_id)
    for layer in CROSSING_LAYERS[:max(0, limits[task.target_id] - 1)]:
        k = f"__crossing__{task.target_id}::{layer}"
        while k in crossing:
            k += "#"
        crossing[k] = tgt.layers[layer]
    return {"base": base, "warnings": warnings, "crossing_boundaries": crossing}


def crossing_layer_keys(cons):
    """crossing_boundaries 中 warnings 之后追加的深层键 → 圈层名（按追加顺序 alert、protected）。
    只供突入见证记录实际键名映射；不写入旧意图合同。"""
    deeper = list(cons["crossing_boundaries"])[len(cons["warnings"]):]
    return dict(zip(deeper, CROSSING_LAYERS))


def constraints_identity(constraints):
    """有序约束的完整身份（名字、几何内容键、sense、minimum_m），作为通用阶段缓存键的一部分，避免不同意图混用。"""
    from ..scene.field import geometry_key
    return tuple((c.name, geometry_key(c.geometry), int(c.sense), float(c.minimum_m)) for c in constraints)
