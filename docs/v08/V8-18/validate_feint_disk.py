"""V8-18 保存后只读核验：独立按磁盘帧重算冻结核验与两层1/1，不运行生成器。"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08")
sys.path.insert(0, str(REPO / "Multi-UAV SimpleGC"))
from collect_lazy_evidence import read, scan


def main():
    from v08.criteria.segment import SegmentTask, verify_segments
    from v08.criteria.validity import check_validity, visible_track
    from v08.scene.context import load_context
    from v08.scene.exact import signed_distance
    from v08.sim.types import MemberTrack
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--stage", choices=("quick", "full"), required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--include-diversity", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    manifest = read(REPO / "docs/v08/V8-18/manifest.json")
    devset = read(manifest["devset"]["path"])
    entries = {e["family_id"]: e for e in (devset["families"] if isinstance(devset, dict) else devset)}
    contexts, results, payload, missing, p0 = {}, [], [], [], []
    expected = set(manifest["keys"]["quick20"] if args.stage == "quick" else manifest["keys"]["full200"])
    primary = read(root / "records.json")
    if {r["contract_id"] for r in primary} != expected or len(primary) != len(expected):
        missing.append("主批名单或计数不一致")
    sources = [(root, r) for r in primary]
    if args.include_diversity:
        diversity = read(root / "diversity/records.json")
        if len(diversity) != 100 or {r["contract_id"] for r in diversity} != set(manifest["keys"]["diversity100"]):
            missing.append("多样性不是100个唯一合同")
        sources += [(root / "diversity", r) for r in diversity]
    for parent, row in sources:
        cid = row["contract_id"]
        folder = parent / "contracts" / cid
        info = {"contract_id": cid, "scope": "diversity" if parent != root else args.stage,
                "success": row["success"], "members": {}, "violations": []}
        try:
            saved = read(folder / "result.json")
            for file in folder.rglob("*.json"):
                payload.extend({"file": str(file), "location": at} for at in scan(read(file)))
            if saved["success"] != row["success"]:
                info["violations"].append("records/result成功状态不一致")
                p0.append(cid)
                results.append(info)
                break
            if not row["success"]:
                results.append(info)
                continue
            if not row["member_ids"] or len(row["member_ids"]) != row["group_size"]:
                info["violations"].append("保留成员集合为空或人数不一致")
                p0.append(cid)
                results.append(info)
                break
            fid = row["family_id"]
            if fid not in contexts:
                contexts[fid] = load_context(entries[fid], data_root=Path(manifest["data_root"]),
                                             cache_dir=Path(manifest["run_root"]["cache"]))
            ctx = contexts[fid]
            target = ctx.facility_by_id[row["target_id"]]
            tracks = {}
            for mid in row["member_ids"]:
                arrays = {key: np.load(folder / "tracks" / mid / (key + ".npy"), allow_pickle=False)
                          for key in ("tau_us", "p", "v", "a", "segment_index")}
                failures = []
                if not np.issubdtype(arrays["tau_us"].dtype, np.integer) or not np.all(np.diff(arrays["tau_us"]) == 100_000):
                    failures.append("时间网格不是10Hz整数微秒")
                if not np.all(arrays["segment_index"] == 0):
                    failures.append("单段编号不为0")
                if not all(np.isfinite(arrays[k]).all() for k in ("p", "v", "a")):
                    failures.append("物理数组非有限")
                track = MemberTrack(mid, arrays["tau_us"], arrays["p"], arrays["v"], arrays["a"], arrays["segment_index"], ())
                tracks[mid] = track
                mask = (track.tau_us >= saved["release_us"][mid]) & (track.segment_index == 0)
                if not mask.any():
                    failures.append("释放后窗口为空")
                    info["members"][mid] = {"violations": failures}
                    continue
                times, xy = track.tau_us[mask], track.p[mask, :2]
                distance = np.asarray(signed_distance(target.geometry, xy))
                if distance[0] <= target.offsets["warning"]:
                    failures.append("实测释放后首帧已在warning内")
                serialized = saved["feint"]["members"][mid]
                events = {}
                for layer in ("warning", "alert"):
                    inside = distance <= target.offsets[layer]
                    starts = np.flatnonzero(inside & ~np.r_[False, inside[:-1]])
                    ends = np.flatnonzero(~inside & np.r_[False, inside[:-1]])
                    events[layer] = {"entries": len(starts), "exits": len(ends)}
                    if (len(starts), len(ends)) != (1, 1):
                        failures.append(layer + "进入/退出不是1/1")
                    elif (serialized["entry_counts"][layer] != 1
                          or serialized["first_entry_us"][layer] != int(times[starts[0]])
                          or serialized["first_exit_us"][layer] != int(times[ends[0]])):
                        failures.append(layer + "保存事件与NPY不一致")
                minimum = float(np.min(signed_distance(target.layers["protected"], xy)))
                if minimum != serialized["min_protected_sdf_m"]:
                    failures.append("最深protected距离保存不一致")
                if not np.all(distance > target.offsets["protected"]):
                    failures.append("实测进入protected")
                if not all(float(signed_distance(f.geometry, xy[-1])) > f.offsets["warning"] for f in ctx.facilities):
                    failures.append("末帧仍在某warning内")
                info["members"][mid] = {"events": events, "min_protected_sdf_m": minimum, "violations": failures}
            verdicts = verify_segments(ctx.scene, tracks, saved["release_us"], [SegmentTask(0, "feint", target.id)])
            validity = check_validity(ctx.scene, [visible_track(tracks[m], saved["release_us"][m]) for m in sorted(tracks)])
            if not all(v.passed for v in verdicts):
                info["violations"].append("冻结段核验失败")
            if not validity.passed:
                info["violations"].append("冻结有效性核验失败")
            if validity.min_separation_m is not None and validity.min_separation_m < 2.0:
                info["violations"].append("实测间距小于2m")
            if not saved["retained_p0_ok"]:
                info["violations"].append("保存的retained_p0_ok为False")
            info["min_separation_m"] = validity.min_separation_m
            info["segment_passed"] = all(v.passed for v in verdicts)
            info["validity_passed"] = validity.passed
            if info["violations"] or any(m["violations"] for m in info["members"].values()):
                p0.append(cid)
        except Exception as exc:
            missing.append({"contract_id": cid, "error": repr(exc)})
        results.append(info)
        if p0:
            break
    output = {"stage": args.stage, "expected_primary": len(expected), "primary_records": len(primary),
              "checked": len(results), "retained": sum(r["success"] for r in results),
              "p0_contracts": p0, "incomplete": missing, "payload_violations": payload, "results": results}
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in output.items() if k != "results"}, ensure_ascii=False))
    return 4 if p0 else 3 if missing or payload else 0


if __name__ == "__main__":
    sys.exit(main())
