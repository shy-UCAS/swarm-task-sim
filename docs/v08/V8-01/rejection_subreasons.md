# V8-01 §3.4 补充：逐候选拒绝的子原因（只覆盖进入 C 的骨架）

来源：全部 9 批 `episodes/<sk>/candidate_search.json` 共 2435 个文件（`scripts/v8_01_scan_subreasons.py`）。 B 为 REJECT 的骨架没有这类文件，见 failures.md §1。

- `connection_search_budget_exhausted`：每个被拒提案有 10 次衔接尝试（`route.py:164` / `operation_routes.py:35`），子原因是每次尝试抛出的 `GeometryRejected.reason`。
- `shape_search_budget_exhausted`：每个被拒提案有 20 次形态尝试（`shapes.py:21` / `operation_shapes.py:165`）。
- `whole_route_check`：子原因是 `plan_checks` 问题清单中的 `code`（`checks.py:68-186`），一个候选可同时有多个。

## connection_search_budget_exhausted

| 子原因 | transit 尝试数 / 候选数 | reconnaissance 尝试数 / 候选数 | monitoring 尝试数 / 候选数 | feint 尝试数 / 候选数 | penetration 尝试数 / 候选数 |
|---|---|---|---|---|---|
| retreat_outside_available_domain | 86956 / 10383 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| alignment_consumed_by_lane_turn | 21472 / 5868 | 23083 / 3266 | 8968 / 1579 | 17705 / 2070 | 8844 / 1161 |
| no_exterior_connection | 41983 / 4742 | 4591 / 640 | 12039 / 1415 | 4500 / 623 | 4837 / 626 |
| lane_swallowtail | 32359 / 3806 | 3941 / 518 | 18247 / 2188 | 3934 / 524 | 3219 / 404 |
| no_interior_connection | 0 / 0 | 10962 / 1601 | 449 / 57 | 0 / 0 | 120 / 12 |
| retreat_endpoint_invalid | 0 / 0 | 2 / 2 | 19 / 11 | 0 / 0 | 0 / 0 |
| sub_metre_semantic_join | 0 / 0 | 1 / 1 | 8 / 3 | 1 / 1 | 0 / 0 |

## shape_search_budget_exhausted

| 子原因 | transit 尝试数 / 候选数 | reconnaissance 尝试数 / 候选数 | monitoring 尝试数 / 候选数 | feint 尝试数 / 候选数 | penetration 尝试数 / 候选数 |
|---|---|---|---|---|---|
| ingress_line_blocked | 0 / 0 | 1078 / 720 | 71086 / 5226 | 0 / 0 | 3262 / 486 |
| survey_area_unavailable | 0 / 0 | 55255 / 3058 | 0 / 0 | 0 / 0 | 0 / 0 |
| intrusion_contour_unavailable | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 38577 / 3364 |
| patrol_arc_too_short | 0 / 0 | 0 / 0 | 34965 / 2650 | 0 / 0 | 2994 / 174 |
| intrusion_interior_unavailable | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 31471 / 3762 |
| intrusion_endpoint_spacing | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 7796 / 899 |
| work_segment_clearance | 0 / 0 | 3630 / 1663 | 224 / 207 | 0 / 0 | 6 / 6 |
| survey_insufficient_strips | 0 / 0 | 1089 / 467 | 0 / 0 | 0 / 0 | 0 / 0 |
| sub_metre_semantic_join | 0 / 0 | 41 / 40 | 343 / 320 | 0 / 0 | 13 / 10 |
| retreat_endpoint_invalid | 0 / 0 | 2 / 2 | 102 / 94 | 0 / 0 | 1 / 1 |
| survey_strip_unavailable | 0 / 0 | 85 / 84 | 0 / 0 | 0 / 0 | 0 / 0 |

## whole_route_check

| 子原因 | transit 尝试数 / 候选数 | reconnaissance 尝试数 / 候选数 | monitoring 尝试数 / 候选数 | feint 尝试数 / 候选数 | penetration 尝试数 / 候选数 |
|---|---|---|---|---|---|
| collection_clearance | 32680 / 15682 | 2754 / 1207 | 33789 / 15978 | 3045 / 1393 | 3331 / 2050 |
| terminal_endpoint_spacing | 135 / 135 | 11282 / 11282 | 2253 / 2253 | 41 / 41 | 206 / 206 |
| constraint_clearance | 3989 / 1931 | 30 / 25 | 356 / 264 | 31 / 26 | 123 / 97 |
| warning_visit_count | 0 / 0 | 192 / 48 | 0 / 0 | 0 / 0 | 0 / 0 |

