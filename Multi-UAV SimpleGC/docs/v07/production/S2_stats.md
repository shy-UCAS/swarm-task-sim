# v0.7 first_edition production statistics

## 1. Yield

| families | family_unsampleable | descriptors | draws | b_all_pass_draws | retained_draws | b_all_pass_ratio | draw_retention_ratio |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 10 | 2 | 0 | 0 | 0.0 | 0.0 |

### by_layout

| bucket | draws | b_all_pass | retained | b_all_pass_ratio | retention_ratio |
|---|---|---|---|---|---|
| clustered | 2 | 0 | 0 | 0.0 | 0.0 |

### by_facility_count

| bucket | draws | b_all_pass | retained | b_all_pass_ratio | retention_ratio |
|---|---|---|---|---|---|
| 2 | 2 | 0 | 0 | 0.0 | 0.0 |

### by_vehicle_count

| bucket | draws | b_all_pass | retained | b_all_pass_ratio | retention_ratio |
|---|---|---|---|---|---|
| >=6 | 2 | 0 | 0 | 0.0 | 0.0 |

## 2. Intents

| intent | b_total | b_pass | b_pass_ratio | c_in_b_pass | c_paired | c_pair_ratio | retained_episodes |
|---|---|---|---|---|---|---|---|
| transit | 2 | 2 | 1.0 | 0 | 0 | None | 0 |
| reconnaissance | 2 | 2 | 1.0 | 0 | 0 | None | 0 |
| monitoring | 2 | 1 | 0.5 | 0 | 0 | None | 0 |
| feint | 2 | 2 | 1.0 | 0 | 0 | None | 0 |
| penetration | 2 | 1 | 0.5 | 0 | 0 | None | 0 |

## 3. Coverage bias


### all_draws

- layouts: {'clustered': 2}
- facility_counts: {'2': 2}
- vehicle_counts: {'11': 2}
- vehicle_buckets: {'>=6': 2}
- actual_unit_counts: {'2': 2}
- approach_modes: {'multi_direction': 1, 'same_direction': 1}
- task_groups_by_intent: {'feint': {'draws': 2, 'groups': 2, 'members': 22, 'mean_groups': 1.0, 'mean_members': 11.0}, 'monitoring': {'draws': 2, 'groups': 2, 'members': 22, 'mean_groups': 1.0, 'mean_members': 11.0}, 'penetration': {'draws': 2, 'groups': 2, 'members': 22, 'mean_groups': 1.0, 'mean_members': 11.0}, 'reconnaissance': {'draws': 2, 'groups': 2, 'members': 22, 'mean_groups': 1.0, 'mean_members': 11.0}, 'transit': {'draws': 2, 'groups': 2, 'members': 22, 'mean_groups': 1.0, 'mean_members': 11.0}}

### b_all_pass_draws

- layouts: {}
- facility_counts: {}
- vehicle_counts: {}
- vehicle_buckets: {}
- actual_unit_counts: {}
- approach_modes: {}
- task_groups_by_intent: {}

### retained_draws

- layouts: {}
- facility_counts: {}
- vehicle_counts: {}
- vehicle_buckets: {}
- actual_unit_counts: {}
- approach_modes: {}
- task_groups_by_intent: {}

## 4. Low speed and dwell (retained only)

| role | execution_method | mode | members | events_per_km | low_speed_time_share | dwell_positive | dwell_evaluable |
|---|---|---|---|---|---|---|---|

## 5. Waiting and end dwell (retained only)

| group | members | evaluable_members | initial_speed_gt_1_share | release_s | episode_release_span_s | low_speed_share_after_release | end_dwell_s |
|---|---|---|---|---|---|---|---|

## 6. Timing and size

| total_wall_s | run_dir_bytes | retained_episode_bytes | mean_retained_episode_bytes |
|---|---|---|---|
| 358.76599999997416 | 14267974 | 0 | None |

| intent | b_wall_s | c_wall_s |
|---|---|---|
| transit | {'count': 2, 'median': 104.8125, 'p90': 128.5872999999905, 'max': 134.53099999998813} | {'count': 0, 'median': None, 'p90': None, 'max': None} |
| reconnaissance | {'count': 2, 'median': 104.82799999999406, 'p90': 121.8655999999988, 'max': 126.125} | {'count': 0, 'median': None, 'p90': None, 'max': None} |
| monitoring | {'count': 2, 'median': 300.49199999999837, 'p90': 344.6736000000092, 'max': 355.7190000000119} | {'count': 0, 'median': None, 'p90': None, 'max': None} |
| feint | {'count': 2, 'median': 139.45350000000326, 'p90': 161.29070000000064, 'max': 166.75} | {'count': 0, 'median': None, 'p90': None, 'max': None} |
| penetration | {'count': 2, 'median': 51.56249999998545, 'p90': 92.4748999999807, 'max': 102.70299999997951} | {'count': 0, 'median': None, 'p90': None, 'max': None} |
