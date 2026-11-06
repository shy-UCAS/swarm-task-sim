"""V8-16 指令 8.3：重访检测向量化候选的三方逐位对照与计时（本项新增；只读诊断）。

  --mode v811：在进程内临时包装 v08.criteria.window.revisit（只改运行时引用，不改文件；finally 恢复），每次拿到冻结窗口器
      的完整实参，同时调用冻结 task_v07.detectors.revisit、nominal_checks 原实现（oracle）、新候选，记录全部字段的
      浮点原始 64 位是否相等，返回冻结结果让原 V8-11 full 回归照常比较。
  --mode quick20：对监视快批 20 合同（full_v14c 保留目录）实际优化后名义窗口（check_monitoring 同一 10 Hz 网格、含末端保持）
      以 work_mask 与全窗口两种 frames 直接调用 oracle 与候选逐位对照。
计时：同一输入集合上顺序运行原/新（输入读取与比对不计时），报告总耗时与每例比值；不设无来源的最低提速百分比。
用法：python -B tools/v08/revisit_equivalence_v16.py --mode v811 --data-root <SwarmData> --out <新目录>
      python -B tools/v08/revisit_equivalence_v16.py --mode quick20 --baseline <full_v14c> --devset ... --data-root ...
          --cache ... --keys <manifest.json> --out <新目录>
"""
import argparse
import importlib.util
import json
import math
import struct
import sys
import time
from pathlib import Path

import numpy as np

PROJ = Path(__file__).resolve().parents[2]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))


def bits(value):
    if isinstance(value, dict):
        return tuple((k, bits(value[k])) for k in sorted(value))
    if isinstance(value, (list, tuple)):
        return tuple(bits(x) for x in value)
    if isinstance(value, (float, np.floating)):
        return ("f64", struct.pack(">d", float(value)))
    if isinstance(value, (bool, np.bool_)):
        return ("bool", bool(value))
    if isinstance(value, (int, np.integer)):
        return ("int", int(value))
    return value


class Tally:
    def __init__(self):
        self.calls = self.positive = self.empty = self.max_len = 0
        self.diff_frozen_orig = self.diff_orig_cand = 0
        self.first_diff = None
        self.t_orig = self.t_cand = 0.0
        self.ratios = []

    def add(self, args, frozen, orig, cand, t_o, t_c, tag):
        self.calls += 1
        self.positive += bool(orig["detected"])
        self.empty += int(len(args[0]) == 0)
        self.max_len = max(self.max_len, len(args[0]))
        self.t_orig += t_o
        self.t_cand += t_c
        if t_o > 0:
            self.ratios.append(t_c / t_o)
        if frozen is not None and bits(frozen) != bits(orig):
            self.diff_frozen_orig += 1
            self.first_diff = self.first_diff or {"tag": tag, "kind": "frozen_vs_orig", "frozen": frozen, "orig": orig}
        if bits(orig) != bits(cand):
            self.diff_orig_cand += 1
            self.first_diff = self.first_diff or {"tag": tag, "kind": "orig_vs_candidate", "orig": orig, "cand": cand}

    def doc(self):
        r = sorted(self.ratios)
        pick = lambda p: r[min(len(r) - 1, int(round(p * (len(r) - 1))))] if r else None   # noqa: E731
        return {"calls": self.calls, "positive": self.positive, "empty_inputs": self.empty, "max_len": self.max_len,
                "diff_frozen_vs_orig": self.diff_frozen_orig, "diff_orig_vs_candidate": self.diff_orig_cand,
                "first_diff": self.first_diff, "orig_total_s": self.t_orig, "candidate_total_s": self.t_cand,
                "total_ratio": (self.t_cand / self.t_orig) if self.t_orig else None,
                "per_call_ratio": {"p10": pick(.1), "median": pick(.5), "p90": pick(.9)}}


def _timed(fn, args):
    t0 = time.perf_counter()
    out = fn(*args)
    return out, time.perf_counter() - t0


def mode_v811(args):
    import v08.criteria.window as W
    from task_v07.detectors import revisit as frozen
    from v08.motion import nominal_checks as NC
    orig = NC.__dict__.get("_revisit_original", NC.revisit)
    cand = NC._revisit_vectorized
    tally = Tally()
    real = W.revisit

    def wrapper(*a):
        f = frozen(*a)
        o, t_o = _timed(orig, a)
        c, t_c = _timed(cand, a)
        tally.add(a, f, o, c, t_o, t_c, "v811")
        return f
    spec = importlib.util.spec_from_file_location("v8_11_regress", PROJ / "scripts" / "v08" / "v8_11_regress.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    W.revisit = wrapper
    try:
        code = mod.main(["--data-root", args.data_root, "--stage", "full", "--out", str(Path(args.out) / "regress")])
    finally:
        W.revisit = real
    reg = json.loads((Path(args.out) / "regress" / "regress_full.json").read_text(encoding="utf-8"))
    return {"mode": "v811", "regress_exit": code, "regress": {k: reg.get(k) for k in (
        "samples", "verified", "mismatch_count", "data_unchanged", "list_ok", "wall_s")}, "tally": tally.doc()}


def _quick20(args):
    sys.path.insert(0, str(PROJ / "tools" / "v08"))
    import v15_artifacts as VA
    from task_v07.criteria import load_criteria
    from v08.motion import nominal_checks as NC
    from v08.motion.optimize import load_settings, physical_limits
    from v08.runner.monitoring import load_entries
    from v08.scene.context import load_context
    orig = NC.__dict__.get("_revisit_original", NC.revisit)
    cand = NC._revisit_vectorized
    cfg = load_criteria()
    lim = physical_limits(load_settings())
    keys = json.loads(Path(args.keys).read_text(encoding="utf-8"))["keys"]["quick20"]
    entries = {int(e["order"]): e for e in load_entries(args.devset)}
    tw, tf = Tally(), Tally()
    for cid in keys:
        o = int(cid[1:3])
        ctx = load_context(entries[o], data_root=Path(args.data_root), cache_dir=Path(args.cache))
        b = VA.load_retained(Path(args.baseline) / "contracts" / cid, ctx)
        tgt = b["plan"].witnesses["target_id"]
        fac = ctx.facility_by_id[tgt]
        center = np.asarray(fac.center, float)
        for m, tr in sorted(b["splines"].items()):
            r_us = int(round(tr.release_s * 10)) * 100_000
            e_us = int(math.floor((tr.end_s + lim["hold_s"]) * 10 + 1e-9)) * 100_000
            t_us = np.arange(r_us, e_us + 1, 100_000, dtype=np.int64)
            tt = t_us / 1e6
            xy = tr.evaluate(tt, 0)
            v = np.zeros((len(tt), 3))
            v[:, :2] = tr.evaluate(tt, 1)
            tl, _ = NC.layer_levels(fac, xy)
            for frames, tally in ((NC.work_mask(tl), tw), (np.ones(len(tt), bool), tf)):
                a = (xy, v, t_us, tl, frames, center, cfg)
                oo, t_o = _timed(orig, a)
                cc, t_c = _timed(cand, a)
                tally.add(a, None, oo, cc, t_o, t_c, f"{cid}/{m}")
    return {"mode": "quick20", "contracts": len(keys), "work_mask": tw.doc(), "full_window": tf.doc()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("v811", "quick20"), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--baseline")
    ap.add_argument("--devset")
    ap.add_argument("--cache")
    ap.add_argument("--keys")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    from v08.motion import nominal_checks as NC
    import hashlib
    import inspect
    oracle_src = inspect.getsource(NC.__dict__.get("_revisit_original", NC.revisit))
    doc = mode_v811(args) if args.mode == "v811" else _quick20(args)
    doc["oracle_source_sha256"] = hashlib.sha256(oracle_src.encode("utf-8")).hexdigest()
    doc["candidate_source_sha256"] = hashlib.sha256(inspect.getsource(NC._revisit_vectorized).encode("utf-8")).hexdigest()
    (out / f"revisit_equivalence_{args.mode}.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1, default=lambda x: repr(x)) + "\n", encoding="utf-8")
    t = doc.get("tally") or doc.get("work_mask")
    print(json.dumps({"mode": args.mode, "calls": t["calls"], "diff_orig_vs_candidate": t["diff_orig_vs_candidate"],
                      "diff_frozen_vs_orig": t["diff_frozen_vs_orig"], "total_ratio": t["total_ratio"],
                      **({"regress": doc["regress"]} if "regress" in doc else
                         {"full_window_diff": doc["full_window"]["diff_orig_vs_candidate"],
                          "full_window_ratio": doc["full_window"]["total_ratio"]})}, ensure_ascii=False))
    bad = t["diff_orig_vs_candidate"] or t["diff_frozen_vs_orig"] or (
        args.mode == "quick20" and doc["full_window"]["diff_orig_vs_candidate"])
    return 4 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
