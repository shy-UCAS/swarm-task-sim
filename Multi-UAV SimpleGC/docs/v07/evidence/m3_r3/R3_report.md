# R3 基线契约回归阻断

最终状态：BLOCKED；原因 BASELINE_FAILURE_NOT_IN_CONFIRMED_FOUR。P2 未合并，候选完整集成测试和本阶段默认 r2 七探针重放未执行，R4 未执行。

固定 FE 基线 81f804a969192790d89100528e3f802bc06446b1 的 47 个已有模块共执行 476 项：458 PASS、6 FAIL、12 ERROR；另两模块为 r3/P2 新增内容，基线不存在，未被冒充为已测试。
18 项失败中原 4 项签名保持一致；另 14 项超出原豁免，不扩充白名单。两次独立基线回归的失败 ID 和类型相同。所有相关旧测试源码与 FE、当前候选逐字节相同。

## 为什么停止

这些结果来自固定 FE 基线，不是已证明由 r3 引入的回归。也不能把它们一概豁免：其中包含 M1 判据、独立审计和 P0 配对契约测试，属于 G-2a 要求保留的合同范围。需逐项判断旧夹具/旧断言与现行合同的关系，人工批准后再处理。

例如 test_pair_mismatch_and_escape_paths_are_p0 预期抛出 P0ContractError，实际未抛出；test_independent_group_audit_and_condition_coverage 在旧测试自行建立的临时夹具中缺 source.json（不是隔离副本漏拷历史数据）；多项 M1 旧测试访问现行结果不存在的条件字段。不能据此宣称 r3 仿真发生了新的物理安全错误。

## 工具修复与历史保留

attempt01 首先因日志解析未支持双行 docstring 而 BLOCKED。单独 fix(harness) 提交 6549a8f 修复解析；20 项测试通过，其中包含真实 476 项日志和计数/子测试/跳过/异常签名检查。未改门禁、输入集合、生产代码或既有测试。新 attempt02 完整复跑，得到上述真实阻断。额外 2 次修复额度已用 1 次。
attempt01、attempt04、原 R1 FAIL 全部保留。最终修复后不再是日志工具错误。

## 逐项失败

|测试 ID|类型|范围|
|---|---|---|
|test_v07_s2_abort.AbortEvidenceTests.test_full_abort_labels_and_independent_audit|ERROR|未豁免，需人工审查|
|test_v07_s2_expansion.TransitCriterionTests.test_mid_chord_prefix_is_unknown_and_never_success|ERROR|未豁免，需人工审查|
|test_v07_s2_expansion.TransitCriterionTests.test_small_entry_exit_azimuth_difference_fails|ERROR|未豁免，需人工审查|
|test_v07_s2_expansion.TransitCriterionTests.test_stop_and_loop_inside_warning_fail|ERROR|未豁免，需人工审查|
|test_v07_s2_expansion.TransitCriterionTests.test_two_sided_crossing_succeeds_with_measured_facts|ERROR|未豁免，需人工审查|
|test_v07_s2_fact_repairs.P0FactRepairTests.test_feint_exact_contour_depth_and_fraction|ERROR|未豁免，需人工审查|
|test_v07_s2_groups.GroupEvidenceTests.test_independent_group_audit_and_condition_coverage|ERROR|未豁免，需人工审查|
|test_v07_s2_revision_approach.WarningApproachMeasurementTests.test_one_missing_warning_entry_does_not_use_known_subset|ERROR|未豁免，需人工审查|
|test_v07_s2_revision_approach.WarningApproachMeasurementTests.test_warning_entry_is_separate_from_role_core_event|ERROR|未豁免，需人工审查|
|test_v07_s2_revision_continuous.ContinuousRevisionTests.test_five_calibration_round_limit_and_zero_flights_for_empty_pool|ERROR|原四项签名一致|
|test_v07_s2_revision_continuous.ContinuousRevisionTests.test_variable_observation_dwell_preserves_eighty_percent_criterion|ERROR|原四项签名一致|
|test_v07_s2_solo_spacing.SoloSpacingTests.test_overlay_rejection_changes_combination_and_caps_five_solo_rounds|ERROR|未豁免，需人工审查|
|test_v07_s2_fact_repairs.P0FactRepairTests.test_monitoring_measured_end_does_not_erase_terminal_hold|FAIL|未豁免，需人工审查|
|test_v07_s2_infrastructure.ViewTests.test_balanced_minimum_pairs_and_extended_without_copy|FAIL|未豁免，需人工审查|
|test_v07_s2_infrastructure.ViewTests.test_pair_mismatch_and_escape_paths_are_p0|FAIL|未豁免，需人工审查|
|test_v07_s2_revision_continuous.ContinuousRevisionTests.test_115_percent_filter_then_seeded_order|FAIL|原四项签名一致|
|test_v07_s2_revision_continuous.ContinuousRevisionTests.test_each_group_has_its_own_115_percent_bound|FAIL|原四项签名一致|
|test_v07_s2_revision_retreat.RevisionRetreatTests.test_expanded_request_selects_minimum_without_mutating_descriptor|FAIL|未豁免，需人工审查|

完整堆栈及源码 SHA256：R3_baseline_failure_inventory.json。
外部 attempt01：F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\fast_dynamics\m3\m3_r3_r3_attempt01
外部 attempt02：F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\fast_dynamics\m3\m3_r3_r3_attempt02

## 下一步所需决定

先对额外 14 项逐项审查，明确哪些属于旧测试债务、哪些仍约束现行 M1/P0 合同。当前授权不允许修复旧测试或豁免这些合同。本轮停止，不合并 P2、不进入 R4、不调整 r3 几何/参数。
