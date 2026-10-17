# FE-P2 area_search 拒绝阶段诊断

状态：GATE_NOT_MET。

统计单位独立：提案执行记录、被拒形态尝试、带 phase 的证据条目。单个提案可包含多个尝试及多条 slot/segment 证据；proposal_reason_hits 与 proposals_with_evidence 均在每个提案内去重。
目标归因使用 entity_id == target_id 或 entity_id.startswith(target_id + "_")；同时核验场景实体登记及 facility_id，不匹配时停止。
all_recorded_attempts 遍历两个历史 attempt 的所有日志；completed_owner 只取每个完成骨架所属 attempt，与原汇总口径一致。不同 attempt 中重复执行的同一提案不冒充独立提案身份。

跨 attempt 重复提案身份 515 个，额外执行记录 515 条。

## all_recorded_attempts

| 单位/指标 | multi_direction | same_direction |
|---|---|---|
| proposals | 2915 | 2400 |
| accepted_proposals | 365 | 1951 |
| rejected_proposals | 2550 | 449 |
| shape_attempt_rejections | 50941 | 3447 |
| evidence_entries | 57444 | 91 |

### 表 1：形态尝试拒绝原因（单位：形态尝试）

| reason | multi_direction | same_direction |
|---|---|---|
| ingress_line_blocked | 14334 | 17 |
| nominal_coverage_shortfall | 2 | 0 |
| sub_metre_semantic_join | 68 | 1 |
| survey_area_unavailable | 31596 | 2702 |
| survey_insufficient_strips | 1329 | 511 |
| survey_strip_unavailable | 194 | 11 |
| work_segment_clearance | 3418 | 205 |

### 表 2：phase × kind × 目标归因（单位：证据条目）

| phase | kind | is_target | multi_direction | same_direction |
|---|---|---|---|---|
| entry_to_work_start | forbidden_layer | True | 46587 | 0 |
| entry_to_work_start | obstacle | False | 5555 | 2 |
| ingress_line_outside_entry | obstacle | False | 5302 | 89 |

### 含上述证据的提案数（同一提案内去重）

| phase | kind | is_target | multi_direction | same_direction |
|---|---|---|---|---|
| entry_to_work_start | forbidden_layer | True | 2348 | 0 |
| entry_to_work_start | obstacle | False | 878 | 2 |
| ingress_line_outside_entry | obstacle | False | 860 | 15 |

门槛：{"ingress_shape_attempts": 14334, "all_rejected_shape_attempts": 50941, "ingress_fraction": 0.28138434659704364, "entry_to_work_target_evidence": 46587, "all_target_phase_evidence": 46587, "entry_target_fraction": 1.0, "pass": false}

## completed_owner

| 单位/指标 | multi_direction | same_direction |
|---|---|---|
| proposals | 2400 | 2400 |
| accepted_proposals | 365 | 1951 |
| rejected_proposals | 2035 | 449 |
| shape_attempt_rejections | 40641 | 3447 |
| evidence_entries | 42115 | 91 |

### 表 1：形态尝试拒绝原因（单位：形态尝试）

| reason | multi_direction | same_direction |
|---|---|---|
| ingress_line_blocked | 10416 | 17 |
| nominal_coverage_shortfall | 2 | 0 |
| sub_metre_semantic_join | 55 | 1 |
| survey_area_unavailable | 26168 | 2702 |
| survey_insufficient_strips | 993 | 511 |
| survey_strip_unavailable | 147 | 11 |
| work_segment_clearance | 2860 | 205 |

### 表 2：phase × kind × 目标归因（单位：证据条目）

| phase | kind | is_target | multi_direction | same_direction |
|---|---|---|---|---|
| entry_to_work_start | forbidden_layer | True | 32594 | 0 |
| entry_to_work_start | obstacle | False | 4923 | 2 |
| ingress_line_outside_entry | obstacle | False | 4598 | 89 |

### 含上述证据的提案数（同一提案内去重）

| phase | kind | is_target | multi_direction | same_direction |
|---|---|---|---|---|
| entry_to_work_start | forbidden_layer | True | 1833 | 0 |
| entry_to_work_start | obstacle | False | 774 | 2 |
| ingress_line_outside_entry | obstacle | False | 758 | 15 |

门槛：{"ingress_shape_attempts": 10416, "all_rejected_shape_attempts": 40641, "ingress_fraction": 0.2562929061784897, "entry_to_work_target_evidence": 32594, "all_target_phase_evidence": 32594, "entry_target_fraction": 1.0, "pass": false}

