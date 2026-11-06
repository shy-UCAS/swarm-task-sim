"""V8-16 指令 8.2：两个低速例子的优化诊断（本项新增；只诊断，不修）。

固定 o08_d4/uav_02（egress，结束前约 398 s 处）、o34_d2/uav_08（patrol）；最坏帧取自 V8-15 part3/speed_cases.json。
只恢复保留骨架（v15_artifacts.load_retained）并运行一次原 optimize_segment，不做完整规划/仿真。
进程内 try/finally 包装：
  - v08.motion.optimize.prepare_problem：保留返回的 Prepared 引用；
  - scipy.optimize.minimize：调用原函数一次、原参数不变，只复制返回 x、当轮 ρ、乘子字典（求解时所用）；
所有额外 constraint_values、分类计算都在原优化完成后用保存的 x 与原 Prepared 映射离线重算，不改变求解过程中的评估次数。
低速帧所在 1 s 样条跨内逐点给出 v/t/n/j/turn/geo/sep 各类：物理量与缓冲阈值、无量纲 g、正违反量 max(g,0)、外层乘子 λ、
有效 PHR 系数 max(0, λ + ρg)。从 ls_controls / init_controls 重建样条，沿骨架切向投影速度与位移，比较变号/回摆。
用旧 save_contract 中原样的 optimized.json 字段选择与 _json_bytes 序列化本次结果，与基线逐字节比较。
用法：python -B tools/v08/diagnose_low_speed_v16.py --baseline <full_v14c> --devset ... --data-root ... --cache ...
      --speed-cases <V8-15 part3/speed_cases.json> --out <新目录>
"""
import argparse
import copy
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

PROJ = Path(__file__).resolve().parents[2]
for p in (PROJ, PROJ / "tools" / "v08"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

CASES = (("o08_d4", "uav_02", "egress"), ("o34_d2", "uav_08", "patrol"))
WINDOW_S = 60.0


def tree_hash(d):
    h = hashlib.sha256()
    for p in sorted(Path(d).rglob("*")):
        if p.is_file():
            h.update(p.relative_to(d).as_posix().encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def optimized_bytes(opt):
    """save_contract 中原样的 optimized.json 字段选择与 _json_bytes。"""
    from v08.runner.joint_monitoring import _json_bytes
    from v08.runner.monitoring import jsonable
    sol = opt["solution"]
    opt_doc = {"members": {m: {"release_s": t.release_s, "end_s": t.end_s, "altitude_m": t.altitude_m,
                               "knots": t.knots, "controls": t.controls}
                           for m, t in sorted(sol.references.items())},
               "lines": jsonable(opt["lines"]),
               "lines_raw": jsonable(opt.get("lines_raw")),
               "diagnostics": {k: jsonable(sol.diagnostics.get(k)) for k in
                               ("nit", "nfev", "message", "value", "terms", "max_abs_grad", "reference_deviation",
                                "symmetry_break", "settings_sha256")}}
    return _json_bytes(opt_doc)


def run_case(cid, member, phase, t_star, args, entries):
    import scipy.optimize as so
    import v15_artifacts as VA
    from v08.motion import optimize as OPT
    from v08.motion.optimize import load_settings
    from v08.scene.context import load_context
    d = Path(args.baseline) / "contracts" / cid
    h0 = tree_hash(d)
    ctx = load_context(entries[int(cid[1:3])], data_root=Path(args.data_root), cache_dir=Path(args.cache))
    b = VA.load_retained(d, ctx)
    plan = b["plan"]
    settings = load_settings()
    captured = {"prep": None, "rounds": []}
    real_prep, real_min = OPT.prepare_problem, so.minimize

    def prep_wrap(*a, **k):
        p = real_prep(*a, **k)
        captured["prep"] = p
        return p

    def min_wrap(*a, **k):
        p = captured["prep"]
        mult = {kk: np.array(v, copy=True) for kk, v in p.mult.items()}
        rho = float(p.rho)
        res = real_min(*a, **k)
        captured["rounds"].append({"x": np.array(res.x, copy=True), "rho": rho, "mult": mult,
                                   "nit": int(res.nit), "nfev": int(res.nfev), "message": str(res.message)})
        return res
    OPT.prepare_problem, so.minimize = prep_wrap, min_wrap
    try:
        opt = OPT.optimize_segment(ctx, plan, None, settings)
    finally:
        OPT.prepare_problem, so.minimize = real_prep, real_min
    new_bytes = optimized_bytes(opt)
    old_bytes = (d / "optimized.json").read_bytes()
    sol = opt["solution"]
    oldj = json.loads(old_bytes.decode("utf-8"))
    same_controls = all(np.array_equal(np.asarray(oldj["members"][m]["controls"]), np.asarray(t.controls))
                        and np.array_equal(np.asarray(oldj["members"][m]["knots"]), np.asarray(t.knots))
                        for m, t in sol.references.items())
    prep = captured["prep"]
    last = captured["rounds"][-1]
    x = last["x"]
    # ---- 离线重算（优化完成后）
    vals = prep.constraint_values(x)
    mi = next(i for i, m in enumerate(prep.members) if m.mid == member)
    mem = prep.members[mi]
    P, V, A, J = prep._pvaj[mi]
    t_abs = mem.tau_e + mem.r
    k_span = int(math.floor((t_star - mem.r) / mem.h))
    span = (mem.r + k_span * mem.h, mem.r + (k_span + 1) * mem.h)
    sel = np.flatnonzero((t_abs >= span[0] - 1e-9) & (t_abs <= span[1] + 1e-9))
    rho = last["rho"]
    lam_of = lambda key, n: last["mult"].get(key, np.zeros(n))       # noqa: E731
    s = np.hypot(V[:, 0], V[:, 1])
    rows = {}

    def block(key, phys, cap, idx):
        g = np.asarray(vals[key], float)[idx]
        lam = np.asarray(lam_of(key, len(vals[key])), float)[idx]
        return {"n": int(len(idx)), "physical": np.asarray(phys, float)[idx].tolist(), "buffer_threshold": cap,
                "g": g.tolist(), "violation": np.maximum(g, 0.0).tolist(), "lambda": lam.tolist(),
                "phr_coef": np.maximum(0.0, lam + rho * g).tolist(), "g_max": float(g.max()) if len(g) else None}
    pos = s > 0
    u = np.where(pos[:, None], V / np.where(pos, s, 1.0)[:, None], 0.0)
    at = np.where(pos, u[:, 0] * A[:, 0] + u[:, 1] * A[:, 1], np.hypot(A[:, 0], A[:, 1]))
    an = np.hypot(*(A - at[:, None] * u).T)
    rows["v"] = block(("v", mi), s, prep.cap_v, sel)
    rows["t"] = block(("t", mi), np.abs(at), prep.cap_t, sel)
    rows["n"] = block(("n", mi), an, prep.cap_n, sel)
    jn = np.hypot(J[:, 0], J[:, 1])
    rows["j"] = block(("j", mi), jn, prep.cap_j, np.array([k_span]) if 0 <= k_span < len(jn) else np.array([], int))
    for key in vals:
        if key[0] == "turn" and key[1] == mi:
            idx, rmin = mem.turns[key[2]]
            ins = np.flatnonzero((t_abs[idx] >= span[0] - 1e-9) & (t_abs[idx] <= span[1] + 1e-9))
            g_all = np.asarray(vals[key], float)
            rows[f"turn{key[2]}"] = {"n_in_span": int(len(ins)),
                                     "g_max": float(g_all[ins].max()) if len(ins) else None,
                                     "g_max_whole_turn": float(g_all.max()) if len(g_all) else None,
                                     "t_range_s": [float(t_abs[idx].min()), float(t_abs[idx].max())] if len(idx) else None,
                                     "required_radius_m": float(rmin)}
        if key[0] == "geo" and key[1] == mi:
            name = prep.geo.items[key[2]][0]
            rows[f"geo:{name}"] = block(key, -np.asarray(vals[key]) * prep.geo.items[key[2]][2] + prep.geo.buffer,
                                       prep.geo.buffer, sel)
    seps = {}
    for pi, (a, bb, lo, hi, _) in enumerate(prep.pairs):
        if mi not in (a, bb):
            continue
        frames = np.arange(lo, hi + 1)
        fsel = np.flatnonzero((frames / 10.0 >= span[0] - 1e-9) & (frames / 10.0 <= span[1] + 1e-9))
        if not len(fsel):
            continue
        other = prep.members[bb if a == mi else a].mid
        g = np.asarray(vals[("sep", pi)], float)[fsel]
        lam = np.asarray(lam_of(("sep", pi), len(vals[("sep", pi)])), float)[fsel]
        dist = prep.dbuf - g * prep.L0
        seps[other] = {"min_distance_m": float(dist.min()), "g_max": float(g.max()),
                       "phr_coef_max": float(np.max(np.maximum(0.0, lam + rho * g)))}
    rows["sep"] = seps
    ranking = sorted(((k, v.get("g_max")) for k, v in rows.items() if isinstance(v, dict) and v.get("g_max") is not None),
                     key=lambda kv: -kv[1])
    # ---- 初值振荡：ls_controls / init_controls / 最终解沿骨架切向的速度投影
    from v08.motion.optimize import SplineTrajectory
    fin = sol.references[member]
    ref = b["references"][member]
    tw = np.arange(max(fin.release_s, t_star - WINDOW_S), min(fin.end_s, t_star + WINDOW_S), 0.1)
    rp, rv, _ = ref.pva(tw)
    rv = np.asarray(rv, float).reshape(-1, 2)
    rs = np.hypot(rv[:, 0], rv[:, 1])
    tan = np.where((rs > 0)[:, None], rv / np.where(rs > 0, rs, 1.0)[:, None], 0.0)
    osc = {}
    for name, C in (("ls", sol.diagnostics["ls_controls"][member]), ("init", sol.diagnostics["init_controls"][member]),
                    ("final", fin.controls)):
        tr = SplineTrajectory(member, fin.release_s, fin.end_s, fin.altitude_m, fin.knots, np.asarray(C, float))
        vv = tr.evaluate(tw, 1)
        along = np.sum(vv * tan, axis=1)
        disp = np.sum((tr.evaluate(tw, 0) - np.asarray(rp, float).reshape(-1, 2)) * tan, axis=1)
        osc[name] = {"along_speed_min_m_s": float(along.min()), "along_speed_at_t_star": float(np.interp(t_star, tw, along)),
                     "along_sign_changes": int(np.sum(np.diff(np.sign(along)) != 0)),
                     "along_disp_min_m": float(disp.min()), "along_disp_max_m": float(disp.max())}
    # ---- 低速附近语义直线、间隙与合并
    def near(lines):
        out = []
        for ln in lines:
            if ln[0] != member:
                continue
            if ln[2] >= t_star - 4 * WINDOW_S and ln[1] <= t_star + 4 * WINDOW_S:
                out.append({"t0": float(ln[1]), "t1": float(ln[2]), "meta": ln[5] if len(ln) > 5 else None})
        return out
    raw = sorted(near(opt["lines_raw"]), key=lambda x: (x["t0"], x["t1"]))
    gaps = [raw[i + 1]["t0"] - raw[i]["t1"] for i in range(len(raw) - 1)]
    h1 = tree_hash(d)
    return {"contract_id": cid, "member": member, "phase": phase, "t_star_s": t_star, "span_s": span,
            "optimized_json_bytes_equal": new_bytes == old_bytes, "controls_knots_equal": bool(same_controls),
            "optimized_sha256": {"baseline": hashlib.sha256(old_bytes).hexdigest(),
                                 "recomputed": hashlib.sha256(new_bytes).hexdigest()},
            "nit_nfev": {"new": [sol.diagnostics.get("nit"), sol.diagnostics.get("nfev")],
                         "baseline": [oldj["diagnostics"].get("nit"), oldj["diagnostics"].get("nfev")]},
            "rounds": [{k: r[k] for k in ("rho", "nit", "nfev", "message")} | {"mult_keys": len(r["mult"])}
                       for r in captured["rounds"]],
            "rho_final_round": rho, "constraints_in_span": rows, "ranking_by_g_max": ranking,
            "attribution_note": "排序只作推断；第 1 外轮即通过时 λ 全 0，不能据此说没有活跃约束",
            "oscillation": osc, "semantic_lines_raw_near": raw, "raw_gaps_s": gaps,
            "merge_rule": "gap < 4·knot_s 合并（既有规则，只诊断）", "semantic_lines_merged_near": sorted(near(opt["lines"]), key=lambda x: (x["t0"], x["t1"])),
            "contract_dir_unchanged": h0 == h1, "contract_dir_sha256": h0}


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("--baseline", "--devset", "--data-root", "--cache", "--speed-cases", "--out"):
        ap.add_argument(k, required=True)
    args = ap.parse_args(argv)
    from v08.runner.monitoring import load_entries
    entries = {int(e["order"]): e for e in load_entries(args.devset)}
    cases = json.loads(Path(args.speed_cases).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    docs = []
    for cid, m, ph in CASES:
        c = next(x for x in cases if x["contract_id"] == cid and x["member"] == m and x["phase"] == ph
                 and x["category"] == "midway")
        doc = run_case(cid, m, ph, float(c["t_min_s"]), args, entries)
        doc["speed_case"] = {k: c[k] for k in c if not isinstance(c[k], (list, dict))}
        docs.append(doc)
        (out / f"{cid}_{m}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=repr) + "\n",
                                             encoding="utf-8")
        print(json.dumps({k: doc[k] for k in ("contract_id", "member", "optimized_json_bytes_equal",
                                              "controls_knots_equal", "contract_dir_unchanged")} |
                         {"top": doc["ranking_by_g_max"][:4], "osc_final": doc["oscillation"]["final"]},
                         ensure_ascii=False, default=repr))
    ok = all(d["optimized_json_bytes_equal"] and d["contract_dir_unchanged"] for d in docs)
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
