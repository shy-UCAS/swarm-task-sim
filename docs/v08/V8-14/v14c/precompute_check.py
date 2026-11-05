"""V8-14c 3.2 记录：真实优化解 SplineTrajectory.pva 的数组求值与逐点标量求值是否逐位一致（只读 out/quick）。"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path.cwd()))
from v08.motion.optimize import SplineTrajectory  # noqa: E402
from v08.sim.tracking import _pva, TimeReference  # noqa: E402

quick = Path(sys.argv[1])
out = {}
for cdir in sorted((quick / "contracts").iterdir()):
    opt = json.loads((cdir / "optimized.json").read_text(encoding="utf-8"))["members"]
    for m, o in sorted(opt.items()):
        tr = SplineTrajectory(m, o["release_s"], o["end_s"], o["altitude_m"], np.asarray(o["knots"], float),
                              np.asarray(o["controls"], float))
        ref = TimeReference(m, tr.release_s, tr.end_s, tr.altitude_m, tr.pva)
        grid = np.arange(0, int((tr.end_s + 60) * 1e6), 20_000, dtype=np.int64)
        P, V, A = (np.asarray(x, float).reshape(-1, 2) for x in ref.pva(grid / 1e6))
        S = [_pva(ref, g / 1e6) for g in grid]
        Ps = np.array([s[0] for s in S]); Vs = np.array([s[1] for s in S]); As = np.array([s[2] for s in S])
        diff = {k: (int(np.sum(x != y)), float(np.max(np.abs(x - y)))) for k, x, y in (("p", P, Ps), ("v", V, Vs), ("a", A, As))}
        out[f"{cdir.name}/{m}"] = {"grid": int(len(grid)), **{k: {"mismatch": d[0], "max_abs": d[1]} for k, d in diff.items()}}
    break
print(json.dumps(out, indent=1))
