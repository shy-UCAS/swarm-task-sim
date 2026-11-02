"""V8-08 第 5 部分：旧软件在环数据只读盘点（为 V8-09 标定 a_lat、a_lon 做准备，不下标定结论）。

只读：遍历只用 os.walk 与 os.stat，抽样只打开文件读取；不在根目录下写入、移动、重命名任何东西。
名称以 v07_ 开头的目录一律跳过（不读取任何 v0.7 数据）。
读取前后对每个被读文件记录 (size, mtime, ctime, atime)，写进结果供核对。

用法（在 Multi-UAV SimpleGC 目录下）:
    python -B scripts/v08/v8_08_sitl_inventory.py --roots <根1> <根2> --max-samples 20
"""
import argparse
import csv
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
PROJECT = HERE.parents[2]
REPO = PROJECT.parent
OUT_DIR = REPO / "docs" / "v08" / "V8-08"

NAMED = ("truth.csv", "observations.csv", "manifest.json", "scenario.json", "metadata.json",
         "firmware_parameters.json")
PATTERN_EXTS = (".parm", ".BIN", ".bin")
MAX_EXAMPLES = 20
PARAM_PREFIXES = ("WPNAV_", "PSC_", "ATC_ACCEL", "ANGLE_MAX", "LOIT_", "GUID_")
UP_LEVELS = 3
DOWNSAMPLE_S = 0.1
DOWNSAMPLE_TOL_S = 1e-6
MOVING_M_S = 1.0
TURN_RATE_RAD_S = 0.05
KEY_DEPTH = 3


# ---------------------------------------------------------------- 只读辅助

class ReadLog:
    """记录每个被读文件读取前的 stat；结束时再 stat 一次比较。"""

    def __init__(self):
        self.before = {}

    def open(self, path, **kw):
        path = Path(path)
        if str(path) not in self.before:
            self.before[str(path)] = _stamp(path)
        return path.open("r", **kw)

    def report(self):
        rows = []
        for p, b in sorted(self.before.items()):
            a = _stamp(Path(p))
            rows.append(dict(path=p, before=b, after=a,
                             content_meta_changed=any(a[k] != b[k] for k in ("size", "mtime_ns", "ctime_ns")),
                             atime_changed=a["atime_ns"] != b["atime_ns"]))
        return rows


def _stamp(path):
    st = os.stat(path)
    return dict(size=st.st_size, mtime_ns=st.st_mtime_ns, ctime_ns=st.st_ctime_ns, atime_ns=st.st_atime_ns)


def _skip_dir(name):
    return name.startswith("v07_")


# ---------------------------------------------------------------- 1. 目录概况

def walk_root(root):
    root = Path(root)
    res = dict(root=str(root), exists=root.is_dir())
    if not res["exists"]:
        return res, {}
    total = files = 0
    ext = Counter()
    top = defaultdict(lambda: [0, 0])
    named = {n: [] for n in NAMED + tuple("*" + e for e in PATTERN_EXTS)}
    dir_files = {}
    skipped, errors = [], []
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: errors.append(str(e))):
        keep = []
        for d in dirnames:
            if _skip_dir(d):
                skipped.append(os.path.relpath(os.path.join(dirpath, d), root))
            else:
                keep.append(d)
        dirnames[:] = sorted(keep)
        rel_dir = os.path.relpath(dirpath, root)
        first = rel_dir.split(os.sep)[0] if rel_dir != "." else "."
        dir_files[rel_dir] = filenames
        for f in filenames:
            try:
                size = os.stat(os.path.join(dirpath, f)).st_size
            except OSError as exc:
                errors.append(str(exc))
                continue
            total += size
            files += 1
            ext[os.path.splitext(f)[1] or "(无)"] += 1
            top[first][0] += size
            top[first][1] += 1
            rel = os.path.normpath(os.path.join(rel_dir, f))
            if f in NAMED:
                named[f].append(rel)
            e = os.path.splitext(f)[1]
            if e in PATTERN_EXTS:
                named["*" + e].append(rel)
    res.update(total_bytes=total, total_gb=total / 1e9, file_count=files,
               ext_counts=dict(ext.most_common()),
               top_level={k: dict(bytes=v[0], gb=v[0] / 1e9, files=v[1]) for k, v in sorted(top.items())},
               named_files={k: dict(count=len(v), examples=sorted(v)[:MAX_EXAMPLES]) for k, v in named.items()},
               skipped_v07_dirs=skipped, walk_errors=errors[:50], walk_error_count=len(errors))
    return res, dict(dir_files=dir_files, truth=sorted(named["truth.csv"]))


# ---------------------------------------------------------------- 2. 来源分类

def _ancestors(rel_dir):
    out, d = [], rel_dir
    for _ in range(UP_LEVELS + 1):
        out.append(d)
        if d in (".", ""):
            break
        d = os.path.dirname(d) or "."
    return out


def classify(index):
    sitl, other, evidence = [], [], {}
    for rel in index["truth"]:
        hit = None
        for d in _ancestors(os.path.dirname(rel) or "."):
            names = index["dir_files"].get(d, [])
            if "firmware_parameters.json" in names:
                hit = (d, "firmware_parameters.json")
                break
            if any(n.endswith(".BIN") for n in names):
                hit = (d, "*.BIN")
                break
        (sitl if hit else other).append(rel)
        evidence[rel] = hit
    return sitl, other, evidence


def _find_up(index, rel_file, name):
    for d in _ancestors(os.path.dirname(rel_file) or "."):
        if name in index["dir_files"].get(d, []):
            return os.path.normpath(os.path.join(d, name))
    return None


# ---------------------------------------------------------------- 3. 抽样读取

def read_truth(path, log):
    with log.open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        cols = list(reader.fieldnames or [])
        rows = list(reader)
    by = defaultdict(list)
    for r in rows:
        by[r.get("agent_id")].append(r)
    return cols, len(rows), by


def _valid(r):
    return str(r.get("valid", "")).strip().lower() in ("1", "true", "1.0")


def _pct(x, qs):
    x = np.asarray(x, dtype=float)
    if not len(x):
        return {f"p{q}": None for q in qs} | dict(max=None, n=0)
    return {f"p{q}": float(np.percentile(x, q)) for q in qs} | dict(max=float(x.max()), n=int(len(x)))


def motion_stats(rows):
    pts = []
    for r in rows:
        if not _valid(r):
            continue
        try:
            pts.append((float(r["t_s"]), float(r["east_m"]), float(r["north_m"])))
        except (KeyError, ValueError):
            continue
    pts.sort()
    kept, last = [], None
    for t, x, y in pts:
        if last is None or t >= last + DOWNSAMPLE_S - DOWNSAMPLE_TOL_S:
            kept.append((t, x, y))
            last = t
    if len(kept) < 5:
        return dict(frames_downsampled=len(kept), note="有效帧不足 5，跳过")
    a = np.asarray(kept)
    t, p = a[:, 0], a[:, 1:]
    v = (p[2:] - p[:-2]) / (t[2:] - t[:-2])[:, None]            # 位于 t[1:-1]
    tv = t[1:-1]
    acc = (v[2:] - v[:-2]) / (tv[2:] - tv[:-2])[:, None]         # 位于 t[2:-2]
    vm = v[1:-1]
    speed = np.hypot(vm[:, 0], vm[:, 1])
    mv = speed > MOVING_M_S
    a_lat = np.abs(vm[mv, 0] * acc[mv, 1] - vm[mv, 1] * acc[mv, 0]) / speed[mv]
    a_lon = np.abs(np.sum(vm[mv] * acc[mv], axis=1) / speed[mv])
    turn = a_lat / speed[mv] > TURN_RATE_RAD_S
    sp_m = speed[mv]
    return dict(frames_downsampled=int(len(kept)), frames_moving=int(mv.sum()),
                a_lat=_pct(a_lat, (50, 95, 99)), a_lon_abs=_pct(a_lon, (50, 95, 99)),
                speed_all=_pct(speed, (50, 95)), speed_moving=_pct(sp_m, (50, 95)),
                turn_frames=int(turn.sum()),
                speed_median_turn=float(np.median(sp_m[turn])) if turn.any() else None,
                speed_median_other=float(np.median(sp_m[~turn])) if (~turn).any() else None)


def sample_truth(path, log):
    cols, n, by = read_truth(path, log)
    agents = {}
    for aid, rows in sorted(by.items(), key=lambda kv: str(kv[0])):
        ts = sorted(float(r["t_s"]) for r in rows if r.get("t_s") not in (None, ""))
        dt = np.diff(ts)
        agents[str(aid)] = dict(rows=len(rows), duration_s=(ts[-1] - ts[0]) if ts else None,
                                dt_median_s=float(np.median(dt)) if len(dt) else None,
                                valid_fraction=sum(_valid(r) for r in rows) / len(rows) if rows else None,
                                motion=motion_stats(rows))
    return dict(columns=cols, rows=n, agent_count=len(by), agents=agents)


def key_structure(obj, depth=0):
    if isinstance(obj, dict):
        if depth >= KEY_DEPTH:
            return f"dict[{len(obj)}]"
        return {str(k): key_structure(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        inner = key_structure(obj[0], depth + 1) if obj and isinstance(obj[0], (dict, list)) and depth < KEY_DEPTH \
            else (type(obj[0]).__name__ if obj else None)
        return dict(list_len=len(obj), item=inner)
    return type(obj).__name__


def read_json(path, log):
    with log.open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- 5. 飞控参数

def _flatten_params(doc):
    """firmware_parameters.json 为 {agent: {all_parameters: {...}, ...}}；其他形状按扁平字典处理。"""
    out = {}
    if isinstance(doc, dict) and doc and all(isinstance(v, dict) for v in doc.values()):
        for agent, item in doc.items():
            src = item.get("all_parameters") if isinstance(item.get("all_parameters"), dict) else item
            out[str(agent)] = {k: v for k, v in src.items() if k.startswith(PARAM_PREFIXES)}
    elif isinstance(doc, dict):
        out["(flat)"] = {k: v for k, v in doc.items() if k.startswith(PARAM_PREFIXES)}
    return out


def repo_parm(path):
    rows = {}
    if not path.is_file():
        return dict(path=str(path), exists=False)
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith(PARAM_PREFIXES):
            parts = s.replace(",", " ").split()
            rows[parts[0]] = parts[1] if len(parts) > 1 else None
    return dict(path=str(path), exists=True, params=rows)


# ---------------------------------------------------------------- 主程序

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="+", required=True)
    ap.add_argument("--max-samples", type=int, default=20)
    args = ap.parse_args()
    roots = [Path(r).resolve() for r in args.roots]
    for r in roots:
        if OUT_DIR.resolve().is_relative_to(r):
            sys.exit(f"输出目录 {OUT_DIR} 位于根 {r} 之下，拒绝运行")
    started = time.perf_counter()
    log = ReadLog()
    result = dict(schema="v8-08-sitl-inventory-v1", roots=[], classification={}, samples=[], params={})
    all_sitl = []
    indices = {}
    for r in roots:
        info, index = walk_root(r)
        result["roots"].append(info)
        if not info["exists"]:
            continue
        indices[str(r)] = index
        sitl, other, ev = classify(index)
        result["classification"][str(r)] = dict(
            truth_total=len(index["truth"]), sitl=len(sitl), other=len(other),
            sitl_examples=sitl[:MAX_EXAMPLES], other_examples=other[:MAX_EXAMPLES],
            evidence_kinds=dict(Counter(e[1] for e in ev.values() if e)))
        all_sitl += [(str(r), rel) for rel in sitl]
    walk_s = time.perf_counter() - started
    all_sitl.sort(key=lambda x: os.path.join(*x))
    n = len(all_sitl)
    k = max(1, n // 20)
    picks = all_sitl[::k][:args.max_samples]
    param_sets = []
    for i, (root, rel) in enumerate(picks):
        index = indices[root]
        full = Path(root) / rel
        entry = dict(index=i, root=root, truth=rel)
        try:
            entry.update(sample_truth(full, log))
        except Exception as exc:                                       # 个别文件读不了：记下继续
            entry["error"] = f"{type(exc).__name__}: {exc}"
        if i < 2:
            for name in ("manifest.json", "scenario.json"):
                found = _find_up(index, rel, name)
                entry[name] = dict(path=found)
                if found:
                    try:
                        entry[name]["keys"] = key_structure(read_json(Path(root) / found, log))
                    except Exception as exc:
                        entry[name]["error"] = f"{type(exc).__name__}: {exc}"
            fp = _find_up(index, rel, "firmware_parameters.json")
            entry["firmware_parameters"] = fp
            if fp:
                try:
                    param_sets.append((rel, _flatten_params(read_json(Path(root) / fp, log))))
                except Exception as exc:
                    entry["firmware_parameters_error"] = f"{type(exc).__name__}: {exc}"
        result["samples"].append(entry)
    # 参数：前 2 个样本内各机、跨样本不一致的项
    merged = defaultdict(dict)
    for rel, per_agent in param_sets:
        for agent, kv in per_agent.items():
            for key, val in kv.items():
                merged[key][f"{rel}::{agent}"] = val
    result["params"] = dict(
        from_samples=[dict(truth=rel, agents={a: dict(sorted(kv.items())) for a, kv in pa.items()})
                      for rel, pa in param_sets],
        inconsistent={k: v for k, v in sorted(merged.items()) if len({json.dumps(x) for x in v.values()}) > 1},
        repo_copter_parm=repo_parm(PROJECT / "ArducopterSITL" / "copter.parm"))
    pooled = defaultdict(list)
    for s in result["samples"]:
        for ag in s.get("agents", {}).values():
            if "dt_median_s" in ag and ag["dt_median_s"] is not None:
                pooled["dt_median_s"].append(ag["dt_median_s"])
            if ag.get("valid_fraction") is not None:
                pooled["valid_fraction"].append(ag["valid_fraction"])
    result["sample_summary"] = dict(sitl_truth_total=n, stride=k, sampled=len(picks),
                                    agents=len(pooled["valid_fraction"]),
                                    dt_median_s=_pct(pooled["dt_median_s"], (5, 50, 95)),
                                    valid_fraction=_pct(pooled["valid_fraction"], (5, 50, 95)))
    reads = log.report()
    result["read_only_check"] = dict(files_read=len(reads),
                                     content_meta_changed=sum(r["content_meta_changed"] for r in reads),
                                     atime_changed=sum(r["atime_changed"] for r in reads), files=reads)
    result["timing"] = dict(walk_s=walk_s, total_s=time.perf_counter() - started)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "sitl_inventory.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写出 {out}；软件在环 truth.csv {n} 个，抽样 {len(picks)}；读文件 {len(reads)}，"
          f"内容元数据变化 {result['read_only_check']['content_meta_changed']}，"
          f"atime 变化 {result['read_only_check']['atime_changed']}；用时 {result['timing']['total_s']:.1f} s")


if __name__ == "__main__":
    main()
