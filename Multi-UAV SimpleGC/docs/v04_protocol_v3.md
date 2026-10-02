# v3 协议、资格与观测处理接口

状态：`IMPLEMENTED_AND_TESTED`。WP-E E3 已接通 v3 分析、双通道窗口及产物生成；离线证据见 [WP-E 报告](v04_wp_e_milestone.md)。实际运行结论以 V1 报告为准。

## 协议与绑定

`protocol.semantic_protocol(scene)` 按 TaskSpec schema 分派。`supported_protocols()` 返回 v1/v2/v3 支持集合。v3 的版本如下：

| 字段 | 值 |
| --- | --- |
| task_kind | mission_v3 |
| ontology_version | multi_intent_mission_v1 |
| label_schema_version | 3 |
| semantic_validation_version | multi_intent_validation_v1 |
| eligibility_protocol_version | multi_intent_quality_v1 |
| execution_constraints_version | multi_intent_execution_limits_v1 |

意图名称与 `control_mode` 不进入协议元组，避免无法同集比较不同意图和控制模式。具体规则版本位于 `labels.label_provenance.validator_versions`，与当前注册项及行为标签中的 `rule_version` 一致。修改任何意图验证规则，都必须同时升级统一 `semantic_validation_version`，不能只改某条标签版本。

v3 校验要求 `task.json`、`labels.json`、`quality.json`、`semantic_validation.json`、`execution_constraints.json` 都被 manifest 的 SHA256 绑定；family 必须按物理内容重算一致。还核对模式、任务意图、任务机数/agent IDs、运行状态与完成标记、时钟等级、资格结论和按飞机保存的有效比例/无效区间。时钟模型附件存在时，机号集合、模型版本和去重版本也必须一致。重新计算文件哈希不能绕过这些交叉检查。

`multi_intent_execution_limits_v1` 已接通两种 v3 控制模式的生命周期约束检查；复用原约束数值规则，并保持起飞至降落全程检查。

## 两级资格

`quality.episode_quality_eligibility(quality)` 检查：运行完成、观测和真值质量、时间诊断、执行约束、可接受的时钟等级，以及观测/真值间距证据。它不以 `mission_success` 或 `semantic_consistency` 为门槛。

`v3_eligibility(quality, labels)` 返回 `episode_quality_eligible`、`benchmark_eligible`、`strict_benchmark_eligible`。后两者保留原有“质量门禁通过且任务成功”的含义，并保留共享任务的执行约束、双通道一致及 FCU 任务成功门禁。质量合格但任务失败的 episode 保留，标记为 `episode_quality_eligible=true`、`benchmark_eligible=false`。

`invalid_intervals(traces, maximum_gap_s, flags=None)` 记录每架飞机的无效采样、缺口和异常原因。它不实现窗口级资格，也不会通过裁剪窗口外异常提升整条流的资格。

## 导出、加载与特征边界

`build_dataset(run_paths, output, salt=..., allow_mixed_control_modes=False)` 默认拒绝混合 v3 控制模式；显式允许时记录 `control_modes`、`allow_mixed_control_modes` 和 `mixed_control_modes`。CLI 对应 `dataset --allow-mixed-control-modes`。v2/v3 仍不能混合导出。

数据集按 family 整组划分，保存意图、模式、质量资格、任务成功与语义一致性。加载器检查 episode 与数据集记录的版本、family、模式、状态、资格和机号一致。`load_episode()` 输入仍只有六个 ENU 位置/速度特征，形状为 \(T\times N\times6\)，以及独立的有效掩码。任务、真值、执行诊断、家族和意图都不自动加入特征；标签独立返回。

## v3 观测接口

`observation_processing.filter_exact_duplicates(packets, ...)` 返回保留包和审计记录；`prepare_v3_observations(packets, origin, policy, epoch, end)` 返回采样流、时钟模型、去重审计及处理版本。它们不修改原始记录，当前不会被 v1/v2 调用。

| 字段 | 固定版本 |
| --- | --- |
| observation_processing_version | v3_observation_v1 |
| duplicate_policy_version | exact_duplicate_drop_v1 |
| timeline_policy_version | full_stream_strict_v1 |
| clock_model_version | passive_system_time_piecewise_v1 |

只丢弃同一身份/消息类型、同一源时刻且完整消息字段一致的重复记录，保留首次包及丢弃计数、原行号。回到旧时刻的相同包仍是时间回退；同时间字段冲突也不当作重复丢弃。任一冲突、回退或无效时间都使相关全流失效，后续正常包不能恢复。SYSTEM_TIME 异常使时钟不可用；时钟不可用时不输出冒充可对齐的有效观测。

去重后才按冻结的被动 SYSTEM_TIME 方法拟合时钟并进行训练/验证拆分，不能沿用去重前模型。窗口信息只用于重复包位置审计，不缩小单调性门禁范围。`analyze_run` 将 v3 分派给 `analysis_v3`；manifest、quality、标签 provenance、观测审计、语义验证、窗口、执行约束、执行指标及飞行/生命周期时钟模型均记录四个版本，加载前交叉核对。

v2 的 `execution_metrics.json` 是可选诊断附件，不改变六维特征与语义协议；添加前后的真实 v2 运行可以混合导出和加载，实测结果见 WP-E 报告。v3 所有验证器的具体版本记录在 `labels.json` 的 `label_provenance.validator_versions`；它与四个观测处理版本含义不同。
