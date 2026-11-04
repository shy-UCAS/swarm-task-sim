import sys, json, numpy as np
sys.path.insert(0, ".")
from pathlib import Path
from v08.diagnostics.diversity import discrete_frechet
out = Path(sys.argv[1])
recs = json.loads((out / "diversity" / "records.json").read_text(encoding="utf-8")) if (out / "diversity" / "records.json").exists() else None
if recs is None:
    print(list((out / "diversity").iterdir())[:5]); sys.exit()
fam = {}
for r in recs:
    if r.get("success") and "curve_after" in r:
        fam.setdefault(r["family_id"], []).append(r)
n = eq = 0; maxdiff = 0; disp = []
for fid, rs in list(fam.items())[:3]:
    for i in range(len(rs)):
        a, b = np.asarray(rs[i]["curve_after"]), np.asarray(rs[i]["curve_before"])
        disp.append((len(a), len(b)))
        for j in range(i + 1, len(rs)):
            A, B = np.asarray(rs[i]["curve_after"]), np.asarray(rs[j]["curve_after"])
            f = discrete_frechet(A, B); e = max(np.hypot(*(A[0] - B[0])), np.hypot(*(A[-1] - B[-1])))
            fb = discrete_frechet(np.asarray(rs[i]["curve_before"]), np.asarray(rs[j]["curve_before"]))
            n += 1; eq += abs(f - e) < 1e-9; maxdiff = max(maxdiff, abs(f - fb))
print("pairs", n, "frechet==endpoint", eq, "max|after-before| frechet", maxdiff)
print("lengths sample", disp[:5])
