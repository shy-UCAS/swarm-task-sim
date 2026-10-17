# FE-P2 同输入 A/B 纯规划对照

结论：P2_PLANNING_GAIN_CONFIRMED

A/B 固定同一 32 骨架及描述符。每个骨架只取一份完整结果；未完成与缺失单列。混合方法骨架同时进入各方法分层，不能把方法分母相加。主意图始终为 reconnaissance。
本报告只涉及规划，不推算五意图齐全率，也不代表 M2/fastsim/M1 端到端通过。

## 表 A：组提案接受率

| approach/method | A 完成骨架 | A 接受/提案 | B 完成骨架 | B 接受/提案 | 变化 pp |
|---|---|---|---|---|---|
| multi_direction/area_search | 11 | 104/2400 | 11 | 1222/2400 | 46.58333333333333 |
| multi_direction/close_observation | 7 | 1383/1400 | 7 | 1383/1400 | 0.0 |
| same_direction/area_search | 10 | 1532/2400 | 10 | 1532/2400 | 0.0 |
| same_direction/close_observation | 9 | 1715/1800 | 9 | 1715/1800 | 0.0 |

同一方法分层的完成骨架集合不同时，不直接计算全体接受率差。可配对骨架 ID 与配对后的接受率另存 JSON 的 table_A_paired；完整批次时两种口径一致。

## 表 B：拒绝阶段与统计单位

终局原因每提案只计一次；proposal_reason_hits 对各嵌套原因在每个提案内去重，属于可重叠标签。形态尝试统计含最终成功提案中此前失败的尝试，并另存仅被拒提案子集，不能与终局计数相加。连接尝试与 phase 证据均单列。

### multi_direction/area_search

final_reasons

| reason/phase | A | B |
|---|---|---|
| connection_search_budget_exhausted | 4 | 83 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 0 | 0 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 0 | 0 |
| shape_search_budget_exhausted | 2031 | 338 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 261 | 757 |
| work_segment_clearance | 0 | 0 |

proposal_reason_hits

| reason/phase | A | B |
|---|---|---|
| alignment_consumed_by_lane_turn | 4 | 63 |
| connection_search_budget_exhausted | 4 | 83 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 2060 | 460 |
| inner_alignment_blocked | 3 | 0 |
| lane_swallowtail | 1 | 1 |
| no_exterior_connection | 1 | 2 |
| no_interior_connection | 0 | 81 |
| nominal_coverage_shortfall | 2 | 0 |
| shape_search_budget_exhausted | 2031 | 338 |
| sub_metre_semantic_join | 57 | 14 |
| survey_area_unavailable | 2251 | 1656 |
| survey_insufficient_strips | 607 | 224 |
| survey_strip_unavailable | 156 | 35 |
| whole_route_check | 261 | 757 |
| work_segment_clearance | 1269 | 688 |

shape_attempt_reasons

| reason/phase | A | B |
|---|---|---|
| connection_search_budget_exhausted | 0 | 0 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 11012 | 629 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 0 | 0 |
| nominal_coverage_shortfall | 2 | 0 |
| shape_search_budget_exhausted | 0 | 0 |
| sub_metre_semantic_join | 58 | 14 |
| survey_area_unavailable | 26851 | 12341 |
| survey_insufficient_strips | 1176 | 298 |
| survey_strip_unavailable | 161 | 35 |
| whole_route_check | 0 | 0 |
| work_segment_clearance | 3207 | 1083 |

rejected_proposal_shape_reasons

| reason/phase | A | B |
|---|---|---|
| connection_search_budget_exhausted | 0 | 0 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 10876 | 454 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 0 | 0 |
| nominal_coverage_shortfall | 2 | 0 |
| shape_search_budget_exhausted | 0 | 0 |
| sub_metre_semantic_join | 57 | 7 |
| survey_area_unavailable | 26683 | 8468 |
| survey_insufficient_strips | 1107 | 183 |
| survey_strip_unavailable | 159 | 18 |
| whole_route_check | 0 | 0 |
| work_segment_clearance | 3117 | 776 |

connection_attempt_reasons

| reason/phase | A | B |
|---|---|---|
| alignment_consumed_by_lane_turn | 15 | 242 |
| connection_search_budget_exhausted | 0 | 0 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 0 | 0 |
| inner_alignment_blocked | 20 | 0 |
| lane_swallowtail | 2 | 2 |
| no_exterior_connection | 3 | 8 |
| no_interior_connection | 0 | 578 |
| shape_search_budget_exhausted | 0 | 0 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 0 | 0 |
| work_segment_clearance | 0 | 0 |

phase_evidence_entries

| reason/phase | A | B |
|---|---|---|
| entry_alignment_inner | 0 | 1622 |
| entry_to_work_start | 38951 | 0 |
| ingress_line_outside_entry | 5307 | 1699 |

proposal_phase_hits

| reason/phase | A | B |
|---|---|---|
| entry_alignment_inner | 0 | 428 |
| entry_to_work_start | 2055 | 0 |
| ingress_line_outside_entry | 901 | 442 |

### multi_direction/close_observation

final_reasons

| reason/phase | A | B |
|---|---|---|
| connection_search_budget_exhausted | 8 | 8 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 0 | 0 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 0 | 0 |
| shape_search_budget_exhausted | 0 | 0 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 9 | 9 |
| work_segment_clearance | 0 | 0 |

proposal_reason_hits

| reason/phase | A | B |
|---|---|---|
| alignment_consumed_by_lane_turn | 8 | 8 |
| connection_search_budget_exhausted | 8 | 8 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 246 | 246 |
| inner_alignment_blocked | 0 | 0 |
| no_exterior_connection | 7 | 7 |
| no_interior_connection | 0 | 0 |
| observation_station_blocked | 3 | 3 |
| shape_search_budget_exhausted | 0 | 0 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 9 | 9 |
| work_segment_clearance | 0 | 0 |

shape_attempt_reasons

| reason/phase | A | B |
|---|---|---|
| connection_search_budget_exhausted | 0 | 0 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 340 | 340 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 0 | 0 |
| observation_station_blocked | 3 | 3 |
| shape_search_budget_exhausted | 0 | 0 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 0 | 0 |
| work_segment_clearance | 0 | 0 |

rejected_proposal_shape_reasons

| reason/phase | A | B |
|---|---|---|
| connection_search_budget_exhausted | 0 | 0 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 5 | 5 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 0 | 0 |
| shape_search_budget_exhausted | 0 | 0 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 0 | 0 |
| work_segment_clearance | 0 | 0 |

connection_attempt_reasons

| reason/phase | A | B |
|---|---|---|
| alignment_consumed_by_lane_turn | 46 | 46 |
| connection_search_budget_exhausted | 0 | 0 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 0 | 0 |
| inner_alignment_blocked | 0 | 0 |
| no_exterior_connection | 34 | 34 |
| no_interior_connection | 0 | 0 |
| shape_search_budget_exhausted | 0 | 0 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 0 | 0 |
| work_segment_clearance | 0 | 0 |

phase_evidence_entries

| reason/phase | A | B |
|---|---|---|
| entry_to_work_start | 867 | 867 |
| ingress_line_outside_entry | 957 | 957 |

proposal_phase_hits

| reason/phase | A | B |
|---|---|---|
| entry_to_work_start | 228 | 228 |
| ingress_line_outside_entry | 244 | 244 |

### same_direction/area_search

final_reasons

| reason/phase | A | B |
|---|---|---|
| connection_search_budget_exhausted | 284 | 286 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 0 | 0 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 0 | 0 |
| shape_search_budget_exhausted | 131 | 129 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 453 | 453 |
| work_segment_clearance | 0 | 0 |

proposal_reason_hits

| reason/phase | A | B |
|---|---|---|
| alignment_consumed_by_lane_turn | 62 | 62 |
| connection_search_budget_exhausted | 284 | 286 |
| existing_output_precheck | 0 | 0 |
| form_up_unavailable | 200 | 200 |
| ingress_line_blocked | 26 | 24 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 59 | 61 |
| retreat_endpoint_invalid | 7 | 7 |
| shape_search_budget_exhausted | 131 | 129 |
| sub_metre_semantic_join | 9 | 9 |
| survey_area_unavailable | 1174 | 1173 |
| survey_insufficient_strips | 326 | 325 |
| survey_strip_unavailable | 38 | 38 |
| whole_route_check | 453 | 453 |
| work_segment_clearance | 579 | 579 |

shape_attempt_reasons

| reason/phase | A | B |
|---|---|---|
| connection_search_budget_exhausted | 0 | 0 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 26 | 24 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 0 | 0 |
| retreat_endpoint_invalid | 7 | 7 |
| shape_search_budget_exhausted | 0 | 0 |
| sub_metre_semantic_join | 9 | 9 |
| survey_area_unavailable | 5885 | 5873 |
| survey_insufficient_strips | 819 | 811 |
| survey_strip_unavailable | 39 | 39 |
| whole_route_check | 0 | 0 |
| work_segment_clearance | 864 | 864 |

rejected_proposal_shape_reasons

| reason/phase | A | B |
|---|---|---|
| connection_search_budget_exhausted | 0 | 0 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 17 | 15 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 0 | 0 |
| shape_search_budget_exhausted | 0 | 0 |
| sub_metre_semantic_join | 1 | 1 |
| survey_area_unavailable | 3852 | 3840 |
| survey_insufficient_strips | 744 | 736 |
| survey_strip_unavailable | 18 | 18 |
| whole_route_check | 0 | 0 |
| work_segment_clearance | 355 | 355 |

connection_attempt_reasons

| reason/phase | A | B |
|---|---|---|
| alignment_consumed_by_lane_turn | 487 | 487 |
| connection_search_budget_exhausted | 0 | 0 |
| existing_output_precheck | 0 | 0 |
| form_up_unavailable | 2000 | 2000 |
| ingress_line_blocked | 0 | 0 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 353 | 373 |
| shape_search_budget_exhausted | 0 | 0 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 0 | 0 |
| work_segment_clearance | 0 | 0 |

phase_evidence_entries

| reason/phase | A | B |
|---|---|---|
| entry_to_work_start | 2 | 0 |
| ingress_line_outside_entry | 116 | 116 |

proposal_phase_hits

| reason/phase | A | B |
|---|---|---|
| entry_to_work_start | 2 | 0 |
| ingress_line_outside_entry | 24 | 24 |

### same_direction/close_observation

final_reasons

| reason/phase | A | B |
|---|---|---|
| connection_search_budget_exhausted | 33 | 33 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 0 | 0 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 0 | 0 |
| shape_search_budget_exhausted | 0 | 0 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 52 | 52 |
| work_segment_clearance | 0 | 0 |

proposal_reason_hits

| reason/phase | A | B |
|---|---|---|
| alignment_consumed_by_lane_turn | 32 | 32 |
| connection_search_budget_exhausted | 33 | 33 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 124 | 124 |
| inner_alignment_blocked | 0 | 0 |
| no_exterior_connection | 1 | 1 |
| no_interior_connection | 0 | 0 |
| observation_station_blocked | 65 | 65 |
| retreat_endpoint_invalid | 3 | 3 |
| shape_search_budget_exhausted | 0 | 0 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 52 | 52 |
| work_segment_clearance | 0 | 0 |

shape_attempt_reasons

| reason/phase | A | B |
|---|---|---|
| connection_search_budget_exhausted | 0 | 0 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 142 | 142 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 0 | 0 |
| observation_station_blocked | 82 | 82 |
| retreat_endpoint_invalid | 3 | 3 |
| shape_search_budget_exhausted | 0 | 0 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 0 | 0 |
| work_segment_clearance | 0 | 0 |

rejected_proposal_shape_reasons

| reason/phase | A | B |
|---|---|---|
| connection_search_budget_exhausted | 0 | 0 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 11 | 11 |
| inner_alignment_blocked | 0 | 0 |
| no_interior_connection | 0 | 0 |
| observation_station_blocked | 6 | 6 |
| shape_search_budget_exhausted | 0 | 0 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 0 | 0 |
| work_segment_clearance | 0 | 0 |

connection_attempt_reasons

| reason/phase | A | B |
|---|---|---|
| alignment_consumed_by_lane_turn | 320 | 320 |
| connection_search_budget_exhausted | 0 | 0 |
| existing_output_precheck | 0 | 0 |
| ingress_line_blocked | 0 | 0 |
| inner_alignment_blocked | 0 | 0 |
| no_exterior_connection | 10 | 10 |
| no_interior_connection | 0 | 0 |
| shape_search_budget_exhausted | 0 | 0 |
| survey_area_unavailable | 0 | 0 |
| whole_route_check | 0 | 0 |
| work_segment_clearance | 0 | 0 |

phase_evidence_entries

| reason/phase | A | B |
|---|---|---|
| entry_to_work_start | 518 | 518 |
| ingress_line_outside_entry | 728 | 728 |

proposal_phase_hits

| reason/phase | A | B |
|---|---|---|
| entry_to_work_start | 88 | 88 |
| ingress_line_outside_entry | 119 | 119 |

## 表 C：完整骨架

| approach | 分层 | 登记 | A PASS/完成 | B PASS/完成 |
|---|---|---|---|---|
| multi_direction | area_search | 11 | 2/11 | 10/11 |
| multi_direction | close_observation | 7 | 4/7 | 7/7 |
| multi_direction | ALL_RECONNAISSANCE | 15 | 6/15 | 14/15 |
| same_direction | area_search | 10 | 9/10 | 9/10 |
| same_direction | close_observation | 9 | 9/9 | 9/9 |
| same_direction | ALL_RECONNAISSANCE | 17 | 16/17 | 16/17 |

## 表 D：固定提案索引配对

已配对 8000 条；非 area_search 变化 0 条。直接恢复案例 1142 个。

全部索引的 stage/reason/rejection 哈希与接受状态、阶段迁移、原始日志定位见同名 JSON。

VERIFIED_FROM_SAVED_CONTRACTS

- family_s15_1b876e6b8b6f70c6_ext_006_regular / task_group_01 / 1；seed=7778664290258953489；A=whole_route_check 且含目标入口直线冲突；B=group_feasible，whole_route=PASS，existing_precheck=PASS。
- family_s15_1b876e6b8b6f70c6_ext_006_regular / task_group_01 / 6；seed=3333024390104404114；A=whole_route_check 且含目标入口直线冲突；B=group_feasible，whole_route=PASS，existing_precheck=PASS。
- family_s15_1b876e6b8b6f70c6_ext_006_regular / task_group_01 / 18；seed=9767902868084695732；A=whole_route_check 且含目标入口直线冲突；B=group_feasible，whole_route=PASS，existing_precheck=PASS。

## 表 E：实际绕行

{"count": 142, "min": 1.0156738592739596, "p50": 1.1884387596706965, "p90": 1.947863081059921, "max": 3.3788060870993957}
无法定位的成员数：3。同时保留精确顶点匹配口径；共线顶点被清理时，按原有数值精度 1e-6 m 验证锚点位于实际线段并唯一有序定位，记录残差，再累加真实路线段及端点所在段的相应部分。不存在则单列，不改变任何接受判据。详情见 JSON。

## 表 F：时间及未完成项

| 组 | 骨架耗时 p50/p90/max (s) | 总 attempt 墙钟 (s) | 续跑 (s) | 未完成 |
|---|---|---|---|---|
| a | 41.42443035000906 / 1303.9507265800044 / 2180.599047800002 | 4476.75 | 2076.6870000000054 | 0 |
| b | 42.04100350000226 / 362.78313751000394 / 547.6019225999917 | 871.0939999999973 | 0 | 0 |

耗时仅为观测值，不将非隔离批次时间差归因于单项修改。每骨架时间、未完成清单和指纹稳定性见 JSON。

## 公共抽签分层

| approach | slot | method | 登记 | A PASS/完成 | B PASS/完成 |
|---|---|---|---|---|---|
| multi_direction | 0 | area_search | 7 | 1/7 | 6/7 |
| multi_direction | 0 | close_observation | 6 | 3/6 | 6/6 |
| multi_direction | 0 | ALL_RECONNAISSANCE | 10 | 4/10 | 9/10 |
| multi_direction | 1 | area_search | 4 | 1/4 | 4/4 |
| multi_direction | 1 | close_observation | 1 | 1/1 | 1/1 |
| multi_direction | 1 | ALL_RECONNAISSANCE | 5 | 2/5 | 5/5 |
| same_direction | 0 | area_search | 4 | 3/4 | 3/4 |
| same_direction | 0 | close_observation | 3 | 3/3 | 3/3 |
| same_direction | 0 | ALL_RECONNAISSANCE | 6 | 5/6 | 5/6 |
| same_direction | 1 | area_search | 6 | 6/6 | 6/6 |
| same_direction | 1 | close_observation | 6 | 6/6 | 6/6 |
| same_direction | 1 | ALL_RECONNAISSANCE | 11 | 11/11 | 11/11 |

## 正确性与限制

硬停止事件：[]
P0 停止事件：0
全部合法提案原始合同核验数：{'a': 4734, 'b': 5852}
测试登记：{"status": "PASS", "original_tests": 113, "new_tests": 7, "skipped": 0, "wall_s": 117.70300000000861, "runtime_sha256_stable": true, "non_area_exact_equality": "PASS", "source_scope_audit": "p2_source_scope_audit.json", "deterministic_recovery": {"candidate_index": 1, "proposal_seed": 7778664290258953489, "old_conflicts": 1, "plan_checks": "PASS", "existing_precheck": "PASS"}, "final_test_registration": "p2_tests_after_verified/regression.json", "final_test_registration_sha256": "0f6bd2b967eb8405dc0951a8530044f2a8fdb7ce3d0e5653f59882b2405b7571", "initial_new_test_result": "FAIL: generic fixture had valid candidates but no old-entry-conflict witness; retained unchanged in p2_tests_after/", "resolution": "Used the explicitly permitted unmodified G1 descriptor; retained the generic fixture test and all strong assertions; no existing tests, algorithms, seeds or budgets changed. See p2_functional_fixture_revision.json."}
