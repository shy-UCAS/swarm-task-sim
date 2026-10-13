"""Static, preregistered holdout preparation. Never executes a vehicle/observer.

The two CLI steps deliberately separate registration from generation. Existing
evidence is immutable; all large manifests live under the external output root.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from ..families import family_metadata
from ..generation_v2 import generate_v2, normalize_profile
from .output_policy import assert_created_within, assert_new_attempt_path

GENERATION_SEED = 2026101203
BASE_COUNT = 144
SPLIT_SEED = "2026101202"
METHOD = "rect_relative_d4_v1"
TOLERANCE_M = 1.0
EPSILON_M = 1e-9
NON_TASK_FIXTURES = {"h02_v04_normalization_hashes.json",
                     "intent_registry_DR130_golden.json", "v05_example_loader_baseline.json"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_new_json(path, data):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def checked_json(path, expected):
    # Hash and parse the same bytes, including when the original file is replaced.
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"source identity changed: {path}")
    return json.loads(raw.decode("utf-8-sig"))


def task_scenario(spec):
    scenario = copy.deepcopy(spec["scenario"])
    if "platform" not in scenario and spec.get("schema_version") == 2:
        scenario["platform"] = copy.deepcopy(spec["platform"])
    return scenario


def geometry(spec):
    """Conservative rectangle views; ignores non-position fields by design."""
    scenario = task_scenario(spec)
    vehicles = scenario["vehicles"]
    if not vehicles or not scenario["regions"]:
        raise ValueError("empty geometry cannot be certified")
    views = []
    for region in scenario["regions"]:
        if region["type"] != "rectangle":
            raise ValueError("unregistered region geometry")
        w, h = region["width_m"], region["height_m"]
        cx, cy = region["min_east_m"] + w / 2, region["min_north_m"] + h / 2
        points = sorted((v["east_m"] - cx, v["north_m"] - cy) for v in vehicles)
        values = [w, h, cx, cy, *(x for p in points for x in p)]
        if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x)
               for x in values) or min(w, h) <= 0:
            raise ValueError("invalid physical geometry")
        views.append({"width": w, "height": h, "points": points})
    return views


def matching_within(left, right, tolerance):
    """Bipartite matching, not nearest-neighbour reuse (also supports old N=6)."""
    choices = [[j for j, q in enumerate(right) if math.dist(p, q) <= tolerance + EPSILON_M]
               for p in left]
    matched = {}

    def assign(i, seen):
        for j in choices[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in matched or assign(matched[j], seen):
                matched[j] = i
                return True
        return False

    return len(left) == len(right) and all(assign(i, set()) for i in range(len(left)))


def near(left_views, right_views, tolerance=TOLERANCE_M):
    for a, b in itertools.product(left_views, right_views):
        if len(a["points"]) != len(b["points"]):
            continue
        for swap in (False, True):
            w, h = (b["height"], b["width"]) if swap else (b["width"], b["height"])
            if max(abs(a["width"] - w), abs(a["height"] - h)) > tolerance + EPSILON_M:
                continue
            for sx, sy in itertools.product((-1, 1), repeat=2):
                points = [(sx * (y if swap else x), sy * (x if swap else y))
                          for x, y in b["points"]]
                if matching_within(a["points"], points, tolerance):
                    return True
    return False


def component_id(families):
    ids = sorted(set(families))
    if not ids or any(not re.fullmatch(r"scene_[0-9a-f]{20}", i) for i in ids):
        raise ValueError("component requires actual scene_content_v1 family IDs")
    raw = json.dumps(ids, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def split_components(components):
    seen = set()
    ranked = []
    for families in components:
        ids = sorted(set(families))
        if seen.intersection(ids):
            raise ValueError("family occurs in multiple components")
        seen.update(ids)
        cid = component_id(ids)
        rank = hashlib.sha256(f"{SPLIT_SEED}|{cid}".encode("utf-8")).hexdigest()
        ranked.append(dict(component_id=cid, family_ids=ids, rank=rank))
    ranked.sort(key=lambda r: (r["rank"], r["component_id"]))
    ready = len(ranked) >= 2
    for i, record in enumerate(ranked):
        record["split_group"] = ("calibration" if i < len(ranked) // 2 else "blind_holdout") if ready else None
    return ranked


def build_registry(old, new, tasks):
    """Union all new lineage/geometry edges; old-contact propagates over components."""
    parent = {fid: fid for fid in new}

    def find(fid):
        while parent[fid] != fid:
            parent[fid] = parent[parent[fid]]
            fid = parent[fid]
        return fid

    def union(a, b):
        parent[find(b)] = find(a)

    edges, old_contacts, bases = [], {}, {}
    for fid, record in sorted(new.items()):
        for base in record["bases"]:
            if base in bases:
                union(fid, bases[base])
                edges.append(dict(left=fid, right=bases[base], kind="new_base_lineage"))
            else:
                bases[base] = fid
        for oid, historical in old.items():
            if fid == oid and record["scene_content_sha256"] != historical["scene_content_sha256"]:
                raise ValueError("short family ID collision")
            if fid == oid or near(record["geometry"], historical["geometry"]):
                old_contacts.setdefault(fid, []).append(oid)
    for a, b in itertools.combinations(sorted(new), 2):
        if near(new[a]["geometry"], new[b]["geometry"]):
            union(a, b)
            edges.append(dict(left=a, right=b, kind=METHOD))
    grouped = {}
    for fid in new:
        grouped.setdefault(find(fid), []).append(fid)
    accepted = {t["family_id"] for t in tasks}
    components, eligible = [], []
    for ids in grouped.values():
        ids.sort()
        contacts = sorted({o for fid in ids for o in old_contacts.get(fid, [])})
        accepted_ids = sorted(accepted.intersection(ids))
        reason = "historical_contact" if contacts else (None if accepted_ids else "planning_rejected_only")
        record = dict(component_id=component_id(ids), family_ids=ids,
                      accepted_family_ids=accepted_ids, historical_contacts=contacts,
                      exclusion_reason=reason, split_group=None)
        components.append(record)
        if reason is None:
            eligible.append(ids)
    ranked = split_components(eligible)
    assignments = {r["component_id"]: r for r in ranked}
    family_to_component = {}
    for record in components:
        if record["component_id"] in assignments:
            record.update(assignments[record["component_id"]])
        for fid in record["family_ids"]:
            family_to_component[fid] = record
    result_tasks = []
    for task in tasks:
        component = family_to_component[task["family_id"]]
        result_tasks.append(dict(task, component_id=component["component_id"],
            split_group=component["split_group"], exclusion_reason=component["exclusion_reason"],
            execution_status="NOT_RUN", actual_result=None, reference_episode_available=False))
    return dict(status="FROZEN_INPUTS_ONLY" if len(ranked) >= 2 else "BLOCKED",
        effective_holdout_frozen=len(ranked) >= 2, seed=SPLIT_SEED, method=METHOD,
        counts=dict(old_families=len(old), new_candidate_families=len(new),
                    accepted_families=len(accepted), eligible_components=len(ranked),
                    excluded_components=sum(c["exclusion_reason"] is not None for c in components),
                    calibration_components=sum(c["split_group"] == "calibration" for c in components),
                    blind_components=sum(c["split_group"] == "blind_holdout" for c in components)),
        components=sorted(components, key=lambda r: r["component_id"]),
        tasks=result_tasks, new_edges=edges, direct_old_contacts=old_contacts)


def _add_family(index, spec):
    scenario = task_scenario(spec)
    metadata = family_metadata(scenario)
    fid = metadata["family_id"]
    if fid in index and index[fid]["scene_content_sha256"] != metadata["scene_content_sha256"]:
        raise ValueError("short family ID collision")
    if fid not in index:
        index[fid] = dict(metadata, geometry=geometry(spec))
    return fid


def register(attempt, root, project, source_records, inventory, method_path):
    attempt = assert_new_attempt_path(attempt, root)
    project = Path(project)
    profile = normalize_profile(project / "generation_profiles/tri_intent_v06_production.json")
    profile.update(master_seed=GENERATION_SEED, base_scene_count=BASE_COUNT)
    # Do not create any output until all historical inputs have passed identity checks.
    source_records, inventory = Path(source_records), Path(inventory)
    files = {}
    for row in read_json(source_records):
        files[str(Path(row["task_path"]).resolve())] = row["task_sha256"]
    ignored = []
    for line in inventory.read_text(encoding="utf-8-sig").splitlines():
        row = json.loads(line)
        if row["purpose"] not in ("generated_input", "known_development_fixture"):
            continue
        path = Path(row["path"])
        if row["purpose"] == "known_development_fixture" and path.name in NON_TASK_FIXTURES:
            ignored.append(dict(path=str(path), reason="named non-TaskSpec fixture; not opened"))
            continue
        key = str(path.resolve())
        if key in files and files[key] != row["sha256"]:
            raise ValueError(f"conflicting historical identity: {path}")
        files[key] = row["sha256"]
    for path in (project / "missions/v3").glob("*.json"):
        files[str(path.resolve())] = sha256(path)
    old, file_index = {}, []
    for path, digest in sorted(files.items()):
        spec = checked_json(path, digest)
        fid = _add_family(old, spec)
        file_index.append(dict(path=path, sha256=digest, family_id=fid))
    # Bind all Python source, not merely the top-level wrapper or generator.
    code = sorted((project / "swarm_sim").rglob("*.py"))
    code += [project / "scripts/prepare_fast_dynamics_holdout.py", Path(method_path)]
    bindings = [dict(path=str(p.resolve()), sha256=sha256(p)) for p in code]
    attempt.mkdir(parents=True, exist_ok=False)
    assert_created_within(attempt, root)
    write_new_json(attempt / "historical_inputs.json", file_index)
    write_new_json(attempt / "historical_geometry.json", old)
    registration = dict(schema_version=1, source_id="m2_02b_seed2026101203_v1",
        created_utc=datetime.now(timezone.utc).isoformat(), output_root=str(Path(root).resolve()),
        profile=profile, generation_seed=GENERATION_SEED, base_count=BASE_COUNT,
        split_seed=SPLIT_SEED, method=METHOD, tolerance_m=TOLERANCE_M,
        bindings=bindings, historical_files=len(file_index), historical_families=len(old),
        excluded_non_task_fixtures=ignored,
        inputs=[dict(path=str(p.resolve()), sha256=sha256(p)) for p in
                (source_records, inventory, attempt / "historical_inputs.json", attempt / "historical_geometry.json")])
    write_new_json(attempt / "registration.json", registration)
    return dict(registration=str(attempt / "registration.json"),
                sha256=sha256(attempt / "registration.json"), historical_files=len(file_index), historical_families=len(old))


def freeze(registration_path, expected_sha256):
    registration_path = Path(registration_path).resolve()
    reg = checked_json(registration_path, expected_sha256)
    attempt = registration_path.parent
    root = reg["output_root"]
    bundle = assert_new_attempt_path(attempt / "bundle", root)
    for record in reg["bindings"] + reg["inputs"]:
        if sha256(record["path"]) != record["sha256"]:
            raise ValueError(f"registered source changed: {record['path']}")
    for record in read_json(attempt / "historical_inputs.json"):
        if sha256(record["path"]) != record["sha256"]:
            raise ValueError(f"historical input changed: {record['path']}")
    manifest = generate_v2(reg["profile"], bundle)
    assert_created_within(bundle, root)
    old, new, tasks = read_json(attempt / "historical_geometry.json"), {}, []
    for candidate in manifest["candidates"]:
        for record in candidate["attempts"]:
            spec = checked_json(bundle / record["task"], record["task_sha256"])
            fid = _add_family(new, spec)
            if fid != candidate["family_id"]:
                raise ValueError("candidate family mismatch")
            if len(new[fid]["geometry"]) != 1 or len(spec["scenario"]["vehicles"]) not in (2, 3, 4) or spec["scenario"]["restricted_regions"]:
                raise ValueError("new scene outside registered geometry scope")
            bases = new[fid].setdefault("bases", [])
            if candidate["base_index"] not in bases:
                bases.append(candidate["base_index"])
    for entry in read_json(bundle / "mission_list.json")["missions"]:
        spec = checked_json(bundle / entry["task"], entry["task_sha256"])
        if family_metadata(spec)["family_id"] != entry["family_id"]:
            raise ValueError("accepted task family mismatch")
        tasks.append({key: entry[key] for key in ("mission_id", "base_index", "family_id",
                        "scene_content_sha256", "intent", "flight_pattern", "task", "task_sha256")})
        tasks[-1]["vehicle_count"] = len(spec["scenario"]["vehicles"])
    result = build_registry(old, new, tasks)
    result.update(source_id=reg["source_id"], registration_sha256=expected_sha256,
                  bundle=str(bundle), generation_counts=manifest["counts"],
                  generation_manifest_sha256=sha256(bundle / "generation_manifest.json"))
    write_new_json(attempt / "candidate_geometry.json", new)
    write_new_json(attempt / "evaluation_split.json", result)
    artifact_index = {p.relative_to(attempt).as_posix(): sha256(p)
                      for p in sorted(attempt.rglob("*.json"))}
    write_new_json(attempt / "freeze_manifest.json", artifact_index)
    return {key: result[key] for key in ("status", "counts", "generation_counts")}
