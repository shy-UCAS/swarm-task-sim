# V8-01 §3.4.2 规划拒绝抽样

每个意图取 10 个 B 为 REJECT 的骨架：全部批次合并，按 `skeleton_id` 排序后等间隔抽取（下标 round(i·(n−1)/9)，i=0..9）。

**文件中没有逐候选的环节信息**：REJECT 骨架只留下 `planning_result.json`（逐候选的 `candidates[]` 只写在 `candidate_search` 报告里，该报告只随 `candidate_pool.pkl` 保存，而候选池为空时不写 pickle）。因此"每个候选失败在哪个构造环节"一栏记为"未记录"；下表给出文件中实际有的按原因计数，并按 §4.2 的代码对应关系注明每个原因所属的构造环节。

原因 → 环节（代码位置见 code_map.md §4.2）：`shape_search_budget_exhausted`/`patrol_band_too_narrow` → 作业形态；`connection_search_budget_exhausted` → 衔接段（进场/撤离/作业段连接）；`whole_route_check`/`existing_output_precheck` → 整航线检查；`same_target_work_area_bearing` → 多组组合（同目标方位）；`approach_length_ratio_exceeded` → 同向长度比筛选。

搜索预算（代码常量，记录中的 `candidate_budget` 不存在于 planning_result.json）：每组 200 个提案（`candidate_search.py:18` CANDIDATE_BUDGET）、组合 1000（`group_candidate_pool.py:14`）、每个提案内形态 20 次（`shape_attempts`）、衔接 10 次（`connection_attempts`）。

| 意图 | 批次 | skeleton_id | 机数 | 组数 | 组提案被拒数 | 组合被拒数 | 组提案原因计数 | 组合原因计数 | 逐候选环节 | termination.reason | 规划耗时 s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| transit | prod_f140_180 | family_s15_086c28e2e8aed017_ext_005_regular | 9 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 43.3 |
| transit | prod_f020_060 | family_s15_2a7eced81da133ad_ext_000_regular | 8 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 12.1 |
| transit | prod_f100_140 | family_s15_580e26fc2a865a34_ext_000_regular | 10 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 7.8 |
| transit | prod_f260_300 | family_s15_5ccd037467090f4e_ext_000_regular | 9 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 46.8 |
| transit | prod_f180_220 | family_s15_670806bb31b8faa9_ext_005_regular | 12 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 13.6 |
| transit | prod_f100_140 | family_s15_7e6efc33c11ac19e_ext_005_regular | 12 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 4.5 |
| transit | prod_f140_180 | family_s15_8d78a724f21ea16d_ext_005_regular | 5 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 31.1 |
| transit | prod_f140_180 | family_s15_c78e4d9b24cfcaa4_ext_005_regular | 9 | 2 | 210 | 0 | connection_search_budget_exhausted 205; whole_route_check 5 | — | 未记录 | no_eligible_combination_in_registered_budgets | 54.1 |
| transit | prod_f140_180 | family_s15_f50ccf9d65d685fd_ext_005_regular | 6 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 2.2 |
| transit | prod_f140_180 | family_s15_fb72c358e7bcb2ef_ext_005_regular | 9 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 6.0 |
| reconnaissance | prod_f140_180 | family_s15_086c28e2e8aed017_ext_001_regular | 9 | 1 | 200 | 0 | connection_search_budget_exhausted 70; shape_search_budget_exhausted 65; whole_route_check 65 | — | 未记录 | no_eligible_combination_in_registered_budgets | 240.6 |
| reconnaissance | prod_f020_060 | family_s15_2a7eced81da133ad_ext_001_regular | 8 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 25.8 |
| reconnaissance | prod_f020_060 | family_s15_3de8b14ca62da9ba_ext_001_regular | 12 | 1 | 200 | 0 | whole_route_check 5; shape_search_budget_exhausted 195 | — | 未记录 | no_eligible_combination_in_registered_budgets | 314.3 |
| reconnaissance | prod_f260_300 | family_s15_547cd02ae5aa100c_ext_006_regular | 12 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 0.2 |
| reconnaissance | prod_f260_300 | family_s15_5ccd037467090f4e_ext_001_regular | 9 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 421.6 |
| reconnaissance | prod_f180_220 | family_s15_670806bb31b8faa9_ext_001_regular | 12 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 15.8 |
| reconnaissance | prod_f100_140 | family_s15_7e6efc33c11ac19e_ext_006_regular | 12 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 6.9 |
| reconnaissance | prod_f140_180 | family_s15_c78e4d9b24cfcaa4_ext_001_regular | 9 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 26.6 |
| reconnaissance | prod_f020_060 | family_s15_eaf08fe70e16ed22_ext_006_regular | 11 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 8.6 |
| reconnaissance | prod_f140_180 | family_s15_fb72c358e7bcb2ef_ext_006_regular | 9 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 9.4 |
| monitoring | prod_f140_180 | family_s15_086c28e2e8aed017_ext_007_regular | 9 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 104.7 |
| monitoring | prod_f060_100 | family_s15_2749f2d004f7cf98_ext_002_regular | 10 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 17.9 |
| monitoring | prod_f020_060 | family_s15_3de8b14ca62da9ba_ext_002_regular | 12 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 199.5 |
| monitoring | prod_f220_260 | family_s15_50f108881152c7c1_ext_002_regular | 6 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 11.3 |
| monitoring | prod_f100_140 | family_s15_643795ee68162eed_ext_007_regular | 10 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 15.8 |
| monitoring | prod_f180_220 | family_s15_7bed53b47c2f408d_ext_002_regular | 8 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 75.5 |
| monitoring | prod_f220_260 | family_s15_9e8e301dca3aeaa5_ext_007_regular | 8 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 11.8 |
| monitoring | pilot_f005_020d | family_s15_cd16b042e6f088bd_ext_002_regular | 9 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 13.5 |
| monitoring | prod_f020_060 | family_s15_eaf08fe70e16ed22_ext_007_regular | 11 | 1 | 200 | 0 | connection_search_budget_exhausted 196; shape_search_budget_exhausted 4 | — | 未记录 | no_eligible_combination_in_registered_budgets | 89.7 |
| monitoring | prod_f260_300 | family_s15_fd8369a4578173e2_ext_007_regular | 10 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 14.2 |
| feint | prod_f140_180 | family_s15_086c28e2e8aed017_ext_008_regular | 9 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 54.6 |
| feint | prod_f020_060 | family_s15_2a7eced81da133ad_ext_003_regular | 8 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 20.7 |
| feint | prod_f100_140 | family_s15_580e26fc2a865a34_ext_003_regular | 10 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 22.8 |
| feint | prod_f260_300 | family_s15_5ccd037467090f4e_ext_003_regular | 9 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 65.6 |
| feint | prod_f180_220 | family_s15_670806bb31b8faa9_ext_008_regular | 12 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 38.7 |
| feint | prod_f100_140 | family_s15_7e6efc33c11ac19e_ext_008_regular | 12 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 13.8 |
| feint | prod_f140_180 | family_s15_8d78a724f21ea16d_ext_008_regular | 5 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 39.8 |
| feint | prod_f140_180 | family_s15_c78e4d9b24cfcaa4_ext_008_regular | 9 | 2 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 75.7 |
| feint | prod_f140_180 | family_s15_f50ccf9d65d685fd_ext_008_regular | 6 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 5.6 |
| feint | prod_f140_180 | family_s15_fb72c358e7bcb2ef_ext_008_regular | 9 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 16.4 |
| penetration | prod_f180_220 | family_s15_000c023ef4f18b63_ext_009_regular | 6 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 0.3 |
| penetration | prod_f140_180 | family_s15_339bd1781df4402e_ext_009_regular | 11 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 0.4 |
| penetration | prod_f220_260 | family_s15_45a57a514f7167dd_ext_004_regular | 9 | 2 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 24.0 |
| penetration | prod_f100_140 | family_s15_580e26fc2a865a34_ext_009_regular | 10 | 1 | 200 | 0 | connection_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 10.7 |
| penetration | prod_f020_060 | family_s15_6ea2cedc61f9e69c_ext_004_regular | 10 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 14.2 |
| penetration | prod_f100_140 | family_s15_8d9bcfe4ce91cfb8_ext_004_regular | 8 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 0.3 |
| penetration | prod_f100_140 | family_s15_a69f4a65deeba1dc_ext_004_regular | 10 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 0.4 |
| penetration | prod_f060_100 | family_s15_c6b49487cb7c7e1f_ext_009_regular | 11 | 2 | 14 | 1000 | connection_search_budget_exhausted 6; whole_route_check 8 | same_target_work_area_bearing 188; approach_length_ratio_exceeded 812 | 未记录 | no_eligible_combination_in_registered_budgets | 74.5 |
| penetration | prod_f020_060 | family_s15_dd82f3d232f6f383_ext_009_regular | 8 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 0.3 |
| penetration | prod_f260_300 | family_s15_fd8369a4578173e2_ext_009_regular | 10 | 1 | 200 | 0 | shape_search_budget_exhausted 200 | — | 未记录 | no_eligible_combination_in_registered_budgets | 0.6 |

"组提案被拒数"即尝试过的提案数中被拒的部分；REJECT 骨架的可行提案数 = 组数×200 − 组提案被拒数（若大于 0，则失败在组合阶段）。

