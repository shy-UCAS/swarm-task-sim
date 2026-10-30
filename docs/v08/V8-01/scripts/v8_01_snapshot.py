"""V8-01: 记录 SwarmData\\v07_* 每个目录的文件数、总字节数、最新修改时间（只读）。

用法: python -B v8_01_snapshot.py <输出json>
"""
import json
import os
import sys
import time

DATA_ROOT = r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData"


def walk(path):
    n = 0
    size = 0
    latest = 0.0
    latest_path = ""
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    else:
                        st = e.stat(follow_symlinks=False)
                        n += 1
                        size += st.st_size
                        if st.st_mtime > latest:
                            latest = st.st_mtime
                            latest_path = e.path
                except OSError:
                    pass
    return n, size, latest, latest_path


def main():
    out = sys.argv[1]
    t0 = time.time()
    res = {"taken_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "dirs": {}}
    for name in sorted(os.listdir(DATA_ROOT)):
        p = os.path.join(DATA_ROOT, name)
        if not name.startswith("v07_") or not os.path.isdir(p):
            continue
        n, size, latest, lp = walk(p)
        res["dirs"][name] = {
            "file_count": n,
            "total_bytes": size,
            "latest_mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(latest)) if latest else None,
            "latest_path": os.path.relpath(lp, DATA_ROOT) if lp else None,
        }
    res["elapsed_s"] = round(time.time() - t0, 1)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
