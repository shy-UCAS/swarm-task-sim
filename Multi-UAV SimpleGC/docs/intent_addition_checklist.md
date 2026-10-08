# 新增意图检查清单

适用范围是 [v0.6 正式计划](v06_formal_plan.md) 第 1–3 节。清单记录实现和复核入口；完成离线检查不代表 SITL 试跑已经通过。暂停 A 的具体数字和 CI 结论以当次报告为准。

## 参数、规划和注册

- 在 `swarm_sim/registry.py` 登记意图、允许规划器、语义角色、可见运动槽位，以及规划器／验证器／事实提取／描述模板版本。
- 任务同时保存 `mission.intent`、`flight_pattern` 和 `component_versions`。规划版本对应实际飞法；后面三个组件在同一意图的两种飞法间共用。
- family 共用机数、速度、进场侧和是否返航。意图只采样自己的额外参数；快速通过离开侧由进场侧确定，不独立抽方向。
- 飞法以任务身份派生的独立随机子流等概率抽样；与所有任务固定飞法 1 的结果相比，family、共用参数、场景种子、任务种子和数据划分必须相同。
- 采样得到的飞法规划失败时，保留任务及 `planning_rejected` 原因，不改选飞法、不换一个 family 来掩盖失败。`prepare` 必须拒绝包含不可行任务的清单。
- 三种意图各两种飞法：侦察 `equal_strip_lawnmower`／`interleaved_lanes`；巡逻 `staggered_same_loop`／`bidirectional_lanes`；快速通过 `line_abreast`／`column`。
- 角色词表统一登记 `approach`、`observe`、`patrol`、`transit`、`return`、`idle_padding`、`hold_no_op`。快速通过主阶段只能使用 `transit`；出区是阶段末端事件。
- 生成完整的 300 family／900 任务清单，按意图和飞法分别报告规划通过／拒绝数、机间最小间距分布、低于 10 米数量、世界边界和预计时长。不可行飞法留到暂停 A 上报替代候选，不能自行替换。

## 验证与可见事实

- 一个意图的两种飞法共用验证器。对同一轨迹修改或删除 `flight_pattern` 后，判定必须不变；验证器不得依赖飞法字段。
- 快速通过仅在 `transit` 窗口核验进入、对侧离开、直线通过、区域内无停留及无绕圈；返航再次穿过区域不违反主阶段定义。
- 阈值及理由保存在 `swarm_sim/rapid_passage.py` 的 `THRESHOLDS`／`THRESHOLD_BASIS`；暂停 A 记录暂定值。pilot 核对真实快速通过的余量及其他意图交叉否定，最多调整一次，正式生产前冻结。
- 轨迹缺失、截断、时间间隙或不完整窗口给出否／未知。判定和描述都不能拿规划终点、规划返航或规划进入侧补足观测。
- 事实提取读取实际轨迹；SIM 真值和 FCU 观测分别计算，不能互相补数据。进入／离开侧、穿越、区域内停留／转向和返航事实均要有证据。
- 对快速通过与新增飞法做主阶段截断和返航截断：未完成主任务不能为是，未完成返航不能为是。
- 对 v0.5 完整归档的侦察、巡逻轨迹只读应用快速通过判据；任一通过意味着交叉否定失败，处理只遵循正式计划第 6 节。

## 描述、协议和模型输入

- 运动模式槽位只登记“直穿”，不新造“穿越”等同义槽值。描述不用“更快”，也不描述横队／纵队等飞法。
- 遍历全部已登记意图，前三个措辞属于训练组，第四个属于测试组，两组非空且句式不重叠。
- v0.6 用显式 `execution.protocol_version="v0.6"` 选择协议，并独立配置 `final_hold_s=2.0`、`firmware_version_timeout_s=2.0`；v0.5 缺省保持原行为。
- 终点悬停只发生在最后阶段的终点，成功后再记录任务结束；不更改 `confirmation_dwell_s`、0.5 秒驻留判据或原来的 `terminal_hold_s`。
- 固件消息超时使用已核验二进制内嵌版本回退；消息版本和二进制门禁任一不一致都拒绝起飞。
- 导出／加载验证协议和文件哈希。新增飞法及组件版本只属于元数据，不能进入模型六维 FCU 位置／速度输入。
- 现有四个 v0.5 示例逐个调用 `load_episode()`，原特征、掩码、时间、身份、标签及旧元数据含义保持相同；缺少新增字段不报错。
- 数据按 family 整组划分。收尾审计发现 `family_split_leaks` 必须停止，不得继续描述生成或标记 `finalized`。

## 离线护栏及证据入口

| 正式计划项 | 代码／测试／证据入口 |
| --- | --- |
| 3.1.1 元数据 | `test_v06_planning.test_all_six_patterns_register_versions_and_roles`；`test_component_versions_cannot_lie`；导出元数据测试 |
| 3.1.2 随机隔离 | `test_v06_planning.test_fixed_vs_random_keeps_family_shared_seed_and_split_identity`；`test_pattern_random_substream_is_balanced_and_stable` |
| 3.1.3 模板划分 | `test_v06_data_contract.test_all_registered_intents_have_three_train_one_test_disjoint_wordings` |
| 3.1.4 验证器不依赖飞法 | `test_v06_planning.test_existing_validators_ignore_pattern_and_missing_pattern`；`test_rapid_passage.test_validator_ignores_pattern_and_return_crossing`；`test_v06_data_contract.test_transit_facts_depend_on_measured_complete_trajectory_not_pattern_metadata` |
| 3.1.5 v0.5 DR130 回归 | `scripts/diagnostics/v06_offline_checks.py golden`；主种子 `2026100205`，本次逐项完全相等，无字段排除 |
| 3.1.6 截断扰动 | `test_rapid_passage.test_completed_window_with_truncated_geometry_cannot_pass`；`test_v06_execution.test_missing_or_truncated_hold_evidence_cannot_complete_final_hold`；描述失败／未知反例测试 |
| 3.1.7 交叉否定 | `scripts/diagnostics/v06_offline_checks.py cross-negative --archive ...`，读取冻结归档 |
| 3.1.8 固件门禁 | `test_v06_execution.FirmwareWaitTests`；`test_run_provenance` |
| 3.1.9 人工暂停续跑 | `test_parallel_batch.GlobalControllerTests` 中暂停续跑不重不漏、滚动窗口连续、规则停止拒绝和重复 SIGINT 测试 |
| 3.1.10 角色词表 | `test_v06_planning.test_all_six_patterns_register_versions_and_roles`，核验 `registry.SEMANTIC_ROLES` |
| 用户补充的旧示例兼容 | `test_v06_data_contract.test_four_frozen_v05_examples_preserve_all_features_targets_and_old_metadata` |
| 3.2 完整离线规划 | `scripts/diagnostics/v06_offline_checks.py planning`，逐任务保留失败原因和统计分母 |
| 第 6 节划分泄漏门禁 | `test_parallel_finalize.test_family_split_leakage_stops_finalization_before_descriptions_and_keeps_audit` |
| 不可行任务不可准备 | `test_parallel_batch.FrozenPlanTests.test_prepare_rejects_selected_infeasible_pattern_before_verifying_or_creating_plan` |

表中的测试函数位于对应模块的测试类中。运行与续跑命令见 [v0.6 正式运行命令](v0.6_formal_run_commands.md)。停止条件只使用正式计划第 6 节，时长差异或低通过率作为诊断记录，不追加研究停止条件。

第 3.1.6 项在暂停 A 部分完成：快速通过合成主阶段截断及事实／描述降级已有测试；新增三种飞法的实际几何与返航双通道语义→事实→描述全链截断仍待 pilot 补齐。执行器悬停证据测试不能替代返航语义截断测试。具体覆盖边界见暂停 A 报告。

暂停 A 必须给出提交号、远端 CI 链接、改动统计、各项护栏结果、离线规划分组统计和阈值来由。远端 CI 通过后标记 `v0.6-pauseA`，随后停下；未来获得用户指令后再准备 pilot。
