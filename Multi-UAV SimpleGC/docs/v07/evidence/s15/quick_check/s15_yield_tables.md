# S1.5 阶段 2 纯规划产额统计表

- 描述目录：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15desc_20261016T153508Z`
- 规划目录（1 个 attempt，每个 skeleton_id 只来自其中一个）：
  - `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261016T153520Z`：状态 `TIME_LIMIT_STOP`，选中 16，落盘完成 15，墙钟 600.1 s
- 注册骨架 240 个；本次统计范围（各 attempt 声明并集）16 个，其中有 `planning_result.json` 的 15 个（成功 13）；未完成 **1** 个；注册但不在本次范围内的 224 个
- 组提案 3800 条，接受 2918 条；被拒 882 条，无法按 4.3 解析 0 条（0.0000%）
- 1 设施地图（T5 记 `not_applicable`）：0 个骨架
- 骨架级表格（T1、T2a、T2b、T5、T6）的分母一律包含未完成骨架，并在末列单列 `未完成` 数量；T3、T4 的分母是组提案，未完成骨架不产生提案，故不在其分母内。

## 未完成骨架计数：意图 × 布局

| intent | single | isolated | clustered | linear |
|---|---|---|---|---|
| transit | 0 | 0 | 0 | 0 |
| reconnaissance | 0 | 0 | 0 | 0 |
| monitoring | 0 | 1 | 0 | 0 |
| feint | 0 | 0 | 0 | 0 |
| penetration | 0 | 0 | 0 | 0 |

## T1 骨架成功率：意图 × 布局

| intent | single | isolated | clustered | linear | 未完成 |
|---|---|---|---|---|---|
| transit | 0/0 | 2/2 (100.00%) | 2/2 (100.00%) | 0/0 | 0 |
| reconnaissance | 0/0 | 1/1 (100.00%) | 2/2 (100.00%) | 0/0 | 0 |
| monitoring | 0/0 | 0/1 (0.00%) | 1/2 (50.00%) | 0/0 | 1 |
| feint | 0/0 | 1/1 (100.00%) | 2/2 (100.00%) | 0/0 | 0 |
| penetration | 0/0 | 1/1 (100.00%) | 1/2 (50.00%) | 0/0 | 0 |
| 各布局内五意图成功率最大值/最小值之比 | n/a | inf | 2.0000 | n/a |  |

## T2a 骨架成功率：意图 × 接近方式

| intent | multi_direction | same_direction | 未完成 |
|---|---|---|---|
| transit | 3/3 (100.00%) | 1/1 (100.00%) | 0 |
| reconnaissance | 2/2 (100.00%) | 1/1 (100.00%) | 0 |
| monitoring | 0/2 (0.00%) | 1/1 (100.00%) | 1 |
| feint | 2/2 (100.00%) | 1/1 (100.00%) | 0 |
| penetration | 2/2 (100.00%) | 0/1 (0.00%) | 0 |

## T2b 骨架成功率：意图 × 设施数

| intent | 2 | 未完成 |
|---|---|---|
| transit | 4/4 (100.00%) | 0 |
| reconnaissance | 3/3 (100.00%) | 0 |
| monitoring | 1/3 (33.33%) | 1 |
| feint | 3/3 (100.00%) | 0 |
| penetration | 2/3 (66.67%) | 0 |

## T3 组提案接受率

分母为组提案数；1 个未完成骨架没有 `proposals.jsonl`，不产生提案。

### T3a：role/execution_method × 布局

| role/execution_method | single | isolated | clustered | linear |
|---|---|---|---|---|
| feint/feint | 0/0 | 599/600 (99.83%) | 383/400 (95.75%) | 0/0 |
| intrusion/intrusion | 0/0 | 199/200 (99.50%) | 183/400 (45.75%) | 0/0 |
| monitoring/monitoring | 0/0 | 0/0 | 136/400 (34.00%) | 0/0 |
| reconnaissance/close_observation | 0/0 | 398/400 (99.50%) | 369/400 (92.25%) | 0/0 |
| transit/transit | 0/0 | 428/600 (71.33%) | 223/400 (55.75%) | 0/0 |

### T3b：role/execution_method × 成员数分桶

| role/execution_method | 2–3 | 4–5 | ≥6 | <2 |
|---|---|---|---|---|
| feint/feint | 0/0 | 599/600 (99.83%) | 383/400 (95.75%) | 0/0 |
| intrusion/intrusion | 0/0 | 199/200 (99.50%) | 183/400 (45.75%) | 0/0 |
| monitoring/monitoring | 0/0 | 0/0 | 136/400 (34.00%) | 0/0 |
| reconnaissance/close_observation | 0/0 | 398/400 (99.50%) | 369/400 (92.25%) | 0/0 |
| transit/transit | 0/0 | 292/400 (73.00%) | 359/600 (59.83%) | 0/0 |

## T4 被拒提案归因（多标签计数）

分母为被拒提案数；1 个未完成骨架不产生提案。

### T4a：role/execution_method × 类别

| role/execution_method | obstacle:facility_side | unattributed:connection_search_budget_exhausted | unattributed:shape_search_budget_exhausted | unattributed:whole_route_check | total |
|---|---|---|---|---|---|
| feint/feint | 0 | 14 | 0 | 4 | 18 |
| intrusion/intrusion | 0 | 17 | 200 | 1 | 218 |
| monitoring/monitoring | 200 | 3 | 0 | 61 | 264 |
| reconnaissance/close_observation | 0 | 21 | 0 | 12 | 33 |
| transit/transit | 1 | 241 | 0 | 107 | 349 |

### T4b：layout × 类别

| layout | obstacle:facility_side | unattributed:connection_search_budget_exhausted | unattributed:shape_search_budget_exhausted | unattributed:whole_route_check | total |
|---|---|---|---|---|---|
| single | 0 | 0 | 0 | 0 | 0 |
| isolated | 1 | 136 | 0 | 39 | 176 |
| clustered | 200 | 160 | 200 | 146 | 706 |
| linear | 0 | 0 | 0 | 0 | 0 |

### T4c：互斥签名前 15 名（类别集合排序后以 + 连接）

| signature | count |
|---|---|
| unattributed:connection_search_budget_exhausted | 296 |
| obstacle:facility_side | 201 |
| unattributed:shape_search_budget_exhausted | 200 |
| unattributed:whole_route_check | 185 |

## T5 作业段进入非目标预警区：意图 × 布局（仅多设施布局）

| intent | single | isolated | clustered | linear | 未完成 |
|---|---|---|---|---|---|
| transit | n/a | 0/2 | 0/2 | n/a | 0 |
| reconnaissance | n/a | 0/1 | 0/2 | n/a | 0 |
| monitoring | n/a | 0/0 | 0/1 [not_counted 1] | n/a | 1 |
| feint | n/a | 0/1 | 0/2 | n/a | 0 |
| penetration | n/a | 0/1 | 0/1 [not_counted 1] | n/a | 0 |

分母为有 `selected_skeleton.json` 且可测的骨架数（第 4.4 条只统计有该文件的骨架）；`not_applicable` 为单设施地图；`[not_counted n]` 为无 `selected_skeleton.json` 因而按第 4.4 条不统计的骨架数；`[not_available n]` 为找不到 `references` 或 `work_points_enu_m` 的骨架数；`未完成` 列为该意图下未完成的多设施骨架数。

## T6 每骨架规划墙钟（s）：按意图

| intent | count | min | p50 | p90 | max | 未完成 |
|---|---|---|---|---|---|---|
| transit | 4 | 78.637958 | 132.619025 | 216.270511 | 248.587015 | 0 |
| reconnaissance | 3 | 120.480609 | 137.862578 | 207.178188 | 224.50709 | 0 |
| monitoring | 2 | 277.945159 | 372.465163 | 448.081166 | 466.985167 | 1 |
| feint | 3 | 148.583332 | 182.192357 | 268.567988 | 290.161896 | 0 |
| penetration | 3 | 0.561214 | 117.888589 | 161.496636 | 172.398648 | 0 |
| all | 15 | 0.561214 | 148.583332 | 285.275201 | 466.985167 | 1 |

分布只统计有 `planning_result.json` 的骨架；未完成骨架的墙钟是中止时的快照，不进入分布，其数量单列在 `未完成` 列，并在 summary JSON 的 `t6_all_registered` 中另附。

## T6b 每骨架规划耗时与组构成（意图 / 组数 / 各组成员数）

| skeleton_id | intent | layout | approach_mode | facility_count | group_count | member_counts | roles | planning_wall_s | completed |
|---|---|---|---|---|---|---|---|---|---|
| family_s15_0aeede8b1f29217e_ext_000_regular | transit | clustered | same_direction | 2 | 1 | 11 | transit | 140.8653357999974 | True |
| family_s15_0aeede8b1f29217e_ext_001_regular | reconnaissance | clustered | same_direction | 2 | 1 | 11 | reconnaissance | 137.86257799999657 | True |
| family_s15_0aeede8b1f29217e_ext_002_regular | monitoring | clustered | same_direction | 2 | 1 | 11 | monitoring | 466.985166800001 | True |
| family_s15_0aeede8b1f29217e_ext_003_regular | feint | clustered | same_direction | 2 | 1 | 11 | feint | 182.19235720000142 | True |
| family_s15_0aeede8b1f29217e_ext_004_regular | penetration | clustered | same_direction | 2 | 1 | 11 | intrusion | 0.5612136999989161 | True |
| family_s15_0aeede8b1f29217e_ext_005_regular | transit | clustered | multi_direction | 2 | 1 | 11 | transit | 248.58701470000233 | True |
| family_s15_0aeede8b1f29217e_ext_006_regular | reconnaissance | clustered | multi_direction | 2 | 1 | 11 | reconnaissance | 224.50708999999915 | True |
| family_s15_0aeede8b1f29217e_ext_007_regular | monitoring | clustered | multi_direction | 2 | 1 | 11 | monitoring | 277.94515890000184 | True |
| family_s15_0aeede8b1f29217e_ext_008_regular | feint | clustered | multi_direction | 2 | 1 | 11 | feint | 290.1618955999984 | True |
| family_s15_0aeede8b1f29217e_ext_009_regular | penetration | clustered | multi_direction | 2 | 1 | 11 | intrusion | 172.39864809999926 | True |
| family_s15_19d00d7e8a2f9e99_ext_000_regular | transit | isolated | multi_direction | 2 | 2 | 4/5 | transit/transit | 124.37271519999922 | True |
| family_s15_19d00d7e8a2f9e99_ext_001_regular | reconnaissance | isolated | multi_direction | 2 | 2 | 4/5 | reconnaissance/reconnaissance | 120.48060869999972 | True |
| family_s15_19d00d7e8a2f9e99_ext_002_regular | monitoring | isolated | multi_direction | 2 | 2 | 4/5 | monitoring/monitoring | 372.6100993 | False |
| family_s15_19d00d7e8a2f9e99_ext_003_regular | feint | isolated | multi_direction | 2 | 2 | 4/5 | feint/feint | 148.58333180000045 | True |
| family_s15_19d00d7e8a2f9e99_ext_004_regular | penetration | isolated | multi_direction | 2 | 2 | 4/5 | feint/intrusion | 117.88858940000136 | True |
| family_s15_19d00d7e8a2f9e99_ext_005_regular | transit | isolated | multi_direction | 2 | 1 | 9 | transit | 78.63795839999875 | True |

## 附录 A：按公共抽签（family × slot）聚合

同一 `(family, slot)` 的 5 个意图共享同一次公共抽签，因此抽签才是独立单元；本附录不替换 T1–T6。成=成功，败=拒绝，待=在范围内但未测到，-=不在本次范围内。`未完成`（5 个意图都在范围内但未全部测到）与 `范围不全`（少于 5 个意图在范围内，只出现在限定范围的运行中）是第四、第五类，仍留在各分母内。

### A1 每个抽签一行

| family#slot | layout | facility_count | approach_mode | group_count | member_counts | transit | reconnaissance | monitoring | feint | penetration | 结果 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| de8b1f29217e#slot0 | clustered | 2 | same_direction | 1 | 11 | 成 | 成 | 成 | 成 | 待 | 部分成功 |
| de8b1f29217e#slot1 | clustered | 2 | multi_direction | 1 | 11 | 成 | 成 | 待 | 成 | 成 | 部分成功 |
| 0d7e8a2f9e99#slot0 | isolated | 2 | multi_direction | 2 | 4/5 | 成 | 成 | 待 | 成 | 成 | 未完成 |
| 0d7e8a2f9e99#slot1 | isolated | 2 | multi_direction | 1 | 9 | 成 | - | - | - | - | 范围不全 |

### A2 按 layout / approach_mode 的三类抽签数量

| layout | 全成功 | 全失败 | 部分成功 | 未完成 | 范围不全 |
|---|---|---|---|---|---|
| clustered | 0 | 0 | 2 | 0 | 0 |
| isolated | 0 | 0 | 0 | 1 | 1 |

| approach_mode | 全成功 | 全失败 | 部分成功 | 未完成 | 范围不全 |
|---|---|---|---|---|---|
| multi_direction | 0 | 0 | 1 | 1 | 1 |
| same_direction | 0 | 0 | 1 | 0 | 0 |

### A3 抽签口径产量（全成功抽签数 / 抽签总数）

| layout | 全成功抽签 | 抽签总数 | 其中已测完 | 全成功/全部抽签 | 全成功/已测完抽签 |
|---|---|---|---|---|---|
| isolated | 0 | 2 | 0 | 0.0000 | n/a |
| clustered | 0 | 2 | 2 | 0.0000 | 0.0000 |
| all | 0 | 4 | 2 | 0.0000 | 0.0000 |

### A4 部分成功抽签中失败的意图

| family#slot | layout | approach_mode | groups | members | 失败意图 | 终止拒绝原因 | 组层拒绝原因 | 组合层拒绝原因 | 4.3 归因签名 |
|---|---|---|---|---|---|---|---|---|---|
| de8b1f29217e#slot0 | clustered | same_direction | 1 | 11 | penetration | no_eligible_combination_in_registered_budgets | shape_search_budget_exhausted=200 |  | unattributed:shape_search_budget_exhausted |
| de8b1f29217e#slot1 | clustered | multi_direction | 1 | 11 | monitoring | no_eligible_combination_in_registered_budgets | shape_search_budget_exhausted=200 |  | obstacle:facility_side |

### A5 全失败抽签（用户口径只要求部分成功抽签；全失败抽签仅 1 个，一并列出以免不可读）

| family#slot | layout | approach_mode | groups | members | 失败意图 | 终止拒绝原因 | 组层拒绝原因 | 组合层拒绝原因 | 4.3 归因签名 |
|---|---|---|---|---|---|---|---|---|---|

## 异常记录（逐条见 summary JSON 的 anomalies）

| kind | count |
|---|---|
| single_point_work_set | 47 |

- 作业段扫描覆盖成员 133 名，其中 work_points_enu_m 缺失 0 名；单点作业段 47 名，其中该点落在非目标预警区内 0 名（单点集合按登记的交集长度 > 1e-6 m 口径判为未进入，仅记录此诊断）。
