"""Reassess frozen r1.2 M03 evidence under the user-authorized r1.2a rule.

This does not replay or change the algorithm and never launches SITL. All old
evidence and tested analysis sources must still match their recorded hashes.
Writes a new directory exclusively; existing evidence is never overwritten.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD_DIR = ROOT / "tmp_v05/r12_progress/reproducible_review_01"
OLD_READINESS = ROOT / "tmp_v05/r12/offline_readiness.json"
QUANTIZATION = ROOT / "tmp_v05/r12_progress/regression_sample_quantization.json"
LIMIT_S = 0.2
REASON = (
    "r1.2 requires the closest actual sample within the first hysteretic visit; "
    "the AC4 v2 baseline uses continuous closest points. At nominal 10 Hz, "
    "one agent's matching time may shift by one 0.1 s sample interval and "
    "the fleet D may shift by two intervals (0.2 s). The previous 0.05 s "
    "numeric bound was incompatible with that sample-based requirement."
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_hashes(mapping):
    for path, expected in mapping.items():
        require(digest(path) == expected, f"evidence/source hash changed: {path}")


def write_new(path, content):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(content, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    for name in ("review.json", "summary.json", "offline_readiness.json"):
        require(not (output / name).exists(), f"refusing existing output file: {output / name}")

    original = read(OLD_DIR / "review.json")
    old_summary = read(OLD_DIR / "summary.json")
    old_readiness = read(OLD_READINESS)
    quantization = read(QUANTIZATION)
    require(original["mapping_version"] == "ordered_route_progress_v2", "unexpected mapper")
    require(original["maximum_allowed_D_delta_s"] == 0.05, "old numeric rule changed")
    require(old_readiness["gates"] == {"M01": True, "M02": True, "M03": False},
            "unexpected old readiness gates")
    require(old_summary["report_sha256"] == digest(OLD_DIR / "review.json"),
            "old summary/report binding changed")
    require(all(test["returncode"] == 0 for test in original["tests"]), "old test failure")

    bindings = {str(path.resolve()): digest(path) for path in (
        OLD_DIR / "review.json", OLD_DIR / "summary.json", OLD_READINESS, QUANTIZATION,
    )}
    for mapping in (old_readiness["evidence_sha256"], old_readiness["analysis_source_sha256"],
                    original["code_sha256"], original["baseline_sha256"]):
        for path, sha in mapping.items():
            require(path not in bindings or bindings[path] == sha, f"inconsistent binding: {path}")
            bindings[path] = sha
    for test in original["tests"]:
        bindings[test["log"]] = test["log_sha256"]
    for case in original["cases"]:
        bindings.update(case["source_sha256"])
    verify_hashes(bindings)

    final = read(ROOT / "tmp_v04/ac4_v2_20261002/final_acceptance.json")["records"]
    spikes = read(ROOT / "tmp_v04/ac4_v2_20261002/offline_review_final.json")["wp_s_offline_reviews"]
    routes = [row for row in final if row.get("validation_id") in ("V02", "V03", "V04")]
    require(len(spikes) == 2 and [row["validation_id"] for row in routes] == ["V02", "V02", "V03", "V04"],
            "historical route inventory changed")
    baselines = {row["run_id"]: row for row in spikes + [row["ac4_v2"] for row in routes]}
    require(len(original["cases"]) == len(baselines) == 6, "expected six frozen history cases")
    comparisons, cases = [], []
    for case in original["cases"]:
        baseline = baselines[case["run_id"]]
        require(case["historical_sources_unchanged"] is True, "original history preservation failed")
        case_rows, verdicts = [], {}
        expected_rows = {}
        for channel in ("truth", "observation"):
            older, current = baseline["channels"][channel], case["channels"][channel]
            verdicts[channel] = dict(
                AC4_v2_within_tau=older["within_tau"], ordered_v2_within_tau=current["within_tau"],
                AC4_v2_crosscheck_within_tau=older["crosscheck_within_tau"],
                ordered_v2_crosscheck_within_tau=current["crosscheck_within_tau"],
                verdict_same=(older["within_tau"] == current["within_tau"] and
                              older["crosscheck_within_tau"] == current["crosscheck_within_tau"]),
            )
            require(verdicts[channel]["verdict_same"] == case["run_verdict_same"][channel],
                    "recorded run verdict comparison inconsistent")
            for phase, prior in older["per_phase"].items():
                for mapping in ("primary", "crosscheck"):
                    expected_rows[(channel, phase, mapping)] = (prior[mapping], current["per_phase"][phase][mapping])
        require(len(case["comparisons"]) == len(expected_rows) == 12, "phase comparison inventory changed")
        for previous in case["comparisons"]:
            key = (previous["channel"], previous["phase"], previous["mapping"])
            prior, current = expected_rows.pop(key)
            old_d, new_d = prior["D_s"], current["D_s"]
            delta = abs(old_d - new_d) if old_d is not None and new_d is not None else None
            same = prior["within_tau"] == current["within_tau"]
            old_pass = delta is not None and delta <= 0.05 and same
            require((old_d, new_d, delta, same, old_pass) == (
                previous["AC4_v2_D_s"], previous["ordered_v2_D_s"], previous["absolute_delta_s"],
                previous["verdict_same"], previous["pass_gate"]), "original comparison inconsistent")
            row = dict(run_id=case["run_id"], channel=key[0], phase=key[1], mapping=key[2],
                       AC4_v2_D_s=old_d, ordered_v2_D_s=new_d, absolute_delta_s=delta,
                       AC4_v2_within_tau=prior["within_tau"], ordered_v2_within_tau=current["within_tau"],
                       verdict_same=same, original_r12_0_05_s_pass=old_pass,
                       r12a_0_2_s_diagnostic_within_limit=(delta is not None and delta <= LIMIT_S),
                       soft_metric_regression_pass=same,
                       numeric_deviation_reason=REASON if delta else "unchanged",
                       original_comparison=previous)
            comparisons.append(row)
            case_rows.append(row)
        require(not expected_rows, "missing phase comparison")
        cases.append(dict(label=case["label"], run_id=case["run_id"], comparisons=case_rows,
                          run_verdict_comparison=verdicts, historical_sources_unchanged=True))

    failures = [dict(run_id=case["run_id"], **row) for case in original["cases"]
                for row in case["comparisons"] if not row["pass_gate"]]
    require(failures == old_summary["failures"] and len(failures) == 4, "old four failures changed")
    require(len(comparisons) == old_summary["total_comparisons"] == 72, "expected 72 comparisons")
    require(sum(row["original_r12_0_05_s_pass"] for row in comparisons) == old_summary["passed_comparisons"] == 68,
            "old comparison count changed")
    q_index = {(row["run_id"], row["channel"], row["phase"]): row for row in quantization}
    require(len(q_index) == 4, "expected four preserved quantization records")
    for failure in failures:
        evidence = q_index[(failure["run_id"], failure["channel"], failure["phase"])]
        require(evidence["absolute_D_delta_s"] == failure["absolute_delta_s"], "quantization delta changed")
        for changes in evidence["node_changes"].values():
            for change in changes:
                require(change["sample_actual_s"] - change["legacy_actual_s"] == change["sample_minus_legacy_s"],
                        "quantization arithmetic mismatch")

    verdicts_same = all(row["verdict_same"] for row in comparisons) and all(
        value["verdict_same"] for case in cases for value in case["run_verdict_comparison"].values())
    within_limit = all(row["r12a_0_2_s_diagnostic_within_limit"] for row in comparisons)
    # Under the general r1.2a rule a soft metric's numeric deviation is diagnostic.
    # This frozen M03 dataset also independently meets the requested 0.2 s bound.
    pass_gate = verdicts_same
    verify_hashes(bindings)
    report = dict(version="v05_r12a_frozen_m03_review_v1", generated_utc=datetime.now(timezone.utc).isoformat(),
                  mapping_version="ordered_route_progress_v2", algorithm_modified=False,
                  review_mode="hash_verified_reassessment_of_frozen_results_no_replay",
                  previous_rule="r1.2", current_rule="r1.2a", new_sitl_runs=0,
                  original_maximum_allowed_D_delta_s=0.05, revised_D_delta_diagnostic_limit_s=LIMIT_S,
                  numeric_rule_reason=REASON,
                  general_offline_regression_rule=dict(soft_metrics="verdict consistency; explain numeric deviations without stopping",
                                                       hard_metrics="original criteria unchanged"),
                  input_sha256=bindings, reviewer_sha256={str(Path(__file__).resolve()): digest(__file__)},
                  reused_tests=original["tests"], old_readiness_gates=old_readiness["gates"],
                  original_four_0_05_s_failures=failures, original_quantization_evidence=quantization,
                  cases=cases, all_verdicts_same=verdicts_same,
                  all_D_deltas_within_0_2_s=within_limit, pass_gate=pass_gate)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "review.json"
    write_new(report_path, report)
    summary = dict(version="v05_r12a_frozen_m03_summary_v1", report=str(report_path), report_sha256=digest(report_path),
                   pass_gate=pass_gate, tests_pass=True, tests_reused_after_source_hash_verification=True,
                   total_comparisons=len(comparisons), passed_comparisons=sum(row["soft_metric_regression_pass"] for row in comparisons),
                   original_0_05_s_passed_comparisons=68, preserved_old_failure_count=4,
                   all_verdicts_same=verdicts_same, all_D_deltas_within_0_2_s=within_limit,
                   maximum_absolute_D_delta_s=max(row["absolute_delta_s"] for row in comparisons),
                   all_bound_sources_unchanged=True, verified_file_count=len(bindings),
                   algorithm_modified=False, new_sitl_runs=0)
    write_new(output / "summary.json", summary)
    new_bindings = dict(old_readiness["evidence_sha256"])
    for path in (report_path, output / "summary.json", OLD_READINESS, QUANTIZATION, Path(__file__)):
        new_bindings[str(path.resolve())] = digest(path)
    readiness = dict(version="v05_r12_offline_readiness_v1", acceptance_revision="r1.2a",
                     route_progress_version="ordered_route_progress_v2",
                     gates=dict(M01=old_readiness["gates"]["M01"], M02=old_readiness["gates"]["M02"], M03=pass_gate),
                     evidence_sha256=new_bindings, analysis_source_sha256=old_readiness["analysis_source_sha256"],
                     stop_reason=None if pass_gate else "historical verdict changed",
                     new_sitl_runs=0, historical_attempts_consumed=2,
                     previous_readiness=str(OLD_READINESS), previous_readiness_unchanged=True,
                     numeric_D_diagnostic_limit_s=LIMIT_S, all_D_deltas_within_diagnostic_limit=within_limit)
    write_new(output / "offline_readiness.json", readiness)
    verify_hashes(bindings)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if not pass_gate:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
