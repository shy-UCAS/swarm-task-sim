"""V8-14c 门禁 3（真实数据）：用快速批次（643eebc，out/quick）20 个合同已保存的优化解，用批量版 run_tracking_group
重新仿真；每个成员的 stitch 后数组（tau_us、p、v、a、segment_index）须与已保存 tracks/<m>/*.npy 逐字节相同，
段核验与有效性检查结论相同。只读 out/quick；结果写到 --out（JSON）。任何不一致 → 退出码 4（P0），不切换运行器。

用法（Multi-UAV SimpleGC 目录，conda llm）：
    python -B <本文件> --quick <out/quick> --devset <devset_v08.json> --data-root <SwarmData> --cache <缓存> --out <结果.json>
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path.cwd()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", required=True)
    ap.add_argument("--devset", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    from v08.contract.monitoring import initial_states, monitoring_mission
    from v08.criteria.segment import SegmentTask, verify_segments
    from v08.criteria.validity import check_validity, visible_track
    from v08.motion.optimize import SplineTrajectory
    from v08.runner.monitoring import load_entries
    from v08.sampler.common import sample_common
    from v08.scene.context import load_context
    from v08.sim.stitch import stitch
    from v08.sim.tracking import TimeReference
    from v08.sim.tracking_batch import LAST_GROUP_STATS, run_tracking_group

    quick = Path(a.quick)
    recs = json.loads((quick / "records.json").read_text(encoding="utf-8"))
    by_fid = {e["family_id"]: e for e in load_entries(a.devset)}
    ctx_cache = {}
    rows, all_ok = [], True
    for r in sorted(recs, key=lambda x: x["contract_id"]):
        cid = r["contract_id"]
        cdir = quick / "contracts" / cid
        row = {"contract_id": cid, "success": r["success"]}
        if not r["success"]:
            row["note"] = "失败合同无保留轨迹"
            rows.append(row)
            continue
        fid = r["family_id"]
        if fid not in ctx_cache:
            ctx_cache.clear()
            ctx_cache[fid] = load_context(by_fid[fid], data_root=Path(a.data_root), cache_dir=Path(a.cache))
        ctx = ctx_cache[fid]
        mission = monitoring_mission(ctx, sample_common(ctx.family, int(r["draw_index"])))
        group, task = mission.groups[0], mission.tasks[0]
        states = initial_states(ctx.family, group.member_ids)
        opt = json.loads((cdir / "optimized.json").read_text(encoding="utf-8"))["members"]
        members = sorted(opt)
        refs = []
        for m in members:
            o = opt[m]
            tr = SplineTrajectory(m, o["release_s"], o["end_s"], o["altitude_m"], np.asarray(o["knots"], float),
                                  np.asarray(o["controls"], float))
            refs.append(TimeReference(tr.member_id, float(tr.release_s), float(tr.end_s), float(tr.altitude_m), tr.pva))
        t0 = time.perf_counter()
        results = run_tracking_group(refs, [states[m] for m in members], final=True)
        sim_s = time.perf_counter() - t0
        row.update(members=len(members), batch_sim_s=sim_s, reference_mode=LAST_GROUP_STATS.get("reference_mode"),
                   precompute_s=LAST_GROUP_STATS.get("precompute_s"), loop_s=LAST_GROUP_STATS.get("loop_s"),
                   statuses=[x.status for x in results])
        tracks = stitch(results)
        diffs = []
        for m in members:
            for name in ("tau_us", "p", "v", "a", "segment_index"):
                saved = np.load(cdir / "tracks" / m / f"{name}.npy", allow_pickle=False)
                new = np.ascontiguousarray(getattr(tracks[m], name))
                if not (saved.dtype == new.dtype and saved.shape == new.shape and saved.tobytes() == new.tobytes()):
                    diffs.append(f"{m}/{name}")
        release = {m: int(x.pieces[0].release_us) for m, x in zip(members, results)}
        saved_release = {k: int(v) for k, v in (r.get("release_us") or {}).items()}
        verdicts = verify_segments(ctx.scene, tracks, release, [SegmentTask(0, "monitoring", task.target_id)])
        valid = check_validity(ctx.scene, [visible_track(tracks[m], release[m]) for m in sorted(tracks)])
        res_doc = json.loads((cdir / "result.json").read_text(encoding="utf-8"))
        last = res_doc["attempt_log"][-1]
        same_verdict = (all(v.passed for v in verdicts) is True) and last.get("stage") == "verified"
        same_valid = bool(valid.passed) is True
        row.update(array_bytes_equal=not diffs, differing=diffs, release_equal=release == saved_release,
                   segment_passed=[bool(v.passed) for v in verdicts], validity_passed=bool(valid.passed),
                   validity_codes=list(valid.codes), conclusions_equal=bool(same_verdict and same_valid))
        ok = (not diffs) and row["release_equal"] and row["conclusions_equal"]
        row["ok"] = ok
        all_ok = all_ok and ok
        rows.append(row)
        print(f"{cid}: bytes_equal={not diffs} release_equal={row['release_equal']} conclusions_equal="
              f"{row['conclusions_equal']} sim={sim_s:.1f}s mode={row['reference_mode']}", flush=True)
    doc = {"gate": "V8-14c 4.3", "quick_dir": str(quick.resolve()), "all_ok": all_ok, "rows": rows}
    Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("ALL_OK" if all_ok else "MISMATCH")
    return 0 if all_ok else 4


if __name__ == "__main__":
    sys.exit(main())
