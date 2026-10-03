# 试生产停止 01：已完成运行的部分诊断附件

本附件只含 5 项验证与已经完成的 8 次试生产，包含第 8 次的硬门禁失败证据；不是暂停 1 合并报告，也不是试生产验收通过。

验证预算 6/8；试生产完成 8/20，尝试 8/22，PP09 尚未启动。数据质量资格为 8/8、已完成双意图场景为 4/4；这些计数不覆盖 PP08 的 `known_consistent_labels` 硬失败。

| 用例 | 意图 | 真值 / 观测任务成功 | 语义一致性 | 硬门禁 | 质量资格 | 软标记数 |
| --- | --- | --- | --- | --- | --- | ---: |
| VP1 | patrol | True / True | agree | PASS | True | 4 |
| VP2 | patrol | True / True | agree | PASS | True | 2 |
| VP3 | patrol | True / True | agree | PASS | True | 3 |
| VR1 | reconnaissance | True / True | agree | PASS | True | 0 |
| VR2 | reconnaissance | True / True | agree | PASS | True | 0 |
| PP01 | reconnaissance | True / True | agree | PASS | True | 0 |
| PP02 | patrol | True / True | agree | PASS | True | 0 |
| PP03 | reconnaissance | True / True | agree | PASS | True | 0 |
| PP04 | patrol | True / True | agree | PASS | True | 5 |
| PP05 | reconnaissance | True / True | agree | PASS | True | 0 |
| PP06 | patrol | True / True | agree | PASS | True | 2 |
| PP07 | reconnaissance | True / True | agree | PASS | True | 0 |
| PP08 | patrol | False / True | disagree | FAIL | True | 1 |

进场共 38 架次、76 条通道记录；起始航向全部为 0，航程/出发/到达数值缺失 0 条。到达使用最近距离兜底的 11 条另列，不视作已验证停稳到达。

逐机航程、名义时长、AUTO/运动出发、双通道到达与转角见 [进场表](partial_diagnostics/report.md)，完整来源、兜底及软指标分母见 [JSON](partial_diagnostics/report.json)。主值和事件交叉核对分布另见 [AC4 来源表](partial_ac4_source_distributions.json)。

## 软门禁部分分布

| 组别 / 阶段 / 通道 | 代码 / 状态 / 来源 | 标记数 |
| --- | --- | ---: |
| pilot / patrol / p00_approach / observation | AC4 / exceeded / primary | 1 |
| pilot / patrol / p00_approach / truth | AC4 / exceeded / primary | 2 |
| pilot / patrol / p02_return / truth | AC4 / exceeded / event_crosscheck | 1 |
| pilot / patrol / p02_return / truth | AC4 / exceeded / primary | 1 |
| pilot / patrol / None / observation | AV-1 / unknown / None | 2 |
| pilot / patrol / None / observation | AV-2 / exceeded / None | 1 |
| validation / patrol / p00_approach / observation | AC4 / exceeded / primary | 2 |
| validation / patrol / p00_approach / truth | AC4 / exceeded / event_crosscheck | 1 |
| validation / patrol / p00_approach / truth | AC4 / exceeded / primary | 2 |
| validation / patrol / p02_return / observation | AC4 / exceeded / event_crosscheck | 1 |
| validation / patrol / None / observation | AV-1 / unknown / None | 1 |
| validation / patrol / None / observation | AV-2 / exceeded / None | 2 |

按标记记录计数；同次运行可有多个标记，不等同于运行数。AV-1/AV-2 按意图与阶段的数值、未知分母保存在诊断 JSON；不填补未知，不将部分分布当作 20 次总体。

## 进场到达兜底

| 用例 / 飞机 / 通道 | 到达 s | 来源 | 已验证停稳 |
| --- | ---: | --- | --- |
| VP2 / uav_02 / truth | 29.6 | trajectory_min_distance | False |
| VR1 / uav_02 / truth | 21.9 | trajectory_min_distance | False |
| VR2 / uav_03 / truth | 35.3 | trajectory_min_distance | False |
| VR2 / uav_03 / observation | 35.4 | trajectory_min_distance | False |
| PP01 / uav_02 / truth | 24.1 | trajectory_min_distance | False |
| PP01 / uav_02 / observation | 24.2 | trajectory_min_distance | False |
| PP03 / uav_01 / truth | 24.1 | trajectory_min_distance | False |
| PP05 / uav_03 / truth | 35.4 | trajectory_min_distance | False |
| PP05 / uav_03 / observation | 35.5 | trajectory_min_distance | False |
| PP06 / uav_02 / truth | 35.4 | trajectory_min_distance | False |
| PP08 / uav_02 / truth | 23.2 | trajectory_min_distance | False |

## 完整性与尚缺证据

受保护文件 11307 个均通过，验证和试生产冻结输入及逐次证据哈希通过，两个控制台账在只读汇总前后未变。具体计数和 SHA256 见 [完整性清单](partial_integrity_and_pending.json)。

- PP09-PP20: 12 logical runs have not been started
- 20-run and 10-pair pilot final acceptance has not been performed
- pilot dataset export, audit, describe and loader finalization not performed
- five actual pilot description examples and fact-channel disagreement summary not available
- full 20-run execution distributions, 25-run combined diagnostics and production estimates pending
- Pause 1 consolidated acceptance report not generated; current state is a hard stop before Pause 1
- remaining 240-run batch not authorized or started
