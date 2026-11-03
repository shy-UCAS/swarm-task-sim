"""可视图骨架适配器（V8-12 第 2 部分）。仅本模块的函数内部可以导入 shapely 相关模块。

冻结的 VisibilityPlanner 只膨胀 hard_constraint_obstacle、不处理保护圈、不内缩 world。这里的适配：
1. 用 NumPy 半平面求交把凸 world 内缩 world_margin_m；
2. 把障碍/被禁止圈按各自余量转成显式 Circle/BufferedPolygon 副本，传图时 margin_m=0.0，避免二次膨胀；
3. 沿用冻结图构造的 quad_segs 默认值（8），冻结代码对障碍取外包近似，因此近似只会缩小可行空间。
路径只给可达性与骨架，最终仍由 NumPy 精确线段距离验收；图近似失败不能证明真实几何无解。
"""
from .exact import expand, inset_convex

PLANNER_QUAD_SEGS = 8


def build_planner(world_geometry, blockers, *, world_margin_m):
    """blockers: [(id, 已按余量膨胀的显式几何)]。返回 VisibilityPlanner（惰性导入 shapely）。"""
    from scene_v07.geometry import VisibilityPlanner  # noqa: WPS433 — 惰性导入，保持核心无 shapely

    inner = {"type": "Polygon", "vertices_m": inset_convex(world_geometry["vertices_m"], world_margin_m)}
    scene_like = {"world": {"id": "world", "geometry": inner},
                  "entities": [{"id": i, "type": "hard_constraint_obstacle", "geometry": g} for i, g in blockers]}
    return VisibilityPlanner(scene_like, margin_m=0.0, quad_segs=PLANNER_QUAD_SEGS)


def inflated(geometry, margin_m):
    return expand(geometry, margin_m)


def skeleton_path(planner, start, goal):
    """最短骨架折线 [start, ..., goal]（列表的列表）或 None。"""
    return planner.path([float(start[0]), float(start[1])], [float(goal[0]), float(goal[1])])
