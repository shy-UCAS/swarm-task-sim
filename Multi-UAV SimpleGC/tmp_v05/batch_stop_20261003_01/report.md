# v0.5 双意图数据集报告

**结论：批量已停止，尚未完成最终数据集验收。**

批量完成 1/240 次，尝试 1/264 次；试生产已完成 20/20 次。数据集仅用于算法链路开发，不能用于报告意图识别准确率。

## 异常与研究结果影响

停止原因：`infrastructure_or_integrity_failure: FileNotFoundError: [WinError 3] 系统找不到指定的路径。: 'F:\\CASIA\\Drone Swarm Situational Awareness Algorithm\\Simulation\\Multi-UAV SimpleGC\\verification\\v05_batch_20261002\\analyses\\B001_attempt_0'`。

对研究结果的具体影响：运行配置或证据来源未通过冻结核对，任务执行与标签的对应关系及可复现性不能成立。

记录异常 1/21 次；原始标记、质量证据和全部来源见[报告 JSON](report.json)。

## 实现与测试

批量控制与断点台账：[run_v05_batch.py](../../scripts/run_v05_batch.py)；只读汇总：[build_v05_batch_report.py](../../scripts/build_v05_batch_report.py)；描述生成与一致性：[language_v0.py](../../swarm_sim/language_v0.py)。

本轮完整测试已执行 642/642 项，全部通过：True；[日志](../batch_execution_20261002/full_tests.log)。

试生产非必需返航描述核对、修复及重生成证据直接引用[只读核对报告](../batch_return_check_20261002/report.md)；没有重飞。

## 验收与数据集概况

| 意图 | 质量合格 / 已执行 | 合格内真值成功 | 真值成功 / 失败 / 未知 | 标签不一致 |
| --- | --- | --- | --- | --- |
| reconnaissance | 10/11（90.9%） | 10/10（100.0%） | 10/11 / 0/11 / 1/11 | 0/11（0.0%） |
| patrol | 10/10（100.0%） | 10/10（100.0%） | 10/10 / 0/10 / 0/10 | 0/10（0.0%） |

最终验收要求：全部质量合格至少 90%；双意图均合格场景至少 85%；质量合格内各意图任务成功至少 90%；可描述 episode 覆盖 100% 且一致性全部通过；审计 issues 为空或逐项解释。

当前全量质量合格 20/21（95.2%）；双意图均质量合格场景 10/11（90.9%）。

尚无通过的最终导出/审计/描述/加载验收；不将当前完成部分表述为完整数据集。

## 巡逻阶段时序进度差

仅统计巡逻群阶段的 primary 值；truth 与 observation 分列，不按单机/机对重复计数，也不混入 event crosscheck。完整且 \(D\)、\(\tau\) 均有限才计入已知分母；超限定义为 \(D>\tau\)。中位数、最大值只取已知值，未知单列。本表仅供以后改进规划安全估算，不是本轮门禁。

| 范围 | 通道 | D 中位数 s | D 最大值 s | 超限 / 已知 | 未知 / 全部阶段 | 已执行巡逻 / 计划 |
| --- | --- | --- | --- | --- | --- | --- |
| batch | truth | null | null | 0/0（未知） | 0/0 | 0/120 |
| batch | observation | null | null | 0/0（未知） | 0/0 | 0/120 |
| pilot_and_batch | truth | 1.247 | 2.447 | 0/10（0.0%） | 0/10 | 10/130 |
| pilot_and_batch | observation | 1.145 | 2.534 | 0/10（0.0%） | 0/10 | 10/130 |

## 软标记与执行分布

软标记按运行去重；同一运行可出现多项，不能相加作为异常运行数。

| 意图 | 标记 | 发生运行 / 该意图运行 | exceeded / unknown |
| --- | --- | --- | --- |
| reconnaissance | AV-1 | 0/11（0.0%） | 0/11；0/11 |
| reconnaissance | AV-2 | 1/11（9.1%） | 1/11；0/11 |
| reconnaissance | AC4 | 0/11（0.0%） | 0/11；0/11 |
| patrol | AV-1 | 6/10（60.0%） | 0/10；6/10 |
| patrol | AV-2 | 1/10（10.0%） | 1/10；0/10 |
| patrol | AC4 | 7/10（70.0%） | 7/10；0/10 |
| patrol | AV-8 | 0/10（0.0%） | 0/10；0/10 |

## 证据位置与已知限制

控制台账：[control.json](../../verification/v05_batch_20261002/control.json)；完整报告及来源哈希：[report.json](report.json)。
历史离线门禁、DR、验证和试生产结果引用[暂停 1 报告](../../docs/v0.5_r1.2b_pause1_report.md)及其附件；终点驻留为 0，VP4/HD 已取消。当前数据契约：[data_contract_v0.md](../../docs/data_contract_v0.md)。

已知限制：每种意图只有一种执行策略；内部扫描与边界巡逻的空间差异可能成为强线索；两类时长未均衡；场景较小；无分布外划分或近重复检测；arrival_s 兜底与约 1 s 阶段边界精度保留；时序容差上限依赖经验；覆盖率采用理想观察模型；运动模式检测为启发式；描述来自规则模板。严格时钟资格比例见报告 JSON。不能用本数据集报告意图识别准确率。
