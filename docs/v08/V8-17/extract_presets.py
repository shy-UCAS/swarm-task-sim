import hashlib, re, sys, pathlib
md = pathlib.Path(sys.argv[1]).read_bytes().decode("utf-8")
want = {"test_preset_numeric_v17.py":"eca9adfc243aad4c74bced8597af1f1e0d4ce4b2a33e6e30704e312051188478",
"test_preset_local_geometry_v17.py":"5066c4a07d69bd6fcc4dc8b1aaf2bcbdc98e16665a31c037b53cfd1548327c19",
"test_preset_local_artifacts_v17.py":"cbad45ebb2a23f402b3bf7955e867b40cb0d0e8207f1f9a406e632bdbd90d389"}
print("md sha", hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest(), "crlf" if "\r\n" in md else "lf")
out = pathlib.Path(sys.argv[2])
for name, h in want.items():
    i = md.index(f"`{name}`")
    s = md.index("```python\n", i) + len("```python\n")
    e = md.index("\n```", s)
    body = md[s:e]
    cands = {"raw": body, "nl": body + "\n", "strip_nl": body.rstrip("\n") + "\n"}
    hit = None
    for k, v in cands.items():
        if hashlib.sha256(v.encode("utf-8")).hexdigest() == h:
            hit = k; (out / name).write_bytes(v.encode("utf-8"))
    print(name, hit)
