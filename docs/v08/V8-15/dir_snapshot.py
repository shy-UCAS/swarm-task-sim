"""目录快照：全部文件 SHA256/大小/mtime_ns（只读）。用法：dir_snapshot.py <目录> <out.json> [--compare <旧.json>]"""
import hashlib, json, sys
from pathlib import Path

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

root = Path(sys.argv[1]).resolve()
doc = {"root": str(root), "files": {p.relative_to(root).as_posix(): [sha(p), p.stat().st_size, p.stat().st_mtime_ns]
                                    for p in sorted(root.rglob("*")) if p.is_file()}}
Path(sys.argv[2]).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
msg = {"files": len(doc["files"])}
if "--compare" in sys.argv:
    old = json.loads(Path(sys.argv[sys.argv.index("--compare") + 1]).read_text(encoding="utf-8"))["files"]
    new = doc["files"]
    msg.update(added=sorted(set(new) - set(old)), removed=sorted(set(old) - set(new)),
               changed=sorted(k for k in set(old) & set(new) if old[k] != new[k]))
print(json.dumps(msg, ensure_ascii=False))
