"""第 5 部分接线冒烟：1 个合同全链路（不是批次、不计检查点）。核对 optimization_entered、phase_metrics、
巡逻段 Fréchet 编组曲线、attempt_counters 能在真实对象上运行。"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from v08.runner.monitoring import load_entries, jsonable
from v08.runner import joint_monitoring as JM
from v08.runner import joint_report as JR
from v08.scene.context import load_context
from v08.motion.optimize import load_settings
from v08.contract.monitoring import monitoring_mission
from v08.sampler.common import sample_common

R = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
entries = load_entries(str(R / "Simulation-v08/docs/v08/V8-03/devset_v08.json"))
cache, out = Path(sys.argv[1]), Path(sys.argv[2])
o, d = int(sys.argv[3]), int(sys.argv[4])
e = {int(x["order"]): x for x in entries}[o]
ctx = load_context(e, data_root=R / "SwarmData", cache_dir=cache)
holder = {}
rec = JM.run_contract(ctx, e, d, settings=load_settings(), out_dir=out, keep=holder)
print("success", rec["success"], "attempts", rec["attempts"], "post", rec["post_optimization_failures"],
      "skel", rec["skeleton_failures"], "unknown", rec["unknown_attempts"])
print("flags", [(a["stage"], a["optimization_entered"], a["shape_audit_failed"]) for a in rec["attempt_log"]])
print("counters", JR.attempt_counters(rec["attempt_log"]))
if rec["success"]:
    pm = rec["phase_metrics"]
    for m, v in sorted(pm.items()):
        if "phases" in v:
            print(m, {k: (round(x["reference_min_m_s"] or -1, 2), x["measured_ratio"] and round(x["measured_ratio"], 3),
                          round(x["optimized_along_max_m"], 2)) for k, x in v["phases"].items()})
        else:
            print(m, v)
    group = monitoring_mission(ctx, sample_common(ctx.family, d)).groups[0]
    b, a = JM.group_reference_curves(ctx, group, holder["result"])
    print("patrol curves", b.shape, a.shape)
(out / "chain_smoke.json").write_text(json.dumps(jsonable({k: rec.get(k) for k in (
    "contract_id", "success", "attempts", "post_optimization_failures", "skeleton_failures", "unknown_attempts",
    "phase_metrics")}), ensure_ascii=False, indent=1), encoding="utf-8")
