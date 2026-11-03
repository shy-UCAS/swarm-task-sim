"""V8-12 第 4 部分的三张示意图：一个绕圈成功合同、一个折返成功合同、一个失败合同的最后一次 attempt。

读取第 4 部分输出目录（--plan-dir）里的 contracts/*.json 与 NPZ，场景几何从登记清单重新读入（只读）。
选择规则是确定性的，不按结果好坏挑选：成功合同取 order 最小且拓扑为 loop / retrace 的第一个；
失败合同取 order 最小的第一个失败合同。matplotlib 只在这里使用。

用法（在 Multi-UAV SimpleGC 目录下）:
    python -B scripts/v08/v8_12_figures.py --plan-dir <第4部分输出> --data-root <SwarmData> --cache <缓存> --out-dir <图目录>
"""
import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT))


def circle_xy(c, r, n=360):
    a = np.linspace(0, 2 * np.pi, n)
    return c[0] + r * np.cos(a), c[1] + r * np.sin(a)


def geometry_xy(g):
    if g["type"] == "Circle":
        return circle_xy(g["center_m"], g["radius_m"])
    v = np.asarray(g["vertices_m"], float)
    from v08.scene.exact import expand, signed_distance
    b = float(g.get("buffer_m", 0.0))
    if b <= 0.0:
        v = np.vstack([v, v[:1]])
        return v[:, 0], v[:, 1]
    # 缓冲多边形：取 sdf=0 的轮廓（画图用，网格取点）
    x0, y0, x1, y1 = v[:, 0].min() - b - 5, v[:, 1].min() - b - 5, v[:, 0].max() + b + 5, v[:, 1].max() + b + 5
    xs, ys = np.meshgrid(np.linspace(x0, x1, 400), np.linspace(y0, y1, 400))
    z = signed_distance(g, np.stack([xs, ys], axis=-1))
    import matplotlib.pyplot as plt
    cs = plt.contour(xs, ys, z, levels=[0.0])
    seg = cs.allsegs[0][0]
    plt.close()
    return seg[:, 0], seg[:, 1]


def draw(ax, ctx, rec, arrays, title):
    for f in ctx.facilities:
        for layer, style in (("protected", ":"), ("alert", "--"), ("warning", "-")):
            x, y = geometry_xy(f.layers[layer])
            ax.plot(x, y, style, lw=0.8, color="tab:red" if f.id == rec["target_id"] else "tab:gray")
        ax.text(f.center[0], f.center[1], f.id.replace("facility_", "F"), ha="center", va="center", fontsize=7)
    wv = np.asarray(ctx.world["vertices_m"], float)
    wv = np.vstack([wv, wv[:1]])
    ax.plot(wv[:, 0], wv[:, 1], "k-", lw=0.8)
    for oid, g in ctx.obstacles:
        x, y = geometry_xy(g)
        ax.fill(x, y, color="0.8", zorder=0)
    if arrays is not None:
        for k, v in arrays.items():
            if k.startswith("member."):
                ax.plot(v[:, 0], v[:, 1], lw=0.7, alpha=0.8)
        ref = arrays["reference_xy"]
        ax.plot(ref[:, 0], ref[:, 1], "k-", lw=1.4, label="reference")
        ax.plot(*ref[0], "go", ms=5)
        ax.plot(*ref[-1], "rs", ms=5)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=9)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-dir", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from v08.runner import monitoring as run
    from v08.scene.context import load_context

    entries = {e["family_id"]: e for e in run.load_entries(run.REPO_ROOT / "docs" / "v08" / "V8-03" / "devset_v08.json")}
    recs = [json.loads(Path(f).read_text(encoding="utf-8")) for f in sorted(glob.glob(args.plan_dir + "/contracts/*.json"))]
    recs.sort(key=lambda r: (r["order"], r["draw_index"]))
    picks = []
    for kind in ("loop", "retrace"):
        r = next((r for r in recs if r.get("success") and r["metrics"]["topology"] == kind), None)
        picks.append((f"success_{kind}", r))
    picks.append(("failure", next((r for r in recs if not r.get("success") and "error" not in r), None)))
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, r in picks:
        if r is None:
            print(f"{name}: 没有可画的合同")
            continue
        ctx = load_context(entries[r["family_id"]], data_root=args.data_root, cache_dir=args.cache)
        arrays = None
        npz = Path(args.plan_dir) / "contracts" / (r["contract_id"] + ".npz")
        if npz.exists():
            with np.load(npz) as z:
                arrays = {k: z[k] for k in z.files}
        fig, ax = plt.subplots(figsize=(8, 8))
        if arrays is not None:
            title = (f"{r['contract_id']}  n={r['group_size']}  {r['metrics']['topology']}  {r['metrics']['formation_realized']}  "
                     f"{r['plan']['nominal_duration_s']:.0f}s  attempts={r['attempts']}")
        else:
            last = r["attempt_log"][-1]
            title = (f"{r['contract_id']}  n={r['group_size']}  {r['failure']['code']}  last stage={last['stage']}  "
                     f"attempts={r['attempts']}")
        draw(ax, ctx, r, arrays, title)
        fig.savefig(out / f"{name}.png", dpi=110, bbox_inches="tight")
        plt.close(fig)
        print(f"{name}: {r['contract_id']} -> {out / (name + '.png')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
