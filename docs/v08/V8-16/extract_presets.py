"""V8-16 第 1 部分：从指令原文按"保存为 `…/<名>.py`"后的第一个 ```python 代码块原样提取预置测试（UTF-8、LF、末尾一个换行）。
用法：python extract_presets.py <指令.md> <输出目录>"""
import hashlib, re, sys
from pathlib import Path
src = Path(sys.argv[1]).read_text(encoding="utf-8").replace("\r\n", "\n")
out = Path(sys.argv[2])
for m in re.finditer(r"保存为 `[^`]*/(test_preset_[a-z0-9_]+\.py)`", src):
    name = m.group(1)
    start = src.index("```python\n", m.end()) + len("```python\n")
    body = src[start:src.index("\n```", start)] + "\n"
    p = out / name
    if p.exists():
        raise SystemExit(f"已存在，不覆盖：{p}")
    p.write_bytes(body.encode("utf-8"))
    print(hashlib.sha256(body.encode("utf-8")).hexdigest(), name)
