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
