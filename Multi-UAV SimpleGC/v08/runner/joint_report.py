"""V8-13 检查点、分档与合并 Fréchet（指令 4.4、5.3、5.4；第 6.4 节接口）。

所有比率用 Fraction 精确比较；阈值原样来自 U D.3.4 / D.4.4：
- 快速检查点 2：成功 < 16/20、成功合同尝试数中位数 > 1、单合同优化耗时中位数 > 60 s、任何保留段违反 P0 门禁；
- 全量诊断：总成功率 < 80%；设施数/初速/人数任一非空档比总率低超过 20 个百分点；成功尝试中位数 > 1；
  合并 Fréchet（距离/该族横向间距，所有可比较对合在一起）中位数 < 1。
严格比较：恰好 16/20、中位数 1、60 s、20 个百分点、Fréchet 1 本身都不触发。缺数据（如零成功的尝试中位数、
无配对的 Fréchet）记 None，不触发、不编造。本模块导入时不读数据、不建目录。
"""
from fractions import Fraction
from statistics import median

QUICK_SUCCESS_FLOOR = Fraction(16, 20)      # U D.3.4
QUICK_ATTEMPT_MEDIAN = 1                    # U D.3.4
QUICK_OPT_MEDIAN_S = 60.0                   # U D.3.4
FULL_SUCCESS_FLOOR = Fraction(80, 100)      # U D.4.4
FULL_GAP = Fraction(20, 100)                # U D.4.4：20 个百分点


def speed_bin(value):
    """U D.4：[4,6)→0、[6,8)→1、[8,10]→2（10 属末档）。"""
    v = float(value)
    if v < 6.0:
        return 0
    if v < 8.0:
        return 1
    return 2


def group_bin(value):
    """U D.4：1–4→0、5–8→1、9–12→2（公共抽签实际使用的第 0 组人数）。"""
    n = int(value)
    if n <= 4:
        return 0
    if n <= 8:
        return 1
    return 2


def _median_or_none(xs):
    xs = list(xs)
    return median(xs) if xs else None


def pooled_frechet(blocks):
    """所有可比较对的 "Fréchet/该族横向间距" 合并后取一个中位数；无配对返回 None（N/A）。
    success/attempted 只说明覆盖，不作配对有效性门槛。"""
    vals = []
    for b in blocks:
        s = float(b["spacing_m"])
        vals.extend(float(d) / s for d in b["distances_m"])
    return _median_or_none(vals)


def _rate(rows):
    n = len(rows)
    return Fraction(sum(bool(r["success"]) for r in rows), n) if n else None


def quick_checkpoint(records):
    rows = list(records)
    n = len(rows)
    succ = [r for r in rows if r["success"]]
    rate = _rate(rows)
    att = _median_or_none(r["attempts"] for r in succ)
    opt = _median_or_none(float(r["optimization_s"]) for r in rows)
    bad_p0 = [r["contract_id"] for r in rows if not r.get("retained_p0_ok", True)]
    trig = []
    if rate is not None and rate < QUICK_SUCCESS_FLOOR:
        trig.append("success_rate")
    if att is not None and att > QUICK_ATTEMPT_MEDIAN:
        trig.append("attempts")
    if opt is not None and opt > QUICK_OPT_MEDIAN_S:
        trig.append("optimization_time")
    if bad_p0:
        trig.append("retained_p0")
    return {"triggered": trig,
            "metrics": {"contracts": n, "successes": len(succ), "success_rate": None if rate is None else float(rate),
                        "success_attempts_median": att, "optimization_s_median": opt,
                        "optimization_entered": sum(float(r["optimization_s"]) > 0.0 for r in rows),
                        "retained_p0_violations": bad_p0}}


def _gap(rows, overall, key):
    bins = {}
    for r in rows:
        bins.setdefault(key(r), []).append(r)
    out, worst = {}, None
    for b, rs in sorted(bins.items()):
        rate = _rate(rs)
        gap = overall - rate
        out[b] = {"n": len(rs), "successes": sum(bool(x["success"]) for x in rs), "rate": float(rate),
                  "gap": float(gap)}
        if worst is None or gap > worst:
            worst = gap
    return out, worst


def full_checkpoint(records, frechet_blocks):
    rows = list(records)
    overall = _rate(rows)
    trig = []
    metrics = {"contracts": len(rows), "success_rate": None if overall is None else float(overall)}
    if overall is not None and overall < FULL_SUCCESS_FLOOR:
        trig.append("success_rate")
    for name, key in (("facility_gap", lambda r: int(r["facility_count"])),
                      ("speed_gap", lambda r: speed_bin(r["initial_speed_m_s"])),
                      ("group_gap", lambda r: group_bin(r["group_size"]))):
        if overall is None:
            continue
        bins, worst = _gap(rows, overall, key)
        metrics[name] = bins
        if worst is not None and worst > FULL_GAP:
            trig.append(name)
    att = _median_or_none(r["attempts"] for r in rows if r["success"])
    metrics["success_attempts_median"] = att
    if att is not None and att > QUICK_ATTEMPT_MEDIAN:
        trig.append("attempts")
    fr = pooled_frechet(frechet_blocks)
    metrics["frechet_pooled_median"] = fr
    if fr is not None and fr < 1.0:
        trig.append("frechet")
    return {"triggered": trig, "metrics": metrics}
