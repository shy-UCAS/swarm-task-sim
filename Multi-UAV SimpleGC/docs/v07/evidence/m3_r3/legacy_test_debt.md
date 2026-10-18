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


## 已修复：T-debt（2026-10-17）

本段按 T-debt 及问题1/2、R-1～R-3 授权追加。以上18项历史表和原文完整保留，历史失败事实不改写。

完整冻结测试集 **492执行、492 PASS、0 FAIL、0 ERROR、0 SKIP**。删除0项，新增0项；全部原测试ID保留（部分名称保留历史词汇）。新辅助文件 debt_line_evidence.py 不定义测试方法。两项 A5 改写而不删除。

|测试ID|原语义|现语义|已批准依据|
|---|---|---|---|
|test_v07_s2_abort.AbortEvidenceTests.test_full_abort_labels_and_independent_audit|own_endpoint_hold 判据与独立撤离审计|四项 abort_* 真值、未进入受保护区、退出预警区、前缀不得声明撤离；补 source.execution_status 使审计执行|criteria-r1 / M2-C13|
|test_v07_s2_expansion.TransitCriterionTests.test_mid_chord_prefix_is_unknown_and_never_success|exited_warning/chord_length/no_loop 前缀未知|ended_outside_warning/no_dwell/no_revisit 为 None，组结果 unknown，截断审计 PASS；删除弦长判据断言|criteria-r1；T-debt R-1|
|test_v07_s2_expansion.TransitCriterionTests.test_small_entry_exit_azimuth_difference_fails|小进出方位角判失败|其他条件均满足时 success；观测进出方位角与圆几何解析值一致|criteria-r1 删除角度判据；T-debt 问题2(a)/R-1|
|test_v07_s2_expansion.TransitCriterionTests.test_stop_and_loop_inside_warning_fail|3 秒停顿及 60 米小圈触发旧停止/绕圈条件|按配置构造 dwell.window_s+5 秒停顿、离开再返回且方位覆盖充分的绕圈；各只触发 no_dwell/no_revisit，正对照成功，全程不进第2层|criteria-r1 驻留/再访定义；T-debt 问题2(b)/R-2|
|test_v07_s2_expansion.TransitCriterionTests.test_two_sided_crossing_succeeds_with_measured_facts|多向角度成败条件及旧 schema|观测接近跨度/分类事实、解析弦长/方位角、criteria/0.7-r1 与完整成功|criteria-r1 将接近角度改为观测事实|
|test_v07_s2_fact_repairs.P0FactRepairTests.test_feint_exact_contour_depth_and_fraction|depth_in_band 与 retreat_direction 成败条件|75 m 深度、0.5 带宽比例、转向/作业终点时间及 retreat_ok/回落量诊断|criteria-r1 将深度和撤离形态改为诊断|
|test_v07_s2_groups.GroupEvidenceTests.test_independent_group_audit_and_condition_coverage|缺 source.json 导致审计未执行|补本测试临时 source.execution_status，原 PASS/无未覆盖条件断言不变|M2-C13；A1|
|test_v07_s2_revision_approach.WarningApproachMeasurementTests.test_one_missing_warning_entry_does_not_use_known_subset|缺成员时多向条件 None|接近方位及跨度 None、classification unknown，绝不成功|criteria-r1；A2|
|test_v07_s2_revision_approach.WarningApproachMeasurementTests.test_warning_entry_is_separate_from_role_core_event|同侧进入不满足 multi_direction_span|观测跨度0、classification same_direction；预警进入与保护区核心事件仍独立|criteria-r1；A2|
|test_v07_s2_revision_continuous.ContinuousRevisionTests.test_five_calibration_round_limit_and_zero_flights_for_empty_pool|patch 已删除 calibrate_episode|patch rehearse/select_timing/execute；五轮且逐轮不同候选，空池零预演/零飞行|M2-C3/C6/C10；A5 改写不删除|
|test_v07_s2_revision_continuous.ContinuousRevisionTests.test_variable_observation_dwell_preserves_eighty_percent_criterion|计划驻留80%参数生成和篡改其阈值应 P0|生成断言原样保留；最小计划25秒夹具 observation_dwell True 且 detected True；独立篡改条件/confirm_frame_index 分别 P0_STOP 且字段命中|criteria-r1 20秒空间驻留；T-debt 问题1(a–d)/R-1|
|test_v07_s2_solo_spacing.SoloSpacingTests.test_overlay_rejection_changes_combination_and_caps_five_solo_rounds|旧 calibrate_episode/interval_check 的五轮换组合|现行 rehearse/select_timing 五轮不同候选，10次单机记录、无联合飞行、五项 timing_conflict 历史|M2-C3/C6/C10；A5 改写不删除|
|test_v07_s2_fact_repairs.P0FactRepairTests.test_monitoring_measured_end_does_not_erase_terminal_hold|作业在巡视末点结束|最后离开目标预警区的首个区外帧1396.7秒；3秒终点驻留和抵达事实保留|criteria-r1 作业段定义；A3|
|test_v07_s2_infrastructure.ViewTests.test_balanced_minimum_pairs_and_extended_without_copy|旧成功夹具缺完整性字段|补 all_groups_complete/execution_status，primary10/extended8 原断言保留|严格配对合同；A1|
|test_v07_s2_infrastructure.ViewTests.test_pair_mismatch_and_escape_paths_are_p0|配对不一致必须抛 P0，路径逃逸必须拒绝|补完整性字段；精确匹配 Claimed successful pair changed non-time conditions；路径逃逸断言不变|严格配对合同；A1|
|test_v07_s2_revision_continuous.ContinuousRevisionTests.test_115_percent_filter_then_seeded_order|115% 截断及种子排序|读取 same_direction_length_ratio_max 构造边界，检查筛选和同种子排序|M2-C7 已批准1.30；A4|
|test_v07_s2_revision_continuous.ContinuousRevisionTests.test_each_group_has_its_own_115_percent_bound|每组独立115%上限|按配置上限构造候选，仍仅第2号候选满足两组各自最短比例|M2-C7；A4|
|test_v07_s2_revision_retreat.RevisionRetreatTests.test_expanded_request_selects_minimum_without_mutating_descriptor|旧100m撤离参数|从配置读取 warning_clearance_m，描述符不变断言保留|M2-C8 已批准50m；A3|

A1 配对异常精确匹配指定消息；三个测试的执行行见 [A1证据](T_debt/A1_target_line_evidence.json)。

驻留篡改分别命中 a.result.conditions.observation_dwell、a.contribution.observation_dwell.confirm_frame_index，均返回 P0_STOP；未暴露这两项事实的审计覆盖缺失。

初次局部验证发生测试自身 FileExistsError（save_json 使用独占创建，无法覆盖临时标签），已仅改用测试临时文件写入后重验；不是审计放过篡改，也未改生产。

[A验收](T_debt/A_gate.json) · [完整日志](T_debt/A_full_unittest_attempt01.log)
