"""V8-15 第 6 部分汇总：压力骨架/检查点/余量三步 → summary.json、by_bucket.csv、三张图（只读外部输出）。
用法：make_part6.py <压力运行根 out/stress_v15> <本目录> <devset> <data_root> <cache>"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
PROJ = HERE.parents[4] / "Multi-UAV SimpleGC"
sys.path.insert(0, str(PROJ))
sys.path.insert(0, str(PROJ / "tools" / "v08"))
import matplotlib   # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

root, dst = Path(sys.argv[1]), Path(sys.argv[2])
devset, data_root, cache = sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5])


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8")) if Path(p).exists() else None


sel = load(root / "skeleton" / "stress_selection.json")
skel = load(root / "skeleton" / "run" / "records.json") or []
skel_sum = load(root / "skeleton" / "run" / "summary.json")
plan_cp = load(root / "checkpoint" / "checkpoint_plan.json")
rest_plan = load(root / "checkpoint" / "rest_plan.json")
cp = load(root / "checkpoint" / "run" / "records.json") or []
# 余量批次：首跑 rest/ 在 6/33 时按用户要求中断（无 records/summary），保留不动；重跑写入 rest_r2/。
REST = "rest_r2"
rest = load(root / REST / "run" / "records.json") or []
full = {r["contract_id"]: dict(r, phase="checkpoint") for r in cp}
full.update({r["contract_id"]: dict(r, phase="rest") for r in rest})


def _files(d):
    return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


interrupted = {"dir": "rest/run (首跑，6/33 时中断；未写 records/summary)", "contracts": []}
for d in sorted((root / "rest" / "run" / "contracts").glob("*")) if (root / "rest" / "run" / "contracts").exists() else []:
    r2 = root / REST / "run" / "contracts" / d.name
    a, b = _files(d), (_files(r2) if r2.exists() else None)
    interrupted["contracts"].append({
        "contract_id": d.name, "files": len(a), "in_rest_r2": b is not None,
        "file_sets_equal": b is not None and set(a) == set(b),
        "bytes_equal": b is not None and a == b,
        "differing": sorted(k for k in set(a) | set(b or {}) if (b is None) or a.get(k) != b.get(k))})
an = {}
for ph in ("checkpoint", "rest"):
    s = load(root / f"analysis_{ph}" / "summary.json")
    if s:
        an[ph] = s
pairs = []
for ph in ("checkpoint", "rest"):
    p = root / f"analysis_{ph}" / "pairs.csv"
    if p.exists():
        pairs += list(csv.DictReader(open(p, encoding="utf-8")))
by_c = defaultdict(dict)
for r in pairs:
    if r["bin_kind"] == "all":
        cur = by_c[r["contract_id"]].get(r["source"])
        v = float(r["min_m"])
        if cur is None or v < cur[0]:
            by_c[r["contract_id"]][r["source"]] = (v, r["pair"], float(r["t_s"]))

# ---- 分档
rows = []
skel_by = {r["contract_id"]: r for r in skel}
for c in sel["cases"]:
    cid = c["contract_id"]
    s = skel_by.get(cid, {})
    f = full.get(cid)
    real = ((f or {}).get("formation") or {}).get("realized") if f and f.get("success") else \
        (s.get("formation") or {}).get("realized") if s.get("success") else None
    topo = ((f or {}).get("topology") or {}).get("final") if f and f.get("success") else \
        (s.get("topology") or {}).get("final") if s.get("success") else None
    st = Counter(a["stage"] for a in (f or {}).get("attempt_log") or [] if not a.get("ok"))
    rows.append({"contract_id": cid, "order": c["order"], "prior": c["prior"], "seed": c["seed"],
                 "skeleton_success": s.get("success"), "skeleton_attempts": s.get("attempts"),
                 "skeleton_retreat_attempts": s.get("retreat_attempts"), "skeleton_wall_s": s.get("wall_s"),
                 "full_phase": (f or {}).get("phase"), "full_success": (f or {}).get("success"),
                 "full_attempts": (f or {}).get("attempts"), "full_wall_s": (f or {}).get("wall_s"),
                 "full_retreat_attempts": (f or {}).get("retreat_attempts"),
                 "realized": real, "topology": topo,
                 "retreat_contract": bool(real and real != (s.get("mapped_start") or (f or {}).get("mapped_start"))),
                 "final_failure": ((f or {}).get("failure") or {}).get("code") if f else None,
                 "failed_stages": dict(st),
                 "post_optimization_failures": (f or {}).get("post_optimization_failures"),
                 "measured_min_m": by_c.get(cid, {}).get("measured_sample", (None,))[0],
                 "measured_interp_min_m": by_c.get(cid, {}).get("measured_interp", (None,))[0],
                 "optimized_min_m": by_c.get(cid, {}).get("optimized_xy", (None,))[0],
                 "status": "full_run" if f else ("skipped_all_skeleton_failed"
                                                 if plan_cp and f"o{c['order']:02d}/{c['prior']}" in plan_cp["skipped_all_skeleton_failed"]
                                                 else ("dropped_by_budget" if rest_plan and cid in rest_plan.get("dropped", [])
                                                       else "not_run"))})
with open(dst / "contracts.csv", "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    for r in rows:
        w.writerow(r)
buckets = defaultdict(list)
for r in rows:
    buckets[(r["order"], r["prior"], r["realized"], r["topology"])].append(r)
with open(dst / "by_bucket.csv", "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["family_order", "prior", "realized", "topology", "contracts", "skeleton_success", "full_executed",
                "full_success", "skipped", "dropped", "attempts", "retreat_contracts", "retreat_attempts_full",
                "full_wall_s"])
    for k, rs in sorted(buckets.items(), key=lambda x: tuple(str(y) for y in x[0])):
        ex = [r for r in rs if r["full_success"] is not None]
        w.writerow([k[0], k[1], k[2], k[3], len(rs), sum(bool(r["skeleton_success"]) for r in rs), len(ex),
                    sum(bool(r["full_success"]) for r in ex),
                    sum(r["status"] == "skipped_all_skeleton_failed" for r in rs),
                    sum(r["status"] == "dropped_by_budget" for r in rs),
                    ";".join(str(r["full_attempts"]) for r in ex),
                    sum(r["retreat_contract"] for r in ex if r["full_success"]),
                    sum(int(r["full_retreat_attempts"] or 0) for r in ex),
                    ";".join(f"{r['full_wall_s']:.0f}" for r in ex if r["full_wall_s"] is not None)])

# ---- 图
from v08.runner.monitoring import load_entries   # noqa: E402
from v08.scene.context import load_context      # noqa: E402
import v15_artifacts as VA                       # noqa: E402
entries = {int(e["order"]): e for e in load_entries(devset)}
run_dir = {r["contract_id"]: root / ("checkpoint" if r["phase"] == "checkpoint" else REST) / "run" for r in full.values()}
ok = [r for r in rows if r["full_success"] and r["measured_min_m"] is not None]
figs = {}


def _outline(g):
    """圈层几何字典（v08.scene.exact：Circle / Polygon / BufferedPolygon）→ 绘图用 (xs, ys)；仅作图。"""
    if hasattr(g, "exterior"):
        return g.exterior.xy
    if not isinstance(g, dict):
        return None
    if g.get("type") == "Circle":
        th = np.linspace(0, 2 * np.pi, 361)
        c, r = g["center_m"], float(g["radius_m"])
        return c[0] + r * np.cos(th), c[1] + r * np.sin(th)
    if "vertices_m" in g:
        import shapely
        poly = shapely.Polygon(g["vertices_m"])
        b = float(g.get("buffer_m") or 0.0)
        return (poly.buffer(b, quad_segs=32) if b > 0 else poly).exterior.xy
    return None


def draw_layers(ax, ctx, target_id):
    for f in ctx.facilities:
        if f.id == target_id:
            for lay, col in (("warning", "#e9c46a"), ("alert", "#e76f51")):
                xy = _outline(f.layers.get(lay))
                if xy is not None:
                    ax.plot(*xy, color=col, lw=1, label=f"目标 {lay}")
        else:
            xy = _outline(f.layers.get("alert"))
            if xy is not None:
                ax.plot(*xy, color="#999999", lw=0.8, ls="--")


def draw_success(cid, path, title):
    r = full[cid]
    ctx = load_context(entries[r["order"]], data_root=data_root, cache_dir=cache)
    b = VA.load_retained(run_dir[cid] / "contracts" / cid, ctx)
    v, pair, t_s = by_c[cid]["measured_sample"]
    a, bb = pair.split("|")
    fig, ax = plt.subplots(figsize=(9, 9))
    draw_layers(ax, ctx, r["target_id"])
    for m, tr in sorted(b["tracks"].items()):
        p = np.asarray(tr.p)
        ax.plot(p[:, 0], p[:, 1], color="#bbbbbb", lw=0.5)
    for m in (a, bb):
        tr = b["tracks"][m]
        t = np.asarray(tr.tau_us) / 1e6
        masks = VA.member_phase_masks(b, m, tr.tau_us)
        p = np.asarray(tr.p)
        for name, col in (("collect_ingress", "#457b9d"), ("patrol", "#2a9d8f"), ("egress", "#8d99ae")):
            mk = masks[name]
            ax.plot(np.where(mk, p[:, 0], np.nan), np.where(mk, p[:, 1], np.nan), color=col, lw=1.2)
        mk = masks["turn"]
        ax.plot(np.where(mk, p[:, 0], np.nan), np.where(mk, p[:, 1], np.nan), color="#f4a261", lw=2.0)
        k = int(np.argmin(np.abs(t - t_s)))
        ax.plot(p[k, 0], p[k, 1], "kx", ms=10)
    ax.set_aspect("equal")
    ax.legend(fontsize=7, loc="best")
    ax.set_title(f"{title}\n{cid}：实际队形 {r['formation']['realized']}，拓扑 {r['topology']['final']}，"
                 f"保留 attempt {r['attempts'] - 1}；实测三维采样最小 {v:.3f} m（{pair}，t={t_s:.1f} s，×）\n"
                 "蓝=汇合/进入 绿=巡逻 灰蓝=撤离 橙=掉头（巡逻子区间）；其余成员浅灰", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


if ok:
    best = sorted(ok, key=lambda r: (-len(full[r["contract_id"]].get("member_ids") or []), r["measured_min_m"],
                                     r["order"], r["prior"], r["seed"]))[0]
    draw_success(best["contract_id"], dst / "fig_crowded_success.png", "最拥挤成功")
    figs["crowded_success"] = best["contract_id"]
else:
    figs["crowded_success"] = "无此类样例（成功 0）"
ret = [r for r in ok if r["retreat_contract"]]
if ret:
    bestr = sorted(ret, key=lambda r: (-len(full[r["contract_id"]].get("member_ids") or []), r["measured_min_m"],
                                       r["order"], r["prior"], r["seed"]))[0]
    draw_success(bestr["contract_id"], dst / "fig_retreat_success.png", "退让成功")
    figs["retreat_success"] = bestr["contract_id"]
else:
    figs["retreat_success"] = f"无此类样例（成功 {len(ok)} 个中实际队形≠mapped_start 的 0 个）"
fails = sorted([r for r in rows if r["full_success"] is False], key=lambda r: (r["order"], r["prior"], r["seed"]))
if fails:
    cid = fails[0]["contract_id"]
    fw = load(run_dir[cid] / "contracts" / cid / "failure_witness.json")
    res = load(run_dir[cid] / "contracts" / cid / "result.json")
    fig, ax = plt.subplots(figsize=(9, 9))
    last = res["attempt_log"][-1]
    # 场景与最后 attempt 的抽签几何（attempt_log 中已保存；无 failure_witness 时这是唯一可得的几何见证）
    fr = full[cid]
    ctx = load_context(entries[fr["order"]], data_root=data_root, cache_dir=cache)
    draw_layers(ax, ctx, fr["target_id"])
    for m, st in sorted(ctx.family.initial_states.items()):
        p0 = st.get("position_enu_m") or st.get("position") or st.get("p")
        if p0 is not None:
            ax.plot(p0[0], p0[1], "o", color="#264653", ms=4)
            ax.annotate(m, (p0[0], p0[1]), fontsize=6)
    drw = last.get("draw") or {}
    if drw.get("center_xy") and drw.get("rho0_m"):
        cx, cy = drw["center_xy"]
        th = np.linspace(0, 2 * np.pi, 361)
        ax.plot(cx + drw["rho0_m"] * np.cos(th), cy + drw["rho0_m"] * np.sin(th), color="#2a9d8f", lw=1.2,
                label=f"最后 attempt 抽签圆 ρ0={drw['rho0_m']:.0f} m")
        ax.plot(cx, cy, "+", color="#2a9d8f", ms=10)
    ax.legend(fontsize=7, loc="best")
    stage_cnt = Counter(f"{a['stage']}/{a.get('skeleton_stage') or a.get('reason')}" for a in res["attempt_log"]
                        if not a.get("ok"))
    if fw:
        for m, xy in fw.get("skeleton_members", {}).items():
            xy = np.asarray(xy)
            ax.plot(xy[:, 0], xy[:, 1], color="#bbbbbb", lw=0.6)
        for m, xy in (fw.get("tracks_p") or {}).items():
            xy = np.asarray(xy)
            ax.plot(xy[:, 0], xy[:, 1], lw=0.8)
    ax.set_aspect("equal")
    ax.set_title(f"失败样例 {cid}：最后 attempt {last['attempt']} stage={last['stage']} reason={last.get('reason')}\n"
                 f"最终分类 {(res.get('failure') or {}).get('code')}；"
                 f"见证：{'骨架曲线（灰）' if fw else '无 failure_witness（最后 attempt 骨架未成功）'}"
                 f"{'+实测轨迹' if fw and fw.get('tracks_p') else ''}；"
                 f"物理失败 {fw.get('physical_failures') if fw else None}；validity {fw.get('validity_codes') if fw else None}\n"
                 f"20 次失败阶段：{'；'.join(f'{k}×{v}' for k, v in stage_cnt.most_common())}\n"
                 f"图示：目标 warning/alert 层、其他设施 alert（灰虚线）、全员初始位置、最后 attempt 抽签圆（{drw.get('formation')}，"
                 f"{drw.get('topology')}，K={drw.get('K')}）",
                 fontsize=7)
    fig.tight_layout()
    fig.savefig(dst / "fig_failure.png", dpi=110)
    plt.close(fig)
    figs["failure"] = cid
else:
    figs["failure"] = "无此类样例（完整链路失败 0）"

dist = {}
for s in ("optimized_xy", "measured_sample", "measured_interp"):
    v = [float(r["min_m"]) for r in pairs if r["source"] == s and r["bin_kind"] == "all"]
    w5 = sorted([r for r in pairs if r["source"] == s and r["bin_kind"] == "all"],
                key=lambda r: (float(r["min_m"]), r["contract_id"], r["pair"], float(r["t_s"])))[:5]
    q = np.quantile(v, [0, .1, .5, .9, 1], method="linear").tolist() if v else None
    dist[s] = {"n_pairs": len(v), "quantiles_min_p10_med_p90_max": q,
               "worst5": [{k: r[k] for k in ("contract_id", "pair", "min_m", "t_s", "formation", "topology")}
                          for r in w5]}
summary = {"selection": {k: sel[k] for k in ("rule", "ranking", "chosen")}, "cases": len(sel["cases"]),
           "skeleton_summary": skel_sum, "checkpoint_plan": plan_cp, "rest_plan": rest_plan,
           "full_executed": len(full), "full_success": sum(bool(r.get("success")) for r in full.values()),
           "skeleton_success": sum(bool(r.get("success")) for r in skel), "distances": dist,
           "analysis": {ph: {k: s.get(k) for k in ("analyzed", "errors", "validity_consistency", "empty_pairs",
                                                  "failed_attempts", "speed_case_counts")} for ph, s in an.items()},
           "figures": figs, "rest_dir": REST, "interrupted_first_rest": interrupted,
           "rest_summary": load(root / REST / "run" / "summary.json"),
           "statuses": dict(Counter(r["status"] for r in rows)),
           "retreat_contracts_success": sum(r["retreat_contract"] for r in ok),
           "retreat_attempts_full": sum(int(r["full_retreat_attempts"] or 0) for r in rows if r["full_success"] is not None),
           "retreat_attempts_skeleton": sum(int(r["skeleton_retreat_attempts"] or 0) for r in rows)}
(dst / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
print(json.dumps({k: summary[k] for k in ("full_executed", "full_success", "skeleton_success", "statuses", "figures",
                                          "retreat_contracts_success")}, ensure_ascii=False))
