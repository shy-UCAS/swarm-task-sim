import json
from pathlib import Path

data = json.loads((Path("F:/CASIA/Drone Swarm Situational Awareness Algorithm"
                        "/SwarmData/v07_dataset"
                        "/attempt_s2infra_20261014T023604Z_d2566191"
                        "/private_skeleton_descriptors.json")).read_text())

by_role = {}
for d in data:
    role = d.get("common_draw", {}).get("role") or d.get("base_intent", "?")
    ext = d["skeleton_id"].split("ext_")[1][:3] if "ext_" in d["skeleton_id"] else "?"
    key = f"{role}_{ext}"
    by_role.setdefault(key, []).append(d["skeleton_id"])

for k in sorted(by_role):
    for sid in sorted(by_role[k])[:3]:
        print(k, sid)
