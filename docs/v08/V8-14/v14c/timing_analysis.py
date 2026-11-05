"""V8-14c 第 5.3 节：分环节 CPU、仿真每 1000 s × 每成员耗时、并行效率（只读 full 输出）。

用法：python <本文件> <out/full_v14c>
"""
import json
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
v = s["v14c"]
cpu = v["stage_cpu_s"]
tot = sum(cpu.values())
print("prewarm_s", round(v["prewarm_s"], 1), "dispatch_wall_s", round(v["dispatch_wall_s"], 1), "workers", s["workers"])
print("stage CPU s:", {k: round(x) for k, x in cpu.items()}, "total", round(tot))
print("stage share:", {k: round(x / tot, 3) for k, x in cpu.items()})
print("contract busy s", round(v["contract_busy_s"]), "parallel efficiency", round(v["parallel_efficiency"], 3))
v13c = {"simulation_s": 12139, "optimize_s": 4596, "skeleton_s": 1824, "verify_s": 779}
print("V8-13c (ruling table):", v13c, "total", sum(v13c.values()))
# 仿真每 1000 s × 每成员：成功合同最后一个 attempt 的 simulation_s ÷ Σ 成员实测帧时长
ratios, sim_tot, fly_tot, modes = [], 0.0, 0.0, {}
for sub in (out / "contracts", out / "diversity" / "contracts"):
    for cdir in sorted(sub.iterdir()):
        tele = sub.parent / "telemetry" / f"{cdir.name}.json"
        if not (cdir / "tracks").exists() or not tele.exists():
            continue
        tm = [t for t in json.loads(tele.read_text(encoding="utf-8"))["timing"] if t]
        last = tm[-1]
        fly = sum(len(np.load(m / "tau_us.npy")) * 0.1 for m in (cdir / "tracks").iterdir())
        sim = float(last.get("simulation_s", 0.0))
        mode = (last.get("simulation_detail") or {}).get("reference_mode")
        modes[mode] = modes.get(mode, 0) + 1
        if fly > 0 and sim > 0:
            ratios.append(sim / (fly / 1000.0))
            sim_tot += sim
            fly_tot += fly
r = np.sort(np.asarray(ratios))
print("sim s per 1000 s x member: pooled", round(sim_tot / (fly_tot / 1000.0), 3), "median", round(float(np.median(r)), 3),
      "p10/p90", round(float(r[int(.1 * (len(r) - 1))]), 3), round(float(r[int(.9 * (len(r) - 1))]), 3), "n", len(r),
      "(V8-13c ≈ 6 s)")
print("reference modes (last attempt)", modes)
