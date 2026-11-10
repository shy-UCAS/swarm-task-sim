"""Final prose formatting only; no evidence or computation is changed."""
from evidence_utils import DOC

p = DOC / "REPORT.md"
text = p.read_text(encoding="utf-8")
text = text.replace("墙钟×151/24", r"\(\mathrm{wall}\times151/24\)")
text = text.replace("墙钟 ×151/24", r"\(\mathrm{wall}\times151/24\)")
text = text.replace("β/φ/c/K", r"\(\beta,\varphi,c,K\)")
text = text.replace("完整按 2 s 刷盘的系统采样", "以 2 s 为目标周期并逐样本刷盘的系统采样")
p.write_text(text, encoding="utf-8", newline="\n")
p = DOC / "RUNNING.md"
text = p.read_text(encoding="utf-8").replace("part5/6/7_cost_ruling", "part5_cost_ruling、part6_cost_ruling、part7_cost_ruling")
p.write_text(text, encoding="utf-8", newline="\n")
