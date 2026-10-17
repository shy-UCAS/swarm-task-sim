# G-2a 本轮交付与停止记录

|阶段|状态|说明|
|---|---|---|
|R0|R0_REVALIDATED_PASS|原始 282 条保留，矩形螺旋零可评价为 N/A|
|R1|R1_REVALIDATED_PASS|attempt05：209 执行、205 PASS、4 已知故障、零新增；7 r2 历史逐位一致，7 r3/B2 逐位一致|
|R2|PASS|282 完整、双通道成功一致 282/282、已知运动一致 226/226|
|R3|BLOCKED|固定 FE 扩大测试集暴露额外 14 项未豁免故障，停止于 P2 合并之前|
|R4|未执行|R3 未通过|

## 核心对照

七探针低速事件数 243 → 9。probe_05 最大偏差 1.7849249178526083 → 1.7853429850690588 m；两版均超过 0.5 m，按 G-2a 仅为已知限制/诊断；最大分阶段增加约 1.336 mm。不能宣称已消除全数据集意图捷径。

|校准诊断|r2|r3|
|---|---:|---:|
|total_duration_abs_relative_median|0.015704996882|0.0176052658304|
|total_duration_abs_relative_p95|0.0793458106968|0.0793458106968|
|observe_duration_abs_relative_median|0.0207470172753|0.00819763898787|
|turn_min_speed_abs_difference_median|0.787406187739|0.366821905218|
|lateral_task_p95_median_m|0.406362571937|0.405811093985|

R2 总时长误差中位数变差；每个指标的逐任务值和最差 10 条保留在 R2_gate.json / R2_report.md。R2 最小机间距 7.239747259671382 m。

生产算法、r2 冻结配置和既有测试本轮未修改；P2 未合并。未启动 SITL，未访问 sealed holdout 或重复 internal holdout，未正式冻结/打标签/合并稳定分支/量产。

## 证据索引

- gate_audit_G2a.json / gate_audit_G2a.md：完整分类与当时已有数据干跑。
- R1_revalidated_gate_attempt05.json / R1_revalidation_attempt05_report.md：R1 完整重验。
- R2_gate.json / R2_report.md：282 条原 tiers 验收及数值对照。
- R3_gate.json / R3_report.md / R3_baseline_failure_inventory.json：停止位置、476 项测试及18项堆栈。
- R3_harness_repair_01.json：新额度 1/2 次修复记录。
- pipeline_state.json：阶段状态。

当前需要人工审查额外 14 项旧测试故障与现行合同的关系。本轮不自动豁免。最终提交 SHA 以本报告所在 Git 提交及交付回复为准；仅非强制推送 fe/m3-r3-p2-candidate。
