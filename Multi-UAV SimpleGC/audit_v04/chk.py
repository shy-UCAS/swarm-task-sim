import json, statistics
s = json.load(open("audit_v04/A4_sync.json"))
ev = sum(x["fleet_events"] for x in s); cm = sum(x["common_events"] for x in s)
print("停靠事件总数 =", ev, " 全机共同重叠 =", cm, " 比例 = %.4f" % (cm/ev))
f = [x["sync_frac"] for x in s]
print("同步时间占比: n=%d 中位数=%.4f 范围=[%.4f, %.4f]" % (len(f), statistics.median(f), min(f), max(f)))
