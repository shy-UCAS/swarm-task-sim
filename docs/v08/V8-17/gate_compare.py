"""V8-17 两意图字节门禁比较（只读）：对登记的快批 20 键，逐合同比较 baseline/contracts/<id>/ 与
repeat/contracts/<id>/ 的递归文件集合与原始 bytes（joint_monitoring.compare_dirs，排除清单为空）。
两边都必须存在 contract.json，避免空集合相等的假通过。
用法：python -B gate_compare.py <intent> <phase> <baseline_root> <repeat_root> <out.json>
退出码：0 全部一致；4 有差异或缺目录。"""
import json
import sys
from pathlib import Path

PROJ = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08\Multi-UAV SimpleGC")
sys.path.insert(0, str(PROJ))
HERE = Path(__file__).resolve().parent


def main():
    from v08.runner.joint_monitoring import compare_dirs
    intent, phase, base, rep, out = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])
    keys = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))["keys"]["quick20"]
    rows = json.loads((rep / "records.json").read_text(encoding="utf-8"))
    comps = []
    for cid in keys:
        left, right = base / "contracts" / cid, rep / "contracts" / cid
        exists = (left / "contract.json").is_file() and (right / "contract.json").is_file()
        cmp_ = compare_dirs(left, right) if exists else {"file_sets_equal": False, "bytes_equal": False, "files": []}
        first = (cmp_.get("differing") or cmp_.get("only_source") or cmp_.get("only_repeat") or [None])[0]
        comps.append({"contract_id": cid, "both_exist": exists, "file_sets_equal": bool(cmp_["file_sets_equal"]),
                      "bytes_equal": bool(cmp_["bytes_equal"]), "n_files": len(cmp_.get("files", [])),
                      "differing": cmp_.get("differing", []), "only_baseline": cmp_.get("only_source", []),
                      "only_repeat": cmp_.get("only_repeat", []), "first_difference": first})
    doc = {"intent": intent, "phase": phase, "baseline": str(base.resolve()), "repeat": str(rep.resolve()),
           "keys": keys, "records_keys_equal": sorted(r["contract_id"] for r in rows) == sorted(keys),
           "exclusions": [], "comparisons": comps,
           "equal_count": sum(c["both_exist"] and c["file_sets_equal"] and c["bytes_equal"] for c in comps),
           "total": len(keys)}
    doc["all_equal"] = doc["equal_count"] == len(keys) and doc["records_keys_equal"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("intent", "phase", "equal_count", "total", "records_keys_equal", "all_equal")},
                     ensure_ascii=False))
    sys.exit(0 if doc["all_equal"] else 4)


if __name__ == "__main__":
    main()
