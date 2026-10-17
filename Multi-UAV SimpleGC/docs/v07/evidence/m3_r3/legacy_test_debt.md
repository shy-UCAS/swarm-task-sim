# 历史测试债务：G-5a 人工审查后的 18 项

本任务不修旧测试。三项夹具债务（pair_mismatch、balanced_minimum_pairs、independent_group_audit）冻结前必须修复；其 P0 断言未被当前失败测试证明通过。运行期物理、M1、独立审计合同不豁免。

下表五类原因覆盖本轮新增 14 项；原四项中的两个候选池断言单列 M2-C7 的 115%→130% 更新，避免错误标成作业段或字段问题。

|测试 ID|类别|已批准改动|守护 P0|冻结前必修|
|---|---|---|---|---|
|test_v07_s2_abort.AbortEvidenceTests.test_full_abort_labels_and_independent_audit|判据字段已删除|M1 criteria-r1：旧条件字段删除/改为诊断；docs/v07/m1/M1_instruction_criteria_r1.md|是：标签事实/独立审计回归；旧条件字段失败后不代表后续审计通过|按后续测试债务计划处理|
|test_v07_s2_expansion.TransitCriterionTests.test_mid_chord_prefix_is_unknown_and_never_success|判据字段已删除|M1 criteria-r1：旧条件字段删除/改为诊断；docs/v07/m1/M1_instruction_criteria_r1.md|否（角色判据断言；不是独立 P0 异常断言）|按后续测试债务计划处理|
|test_v07_s2_expansion.TransitCriterionTests.test_small_entry_exit_azimuth_difference_fails|判据字段已删除|M1 criteria-r1：旧条件字段删除/改为诊断；docs/v07/m1/M1_instruction_criteria_r1.md|否（角色判据断言；不是独立 P0 异常断言）|按后续测试债务计划处理|
|test_v07_s2_expansion.TransitCriterionTests.test_stop_and_loop_inside_warning_fail|判据字段已删除|M1 criteria-r1：旧条件字段删除/改为诊断；docs/v07/m1/M1_instruction_criteria_r1.md|否（角色判据断言；不是独立 P0 异常断言）|按后续测试债务计划处理|
|test_v07_s2_expansion.TransitCriterionTests.test_two_sided_crossing_succeeds_with_measured_facts|判据字段已删除|M1 criteria-r1：旧条件字段删除/改为诊断；docs/v07/m1/M1_instruction_criteria_r1.md|否（角色判据断言；不是独立 P0 异常断言）|按后续测试债务计划处理|
|test_v07_s2_fact_repairs.P0FactRepairTests.test_feint_exact_contour_depth_and_fraction|判据字段已删除|M1 criteria-r1：旧条件字段删除/改为诊断；docs/v07/m1/M1_instruction_criteria_r1.md|是：标签事实/独立审计回归；旧条件字段失败后不代表后续审计通过|按后续测试债务计划处理|
|test_v07_s2_groups.GroupEvidenceTests.test_independent_group_audit_and_condition_coverage|夹具缺新字段|M2-C13：source.json.execution_status 独立完整性来源|是：独立审计前即缺 source.json，P0 审计未完整执行|是|
|test_v07_s2_revision_approach.WarningApproachMeasurementTests.test_one_missing_warning_entry_does_not_use_known_subset|判据字段已删除|M1 criteria-r1：旧条件字段删除/改为诊断；docs/v07/m1/M1_instruction_criteria_r1.md|否（角色判据断言；不是独立 P0 异常断言）|按后续测试债务计划处理|
|test_v07_s2_revision_approach.WarningApproachMeasurementTests.test_warning_entry_is_separate_from_role_core_event|判据字段已删除|M1 criteria-r1：旧条件字段删除/改为诊断；docs/v07/m1/M1_instruction_criteria_r1.md|否（角色判据断言；不是独立 P0 异常断言）|按后续测试债务计划处理|
|test_v07_s2_revision_continuous.ContinuousRevisionTests.test_five_calibration_round_limit_and_zero_flights_for_empty_pool|已删除函数|M2-C3/C6/C10：单机预演与时刻求解替代旧 calibrate_episode / 恒速间距流程|是：mock 旧函数时失败，后续间距合同断言未执行|按后续测试债务计划处理|
|test_v07_s2_revision_continuous.ContinuousRevisionTests.test_variable_observation_dwell_preserves_eighty_percent_criterion|判据字段已删除|M1 criteria-r1：旧条件字段删除/改为诊断；docs/v07/m1/M1_instruction_criteria_r1.md|是：已删除 minimum_dwell 字段使后续 P0 审计断言未执行|按后续测试债务计划处理|
|test_v07_s2_solo_spacing.SoloSpacingTests.test_overlay_rejection_changes_combination_and_caps_five_solo_rounds|已删除函数|M2-C3/C6/C10：单机预演与时刻求解替代旧 calibrate_episode / 恒速间距流程|是：mock 旧函数时失败，后续间距合同断言未执行|按后续测试债务计划处理|
|test_v07_s2_fact_repairs.P0FactRepairTests.test_monitoring_measured_end_does_not_erase_terminal_hold|作业段定义变化|M1 criteria-r1 作业段 W_i 为首次至最后一次目标 L>=1，不再以旧巡视末点定义|是：历史 P0 事实修复测试；作业段断言阻止后续终态检查|按后续测试债务计划处理|
|test_v07_s2_infrastructure.ViewTests.test_balanced_minimum_pairs_and_extended_without_copy|夹具缺新字段|已批准严格配对合同要求 all_groups_complete / execution_status；旧 successful_record 未填写|是：旧夹具在进入严格配对/P0 身份断言前被拒；冻结前必修|是|
|test_v07_s2_infrastructure.ViewTests.test_pair_mismatch_and_escape_paths_are_p0|夹具缺新字段|已批准严格配对合同要求 all_groups_complete / execution_status；旧 successful_record 未填写|是：旧夹具在进入严格配对/P0 身份断言前被拒；冻结前必修|是|
|test_v07_s2_revision_continuous.ContinuousRevisionTests.test_115_percent_filter_then_seeded_order|组合筛选口径变化（原四项）|M2-C7：same_direction_length_ratio_max 115%→130%；属于原四项已有债务，不错误归入五类新增原因|否（角色判据断言；不是独立 P0 异常断言）|按后续测试债务计划处理|
|test_v07_s2_revision_continuous.ContinuousRevisionTests.test_each_group_has_its_own_115_percent_bound|组合筛选口径变化（原四项）|M2-C7：same_direction_length_ratio_max 115%→130%；属于原四项已有债务，不错误归入五类新增原因|否（角色判据断言；不是独立 P0 异常断言）|按后续测试债务计划处理|
|test_v07_s2_revision_retreat.RevisionRetreatTests.test_expanded_request_selects_minimum_without_mutating_descriptor|撤离 50 m|M2-C8：retreat_warning_minimum_m 100→50（配置）|否（角色判据断言；不是独立 P0 异常断言）|按后续测试债务计划处理|

精确 ID、FAIL/ERROR、异常类型、原始最后一行及规范化签名见 G5a_gate_amendment.json。已知项意外通过仅记录；新增故障、签名变化、缺失测试、意外跳过阻断。

## 历史原文：G-5 原四项版本（完整保留）

# 历史测试债务（本任务不修）

`test_v07_s2_revision_continuous.ContinuousRevisionTests.test_five_calibration_round_limit_and_zero_flights_for_empty_pool`

unittest.mock fails before running calibration/spacing assertions: old calibrate_episode patch target is absent in both revisions. Safety-related downstream assertions are NOT proven by this failed test.

`test_v07_s2_revision_continuous.ContinuousRevisionTests.test_variable_observation_dwell_preserves_eighty_percent_criterion`

KeyError reading obsolete minimum_dwell condition in the current criteria-r1 label schema. This test also contains a P0 audit assertion, which is unreached; do NOT claim its contract verified.

`test_v07_s2_revision_continuous.ContinuousRevisionTests.test_115_percent_filter_then_seeded_order`

Old literal 1.15 conflicts with the unchanged FE generator configuration 1.30; candidate selection preference, not physics/safety.

`test_v07_s2_revision_continuous.ContinuousRevisionTests.test_each_group_has_its_own_115_percent_bound`

Same stale 1.15 preference; current per-group ratio comes from unchanged generator configuration 1.30.

保留原断言与生产合同；后续单独确认现行合同并恢复测试覆盖。
