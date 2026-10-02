# 连续航线编译与名义时序接口（WP-E E1）

状态：`IMPLEMENTED_AND_TESTED`。此处结果来自纯逻辑和合成场景测试，不是 SITL 实测。v1/v2 编译器、旧 `mission_for`、旧逐航点能力检查保持原实现。

## 编译和 schema 2

`tasks.compile_task` → `mission_v3.compile_mission_v3` → 注册规划器 → `route_planning.compile_continuous_mission`。仅 TaskSpec v3 的 `semantic_phase_route_v1` 进入此路径。`waypoint_barrier_v1` 仍输出 schema 1。

每个实际要求的语义阶段生成一个 `pNN_<semantic>` 阶段；不要求返航时不生成 return 阶段。

```python
phase = {
    "name": "p01_observe",
    "semantic_phase": "observe",
    "routes": {"uav_01": [{"east_m": 1.8, "north_m": 30.0, "up_m": 8.0}, ...]},
    "speed_m_s": 3.0,
    "terminal_hold_s": 0.5,
}
```

以阶段起点为第一个参照点，删除距离上一保留点严格小于 0.05 m 的航点，保留第一个点及其规划器索引。恰好 0.05 m 的航段保留。每机每阶段清理后的航线最多 100 点；超出直接拒绝。删除为空时保留该语义阶段，将该机映射为 `hold_no_op`、`service_enabled=false`，不上传/执行航线，但仍在起点确认并参加屏障。

映射位于：

```python
scene["semantic_plan"]["execution_phases"][phase_name]["agents"][agent_id] = {
    "role": "observe",  # 空航线为 hold_no_op
    "service_enabled": True,
    "partition_id": "R1_strip_01",
    "waypoint_planner_indices": [1, 2, 3, ...],
    "start_point": {"east_m": ..., "north_m": ..., "up_m": ...},
    "terminal_point": {"east_m": ..., "north_m": ..., "up_m": ...},
}
```

`planning.per_agent_reference_routes` 保留规划器原始航线；`removed_planner_waypoint_indices` 记录删除项。MAVLink seq 与索引的关系为：route index = seq − 2，再用 `waypoint_planner_indices` 映回原规划器索引。原扫描线长度分组因此不受删除 observe 首点影响。

`scenario.validate` 对 schema 2 新增严格字段、数值、角色、服务开关、索引、阶段起终点与世界边界检查。`validate_task_binding` 仍通过从原 TaskSpec 重新编译逐项比较；航线、索引映射或名义时序元数据被改动都会拒绝。

## 上传任务项

`scenario.route_mission_for(vehicle, route, speed_m_s, terminal_hold_s, origin)` 输出：home 占位 seq 0、速度命令 seq 1、航点 seq 2 起。中间航点 hold = 0，终点 hold 为任务参数；param2/param3 沿用 1/0，yaw 保持 NaN。空航线由运行器处理，此函数拒绝上传空列表。

WP-S 证明的是当前固件的连续过点行为，不能据此认定 param2 或 WPNAV_RADIUS 中哪一个决定接受半径；代码不改变飞控参数。

## 名义时序与间距

每条航线从本阶段起点沿折线匀速行进，按弧长不超过 0.5 m 采样，精确保留各航点。时间均相对于该语义阶段放行时刻。

- `per_agent_arrival_s`：本机运动到终点的时间，不包含 hold 或 confirmation。
- `per_agent_waypoint_arrival_s`：各保留航点到达时间列表，与 route 列表等长。
- `motion_duration_s`：全队最晚运动到终点的时间。
- `per_agent_completion_s`：运动时间加终点 hold、confirmation；no-op 没有后端 hold，但保留 confirmation。
- `duration_s`：全队最晚完成时间，含终点 hold 和 confirmation。
- `tau_s`：\(\max(\text{min\_s},\ \text{fraction\_of\_phase}\times\text{duration\_s})\)。默认 3 s、0.2，未为使测试通过而改变。

这些字段存入 `planning.nominal_phase_timing[phase_name]`，并记录 `tau_basis`、`timing_tolerance`、采样步长、点数和最近配对。检查所有名义时间差不超过 \(\tau\) 的采样点对；终点和 no-op 按静止时间区间参与，不能只把终点放在瞬时到达时刻检查。要求距离为 `min_separation_m + 2 * tracking_margin_m`。该检查是明确版本化的离散名义模型，不能声称已经证明真实连续飞行安全；WP-V 还需实测时间偏差和真值间距。

现有 3 机主示例纯逻辑结果：阶段为 approach/observe/return，每机保留航点数 1/9/1，observe 的规划器索引为 1…9，全部航段至少 0.05 m；名义覆盖 1620/1620，最小名义间距 14.4 m，高于要求的 7 m。observe 运动时长 54.8 s，含 hold/confirmation 的阶段时长 55.8 s，\(\tau=11.16\,\mathrm{s}\)。

## 受控失败与测试

新增可选 v3 字段 `execution.phase_timeout_override_s`，有限正数范围 [0.001, 3600]；省略时不写默认字段。它随 TaskSpec 绑定，供 V05 受控超时实验使用。运行器只能取原始阶段超时与此值的较小者，不能用它放宽超时。

`tests/test_route_planning.py` 的 15 项测试覆盖 E01/E02/E03/E04/E09：首点和内部去重、完整 no-op 编译、关闭返航、任务项参数、同步交叉拒绝、异时交叉接受、终点驻留/no-op 冲突、采样步长、3 机主示例、100 点边界和编译超限、绑定篡改及 schema 严格检查。另已运行 G1 的 18 项与旧规划器的 15 项回归，全部通过。
