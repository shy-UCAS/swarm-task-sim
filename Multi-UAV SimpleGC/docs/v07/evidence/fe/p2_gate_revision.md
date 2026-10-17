# FE-P2 提案级实验启动门槛修订

本记录依据用户新版《多向区域搜索最小修复与 A/B 验证》指令，授权在固定基线 92068b95416a53d8e84a90488d06112d367f0c09 上开展独立实验。

原诊断保持原样，状态仍为 GATE_NOT_MET。原形态尝试门槛要求 ingress_line_blocked 至少占 50%；completed_owner 实际为 10,416 / 40,641 = 25.63%，上一轮依指令正确停止。本记录不追溯改变原验收结果。

原门槛混合了随机面积不可用、扫描条带不足和入口预检等不同拒绝来源。survey_area_unavailable 出现 26,168 次，不能证明它只是随机噪声，也不能判定其对产量无影响；本轮将其列为独立未修复因素。

新门槛采用 completed_owner 提案级统计，同一提案包含多条 slot/segment 证据仍只计一次：

\[
P=\frac{\text{包含目标设施 entry\_to\_work\_start 违规证据的被拒提案数}}{\text{area\_search 被拒提案数}}
\]

| 指标 | 多向 | 同向 |
|---|---:|---:|
| 被拒提案 | 2035 | 449 |
| 包含目标入口直线冲突证据的提案 | 1833 | 0 |
| 比例 | 90.07% | 0% |
| 修订门槛 | 至少 80% | 至多 1% |
| 结论 | PASS | PASS |

90.07% 仅表示存在此类证据的提案比例，不表示修复后可恢复的比例、理论收益上界或预期收益。同一提案可同时含面积不足与入口冲突等原因。

目标判断与 summarize_v07_s15_yield.py::classify() 一致：entity_id == target_id 或 entity_id.startswith(target_id + "_")；原诊断已通过场景实体登记和 facility_id 对应关系核验，异常为零。

## 固定队列

全部 reconnaissance 32 个：multi_direction 15 个，same_direction 17 个。公共抽签沿用历史描述符，清单仅保存 ID，不重抽种子。

| approach_mode | 仅 area_search | 仅 close_observation | 两种方法混合 | 合计 |
|---|---:|---:|---:|---:|
| multi_direction | 8 | 4 | 3 | 15 |
| same_direction | 8 | 7 | 2 | 17 |

按方法包含关系统计时，混合骨架会同时属于两种方法分层，不能相加作为主意图分母。历史 6/15 属于 reconnaissance 多向整体，仅作历史参考。

A/B 使用同一描述符、32 ID、公共抽签和原有预算，8 进程，每次 2400 秒；最多仅对未完成项续跑一次。每个骨架选择一份完成结果。若仍有未完成则暂停完整 A/B 验收。

仅可修改 ingress_issues()；不修改 survey_area_unavailable、其他算法、配置或预算，不运行 M2/fastsim/M1 生产。

## 输入和历史文件指纹

- 描述符：F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15desc_20261016T154909Z
- 描述符 SHA256：1e5e0be6332ee3edba613b024bf4ce2dfc7ba0271949860ed16fa7695782a128
- 固定清单 SHA256：4169d69be467c33ce6c9337382b2e5d2d4105d52f944ff6ee142f22b464b2d97

- scripts\diagnose_v07_fe_p2_area_search.py：937daac1a822f9e435828d166638f1244904cae0f65660e0478cb7b307d2c52b
- docs\v07\evidence\fe\p2_area_search_diagnosis.md：c7ae3a255d04dfddabe43cf63586f15612d92818b2a117540c785f3ca30307db
- docs\v07\evidence\fe\p2_area_search_diagnosis.json：eaaace36520653f8d56f20f82784d46c8896d4b4c04a4dbe1df10892bd3a97ba
