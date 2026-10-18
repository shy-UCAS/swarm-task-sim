"""v0.7 first_edition batch production entry point.

The user runs stage A (descriptors), stage B (planning only), stage C
(simulation + labels + audit), draw-level retention and reporting.  All output
goes outside the repository; the worktree must stay clean while a run exists.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import platform
import signal
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scripts.audit_m3_r3_r0 import atomic
from scripts.run_m3_r3_r1 import code_hashes
from scripts.run_m3_r3_r4 import pair_result, qc_episode, qc_summary
from scripts.run_v07_s2_expansion import EXPANSION_SCOPE
from scripts.run_v07_s2_episode_batch import run_episode_job
from scripts.v07_fe_production_core import (
    INTENTS, ProductionError, atomic_json, build_manifest, build_stats,
    draw_detail, family_range, group_draws, intent_statuses, read_json,
    render_stats_markdown, sha256_file, split_regular, status_text, utc_iso,
    utc_stamp, vehicle_bucket, write_json,
)
from swarm_sim.fast_dynamics.reference_r3 import CONFIG_SHA256
from task_v07.criteria import CRITERIA_PATH, load_criteria
from task_v07.execution import FROZEN_SHA256
from task_v07.expansion.candidate_search import episode_candidate_pool
from task_v07.expansion.contracts import P0ContractError
from task_v07.expansion.sampling import sample_family_descriptors
from task_v07.io import read_json as task_read_json
from task_v07.io import sha as task_sha
from task_v07.unified.config import CONFIG_PATH as GENERATOR_CONFIG_PATH
from task_v07.unified.config import load_generator

DEFAULT_ROOT = PROJECT.parent.parent / "SwarmData" / "v07_first_edition"
BASELINE_PATH = PROJECT / "docs/v07/s15/S15_frozen_baseline.json"
SCENE_LAYOUT = "v07-s15@b4676bb"
DEFAULT_WORKERS = 14
DEFAULT_PLANNING_TIMEOUT_S = 3600.
DEFAULT_EPISODE_TIMEOUT_S = 5400.
SLOTS_PER_FAMILY = 2
REGULAR_PER_FAMILY = 10


def git(*args):
    return subprocess.check_output(["git", *args], cwd=PROJECT, text=True).strip()


def fe_scope():
    criteria = load_criteria()
    return ("v0.7 first_edition production; fastsim reference r3 "
            f"(config sha256 {CONFIG_SHA256}); point-mass kinematic model, "
            f"4–10 m/s not SITL-calibrated; criteria {criteria['criteria_version']}; "
            f"scene {SCENE_LAYOUT}")


def _load_family(record):
    directory = Path(record["directory"])
    expected = record["sha256"]
    for name in ("public_scene.json", "family_initial.json"):
        if task_sha(directory / name) != expected[name]:
            raise P0ContractError(f"Family source changed since S1.5: {directory / name}")
    scene = task_read_json(directory / "public_scene.json")
    family = task_read_json(directory / "family_initial.json")
    if family.get("family_id") != record["family_id"]:
        raise P0ContractError(f"Family identity differs from the frozen baseline: {directory}")
    return scene, family


def _family_row(record, scene, family):
    return {
        "candidate_index": int(record["candidate_index"]),
        "family_id": record["family_id"],
        "directory": record["directory"],
        "layout": family.get("layout"),
        "vehicle_count": family.get("vehicle_count"),
        "facility_count": sum(1 for entity in scene["entities"] if entity["type"] == "facility"),
        "map_side_m": family.get("map_side_m"),
        "sha256": record["sha256"],
        "public_scene_sha256": record["sha256"]["public_scene.json"],
        "family_initial_sha256": record["sha256"]["family_initial.json"],
    }


def stage_a(run_dir, start, end, base_fields):
    baseline = task_read_json(BASELINE_PATH)
    records = family_range(baseline, start, end)
    family_rows, unsampleable, descriptors = [], [], []
    discarded = 0
    for record in records:
        scene, family = _load_family(record)
        row = _family_row(record, scene, family)
        try:
            raw = sample_family_descriptors((scene, family, SLOTS_PER_FAMILY))
        except P0ContractError:
            raise
        except ValueError as exc:
            unsampleable.append({**row, "error": str(exc)})
            family_rows.append(row)
            continue
        regular, aborted = split_regular(raw)
        if len(regular) != REGULAR_PER_FAMILY:
            raise P0ContractError(
                f"Family {record['family_id']} produced {len(regular)} regular descriptors, expected {REGULAR_PER_FAMILY}")
        descriptors.extend(regular)
        discarded += aborted
        family_rows.append(row)
    descriptors.sort(key=lambda row: row["skeleton_id"])
    descriptor_path = run_dir / "descriptors" / "descriptors.json"
    write_json(descriptor_path, descriptors)
    registration = {
        **base_fields,
        "families_range": [start, end],
        "family_rows": family_rows,
        "family_unsampleable": unsampleable,
        "slots_per_family": SLOTS_PER_FAMILY,
        "subset": "regular",
        "discarded_aborted_count": discarded,
        "intents": list(INTENTS),
        "descriptor_count": len(descriptors),
        "descriptors_sha256": sha256_file(descriptor_path),
    }
    atomic_json(run_dir / "registration.json", registration)
    return registration, descriptors, baseline


def _check_root(root):
    root = Path(root).resolve()
    project = PROJECT.resolve()
    if root == project or project in root.parents:
        raise ProductionError(3, "Output root must be outside the project worktree", {"root": str(root)})
    return root


def _validate_run_id(run_id):
    if (not run_id or run_id in (".", "..") or Path(run_id).name != run_id
            or "/" in run_id or "\\" in run_id or ":" in run_id):
        raise ProductionError(3, "run-id must be one safe path segment", {"run_id": run_id})


def _check_overlap(root, start, end):
    for entry in sorted(Path(root).iterdir()):
        if not entry.is_dir():
            continue
        registration = entry / "registration.json"
        if not registration.exists():
            continue
        data = read_json(registration)
        indices = {int(row["candidate_index"]) for row in data.get("family_rows", [])}
        overlap = sorted(index for index in indices if start <= index < end)
        if overlap:
            raise ProductionError(3, "Family range overlaps an existing run",
                                  {"run": entry.name, "overlap": overlap})


def _new_run(root, run_id, start, end, workers, planning_timeout_s, episode_timeout_s, dry_run):
    root = _check_root(root)
    _validate_run_id(run_id)
    root.mkdir(parents=True, exist_ok=True)
    run_dir = root / run_id
    if run_dir.exists():
        raise ProductionError(3, "Run directory already exists", {"run_dir": str(run_dir)})
    _check_overlap(root, start, end)
    head = git("rev-parse", "HEAD")
    porcelain = git("status", "--porcelain")
    if porcelain:
        raise ProductionError(3, "Worktree is not clean", {"status": porcelain})
    hashes = code_hashes()
    run_dir.mkdir(parents=True)
    code_path = run_dir / "code_hashes.json"
    write_json(code_path, hashes)
    base_fields = {
        "run_id": run_id,
        "created_utc": utc_iso(),
        "code_commit": head,
        "git_clean": True,
        "code_hashes_sha256": sha256_file(code_path),
        "reference_version": "r3",
        "r3_config_sha256": CONFIG_SHA256,
        "r2_frozen_sha256": FROZEN_SHA256,
        "criteria_version": load_criteria()["criteria_version"],
        "criteria_path": str(CRITERIA_PATH),
        "criteria_sha256": sha256_file(CRITERIA_PATH),
        "generator_config_path": str(GENERATOR_CONFIG_PATH),
        "generator_config_sha256": sha256_file(GENERATOR_CONFIG_PATH),
        "baseline_path": str(BASELINE_PATH),
        "baseline_sha256": sha256_file(BASELINE_PATH),
        "scene_layout": SCENE_LAYOUT,
        "workers": workers,
        "planning_timeout_s": planning_timeout_s,
        "episode_timeout_s": episode_timeout_s,
        "FE_SCOPE": fe_scope(),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "dry_run": bool(dry_run),
    }
    registration, descriptors, _baseline = stage_a(run_dir, start, end, base_fields)
    if not dry_run:
        for name in ("planning", "episodes", "qc", "status", "logs"):
            (run_dir / name).mkdir()
    return run_dir, registration, descriptors


def _resume_startup(root, run_id):
    root = _check_root(root)
    _validate_run_id(run_id)
    run_dir = root / run_id
    if not run_dir.exists():
        raise ProductionError(3, "Run directory does not exist", {"run_dir": str(run_dir)})
    registration = read_json(run_dir / "registration.json")
    head = git("rev-parse", "HEAD")
    hashes = code_hashes()
    registered = read_json(run_dir / "code_hashes.json")
    if head != registration.get("code_commit"):
        raise ProductionError(3, "HEAD differs from the registered commit",
                              {"expected": registration.get("code_commit"), "actual": head})
    if hashes != registered:
        raise ProductionError(3, "Source hashes differ from the registered code state")
    return run_dir, registration, read_json(run_dir / "descriptors" / "descriptors.json")


def _move(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dst)


def prepare_resume(run_dir, descriptors):
    run_dir = Path(run_dir)
    base = run_dir / "_aborted" / utc_stamp()
    if base.exists():
        suffix = 2
        while True:
            candidate = base.with_name(f"{base.name}_{suffix}")
            if not candidate.exists():
                base = candidate
                break
            suffix += 1
    moved = []
    for descriptor in descriptors:
        sid = descriptor["skeleton_id"]
        if not (run_dir / "status" / f"B__{sid}.json").exists() and (run_dir / "planning" / sid).exists():
            destination = base / "B" / sid
            _move(run_dir / "planning" / sid, destination)
            moved.append({"stage": "B", "skeleton_id": sid, "destination": str(destination)})
        if not (run_dir / "status" / f"C__{sid}.json").exists() and (run_dir / "episodes" / sid).exists():
            destination = base / "C" / sid
            _move(run_dir / "episodes" / sid, destination)
            moved.append({"stage": "C", "skeleton_id": sid, "destination": str(destination)})
    for temp in sorted((run_dir / "status").glob("*.tmp")):
        destination = base / "status_tmp" / temp.name
        _move(temp, destination)
        moved.append({"stage": "status_tmp", "path": temp.name, "destination": str(destination)})
    if moved:
        atomic_json(base / "resume.json", {"created_utc": utc_iso(), "moved": moved})
    return {"timestamp": base.name, "moved": moved}


def _status_path(run_dir, stage, sid):
    return Path(run_dir) / "status" / f"{stage}__{sid}.json"


def _read_status(run_dir, stage, sid):
    path = _status_path(run_dir, stage, sid)
    return read_json(path) if path.exists() else None


def load_statuses(run_dir):
    result = {"B": {}, "C": {}}
    status_dir = Path(run_dir) / "status"
    if not status_dir.exists():
        return result
    for path in sorted(status_dir.glob("*.json")):
        name = path.stem
        if "__" not in name:
            continue
        stage, sid = name.split("__", 1)
        if stage in result:
            result[stage][sid] = read_json(path)
    return result


def _write_status(run_dir, stage, sid, status, detail=None, **extra):
    atomic(_status_path(run_dir, stage, sid),
           {"stage": stage, "skeleton_id": sid, "status": status, "detail": detail, **extra})


def _descriptor_for(descriptors, sid):
    for descriptor in descriptors:
        if descriptor["skeleton_id"] == sid:
            return descriptor
    raise P0ContractError(f"Unknown skeleton_id: {sid}")


def _family_for(registration, family_id):
    for row in registration.get("family_rows", []):
        if row["family_id"] == family_id:
            return row
    raise P0ContractError(f"Family not registered: {family_id}")


def worker_b(run_dir, sid):
    run_dir = Path(run_dir)
    registration = read_json(run_dir / "registration.json")
    descriptors = read_json(run_dir / "descriptors" / "descriptors.json")
    descriptor = _descriptor_for(descriptors, sid)
    scene, _family = _load_family(_family_for(registration, descriptor["family_id"]))
    planning_dir = run_dir / "planning" / sid
    planning_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    try:
        pool, search = episode_candidate_pool(scene, descriptor, backend="unified")
        limit = load_generator()["calibration"]["max_rounds"]
        digest = None
        if pool:
            candidate_path = planning_dir / "candidate_pool.pkl"
            try:
                with candidate_path.open("xb") as stream:
                    pickle.dump({"skeleton_id": sid, "pool": pool[:limit], "search": search},
                                stream, protocol=5)
            except Exception as exc:
                _write_status(run_dir, "B", sid, "ERROR", {
                    "message": "CANDIDATE_POOL_NOT_PICKLABLE",
                    "type": type(exc).__name__, "repr": repr(exc),
                    "planning_wall_s": time.monotonic() - started,
                }, fatal=True, traceback=traceback.format_exc())
                return 1
            digest = sha256_file(candidate_path)
        wall = time.monotonic() - started
        planning_result = {
            "skeleton_id": sid,
            "family_id": descriptor["family_id"],
            "slot": int(descriptor["common_draw"]["slot"]),
            "intent": descriptor["base_intent"],
            "status": "PASS" if pool else "REJECT",
            "eligible_combinations": len(pool),
            "rejection_reasons": search.get("rejection_reasons", {}),
            "group_rejection_reasons": search.get("group_rejection_reasons", {}),
            "combination_rejection_reasons": search.get("combination_rejection_reasons", {}),
            "rejection_class_counts": search.get("rejection_class_counts", {}),
            "termination": search.get("termination"),
            "selection": search.get("selection"),
            "planning_wall_s": wall,
            "candidate_pool_sha256": digest,
        }
        write_json(planning_dir / "planning_result.json", planning_result)
        _write_status(run_dir, "B", sid, planning_result["status"], {
            "eligible_combinations": len(pool),
            "candidate_pool_sha256": digest,
            "rejection_reasons": search.get("rejection_reasons", {}),
            "termination": search.get("termination"),
            "planning_wall_s": wall,
        }, planning_wall_s=wall)
        return 0
    except P0ContractError as exc:
        _write_status(run_dir, "B", sid, "P0_STOP", str(exc),
                      planning_wall_s=time.monotonic() - started,
                      traceback=traceback.format_exc())
        return 2
    except Exception as exc:
        _write_status(run_dir, "B", sid, "ERROR", repr(exc),
                      planning_wall_s=time.monotonic() - started,
                      traceback=traceback.format_exc())
        return 1


def worker_c(run_dir, sid):
    run_dir = Path(run_dir)
    registration = read_json(run_dir / "registration.json")
    descriptors = read_json(run_dir / "descriptors" / "descriptors.json")
    descriptor = _descriptor_for(descriptors, sid)
    b_status = _read_status(run_dir, "B", sid)
    if not b_status or b_status.get("status") != "PASS":
        _write_status(run_dir, "C", sid, "ERROR", "B_NOT_PASS",
                      elapsed_wall_s=0.)
        return 1
    scene, _family = _load_family(_family_for(registration, descriptor["family_id"]))
    planning_result = read_json(run_dir / "planning" / sid / "planning_result.json")
    started = time.monotonic()
    try:
        payload = {
            "scene": scene,
            "descriptor": descriptor,
            "planner": ["role"],
            "out": str(run_dir / "episodes"),
            "scope": EXPANSION_SCOPE,
            "geometry_backend": "unified",
            "reference_version": "r3",
            "candidate_pool_pickle": str(run_dir / "planning" / sid / "candidate_pool.pkl"),
            "candidate_pool_sha256": planning_result["candidate_pool_sha256"],
            "episode_scope": registration["FE_SCOPE"],
        }
        rows = run_episode_job(payload)
        result = pair_result(run_dir / "episodes", sid, rows, CONFIG_SHA256)
        if result["hard_physical_audit_passed"] is not True:
            _write_status(run_dir, "C", sid, "P0_STOP", result,
                          elapsed_wall_s=time.monotonic() - started)
            return 2
        qc_rows = []
        for row in rows:
            if row.get("path"):
                qc_rows.append(qc_episode(run_dir / "episodes" / row["path"], sid, row["mode"]))
        atomic(run_dir / "qc" / f"{sid}.json", qc_rows)
        elapsed = time.monotonic() - started
        status = "PAIRED" if result["paired"] else "NOT_PAIRED"
        _write_status(run_dir, "C", sid, status, {
            "paired": result["paired"],
            "first_failure": result["first_failure"],
            "rows": rows,
            "elapsed_wall_s": elapsed,
        }, paired=result["paired"], first_failure=result["first_failure"], rows=rows,
                      elapsed_wall_s=elapsed)
        return 0
    except P0ContractError as exc:
        _write_status(run_dir, "C", sid, "P0_STOP", str(exc),
                      elapsed_wall_s=time.monotonic() - started,
                      traceback=traceback.format_exc())
        return 2
    except Exception as exc:
        _write_status(run_dir, "C", sid, "ERROR", repr(exc),
                      elapsed_wall_s=time.monotonic() - started,
                      traceback=traceback.format_exc())
        return 1


def default_worker_command(task, run_dir):
    return [sys.executable, "-B", str(Path(__file__).resolve()),
            "--worker-stage", task["stage"], "--run-dir", str(run_dir),
            "--skeleton", task["sid"]]


def _kill_active(active):
    for info in active.values():
        process = info["process"]
        if process.poll() is None:
            process.kill()
        process.wait()
        info["log"].close()
    active.clear()


def _active_list(active):
    now = time.monotonic()
    return [{"stage": info["task"]["stage"], "skeleton_id": info["task"]["sid"],
             "elapsed_s": now - info["started"]} for info in active.values()]


def _completed_count(tasks, statuses):
    return sum(task["sid"] in statuses[task["stage"]] for task in tasks)


def _write_progress(run_dir, descriptors, b_tasks, c_tasks, queue, active, statuses, started, stop):
    draws = group_draws(descriptors)
    draw_rows = [draw_detail(draw, intent_statuses(draw, statuses, "B"),
                             intent_statuses(draw, statuses, "C")) for draw in draws]
    atomic_json(Path(run_dir) / "progress.json", {
        "completed": _completed_count(b_tasks + c_tasks, statuses),
        "total": len(b_tasks) + len(c_tasks),
        "active": _active_list(active),
        "pending": [{"stage": task["stage"], "skeleton_id": task["sid"]} for task in queue],
        "draws": draw_rows,
        "elapsed_wall_s": time.monotonic() - started,
        "stop": stop,
    })


def _enqueue_c_tasks(draws, statuses, queue, c_tasks, c_sids, c_draws, single_skeletons):
    if single_skeletons is not None:
        for draw in draws:
            for intent, descriptor in draw["intents"].items():
                sid = descriptor["skeleton_id"]
                if sid not in single_skeletons or sid in c_sids:
                    continue
                if status_text(statuses["B"].get(sid)) != "PASS":
                    continue
                if sid in statuses["C"]:
                    continue
                task = {"stage": "C", "sid": sid, "descriptor": descriptor,
                        "draw_key": draw["draw_key"], "timeout_s": None}
                queue.insert(0, task)
                c_tasks.append(task)
                c_sids.add(sid)
        return
    for draw in draws:
        key = draw["draw_key"]
        if key in c_draws:
            continue
        b_statuses = intent_statuses(draw, statuses, "B")
        if any(status_text(b_statuses.get(intent)) != "PASS" for intent in draw["intents"]):
            continue
        tasks = []
        for intent, descriptor in draw["intents"].items():
            sid = descriptor["skeleton_id"]
            if sid in c_sids or sid in statuses["C"]:
                continue
            tasks.append({"stage": "C", "sid": sid, "descriptor": descriptor,
                          "draw_key": key, "timeout_s": None})
        if tasks:
            queue[0:0] = tasks
            c_tasks.extend(tasks)
            c_sids.update(task["sid"] for task in tasks)
        c_draws.add(key)


def _install_signal_handlers(stop_event):
    previous = {}
    def handler(signum, frame):
        stop_event.set()
    for sig in (signal.SIGINT, getattr(signal, "SIGBREAK", None)):
        if sig is None:
            continue
        try:
            previous[sig] = signal.signal(sig, handler)
        except (ValueError, OSError):
            pass
    return previous


def _restore_signal_handlers(previous):
    for sig, handler in previous.items():
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass


def _p0_stop(run_dir, active, reason, sid=None, stage=None, detail=None, traceback_text=None,
             descriptors=None, b_tasks=None, c_tasks=None, queue=None, statuses=None, started=None):
    _kill_active(active)
    record = {"status": "P0_STOP", "reason": reason, "skeleton_id": sid, "stage": stage,
              "detail": detail, "created_utc": utc_iso()}
    if traceback_text:
        record["traceback"] = traceback_text
    atomic_json(Path(run_dir) / "P0_STOP.json", record)
    if descriptors is not None and statuses is not None and started is not None:
        _write_progress(run_dir, descriptors, b_tasks or [], c_tasks or [], queue or [], active, statuses,
                        started, {"status": "P0_STOP", "reason": reason, "skeleton_id": sid})
    print(json.dumps(record, ensure_ascii=False), flush=True)
    return 2


def _graceful_stop(run_dir, descriptors, b_tasks, c_tasks, queue, active, statuses, started):
    _kill_active(active)
    _write_progress(run_dir, descriptors, b_tasks, c_tasks, queue, active, statuses, started,
                    {"status": "INTERRUPTED", "reason": "SIGINT/SIGBREAK"})
    return 130


def run_scheduler(run_dir, registration, descriptors, workers, planning_timeout_s, episode_timeout_s,
                  single_skeletons=None, worker_command=None, poll_s=5.0, stop_event=None):
    run_dir = Path(run_dir)
    draws = group_draws(descriptors)
    statuses = load_statuses(run_dir)
    for stage in ("B", "C"):
        for sid, record in statuses[stage].items():
            if record.get("status") == "P0_STOP":
                return _p0_stop(run_dir, {}, "EXISTING_P0_STATUS", sid, stage, record.get("detail"),
                                record.get("traceback"), descriptors, [], [], [], statuses, time.monotonic())
    all_b = [{"stage": "B", "sid": descriptor["skeleton_id"], "descriptor": descriptor,
              "draw_key": (descriptor["family_id"], int(descriptor["common_draw"]["slot"])),
              "timeout_s": planning_timeout_s}
             for descriptor in sorted(descriptors, key=lambda row: row["skeleton_id"])]
    if single_skeletons is not None:
        all_b = [task for task in all_b if task["sid"] in single_skeletons]
    queue = [task for task in all_b if task["sid"] not in statuses["B"]]
    c_tasks, c_sids, c_draws = [], set(), set()
    active = {}
    started = time.monotonic()
    stop_event = stop_event or threading.Event()
    previous = _install_signal_handlers(stop_event)
    registered_hashes = read_json(run_dir / "code_hashes.json")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    try:
        while True:
            if stop_event.is_set():
                return _graceful_stop(run_dir, descriptors, all_b, c_tasks, queue, active, statuses, started)
            if code_hashes() != registered_hashes:
                return _p0_stop(run_dir, active, "SOURCE_FINGERPRINT_CHANGED", descriptors=descriptors,
                                b_tasks=all_b, c_tasks=c_tasks, queue=queue, statuses=statuses, started=started)
            statuses = load_statuses(run_dir)
            _enqueue_c_tasks(draws, statuses, queue, c_tasks, c_sids, c_draws, single_skeletons)
            while queue and len(active) < workers:
                task = queue.pop(0)
                if task["sid"] in statuses[task["stage"]] or task["sid"] in active:
                    continue
                task["timeout_s"] = planning_timeout_s if task["stage"] == "B" else episode_timeout_s
                log_path = run_dir / "logs" / f"{task['stage']}__{task['sid']}.txt"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log = log_path.open("a", encoding="utf-8")
                command = (worker_command or default_worker_command)(task, run_dir)
                try:
                    process = subprocess.Popen(command, cwd=PROJECT, stdout=log, stderr=subprocess.STDOUT,
                                               creationflags=creationflags)
                except Exception as exc:
                    log.close()
                    if not stop_event.is_set():
                        _write_status(run_dir, task["stage"], task["sid"], "ERROR",
                                      {"message": "WORKER_START_FAILED", "repr": repr(exc)},
                                      traceback=traceback.format_exc())
                    continue
                active[task["sid"]] = {"task": task, "process": process, "log": log,
                                       "started": time.monotonic()}
            for sid, info in list(active.items()):
                process = info["process"]
                task = info["task"]
                returncode = process.poll()
                timed_out = returncode is None and time.monotonic() - info["started"] > task["timeout_s"]
                if returncode is None and not timed_out:
                    continue
                if returncode is None:
                    process.kill()
                    returncode = process.wait()
                info["log"].close()
                del active[sid]
                if stop_event.is_set():
                    continue
                record = _read_status(run_dir, task["stage"], sid)
                if record is None:
                    if timed_out:
                        _write_status(run_dir, task["stage"], sid, "TIMEOUT",
                                      {"timeout_s": task["timeout_s"], "returncode": returncode})
                    else:
                        _write_status(run_dir, task["stage"], sid, "ERROR",
                                      {"message": "WORKER_EXIT_WITHOUT_STATUS", "returncode": returncode},
                                      traceback=None)
                    record = _read_status(run_dir, task["stage"], sid)
                statuses = load_statuses(run_dir)
                completed = _completed_count(all_b + c_tasks, statuses)
                print(json.dumps({"stage": task["stage"], "skeleton_id": sid,
                                  "status": record.get("status") if record else "UNKNOWN",
                                  "completed": completed, "total": len(all_b) + len(c_tasks)},
                                 ensure_ascii=False), flush=True)
                if record and record.get("status") == "P0_STOP":
                    return _p0_stop(run_dir, active, "WORKER_P0_STOP", sid, task["stage"],
                                    record.get("detail"), record.get("traceback"), descriptors,
                                    all_b, c_tasks, queue, statuses, started)
            statuses = load_statuses(run_dir)
            _enqueue_c_tasks(draws, statuses, queue, c_tasks, c_sids, c_draws, single_skeletons)
            _write_progress(run_dir, descriptors, all_b, c_tasks, queue, active, statuses, started, None)
            if not queue and not active:
                break
            time.sleep(poll_s)
    except KeyboardInterrupt:
        stop_event.set()
        return _graceful_stop(run_dir, descriptors, all_b, c_tasks, queue, active, statuses, started)
    except P0ContractError as exc:
        return _p0_stop(run_dir, active, "SCHEDULER_P0", detail=str(exc),
                        traceback_text=traceback.format_exc(), descriptors=descriptors,
                        b_tasks=all_b, c_tasks=c_tasks, queue=queue, statuses=statuses, started=started)
    except Exception as exc:
        _kill_active(active)
        atomic_json(run_dir / "progress.json", {
            "completed": _completed_count(all_b + c_tasks, load_statuses(run_dir)),
            "total": len(all_b) + len(c_tasks), "active": [], "pending": [],
            "elapsed_wall_s": time.monotonic() - started,
            "stop": {"status": "SCHEDULER_ERROR", "reason": repr(exc),
                     "traceback": traceback.format_exc()},
        })
        traceback.print_exc()
        return 1
    finally:
        _restore_signal_handlers(previous)
    statuses = load_statuses(run_dir)
    _write_progress(run_dir, descriptors, all_b, c_tasks, queue, active, statuses, started, None)
    return 0


def generate_report(run_dir):
    run_dir = Path(run_dir)
    registration = read_json(run_dir / "registration.json")
    descriptors = read_json(run_dir / "descriptors" / "descriptors.json")
    statuses = load_statuses(run_dir)
    manifest = build_manifest(run_dir, registration, descriptors, statuses)
    atomic_json(run_dir / "manifest.json", manifest)
    stats = build_stats(run_dir, registration, descriptors, statuses, qc_summary)
    atomic_json(run_dir / "stats.json", stats)
    with (run_dir / "stats.md").open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(render_stats_markdown(stats))
    return manifest, stats


def dry_run_report(run_dir, registration, descriptors):
    families = registration["family_rows"]
    report = {
        "status": "DRY_RUN",
        "run_id": registration["run_id"],
        "families_range": registration["families_range"],
        "families": len(families),
        "family_unsampleable": registration["family_unsampleable"],
        "layout_counts": {},
        "vehicle_bucket_counts": {},
        "descriptor_count": len(descriptors),
        "expected_descriptor_count": (len(families) - len(registration["family_unsampleable"])) * REGULAR_PER_FAMILY,
        "discarded_aborted_count": registration["discarded_aborted_count"],
        "code_commit": registration["code_commit"],
    }
    for row in families:
        layout = str(row.get("layout"))
        bucket = vehicle_bucket(row.get("vehicle_count", 0))
        report["layout_counts"][layout] = report["layout_counts"].get(layout, 0) + 1
        report["vehicle_bucket_counts"][bucket] = report["vehicle_bucket_counts"].get(bucket, 0) + 1
    atomic_json(Path(run_dir) / "dryrun_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)
    return report


def _parse_range(text):
    if not text or text.count(":") != 1:
        raise ProductionError(3, "--families must be START:END", {"value": text})
    start, end = text.split(":")
    try:
        start, end = int(start), int(end)
    except ValueError:
        raise ProductionError(3, "--families must contain integers", {"value": text})
    if start < 0 or end <= start:
        raise ProductionError(3, "Invalid family range", {"value": text})
    return start, end


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--families")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--planning-timeout-s", type=float, default=DEFAULT_PLANNING_TIMEOUT_S)
    parser.add_argument("--episode-timeout-s", type=float, default=DEFAULT_EPISODE_TIMEOUT_S)
    parser.add_argument("--worker-stage", choices=("B", "C"))
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--skeleton")
    args = parser.parse_args(argv)
    if args.worker_stage:
        if not args.run_dir or not args.skeleton:
            raise SystemExit("worker mode requires --run-dir and --skeleton")
        return worker_b(args.run_dir, args.skeleton) if args.worker_stage == "B" else worker_c(args.run_dir, args.skeleton)
    if not args.run_id:
        raise ProductionError(3, "--run-id is required")
    if args.report:
        if args.resume:
            raise ProductionError(3, "--report and --resume are mutually exclusive")
        generate_report(args.root / args.run_id)
        return 0
    if args.resume:
        if args.dry_run or args.families:
            raise ProductionError(3, "--resume cannot be combined with --dry-run or --families")
        try:
            run_dir, registration, descriptors = _resume_startup(args.root, args.run_id)
            prepare_resume(run_dir, descriptors)
            code = run_scheduler(run_dir, registration, descriptors, args.workers,
                                 args.planning_timeout_s, args.episode_timeout_s)
            if code == 0:
                generate_report(run_dir)
            return code
        except ProductionError as exc:
            print(json.dumps({"status": "REFUSED", "code": exc.code, "reason": str(exc),
                              "detail": exc.detail}, ensure_ascii=False), flush=True)
            return exc.code
        except P0ContractError as exc:
            print(json.dumps({"status": "P0_STOP", "reason": str(exc)}, ensure_ascii=False), flush=True)
            return 2
        except Exception:
            traceback.print_exc()
            return 1
    if not args.families:
        raise ProductionError(3, "--families is required for a new run")
    start, end = _parse_range(args.families)
    if args.workers < 1 or args.planning_timeout_s <= 0 or args.episode_timeout_s <= 0:
        raise ProductionError(3, "workers and timeouts must be positive")
    run_dir = args.root / args.run_id
    try:
        run_dir, registration, descriptors = _new_run(
            args.root, args.run_id, start, end, args.workers,
            args.planning_timeout_s, args.episode_timeout_s, args.dry_run)
        if args.dry_run:
            dry_run_report(run_dir, registration, descriptors)
            return 0
        code = run_scheduler(run_dir, registration, descriptors, args.workers,
                             args.planning_timeout_s, args.episode_timeout_s)
        if code == 0:
            generate_report(run_dir)
        return code
    except ProductionError as exc:
        print(json.dumps({"status": "REFUSED", "code": exc.code, "reason": str(exc),
                          "detail": exc.detail}, ensure_ascii=False), flush=True)
        return exc.code
    except P0ContractError as exc:
        if run_dir.exists():
            atomic_json(run_dir / "P0_STOP.json", {
                "status": "P0_STOP", "reason": str(exc), "created_utc": utc_iso(),
                "traceback": traceback.format_exc()})
        print(json.dumps({"status": "P0_STOP", "reason": str(exc)}, ensure_ascii=False), flush=True)
        return 2
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
