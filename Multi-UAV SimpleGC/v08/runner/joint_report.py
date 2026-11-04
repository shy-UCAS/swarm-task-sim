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

import numpy as np

QUICK_SUCCESS_FLOOR = Fraction(16, 20)      # U D.3.4
QUICK_ATTEMPT_MEDIAN = 1                    # U D.3.4
QUICK_OPT_MEDIAN_S = 60.0                   # U D.3.4
QUICK_POST_OPT_MEDIAN = 0                   # V8-13c 裁定 2：进入优化后失败次数中位数 > 0 触发
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
    """V8-13c 裁定 2 修正尝试次数项：成功合同中"进入优化之后失败的尝试次数"的中位数 > 0 即触发
    （post_optimization_failures）；原"成功合同尝试次数中位数"与骨架构造失败只作诊断。缺该字段的成功记录
    使该项无法判定（记 attempts_undetermined，不当作通过也不当作触发）。"""
    rows = list(records)
    n = len(rows)
    succ = [r for r in rows if r["success"]]
    rate = _rate(rows)
    att_all = _median_or_none(r["attempts"] for r in succ)
    post = [r.get("post_optimization_failures") for r in succ]
    undetermined = any(p is None for p in post)
    att = None if undetermined else _median_or_none(post)
    opt = _median_or_none(float(r["optimization_s"]) for r in rows)
    bad_p0 = [r["contract_id"] for r in rows if not r.get("retained_p0_ok", True)]
    trig = []
    if rate is not None and rate < QUICK_SUCCESS_FLOOR:
        trig.append("success_rate")
    if att is not None and att > QUICK_POST_OPT_MEDIAN:
        trig.append("attempts")
    if opt is not None and opt > QUICK_OPT_MEDIAN_S:
        trig.append("optimization_time")
    if bad_p0:
        trig.append("retained_p0")
    return {"triggered": trig,
            "metrics": {"contracts": n, "successes": len(succ), "success_rate": None if rate is None else float(rate),
                        "post_optimization_failures_median": att, "attempts_undetermined": undetermined,
                        "success_attempts_median_diagnostic": att_all,
                        "skeleton_failures_total_diagnostic": sum(r.get("skeleton_failures") or 0 for r in rows),
                        "optimization_s_median": opt,
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


# ================================================================ 第 5.5 节分布与三张图

def _q(xs):
    xs = [float(x) for x in xs if x is not None]
    if not xs:
        return None
    a = sorted(xs)
    pick = lambda p: a[min(len(a) - 1, int(round(p * (len(a) - 1))))]
    return {"n": len(a), "min": a[0], "p10": pick(.1), "p50": pick(.5), "p90": pick(.9), "max": a[-1],
            "mean": sum(a) / len(a)}


def distributions(records, div_records=(), *, legacy_budget_s=1800.0):
    """第 5.5 节第 1–5、8 项的数值分布（第 6、7 项另由 make_figures 与复跑比较给出）。"""
    rows = [r for r in records if not r.get("error")]
    succ = [r for r in rows if r.get("success")]
    dev_max, dev_mean, worst = [], [], None
    by_speed = {0: [], 1: [], 2: []}
    for r in succ:
        for m, d in (r.get("deviation") or {}).items():
            dev_max.append(d["max_m"])
            dev_mean.append(d["mean_m"])
            by_speed[speed_bin(r["initial_speed_m_s"])].append(d["max_m"])
            if worst is None or d["max_m"] > worst[2]:
                worst = (r["contract_id"], m, d["max_m"])
    form = {}
    for k in ("prior", "start", "realized"):
        c = {}
        for r in succ:
            v = (r.get("formation") or {}).get(k)
            c[v] = c.get(v, 0) + 1
        form[k] = c
    form["mapped_from_loose"] = sum(bool((r.get("formation") or {}).get("mapped_from_loose")) for r in succ)
    form["width_retreat"] = sum((r.get("formation") or {}).get("realized") != (r.get("formation") or {}).get("start")
                                for r in succ)
    dur = {b: [] for b in (0, 1, 2)}
    for r in succ:
        if r.get("nominal_duration_s") is not None:
            dur[speed_bin(r["initial_speed_m_s"])].append(r["nominal_duration_s"])
    all_dur = [x for v in dur.values() for x in v]
    topo = {}
    for r in succ:
        t = r.get("topology") or {}
        key = t.get("final")
        topo.setdefault(key, {"n": 0, "laps": [], "traversals": []})
        topo[key]["n"] += 1
        if t.get("laps") is not None:
            topo[key]["laps"].append(t["laps"])
        if t.get("traversals") is not None:
            topo[key]["traversals"].append(t["traversals"])
    trk = {k: [] for k in ("max_step_pos_err_m", "max_core_accel_xy", "max_core_jerk_xy", "max_10hz_diff_jerk_xy")}
    tube = 0
    for r in succ:
        for m, d in (r.get("tracking") or {}).items():
            for k in trk:
                trk[k].append(d[k])
            tube += bool(d.get("tube_exceeded_0p5"))
    timing = {k: _q([(r.get("stage_timing") or {}).get(k) for r in rows]) for k in
              ("skeleton_s", "optimize_s", "simulation_s", "verify_s")}
    stages = {}
    for r in rows:
        for s_ in r.get("attempt_stages") or []:
            stages[s_] = stages.get(s_, 0) + 1
    fails = {}
    for r in rows:
        if not r.get("success"):
            c = (r.get("failure") or {}).get("code")
            fails[c] = fails.get(c, 0) + 1
    return {
        "deviation_max_m": _q(dev_max), "deviation_mean_m": _q(dev_mean), "deviation_worst": worst,
        "deviation_max_by_speed_bin": {b: _q(v) for b, v in by_speed.items()},
        "formation": form, "nominal_duration_by_speed_bin": {b: _q(v) for b, v in dur.items()},
        "nominal_duration_over_legacy_1800s": {"count": sum(x > legacy_budget_s for x in all_dur), "of": len(all_dur)},
        "topology": {k: {"n": v["n"], "laps": _q(v["laps"]), "traversals": _q(v["traversals"])} for k, v in topo.items()},
        "tracking": {k: _q(v) for k, v in trk.items()}, "tube_exceeded_members": tube,
        "timing_s": timing, "wall_s": _q([r.get("wall_s") for r in rows]),
        "attempt_stages": stages, "final_failures": fails,
        "success_attempts": _q([r["attempts"] for r in succ]),
        "optimizer_iterations": _q([n for r in rows for n in (r.get("nit") or []) if n is not None]),
        "retained_p0_violations": [r["contract_id"] for r in succ if not r.get("retained_p0_ok", True)],
        "diversity": {"seeds": len(div_records), "success": sum(bool(r.get("success")) for r in div_records)},
    }


def _geom_xy(g):
    if g["type"] == "Circle":
        a = np.linspace(0, 2 * np.pi, 361)
        return g["center_m"][0] + g["radius_m"] * np.cos(a), g["center_m"][1] + g["radius_m"] * np.sin(a)
    v = np.asarray(g.get("vertices_m") or g.get("vertices"), float)
    b = float(g.get("buffer_m", 0.0))
    if b <= 0.0:
        v = np.vstack([v, v[:1]])
        return v[:, 0], v[:, 1]
    from ..scene.exact import signed_distance
    x0, y0 = v.min(axis=0) - b - 5
    x1, y1 = v.max(axis=0) + b + 5
    xs, ys = np.meshgrid(np.linspace(x0, x1, 300), np.linspace(y0, y1, 300))
    z = signed_distance(g, np.stack([xs, ys], axis=-1))
    return (xs, ys, z)


def _draw_geom(ax, g, **kw):
    r = _geom_xy(g)
    if len(r) == 3:
        ax.contour(r[0], r[1], r[2], levels=[0.0], colors=[kw.get("color", "k")], linewidths=kw.get("lw", 0.8))
    else:
        ax.plot(r[0], r[1], color=kw.get("color", "k"), lw=kw.get("lw", 0.8), ls=kw.get("ls", "-"))


def make_figures(out_dir, entries, *, data_root, cache_dir, fig_dir):
    """三张图：成功绕圈、成功折返、一个失败例（按最小业务 key 选；类别不存在写占位说明）。"""
    import json as _json
    from pathlib import Path as _P
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]   # 图中中文标签
    plt.rcParams["axes.unicode_minus"] = False
    from ..motion.optimize import SplineTrajectory
    from ..scene.context import load_context
    out = _P(out_dir)
    fig_dir = _P(fig_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)
    recs = _json.loads((out / "records.json").read_text(encoding="utf-8"))
    by_fid = {e["family_id"]: e for e in entries}
    pick = {}
    for r in sorted(recs, key=lambda x: x["contract_id"]):
        if r.get("success"):
            topo = (r.get("topology") or {}).get("final")
            name = "success_loop" if topo == "loop" else "success_retrace"
            pick.setdefault(name, r)
        else:
            pick.setdefault("failure", r)      # 最小失败 key，不论最后一次 attempt 停在哪个阶段
    made = {}
    for name in ("success_loop", "success_retrace", "failure"):
        r = pick.get(name)
        path = fig_dir / f"{name}.png"
        fig, ax = plt.subplots(figsize=(9, 9))
        if r is None:
            ax.text(0.5, 0.5, "本批无此类别", ha="center", va="center", fontsize=20)
            ax.set_axis_off()
            fig.savefig(path, dpi=110)
            plt.close(fig)
            made[name] = None
            continue
        ctx = load_context(by_fid[r["family_id"]], data_root=data_root, cache_dir=cache_dir)
        for f in ctx.facilities:
            for lay, col in (("warning", "orange"), ("alert", "red")):
                if lay in f.layers:
                    _draw_geom(ax, f.layers[lay], color=col)
        for _, g in ctx.obstacles:
            _draw_geom(ax, g, color="k", lw=1.2)
        cdir = out / "contracts" / r["contract_id"]
        if name != "failure":
            sk = _json.loads((cdir / "skeleton.json").read_text(encoding="utf-8"))
            op = _json.loads((cdir / "optimized.json").read_text(encoding="utf-8"))
            skel = {m: np.asarray(sk["arrays"][v["curve_xy"]["npz"]], float) for m, v in sk["members"].items()}
            opt = op["members"]
            tracks = {m: np.load(cdir / "tracks" / m / "p.npy") for m in skel}
            wit = None
        else:
            fwp = cdir / "failure_witness.json"
            if fwp.exists():
                fw = _json.loads(fwp.read_text(encoding="utf-8"))
            else:
                res = _json.loads((cdir / "result.json").read_text(encoding="utf-8"))
                last = res["attempt_log"][-1] if res["attempt_log"] else {}
                fw = {"skeleton_members": {}, "stage": last.get("stage"),
                      "physical_failures": [{"kind": f"最后一次 attempt 停在 {last.get('feasible_set') or last.get('stage')}，"
                                                     f"无骨架/优化曲线；最终 {(res.get('failure') or {}).get('code')}"}]}
                p0 = np.array([s_["position_enu_m"][:2] for s_ in ctx.family.initial_states.values()], float)
                ax.plot(p0[:, 0], p0[:, 1], "k^", ms=5, label="成员起点")
            skel = {m: np.asarray(v, float) for m, v in fw["skeleton_members"].items()}
            opt = fw.get("optimized") or {}
            tracks = {m: np.asarray(v, float) for m, v in (fw.get("tracks_p") or {}).items()}
            wit = fw
        for i, m in enumerate(sorted(skel)):
            ax.plot(skel[m][:, 0], skel[m][:, 1], color="0.6", lw=0.8, label="骨架" if i == 0 else None)
            if m in opt:
                o = opt[m]
                tr = SplineTrajectory(m, o["release_s"], o["end_s"], 0.0, np.asarray(o["knots"]),
                                      np.asarray(o["controls"]))
                t = np.arange(o["release_s"], o["end_s"], 0.5)
                xy = tr.evaluate(t)
                ax.plot(xy[:, 0], xy[:, 1], color="C0", lw=0.9, label="优化" if i == 0 else None)
            if m in tracks:
                ax.plot(tracks[m][:, 0], tracks[m][:, 1], color="C2", lw=0.6, ls="--", label="实测" if i == 0 else None)
        if wit is not None:
            for f_ in (wit.get("physical_failures") or []) + (wit.get("monitoring_failures") or []):
                ax.set_title(f"{r['contract_id']} 失败：{wit.get('stage')} {f_.get('kind')}", fontsize=10)
                break
        else:
            ax.set_title(f"{r['contract_id']} {name}", fontsize=10)
        ax.set_aspect("equal")
        ax.legend(loc="upper right", fontsize=8)
        fig.savefig(path, dpi=110)
        plt.close(fig)
        made[name] = r["contract_id"]
    return made


# ================================================================ V8-13c 裁定 3：骨架重试偏差诊断（只报告，不设门禁）

def ks_statistic(a, b):
    """两样本 Kolmogorov–Smirnov 统计量 D = sup|F_a − F_b|（经验分布在合并样本点上求值）。"""
    a = np.sort(np.asarray([x for x in a if x is not None], float))
    b = np.sort(np.asarray([x for x in b if x is not None], float))
    if not len(a) or not len(b):
        return None
    pts = np.concatenate([a, b])
    fa = np.searchsorted(a, pts, side="right") / len(a)
    fb = np.searchsorted(b, pts, side="right") / len(b)
    return float(np.max(np.abs(fa - fb)))


def cramers_v(a, b):
    """两组类别样本的 Cramér's V = sqrt(χ²/(n·(min(r,c)−1)))，表为 2 × 类别数。"""
    a = [x for x in a if x is not None]
    b = [x for x in b if x is not None]
    cats = sorted({*map(str, a), *map(str, b)})
    if not a or not b or len(cats) < 2:
        return None
    table = np.array([[sum(str(x) == c for x in g) for c in cats] for g in (a, b)], float)
    n = table.sum()
    exp = table.sum(1, keepdims=True) * table.sum(0, keepdims=True) / n
    chi2 = float(np.sum((table - exp) ** 2 / np.where(exp > 0, exp, 1.0)))
    return float(np.sqrt(chi2 / (n * (min(table.shape) - 1))))


def skeleton_bias(records):
    """按初速/人数/设施数分档报告平均骨架尝试次数（= attempt 数，每次 attempt 构造一次骨架）与平均骨架构造失败数；
    比较"全部抽到的骨架"（所有合同所有 attempt 中已抽到形状者）与"最终保留的骨架"（成功合同的最后一次）的分布。"""
    rows = [r for r in records if not r.get("error") and r.get("attempts")]
    bins = {}
    for name, key in (("speed", lambda r: speed_bin(r["initial_speed_m_s"])), ("group", lambda r: group_bin(r["group_size"])),
                      ("facility", lambda r: int(r["facility_count"]))):
        out = {}
        for r in rows:
            out.setdefault(key(r), []).append(r)
        bins[name] = {k: {"contracts": len(v), "mean_attempts": float(np.mean([x["attempts"] for x in v])),
                          "mean_skeleton_failures": float(np.mean([x.get("skeleton_failures") or 0 for x in v]))}
                      for k, v in sorted(out.items())}
    drawn = [d for r in rows for d in (r.get("draws") or []) if d]
    kept = [(r.get("draws") or [None])[-1] for r in rows if r.get("success")]
    kept = [d for d in kept if d]
    loops = lambda ds: [d.get("laps") for d in ds if d.get("topology") == "loop"]
    travs = lambda ds: [d.get("traversals") for d in ds if d.get("topology") == "retrace"]
    comp = {
        "patrol_mean_radius_rho0_ks": ks_statistic([d.get("rho0_m") for d in drawn], [d.get("rho0_m") for d in kept]),
        "laps_ks": ks_statistic(loops(drawn), loops(kept)),
        "traversals_ks": ks_statistic(travs(drawn), travs(kept)),
        "topology_cramers_v": cramers_v([d.get("topology") for d in drawn], [d.get("topology") for d in kept]),
        "formation_cramers_v": cramers_v([d.get("formation") for d in drawn], [d.get("formation") for d in kept]),
    }
    counts = {"drawn": len(drawn), "kept": len(kept),
              "drawn_with_shape": sum(d.get("rho0_m") is not None for d in drawn),
              "attempts_without_draw": sum(1 for r in rows for d in (r.get("draws") or []) if not d)}
    return {"bins": bins, "drawn_vs_kept": comp, "counts": counts}
