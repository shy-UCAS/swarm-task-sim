"""A5: 全部 episode 的时间构成
拆解口径(与 runner.py 结构一致):
  任务跨度 T0..T1 = min(phase_start_sent_0) .. max(task_target_verified_last)
  每个阶段 N:
    upload_release_N = min(phase_start_sent_N)   - max(task_target_verified_{N-1})
    flight_N         = max(phase_finished_N)     - min(phase_start_sent_N)
    confirm_N        = max(task_target_verified_N) - max(phase_finished_N)
  三者之和 == T1 - T0 (望远镜求和)
"""
import json
import statistics
from pathlib import Path

DATASETS = {
    "v03_pilot_final": Path("verification/v03_pilot_final_20260930/dataset"),
    "v03_integration": Path("verification/v03_integration_20260930/dataset_final"),
}


def pct(v, q):
    v = sorted(v)
    x = (len(v) - 1) * q
    lo = int(x)
    return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (x - lo)


eps = []
for name, base in DATASETS.items():
    mf = json.loads((base / "dataset_manifest.json").read_text(encoding="utf-8"))
    for e in mf["episodes"]:
        d = base / "episodes" / e["run_id"]
        if (d / "manifest.json").exists():
            eps.append(dict(dataset=name, run_id=e["run_id"], scenario=e.get("scenario_id"), dir=d))

print("episode 总数: %d\n" % len(eps))
rows = []

for ep in eps:
    man = json.loads((ep["dir"] / "manifest.json").read_text(encoding="utf-8"))
    rd = Path(man["run_directory"])
    meta = json.loads((rd / "metadata.json").read_text(encoding="utf-8"))
    ev = [json.loads(l) for l in (rd / "events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    def T(kind, **f):
        return sorted(e["t"] for e in ev if e["event"] == kind and all(e.get(k) == v for k, v in f.items()))

    rel = T("phase_release_scheduled")
    snt = T("phase_start_sent")
    auto = T("phase_auto_confirmed")
    fin = T("phase_finished")
    ver = T("task_target_verified")

    phases = sorted({e["phase"] for e in ev if e.get("phase")} )
    phases.sort()

    # 每阶段(swarm 时间线)
    up, fl, cf, bar = [], [], [], []
    prev_end = None
    for ph in phases:
        s, f, a, v = (min(T("phase_start_sent", phase=ph), default=None),
                      max(T("phase_finished", phase=ph), default=None),
                      min(T("phase_auto_confirmed", phase=ph), default=None),
                      max(T("task_target_verified", phase=ph), default=None))
        if None in (s, f, v):
            continue
        if prev_end is not None:
            up.append(s - prev_end)
        fl.append(f - s)
        cf.append(v - f)
        prev_end = v
        fin_all = T("phase_finished", phase=ph)
        if fin_all:
            bar.append(max(fin_all) - min(fin_all))

    T0 = min(snt) if snt else None
    T1 = max(ver) if ver else None
    mission = (T1 - T0) if (T0 is not None and T1 is not None) else None

    conn = max(T("connected"), default=None)
    airb = max(T("airborne_ready"), default=None)
    lstart = max(T("landing_started"), default=None)
    landed = max(T("landed"), default=None)

    row = dict(
        dataset=ep["dataset"], episode=ep["run_id"], scenario=ep["scenario"],
        status=meta.get("status"), elapsed_s=meta.get("elapsed_s"),
        phases=len(phases),
        connected_s=conn, airborne_ready_s=airb,
        mission_T0_s=T0, mission_T1_s=T1, mission_s=mission,
        sum_upload_release=sum(up), sum_flight=sum(fl), sum_confirm=sum(cf),
        sum_barrier_in_flight=sum(bar),
        landing_started_s=lstart, landed_s=landed,
        n_upload_samples=len(up))
    if mission and mission > 0:
        row["frac_upload_release"] = sum(up) / mission
        row["frac_flight"] = sum(fl) / mission
        row["frac_confirm"] = sum(cf) / mission
        row["frac_overhead"] = (sum(up) + sum(cf)) / mission
    rows.append(row)

Path("audit_v04/A5_final.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

print("=" * 132)
print("A5-1 每个 episode 的 elapsed_s 与主要时间点")
print("=" * 132)
print("%-24s %-16s %8s %8s %8s %8s %8s %8s" %
      ("episode", "scenario", "elapsed", "连接", "离地", "任务起点", "任务终点", "任务跨度"))
for r in rows:
    f = lambda x: ("%8.2f" % x) if x is not None else "     n/a"
    print("%-24s %-16s %s %s %s %s %s %s" %
          (r["episode"], r["scenario"] or "-", f(r["elapsed_s"]), f(r["connected_s"]),
           f(r["airborne_ready_s"]), f(r["mission_T0_s"]), f(r["mission_T1_s"]), f(r["mission_s"])))

print()
print("=" * 132)
print("A5-2 任务阶段拆解 (swarm 时间线, 秒)")
print("=" * 132)
print("%-24s %4s %10s %10s %10s %10s %9s %9s" %
      ("episode", "阶段", "上传+放行", "飞行", "确认驻留", "三者之和", "任务跨度", "校验差"))
for r in rows:
    tot = r["sum_upload_release"] + r["sum_flight"] + r["sum_confirm"]
    diff = (tot - r["mission_s"]) if r["mission_s"] else None
    print("%-24s %4d %10.2f %10.2f %10.2f %10.2f %9s %9s" %
          (r["episode"], r["phases"], r["sum_upload_release"], r["sum_flight"],
           r["sum_confirm"], tot,
           ("%.2f" % r["mission_s"]) if r["mission_s"] else "n/a",
           ("%.4f" % diff) if diff is not None else "n/a"))

print()
print("=" * 132)
print("A5-3 占比: (上传+放行+确认驻留) / 任务阶段总时长")
print("=" * 132)
print("%-24s %12s %10s %10s %10s %12s" %
      ("episode", "上传+放行%", "飞行%", "确认%", "屏障(含在飞行)", "过载占比%"))
for r in rows:
    if "frac_upload_release" not in r:
        continue
    print("%-24s %11.2f%% %9.2f%% %9.2f%% %12.2f %11.2f%%" %
          (r["episode"], r["frac_upload_release"] * 100, r["frac_flight"] * 100,
           r["frac_confirm"] * 100, r["sum_barrier_in_flight"], r["frac_overhead"] * 100))

val = [r for r in rows if "frac_overhead" in r]
print()
print("汇总 (n=%d):" % len(val))
for key, lbl in (("frac_upload_release", "上传+放行"), ("frac_flight", "飞行"),
                 ("frac_confirm", "确认驻留"), ("frac_overhead", "上传+放行+确认")):
    v = [r[key] for r in val]
    print("  %-12s 中位数=%.4f (%.2f%%)  均值=%.4f  范围=[%.4f, %.4f]" %
          (lbl, statistics.median(v), statistics.median(v) * 100, statistics.mean(v), min(v), max(v)))

el = [r["elapsed_s"] for r in rows if r["elapsed_s"]]
mi = [r["mission_s"] for r in rows if r["mission_s"]]
print()
print("elapsed_s (主机总耗时, 含 SITL 启动/连接): 中位数=%.2fs 均值=%.2fs 范围=[%.2f, %.2f]  n=%d" %
      (statistics.median(el), statistics.mean(el), min(el), max(el), len(el)))
print("任务跨度:                              中位数=%.2fs 均值=%.2fs 范围=[%.2f, %.2f]  n=%d" %
      (statistics.median(mi), statistics.mean(mi), min(mi), max(mi), len(mi)))
print("任务跨度 / elapsed_s 的中位数 = %.4f" %
      statistics.median([r["mission_s"] / r["elapsed_s"] for r in rows if r["mission_s"] and r["elapsed_s"]]))
st = {}
for r in rows:
    st[r["status"]] = st.get(r["status"], 0) + 1
print("run_status 分布: %s" % st)
