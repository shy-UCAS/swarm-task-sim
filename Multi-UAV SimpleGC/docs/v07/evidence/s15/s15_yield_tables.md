# S1.5 阶段 2 纯规划产额统计表

- 描述目录：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15desc_20261016T154909Z`
- 规划目录（2 个 attempt，每个 skeleton_id 只来自其中一个）：
  - `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261016T154921Z`：状态 `TIME_LIMIT_STOP`，选中 160，落盘完成 99，墙钟 2700.1 s
  - `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261016T163901Z`：状态 `completed`，选中 61，落盘完成 61，墙钟 3889.6 s
- 注册骨架 160 个；本次统计范围（各 attempt 声明并集）160 个，其中有 `planning_result.json` 的 160 个（成功 141）；未完成 **0** 个
- 组提案 42000 条，接受 31718 条；被拒 10282 条，无法按 4.3 解析 0 条（0.0000%）
- 1 设施地图（T5 记 `not_applicable`）：40 个骨架
- 骨架级表格（T1、T2a、T2b、T5、T6）的分母一律包含未完成骨架，并在末列单列 `未完成` 数量；T3、T4 的分母是组提案，未完成骨架不产生提案，故不在其分母内。

## 未完成骨架计数：意图 × 布局

| intent | single | isolated | clustered | linear |
|---|---|---|---|---|
| transit | 0 | 0 | 0 | 0 |
| reconnaissance | 0 | 0 | 0 | 0 |
| monitoring | 0 | 0 | 0 | 0 |
| feint | 0 | 0 | 0 | 0 |
| penetration | 0 | 0 | 0 | 0 |

## T1 骨架成功率：意图 × 布局

| intent | single | isolated | clustered | linear | 未完成 |
|---|---|---|---|---|---|
| transit | 7/8 (87.50%) | 8/8 (100.00%) | 8/8 (100.00%) | 8/8 (100.00%) | 0 |
| reconnaissance | 4/8 (50.00%) | 7/8 (87.50%) | 7/8 (87.50%) | 4/8 (50.00%) | 0 |
| monitoring | 6/8 (75.00%) | 8/8 (100.00%) | 7/8 (87.50%) | 7/8 (87.50%) | 0 |
| feint | 7/8 (87.50%) | 8/8 (100.00%) | 8/8 (100.00%) | 8/8 (100.00%) | 0 |
| penetration | 7/8 (87.50%) | 7/8 (87.50%) | 7/8 (87.50%) | 8/8 (100.00%) | 0 |
| 各布局内五意图成功率最大值/最小值之比 | 1.7500 | 1.1429 | 1.1429 | 2.0000 |  |

## T2a 骨架成功率：意图 × 接近方式

| intent | multi_direction | same_direction | 未完成 |
|---|---|---|---|
| transit | 15/15 (100.00%) | 16/17 (94.12%) | 0 |
| reconnaissance | 6/15 (40.00%) | 16/17 (94.12%) | 0 |
| monitoring | 12/15 (80.00%) | 16/17 (94.12%) | 0 |
| feint | 15/15 (100.00%) | 16/17 (94.12%) | 0 |
| penetration | 15/15 (100.00%) | 14/17 (82.35%) | 0 |

## T2b 骨架成功率：意图 × 设施数

| intent | 1 | 2 | 3 | 未完成 |
|---|---|---|---|---|
| transit | 7/8 (87.50%) | 14/14 (100.00%) | 10/10 (100.00%) | 0 |
| reconnaissance | 4/8 (50.00%) | 10/14 (71.43%) | 8/10 (80.00%) | 0 |
| monitoring | 6/8 (75.00%) | 12/14 (85.71%) | 10/10 (100.00%) | 0 |
| feint | 7/8 (87.50%) | 14/14 (100.00%) | 10/10 (100.00%) | 0 |
| penetration | 7/8 (87.50%) | 12/14 (85.71%) | 10/10 (100.00%) | 0 |

## T3 组提案接受率

分母为组提案数；0 个未完成骨架没有 `proposals.jsonl`，不产生提案。

### T3a：role/execution_method × 布局

| role/execution_method | single | isolated | clustered | linear |
|---|---|---|---|---|
| feint/feint | 1562/1800 (86.78%) | 2707/2800 (96.68%) | 2547/2600 (97.96%) | 2779/2800 (99.25%) |
| intrusion/intrusion | 1182/1600 (73.88%) | 1634/2200 (74.27%) | 1370/1600 (85.62%) | 1979/2000 (98.95%) |
| monitoring/monitoring | 588/2000 (29.40%) | 1363/2200 (61.95%) | 1549/2200 (70.41%) | 1726/2200 (78.45%) |
| reconnaissance/area_search | 365/1200 (30.42%) | 978/1400 (69.86%) | 387/600 (64.50%) | 586/1600 (36.62%) |
| reconnaissance/close_observation | 365/400 (91.25%) | 774/800 (96.75%) | 1373/1400 (98.07%) | 597/600 (99.50%) |
| transit/transit | 902/1600 (56.38%) | 1397/2200 (63.50%) | 1293/2000 (64.65%) | 1715/2200 (77.95%) |

### T3b：role/execution_method × 成员数分桶

| role/execution_method | 2–3 | 4–5 | ≥6 | <2 |
|---|---|---|---|---|
| feint/feint | 2199/2200 (99.95%) | 2393/2400 (99.71%) | 5003/5400 (92.65%) | 0/0 |
| intrusion/intrusion | 1797/1800 (99.83%) | 1253/1400 (89.50%) | 3115/4200 (74.17%) | 0/0 |
| monitoring/monitoring | 1311/1800 (72.83%) | 1255/1600 (78.44%) | 2660/5200 (51.15%) | 0/0 |
| reconnaissance/area_search | 199/600 (33.17%) | 777/1400 (55.50%) | 1340/2800 (47.86%) | 0/0 |
| reconnaissance/close_observation | 600/600 (100.00%) | 200/200 (100.00%) | 2309/2400 (96.21%) | 0/0 |
| transit/transit | 1072/1200 (89.33%) | 1303/1600 (81.44%) | 2932/5200 (56.38%) | 0/0 |

## T4 被拒提案归因（多标签计数）

分母为被拒提案数；0 个未完成骨架不产生提案。

### T4a：role/execution_method × 类别

| role/execution_method | target_facility | obstacle:between_facilities | obstacle:entry_blocking | obstacle:facility_side | unattributed:connection_search_budget_exhausted | unattributed:shape_search_budget_exhausted | unattributed:whole_route_check | total |
|---|---|---|---|---|---|---|---|---|
| feint/feint | 0 | 0 | 0 | 0 | 260 | 0 | 145 | 405 |
| intrusion/intrusion | 0 | 0 | 0 | 29 | 23 | 1132 | 51 | 1235 |
| monitoring/monitoring | 0 | 203 | 125 | 840 | 613 | 443 | 1262 | 3374 |
| reconnaissance/area_search | 1837 | 148 | 234 | 1047 | 288 | 167 | 34 | 2484 |
| reconnaissance/close_observation | 0 | 0 | 0 | 0 | 41 | 0 | 50 | 91 |
| transit/transit | 0 | 14 | 45 | 77 | 1385 | 0 | 1173 | 2693 |

### T4b：layout × 类别

| layout | target_facility | obstacle:between_facilities | obstacle:entry_blocking | obstacle:facility_side | unattributed:connection_search_budget_exhausted | unattributed:shape_search_budget_exhausted | unattributed:whole_route_check | total |
|---|---|---|---|---|---|---|---|---|
| single | 590 | 0 | 266 | 1287 | 1273 | 647 | 359 | 3636 |
| isolated | 173 | 30 | 10 | 370 | 533 | 640 | 1097 | 2747 |
| clustered | 154 | 329 | 0 | 4 | 572 | 230 | 699 | 1881 |
| linear | 920 | 6 | 128 | 332 | 232 | 225 | 560 | 2018 |

### T4c：互斥签名前 15 名（类别集合排序后以 + 连接）

| signature | count |
|---|---|
| unattributed:whole_route_check | 2715 |
| unattributed:connection_search_budget_exhausted | 2610 |
| unattributed:shape_search_budget_exhausted | 1742 |
| obstacle:facility_side | 910 |
| obstacle:facility_side+target_facility | 776 |
| target_facility | 760 |
| obstacle:between_facilities | 258 |
| obstacle:entry_blocking+obstacle:facility_side+target_facility | 171 |
| obstacle:entry_blocking+obstacle:facility_side | 136 |
| obstacle:between_facilities+target_facility | 107 |
| obstacle:entry_blocking | 74 |
| obstacle:entry_blocking+target_facility | 23 |

## T5 作业段进入非目标预警区：意图 × 布局（仅多设施布局）

| intent | single | isolated | clustered | linear | 未完成 |
|---|---|---|---|---|---|
| transit | not_applicable | 0/8 | 1/8 | 0/8 | 0 |
| reconnaissance | not_applicable | 0/7 [not_counted 1] | 0/7 [not_counted 1] | 0/4 [not_counted 4] | 0 |
| monitoring | not_applicable | 0/8 | 0/7 [not_counted 1] | 0/7 [not_counted 1] | 0 |
| feint | not_applicable | 0/8 | 0/8 | 0/8 | 0 |
| penetration | not_applicable | 0/7 [not_counted 1] | 0/7 [not_counted 1] | 0/8 | 0 |

分母为有 `selected_skeleton.json` 且可测的骨架数（第 4.4 条只统计有该文件的骨架）；`not_applicable` 为单设施地图；`[not_counted n]` 为无 `selected_skeleton.json` 因而按第 4.4 条不统计的骨架数；`[not_available n]` 为找不到 `references` 或 `work_points_enu_m` 的骨架数；`未完成` 列为该意图下未完成的多设施骨架数。

## T6 每骨架规划墙钟（s）：按意图

| intent | count | min | p50 | p90 | max | 未完成 |
|---|---|---|---|---|---|---|
| transit | 32 | 9.178188 | 54.349057 | 188.182761 | 271.283981 | 0 |
| reconnaissance | 32 | 6.867401 | 88.286577 | 2049.024934 | 2991.325922 | 0 |
| monitoring | 32 | 13.918993 | 266.682278 | 487.776415 | 631.668724 | 0 |
| feint | 32 | 23.12528 | 90.581065 | 267.986261 | 309.842164 | 0 |
| penetration | 32 | 0.438274 | 65.470936 | 205.78435 | 275.902805 | 0 |
| all | 160 | 0.438274 | 91.238495 | 397.179195 | 2991.325922 | 0 |

分布只统计有 `planning_result.json` 的骨架；未完成骨架的墙钟是中止时的快照，不进入分布，其数量单列在 `未完成` 列，并在 summary JSON 的 `t6_all_registered` 中另附。

## T6b 每骨架规划耗时与组构成（意图 / 组数 / 各组成员数）

| skeleton_id | intent | layout | approach_mode | facility_count | group_count | member_counts | roles | planning_wall_s | completed |
|---|---|---|---|---|---|---|---|---|---|
| family_s15_1b876e6b8b6f70c6_ext_000_regular | transit | single | same_direction | 1 | 1 | 10 | transit | 16.56193919999714 | True |
| family_s15_1b876e6b8b6f70c6_ext_001_regular | reconnaissance | single | same_direction | 1 | 1 | 10 | reconnaissance | 20.54473810000127 | True |
| family_s15_1b876e6b8b6f70c6_ext_002_regular | monitoring | single | same_direction | 1 | 1 | 10 | monitoring | 75.55359930000122 | True |
| family_s15_1b876e6b8b6f70c6_ext_003_regular | feint | single | same_direction | 1 | 1 | 10 | feint | 23.125280100000964 | True |
| family_s15_1b876e6b8b6f70c6_ext_004_regular | penetration | single | same_direction | 1 | 1 | 10 | intrusion | 0.43827410000085365 | True |
| family_s15_1b876e6b8b6f70c6_ext_005_regular | transit | single | multi_direction | 1 | 1 | 10 | transit | 77.69490489999953 | True |
| family_s15_1b876e6b8b6f70c6_ext_006_regular | reconnaissance | single | multi_direction | 1 | 1 | 10 | reconnaissance | 86.14170889999878 | True |
| family_s15_1b876e6b8b6f70c6_ext_007_regular | monitoring | single | multi_direction | 1 | 1 | 10 | monitoring | 282.7844287000007 | True |
| family_s15_1b876e6b8b6f70c6_ext_008_regular | feint | single | multi_direction | 1 | 1 | 10 | feint | 89.11658380000154 | True |
| family_s15_1b876e6b8b6f70c6_ext_009_regular | penetration | single | multi_direction | 1 | 1 | 10 | intrusion | 59.810294000002614 | True |
| family_s15_1c267d4d7000043d_ext_000_regular | transit | clustered | multi_direction | 2 | 2 | 3/3 | transit/transit | 28.58144799999718 | True |
| family_s15_1c267d4d7000043d_ext_001_regular | reconnaissance | clustered | multi_direction | 2 | 2 | 3/3 | reconnaissance/reconnaissance | 31.03000780000002 | True |
| family_s15_1c267d4d7000043d_ext_002_regular | monitoring | clustered | multi_direction | 2 | 2 | 3/3 | monitoring/monitoring | 115.22164580000026 | True |
| family_s15_1c267d4d7000043d_ext_003_regular | feint | clustered | multi_direction | 2 | 2 | 3/3 | feint/feint | 32.21605289999934 | True |
| family_s15_1c267d4d7000043d_ext_004_regular | penetration | clustered | multi_direction | 2 | 2 | 3/3 | intrusion/feint | 23.192218399999547 | True |
| family_s15_1c267d4d7000043d_ext_005_regular | transit | clustered | same_direction | 2 | 1 | 6 | transit | 21.055825400002504 | True |
| family_s15_1c267d4d7000043d_ext_006_regular | reconnaissance | clustered | same_direction | 2 | 1 | 6 | reconnaissance | 29.09742720000213 | True |
| family_s15_1c267d4d7000043d_ext_007_regular | monitoring | clustered | same_direction | 2 | 1 | 6 | monitoring | 192.50866329999917 | True |
| family_s15_1c267d4d7000043d_ext_008_regular | feint | clustered | same_direction | 2 | 1 | 6 | feint | 52.0605936000029 | True |
| family_s15_1c267d4d7000043d_ext_009_regular | penetration | clustered | same_direction | 2 | 1 | 6 | intrusion | 24.172707899997476 | True |
| family_s15_38bedc9d791d547b_ext_000_regular | transit | clustered | same_direction | 2 | 1 | 7 | transit | 39.28521030000047 | True |
| family_s15_38bedc9d791d547b_ext_001_regular | reconnaissance | clustered | same_direction | 2 | 1 | 7 | reconnaissance | 83.20737059999738 | True |
| family_s15_38bedc9d791d547b_ext_002_regular | monitoring | clustered | same_direction | 2 | 1 | 7 | monitoring | 161.12999430000127 | True |
| family_s15_38bedc9d791d547b_ext_003_regular | feint | clustered | same_direction | 2 | 1 | 7 | feint | 72.47413219999726 | True |
| family_s15_38bedc9d791d547b_ext_004_regular | penetration | clustered | same_direction | 2 | 1 | 7 | intrusion | 0.4896030999989307 | True |
| family_s15_38bedc9d791d547b_ext_005_regular | transit | clustered | same_direction | 2 | 1 | 7 | transit | 44.049017400000594 | True |
| family_s15_38bedc9d791d547b_ext_006_regular | reconnaissance | clustered | same_direction | 2 | 1 | 7 | reconnaissance | 54.05206019999969 | True |
| family_s15_38bedc9d791d547b_ext_007_regular | monitoring | clustered | same_direction | 2 | 1 | 7 | monitoring | 219.129997 | True |
| family_s15_38bedc9d791d547b_ext_008_regular | feint | clustered | same_direction | 2 | 1 | 7 | feint | 61.57452919999923 | True |
| family_s15_38bedc9d791d547b_ext_009_regular | penetration | clustered | same_direction | 2 | 2 | 2/5 | feint/intrusion | 64.92720420000114 | True |
| family_s15_5024cb2ccea653ae_ext_000_regular | transit | linear | multi_direction | 2 | 2 | 5/3 | transit/transit | 132.20613270000104 | True |
| family_s15_5024cb2ccea653ae_ext_001_regular | reconnaissance | linear | multi_direction | 2 | 2 | 5/3 | reconnaissance/reconnaissance | 1762.1946726999995 | True |
| family_s15_5024cb2ccea653ae_ext_002_regular | monitoring | linear | multi_direction | 2 | 2 | 5/3 | monitoring/monitoring | 396.99617450000005 | True |
| family_s15_5024cb2ccea653ae_ext_003_regular | feint | linear | multi_direction | 2 | 2 | 5/3 | feint/feint | 161.85254319999876 | True |
| family_s15_5024cb2ccea653ae_ext_004_regular | penetration | linear | multi_direction | 2 | 3 | 3/3/2 | intrusion/intrusion/feint | 96.20182529999875 | True |
| family_s15_5024cb2ccea653ae_ext_005_regular | transit | linear | multi_direction | 2 | 2 | 4/4 | transit/transit | 125.46626639999886 | True |
| family_s15_5024cb2ccea653ae_ext_006_regular | reconnaissance | linear | multi_direction | 2 | 2 | 4/4 | reconnaissance/reconnaissance | 2763.9517646999957 | True |
| family_s15_5024cb2ccea653ae_ext_007_regular | monitoring | linear | multi_direction | 2 | 2 | 4/4 | monitoring/monitoring | 398.8263805000024 | True |
| family_s15_5024cb2ccea653ae_ext_008_regular | feint | linear | multi_direction | 2 | 2 | 4/4 | feint/feint | 155.07747069999823 | True |
| family_s15_5024cb2ccea653ae_ext_009_regular | penetration | linear | multi_direction | 2 | 3 | 2/4/2 | intrusion/intrusion/feint | 89.8049142000018 | True |
| family_s15_79c93b22d09e8a7a_ext_000_regular | transit | clustered | same_direction | 3 | 2 | 4/2 | transit/transit | 160.5531540000011 | True |
| family_s15_79c93b22d09e8a7a_ext_001_regular | reconnaissance | clustered | same_direction | 3 | 2 | 4/2 | reconnaissance/reconnaissance | 602.1299024 | True |
| family_s15_79c93b22d09e8a7a_ext_002_regular | monitoring | clustered | same_direction | 3 | 2 | 4/2 | monitoring/monitoring | 378.1766362999988 | True |
| family_s15_79c93b22d09e8a7a_ext_003_regular | feint | clustered | same_direction | 3 | 2 | 4/2 | feint/feint | 206.4793916000017 | True |
| family_s15_79c93b22d09e8a7a_ext_004_regular | penetration | clustered | same_direction | 3 | 3 | 2/2/2 | intrusion/feint/monitoring | 275.90280500000154 | True |
| family_s15_79c93b22d09e8a7a_ext_005_regular | transit | clustered | same_direction | 3 | 1 | 6 | transit | 108.42785820000063 | True |
| family_s15_79c93b22d09e8a7a_ext_006_regular | reconnaissance | clustered | same_direction | 3 | 1 | 6 | reconnaissance | 95.61485149999862 | True |
| family_s15_79c93b22d09e8a7a_ext_007_regular | monitoring | clustered | same_direction | 3 | 1 | 6 | monitoring | 264.61694089999946 | True |
| family_s15_79c93b22d09e8a7a_ext_008_regular | feint | clustered | same_direction | 3 | 1 | 6 | feint | 99.46327340000062 | True |
| family_s15_79c93b22d09e8a7a_ext_009_regular | penetration | clustered | same_direction | 3 | 1 | 6 | intrusion | 66.01466839999921 | True |
| family_s15_7a34c19b154f1faf_ext_000_regular | transit | isolated | same_direction | 2 | 1 | 9 | transit | 18.110330300001806 | True |
| family_s15_7a34c19b154f1faf_ext_001_regular | reconnaissance | isolated | same_direction | 2 | 1 | 9 | reconnaissance | 36.28303270000106 | True |
| family_s15_7a34c19b154f1faf_ext_002_regular | monitoring | isolated | same_direction | 2 | 1 | 9 | monitoring | 143.7266314999979 | True |
| family_s15_7a34c19b154f1faf_ext_003_regular | feint | isolated | same_direction | 2 | 1 | 9 | feint | 47.05839990000095 | True |
| family_s15_7a34c19b154f1faf_ext_004_regular | penetration | isolated | same_direction | 2 | 1 | 9 | intrusion | 0.5706175999985135 | True |
| family_s15_7a34c19b154f1faf_ext_005_regular | transit | isolated | same_direction | 2 | 2 | 5/4 | transit/transit | 36.9869437999987 | True |
| family_s15_7a34c19b154f1faf_ext_006_regular | reconnaissance | isolated | same_direction | 2 | 2 | 5/4 | reconnaissance/reconnaissance | 75.82779579999988 | True |
| family_s15_7a34c19b154f1faf_ext_007_regular | monitoring | isolated | same_direction | 2 | 2 | 5/4 | monitoring/monitoring | 171.64608170000065 | True |
| family_s15_7a34c19b154f1faf_ext_008_regular | feint | isolated | same_direction | 2 | 2 | 5/4 | feint/feint | 60.76318430000174 | True |
| family_s15_7a34c19b154f1faf_ext_009_regular | penetration | isolated | same_direction | 2 | 2 | 5/4 | intrusion/intrusion | 27.962528699998074 | True |
| family_s15_7b73a7fc210d4c8f_ext_000_regular | transit | linear | multi_direction | 3 | 1 | 12 | transit | 140.28842670000085 | True |
| family_s15_7b73a7fc210d4c8f_ext_001_regular | reconnaissance | linear | multi_direction | 3 | 1 | 12 | reconnaissance | 2979.922057399999 | True |
| family_s15_7b73a7fc210d4c8f_ext_002_regular | monitoring | linear | multi_direction | 3 | 1 | 12 | monitoring | 606.7398098999984 | True |
| family_s15_7b73a7fc210d4c8f_ext_003_regular | feint | linear | multi_direction | 3 | 1 | 12 | feint | 207.0371742999996 | True |
| family_s15_7b73a7fc210d4c8f_ext_004_regular | penetration | linear | multi_direction | 3 | 1 | 12 | intrusion | 125.48255359999894 | True |
| family_s15_7b73a7fc210d4c8f_ext_005_regular | transit | linear | same_direction | 3 | 2 | 7/5 | transit/transit | 191.25271710000015 | True |
| family_s15_7b73a7fc210d4c8f_ext_006_regular | reconnaissance | linear | same_direction | 3 | 2 | 7/5 | reconnaissance/reconnaissance | 522.4442008000005 | True |
| family_s15_7b73a7fc210d4c8f_ext_007_regular | monitoring | linear | same_direction | 3 | 2 | 7/5 | monitoring/monitoring | 588.2956177999986 | True |
| family_s15_7b73a7fc210d4c8f_ext_008_regular | feint | linear | same_direction | 3 | 2 | 7/5 | feint/feint | 302.6414545000007 | True |
| family_s15_7b73a7fc210d4c8f_ext_009_regular | penetration | linear | same_direction | 3 | 2 | 7/5 | intrusion/feint | 206.53892570000244 | True |
| family_s15_8412c1cdb40e54b1_ext_000_regular | transit | isolated | same_direction | 2 | 1 | 11 | transit | 58.74538179999945 | True |
| family_s15_8412c1cdb40e54b1_ext_001_regular | reconnaissance | isolated | same_direction | 2 | 1 | 11 | reconnaissance | 442.4271927000009 | True |
| family_s15_8412c1cdb40e54b1_ext_002_regular | monitoring | isolated | same_direction | 2 | 1 | 11 | monitoring | 352.0754250000027 | True |
| family_s15_8412c1cdb40e54b1_ext_003_regular | feint | isolated | same_direction | 2 | 1 | 11 | feint | 73.9971863000028 | True |
| family_s15_8412c1cdb40e54b1_ext_004_regular | penetration | isolated | same_direction | 2 | 1 | 11 | intrusion | 11.050801800000045 | True |
| family_s15_8412c1cdb40e54b1_ext_005_regular | transit | isolated | same_direction | 2 | 1 | 11 | transit | 28.747270700001536 | True |
| family_s15_8412c1cdb40e54b1_ext_006_regular | reconnaissance | isolated | same_direction | 2 | 1 | 11 | reconnaissance | 30.374338599998737 | True |
| family_s15_8412c1cdb40e54b1_ext_007_regular | monitoring | isolated | same_direction | 2 | 1 | 11 | monitoring | 226.59497100000226 | True |
| family_s15_8412c1cdb40e54b1_ext_008_regular | feint | isolated | same_direction | 2 | 1 | 11 | feint | 57.911212899998645 | True |
| family_s15_8412c1cdb40e54b1_ext_009_regular | penetration | isolated | same_direction | 2 | 2 | 9/2 | feint/intrusion | 71.62625539999863 | True |
| family_s15_8e012bf033eb6821_ext_000_regular | transit | isolated | multi_direction | 3 | 2 | 5/3 | transit/transit | 211.39969360000032 | True |
| family_s15_8e012bf033eb6821_ext_001_regular | reconnaissance | isolated | multi_direction | 3 | 2 | 5/3 | reconnaissance/reconnaissance | 90.4314443000003 | True |
| family_s15_8e012bf033eb6821_ext_002_regular | monitoring | isolated | multi_direction | 3 | 2 | 5/3 | monitoring/monitoring | 268.44679929999984 | True |
| family_s15_8e012bf033eb6821_ext_003_regular | feint | isolated | multi_direction | 3 | 2 | 5/3 | feint/feint | 274.75838229999863 | True |
| family_s15_8e012bf033eb6821_ext_004_regular | penetration | isolated | multi_direction | 3 | 2 | 5/3 | intrusion/intrusion | 222.88948009999876 | True |
| family_s15_8e012bf033eb6821_ext_005_regular | transit | isolated | same_direction | 3 | 1 | 8 | transit | 74.78521810000166 | True |
| family_s15_8e012bf033eb6821_ext_006_regular | reconnaissance | isolated | same_direction | 3 | 1 | 8 | reconnaissance | 79.54039639999974 | True |
| family_s15_8e012bf033eb6821_ext_007_regular | monitoring | isolated | same_direction | 3 | 1 | 8 | monitoring | 264.91775589999816 | True |
| family_s15_8e012bf033eb6821_ext_008_regular | feint | isolated | same_direction | 3 | 1 | 8 | feint | 151.60138400000142 | True |
| family_s15_8e012bf033eb6821_ext_009_regular | penetration | isolated | same_direction | 3 | 2 | 4/4 | intrusion/feint | 198.99316650000037 | True |
| family_s15_aa4c66be8e85d64d_ext_000_regular | transit | single | multi_direction | 1 | 1 | 9 | transit | 51.38400100000217 | True |
| family_s15_aa4c66be8e85d64d_ext_001_regular | reconnaissance | single | multi_direction | 1 | 1 | 9 | reconnaissance | 65.23564029999761 | True |
| family_s15_aa4c66be8e85d64d_ext_002_regular | monitoring | single | multi_direction | 1 | 1 | 9 | monitoring | 301.67775040000197 | True |
| family_s15_aa4c66be8e85d64d_ext_003_regular | feint | single | multi_direction | 1 | 1 | 9 | feint | 99.71344930000123 | True |
| family_s15_aa4c66be8e85d64d_ext_004_regular | penetration | single | multi_direction | 1 | 1 | 9 | intrusion | 54.29308840000158 | True |
| family_s15_aa4c66be8e85d64d_ext_005_regular | transit | single | multi_direction | 1 | 1 | 9 | transit | 51.41974290000144 | True |
| family_s15_aa4c66be8e85d64d_ext_006_regular | reconnaissance | single | multi_direction | 1 | 1 | 9 | reconnaissance | 2080.894963400002 | True |
| family_s15_aa4c66be8e85d64d_ext_007_regular | monitoring | single | multi_direction | 1 | 1 | 9 | monitoring | 312.8679207000023 | True |
| family_s15_aa4c66be8e85d64d_ext_008_regular | feint | single | multi_direction | 1 | 1 | 9 | feint | 100.25631689999864 | True |
| family_s15_aa4c66be8e85d64d_ext_009_regular | penetration | single | multi_direction | 1 | 2 | 6/3 | intrusion/monitoring | 192.65412880000076 | True |
| family_s15_c713f51898e81011_ext_000_regular | transit | clustered | multi_direction | 3 | 1 | 10 | transit | 271.283981200002 | True |
| family_s15_c713f51898e81011_ext_001_regular | reconnaissance | clustered | multi_direction | 3 | 1 | 10 | reconnaissance | 240.04480719999992 | True |
| family_s15_c713f51898e81011_ext_002_regular | monitoring | clustered | multi_direction | 3 | 1 | 10 | monitoring | 497.069978800002 | True |
| family_s15_c713f51898e81011_ext_003_regular | feint | clustered | multi_direction | 3 | 1 | 10 | feint | 305.431953299998 | True |
| family_s15_c713f51898e81011_ext_004_regular | penetration | clustered | multi_direction | 3 | 1 | 10 | intrusion | 257.59142559999964 | True |
| family_s15_c713f51898e81011_ext_005_regular | transit | clustered | multi_direction | 3 | 1 | 10 | transit | 252.56722319999972 | True |
| family_s15_c713f51898e81011_ext_006_regular | reconnaissance | clustered | multi_direction | 3 | 1 | 10 | reconnaissance | 216.04252260000067 | True |
| family_s15_c713f51898e81011_ext_007_regular | monitoring | clustered | multi_direction | 3 | 1 | 10 | monitoring | 631.6687242000007 | True |
| family_s15_c713f51898e81011_ext_008_regular | feint | clustered | multi_direction | 3 | 1 | 10 | feint | 309.8421641999994 | True |
| family_s15_c713f51898e81011_ext_009_regular | penetration | clustered | multi_direction | 3 | 1 | 10 | intrusion | 198.8729353000017 | True |
| family_s15_cd16b042e6f088bd_ext_000_regular | transit | single | multi_direction | 1 | 1 | 9 | transit | 13.576929999999265 | True |
| family_s15_cd16b042e6f088bd_ext_001_regular | reconnaissance | single | multi_direction | 1 | 1 | 9 | reconnaissance | 6.867400899998756 | True |
| family_s15_cd16b042e6f088bd_ext_002_regular | monitoring | single | multi_direction | 1 | 1 | 9 | monitoring | 16.12812860000122 | True |
| family_s15_cd16b042e6f088bd_ext_003_regular | feint | single | multi_direction | 1 | 1 | 9 | feint | 31.892959699998755 | True |
| family_s15_cd16b042e6f088bd_ext_004_regular | penetration | single | multi_direction | 1 | 2 | 6/3 | intrusion/monitoring | 29.887861399998656 | True |
| family_s15_cd16b042e6f088bd_ext_005_regular | transit | single | same_direction | 1 | 1 | 9 | transit | 9.178187500001513 | True |
| family_s15_cd16b042e6f088bd_ext_006_regular | reconnaissance | single | same_direction | 1 | 1 | 9 | reconnaissance | 16.916714500002854 | True |
| family_s15_cd16b042e6f088bd_ext_007_regular | monitoring | single | same_direction | 1 | 1 | 9 | monitoring | 44.292307300001994 | True |
| family_s15_cd16b042e6f088bd_ext_008_regular | feint | single | same_direction | 1 | 1 | 9 | feint | 25.254914099998132 | True |
| family_s15_cd16b042e6f088bd_ext_009_regular | penetration | single | same_direction | 1 | 1 | 9 | intrusion | 2.340199099999154 | True |
| family_s15_ef1ed9ff0b0e7013_ext_000_regular | transit | linear | multi_direction | 2 | 1 | 7 | transit | 83.68382030000066 | True |
| family_s15_ef1ed9ff0b0e7013_ext_001_regular | reconnaissance | linear | multi_direction | 2 | 1 | 7 | reconnaissance | 10.053453100001207 | True |
| family_s15_ef1ed9ff0b0e7013_ext_002_regular | monitoring | linear | multi_direction | 2 | 1 | 7 | monitoring | 13.91899310000008 | True |
| family_s15_ef1ed9ff0b0e7013_ext_003_regular | feint | linear | multi_direction | 2 | 1 | 7 | feint | 153.0674528999989 | True |
| family_s15_ef1ed9ff0b0e7013_ext_004_regular | penetration | linear | multi_direction | 2 | 1 | 7 | intrusion | 107.66590770000039 | True |
| family_s15_ef1ed9ff0b0e7013_ext_005_regular | transit | linear | same_direction | 2 | 1 | 7 | transit | 96.99504909999814 | True |
| family_s15_ef1ed9ff0b0e7013_ext_006_regular | reconnaissance | linear | same_direction | 2 | 1 | 7 | reconnaissance | 98.50450219999766 | True |
| family_s15_ef1ed9ff0b0e7013_ext_007_regular | monitoring | linear | same_direction | 2 | 1 | 7 | monitoring | 339.5135435000011 | True |
| family_s15_ef1ed9ff0b0e7013_ext_008_regular | feint | linear | same_direction | 2 | 1 | 7 | feint | 129.55348690000028 | True |
| family_s15_ef1ed9ff0b0e7013_ext_009_regular | penetration | linear | same_direction | 2 | 1 | 7 | intrusion | 82.75395909999861 | True |
| family_s15_f2adfbfae12fbbad_ext_000_regular | transit | single | multi_direction | 1 | 1 | 9 | transit | 56.87685910000073 | True |
| family_s15_f2adfbfae12fbbad_ext_001_regular | reconnaissance | single | multi_direction | 1 | 1 | 9 | reconnaissance | 1743.5212756 | True |
| family_s15_f2adfbfae12fbbad_ext_002_regular | monitoring | single | multi_direction | 1 | 1 | 9 | monitoring | 404.1343428 | True |
| family_s15_f2adfbfae12fbbad_ext_003_regular | feint | single | multi_direction | 1 | 1 | 9 | feint | 92.04554659999849 | True |
| family_s15_f2adfbfae12fbbad_ext_004_regular | penetration | single | multi_direction | 1 | 1 | 9 | intrusion | 49.83653680000134 | True |
| family_s15_f2adfbfae12fbbad_ext_005_regular | transit | single | multi_direction | 1 | 1 | 9 | transit | 51.821254300000874 | True |
| family_s15_f2adfbfae12fbbad_ext_006_regular | reconnaissance | single | multi_direction | 1 | 1 | 9 | reconnaissance | 2991.325921799995 | True |
| family_s15_f2adfbfae12fbbad_ext_007_regular | monitoring | single | multi_direction | 1 | 1 | 9 | monitoring | 367.04349680000087 | True |
| family_s15_f2adfbfae12fbbad_ext_008_regular | feint | single | multi_direction | 1 | 1 | 9 | feint | 87.62104149999868 | True |
| family_s15_f2adfbfae12fbbad_ext_009_regular | penetration | single | multi_direction | 1 | 2 | 5/4 | intrusion/feint | 70.12212720000025 | True |
| family_s15_fac1d381571b4d36_ext_000_regular | transit | isolated | same_direction | 2 | 1 | 9 | transit | 45.00589399999808 | True |
| family_s15_fac1d381571b4d36_ext_001_regular | reconnaissance | isolated | same_direction | 2 | 1 | 9 | reconnaissance | 58.04872200000318 | True |
| family_s15_fac1d381571b4d36_ext_002_regular | monitoring | isolated | same_direction | 2 | 1 | 9 | monitoring | 214.21382639999865 | True |
| family_s15_fac1d381571b4d36_ext_003_regular | feint | isolated | same_direction | 2 | 1 | 9 | feint | 75.25355940000009 | True |
| family_s15_fac1d381571b4d36_ext_004_regular | penetration | isolated | same_direction | 2 | 1 | 9 | intrusion | 53.641842500001076 | True |
| family_s15_fac1d381571b4d36_ext_005_regular | transit | isolated | same_direction | 2 | 2 | 7/2 | transit/transit | 73.99890589999995 | True |
| family_s15_fac1d381571b4d36_ext_006_regular | reconnaissance | isolated | same_direction | 2 | 2 | 7/2 | reconnaissance/reconnaissance | 416.8825990000005 | True |
| family_s15_fac1d381571b4d36_ext_007_regular | monitoring | isolated | same_direction | 2 | 2 | 7/2 | monitoring/monitoring | 321.43664029999854 | True |
| family_s15_fac1d381571b4d36_ext_008_regular | feint | isolated | same_direction | 2 | 2 | 7/2 | feint/feint | 124.15797530000054 | True |
| family_s15_fac1d381571b4d36_ext_009_regular | penetration | isolated | same_direction | 2 | 3 | 5/2/2 | feint/intrusion/intrusion | 116.41252809999787 | True |
| family_s15_ffbbf066d62e3e2f_ext_000_regular | transit | linear | multi_direction | 3 | 1 | 6 | transit | 49.88448929999868 | True |
| family_s15_ffbbf066d62e3e2f_ext_001_regular | reconnaissance | linear | multi_direction | 3 | 1 | 6 | reconnaissance | 43.06147640000199 | True |
| family_s15_ffbbf066d62e3e2f_ext_002_regular | monitoring | linear | multi_direction | 3 | 1 | 6 | monitoring | 147.98133410000082 | True |
| family_s15_ffbbf066d62e3e2f_ext_003_regular | feint | linear | multi_direction | 3 | 1 | 6 | feint | 51.63353780000034 | True |
| family_s15_ffbbf066d62e3e2f_ext_004_regular | penetration | linear | multi_direction | 3 | 1 | 6 | intrusion | 34.038355499997124 | True |
| family_s15_ffbbf066d62e3e2f_ext_005_regular | transit | linear | same_direction | 3 | 1 | 6 | transit | 38.9714718000032 | True |
| family_s15_ffbbf066d62e3e2f_ext_006_regular | reconnaissance | linear | same_direction | 3 | 1 | 6 | reconnaissance | 250.50967769999988 | True |
| family_s15_ffbbf066d62e3e2f_ext_007_regular | monitoring | linear | same_direction | 3 | 1 | 6 | monitoring | 177.20231870000134 | True |
| family_s15_ffbbf066d62e3e2f_ext_008_regular | feint | linear | same_direction | 3 | 1 | 6 | feint | 62.30052110000179 | True |
| family_s15_ffbbf066d62e3e2f_ext_009_regular | penetration | linear | same_direction | 3 | 1 | 6 | intrusion | 26.714816199997585 | True |

## 附录 A：按公共抽签（family × slot）聚合

同一 `(family, slot)` 的 5 个意图共享同一次公共抽签，因此抽签才是独立单元；本附录不替换 T1–T6。成=成功，败=拒绝，待=在范围内但未测到，-=不在本次范围内。`未完成`（5 个意图都在范围内但未全部测到）与 `范围不全`（少于 5 个意图在范围内，只出现在限定范围的运行中）是第四、第五类，仍留在各分母内。

### A1 每个抽签一行

| family#slot | layout | facility_count | approach_mode | group_count | member_counts | transit | reconnaissance | monitoring | feint | penetration | 结果 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 6e6b8b6f70c6#slot0 | single | 1 | same_direction | 1 | 10 | 待 | 待 | 待 | 待 | 待 | 全失败 |
| 6e6b8b6f70c6#slot1 | single | 1 | multi_direction | 1 | 10 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| 7d4d7000043d#slot0 | clustered | 2 | multi_direction | 2 | 3/3 | 成 | 待 | 待 | 成 | 成 | 部分成功 |
| 7d4d7000043d#slot1 | clustered | 2 | same_direction | 1 | 6 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| dc9d791d547b#slot0 | clustered | 2 | same_direction | 1 | 7 | 成 | 成 | 成 | 成 | 待 | 部分成功 |
| dc9d791d547b#slot1 | clustered | 2 | same_direction | 1 | 7 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| cb2ccea653ae#slot0 | linear | 2 | multi_direction | 2 | 5/3 | 成 | 待 | 成 | 成 | 成 | 部分成功 |
| cb2ccea653ae#slot1 | linear | 2 | multi_direction | 2 | 4/4 | 成 | 待 | 成 | 成 | 成 | 部分成功 |
| 3b22d09e8a7a#slot0 | clustered | 3 | same_direction | 2 | 4/2 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| 3b22d09e8a7a#slot1 | clustered | 3 | same_direction | 1 | 6 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| c19b154f1faf#slot0 | isolated | 2 | same_direction | 1 | 9 | 成 | 成 | 成 | 成 | 待 | 部分成功 |
| c19b154f1faf#slot1 | isolated | 2 | same_direction | 2 | 5/4 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| a7fc210d4c8f#slot0 | linear | 3 | multi_direction | 1 | 12 | 成 | 待 | 成 | 成 | 成 | 部分成功 |
| a7fc210d4c8f#slot1 | linear | 3 | same_direction | 2 | 7/5 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| c1cdb40e54b1#slot0 | isolated | 2 | same_direction | 1 | 11 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| c1cdb40e54b1#slot1 | isolated | 2 | same_direction | 1 | 11 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| 2bf033eb6821#slot0 | isolated | 3 | multi_direction | 2 | 5/3 | 成 | 待 | 成 | 成 | 成 | 部分成功 |
| 2bf033eb6821#slot1 | isolated | 3 | same_direction | 1 | 8 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| 66be8e85d64d#slot0 | single | 1 | multi_direction | 1 | 9 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| 66be8e85d64d#slot1 | single | 1 | multi_direction | 1 | 9 | 成 | 待 | 成 | 成 | 成 | 部分成功 |
| f51898e81011#slot0 | clustered | 3 | multi_direction | 1 | 10 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| f51898e81011#slot1 | clustered | 3 | multi_direction | 1 | 10 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| b042e6f088bd#slot0 | single | 1 | multi_direction | 1 | 9 | 成 | 待 | 待 | 成 | 成 | 部分成功 |
| b042e6f088bd#slot1 | single | 1 | same_direction | 1 | 9 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| d9ff0b0e7013#slot0 | linear | 2 | multi_direction | 1 | 7 | 成 | 待 | 待 | 成 | 成 | 部分成功 |
| d9ff0b0e7013#slot1 | linear | 2 | same_direction | 1 | 7 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| fbfae12fbbad#slot0 | single | 1 | multi_direction | 1 | 9 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| fbfae12fbbad#slot1 | single | 1 | multi_direction | 1 | 9 | 成 | 待 | 成 | 成 | 成 | 部分成功 |
| d381571b4d36#slot0 | isolated | 2 | same_direction | 1 | 9 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| d381571b4d36#slot1 | isolated | 2 | same_direction | 2 | 7/2 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| f066d62e3e2f#slot0 | linear | 3 | multi_direction | 1 | 6 | 成 | 成 | 成 | 成 | 成 | 全成功 |
| f066d62e3e2f#slot1 | linear | 3 | same_direction | 1 | 6 | 成 | 成 | 成 | 成 | 成 | 全成功 |

### A2 按 layout / approach_mode 的三类抽签数量

| layout | 全成功 | 全失败 | 部分成功 | 未完成 | 范围不全 |
|---|---|---|---|---|---|
| clustered | 6 | 0 | 2 | 0 | 0 |
| isolated | 6 | 0 | 2 | 0 | 0 |
| linear | 4 | 0 | 4 | 0 | 0 |
| single | 4 | 1 | 3 | 0 | 0 |

| approach_mode | 全成功 | 全失败 | 部分成功 | 未完成 | 范围不全 |
|---|---|---|---|---|---|
| multi_direction | 6 | 0 | 9 | 0 | 0 |
| same_direction | 14 | 1 | 2 | 0 | 0 |

### A3 抽签口径产量（全成功抽签数 / 抽签总数）

| layout | 全成功抽签 | 抽签总数 | 其中已测完 | 全成功/全部抽签 | 全成功/已测完抽签 |
|---|---|---|---|---|---|
| single | 4 | 8 | 8 | 0.5000 | 0.5000 |
| isolated | 6 | 8 | 8 | 0.7500 | 0.7500 |
| clustered | 6 | 8 | 8 | 0.7500 | 0.7500 |
| linear | 4 | 8 | 8 | 0.5000 | 0.5000 |
| all | 20 | 32 | 32 | 0.6250 | 0.6250 |

### A4 部分成功抽签中失败的意图

| family#slot | layout | approach_mode | groups | members | 失败意图 | 终止拒绝原因 | 组层拒绝原因 | 组合层拒绝原因 | 4.3 归因签名 |
|---|---|---|---|---|---|---|---|---|---|
| 7d4d7000043d#slot0 | clustered | multi_direction | 2 | 3/3 | reconnaissance, monitoring | no_eligible_combination_in_registered_budgets | shape_search_budget_exhausted=200; shape_search_budget_exhausted=200; whole_route_check=2 |  | obstacle:between_facilities+target_facility+unattributed:shape_search_budget_exhausted; obstacle:between_facilities+unattributed:shape_search_budget_exhausted |
| dc9d791d547b#slot0 | clustered | same_direction | 1 | 7 | penetration | no_eligible_combination_in_registered_budgets | shape_search_budget_exhausted=200 |  | unattributed:shape_search_budget_exhausted |
| cb2ccea653ae#slot0 | linear | multi_direction | 2 | 5/3 | reconnaissance | no_eligible_combination_in_registered_budgets | shape_search_budget_exhausted=200 |  | target_facility |
| cb2ccea653ae#slot1 | linear | multi_direction | 2 | 4/4 | reconnaissance | no_eligible_combination_in_registered_budgets | shape_search_budget_exhausted=400 |  | target_facility |
| c19b154f1faf#slot0 | isolated | same_direction | 1 | 9 | penetration | no_eligible_combination_in_registered_budgets | shape_search_budget_exhausted=200 |  | unattributed:shape_search_budget_exhausted |
| a7fc210d4c8f#slot0 | linear | multi_direction | 1 | 12 | reconnaissance | no_eligible_combination_in_registered_budgets | shape_search_budget_exhausted=200 |  | obstacle:facility_side+target_facility |
| 2bf033eb6821#slot0 | isolated | multi_direction | 2 | 5/3 | reconnaissance | no_eligible_combination_in_registered_budgets | shape_search_budget_exhausted=200 |  | obstacle:facility_side+target_facility+unattributed:shape_search_budget_exhausted |
| 66be8e85d64d#slot1 | single | multi_direction | 1 | 9 | reconnaissance | no_eligible_combination_in_registered_budgets | shape_search_budget_exhausted=200 |  | obstacle:entry_blocking+obstacle:facility_side+target_facility |
| b042e6f088bd#slot0 | single | multi_direction | 1 | 9 | reconnaissance, monitoring | no_eligible_combination_in_registered_budgets | shape_search_budget_exhausted=200; shape_search_budget_exhausted=200 |  | obstacle:facility_side+target_facility+unattributed:shape_search_budget_exhausted; unattributed:shape_search_budget_exhausted |
| d9ff0b0e7013#slot0 | linear | multi_direction | 1 | 7 | reconnaissance, monitoring | no_eligible_combination_in_registered_budgets | shape_search_budget_exhausted=200; shape_search_budget_exhausted=200 |  | obstacle:entry_blocking+obstacle:facility_side+target_facility+unattributed:shape_search_budget_exhausted; unattributed:shape_search_budget_exhausted |
| fbfae12fbbad#slot1 | single | multi_direction | 1 | 9 | reconnaissance | no_eligible_combination_in_registered_budgets | shape_search_budget_exhausted=200 |  | obstacle:facility_side+target_facility |

### A5 全失败抽签（用户口径只要求部分成功抽签；全失败抽签仅 1 个，一并列出以免不可读）

| family#slot | layout | approach_mode | groups | members | 失败意图 | 终止拒绝原因 | 组层拒绝原因 | 组合层拒绝原因 | 4.3 归因签名 |
|---|---|---|---|---|---|---|---|---|---|
| 6e6b8b6f70c6#slot0 | single | same_direction | 1 | 10 | transit, reconnaissance, monitoring, feint, penetration | no_eligible_combination_in_registered_budgets | connection_search_budget_exhausted=200; connection_search_budget_exhausted=200; connection_search_budget_exhausted=200; connection_search_budget_exhausted=200; shape_search_budget_exhausted=200 |  | unattributed:connection_search_budget_exhausted; unattributed:shape_search_budget_exhausted |

## 异常记录（逐条见 summary JSON 的 anomalies）

| kind | count |
|---|---|
| single_point_work_set | 225 |

- 作业段扫描覆盖成员 912 名，其中 work_points_enu_m 缺失 0 名；单点作业段 225 名，其中该点落在非目标预警区内 0 名（单点集合按登记的交集长度 > 1e-6 m 口径判为未进入，仅记录此诊断）。
