import json
from pathlib import Path

D = Path("F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset"
         "/attempt_s2x_p1_20261014T103824Z_2741f4ee")

print("=== audits ===")
for f in sorted(D.rglob("independent_exact_audit.json")):
    if "process_check" in str(f):
        continue
    d = json.loads(f.read_text())
    rel = f.parent.relative_to(D).as_posix()
    print(f"  {d['status']:8s} {rel}")

print("=== planning layer intervals ===")
for f in sorted(D.rglob("planning_layer_interval.json")):
    if "process_check" in str(f):
        continue
    d = json.loads(f.read_text())
    rel = f.parent.relative_to(D).as_posix()
    print(f"  {rel}: sync={d['synchronous']['minimum_m']} seq={d['sequential']['minimum_m']}")

print("=== episode dirs (state) ===")
for sk in sorted(p for p in D.iterdir() if p.is_dir() and "process_check" not in p.name):
    for mode in ("synchronous", "sequential"):
        labels = sk / mode / "labels.json"
        if labels.exists():
            lb = json.loads(labels.read_text())
            gid = next(iter(lb["task_groups"]))
            tg = lb["task_groups"][gid]
            sep = lb["cluster"]["observed"]["minimum_separation_m"]
            qual = lb["generation_quality"]["retained"]
            print(f"  {sk.name}/{mode}: result={tg['result']['status']} sep={sep:.3f} retained={qual}")
        else:
            print(f"  {sk.name}/{mode}: (missing)")
