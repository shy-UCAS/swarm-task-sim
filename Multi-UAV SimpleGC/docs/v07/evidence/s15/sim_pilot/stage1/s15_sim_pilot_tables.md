# S1.5 仿真试点统计表（下游链路：规划 → M2 预演/时刻 → 联合 fastsim → M1 → 审计）

- 试点 attempt（1 个，每个 skeleton_id 只来自其中一个）：
  - `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261016T184726Z`：状态 `TIME_LIMIT_STOP`，声明 5，有 episode 行 4，墙钟 1500.1 s（上限 1500 s）
- 入口提交：`b9950d2a71fb443a56b1fa8656bfa8edf6222807`；合计墙钟 1500.1 s；运行前后指纹一致 True
- 声明骨架 5 个；有 episode 行的 4 个；未完成 1 个
- 严格配对（同步与递次两版都成功）：4/5 个骨架；六次抽签中五意图全部配对的 0/6 次
- 失败环节计数（按链路顺序取第一个失败环节）：{"规划": 0, "单机预演": 0, "时刻叠加间距": 0, "联合执行（超时）": 0, "联合执行（质量）": 0, "M1 角色判据": 0, "审计": 0}
- 实测逼近方式与抽签指定一致：8/8 次比较

## P1 逐骨架：严格配对、轮数、失败环节与墙钟

| skeleton_id | attempt | draw | intent | 指定方式 | 严格配对 | 轮数 | 状态 | 失败环节 | 墙钟s |
|---|---|---|---|---|---|---|---|---|---|
| family_s15_1b876e6b8b6f70c6_ext_005_regular | attempt_s15sim_20261016T184726Z | 6e6b8b6f70c6#slot1 | transit | multi_direction | True | 2 | synchronous=generated/sequential=generated |  | 611.238 |
| family_s15_1b876e6b8b6f70c6_ext_006_regular | attempt_s15sim_20261016T184726Z | 6e6b8b6f70c6#slot1 | reconnaissance | multi_direction | True | 4 | synchronous=generated/sequential=generated |  | 1120.167 |
| family_s15_1b876e6b8b6f70c6_ext_007_regular | - | 6e6b8b6f70c6#slot1 | - | multi_direction | False | - |  |  | None |
| family_s15_1b876e6b8b6f70c6_ext_008_regular | attempt_s15sim_20261016T184726Z | 6e6b8b6f70c6#slot1 | feint | multi_direction | True | 2 | synchronous=generated/sequential=generated |  | 685.472 |
| family_s15_1b876e6b8b6f70c6_ext_009_regular | attempt_s15sim_20261016T184726Z | 6e6b8b6f70c6#slot1 | penetration | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 387.775 |

## P2 原始 reason 计数（未归类前的字面值）

| mode:stage:reason | count |
|---|---|

## P3 按抽签：五个意图是否全部得到严格配对

| family#slot | approach_mode | layout | facility_count | group_count | member_counts | 本次运行 | 严格配对 | 五意图全配对 | 未配对意图 | 失败环节 |
|---|---|---|---|---|---|---|---|---|---|---|
| family_s15_1b876e6b8b6f70c6#slot1 | multi_direction | single | 1 | 1 | 10 | 5/5 | 4/5 | False | - | - |
| family_s15_1c267d4d7000043d#slot1 | same_direction | clustered | 2 | 1 | 6 | 0/5 | 未运行 | n/a | - | - |
| family_s15_38bedc9d791d547b#slot1 | same_direction | clustered | 2 | 1 | 7 | 0/5 | 未运行 | n/a | - | - |
| family_s15_79c93b22d09e8a7a#slot0 | same_direction | clustered | 3 | 2 | 4/2 | 0/5 | 未运行 | n/a | - | - |
| family_s15_aa4c66be8e85d64d#slot0 | multi_direction | single | 1 | 1 | 9 | 0/5 | 未运行 | n/a | - | - |
| family_s15_c713f51898e81011#slot0 | multi_direction | clustered | 3 | 1 | 10 | 0/5 | 未运行 | n/a | - | - |

## P4 M1 实测事实：逼近方式一致性与驻留/重访检出

| intent | 骨架 | 严格配对 | 参与成员 | 驻留检出 | 重访检出 | 观察驻留检出 | 轮数分布 |
|---|---|---|---|---|---|---|---|
| transit | 1 | 1 | 20 | 0 | 0 | 0 | {"2": 1} |
| reconnaissance | 1 | 1 | 20 | 16 | 0 | 0 | {"4": 1} |
| monitoring | 0 | 0 | 0 | 0 | 0 | 0 | {} |
| feint | 1 | 1 | 20 | 20 | 0 | 0 | {"2": 1} |
| penetration | 1 | 1 | 20 | 9 | 0 | 0 | {"1": 1} |

- 实测逼近方式与指定一致：8/8 次（逐骨架见 P1 与 summary JSON 的 measured_approach_matches_spec）。

## P5 实测最小机间距（m，取全部 episode 行）

| 范围 | count | min | p50 | p90 | max |
|---|---|---|---|---|---|
| all | 8 | 2.195949 | 13.296085 | 15.743702 | 15.754017 |

## P6 每骨架分阶段墙钟（s）

| skeleton_id | 规划 | 单机预演+时刻安排 | 联合仿真 | M1判定+审计+测量+写盘 | skeleton_total |
|---|---|---|---|---|---|
| family_s15_1b876e6b8b6f70c6_ext_005_regular | 73.918 | 335.822 | 187.919 | 13.579 | 611.238 |
| family_s15_1b876e6b8b6f70c6_ext_006_regular | 83.149 | 738.486 | 261.52 | 37.012 | 1120.167 |
| family_s15_1b876e6b8b6f70c6_ext_007_regular | None | None | None | None | None |
| family_s15_1b876e6b8b6f70c6_ext_008_regular | 90.284 | 369.854 | 210.611 | 14.724 | 685.472 |
| family_s15_1b876e6b8b6f70c6_ext_009_regular | 56.804 | 160.333 | 158.052 | 12.587 | 387.775 |

口径：记录未分阶段计时。规划取自 `candidate_pool.json` 的 `group_search_metrics[*].wall_s` 与 `combination_search.wall_s`；单机预演与时刻安排在记录中不分开，合并为 setup 残差（各 mode 的 `amortized_skeleton_setup_s` 之和减去规划）；联合仿真取 `simulation_wall_s`；M1 判定、审计、测量与写盘在记录中不分开，合并取 `episode_postprocess_wall_s`。未为取得更细的分段而修改被测代码。

## P7 分阶段分布汇总（s）

| 阶段 | count | min | p50 | p90 | max |
|---|---|---|---|---|---|
| 规划 | 4 | 56.803508 | 78.533257 | 88.143177 | 90.283618 |
| 单机预演+时刻安排 | 4 | 160.333138 | 352.838241 | 627.896695 | 738.48628 |
| 联合仿真 | 4 | 158.051672 | 199.264907 | 246.247551 | 261.520455 |
| M1判定+审计+测量+写盘 | 4 | 12.586961 | 14.151206 | 30.325381 | 37.011793 |
| skeleton_total | 4 | 387.775279 | 648.355014 | 989.758881 | 1120.167342 |
