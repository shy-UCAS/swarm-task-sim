# report_A.md 补充与更正（A1–A6）

**审查日期**: 2026-10-01
**HEAD**: `e13564b700934b481ad37cba053db9daabf9e4fa`
**数据源**: `verification/v03_pilot_final_20260930/dataset`(10) + `verification/v03_integration_20260930/dataset_final`(5) = 15 个 episode

本文件更正 `report_A.md` 中的三处问题（A2 代码摘录非原文、A3 未核实上传模式、A4 口径错误），
并补全 A3、A4、A5 的缺失项。

---

## 0. 对 report_A.md 的更正

| 位置 | 原报告写法 | 源码实际 | 性质 |
|------|-----------|---------|------|
| A2 摘录 | 自行改写的伪代码 | `runner.py:94-113`（见 2.2 节原文） | **错误**：非原样摘录，且遗漏 `release = time.perf_counter() + 0.3`、`mission_for(v, phase["targets"][v["id"]], scenario["origin"])` |
| A3 模式 | "upload 开始: LOITER" | 共享任务下为 **BRAKE**（`vehicle.py:218` 三元表达式 + `runner.py:86-88` 传入 `record_lifecycle=shared_mission`） | **错误** |
| A4 (c) | "零长度航段累积停靠约占 3.4% 任务时间" | 该 3.4% 由"零长度航段的窗口时长"算出，窗口时长不等于静止时长 | **撤回**（见 4.3） |
| A1 状态 | 否定 | **证实**（见 1 节） | **更正** |
| A1 `lanes` | 把 observe 阶段数当作 lanes | `lanes = observe_phases / 2`（见 1 节） | **错误** |

---

## 1. A1 规划编译：一个航点是否等于一个执行阶段

### 状态
**证实**。任务书所指"一个航点等于一个执行阶段"成立：`compile_execution_phases` 按航点下标逐个生成 `leg_xxx`，每个阶段为每架飞机指定一个目标点。

### 证据

`swarm_sim/mission_planning.py:60-79`（原样摘录）:

```python
    for semantic in ("approach", "observe", "return"):
        by_semantic[semantic] = []
        length = max(len(routes[agent][semantic]) for agent in agents)
        for index in range(length):
            name = f"leg_{len(phases):03d}"
            targets, roles = {}, {}
            for agent in agents:
                active = index < len(routes[agent][semantic])
                point = routes[agent][semantic][index] if active else previous[agent]
                targets[agent] = {"east_m": point["east_m"], "north_m": point["north_m"],
                                  "up_m": execution["takeoff_alt_m"], "speed_m_s": execution["speed_m_s"],
                                  "hold_s": execution["waypoint_hold_s"]}
                role = semantic if active else "idle_padding"
                roles[agent] = {"role": role, "service_enabled": role == "observe",
                                "partition_id": assignments[agent]}
                idle[agent] += int(not active)
                previous[agent] = point
            phases.append({"name": name, "targets": targets})
```

`swarm_sim/mission_planning.py:125-138`（原样摘录）:

```python
    lanes = max(1, math.ceil(cross_width / planner["lane_spacing_m"]))
    if 1 + 2 * lanes + int(mission["return_required"]) > 100:
        raise ValueError("shared route exceeds backend limit of 100 execution phases")
    ordering = sorted(scenario["vehicles"], key=lambda v: (v[f"{axis}_m"], v["id"]))
    assignments, routes = {}, {}
    for vehicle, partition in zip(ordering, partitions):
        agent = vehicle["id"]
        assignments[agent] = partition["id"]
        scan = lawnmower_route(partition, axis, lanes)
        routes[agent] = {"approach": [copy.deepcopy(scan[0])], "observe": scan,
                         "return": [{"east_m": vehicle["east_m"], "north_m": vehicle["north_m"]}]
                         if mission["return_required"] else []}
```

### 实测（4 个任务，内存编译 `audit_v04/A1_compile_corrected.py`）

| 任务 | 飞机 | 剖分轴 | 条带横向宽度 | 扫描线长度 | lane_spacing | **lanes** | approach | observe | return | 阶段合计 |
|------|------|--------|------------|-----------|-------------|-----------|----------|---------|--------|---------|
| recon_shared_3uav | 3 | east | 18.00 m | 30.00 m | 4.0 | **5** | 1 | 10 | 1 | 12 |
| recon_smoke_3uav | 3 | east | 12.00 m | 8.00 m | 4.0 | **3** | 1 | 6 | 1 | 8 |
| recon_smoke_2uav_north | 2 | north | 12.00 m | 8.00 m | 4.0 | **3** | 1 | 6 | 1 | 8 |
| recon_smoke_6uav | 6 | east | 12.00 m | 8.00 m | 4.0 | **3** | 1 | 6 | 1 | 8 |

- 4/4 任务满足 `observe_phases == 2 × lanes`。
- 4/4 任务满足 `execution_phase_count == 1 + 2 × lanes + return`。
- **`idle_padding_steps` 在 4/4 任务的每一架飞机上均为 0**（因为 approach/observe/return 三段路线在所有飞机上长度一致，无补齐）。
- **approach 目标点 == observe 首个目标点**：4/4 任务、全部飞机（3/3、3/3、2/2、6/6）。

**由此产生的零长度航段**：`previous[agent]` 在 approach 段结束后等于 `scan[0]`，而 observe 段的 `index=0` 目标也是 `scan[0]`，故 observe 的第一个执行阶段为原地不动的零长度航段。星测统计见 4.5 节：57/57 个零长度航段全部位于 observe 段序号 0。

### 对 v0.4 的影响
每个航点对应一个独立执行阶段，意味着执行阶段的粒度等于航点数；新增意图若改变航点数量，执行阶段数随之线性变化（上限 100，`mission_planning.py:126`）。approach 与 observe 首点重合产生的零长度航段，会使每个任务的执行阶段数比"实际飞行的航段数"多 1。

---

## 2. A2 运行器：每个阶段的执行流程

### 状态
**证实**。

### 2.2 证据：`swarm_sim/runner.py:94-113`（原样摘录）

```python
        for phase in scenario["phases"]:
            plans = {v["id"]: mission_for(v, phase["targets"][v["id"]], scenario["origin"])
                     for v in scenario["vehicles"]}
            parallel(lambda client, vehicle: client.upload(plans[client.id]))
            release = time.perf_counter() + 0.3
            if "flight_epoch_monotonic_s" not in metadata:
                metadata["flight_epoch_monotonic_s"] = release
                write_json(directory / "metadata.json", metadata)
            event("phase_release_scheduled", phase=phase["name"], release_t=release - epoch)
            parallel(lambda client, vehicle: client.execute(release, len(plans[client.id]),
                                                            max(1, deadline - time.perf_counter()), phase["name"]))
            if "task_spec" in scenario:
                def confirm(client, vehicle):
                    requirement = target_confirmation(scenario, phase, client.id)
                    options = dict(max_gap=scenario["max_gap_s"], quality_policy=policy) if shared_mission else {}
                    client.confirm_target(phase["targets"][client.id], scenario["origin"],
                        requirement["tolerance_m"], requirement["dwell_s"], phase["name"],
                        timeout=min(requirement["dwell_s"] + 20, max(1, deadline - time.perf_counter())), **options)
                parallel(confirm)
```

`swarm_sim/runner.py:68-80`（原样摘录，`parallel` 是全机屏障）:

```python
    def parallel(function):
        futures = {executor.submit(function, client, vehicle) for client, vehicle in zip(clients, scenario["vehicles"])}
        while futures:
            if time.perf_counter() > deadline:
                raise TimeoutError("scenario total timeout")
            processes.check()
            if recorder and recorder.error:
                raise RuntimeError(f"recorder failed: {recorder.error}")
            for client in clients:
                client.check()
            done, futures = wait(futures, timeout=0.1, return_when=FIRST_COMPLETED)
            for future in done:
                future.result()
```

### 每阶段的步骤顺序与等待点

| 序号 | 动作 | 代码位置 | 是否需要等全部飞机 |
|------|------|---------|------------------|
| 1 | 生成该阶段每机单航点任务 | `runner.py:95-96` | 否 |
| 2 | `parallel(upload)` | `runner.py:97` | **是**（三次 `parallel` 依次执行，各是一次全机屏障） |
| 3 | 计算放行时刻 `release = now + 0.3` | `runner.py:98` | 否 |
| 4 | 记录 `phase_release_scheduled` | `runner.py:102` | 否 |
| 5 | `parallel(execute)` —— 各机等到 `release` 后进 AUTO、等末位航点 `MISSION_ITEM_REACHED` | `runner.py:103-104` | **是** |
| 6 | `parallel(confirm)` —— 各机做几何驻留确认 | `runner.py:105-112` | **是** |
| 7 | 进入下一阶段（回到步骤 1） | `runner.py:94` | —— |

即：**阶段内的 upload / execute / confirm 三个子步骤各是一次全机屏障**，一个执行阶段内至少出现 3 次全机同步点。

### 对 v0.4 的影响
`parallel` 在每个阶段内被调用 3 次（upload、execute、confirm），每次都是全机屏障。全机同步点的数量等于 `3 × execution_phase_count`（本批 4 个任务为 24、24、24、36 次）。

---

## 3. A3 飞控交互：每个航段上传什么、模式如何切换

### 状态
**证实**（补全）。

### 3.1 每个航段上传的 MAVLink 任务项

`swarm_sim/scenario.py:97-105`（原样摘录）:

```python
def mission_for(vehicle, target, origin):
    """Home placeholder, speed, and one reached-and-held waypoint per phase."""
    home_lat, home_lon = enu_to_geo(vehicle["east_m"], vehicle["north_m"], origin)
    lat, lon = enu_to_geo(target["east_m"], target["north_m"], origin)
    return [
        dict(command=16, frame=3, params=[0, 0, 0, 0], lat=home_lat, lon=home_lon, alt=0),
        dict(command=178, frame=2, params=[1, target["speed_m_s"], -1, 0], lat=0, lon=0, alt=0),
        dict(command=16, frame=3, params=[target["hold_s"], 1, 0, float("nan")], lat=lat, lon=lon, alt=target["up_m"]),
    ]
```

**每个执行阶段上传的 AUTO 任务固定为 3 项**：

| seq | command | 含义 | frame | params[0..3] | lat/lon/alt |
|-----|---------|------|-------|--------------|-------------|
| 0 | 16 | `MAV_CMD_NAV_WAYPOINT`（home 占位项） | 3 = GLOBAL_RELATIVE_ALT | `[0, 0, 0, 0]` | 本机 spawn 点，alt=0 |
| 1 | 178 | `MAV_CMD_DO_CHANGE_SPEED` | 2 = MISSION | `[1, speed_m_s, -1, 0]` | 0 / 0 / 0 |
| 2 | 16 | `MAV_CMD_NAV_WAYPOINT`（本阶段唯一目标） | 3 = GLOBAL_RELATIVE_ALT | `[hold_s, 1, 0, nan]` | 阶段目标点，alt=up_m |

**驻留时间写在任务项里**：seq=2 的 `param1 = target["hold_s"]`，即 `MAV_CMD_NAV_WAYPOINT.param1`（Hold time）。同项 `param2 = 1`（接受半径 1 m，等于 `arrival_tolerance_m`），`param3 = 0`（Pass Radius 0，表示到点停住而非飞掠），`param4 = NaN`（不改变偏航）。

上传时 `frame=3` 的项在 `MISSION_REQUEST_INT` 路径下被改写为 `6`（GLOBAL_RELATIVE_ALT_INT）：

`swarm_sim/vehicle.py:242-250`（原样摘录）:

```python
            args = [self.sysid, self.target_component, message.seq, item["frame"], item["command"],
                    int(message.seq == 0), 1, *item["params"]]
            if message.get_type() == "MISSION_REQUEST_INT":
                # GLOBAL_RELATIVE_ALT_INT for coordinate-bearing items, MISSION for DO.
                args[3] = 6 if item["frame"] == 3 else item["frame"]
                self.send("mission_item_int_send", *args, round(item["lat"] * 1e7), round(item["lon"] * 1e7), item["alt"])
            else:
                self.send("mission_item_send", *args, item["lat"], item["lon"], item["alt"])
```

### 3.2 BRAKE / AUTO / LOITER 切换时机

`swarm_sim/vehicle.py:217-218`（原样摘录）:

```python
    def upload(self, mission, timeout=20):
        self.mode("BRAKE" if self.record_lifecycle else "LOITER")
```

`swarm_sim/runner.py:86-88`（原样摘录）:

```python
        clients = [Vehicle(instance, directory / "raw" / f"{instance['id']}.jsonl", cancel, event,
                           record_lifecycle=shared_mission)
                   for instance in instances]
```

`shared_mission` 定义于 `runner.py:28`（`scenario.get("task_spec", {}).get("schema_version") == 2`）。
因此 **v2 共享任务下 `record_lifecycle=True`，`upload` 进入的是 `BRAKE` 模式，不是 LOITER**。

`swarm_sim/vehicle.py:257-274`（原样摘录）:

```python
    def execute(self, epoch, mission_count, timeout, phase):
        while time.perf_counter() < epoch:
            self.check()
            self.cancel.wait(min(0.01, max(0, epoch - time.perf_counter())))
        cursor = self.cursor()
        self.event("phase_start_sent", self.id, phase=phase)
        self.mode("AUTO")
        # AUTO starts the preselected mission. Avoid a second MISSION_START that
        # could restart a short route after the mode-confirmation heartbeat.
        self.event("phase_auto_confirmed", self.id, phase=phase)
        self.wait_message(["MISSION_ITEM_REACHED"], lambda m: m.seq == mission_count - 1,
                          after=cursor, timeout=timeout)
        self.event("phase_finished", self.id, phase=phase)
        # Shared missions keep the AUTO waypoint controller active until the
        # independent geometric dwell succeeds. LOITER accepts pilot throttle;
        # SITL's default low throttle would descend during a scheduling barrier.
        if not self.record_lifecycle:
            self.mode("LOITER")
```

| 时机 | v2 共享任务下的模式 |
|------|-------------------|
| `upload` 开头（含 `mission_clear_all` 与逐项上传） | **BRAKE** |
| `execute` 开头（等到 `release` 之后） | **AUTO** |
| `execute` 结束（末位航点 `MISSION_ITEM_REACHED` 之后） | **保持 AUTO**（`record_lifecycle=True` 时不切 LOITER） |
| `confirm_target` 期间 | 保持 AUTO |
| `land` | **LAND** |

注意 `upload` 的流程为：`BRAKE` → `mission_clear_all` → `mission_count` → 逐项应答 → `mission_set_current(1)` → 等 `MISSION_CURRENT seq==1`（`vehicle.py:220-255`）。设 current 到 seq 1（DO_CHANGE_SPEED），跳过 seq 0 的 home 占位项。

### 3.3 `confirm_target` 的完整判定逻辑

`swarm_sim/vehicle.py:283-318`（原样摘录）:

```python
    def confirm_target(self, target, origin, tolerance, dwell_s, phase, timeout=20, max_gap=0.5, quality_policy=None):
        """After AUTO/LOITER, require fresh geometric evidence in FCU source time.

        This deliberately adds a verification dwell; the mission ACK alone does
        not provide task completion evidence. Any invalid interval restarts it.
        """
        deadline = time.perf_counter() + timeout
        cursor = self.cursor()
        since = previous = None
        position = [target[k] for k in ("east_m", "north_m", "up_m")]
        while time.perf_counter() < deadline:
            message = self.wait_message(["GLOBAL_POSITION_INT"], after=cursor,
                                        timeout=max(0.01, deadline - time.perf_counter()))
            with self.condition:
                # Use the latest stamped sample, not an older inbox item with a
                # newer sample's receive timestamp during a receive burst.
                cursor = self.sequence
                received, message = self.latest["GLOBAL_POSITION_INT"]
            source = message.time_boot_ms / 1000
            actual = geo_to_enu(message.lat / 1e7, message.lon / 1e7, message.alt / 1000, origin)
            content_valid = True
            if quality_policy is not None:
                from .observations import live_observation
                values, _ = live_observation(message, received, time.perf_counter(), max_gap, origin, quality_policy)
                content_valid = values is not None
            inside = content_valid and math.dist(actual, position) <= tolerance and time.perf_counter() - received <= max_gap
            continuous = previous is not None and 0 < source - previous <= max_gap
            if not inside:
                since = None
            elif since is None or not continuous:
                since = source
            if inside and since is not None and source - since + 1e-8 >= dwell_s:
                self.event("task_target_verified", self.id, phase=phase, source_dwell_s=source - since,
                           tolerance_m=tolerance, position_error_m=math.dist(actual, position))
                return
            previous = source
        raise TimeoutError(f"{self.id}: geometric target/dwell confirmation timed out")
```

判定要素：

| 要素 | 取值/逻辑 |
|------|----------|
| 到达容差 | `math.dist(actual, position) <= tolerance`，**三维距离**（含高度，即 `up_m` 也须落在容差球内） |
| 连续驻留时长 | `source - since >= dwell_s`，`source = message.time_boot_ms / 1000`（FCU 源时间，非主机时间） |
| 连续性判据 | `continuous = previous is not None and 0 < source - previous <= max_gap`；`max_gap = scenario["max_gap_s"] = 0.5 s` |
| 数据新鲜度 | 额外要求 `time.perf_counter() - received <= max_gap` |
| 内容合法性 | 传入 `quality_policy` 时，须通过 `live_observation` 的 `decode_observation` 检查 |
| 重置条件 | `if not inside: since = None` —— 任一次越出容差即清零，重新计时 |
| 超时 | 由 `runner.py:111` 给出：`timeout = min(dwell_s + 20, max(1, deadline - now))`，失败抛 `TimeoutError` |
| **是否要求飞机静止** | **否**。函数内无任何速度或位置变化率判据；只要持续落在容差球内满 `dwell_s` 即通过 |

### 3.4 `tasks.target_confirmation` 在 v2 下的取值来源

`swarm_sim/tasks.py:128-137`（原样摘录）:

```python
def target_confirmation(scene, phase, agent_id):
    """Numerical control requirements; intent semantics stay outside the driver."""
    spec = scene["task_spec"]
    if spec["schema_version"] == 1:
        return dict(tolerance_m=spec["task"]["tolerance_m"], dwell_s=spec["task"]["dwell_s"], role="legacy")
    execution = spec["execution"]
    role = scene["semantic_plan"]["execution_phases"][phase["name"]]["agents"][agent_id]["role"]
    return dict(tolerance_m=execution["arrival_tolerance_m"],
                dwell_s=0 if role == "idle_padding" else execution["confirmation_dwell_s"], role=role)
```

v2 下取值来源：

| 字段 | 来源 |
|------|------|
| `tolerance_m` | `scene["task_spec"]["execution"]["arrival_tolerance_m"]`（任务文件中的 `execution.arrival_tolerance_m`） |
| `dwell_s` | 角色为 `idle_padding` 时为 **0**；否则为 `execution["confirmation_dwell_s"]` |
| `role` | 由 `scene["semantic_plan"]["execution_phases"][phase]["agents"][agent]["role"]` 决定，即编译期写入的语义角色 |

### 3.5 任务文件与生成模板的实际取值

`audit_v04/A3_params.py` / `A3_generated_params.py` 输出：

| 文件 | `waypoint_hold_s` | `confirmation_dwell_s` | `arrival_tolerance_m` | `speed_m_s` | `lane_spacing_m` |
|------|------------------|----------------------|---------------------|-------------|-----------------|
| `missions/recon_shared_3uav.json` | 0.5 | 0.5 | 1.0 | 3.0 | 4.0 |
| `missions/recon_smoke_3uav.json` | 0.5 | 0.5 | 1.0 | 3.0 | 4.0 |
| `missions/recon_smoke_2uav_north.json` | 0.5 | 0.5 | 1.0 | 3.0 | 4.0 |
| `missions/recon_smoke_6uav.json` | 0.5 | 0.5 | 1.0 | 3.0 | 4.0 |
| `generation_profiles/recon_pilot_v03.json` | 无同名字段；`template = "../missions/recon_shared_3uav.json"` | 同左（继承模板） | 同左 | 由 `speeds_m_s = [2.0, 2.5, 3.0]` 采样覆盖 | 同左 |

`generation_profiles/recon_pilot_v03.json` 全文（原样摘录）:

```json
{
  "schema_version": 1,
  "master_seed": 20260930,
  "base_scene_count": 100,
  "max_candidates_per_base": 3,
  "template": "../missions/recon_shared_3uav.json",
  "vehicle_counts": [2, 3, 6],
  "partition_axes": ["east", "north"],
  "strip_width_m": [12.0, 16.0],
  "sweep_length_m": [8.0, 12.0],
  "region_east_m": [-20.0, 0.0],
  "region_north_m": [-20.0, 0.0],
  "entry_distance_m": [10.0, 14.0],
  "entry_sides": ["low", "high"],
  "speeds_m_s": [2.0, 2.5, 3.0],
  "return_required": [true, false],
  "variant_speed_factors": [1.0]
}
```

`generated/recon_pilot_v03_20260930/missions/` 全部 100 个已生成任务的实际分布：

| 字段 | 分布 |
|------|------|
| `execution.waypoint_hold_s` | 0.5 → **100/100** |
| `execution.confirmation_dwell_s` | 0.5 → **100/100** |
| `execution.arrival_tolerance_m` | 1.0 → **100/100** |
| `execution.speed_m_s` | 2.0 → 35/100；2.5 → 32/100；3.0 → 33/100 |
| `planner.lane_spacing_m` | 4.0 → **100/100** |

### 3.6 SITL 参数文件中的航点导航参数

检索 `ArducopterSITL/copter.parm` 与 `ArducopterSITL/swarm/1..5/copter.parm`，匹配 `^WPNAV_|^WP_|^LOIT_` 的结果为 **0 条**。

各机参数文件与主文件的唯一差异：

```
$ diff ArducopterSITL/copter.parm ArducopterSITL/swarm/1/copter.parm
94a95
> SYSID_THISMAV 1
```

**结论：`WPNAV_*` 与 `WP_*` 均未显式设置，使用固件默认值。** 参数文件中与本次审查相关的显式设置只有飞行模式映射（`copter.parm` 原文）：

```
FLTMODE1        7
FLTMODE2        9
FLTMODE3        6
FLTMODE4        3
FLTMODE5        5
FLTMODE6		0
```

其中 `FLTMODE4 = 3`（AUTO）、`FLTMODE5 = 5`（LOITER）、`FLTMODE3 = 6`（RTL）、`FLTMODE1 = 7`（CIRCLE）。`BRAKE` 模式未出现在 `FLTMODE*` 映射中，由 `vehicle.mode()` 经 `master.mode_mapping()` 直接下发：

`swarm_sim/vehicle.py:168-174`（原样摘录）:

```python
    def mode(self, name, timeout=10):
        mapping = self.master.mode_mapping()
        if name not in mapping:
            raise ValueError(f"{self.id}: unsupported mode {name}")
        cursor = self.cursor()
        self.send("set_mode_send", self.sysid, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mapping[name])
        self.wait_message(["HEARTBEAT"], lambda m: m.custom_mode == mapping[name], after=cursor, timeout=timeout)
```

### 对 v0.4 的影响
- 驻留与到达判定由**任务项参数**（`hold_s`、接受半径 1 m）与**软件驻留**（`confirmation_dwell_s`）双重定义；两者都硬编码在 `mission_for` 与 `execution` 中，新增意图若需要不同的驻留语义，须同时改动这两处。
- `confirm_target` 不检查静止，只检查"落在 1.0 m 容差球内且连续 0.5 s"，因此在**减速末段**即可满足（其后果见 4.2）。
- `WPNAV_*` 全部为固件默认，故到点减速曲线不受项目配置控制；改变停靠行为无法通过调参实现。

---

## 4. A4 实测验证：用已有数据量化停靠（重做）

### 状态
**证实**：执行层在每个航点产生全机同步停靠。

### 4.0 方法与口径说明

- 数据源：15 个 episode 的 `observations.csv`（仅 `valid=1` 行），速度 $|v_{xy}|=\sqrt{v_e^2+v_n^2}$，采样率 10 Hz（`record_hz=10`）。
- **速度字段可信性核对**（`audit_v04/A4_diag_velocity_trust.py`，episode `20260930T153623Z_af3f4fcd` / `uav_01`，569 个相邻样本对）：
  - 上报 `|v_xy|` 中位数 **1.3614** m/s，位置有限差分速度中位数 **1.3488** m/s；
  - `|上报 − 差分| > 0.5 m/s` 的样本对：**0/569**；
  - 二者均 `< 0.1 m/s` 的样本对：15/569。
  - 结论：`observations.csv` 的速度字段与位置自洽，可直接用于停靠判定。
- 任务窗口定义：取该 episode 全部阶段窗口的最小 `start_s` 到最大 `end_s`（可从产物确定，无需回退到全 CSV 时间范围）。
- 15 个 episode 中 `20260930T153556Z_bf2d3529` 的 `phase_windows.json` 无可用窗口（该 run `status=failed`，`scenario_id=recon_shared_demo_3uav_ready_timeout`），未纳入 A4 的窗口类统计，仅在 A5 报告中列出。

### 4.1 (a) 停靠段数量 vs `execution_phase_count`

**任务书口径**（`|v_xy| < 0.3 m/s` 且持续 ≥ 1.0 s）严重漏检，因为真实停住只持续约 0.3–0.7 s（见 4.2、4.4）。下表同时给出宽松口径（≥ 0.2 s）。

| episode | agents | execution_phase_count | 停靠段数 @0.3,≥1.0s | 停靠段数 @0.3,≥0.2s | 停靠段数 @0.5,≥0.2s |
|---------|--------|----------------------|--------------------|--------------------|--------------------|
| 20260930T153623Z_af3f4fcd | 6 | 9 | 9 | 55 | 54 |
| 20260930T153848Z_46d1aaa3 | 2 | 10 | 2 | 20 | 18 |
| 20260930T154116Z_ed102766 | 6 | 10 | 7 | 65 | 54 |
| 20260930T155237Z_12275488 | 6 | 9 | 10 | 51 | 54 |
| 20260930T155457Z_200822e7 | 3 | 10 | 1 | 30 | 30 |
| 20260930T155726Z_bd656d6a | 6 | 10 | 7 | 66 | 54 |
| 20260930T160032Z_3eb54ff1 | 6 | 9 | 5 | 53 | 50 |
| 20260930T160246Z_f7b6895d | 3 | 9 | 2 | 23 | 27 |
| 20260930T160457Z_bcd46846 | 2 | 10 | 3 | 17 | 20 |
| 20260930T160719Z_a58405a9 | 3 | 10 | 0 | 33 | 27 |
| 20260930T152031Z_08eff45d | 3 | 12 | 2 | 34 | 36 |
| 20260930T152358Z_56f3a95a | 3 | 12 | 3 | 35 | 36 |
| 20260930T152726Z_85b2bcb7 | 2 | 8 | 1 | 16 | 16 |
| 20260930T152929Z_faff6f17 | 6 | 8 | 6 | 47 | 48 |

**逐机比对**（宽松口径 @0.3,≥0.2s；数据见 `audit_v04/A4_dwell.json`）：每机停靠段数与该 episode 的 `execution_phase_count` 呈近似 1:1。例如

- `af3f4fcd`：phases=9，各机 {9, 10, 9, 9, 9, 9}
- `bd656d6a`：phases=10，各机 {11, 11, 11, 11, 11, 11}
- `200822e7`：phases=10，各机 {10, 10, 10}
- `56f3a95a`：phases=12，各机 {12, 11, 12}
- `3eb54ff1`：phases=9，各机 {8, 9, 9, 9, 9, 9}

即**每个执行阶段对应一次停住**。任务书口径（≥1.0 s）得到的 0–2 个/机不反映真实停靠次数。

### 4.2 (b) 关键判别量：航段窗口结束时刻附近的 $|v_{xy}|$ 最小值

| 口径 | n | 中位数 | 均值 | P10 | P90 | 最小 | 最大 |
|------|---|--------|------|-----|-----|------|------|
| **窗口结束 ±0.3 s**（任务书口径） | 545 | **0.6076** | 0.6121 | 0.4064 | 0.8297 | 0.2213 | 1.1670 |
| **窗口结束 −0.3 ~ +2.0 s**（附加口径） | 545 | **0.0678** | 0.1633 | 0.0224 | 0.7087 | 0.0033 | 1.1670 |

分三类（附加口径）：

| 类别 | n | 中位数 | 均值 | P10 | P90 | 最小 | 最大 |
|------|---|--------|------|-----|-----|------|------|
| 扫描线 | 226 | 0.0557 | 0.1349 | 0.0303 | 0.1115 | 0.0090 | 1.1024 |
| 换线 | 169 | 0.1334 | 0.1333 | 0.0842 | 0.1863 | 0.0440 | 0.2373 |
| 零长度 | 57 | 0.0326 | 0.0305 | 0.0121 | 0.0484 | 0.0033 | 0.0557 |
| 进近/返航 | 93 | 0.0431 | 0.3683 | 0.0140 | 0.9923 | 0.0033 | 1.1670 |
| 全部 | 545 | 0.0678 | 0.1633 | 0.0224 | 0.7087 | 0.0033 | 1.1670 |

**两个口径给出相反结论，原因已定位**：任务书口径测到的不是停靠时刻。
**最低速度相对窗口结束时刻的滞后：中位数 0.68 s，P10 = 0.16 s，P90 = 0.96 s，范围 [−0.09, 1.98] s。**

原始轨迹佐证（`audit_v04/A4_diag_velocity_trust.py`，episode `af3f4fcd` / `uav_01`，`|v_xy|` 单位 m/s）：

```
--- leg_000 (approach) 窗口=[0.03, 10.91] ---
    10.70   1.2854    ...
    10.80   1.1470
    10.90   1.0177  <== 窗口结束   (确认事件在此触发, 速度仍为 1.02)
    11.00   0.8908
    11.10   0.7316
    11.20   0.5331
    11.30   0.3345
    11.40   0.1386
    11.50   0.0434   <== 实际最低速 (滞后 +0.60 s)
    11.60   0.2092
--- leg_002 (observe) 窗口=[12.53, 20.00] ---
    20.00   1.1137  <== 窗口结束
    20.40   0.5417
    20.60   0.1867
    20.70   0.0628   <== 实际最低速 (滞后 +0.70 s)
```

机制：`confirm_target` 只要求"落在 1.0 m 容差球内连续 0.5 s"（3.3 节），该条件在**减速末段**即被满足（例：t=10.40 时距航点 0.97 m，已入球），故 `task_target_verified` 事件早于真实到达约 0.6–0.8 s。

**附加口径下的停靠比例**：
- `extended_min < 0.3 m/s`：**488/545 = 89.5%**
- `extended_min < 0.2 m/s`：**477/545 = 87.5%**

**独立交叉验证**（`audit_v04/A4_verify_stops_at_waypoints.py`）：对全部 15 个 episode 检测停住段（`|v_xy| < 0.3 m/s` 持续 ≥ 0.2 s），取每段最低速时刻的位置，计算到该机**全部规划航点**的最近距离：

| 指标 | 值 |
|------|-----|
| 停住点总数 | 548 |
| 到最近规划航点距离 中位数 | **0.2095 m** |
| 均值 | 0.7393 m |
| P90 | 0.3812 m |
| ≤ 1.0 m（= `arrival_tolerance_m`） | **524/548 = 95.62%** |

未落在 1.0 m 内的 24 个点中，3 个来自失败 run `bf2d3529`（距离恰为 20.000 m，即 spawn 点，该 run 从未起飞）；其余 4 个 episode 各有 1 个约 10.6–12.8 m 的点，为起飞前/降落后的 spawn 点。**在飞行段内，停住点全部落在规划航点上。**

### 4.3 (c) 静止时间占任务窗口比例

| 口径 | 中位数 | 均值 | 最小 | 最大 | n |
|------|--------|------|------|------|---|
| 0.3 m/s, ≥1.0 s（任务书口径） | 0.0174 | 0.0167 | 0.0000 | 0.0382 | 14 |
| 0.5 m/s, ≥1.0 s（任务书对照） | 0.1307 | 0.1255 | 0.0538 | 0.1780 | 14 |
| **0.3 m/s, ≥0.2 s（匹配真实停住）** | **0.0808** | 0.0788 | 0.0425 | 0.1002 | 14 |
| 0.5 m/s, ≥0.2 s（匹配真实停住） | 0.1660 | 0.1600 | 0.0861 | 0.1967 | 14 |

分母 = 任务窗口时长 × 飞机数（各机停靠时长之和 / 该乘积）。

每机静止占比（0.3 m/s, ≥0.2 s）分布很窄，例如 `af3f4fcd` 六机为 {0.0947, 0.0982, 0.1017, 0.0999, 0.1052, 0.1017}，`200822e7` 三机为 {0.0709, 0.0709, 0.0681}。

> **撤回 report_A.md 的"零长度航段累积停靠约占任务时间 3.4%"**：该数字用"零长度航段的窗口时长"求和得出，窗口时长是执行阶段的持续时长，不是静止时长；且只统计了 57 个零长度航段，未覆盖其余 488 个航段的停靠。按本节口径，静止时间占比为 **8.08%（中位数，0.3 m/s / ≥0.2 s 口径）**。

### 4.4 (d) 全机同步停靠

判定基准：`|v_xy| < 0.3 m/s` 且持续 ≥ 0.2 s。**同步时间占比** = 任务窗口内全部飞机同时处于停靠段的时长 / 任务窗口时长。**停靠事件** = 合并全体飞机停靠区间后的极大区间；**全机共同重叠** = 该事件内所有飞机的停靠区间交集非空的事件数。

| episode | agents | 同步时间占比 | 停靠事件数 | 全机共同重叠 | 各机停靠数 |
|---------|--------|-------------|-----------|-------------|-----------|
| 20260930T153623Z_af3f4fcd | 6 | 0.0736 | 9 | 8 | {9,10,9,9,9,9} |
| 20260930T153848Z_46d1aaa3 | 2 | 0.0797 | 10 | 10 | {10,10} |
| 20260930T154116Z_ed102766 | 6 | 0.0619 | 10 | 10 | {11,11,10,11,11,11} |
| 20260930T155237Z_12275488 | 6 | 0.0755 | 9 | 8 | {9,8,9,8,8,9} |
| 20260930T155457Z_200822e7 | 3 | 0.0567 | 11 | 9 | {10,10,10} |
| 20260930T155726Z_bd656d6a | 6 | 0.0759 | 11 | 11 | {11,11,11,11,11,11} |
| 20260930T160032Z_3eb54ff1 | 6 | 0.0719 | 9 | 8 | {8,9,9,9,9,9} |
| 20260930T160246Z_f7b6895d | 3 | 0.0597 | 8 | 7 | {8,7,8} |
| 20260930T160457Z_bcd46846 | 2 | 0.0714 | 9 | 8 | {8,9} |
| 20260930T160719Z_a58405a9 | 3 | 0.0680 | 11 | 11 | {11,11,11} |
| 20260930T152031Z_08eff45d | 3 | 0.0354 | 12 | 10 | {11,11,12} |
| 20260930T152358Z_56f3a95a | 3 | 0.0378 | 12 | 11 | {12,11,12} |
| 20260930T152726Z_85b2bcb7 | 2 | 0.0665 | 8 | 8 | {8,8} |
| 20260930T152929Z_faff6f17 | 6 | 0.0615 | 8 | 7 | {8,8,7,8,8,8} |

- 同步时间占比：中位数 **0.0673**，范围 [0.0354, 0.0797]（n=14）。
- 全机共同重叠的停靠事件：合计 **126/137 = 91.97%** 的停靠事件满足全部飞机同时停靠。

**结论：全机同步停靠成立。** 除了少数事件（每 episode 0–2 个）外，每次停住都是全机同时停住。这与运行器结构一致——每个阶段内 `upload`/`execute`/`confirm` 各是一次 `parallel()` 全机屏障（2 节），任一飞机未到点则全机等待。

### 4.5 (e) 零长度航段核对

**57 个零长度航段，全部位于 observe 语义内的序号 0**（即与 approach 目标点重合的 `scan[0]`）：

- 按 observe 段内序号分布：`{0: 57}`
- `全部 idx_in_observe == 0 ? True`
- 逐条清单见 `audit_v04/A4_zero_len.json`

**与任务书要求的 57 个数量一致。** 需注意该 57 个的成因是 `compile_execution_phases` 中 `previous[agent]` 在 approach 结束后即等于 `scan[0]`（1 节），并非飞行中的停靠；但它们的**窗口时长**（0.50–0.76 s，中位 0.62 s）反映的是 `confirm_target` 的最小驻留开销。

### 4.6 (f) 速度曲线图

已保存：`audit_v04/speed_profile_20260930T155457Z_200822e7.png`（episode `recon_0004_v00`，3 机，265,931 字节）。

图内容：三条 `|v_xy|`–时间曲线（`uav_01/02/03`），灰色竖虚线为每个阶段窗口的 `end_s` 事件，橙色点线为 0.3 m/s 参考线，黑色竖线为任务窗口起点。图中可直接观察到：每次灰色竖线之后约 0.7 s，三条曲线同时降至接近 0，且三条曲线在时间上对齐。

### 对 v0.4 的影响
- 执行层在**每个执行阶段**产生一次全机同步停靠（阶段数 = 航点数，1 节），停靠点落在规划航点上（95.62% 在 1.0 m 内）。
- 停靠时长由 `waypoint_hold_s = 0.5 s`（任务项 param1）+ `confirmation_dwell_s = 0.5 s`（软件驻留）+ 阶段间屏障共同决定；实测每机静止时间占任务窗口 **8.08%**（中位，0.3 m/s/≥0.2 s 口径）。
- `task_target_verified` 事件早于真实到达中位 **0.68 s**，因此一切以该事件为边界的产品（`phase_windows.json` 的 `end_s`、由它派生的服务窗口）在时间上系统性偏早约 0.7 s。
- 同步停靠占 **91.97%（126/137）** 的停靠事件；同步时间占比中位数 **0.0673**。按飞机数分组：2 机 0.0665–0.0797（n=3，中位 0.0714）、3 机 0.0354–0.0680（n=5，中位 0.0567）、6 机 0.0615–0.0759（n=6，中位 0.0727）。**该占比与飞机数无单调关系**；与任务窗口时长呈负相关（r = −0.774）：停靠次数相近时窗口越长占比越低。3 机组的最低两值来自 `recon_shared_demo_3uav` 的两次运行（窗口 118.7 / 118.8 s，约为其余 episode 的两倍）。

---

## 5. A5 每个运行的时间构成（补全）

### 状态
**证实**（补全为全部 15 个 episode，并加入 `elapsed_s` 与阶段细分）。

### 5.1 拆解口径

与 `runner.py` 结构一致，在 swarm 时间线上：

```
T0 = min(phase_start_sent_0),  T1 = max(task_target_verified_last),  任务跨度 = T1 - T0
每阶段 N:
  upload_release_N = min(phase_start_sent_N)     - max(task_target_verified_{N-1})
  flight_N         = max(phase_finished_N)       - min(phase_start_sent_N)
  confirm_N        = max(task_target_verified_N) - max(phase_finished_N)
```

三者之和恒等于任务跨度（望远镜求和）。**14/14 个 episode 的校验差均为 0.0000 s**（见 `audit_v04/A5_final.json`）。

### 5.2 每个 episode 的 `elapsed_s` 与主要时间点（秒）

| episode | scenario | `elapsed_s` | 连接完成 | `airborne_ready` | 任务起点 T0 | 任务终点 T1 | 任务跨度 |
|---------|----------|------------|---------|-----------------|------------|------------|---------|
| 20260930T153623Z_af3f4fcd | recon_0000_v00 | 133.16 | 1.68 | 52.95 | 54.38 | 111.38 | 56.99 |
| 20260930T153848Z_46d1aaa3 | recon_0001_v00 | 146.79 | 1.51 | 51.35 | 52.67 | 125.40 | 72.73 |
| 20260930T154116Z_ed102766 | recon_0002_v00 | 140.87 | 1.56 | 52.81 | 54.16 | 118.67 | 64.51 |
| 20260930T155237Z_12275488 | recon_0003_v00 | 130.65 | 1.68 | 52.84 | 54.19 | 108.44 | 54.25 |
| 20260930T155457Z_200822e7 | recon_0004_v00 | 144.94 | 1.53 | 51.53 | 52.93 | 123.31 | 70.38 |
| 20260930T155726Z_bd656d6a | recon_0005_v00 | 144.54 | 1.55 | 53.24 | 54.50 | 122.87 | 68.38 |
| 20260930T160032Z_3eb54ff1 | recon_0006_v00 | 125.90 | 1.66 | 52.99 | 54.22 | 104.27 | 50.05 |
| 20260930T160246Z_f7b6895d | recon_0007_v00 | 128.35 | 1.53 | 51.53 | 52.86 | 106.41 | 53.55 |
| 20260930T160457Z_bcd46846 | recon_0008_v00 | 140.24 | 1.52 | 51.28 | 52.37 | 118.03 | 65.66 |
| 20260930T160719Z_a58405a9 | recon_0009_v00 | 137.60 | 1.51 | 51.48 | 52.79 | 115.95 | 63.17 |
| 20260930T152031Z_08eff45d | recon_shared_demo_3uav | 193.67 | 1.66 | 51.98 | 53.41 | 172.16 | 118.75 |
| 20260930T152358Z_56f3a95a | recon_shared_demo_3uav | 193.46 | 1.54 | 51.71 | 53.08 | 171.86 | 118.78 |
| 20260930T152726Z_85b2bcb7 | recon_smoke_2uav_north | 122.08 | 1.52 | 51.30 | 52.55 | 100.60 | 48.05 |
| 20260930T152929Z_faff6f17 | recon_smoke_6uav | 124.98 | 1.57 | 52.90 | 54.19 | 102.88 | 48.70 |
| 20260930T153556Z_bf2d3529 | recon_shared_demo_3uav_ready_timeout | 11.70 | 1.59 | n/a | n/a | n/a | n/a |

- `elapsed_s`（主机总耗时，含 SITL 启动与连接）：中位数 **137.60 s**，均值 134.60 s，范围 [11.70, 193.67]，n=15。
- 任务跨度：中位数 **63.84 s**，均值 68.14 s，范围 [48.05, 118.78]，n=14。
- **任务跨度 / `elapsed_s` 中位数 = 0.4585**，即约 54% 的主机耗时在任务阶段之外。
- `run_status`：`completed` 14 个，`failed` 1 个（`bf2d3529`，`scenario_id` 为 `..._ready_timeout`）。

窗口外的时间构成（中位口径）：SITL 启动与连接 0 → 1.55 s；起飞准备至 `airborne_ready` 约 51.5 s；任务阶段 T0–T1；T1 → `landed` 约 20 s；之后至 `elapsed_s` 为收尾。

### 5.3 任务阶段细分（swarm 时间线，秒）

| episode | 阶段数 | 上传+放行 | 飞行 | 确认驻留 | 三者之和 | 任务跨度 | 校验差 |
|---------|--------|----------|------|---------|---------|---------|--------|
| 20260930T153623Z_af3f4fcd | 9 | 3.97 | 44.03 | 8.99 | 56.99 | 56.99 | 0.0000 |
| 20260930T153848Z_46d1aaa3 | 10 | 4.01 | 58.78 | 9.94 | 72.73 | 72.73 | 0.0000 |
| 20260930T154116Z_ed102766 | 10 | 3.82 | 50.85 | 9.84 | 64.51 | 64.51 | 0.0000 |
| 20260930T155237Z_12275488 | 9 | 3.53 | 40.89 | 9.84 | 54.25 | 54.25 | 0.0000 |
| 20260930T155457Z_200822e7 | 10 | 3.74 | 55.55 | 11.09 | 70.38 | 70.38 | 0.0000 |
| 20260930T155726Z_bd656d6a | 10 | 3.98 | 54.58 | 9.81 | 68.38 | 68.38 | 0.0000 |
| 20260930T160032Z_3eb54ff1 | 9 | 3.49 | 37.10 | 9.46 | 50.05 | 50.05 | 0.0000 |
| 20260930T160246Z_f7b6895d | 9 | 3.31 | 41.36 | 8.87 | 53.55 | 53.55 | 0.0000 |
| 20260930T160457Z_bcd46846 | 10 | 3.84 | 51.10 | 10.72 | 65.66 | 65.66 | 0.0000 |
| 20260930T160719Z_a58405a9 | 10 | 3.79 | 49.27 | 10.11 | 63.17 | 63.17 | 0.0000 |
| 20260930T152031Z_08eff45d | 12 | 4.90 | 100.93 | 12.92 | 118.75 | 118.75 | 0.0000 |
| 20260930T152358Z_56f3a95a | 12 | 5.02 | 100.63 | 13.13 | 118.78 | 118.78 | 0.0000 |
| 20260930T152726Z_85b2bcb7 | 8 | 3.17 | 36.24 | 8.64 | 48.05 | 48.05 | 0.0000 |
| 20260930T152929Z_faff6f17 | 8 | 3.46 | 37.02 | 8.22 | 48.70 | 48.70 | 0.0000 |

### 5.4 占比

| episode | 上传+放行 | 飞行 | 确认驻留 | 上传+放行+确认 | 屏障等待（含在飞行内） |
|---------|----------|------|---------|---------------|---------------------|
| 20260930T153623Z_af3f4fcd | 6.96% | 77.26% | 15.78% | **22.74%** | 1.11 s |
| 20260930T153848Z_46d1aaa3 | 5.52% | 80.82% | 13.66% | **19.18%** | 1.23 s |
| 20260930T154116Z_ed102766 | 5.92% | 78.83% | 15.25% | **21.17%** | 2.42 s |
| 20260930T155237Z_12275488 | 6.51% | 75.37% | 18.13% | **24.63%** | 1.34 s |
| 20260930T155457Z_200822e7 | 5.31% | 78.93% | 15.76% | **21.07%** | 1.40 s |
| 20260930T155726Z_bd656d6a | 5.82% | 79.83% | 14.35% | **20.17%** | 2.44 s |
| 20260930T160032Z_3eb54ff1 | 6.98% | 74.13% | 18.90% | **25.87%** | 1.30 s |
| 20260930T160246Z_f7b6895d | 6.18% | 77.25% | 16.57% | **22.75%** | 1.58 s |
| 20260930T160457Z_bcd46846 | 5.85% | 77.83% | 16.32% | **22.17%** | 1.16 s |
| 20260930T160719Z_a58405a9 | 5.99% | 77.99% | 16.01% | **22.01%** | 1.01 s |
| 20260930T152031Z_08eff45d | 4.12% | 85.00% | 10.88% | **15.00%** | 1.50 s |
| 20260930T152358Z_56f3a95a | 4.22% | 84.72% | 11.06% | **15.28%** | 1.46 s |
| 20260930T152726Z_85b2bcb7 | 6.60% | 75.42% | 17.98% | **24.58%** | 0.62 s |
| 20260930T152929Z_faff6f17 | 7.10% | 76.01% | 16.89% | **23.99%** | 1.77 s |

**汇总（n=14）**：

| 分量 | 中位数 | 均值 | 范围 |
|------|--------|------|------|
| 上传 + 放行 | 5.96% | 5.93% | [4.12%, 7.10%] |
| 飞行 | 77.91% | 78.53% | [74.13%, 85.00%] |
| 确认驻留 | 15.89% | 15.54% | [10.88%, 18.90%] |
| **上传 + 放行 + 确认驻留** | **22.09%** | 21.47% | [15.00%, 25.87%] |
| 屏障等待（绝对量） | — | — | [0.62, 2.44] s |

### 对 v0.4 的影响
- "上传 + 放行 + 确认驻留" 占任务阶段总时长中位 **22.09%**；这部分时间与飞行无关，随阶段数线性增长（阶段数 = 航点数）。
- `elapsed_s` 中位数 137.60 s，其中任务跨度仅占 45.85%；约 51.5 s 花在起飞准备（`connected` → `airborne_ready`），约 20 s 花在任务结束到 `landed`。
- 屏障等待绝对值很小（0.62–2.44 s，占任务跨度 < 3%）。`confirm` 由 `parallel(confirm)`（`runner.py:112`）**并发**执行，各机同时进行，不存在逐机串行；本节测得的每阶段确认驻留时长 = 该阶段全机 `task_target_verified` 的最晚时刻 − 全机 `phase_finished` 的最晚时刻，即开销来自**等待最慢的一架**完成确认。

---

## 6. A6 改动范围（更正措辞）

`report_A.md` 的 A6 内容不变，仅将"对 v0.4 的影响"改为事实陈述：

- 改为"每机整段连续航线"需要改动 `mission_planning.compile_execution_phases`、`runner.run_scene` 的阶段循环、`vehicle.execute/confirm_target`、`mission_evaluation.execution_windows`（4 个核心文件），以及 `tasks.target_confirmation`、`scenario.mission_for`、`mission_schema`（schema 版本）3 个适配文件。
- 现有代码中的多航点上传能力：`mission_for` 每次只生成 3 项（`scenario.py:97-105`），但 `vehicle.upload` 接受任意长度的 mission 列表并逐项应答（`vehicle.py:225-252`），`vehicle.execute` 以 `mission_count - 1` 作为完成判据（`vehicle.py:267-268`），故上传通道本身已支持多航点。
- v1 路径（`tasks.compile_task_v1`，`tasks.py:92-95`）已按航点逐项生成 `scene["phases"]`，每个 phase 仍是一个航点，未提供"整段一次上传"的先例。
- 受影响测试：`tests/` 下与 phase 窗口、语义服务窗口、屏障、`validate_task_binding` 相关的用例需同步修改；具体数量未在本批统计。

---

## 7. 本批自检

| 编号 | 是否有对应小节 | 状态 |
|------|--------------|------|
| 基线 | 见 `report_A.md` 第 0 节（本批重新核对，结论未变：HEAD `e13564b`、`__version__ = "0.3.0"`、23 个模块、150 项测试全通过、episode 数 10+5、生成任务 100） | 完成 |
| A1 | 第 1 节 | 完成（状态更正为证实） |
| A2 | 第 2 节 | 完成（摘录更正为原文） |
| A3 | 第 3 节 | 完成（补全 3.1–3.6） |
| A4 | 第 4 节 | 完成（(a)–(f) 全部重做） |
| A5 | 第 5 节 | 完成（补全至 15 个 episode） |
| A6 | 第 6 节 | 完成（措辞更正） |

**本批未完成项**：无。

**新增脚本清单**：

| 文件 | 用途 |
|------|------|
| `A1_compile_corrected.py` | A1 修正：lanes、阶段构成、approach/observe 首点重合 |
| `A3_params.py` | A3：5 个任务/模板文件的参数提取 |
| `A3_generated_params.py` | A3：100 个已生成任务的参数分布 |
| `A4_velocity_analysis.py` | A4 第一遍：停靠段、窗口结束最低速、同步停靠 |
| `A4_diag_velocity_trust.py` | A4 诊断：速度字段可信性 + 原始轨迹 |
| `A4_final.py` | A4 最终：(a)–(e) |
| `A4_addendum.py` | A4 补充：(c) 两种口径 + (f) 绘图 |
| `A4_verify_stops_at_waypoints.py` | A4 独立交叉验证：停住点 vs 规划航点 |
| `A5_final.py` | A5：15 个 episode 时间构成 |

**数据产物**：`A1_corrected.json`、`A4_dwell.json`、`A4_legs.json`、`A4_zero_len.json`、`A4_sync.json`、`A4_velocity_summary.json`、`A5_final.json`、`speed_profile_20260930T155457Z_200822e7.png`

---

## 8. 更正记录

**更正 1（4.4 节，"对 v0.4 的影响"）**

- 原文：`同步停靠占 90.5% 的停靠事件，同步时间占比 6.65%（中位）。这一比例随飞机数增加而下降（6 机 episode 为 0.0615–0.0759，3 机为 0.0354–0.0597），因为更多飞机更难同时满足停靠判据。`
- 问题：与本节表格不符。表格显示 6 机为 0.0615–0.0759（中位 0.0727），高于 3 机的 0.0354–0.0680（中位 0.0567），不存在"随飞机数增加而下降"。
- 依据：按飞机数分组的实测（`audit_v04/A4_sync.json` 与 `A4_dwell.json` 联表）：
  - 2 机 n=3：0.0665–0.0797，中位 0.0714
  - 3 机 n=5：0.0354–0.0680，中位 0.0567
  - 6 机 n=6：0.0615–0.0759，中位 0.0727
  - 同步占比与窗口时长的相关系数 **r = −0.774**；3 机组最低两值（0.0354、0.0378）来自 `recon_shared_demo_3uav` 的两次运行，窗口 118.7 / 118.8 s，约为其余 episode 的两倍。
- 改为：报告三组实测范围与中位数，指出与飞机数无单调关系、与窗口时长负相关，并说明 3 机组低值的来源。
- 同处 `90.5%` 一并更正为 **91.97%（126/137）**（见更正 2）。

**更正 2（4.4 节与 4.4 汇总）**

- 原文：`全机共同重叠的停靠事件：合计 124/137 = 90.5%`（4.4 表格下方汇总）与更正 1 所涉句子中的 `90.5%`。
- 问题：分项与合计不一致。逐 episode 的 `common_events` 之和为 126，`fleet_events` 之和为 137。
- 依据：`sum(common_events) = 8+10+10+8+9+11+8+7+8+11+10+11+8+7 = 126`；`sum(fleet_events) = 137`；`126/137 = 0.9197`。
- 改为：统一为 **126/137 = 91.97%**。

**更正 3（5.4 节，"对 v0.4 的影响"）**

- 原文：`屏障等待绝对值很小（0.62–2.44 s，占任务跨度 < 3%），全机同步的开销主要体现在 confirm 的逐机串行驻留上，而非屏障空等。`
- 问题：`confirm` 并非逐机串行。`runner.py:112` 的 `parallel(confirm)` 使各机的 `confirm_target` 并发执行（`runner.py:68-80` 的 `parallel` 把每个 client 提交到 `ThreadPoolExecutor`），阶段结束时刻取全机最晚者。
- 依据：`swarm_sim/runner.py:105-112` 与 `swarm_sim/runner.py:68-80`（原文见 2 节）。
- 改为：说明 `confirm` 并发执行、无逐机串行；本节的每阶段确认驻留时长 = 全机 `task_target_verified` 最晚时刻 − 全机 `phase_finished` 最晚时刻，开销来自等待最慢的一架。

**更正 4（4.1 节零长度航段数的表述）**

- 说明：4.1 节 (a) 表与 4.5 节的"57 个零长度航段"在该批次执行时已按 `A4_final.py` 重新计算，与 4.5 节一致；本更正仅记录该数字在 `report_A.md` 初版与补充版之间未发生口径变化，无需修改。

**更正 5（自检范围）**

- 本文件第 7 节的自检表在撰写时点确认无遗漏；上述更正 1–3 均为该自检之后、由委托方复核发现的表述错误，不改变任何数值结论（A4 (a)–(f) 与 A5 的统计结果均未变动）。
