"""Import complete frozen families for a pilot; never regenerate production inputs."""
import copy
import shutil
from pathlib import Path

from . import parallel_batch as batch
from .generation import checked_path, file_hash, verify_generation
from .protocol import apply_execution_override, semantic_protocol
from .time_contract import is_sim_time
from .quality import policy_hash, resolve_policy


def select_listing(listing, mission_ids):
    if (not isinstance(mission_ids, list) or not mission_ids
            or any(not isinstance(m, str) for m in mission_ids)
            or len(set(mission_ids)) != len(mission_ids)):
        raise ValueError("mission_ids must be a nonempty unique string list")
    selected = set(mission_ids)
    entries = listing["missions"]
    if selected - {e["mission_id"] for e in entries}:
        raise ValueError("unknown mission_ids in subset")
    families = {e["family_id"] for e in entries if e["mission_id"] in selected}
    if {e["mission_id"] for e in entries if e["family_id"] in families} != selected:
        raise ValueError("subset must contain complete families")
    result = copy.deepcopy(listing)
    result["missions"] = [e for e in result["missions"] if e["mission_id"] in selected]
    return result


def tree_hashes(directory):
    root = Path(directory).resolve()
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root):
            raise ValueError("imported bundle must not contain redirected paths")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = file_hash(path)
    return result


def verify_subset(plan, listing):
    subset = plan["subset"]
    if plan.get("purpose") != "pilot" or plan.get("training_data") is not False:
        raise ValueError("imported subset must remain pilot and non-training")
    if tree_hashes(plan["bundle"]) != subset["source_bundle_sha256"]:
        raise ValueError("imported bundle file set or hash changed")
    return select_listing(listing, subset["mission_ids"])


def audit_manifest(plan):
    """Derived audit scope outside the byte-identical imported bundle."""
    source = Path(plan["bundle"]) / "generation_manifest.json"
    if "subset" not in plan:
        return source
    generation = batch.read(source)
    families = {t["family_id"] for t in plan["tasks"]}
    # This is a selection, not a new generation experiment. Do not report a
    # selected-sample planning acceptance rate using the full source counts.
    derived = dict(bases=[b for b in generation["bases"] if b.get("family_id") in families],
                   counts=dict(base_scenes=len(families)), purpose="pilot", training_data=False,
                   source_manifest_sha256=file_hash(source))
    path = Path(plan["root"]) / "subset_audit_manifest.json"
    batch.save_atomic(path, derived)
    return path


def prepare_subset(source_bundle, mission_ids, batch_id, *, shards=4, max_attempts,
                   storage_bytes_per_attempt, export_reserve_bytes,
                   split_salt="simplegc-v02", binary=None, parameters=None, quality_policy=None,
                   base_port=19100, protocol_version=None, sim_speedup=None, startup_stagger_host_s=None):
    settings = batch.execution_settings(protocol_version, sim_speedup, startup_stagger_host_s)
    data_root = batch.resolve_data_root()
    root = batch.batch_directory(data_root, batch_id)
    source = Path(source_bundle).resolve()
    if root.exists():
        raise ValueError("batch directory already exists; select a new batch-id")
    if root.is_relative_to(source) or source.is_relative_to(root):
        raise ValueError("source bundle and destination must be disjoint")
    for name, value in (("max_attempts", max_attempts),
                        ("storage_bytes_per_attempt", storage_bytes_per_attempt),
                        ("export_reserve_bytes", export_reserve_bytes)):
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be an explicit positive integer")
    batch.port_blocks(shards, 1, base_port)
    source_hashes = tree_hashes(source)
    listing, manifest = verify_generation(source / "mission_list.json")
    selected = select_listing(listing, mission_ids)
    families = {e["family_id"] for e in selected["missions"]}
    if any(b.get("status") != "accepted" for b in manifest["bases"] if b.get("family_id") in families):
        raise ValueError("subset contains rejected families")
    tasks = batch.assign_tasks(selected, source, shards, split_salt)
    if not len(tasks) <= max_attempts <= 2*len(tasks):
        raise ValueError("global attempt budget must cover tasks and at most one retry each")
    binary = Path(binary or batch.PROJECT / "ArducopterSITL/arducopter.exe").resolve()
    parameters = Path(parameters or batch.PROJECT / "ArducopterSITL/copter.parm").resolve()
    provenance = batch.verify_preflight_files(binary, parameters)
    policy = resolve_policy(quality_policy)
    protected = batch._protected_files(batch.PROJECT, binary, parameters)
    scenes = [batch.read(checked_path(source, t["entry"]["scene"])) for t in tasks]
    scenes = [apply_execution_override(s, settings.get("execution_override")) for s in scenes]
    if "startup_stagger_host_s" not in settings and all(is_sim_time(s) for s in scenes):
        settings["startup_stagger_host_s"] = 30.0
    protocols = [semantic_protocol(s, patrol_validator_version=batch.PATROL_VERSION) for s in scenes]
    if any(p != protocols[0] for p in protocols):
        raise ValueError("one consistent v0.5 protocol required")
    ports = batch.port_blocks(shards, max(len(s["vehicles"]) for s in scenes), base_port)
    batch.probe_ports(ports)
    root.mkdir(parents=True, exist_ok=False)
    try:
        bundle = root / "bundle"
        shutil.copytree(source, bundle)
        if tree_hashes(bundle) != source_hashes or tree_hashes(source) != source_hashes:
            raise ValueError("source/imported bundle changed during copy")
        verify_generation(bundle / "mission_list.json")
        plan = dict(version=batch.VERSION, batch_id=batch_id, root=str(root), data_root=str(data_root),
                    project_root=str(batch.PROJECT), bundle=str(bundle), created_utc=batch.utc(),
                    shards=shards, ports=ports, tasks=tasks, max_attempts=max_attempts,
                    storage_bytes_per_attempt=storage_bytes_per_attempt,
                    export_reserve_bytes=export_reserve_bytes, split_salt=split_salt,
                    binary=str(binary), parameters=str(parameters), **provenance["actual"],
                    quality_policy=policy, quality_policy_sha256=policy_hash(policy),
                    protocol=protocols[0], acceptance_policy=batch.POLICY_VERSION,
                    progress_mapping_version=batch.PROGRESS_VERSION, patrol_validator_version=batch.PATROL_VERSION,
                    protected_sha256=protected,
                    bundle_sha256={str(bundle / p): digest for p, digest in source_hashes.items()},
                    purpose="pilot", training_data=False,
                    subset=dict(source_bundle=str(source), source_bundle_sha256=source_hashes,
                                mission_ids=[t["mission_id"] for t in tasks],
                                source_global_indices=[i for i, e in enumerate(listing["missions"])
                                                       if e["mission_id"] in set(mission_ids)]))
        if base_port != 19100:
            plan["base_port"] = base_port
        plan.update(settings)
        batch.disk_status(plan, 0)
        batch.save_atomic(root / "plan.json", plan)
        (root / "plan.sha256").write_text(file_hash(root / "plan.json") + "\n", encoding="ascii")
        batch.save_atomic(root / "batch_purpose.json", dict(purpose="pilot", training_data=False))
        for k in range(shards):
            (root / "shards" / f"shard_{k:02d}" / "attempts").mkdir(parents=True)
        batch._save_state(root, batch.new_state(plan))
        batch.integrity(plan)
        return plan
    except Exception as exc:
        batch.save_atomic(root / "prepare_error.json", dict(error=f"{type(exc).__name__}: {exc}"))
        raise
