"""V8-01 §5 驱动：在隔离目录中调用冻结生成器（fe/production-r3 @ 641a9b3）的规划/仿真函数。

不修改冻结代码：只把 `Multi-UAV SimpleGC` 加入 sys.path 后导入；所有输出写到 --out 指定的
隔离目录（其下 run/ 为仿造的批次目录，只含复制来的 registration.json 与 descriptors.json）。

子命令：
  plan       只跑规划阶段（直接调用 worker_b），供 §5.1 快速检查
  sample     规划阶段 + 只跑同步方式的仿真阶段，带分环节计时（§5.2）
  profile    cProfile：--target sim（先不剖析地跑规划，再剖析同步仿真阶段）或 --target plan（§5.3）
  resume     仿真续跑实验（§5.4）

仿真阶段只跑同步方式：照搬 scripts/run_v07_s2_episode_batch.py::run_episode_job 的步骤与写盘，
只把方式循环限定为 synchronous，并跳过只对一对方式有意义的 validate_pair / load_pair / pair_result。
"""
import argparse
import cProfile
import json
import os
import pickle
import pstats
import shutil
import sys
import threading
import time
from copy import deepcopy
from pathlib import Path

sys.dont_write_bytecode = True
PROJECT = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-prod-r3\Multi-UAV SimpleGC")
sys.path.insert(0, str(PROJECT))
DATA_ROOT = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData")
FE_ROOT = DATA_ROOT / "v07_first_edition"

import numpy as np  # noqa: E402


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=1, default=str)
    tmp.replace(path)


def prepare_run_dir(run_id, sid, out):
    """隔离批次目录：只复制 registration.json 与 descriptors.json（只读来源）。"""
    run_dir = Path(out) / "run"
    src = FE_ROOT / run_id
    (run_dir / "descriptors").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src / "registration.json", run_dir / "registration.json")
    shutil.copyfile(src / "descriptors" / "descriptors.json", run_dir / "descriptors" / "descriptors.json")
    return run_dir


def dir_bytes(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            total += os.path.getsize(os.path.join(root, name))
    return total


# ---------------------------------------------------------------- 计时包装
class Timers:
    """包装在调用方实际查找函数的模块命名空间上；记录含子调用耗时、独占耗时与调用次数。"""

    def __init__(self):
        self.stats = {}
        self.stack = []
        self.extra = {}
        self.installed = []
        self.lock = threading.Lock()

    def wrap(self, module, attr, label):
        original = getattr(module, attr)
        timers = self

        def wrapper(*args, **kwargs):
            parent = timers.stack[-1] if timers.stack else None
            timers.stack.append(label)
            started = time.perf_counter()
            hook = timers.extra_hooks.get(label)
            before = hook[0]() if hook else None
            try:
                return original(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - started
                timers.stack.pop()
                with timers.lock:
                    s = timers.stats.setdefault(label, {"calls": 0, "inclusive_s": 0., "children_s": 0.,
                                                        "parents": {}})
                    s["calls"] += 1
                    s["inclusive_s"] += elapsed
                    s["parents"][str(parent)] = s["parents"].get(str(parent), 0) + 1
                    bp = s.setdefault("by_parent", {}).setdefault(str(parent), {"calls": 0, "inclusive_s": 0.})
                    bp["calls"] += 1
                    bp["inclusive_s"] += elapsed
                    if parent is not None:
                        p = timers.stats.setdefault(parent, {"calls": 0, "inclusive_s": 0., "children_s": 0.,
                                                             "parents": {}})
                        p["children_s"] += elapsed
                    if hook:
                        hook[1](before, args, kwargs, elapsed)

        wrapper.__wrapped__ = original
        setattr(module, attr, wrapper)
        self.installed.append({"module": module.__name__, "attr": attr, "label": label})

    extra_hooks = {}

    def snapshot(self):
        with self.lock:
            stats = deepcopy(self.stats)
        for s in stats.values():
            s["exclusive_s"] = s["inclusive_s"] - s["children_s"]
        return {"installed": self.installed, "stats": stats, "extra": deepcopy(self.extra)}


def install_timers(timers):
    from scripts import run_v07_fe_production as prod
    from scripts import run_v07_s2_episode_batch as batch
    from task_v07 import execution
    from task_v07.expansion import group_candidate_pool as gcp, candidate_search, episode_pipeline, solo_spacing
    from task_v07.unified import (adapter, route, operation_routes, operation_shapes, patrol_shape,
                                  terminal_shapes, construction, rehearsal, timing)
    w = timers.wrap
    # 场景加载、规划入口（worker_b / 本驱动均在 prod 命名空间查找）
    w(prod, "_load_family", "场景加载 _load_family")
    w(prod, "episode_candidate_pool", "B 规划入口 episode_candidate_pool")
    w(gcp, "build_group_pool", "B 组提案池 build_group_pool")
    w(adapter, "build_spec", "B TaskSpec/公开分股 build_spec")
    w(adapter, "free_space", "B 可行空间 free_space")
    w(adapter, "work_region", "B 作业区域 work_region")
    w(adapter, "draw_shape", "B 作业形态 draw_shape")
    w(operation_shapes, "draw_operation", "B 作业形态(非过境) draw_operation")
    w(operation_shapes, "search_shape", "B 形态-区域搜索 search_shape")
    w(operation_shapes, "observation_shape", "B 形态-抵近观察 observation_shape")
    w(patrol_shape, "patrol_shape", "B 形态-巡逻 patrol_shape")
    w(terminal_shapes, "feint_shape", "B 形态-佯动 feint_shape")
    w(terminal_shapes, "intrusion_shape", "B 形态-突入 intrusion_shape")
    w(construction, "precheck_operation", "B 形态阶段进场/撤离预检 precheck_operation")
    w(adapter, "route_group", "B 衔接段 route_group")
    w(operation_routes, "route_operation", "B 衔接段(非过境) route_operation")
    w(route, "_approaches", "B 进场 _approaches")
    w(operation_routes, "_approaches", "B 进场 _approaches")
    w(operation_routes, "retreat_endpoint", "B 撤离点 retreat_endpoint")
    w(operation_routes, "connect", "B 作业段内连接 connect")
    w(adapter, "plan_checks", "B 整航线检查 plan_checks")
    w(adapter, "assemble_skeleton", "B 骨架装配 assemble_skeleton")
    w(adapter, "precheck", "B 既有输出预检 precheck")
    w(gcp, "bearing_allowed", "B 多股协调-同目标方位 bearing_allowed")
    w(episode_pipeline, "assemble_episode", "B 多组装配 assemble_episode")
    w(candidate_search, "choose_eligible", "B 同向长度比筛选 choose_eligible")
    w(prod, "write_json", "B 写盘 write_json")
    w(prod, "_write_status", "B 写状态 _write_status")
    # 仿真阶段（本驱动按 run_episode_job 的查找方式调用这些模块属性）
    w(rehearsal, "rehearse", "C 单机预演 rehearse")
    w(rehearsal, "execute", "C 单机仿真 execute(solo)")
    w(rehearsal, "measure", "C 单机判定 measure(solo)")
    w(timing, "select_timing", "C 时刻安排 select_timing")
    w(timing, "episode_plan", "C 出发延迟抽取 episode_plan")
    w(solo_spacing, "solo_interval_check", "C 2m间距检查 solo_interval_check")
    w(rehearsal, "joint_budget", "C 联合时限 joint_budget")
    w(batch, "execute", "C 联合仿真 execute(joint)")
    w(batch, "prediction_error", "C 叠加预测误差 prediction_error")
    w(batch, "write_result", "C 判定+写盘+审计 write_result")
    w(batch, "measure", "C 判定与标签 measure")
    w(batch, "write_episode", "C 写盘 write_episode")
    w(batch, "audit_episode", "C 独立审计 audit_episode")
    w(batch, "audit_groups", "C 独立审计 audit_groups")
    w(batch, "exact_frame_geometry", "C 审计几何 exact_frame_geometry")
    w(batch, "audit_geometry", "C 审计几何 audit_geometry")
    w(batch, "load_episode", "C 回读 load_episode")
    w(batch, "group_truncations", "C 半程截断检查 group_truncations")
    w(batch, "save_json", "C 写盘 save_json")
    w(prod, "qc_episode", "C 速度剖面QC qc_episode")

    def steps_now():
        return dict(execution._TRANSACTION_STATS)

    def after_joint(before, args, kwargs, elapsed):
        now = execution._TRANSACTION_STATS
        timers.extra.setdefault("joint_execute", []).append({
            "steps": now["steps"] - before["steps"], "rollbacks": now["rollbacks"] - before["rollbacks"],
            "agents": len(args[0]["agent_ids"]), "wall_s": elapsed})

    def after_solo(before, args, kwargs, elapsed):
        now = execution._TRANSACTION_STATS
        t = timers.extra.setdefault("solo_execute", {"calls": 0, "steps": 0, "rollbacks": 0, "wall_s": 0.})
        t["calls"] += 1
        t["steps"] += now["steps"] - before["steps"]
        t["rollbacks"] += now["rollbacks"] - before["rollbacks"]
        t["wall_s"] += elapsed

    Timers.extra_hooks = {"C 联合仿真 execute(joint)": (steps_now, after_joint),
                          "C 单机仿真 execute(solo)": (steps_now, after_solo)}


def _savez(path, **arrays):
    np.savez_compressed(path, **arrays)


# ---------------------------------------------------------------- 仿真阶段（只同步方式）
def c_sync(run_dir, sid, timers=None):
    from scripts import run_v07_fe_production as prod
    from scripts import run_v07_s2_episode_batch as batch
    from task_v07.unified import rehearsal, timing
    from task_v07.unified.config import load_generator
    from task_v07.expansion.contracts import P0ContractError
    from task_v07.io import sha
    run_dir = Path(run_dir)
    registration = read_json(run_dir / "registration.json")
    descriptor = prod._descriptor_for(read_json(run_dir / "descriptors" / "descriptors.json"), sid)
    scene, _family = prod._load_family(prod._family_for(registration, descriptor["family_id"]))
    planning_result = read_json(run_dir / "planning" / sid / "planning_result.json")
    cached = run_dir / "planning" / sid / "candidate_pool.pkl"
    out = run_dir / "episodes"
    skroot = out / sid
    skroot.mkdir(parents=True)
    started = time.perf_counter()
    limit = load_generator()["calibration"]["max_rounds"]
    if sha(cached) != planning_result["candidate_pool_sha256"]:
        raise P0ContractError("Cached candidate pool SHA256 differs from the registered value")
    with cached.open("rb") as stream:
        saved = pickle.load(stream)
    pool, search = saved["pool"], saved["search"]
    search.update(actual_single_agent_calibration_rounds=0, solo_flights_run=0)
    batch.save_json(skroot / "candidate_pool.json", search)
    history = []
    for variant, candidate in enumerate(pool[:limit]):
        attempt = skroot / f"geometry_{variant:02d}"; attempt.mkdir()
        sk, bundle, pre = candidate["skeleton"], candidate["bundle"], candidate["checks"]
        batch.save_json(attempt / "skeleton.json", sk)
        batch.save_json(attempt / "planning_checks.json", pre)
        rehearsal_result, solo = rehearsal.rehearse(scene, sk, reference_version="r3")
        search["actual_single_agent_calibration_rounds"] += 1
        search["solo_flights_run"] += len(solo)
        for agent, flight in solo.items():
            _savez(attempt / f"single_agent_{agent}.npz", time_us=flight["time_us"], p=flight["p"], v=flight["v"],
                   agent_ids=np.array(flight["agent_ids"]), execution_status=np.array(flight["execution_status"]))
        batch.save_json(attempt / "rehearsal.json", rehearsal_result)
        item = {"geometry_variant": variant, "candidate_index": candidate["index"], "rehearsal": rehearsal_result,
                "timing": None}
        timing_result = None
        if rehearsal_result["status"] == "rejected":
            item.update(category="rehearsal_failure")
        else:
            timing_result = timing.select_timing(sk, rehearsal_result["core_times_s"], solo)
            item["timing"] = timing_result
            batch.save_json(attempt / "timing_selection.json", timing_result)
            item.update(category="timing_conflict" if timing_result["status"] == "rejected" else None)
        calibration = {"core_times_s": rehearsal_result["core_times_s"],
                       "completed_hold_times_s": rehearsal_result["completion_times_s"],
                       "timing_plans": None if timing_result is None else timing_result["plans"],
                       "candidate_index": candidate["index"], "calibration_round": variant + 1}
        batch.save_json(attempt / "timing_calibration.json", calibration)
        batch.save_json(attempt / "candidate_search_progress.json",
                        {k: search[k] for k in ("actual_single_agent_calibration_rounds", "solo_flights_run")})
        history.append(item)
        if item["category"] is not None:
            continue
        batch.save_json(skroot / "skeleton.json", sk)
        batch.save_json(skroot / "planning_checks.json", pre)
        batch.save_json(skroot / "timing_calibration.json", calibration)
        batch.save_json(skroot / "timing_selection.json", timing_result)
        batch.save_json(skroot / "geometry_history.json", history)
        batch.save_json(skroot / "candidate_search.json", search)
        setup_s = time.perf_counter() - started
        mode = "synchronous"
        plan = timing_result["plans"][mode]
        current = deepcopy(sk)
        run = batch.execute(current, plan["departure_delays_s"],
                            time_budget=rehearsal.joint_budget(current, plan["departure_delays_s"],
                                                               rehearsal_result["completion_times_s"]),
                            reference_version="r3")
        prediction = batch.prediction_error(solo, plan, run, timing_result["overlay"][mode])
        row = batch.write_result(scene, descriptor, current, bundle, run, plan, rehearsal_result["core_times_s"],
                                 mode, out, setup_s, extra_metrics={
                                     "geometry_candidate_budget": search["candidate_budget"],
                                     "geometry_candidates_attempted": search["attempted_candidates"],
                                     "single_agent_calibration_rounds": search["actual_single_agent_calibration_rounds"],
                                     "solo_flights_run": search["solo_flights_run"],
                                     "selected_candidate_index": candidate["index"],
                                     "rehearsal": rehearsal_result, "timing_selection": timing_result["versions"],
                                     "solo_overlay_prediction_error": prediction},
                                 scope=registration["FE_SCOPE"])
        batch.save_json(skroot / mode / "solo_overlay_comparison.json", prediction)
        qc = prod.qc_episode(out / row["path"], sid, mode)
        (run_dir / "qc").mkdir(exist_ok=True)  # worker_c 依赖批次目录预建的 qc/；隔离目录里自己建
        batch.save_json(run_dir / "qc" / f"{sid}__{mode}.json", qc)
        return {"status": "generated", "row_state": row["state"], "task_result": row["task_result"],
                "execution_status": row["execution_status"], "simulation_wall_s": row["simulation_wall_s"],
                "setup_s": setup_s, "episode_postprocess_wall_s": row["episode_postprocess_wall_s"],
                "selected_candidate_index": candidate["index"], "geometry_variants_tried": variant + 1,
                "n_agents": len(current["agent_ids"]), "n_task_groups": len(current["group_skeletons"]),
                "sim_duration_s": row["duration_s"], "c_stage_wall_s": time.perf_counter() - started}
    return {"status": "exhausted", "history_categories": [h.get("category") for h in history],
            "c_stage_wall_s": time.perf_counter() - started}


def run_plan(run_dir, sid):
    from scripts import run_v07_fe_production as prod
    started = time.perf_counter()
    code = prod.worker_b(run_dir, sid)
    status = read_json(Path(run_dir) / "status" / f"B__{sid}.json")
    return {"returncode": code, "status": status["status"], "planning_wall_s": status.get("planning_wall_s"),
            "b_stage_wall_s": time.perf_counter() - started}


# ---------------------------------------------------------------- 子命令
def cmd_plan(args):
    run_dir = prepare_run_dir(args.run, args.sid, args.out)
    result = run_plan(run_dir, args.sid)
    write_json(Path(args.out) / "plan_result.json", result)
    print(json.dumps(result, ensure_ascii=False))


def cmd_sample(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    timers = Timers()
    install_timers(timers)
    state = {"run_id": args.run, "skeleton_id": args.sid, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "complete": False, "phase": "prepare"}
    stop = threading.Event()

    def flush():
        write_json(out / "stage_timing.json", {**state, "elapsed_s": time.perf_counter() - t0, **timers.snapshot()})

    def loop():
        while not stop.wait(60):
            flush()

    t0 = time.perf_counter()
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    run_dir = prepare_run_dir(args.run, args.sid, out)
    try:
        state["phase"] = "B"
        state["B"] = run_plan(run_dir, args.sid)
        flush()
        if state["B"]["status"] == "PASS":
            state["phase"] = "C_synchronous"
            state["C_synchronous"] = c_sync(run_dir, args.sid, timers)
    except BaseException as exc:
        import traceback
        state["error"] = {"repr": repr(exc), "traceback": traceback.format_exc()}
        stop.set()
        flush()
        raise
    state["phase"] = "done"
    state["complete"] = True
    state["output_bytes"] = {"planning": dir_bytes(run_dir / "planning"), "episodes": dir_bytes(run_dir / "episodes"),
                             "episode_synchronous_dir": dir_bytes(run_dir / "episodes" / args.sid / "synchronous")
                             if (run_dir / "episodes" / args.sid / "synchronous").exists() else 0,
                             "qc": dir_bytes(run_dir / "qc") if (run_dir / "qc").exists() else 0}
    stop.set()
    flush()
    print(json.dumps({k: state[k] for k in ("B", "C_synchronous") if k in state}, ensure_ascii=False))


def _write_profile(profiler, prof_path, txt_path, header):
    profiler.dump_stats(str(prof_path))
    import io
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(header)
        for key, title in (("cumulative", "按累计时间（cumulative）排序前 30 项"), ("tottime", "按自身时间（tottime）排序前 30 项")):
            buf = io.StringIO()
            stats = pstats.Stats(str(prof_path), stream=buf)
            stats.sort_stats(key).print_stats(30)
            f.write(f"\n## {title}\n\n```\n{buf.getvalue()}```\n")


def cmd_profile(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    from task_v07 import execution
    run_dir = prepare_run_dir(args.run, args.sid, out)
    profiler = cProfile.Profile()
    info = {"run_id": args.run, "skeleton_id": args.sid, "target": args.target}
    if args.target == "plan":
        t = time.perf_counter()
        profiler.enable()
        info["B"] = run_plan(run_dir, args.sid)
        profiler.disable()
        info["profiled_wall_s"] = time.perf_counter() - t
    else:
        info["B_unprofiled"] = run_plan(run_dir, args.sid)
        from scripts import run_v07_s2_episode_batch as batch
        original = batch.execute
        joint = {}

        def joint_execute(*a, **k):
            before = dict(execution._TRANSACTION_STATS)
            t1 = time.perf_counter()
            result = original(*a, **k)
            joint.update(wall_s=time.perf_counter() - t1, agents=len(a[0]["agent_ids"]),
                         steps=execution._TRANSACTION_STATS["steps"] - before["steps"],
                         rollbacks=execution._TRANSACTION_STATS["rollbacks"] - before["rollbacks"],
                         samples_10hz=len(result["time_us"]), sim_end_s=result["end_us"] / 1e6)
            return result

        batch.execute = joint_execute
        t = time.perf_counter()
        profiler.enable()
        info["C_synchronous"] = c_sync(run_dir, args.sid)
        profiler.disable()
        info["profiled_wall_s"] = time.perf_counter() - t
        info["joint_execute"] = joint
        if joint:
            info["joint_us_per_step_per_agent"] = joint["wall_s"] / (joint["steps"] * joint["agents"]) * 1e6
    prof = out / f"profile_{args.name}.prof"
    header = (f"# V8-01 §5.3 cProfile：{args.name}\n\n- 批次/骨架：{args.run} / {args.sid}\n- 剖析对象：{args.target}\n"
              f"- 运行信息：\n\n```json\n{json.dumps(info, ensure_ascii=False, indent=1, default=str)}\n```\n")
    _write_profile(profiler, prof, args.txt, header)
    write_json(out / "profile_info.json", info)


def cmd_resume(args):
    """§5.4：用生产方式（r3）对第一架飞机完整仿真得 A；在中点以 A 的状态为初值续跑剩余航线得 B。"""
    from task_v07.execution import execute
    from swarm_sim.fast_dynamics.route_tracker import RouteTracker  # noqa: F401  仅为确认接口位置
    task = read_json(args.task)
    agent = task["agent_ids"][0]
    group = next(g for g in task["group_skeletons"].values() if agent in g["members"])
    a_run = execute(group, {a: 0. for a in group["members"]}, only_agent=agent, reference_version="r3")
    t_us = np.asarray(a_run["time_us"])
    route = np.asarray(group["references"][agent]["points_enu_m"], float)
    release_us = round(group["initial_settle_s"] * 1e6)
    mid = (release_us + int(t_us[-1])) // 2
    k = int(np.searchsorted(t_us, mid - mid % 100000))  # 对齐到 10 Hz 输出（也是 20 ms 积分步的整数倍）
    ts_us = int(t_us[k])
    p_s, v_s, a_s = (np.asarray(a_run[key])[k, 0] for key in ("p", "v", "a"))
    # 剩余航线：按 t_s 前的轨迹沿航线单调推进，确定当前所在航段 j（p 位于 route[j]→route[j+1] 之间）
    seg = 0
    for i in range(k + 1):
        if t_us[i] < release_us:
            continue
        xy = np.asarray(a_run["p"])[i, 0, :2]
        best, best_d = seg, None
        for j in range(seg, len(route) - 1):
            a, b = route[j, :2], route[j + 1, :2]
            u = b - a
            s = float(np.clip((xy - a) @ u / (u @ u), 0, 1))
            d = float(np.linalg.norm(a + s * u - xy))
            if best_d is None or d < best_d - 1e-9:
                best, best_d = j, d
            if j > seg + 3:
                break
        seg = best
    remaining = np.vstack([[p_s[0], p_s[1], route[0, 2]], route[seg + 1:]])

    def resume(p, v, a):
        sk = deepcopy(group)
        sk["initial_settle_s"] = 0.
        sk["initial_states"] = [dict(s) for s in group["initial_states"]]
        for s in sk["initial_states"]:
            if s["agent_id"] == agent:
                s.update(position_enu_m=list(map(float, p)), velocity_enu_m_s=list(map(float, v)),
                         acceleration_enu_m_s2=list(map(float, a)))
        sk["references"] = deepcopy(group["references"])
        sk["references"][agent]["points_enu_m"] = remaining.tolist()
        return execute(sk, {x: 0. for x in group["members"]}, only_agent=agent, reference_version="r3")

    def compare(b_run):
        tb = np.asarray(b_run["time_us"]) + ts_us
        common = np.intersect1d(t_us[t_us >= ts_us], tb)
        ia = np.searchsorted(t_us, common)
        ib = np.searchsorted(tb, common)
        pa, pb = np.asarray(a_run["p"])[ia, 0], np.asarray(b_run["p"])[ib, 0]
        va, vb = np.asarray(a_run["v"])[ia, 0], np.asarray(b_run["v"])[ib, 0]
        dp = np.linalg.norm(pa - pb, axis=1)
        dv = np.linalg.norm(va - vb, axis=1)
        first10 = common < ts_us + 10_000_000
        return {"compared_samples": int(len(common)), "max_position_diff_m": float(dp.max()),
                "max_velocity_diff_m_s": float(dv.max()),
                "max_position_diff_first_10s_m": float(dp[first10].max()) if first10.any() else None,
                "max_velocity_diff_first_10s_m_s": float(dv[first10].max()) if first10.any() else None,
                "position_diff_at_end_m": float(dp[-1]),
                "A_end_s": float(a_run["end_us"] / 1e6), "B_end_plus_ts_s": float(b_run["end_us"] / 1e6 + ts_us / 1e6),
                "A_status": a_run["execution_status"], "B_status": b_run["execution_status"]}

    zero = np.zeros(3)
    variants = {"p_v_a": resume(p_s, v_s, a_s), "p_v": resume(p_s, v_s, zero), "p_only": resume(p_s, zero, zero)}
    result = {"task_json": str(Path(args.task).relative_to(DATA_ROOT)) if str(args.task).startswith(str(DATA_ROOT)) else str(args.task),
              "agent": agent, "group_id": group["group_id"], "route_points": len(route), "reference_version": "r3",
              "t_s": ts_us / 1e6, "t_s_frame": k, "release_s": release_us / 1e6,
              "state_at_t_s": {"p": p_s.tolist(), "v": v_s.tolist(), "a": a_s.tolist()},
              "remaining_route_starts_after_segment": seg, "remaining_route_points": len(remaining),
              "B_input": "skeleton.initial_states[agent] 的 position/velocity/acceleration = A 在 t_s 的 p/v/a；"
                         "initial_settle_s=0、出发延迟 0；参考航线 = [A 在 t_s 的平面位置(航线高度)] + 其后的原航点",
              "comparisons": {name: compare(run) for name, run in variants.items()}}
    write_json(Path(args.out) / "resume_result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=1))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "sample", "profile"):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True)
        p.add_argument("--sid", required=True)
        p.add_argument("--out", required=True)
        if name == "profile":
            p.add_argument("--target", choices=("plan", "sim"), required=True)
            p.add_argument("--name", required=True)
            p.add_argument("--txt", required=True)
    p = sub.add_parser("resume")
    p.add_argument("--task", required=True)
    p.add_argument("--out", required=True)
    args = parser.parse_args()
    {"plan": cmd_plan, "sample": cmd_sample, "profile": cmd_profile, "resume": cmd_resume}[args.cmd](args)


if __name__ == "__main__":
    main()
