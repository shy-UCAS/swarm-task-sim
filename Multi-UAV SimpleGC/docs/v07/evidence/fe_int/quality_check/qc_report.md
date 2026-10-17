# FE-INT 冻结前数据质量快检（只读统计）

- 数据根：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261017T071447Z`
- 骨架：30；episode：60（synchronous 30，sequential 30）
- 脚本：`scripts/qc_v07_fe_pre_freeze.py`
- 脚本 SHA256：`d37ebdb4be3effe4fb66a74a4b844ec077cfa0634bfe4e7752f7fb91a00bce9d`
- 范围：只读 `truth_10hz.npz`、`metrics.json`、`labels.json`、`task.json`；未运行规划或仿真，未修改任何既有源码、配置或测试。

## Q1 停顿事件（按 role/execution_method × mode）

状态：**BLOCKED**。Q1 表未计算。

口径：按要求读取 `task_v07.criteria.load_criteria()["detectors"]["dwell"]`，键值原样如下。

```json
{
  "window_s": 20.0,
  "radius_m": 30.0,
  "max_start_end_m": 30.0
}
```

- 配置键：`window_s`, `radius_m`, `max_start_end_m`。
- 速度阈值字段：未找到。
- 最短持续时间字段：未找到。
- 字段语义：`window_s` 为窗口长度，`radius_m` / `max_start_end_m` 为距离；三者均不是速度阈值，也不是最短持续时间阈值。
- 原因：detectors.dwell 中无明确的速度阈值字段，也无最短持续时间字段；未选取任何数值。
- 未采用的同名字段（不在指定配置源中）：`stop_speed_m_s` = [1.5]；`stop_hold_s` = [1.0]。

- 目标几何：在 `task.json` 中检查 74 个 episode-group 记录的 `center_m` / `vertices_m`，找到 0 个（状态 `not_found_in_task_json`）。
- 按“找不到明确的速度或时长字段，停下报告字段清单，不要自选数值”执行；未选取任何阈值，未从其他文件替代取值。

Q1 表：BLOCKED（无阈值字段，无目标几何）。

### M1 驻留检出（部分）

口径：字段路径 `labels.json -> agents[agent_id] -> observed -> contribution -> dwell -> detected`，与 `scripts/summarize_v07_s15_sim_pilot.py` 的 `label_facts()` 一致；单位为 agent-episode。

| role / execution_method | 成员数 | M1 驻留检出=是 | M1 驻留检出=否 |
|---|---|---|---|
| feint / feint | 104 | 104 | 0 |
| intrusion / intrusion | 84 | 42 | 42 |
| monitoring / monitoring | 100 | 96 | 4 |
| reconnaissance / area_search | 28 | 14 | 14 |
| reconnaissance / close_observation | 68 | 68 | 0 |
| transit / transit | 96 | 0 | 96 |

缺失 `dwell.detected` 字段的 agent-episode：0。
Q1 列为 BLOCKED，故请求的 2×2 交叉计数未产出；上表仅为 M1 边际计数。

## Q2 航线转角（按 role/execution_method）

口径：取 `task.json` 的 `references[agent_id].points_enu_m` 前两维；每个内部顶点的航向转角 θ = arccos(clip(u·w, −1, 1))，单位度，u、w 为相邻两段单位方向向量；长度 < 1e-6 m 的段跳过；每成员取最大转角。去重口径：30/30 骨架的 task.json 在 synchronous 与 sequential 间逐字节一致；按骨架去重，每个骨架成员计一次；比例分母为有 ≥1 个有效内部顶点的成员数；分位数采用线性插值分位（0 基索引）。

| role / execution_method | 成员数 | 有效成员数 | 最大转角 min (°) | p50 (°) | max (°) | ≥90° | ≥150° |
|---|---|---|---|---|---|---|---|
| feint / feint | 52 | 52 | 45.000000 | 46.560190 | 123.893131 | 11/52 (21.15%) | 0/52 (0.00%) |
| intrusion / intrusion | 42 | 42 | 7.001891 | 66.072418 | 118.289149 | 11/42 (26.19%) | 0/42 (0.00%) |
| monitoring / monitoring | 50 | 50 | 34.473936 | 180.000000 | 180.000000 | 48/50 (96.00%) | 48/50 (96.00%) |
| reconnaissance / area_search | 14 | 14 | 54.019242 | 91.005856 | 179.580398 | 7/14 (50.00%) | 3/14 (21.43%) |
| reconnaissance / close_observation | 34 | 34 | 150.000000 | 180.000000 | 180.000000 | 34/34 (100.00%) | 28/34 (82.35%) |
| transit / transit | 48 | 48 | 20.373154 | 58.378195 | 176.027145 | 10/48 (20.83%) | 1/48 (2.08%) |

无有效内部顶点的成员：0/240。
若按 60 个 episode 逐个成员计，成员数为 480；因 task.json 逐字节一致，转角分布与上表相同。

## Q3 最小机间距（按 intent × mode）

口径：`metrics.json` 的 `minimum_separation_m`（episode 级）；分位数采用线性插值分位（0 基索引）；`< 3 m` 为严格小于；每个 intent × mode 行为 6 条 episode。

| intent | mode | episode 数 | min (m) | p10 (m) | p50 (m) | max (m) | < 3 m |
|---|---|---|---|---|---|---|---|
| transit | synchronous | 6 | 2.069796 | 2.818821 | 16.429016 | 17.996908 | 1 |
| transit | sequential | 6 | 5.180400 | 10.459841 | 17.257822 | 21.949913 | 0 |
| reconnaissance | synchronous | 6 | 2.250106 | 2.412235 | 14.198517 | 22.059206 | 2 |
| reconnaissance | sequential | 6 | 9.360561 | 12.755234 | 16.709867 | 22.069216 | 0 |
| monitoring | synchronous | 6 | 3.358913 | 3.924385 | 12.647987 | 18.636075 | 0 |
| monitoring | sequential | 6 | 7.100964 | 11.625435 | 18.165119 | 19.373715 | 0 |
| feint | synchronous | 6 | 9.067555 | 9.960222 | 12.245910 | 16.296328 | 0 |
| feint | sequential | 6 | 2.195949 | 2.748084 | 5.112785 | 15.046106 | 1 |
| penetration | synchronous | 6 | 5.277347 | 5.637657 | 13.665016 | 17.113453 | 0 |
| penetration | sequential | 6 | 11.786460 | 13.762871 | 17.891168 | 19.373715 | 0 |

### 全部 episode 中最小机间距最小的 3 条

口径：`metrics.json` 数值排序；重算用 `truth_10hz.npz` 的全部帧与全部机对，取 3D 欧氏距离全局最小值；差值 > 1e-6 m 标注。

| skeleton_id | mode | metrics (m) | 重算 (m) | 机对 | 时刻 (s) | 差值 (m) | 标注 |
|---|---|---|---|---|---|---|---|
| family_s15_c713f51898e81011_ext_000_regular | synchronous | 2.069796 | 2.069796 | uav_06 / uav_05 | 1613.700000 | 0.000e+00 | 一致 |
| family_s15_1b876e6b8b6f70c6_ext_008_regular | sequential | 2.195949 | 2.195949 | uav_10 / uav_03 | 1465.100000 | 0.000e+00 | 一致 |
| family_s15_79c93b22d09e8a7a_ext_001_regular | synchronous | 2.250106 | 2.250106 | uav_03 / uav_05 | 350.400000 | 0.000e+00 | 一致 |

## 数据完整性检查

口径：逐 episode 核对文件存在、成员覆盖、`truth_10hz.npz` 的 agent 顺序与数量、`labels.json` 的 agent 集合、`metrics.json` 的 skeleton/mode 标识；只读。

| 检查项 | 结果 |
|---|---|
| 骨架数 | 30 |
| episode 数 | 60 |
| 同时具备两 mode 的骨架数 | 30 |
| agent 数量不一致 | 0 |
| npz agent 顺序不一致 | 0 |
| labels agent 集合不一致 | 0 |
| metrics skeleton/mode 标识不一致 | 0 |

## 来源与键名

- 配置键：`task_v07.criteria.load_criteria()["detectors"]["dwell"]` → `window_s`、`radius_m`、`max_start_end_m`（原样读取；未用于选值）。
- 数据路径：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261017T071447Z`，每骨架下 `synchronous/`、`sequential/` 的 `truth_10hz.npz`、`metrics.json`、`labels.json`、`task.json`。
- 脚本 SHA256：`d37ebdb4be3effe4fb66a74a4b844ec077cfa0634bfe4e7752f7fb91a00bce9d`。
