"""Independent static verifier; intentionally does not import holdout.py.

Uses permutation matching and graph traversal instead of augmenting matching
and disjoint sets. Reads task inputs and identity manifests, never run results.
"""
import argparse
import copy
import hashlib
import itertools
import json
import math
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from swarm_sim.families import family_metadata
from swarm_sim.generation_v2 import normalize_profile
from swarm_sim.fast_dynamics.output_policy import assert_new_external_path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def project(spec):
    scenario = copy.deepcopy(spec["scenario"])
    if "platform" not in scenario and spec.get("schema_version") == 2:
        scenario["platform"] = spec["platform"]
    identity = family_metadata(scenario)
    shapes = []
    for r in scenario["regions"]:
        assert r["type"] == "rectangle"
        center = (r["min_east_m"] + r["width_m"]/2, r["min_north_m"] + r["height_m"]/2)
        shapes.append((r["width_m"], r["height_m"],
            sorted((v["east_m"]-center[0], v["north_m"]-center[1]) for v in scenario["vehicles"])))
    return identity, shapes


def similar(left, right):
    transforms = [lambda x,y: (x,y), lambda x,y: (-x,y), lambda x,y: (x,-y),
                  lambda x,y: (-x,-y), lambda x,y: (y,x), lambda x,y: (-y,x),
                  lambda x,y: (y,-x), lambda x,y: (-y,-x)]
    for aw, ah, ap in left:
        for bw, bh, bp in right:
            if len(ap) != len(bp):
                continue
            for number, transform in enumerate(transforms):
                tw, th = (bw, bh) if number < 4 else (bh, bw)
                if abs(aw-tw) > 1.000000001 or abs(ah-th) > 1.000000001:
                    continue
                points = [transform(x,y) for x,y in bp]
                if any(all(math.dist(a,b) <= 1.000000001 for a,b in zip(ap, perm))
                       for perm in itertools.permutations(points)):
                    return True
    return False


def verify(attempt):
    checks = []
    def check(name, condition):
        checks.append(dict(name=name, passed=bool(condition)))
        if not condition:
            raise AssertionError(name)

    reg = load(attempt / "registration.json")
    result = load(attempt / "evaluation_split.json")
    manifest = load(attempt / "freeze_manifest.json")
    check("frozen artifacts unchanged", all(digest(attempt/p) == d for p,d in manifest.items()))
    check("registration bound by split", digest(attempt/"registration.json") == result["registration_sha256"])
    check("code method and source indexes unchanged", all(digest(r["path"]) == r["sha256"] for r in reg["bindings"]+reg["inputs"]))
    expected_profile = normalize_profile(PROJECT / "generation_profiles/tri_intent_v06_production.json")
    expected_profile.update(master_seed=2026101203, base_scene_count=144)
    check("only authorized profile changes", expected_profile == reg["profile"])
    check("fixed generation and split parameters", reg["split_seed"] == result["seed"] == "2026101202"
          and reg["generation_seed"] == 2026101203 and reg["base_count"] == 144
          and reg["method"] == result["method"] == "rect_relative_d4_v1" and reg["tolerance_m"] == 1.0)
    expected_inputs = {str(Path(r["task_path"]).resolve()): r["task_sha256"] for r in load(reg["inputs"][0]["path"])}
    ignored = {"h02_v04_normalization_hashes.json", "intent_registry_DR130_golden.json", "v05_example_loader_baseline.json"}
    for line in Path(reg["inputs"][1]["path"]).read_text(encoding="utf-8-sig").splitlines():
        r = json.loads(line)
        if r["purpose"] == "generated_input" or (r["purpose"] == "known_development_fixture" and Path(r["path"]).name not in ignored):
            expected_inputs[str(Path(r["path"]).resolve())] = r["sha256"]
    for p in (PROJECT/"missions/v3").glob("*.json"):
        expected_inputs[str(p.resolve())] = digest(p)
    historical = load(attempt/"historical_inputs.json")
    check("historical scope complete", expected_inputs == {r["path"]:r["sha256"] for r in historical})
    old, old_hashes = {}, {}
    for r in historical:
        check_hash = digest(r["path"]) == r["sha256"]
        identity, shape = project(load(r["path"]))
        assert check_hash and identity["family_id"] == r["family_id"]
        old[r["family_id"]] = shape
        old_hashes[r["family_id"]] = identity["scene_content_sha256"]
    check("historical task hashes and identities", len(old) == reg["historical_families"])
    stored_old = load(attempt/"historical_geometry.json")
    check("historical geometry independently projected", all(
        stored_old[fid]["geometry"] == [dict(width=w,height=h,points=[list(p) for p in ps]) for w,h,ps in shapes]
        and stored_old[fid]["scene_content_sha256"] == old_hashes[fid] for fid,shapes in old.items()))
    bundle = attempt/"bundle"
    gen = load(bundle/"generation_manifest.json")
    check("generator artifacts unchanged", all(digest(bundle/p) == d for p,d in gen["artifact_sha256"].items()))
    check("all registered bases attempted once", [b["base_index"] for b in gen["bases"]] == list(range(144)))
    new, lineage = {}, {}
    for c in gen["candidates"]:
        for r in c["attempts"]:
            assert digest(bundle/r["task"]) == r["task_sha256"]
            identity, shape = project(load(bundle/r["task"]))
            assert identity["family_id"] == c["family_id"]
            new[identity["family_id"]] = shape
            lineage.setdefault(c["base_index"], set()).add(identity["family_id"])
    accepted = load(bundle/"mission_list.json")["missions"]
    check("three intents per admitted base", all(
        {r["intent"] for r in accepted if r["base_index"] == b["base_index"]} ==
        {"reconnaissance", "patrol", "rapid_passage"} for b in gen["bases"] if b["status"] == "accepted"))
    check("accepted task identities", all(digest(bundle/r["task"]) == r["task_sha256"] and
        project(load(bundle/r["task"]))[0]["family_id"] == r["family_id"] for r in accepted))
    adjacency = {fid:set() for fid in new}
    for members in lineage.values():
        for a,b in itertools.combinations(members,2):
            adjacency[a].add(b); adjacency[b].add(a)
    contacts = {}
    for a, shape in new.items():
        for b, old_shape in old.items():
            if a == b or similar(shape,old_shape):
                contacts.setdefault(a,set()).add(b)
    for a,b in itertools.combinations(new,2):
        if similar(new[a],new[b]):
            adjacency[a].add(b); adjacency[b].add(a)
    check("old near-duplicate contacts independently reproduced",
          {k:sorted(v) for k,v in contacts.items()} == result["direct_old_contacts"])
    unseen = set(new)
    rebuilt = []
    admitted = {r["family_id"] for r in accepted}
    while unseen:
        seed = min(unseen); pending = [seed]; members = set()
        while pending:
            node = pending.pop()
            if node in members: continue
            members.add(node); pending.extend(adjacency[node]-members)
        unseen -= members
        ids = sorted(members)
        cid = hashlib.sha256(json.dumps(ids,ensure_ascii=True,separators=(',',':')).encode()).hexdigest()
        touched = sorted(set().union(*(contacts.get(fid,set()) for fid in members)))
        accepted_ids = sorted(members & admitted)
        reason = "historical_contact" if touched else (None if accepted_ids else "planning_rejected_only")
        rebuilt.append(dict(component_id=cid,family_ids=ids,accepted_family_ids=accepted_ids,
                            historical_contacts=touched,exclusion_reason=reason,split_group=None))
    eligible = [r for r in rebuilt if r["exclusion_reason"] is None]
    for r in eligible:
        r["rank"] = hashlib.sha256(("2026101202|"+r["component_id"]).encode()).hexdigest()
    eligible.sort(key=lambda r:(r["rank"],r["component_id"]))
    for i,r in enumerate(eligible):
        r["split_group"] = ("calibration" if i < len(eligible)//2 else "blind_holdout") if len(eligible)>=2 else None
    check("full graph and exact allocation independently reproduced", sorted(rebuilt,key=lambda r:r["component_id"]) == result["components"])
    groups = {r["component_id"]:r for r in rebuilt}
    check("task roster complete", {r["task"] for r in accepted} == {r["task"] for r in result["tasks"]})
    for t in result["tasks"]:
        r = groups[t["component_id"]]
        assert t["family_id"] in r["family_ids"] and t["split_group"] == r["split_group"]
        assert t["execution_status"] == "NOT_RUN" and t["actual_result"] is None and not t["reference_episode_available"]
    check("task group and not-run claims consistent", True)
    check("sufficient eligible components", len(eligible)>=2 and result["effective_holdout_frozen"])
    check("no held-out execution products", not any(p.suffix.lower() in (".csv", ".parquet") or
        p.name in ("episode.json","labels.json","quality.json","completion.json") for p in bundle.rglob("*")))
    return dict(status="PASS", checks=checks, check_count=len(checks), counts=result["counts"],
                freeze_manifest_sha256=digest(attempt/"freeze_manifest.json"),
                verifier_sha256=digest(__file__), limitation="same author, independent algorithm; no flight or reference episodes")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--attempt", required=True)
    p.add_argument("--report", required=True)
    args = p.parse_args()
    output = assert_new_external_path(args.report)
    try:
        report = verify(Path(args.attempt))
    except Exception as exc:
        report = dict(status="FAIL", error=f"{type(exc).__name__}: {exc}", verifier_sha256=digest(__file__))
    with output.open("x",encoding="utf-8",newline="\n") as f:
        json.dump(report,f,ensure_ascii=False,indent=2); f.write("\n")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
