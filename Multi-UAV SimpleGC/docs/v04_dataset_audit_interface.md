# v0.4 WP-G 数据审计接口

`swarm_sim.dataset_audit.audit_dataset(dataset_path, generation_manifest=None, attempt_ledger=None)` 保留原接口；数据集协议为 `mission_v3` 时分派至 `dataset_audit_v3.audit_dataset_v3`，旧协议继续原算法。本模块只读取冻结产物，不重新规划、不重分析、不启动 SITL。

## 输入与可信边界

首先通过 `load_episode` 和清单哈希检查。只有分析 manifest 的 `artifact_sha256` 覆盖的文件用于审计；目录中额外加入的同名可选报告不能成为证据。基础来源为 task、quality、labels、semantic_validation、execution_constraints、phase_windows、allocation 和 execution_metrics。

## 输出

- `audit_version=multi_intent_dataset_audit_v1`；`groups` 按 `(intent, control_mode)` 分组，报告样本数、通用指标、意图指标、时钟等级、编号位置一致性和拓扑分布。
- `metrics` 的每项给出 count/min/median/p95/max、expected_values 和 missing_values。每机指标的分母按飞机数，单场指标按 episode 数；完全缺证据为 count=0、其余统计 null，不能视为测得零。
- 通用指标包括时长、机数、观测/真值有效率、目标区域尺寸、起点跨度、速度、执行/计划路径长度、飞行时长、执行阶段数、屏障等待和执行伪影指标。
- 执行伪影读取 `execution_metrics.json` 的 0.3/0.5 m/s 阈值统计、逐机停靠数、停靠位置分类、静止与同步占比、全机停靠/共同重叠事件数、中间点停靠率。到达滞后和屏障等待的聚合单位是每场中位数，字段名明确包含 `median`。名义偏差无结果时仍报告缺失，不假设为零。只识别 `execution_artifacts_v1`；未知版本记录错误并保留缺失。部分轨迹产生的停靠数下界另列 `execution_lower_bound_stop_counts`，不混进完整停靠数分布。
- 每个意图只检查注册表 `required_audit_metrics` 声明的指标，在真值语义结果内按字段名称查找；不把侦察覆盖率强加给其他意图。`missing_intent_metrics` 与 `missing_common_metrics` 分开。
- `counterfactual_completeness.matrix` 为 family × intent，合格依据是 `episode_quality_eligible`。任务未成功但质量合格的样本可以填充该格。没有合格样本的格明确列在 missing 中。所需意图来自导出数据和可选生成清单，额外纳入生成清单已接受但未导出的 family。
- `id_position_order` 使用按 ID 字典序排列后的飞机对，分别计算东/北坐标升序一致率。坐标差不超过 \(10^{-6}\) m 的平局不进入分母；全平局时比例为 null。另报整场完全一致率与平局对数。
- 拓扑由注册意图的 `topology_signature(task, allocation)` 给出，不从缺失文件重新编译。训练/测试拓扑重合只在同意图、同控制模式内比较，同时报告逐 episode 和去重签名两种分母。无签名的测试 episode 另计，不能作为“不重合”。
- 保留规范化输入的完全重复检测和 family 跨划分泄漏检查。不输出分类准确率，也不把描述性分布视为意图可辨识性证明。

## 当前能力边界

生产注册表仍只有 reconnaissance。测试意图与采样器仅用于临时测试上下文，退出即注销；测试数据只写临时目录。连续模式的审计可以读取明确标记的合成协议样本，但不意味着 WP-E 连续执行编译器或运行器已经实现。缺失的时序/执行指标将如实标记 missing，后续 WP-E 产物到位后再形成实测统计。
