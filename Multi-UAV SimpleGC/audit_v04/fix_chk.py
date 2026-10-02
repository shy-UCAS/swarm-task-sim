import json, math, statistics
s = json.load(open("audit_v04/A4_sync.json"))
d = {x["episode"]: x["window_s"] for x in json.load(open("audit_v04/A4_dwell.json"))}
by = {}
for x in s:
    by.setdefault(x["agents"], []).append((x["sync_frac"], d.get(x["episode"]), x["episode"], x["fleet_events"]))
print("按飞机数分组:")
for n in sorted(by):
    v = sorted(by[n])
    fr = [a for a,_,_,_ in v]
    print("  %d 机 (n=%d): %.4f - %.4f  中位 %.4f" % (n, len(v), min(fr), max(fr), statistics.median(fr)))
    for a,w,e,f in v:
        print("       %s  占比=%.4f  窗口=%.1fs  事件=%d" % (e, a, w, f))
xs=[d[x["episode"]] for x in s]; ys=[x["sync_frac"] for x in s]
mx,my=statistics.mean(xs),statistics.mean(ys)
num=sum((a-mx)*(b-my) for a,b in zip(xs,ys))
den=math.sqrt(sum((a-mx)**2 for a in xs)*sum((b-my)**2 for b in ys))
print("\n占比 vs 窗口时长: r = %.4f" % (num/den))
