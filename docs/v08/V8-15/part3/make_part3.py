"""V8-15 第 3 部分：从外部 out/analysis 复制轻量结果并画图（只读输入）。用法：make_part3.py <out/analysis> <本目录>"""
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
for n in ("summary.json", "by_group.csv", "failed_attempts_rows.json", "speed_cases.json"):
    shutil.copyfile(src / n, dst / n)
hashes = {n: hashlib.sha256((src / n).read_bytes()).hexdigest() for n in sorted(p.name for p in src.iterdir())}
(dst / "external_hashes.json").write_text(json.dumps({"root": str(src.resolve()), "sha256": hashes}, indent=1) + "\n",
                                          encoding="utf-8")
rows = list(csv.DictReader(open(src / "pairs.csv", encoding="utf-8")))
sources = ("optimized_xy", "measured_sample", "measured_interp")
bins = ["phase:collect_ingress", "phase:patrol", "turn:a", "turn:b", "turn:both", "phase:egress", "phase:hold",
        "phase:mixed:collect_ingress|patrol", "phase:mixed:egress|patrol", "phase:mixed:egress|hold"]
fig, axes = plt.subplots(3, 1, figsize=(12, 11), sharex=True)
for ax, s in zip(axes, sources):
    data = []
    for b in bins:
        kind, key = b.split(":", 1)
        data.append([float(r["min_m"]) for r in rows if r["source"] == s and r["bin_kind"] == kind and r["bin"] == key])
    bp = ax.boxplot(data, whis=(0, 100), showfliers=False, patch_artist=True)
    for i, patch in enumerate(bp["boxes"]):
        patch.set_facecolor("#f4a261" if bins[i].startswith("turn") else "#8ecae6")
    ax.axhline(3.0, color="#2a9d8f", lw=1, ls="--", label="3 m（规划硬间距）")
    ax.axhline(2.0, color="#e63946", lw=1, ls="--", label="2 m（实测门禁，严格小于才违规）")
    ax.set_yscale("log")
    ax.set_ylabel(f"{s}\n成员对分档最小值 (m)")
    ax.legend(loc="upper right", fontsize=8)
axes[-1].set_xticks(range(1, len(bins) + 1), [b.replace("phase:", "").replace("mixed:", "mix:") for b in bins],
                    rotation=30, ha="right")
fig.suptitle("full_v14c 198 保留合同：成员对分阶段最小间距（须线为 min/max；橙色 turn 与巡逻重叠，不能相加）")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
fig.tight_layout()
fig.savefig(dst / "separation_by_phase.png", dpi=110)
print("ok", len(rows))
