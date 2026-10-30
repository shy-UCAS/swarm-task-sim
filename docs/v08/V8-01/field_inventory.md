# V8-01 §3.1 字段清点（prod_f020_060）

由 `scripts/v8_01_field_inventory.py` 生成。数组只展开第一个元素；同类编号键只展开第一个。

B 状态取值（本批）：['PASS', 'REJECT']；C 状态取值（本批）：['NOT_PAIRED', 'PAIRED']

### stats.json

文件：`v07_first_edition/prod_f020_060/stats.json`

```
yield : dict(11)
yield.families : int = 40
yield.family_unsampleable : int = 0
yield.descriptors : int = 400
yield.draws : int = 80
yield.b_all_pass_draws : int = 70
yield.retained_draws : int = 64
yield.draw_retention_ratio : float = 0.8
yield.b_all_pass_ratio : float = 0.875
yield.by_layout : dict(4)
yield.by_layout.clustered : dict(5)
yield.by_layout.clustered.draws : int = 18
yield.by_layout.clustered.b_all_pass : int = 15
yield.by_layout.clustered.retained : int = 13
yield.by_layout.clustered.b_all_pass_ratio : float = 0.8333333333333334
yield.by_layout.clustered.retention_ratio : float = 0.7222222222222222
yield.by_layout.isolated : dict(5)
yield.by_layout.isolated.draws : int = 16
yield.by_layout.isolated.b_all_pass : int = 15
yield.by_layout.isolated.retained : int = 13
yield.by_layout.isolated.b_all_pass_ratio : float = 0.9375
yield.by_layout.isolated.retention_ratio : float = 0.8125
yield.by_layout.linear : dict(5)
yield.by_layout.linear.draws : int = 16
yield.by_layout.linear.b_all_pass : int = 16
yield.by_layout.linear.retained : int = 15
yield.by_layout.linear.b_all_pass_ratio : float = 1.0
yield.by_layout.linear.retention_ratio : float = 0.9375
yield.by_layout.single : dict(5)
yield.by_layout.single.draws : int = 30
yield.by_layout.single.b_all_pass : int = 24
yield.by_layout.single.retained : int = 23
yield.by_layout.single.b_all_pass_ratio : float = 0.8
yield.by_layout.single.retention_ratio : float = 0.7666666666666667
yield.by_facility_count : dict(3)
yield.by_facility_count.1  (同类键 `#` 共 3 个，只展开第一个) : dict(5)
yield.by_facility_count.1.draws : int = 30
yield.by_facility_count.1.b_all_pass : int = 24
yield.by_facility_count.1.retained : int = 23
yield.by_facility_count.1.b_all_pass_ratio : float = 0.8
yield.by_facility_count.1.retention_ratio : float = 0.7666666666666667
yield.by_vehicle_count : dict(2)
yield.by_vehicle_count.4-5 : dict(5)
yield.by_vehicle_count.4-5.draws : int = 12
yield.by_vehicle_count.4-5.b_all_pass : int = 12
yield.by_vehicle_count.4-5.retained : int = 12
yield.by_vehicle_count.4-5.b_all_pass_ratio : float = 1.0
yield.by_vehicle_count.4-5.retention_ratio : float = 1.0
yield.by_vehicle_count.>=6 : dict(5)
yield.by_vehicle_count.>=6.draws : int = 68
yield.by_vehicle_count.>=6.b_all_pass : int = 58
yield.by_vehicle_count.>=6.retained : int = 52
yield.by_vehicle_count.>=6.b_all_pass_ratio : float = 0.8529411764705882
yield.by_vehicle_count.>=6.retention_ratio : float = 0.7647058823529411
intents : dict(5)
intents.transit : dict(9)
intents.transit.b_total : int = 80
intents.transit.b_pass : int = 77
intents.transit.b_pass_ratio : float = 0.9625
intents.transit.b_rejection_top5 : dict(1)
intents.transit.b_rejection_top5.connection_search_budget_exhausted : int = 600
intents.transit.c_in_b_pass : int = 70
intents.transit.c_paired : int = 69
intents.transit.c_pair_ratio : float = 0.9857142857142858
intents.transit.c_first_failure_top5 : dict(1)
intents.transit.c_first_failure_top5.{'stage': 'execution', 'reason': 'timeout'} : int = 1
intents.transit.retained_episodes : int = 128
intents.reconnaissance : dict(9)
intents.reconnaissance.b_total : int = 80
intents.reconnaissance.b_pass : int = 75
intents.reconnaissance.b_pass_ratio : float = 0.9375
intents.reconnaissance.b_rejection_top5 : dict(3)
intents.reconnaissance.b_rejection_top5.connection_search_budget_exhausted : int = 713
intents.reconnaissance.b_rejection_top5.shape_search_budget_exhausted : int = 277
intents.reconnaissance.b_rejection_top5.whole_route_check : int = 10
intents.reconnaissance.c_in_b_pass : int = 70
intents.reconnaissance.c_paired : int = 69
intents.reconnaissance.c_pair_ratio : float = 0.9857142857142858
intents.reconnaissance.c_first_failure_top5 : dict(1)
intents.reconnaissance.c_first_failure_top5.{'stage': 'execution', 'reason': 'timeout'} : int = 1
intents.reconnaissance.retained_episodes : int = 128
intents.monitoring : dict(9)
intents.monitoring.b_total : int = 80
intents.monitoring.b_pass : int = 74
intents.monitoring.b_pass_ratio : float = 0.925
intents.monitoring.b_rejection_top5 : dict(2)
intents.monitoring.b_rejection_top5.shape_search_budget_exhausted : int = 604
intents.monitoring.b_rejection_top5.connection_search_budget_exhausted : int = 596
intents.monitoring.c_in_b_pass : int = 70
intents.monitoring.c_paired : int = 69
intents.monitoring.c_pair_ratio : float = 0.9857142857142858
intents.monitoring.c_first_failure_top5 : dict(1)
intents.monitoring.c_first_failure_top5.{'stage': 'timing_conflict', 'reason': 'timing_conflict', 'first_attempt': {'...（键为序列化的长字典，已截断） : int = 1
intents.monitoring.retained_episodes : int = 128
intents.feint : dict(9)
intents.feint.b_total : int = 80
intents.feint.b_pass : int = 77
intents.feint.b_pass_ratio : float = 0.9625
intents.feint.b_rejection_top5 : dict(1)
intents.feint.b_rejection_top5.connection_search_budget_exhausted : int = 600
intents.feint.c_in_b_pass : int = 70
intents.feint.c_paired : int = 70
intents.feint.c_pair_ratio : float = 1.0
intents.feint.c_first_failure_top5 : dict(0)
intents.feint.retained_episodes : int = 128
intents.penetration : dict(9)
intents.penetration.b_total : int = 80
intents.penetration.b_pass : int = 74
intents.penetration.b_pass_ratio : float = 0.925
intents.penetration.b_rejection_top5 : dict(2)
intents.penetration.b_rejection_top5.shape_search_budget_exhausted : int = 1000
intents.penetration.b_rejection_top5.connection_search_budget_exhausted : int = 200
intents.penetration.c_in_b_pass : int = 70
intents.penetration.c_paired : int = 67
intents.penetration.c_pair_ratio : float = 0.9571428571428572
intents.penetration.c_first_failure_top5 : dict(1)
intents.penetration.c_first_failure_top5.{'stage': 'execution', 'reason': 'timeout'} : int = 3
intents.penetration.retained_episodes : int = 128
coverage_bias : dict(3)
coverage_bias.all_draws : dict(7)
coverage_bias.all_draws.layouts : dict(4)
coverage_bias.all_draws.layouts.clustered : int = 18
coverage_bias.all_draws.layouts.isolated : int = 16
coverage_bias.all_draws.layouts.linear : int = 16
coverage_bias.all_draws.layouts.single : int = 30
coverage_bias.all_draws.facility_counts : dict(3)
coverage_bias.all_draws.facility_counts.1  (同类键 `#` 共 3 个，只展开第一个) : int
coverage_bias.all_draws.vehicle_counts : dict(9)
coverage_bias.all_draws.vehicle_counts.10  (同类键 `#` 共 9 个，只展开第一个) : int
coverage_bias.all_draws.vehicle_buckets : dict(2)
coverage_bias.all_draws.vehicle_buckets.4-5 : int = 12
coverage_bias.all_draws.vehicle_buckets.>=6 : int = 68
coverage_bias.all_draws.actual_unit_counts : dict(3)
coverage_bias.all_draws.actual_unit_counts.1  (同类键 `#` 共 3 个，只展开第一个) : int
coverage_bias.all_draws.approach_modes : dict(2)
coverage_bias.all_draws.approach_modes.multi_direction : int = 37
coverage_bias.all_draws.approach_modes.same_direction : int = 43
coverage_bias.all_draws.task_groups_by_intent : dict(5)
coverage_bias.all_draws.task_groups_by_intent.feint : dict(5)
coverage_bias.all_draws.task_groups_by_intent.feint.draws : int = 80
coverage_bias.all_draws.task_groups_by_intent.feint.groups : int = 102
coverage_bias.all_draws.task_groups_by_intent.feint.members : int = 660
coverage_bias.all_draws.task_groups_by_intent.feint.mean_groups : float = 1.275
coverage_bias.all_draws.task_groups_by_intent.feint.mean_members : float = 6.470588235294118
coverage_bias.all_draws.task_groups_by_intent.monitoring : dict(5)
coverage_bias.all_draws.task_groups_by_intent.monitoring.draws : int = 80
coverage_bias.all_draws.task_groups_by_intent.monitoring.groups : int = 102
coverage_bias.all_draws.task_groups_by_intent.monitoring.members : int = 660
coverage_bias.all_draws.task_groups_by_intent.monitoring.mean_groups : float = 1.275
coverage_bias.all_draws.task_groups_by_intent.monitoring.mean_members : float = 6.470588235294118
coverage_bias.all_draws.task_groups_by_intent.penetration : dict(5)
coverage_bias.all_draws.task_groups_by_intent.penetration.draws : int = 80
coverage_bias.all_draws.task_groups_by_intent.penetration.groups : int = 131
coverage_bias.all_draws.task_groups_by_intent.penetration.members : int = 660
coverage_bias.all_draws.task_groups_by_intent.penetration.mean_groups : float = 1.6375
coverage_bias.all_draws.task_groups_by_intent.penetration.mean_members : float = 5.038167938931298
coverage_bias.all_draws.task_groups_by_intent.reconnaissance : dict(5)
coverage_bias.all_draws.task_groups_by_intent.reconnaissance.draws : int = 80
coverage_bias.all_draws.task_groups_by_intent.reconnaissance.groups : int = 102
coverage_bias.all_draws.task_groups_by_intent.reconnaissance.members : int = 660
coverage_bias.all_draws.task_groups_by_intent.reconnaissance.mean_groups : float = 1.275
coverage_bias.all_draws.task_groups_by_intent.reconnaissance.mean_members : float = 6.470588235294118
coverage_bias.all_draws.task_groups_by_intent.transit : dict(5)
coverage_bias.all_draws.task_groups_by_intent.transit.draws : int = 80
coverage_bias.all_draws.task_groups_by_intent.transit.groups : int = 102
coverage_bias.all_draws.task_groups_by_intent.transit.members : int = 660
coverage_bias.all_draws.task_groups_by_intent.transit.mean_groups : float = 1.275
coverage_bias.all_draws.task_groups_by_intent.transit.mean_members : float = 6.470588235294118
coverage_bias.b_all_pass_draws : dict(7)
coverage_bias.b_all_pass_draws.layouts : dict(4)
coverage_bias.b_all_pass_draws.layouts.clustered : int = 15
coverage_bias.b_all_pass_draws.layouts.isolated : int = 15
coverage_bias.b_all_pass_draws.layouts.linear : int = 16
coverage_bias.b_all_pass_draws.layouts.single : int = 24
coverage_bias.b_all_pass_draws.facility_counts : dict(3)
coverage_bias.b_all_pass_draws.facility_counts.1  (同类键 `#` 共 3 个，只展开第一个) : int
coverage_bias.b_all_pass_draws.vehicle_counts : dict(8)
coverage_bias.b_all_pass_draws.vehicle_counts.10  (同类键 `#` 共 8 个，只展开第一个) : int
coverage_bias.b_all_pass_draws.vehicle_buckets : dict(2)
coverage_bias.b_all_pass_draws.vehicle_buckets.4-5 : int = 12
coverage_bias.b_all_pass_draws.vehicle_buckets.>=6 : int = 58
coverage_bias.b_all_pass_draws.actual_unit_counts : dict(3)
coverage_bias.b_all_pass_draws.actual_unit_counts.1  (同类键 `#` 共 3 个，只展开第一个) : int
coverage_bias.b_all_pass_draws.approach_modes : dict(2)
coverage_bias.b_all_pass_draws.approach_modes.multi_direction : int = 34
coverage_bias.b_all_pass_draws.approach_modes.same_direction : int = 36
coverage_bias.b_all_pass_draws.task_groups_by_intent : dict(5)
coverage_bias.b_all_pass_draws.task_groups_by_intent.feint : dict(5)
coverage_bias.b_all_pass_draws.task_groups_by_intent.feint.draws : int = 70
coverage_bias.b_all_pass_draws.task_groups_by_intent.feint.groups : int = 92
coverage_bias.b_all_pass_draws.task_groups_by_intent.feint.members : int = 557
coverage_bias.b_all_pass_draws.task_groups_by_intent.feint.mean_groups : float = 1.3142857142857143
coverage_bias.b_all_pass_draws.task_groups_by_intent.feint.mean_members : float = 6.054347826086956
coverage_bias.b_all_pass_draws.task_groups_by_intent.monitoring : dict(5)
coverage_bias.b_all_pass_draws.task_groups_by_intent.monitoring.draws : int = 70
coverage_bias.b_all_pass_draws.task_groups_by_intent.monitoring.groups : int = 92
coverage_bias.b_all_pass_draws.task_groups_by_intent.monitoring.members : int = 557
coverage_bias.b_all_pass_draws.task_groups_by_intent.monitoring.mean_groups : float = 1.3142857142857143
coverage_bias.b_all_pass_draws.task_groups_by_intent.monitoring.mean_members : float = 6.054347826086956
coverage_bias.b_all_pass_draws.task_groups_by_intent.penetration : dict(5)
coverage_bias.b_all_pass_draws.task_groups_by_intent.penetration.draws : int = 70
coverage_bias.b_all_pass_draws.task_groups_by_intent.penetration.groups : int = 119
coverage_bias.b_all_pass_draws.task_groups_by_intent.penetration.members : int = 557
coverage_bias.b_all_pass_draws.task_groups_by_intent.penetration.mean_groups : float = 1.7
coverage_bias.b_all_pass_draws.task_groups_by_intent.penetration.mean_members : float = 4.680672268907563
coverage_bias.b_all_pass_draws.task_groups_by_intent.reconnaissance : dict(5)
coverage_bias.b_all_pass_draws.task_groups_by_intent.reconnaissance.draws : int = 70
coverage_bias.b_all_pass_draws.task_groups_by_intent.reconnaissance.groups : int = 92
coverage_bias.b_all_pass_draws.task_groups_by_intent.reconnaissance.members : int = 557
coverage_bias.b_all_pass_draws.task_groups_by_intent.reconnaissance.mean_groups : float = 1.3142857142857143
coverage_bias.b_all_pass_draws.task_groups_by_intent.reconnaissance.mean_members : float = 6.054347826086956
coverage_bias.b_all_pass_draws.task_groups_by_intent.transit : dict(5)
coverage_bias.b_all_pass_draws.task_groups_by_intent.transit.draws : int = 70
coverage_bias.b_all_pass_draws.task_groups_by_intent.transit.groups : int = 92
coverage_bias.b_all_pass_draws.task_groups_by_intent.transit.members : int = 557
coverage_bias.b_all_pass_draws.task_groups_by_intent.transit.mean_groups : float = 1.3142857142857143
coverage_bias.b_all_pass_draws.task_groups_by_intent.transit.mean_members : float = 6.054347826086956
coverage_bias.retained_draws : dict(7)
coverage_bias.retained_draws.layouts : dict(4)
coverage_bias.retained_draws.layouts.clustered : int = 13
coverage_bias.retained_draws.layouts.isolated : int = 13
coverage_bias.retained_draws.layouts.linear : int = 15
coverage_bias.retained_draws.layouts.single : int = 23
coverage_bias.retained_draws.facility_counts : dict(3)
coverage_bias.retained_draws.facility_counts.1  (同类键 `#` 共 3 个，只展开第一个) : int
coverage_bias.retained_draws.vehicle_counts : dict(8)
coverage_bias.retained_draws.vehicle_counts.10  (同类键 `#` 共 8 个，只展开第一个) : int
coverage_bias.retained_draws.vehicle_buckets : dict(2)
coverage_bias.retained_draws.vehicle_buckets.4-5 : int = 12
coverage_bias.retained_draws.vehicle_buckets.>=6 : int = 52
coverage_bias.retained_draws.actual_unit_counts : dict(3)
coverage_bias.retained_draws.actual_unit_counts.1  (同类键 `#` 共 3 个，只展开第一个) : int
coverage_bias.retained_draws.approach_modes : dict(2)
coverage_bias.retained_draws.approach_modes.multi_direction : int = 31
coverage_bias.retained_draws.approach_modes.same_direction : int = 33
coverage_bias.retained_draws.task_groups_by_intent : dict(5)
coverage_bias.retained_draws.task_groups_by_intent.feint : dict(5)
coverage_bias.retained_draws.task_groups_by_intent.feint.draws : int = 64
coverage_bias.retained_draws.task_groups_by_intent.feint.groups : int = 83
coverage_bias.retained_draws.task_groups_by_intent.feint.members : int = 503
coverage_bias.retained_draws.task_groups_by_intent.feint.mean_groups : float = 1.296875
coverage_bias.retained_draws.task_groups_by_intent.feint.mean_members : float = 6.0602409638554215
coverage_bias.retained_draws.task_groups_by_intent.monitoring : dict(5)
coverage_bias.retained_draws.task_groups_by_intent.monitoring.draws : int = 64
coverage_bias.retained_draws.task_groups_by_intent.monitoring.groups : int = 83
coverage_bias.retained_draws.task_groups_by_intent.monitoring.members : int = 503
coverage_bias.retained_draws.task_groups_by_intent.monitoring.mean_groups : float = 1.296875
coverage_bias.retained_draws.task_groups_by_intent.monitoring.mean_members : float = 6.0602409638554215
coverage_bias.retained_draws.task_groups_by_intent.penetration : dict(5)
coverage_bias.retained_draws.task_groups_by_intent.penetration.draws : int = 64
coverage_bias.retained_draws.task_groups_by_intent.penetration.groups : int = 108
coverage_bias.retained_draws.task_groups_by_intent.penetration.members : int = 503
coverage_bias.retained_draws.task_groups_by_intent.penetration.mean_groups : float = 1.6875
coverage_bias.retained_draws.task_groups_by_intent.penetration.mean_members : float = 4.657407407407407
coverage_bias.retained_draws.task_groups_by_intent.reconnaissance : dict(5)
coverage_bias.retained_draws.task_groups_by_intent.reconnaissance.draws : int = 64
coverage_bias.retained_draws.task_groups_by_intent.reconnaissance.groups : int = 83
coverage_bias.retained_draws.task_groups_by_intent.reconnaissance.members : int = 503
coverage_bias.retained_draws.task_groups_by_intent.reconnaissance.mean_groups : float = 1.296875
coverage_bias.retained_draws.task_groups_by_intent.reconnaissance.mean_members : float = 6.0602409638554215
coverage_bias.retained_draws.task_groups_by_intent.transit : dict(5)
coverage_bias.retained_draws.task_groups_by_intent.transit.draws : int = 64
coverage_bias.retained_draws.task_groups_by_intent.transit.groups : int = 83
coverage_bias.retained_draws.task_groups_by_intent.transit.members : int = 503
coverage_bias.retained_draws.task_groups_by_intent.transit.mean_groups : float = 1.296875
coverage_bias.retained_draws.task_groups_by_intent.transit.mean_members : float = 6.0602409638554215
low_speed_and_dwell : list(12)
low_speed_and_dwell[0].role : str = "feint"
low_speed_and_dwell[0].execution_method : str = "feint"
low_speed_and_dwell[0].mode : str = "sequential"
low_speed_and_dwell[0].members : int = 587
low_speed_and_dwell[0].low_speed_events : int = 1050
low_speed_and_dwell[0].distance_km : float = 2655.5783149080044
low_speed_and_dwell[0].motion_time_s : float = 501388.0999999999
low_speed_and_dwell[0].low_speed_time_s : float = 65900.90000000005
low_speed_and_dwell[0].dwell_positive : int = 363
low_speed_and_dwell[0].dwell_evaluable : int = 587
low_speed_and_dwell[0].empty_motion_windows : int = 0
low_speed_and_dwell[0].near_corner_events : int = 594
low_speed_and_dwell[0].events_per_km : float = 0.39539410082747817
low_speed_and_dwell[0].low_speed_time_share : float = 0.1314369048647147
waiting_and_end_dwell : dict(10)
waiting_and_end_dwell.feint/sequential : dict(7)
waiting_and_end_dwell.feint/sequential.members : int = 503
waiting_and_end_dwell.feint/sequential.release_s : dict(4)
waiting_and_end_dwell.feint/sequential.release_s.count : int = 503
waiting_and_end_dwell.feint/sequential.release_s.median : float = 219.9
waiting_and_end_dwell.feint/sequential.release_s.p90 : float = 593.74
waiting_and_end_dwell.feint/sequential.release_s.max : float = 1203.8
waiting_and_end_dwell.feint/sequential.episode_release_span_s : dict(4)
waiting_and_end_dwell.feint/sequential.episode_release_span_s.count : int = 64
waiting_and_end_dwell.feint/sequential.episode_release_span_s.median : float = 348.8
waiting_and_end_dwell.feint/sequential.episode_release_span_s.p90 : float = 643.03
waiting_and_end_dwell.feint/sequential.episode_release_span_s.max : float = 1068.7
waiting_and_end_dwell.feint/sequential.low_speed_share_after_release : dict(4)
waiting_and_end_dwell.feint/sequential.low_speed_share_after_release.count : int = 503
waiting_and_end_dwell.feint/sequential.low_speed_share_after_release.median : float = 0.001858470335954253
waiting_and_end_dwell.feint/sequential.low_speed_share_after_release.p90 : float = 0.007424235607285503
waiting_and_end_dwell.feint/sequential.low_speed_share_after_release.max : float = 0.018736383442265796
waiting_and_end_dwell.feint/sequential.end_dwell_s : dict(4)
waiting_and_end_dwell.feint/sequential.end_dwell_s.count : int = 503
waiting_and_end_dwell.feint/sequential.end_dwell_s.median : float = 78.60000000000002
waiting_and_end_dwell.feint/sequential.end_dwell_s.p90 : float = 242.38
waiting_and_end_dwell.feint/sequential.end_dwell_s.max : float = 831.4
waiting_and_end_dwell.feint/sequential.initial_speed_gt_1_share : float = 0.3956262425447316
waiting_and_end_dwell.feint/sequential.evaluable_members : int = 503
waiting_and_end_dwell.feint/synchronous : dict(7)
waiting_and_end_dwell.feint/synchronous.members : int = 503
waiting_and_end_dwell.feint/synchronous.release_s : dict(4)
waiting_and_end_dwell.feint/synchronous.release_s.count : int = 503
waiting_and_end_dwell.feint/synchronous.release_s.median : float = 110.4
waiting_and_end_dwell.feint/synchronous.release_s.p90 : float = 525.18
waiting_and_end_dwell.feint/synchronous.release_s.max : float = 1034.3
waiting_and_end_dwell.feint/synchronous.episode_release_span_s : dict(4)
waiting_and_end_dwell.feint/synchronous.episode_release_span_s.count : int = 64
waiting_and_end_dwell.feint/synchronous.episode_release_span_s.median : float = 275.0
waiting_and_end_dwell.feint/synchronous.episode_release_span_s.p90 : float = 591.64
waiting_and_end_dwell.feint/synchronous.episode_release_span_s.max : float = 928.4
waiting_and_end_dwell.feint/synchronous.low_speed_share_after_release : dict(4)
waiting_and_end_dwell.feint/synchronous.low_speed_share_after_release.count : int = 503
waiting_and_end_dwell.feint/synchronous.low_speed_share_after_release.median : float = 0.001858470335954253
waiting_and_end_dwell.feint/synchronous.low_speed_share_after_release.p90 : float = 0.007424235607285503
waiting_and_end_dwell.feint/synchronous.low_speed_share_after_release.max : float = 0.018736383442265796
waiting_and_end_dwell.feint/synchronous.end_dwell_s : dict(4)
waiting_and_end_dwell.feint/synchronous.end_dwell_s.count : int = 503
waiting_and_end_dwell.feint/synchronous.end_dwell_s.median : float = 3.699999999999818
waiting_and_end_dwell.feint/synchronous.end_dwell_s.p90 : float = 66.64000000000003
waiting_and_end_dwell.feint/synchronous.end_dwell_s.max : float = 681.1999999999999
waiting_and_end_dwell.feint/synchronous.initial_speed_gt_1_share : float = 0.3956262425447316
waiting_and_end_dwell.feint/synchronous.evaluable_members : int = 503
waiting_and_end_dwell.monitoring/sequential : dict(7)
waiting_and_end_dwell.monitoring/sequential.members : int = 503
waiting_and_end_dwell.monitoring/sequential.release_s : dict(4)
waiting_and_end_dwell.monitoring/sequential.release_s.count : int = 503
waiting_and_end_dwell.monitoring/sequential.release_s.median : float = 255.8
waiting_and_end_dwell.monitoring/sequential.release_s.p90 : float = 664.2
waiting_and_end_dwell.monitoring/sequential.release_s.max : float = 1261.7
waiting_and_end_dwell.monitoring/sequential.episode_release_span_s : dict(4)
waiting_and_end_dwell.monitoring/sequential.episode_release_span_s.count : int = 64
waiting_and_end_dwell.monitoring/sequential.episode_release_span_s.median : float = 354.20000000000005
waiting_and_end_dwell.monitoring/sequential.episode_release_span_s.p90 : float = 794.8
waiting_and_end_dwell.monitoring/sequential.episode_release_span_s.max : float = 1153.5
waiting_and_end_dwell.monitoring/sequential.low_speed_share_after_release : dict(4)
waiting_and_end_dwell.monitoring/sequential.low_speed_share_after_release.count : int = 503
waiting_and_end_dwell.monitoring/sequential.low_speed_share_after_release.median : float = 0.006847556278353163
waiting_and_end_dwell.monitoring/sequential.low_speed_share_after_release.p90 : float = 0.01603580679143545
waiting_and_end_dwell.monitoring/sequential.low_speed_share_after_release.max : float = 0.02671872607563926
waiting_and_end_dwell.monitoring/sequential.end_dwell_s : dict(4)
waiting_and_end_dwell.monitoring/sequential.end_dwell_s.count : int = 503
waiting_and_end_dwell.monitoring/sequential.end_dwell_s.median : float = 208.39999999999964
waiting_and_end_dwell.monitoring/sequential.end_dwell_s.p90 : float = 698.02
waiting_and_end_dwell.monitoring/sequential.end_dwell_s.max : float = 1868.4999999999998
waiting_and_end_dwell.monitoring/sequential.initial_speed_gt_1_share : float = 0.3956262425447316
waiting_and_end_dwell.monitoring/sequential.evaluable_members : int = 503
waiting_and_end_dwell.monitoring/synchronous : dict(7)
waiting_and_end_dwell.monitoring/synchronous.members : int = 503
waiting_and_end_dwell.monitoring/synchronous.release_s : dict(4)
waiting_and_end_dwell.monitoring/synchronous.release_s.count : int = 503
waiting_and_end_dwell.monitoring/synchronous.release_s.median : float = 111.9
waiting_and_end_dwell.monitoring/synchronous.release_s.p90 : float = 463.46000000000004
waiting_and_end_dwell.monitoring/synchronous.release_s.max : float = 1102.9
waiting_and_end_dwell.monitoring/synchronous.episode_release_span_s : dict(4)
waiting_and_end_dwell.monitoring/synchronous.episode_release_span_s.count : int = 64
waiting_and_end_dwell.monitoring/synchronous.episode_release_span_s.median : float = 198.9
waiting_and_end_dwell.monitoring/synchronous.episode_release_span_s.p90 : float = 582.8000000000002
waiting_and_end_dwell.monitoring/synchronous.episode_release_span_s.max : float = 993.7
waiting_and_end_dwell.monitoring/synchronous.low_speed_share_after_release : dict(4)
waiting_and_end_dwell.monitoring/synchronous.low_speed_share_after_release.count : int = 503
waiting_and_end_dwell.monitoring/synchronous.low_speed_share_after_release.median : float = 0.006847556278353163
waiting_and_end_dwell.monitoring/synchronous.low_speed_share_after_release.p90 : float = 0.01603580679143545
waiting_and_end_dwell.monitoring/synchronous.low_speed_share_after_release.max : float = 0.02679528403001072
waiting_and_end_dwell.monitoring/synchronous.end_dwell_s : dict(4)
waiting_and_end_dwell.monitoring/synchronous.end_dwell_s.count : int = 503
waiting_and_end_dwell.monitoring/synchronous.end_dwell_s.median : float = 115.80000000000018
waiting_and_end_dwell.monitoring/synchronous.end_dwell_s.p90 : float = 560.96
waiting_and_end_dwell.monitoring/synchronous.end_dwell_s.max : float = 1857.3999999999999
waiting_and_end_dwell.monitoring/synchronous.initial_speed_gt_1_share : float = 0.3956262425447316
waiting_and_end_dwell.monitoring/synchronous.evaluable_members : int = 503
waiting_and_end_dwell.penetration/sequential : dict(7)
waiting_and_end_dwell.penetration/sequential.members : int = 503
waiting_and_end_dwell.penetration/sequential.release_s : dict(4)
waiting_and_end_dwell.penetration/sequential.release_s.count : int = 503
waiting_and_end_dwell.penetration/sequential.release_s.median : float = 226.8
waiting_and_end_dwell.penetration/sequential.release_s.p90 : float = 575.2600000000001
waiting_and_end_dwell.penetration/sequential.release_s.max : float = 1124.0
waiting_and_end_dwell.penetration/sequential.episode_release_span_s : dict(4)
waiting_and_end_dwell.penetration/sequential.episode_release_span_s.count : int = 64
waiting_and_end_dwell.penetration/sequential.episode_release_span_s.median : float = 329.0
waiting_and_end_dwell.penetration/sequential.episode_release_span_s.p90 : float = 736.6400000000001
waiting_and_end_dwell.penetration/sequential.episode_release_span_s.max : float = 1067.3
waiting_and_end_dwell.penetration/sequential.low_speed_share_after_release : dict(4)
waiting_and_end_dwell.penetration/sequential.low_speed_share_after_release.count : int = 503
waiting_and_end_dwell.penetration/sequential.low_speed_share_after_release.median : float = 0.002311390532544379
waiting_and_end_dwell.penetration/sequential.low_speed_share_after_release.p90 : float = 0.00907584618110934
waiting_and_end_dwell.penetration/sequential.low_speed_share_after_release.max : float = 0.019699167748339314
waiting_and_end_dwell.penetration/sequential.end_dwell_s : dict(4)
waiting_and_end_dwell.penetration/sequential.end_dwell_s.count : int = 503
waiting_and_end_dwell.penetration/sequential.end_dwell_s.median : float = 129.0
waiting_and_end_dwell.penetration/sequential.end_dwell_s.p90 : float = 519.6800000000001
waiting_and_end_dwell.penetration/sequential.end_dwell_s.max : float = 2654.6
waiting_and_end_dwell.penetration/sequential.initial_speed_gt_1_share : float = 0.3956262425447316
waiting_and_end_dwell.penetration/sequential.evaluable_members : int = 503
waiting_and_end_dwell.penetration/synchronous : dict(7)
waiting_and_end_dwell.penetration/synchronous.members : int = 503
waiting_and_end_dwell.penetration/synchronous.release_s : dict(4)
waiting_and_end_dwell.penetration/synchronous.release_s.count : int = 503
waiting_and_end_dwell.penetration/synchronous.release_s.median : float = 105.6
waiting_and_end_dwell.penetration/synchronous.release_s.p90 : float = 440.80000000000007
waiting_and_end_dwell.penetration/synchronous.release_s.max : float = 1074.9
waiting_and_end_dwell.penetration/synchronous.episode_release_span_s : dict(4)
waiting_and_end_dwell.penetration/synchronous.episode_release_span_s.count : int = 64
waiting_and_end_dwell.penetration/synchronous.episode_release_span_s.median : float = 209.8
waiting_and_end_dwell.penetration/synchronous.episode_release_span_s.p90 : float = 516.4600000000002
waiting_and_end_dwell.penetration/synchronous.episode_release_span_s.max : float = 1017.8000000000001
waiting_and_end_dwell.penetration/synchronous.low_speed_share_after_release : dict(4)
waiting_and_end_dwell.penetration/synchronous.low_speed_share_after_release.count : int = 503
waiting_and_end_dwell.penetration/synchronous.low_speed_share_after_release.median : float = 0.002311390532544379
waiting_and_end_dwell.penetration/synchronous.low_speed_share_after_release.p90 : float = 0.009057004918744761
waiting_and_end_dwell.penetration/synchronous.low_speed_share_after_release.max : float = 0.019699167748339314
waiting_and_end_dwell.penetration/synchronous.end_dwell_s : dict(4)
waiting_and_end_dwell.penetration/synchronous.end_dwell_s.count : int = 503
waiting_and_end_dwell.penetration/synchronous.end_dwell_s.median : float = 6.2000000000000455
waiting_and_end_dwell.penetration/synchronous.end_dwell_s.p90 : float = 320.12000000000006
waiting_and_end_dwell.penetration/synchronous.end_dwell_s.max : float = 2582.7999999999997
waiting_and_end_dwell.penetration/synchronous.initial_speed_gt_1_share : float = 0.3956262425447316
waiting_and_end_dwell.penetration/synchronous.evaluable_members : int = 503
waiting_and_end_dwell.reconnaissance/sequential : dict(7)
waiting_and_end_dwell.reconnaissance/sequential.members : int = 503
waiting_and_end_dwell.reconnaissance/sequential.release_s : dict(4)
waiting_and_end_dwell.reconnaissance/sequential.release_s.count : int = 503
waiting_and_end_dwell.reconnaissance/sequential.release_s.median : float = 266.5
waiting_and_end_dwell.reconnaissance/sequential.release_s.p90 : float = 732.96
waiting_and_end_dwell.reconnaissance/sequential.release_s.max : float = 1545.7
waiting_and_end_dwell.reconnaissance/sequential.episode_release_span_s : dict(4)
waiting_and_end_dwell.reconnaissance/sequential.episode_release_span_s.count : int = 64
waiting_and_end_dwell.reconnaissance/sequential.episode_release_span_s.median : float = 393.9
waiting_and_end_dwell.reconnaissance/sequential.episode_release_span_s.p90 : float = 798.06
waiting_and_end_dwell.reconnaissance/sequential.episode_release_span_s.max : float = 1217.9
waiting_and_end_dwell.reconnaissance/sequential.low_speed_share_after_release : dict(4)
waiting_and_end_dwell.reconnaissance/sequential.low_speed_share_after_release.count : int = 503
waiting_and_end_dwell.reconnaissance/sequential.low_speed_share_after_release.median : float = 0.0539010067114094
waiting_and_end_dwell.reconnaissance/sequential.low_speed_share_after_release.p90 : float = 0.1639906968031968
waiting_and_end_dwell.reconnaissance/sequential.low_speed_share_after_release.max : float = 0.3184737438609747
waiting_and_end_dwell.reconnaissance/sequential.end_dwell_s : dict(4)
waiting_and_end_dwell.reconnaissance/sequential.end_dwell_s.count : int = 503
waiting_and_end_dwell.reconnaissance/sequential.end_dwell_s.median : float = 126.10000000000002
waiting_and_end_dwell.reconnaissance/sequential.end_dwell_s.p90 : float = 367.12
waiting_and_end_dwell.reconnaissance/sequential.end_dwell_s.max : float = 765.1000000000001
waiting_and_end_dwell.reconnaissance/sequential.initial_speed_gt_1_share : float = 0.3956262425447316
waiting_and_end_dwell.reconnaissance/sequential.evaluable_members : int = 503
waiting_and_end_dwell.reconnaissance/synchronous : dict(7)
waiting_and_end_dwell.reconnaissance/synchronous.members : int = 503
waiting_and_end_dwell.reconnaissance/synchronous.release_s : dict(4)
waiting_and_end_dwell.reconnaissance/synchronous.release_s.count : int = 503
waiting_and_end_dwell.reconnaissance/synchronous.release_s.median : float = 114.3
waiting_and_end_dwell.reconnaissance/synchronous.release_s.p90 : float = 562.9000000000001
waiting_and_end_dwell.reconnaissance/synchronous.release_s.max : float = 1216.3
waiting_and_end_dwell.reconnaissance/synchronous.episode_release_span_s : dict(4)
waiting_and_end_dwell.reconnaissance/synchronous.episode_release_span_s.count : int = 64
waiting_and_end_dwell.reconnaissance/synchronous.episode_release_span_s.median : float = 255.64999999999998
waiting_and_end_dwell.reconnaissance/synchronous.episode_release_span_s.p90 : float = 673.79
waiting_and_end_dwell.reconnaissance/synchronous.episode_release_span_s.max : float = 1130.8999999999999
waiting_and_end_dwell.reconnaissance/synchronous.low_speed_share_after_release : dict(4)
waiting_and_end_dwell.reconnaissance/synchronous.low_speed_share_after_release.count : int = 503
waiting_and_end_dwell.reconnaissance/synchronous.low_speed_share_after_release.median : float = 0.0539010067114094
waiting_and_end_dwell.reconnaissance/synchronous.low_speed_share_after_release.p90 : float = 0.1639906968031968
waiting_and_end_dwell.reconnaissance/synchronous.low_speed_share_after_release.max : float = 0.3184737438609747
waiting_and_end_dwell.reconnaissance/synchronous.end_dwell_s : dict(4)
waiting_and_end_dwell.reconnaissance/synchronous.end_dwell_s.count : int = 503
waiting_and_end_dwell.reconnaissance/synchronous.end_dwell_s.median : float = 5.900000000000091
waiting_and_end_dwell.reconnaissance/synchronous.end_dwell_s.p90 : float = 152.36000000000007
waiting_and_end_dwell.reconnaissance/synchronous.end_dwell_s.max : float = 704.6999999999999
waiting_and_end_dwell.reconnaissance/synchronous.initial_speed_gt_1_share : float = 0.3956262425447316
waiting_and_end_dwell.reconnaissance/synchronous.evaluable_members : int = 503
waiting_and_end_dwell.transit/sequential : dict(7)
waiting_and_end_dwell.transit/sequential.members : int = 503
waiting_and_end_dwell.transit/sequential.release_s : dict(4)
waiting_and_end_dwell.transit/sequential.release_s.count : int = 503
waiting_and_end_dwell.transit/sequential.release_s.median : float = 257.6
waiting_and_end_dwell.transit/sequential.release_s.p90 : float = 678.7
waiting_and_end_dwell.transit/sequential.release_s.max : float = 1063.5
waiting_and_end_dwell.transit/sequential.episode_release_span_s : dict(4)
waiting_and_end_dwell.transit/sequential.episode_release_span_s.count : int = 64
waiting_and_end_dwell.transit/sequential.episode_release_span_s.median : float = 335.65
waiting_and_end_dwell.transit/sequential.episode_release_span_s.p90 : float = 795.9499999999999
waiting_and_end_dwell.transit/sequential.episode_release_span_s.max : float = 942.8
waiting_and_end_dwell.transit/sequential.low_speed_share_after_release : dict(4)
waiting_and_end_dwell.transit/sequential.low_speed_share_after_release.count : int = 503
waiting_and_end_dwell.transit/sequential.low_speed_share_after_release.median : float = 0.0018442892899486233
waiting_and_end_dwell.transit/sequential.low_speed_share_after_release.p90 : float = 0.007747942140174219
waiting_and_end_dwell.transit/sequential.low_speed_share_after_release.max : float = 0.024013098053483718
waiting_and_end_dwell.transit/sequential.end_dwell_s : dict(4)
waiting_and_end_dwell.transit/sequential.end_dwell_s.count : int = 503
waiting_and_end_dwell.transit/sequential.end_dwell_s.median : float = 123.80000000000007
waiting_and_end_dwell.transit/sequential.end_dwell_s.p90 : float = 408.9200000000002
waiting_and_end_dwell.transit/sequential.end_dwell_s.max : float = 834.3
waiting_and_end_dwell.transit/sequential.initial_speed_gt_1_share : float = 0.3956262425447316
waiting_and_end_dwell.transit/sequential.evaluable_members : int = 503
waiting_and_end_dwell.transit/synchronous : dict(7)
waiting_and_end_dwell.transit/synchronous.members : int = 503
waiting_and_end_dwell.transit/synchronous.release_s : dict(4)
waiting_and_end_dwell.transit/synchronous.release_s.count : int = 503
waiting_and_end_dwell.transit/synchronous.release_s.median : float = 116.3
waiting_and_end_dwell.transit/synchronous.release_s.p90 : float = 439.56
waiting_and_end_dwell.transit/synchronous.release_s.max : float = 954.0
waiting_and_end_dwell.transit/synchronous.episode_release_span_s : dict(4)
waiting_and_end_dwell.transit/synchronous.episode_release_span_s.count : int = 64
waiting_and_end_dwell.transit/synchronous.episode_release_span_s.median : float = 211.3
waiting_and_end_dwell.transit/synchronous.episode_release_span_s.p90 : float = 592.8
waiting_and_end_dwell.transit/synchronous.episode_release_span_s.max : float = 892.5
waiting_and_end_dwell.transit/synchronous.low_speed_share_after_release : dict(4)
waiting_and_end_dwell.transit/synchronous.low_speed_share_after_release.count : int = 503
waiting_and_end_dwell.transit/synchronous.low_speed_share_after_release.median : float = 0.0018442892899486233
waiting_and_end_dwell.transit/synchronous.low_speed_share_after_release.p90 : float = 0.007747942140174219
waiting_and_end_dwell.transit/synchronous.low_speed_share_after_release.max : float = 0.024013098053483718
waiting_and_end_dwell.transit/synchronous.end_dwell_s : dict(4)
waiting_and_end_dwell.transit/synchronous.end_dwell_s.count : int = 503
waiting_and_end_dwell.transit/synchronous.end_dwell_s.median : float = 21.0
waiting_and_end_dwell.transit/synchronous.end_dwell_s.p90 : float = 151.76
waiting_and_end_dwell.transit/synchronous.end_dwell_s.max : float = 709.2
waiting_and_end_dwell.transit/synchronous.initial_speed_gt_1_share : float = 0.3956262425447316
waiting_and_end_dwell.transit/synchronous.evaluable_members : int = 503
timing_and_size : dict(5)
timing_and_size.by_intent : dict(5)
timing_and_size.by_intent.transit : dict(2)
timing_and_size.by_intent.transit.b_wall_s : dict(4)
timing_and_size.by_intent.transit.b_wall_s.count : int = 80
timing_and_size.by_intent.transit.b_wall_s.median : float = 37.3125
timing_and_size.by_intent.transit.b_wall_s.p90 : float = 94.350400000003
timing_and_size.by_intent.transit.b_wall_s.max : float = 198.17200000000048
timing_and_size.by_intent.transit.c_wall_s : dict(4)
timing_and_size.by_intent.transit.c_wall_s.count : int = 70
timing_and_size.by_intent.transit.c_wall_s.median : float = 253.46900000000187
timing_and_size.by_intent.transit.c_wall_s.p90 : float = 498.4576
timing_and_size.by_intent.transit.c_wall_s.max : float = 917.1720000000005
timing_and_size.by_intent.reconnaissance : dict(2)
timing_and_size.by_intent.reconnaissance.b_wall_s : dict(4)
timing_and_size.by_intent.reconnaissance.b_wall_s.count : int = 80
timing_and_size.by_intent.reconnaissance.b_wall_s.median : float = 59.38249999999971
timing_and_size.by_intent.reconnaissance.b_wall_s.p90 : float = 515.4029000000008
timing_and_size.by_intent.reconnaissance.b_wall_s.max : float = 760.7039999999997
timing_and_size.by_intent.reconnaissance.c_wall_s : dict(4)
timing_and_size.by_intent.reconnaissance.c_wall_s.count : int = 70
timing_and_size.by_intent.reconnaissance.c_wall_s.median : float = 267.7660000000001
timing_and_size.by_intent.reconnaissance.c_wall_s.p90 : float = 531.4759999999995
timing_and_size.by_intent.reconnaissance.c_wall_s.max : float = 867.3119999999999
timing_and_size.by_intent.monitoring : dict(2)
timing_and_size.by_intent.monitoring.b_wall_s : dict(4)
timing_and_size.by_intent.monitoring.b_wall_s.count : int = 80
timing_and_size.by_intent.monitoring.b_wall_s.median : float = 209.4369999999999
timing_and_size.by_intent.monitoring.b_wall_s.p90 : float = 397.4035000000002
timing_and_size.by_intent.monitoring.b_wall_s.max : float = 680.9220000000005
timing_and_size.by_intent.monitoring.c_wall_s : dict(4)
timing_and_size.by_intent.monitoring.c_wall_s.count : int = 70
timing_and_size.by_intent.monitoring.c_wall_s.median : float = 1204.0315
timing_and_size.by_intent.monitoring.c_wall_s.p90 : float = 2217.0081
timing_and_size.by_intent.monitoring.c_wall_s.max : float = 2852.6720000000023
timing_and_size.by_intent.feint : dict(2)
timing_and_size.by_intent.feint.b_wall_s : dict(4)
timing_and_size.by_intent.feint.b_wall_s.count : int = 80
timing_and_size.by_intent.feint.b_wall_s.median : float = 58.32000000000062
timing_and_size.by_intent.feint.b_wall_s.p90 : float = 128.50069999999954
timing_and_size.by_intent.feint.b_wall_s.max : float = 227.17200000000048
timing_and_size.by_intent.feint.c_wall_s : dict(4)
timing_and_size.by_intent.feint.c_wall_s.count : int = 70
timing_and_size.by_intent.feint.c_wall_s.median : float = 249.3744999999999
timing_and_size.by_intent.feint.c_wall_s.p90 : float = 469.36389999999795
timing_and_size.by_intent.feint.c_wall_s.max : float = 838.3439999999991
timing_and_size.by_intent.penetration : dict(2)
timing_and_size.by_intent.penetration.b_wall_s : dict(4)
timing_and_size.by_intent.penetration.b_wall_s.count : int = 80
timing_and_size.by_intent.penetration.b_wall_s.median : float = 43.491999999999734
timing_and_size.by_intent.penetration.b_wall_s.p90 : float = 131.3871000000003
timing_and_size.by_intent.penetration.b_wall_s.max : float = 257.9380000000001
timing_and_size.by_intent.penetration.c_wall_s : dict(4)
timing_and_size.by_intent.penetration.c_wall_s.count : int = 70
timing_and_size.by_intent.penetration.c_wall_s.median : float = 242.64050000000043
timing_and_size.by_intent.penetration.c_wall_s.p90 : float = 636.2928000000005
timing_and_size.by_intent.penetration.c_wall_s.max : float = 1094.280999999999
timing_and_size.total_wall_s : float = 18712.813000000002
timing_and_size.run_dir_bytes : int = 32433123252
timing_and_size.retained_episode_bytes : int = 24440182525
timing_and_size.mean_retained_episode_bytes : float = 38187785.1953125
```

### status/B__*.json — PASS

文件：`v07_first_edition/prod_f020_060/status/B__family_s15_055e9333b067d2bc_ext_000_regular.json`

```
stage : str = "B"
skeleton_id : str = "family_s15_055e9333b067d2bc_ext_000_regular"
status : str = "PASS"
detail : dict(5)
detail.eligible_combinations : int = 79
detail.candidate_pool_sha256 : str = "b57ad1e76009ca80627eb93c6990d069ef236a495e8b9702440c1f01...
detail.rejection_reasons : dict(2)
detail.rejection_reasons.whole_route_check : int = 53
detail.rejection_reasons.connection_search_budget_exhausted : int = 68
detail.termination : NoneType = null
detail.planning_wall_s : float = 113.4369999999999
planning_wall_s : float = 113.4369999999999
```

### status/B__*.json — REJECT

文件：`v07_first_edition/prod_f020_060/status/B__family_s15_1b876e6b8b6f70c6_ext_000_regular.json`

```
stage : str = "B"
skeleton_id : str = "family_s15_1b876e6b8b6f70c6_ext_000_regular"
status : str = "REJECT"
detail : dict(5)
detail.eligible_combinations : int = 0
detail.candidate_pool_sha256 : NoneType = null
detail.rejection_reasons : dict(1)
detail.rejection_reasons.connection_search_budget_exhausted : int = 200
detail.termination : dict(5)
detail.termination.classification : str = "search_budget_exhausted"
detail.termination.scope : str = "skeleton_search"
detail.termination.reason : str = "no_eligible_combination_in_registered_budgets"
detail.termination.geometric_evidence : list(0)
detail.termination.global_infeasibility_claimed : bool = false
detail.planning_wall_s : float = 7.844000000000051
planning_wall_s : float = 7.844000000000051
```

### status/C__*.json — NOT_PAIRED

文件：`v07_first_edition/prod_f020_060/status/C__family_s15_3de8b14ca62da9ba_ext_009_regular.json`

```
stage : str = "C"
skeleton_id : str = "family_s15_3de8b14ca62da9ba_ext_009_regular"
status : str = "NOT_PAIRED"
detail : dict(4)
detail.paired : bool = false
detail.first_failure : dict(2)
detail.first_failure.stage : str = "execution"
detail.first_failure.reason : str = "timeout"
detail.rows : list(2)
detail.rows[0].episode_id : str = "family_s15_3de8b14ca62da9ba_ext_009_regular_synchronous"
detail.rows[0].family_id : str = "family_s15_3de8b14ca62da9ba"
detail.rows[0].skeleton_id : str = "family_s15_3de8b14ca62da9ba_ext_009_regular"
detail.rows[0].intent : str = "penetration"
detail.rows[0].mode : str = "synchronous"
detail.rows[0].aborted : bool = false
detail.rows[0].diagnostic_only : bool = false
detail.rows[0].common_slot : int = 1
detail.rows[0].state : str = "generated"
detail.rows[0].reason : NoneType = null
detail.rows[0].path : str = "family_s15_3de8b14ca62da9ba_ext_009_regular/synchronous"
detail.rows[0].quality_valid : bool = true
detail.rows[0].audit_passed : bool = true
detail.rows[0].task_result : str = "success"
detail.rows[0].agent_ids : list(12)
detail.rows[0].condition_digest : str = "57412e036e7745cca6c52c95bb94ea4add8749322843411602b956c5...
detail.rows[0].scene_digest : str = "162cf9cc4ec9ab906c18d266567e39f3789b1e36b83b6d5481ece627...
detail.rows[0].group_count : int = 3
detail.rows[0].groups : dict(3)
detail.rows[0].groups.task_group_01  (同类键 `task_group_#` 共 3 个，只展开第一个) : dict(9)
detail.rows[0].groups.task_group_01.role : str = "intrusion"
detail.rows[0].groups.task_group_01.execution_method : str = "intrusion"
detail.rows[0].groups.task_group_01.target_id : str = "facility_02"
detail.rows[0].groups.task_group_01.members : list(4)
detail.rows[0].groups.task_group_01.formation_split_count : int = 2
detail.rows[0].groups.task_group_01.approach_span_deg : float = 133.29509104341173
detail.rows[0].groups.task_group_01.coordination : dict(9)
detail.rows[0].groups.task_group_01.coordination.scope : str = "task_group"
detail.rows[0].groups.task_group_01.coordination.event_type : str = "start_core_operation"
detail.rows[0].groups.task_group_01.coordination.source : str = "truth.csv:10Hz_half_open_sim_clock"
detail.rows[0].groups.task_group_01.coordination.sync_window_s : float = 10.0
detail.rows[0].groups.task_group_01.coordination.batch_split_gap_s : float = 20.0
detail.rows[0].groups.task_group_01.coordination.event_times_s : dict(4)
detail.rows[0].groups.task_group_01.coordination.event_times_s.uav_01  (同类键 `uav_#` 共 4 个，只展开第一个) : float
detail.rows[0].groups.task_group_01.coordination.event_range_s : float = 3.1
detail.rows[0].groups.task_group_01.coordination.batches : list(1)
detail.rows[0].groups.task_group_01.coordination.batches[0].batch_index : int = 0
detail.rows[0].groups.task_group_01.coordination.batches[0].members : list(4)
detail.rows[0].groups.task_group_01.coordination.batches[0].start_s : float = 656.0
detail.rows[0].groups.task_group_01.coordination.batches[0].end_s : float = 659.1
detail.rows[0].groups.task_group_01.coordination.batches[0].span_s : float = 3.1
detail.rows[0].groups.task_group_01.coordination.classification : str = "synchronous"
detail.rows[0].groups.task_group_01.timing_diagnostics : dict(2)
detail.rows[0].groups.task_group_01.timing_diagnostics.coordination_matches_assignment : bool = true
detail.rows[0].groups.task_group_01.timing_diagnostics.batch_members_match_assignment : bool = true
detail.rows[0].groups.task_group_01.result : dict(2)
detail.rows[0].groups.task_group_01.result.status : str = "success"
detail.rows[0].groups.task_group_01.result.conditions : dict(1)
detail.rows[0].groups.task_group_01.result.conditions.member_contributions_complete : bool = true
detail.rows[0].coordination_by_group : dict(3)
detail.rows[0].coordination_by_group.task_group_01  (同类键 `task_group_#` 共 3 个，只展开第一个) : str
detail.rows[0].approach_mode : str = "multi_direction"
detail.rows[0].duration_s : float = 2684.2
detail.rows[0].minimum_separation_m : float = 13.880259653638735
detail.rows[0].execution_status : str = "timeout"
detail.rows[0].time_budget : dict(6)
detail.rows[0].time_budget.basis : str = "conservative bootstrap: settle + 2*route_length/speed + ...
detail.rows[0].time_budget.single_agent_completion_s : dict(12)
detail.rows[0].time_budget.single_agent_completion_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
detail.rows[0].time_budget.planned_completion_times_s : dict(12)
detail.rows[0].time_budget.planned_completion_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
detail.rows[0].time_budget.latest_planned_completion_s : float = 2236.791803265592
detail.rows[0].time_budget.margin_s : float = 447.35836065311844
detail.rows[0].time_budget.max_duration_s : float = 2684.2
detail.rows[0].coordination_matches : bool = true
detail.rows[0].batch_members_match : bool = true
detail.rows[0].audit : dict(7)
detail.rows[0].audit.independent_status : str = "PASS"
detail.rows[0].audit.region_difference_count : int = 0
detail.rows[0].audit.target_difference_count : int = 0
detail.rows[0].audit.event_or_metric_difference_count : int = 0
detail.rows[0].audit.uncovered_conditions : list(0)
detail.rows[0].audit.input_whitelist_passed : bool = true
detail.rows[0].audit.id_aligned_permutation_invariant : bool = true
detail.rows[0].truncation : dict(3)
detail.rows[0].truncation.task_group_01  (同类键 `task_group_#` 共 3 个，只展开第一个) : dict(7)
detail.rows[0].truncation.task_group_01.status : str = "PASS"
detail.rows[0].truncation.task_group_01.full_verdict : str = "yes"
detail.rows[0].truncation.task_group_01.prefix_verdict : str = "unknown"
detail.rows[0].truncation.task_group_01.cutoff_s : float = 670.5
detail.rows[0].truncation.task_group_01.protocol : str = "offline_half_work_truncation"
detail.rows[0].truncation.task_group_01.prefix_event_frames : dict(4)
detail.rows[0].truncation.task_group_01.prefix_event_frames.uav_01  (同类键 `uav_#` 共 4 个，只展开第一个) : int
detail.rows[0].truncation.task_group_01.measured_work_interval_s : list(2)
detail.rows[0].event_times_s : dict(12)
detail.rows[0].event_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
detail.rows[0].simulation_wall_s : float = 161.62962960000004
detail.rows[0].amortized_skeleton_setup_s : float = 346.06180394999956
detail.rows[0].episode_postprocess_wall_s : float = 33.56169239999872
detail.rows[0].primary_task_success : bool = true
detail.rows[0].all_groups_complete : bool = true
detail.rows[0].quality_status : str = "valid"
detail.rows[0].measured_approach_by_group : dict(3)
detail.rows[0].measured_approach_by_group.task_group_01  (同类键 `task_group_#` 共 3 个，只展开第一个) : str
detail.rows[0].geometry_candidate_budget : int = 200
detail.rows[0].geometry_candidates_attempted : int = 600
detail.rows[0].single_agent_calibration_rounds : int = 3
detail.rows[0].solo_flights_run : int = 36
detail.rows[0].selected_candidate_index : int = 907
detail.rows[0].rehearsal : dict(8)
detail.rows[0].rehearsal.status : str = "passed"
detail.rows[0].rehearsal.category : NoneType = null
detail.rows[0].rehearsal.agents : dict(12)
detail.rows[0].rehearsal.agents.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : dict(6)
detail.rows[0].rehearsal.agents.uav_01.group_id : str = "task_group_01"
detail.rows[0].rehearsal.agents.uav_01.result : dict(2)
detail.rows[0].rehearsal.agents.uav_01.result.status : str = "success"
detail.rows[0].rehearsal.agents.uav_01.result.conditions : dict(3)
detail.rows[0].rehearsal.agents.uav_01.result.conditions.entered_protected : bool = true
detail.rows[0].rehearsal.agents.uav_01.result.conditions.near_facility_contour : bool = true
detail.rows[0].rehearsal.agents.uav_01.result.conditions.exclusion_policy_respected : bool = true
detail.rows[0].rehearsal.agents.uav_01.core_event : dict(9)
detail.rows[0].rehearsal.agents.uav_01.core_event.raw_event_type : str = "enter_protected_zone"
detail.rows[0].rehearsal.agents.uav_01.core_event.role_core_event : str = "start_core_operation"
detail.rows[0].rehearsal.agents.uav_01.core_event.t_s : float = 479.1
detail.rows[0].rehearsal.agents.uav_01.core_event.frame_index : int = 4791
detail.rows[0].rehearsal.agents.uav_01.core_event.status : str = "known"
detail.rows[0].rehearsal.agents.uav_01.core_event.source : str = "truth.csv:10Hz_half_open_sim_clock"
detail.rows[0].rehearsal.agents.uav_01.core_event.resolution_s : float = 0.1
detail.rows[0].rehearsal.agents.uav_01.core_event.t_confirm : float = 479.1
detail.rows[0].rehearsal.agents.uav_01.core_event.confirm_frame_index : int = 4791
detail.rows[0].rehearsal.agents.uav_01.execution_status : str = "timeout"
detail.rows[0].rehearsal.agents.uav_01.completion_time_s : NoneType = null
detail.rows[0].rehearsal.agents.uav_01.last_sample_s : float = 1492.4
detail.rows[0].rehearsal.groups : dict(3)
detail.rows[0].rehearsal.groups.task_group_01  (同类键 `task_group_#` 共 3 个，只展开第一个) : dict(3)
detail.rows[0].rehearsal.groups.task_group_01.core_times_s : dict(4)
detail.rows[0].rehearsal.groups.task_group_01.core_times_s.uav_01  (同类键 `uav_#` 共 4 个，只展开第一个) : float
detail.rows[0].rehearsal.groups.task_group_01.shared_coverage : NoneType = null
detail.rows[0].rehearsal.groups.task_group_01.status : str = "success"
detail.rows[0].rehearsal.failures : list(0)
detail.rows[0].rehearsal.core_times_s : dict(12)
detail.rows[0].rehearsal.core_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
detail.rows[0].rehearsal.completion_times_s : dict(12)
detail.rows[0].rehearsal.completion_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : NoneType
detail.rows[0].rehearsal.completion_budget_basis : str = "conservative"
detail.rows[0].timing_selection : dict(2)
detail.rows[0].timing_selection.synchronous : dict(3)
detail.rows[0].timing_selection.synchronous.accepted_draw : int = 0
detail.rows[0].timing_selection.synchronous.rejected_count : int = 0
detail.rows[0].timing_selection.synchronous.attempts : list(1)
detail.rows[0].timing_selection.synchronous.attempts[0].draw : int = 0
detail.rows[0].timing_selection.synchronous.attempts[0].status : str = "passed"
detail.rows[0].timing_selection.synchronous.attempts[0].minimum_m : float = 13.880259691531377
detail.rows[0].timing_selection.synchronous.attempts[0].closest_pair : dict(3)
detail.rows[0].timing_selection.synchronous.attempts[0].closest_pair.agents : list(2)
detail.rows[0].timing_selection.synchronous.attempts[0].closest_pair.frame_index : int = 970
detail.rows[0].timing_selection.synchronous.attempts[0].closest_pair.t_s : float = 97.0
detail.rows[0].timing_selection.synchronous.attempts[0].frames_checked : int = 16694
detail.rows[0].timing_selection.synchronous.attempts[0].below_warning : bool = false
detail.rows[0].timing_selection.synchronous.attempts[0].predicted_end_s : float = 1669.3
detail.rows[0].timing_selection.sequential : dict(3)
detail.rows[0].timing_selection.sequential.accepted_draw : int = 0
detail.rows[0].timing_selection.sequential.rejected_count : int = 0
detail.rows[0].timing_selection.sequential.attempts : list(1)
detail.rows[0].timing_selection.sequential.attempts[0].draw : int = 0
detail.rows[0].timing_selection.sequential.attempts[0].status : str = "passed"
detail.rows[0].timing_selection.sequential.attempts[0].minimum_m : float = 5.421261945348796
detail.rows[0].timing_selection.sequential.attempts[0].closest_pair : dict(3)
detail.rows[0].timing_selection.sequential.attempts[0].closest_pair.agents : list(2)
detail.rows[0].timing_selection.sequential.attempts[0].closest_pair.frame_index : int = 9766
detail.rows[0].timing_selection.sequential.attempts[0].closest_pair.t_s : float = 976.6
detail.rows[0].timing_selection.sequential.attempts[0].frames_checked : int = 16713
detail.rows[0].timing_selection.sequential.attempts[0].below_warning : bool = false
detail.rows[0].timing_selection.sequential.attempts[0].predicted_end_s : float = 1671.2
detail.rows[0].solo_overlay_prediction_error : dict(10)
detail.rows[0].solo_overlay_prediction_error.prediction : dict(5)
detail.rows[0].solo_overlay_prediction_error.prediction.minimum_m : float = 13.880259691531377
detail.rows[0].solo_overlay_prediction_error.prediction.closest_pair : dict(3)
detail.rows[0].solo_overlay_prediction_error.prediction.closest_pair.agents : list(2)
detail.rows[0].solo_overlay_prediction_error.prediction.closest_pair.frame_index : int = 970
detail.rows[0].solo_overlay_prediction_error.prediction.closest_pair.t_s : float = 97.0
detail.rows[0].solo_overlay_prediction_error.prediction.frames_checked : int = 16694
detail.rows[0].solo_overlay_prediction_error.prediction.below_warning : bool = false
detail.rows[0].solo_overlay_prediction_error.prediction.predicted_end_s : float = 1669.3
detail.rows[0].solo_overlay_prediction_error.actual : dict(4)
detail.rows[0].solo_overlay_prediction_error.actual.minimum_m : float = 13.880259653638735
detail.rows[0].solo_overlay_prediction_error.actual.closest_pair : dict(3)
detail.rows[0].solo_overlay_prediction_error.actual.closest_pair.agents : list(2)
detail.rows[0].solo_overlay_prediction_error.actual.closest_pair.frame_index : int = 970
detail.rows[0].solo_overlay_prediction_error.actual.closest_pair.t_s : float = 97.0
detail.rows[0].solo_overlay_prediction_error.actual.frames_checked : int = 26842
detail.rows[0].solo_overlay_prediction_error.actual.below_warning : bool = false
detail.rows[0].solo_overlay_prediction_error.minimum_error_predicted_minus_actual_m : float = 3.7892641913117586e-08
detail.rows[0].solo_overlay_prediction_error.position_error_p95_m : float = 0.7360104515788154
detail.rows[0].solo_overlay_prediction_error.position_error_max_m : float = 0.7407474112221633
detail.rows[0].solo_overlay_prediction_error.actual_end_s : float = 2684.1
detail.rows[0].solo_overlay_prediction_error.separation_classification_matches : bool = true
detail.rows[0].solo_overlay_prediction_error.separation_threshold_m : float = 2.0
detail.rows[0].solo_overlay_prediction_error.segments : dict(2)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end : dict(3)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted : dict(2)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.minimum_m : float = 13.880259691531377
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair : dict(3)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.agents : list(2)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.frame_index : int = 970
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.t_s : float = 97.0
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual : dict(2)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.minimum_m : float = 13.880259653638735
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair : dict(3)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.agents : list(2)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.frame_index : int = 970
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.t_s : float = 97.0
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.minimum_error_predicted_minus_actual_m : float = 3.7892641913117586e-08
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end : dict(3)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted : dict(2)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.minimum_m : float = 24.918186091386023
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair : dict(3)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.agents : list(2)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.frame_index : int = 10197
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.t_s : float = 1019.7
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual : dict(2)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.minimum_m : float = 24.917802348202063
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair : dict(3)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.agents : list(2)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.frame_index : int = 10488
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.t_s : float = 1048.8
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.minimum_error_predicted_minus_actual_m : float = 0.00038374318395995033
detail.rows[0].solo_overlay_prediction_error.segment_definition : str = "before: both members remain within shifted recorded solo...
detail.rows[0].timing_diagnostics : dict(4)
detail.rows[0].timing_diagnostics.mode : str = "synchronous"
detail.rows[0].timing_diagnostics.accepted_draw : int = 0
detail.rows[0].timing_diagnostics.rejected_count : int = 0
detail.rows[0].timing_diagnostics.by_group : dict(3)
detail.rows[0].timing_diagnostics.by_group.task_group_01  (同类键 `task_group_#` 共 3 个，只展开第一个) : dict(6)
detail.rows[0].timing_diagnostics.by_group.task_group_01.draw : int = 0
detail.rows[0].timing_diagnostics.by_group.task_group_01.random_seed : int = 16624748680354615064
detail.rows[0].timing_diagnostics.by_group.task_group_01.jitter_span_s : float = 3.1124320651782904
detail.rows[0].timing_diagnostics.by_group.task_group_01.batch_count : int = 1
detail.rows[0].timing_diagnostics.by_group.task_group_01.batch_spans_s : list(1)
detail.rows[0].timing_diagnostics.by_group.task_group_01.inter_batch_gaps_s : list(0)
detail.rows[0].rehearsal_inconsistency : dict(3)
detail.rows[0].rehearsal_inconsistency.agent_count : int = 0
detail.rows[0].rehearsal_inconsistency.condition_difference_agent_count : int = 0
detail.rows[0].rehearsal_inconsistency.agents : list(0)
detail.elapsed_wall_s : float = 1094.280999999999
paired : bool = false
first_failure : dict(2)
first_failure.stage : str = "execution"
first_failure.reason : str = "timeout"
rows : list(2)
rows[0].episode_id : str = "family_s15_3de8b14ca62da9ba_ext_009_regular_synchronous"
rows[0].family_id : str = "family_s15_3de8b14ca62da9ba"
rows[0].skeleton_id : str = "family_s15_3de8b14ca62da9ba_ext_009_regular"
rows[0].intent : str = "penetration"
rows[0].mode : str = "synchronous"
rows[0].aborted : bool = false
rows[0].diagnostic_only : bool = false
rows[0].common_slot : int = 1
rows[0].state : str = "generated"
rows[0].reason : NoneType = null
rows[0].path : str = "family_s15_3de8b14ca62da9ba_ext_009_regular/synchronous"
rows[0].quality_valid : bool = true
rows[0].audit_passed : bool = true
rows[0].task_result : str = "success"
rows[0].agent_ids : list(12)
rows[0].condition_digest : str = "57412e036e7745cca6c52c95bb94ea4add8749322843411602b956c5...
rows[0].scene_digest : str = "162cf9cc4ec9ab906c18d266567e39f3789b1e36b83b6d5481ece627...
rows[0].group_count : int = 3
rows[0].groups : dict(3)
rows[0].groups.task_group_01  (同类键 `task_group_#` 共 3 个，只展开第一个) : dict(9)
rows[0].groups.task_group_01.role : str = "intrusion"
rows[0].groups.task_group_01.execution_method : str = "intrusion"
rows[0].groups.task_group_01.target_id : str = "facility_02"
rows[0].groups.task_group_01.members : list(4)
rows[0].groups.task_group_01.formation_split_count : int = 2
rows[0].groups.task_group_01.approach_span_deg : float = 133.29509104341173
rows[0].groups.task_group_01.coordination : dict(9)
rows[0].groups.task_group_01.coordination.scope : str = "task_group"
rows[0].groups.task_group_01.coordination.event_type : str = "start_core_operation"
rows[0].groups.task_group_01.coordination.source : str = "truth.csv:10Hz_half_open_sim_clock"
rows[0].groups.task_group_01.coordination.sync_window_s : float = 10.0
rows[0].groups.task_group_01.coordination.batch_split_gap_s : float = 20.0
rows[0].groups.task_group_01.coordination.event_times_s : dict(4)
rows[0].groups.task_group_01.coordination.event_times_s.uav_01  (同类键 `uav_#` 共 4 个，只展开第一个) : float
rows[0].groups.task_group_01.coordination.event_range_s : float = 3.1
rows[0].groups.task_group_01.coordination.batches : list(1)
rows[0].groups.task_group_01.coordination.batches[0].batch_index : int = 0
rows[0].groups.task_group_01.coordination.batches[0].members : list(4)
rows[0].groups.task_group_01.coordination.batches[0].start_s : float = 656.0
rows[0].groups.task_group_01.coordination.batches[0].end_s : float = 659.1
rows[0].groups.task_group_01.coordination.batches[0].span_s : float = 3.1
rows[0].groups.task_group_01.coordination.classification : str = "synchronous"
rows[0].groups.task_group_01.timing_diagnostics : dict(2)
rows[0].groups.task_group_01.timing_diagnostics.coordination_matches_assignment : bool = true
rows[0].groups.task_group_01.timing_diagnostics.batch_members_match_assignment : bool = true
rows[0].groups.task_group_01.result : dict(2)
rows[0].groups.task_group_01.result.status : str = "success"
rows[0].groups.task_group_01.result.conditions : dict(1)
rows[0].groups.task_group_01.result.conditions.member_contributions_complete : bool = true
rows[0].coordination_by_group : dict(3)
rows[0].coordination_by_group.task_group_01  (同类键 `task_group_#` 共 3 个，只展开第一个) : str
rows[0].approach_mode : str = "multi_direction"
rows[0].duration_s : float = 2684.2
rows[0].minimum_separation_m : float = 13.880259653638735
rows[0].execution_status : str = "timeout"
rows[0].time_budget : dict(6)
rows[0].time_budget.basis : str = "conservative bootstrap: settle + 2*route_length/speed + ...
rows[0].time_budget.single_agent_completion_s : dict(12)
rows[0].time_budget.single_agent_completion_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rows[0].time_budget.planned_completion_times_s : dict(12)
rows[0].time_budget.planned_completion_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rows[0].time_budget.latest_planned_completion_s : float = 2236.791803265592
rows[0].time_budget.margin_s : float = 447.35836065311844
rows[0].time_budget.max_duration_s : float = 2684.2
rows[0].coordination_matches : bool = true
rows[0].batch_members_match : bool = true
rows[0].audit : dict(7)
rows[0].audit.independent_status : str = "PASS"
rows[0].audit.region_difference_count : int = 0
rows[0].audit.target_difference_count : int = 0
rows[0].audit.event_or_metric_difference_count : int = 0
rows[0].audit.uncovered_conditions : list(0)
rows[0].audit.input_whitelist_passed : bool = true
rows[0].audit.id_aligned_permutation_invariant : bool = true
rows[0].truncation : dict(3)
rows[0].truncation.task_group_01  (同类键 `task_group_#` 共 3 个，只展开第一个) : dict(7)
rows[0].truncation.task_group_01.status : str = "PASS"
rows[0].truncation.task_group_01.full_verdict : str = "yes"
rows[0].truncation.task_group_01.prefix_verdict : str = "unknown"
rows[0].truncation.task_group_01.cutoff_s : float = 670.5
rows[0].truncation.task_group_01.protocol : str = "offline_half_work_truncation"
rows[0].truncation.task_group_01.prefix_event_frames : dict(4)
rows[0].truncation.task_group_01.prefix_event_frames.uav_01  (同类键 `uav_#` 共 4 个，只展开第一个) : int
rows[0].truncation.task_group_01.measured_work_interval_s : list(2)
rows[0].event_times_s : dict(12)
rows[0].event_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rows[0].simulation_wall_s : float = 161.62962960000004
rows[0].amortized_skeleton_setup_s : float = 346.06180394999956
rows[0].episode_postprocess_wall_s : float = 33.56169239999872
rows[0].primary_task_success : bool = true
rows[0].all_groups_complete : bool = true
rows[0].quality_status : str = "valid"
rows[0].measured_approach_by_group : dict(3)
rows[0].measured_approach_by_group.task_group_01  (同类键 `task_group_#` 共 3 个，只展开第一个) : str
rows[0].geometry_candidate_budget : int = 200
rows[0].geometry_candidates_attempted : int = 600
rows[0].single_agent_calibration_rounds : int = 3
rows[0].solo_flights_run : int = 36
rows[0].selected_candidate_index : int = 907
rows[0].rehearsal : dict(8)
rows[0].rehearsal.status : str = "passed"
rows[0].rehearsal.category : NoneType = null
rows[0].rehearsal.agents : dict(12)
rows[0].rehearsal.agents.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : dict(6)
rows[0].rehearsal.agents.uav_01.group_id : str = "task_group_01"
rows[0].rehearsal.agents.uav_01.result : dict(2)
rows[0].rehearsal.agents.uav_01.result.status : str = "success"
rows[0].rehearsal.agents.uav_01.result.conditions : dict(3)
rows[0].rehearsal.agents.uav_01.result.conditions.entered_protected : bool = true
rows[0].rehearsal.agents.uav_01.result.conditions.near_facility_contour : bool = true
rows[0].rehearsal.agents.uav_01.result.conditions.exclusion_policy_respected : bool = true
rows[0].rehearsal.agents.uav_01.core_event : dict(9)
rows[0].rehearsal.agents.uav_01.core_event.raw_event_type : str = "enter_protected_zone"
rows[0].rehearsal.agents.uav_01.core_event.role_core_event : str = "start_core_operation"
rows[0].rehearsal.agents.uav_01.core_event.t_s : float = 479.1
rows[0].rehearsal.agents.uav_01.core_event.frame_index : int = 4791
rows[0].rehearsal.agents.uav_01.core_event.status : str = "known"
rows[0].rehearsal.agents.uav_01.core_event.source : str = "truth.csv:10Hz_half_open_sim_clock"
rows[0].rehearsal.agents.uav_01.core_event.resolution_s : float = 0.1
rows[0].rehearsal.agents.uav_01.core_event.t_confirm : float = 479.1
rows[0].rehearsal.agents.uav_01.core_event.confirm_frame_index : int = 4791
rows[0].rehearsal.agents.uav_01.execution_status : str = "timeout"
rows[0].rehearsal.agents.uav_01.completion_time_s : NoneType = null
rows[0].rehearsal.agents.uav_01.last_sample_s : float = 1492.4
rows[0].rehearsal.groups : dict(3)
rows[0].rehearsal.groups.task_group_01  (同类键 `task_group_#` 共 3 个，只展开第一个) : dict(3)
rows[0].rehearsal.groups.task_group_01.core_times_s : dict(4)
rows[0].rehearsal.groups.task_group_01.core_times_s.uav_01  (同类键 `uav_#` 共 4 个，只展开第一个) : float
rows[0].rehearsal.groups.task_group_01.shared_coverage : NoneType = null
rows[0].rehearsal.groups.task_group_01.status : str = "success"
rows[0].rehearsal.failures : list(0)
rows[0].rehearsal.core_times_s : dict(12)
rows[0].rehearsal.core_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rows[0].rehearsal.completion_times_s : dict(12)
rows[0].rehearsal.completion_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : NoneType
rows[0].rehearsal.completion_budget_basis : str = "conservative"
rows[0].timing_selection : dict(2)
rows[0].timing_selection.synchronous : dict(3)
rows[0].timing_selection.synchronous.accepted_draw : int = 0
rows[0].timing_selection.synchronous.rejected_count : int = 0
rows[0].timing_selection.synchronous.attempts : list(1)
rows[0].timing_selection.synchronous.attempts[0].draw : int = 0
rows[0].timing_selection.synchronous.attempts[0].status : str = "passed"
rows[0].timing_selection.synchronous.attempts[0].minimum_m : float = 13.880259691531377
rows[0].timing_selection.synchronous.attempts[0].closest_pair : dict(3)
rows[0].timing_selection.synchronous.attempts[0].closest_pair.agents : list(2)
rows[0].timing_selection.synchronous.attempts[0].closest_pair.frame_index : int = 970
rows[0].timing_selection.synchronous.attempts[0].closest_pair.t_s : float = 97.0
rows[0].timing_selection.synchronous.attempts[0].frames_checked : int = 16694
rows[0].timing_selection.synchronous.attempts[0].below_warning : bool = false
rows[0].timing_selection.synchronous.attempts[0].predicted_end_s : float = 1669.3
rows[0].timing_selection.sequential : dict(3)
rows[0].timing_selection.sequential.accepted_draw : int = 0
rows[0].timing_selection.sequential.rejected_count : int = 0
rows[0].timing_selection.sequential.attempts : list(1)
rows[0].timing_selection.sequential.attempts[0].draw : int = 0
rows[0].timing_selection.sequential.attempts[0].status : str = "passed"
rows[0].timing_selection.sequential.attempts[0].minimum_m : float = 5.421261945348796
rows[0].timing_selection.sequential.attempts[0].closest_pair : dict(3)
rows[0].timing_selection.sequential.attempts[0].closest_pair.agents : list(2)
rows[0].timing_selection.sequential.attempts[0].closest_pair.frame_index : int = 9766
rows[0].timing_selection.sequential.attempts[0].closest_pair.t_s : float = 976.6
rows[0].timing_selection.sequential.attempts[0].frames_checked : int = 16713
rows[0].timing_selection.sequential.attempts[0].below_warning : bool = false
rows[0].timing_selection.sequential.attempts[0].predicted_end_s : float = 1671.2
rows[0].solo_overlay_prediction_error : dict(10)
rows[0].solo_overlay_prediction_error.prediction : dict(5)
rows[0].solo_overlay_prediction_error.prediction.minimum_m : float = 13.880259691531377
rows[0].solo_overlay_prediction_error.prediction.closest_pair : dict(3)
rows[0].solo_overlay_prediction_error.prediction.closest_pair.agents : list(2)
rows[0].solo_overlay_prediction_error.prediction.closest_pair.frame_index : int = 970
rows[0].solo_overlay_prediction_error.prediction.closest_pair.t_s : float = 97.0
rows[0].solo_overlay_prediction_error.prediction.frames_checked : int = 16694
rows[0].solo_overlay_prediction_error.prediction.below_warning : bool = false
rows[0].solo_overlay_prediction_error.prediction.predicted_end_s : float = 1669.3
rows[0].solo_overlay_prediction_error.actual : dict(4)
rows[0].solo_overlay_prediction_error.actual.minimum_m : float = 13.880259653638735
rows[0].solo_overlay_prediction_error.actual.closest_pair : dict(3)
rows[0].solo_overlay_prediction_error.actual.closest_pair.agents : list(2)
rows[0].solo_overlay_prediction_error.actual.closest_pair.frame_index : int = 970
rows[0].solo_overlay_prediction_error.actual.closest_pair.t_s : float = 97.0
rows[0].solo_overlay_prediction_error.actual.frames_checked : int = 26842
rows[0].solo_overlay_prediction_error.actual.below_warning : bool = false
rows[0].solo_overlay_prediction_error.minimum_error_predicted_minus_actual_m : float = 3.7892641913117586e-08
rows[0].solo_overlay_prediction_error.position_error_p95_m : float = 0.7360104515788154
rows[0].solo_overlay_prediction_error.position_error_max_m : float = 0.7407474112221633
rows[0].solo_overlay_prediction_error.actual_end_s : float = 2684.1
rows[0].solo_overlay_prediction_error.separation_classification_matches : bool = true
rows[0].solo_overlay_prediction_error.separation_threshold_m : float = 2.0
rows[0].solo_overlay_prediction_error.segments : dict(2)
rows[0].solo_overlay_prediction_error.segments.before_solo_end : dict(3)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted : dict(2)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.minimum_m : float = 13.880259691531377
rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair : dict(3)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.agents : list(2)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.frame_index : int = 970
rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.t_s : float = 97.0
rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual : dict(2)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.minimum_m : float = 13.880259653638735
rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair : dict(3)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.agents : list(2)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.frame_index : int = 970
rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.t_s : float = 97.0
rows[0].solo_overlay_prediction_error.segments.before_solo_end.minimum_error_predicted_minus_actual_m : float = 3.7892641913117586e-08
rows[0].solo_overlay_prediction_error.segments.after_solo_end : dict(3)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted : dict(2)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.minimum_m : float = 24.918186091386023
rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair : dict(3)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.agents : list(2)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.frame_index : int = 10197
rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.t_s : float = 1019.7
rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual : dict(2)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.minimum_m : float = 24.917802348202063
rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair : dict(3)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.agents : list(2)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.frame_index : int = 10488
rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.t_s : float = 1048.8
rows[0].solo_overlay_prediction_error.segments.after_solo_end.minimum_error_predicted_minus_actual_m : float = 0.00038374318395995033
rows[0].solo_overlay_prediction_error.segment_definition : str = "before: both members remain within shifted recorded solo...
rows[0].timing_diagnostics : dict(4)
rows[0].timing_diagnostics.mode : str = "synchronous"
rows[0].timing_diagnostics.accepted_draw : int = 0
rows[0].timing_diagnostics.rejected_count : int = 0
rows[0].timing_diagnostics.by_group : dict(3)
rows[0].timing_diagnostics.by_group.task_group_01  (同类键 `task_group_#` 共 3 个，只展开第一个) : dict(6)
rows[0].timing_diagnostics.by_group.task_group_01.draw : int = 0
rows[0].timing_diagnostics.by_group.task_group_01.random_seed : int = 16624748680354615064
rows[0].timing_diagnostics.by_group.task_group_01.jitter_span_s : float = 3.1124320651782904
rows[0].timing_diagnostics.by_group.task_group_01.batch_count : int = 1
rows[0].timing_diagnostics.by_group.task_group_01.batch_spans_s : list(1)
rows[0].timing_diagnostics.by_group.task_group_01.inter_batch_gaps_s : list(0)
rows[0].rehearsal_inconsistency : dict(3)
rows[0].rehearsal_inconsistency.agent_count : int = 0
rows[0].rehearsal_inconsistency.condition_difference_agent_count : int = 0
rows[0].rehearsal_inconsistency.agents : list(0)
elapsed_wall_s : float = 1094.280999999999
```

### status/C__*.json — PAIRED

文件：`v07_first_edition/prod_f020_060/status/C__family_s15_055e9333b067d2bc_ext_000_regular.json`

```
stage : str = "C"
skeleton_id : str = "family_s15_055e9333b067d2bc_ext_000_regular"
status : str = "PAIRED"
detail : dict(4)
detail.paired : bool = true
detail.first_failure : NoneType = null
detail.rows : list(2)
detail.rows[0].episode_id : str = "family_s15_055e9333b067d2bc_ext_000_regular_synchronous"
detail.rows[0].family_id : str = "family_s15_055e9333b067d2bc"
detail.rows[0].skeleton_id : str = "family_s15_055e9333b067d2bc_ext_000_regular"
detail.rows[0].intent : str = "transit"
detail.rows[0].mode : str = "synchronous"
detail.rows[0].aborted : bool = false
detail.rows[0].diagnostic_only : bool = false
detail.rows[0].common_slot : int = 0
detail.rows[0].state : str = "generated"
detail.rows[0].reason : NoneType = null
detail.rows[0].path : str = "family_s15_055e9333b067d2bc_ext_000_regular/synchronous"
detail.rows[0].quality_valid : bool = true
detail.rows[0].audit_passed : bool = true
detail.rows[0].task_result : str = "success"
detail.rows[0].agent_ids : list(12)
detail.rows[0].condition_digest : str = "b8d74f2ad21a8c248345c10d9f9526ca8b6109af9218f787926cc625...
detail.rows[0].scene_digest : str = "ba0fa0b51e5eeccdd74658829d592f11accda1a5fea8f84e1eb37c59...
detail.rows[0].group_count : int = 1
detail.rows[0].groups : dict(1)
detail.rows[0].groups.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(9)
detail.rows[0].groups.task_group_01.role : str = "transit"
detail.rows[0].groups.task_group_01.execution_method : str = "transit"
detail.rows[0].groups.task_group_01.target_id : str = "facility_01"
detail.rows[0].groups.task_group_01.members : list(12)
detail.rows[0].groups.task_group_01.formation_split_count : int = 2
detail.rows[0].groups.task_group_01.approach_span_deg : float = 166.06585669950186
detail.rows[0].groups.task_group_01.coordination : dict(9)
detail.rows[0].groups.task_group_01.coordination.scope : str = "task_group"
detail.rows[0].groups.task_group_01.coordination.event_type : str = "start_core_operation"
detail.rows[0].groups.task_group_01.coordination.source : str = "truth.csv:10Hz_half_open_sim_clock"
detail.rows[0].groups.task_group_01.coordination.sync_window_s : float = 10.0
detail.rows[0].groups.task_group_01.coordination.batch_split_gap_s : float = 20.0
detail.rows[0].groups.task_group_01.coordination.event_times_s : dict(12)
detail.rows[0].groups.task_group_01.coordination.event_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
detail.rows[0].groups.task_group_01.coordination.event_range_s : float = 5.8
detail.rows[0].groups.task_group_01.coordination.batches : list(1)
detail.rows[0].groups.task_group_01.coordination.batches[0].batch_index : int = 0
detail.rows[0].groups.task_group_01.coordination.batches[0].members : list(12)
detail.rows[0].groups.task_group_01.coordination.batches[0].start_s : float = 703.7
detail.rows[0].groups.task_group_01.coordination.batches[0].end_s : float = 709.5
detail.rows[0].groups.task_group_01.coordination.batches[0].span_s : float = 5.8
detail.rows[0].groups.task_group_01.coordination.classification : str = "synchronous"
detail.rows[0].groups.task_group_01.timing_diagnostics : dict(2)
detail.rows[0].groups.task_group_01.timing_diagnostics.coordination_matches_assignment : bool = true
detail.rows[0].groups.task_group_01.timing_diagnostics.batch_members_match_assignment : bool = true
detail.rows[0].groups.task_group_01.result : dict(2)
detail.rows[0].groups.task_group_01.result.status : str = "success"
detail.rows[0].groups.task_group_01.result.conditions : dict(1)
detail.rows[0].groups.task_group_01.result.conditions.member_contributions_complete : bool = true
detail.rows[0].coordination_by_group : dict(1)
detail.rows[0].coordination_by_group.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : str
detail.rows[0].approach_mode : str = "multi_direction"
detail.rows[0].duration_s : float = 902.22
detail.rows[0].minimum_separation_m : float = 18.19358650487551
detail.rows[0].execution_status : str = "completed"
detail.rows[0].time_budget : dict(6)
detail.rows[0].time_budget.basis : str = "single-agent completed endpoint hold on exported 10 Hz t...
detail.rows[0].time_budget.single_agent_completion_s : dict(12)
detail.rows[0].time_budget.single_agent_completion_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
detail.rows[0].time_budget.planned_completion_times_s : dict(12)
detail.rows[0].time_budget.planned_completion_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
detail.rows[0].time_budget.latest_planned_completion_s : float = 902.1999999999999
detail.rows[0].time_budget.margin_s : float = 180.44
detail.rows[0].time_budget.max_duration_s : float = 1082.7
detail.rows[0].coordination_matches : bool = true
detail.rows[0].batch_members_match : bool = true
detail.rows[0].audit : dict(7)
detail.rows[0].audit.independent_status : str = "PASS"
detail.rows[0].audit.region_difference_count : int = 0
detail.rows[0].audit.target_difference_count : int = 0
detail.rows[0].audit.event_or_metric_difference_count : int = 0
detail.rows[0].audit.uncovered_conditions : list(0)
detail.rows[0].audit.input_whitelist_passed : bool = true
detail.rows[0].audit.id_aligned_permutation_invariant : bool = true
detail.rows[0].truncation : dict(1)
detail.rows[0].truncation.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(7)
detail.rows[0].truncation.task_group_01.status : str = "PASS"
detail.rows[0].truncation.task_group_01.full_verdict : str = "yes"
detail.rows[0].truncation.task_group_01.prefix_verdict : str = "unknown"
detail.rows[0].truncation.task_group_01.cutoff_s : float = 787.2
detail.rows[0].truncation.task_group_01.protocol : str = "offline_half_work_truncation"
detail.rows[0].truncation.task_group_01.prefix_event_frames : dict(12)
detail.rows[0].truncation.task_group_01.prefix_event_frames.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : int
detail.rows[0].truncation.task_group_01.measured_work_interval_s : list(2)
detail.rows[0].event_times_s : dict(12)
detail.rows[0].event_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
detail.rows[0].simulation_wall_s : float = 81.42831500000011
detail.rows[0].amortized_skeleton_setup_s : float = 60.17495895000002
detail.rows[0].episode_postprocess_wall_s : float = 8.986188400000174
detail.rows[0].primary_task_success : bool = true
detail.rows[0].all_groups_complete : bool = true
detail.rows[0].quality_status : str = "valid"
detail.rows[0].measured_approach_by_group : dict(1)
detail.rows[0].measured_approach_by_group.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : str
detail.rows[0].geometry_candidate_budget : int = 200
detail.rows[0].geometry_candidates_attempted : int = 200
detail.rows[0].single_agent_calibration_rounds : int = 1
detail.rows[0].solo_flights_run : int = 12
detail.rows[0].selected_candidate_index : int = 11
detail.rows[0].rehearsal : dict(8)
detail.rows[0].rehearsal.status : str = "passed"
detail.rows[0].rehearsal.category : NoneType = null
detail.rows[0].rehearsal.agents : dict(12)
detail.rows[0].rehearsal.agents.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : dict(6)
detail.rows[0].rehearsal.agents.uav_01.group_id : str = "task_group_01"
detail.rows[0].rehearsal.agents.uav_01.result : dict(2)
detail.rows[0].rehearsal.agents.uav_01.result.status : str = "success"
detail.rows[0].rehearsal.agents.uav_01.result.conditions : dict(6)
detail.rows[0].rehearsal.agents.uav_01.result.conditions.entered_warning : bool = true
detail.rows[0].rehearsal.agents.uav_01.result.conditions.single_warning_visit : bool = true
detail.rows[0].rehearsal.agents.uav_01.result.conditions.no_dwell : bool = true
detail.rows[0].rehearsal.agents.uav_01.result.conditions.no_revisit : bool = true
detail.rows[0].rehearsal.agents.uav_01.result.conditions.ended_outside_warning : bool = true
detail.rows[0].rehearsal.agents.uav_01.result.conditions.exclusion_policy_respected : bool = true
detail.rows[0].rehearsal.agents.uav_01.core_event : dict(9)
detail.rows[0].rehearsal.agents.uav_01.core_event.raw_event_type : str = "enter_warning_zone"
detail.rows[0].rehearsal.agents.uav_01.core_event.role_core_event : str = "start_core_operation"
detail.rows[0].rehearsal.agents.uav_01.core_event.t_s : float = 327.4
detail.rows[0].rehearsal.agents.uav_01.core_event.frame_index : int = 3274
detail.rows[0].rehearsal.agents.uav_01.core_event.status : str = "known"
detail.rows[0].rehearsal.agents.uav_01.core_event.source : str = "truth.csv:10Hz_half_open_sim_clock"
detail.rows[0].rehearsal.agents.uav_01.core_event.resolution_s : float = 0.1
detail.rows[0].rehearsal.agents.uav_01.core_event.t_confirm : float = 327.4
detail.rows[0].rehearsal.agents.uav_01.core_event.confirm_frame_index : int = 3274
detail.rows[0].rehearsal.agents.uav_01.execution_status : str = "completed"
detail.rows[0].rehearsal.agents.uav_01.completion_time_s : float = 511.9
detail.rows[0].rehearsal.agents.uav_01.last_sample_s : float = 511.9
detail.rows[0].rehearsal.groups : dict(1)
detail.rows[0].rehearsal.groups.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(3)
detail.rows[0].rehearsal.groups.task_group_01.core_times_s : dict(12)
detail.rows[0].rehearsal.groups.task_group_01.core_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
detail.rows[0].rehearsal.groups.task_group_01.shared_coverage : NoneType = null
detail.rows[0].rehearsal.groups.task_group_01.status : str = "success"
detail.rows[0].rehearsal.failures : list(0)
detail.rows[0].rehearsal.core_times_s : dict(12)
detail.rows[0].rehearsal.core_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
detail.rows[0].rehearsal.completion_times_s : dict(12)
detail.rows[0].rehearsal.completion_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
detail.rows[0].rehearsal.completion_budget_basis : str = "measured"
detail.rows[0].timing_selection : dict(2)
detail.rows[0].timing_selection.synchronous : dict(3)
detail.rows[0].timing_selection.synchronous.accepted_draw : int = 0
detail.rows[0].timing_selection.synchronous.rejected_count : int = 0
detail.rows[0].timing_selection.synchronous.attempts : list(1)
detail.rows[0].timing_selection.synchronous.attempts[0].draw : int = 0
detail.rows[0].timing_selection.synchronous.attempts[0].status : str = "passed"
detail.rows[0].timing_selection.synchronous.attempts[0].minimum_m : float = 18.19468261245471
detail.rows[0].timing_selection.synchronous.attempts[0].closest_pair : dict(3)
detail.rows[0].timing_selection.synchronous.attempts[0].closest_pair.agents : list(2)
detail.rows[0].timing_selection.synchronous.attempts[0].closest_pair.frame_index : int = 6699
detail.rows[0].timing_selection.synchronous.attempts[0].closest_pair.t_s : float = 669.9
detail.rows[0].timing_selection.synchronous.attempts[0].frames_checked : int = 9023
detail.rows[0].timing_selection.synchronous.attempts[0].below_warning : bool = false
detail.rows[0].timing_selection.synchronous.attempts[0].predicted_end_s : float = 902.2
detail.rows[0].timing_selection.sequential : dict(3)
detail.rows[0].timing_selection.sequential.accepted_draw : int = 0
detail.rows[0].timing_selection.sequential.rejected_count : int = 0
detail.rows[0].timing_selection.sequential.attempts : list(1)
detail.rows[0].timing_selection.sequential.attempts[0].draw : int = 0
detail.rows[0].timing_selection.sequential.attempts[0].status : str = "passed"
detail.rows[0].timing_selection.sequential.attempts[0].minimum_m : float = 8.722593583026299
detail.rows[0].timing_selection.sequential.attempts[0].closest_pair : dict(3)
detail.rows[0].timing_selection.sequential.attempts[0].closest_pair.agents : list(2)
detail.rows[0].timing_selection.sequential.attempts[0].closest_pair.frame_index : int = 9636
detail.rows[0].timing_selection.sequential.attempts[0].closest_pair.t_s : float = 963.6
detail.rows[0].timing_selection.sequential.attempts[0].frames_checked : int = 13805
detail.rows[0].timing_selection.sequential.attempts[0].below_warning : bool = false
detail.rows[0].timing_selection.sequential.attempts[0].predicted_end_s : float = 1380.4
detail.rows[0].solo_overlay_prediction_error : dict(10)
detail.rows[0].solo_overlay_prediction_error.prediction : dict(5)
detail.rows[0].solo_overlay_prediction_error.prediction.minimum_m : float = 18.19468261245471
detail.rows[0].solo_overlay_prediction_error.prediction.closest_pair : dict(3)
detail.rows[0].solo_overlay_prediction_error.prediction.closest_pair.agents : list(2)
detail.rows[0].solo_overlay_prediction_error.prediction.closest_pair.frame_index : int = 6699
detail.rows[0].solo_overlay_prediction_error.prediction.closest_pair.t_s : float = 669.9
detail.rows[0].solo_overlay_prediction_error.prediction.frames_checked : int = 9023
detail.rows[0].solo_overlay_prediction_error.prediction.below_warning : bool = false
detail.rows[0].solo_overlay_prediction_error.prediction.predicted_end_s : float = 902.2
detail.rows[0].solo_overlay_prediction_error.actual : dict(4)
detail.rows[0].solo_overlay_prediction_error.actual.minimum_m : float = 18.19358650487551
detail.rows[0].solo_overlay_prediction_error.actual.closest_pair : dict(3)
detail.rows[0].solo_overlay_prediction_error.actual.closest_pair.agents : list(2)
detail.rows[0].solo_overlay_prediction_error.actual.closest_pair.frame_index : int = 6699
detail.rows[0].solo_overlay_prediction_error.actual.closest_pair.t_s : float = 669.9
detail.rows[0].solo_overlay_prediction_error.actual.frames_checked : int = 9023
detail.rows[0].solo_overlay_prediction_error.actual.below_warning : bool = false
detail.rows[0].solo_overlay_prediction_error.minimum_error_predicted_minus_actual_m : float = 0.0010961075792010888
detail.rows[0].solo_overlay_prediction_error.position_error_p95_m : float = 0.006783092715240968
detail.rows[0].solo_overlay_prediction_error.position_error_max_m : float = 3.3017360805949885
detail.rows[0].solo_overlay_prediction_error.actual_end_s : float = 902.2
detail.rows[0].solo_overlay_prediction_error.separation_classification_matches : bool = true
detail.rows[0].solo_overlay_prediction_error.separation_threshold_m : float = 2.0
detail.rows[0].solo_overlay_prediction_error.segments : dict(2)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end : dict(3)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted : dict(2)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.minimum_m : float = 18.19468261245471
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair : dict(3)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.agents : list(2)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.frame_index : int = 6699
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.t_s : float = 669.9
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual : dict(2)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.minimum_m : float = 18.19358650487551
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair : dict(3)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.agents : list(2)
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.frame_index : int = 6699
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.t_s : float = 669.9
detail.rows[0].solo_overlay_prediction_error.segments.before_solo_end.minimum_error_predicted_minus_actual_m : float = 0.0010961075792010888
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end : dict(3)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted : dict(2)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.minimum_m : float = 22.4081725411344
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair : dict(3)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.agents : list(2)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.frame_index : int = 8740
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.t_s : float = 874.0
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual : dict(2)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.minimum_m : float = 22.408192569137857
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair : dict(3)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.agents : list(2)
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.frame_index : int = 8693
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.t_s : float = 869.3
detail.rows[0].solo_overlay_prediction_error.segments.after_solo_end.minimum_error_predicted_minus_actual_m : float = -2.0028003454797272e-05
detail.rows[0].solo_overlay_prediction_error.segment_definition : str = "before: both members remain within shifted recorded solo...
detail.rows[0].timing_diagnostics : dict(4)
detail.rows[0].timing_diagnostics.mode : str = "synchronous"
detail.rows[0].timing_diagnostics.accepted_draw : int = 0
detail.rows[0].timing_diagnostics.rejected_count : int = 0
detail.rows[0].timing_diagnostics.by_group : dict(1)
detail.rows[0].timing_diagnostics.by_group.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(6)
detail.rows[0].timing_diagnostics.by_group.task_group_01.draw : int = 0
detail.rows[0].timing_diagnostics.by_group.task_group_01.random_seed : int = 5293166445879185529
detail.rows[0].timing_diagnostics.by_group.task_group_01.jitter_span_s : float = 5.848850528403337
detail.rows[0].timing_diagnostics.by_group.task_group_01.batch_count : int = 1
detail.rows[0].timing_diagnostics.by_group.task_group_01.batch_spans_s : list(1)
detail.rows[0].timing_diagnostics.by_group.task_group_01.inter_batch_gaps_s : list(0)
detail.rows[0].rehearsal_inconsistency : dict(3)
detail.rows[0].rehearsal_inconsistency.agent_count : int = 0
detail.rows[0].rehearsal_inconsistency.condition_difference_agent_count : int = 0
detail.rows[0].rehearsal_inconsistency.agents : list(0)
detail.elapsed_wall_s : float = 308.7650000000003
paired : bool = true
first_failure : NoneType = null
rows : list(2)
rows[0].episode_id : str = "family_s15_055e9333b067d2bc_ext_000_regular_synchronous"
rows[0].family_id : str = "family_s15_055e9333b067d2bc"
rows[0].skeleton_id : str = "family_s15_055e9333b067d2bc_ext_000_regular"
rows[0].intent : str = "transit"
rows[0].mode : str = "synchronous"
rows[0].aborted : bool = false
rows[0].diagnostic_only : bool = false
rows[0].common_slot : int = 0
rows[0].state : str = "generated"
rows[0].reason : NoneType = null
rows[0].path : str = "family_s15_055e9333b067d2bc_ext_000_regular/synchronous"
rows[0].quality_valid : bool = true
rows[0].audit_passed : bool = true
rows[0].task_result : str = "success"
rows[0].agent_ids : list(12)
rows[0].condition_digest : str = "b8d74f2ad21a8c248345c10d9f9526ca8b6109af9218f787926cc625...
rows[0].scene_digest : str = "ba0fa0b51e5eeccdd74658829d592f11accda1a5fea8f84e1eb37c59...
rows[0].group_count : int = 1
rows[0].groups : dict(1)
rows[0].groups.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(9)
rows[0].groups.task_group_01.role : str = "transit"
rows[0].groups.task_group_01.execution_method : str = "transit"
rows[0].groups.task_group_01.target_id : str = "facility_01"
rows[0].groups.task_group_01.members : list(12)
rows[0].groups.task_group_01.formation_split_count : int = 2
rows[0].groups.task_group_01.approach_span_deg : float = 166.06585669950186
rows[0].groups.task_group_01.coordination : dict(9)
rows[0].groups.task_group_01.coordination.scope : str = "task_group"
rows[0].groups.task_group_01.coordination.event_type : str = "start_core_operation"
rows[0].groups.task_group_01.coordination.source : str = "truth.csv:10Hz_half_open_sim_clock"
rows[0].groups.task_group_01.coordination.sync_window_s : float = 10.0
rows[0].groups.task_group_01.coordination.batch_split_gap_s : float = 20.0
rows[0].groups.task_group_01.coordination.event_times_s : dict(12)
rows[0].groups.task_group_01.coordination.event_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rows[0].groups.task_group_01.coordination.event_range_s : float = 5.8
rows[0].groups.task_group_01.coordination.batches : list(1)
rows[0].groups.task_group_01.coordination.batches[0].batch_index : int = 0
rows[0].groups.task_group_01.coordination.batches[0].members : list(12)
rows[0].groups.task_group_01.coordination.batches[0].start_s : float = 703.7
rows[0].groups.task_group_01.coordination.batches[0].end_s : float = 709.5
rows[0].groups.task_group_01.coordination.batches[0].span_s : float = 5.8
rows[0].groups.task_group_01.coordination.classification : str = "synchronous"
rows[0].groups.task_group_01.timing_diagnostics : dict(2)
rows[0].groups.task_group_01.timing_diagnostics.coordination_matches_assignment : bool = true
rows[0].groups.task_group_01.timing_diagnostics.batch_members_match_assignment : bool = true
rows[0].groups.task_group_01.result : dict(2)
rows[0].groups.task_group_01.result.status : str = "success"
rows[0].groups.task_group_01.result.conditions : dict(1)
rows[0].groups.task_group_01.result.conditions.member_contributions_complete : bool = true
rows[0].coordination_by_group : dict(1)
rows[0].coordination_by_group.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : str
rows[0].approach_mode : str = "multi_direction"
rows[0].duration_s : float = 902.22
rows[0].minimum_separation_m : float = 18.19358650487551
rows[0].execution_status : str = "completed"
rows[0].time_budget : dict(6)
rows[0].time_budget.basis : str = "single-agent completed endpoint hold on exported 10 Hz t...
rows[0].time_budget.single_agent_completion_s : dict(12)
rows[0].time_budget.single_agent_completion_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rows[0].time_budget.planned_completion_times_s : dict(12)
rows[0].time_budget.planned_completion_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rows[0].time_budget.latest_planned_completion_s : float = 902.1999999999999
rows[0].time_budget.margin_s : float = 180.44
rows[0].time_budget.max_duration_s : float = 1082.7
rows[0].coordination_matches : bool = true
rows[0].batch_members_match : bool = true
rows[0].audit : dict(7)
rows[0].audit.independent_status : str = "PASS"
rows[0].audit.region_difference_count : int = 0
rows[0].audit.target_difference_count : int = 0
rows[0].audit.event_or_metric_difference_count : int = 0
rows[0].audit.uncovered_conditions : list(0)
rows[0].audit.input_whitelist_passed : bool = true
rows[0].audit.id_aligned_permutation_invariant : bool = true
rows[0].truncation : dict(1)
rows[0].truncation.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(7)
rows[0].truncation.task_group_01.status : str = "PASS"
rows[0].truncation.task_group_01.full_verdict : str = "yes"
rows[0].truncation.task_group_01.prefix_verdict : str = "unknown"
rows[0].truncation.task_group_01.cutoff_s : float = 787.2
rows[0].truncation.task_group_01.protocol : str = "offline_half_work_truncation"
rows[0].truncation.task_group_01.prefix_event_frames : dict(12)
rows[0].truncation.task_group_01.prefix_event_frames.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : int
rows[0].truncation.task_group_01.measured_work_interval_s : list(2)
rows[0].event_times_s : dict(12)
rows[0].event_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rows[0].simulation_wall_s : float = 81.42831500000011
rows[0].amortized_skeleton_setup_s : float = 60.17495895000002
rows[0].episode_postprocess_wall_s : float = 8.986188400000174
rows[0].primary_task_success : bool = true
rows[0].all_groups_complete : bool = true
rows[0].quality_status : str = "valid"
rows[0].measured_approach_by_group : dict(1)
rows[0].measured_approach_by_group.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : str
rows[0].geometry_candidate_budget : int = 200
rows[0].geometry_candidates_attempted : int = 200
rows[0].single_agent_calibration_rounds : int = 1
rows[0].solo_flights_run : int = 12
rows[0].selected_candidate_index : int = 11
rows[0].rehearsal : dict(8)
rows[0].rehearsal.status : str = "passed"
rows[0].rehearsal.category : NoneType = null
rows[0].rehearsal.agents : dict(12)
rows[0].rehearsal.agents.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : dict(6)
rows[0].rehearsal.agents.uav_01.group_id : str = "task_group_01"
rows[0].rehearsal.agents.uav_01.result : dict(2)
rows[0].rehearsal.agents.uav_01.result.status : str = "success"
rows[0].rehearsal.agents.uav_01.result.conditions : dict(6)
rows[0].rehearsal.agents.uav_01.result.conditions.entered_warning : bool = true
rows[0].rehearsal.agents.uav_01.result.conditions.single_warning_visit : bool = true
rows[0].rehearsal.agents.uav_01.result.conditions.no_dwell : bool = true
rows[0].rehearsal.agents.uav_01.result.conditions.no_revisit : bool = true
rows[0].rehearsal.agents.uav_01.result.conditions.ended_outside_warning : bool = true
rows[0].rehearsal.agents.uav_01.result.conditions.exclusion_policy_respected : bool = true
rows[0].rehearsal.agents.uav_01.core_event : dict(9)
rows[0].rehearsal.agents.uav_01.core_event.raw_event_type : str = "enter_warning_zone"
rows[0].rehearsal.agents.uav_01.core_event.role_core_event : str = "start_core_operation"
rows[0].rehearsal.agents.uav_01.core_event.t_s : float = 327.4
rows[0].rehearsal.agents.uav_01.core_event.frame_index : int = 3274
rows[0].rehearsal.agents.uav_01.core_event.status : str = "known"
rows[0].rehearsal.agents.uav_01.core_event.source : str = "truth.csv:10Hz_half_open_sim_clock"
rows[0].rehearsal.agents.uav_01.core_event.resolution_s : float = 0.1
rows[0].rehearsal.agents.uav_01.core_event.t_confirm : float = 327.4
rows[0].rehearsal.agents.uav_01.core_event.confirm_frame_index : int = 3274
rows[0].rehearsal.agents.uav_01.execution_status : str = "completed"
rows[0].rehearsal.agents.uav_01.completion_time_s : float = 511.9
rows[0].rehearsal.agents.uav_01.last_sample_s : float = 511.9
rows[0].rehearsal.groups : dict(1)
rows[0].rehearsal.groups.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(3)
rows[0].rehearsal.groups.task_group_01.core_times_s : dict(12)
rows[0].rehearsal.groups.task_group_01.core_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rows[0].rehearsal.groups.task_group_01.shared_coverage : NoneType = null
rows[0].rehearsal.groups.task_group_01.status : str = "success"
rows[0].rehearsal.failures : list(0)
rows[0].rehearsal.core_times_s : dict(12)
rows[0].rehearsal.core_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rows[0].rehearsal.completion_times_s : dict(12)
rows[0].rehearsal.completion_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rows[0].rehearsal.completion_budget_basis : str = "measured"
rows[0].timing_selection : dict(2)
rows[0].timing_selection.synchronous : dict(3)
rows[0].timing_selection.synchronous.accepted_draw : int = 0
rows[0].timing_selection.synchronous.rejected_count : int = 0
rows[0].timing_selection.synchronous.attempts : list(1)
rows[0].timing_selection.synchronous.attempts[0].draw : int = 0
rows[0].timing_selection.synchronous.attempts[0].status : str = "passed"
rows[0].timing_selection.synchronous.attempts[0].minimum_m : float = 18.19468261245471
rows[0].timing_selection.synchronous.attempts[0].closest_pair : dict(3)
rows[0].timing_selection.synchronous.attempts[0].closest_pair.agents : list(2)
rows[0].timing_selection.synchronous.attempts[0].closest_pair.frame_index : int = 6699
rows[0].timing_selection.synchronous.attempts[0].closest_pair.t_s : float = 669.9
rows[0].timing_selection.synchronous.attempts[0].frames_checked : int = 9023
rows[0].timing_selection.synchronous.attempts[0].below_warning : bool = false
rows[0].timing_selection.synchronous.attempts[0].predicted_end_s : float = 902.2
rows[0].timing_selection.sequential : dict(3)
rows[0].timing_selection.sequential.accepted_draw : int = 0
rows[0].timing_selection.sequential.rejected_count : int = 0
rows[0].timing_selection.sequential.attempts : list(1)
rows[0].timing_selection.sequential.attempts[0].draw : int = 0
rows[0].timing_selection.sequential.attempts[0].status : str = "passed"
rows[0].timing_selection.sequential.attempts[0].minimum_m : float = 8.722593583026299
rows[0].timing_selection.sequential.attempts[0].closest_pair : dict(3)
rows[0].timing_selection.sequential.attempts[0].closest_pair.agents : list(2)
rows[0].timing_selection.sequential.attempts[0].closest_pair.frame_index : int = 9636
rows[0].timing_selection.sequential.attempts[0].closest_pair.t_s : float = 963.6
rows[0].timing_selection.sequential.attempts[0].frames_checked : int = 13805
rows[0].timing_selection.sequential.attempts[0].below_warning : bool = false
rows[0].timing_selection.sequential.attempts[0].predicted_end_s : float = 1380.4
rows[0].solo_overlay_prediction_error : dict(10)
rows[0].solo_overlay_prediction_error.prediction : dict(5)
rows[0].solo_overlay_prediction_error.prediction.minimum_m : float = 18.19468261245471
rows[0].solo_overlay_prediction_error.prediction.closest_pair : dict(3)
rows[0].solo_overlay_prediction_error.prediction.closest_pair.agents : list(2)
rows[0].solo_overlay_prediction_error.prediction.closest_pair.frame_index : int = 6699
rows[0].solo_overlay_prediction_error.prediction.closest_pair.t_s : float = 669.9
rows[0].solo_overlay_prediction_error.prediction.frames_checked : int = 9023
rows[0].solo_overlay_prediction_error.prediction.below_warning : bool = false
rows[0].solo_overlay_prediction_error.prediction.predicted_end_s : float = 902.2
rows[0].solo_overlay_prediction_error.actual : dict(4)
rows[0].solo_overlay_prediction_error.actual.minimum_m : float = 18.19358650487551
rows[0].solo_overlay_prediction_error.actual.closest_pair : dict(3)
rows[0].solo_overlay_prediction_error.actual.closest_pair.agents : list(2)
rows[0].solo_overlay_prediction_error.actual.closest_pair.frame_index : int = 6699
rows[0].solo_overlay_prediction_error.actual.closest_pair.t_s : float = 669.9
rows[0].solo_overlay_prediction_error.actual.frames_checked : int = 9023
rows[0].solo_overlay_prediction_error.actual.below_warning : bool = false
rows[0].solo_overlay_prediction_error.minimum_error_predicted_minus_actual_m : float = 0.0010961075792010888
rows[0].solo_overlay_prediction_error.position_error_p95_m : float = 0.006783092715240968
rows[0].solo_overlay_prediction_error.position_error_max_m : float = 3.3017360805949885
rows[0].solo_overlay_prediction_error.actual_end_s : float = 902.2
rows[0].solo_overlay_prediction_error.separation_classification_matches : bool = true
rows[0].solo_overlay_prediction_error.separation_threshold_m : float = 2.0
rows[0].solo_overlay_prediction_error.segments : dict(2)
rows[0].solo_overlay_prediction_error.segments.before_solo_end : dict(3)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted : dict(2)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.minimum_m : float = 18.19468261245471
rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair : dict(3)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.agents : list(2)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.frame_index : int = 6699
rows[0].solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.t_s : float = 669.9
rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual : dict(2)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.minimum_m : float = 18.19358650487551
rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair : dict(3)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.agents : list(2)
rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.frame_index : int = 6699
rows[0].solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.t_s : float = 669.9
rows[0].solo_overlay_prediction_error.segments.before_solo_end.minimum_error_predicted_minus_actual_m : float = 0.0010961075792010888
rows[0].solo_overlay_prediction_error.segments.after_solo_end : dict(3)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted : dict(2)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.minimum_m : float = 22.4081725411344
rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair : dict(3)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.agents : list(2)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.frame_index : int = 8740
rows[0].solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.t_s : float = 874.0
rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual : dict(2)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.minimum_m : float = 22.408192569137857
rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair : dict(3)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.agents : list(2)
rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.frame_index : int = 8693
rows[0].solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.t_s : float = 869.3
rows[0].solo_overlay_prediction_error.segments.after_solo_end.minimum_error_predicted_minus_actual_m : float = -2.0028003454797272e-05
rows[0].solo_overlay_prediction_error.segment_definition : str = "before: both members remain within shifted recorded solo...
rows[0].timing_diagnostics : dict(4)
rows[0].timing_diagnostics.mode : str = "synchronous"
rows[0].timing_diagnostics.accepted_draw : int = 0
rows[0].timing_diagnostics.rejected_count : int = 0
rows[0].timing_diagnostics.by_group : dict(1)
rows[0].timing_diagnostics.by_group.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(6)
rows[0].timing_diagnostics.by_group.task_group_01.draw : int = 0
rows[0].timing_diagnostics.by_group.task_group_01.random_seed : int = 5293166445879185529
rows[0].timing_diagnostics.by_group.task_group_01.jitter_span_s : float = 5.848850528403337
rows[0].timing_diagnostics.by_group.task_group_01.batch_count : int = 1
rows[0].timing_diagnostics.by_group.task_group_01.batch_spans_s : list(1)
rows[0].timing_diagnostics.by_group.task_group_01.inter_batch_gaps_s : list(0)
rows[0].rehearsal_inconsistency : dict(3)
rows[0].rehearsal_inconsistency.agent_count : int = 0
rows[0].rehearsal_inconsistency.condition_difference_agent_count : int = 0
rows[0].rehearsal_inconsistency.agents : list(0)
elapsed_wall_s : float = 308.7650000000003
```

### planning/<skeleton>/planning_result.json — B PASS

文件：`v07_first_edition/prod_f020_060/planning/family_s15_055e9333b067d2bc_ext_000_regular/planning_result.json`

```
skeleton_id : str = "family_s15_055e9333b067d2bc_ext_000_regular"
family_id : str = "family_s15_055e9333b067d2bc"
slot : int = 0
intent : str = "transit"
status : str = "PASS"
eligible_combinations : int = 79
rejection_reasons : dict(2)
rejection_reasons.whole_route_check : int = 53
rejection_reasons.connection_search_budget_exhausted : int = 68
group_rejection_reasons : dict(2)
group_rejection_reasons.whole_route_check : int = 53
group_rejection_reasons.connection_search_budget_exhausted : int = 68
combination_rejection_reasons : dict(0)
rejection_class_counts : dict(2)
rejection_class_counts.geometric_infeasibility : int = 53
rejection_class_counts.search_budget_exhausted : int = 68
termination : NoneType = null
selection : dict(7)
selection.minimum_approach_length_m : float = 34986.654794433474
selection.maximum_ratio : NoneType = null
selection.minimum_approach_length_by_group_m : dict(1)
selection.minimum_approach_length_by_group_m.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : float
selection.ratio_scope : str = "each task group independently within whole-episode feasi...
selection.feasible_candidates : int = 79
selection.eligible_candidates : int = 79
selection.selection_order : str = "feasible candidates -> configured same-direction length ...
planning_wall_s : float = 113.4369999999999
candidate_pool_sha256 : str = "b57ad1e76009ca80627eb93c6990d069ef236a495e8b9702440c1f01...
```

### planning/<skeleton>/planning_result.json — B REJECT

文件：`v07_first_edition/prod_f020_060/planning/family_s15_1b876e6b8b6f70c6_ext_000_regular/planning_result.json`

```
skeleton_id : str = "family_s15_1b876e6b8b6f70c6_ext_000_regular"
family_id : str = "family_s15_1b876e6b8b6f70c6"
slot : int = 0
intent : str = "transit"
status : str = "REJECT"
eligible_combinations : int = 0
rejection_reasons : dict(1)
rejection_reasons.connection_search_budget_exhausted : int = 200
group_rejection_reasons : dict(1)
group_rejection_reasons.connection_search_budget_exhausted : int = 200
combination_rejection_reasons : dict(0)
rejection_class_counts : dict(1)
rejection_class_counts.search_budget_exhausted : int = 200
termination : dict(5)
termination.classification : str = "search_budget_exhausted"
termination.scope : str = "skeleton_search"
termination.reason : str = "no_eligible_combination_in_registered_budgets"
termination.geometric_evidence : list(0)
termination.global_infeasibility_claimed : bool = false
selection : dict(3)
selection.minimum_approach_length_m : NoneType = null
selection.feasible_candidates : int = 0
selection.eligible_candidates : int = 0
planning_wall_s : float = 7.844000000000051
candidate_pool_sha256 : NoneType = null
```

### episodes/<skeleton>/<mode>/metrics.json

文件：`v07_first_edition/prod_f020_060/episodes/family_s15_055e9333b067d2bc_ext_000_regular/synchronous/metrics.json`

```
episode_id : str = "family_s15_055e9333b067d2bc_ext_000_regular_synchronous"
family_id : str = "family_s15_055e9333b067d2bc"
skeleton_id : str = "family_s15_055e9333b067d2bc_ext_000_regular"
intent : str = "transit"
mode : str = "synchronous"
aborted : bool = false
diagnostic_only : bool = false
common_slot : int = 0
state : str = "generated"
reason : NoneType = null
path : str = "family_s15_055e9333b067d2bc_ext_000_regular/synchronous"
quality_valid : bool = true
audit_passed : bool = true
task_result : str = "success"
agent_ids : list(12)
condition_digest : str = "b8d74f2ad21a8c248345c10d9f9526ca8b6109af9218f787926cc625...
scene_digest : str = "ba0fa0b51e5eeccdd74658829d592f11accda1a5fea8f84e1eb37c59...
group_count : int = 1
groups : dict(1)
groups.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(9)
groups.task_group_01.role : str = "transit"
groups.task_group_01.execution_method : str = "transit"
groups.task_group_01.target_id : str = "facility_01"
groups.task_group_01.members : list(12)
groups.task_group_01.formation_split_count : int = 2
groups.task_group_01.approach_span_deg : float = 166.06585669950186
groups.task_group_01.coordination : dict(9)
groups.task_group_01.coordination.scope : str = "task_group"
groups.task_group_01.coordination.event_type : str = "start_core_operation"
groups.task_group_01.coordination.source : str = "truth.csv:10Hz_half_open_sim_clock"
groups.task_group_01.coordination.sync_window_s : float = 10.0
groups.task_group_01.coordination.batch_split_gap_s : float = 20.0
groups.task_group_01.coordination.event_times_s : dict(12)
groups.task_group_01.coordination.event_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
groups.task_group_01.coordination.event_range_s : float = 5.8
groups.task_group_01.coordination.batches : list(1)
groups.task_group_01.coordination.batches[0].batch_index : int = 0
groups.task_group_01.coordination.batches[0].members : list(12)
groups.task_group_01.coordination.batches[0].start_s : float = 703.7
groups.task_group_01.coordination.batches[0].end_s : float = 709.5
groups.task_group_01.coordination.batches[0].span_s : float = 5.8
groups.task_group_01.coordination.classification : str = "synchronous"
groups.task_group_01.timing_diagnostics : dict(2)
groups.task_group_01.timing_diagnostics.coordination_matches_assignment : bool = true
groups.task_group_01.timing_diagnostics.batch_members_match_assignment : bool = true
groups.task_group_01.result : dict(2)
groups.task_group_01.result.status : str = "success"
groups.task_group_01.result.conditions : dict(1)
groups.task_group_01.result.conditions.member_contributions_complete : bool = true
coordination_by_group : dict(1)
coordination_by_group.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : str
approach_mode : str = "multi_direction"
duration_s : float = 902.22
minimum_separation_m : float = 18.19358650487551
execution_status : str = "completed"
time_budget : dict(6)
time_budget.basis : str = "single-agent completed endpoint hold on exported 10 Hz t...
time_budget.single_agent_completion_s : dict(12)
time_budget.single_agent_completion_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
time_budget.planned_completion_times_s : dict(12)
time_budget.planned_completion_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
time_budget.latest_planned_completion_s : float = 902.1999999999999
time_budget.margin_s : float = 180.44
time_budget.max_duration_s : float = 1082.7
coordination_matches : bool = true
batch_members_match : bool = true
audit : dict(7)
audit.independent_status : str = "PASS"
audit.region_difference_count : int = 0
audit.target_difference_count : int = 0
audit.event_or_metric_difference_count : int = 0
audit.uncovered_conditions : list(0)
audit.input_whitelist_passed : bool = true
audit.id_aligned_permutation_invariant : bool = true
truncation : dict(1)
truncation.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(7)
truncation.task_group_01.status : str = "PASS"
truncation.task_group_01.full_verdict : str = "yes"
truncation.task_group_01.prefix_verdict : str = "unknown"
truncation.task_group_01.cutoff_s : float = 787.2
truncation.task_group_01.protocol : str = "offline_half_work_truncation"
truncation.task_group_01.prefix_event_frames : dict(12)
truncation.task_group_01.prefix_event_frames.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : int
truncation.task_group_01.measured_work_interval_s : list(2)
event_times_s : dict(12)
event_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
simulation_wall_s : float = 81.42831500000011
amortized_skeleton_setup_s : float = 60.17495895000002
episode_postprocess_wall_s : float = 8.986188400000174
primary_task_success : bool = true
all_groups_complete : bool = true
quality_status : str = "valid"
measured_approach_by_group : dict(1)
measured_approach_by_group.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : str
geometry_candidate_budget : int = 200
geometry_candidates_attempted : int = 200
single_agent_calibration_rounds : int = 1
solo_flights_run : int = 12
selected_candidate_index : int = 11
rehearsal : dict(8)
rehearsal.status : str = "passed"
rehearsal.category : NoneType = null
rehearsal.agents : dict(12)
rehearsal.agents.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : dict(6)
rehearsal.agents.uav_01.group_id : str = "task_group_01"
rehearsal.agents.uav_01.result : dict(2)
rehearsal.agents.uav_01.result.status : str = "success"
rehearsal.agents.uav_01.result.conditions : dict(6)
rehearsal.agents.uav_01.result.conditions.entered_warning : bool = true
rehearsal.agents.uav_01.result.conditions.single_warning_visit : bool = true
rehearsal.agents.uav_01.result.conditions.no_dwell : bool = true
rehearsal.agents.uav_01.result.conditions.no_revisit : bool = true
rehearsal.agents.uav_01.result.conditions.ended_outside_warning : bool = true
rehearsal.agents.uav_01.result.conditions.exclusion_policy_respected : bool = true
rehearsal.agents.uav_01.core_event : dict(9)
rehearsal.agents.uav_01.core_event.raw_event_type : str = "enter_warning_zone"
rehearsal.agents.uav_01.core_event.role_core_event : str = "start_core_operation"
rehearsal.agents.uav_01.core_event.t_s : float = 327.4
rehearsal.agents.uav_01.core_event.frame_index : int = 3274
rehearsal.agents.uav_01.core_event.status : str = "known"
rehearsal.agents.uav_01.core_event.source : str = "truth.csv:10Hz_half_open_sim_clock"
rehearsal.agents.uav_01.core_event.resolution_s : float = 0.1
rehearsal.agents.uav_01.core_event.t_confirm : float = 327.4
rehearsal.agents.uav_01.core_event.confirm_frame_index : int = 3274
rehearsal.agents.uav_01.execution_status : str = "completed"
rehearsal.agents.uav_01.completion_time_s : float = 511.9
rehearsal.agents.uav_01.last_sample_s : float = 511.9
rehearsal.groups : dict(1)
rehearsal.groups.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(3)
rehearsal.groups.task_group_01.core_times_s : dict(12)
rehearsal.groups.task_group_01.core_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rehearsal.groups.task_group_01.shared_coverage : NoneType = null
rehearsal.groups.task_group_01.status : str = "success"
rehearsal.failures : list(0)
rehearsal.core_times_s : dict(12)
rehearsal.core_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rehearsal.completion_times_s : dict(12)
rehearsal.completion_times_s.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : float
rehearsal.completion_budget_basis : str = "measured"
timing_selection : dict(2)
timing_selection.synchronous : dict(3)
timing_selection.synchronous.accepted_draw : int = 0
timing_selection.synchronous.rejected_count : int = 0
timing_selection.synchronous.attempts : list(1)
timing_selection.synchronous.attempts[0].draw : int = 0
timing_selection.synchronous.attempts[0].status : str = "passed"
timing_selection.synchronous.attempts[0].minimum_m : float = 18.19468261245471
timing_selection.synchronous.attempts[0].closest_pair : dict(3)
timing_selection.synchronous.attempts[0].closest_pair.agents : list(2)
timing_selection.synchronous.attempts[0].closest_pair.frame_index : int = 6699
timing_selection.synchronous.attempts[0].closest_pair.t_s : float = 669.9
timing_selection.synchronous.attempts[0].frames_checked : int = 9023
timing_selection.synchronous.attempts[0].below_warning : bool = false
timing_selection.synchronous.attempts[0].predicted_end_s : float = 902.2
timing_selection.sequential : dict(3)
timing_selection.sequential.accepted_draw : int = 0
timing_selection.sequential.rejected_count : int = 0
timing_selection.sequential.attempts : list(1)
timing_selection.sequential.attempts[0].draw : int = 0
timing_selection.sequential.attempts[0].status : str = "passed"
timing_selection.sequential.attempts[0].minimum_m : float = 8.722593583026299
timing_selection.sequential.attempts[0].closest_pair : dict(3)
timing_selection.sequential.attempts[0].closest_pair.agents : list(2)
timing_selection.sequential.attempts[0].closest_pair.frame_index : int = 9636
timing_selection.sequential.attempts[0].closest_pair.t_s : float = 963.6
timing_selection.sequential.attempts[0].frames_checked : int = 13805
timing_selection.sequential.attempts[0].below_warning : bool = false
timing_selection.sequential.attempts[0].predicted_end_s : float = 1380.4
solo_overlay_prediction_error : dict(10)
solo_overlay_prediction_error.prediction : dict(5)
solo_overlay_prediction_error.prediction.minimum_m : float = 18.19468261245471
solo_overlay_prediction_error.prediction.closest_pair : dict(3)
solo_overlay_prediction_error.prediction.closest_pair.agents : list(2)
solo_overlay_prediction_error.prediction.closest_pair.frame_index : int = 6699
solo_overlay_prediction_error.prediction.closest_pair.t_s : float = 669.9
solo_overlay_prediction_error.prediction.frames_checked : int = 9023
solo_overlay_prediction_error.prediction.below_warning : bool = false
solo_overlay_prediction_error.prediction.predicted_end_s : float = 902.2
solo_overlay_prediction_error.actual : dict(4)
solo_overlay_prediction_error.actual.minimum_m : float = 18.19358650487551
solo_overlay_prediction_error.actual.closest_pair : dict(3)
solo_overlay_prediction_error.actual.closest_pair.agents : list(2)
solo_overlay_prediction_error.actual.closest_pair.frame_index : int = 6699
solo_overlay_prediction_error.actual.closest_pair.t_s : float = 669.9
solo_overlay_prediction_error.actual.frames_checked : int = 9023
solo_overlay_prediction_error.actual.below_warning : bool = false
solo_overlay_prediction_error.minimum_error_predicted_minus_actual_m : float = 0.0010961075792010888
solo_overlay_prediction_error.position_error_p95_m : float = 0.006783092715240968
solo_overlay_prediction_error.position_error_max_m : float = 3.3017360805949885
solo_overlay_prediction_error.actual_end_s : float = 902.2
solo_overlay_prediction_error.separation_classification_matches : bool = true
solo_overlay_prediction_error.separation_threshold_m : float = 2.0
solo_overlay_prediction_error.segments : dict(2)
solo_overlay_prediction_error.segments.before_solo_end : dict(3)
solo_overlay_prediction_error.segments.before_solo_end.predicted : dict(2)
solo_overlay_prediction_error.segments.before_solo_end.predicted.minimum_m : float = 18.19468261245471
solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair : dict(3)
solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.agents : list(2)
solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.frame_index : int = 6699
solo_overlay_prediction_error.segments.before_solo_end.predicted.closest_pair.t_s : float = 669.9
solo_overlay_prediction_error.segments.before_solo_end.actual : dict(2)
solo_overlay_prediction_error.segments.before_solo_end.actual.minimum_m : float = 18.19358650487551
solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair : dict(3)
solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.agents : list(2)
solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.frame_index : int = 6699
solo_overlay_prediction_error.segments.before_solo_end.actual.closest_pair.t_s : float = 669.9
solo_overlay_prediction_error.segments.before_solo_end.minimum_error_predicted_minus_actual_m : float = 0.0010961075792010888
solo_overlay_prediction_error.segments.after_solo_end : dict(3)
solo_overlay_prediction_error.segments.after_solo_end.predicted : dict(2)
solo_overlay_prediction_error.segments.after_solo_end.predicted.minimum_m : float = 22.4081725411344
solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair : dict(3)
solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.agents : list(2)
solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.frame_index : int = 8740
solo_overlay_prediction_error.segments.after_solo_end.predicted.closest_pair.t_s : float = 874.0
solo_overlay_prediction_error.segments.after_solo_end.actual : dict(2)
solo_overlay_prediction_error.segments.after_solo_end.actual.minimum_m : float = 22.408192569137857
solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair : dict(3)
solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.agents : list(2)
solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.frame_index : int = 8693
solo_overlay_prediction_error.segments.after_solo_end.actual.closest_pair.t_s : float = 869.3
solo_overlay_prediction_error.segments.after_solo_end.minimum_error_predicted_minus_actual_m : float = -2.0028003454797272e-05
solo_overlay_prediction_error.segment_definition : str = "before: both members remain within shifted recorded solo...
timing_diagnostics : dict(4)
timing_diagnostics.mode : str = "synchronous"
timing_diagnostics.accepted_draw : int = 0
timing_diagnostics.rejected_count : int = 0
timing_diagnostics.by_group : dict(1)
timing_diagnostics.by_group.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(6)
timing_diagnostics.by_group.task_group_01.draw : int = 0
timing_diagnostics.by_group.task_group_01.random_seed : int = 5293166445879185529
timing_diagnostics.by_group.task_group_01.jitter_span_s : float = 5.848850528403337
timing_diagnostics.by_group.task_group_01.batch_count : int = 1
timing_diagnostics.by_group.task_group_01.batch_spans_s : list(1)
timing_diagnostics.by_group.task_group_01.inter_batch_gaps_s : list(0)
rehearsal_inconsistency : dict(3)
rehearsal_inconsistency.agent_count : int = 0
rehearsal_inconsistency.condition_difference_agent_count : int = 0
rehearsal_inconsistency.agents : list(0)
```

### 补充：episodes/<skeleton>/candidate_search.json（规划阶段 search 报告的副本）

文件：`v07_first_edition/prod_f020_060/episodes/family_s15_055e9333b067d2bc_ext_000_regular/candidate_search.json`

```
candidate_budget : int = 200
candidate_budget_scope : str = "each task group independently"
attempted_candidates : int = 200
group_attempt_counts : dict(1)
group_attempt_counts.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : int
group_search_metrics : dict(1)
group_search_metrics.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(7)
group_search_metrics.task_group_01.attempts : int = 200
group_search_metrics.task_group_01.budget : int = 200
group_search_metrics.task_group_01.feasible_candidates : int = 79
group_search_metrics.task_group_01.wall_s : float = 113.32199059999948
group_search_metrics.task_group_01.geometry_wall_s : float = 113.32199059999948
group_search_metrics.task_group_01.backend : str = "unified"
group_search_metrics.task_group_01.phase_search : dict(2)
group_search_metrics.task_group_01.phase_search.evaluations : int = 0
group_search_metrics.task_group_01.phase_search.wall_s : float = 0.0
group_terminations : dict(1)
group_terminations.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : NoneType
group_feasible_candidate_indices : dict(1)
group_feasible_candidate_indices.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : list(79)
group_eligible_candidate_indices : dict(1)
group_eligible_candidate_indices.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : list(79)
combination_search : dict(6)
combination_search.budget : int = 1000
combination_search.total_possible : int = 79
combination_search.attempts : int = 79
combination_search.random_seed : int = 2852203402604058400
combination_search.sampling : str = "uniform without replacement over independent pool Cartes...
combination_search.wall_s : float = 0.06201819999932923
group_rejection_reasons : dict(2)
group_rejection_reasons.whole_route_check : int = 53
group_rejection_reasons.connection_search_budget_exhausted : int = 68
combination_rejection_reasons : dict(0)
rejection_reasons : dict(2)
rejection_reasons.whole_route_check : int = 53
rejection_reasons.connection_search_budget_exhausted : int = 68
rejection_class_counts : dict(2)
rejection_class_counts.geometric_infeasibility : int = 53
rejection_class_counts.search_budget_exhausted : int = 68
rejection_count_units : str = "group proposals and episode combinations; see separate c...
termination : NoneType = null
selection : dict(7)
selection.minimum_approach_length_m : float = 34986.654794433474
selection.maximum_ratio : NoneType = null
selection.minimum_approach_length_by_group_m : dict(1)
selection.minimum_approach_length_by_group_m.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : float
selection.ratio_scope : str = "each task group independently within whole-episode feasi...
selection.feasible_candidates : int = 79
selection.eligible_candidates : int = 79
selection.selection_order : str = "feasible candidates -> configured same-direction length ...
eligible_candidate_order : list(79)
max_single_agent_calibration_rounds : int = 5
solo_flights_run : int = 12
candidates : list(200)
candidates[0].candidate_index : int = 0
candidates[0].proposal_id : str = "task_group_01:0"
candidates[0].group_id : str = "task_group_01"
candidates[0].stage : str = "group_feasible"
candidates[0].reason : NoneType = null
candidates[0].rejection : NoneType = null
candidates[0].draws_by_group : dict(1)
candidates[0].draws_by_group.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : dict(2)
candidates[0].draws_by_group.task_group_01.proposal_seed : int = 2703285285244211435
candidates[0].draws_by_group.task_group_01.shape : dict(7)
candidates[0].draws_by_group.task_group_01.shape.direction_deg : float = 102.35283143207245
candidates[0].draws_by_group.task_group_01.shape.bend : bool = false
candidates[0].draws_by_group.task_group_01.shape.bend_angle_deg : float = 0.0
candidates[0].draws_by_group.task_group_01.shape.bend_sign : int = 1
candidates[0].draws_by_group.task_group_01.shape.split_draws : list(2)
candidates[0].draws_by_group.task_group_01.shape.split_draws[0].split_index : int = 0
candidates[0].draws_by_group.task_group_01.shape.split_draws[0].chord_quantile : float = 0.2389191070116553
candidates[0].draws_by_group.task_group_01.shape.split_draws[0].feasible_lateral_intervals_m : list(2)
candidates[0].draws_by_group.task_group_01.shape.split_draws[0].accepted_lateral_m : float = -5543.19621493392
candidates[0].draws_by_group.task_group_01.shape.shape_attempt : int = 0
candidates[0].draws_by_group.task_group_01.shape.rejected_shape_attempts : list(0)
candidates[0].whole_route_checks : dict(9)
candidates[0].whole_route_checks.status : str = "PASS"
candidates[0].whole_route_checks.issues : list(0)
candidates[0].whole_route_checks.members : dict(12)
candidates[0].whole_route_checks.members.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : dict(6)
candidates[0].whole_route_checks.members.uav_01.status : str = "PASS"
candidates[0].whole_route_checks.members.uav_01.issues : list(0)
candidates[0].whole_route_checks.members.uav_01.warning_intervals_route_m : list(1)
candidates[0].whole_route_checks.members.uav_01.first_warning_entry : dict(5)
candidates[0].whole_route_checks.members.uav_01.first_warning_entry.segment : int = 2
candidates[0].whole_route_checks.members.uav_01.first_warning_entry.distance_on_segment_m : float = 237.04946424288713
candidates[0].whole_route_checks.members.uav_01.first_warning_entry.point : list(2)
candidates[0].whole_route_checks.members.uav_01.first_warning_entry.direction : list(2)
candidates[0].whole_route_checks.members.uav_01.first_warning_entry.straight_before_warning_m : float = 237.04946424288713
candidates[0].whole_route_checks.members.uav_01.retreat_clearances_m : dict(3)
candidates[0].whole_route_checks.members.uav_01.retreat_clearances_m.facility_01_warning : float = 231.39875955152422
candidates[0].whole_route_checks.members.uav_01.retreat_clearances_m.facility_02_warning : float = 662.576738120559
candidates[0].whole_route_checks.members.uav_01.retreat_clearances_m.facility_03_warning : float = 2486.7072584774514
candidates[0].whole_route_checks.members.uav_01.segment_count : int = 3
candidates[0].whole_route_checks.scope : str = "all segments against original primitives; no nominal-spa...
candidates[0].whole_route_checks.multi_max_pairwise_ingress_heading_deg : float = 166.06585669950024
candidates[0].whole_route_checks.heading_aim_deg_diagnostic_only : float = 90.0
candidates[0].whole_route_checks.observed_minimum_separation_m : NoneType = null
candidates[0].whole_route_checks.observed_spacing_reason : str = "planning_only_no_simulation"
candidates[0].whole_route_checks.existing_precheck : dict(8)
candidates[0].whole_route_checks.existing_precheck.route_bundle : str = "PASS"
candidates[0].whole_route_checks.existing_precheck.polylines : dict(12)
candidates[0].whole_route_checks.existing_precheck.polylines.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : dict(3)
candidates[0].whole_route_checks.existing_precheck.polylines.uav_01.valid : bool = true
candidates[0].whole_route_checks.existing_precheck.polylines.uav_01.issues : list(0)
candidates[0].whole_route_checks.existing_precheck.polylines.uav_01.numerical_tolerance_m : float = 1e-06
candidates[0].whole_route_checks.existing_precheck.retreat_points : dict(12)
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : dict(4)
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.valid : bool = true
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.world_inward_clearance_m : float = 1757.532081738278
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances : dict(6)
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.facility_01_warning : dict(3)
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.facility_01_warning.clearance_m : float = 231.39875955152422
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.facility_01_warning.required_m : float = 50.0
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.facility_01_warning.valid : bool = true
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.facility_02_warning : dict(3)
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.facility_02_warning.clearance_m : float = 662.576738120559
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.facility_02_warning.required_m : float = 50.0
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.facility_02_warning.valid : bool = true
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.facility_03_warning : dict(3)
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.facility_03_warning.clearance_m : float = 2486.7072584774514
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.facility_03_warning.required_m : float = 50.0
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.facility_03_warning.valid : bool = true
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.obstacle_01 : dict(3)
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.obstacle_01.clearance_m : float = 1809.529262767409
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.obstacle_01.required_m : float = 35.0
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.obstacle_01.valid : bool = true
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.obstacle_02 : dict(3)
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.obstacle_02.clearance_m : float = 3149.914748769157
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.obstacle_02.required_m : float = 35.0
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.obstacle_02.valid : bool = true
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.obstacle_03 : dict(3)
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.obstacle_03.clearance_m : float = 2255.580064637999
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.obstacle_03.required_m : float = 35.0
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.clearances.obstacle_03.valid : bool = true
candidates[0].whole_route_checks.existing_precheck.retreat_points.uav_01.numerical_tolerance_m : float = 1e-06
candidates[0].whole_route_checks.existing_precheck.endpoint_spacing : NoneType = null
candidates[0].whole_route_checks.existing_precheck.policy : dict(12)
candidates[0].whole_route_checks.existing_precheck.policy.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : dict(3)
candidates[0].whole_route_checks.existing_precheck.policy.uav_01.facility_01  (同类键 `facility_#` 共 3 个，只展开第一个) : str
candidates[0].whole_route_checks.existing_precheck.semantic_polylines : dict(12)
candidates[0].whole_route_checks.existing_precheck.semantic_polylines.uav_01  (同类键 `uav_#` 共 12 个，只展开第一个) : dict(3)
candidates[0].whole_route_checks.existing_precheck.semantic_polylines.uav_01.valid : bool = true
candidates[0].whole_route_checks.existing_precheck.semantic_polylines.uav_01.issues : list(0)
candidates[0].whole_route_checks.existing_precheck.semantic_polylines.uav_01.numerical_tolerance_m : float = 1e-06
candidates[0].whole_route_checks.existing_precheck.failures : list(0)
candidates[0].whole_route_checks.existing_precheck.status : str = "PASS"
candidates[0].approach_length_m : float = 42961.05841569028
combination_records : list(79)
combination_records[0].candidate_index : int = 0
combination_records[0].group_candidate_indices : dict(1)
combination_records[0].group_candidate_indices.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : int
combination_records[0].stage : str = "feasible"
combination_records[0].reason : NoneType = null
combination_records[0].rejection : NoneType = null
combination_records[0].approach_length_by_group_m : dict(1)
combination_records[0].approach_length_by_group_m.task_group_01  (同类键 `task_group_#` 共 1 个，只展开第一个) : float
actual_single_agent_calibration_rounds : int = 1
```

### logs/

文件总数 750（B 400，C 350）；非空 350（B 0，C 350）。

`v07_first_edition/prod_f020_060/logs/C__family_s15_055e9333b067d2bc_ext_000_regular.txt` 前 30 行：

```
{"stage": "rehearsal", "skeleton": "family_s15_055e9333b067d2bc_ext_000_regular", "round": 1, "candidate_index": 11}
{"stage": "episode_complete", "episode_id": "family_s15_055e9333b067d2bc_ext_000_regular_synchronous", "state": "generated", "task_result": "success", "coordination_matches": true, "minimum_separation_m": 18.19358650487551}
{"stage": "episode_complete", "episode_id": "family_s15_055e9333b067d2bc_ext_000_regular_sequential", "state": "generated", "task_result": "success", "coordination_matches": true, "minimum_separation_m": 8.722593584020128}



























```

## 记录了耗时的字段

单位均为秒（墙钟）。

| 文件 | 键 | 含义 | 粒度 |
|---|---|---|---|
| `status/B__<sk>.json` | `planning_wall_s`（顶层与 `detail.planning_wall_s` 同值） | `worker_b` 内 `time.monotonic` 计时：候选池搜索 + pickle 写盘（`run_v07_fe_production.py:323-342`） | 按骨架 |
| `planning/<sk>/planning_result.json` | `planning_wall_s` | 同上 | 按骨架 |
| `status/C__<sk>.json` | `detail.elapsed_wall_s`（顶层同值） | `worker_c` 整个仿真阶段（两个方式 + 配对检查 + QC，`:392-417`） | 按骨架 |
| `status/C__<sk>.json` 的 `detail.rows[]`，`episodes/<sk>/<mode>/metrics.json` | `simulation_wall_s` | 该方式联合仿真 `execute` 的 `wall_s`（`execution.py:161`） | **按方式** |
| 同上 | `amortized_skeleton_setup_s` | 骨架级准备耗时（候选池载入、单机预演、时刻安排、相关写盘）的一半（`run_v07_s2_episode_batch.py:154` 写死 `setup_s / 2`） | 按方式（两方式相同） |
| 同上 | `episode_postprocess_wall_s` | 该方式 `write_result`：判定、写盘、独立审计、截断检查 | 按方式 |
| `episodes/<sk>/candidate_search.json`（仅进入 C 的骨架） | `group_search_metrics.<g>.wall_s`、`.geometry_wall_s`（unified 后端两者相同）、`.phase_search.wall_s`（unified 恒 0）、`combination_search.wall_s` | 规划阶段每组提案池耗时、组合搜索耗时 | 按骨架×任务组 |
| `stats.json` | `timing_and_size.by_intent.<i>.b_wall_s/c_wall_s`（count/median/p90/max）、`timing_and_size.total_wall_s` | 批次汇总 | 按批次 |
| `logs/C__<sk>.txt` | 无耗时字段（只有 rehearsal / episode_complete 事件行）；`logs/B__*.txt` 全部为空 | | |

`rows[]` 中没有进入联合仿真的方式行（state = infeasible）不含上述三项方式级耗时。`duration_s`、`time_budget.*`、`event_times_s` 等是**仿真时钟**时刻/时长，不是计算耗时。

## 记录了失败原因的字段

| 文件 | 键 | 内容 |
|---|---|---|
| `status/B__<sk>.json` | `status`；`detail.rejection_reasons`（原因→次数）；`detail.termination`（classification/scope/reason/geometric_evidence/global_infeasibility_claimed） | B 结论与按原因计数（组提案级 + 组合级合并） |
| `planning/<sk>/planning_result.json` | `rejection_reasons`、`group_rejection_reasons`、`combination_rejection_reasons`、`rejection_class_counts`、`termination`、`selection` | 同上，并分开组提案级与组合级 |
| `episodes/<sk>/candidate_search.json`（仅进入 C 的骨架） | `candidates[].stage`、`.reason`、`.rejection.geometric_evidence`（衔接/形态的逐次尝试原因、整航线检查的问题 code）；`combination_records[]`；`group_terminations` | 逐候选的构造环节与子原因 |
| `status/C__<sk>.json` | `status`、`detail.first_failure`（stage/reason，及 first_attempt/final_detail）、`detail.rows[].state/reason/category/execution_status/all_groups_complete/rejection_detail/geometry_attempts` | 仿真阶段失败的环节、原因、方式 |
| `episodes/<sk>/geometry_XX/planning_rejection.json`、`geometry_history.json` | 每个候选的预演/时刻失败类别 | |
| `stats.json` | `intents.<i>.b_rejection_top5`、`c_first_failure_top5` | 批次汇总（只列前 5） |
