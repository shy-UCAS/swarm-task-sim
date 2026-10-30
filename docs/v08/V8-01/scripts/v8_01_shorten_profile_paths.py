"""V8-01 §5.3：把剖析文本里的长绝对路径换成缩写，便于阅读（只改本任务自己的输出文件）。

用法: python -B v8_01_shorten_profile_paths.py <profile_*.txt> ...
"""
import sys

REPLACE = [
    ("F:\\CASIA\\Drone Swarm Situational Awareness Algorithm\\Simulation-fe-prod-r3\\Multi-UAV SimpleGC\\", "<frozen>\\"),
    ("F:\\CASIA\\Drone Swarm Situational Awareness Algorithm\\_handoff\\2026-10-29_V8-01_baseline-diagnosis\\", "<V8-01>\\"),
    ("C:\\Users\\shy\\anaconda3\\envs\\llm\\Lib\\site-packages\\", "<site-packages>\\"),
    ("C:\\Users\\shy\\anaconda3\\envs\\llm\\Lib\\", "<stdlib>\\"),
]
NOTE = ("路径缩写：`<frozen>` = `Simulation-fe-prod-r3\\Multi-UAV SimpleGC`，`<V8-01>` = `_handoff\\2026-10-29_V8-01_baseline-diagnosis`，"
        "`<site-packages>` / `<stdlib>` = conda `llm` 环境。\n")

for name in sys.argv[1:]:
    with open(name, encoding="utf-8") as f:
        text = f.read()
    for old, new in REPLACE:
        text = text.replace(old, new)
    if "路径缩写" not in text:
        text = text.replace("\n## ", "\n" + NOTE + "\n## ", 1)
    with open(name, "w", encoding="utf-8") as f:
        f.write(text)
