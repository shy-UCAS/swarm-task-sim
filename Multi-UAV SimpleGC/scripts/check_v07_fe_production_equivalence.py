"""S1a/S1b equivalence checks for the v0.7 first_edition production harness."""
from __future__ import annotations

import argparse
import json
import platform
import sys
import traceback
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scripts import run_v07_fe_production as prod
from scripts import v07_fe_production_core as core
from scripts.run_m3_r3_r1 import code_hashes
from scripts.run_m3_r3_r4 import pair_result
from scripts.run_v07_s2_expansion import classify, deep_diff, npz_diff, sha
from swarm_sim.fast_dynamics.reference_r3 import CONFIG_SHA256
from task_v07.criteria import CRITERIA_PATH, load_criteria
from task_v07.execution import FROZEN_SHA256
from task_v07.expansion.contracts import P0ContractError
from task_v07.expansion.sampling import sample_family_descriptors
from task_v07.unified.config import CONFIG_PATH as GENERATOR_CONFIG_PATH

DEFAULT_ROOT = PROJECT.parent.parent / "SwarmData" / "v07_first_edition_checks"
BASELINE_ROOT = PROJECT.parent.parent / "SwarmData" / "fast_dynamics" / "m3" / "m3_r3_r4_attempt01"
PLAN_PATH = PROJECT / "docs/v07/evidence/m3_r3/R0_validation_plan_amended.json"
S1B_SIDS = (
    "family_s15_1c267d4d7000043d_ext_001_regular",
    "family_s15_38bedc9d791d547b_ext_008_regular",
    "family_s15_1b876e6b8b6f70c6_ext_005_regular",
)
MODES = ("synchronous", "sequential")
MODE_JSON = ("labels.json", "prefix_labels.json", "task.json", "public_scene.json",
             "source.json", "metrics.json", "independent_exact_audit.json",
             "policy_geometry_audit.json", "truncation_check.json",
             "solo_overlay_comparison.json", "manifest.json")
MODE_NPZ = ("truth_10hz.npz", "model_input.npz", "frame_labels.npz")
MODE_CSV = ("truth.csv", "observations.csv")
SID_JSON = ("skeleton.json", "planning_checks.json", "timing_calibration.json",
            "timing_selection.json", "geometry_history.json", "candidate_search.json",
            "candidate_pool.json")
ALLOWED_LEAVES = {"amortized_skeleton_setup_s", "episode_postprocess_wall_s"}


def _base_fields(run_id, workers):
    if prod.git("status", "--porcelain"):
        raise core.ProductionError(3, "Worktree is not clean")
    hashes = code_hashes()
    return {
        "run_id": run_id,
        "created_utc": core.utc_iso(),
        "code_commit": prod.git("rev-parse", "HEAD"),
        "git_clean": True,
        "code_hashes": hashes,
        "reference_version": "r3",
        "r3_config_sha256": CONFIG_SHA256,
        "r2_frozen_sha256": FROZEN_SHA256,
        "criteria_version": load_criteria()["criteria_version"],
        "criteria_path": str(CRITERIA_PATH),
        "criteria_sha256": core.sha256_file(CRITERIA_PATH),
        "generator_config_path": str(GENERATOR_CONFIG_PATH),
        "generator_config_sha256": core.sha256_file(GENERATOR_CONFIG_PATH),
        "baseline_path": str(prod.BASELINE_PATH),
        "baseline_sha256": core.sha256_file(prod.BASELINE_PATH),
        "scene_layout": prod.SCENE_LAYOUT,
        "workers": workers,
        "planning_timeout_s": prod.DEFAULT_PLANNING_TIMEOUT_S,
        "episode_timeout_s": prod.DEFAULT_EPISODE_TIMEOUT_S,
        "FE_SCOPE": prod.fe_scope(),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "dry_run": False,
    }


def _stage_a_selected(run_dir, records, base):
    family_rows, descriptors = [], []
    discarded = 0
    for record in records:
        scene, family = prod._load_family(record)
        family_rows.append(prod._family_row(record, scene, family))
        raw = sample_family_descriptors((scene, family, prod.SLOTS_PER_FAMILY))
        regular, aborted = core.split_regular(raw)
        if len(regular) != prod.REGULAR_PER_FAMILY:
            raise P0ContractError(f"Family {record['family_id']} produced {len(regular)} regular descriptors")
        descriptors.extend(regular)
        discarded += aborted
    descriptors.sort(key=lambda row: row["skeleton_id"])
    descriptor_path = run_dir / "descriptors" / "descriptors.json"
    core.write_json(descriptor_path, descriptors)
    registration = {
        **{key: value for key, value in base.items() if key != "code_hashes"},
        "code_hashes_sha256": core.sha256_file(run_dir / "code_hashes.json"),
        "families_range": [min(row["candidate_index"] for row in family_rows),
                           max(row["candidate_index"] for row in family_rows) + 1],
        "family_rows": family_rows,
        "family_unsampleable": [],
        "slots_per_family": prod.SLOTS_PER_FAMILY,
        "subset": "regular",
        "discarded_aborted_count": discarded,
        "intents": list(core.INTENTS),
        "descriptor_count": len(descriptors),
        "descriptors_sha256": core.sha256_file(descriptor_path),
    }
    core.atomic_json(run_dir / "registration.json", registration)
    return registration, descriptors


def _new_check_dir(root, prefix):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    base = root / f"{prefix}_{core.utc_stamp()}"
    if not base.exists():
        return base
    suffix = 2
    while (base.with_name(f"{base.name}_{suffix}")).exists():
        suffix += 1
    return base.with_name(f"{base.name}_{suffix}")


def _normalizer(*roots):
    forms = []
    for root in roots:
        text = str(Path(root))
        forms.extend({text, text.replace("\\", "/"), text.replace("/", "\\")})
    forms.sort(key=len, reverse=True)
    def normalize(value):
        if isinstance(value, str):
            for form in forms:
                value = value.replace(form, "<RUN_ROOT>")
            return value
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        return value
    return normalize


def _is_allowed(path, cls):
    leaf = path.split(".")[-1].split("[")[0]
    return (cls.startswith("metadata:") or leaf in ALLOWED_LEAVES
            or leaf.endswith("_wall_s") or leaf == "scope")


def _json_diffs(name, reference, new, normalize, display=None):
    label = display or name
    ref = normalize(core.read_json(reference / name))
    cur = normalize(core.read_json(new / name))
    if name == "manifest.json":
        ref.pop("artifact_sha256", None)
        cur.pop("artifact_sha256", None)
    rows = []
    for diff in deep_diff(ref, cur):
        cls = classify(diff["path"])
        rows.append({"file": label, **diff, "class": cls,
                     "allowed": _is_allowed(diff["path"], cls)})
    return rows


def _mode_diffs(reference, new, normalize):
    rows = []
    for name in MODE_JSON:
        if (reference / name).exists() and (new / name).exists():
            rows.extend(_json_diffs(name, reference, new, normalize))
        else:
            rows.append({"file": name, "path": "<missing>", "class": "content",
                         "allowed": False, "reference": (reference / name).exists(),
                         "new": (new / name).exists()})
    for name in MODE_NPZ:
        if (reference / name).exists() and (new / name).exists():
            for key in npz_diff(reference / name, new / name):
                rows.append({"file": name, "path": key, "class": "content",
                             "allowed": False})
        else:
            rows.append({"file": name, "path": "<missing>", "class": "content",
                         "allowed": False})
    for name in MODE_CSV:
        if (reference / name).exists() and (new / name).exists():
            if sha(reference / name) != sha(new / name):
                rows.append({"file": name, "path": "<sha256>", "class": "content",
                             "allowed": False})
        else:
            rows.append({"file": name, "path": "<missing>", "class": "content",
                         "allowed": False})
    return rows


def _compare_sid(reference, new, normalize):
    rows = []
    ref_files = {path.relative_to(reference).as_posix() for path in reference.rglob("*")
                 if path.is_file() and "logs" not in path.parts}
    new_files = {path.relative_to(new).as_posix() for path in new.rglob("*")
                 if path.is_file() and "logs" not in path.parts}
    for name in sorted(ref_files - new_files):
        rows.append({"file": name, "path": "<missing_in_new>", "class": "content",
                     "allowed": False})
    for name in sorted(new_files - ref_files):
        rows.append({"file": name, "path": "<extra_in_new>", "class": "content",
                     "allowed": False})
    for mode in MODES:
        if (reference / mode).is_dir() and (new / mode).is_dir():
            rows.extend(_mode_diffs(reference / mode, new / mode, normalize))
        else:
            rows.append({"file": mode, "path": "<missing>", "class": "content",
                         "allowed": False})
    for name in SID_JSON:
        if (reference / name).exists() and (new / name).exists():
            rows.extend(_json_diffs(name, reference, new, normalize))
        else:
            rows.append({"file": name, "path": "<missing>", "class": "content",
                         "allowed": False})
    ref_geometry = {path.name for path in reference.glob("geometry_*") if path.is_dir()}
    new_geometry = {path.name for path in new.glob("geometry_*") if path.is_dir()}
    for name in sorted(ref_geometry ^ new_geometry):
        rows.append({"file": name, "path": "<geometry_missing>", "class": "content",
                     "allowed": False})
    for name in sorted(ref_geometry & new_geometry):
        ref_dir, new_dir = reference / name, new / name
        ref_json = {path.name for path in ref_dir.glob("*.json")}
        new_json = {path.name for path in new_dir.glob("*.json")}
        for missing in sorted(ref_json ^ new_json):
            rows.append({"file": f"{name}/{missing}", "path": "<missing>",
                         "class": "content", "allowed": False})
        for json_name in sorted(ref_json & new_json):
            rows.extend(_json_diffs(json_name, ref_dir, new_dir, normalize,
                                    display=f"{name}/{json_name}"))
        ref_npz = {path.name for path in ref_dir.glob("*.npz")}
        new_npz = {path.name for path in new_dir.glob("*.npz")}
        for missing in sorted(ref_npz ^ new_npz):
            rows.append({"file": f"{name}/{missing}", "path": "<missing>",
                         "class": "content", "allowed": False})
        for npz_name in sorted(ref_npz & new_npz):
            for key in npz_diff(ref_dir / npz_name, new_dir / npz_name):
                rows.append({"file": f"{name}/{npz_name}", "path": key,
                             "class": "content", "allowed": False})
    return rows


def s1a(root):
    baseline = core.read_json(prod.BASELINE_PATH)
    plan = core.read_json(PLAN_PATH)
    by_family = {}
    for record in baseline["families"]:
        by_family[record["family_id"]] = record
    jobs = plan["R4"]["jobs"]
    families = sorted({job["descriptor"]["family_id"] for job in jobs})
    regenerated = {}
    scenes = {}
    for family_id in families:
        scene, family = prod._load_family(by_family[family_id])
        scenes[family_id] = scene
        raw = sample_family_descriptors((scene, family, prod.SLOTS_PER_FAMILY))
        regular, _aborted = core.split_regular(raw)
        for descriptor in regular:
            regenerated[descriptor["skeleton_id"]] = descriptor
    mismatches = []
    for job in jobs:
        sid = job["descriptor"]["skeleton_id"]
        if sid not in regenerated:
            mismatches.append({"skeleton_id": sid, "path": "<missing_descriptor>"})
            continue
        for diff in deep_diff(job["descriptor"], regenerated[sid]):
            mismatches.append({"skeleton_id": sid, "path": f"descriptor.{diff['path']}",
                               "reference": diff["reference"], "new": diff["new"]})
        for diff in deep_diff(job["scene"], scenes[job["descriptor"]["family_id"]]):
            mismatches.append({"skeleton_id": sid, "path": f"scene.{diff['path']}",
                               "reference": diff["reference"], "new": diff["new"]})
    result = {
        "stage": "S1a",
        "status": "PASS" if len(jobs) == 38 and not mismatches else "FAIL",
        "families": len(families),
        "skeletons": len(jobs),
        "mismatch_count": len(mismatches),
        "first_mismatches": mismatches[:20],
        "code_commit": prod.git("rev-parse", "HEAD"),
    }
    run_dir = _new_check_dir(root, "s1a")
    run_dir.mkdir()
    core.atomic_json(run_dir / "s1a.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=1), flush=True)
    return 0 if result["status"] == "PASS" else 1


def s1b(root, workers):
    baseline = core.read_json(prod.BASELINE_PATH)
    by_family = {record["family_id"]: record for record in baseline["families"]}
    family_ids = sorted({sid.rsplit("_ext_", 1)[0] for sid in S1B_SIDS})
    records = [by_family[family_id] for family_id in family_ids]
    run_dir = _new_check_dir(root, "s1b")
    run_dir.mkdir(parents=True)
    for name in ("planning", "episodes", "qc", "status", "logs"):
        (run_dir / name).mkdir()
    base = _base_fields(run_dir.name, workers)
    core.write_json(run_dir / "code_hashes.json", base["code_hashes"])
    registration, descriptors = _stage_a_selected(run_dir, records, base)
    code = prod.run_scheduler(run_dir, registration, descriptors, workers,
                              prod.DEFAULT_PLANNING_TIMEOUT_S, prod.DEFAULT_EPISODE_TIMEOUT_S,
                              single_skeletons=set(S1B_SIDS))
    statuses = prod.load_statuses(run_dir)
    checks = {}
    for sid in S1B_SIDS:
        b = statuses["B"].get(sid)
        c = statuses["C"].get(sid)
        paired = hard = None
        if c and c.get("rows"):
            result = pair_result(run_dir / "episodes", sid, c["rows"], CONFIG_SHA256)
            paired = result["paired"]
            hard = result["hard_physical_audit_passed"]
        checks[sid] = {
            "b": b.get("status") if b else None,
            "c": c.get("status") if c else None,
            "paired": paired,
            "hard_physical_audit_passed": hard,
        }
    normalize = _normalizer(BASELINE_ROOT, run_dir, run_dir / "episodes")
    comparisons = {}
    content = []
    allowed = []
    for sid in S1B_SIDS:
        reference = BASELINE_ROOT / sid
        new = run_dir / "episodes" / sid
        if not reference.exists() or not new.exists():
            content.append({"skeleton_id": sid, "path": "<missing_root>",
                            "class": "content", "allowed": False})
            continue
        rows = _compare_sid(reference, new, normalize)
        comparisons[sid] = {"differences": len(rows),
                            "content": sum(not row["allowed"] for row in rows),
                            "allowed": sum(row["allowed"] for row in rows)}
        content.extend({"skeleton_id": sid, **row} for row in rows if not row["allowed"])
        allowed.extend({"skeleton_id": sid, **row} for row in rows if row["allowed"])
    passed = (code == 0 and not content
              and all(value["b"] == "PASS" and value["c"] == "PAIRED"
                      and value["paired"] is True and value["hard_physical_audit_passed"] is True
                      for value in checks.values()))
    result = {
        "stage": "S1b",
        "status": "PASS" if passed else "FAIL",
        "exit_code": code,
        "skeletons": list(S1B_SIDS),
        "checks": checks,
        "comparison": comparisons,
        "content_difference_count": len(content),
        "allowed_difference_count": len(allowed),
        "first_content_differences": content[:20],
        "allowed_differences": allowed,
        "code_commit": prod.git("rev-parse", "HEAD"),
        "run_dir": str(run_dir),
    }
    core.atomic_json(run_dir / "s1b.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=1), flush=True)
    return 0 if passed else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("s1a", "s1b"), required=True)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        return s1a(args.root) if args.stage == "s1a" else s1b(args.root, args.workers)
    except core.ProductionError as exc:
        print(json.dumps({"status": "REFUSED", "code": exc.code, "reason": str(exc),
                          "detail": exc.detail}, ensure_ascii=False), flush=True)
        return exc.code
    except P0ContractError as exc:
        print(json.dumps({"status": "P0_STOP", "reason": str(exc)}, ensure_ascii=False), flush=True)
        return 2
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
