"""V8-18 第 1 部分：从指令第 9 节原样取出三份预置测试，并与作者静态复核记录（author_static_review.json）的 SHA256 比较。
用法：python -B extract_presets.py <指令.md> <输出目录>"""
import hashlib, sys, pathlib
md = pathlib.Path(sys.argv[1]).read_bytes().decode("utf-8")
want = {"test_preset_numeric_v18.py": "37e0f99b805755a14fbc04ae10a5d19c8ac753401d014e2c6d2929dfca4f914c",
        "test_preset_local_geometry_v18.py": "df210a76922abd28e7ac66f5af5f8a64b8b53e04e11663fcac6b5895c0bf0c39",
        "test_preset_local_artifacts_v18.py": "028620ee13f136efec275f2925ae7e8948b46e75d2c7fd91c58b3c9c86eeea52"}
print("md sha", hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest(), "crlf" if "\r\n" in md else "lf")
out = pathlib.Path(sys.argv[2])
for name, h in want.items():
    i = md.index(f"`tests/v08/V8-18/{name}`")
    s = md.index("```python\n", i) + len("```python\n")
    e = md.index("\n```", s)
    body = md[s:e]
    cands = {"raw": body, "nl": body + "\n", "strip_nl": body.rstrip("\n") + "\n"}
    hit = None
    for k, v in cands.items():
        if hashlib.sha256(v.encode("utf-8")).hexdigest() == h:
            hit = k; (out / name).write_bytes(v.encode("utf-8"))
    if hit is None:
        (out / name).write_bytes((body + "\n").encode("utf-8"))
    print(name, hit, hashlib.sha256((out / name).read_bytes()).hexdigest())
