# S1.5 仿真试点统计表（下游链路：规划 → M2 预演/时刻 → 联合 fastsim → M1 → 审计）

- 试点 attempt（2 个，每个 skeleton_id 只来自其中一个）：
  - `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261016T184726Z`：状态 `TIME_LIMIT_STOP`，声明 5，有 episode 行 4，墙钟 1500.1 s（上限 1500 s）
  - `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261016T191411Z`：状态 `TIME_LIMIT_STOP`，声明 25，有 episode 行 23，墙钟 4500.1 s（上限 4500 s）
- 入口提交：`b9950d2a71fb443a56b1fa8656bfa8edf6222807`；合计墙钟 6000.1 s；运行前后指纹一致 True
- 声明骨架 30 个；有 episode 行的 27 个；未完成 3 个
- 严格配对（同步与递次两版都成功）：24/30 个骨架；六次抽签中五意图全部配对的 1/6 次
- 失败环节计数（按链路顺序取第一个失败环节）：{"规划": 0, "单机预演": 0, "时刻叠加间距": 6, "联合执行（超时）": 0, "联合执行（质量）": 0, "M1 角色判据": 0, "审计": 0}
- 实测逼近方式与抽签指定一致：56/56 次比较

## P1 逐骨架：严格配对、轮数、失败环节与墙钟

| skeleton_id | attempt | draw | intent | 指定方式 | 严格配对 | 轮数 | 状态 | 失败环节 | 墙钟s |
|---|---|---|---|---|---|---|---|---|---|
| family_s15_1b876e6b8b6f70c6_ext_005_regular | attempt_s15sim_20261016T184726Z | 6e6b8b6f70c6#slot1 | transit | multi_direction | True | 2 | synchronous=generated/sequential=generated |  | 611.238 |
| family_s15_1b876e6b8b6f70c6_ext_006_regular | attempt_s15sim_20261016T184726Z | 6e6b8b6f70c6#slot1 | reconnaissance | multi_direction | True | 4 | synchronous=generated/sequential=generated |  | 1120.167 |
| family_s15_1b876e6b8b6f70c6_ext_007_regular | - | 6e6b8b6f70c6#slot1 | - | multi_direction | False | - |  |  | None |
| family_s15_1b876e6b8b6f70c6_ext_008_regular | attempt_s15sim_20261016T184726Z | 6e6b8b6f70c6#slot1 | feint | multi_direction | True | 2 | synchronous=generated/sequential=generated |  | 685.472 |
| family_s15_1b876e6b8b6f70c6_ext_009_regular | attempt_s15sim_20261016T184726Z | 6e6b8b6f70c6#slot1 | penetration | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 387.775 |
| family_s15_1c267d4d7000043d_ext_005_regular | attempt_s15sim_20261016T191411Z | 7d4d7000043d#slot1 | transit | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 187.888 |
| family_s15_1c267d4d7000043d_ext_006_regular | attempt_s15sim_20261016T191411Z | 7d4d7000043d#slot1 | reconnaissance | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 154.201 |
| family_s15_1c267d4d7000043d_ext_007_regular | attempt_s15sim_20261016T191411Z | 7d4d7000043d#slot1 | monitoring | same_direction | True | 3 | synchronous=generated/sequential=generated |  | 1384.913 |
| family_s15_1c267d4d7000043d_ext_008_regular | attempt_s15sim_20261016T191411Z | 7d4d7000043d#slot1 | feint | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 177.587 |
| family_s15_1c267d4d7000043d_ext_009_regular | attempt_s15sim_20261016T191411Z | 7d4d7000043d#slot1 | penetration | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 117.011 |
| family_s15_38bedc9d791d547b_ext_005_regular | attempt_s15sim_20261016T191411Z | dc9d791d547b#slot1 | transit | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 245.448 |
| family_s15_38bedc9d791d547b_ext_006_regular | attempt_s15sim_20261016T191411Z | dc9d791d547b#slot1 | reconnaissance | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 265.801 |
| family_s15_38bedc9d791d547b_ext_007_regular | - | dc9d791d547b#slot1 | - | same_direction | False | - |  |  | None |
| family_s15_38bedc9d791d547b_ext_008_regular | attempt_s15sim_20261016T191411Z | dc9d791d547b#slot1 | feint | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 315.701 |
| family_s15_38bedc9d791d547b_ext_009_regular | attempt_s15sim_20261016T191411Z | dc9d791d547b#slot1 | penetration | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 252.027 |
| family_s15_79c93b22d09e8a7a_ext_000_regular | attempt_s15sim_20261016T191411Z | 3b22d09e8a7a#slot0 | transit | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 182.908 |
| family_s15_79c93b22d09e8a7a_ext_001_regular | attempt_s15sim_20261016T191411Z | 3b22d09e8a7a#slot0 | reconnaissance | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 569.492 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | attempt_s15sim_20261016T191411Z | 3b22d09e8a7a#slot0 | monitoring | same_direction | False | - | synchronous=infeasible/sequential=infeasible | synchronous:时刻叠加间距/sequential:时刻叠加间距 | None |
| family_s15_79c93b22d09e8a7a_ext_003_regular | attempt_s15sim_20261016T191411Z | 3b22d09e8a7a#slot0 | feint | same_direction | True | 1 | synchronous=generated/sequential=generated |  | 229.02 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | attempt_s15sim_20261016T191411Z | 3b22d09e8a7a#slot0 | penetration | same_direction | False | - | synchronous=infeasible/sequential=infeasible | synchronous:时刻叠加间距/sequential:时刻叠加间距 | None |
| family_s15_aa4c66be8e85d64d_ext_000_regular | attempt_s15sim_20261016T191411Z | 66be8e85d64d#slot0 | transit | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 160.59 |
| family_s15_aa4c66be8e85d64d_ext_001_regular | attempt_s15sim_20261016T191411Z | 66be8e85d64d#slot0 | reconnaissance | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 197.266 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | attempt_s15sim_20261016T191411Z | 66be8e85d64d#slot0 | monitoring | multi_direction | False | - | synchronous=infeasible/sequential=infeasible | synchronous:时刻叠加间距/sequential:时刻叠加间距 | None |
| family_s15_aa4c66be8e85d64d_ext_003_regular | attempt_s15sim_20261016T191411Z | 66be8e85d64d#slot0 | feint | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 270.2 |
| family_s15_aa4c66be8e85d64d_ext_004_regular | attempt_s15sim_20261016T191411Z | 66be8e85d64d#slot0 | penetration | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 189.921 |
| family_s15_c713f51898e81011_ext_000_regular | attempt_s15sim_20261016T191411Z | f51898e81011#slot0 | transit | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 650.773 |
| family_s15_c713f51898e81011_ext_001_regular | attempt_s15sim_20261016T191411Z | f51898e81011#slot0 | reconnaissance | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 550.635 |
| family_s15_c713f51898e81011_ext_002_regular | - | f51898e81011#slot0 | - | multi_direction | False | - |  |  | None |
| family_s15_c713f51898e81011_ext_003_regular | attempt_s15sim_20261016T191411Z | f51898e81011#slot0 | feint | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 651.468 |
| family_s15_c713f51898e81011_ext_004_regular | attempt_s15sim_20261016T191411Z | f51898e81011#slot0 | penetration | multi_direction | True | 1 | synchronous=generated/sequential=generated |  | 530.994 |

## P2 原始 reason 计数（未归类前的字面值）

| mode:stage:reason | count |
|---|---|
| sequential:时刻叠加间距:timing_conflict | 3 |
| synchronous:时刻叠加间距:timing_conflict | 3 |

## P3 按抽签：五个意图是否全部得到严格配对

| family#slot | approach_mode | layout | facility_count | group_count | member_counts | 本次运行 | 严格配对 | 五意图全配对 | 未配对意图 | 失败环节 |
|---|---|---|---|---|---|---|---|---|---|---|
| family_s15_1b876e6b8b6f70c6#slot1 | multi_direction | single | 1 | 1 | 10 | 5/5 | 4/5 | False | - | - |
| family_s15_1c267d4d7000043d#slot1 | same_direction | clustered | 2 | 1 | 6 | 5/5 | 5/5 | True | - | - |
| family_s15_38bedc9d791d547b#slot1 | same_direction | clustered | 2 | 1 | 7 | 5/5 | 4/5 | False | - | - |
| family_s15_79c93b22d09e8a7a#slot0 | same_direction | clustered | 3 | 2 | 4/2 | 5/5 | 3/5 | False | monitoring, penetration | 时刻叠加间距 |
| family_s15_aa4c66be8e85d64d#slot0 | multi_direction | single | 1 | 1 | 9 | 5/5 | 4/5 | False | monitoring | 时刻叠加间距 |
| family_s15_c713f51898e81011#slot0 | multi_direction | clustered | 3 | 1 | 10 | 5/5 | 4/5 | False | - | - |

## P4 M1 实测事实：逼近方式一致性与驻留/重访检出

| intent | 骨架 | 严格配对 | 参与成员 | 驻留检出 | 重访检出 | 观察驻留检出 | 轮数分布 |
|---|---|---|---|---|---|---|---|
| transit | 6 | 6 | 96 | 0 | 0 | 0 | {"2": 1, "1": 5} |
| reconnaissance | 6 | 6 | 96 | 84 | 0 | 68 | {"4": 1, "1": 5} |
| monitoring | 3 | 1 | 12 | 12 | 12 | 0 | {"3": 1} |
| feint | 6 | 6 | 96 | 96 | 0 | 0 | {"2": 1, "1": 5} |
| penetration | 6 | 5 | 84 | 42 | 0 | 0 | {"1": 5} |

- 实测逼近方式与指定一致：56/56 次（逐骨架见 P1 与 summary JSON 的 measured_approach_matches_spec）。

## P5 实测最小机间距（m，取全部 episode 行）

| 范围 | count | min | p50 | p90 | max |
|---|---|---|---|---|---|
| all | 48 | 2.195949 | 15.739282 | 19.622268 | 22.069216 |

## P6 每骨架分阶段墙钟（s）

| skeleton_id | 规划 | 单机预演+时刻安排 | 联合仿真 | M1判定+审计+测量+写盘 | skeleton_total |
|---|---|---|---|---|---|
| family_s15_1b876e6b8b6f70c6_ext_005_regular | 73.918 | 335.822 | 187.919 | 13.579 | 611.238 |
| family_s15_1b876e6b8b6f70c6_ext_006_regular | 83.149 | 738.486 | 261.52 | 37.012 | 1120.167 |
| family_s15_1b876e6b8b6f70c6_ext_007_regular | None | None | None | None | None |
| family_s15_1b876e6b8b6f70c6_ext_008_regular | 90.284 | 369.854 | 210.611 | 14.724 | 685.472 |
| family_s15_1b876e6b8b6f70c6_ext_009_regular | 56.804 | 160.333 | 158.052 | 12.587 | 387.775 |
| family_s15_1c267d4d7000043d_ext_005_regular | 18.935 | 63.677 | 91.557 | 13.719 | 187.888 |
| family_s15_1c267d4d7000043d_ext_006_regular | 22.719 | 50.917 | 73.694 | 6.871 | 154.201 |
| family_s15_1c267d4d7000043d_ext_007_regular | 120.569 | 875.379 | 326.7 | 62.265 | 1384.913 |
| family_s15_1c267d4d7000043d_ext_008_regular | 33.766 | 55.908 | 82.338 | 5.575 | 177.587 |
| family_s15_1c267d4d7000043d_ext_009_regular | 16.127 | 39.87 | 56.749 | 4.265 | 117.011 |
| family_s15_38bedc9d791d547b_ext_005_regular | 27.029 | 88.973 | 121.693 | 7.753 | 245.448 |
| family_s15_38bedc9d791d547b_ext_006_regular | 32.424 | 95.175 | 129.611 | 8.592 | 265.801 |
| family_s15_38bedc9d791d547b_ext_007_regular | None | None | None | None | None |
| family_s15_38bedc9d791d547b_ext_008_regular | 38.921 | 111.456 | 155.917 | 9.408 | 315.701 |
| family_s15_38bedc9d791d547b_ext_009_regular | 39.649 | 86.764 | 117.945 | 7.669 | 252.027 |
| family_s15_79c93b22d09e8a7a_ext_000_regular | 98.081 | 32.759 | 48.02 | 4.047 | 182.908 |
| family_s15_79c93b22d09e8a7a_ext_001_regular | 406.276 | 60.744 | 92.195 | 10.277 | 569.492 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | None | None | None | None | None |
| family_s15_79c93b22d09e8a7a_ext_003_regular | 128.79 | 37.418 | 58.444 | 4.367 | 229.02 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | None | None | None | None | None |
| family_s15_aa4c66be8e85d64d_ext_000_regular | 31.177 | 51.987 | 70.863 | 6.564 | 160.59 |
| family_s15_aa4c66be8e85d64d_ext_001_regular | 40.675 | 60.835 | 85.271 | 10.486 | 197.266 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | None | None | None | None | None |
| family_s15_aa4c66be8e85d64d_ext_003_regular | 60.14 | 78.916 | 121.362 | 9.781 | 270.2 |
| family_s15_aa4c66be8e85d64d_ext_004_regular | 33.144 | 62.409 | 87.164 | 7.204 | 189.921 |
| family_s15_c713f51898e81011_ext_000_regular | 170.896 | 193.373 | 263.66 | 22.844 | 650.773 |
| family_s15_c713f51898e81011_ext_001_regular | 150.842 | 162.979 | 215.416 | 21.398 | 550.635 |
| family_s15_c713f51898e81011_ext_002_regular | None | None | None | None | None |
| family_s15_c713f51898e81011_ext_003_regular | 190.328 | 185.171 | 254.417 | 21.551 | 651.468 |
| family_s15_c713f51898e81011_ext_004_regular | 165.776 | 153.637 | 196.314 | 15.267 | 530.994 |

口径：记录未分阶段计时。规划取自 `candidate_pool.json` 的 `group_search_metrics[*].wall_s` 与 `combination_search.wall_s`；单机预演与时刻安排在记录中不分开，合并为 setup 残差（各 mode 的 `amortized_skeleton_setup_s` 之和减去规划）；联合仿真取 `simulation_wall_s`；M1 判定、审计、测量与写盘在记录中不分开，合并取 `episode_postprocess_wall_s`。未为取得更细的分段而修改被测代码。

## P7 分阶段分布汇总（s）

| 阶段 | count | min | p50 | p90 | max |
|---|---|---|---|---|---|
| 规划 | 24 | 16.12709 | 58.471874 | 169.359866 | 406.275917 |
| 单机预演+时刻安排 | 24 | 32.759305 | 87.868381 | 359.644677 | 875.379329 |
| 联合仿真 | 24 | 48.019933 | 121.527651 | 259.389515 | 326.699694 |
| M1判定+审计+测量+写盘 | 24 | 4.047475 | 10.029375 | 22.456241 | 62.264826 |
| skeleton_total | 24 | 117.01121 | 268.000736 | 675.271253 | 1384.912895 |
