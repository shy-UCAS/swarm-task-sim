# V06 试生产只读分布对照与数据审计

结论：PASS；完成且质量合格 10/10；SITL 尝试 10/10。

数值是分布描述，不能解释为配对实验或单独由控制模式引起的因果变化。详细分母、未知值、逐集证据与文件哈希见 report.json；6.9 审计全文见 audit.json。

| 指标 | v0.3 barrier：中位数 [最小, 最大] | v0.4 route：中位数 [最小, 最大] |
|---|---:|---:|
| speed_lt_0.3_m_s:stop_count_per_aircraft | 9.0000 [7.0000, 11.0000]；n=43 | 3.0000 [1.0000, 5.0000]；n=38 |
| speed_lt_0.3_m_s:stationary_time_fraction | 0.0856 [0.0700, 0.1002]；n=10 | 0.0497 [0.0230, 0.0606]；n=10 |
| speed_lt_0.3_m_s:synchronized_time_fraction | 0.0716 [0.0567, 0.0797]；n=10 | 0.0413 [0.0190, 0.0525]；n=10 |
| speed_lt_0.5_m_s:stop_count_per_aircraft | 9.0000 [8.0000, 10.0000]；n=43 | 3.0000 [2.0000, 3.0000]；n=38 |
| speed_lt_0.5_m_s:stationary_time_fraction | 0.1868 [0.1386, 0.1967]；n=10 | 0.0779 [0.0404, 0.0966]；n=10 |
| speed_lt_0.5_m_s:synchronized_time_fraction | 0.1635 [0.1248, 0.1820]；n=10 | 0.0733 [0.0380, 0.0893]；n=10 |
| task_span_s | 63.8251 [50.0429, 72.7245]；n=10 | 48.2768 [38.8728, 60.0615]；n=10 |
| elapsed_s | 138.9195 [125.8996, 146.7942]；n=10 | 122.8475 [113.8083, 135.7607]；n=10 |
| truth_coverage | 1.0000 [1.0000, 1.0000]；n=10 | 1.0000 [1.0000, 1.0000]；n=10 |
| observation_coverage | 1.0000 [1.0000, 1.0000]；n=10 | 1.0000 [1.0000, 1.0000]；n=10 |
| upload_release_confirmation_fraction | UNKNOWN (10/10) | 0.0961 [0.0851, 0.1121]；n=10 |
| agents | 4.5000 [2.0000, 6.0000]；n=10 | 3.0000 [2.0000, 6.0000]；n=10 |
| speed_m_s | 2.5000 [2.0000, 3.0000]；n=10 | 2.5000 [2.0000, 3.0000]；n=10 |
| execution_stage_count | 10.0000 [9.0000, 10.0000]；n=10 | 3.0000 [2.0000, 3.0000]；n=10 |

| 扫描线长度（m） | 有效/总点数 | 未知 | 最小 / P10 / 中位 / P90 / 最大（m/s） |
|---:|---:|---:|---|
| 10.411215 | 36/36 | 0 | 0.8960 / 0.9027 / 0.9997 / 1.0821 / 1.1027 |
| 10.513195 | 36/36 | 0 | 0.9215 / 0.9648 / 1.1244 / 1.2310 / 1.2491 |
| 10.955055 | 18/18 | 0 | 0.9338 / 1.0450 / 1.1597 / 1.2677 / 1.2807 |
| 11.913469 | 36/36 | 0 | 1.0939 / 1.1058 / 1.1606 / 1.2002 / 1.2104 |
| 11.933615 | 18/18 | 0 | 1.0639 / 1.1075 / 1.1709 / 1.2361 / 1.2427 |
| 8.105012 | 18/18 | 0 | 0.9971 / 1.0117 / 1.1028 / 1.2138 / 1.2201 |
| 8.510953 | 18/18 | 0 | 0.9185 / 0.9221 / 1.0234 / 1.0899 / 1.0965 |
| 9.058748 | 18/18 | 0 | 0.9250 / 0.9303 / 1.0141 / 1.1405 / 1.1464 |
| 9.588412 | 18/18 | 0 | 0.9630 / 1.0672 / 1.1180 / 1.2309 / 1.2415 |
| 9.941919 | 12/12 | 0 | 1.0775 / 1.0869 / 1.1617 / 1.2502 / 1.2553 |

过点速度：FCU 水平速度，航点 2 m 邻域，execution_artifacts_v1；四个观测处理版本逐集保留于 report.json。

所有检查：
- ten_exported_scenes: PASS
- at_most_ten_attempts: PASS
- ledger_all_attempts_exported: PASS
- at_least_eight_completed_and_quality_eligible: PASS
- matching_profile_parameter_distributions: PASS
- new_profile_fingerprint_verified: PASS
- ten_generated_scenes: PASS
- family_scheme: PASS
- route_only: PASS
- reconnaissance_only: PASS
- audit_69_fields: PASS
- no_audit_issues: PASS
- loader_all_pass: PASS
- legacy_loader_all_pass: PASS
- distribution_comparison: PASS
- source_files_unchanged: PASS
