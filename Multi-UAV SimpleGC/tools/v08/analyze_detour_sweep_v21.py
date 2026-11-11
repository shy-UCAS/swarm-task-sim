"""[V8-21 第 7.4 节复制扩展：原脚本 sweep_stats_v21.py SHA256 6695939ff75038bc9e0da1f4c43885530116f418aa2dcb6fad55c4ddc843ce5f；
只追加 detour 意图、单段核对、--candidate-config 选中口径与未舍入余量报告，原六意图口径不变。]

V8-21 第 0 步：六意图单段全量数据中"偶然扫角"的只读统计（规划审查方编写，2026-11-10）。

用途：给迂回候选判据定 Θ（扫角下限）和 D_near（近距离带宽度），并完成互斥条件复核（V8-02 r4 9.2 两条新增条件）。
只读：不改仓库、不改任何运行目录、不重跑生成；输出只写 --out 指定的新目录。

口径（与 V8-21 上层要求一致）：
- 帧：成员释放之后的全部 10 Hz 实测帧（tau_us >= release_us[成员]，同 v08.criteria.validity.visible_track）。
- 近距离带（设施 F、宽度 D）：到 F 预警边界的有符号距离 d 满足 0 < d <= D（预警圈外、距边界不超过 D）。
  距离用 v08.scene.exact.signed_distance 的精确几何。
- 段内区间：近距离带内连续帧组成的最长区间（帧号连续）。
- 扫角（主口径 span）：区间内相对 F 中心（v08.scene.exact.center_of_geometry(设施几何)，与判据窗口
  的 center_of 一致）的方位角展开（np.unwrap）后的 max − min，单位度。另报净变化 net = |末 − 首|。
- 成员级：每个（成员, 设施）取所有区间 span 的最大值。
- 编组级（迂回判据的同口径，"每个成员都存在"）：G_all = min_成员(成员级)；另报 G_any = max_成员(成员级)。
- 合同级（一个段）：S_all = max_设施 G_all；S_any = max_设施 G_any。
- D 的两种口径：固定值 D ∈ FIXED_D；按预警圈等效半径归一化 D = α·R_eq，R_eq = sqrt(预警区面积/π)。

用法（在任意目录，conda llm，单线程）：
  python -B sweep_stats_v21.py --selftest --repo "<…\\Multi-UAV SimpleGC>"
  python -B sweep_stats_v21.py --repo <…> --devset <devset_v08.json> --data-root <SwarmData>
      --run monitoring=<目录> --run transit=<目录> … --out <不存在的新目录> [--limit N] [--workers K]
--run 的目录是含 contracts\\ 子目录的运行根（交接文档第 2 节表格中的全量目录）。--limit N 只取每个意图按合同号排序
的前 N 个合同（快速检查用）。
"""
import argparse
import csv
import json
import math
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import numpy as np

FIXED_D = (25.0, 50.0, 75.0, 100.0, 150.0, 200.0, 300.0, 400.0)
ALPHAS = (0.025, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40)
THETAS = (45, 60, 90, 120, 150, 180, 240, 300)
PCTS = (50, 90, 95, 99, 99.5, 100)
INTENTS = ("monitoring", "transit", "intrusion", "feint", "close_observation", "area_search", "detour")
SELECTED = {}   # --candidate-config：{"name": 选项名, "D": 米, "theta": 度, "upper": 度}


def options_for(r_eq):
    out = [(f"D{int(d)}", d) for d in FIXED_D]
    out += [(f"a{a:.3f}", a * r_eq) for a in ALPHAS]
    if SELECTED and not any(name == SELECTED["name"] for name, _ in out):
        out.append((SELECTED["name"], SELECTED["D"]))
    return out


def runs_of(mask):
    """mask 中连续 True 的 [起, 止) 区间。"""
    m = np.asarray(mask, bool)
    if not m.any():
        return []
    d = np.diff(np.r_[0, m.astype(np.int8), 0])
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def best_run(sd, phi_unwrapped_full, D):
    """返回 (span_deg, net_deg, i0, i1)；无区间返回 None。phi 已在整条可见轨迹上展开（区间内展开等价）。"""
    best = None
    for a, b in runs_of((sd > 0.0) & (sd <= D)):
        if b - a < 2:
            continue
        seg = phi_unwrapped_full[a:b]
        span = math.degrees(float(seg.max() - seg.min()))
        if best is None or span > best[0]:
            best = (span, math.degrees(abs(float(seg[-1] - seg[0]))), int(a), int(b))
    return best


def facilities_of(scene):
    from v08.scene.exact import center_of_geometry
    fac, warn = {}, {}
    for e in scene["entities"]:
        if e["type"] == "facility":
            fac[e["id"]] = e["geometry"]
        elif e["type"] == "protection_zone" and e.get("layer") == "warning":
            warn[e["facility_id"]] = e["geometry"]
    out = []
    for fid in sorted(fac):
        w = warn[fid]
        out.append({"id": fid, "warning": w, "center": np.asarray(center_of_geometry(fac[fid]), float),
                    "r_eq": warning_req(w)})
    return out


def warning_req(g):
    """预警区等效半径 sqrt(面积/π)。BufferedPolygon 面积 = 多边形面积 + 周长·b + π b²（凸多边形的 Minkowski 和）。"""
    if g["type"] == "Circle":
        return float(g["radius_m"])
    v = np.asarray(g["vertices_m"], float)
    x, y = v[:, 0], v[:, 1]
    area = 0.5 * abs(float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)))
    per = float(np.sum(np.hypot(*(np.roll(v, -1, 0) - v).T)))
    b = float(g.get("buffer_m", 0.0)) if g["type"] == "BufferedPolygon" else 0.0
    return math.sqrt((area + per * b + math.pi * b * b) / math.pi)


def member_rows(xy, facs, target_id):
    """一名成员对各设施、各口径的成员级最大扫角。xy: (T,2) 可见帧。"""
    from v08.scene.exact import signed_distance
    rows = []
    for f in facs:
        sd = np.asarray(signed_distance(f["warning"], xy), float)
        rel = xy - f["center"][None, :]
        phi = np.unwrap(np.arctan2(rel[:, 1], rel[:, 0]))
        role = "target" if f["id"] == target_id else "other"
        if role == "target":
            inside = np.flatnonzero(sd <= 0.0)
            i_in, i_out = (int(inside[0]), int(inside[-1])) if len(inside) else (None, None)
        for name, D in options_for(f["r_eq"]):
            br = best_run(sd, phi, D)
            row = {"facility": f["id"], "role": role, "option": name, "D_m": round(D, 3), "r_eq_m": round(f["r_eq"], 3)}
            all_spans = [math.degrees(float(phi[a_:b_].max() - phi[a_:b_].min()))
                         for a_, b_ in runs_of((sd > 0.0) & (sd <= D))]
            row["span_raw_deg"] = 0.0 if br is None else br[0]
            row["max_any_run_raw_deg"] = max(all_spans) if all_spans else 0.0
            if br is None:
                row.update(span_deg=0.0, net_deg=0.0, run_s=0.0, phase="none")
            else:
                span, net, a, b = br
                if role == "other":
                    phase = "other"
                elif i_in is None:
                    phase = "never_entered"
                elif b <= i_in:
                    phase = "approach"
                elif a > i_out:
                    phase = "departure"
                else:
                    phase = "between"
                row.update(span_deg=round(span, 4), net_deg=round(net, 4), run_s=round((b - a) / 10.0, 1),
                           phase=phase, run_start_frame=a, run_end_frame=b)
            rows.append(row)
    return rows


def process_contract(args):
    intent, cdir, scene_path = args
    cdir = Path(cdir)
    res = json.loads((cdir / "result.json").read_text(encoding="utf-8"))
    con = json.loads((cdir / "contract.json").read_text(encoding="utf-8"))
    for doc in (res, con):
        if "intent" in doc and doc["intent"] != intent:
            raise RuntimeError(f"{cdir}: 文件中的 intent={doc['intent']!r} 与 --run 标签 {intent!r} 不符（目录对应错误，停止）")
    dwell = dwell_rejections(res)
    if not res.get("success"):
        return {"contract": cdir.name, "intent": intent, "success": False, "rows": [], "dwell": dwell,
                "attempts": res.get("attempts")}
    scene = json.loads(Path(scene_path).read_text(encoding="utf-8"))
    facs = facilities_of(scene)
    rows = []
    for m in sorted(con["member_ids"]):
        td = cdir / "tracks" / m
        tau = np.load(td / "tau_us.npy")
        p = np.load(td / "p.npy")
        keep = tau >= int(res["release_us"][m])
        seg = np.load(td / "segment_index.npy")
        if not np.all(seg[keep] == 0):
            raise RuntimeError(f"{cdir}: 释放后帧含非 0 段（单段统计不静默处理）")
        xy = np.asarray(p, float)[keep, :2]
        for r in member_rows(xy, facs, con["target_id"]):
            r.update(member=m)
            rows.append(r)
    return {"contract": cdir.name, "intent": intent, "success": True, "group_size": len(con["member_ids"]),
            "facility_count": len(facs), "target": con["target_id"], "rows": rows, "dwell": dwell,
            "attempts": res.get("attempts")}


def dwell_rejections(res):
    """互斥复核第 1 条：attempt_log 中因驻留被拒的尝试（序列化文本含 no_dwell 的失败条目），按阶段计数。"""
    out = {}
    for a in res.get("attempt_log") or []:
        if a.get("ok") or a.get("stage") == "accepted":
            continue
        s = json.dumps(a, ensure_ascii=False)
        if "no_dwell" in s:
            form = ((a.get("draw") or {}).get("formation")) if isinstance(a.get("draw"), dict) else None
            k = f"{a.get('stage')}|{form}"
            out[k] = out.get(k, 0) + 1
    return out


def pct(vals, q):
    return float(np.percentile(np.asarray(vals, float), q)) if len(vals) else None


def summarize(results):
    ok = [r for r in results if r["success"]]
    opts = sorted({row["option"] for r in ok for row in r["rows"]}, key=lambda s: (s[0], float(s[1:])))
    contract_level = {o: [] for o in opts}          # (intent, S_all, S_any, 最坏设施, 角色, 阶段, 合同)
    group_level = {o: [] for o in opts}
    for r in ok:
        by = {}
        for row in r["rows"]:
            by.setdefault((row["option"], row["facility"]), []).append(row)
        for o in opts:
            best_all = (-1.0, None)
            best_any = (-1.0, None)
            for (oo, fid), rs in by.items():
                if oo != o:
                    continue
                g_all = min(x["span_deg"] for x in rs)
                worst = max(rs, key=lambda x: x["span_deg"])
                g_any = worst["span_deg"]
                group_level[o].append({"intent": r["intent"], "contract": r["contract"], "facility": fid,
                                       "role": rs[0]["role"], "G_all": g_all, "G_any": g_any, "phase_any": worst["phase"]})
                if g_all > best_all[0]:
                    best_all = (g_all, fid)
                if g_any > best_any[0]:
                    best_any = (g_any, (fid, worst["role"], worst["phase"], worst["member"]))
            contract_level[o].append({"intent": r["intent"], "contract": r["contract"], "group_size": r["group_size"],
                                      "facility_count": r["facility_count"], "S_all": best_all[0],
                                      "S_all_facility": best_all[1], "S_any": best_any[0],
                                      "S_any_where": best_any[1]})
    summary = {"contracts_success": len(ok), "contracts_total": len(results), "options": {}}
    for o in opts:
        cl = contract_level[o]
        entry = {}
        for metric in ("S_all", "S_any"):
            vals = [c[metric] for c in cl]
            entry[metric] = {"pooled": {f"P{q}": pct(vals, q) for q in PCTS},
                             "share_ge_theta": {str(t): float(np.mean(np.asarray(vals) >= t)) for t in THETAS},
                             "by_intent": {i: {"n": sum(c["intent"] == i for c in cl),
                                               "P99": pct([c[metric] for c in cl if c["intent"] == i], 99),
                                               "max": pct([c[metric] for c in cl if c["intent"] == i], 100)}
                                           for i in INTENTS if any(c["intent"] == i for c in cl)}}
        gl = group_level[o]
        entry["group_level_by_role"] = {
            role: {"n": sum(g["role"] == role for g in gl),
                   "visited_share": float(np.mean([g["G_any"] > 0 for g in gl if g["role"] == role])) if any(g["role"] == role for g in gl) else None,
                   "G_all": {f"P{q}": pct([g["G_all"] for g in gl if g["role"] == role], q) for q in PCTS},
                   "G_any": {f"P{q}": pct([g["G_any"] for g in gl if g["role"] == role], q) for q in PCTS},
                   "phase_of_worst_member": dict(sorted({ph: sum(1 for g in gl if g["role"] == role and g["phase_any"] == ph)
                                                         for ph in {g["phase_any"] for g in gl}}.items()))}
            for role in ("target", "other")}
        # 固定 D 与归一化 D 的比较：目标设施的编组级扫角按预警圈等效半径分三档（直线切过时扫角上界 2·arccos(R/(R+D))
        # 随 R 变小而增大；归一化口径应使三档接近）
        req = {}
        for r in ok:
            for row in r["rows"]:
                if row["option"] == o and row["role"] == "target":
                    req[(r["contract"], r["intent"])] = row["r_eq_m"]
        bins = {"R<900": (0, 900), "900<=R<1100": (900, 1100), "R>=1100": (1100, 1e9)}
        tg = [g for g in gl if g["role"] == "target"]
        entry["target_G_all_by_Req"] = {
            k: {"n": len(v), "P95": pct(v, 95), "P99": pct(v, 99), "max": pct(v, 100)}
            for k, (a_, b_) in bins.items()
            for v in [[g["G_all"] for g in tg if a_ <= req.get((g["contract"], g["intent"]), -1) < b_]]}
        entry["top20_S_any"] = sorted(cl, key=lambda c: -c["S_any"])[:20]
        entry["top20_S_all"] = sorted(cl, key=lambda c: -c["S_all"])[:20]
        summary["options"][o] = entry
    dw = {}
    for r in results:
        for stage, n in (r["dwell"] or {}).items():
            dw.setdefault(r["intent"], {}).setdefault(stage, 0)
            dw[r["intent"]][stage] += n
    summary["dwell_rejections_by_intent_stage_formation"] = dw
    summary["dwell_rejected_contracts_by_intent"] = {i: sum(1 for r in results if r["intent"] == i and r["dwell"])
                                                     for i in INTENTS if any(r["intent"] == i for r in results)}
    if SELECTED:
        summary["selected_candidate"] = dict(SELECTED)
        summary["detour_extension"] = detour_extension(ok)
    summary["attempts_by_intent"] = {i: {"contracts": sum(r["intent"] == i for r in results),
                                         "success": sum(r["intent"] == i and r["success"] for r in results),
                                         "attempts_total": sum((r["attempts"] or 0) for r in results if r["intent"] == i)}
                                     for i in INTENTS if any(r["intent"] == i for r in results)}
    return summary, contract_level


def detour_extension(ok):
    """第 7.4 节：选中口径下六意图合并 S_all 与迂回目标编组扫角的分布、间隔与重叠；未舍入值算余量。"""
    o, theta, upper = SELECTED["name"], SELECTED["theta"], SELECTED["upper"]
    six, det, others = [], [], []
    for r in ok:
        by = {}
        for row in r["rows"]:
            if row["option"] == o:
                by.setdefault(row["facility"], []).append(row)
        g_all = {f: min(x["span_raw_deg"] for x in rs) for f, rs in by.items()}
        if r["intent"] == "detour":
            tgt = r["target"]
            members = by[tgt]
            det.append({"contract": r["contract"], "target_G_all_deg": g_all[tgt],
                        "lower_margin_deg": g_all[tgt] - theta,
                        "upper_margin_deg": upper - max(x["max_any_run_raw_deg"] for x in members),
                        "member_min_deg": min(x["span_raw_deg"] for x in members),
                        "other_G_f_deg": {f: v for f, v in g_all.items() if f != tgt}})
            others.extend(v for f, v in g_all.items() if f != tgt)
        else:
            six.append({"intent": r["intent"], "contract": r["contract"], "S_all_deg": max(g_all.values()) if g_all else 0.0})
    sv = [x["S_all_deg"] for x in six]
    dv = [x["target_G_all_deg"] for x in det]
    q = lambda v: {f"P{p}": pct(v, p) for p in (0, 1, 5, 10, 50, 90, 95, 99, 100)}   # noqa: E731
    return {"option": o, "theta_deg": theta, "six_intent_S_all": q(sv), "six_by_intent": {
                i: q([x["S_all_deg"] for x in six if x["intent"] == i]) for i in INTENTS if i != "detour"},
            "detour_target_G_all": q(dv), "detour_member_min": q([x["member_min_deg"] for x in det]),
            "detour_other_G_f": q(others),
            "gap_detour_min_minus_six_max_deg": (min(dv) - max(sv)) if dv and sv else None,
            "gap_detour_P1_minus_six_P99_deg": (pct(dv, 1) - pct(sv, 99)) if dv and sv else None,
            "six_contracts_ge_detour_min": sum(x >= min(dv) for x in sv) if dv else None,
            "detour_contracts_le_six_max": sum(x <= max(sv) for x in dv) if sv else None,
            "six_contracts_ge_theta": sum(x >= theta for x in sv),
            "detour_lower_margin_min_deg": min((x["lower_margin_deg"] for x in det), default=None),
            "detour_upper_margin_min_deg": min((x["upper_margin_deg"] for x in det), default=None),
            "detour_rows": det}


def selftest():
    """合成用例：圆形设施（预警半径 1000 m）。① 带内圆弧 150° → span ≈ 150；② 距边界 10 m 的切向直线，
    D = 200 时 span ≈ 2·arccos(1010/1200)·… 的解析值；③ 穿入预警圈的直线在带内被切成两段，各段 span 小。"""
    from v08.scene.exact import signed_distance  # noqa: F401（确认可导入）
    fac = [{"id": "F", "warning": {"type": "Circle", "center_m": [0.0, 0.0], "radius_m": 1000.0},
            "center": np.zeros(2), "r_eq": 1000.0}]
    th = np.radians(np.linspace(10, 160, 1501))
    arc = 1100.0 * np.c_[np.cos(th), np.sin(th)]
    r1 = {x["option"]: x for x in member_rows(arc, fac, "F")}
    assert abs(r1["D200"]["span_deg"] - 150.0) < 0.05, r1["D200"]
    assert r1["D50"]["span_deg"] == 0.0
    y = 1010.0
    xs = np.arange(-2000.0, 2000.0, 0.5)
    line = np.c_[xs, np.full_like(xs, y)]
    r2 = {x["option"]: x for x in member_rows(line, fac, "F")}
    expect = 2 * math.degrees(math.acos(y / 1200.0))
    assert abs(r2["D200"]["span_deg"] - expect) < 0.2, (r2["D200"], expect)
    line2 = np.c_[xs, np.full_like(xs, 500.0)]
    r3 = {x["option"]: x for x in member_rows(line2, fac, "F")}
    lo = math.degrees(math.atan2(500, math.sqrt(1000**2 - 500**2)) - math.atan2(500, math.sqrt(1200**2 - 500**2)))
    assert abs(r3["D200"]["span_deg"] - abs(lo)) < 0.2, (r3["D200"], lo)
    print("selftest ok: arc150 ->", r1["D200"]["span_deg"], "; tangent line ->", r2["D200"]["span_deg"],
          f"(analytic {expect:.3f}); crossing line ->", r3["D200"]["span_deg"], f"(analytic {abs(lo):.3f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--devset")
    ap.add_argument("--data-root")
    ap.add_argument("--run", action="append", default=[])
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--candidate-config", help="V8-21 选中候选配置；D 不在原表时仅追加一个明确命名的选项")
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.repo)))
    if a.candidate_config:
        cfg = json.loads(Path(a.candidate_config).read_text(encoding="utf-8"))["parameters"]
        D = float(cfg["near_band_width_m"]["value"])
        name = next((f"D{int(d)}" for d in FIXED_D if d == D), f"selected_D{D:g}")
        SELECTED.update(name=name, D=D, theta=float(cfg["min_sweep_deg"]["value"]),
                        upper=float(cfg["max_sweep_deg_exclusive"]["value"]),
                        config_sha256=__import__("hashlib").sha256(Path(a.candidate_config).read_bytes()).hexdigest())
    if a.selftest:
        selftest()
        return 0
    out = Path(a.out)
    if out.exists():
        print("输出目录已存在，拒绝覆盖：", out)
        return 1
    dev = {e["family_id"]: e for e in json.loads(Path(a.devset).read_text(encoding="utf-8"))}
    import hashlib
    sha_ok = {}
    tasks = []
    for spec in a.run:
        intent, d = spec.split("=", 1)
        if intent not in INTENTS:
            print("未知意图：", intent)
            return 1
        cdirs = sorted(p for p in (Path(d) / "contracts").iterdir() if p.is_dir())
        if a.limit:
            cdirs = cdirs[:a.limit]
        for c in cdirs:
            fam = json.loads((c / "contract.json").read_text(encoding="utf-8"))["family_id"]
            rel = dev[fam]["directory_rel"].split("/")
            sp = Path(a.data_root).joinpath(*rel) / "public_scene.json"
            if fam not in sha_ok:
                sha_ok[fam] = hashlib.sha256(sp.read_bytes()).hexdigest() == dev[fam]["public_scene_sha256"]
                if not sha_ok[fam]:
                    print("public_scene.json 的 SHA256 与登记表不符，停止：", sp)
                    return 4
            tasks.append((intent, str(c), str(sp)))
    counts = {}
    for t in tasks:
        counts[t[0]] = counts.get(t[0], 0) + 1
    print("合同目录数：", counts, "；场景 SHA256 核对通过：", len(sha_ok), "族")
    t0 = time.perf_counter()
    if a.workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(a.workers) as ex:
            results = list(ex.map(process_contract, tasks, chunksize=4))
    else:
        results = [process_contract(t) for t in tasks]
    el = time.perf_counter() - t0
    out.mkdir(parents=True)
    with open(out / "member_level.csv", "w", newline="", encoding="utf-8") as fh:
        cols = ["intent", "contract", "member", "facility", "role", "option", "D_m", "r_eq_m", "span_deg", "net_deg",
                "run_s", "phase", "run_start_frame", "run_end_frame"]
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in results:
            for row in r["rows"]:
                w.writerow({"intent": r["intent"], "contract": r["contract"], **row})
    summary, cl = summarize(results)
    summary["elapsed_s"] = round(el, 1)
    summary["workers"] = a.workers
    summary["limit"] = a.limit
    with open(out / "contract_level.json", "w", encoding="utf-8") as fh:
        json.dump(cl, fh, ensure_ascii=False, indent=1)
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print(f"完成：{len(results)} 个合同（成功 {summary['contracts_success']}），用时 {el:.1f} s，输出 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
