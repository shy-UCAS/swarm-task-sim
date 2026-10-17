# FE-INT 冻结前速度剖面快检（只读统计）

- 数据根：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261017T071447Z`
- 骨架：30；episode：60
- 诊断常数：V_LOW = 1.0 m/s；V_MOVE = 1.0 m/s；NEAR_VERTEX = 3.0 m；仅用于本次统计，不是判据。
- 脚本：`scripts/qc_v07_fe_speed_profile.py`
- 脚本 SHA256：`a901b7bc45228b9f53df7a9a39e01071acf39fd7e6e8a9e6a0b8de304c643b43`
- 范围：只读 `truth_10hz.npz`、`metrics.json`、`labels.json`、`task.json`；未运行规划或仿真，未修改任何既有源码、配置或测试。

## S1 低速事件与速度水平（按 role/execution_method × mode）

口径：运动窗为第一个 s > V_MOVE 的帧到最后一个 s > V_MOVE 的帧（含端点）；低速事件为运动窗内连续 s < V_LOW 的帧段，不设最短时长，时长 = 帧数 × 0.1 s；L = 运动窗内 Σ‖Δp_xy‖（km）；s/c 为组内所有成员运动窗内全部 10 Hz 帧合并后的分位（线性插值，0 基索引）；其余列为每成员先算指标再跨成员取 p50/max。逐成员、逐事件的记录（含位置、d_v、最近顶点转角）见 `qc_speed_report.json` 的 `s1.per_member`。

| role / execution_method | mode | 成员数 | 事件数 p50 | 事件数 max | 事件数/L p50 (次/km) | s<V_LOW 时间占比 p50 | s/c p10 | s/c p50 |
|---|---|---|---|---|---|---|---|---|
| feint / feint | synchronous | 52 | 11.000000 | 28 | 2.590387 | 0.014880 | 0.754671 | 1.000000 |
| feint / feint | sequential | 52 | 11.000000 | 28 | 2.590386 | 0.014988 | 0.183909 | 1.000000 |
| intrusion / intrusion | synchronous | 42 | 4.000000 | 23 | 1.388049 | 0.011016 | 0.360011 | 1.000000 |
| intrusion / intrusion | sequential | 42 | 4.000000 | 23 | 1.388052 | 0.011016 | 0.000000 | 1.000000 |
| monitoring / monitoring | synchronous | 50 | 94.500000 | 209 | 8.472515 | 0.037176 | 0.574041 | 1.000000 |
| monitoring / monitoring | sequential | 50 | 94.500000 | 209 | 8.472513 | 0.037337 | 0.484472 | 1.000000 |
| reconnaissance / area_search | synchronous | 14 | 18.500000 | 47 | 5.149990 | 0.031463 | 0.227653 | 1.000000 |
| reconnaissance / area_search | sequential | 14 | 18.500000 | 47 | 5.150024 | 0.031463 | 0.001748 | 1.000000 |
| reconnaissance / close_observation | synchronous | 34 | 7.500000 | 17 | 1.682658 | 0.102308 | 0.000000 | 1.000000 |
| reconnaissance / close_observation | sequential | 34 | 7.500000 | 17 | 1.682658 | 0.102308 | 0.000000 | 1.000000 |
| transit / transit | synchronous | 48 | 6.000000 | 24 | 1.282774 | 0.008363 | 0.998762 | 1.000000 |
| transit / transit | sequential | 48 | 6.000000 | 24 | 1.282774 | 0.008363 | 0.010909 | 1.000000 |

空运动窗：0；L = 0 的成员：0。

## S2 顶点附近低速事件（按 role/execution_method，合并两个 mode）

口径：d_v 为事件内最低速帧位置到最近内部顶点的水平距离；顶点附近事件为 d_v ≤ 3.0 m；比例分母为该角色全部低速事件（两个 mode 合并，每成员计两次）；转角定义与上一轮 Q2 相同（相邻两段单位方向向量的 arccos，度）；分档为 < 10°、10–45°、45–90°、≥ 90°（含下界、不含上界）；内部顶点数/航线长度使用完整航线（非运动窗航程），每成员先算比值再取 p50。

| role / execution_method | 全部低速事件 | 顶点附近事件 | 比例 | <10° | 10–45° | 45–90° | ≥90° | 转角缺失 | 内部顶点数/航线长度 p50 (个/km) |
|---|---|---|---|---|---|---|---|---|---|
| feint / feint | 1324 | 1200 | 1200/1324 (90.63%) | 304 | 664 | 210 | 22 | 0 | 2.769947 |
| intrusion / intrusion | 590 | 542 | 542/590 (91.86%) | 246 | 224 | 50 | 22 | 0 | 1.762338 |
| monitoring / monitoring | 7882 | 7814 | 7814/7882 (99.14%) | 7362 | 256 | 60 | 136 | 0 | 8.702664 |
| reconnaissance / area_search | 578 | 554 | 554/578 (95.85%) | 126 | 334 | 74 | 20 | 0 | 5.978886 |
| reconnaissance / close_observation | 554 | 502 | 502/554 (90.61%) | 202 | 188 | 32 | 80 | 0 | 1.999095 |
| transit / transit | 658 | 568 | 568/658 (86.32%) | 272 | 226 | 50 | 20 | 0 | 1.289920 |

## S3 M1 驻留字段与低速事件的时间对应（按 role/execution_method）

口径：字段路径 `labels.json -> agents[agent_id] -> observed -> contribution -> dwell`，取 `detected`、`t_s`、`total_duration_s`；合并两个 mode，每成员计两次；`detected=True` 的 `total_duration_s` 取 p50/max；`t_s` 按 round(t_s × 10) 对应帧，若该时刻落在任一低速事件的 [start − 20 s, end + 20 s] 内则计为对应；比例分母为 `detected=True` 且 `t_s` 非空的 agent-episode 数。

| role / execution_method | 成员数 | detected=True | detected=False | total_duration_s p50 | max | t_s 有效 | t_s 对应 ±20 s | 比例 |
|---|---|---|---|---|---|---|---|---|
| feint / feint | 104 | 104 | 0 | 22.900000 | 25.600000 | 104 | 104 | 104/104 (100.00%) |
| intrusion / intrusion | 84 | 42 | 42 | 115.300000 | 2579.300000 | 42 | 0 | 0/42 (0.00%) |
| monitoring / monitoring | 100 | 96 | 4 | 42.600000 | 84.700000 | 96 | 96 | 96/96 (100.00%) |
| reconnaissance / area_search | 28 | 14 | 14 | 47.300000 | 50.300000 | 14 | 14 | 14/14 (100.00%) |
| reconnaissance / close_observation | 68 | 68 | 0 | 73.800000 | 99.300000 | 68 | 68 | 68/68 (100.00%) |
| transit / transit | 96 | 0 | 96 | NA | NA | 0 | 0 | 0/0 (NA) |

## 时间序列（JSON）

口径：按 (skeleton_id, agent_id) 排序后，佯动与监视角色各取第一个成员；每 1 s 取一帧速度值；内部顶点到达时刻取整段轨迹中距该顶点最近的一帧；详细序列见 `qc_speed_report.json` 的 `time_series`，不在此表展开。

## 来源与键名

- 巡航速度字段：`task.json -> group_skeletons[group_id] -> cruise_speed_m_s`；顶层 `task.json -> cruise_speed_m_s` 在 60/60 episode 中与 group 值相同。
- 驻留字段：`labels.json -> agents[agent_id] -> observed -> contribution -> dwell` 的 `detected`、`t_s`、`total_duration_s`。
- 数据路径：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261017T071447Z`，每骨架下 `synchronous/`、`sequential/` 的 `truth_10hz.npz`、`labels.json`、`task.json`。
- 脚本 SHA256：`a901b7bc45228b9f53df7a9a39e01071acf39fd7e6e8a9e6a0b8de304c643b43`。
