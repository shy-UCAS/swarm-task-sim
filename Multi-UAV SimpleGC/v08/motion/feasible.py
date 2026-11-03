"""可行集合的空集分类与必要条件证书（V8-12 第 2 部分；r4 6.5）。

只有"精确必要条件证书"才能报 proven_infeasible；距离场保守集为空、但无证书时只能报 approx_empty，
精确复核找到可行点时必须带 exact_nonempty=True。图近似断路、优化器不收敛都不是数学无解。
"""
import math

import numpy as np

from ..contract.monitoring import Failure
from ..scene.exact import GeometryError, clearance_values, kind_of

CONCENTRIC = "concentric_circles"
PARALLEL = "parallel_buffers"


def _band_radii(alert, warning, alert_clearance_m, warning_inset_m):
    """同心圆环或同一凸基轮廓的平行 buffer：单车道的必要条件只与两个半径（偏移）有关。
    返回 (kind, inner, outer) 或 None（前提不满足，证书不适用）。"""
    try:
        ta, tw = kind_of(alert), kind_of(warning)
    except GeometryError:
        return None
    if ta == "Circle" and tw == "Circle":
        ca, cw = np.asarray(alert["center_m"], float), np.asarray(warning["center_m"], float)
        if np.max(np.abs(ca - cw)) > 1e-9:
            return None
        return CONCENTRIC, float(alert["radius_m"]) + alert_clearance_m, float(warning["radius_m"]) - warning_inset_m
    if ta == "BufferedPolygon" and tw == "BufferedPolygon":
        va, vw = np.asarray(alert["vertices_m"], float), np.asarray(warning["vertices_m"], float)
        if va.shape != vw.shape or np.max(np.abs(va - vw)) > 1e-9:
            return None
        return PARALLEL, float(alert["buffer_m"]) + alert_clearance_m, float(warning["buffer_m"]) - warning_inset_m
    return None


def prove_concentric_band_empty(alert, warning, *, alert_clearance_m, warning_inset_m, member_count, formation):
    """目标 alert 外 alert_clearance_m、warning 内 warning_inset_m 的环带是否连"单车道"都不存在。

    同心圆：内可用半径 R_a + c_a，外可用半径 R_w − c_w；内 > 外则空（纵列也不可行，故与队形、人数无关）。
    同一凸基轮廓的平行 buffer：sdf 的水平集，条件同样是 buffer 差减两侧余量。
    返回 Failure(proven_infeasible) 或 None；None 只表示这个必要条件没有证明为空，
    不表示整合同已证明可行。
    """
    found = _band_radii(alert, warning, alert_clearance_m, warning_inset_m)
    if found is None:
        return None
    kind, inner, outer = found
    gap = outer - inner
    if not gap < 0.0:
        return None
    witness = {
        "kind": kind,
        "constraint": "target_alert_outside_min + target_warning_inside_inset",
        "inner_required_radius_m": inner,
        "outer_allowed_radius_m": outer,
        "gap_m": gap,
        "alert_clearance_m": alert_clearance_m,
        "warning_inset_m": warning_inset_m,
        "member_count": member_count,
        "formation": formation,
        "alert": alert,
        "warning": warning,
    }
    return Failure("proven_infeasible",
                   f"目标环带内可用半径 {inner} m 大于外可用半径 {outer} m，连单车道都不存在",
                   "patrol_band(target)", witness, False)


def certificate_valid(failure):
    """从 witness 里保存的原几何重新计算证书，确认前提与数值；REPORT 和检查点读这个，不读非空 dict。"""
    if failure is None or failure.code != "proven_infeasible" or not isinstance(failure.witness, dict):
        return False
    w = failure.witness
    try:
        redo = prove_concentric_band_empty(w["alert"], w["warning"], alert_clearance_m=w["alert_clearance_m"],
                                           warning_inset_m=w["warning_inset_m"], member_count=w["member_count"],
                                           formation=w["formation"])
    except (KeyError, TypeError, ValueError):
        return False
    if redo is None:
        return False
    keys = ("kind", "inner_required_radius_m", "outer_allowed_radius_m", "gap_m")
    return all(redo.witness[k] == w.get(k) for k in keys)


def exact_margins(constraints, point):
    """点对每个约束的精确余量 {约束名: sense*sdf − minimum}（sense=0 时为 |sdf| − minimum）。"""
    p = np.asarray(point, dtype=float)[:2]
    return {c.name: float(clearance_values(c.geometry, p, sense=c.sense, minimum_m=c.minimum_m)) for c in constraints}


def classify_empty(field, constraints, *, exact_witnesses=(), certificate=None):
    """距离场保守集为空时的分类。保守集非空返回 None（不是空）。

    - 给出的精确见证点满足全部约束：approx_empty，exact_nonempty=True，witness 带该点与各约束余量；
    - 无见证、有已验证的证书：proven_infeasible；
    - 否则 approx_empty，exact_nonempty=None（精确状态未知，不当作空）。
    """
    mask = field.certified_cell_mask(names=[c.name for c in constraints])
    if bool(np.any(mask)):
        return None
    label = "+".join(c.name for c in constraints)
    for pt in exact_witnesses:
        margins = exact_margins(constraints, pt)
        if all(m >= 0.0 for m in margins.values()):
            return Failure("approx_empty", "距离场保守集为空，但精确复核找到可行点（近似漏检）", label,
                           {"point": [float(pt[0]), float(pt[1])], "margins": margins}, True)
    if certificate is not None and certificate_valid(certificate):
        return certificate
    return Failure("approx_empty", "距离场保守集为空，精确复核未找到可行点也没有证书", label, None, None)
