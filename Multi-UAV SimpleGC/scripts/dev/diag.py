import json
from pathlib import Path
import numpy as np

D = Path("F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset"
         "/attempt_s2x_p1_20261014T103824Z_2741f4ee")
sk_dir = D / "family_s12_4d13d93f9171c446_ext_001_regular"
sk = json.loads((sk_dir / "skeleton.json").read_text())

print("=== initial states (start positions) ===")
for st in sorted(sk["initial_states"], key=lambda s: s["agent_id"]):
    print(f"  {st['agent_id']}: {[round(v,1) for v in st['position_enu_m'][:2]]}")

print("=== planned routes ===")
for a in sorted(sk["members"]):
    wps = sk["references"][a]["points_enu_m"]
    print(f"  {a}: n={len(wps)} first={[round(v,1) for v in wps[0][:2]]} "
          f"last={[round(v,1) for v in wps[-1][:2]]}")

print("=== spatial min distance between planned routes (ignoring time) ===")
routes = {a: np.array(sk["references"][a]["points_enu_m"])[:, :2] for a in sk["members"]}
ids = sorted(routes)
worst = []
for i in range(len(ids)):
    for j in range(i + 1, len(ids)):
        A, B = routes[ids[i]], routes[ids[j]]
        d = np.linalg.norm(A[:, None, :] - B[None, :, :], axis=2).min()
        worst.append((float(d), ids[i], ids[j]))
worst.sort()
for d, a, b in worst[:5]:
    print(f"  {a}-{b}: {d:.3f} m")

print("=== truth closest approach ===")
for mode in ("synchronous", "sequential"):
    f = sk_dir / mode / "truth_10hz.npz"
    if not f.exists():
        print(f"  {mode}: missing")
        continue
    tr = np.load(f, allow_pickle=True)
    tids = tr["agent_ids"].tolist()
    p = tr["p"]
    t = tr["time_us"]
    best = None
    for i in range(len(tids)):
        for j in range(i + 1, len(tids)):
            d = np.linalg.norm(p[:, i, :2] - p[:, j, :2], axis=1)
            k = int(d.argmin())
            if best is None or d[k] < best[0]:
                best = (float(d[k]), tids[i], tids[j], k,
                        p[k, i, :2].copy(), p[k, j, :2].copy())
    dmin, a, b, k, pa, pb = best
    print(f"  {mode}: min={dmin:.3f} m at t={t[k]/1e6:.1f}s between {a} and {b}")
    print(f"     {a} at {[round(v,1) for v in pa]}")
    print(f"     {b} at {[round(v,1) for v in pb]}")
