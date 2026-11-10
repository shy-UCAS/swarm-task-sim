"""V8-22 进场诊断（只读）：每个保留合同的目标预警进入次数、首次入圈时间跨度、入圈前是否已经过集合点、
最早释放到首次入圈的时长、首个成员入圈时成员到编组中心的平均距离。

用法：python -B docs/v08/V8-22/entry_diag_v22.py --repo "<…\\Multi-UAV SimpleGC>" --devset <devset_v08.json>
          --data-root <SwarmData> --run <运行根（含 contracts\\）> --label <名字> --out <新 json 文件>
"""
import argparse, json, os, sys
from pathlib import Path
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import numpy as np


def contract_row(cdir, scene, sd_fn):
    con = json.loads((cdir / "contract.json").read_text(encoding="utf-8"))
    res = json.loads((cdir / "result.json").read_text(encoding="utf-8"))
    if not res.get("success") or not (cdir / "skeleton.json").exists():
        return None
    sk = json.loads((cdir / "skeleton.json").read_text(encoding="utf-8"))
    C = (sk.get("proposal") or {}).get("collection_xy")
    W = next(e["geometry"] for e in scene["entities"] if e.get("type") == "protection_zone"
             and e.get("facility_id") == con["target_id"] and e.get("layer") == "warning")
    ent, fe, rel, before, pos = {}, {}, {}, 0, {}
    for m in sorted(con["member_ids"]):
        tau = np.load(cdir / "tracks" / m / "tau_us.npy")
        p = np.load(cdir / "tracks" / m / "p.npy")
        k = tau >= int(res["release_us"][m])
        t, xy = tau[k] / 1e6, np.asarray(p, float)[k, :2]
        ins = np.asarray(sd_fn(W, xy), float) <= 0.0
        ent[m] = int(np.sum(np.diff(ins.astype(np.int8)) == 1) + int(ins[0]))
        i0 = int(np.argmax(ins)) if ins.any() else None
        fe[m] = float(t[i0]) if i0 is not None else None
        rel[m] = float(t[0])
        pos[m] = (t, xy)
        if C is not None and i0 is not None:
            ic = int(np.argmin(np.hypot(*(xy - np.asarray(C, float)).T)))
            before += int(i0 < ic)
    f = [v for v in fe.values() if v is not None]
    t_first = min(f) if f else None
    cen_d = None
    if t_first is not None:
        pts = []
        for m, (t, xy) in pos.items():
            j = int(np.argmin(np.abs(t - t_first)))
            if abs(t[j] - t_first) < 0.051:
                pts.append(xy[j])
        if len(pts) > 1:
            P = np.asarray(pts)
            cen_d = float(np.mean(np.hypot(*(P - P.mean(0)).T)))
    return {"contract": cdir.name, "n": len(ent), "entries": ent, "all_single": all(v == 1 for v in ent.values()),
            "first_entry_spread_s": (max(f) - min(f)) if f else None, "entered_before_collection": before,
            "release_to_first_entry_s": (t_first - min(rel.values())) if t_first is not None else None,
            "mean_dist_to_centroid_at_first_entry_m": cen_d}


def main():
    ap = argparse.ArgumentParser()
    for k in ("repo", "devset", "data-root", "run", "label", "out"):
        ap.add_argument("--" + k, required=True)
    a = ap.parse_args()
    sys.path.insert(0, a.repo)
    from v08.scene.exact import signed_distance
    if Path(a.out).exists():
        print("输出已存在，拒绝覆盖"); return 1
    dev = {e["family_id"]: e for e in json.loads(Path(a.devset).read_text(encoding="utf-8"))}
    rows, scenes = [], {}
    for c in sorted(p for p in (Path(a.run) / "contracts").iterdir() if p.is_dir()):
        fam = json.loads((c / "contract.json").read_text(encoding="utf-8"))["family_id"]
        if fam not in scenes:
            rel = dev[fam]["directory_rel"].split("/")
            scenes[fam] = json.loads((Path(a.data_root).joinpath(*rel) / "public_scene.json").read_text(encoding="utf-8"))
        r = contract_row(c, scenes[fam], signed_distance)
        if r is not None:
            rows.append(r)
    def q(key):
        v = [r[key] for r in rows if r[key] is not None]
        return {"n": len(v), "P50": float(np.median(v)) if v else None, "P90": float(np.percentile(v, 90)) if v else None,
                "max": float(max(v)) if v else None}
    summary = {"label": a.label, "run": a.run, "contracts": len(rows),
               "contracts_with_any_member_entries_ne_1": sum(not r["all_single"] for r in rows),
               "members_entries_ne_1": sum(sum(v != 1 for v in r["entries"].values()) for r in rows),
               "contracts_with_entry_before_collection": sum(r["entered_before_collection"] > 0 for r in rows),
               "first_entry_spread_s": q("first_entry_spread_s"), "release_to_first_entry_s": q("release_to_first_entry_s"),
               "mean_dist_to_centroid_at_first_entry_m": q("mean_dist_to_centroid_at_first_entry_m")}
    Path(a.out).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
