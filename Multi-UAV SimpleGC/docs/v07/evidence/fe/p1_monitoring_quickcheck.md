# FE-P1 监视撤离规划快速检查

判定：**PASS**；运行状态：completed。

仅覆盖七个指定骨架的规划，不代表飞行时序或完整仿真验收。

## A：骨架状态

| skeleton_id | completed | status | eligible_combinations | old_eligible_combinations |
| --- | --- | --- | --- | --- |
| family_s15_79c93b22d09e8a7a_ext_002_regular | True | PASS | 74 | 86 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | True | PASS | 1 | 5 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | True | PASS | 98 | 98 |
| family_s15_1c267d4d7000043d_ext_007_regular | True | PASS | 96 | 97 |
| family_s15_1b876e6b8b6f70c6_ext_007_regular | True | PASS | 192 | 192 |
| family_s15_38bedc9d791d547b_ext_007_regular | True | PASS | 44 | 47 |
| family_s15_c713f51898e81011_ext_002_regular | True | PASS | 149 | 173 |

## B：所选候选的组内终点间距

lateral_spacing_m 来源：descriptor.family_conditions.lateral_spacing_m；单成员距离记为 -。

| skeleton_id | group_id | role | execution_method | member_count | minimum_endpoint_distance_m | lateral_spacing_m |
| --- | --- | --- | --- | --- | --- | --- |
| family_s15_79c93b22d09e8a7a_ext_002_regular | task_group_01 | monitoring | monitoring | 4 | 23.106178 | 19.308601 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | task_group_02 | monitoring | monitoring | 2 | 28.022777 | 19.308601 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | task_group_01 | intrusion | intrusion | 2 | 27.896945 | 19.308601 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | task_group_02 | feint | feint | 2 | 19.318394 | 19.308601 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | task_group_03 | monitoring | monitoring | 2 | 25.214291 | 19.308601 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | task_group_01 | monitoring | monitoring | 9 | 25.590963 | 23.202986 |
| family_s15_1c267d4d7000043d_ext_007_regular | task_group_01 | monitoring | monitoring | 6 | 24.809416 | 19.160423 |
| family_s15_1b876e6b8b6f70c6_ext_007_regular | task_group_01 | monitoring | monitoring | 10 | 20.303519 | 17.889727 |
| family_s15_38bedc9d791d547b_ext_007_regular | task_group_01 | monitoring | monitoring | 7 | 26.217187 | 19.197824 |
| family_s15_c713f51898e81011_ext_002_regular | task_group_01 | monitoring | monitoring | 10 | 27.582256 | 22.627096 |

## C：七个骨架的提案接受率

| role | execution_method | new_accepted | new_proposals | new_rate | old_accepted | old_proposals | old_rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| feint | feint | 200 | 200 | 1.000000 | 200 | 200 | 1.000000 |
| intrusion | intrusion | 200 | 200 | 1.000000 | 200 | 200 | 1.000000 |
| monitoring | monitoring | 1239 | 1600 | 0.774375 | 1290 | 1600 | 0.806250 |

停止条件 2 仅比较本次已完成骨架的相同新旧集合：

| role | execution_method | new_accepted | new_proposals | new_rate | old_accepted | old_proposals | old_rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| feint | feint | 200 | 200 | 1.000000 | 200 | 200 | 1.000000 |
| intrusion | intrusion | 200 | 200 | 1.000000 | 200 | 200 | 1.000000 |
| monitoring | monitoring | 1239 | 1600 | 0.774375 | 1290 | 1600 | 0.806250 |

## D：新运行拒绝提案中的触发统计

proposals 为含该原因的去重提案数；occurrences 为整条记录递归出现次数（可包含重复证据）。

| role | execution_method | terminal_endpoint_spacing_proposals | terminal_endpoint_spacing_occurrences | retreat_endpoint_invalid_proposals | retreat_endpoint_invalid_occurrences | inward_rotation_skipped_proposals | inward_rotation_skipped_occurrences |
| --- | --- | --- | --- | --- | --- | --- | --- |
| feint | feint | 0 | 0 | 0 | 0 | 0 | 0 |
| intrusion | intrusion | 0 | 0 | 0 | 0 | 0 | 0 |
| monitoring | monitoring | 54 | 108 | 6 | 6 | 86 | 666 |

## E：未完成骨架

无。

## 停止条件与诊断

停止条件：[]

低于 0.99 倍编队间距的监视组及旋转证据：[]

## 来源

- new: F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261017T053528Z
- descriptors: F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15desc_20261016T154909Z
- old: ['F:\\CASIA\\Drone Swarm Situational Awareness Algorithm\\SwarmData\\v07_dataset\\attempt_s15yield_20261016T154921Z', 'F:\\CASIA\\Drone Swarm Situational Awareness Algorithm\\SwarmData\\v07_dataset\\attempt_s15yield_20261016T163901Z']
- run_status: completed
- entry_commit: 01eb76c400fa79e4534a859d2f3a4165bd453b79
- summary_commit: 01eb76c400fa79e4534a859d2f3a4165bd453b79
