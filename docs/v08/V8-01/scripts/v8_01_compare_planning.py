"""V8-01 §5.1：比较重跑的 planning_result.json / candidate_pool.pkl 与原记录（只读）。

去掉随运行变化的字段后逐键比较，列出前 20 处差异。
用法: python -B v8_01_compare_planning.py <run_id> <skeleton_id> <rerun_run_dir> <输出json>
"""
import json
import math
import pickle
import sys
from pathlib import Path

sys.dont_write_bytecode = True
PROJECT = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-prod-r3\Multi-UAV SimpleGC")
sys.path.insert(0, str(PROJECT))  # 反序列化候选池需要冻结代码中的类定义（只读导入）
FE_ROOT = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_first_edition")

# 随运行变化的键：墙钟耗时；候选池 pickle 内含墙钟，因此其 sha256 也随运行变化
VOLATILE = {"planning_wall_s", "wall_s", "geometry_wall_s", "candidate_pool_sha256"}


def strip(obj, removed, path=""):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in VOLATILE or (isinstance(k, str) and k.endswith("_wall_s")):
                removed.add(f"{path}.{k}" if path else k)
                continue
            out[k] = strip(v, removed, f"{path}.{k}" if path else str(k))
        return out
    if isinstance(obj, (list, tuple)):
        return [strip(v, removed, f"{path}[]") for v in obj]
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        return {"__class__": type(obj).__name__, **strip(vars(obj), removed, path)}
    if hasattr(obj, "tolist"):
        return obj.tolist()
    return obj


def diff(a, b, path, out, limit=20):
    if len(out) >= limit:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append({"path": f"{path}.{k}", "original": a.get(k, "<missing>"), "rerun": b.get(k, "<missing>")})
            else:
                diff(a[k], b[k], f"{path}.{k}", out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append({"path": path, "original_len": len(a), "rerun_len": len(b)})
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out, limit)
    else:
        same = a == b or (isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b))
        if not same:
            out.append({"path": path, "original": a, "rerun": b})


def count_diff(a, b):
    out = []
    diff(a, b, "", out, limit=10 ** 9)
    return len(out)


def main():
    run_id, sid, rerun, dst = sys.argv[1:5]
    rerun = Path(rerun)
    orig_dir = FE_ROOT / run_id / "planning" / sid
    new_dir = rerun / "planning" / sid
    result = {"original": f"v07_first_edition/{run_id}/planning/{sid}", "rerun": str(new_dir)}
    removed = set()
    a = strip(json.load(open(orig_dir / "planning_result.json", encoding="utf-8")), removed)
    b = strip(json.load(open(new_dir / "planning_result.json", encoding="utf-8")), removed)
    d = []
    diff(a, b, "planning_result", d)
    result["planning_result"] = {"identical_after_strip": not d, "removed_keys": sorted(removed),
                                 "difference_count": count_diff(a, b), "first_20_differences": d}
    removed = set()
    with open(orig_dir / "candidate_pool.pkl", "rb") as f:
        pa = strip(pickle.load(f), removed)
    with open(new_dir / "candidate_pool.pkl", "rb") as f:
        pb = strip(pickle.load(f), removed)
    d = []
    diff(pa, pb, "candidate_pool", d)
    result["candidate_pool_pkl"] = {"identical_after_strip": not d, "removed_keys": sorted(removed),
                                    "difference_count": count_diff(pa, pb), "first_20_differences": d}
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1, default=str)
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != "first_20_differences"})
                      for k, v in result.items()}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
