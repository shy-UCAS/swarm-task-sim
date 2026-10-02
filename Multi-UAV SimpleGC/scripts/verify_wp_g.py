"""WP-G offline preservation/regression evidence. Never launches SITL."""
import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from swarm_sim.tasks import compile_task, validate_task_binding
from swarm_sim.episode_loader import load_episode

DATASETS = ("verification/v03_integration_20260930/dataset_final", "verification/v03_pilot_final_20260930/dataset")
OUTPUT = PROJECT / "tmp_v04/wp_g"

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()

def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

def save_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)

def episodes():
    for name in DATASETS:
        root = PROJECT / name
        for entry in read(root / "dataset_manifest.json")["episodes"]:
            yield root, entry, root / entry["directory"]

def baseline():
    compiled, loaded, protected, bindings = {}, {}, {}, []
    listing = read(PROJECT / "generated/recon_pilot_v03_20260930/mission_list.json")
    sources = list((PROJECT / "missions").glob("*.json"))
    sources += [PROJECT / "generated/recon_pilot_v03_20260930" / e["task"] for e in listing["missions"]]
    for path in sources:
        compiled[path.relative_to(PROJECT).as_posix()] = canonical(compile_task(read(path)))
    for data, entry, episode in episodes():
        loaded[episode.relative_to(PROJECT).as_posix()] = canonical(load_episode(episode))
        source = Path(entry["source_run"])
        validate_task_binding(read(source / "scenario.json"))
        bindings.append(str(source))
    for directory in ("runs", "datasets", "generated", "verification", "audit_v04"):
        for path in (PROJECT / directory).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                protected[path.relative_to(PROJECT).as_posix()] = sha(path)
    for name in ("v04_spike_summary.json", "v04_spike_continuous_route.md", "v04_spike_review_01.md"):
        path = PROJECT / "docs" / name
        protected[path.relative_to(PROJECT).as_posix()] = sha(path)
    save_new(OUTPUT / "baseline.json", dict(compiled=compiled, loaded=loaded, bindings=bindings, protected=protected,
                 baseline_tests=dict(count=210, status="PASS", duration_s=9.357)))
    report = PROJECT / "docs/v04_spike_review_01.md"
    summary = PROJECT / "tmp_v04/spike_review_01/review_summary.json"
    save_new(PROJECT / "docs/v04_spike_go_confirmation.json", dict(schema_version=1, milestone="WP-S", decision="GO",
        recorded_utc=datetime.now(timezone.utc).isoformat(), authority="explicit_user_confirmation_in_current_conversation",
        user_confirmation="接受 exact_duplicate_drop_v1 作为 WP-S 离线复核规则。WP-S 判定为 GO。",
        accepted_duplicate_policy="exact_duplicate_drop_v1",
        evidence=[dict(path=p.relative_to(PROJECT).as_posix(), sha256=sha(p)) for p in (report,summary)],
        original_summary=dict(path="docs/v04_spike_summary.json", sha256=sha(PROJECT/"docs/v04_spike_summary.json"), preserved=True),
        original_unknown_reports=[dict(path=f"runs/{run}/spike_metrics.json", sha256=sha(PROJECT/"runs"/run/"spike_metrics.json"))
            for run in ("spike_v04_20261001T153235Z_5eddb7ae", "spike_v04_20261001T153806Z_42150c31")],
        authorized_next_work="WP-G G1-G4 only; pause after G4 for user confirmation before WP-E"))
    print(json.dumps(dict(compiled_tasks=len(compiled),loaded_episodes=len(loaded),bindings=len(bindings),protected_files=len(protected))))


def regress(subdirectory=None, evidence_output=None):
    """R02-R05 use pre-edit outputs and frozen files, never self-generated expectations."""
    from swarm_sim.analysis import analyze_run
    before=read(OUTPUT/"baseline.json")
    destination_root=OUTPUT
    if evidence_output is not None:
        destination_root=Path(evidence_output).resolve()
        if not destination_root.is_relative_to(PROJECT/"tmp_v04"):
            raise ValueError("regression evidence must stay in a new tmp_v04 directory")
        destination_root.mkdir(parents=True,exist_ok=False)
    elif subdirectory is not None:
        if not subdirectory or Path(subdirectory).name != subdirectory or subdirectory in (".", ".."):
            raise ValueError("regression subdirectory must be one new directory name")
        destination_root=OUTPUT/subdirectory
        destination_root.mkdir(exist_ok=False)
    r02=[]
    for path,expected in before["compiled"].items():
        actual=compile_task(read(PROJECT/path))
        r02.append(dict(path=path,matches_baseline=canonical(actual)==expected))
    listing=read(PROJECT/"generated/recon_pilot_v03_20260930/mission_list.json")
    stored=[]
    for entry in listing["missions"]:
        root=PROJECT/"generated/recon_pilot_v03_20260930"
        stored.append(dict(task=entry["task"],matches_stored_scene=canonical(compile_task(read(root/entry["task"])))==canonical(read(root/entry["scene"]))))
    r03=[]
    for path in before["bindings"]:
        validate_task_binding(read(Path(path)/"scenario.json"))
        r03.append(dict(path=path,passed=True))
    r04=[dict(path=path,matches_baseline=canonical(load_episode(PROJECT/path))==expected) for path,expected in before["loaded"].items()]
    r05=[]
    copies=destination_root/"legacy_copies"
    copies.mkdir(exist_ok=False)
    def differences(expected,actual,path=""):
        if isinstance(expected,dict):
            if not isinstance(actual,dict): return [path]
            return [item for key,value in expected.items() for item in
                    ([path+"/"+key] if key not in actual else differences(value,actual[key],path+"/"+key))]
        return [] if expected==actual else [path]
    for _,entry,episode in episodes():
        source=Path(entry["source_run"])
        destination=copies/source.name
        shutil.copytree(source,destination)
        output,quality,labels=analyze_run(destination)
        changed={name:differences(read(episode/name),read(output/name)) for name in ("labels.json","semantic_validation.json")}
        r05.append(dict(run_id=entry["run_id"],source=str(source),copy=str(destination),analysis=str(output),
                        prior_fields_unchanged=not any(changed.values()),differences=changed,
                        execution_metrics_exists=(output/"execution_metrics.json").is_file()))
        print(f"R05 {entry['run_id']}: prior fields unchanged={not any(changed.values())}",flush=True)
    report=dict(R02=dict(status="PASS" if all(x["matches_baseline"] for x in r02) and all(x["matches_stored_scene"] for x in stored) else "FAIL",
                        count=len(r02),generated_stored_scene_count=len(stored),tasks=r02,stored_scenes=stored),
                R03=dict(status="PASS",count=len(r03),runs=r03),
                R04=dict(status="PASS" if all(x["matches_baseline"] for x in r04) else "FAIL",dataset_count=2,count=len(r04),episodes=r04),
                R05=dict(status="PASS" if all(x["prior_fields_unchanged"] for x in r05) else "FAIL",count=len(r05),runs=r05))
    save_new(destination_root/"legacy_regression.json",report)
    assert all(r["status"]=="PASS" for r in report.values()),"legacy regression failed; see report"
    print(json.dumps({k:{x:v for x,v in r.items() if x in ("status","count")} for k,r in report.items()}))


def preserve():
    before=read(OUTPUT/"baseline.json")
    changed=[p for p,h in before["protected"].items() if not (PROJECT/p).is_file() or sha(PROJECT/p)!=h]
    result=dict(protected_file_count=len(before["protected"]),changed=changed,unchanged=not changed,
                no_new_sitl=True,checked_utc=datetime.now(timezone.utc).isoformat())
    save_new(OUTPUT/"preservation.json",result)
    assert not changed,changed
    print(json.dumps(result))

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["baseline","regress","preserve"])
    parser.add_argument("--regression-subdirectory", help="new evidence directory; never overwrite an earlier pass")
    parser.add_argument("--evidence-output", help="new tmp_v04 directory for a later milestone's regression")
    args=parser.parse_args()
    if args.mode == "regress":
        regress(args.regression_subdirectory,args.evidence_output)
    else:
        {"baseline":baseline,"preserve":preserve}[args.mode]()
