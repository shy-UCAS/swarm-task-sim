# v0.7 first_edition 生产脚本任务报告（PROD）

## 结论

生产脚本、3 处传参改动、T1–T12 测试、S0/S1a/S1b/S2 检查和合并后完整测试均已完成。最终生产代码状态为 `40f5b881b330ce215163fb176af37b0a062b206d`；测试债务修复合并提交为 `546dbcaaf11b95eebbf762b6d152667fc459c4ee`。合并只带入 `tests/` 与 `docs/`，生产代码未变。

- S0：PASS。300 family、0 unsampleable、3000 descriptors（期望 3000）、丢弃 300 条 aborted。
- S1a：PASS。11 family、38 skeleton、0 mismatch。
- S1b：PASS。3/3 B PASS、3/3 C PAIRED、hard physical audit 全 True、content diff 0；52 条允许差异。
- S2：中断码 130、续跑码 0、10 个 B 终态、已完成 status 续跑前后 SHA 不变、7 个中断残留 B 目录进入 `_aborted`、manifest/stats 生成、无 P0。该 family 两个抽签各有一个 B `REJECT`（`shape_search_budget_exhausted`），因此没有 C/episode；S1b 已覆盖 C 等价性。
- 合并前完整回归：507 项，489 通过，18 项 G-5a 已知失败，0 新增失败、0 签名变化，15 个新测试全部通过。
- 合并后完整回归：507/507 全部通过，零失败、零错误。

## 1. 环境核对

| 项目 | 值 |
|---|---|
| 工作树 | `F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-prod-r3` |
| 分支 | `fe/production-r3` |
| 基线提交 | `5fc713afcfc8f140dac6f143e83f4048b915be4f` |
| 最终生产代码提交 | `40f5b881b330ce215163fb176af37b0a062b206d` |
| 合并提交 | `546dbcaaf11b95eebbf762b6d152667fc459c4ee` |
| Python / NumPy | 3.12.3 / 2.5.3 |
| r3 `CONFIG_SHA256` | `0fe3efff6f97ed88c665374d0280aef571b92399ac3711184f13e5c6a3de3b30` |
| r2 `FROZEN_SHA256` | `94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193` |
| S1.5 基线 | 300 family，`external_attempt_path` = `SwarmData\v07_scene\attempt_s15_20261016T144107Z` |
| R4 原始结果 | `SwarmData\fast_dynamics\m3\m3_r3_r4_attempt01` |
| 旧 `Simulation-fe-prod` | 不存在，无需清理 |

## 2. 生产代码改动（3 处）

1. `task_v07/unified/rehearsal.py::rehearse`：增加仅关键字 `reference_version="r2"`，传给 `execute`。
2. `scripts/run_v07_s2_episode_batch.py::run_episode_job`：读取并透传 `reference_version`；校验并使用 `candidate_pool_pickle`（SHA256、顶层 skeleton_id、每个 pool skeleton_id）；调用 `write_result` 时传 `scope`。
3. `scripts/run_v07_s2_episode_batch.py::write_result`：增加 `scope=EXPANSION_SCOPE`，传给 `write_episode`。

不变量：不传新键的旧调用方保持默认 r2、实时候选池、`EXPANSION_SCOPE`。未改规划器、判据、审计、`configs/`、场景、`task_v07/expansion/views.py`。

## 3. 既有测试兼容性修改

没有修改既有测试断言，也没有 4.4 签名兼容修改。合并的测试债务修复只改 `tests/` 和 `docs/`；合并后 507/507 通过。

## 4. T1–T12

`tests/test_v07_fe_production.py` 共 15 个测试方法（T1–T12，外加 3 个 harness 修复回归测试）：

- T1 r3 传参；T2 默认 r2；T3 缓存候选池与三种损坏；T4 episode scope；T5 抽签级保留；T6 B 拒绝/超时与 C 延后；T7 续跑残留迁移与中断不写 status；T8 worker P0；T9 r2 配置硬审计失败；T10 阶段 A 确定性与异常分类；T11 启动拒绝与版本字段；T12 超时。
- 结果：15/15 PASS，`returncode = 0`。
- 证据：`docs/v07/evidence/production/T1_T12.json`。

## 5. S0 干跑

命令（HEAD `40f5b88`）：

```text
--run-id s0_dryrun --families 0:300 --dry-run --root <ROOT>\SwarmData\v07_first_edition_checks_v3
```

结果：PASS。300 family、0 unsampleable、3000 descriptors（期望 3000）、丢弃 300 条 aborted。layout：linear 66、clustered 60、isolated 58、single 116；机数桶：4–5 为 59、≥6 为 241。

## 6. S1a 阶段 A 等价性

HEAD `40f5b88`：11 family、38 skeleton、0 mismatch；每个 descriptor 和 scene 均与 R4 `R0_validation_plan_amended.json` 的 `R4.jobs` deep-equal。

证据：`docs/v07/evidence/production/S1a_equivalence.json`。

## 7. S1b 阶段 B+C 逐位等价

HEAD `40f5b88`，3 workers，3 个骨架：

- `family_s15_1c267d4d7000043d_ext_001_regular`
- `family_s15_38bedc9d791d547b_ext_008_regular`
- `family_s15_1b876e6b8b6f70c6_ext_005_regular`

结果：

| 骨架 | B | C | paired | hard physical audit |
|---|---|---|---|---|
| `...1c267d4d7000043d_ext_001_regular` | PASS | PAIRED | True | True |
| `...38bedc9d791d547b_ext_008_regular` | PASS | PAIRED | True | True |
| `...1b876e6b8b6f70c6_ext_005_regular` | PASS | PAIRED | True | True |

- content 差异：0。
- 允许差异：52 条。其中 `source.json.scope` 6 条（`metadata:text`）；墙钟类 34 条（`metadata:wall_clock`）；`metrics.json` 的 `amortized_skeleton_setup_s` 与 `episode_postprocess_wall_s` 共 12 条（检查脚本显式允许这两个叶子键）。
- 耗时：B 规划 36.6 / 43.2 / 43.2 s；C 仿真 193.7 / 313.6 / 569.3 s；总墙钟 624.2 s。
- 证据：`docs/v07/evidence/production/S1b_equivalence.json`。

## 8. S2 冒烟与中断/续跑

family：`candidate_index = 7`，`family_s15_0aeede8b1f29217e`（不在阶段 2 `attempt_s15desc_20261016T154909Z` 的 `selected` 列表中）。2 个抽签、10 个 B 任务、8 workers。

- 两个抽签均为 `B_REJECT`：
  - slot 0：penetration `family_..._ext_004_regular`，`shape_search_budget_exhausted = 200`；
  - slot 1：monitoring `family_..._ext_007_regular`，`shape_search_budget_exhausted = 200`。
- 其余 8 个 B 为 PASS；B 成功率：transit 2/2、reconnaissance 2/2、monitoring 1/2、feint 2/2、penetration 1/2。
- 因没有抽签满足“5 个 B 全部 PASS”，没有任何 C 任务，也没有 episode。该 family 的 S2 因此覆盖阶段 A/B、中断/续跑与报告；C 的逐位等价已由 S1b 覆盖。
- 中断：在 3 个 B 完成后发送 `CTRL_BREAK_EVENT`，调度器退出码 130；中断时正在运行的 7 个 B 任务没有写 status，残留目录进入 `_aborted/20261018T033108Z/B/`。
- 续跑：`--resume` 退出码 0；10 个 B 任务全部有终态；中断前已完成任务的 status SHA 续跑前后不变；无 P0。
- manifest：`retained_episodes = 0`、`non_retained_episodes = 0`、`draws = 2`（均 `B_REJECT`）；版本字段齐全，`reference_version = r3`。
- stats：6 个部分齐全；总墙钟 358.8 s；run 目录 14,267,974 bytes；没有保留 episode，因此 `retained_episode_bytes = 0`。
- 证据：`docs/v07/evidence/production/S2_interrupt_resume.json`、`S2_pre_interrupt.json`、`S2_manifest.json`、`S2_stats.json`、`S2_progress.json`；`docs/v07/production/S2_stats.md`。

## 9. 完整测试集

文档写“测试模块 = `tests/test_*.py` 的全部模块名”；实际 `tests/test_*.py` 有 152 个模块、1425 项，与文档所述 492 项不符。经核对，`docs/v07/evidence/m3_r3/R0_validation_plan_amended.json::R3.regression_modules` 的 49 个模块正好产生 492 项、18 项 G-5a 已知失败；检查脚本使用该 49 模块 + 本任务 `test_v07_fe_production`，这是唯一与 492/18 基线一致的完整离线集。

- 合并前（HEAD `40f5b88`）：507 项 = 492 基线 + 15 新测试；489 通过；18 项 G-5a 已知失败；G-5a `status = PASS`；0 新增失败；0 签名变化；15 个新测试全部通过。
- 合并后（HEAD `546dbc`）：507/507 通过；`returncode = 0`；零失败、零错误；18 项历史债务已修复（`signature_changes` 列出 18 项，作为预期）；15 个新测试通过。
- 证据：`docs/v07/evidence/production/regression_pre_merge.json`、`regression_post_merge.json`。

## 10. 合并与推送

- `git fetch origin` 成功；`git merge --no-ff 85bad0381a22a1853dd761ec94e10932ea5de144` 成功，无冲突。
- 合并前 HEAD `40f5b88`，合并后 HEAD `546dbc`。
- `git diff --stat 40f5b88 546dbc`：40 个文件，12,982 insertions，67 deletions；变更路径全部在 `Multi-UAV SimpleGC/tests/` 和 `Multi-UAV SimpleGC/docs/`，范围外文件 0 个。按补充 4，S0–S2 不重跑，只重跑完整测试集。
- 分支推送 `fe/production-r3`（不强制、不推送其他分支）；远端 SHA 与本地一致由收尾命令核对。

## 11. 证据路径

仓库内：

- `docs/v07/evidence/production/environment.json`
- `docs/v07/evidence/production/S0_dryrun.json`
- `docs/v07/evidence/production/S1a_equivalence.json`
- `docs/v07/evidence/production/S1b_equivalence.json`
- `docs/v07/evidence/production/S2_interrupt_resume.json`
- `docs/v07/evidence/production/S2_pre_interrupt.json`
- `docs/v07/evidence/production/S2_manifest.json`
- `docs/v07/evidence/production/S2_stats.json`
- `docs/v07/evidence/production/S2_progress.json`
- `docs/v07/evidence/production/regression_pre_merge.json`
- `docs/v07/evidence/production/regression_post_merge.json`
- `docs/v07/evidence/production/merge_scope.json`
- `docs/v07/evidence/production/T1_T12.json`
- `docs/v07/production/S2_stats.md`

仓库外原始运行：

- `SwarmData\v07_first_edition_checks_v3\s0_dryrun`
- `SwarmData\v07_first_edition_checks_v3\s1a_20261018T031209Z`
- `SwarmData\v07_first_edition_checks_v3\s1b_20261018T031214Z`
- `SwarmData\v07_first_edition_smoke_v2\s2_smoke`
- `SwarmData\v07_first_edition_smoke_v2\s2_driver`
- `SwarmData\v07_first_edition_checks_v3\regression_20261018T033730Z`
- `SwarmData\v07_first_edition_checks_v3\regression_20261018T034122Z`

保留的失败/早先运行：`v07_first_edition_checks`、`v07_first_edition_checks_v2`、`v07_first_edition_smoke` 均未删除。

## 12. 已知限制与偏差

- 点质量运动学模型；4–10 m/s 未做 SITL 校准；M3 已知 10 m/s 高速用例约 4 m 冲出、四机汇聚最小间距 2.931 m，不能宣称高速规划合格。
- 不启动 SITL；不访问 M2-02B 封存留出集；不重跑 M3 内部留出集。
- S2 的 family 两个抽签均为 B_REJECT，没有 C/episode；因此 S2 的“保留 episode 的 `source.json.config_sha256` 为 r3”是空真，C 侧证据来自 S1b 的 3 个骨架。
- 文档“全部 `tests/test_*.py`”与 492 项基线不一致，已按 R3 计划的 49 模块 + 新测试执行并记录。
- S1b 使用时间戳目录本身作为运行根，避免与 S0 的 registration 范围相交。
- S2 中断使用 `CREATE_NEW_PROCESS_GROUP` + `CTRL_BREAK_EVENT` 模拟 Ctrl+C；调度器同时处理 SIGINT/SIGBREAK。
- harness 修复 2 次：`76974fd`（worker 参数）、`40f5b88`（C 任务延后 + geometry JSON 比较路径），均带回归测试；修复后重跑了 S0/S1a/S1b。
- 运行中未修改生产代码；S0/S1a/S1b/S2 均在最终生产代码状态 `40f5b88` 上执行。

## 13. S2 `stats.md` 全文

（见下页代码块；文件同时保存在 `docs/v07/production/S2_stats.md`。）

```text
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
```
