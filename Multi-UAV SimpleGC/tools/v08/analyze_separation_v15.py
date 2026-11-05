"""V8-15 第 3 部分入口：只读分析既有 full_v14c（指令 3.1–3.3）；输入只读、输出新目录。

不重新规划、优化或仿真。对 198 个保留合同逐成员对求三种距离（优化 XY 采样、实测三维采样、实测三维相邻帧插值）
的全程与分阶段最小值；对全部 200 合同统计失败 attempt 的阶段与底层代码；对阶段最低速度最坏样例归类。
P0-1 按附录裁定 1 引用 V8-14 的 e2e 结果，不在这里重算段核验与有效性。

用法（Multi-UAV SimpleGC 目录，conda llm，线程变量=1）：
    python -B tools/v08/analyze_separation_v15.py --baseline <full_v14c> --devset <devset_v08.json>
        --data-root <SwarmData> --cache <V8-15 缓存副本> --out <不存在的新目录> [--workers 8] [--limit N]
"""
import argparse
import csv
import json
import math
import sys
import time
import traceback
from itertools import combinations
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(HERE))

from v15_metrics import FRAME_US, pair_minima, quantiles, segment_min   # noqa: E402
import v15_artifacts as VA                                               # noqa: E402

SOURCES = ("optimized_xy", "measured_sample", "measured_interp")
SPEED_RATIO = 0.8          # U D.2.3：只用于选诊断样例
ALONG_M = 10.0             # U D.2.3
TAIL_S = 20.0              # U D.2.3：阶段末尾 20 s（含边界）
NAMED = (("o34_d2", "uav_08", "patrol"), ("o08_d4", "uav_02", "egress"))   # REPORT14 C.3 / U C.2


def _label(ca, cb):
    na, nb = VA.CODE_NAMES[int(ca)], VA.CODE_NAMES[int(cb)]
    return na if na == nb else "mixed:" + "|".join(sorted((na, nb)))


def _turn_who(ta, tb):
    return "both" if (ta and tb) else ("a" if ta else ("b" if tb else None))


def _group_min(d, t_s, keys):
    """按键分组取最小值；平局取最早时刻。返回 {key: (min, t_s)}。"""
    out = {}
    order = np.lexsort((t_s, d))
    for i in order:
        k = keys[i]
        if k not in out:
            out[k] = (float(d[i]), float(t_s[i]))
    return out


def _pair_bins(d, t_s, code_a, code_b, turn_a, turn_b):
    """分阶段（互斥 phase 分档）与掉头子分档（重叠）的最小值。"""
    phase_keys = [_label(x, y) for x, y in zip(code_a, code_b)]
    out = {("phase", k): v for k, v in _group_min(d, t_s, phase_keys).items()}
    who = [_turn_who(x, y) for x, y in zip(turn_a, turn_b)]
    sel = np.array([w is not None for w in who])
    if sel.any():
        idx = np.flatnonzero(sel)
        out.update({("turn", k): v for k, v in _group_min(d[idx], t_s[idx], [who[i] for i in idx]).items()})
    return out


def analyze_contract(bundle, hold_s):
    """一个保留合同：返回 (行列表, 合同摘要)。"""
    from v08.criteria.validity import visible_track
    cid = bundle["contract_id"]
    members = sorted(bundle["tracks"])
    bounds = {m: VA.phase_bounds(bundle, m) for m in members}
    btimes = {m: VA.boundary_times(bounds[m]) for m in members}
    # 优化：optimize_checks._frames 口径
    opt = {}
    for m in members:
        tr = bundle["splines"][m]
        f0 = math.ceil(float(tr.release_s) * 10 - 1e-9)
        f1 = math.floor((float(tr.end_s) + hold_s) * 10 + 1e-9)
        fr = np.arange(f0, f1 + 1, dtype=np.int64)
        opt[m] = (fr, tr.evaluate(fr / 10.0))
    meas = {}
    for m in members:
        vt = visible_track(bundle["tracks"][m], bundle["release_us"][m])
        meas[m] = (np.asarray(vt.time_us, np.int64), np.asarray(vt.p, float))
    rows, empty = [], []
    for a, b in combinations(members, 2):
        base = {"contract_id": cid, "pair": f"{a}|{b}", "formation": bundle["formation"], "topology": bundle["topology"]}
        # --- 优化 XY 采样
        fa, pa = opt[a]
        fb, pb = opt[b]
        com, ia, ib = np.intersect1d(fa, fb, assume_unique=True, return_indices=True)
        if len(com):
            d = np.hypot(pa[ia, 0] - pb[ib, 0], pa[ia, 1] - pb[ib, 1])
            t = com / 10.0
            ca, ta = VA.phase_codes_at(bounds[a], t)
            cb, tb = VA.phase_codes_at(bounds[b], t)
            k = int(np.argmin(d))
            rows.append({**base, "source": "optimized_xy", "bin_kind": "all", "bin": "all", "min_m": float(d[k]),
                         "t_s": float(t[k]), "frames": int(len(com))})
            for (kind, key), (v, ts) in _pair_bins(d, t, ca, cb, ta, tb).items():
                rows.append({**base, "source": "optimized_xy", "bin_kind": kind, "bin": key, "min_m": v, "t_s": ts,
                             "frames": None})
        else:
            empty.append({**base, "source": "optimized_xy", "reason": "no_common_frames"})
        # --- 实测三维采样与插值
        tau_a, qa = meas[a]
        tau_b, qb = meas[b]
        com, ia, ib = np.intersect1d(tau_a, tau_b, assume_unique=True, return_indices=True)
        pm = pair_minima(com, qa[ia], qb[ib])
        if pm["reason"] is not None:
            empty.append({**base, "source": "measured", "reason": pm["reason"]})
            continue
        r = qa[ia] - qb[ib]
        d = np.linalg.norm(r, axis=1)
        t = com / 1e6
        ca, ta = VA.phase_codes_at(bounds[a], t)
        cb, tb = VA.phase_codes_at(bounds[b], t)
        rows.append({**base, "source": "measured_sample", "bin_kind": "all", "bin": "all", "min_m": pm["sample_min_m"],
                     "t_s": pm["sample_time_us"] / 1e6, "frames": int(len(com))})
        for (kind, key), (v, ts) in _pair_bins(d, t, ca, cb, ta, tb).items():
            rows.append({**base, "source": "measured_sample", "bin_kind": kind, "bin": key, "min_m": v, "t_s": ts,
                         "frames": None})
        rows.append({**base, "source": "measured_interp", "bin_kind": "all", "bin": "all", "min_m": pm["interp_min_m"],
                     "t_s": pm["t_s"], "frames": int(len(com)), "interval_start_us": pm["interval_start_us"],
                     "fraction": pm["fraction"]})
        cont = np.flatnonzero(np.diff(com) == FRAME_US)
        if len(cont):
            # 按两成员全部阶段/掉头边界把区间切小，逐小区间解析求最小
            ks, lo, hi = [], [], []
            splits = {}
            for bt in sorted(set(btimes[a]) | set(btimes[b])):
                bu = bt * 1e6
                j = int(np.searchsorted(com, bu, side="right")) - 1
                if 0 <= j < len(com) - 1 and com[j + 1] - com[j] == FRAME_US and com[j] < bu < com[j + 1]:
                    splits.setdefault(j, []).append((bu - com[j]) / FRAME_US)
            for j in cont:
                al = [0.0] + sorted(splits.get(int(j), [])) + [1.0]
                for x0, x1 in zip(al[:-1], al[1:]):
                    ks.append(int(j))
                    lo.append(x0)
                    hi.append(x1)
            ks, lo, hi = np.asarray(ks), np.asarray(lo), np.asarray(hi)
            di, alpha = segment_min(r[ks], r[ks + 1] - r[ks], lo, hi)
            t_exact = (com[ks].astype(float) + alpha * FRAME_US) / 1e6
            t_mid = (com[ks].astype(float) + 0.5 * (lo + hi) * FRAME_US) / 1e6
            ca, ta = VA.phase_codes_at(bounds[a], t_mid)
            cb, tb = VA.phase_codes_at(bounds[b], t_mid)
            # 孤立采样帧（不在任何连续区间端点上）作为候选并入对应分档
            iso = np.setdiff1d(np.arange(len(com)), np.r_[cont, cont + 1])
            if len(iso):
                ci, ti = VA.phase_codes_at(bounds[a], t[iso])
                cj, tj = VA.phase_codes_at(bounds[b], t[iso])
                di = np.r_[di, d[iso]]
                t_exact = np.r_[t_exact, t[iso]]
                ca, cb, ta, tb = np.r_[ca, ci], np.r_[cb, cj], np.r_[ta, ti], np.r_[tb, tj]
            for (kind, key), (v, ts) in _pair_bins(di, t_exact, ca, cb, ta, tb).items():
                rows.append({**base, "source": "measured_interp", "bin_kind": kind, "bin": key, "min_m": v,
                             "t_s": ts, "frames": None})
        else:
            for (kind, key), (v, ts) in _pair_bins(d, t, ca, cb, ta, tb).items():
                rows.append({**base, "source": "measured_interp", "bin_kind": kind, "bin": key, "min_m": v,
                             "t_s": ts, "frames": None})
    allm = {s: [r["min_m"] for r in rows if r["source"] == s and r["bin_kind"] == "all"] for s in SOURCES}
    summ = {"contract_id": cid, "members": len(members), "pairs": len(members) * (len(members) - 1) // 2,
            "empty": empty, "contract_min": {s: (min(v) if v else None) for s, v in allm.items()},
            "bounds": {m: {k: v for k, v in bounds[m].items()} for m in members}}
    return rows, summ


def speed_cases(bundle, saved_pm):
    """指令 3.3：按保存的 phase_metrics 选样（ratio<0.8 或 along>10），用同一批参考≥0.5 m/s 帧重新求值并归类。"""
    from v08.diagnostics.monitoring_skeleton import _min_reference_speed
    vmin = _min_reference_speed()
    plan = bundle["plan"]
    mm = (plan.witnesses or {}).get("member_map_v14") or {}
    out = []
    for m in sorted(bundle["tracks"]):
        pmm = (saved_pm or {}).get(m) or {}
        for ph in ("patrol", "egress"):
            rec = (pmm.get("phases") or {}).get(ph)
            if not rec:
                continue
            ratio, along = rec.get("measured_ratio"), rec.get("measured_along_max_m")
            hit = (ratio is not None and ratio < SPEED_RATIO) or (along is not None and along > ALONG_M)
            named = (bundle["contract_id"], m, ph) in NAMED
            if not (hit or named):
                continue
            maps = bundle["maps"][m]
            nom = maps["nominal"]
            cs, ta = np.asarray(maps["curve_s"], float), np.asarray(maps["t_abs"], float)
            ref = bundle["references"][m]
            mp = mm["members"][m]
            pa, pb = mp["patrol_member_s"]
            t_pa, t_pb = float(np.interp(pa, cs, ta)), float(np.interp(pb, cs, ta))
            tr = bundle["tracks"][m]
            t = np.asarray(tr.tau_us, np.int64) / 1e6
            sel0 = (t >= ref.release_s - 1e-9) & (t <= ref.end_s + 1e-9)
            t = t[sel0]
            rp, rv, _ = ref.pva(t)
            rp, rv = np.asarray(rp, float).reshape(-1, 2), np.asarray(rv, float).reshape(-1, 2)
            s_now = np.interp(t, ta, cs)
            tan_c = np.asarray(nom.curve.tangent, float)
            idx = np.clip(np.searchsorted(cs, s_now, side="right") - 1, 0, len(tan_c) - 1)
            sp = np.hypot(rv[:, 0], rv[:, 1])
            tan = np.where((sp > 0.0)[:, None], rv / np.maximum(sp, np.finfo(float).tiny)[:, None], tan_c[idx])
            tan = tan / np.maximum(np.hypot(tan[:, 0], tan[:, 1]), np.finfo(float).tiny)[:, None]
            sp_l = bundle["splines"][m]
            op, ov = sp_l.evaluate(t, 0), sp_l.evaluate(t, 1)
            mpv, mvv = np.asarray(tr.p, float)[sel0, :2], np.asarray(tr.v, float)[sel0, :2]
            a, b = (t_pa, t_pb) if ph == "patrol" else (t_pb, ref.end_s)
            sel = (t >= a) & ((t < b) if ph == "patrol" else (t <= b))
            moving = sel & (sp >= vmin)
            row = {"contract_id": bundle["contract_id"], "member": m, "phase": ph, "stage_start_s": a, "stage_end_s": b,
                   "selected_by": ("ratio" if ratio is not None and ratio < SPEED_RATIO else "") +
                                  ("+along" if along is not None and along > ALONG_M else "") or "named_only",
                   "saved_ratio": ratio, "saved_along_max_m": along, "n_moving": int(moving.sum())}
            if not moving.any():
                row.update(category="N/A", reason="no_moving_reference_samples")
                out.append(row)
                continue
            ms = np.hypot(mvv[:, 0], mvv[:, 1])
            os_ = np.hypot(ov[:, 0], ov[:, 1])
            iw = np.flatnonzero(moving)
            k = int(iw[int(np.argmin(ms[iw]))])
            ref_min, meas_min = float(sp[moving].min()), float(ms[moving].min())
            along_all = np.abs(np.sum((mpv[sel] - rp[sel]) * tan[sel], axis=1))
            ka = int(np.argmax(along_all))
            isel = np.flatnonzero(sel)
            row.update(t_min_s=float(t[k]), to_stage_end_s=float(b - t[k]),
                       category="tail_20s" if b - t[k] <= TAIL_S else "midway",
                       position_xy=[float(mpv[k, 0]), float(mpv[k, 1])], reference_speed_at_t_m_s=float(sp[k]),
                       optimized_speed_at_t_m_s=float(os_[k]), measured_speed_at_t_m_s=float(ms[k]),
                       reference_min_m_s=ref_min, measured_min_m_s=meas_min, ratio=meas_min / ref_min,
                       ratio_equals_saved=(ratio is not None and meas_min / ref_min == ratio),
                       along_max_m=float(along_all[ka]), along_max_t_s=float(t[isel[ka]]),
                       along_max_xy=[float(mpv[isel[ka], 0]), float(mpv[isel[ka], 1])],
                       along_equals_saved=(along is not None and float(along_all[ka]) == along))
            out.append(row)
    return out


def failed_attempts(contract_dirs):
    """全部合同 result.json.attempt_log 的失败 attempt：stage/reason 与底层代码。"""
    by_stage, low, sep_phys, sep_only, sep_mixed, sep_valid, missing_phys = {}, {}, 0, 0, 0, 0, 0
    rows = []
    n_att = n_fail = 0
    retained_hist = {"true": 0, "false": 0}
    for d in contract_dirs:
        res = json.loads((d / "result.json").read_text(encoding="utf-8"))
        if res.get("success"):
            retained_hist["true" if res.get("retained_p0_ok") else "false"] += 1
        for a in res.get("attempt_log") or []:
            n_att += 1
            if a.get("ok"):
                continue
            n_fail += 1
            key = f"{a.get('stage')}/{a.get('reason')}"
            by_stage[key] = by_stage.get(key, 0) + 1
            codes = []
            for seg in a.get("segment_failures") or []:
                codes += [f"segment:{f[1]}:{f[2]}" for f in seg]
            for c in (a.get("validity") or {}).get("codes") or []:
                codes.append(f"validity:{c}")
            opt = a.get("optimize") or {}
            phys = opt.get("physical_failures")
            kinds = []
            if opt and phys is None and a.get("stage") in ("optimize", "optimize_monitoring"):
                missing_phys += 1
            for f in phys or []:
                kinds.append(f.get("kind"))
                codes.append(f"physical:{f.get('kind')}")
            for f in opt.get("monitoring_failures") or []:
                codes.append("monitoring:" + str(f.get("kind") if isinstance(f, dict) else f))
            if "separation" in kinds:
                sep_phys += 1
                if set(kinds) == {"separation"}:
                    sep_only += 1
                else:
                    sep_mixed += 1
            if "separation_violation" in ((a.get("validity") or {}).get("codes") or []):
                sep_valid += 1
            for c in set(codes):
                low[c] = low.get(c, 0) + 1
            rows.append({"contract_id": d.name, "attempt": a.get("attempt"), "stage": a.get("stage"),
                         "reason": a.get("reason"), "code": a.get("code"), "skeleton_stage": a.get("skeleton_stage"),
                         "physical_kinds": sorted(set(kinds)), "low_codes": sorted(set(codes)),
                         "optimizer_message": opt.get("message")})
    return {"contracts": len(contract_dirs), "attempts": n_att, "failed_attempts": n_fail,
            "by_stage_reason": dict(sorted(by_stage.items())), "low_level_codes": dict(sorted(low.items())),
            "attempts_with_physical_separation": sep_phys, "separation_only": sep_only,
            "separation_mixed": sep_mixed, "validity_separation_violation": sep_valid,
            "optimize_attempts_missing_physical_failures": missing_phys,
            "worst_constraint_is_separation": "N/A：_attempt_summary 未保存 AL 最大约束键与每轮违反量（指令 11.7）",
            "retained_p0_ok_history": retained_hist}, rows


def _family_job(job):
    """一个族的全部保留合同（同族串行，场景缓存只读）。"""
    import os
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(k, "1")
    entry, dirs, data_root, cache = job
    from v08.motion.optimize import load_settings, physical_limits
    from v08.runner import joint_monitoring as JM
    from v08.runner.monitoring import jsonable
    from v08.scene.context import load_context
    hold_s = physical_limits(load_settings())["hold_s"]
    out = []
    try:
        ctx = load_context(entry, data_root=Path(data_root), cache_dir=Path(cache))
    except Exception:
        return [{"contract_id": Path(d).name, "error": traceback.format_exc()} for d in dirs]
    for d in dirs:
        d = Path(d)
        t0 = time.perf_counter()
        try:
            bundle = VA.load_retained(d, ctx)
            rows, summ = analyze_contract(bundle, hold_s)
            saved_pm = bundle["result"].get("phase_metrics")
            try:
                again = jsonable(JM.phase_diagnostics(VA.phase_res(bundle)))
                summ["phase_metrics_reproduced"] = (json.dumps(again, sort_keys=True) ==
                                                    json.dumps(jsonable(saved_pm), sort_keys=True))
            except Exception:
                summ["phase_metrics_reproduced"] = None
                summ["phase_metrics_error"] = traceback.format_exc()
            summ["speed_cases"] = speed_cases(bundle, saved_pm)
            ret = [a for a in bundle["result"]["attempt_log"] if a.get("ok")]
            summ["saved_validity_min_m"] = (ret[-1].get("validity") or {}).get("min_separation_m") if ret else None
            summ["order"], summ["draw_index"] = int(bundle["contract"]["order"]), int(bundle["contract"]["draw_index"])
            summ["formation"], summ["topology"] = bundle["formation"], bundle["topology"]
            summ["wall_s"] = time.perf_counter() - t0
            out.append({"contract_id": d.name, "rows": rows, "summary": summ})
        except Exception:
            out.append({"contract_id": d.name, "error": traceback.format_exc()})
    return out


def _stats(rows, summaries):
    groups = {}
    for r in rows:
        if r["bin_kind"] == "all":
            continue
        k = (r["formation"], r["topology"], f"{r['bin_kind']}:{r['bin']}", r["source"])
        g = groups.setdefault(k, {"v": [], "c": set()})
        g["v"].append(r["min_m"])
        g["c"].add(r["contract_id"])
    out = []
    for (f, tp, b, s), g in sorted(groups.items(), key=lambda x: tuple(str(y) for y in x[0])):
        q = quantiles(g["v"])
        out.append({"formation": f, "topology": tp, "bin": b, "source": s, "samples": q["n"], "contracts": len(g["c"]),
                    **{k: q[k] for k in ("min", "p10", "median", "p90", "max")}})
    overall = {}
    for s in SOURCES:
        pair_all = [r["min_m"] for r in rows if r["source"] == s and r["bin_kind"] == "all"]
        contract_min = [x["contract_min"][s] for x in summaries if x["contract_min"][s] is not None]
        bybin = {}
        for r in rows:
            if r["source"] == s and r["bin_kind"] != "all":
                bybin.setdefault(f"{r['bin_kind']}:{r['bin']}", []).append(r["min_m"])
        overall[s] = {"pair_level": quantiles(pair_all), "contract_level": quantiles(contract_min),
                      "by_bin": {k: quantiles(v) for k, v in sorted(bybin.items())}}
    return out, overall


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--devset", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None, help="只分析前 N 个保留合同（开发自检用）")
    args = ap.parse_args(argv)
    from v08.runner.monitoring import guard_path, load_entries, write_json
    data_root = Path(args.data_root)
    out = guard_path(args.out, label="输出", data_root=data_root, must_not_exist=True)
    cache = guard_path(args.cache, label="缓存", data_root=data_root)
    base = Path(args.baseline).resolve()
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.time()
    entries = {int(e["order"]): e for e in load_entries(args.devset)}
    dirs = sorted(p for p in (base / "contracts").iterdir() if p.is_dir())
    fa, fa_rows = failed_attempts(dirs)
    ok_dirs = [d for d in dirs if json.loads((d / "result.json").read_text(encoding="utf-8")).get("success")]
    if args.limit:
        ok_dirs = ok_dirs[:args.limit]
    jobs = {}
    for d in ok_dirs:
        o = int(json.loads((d / "contract.json").read_text(encoding="utf-8"))["order"])
        jobs.setdefault(o, []).append(str(d))
    tasks = [(entries[o], ds, str(data_root), str(cache)) for o, ds in sorted(jobs.items())]
    results = []
    if args.workers <= 1:
        for t in tasks:
            results += _family_job(t)
    else:
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=mp.get_context("spawn")) as ex:
            for got in ex.map(_family_job, tasks):
                results += got
                print(f"[{len(results)}/{len(ok_dirs)}] {got[-1]['contract_id']}", flush=True)
    results.sort(key=lambda x: x["contract_id"])
    errors = [x for x in results if "error" in x]
    good = [x for x in results if "error" not in x]
    rows = [r for x in good for r in x["rows"]]
    summaries = [x["summary"] for x in good]
    by_group, overall = _stats(rows, summaries)
    worst = {}
    for s in SOURCES:
        pr = [r for r in rows if r["source"] == s and r["bin_kind"] == "all"]
        sm = {x["contract_id"]: x for x in summaries}
        pr.sort(key=lambda r: (r["min_m"], sm[r["contract_id"]]["order"], sm[r["contract_id"]]["draw_index"],
                               r["pair"], r["t_s"]))
        worst[s] = pr[:10]
    consist = [{"contract_id": x["contract_id"], "measured_sample_min": x["contract_min"]["measured_sample"],
                "saved_validity_min": x["saved_validity_min_m"],
                "equal": x["contract_min"]["measured_sample"] == x["saved_validity_min_m"]} for x in summaries]
    cases = [c for x in summaries for c in x["speed_cases"]]
    cat = {}
    for c in cases:
        if (c["contract_id"], c["member"], c["phase"]) in NAMED and c["selected_by"] == "named_only":
            continue
        k = f"{c['phase']}:{c['category']}"
        cat[k] = cat.get(k, 0) + 1
    with open(out / "pairs.csv", "w", encoding="utf-8", newline="") as fh:
        cols = ["contract_id", "formation", "topology", "pair", "source", "bin_kind", "bin", "min_m", "t_s", "frames",
                "interval_start_us", "fraction"]
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(out / "by_group.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(by_group[0].keys()) if by_group else ["empty"])
        w.writeheader()
        for r in by_group:
            w.writerow(r)
    write_json(out / "failed_attempts_rows.json", fa_rows, indent=1)
    write_json(out / "speed_cases.json", cases, indent=1)
    summary = {"baseline": str(base), "contracts_total": len(dirs), "retained_selected": len(ok_dirs),
               "analyzed": len(good), "errors": [{"contract_id": x["contract_id"], "error": x["error"]} for x in errors],
               "empty_pairs": [e for x in summaries for e in x["empty"]],
               "overall": overall, "worst10": worst,
               "validity_consistency": {"equal": sum(c["equal"] for c in consist), "total": len(consist),
                                        "mismatch": [c for c in consist if not c["equal"]]},
               "phase_metrics_reproduced": {"true": sum(x.get("phase_metrics_reproduced") is True for x in summaries),
                                            "false": [x["contract_id"] for x in summaries
                                                      if x.get("phase_metrics_reproduced") is False],
                                            "error": [x["contract_id"] for x in summaries
                                                      if x.get("phase_metrics_reproduced") is None]},
               "speed_case_counts": cat, "speed_cases_total": len(cases),
               "named_cases": [c for c in cases if (c["contract_id"], c["member"], c["phase"]) in NAMED],
               "failed_attempts": fa, "notes": {
                   "turn_overlap": "turn 子分档与 phase 分档重叠（掉头属于巡逻的子区间），不能相加",
                   "optimized": "XY 水平距离，frames = optimize_checks._frames（释放至 end+hold_s）",
                   "measured": "三维，visible_track 后的真实整数 tau_us 共同帧，含保存的末端保持帧",
                   "interp": "仅相邻共同帧（差 100000 µs）；按两成员阶段/掉头边界切小区间解析求最小；边界点同属两侧",
                   "quantiles": "numpy.quantile(method='linear')"},
               "wall_s": time.time() - t0}
    write_json(out / "summary.json", summary, indent=1)
    print(json.dumps({k: summary[k] for k in ("contracts_total", "retained_selected", "analyzed", "validity_consistency",
                                              "phase_metrics_reproduced", "speed_case_counts", "wall_s")},
                     ensure_ascii=False, default=str)[:3000])
    return 0 if not errors else 3


if __name__ == "__main__":
    sys.exit(main())
