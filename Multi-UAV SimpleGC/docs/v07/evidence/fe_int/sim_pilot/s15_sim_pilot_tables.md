# S1.5 仿真试点统计表（下游链路：规划 → M2 预演/时刻 → 联合 fastsim → M1 → 审计）

- 试点 attempt（1 个，每个 skeleton_id 只来自其中一个）：
  - `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261017T071447Z`：状态 `completed`，声明 30，有 episode 行 30，墙钟 4035.1 s（上限 4500 s）
- 入口提交：`f176dc997dd063ce1330913dbd07e10aa43f673e`；合计墙钟 4035.1 s；运行前后指纹一致 True
- 声明骨架 30 个；有 episode 行的 30 个；未完成 0 个
- 严格配对（同步与递次两版都成功）：30/30 个骨架；六次抽签中五意图全部配对的 6/6 次
- 失败环节计数（按链路顺序取第一个失败环节）：{"规划": 0, "单机预演": 0, "时刻叠加间距": 0, "联合执行（超时）": 0, "联合执行（质量）": 0, "M1 角色判据": 0, "审计": 0}
- 实测逼近方式与抽签指定一致：74/74 次比较

## P1 逐骨架：严格配对、轮数、失败环节与墙钟

| skeleton_id | attempt | draw | intent | 指定方式 | 严格配对 | 轮数 | 状态 | 失败环节 | 墙钟s |
|---|---|---|---|---|---|---|---|---|---|
| family_s15_1b876e6b8b6f70c6_ext_005_regular | attempt_s15sim_20261017T071447Z | 6e6b8b6f70c6#slot1 | transit | multi_direction | True | 2 | synchronous=generated/sequential=generated |  | 601.873 |
| family_s15_1b876e6b8b6f70c6_ext_006_regular | attempt_s15sim_20261017T071447Z | 6e6b8b6f70c6#slot1 | reconnaissance | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 492.307 |
| family_s15_1b876e6b8b6f70c6_ext_007_regular | attempt_s15sim_20261017T071447Z | 6e6b8b6f70c6#slot1 | monitoring | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 1661.596 |
| family_s15_1b876e6b8b6f70c6_ext_008_regular | attempt_s15sim_20261017T071447Z | 6e6b8b6f70c6#slot1 | feint | multi_direction | True | 2 | synchronous=generated/sequential=generated |  | 637.025 |
| family_s15_1b876e6b8b6f70c6_ext_009_regular | attempt_s15sim_20261017T071447Z | 6e6b8b6f70c6#slot1 | penetration | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 394.022 |
| family_s15_1c267d4d7000043d_ext_005_regular | attempt_s15sim_20261017T071447Z | 7d4d7000043d#slot1 | transit | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 241.46 |
| family_s15_1c267d4d7000043d_ext_006_regular | attempt_s15sim_20261017T071447Z | 7d4d7000043d#slot1 | reconnaissance | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 205.224 |
| family_s15_1c267d4d7000043d_ext_007_regular | attempt_s15sim_20261017T071447Z | 7d4d7000043d#slot1 | monitoring | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 796.011 |
| family_s15_1c267d4d7000043d_ext_008_regular | attempt_s15sim_20261017T071447Z | 7d4d7000043d#slot1 | feint | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 226.268 |
| family_s15_1c267d4d7000043d_ext_009_regular | attempt_s15sim_20261017T071447Z | 7d4d7000043d#slot1 | penetration | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 154.413 |
| family_s15_38bedc9d791d547b_ext_005_regular | attempt_s15sim_20261017T071447Z | dc9d791d547b#slot1 | transit | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 215.818 |
| family_s15_38bedc9d791d547b_ext_006_regular | attempt_s15sim_20261017T071447Z | dc9d791d547b#slot1 | reconnaissance | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 221.485 |
| family_s15_38bedc9d791d547b_ext_007_regular | attempt_s15sim_20261017T071447Z | dc9d791d547b#slot1 | monitoring | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 1198.309 |
| family_s15_38bedc9d791d547b_ext_008_regular | attempt_s15sim_20261017T071447Z | dc9d791d547b#slot1 | feint | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 311.844 |
| family_s15_38bedc9d791d547b_ext_009_regular | attempt_s15sim_20261017T071447Z | dc9d791d547b#slot1 | penetration | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 305.164 |
| family_s15_79c93b22d09e8a7a_ext_000_regular | attempt_s15sim_20261017T071447Z | 3b22d09e8a7a#slot0 | transit | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 188.724 |
| family_s15_79c93b22d09e8a7a_ext_001_regular | attempt_s15sim_20261017T071447Z | 3b22d09e8a7a#slot0 | reconnaissance | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 611.188 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | attempt_s15sim_20261017T071447Z | 3b22d09e8a7a#slot0 | monitoring | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 686.227 |
| family_s15_79c93b22d09e8a7a_ext_003_regular | attempt_s15sim_20261017T071447Z | 3b22d09e8a7a#slot0 | feint | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 250.602 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | attempt_s15sim_20261017T071447Z | 3b22d09e8a7a#slot0 | penetration | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 509.318 |
| family_s15_aa4c66be8e85d64d_ext_000_regular | attempt_s15sim_20261017T071447Z | 66be8e85d64d#slot0 | transit | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 214.859 |
| family_s15_aa4c66be8e85d64d_ext_001_regular | attempt_s15sim_20261017T071447Z | 66be8e85d64d#slot0 | reconnaissance | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 215.857 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | attempt_s15sim_20261017T071447Z | 66be8e85d64d#slot0 | monitoring | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 663.76 |
| family_s15_aa4c66be8e85d64d_ext_003_regular | attempt_s15sim_20261017T071447Z | 66be8e85d64d#slot0 | feint | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 212.478 |
| family_s15_aa4c66be8e85d64d_ext_004_regular | attempt_s15sim_20261017T071447Z | 66be8e85d64d#slot0 | penetration | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 153.866 |
| family_s15_c713f51898e81011_ext_000_regular | attempt_s15sim_20261017T071447Z | f51898e81011#slot0 | transit | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 700.814 |
| family_s15_c713f51898e81011_ext_001_regular | attempt_s15sim_20261017T071447Z | f51898e81011#slot0 | reconnaissance | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 590.299 |
| family_s15_c713f51898e81011_ext_002_regular | attempt_s15sim_20261017T071447Z | f51898e81011#slot0 | monitoring | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 2744.702 |
| family_s15_c713f51898e81011_ext_003_regular | attempt_s15sim_20261017T071447Z | f51898e81011#slot0 | feint | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 722.265 |
| family_s15_c713f51898e81011_ext_004_regular | attempt_s15sim_20261017T071447Z | f51898e81011#slot0 | penetration | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 602.632 |

## P2 原始 reason 计数（未归类前的字面值）

| mode:stage:reason | count |
|---|---|

## P3 按抽签：五个意图是否全部得到严格配对

| family#slot | approach_mode | layout | facility_count | group_count | member_counts | 本次运行 | 严格配对 | 五意图全配对 | 未配对意图 | 失败环节 |
|---|---|---|---|---|---|---|---|---|---|---|
| family_s15_1b876e6b8b6f70c6#slot1 | multi_direction | single | 1 | 1 | 10 | 5/5 | 5/5 | True | - | - |
| family_s15_1c267d4d7000043d#slot1 | same_direction | clustered | 2 | 1 | 6 | 5/5 | 5/5 | True | - | - |
| family_s15_38bedc9d791d547b#slot1 | same_direction | clustered | 2 | 1 | 7 | 5/5 | 5/5 | True | - | - |
| family_s15_79c93b22d09e8a7a#slot0 | same_direction | clustered | 3 | 2 | 4/2 | 5/5 | 5/5 | True | - | - |
| family_s15_aa4c66be8e85d64d#slot0 | multi_direction | single | 1 | 1 | 9 | 5/5 | 5/5 | True | - | - |
| family_s15_c713f51898e81011#slot0 | multi_direction | clustered | 3 | 1 | 10 | 5/5 | 5/5 | True | - | - |

## P4 M1 实测事实：逼近方式一致性与驻留/重访检出

| intent | 骨架 | 严格配对 | 参与成员 | 驻留检出 | 重访检出 | 观察驻留检出 | 轮数分布 |
|---|---|---|---|---|---|---|---|
| transit | 6 | 6 | 96 | 0 | 0 | 0 | {"2": 1, "1": 5} |
| reconnaissance | 6 | 6 | 96 | 82 | 0 | 68 | {"1": 6} |
| monitoring | 6 | 6 | 96 | 92 | 96 | 0 | {"1": 6} |
| feint | 6 | 6 | 96 | 96 | 0 | 0 | {"2": 1, "1": 5} |
| penetration | 6 | 6 | 96 | 54 | 4 | 0 | {"1": 6} |

- 实测逼近方式与指定一致：74/74 次（逐骨架见 P1 与 summary JSON 的 measured_approach_matches_spec）。

## P5 实测最小机间距（m，取全部 episode 行）

| 范围 | count | min | p50 | p90 | max |
|---|---|---|---|---|---|
| all | 60 | 2.069796 | 15.739282 | 19.167268 | 22.069216 |

## P6 每骨架分阶段墙钟（s）

| skeleton_id | 规划 | 单机预演+时刻安排 | 联合仿真 | M1判定+审计+测量+写盘 | skeleton_total |
|---|---|---|---|---|---|
| family_s15_1b876e6b8b6f70c6_ext_005_regular | 48.518 | 382.248 | 145.679 | 25.428 | 601.873 |
| family_s15_1b876e6b8b6f70c6_ext_006_regular | 55.627 | 181.376 | 220.938 | 34.365 | 492.307 |
| family_s15_1b876e6b8b6f70c6_ext_007_regular | 264.081 | 422.167 | 535.199 | 440.15 | 1661.596 |
| family_s15_1b876e6b8b6f70c6_ext_008_regular | 63.91 | 395.745 | 162.378 | 14.992 | 637.025 |
| family_s15_1b876e6b8b6f70c6_ext_009_regular | 39.053 | 148.348 | 188.398 | 18.224 | 394.022 |
| family_s15_1c267d4d7000043d_ext_005_regular | 22.047 | 84.493 | 113.632 | 21.288 | 241.46 |
| family_s15_1c267d4d7000043d_ext_006_regular | 26.753 | 70.548 | 97.0 | 10.922 | 205.224 |
| family_s15_1c267d4d7000043d_ext_007_regular | 185.39 | 250.224 | 242.275 | 118.122 | 796.011 |
| family_s15_1c267d4d7000043d_ext_008_regular | 45.023 | 72.459 | 100.309 | 8.477 | 226.268 |
| family_s15_1c267d4d7000043d_ext_009_regular | 21.325 | 54.212 | 72.438 | 6.437 | 154.413 |
| family_s15_38bedc9d791d547b_ext_005_regular | 31.074 | 79.266 | 98.075 | 7.403 | 215.818 |
| family_s15_38bedc9d791d547b_ext_006_regular | 38.659 | 77.695 | 96.608 | 8.524 | 221.485 |
| family_s15_38bedc9d791d547b_ext_007_regular | 119.802 | 373.684 | 391.786 | 313.037 | 1198.309 |
| family_s15_38bedc9d791d547b_ext_008_regular | 29.627 | 93.126 | 174.521 | 14.57 | 311.844 |
| family_s15_38bedc9d791d547b_ext_009_regular | 28.362 | 114.532 | 150.41 | 11.861 | 305.164 |
| family_s15_79c93b22d09e8a7a_ext_000_regular | 72.148 | 46.546 | 63.851 | 6.179 | 188.724 |
| family_s15_79c93b22d09e8a7a_ext_001_regular | 511.995 | 38.842 | 52.329 | 8.022 | 611.188 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | 342.899 | 131.337 | 154.179 | 57.813 | 686.227 |
| family_s15_79c93b22d09e8a7a_ext_003_regular | 121.302 | 51.662 | 70.809 | 6.829 | 250.602 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | 211.086 | 105.623 | 161.316 | 31.293 | 509.318 |
| family_s15_aa4c66be8e85d64d_ext_000_regular | 38.169 | 72.886 | 93.577 | 10.227 | 214.859 |
| family_s15_aa4c66be8e85d64d_ext_001_regular | 51.505 | 81.877 | 72.449 | 10.026 | 215.857 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | 189.282 | 126.266 | 212.288 | 135.923 | 663.76 |
| family_s15_aa4c66be8e85d64d_ext_003_regular | 48.79 | 66.038 | 88.193 | 9.457 | 212.478 |
| family_s15_aa4c66be8e85d64d_ext_004_regular | 27.448 | 52.633 | 67.185 | 6.599 | 153.866 |
| family_s15_c713f51898e81011_ext_000_regular | 89.999 | 233.425 | 343.592 | 33.798 | 700.814 |
| family_s15_c713f51898e81011_ext_001_regular | 84.921 | 195.574 | 279.331 | 30.472 | 590.299 |
| family_s15_c713f51898e81011_ext_002_regular | 331.313 | 890.861 | 1033.796 | 488.731 | 2744.702 |
| family_s15_c713f51898e81011_ext_003_regular | 124.953 | 254.747 | 311.304 | 31.26 | 722.265 |
| family_s15_c713f51898e81011_ext_004_regular | 101.826 | 217.884 | 260.338 | 22.584 | 602.632 |

口径：记录未分阶段计时。规划取自 `candidate_pool.json` 的 `group_search_metrics[*].wall_s` 与 `combination_search.wall_s`；单机预演与时刻安排在记录中不分开，合并为 setup 残差（各 mode 的 `amortized_skeleton_setup_s` 之和减去规划）；联合仿真取 `simulation_wall_s`；M1 判定、审计、测量与写盘在记录中不分开，合并取 `episode_postprocess_wall_s`。未为取得更细的分段而修改被测代码。

## P7 分阶段分布汇总（s）

| 阶段 | count | min | p50 | p90 | max |
|---|---|---|---|---|---|
| 规划 | 30 | 21.3251 | 59.768883 | 270.80443 | 511.995368 |
| 单机预演+时刻安排 | 30 | 38.841511 | 110.077092 | 383.597522 | 890.861205 |
| 联合仿真 | 30 | 52.32908 | 152.294384 | 348.411401 | 1033.796099 |
| M1判定+审计+测量+写盘 | 30 | 6.178815 | 16.607878 | 153.634643 | 488.730945 |
| skeleton_total | 30 | 153.865681 | 443.164743 | 836.240816 | 2744.701616 |
