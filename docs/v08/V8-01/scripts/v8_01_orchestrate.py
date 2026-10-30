"""V8-01 §5.2/§5.3：并行启动 5 个分环节计时进程和 2 个剖析进程，超过上限就终止并记录。

用法: python -B v8_01_orchestrate.py <out_dir> [<标签> <作业名,...>]
  给出标签时只启动列出的作业，日志与汇总文件名带该标签（用于修复驱动后重跑部分作业）。
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRIVER = HERE / "v8_01_driver.py"

# 样本：timing_records.csv 中该意图全部保留骨架里 |ln(B/B中位)|+|ln(C同步/C同步中位)| 最小者
# 上限：min(3600, 2×原记录耗时)，原记录耗时 = B 规划 + 同步方式（仿真 + 2×摊分准备 + 后处理），见报告说明
SAMPLES = [
    ("s52_transit", "prod_f100_140", "family_s15_353b8b5f4cae79d3_ext_005_regular", 36.4 + 61.9 + 88.2 + 4.3),
    ("s52_reconnaissance", "prod_f020_060", "family_s15_dc9e63c745907aa8_ext_001_regular", 58.5 + 66.4 + 89.7 + 12.5),
    ("s52_monitoring", "prod_f180_220", "family_s15_1c1cf42fbb718d98_ext_002_regular", 207.8 + 287.3 + 355.2 + 32.4),
    ("s52_feint", "prod_f100_140", "family_s15_19db8d41d1ebea45_ext_003_regular", 57.5 + 59.9 + 84.4 + 3.6),
    ("s52_penetration", "prod_f060_100", "family_s15_617b861a82b92aa4_ext_009_regular", 46.0 + 61.6 + 92.4 + 5.6),
]
PROFILES = [
    ("sim_transit", "prod_f100_140", "family_s15_353b8b5f4cae79d3_ext_005_regular", "sim"),
    ("plan_monitoring", "prod_f220_260", "family_s15_e891bec0170b57ed_ext_007_regular", "plan"),
]


def main():
    out = Path(sys.argv[1])
    rerun = out / "rerun"
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    jobs = []
    for name, run, sid, recorded in SAMPLES:
        limit = min(3600., 2 * recorded)
        cmd = [sys.executable, "-B", str(DRIVER), "sample", "--run", run, "--sid", sid, "--out", str(rerun / name)]
        jobs.append({"name": name, "kind": "5.2", "run": run, "sid": sid, "recorded_s": recorded, "limit_s": limit, "cmd": cmd})
    for name, run, sid, target in PROFILES:
        cmd = [sys.executable, "-B", str(DRIVER), "profile", "--run", run, "--sid", sid, "--target", target,
               "--name", name, "--out", str(rerun / f"profile_{name}"), "--txt", str(out / f"profile_{name}.txt")]
        jobs.append({"name": f"profile_{name}", "kind": "5.3", "run": run, "sid": sid, "limit_s": 2700., "cmd": cmd})
    tag = ""
    if len(sys.argv) > 3:
        tag = "_" + sys.argv[2]
        wanted = set(sys.argv[3].split(","))
        jobs = [j for j in jobs if j["name"] in wanted]
        if len(sys.argv) > 4 and sys.argv[4] == "--separate-dirs":
            # 输出目录也带标签，避免覆盖上一轮
            for j in jobs:
                i = j["cmd"].index("--out")
                j["cmd"][i + 1] = j["cmd"][i + 1] + tag
    for job in jobs:
        log = open(rerun / f"{job['name']}{tag}.log", "w", encoding="utf-8")
        job["log"] = log
        job["started"] = time.time()
        job["proc"] = subprocess.Popen(job["cmd"], stdout=log, stderr=subprocess.STDOUT, env=env)
    while any(j["proc"].poll() is None for j in jobs):
        for j in jobs:
            if j["proc"].poll() is None and time.time() - j["started"] > j["limit_s"]:
                j["proc"].kill()
                j["proc"].wait()
                j["timed_out"] = True
            if j["proc"].poll() is not None and "finished" not in j:
                j["finished"] = time.time()
        time.sleep(5)
    record = []
    for j in jobs:
        j["log"].close()
        record.append({k: j.get(k) for k in ("name", "kind", "run", "sid", "recorded_s", "limit_s")} |
                      {"returncode": j["proc"].returncode, "timed_out": j.get("timed_out", False),
                       "wall_s": round(j.get("finished", time.time()) - j["started"], 1)})
    with open(rerun / f"orchestrator{tag}.json", "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
