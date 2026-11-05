"""V8-15 纯统计模块（指令 3.1、4.1–4.2、0.4）：成员对距离最小值、耗时名单、进程数选择、合同目录逐字节比较。

只依赖标准库与 NumPy；不导入 shapely、不导入生产 runner（避免加载几何依赖）。
这里的数值全部按原精度比较，没有物理容差；分位数用 NumPy quantile(method="linear")（本稿测量协议）。
"""
import math
from pathlib import Path

import numpy as np

FRAME_US = 100_000              # 10 Hz 帧间隔（相邻共同帧才插值；指令 3.1）
MEMORY_LIMIT = 0.60             # U D.3.5：全机已用物理内存采样峰值比例 ≤ 60%
PREFER_16_RATIO = 1.10          # U D.3.5：24 相对 16 吞吐量增益 < 10% 时取 16


# ---------------------------------------------------------------- 成员对距离

def segment_min(r0, dr, a_lo=0.0, a_hi=1.0):
    """相对位移 r(α) = r0 + α·dr 在 α∈[a_lo, a_hi] 上的最小范数（逐行，向量化）。返回 (d, α)。
    α* = clip(−r0·dr/‖dr‖², a_lo, a_hi)；‖dr‖=0 时取 α = a_lo（指令 3.1：分母为 0 取左端）。"""
    r0 = np.atleast_2d(np.asarray(r0, float))
    dr = np.atleast_2d(np.asarray(dr, float))
    a_lo = np.broadcast_to(np.asarray(a_lo, float), (len(r0),))
    a_hi = np.broadcast_to(np.asarray(a_hi, float), (len(r0),))
    den = np.einsum("ij,ij->i", dr, dr)
    num = -np.einsum("ij,ij->i", r0, dr)
    with np.errstate(divide="ignore", invalid="ignore"):
        a = np.where(den > 0.0, num / np.where(den > 0.0, den, 1.0), a_lo)
    a = np.minimum(np.maximum(a, a_lo), a_hi)
    d = np.linalg.norm(r0 + a[:, None] * dr, axis=1)
    return d, a


def pair_minima(time_us, p_a, p_b):
    """共同整数 10 Hz 帧上的采样和相邻帧线性插值最小值；返回距离、帧、插值分数及空集原因。

    time_us：共同帧时刻（int µs，升序）；p_a、p_b：同一行对齐的位置（维数由调用方决定：实测三维、优化 XY）。
    返回键：sample_min_m、sample_time_us、interp_min_m、interval_start_us、fraction、t_s、reason。
    - 平局取最早帧；插值只在相差恰 100000 µs 的相邻共同帧间计算（不跨缺帧）；
    - 插值结果至少包含所有采样端点；没有连续区间（或最小值落在孤立采样帧）时 interval_start_us/fraction=None，
      t_s 为最早采样最小时刻；
    - 无共同帧：两个最小值为 None，reason="no_common_frames"（不是 0）。"""
    t = np.asarray(time_us, np.int64).reshape(-1)
    if len(t) == 0:
        return {"sample_min_m": None, "sample_time_us": None, "interp_min_m": None, "interval_start_us": None,
                "fraction": None, "t_s": None, "reason": "no_common_frames"}
    a = np.asarray(p_a, float).reshape(len(t), -1)
    b = np.asarray(p_b, float).reshape(len(t), -1)
    r = a - b
    d = np.linalg.norm(r, axis=1)
    k = int(np.argmin(d))                       # argmin 返回首个最小值 = 最早帧
    out = {"sample_min_m": float(d[k]), "sample_time_us": int(t[k]), "interp_min_m": float(d[k]),
           "interval_start_us": None, "fraction": None, "t_s": float(t[k]) / 1e6, "reason": None}
    if len(t) < 2:
        return out
    cont = np.flatnonzero(np.diff(t) == FRAME_US)
    if len(cont) == 0:
        return out
    di, al = segment_min(r[cont], r[cont + 1] - r[cont])
    tt = (t[cont].astype(float) + al * FRAME_US) / 1e6
    order = np.lexsort((tt, di))                # 先距离、再精确时刻
    j = int(order[0])
    if di[j] < d[k] or (di[j] == d[k] and tt[j] <= out["t_s"]):
        out.update(interp_min_m=float(di[j]), interval_start_us=int(t[cont[j]]), fraction=float(al[j]),
                   t_s=float(tt[j]))
    return out


# ---------------------------------------------------------------- 名单与进程数

def _branch(x):
    return -1 if x is None else int(x)


def select_timing_keys(rows, count=40):
    """p20-p80闭区间内按耗时/业务键排序，等距选count个键。

    rows 每条含 wall_s、order、draw_index、branch；只用有限正耗时；失败合同不排除。
    返回 [(order, draw_index), ...]；候选不足 count 时返回 None（前提缺失，不另选便宜合同）。"""
    good = [r for r in rows if r.get("wall_s") is not None and math.isfinite(float(r["wall_s"]))
            and float(r["wall_s"]) > 0.0]
    if not good:
        return None
    w = np.array([float(r["wall_s"]) for r in good])
    q20, q80 = np.quantile(w, [0.2, 0.8], method="linear")
    cand = [r for r in good if q20 <= float(r["wall_s"]) <= q80]
    cand.sort(key=lambda r: (float(r["wall_s"]), int(r["order"]), int(r["draw_index"]), _branch(r.get("branch"))))
    M = len(cand)
    if M < count:
        return None
    if count == 1:
        idx = [0]
    else:
        idx = [k * (M - 1) // (count - 1) for k in range(count)]
    return [(int(cand[i]["order"]), int(cand[i]["draw_index"])) for i in idx]


def selection_detail(rows, count=40):
    """名单协议的完整中间量（入库 part4/selection.json）。"""
    good = [r for r in rows if r.get("wall_s") is not None and math.isfinite(float(r["wall_s"]))
            and float(r["wall_s"]) > 0.0]
    w = np.array([float(r["wall_s"]) for r in good])
    q20, q80 = (float(x) for x in np.quantile(w, [0.2, 0.8], method="linear"))
    cand = sorted([r for r in good if q20 <= float(r["wall_s"]) <= q80],
                  key=lambda r: (float(r["wall_s"]), int(r["order"]), int(r["draw_index"]), _branch(r.get("branch"))))
    M = len(cand)
    idx = None if M < count else ([0] if count == 1 else [k * (M - 1) // (count - 1) for k in range(count)])
    return {"n_rows": len(rows), "n_finite_positive": len(good), "p20_s": q20, "p80_s": q80,
            "candidates": [{"order": int(r["order"]), "draw_index": int(r["draw_index"]), "branch": r.get("branch"),
                            "wall_s": float(r["wall_s"])} for r in cand],
            "indices": idx, "count": count,
            "keys": None if idx is None else [[int(cand[i]["order"]), int(cand[i]["draw_index"])] for i in idx]}


def choose_workers(rows):
    """接收每档 workers、inflation_median、peak_memory_fraction；返回选定档或None及依据。

    合格：三项数据齐全（且 p0_3_ok 若给出须为真）、峰值内存比例 ≤ 0.60。吞吐量 S = W / I；取最大 S，
    精确同值取较小 W；若本来选 24 而 16 也合格且 S24/S16 < 1.10，取 16。无合格档 selected=None。"""
    basis = []
    ok = []
    for r in sorted(rows, key=lambda x: int(x["workers"])):
        w = int(r["workers"])
        inf = r.get("inflation_median")
        mem = r.get("peak_memory_fraction")
        why = []
        if inf is None or not math.isfinite(float(inf)) or float(inf) <= 0.0:
            why.append("inflation_missing")
        if mem is None or not math.isfinite(float(mem)):
            why.append("memory_missing")
        elif float(mem) > MEMORY_LIMIT:
            why.append("memory_over_60pct")
        if r.get("p0_3_ok") is False:
            why.append("p0_3_failed")
        s = None if "inflation_missing" in why else w / float(inf)
        basis.append({"workers": w, "inflation_median": inf, "peak_memory_fraction": mem, "throughput": s,
                      "eligible": not why, "rejected_because": why})
        if not why:
            ok.append((w, s))
    if not ok:
        return {"selected": None, "basis": basis, "rule": "无合格档：不猜默认值"}
    best_s = max(s for _, s in ok)
    sel = min(w for w, s in ok if s == best_s)
    note = None
    s_map = dict(ok)
    if sel == 24 and 16 in s_map and s_map[24] / s_map[16] < PREFER_16_RATIO:
        note = f"S24/S16 = {s_map[24] / s_map[16]:.6f} < 1.10，取 16"
        sel = 16
    return {"selected": sel, "basis": basis, "preference_note": note,
            "rule": "S=W/I 最大；同值取小；24 相对 16 增益 <10% 取 16；内存 ≤60%"}


# ---------------------------------------------------------------- 合同目录逐字节比较

def compare_contracts(source, repeat):
    """按生产compare_dirs同口径比较全部路径与字节；纯模块中不导入生产几何依赖。
    输入是两个 contracts/<同一 id> 目录；无排除项。返回字段与 joint_monitoring.compare_dirs 相同。"""
    source, repeat = Path(source), Path(repeat)
    src = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}
    rep = {p.relative_to(repeat).as_posix() for p in repeat.rglob("*") if p.is_file()}
    diff = sorted(n for n in src & rep if (source / n).read_bytes() != (repeat / n).read_bytes())
    same = src == rep and not diff
    return {"files": sorted(src), "file_sets_equal": src == rep, "bytes_equal": same, "differing": diff,
            "only_source": sorted(src - rep), "only_repeat": sorted(rep - src)}


# ---------------------------------------------------------------- 分布摘要

def quantiles(xs):
    """min/p10/median/p90/max（linear）；空列表返回 None。"""
    v = np.asarray([float(x) for x in xs if x is not None], float)
    if len(v) == 0:
        return None
    q = np.quantile(v, [0.0, 0.1, 0.5, 0.9, 1.0], method="linear")
    return {"n": int(len(v)), "min": float(q[0]), "p10": float(q[1]), "median": float(q[2]), "p90": float(q[3]),
            "max": float(q[4])}
