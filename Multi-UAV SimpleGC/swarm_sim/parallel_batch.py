"""Frozen family shards, one controller, graceful stop and evidence-only recovery.

Only the new v0.6 entry point uses this module. UTC is diagnostic; the atomic
controller ledger defines completion order. Shard ledgers are rebuildable views.
"""
import copy
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .dataset import family_split
from .generation import canonical_hash, checked_path, file_hash, generate, verify_generation
from .protocol import semantic_protocol
from .quality import policy_hash, resolve_policy
from .run_provenance import verify_preflight_files
from .validation_policy_r12b import VERSION as POLICY_VERSION, assess_recent_runs

PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY = PROJECT.parent
ARCHIVE = REPOSITORY.with_name("Simulation")
VERSION = "v06_parallel_batch_v1"
PROGRESS_VERSION = "ordered_route_progress_v2"
PATROL_VERSION = "perimeter_revisit_v2"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def utc():
    return datetime.now(timezone.utc).isoformat()


def save_atomic(path, value):
    path = resolve_data_root(Path(path).absolute())
    temporary = resolve_data_root(path.with_name(path.name + ".tmp"))
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def resolve_data_root(value=None, *, project_root=PROJECT):
    value = os.environ.get("SIM_DATA_ROOT") if value is None else value
    if not value or not str(value).strip():
        raise ValueError("SIM_DATA_ROOT must be set explicitly; there is no default data path")
    source = Path(value)
    if not source.is_absolute():
        raise ValueError("SIM_DATA_ROOT must be an absolute path")
    root = source.resolve()
    repository = Path(project_root).resolve().parent
    if root.is_relative_to(repository) or root.is_relative_to(ARCHIVE.resolve()):
        raise ValueError("SIM_DATA_ROOT cannot be inside the repository or frozen archive")
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        raise ValueError("SIM_DATA_ROOT cannot be inside any Git repository")
    return root


def batch_directory(data_root, batch_id):
    if not isinstance(batch_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", batch_id):
        raise ValueError("batch-id must be a simple directory name")
    data_root = resolve_data_root(data_root)
    root = (data_root / "parallel_batch" / batch_id).resolve()
    if not root.is_relative_to(data_root):
        raise ValueError("batch directory escapes SIM_DATA_ROOT")
    resolve_data_root(root)  # Detect a nested repository or redirected directory too.
    return root


class FileLock:
    """OS-owned lock: a stale filename is harmless after process death."""
    def __init__(self, path):
        self.path, self.stream = Path(path), None

    def __enter__(self):
        self.path = resolve_data_root(self.path.absolute())
        self.stream = self.path.open("a+b")
        try:
            if self.path.stat().st_size == 0:
                self.stream.write(b"0")
                self.stream.flush()
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            self.stream = None
            raise ValueError(f"writer already active: {self.path}") from exc
        return self

    def __exit__(self, *_):
        if self.stream is not None:
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_UN)
            self.stream.close()
            self.stream = None


def port_blocks(shards, max_vehicles):
    if type(shards) is not int or not 1 <= shards <= 459:
        raise ValueError("shards must be an integer in [1, 459]")
    if type(max_vehicles) is not int or not 1 <= max_vehicles <= 10:
        raise ValueError("each 100-port block supports at most 10 vehicles")
    return [dict(shard_id=k, base_port=19100 + 100*k, end_port=19199 + 100*k)
            for k in range(shards)]


def probe_ports(blocks):
    seen = set()
    for block in blocks:
        for port in range(block["base_port"], block["end_port"] + 1):
            if port in seen or not 1024 <= port <= 65000:
                raise ValueError("overlapping or invalid port blocks")
            seen.add(port)
            for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
                try:
                    with socket.socket(socket.AF_INET, kind) as probe:
                        if os.name == "nt":
                            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                        probe.bind(("127.0.0.1", port))
                except OSError as exc:
                    raise ValueError(f"port unavailable: {port} ({kind})") from exc


def assign_tasks(listing, bundle, shards, split_salt="simplegc-v02"):
    port_blocks(shards, 1)
    families, tasks = {}, []
    for index, entry in enumerate(listing["missions"]):
        if entry.get("status") != "planned":
            raise ValueError("complete frozen list must contain only successfully planned tasks")
        family = entry["family_id"]
        families.setdefault(family, len(families) % shards)
        scene = read(checked_path(bundle, entry["scene"]))
        task = scene["task_spec"]
        if task["family_id"] != family:
            raise ValueError("task family differs from frozen listing")
        tasks.append(dict(global_index=index, mission_id=entry["mission_id"], family_id=family,
                          shard_id=families[family], seed=task["seed"],
                          split=family_split(family, split_salt), entry=copy.deepcopy(entry)))
    if not tasks or len({t["mission_id"] for t in tasks}) != len(tasks):
        raise ValueError("nonempty unique mission list required")
    return tasks


def _protected_files(project, binary, parameters):
    files = set(project.glob("*.py"))
    for name in ("swarm_sim", "scripts"):
        files.update((project / name).rglob("*.py"))
    for name in ("generation_profiles", "quality_policies", "missions", "tasks", "scenarios"):
        files.update((project / name).rglob("*.json"))
    files.update((binary, parameters))
    if any(not p.resolve().is_relative_to(project.parent) for p in files):
        raise ValueError("v0.6 protected source and configuration must belong to this repository")
    return {str(p.resolve()): file_hash(p) for p in sorted(files)}


def prepare(profile, batch_id, *, shards=2, max_attempts, storage_bytes_per_attempt,
            export_reserve_bytes, split_salt="simplegc-v02", binary=None,
            parameters=None, quality_policy=None):
    data_root = resolve_data_root()
    root = batch_directory(data_root, batch_id)
    for name, value in (("max_attempts", max_attempts),
                        ("storage_bytes_per_attempt", storage_bytes_per_attempt),
                        ("export_reserve_bytes", export_reserve_bytes)):
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be an explicit positive integer")
    port_blocks(shards, 1)
    binary = Path(binary or PROJECT / "ArducopterSITL/arducopter.exe").resolve()
    parameters = Path(parameters or PROJECT / "ArducopterSITL/copter.parm").resolve()
    provenance = verify_preflight_files(binary, parameters)
    policy = resolve_policy(quality_policy)
    protected = _protected_files(PROJECT, binary, parameters)
    if root.exists():
        raise ValueError("batch directory already exists; select a new batch-id")
    root.mkdir(parents=True, exist_ok=False)
    try:
        generate(profile, root / "bundle")
        listing, manifest = verify_generation(root / "bundle/mission_list.json")
        if any(b.get("status") != "accepted" for b in manifest["bases"]):
            raise ValueError("generation contains rejected families; full task coverage is required")
        tasks = assign_tasks(listing, root / "bundle", shards, split_salt)
        if not len(tasks) <= max_attempts <= 2*len(tasks):
            raise ValueError("global attempt budget must cover tasks and at most one retry each")
        scenes = [read(checked_path(root / "bundle", t["entry"]["scene"])) for t in tasks]
        protocols = [semantic_protocol(s, patrol_validator_version=PATROL_VERSION) for s in scenes]
        if any(p != protocols[0] for p in protocols):
            raise ValueError("one consistent v0.5 protocol required")
        ports = port_blocks(shards, max(len(s["vehicles"]) for s in scenes))
        probe_ports(ports)
        plan = dict(version=VERSION, batch_id=batch_id, root=str(root), data_root=str(data_root),
                    project_root=str(PROJECT), bundle=str(root / "bundle"), created_utc=utc(),
                    shards=shards, ports=ports, tasks=tasks, max_attempts=max_attempts,
                    storage_bytes_per_attempt=storage_bytes_per_attempt,
                    export_reserve_bytes=export_reserve_bytes, split_salt=split_salt,
                    binary=str(binary), parameters=str(parameters), **provenance["actual"],
                    quality_policy=policy, quality_policy_sha256=policy_hash(policy),
                    protocol=protocols[0], acceptance_policy=POLICY_VERSION,
                    progress_mapping_version=PROGRESS_VERSION, patrol_validator_version=PATROL_VERSION,
                    protected_sha256=protected,
                    bundle_sha256={str(p.resolve()): file_hash(p) for p in sorted((root / "bundle").rglob("*.json"))})
        disk_status(plan, 0)
        save_atomic(root / "plan.json", plan)
        (root / "plan.sha256").write_text(file_hash(root / "plan.json") + "\n", encoding="ascii")
        for k in range(shards):
            (root / "shards" / f"shard_{k:02d}" / "attempts").mkdir(parents=True)
        state = new_state(plan)
        _save_state(root, state)
        return plan
    except Exception as exc:
        save_atomic(root / "prepare_error.json", dict(error=f"{type(exc).__name__}: {exc}"))
        raise


def load_plan(root):
    root = Path(root).resolve()
    plan = read(root / "plan.json")
    if file_hash(root / "plan.json") != (root / "plan.sha256").read_text(encoding="ascii").strip():
        raise ValueError("frozen plan hash changed")
    if (plan.get("version") != VERSION or plan.get("project_root") != str(PROJECT)
            or batch_directory(resolve_data_root(), plan["batch_id"]) != root
            or Path(plan["root"]) != root or Path(plan["data_root"]) != resolve_data_root()):
        raise ValueError("batch path, environment or version binding changed")
    return plan


def integrity(plan):
    root = Path(plan["root"])
    if load_plan(root) != plan:
        raise ValueError("frozen plan changed in memory")
    for k in range(plan["shards"]):
        path = root / "shards" / f"shard_{k:02d}" / "attempts"
        if path.resolve() != path:
            raise ValueError("attempt output path is redirected by a symlink or junction")
    if _protected_files(PROJECT, Path(plan["binary"]), Path(plan["parameters"])) != plan["protected_sha256"]:
        raise ValueError("protected source/configuration file set or hash changed")
    for bindings in (plan["bundle_sha256"],):
        for path, digest in bindings.items():
            if file_hash(path) != digest:
                raise ValueError(f"protected file hash changed: {path}")
    listing, _ = verify_generation(Path(plan["bundle"]) / "mission_list.json")
    if assign_tasks(listing, plan["bundle"], plan["shards"], plan["split_salt"]) != plan["tasks"]:
        raise ValueError("frozen task assignment changed")


def disk_status(plan, attempts_used):
    required = (plan["max_attempts"] - attempts_used)*plan["storage_bytes_per_attempt"]
    required += plan["export_reserve_bytes"]
    free = shutil.disk_usage(plan["root"]).free
    if free < required:
        raise ValueError(f"insufficient disk for all shards: {free} free, {required} required")
    return dict(free_bytes=free, required_bytes=required,
                basis="global_remaining_attempt_budget_plus_unified_export_reserve")


def new_state(plan):
    return dict(version=VERSION, plan_sha256=canonical_hash(plan), attempts=[], completion_order=[],
                stopped_reason=None, stop_attempt_id=None, completed=False, finalized=False,
                rolling=assess_recent_runs([], stage="batch"))


def _stop(state, reason, attempt_id=None):
    events = state.setdefault("stop_events", [])
    if not any(e["reason"] == reason and e["attempt_id"] == attempt_id for e in events):
        events.append(dict(reason=reason, attempt_id=attempt_id, utc=utc()))
    if not state["stopped_reason"]:
        state.update(stopped_reason=reason, stop_attempt_id=attempt_id, stopped_utc=utc())


def register_completion(state, attempt, result):
    if attempt["attempt_id"] in state["completion_order"]:
        if attempt.get("result") != result:
            raise ValueError("previously registered completion changed")
        return
    if result.get("run_id") and any(a.get("result", {}).get("run_id") == result["run_id"]
                                    for a in state["attempts"]):
        raise ValueError("duplicate completed run identity")
    attempt.update(status="finished", result=copy.deepcopy(result),
                   completion_seq=len(state["completion_order"])+1,
                   finished_utc=utc(), completed_after_stop=bool(state["stopped_reason"]))
    state["completion_order"].append(attempt["attempt_id"])
    ordered = sorted((a for a in state["attempts"] if a.get("completion_seq")),
                     key=lambda a: a["completion_seq"])
    state["rolling"] = assess_recent_runs([
        dict(run_id=a["result"]["run_id"], stage="batch", assessment=a["result"]["assessment"])
        for a in ordered if a["result"].get("assessment")], stage="batch")
    if result.get("infrastructure_error"):
        _stop(state, "infrastructure: " + result["infrastructure_error"], attempt["attempt_id"])
    elif result.get("hard_failures"):
        _stop(state, "confirmed violation: " + ", ".join(result["hard_failures"]), attempt["attempt_id"])
    elif state["rolling"]["stop"]:
        _stop(state, "global rolling anomalies reached 5 in the latest 20 runs", attempt["attempt_id"])


def _save_state(root, state):
    save_atomic(root / "control.json", state)
    for folder in sorted((root / "shards").glob("shard_*")):
        if not folder.resolve().is_relative_to(root):
            raise ValueError("shard output directory escapes batch root")
        shard_id = int(folder.name.split("_")[-1])
        save_atomic(folder / "ledger.json", dict(version=VERSION, plan_sha256=state["plan_sha256"],
            shard_id=shard_id, attempts=[a for a in state["attempts"] if a["shard_id"] == shard_id]))
    if state["stopped_reason"]:
        save_atomic(root / "stop_report.json", dict(reason=state["stopped_reason"],
            trigger_attempt_id=state["stop_attempt_id"], events=state.get("stop_events", []),
            rolling=state["rolling"],
            draining_attempts=[a["attempt_id"] for a in state["attempts"] if a["status"] != "finished"],
            completed_after_stop=[a["attempt_id"] for a in state["attempts"] if a.get("completed_after_stop")],
            research_impact="Unverified or interrupted evidence cannot support reproducible task outcomes; preserve all attempts for review."))


def _next_task(plan, state, shard_id):
    for task in plan["tasks"]:
        if task["shard_id"] != shard_id:
            continue
        attempts = [a for a in state["attempts"] if a["global_index"] == task["global_index"]]
        if not attempts:
            return task, 0
        previous = attempts[-1]
        if previous["status"] != "finished":
            return None
        result = previous["result"]
        if result.get("retryable_pre_takeoff") and previous["attempt_index"] == 0:
            return task, 1
    return None


def _validate_state(plan, state):
    if state.get("version") != VERSION or state.get("plan_sha256") != canonical_hash(plan):
        raise ValueError("controller state/plan binding changed")
    ids, task_attempts, previous_by_task = set(), set(), {}
    for a in state["attempts"]:
        index = a["global_index"]
        if type(index) is not int or not 0 <= index < len(plan["tasks"]):
            raise ValueError("attempt references unknown task")
        task = plan["tasks"][index]
        expected_dir = Path(plan["root"]) / "shards" / f"shard_{task['shard_id']:02d}" / "attempts" / a["attempt_id"]
        if (a["attempt_id"] in ids or not re.fullmatch(r"a[0-9]{6}", a["attempt_id"])
                or (index, a["attempt_index"]) in task_attempts or a["attempt_index"] not in (0, 1)
                or a["shard_id"] != task["shard_id"] or a["mission_id"] != task["mission_id"]
                or a["family_id"] != task["family_id"] or Path(a["attempt_directory"]).resolve() != expected_dir
                or a["base_port"] != 19100+100*task["shard_id"]):
            raise ValueError("duplicate or inconsistent attempt assignment")
        previous = previous_by_task.get(index)
        if a["attempt_index"] == 1 and (not previous or previous["status"] != "finished"
                or previous["attempt_index"] != 0 or not previous["result"].get("retryable_pre_takeoff")
                or previous["result"].get("infrastructure_error") or previous["result"].get("hard_failures")):
            raise ValueError("retry requires one completed, verified pre-takeoff failure")
        if (a["status"] not in ("running", "finished")
                or (a["status"] == "finished") != (type(a.get("completion_seq")) is int)
                or a["status"] == "finished" and not isinstance(a.get("result"), dict)):
            raise ValueError("finished attempt is missing result or completion sequence")
        ids.add(a["attempt_id"])
        task_attempts.add((index, a["attempt_index"]))
        previous_by_task[index] = a
    finished = sorted((a for a in state["attempts"] if a.get("completion_seq")), key=lambda a: a["completion_seq"])
    if ([a["completion_seq"] for a in finished] != list(range(1, len(finished)+1))
            or state["completion_order"] != [a["attempt_id"] for a in finished]
            or len(state["attempts"]) > plan["max_attempts"]):
        raise ValueError("completion sequence or global budget corrupted")
    replayed = assess_recent_runs([dict(run_id=a["result"]["run_id"], stage="batch", assessment=a["result"]["assessment"])
                                  for a in finished if a["result"].get("assessment")], stage="batch")
    if replayed != state["rolling"]:
        raise ValueError("persisted rolling window differs from completion sequence replay")
    historical_stop = bool(state.get("stop_events"))
    anomaly_window, run_ids = [], set()
    for attempt in finished:
        result = attempt["result"]
        historical_stop |= bool(result.get("infrastructure_error") or result.get("hard_failures"))
        if result.get("run_id"):
            if result["run_id"] in run_ids:
                raise ValueError("duplicate completed run identity")
            run_ids.add(result["run_id"])
        if result.get("assessment"):
            anomaly_window = [*anomaly_window, result["assessment"]["aggregate_anomaly"]][-20:]
            historical_stop |= sum(anomaly_window) >= 5
    if historical_stop and not state["stopped_reason"]:
        raise ValueError("persisted stop was cleared despite a historical stop condition")


def _default_verifier(plan, attempt, result):
    from .parallel_worker import verify_result
    return verify_result(plan, attempt, result)


class Controller:
    def __init__(self, root, *, launcher=None, verifier=None):
        self.root = Path(root).resolve()
        self.plan = load_plan(self.root)
        self.launcher = launcher or self._launch
        self.verifier = verifier or _default_verifier
        self.processes = {}

    def _persist(self, state):
        try:
            _save_state(self.root, state)
            return True
        except Exception as exc:
            reason = f"state persistence failed: {type(exc).__name__}: {exc}"
            fresh = not any(e["reason"] == reason for e in state.get("stop_events", []))
            _stop(state, reason)
            if fresh:
                print(reason + "; active workers will still drain", file=sys.stderr)
            return False

    def _launch(self, plan, attempt):
        log_path = Path(attempt["attempt_directory"]) / "worker.log"
        if log_path.resolve() != log_path:
            raise ValueError("worker output path escapes reserved attempt directory")
        log = log_path.open("ab")
        try:
            return subprocess.Popen([sys.executable, str(PROJECT / "scripts/run_parallel_batch.py"),
                "_worker", "--batch-id", plan["batch_id"], "--attempt-id", attempt["attempt_id"]],
                cwd=attempt["attempt_directory"], stdout=log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0,
                start_new_session=os.name != "nt")
        finally:
            log.close()

    def _accept(self, state, attempt):
        path = Path(attempt["attempt_directory"]) / "result.json"
        try:
            integrity(self.plan)
            result = read(path)
            if attempt.get("result_sha256") and file_hash(path) != attempt["result_sha256"]:
                raise ValueError("registered result file changed")
            result = self.verifier(self.plan, attempt, result)
            attempt["result_sha256"] = file_hash(path)
        except Exception as exc:
            result = dict(infrastructure_error=f"result verification failed: {type(exc).__name__}: {exc}",
                          retryable_pre_takeoff=False)
        register_completion(state, attempt, result)
        _save_state(self.root, state)

    def _recover(self, state):
        for attempt in state["attempts"]:
            if attempt["status"] == "finished":
                if attempt.get("result_sha256"):
                    path = Path(attempt["attempt_directory"]) / "result.json"
                    if file_hash(path) != attempt["result_sha256"]:
                        raise ValueError("registered result file changed")
                    if self.verifier(self.plan, attempt, read(path)) != attempt["result"]:
                        raise ValueError("registered assessment changed")
                continue
            lock = self.root / "shards" / f"shard_{attempt['shard_id']:02d}" / "writer.lock"
            guard = FileLock(lock)
            try:
                guard.__enter__()
            except ValueError:
                _stop(state, "worker still active; recovery will not launch another writer", attempt["attempt_id"])
                continue
            try:
                if (Path(attempt["attempt_directory"]) / "result.json").is_file():
                    self._accept(state, attempt)
                else:
                    _stop(state, "unresolved interrupted attempt; no automatic reflight", attempt["attempt_id"])
            finally:
                guard.__exit__()
        _save_state(self.root, state)

    def run(self, resume=False, poll_seconds=0.2):
        with FileLock(self.root / "controller.lock"):
            state = read(self.root / "control.json")
            _validate_state(self.plan, state)
            if state["attempts"] and not resume:
                raise ValueError("existing attempts require explicit --resume; no automatic reflight")
            if state["finalized"]:
                raise ValueError("batch already finalized")
            try:
                integrity(self.plan)
                if resume:
                    self._recover(state)
                finished = sum(a["status"] == "finished" for a in state["attempts"])
                state["disk_check"] = disk_status(self.plan, finished)
                probe_ports(self.plan["ports"])
            except Exception as exc:
                _stop(state, f"startup verification: {type(exc).__name__}: {exc}")
                self._persist(state)
                return state
            while True:
                try:
                    # Consume finished workers before another dispatch; completion_seq is
                    # assigned here, never from a worker's UTC timestamp or exit code.
                    for attempt_id, process in list(self.processes.items()):
                        if process.poll() is not None:
                            attempt = next(a for a in state["attempts"] if a["attempt_id"] == attempt_id)
                            try:
                                self._accept(state, attempt)
                            except Exception as exc:
                                _stop(state, f"completion registration failed: {type(exc).__name__}: {exc}", attempt_id)
                            finally:
                                del self.processes[attempt_id]
                    if not state["stopped_reason"]:
                        try:
                            integrity(self.plan)
                            for k in range(self.plan["shards"]):
                                if any(a["shard_id"] == k and a["attempt_id"] in self.processes for a in state["attempts"]):
                                    continue
                                selection = _next_task(self.plan, state, k)
                                if selection is None:
                                    continue
                                if len(state["attempts"]) >= self.plan["max_attempts"]:
                                    _stop(state, "global attempt budget exhausted")
                                    break
                                task, retry_index = selection
                                attempt_id = f"a{len(state['attempts']):06d}"
                                directory = self.root / "shards" / f"shard_{k:02d}" / "attempts" / attempt_id
                                if directory.resolve() != directory:
                                    raise ValueError("attempt output path escapes reserved shard directory")
                                directory.mkdir(exist_ok=False)
                                attempt = dict(attempt_id=attempt_id, global_index=task["global_index"],
                                    mission_id=task["mission_id"], family_id=task["family_id"], shard_id=k,
                                    attempt_index=retry_index, attempt_directory=str(directory), base_port=19100+100*k,
                                    status="running", started_utc=utc())
                                state["attempts"].append(attempt)
                                _save_state(self.root, state)  # Reserve global budget before Popen.
                                self.processes[attempt_id] = self.launcher(self.plan, attempt)
                        except Exception as exc:
                            _stop(state, f"dispatch infrastructure: {type(exc).__name__}: {exc}")
                    if not self.processes:
                        try:
                            integrity(self.plan)
                        except Exception as exc:
                            _stop(state, f"final integrity: {type(exc).__name__}: {exc}")
                        state["completed"] = (not state["stopped_reason"] and
                            all(_next_task(self.plan, state, k) is None for k in range(self.plan["shards"])))
                        self._persist(state)
                        return state
                    self._persist(state)
                    time.sleep(poll_seconds)
                except KeyboardInterrupt:
                    _stop(state, "controller interrupted; dispatch stopped, active workers draining")
                    self._persist(state)


def merge_records(plan, state, *, verifier=None):
    _validate_state(plan, state)
    require_result_file = verifier is None
    verifier = verifier or _default_verifier
    by_task, run_ids = {}, set()
    for attempt in state["attempts"]:
        if attempt["status"] != "finished" or "result" not in attempt:
            raise ValueError("missing or unfinished attempt at merge")
        if require_result_file or attempt.get("result_sha256"):
            result_file = Path(attempt["attempt_directory"]) / "result.json"
            if (not attempt.get("result_sha256") or file_hash(result_file) != attempt["result_sha256"]
                    or read(result_file) != attempt["result"]):
                raise ValueError("merge result file hash or ledger binding changed")
        result = verifier(plan, attempt, attempt["result"])
        if result.get("infrastructure_error"):
            raise ValueError("unverified infrastructure result at merge")
        if (result.get("semantic_protocol") != plan["protocol"]
                or result.get("quality_policy_sha256") != plan["quality_policy_sha256"]):
            raise ValueError("merge protocol or quality policy mismatch")
        if not result.get("run_id") or result["run_id"] in run_ids:
            raise ValueError("duplicate or missing run identity")
        run_ids.add(result["run_id"])
        index = attempt["global_index"]
        if index in by_task:
            previous = by_task[index]
            if not (attempt["attempt_index"] == 1 and previous["attempt_index"] == 0
                    and previous["result"].get("retryable_pre_takeoff")):
                raise ValueError("duplicate task at merge")
        by_task[index] = attempt
    if set(by_task) != set(range(len(plan["tasks"]))):
        raise ValueError("missing tasks at merge")
    return [dict(by_task[i]["result"], global_index=i, mission_id=plan["tasks"][i]["mission_id"],
                 family_id=plan["tasks"][i]["family_id"]) for i in range(len(plan["tasks"]))]


def patrol_diagnostics(plan, rows):
    from scripts.build_v05_batch_report import patrol_timing

    evidence = []
    for task, row in zip(plan["tasks"], rows):
        scene = read(checked_path(plan["bundle"], task["entry"]["scene"]))
        if scene["task_spec"]["mission"]["intent"] == "patrol":
            evidence.append(dict(intent="patrol", stage="batch", run_id=row["run_id"],
                case_id=task["global_index"], semantic_plan=scene["semantic_plan"],
                ac4=read(Path(row["analysis_directory"]) / "ac4_timing_v3.json")))
    report = patrol_timing(evidence)
    report["groups"] = [g for g in report["groups"] if g["scope"] == "batch"]
    return report


def finalize(root):
    from scripts.run_v05c_pp import _description_gate
    from .dataset import build_dataset
    from .dataset_audit import audit_dataset
    from .episode_loader import load_episode, load_public_scene
    from .language_v0 import describe_dataset

    root = Path(root).resolve()
    plan = load_plan(root)
    with FileLock(root / "controller.lock"):
        state = read(root / "control.json")
        if not state["completed"] or state["stopped_reason"] or state["finalized"]:
            raise ValueError("finalize requires a complete, unstopped, unfinalized batch")
        try:
            integrity(plan)
            rows = merge_records(plan, state)
            selections = {r["run_directory"]: dict(directory=r["analysis_directory"],
                manifest_sha256=file_hash(Path(r["analysis_directory"]) / "manifest.json")) for r in rows}
            save_atomic(root / "merged_records.json", rows)
            save_atomic(root / "analysis_selections.json", selections)
            audit_ledger = root / "audit_attempt_ledger.json"
            save_atomic(audit_ledger, dict(schema_version=1, missions=[dict(mission_id=t["mission_id"],
                attempts=[dict(a["result"], status=a["result"].get("run_status"))
                          for a in state["attempts"] if a["global_index"] == t["global_index"]]) for t in plan["tasks"]]))
            dataset, language = root / "dataset", root / "language"
            manifest = build_dataset([r["run_directory"] for r in rows], dataset,
                                     salt=plan["split_salt"], analysis_selections=selections)
            if ([e["run_id"] for e in manifest["episodes"]] != [r["run_id"] for r in rows]
                    or [e["split"] for e in manifest["episodes"]] != [t["split"] for t in plan["tasks"]]):
                raise ValueError("export order or frozen family split changed")
            audit = audit_dataset(dataset, generation_manifest=Path(plan["bundle"]) / "generation_manifest.json",
                                  attempt_ledger=audit_ledger)
            save_atomic(root / "dataset_audit.json", audit)
            describe_dataset(dataset, language)
            descriptions = _description_gate(dataset, language)
            if not descriptions["consistency_pass"]:
                raise ValueError("unified description consistency check failed")
            loaded = []
            for entry in manifest["episodes"]:
                episode_path = checked_path(dataset, entry["directory"])
                episode = load_episode(episode_path, verify_hashes=True)
                corners = load_public_scene(episode_path)
                loaded.append(dict(run_id=entry["run_id"], frames=len(episode["t_s"]),
                                   agents=len(episode["agent_ids"]), corners=len(corners)))
            integrity(plan)
            result = dict(version=VERSION, total=len(rows), loaded=loaded, description_check=descriptions,
                          audit_issues=audit.get("issues", []), rolling=state["rolling"],
                          patrol_timing=patrol_diagnostics(plan, rows),
                          dataset_manifest_sha256=file_hash(dataset / "dataset_manifest.json"),
                          language_manifest_sha256=file_hash(language / "language_manifest.json"))
            save_atomic(root / "final_report.json", result)
            state["finalized"] = True
            _save_state(root, state)
            return result
        except Exception as exc:
            _stop(state, f"finalization infrastructure: {type(exc).__name__}: {exc}")
            _save_state(root, state)
            raise
