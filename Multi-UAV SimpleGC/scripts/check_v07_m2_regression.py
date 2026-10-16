"""Q-C: compare the eight unchanged vertical episodes, without simulation."""
import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from task_v07.io import read_json, sha
from scripts.run_v07_s2_expansion import REFERENCE_SLICE, deep_diff


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt", type=Path)
    args = parser.parse_args()
    reference = REFERENCE_SLICE
    skeletons = sorted(p for p in reference.glob("family_*_s2r3_sk[0-9][0-9]") if p.is_dir())
    if len(skeletons) != 4:
        raise ValueError("Expected the four registered vertical-slice skeletons")
    rows = []
    for skeleton in skeletons:
        for mode in ("synchronous", "sequential"):
            old = skeleton / mode
            new = args.attempt / skeleton.name / mode
            files = {}
            for name in ("truth.csv", "truth_10hz.npz"):
                files[name] = {"baseline_sha256": sha(old / name), "new_sha256": sha(new / name),
                               "byte_identical": (old / name).read_bytes() == (new / name).read_bytes()}
            labels = {}
            for name in ("labels.json", "prefix_labels.json"):
                differences = deep_diff(read_json(old / name), read_json(new / name))
                labels[name] = {"field_identical": not differences, "differences": differences,
                                "baseline_sha256": sha(old / name), "new_sha256": sha(new / name)}
            rows.append({"episode": f"{skeleton.name}/{mode}", "trajectory_files": files, "labels": labels,
                         "independent_audit_status": read_json(new / "independent_exact_audit.json")["status"]})
    passed = all(all(item["byte_identical"] for item in row["trajectory_files"].values()) and
                 all(item["field_identical"] for item in row["labels"].values()) and
                 row["independent_audit_status"] == "PASS" for row in rows)
    result = {"status": "PASS" if passed else "P0_STOP", "baseline_commit": "e1fca53",
              "baseline_attempt": str(reference), "new_attempt": str(args.attempt),
              "scope": "Q-C vertical eight only; unchanged M1 legacy label path; no extension comparisons",
              "episodes": len(rows), "trajectory_files_byte_identical": sum(
                  item["byte_identical"] for row in rows for item in row["trajectory_files"].values()),
              "label_files_field_identical": sum(
                  item["field_identical"] for row in rows for item in row["labels"].values()),
              "rows": rows}
    command_receipt = args.attempt / "regression_comparison.json"
    if command_receipt.exists():
        command = read_json(command_receipt)
        result["full_command_summary"] = {key: command.get(key) for key in
            ("status", "episodes", "baseline_counts", "content_difference_count", "total_wall_s", "not_executed")}
        result["full_command_summary"]["episode_content_differences_by_kind"] = {
            kind: sum(row["content_differences"] for row in command.get("episode_comparisons", [])
                      if row["baseline_kind"] == kind)
            for kind in ("vertical_slice", "transit", "new_roles")}
    path = PROJECT / "docs/v07/evidence/m2/qc_regression.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
