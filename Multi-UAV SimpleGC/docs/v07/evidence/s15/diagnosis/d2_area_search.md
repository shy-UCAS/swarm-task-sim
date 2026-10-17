# D2 多向区域搜索（role=reconnaissance, execution_method=area_search）

数据源：
- `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261016T154921Z`
- `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261016T163901Z`
- 描述目录：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15desc_20261016T154909Z`

## 提案接受率与 reason/归因计数

| 指标 | multi_direction | same_direction |
|---|---|---|
| 接受/提案 | 365/2400 | 1951/2400 |

### approach_mode = multi_direction

- 提案 2400 条，接受 365 条，接受率 0.1521

reason 字面值计数：

| reason | count |
|---|---|
| connection_search_budget_exhausted | 4 |
| shape_search_budget_exhausted | 2031 |

归因类别计数（多标签，复用 summarize_v07_s15_yield.py 的 collect_entities/classify）：

| 类别 | count |
|---|---|
| obstacle:between_facilities | 124 |
| obstacle:entry_blocking | 234 |
| obstacle:facility_side | 1017 |
| target_facility | 1836 |
| unattributed:connection_search_budget_exhausted | 4 |
| unattributed:shape_search_budget_exhausted | 90 |

### target_facility 归因的提案（1836 条）

出现最多的前 20 条键路径：

| 键路径 | count |
|---|---|
| geometric_evidence[].evidence[].slot | 76649 |
| geometric_evidence[].evidence[].code | 76649 |
| geometric_evidence[].evidence[].entity_id | 76649 |
| geometric_evidence[].evidence[].clearance_m | 76649 |
| geometric_evidence[].evidence[].required_m | 76649 |
| geometric_evidence[].evidence[].kind | 76649 |
| geometric_evidence[].evidence[].phase | 42078 |
| geometric_evidence[].evidence[].start_m | 42078 |
| geometric_evidence[].evidence[].end_m | 42078 |
| geometric_evidence[].draw | 36720 |
| geometric_evidence[].draw.direction_deg | 36720 |
| geometric_evidence[].draw.shape_attempt | 36720 |
| geometric_evidence[].draw.span_deg | 36720 |
| geometric_evidence[].draw.area_m2 | 36720 |
| geometric_evidence[].draw.overlap | 36720 |
| geometric_evidence[].reason | 36720 |
| geometric_evidence[].evidence | 36720 |
| geometric_evidence[].evidence[].segment | 34571 |
| geometric_evidence[].evidence[].direction_deg | 22442 |
| geometric_evidence[].evidence[].shape_attempt | 22442 |

侵入的目标圈层（按实体 ID 后缀）：

| 圈层 | count |
|---|---|
| alert | 1282 |

- `clearances_m` 数值分布：{"count": 76649, "min": -423.894813, "p50": 0.0, "max": 34.996577}
- `required_m` 数值分布：{"count": 76649, "min": 10.0, "p50": 35.0, "max": 35.0}

### approach_mode = same_direction

- 提案 2400 条，接受 1951 条，接受率 0.8129

reason 字面值计数：

| reason | count |
|---|---|
| connection_search_budget_exhausted | 284 |
| shape_search_budget_exhausted | 131 |
| whole_route_check | 34 |

归因类别计数（多标签，复用 summarize_v07_s15_yield.py 的 collect_entities/classify）：

| 类别 | count |
|---|---|
| obstacle:between_facilities | 24 |
| obstacle:facility_side | 30 |
| target_facility | 1 |
| unattributed:connection_search_budget_exhausted | 284 |
| unattributed:shape_search_budget_exhausted | 77 |
| unattributed:whole_route_check | 34 |

### target_facility 归因的提案（1 条）

出现最多的前 20 条键路径：

| 键路径 | count |
|---|---|
| geometric_evidence[].draw | 20 |
| geometric_evidence[].draw.direction_deg | 20 |
| geometric_evidence[].draw.shape_attempt | 20 |
| geometric_evidence[].draw.span_deg | 20 |
| geometric_evidence[].draw.area_m2 | 20 |
| geometric_evidence[].draw.overlap | 20 |
| geometric_evidence[].reason | 20 |
| geometric_evidence[].evidence | 20 |
| geometric_evidence[].evidence[].direction_deg | 18 |
| geometric_evidence[].evidence[].shape_attempt | 18 |
| geometric_evidence[].evidence[].span_deg | 18 |
| geometric_evidence[].evidence[].area_m2 | 18 |
| geometric_evidence[].evidence[].overlap | 18 |
| geometric_evidence[].evidence[].slot | 8 |
| geometric_evidence[].evidence[].segment | 8 |
| geometric_evidence[].evidence[].code | 8 |
| geometric_evidence[].evidence[].entity_id | 8 |
| geometric_evidence[].evidence[].clearance_m | 8 |
| geometric_evidence[].evidence[].required_m | 8 |
| geometric_evidence[].evidence[].kind | 8 |

侵入的目标圈层（按实体 ID 后缀）：

| 圈层 | count |
|---|---|
| alert | 1 |

- `clearances_m` 数值分布：{"count": 8, "min": 0.0, "p50": 7.353325, "max": 33.598773}
- `required_m` 数值分布：{"count": 8, "min": 10.0, "p50": 35.0, "max": 35.0}

> 本节只记录分布与圈层归属，不推测原因。area_search 的证据条目实际是标量 `clearance_m` + `required_m`；另有 `clearances_m` 字典形式出现在别处，两种形态都收集。任务书写作 clearance_m，与实际字段一致。
