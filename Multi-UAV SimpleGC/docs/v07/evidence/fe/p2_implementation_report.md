# FE-P2 多向区域搜索最小修复：实施与验收记录

最终规划判定：**P2_PLANNING_GAIN_CONFIRMED**。

## 范围与实验登记

固定算法基线为 `92068b95416a53d8e84a90488d06112d367f0c09`，工作分支 `fe/area-search-precheck`。生产代码仅修改 `task_v07/unified/construction.py::ingress_issues()`：area_search 第二段预检从入口至作业起点直线改为真实入口对准段；其后连接仍使用原路径规划和整线判据。其他任务方法保留原入口段。
140 个生产源码及配置文件审计仅发现这一文件变化；AST 差异仅在这一函数。`retreat_endpoint()` 及其后源码、原有测试、配置均与固定基线一致。详见 `p2_source_scope_audit.json`。
原诊断 `GATE_NOT_MET` 原样保留。提案级新启动门槛为多向 1833/2035、同向 0/449；90.07% 是含相关证据的拒绝提案比例，不能当作可恢复比例。`survey_area_unavailable` 是独立未修复问题。其观测尝试次数下降可能来自形态搜索更早成功并终止尝试，不能视为已修复该原因。

固定全部 32 个 reconnaissance 骨架：多向 15、同向 17。按实际 execution_method 分层，多向含 area_search 的骨架 11、同向 10；混合方法骨架在两类方法分层中重叠，不能相加。公共抽签与主意图分层详见对照报告。包含 close_observation 的多向混合骨架也可因另一 area_search 组恢复而成功；这不表示 close_observation 提案改变。
描述符 SHA256：`1e5e0be6332ee3edba613b024bf4ce2dfc7ba0271949860ed16fa7695782a128`。选样 SHA256：`4169d69be467c33ce6c9337382b2e5d2d4105d52f944ff6ee142f22b464b2d97`。A/B 环境、输入、种子和预算核验一致，每组 200 提案、20 形态尝试、10 连接尝试、1000 组合、8 进程、每 attempt 上限 2400 秒。

## 正确性

固定基线原回归 113/113 通过。修改后原有 113/113、新增 7/7 通过，无跳过、无既有测试断言修改；最终测试总墙钟 117.703 s，运行中生产源码与配置指纹稳定。使用 `python -B -m unittest -v` 模块入口。
新增测试覆盖非 area_search 固定输入完整证据及顺序相等、单股和多股入口端点、实际 alignment 配置读取、真实候选的合同和确定性恢复。
首轮新增测试 5/6 通过、1 项失败：generic fixture 有合法候选，但未出现旧入口冲突，不能证明修复有效性。这份失败记录保留在 `p2_tests_after/`。随后按 G3 T3 明确许可，使用 G1 原登记 descriptor 与 scene，未改变场景、种子或约束，保持 20 提案测试上限及强断言，并保留原 generic fixture 的候选合同测试。最终日志在 `p2_tests_after_verified/`；输入来源及哈希在 `p2_functional_fixture_revision.json`。
确定性案例：`family_s15_1b876e6b8b6f70c6_ext_006_regular / task_group_01 / candidate_index=1`，seed `7778664290258953489`。旧实现有 1 条目标设施 entry_to_work_start 禁入冲突；新入口预检无冲突，原 route_operation 被实际调用，plan_checks 与原 precheck 均为 PASS。
全部有效候选的保存合同核验：A=4734，B=5852。非 area_search 变化提案数=0。P0 停止事件=0；硬停止事件=0。最终独立保存结果审计见 `p2_final_audit.json`。

## A/B 主要结果

| 指标 | A 原版 | B P2 |
|---|---|---|
| 多向 area_search 合法组提案/提案 | 104/2400 | 1222/2400 |
| 同向 area_search 合法组提案/提案 | 1532/2400 | 1532/2400 |
| 多向 area_search 骨架 PASS/完成 | 2/11 | 10/11 |
| 同向 area_search 骨架 PASS/完成 | 9/10 | 9/10 |
| 多向 reconnaissance 整体 骨架 PASS/完成 | 6/15 | 14/15 |
| 同向 reconnaissance 整体 骨架 PASS/完成 | 16/17 | 16/17 |
| 入口预检拒绝（area_search，形态尝试） | 11038 | 653 |
| 正式连接终局失败（area_search，配对提案） | 288 | 369 |
| 面积不可用（area_search，形态尝试） | 32736 | 18214 |
| 未完成骨架 | 0 | 0 |

这些 A 值来自本轮新运行，不能替换成历史 S1.5 的提案统计。A 的多向/同向 area_search 分别为 104/2400、1532/2400；历史 6/15 是多向 reconnaissance 整体骨架成功数，本轮 area_search 子集为 2/11。
正式连接失败按终局停在 connection 阶段的不同提案计数；嵌套连接尝试、形态尝试、slot/segment 证据不能相加。表 B 同时给出终局原因、提案内去重原因、形态尝试、连接尝试、phase 证据与 phase 提案命中数。
A/B 均已完成全部 32 个骨架，完整配对 8000 条提案，无缺失。A 首次 attempt 的未完成部分被保留但不计入统计，续跑只采用该骨架的完整结果。

### 关键阶段变化

| 统计量（area_search 全部分层） | A | B |
|---|---|---|
| proposal_reason_hits: ingress_line_blocked | 2086 | 484 |
| proposal_phase_hits: entry_to_work_start | 2057 | 0 |
| phase_evidence_entries: entry_to_work_start | 38953 | 0 |
| proposal_reason_hits: inner_alignment_blocked | 3 | 0 |
| proposal_reason_hits: no_interior_connection | 59 | 142 |
| final_reasons: connection_search_budget_exhausted | 288 | 369 |
| final_reasons: whole_route_check | 714 | 1210 |

对以上原因采用可重叠的提案命中或指定的单独统计单位，不将原因标签求和当作失败提案总数。
同向 area_search 接受率变化：0.0 个百分点。
提案接受状态迁移：`{"multi_direction": {"reject_to_accept": 1142, "accept_to_reject": 24}, "same_direction": {"reject_to_accept": 0, "accept_to_reject": 0}}`。
B 新出现的终局 reason 类型：`{"same_direction/area_search": [], "multi_direction/area_search": [], "multi_direction/close_observation": [], "same_direction/close_observation": []}`；出现次数及其他原有失败变化见表 B。

### 可核验恢复案例

A 含目标入口直线冲突且被拒、B 同索引通过的提案共 1142 个。

- `family_s15_1b876e6b8b6f70c6_ext_006_regular / task_group_01 / 1`，seed `7778664290258953489`。A：whole_route_check；B：group_feasible；整线及原预检均 PASS。
  - A 原始日志：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261017T105201Z\family_s15_1b876e6b8b6f70c6_ext_006_regular\proposals.jsonl`
  - B 原始日志：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261017T122223Z\family_s15_1b876e6b8b6f70c6_ext_006_regular\proposals.jsonl`

- `family_s15_1b876e6b8b6f70c6_ext_006_regular / task_group_01 / 6`，seed `3333024390104404114`。A：whole_route_check；B：group_feasible；整线及原预检均 PASS。
  - A 原始日志：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261017T105201Z\family_s15_1b876e6b8b6f70c6_ext_006_regular\proposals.jsonl`
  - B 原始日志：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261017T122223Z\family_s15_1b876e6b8b6f70c6_ext_006_regular\proposals.jsonl`

- `family_s15_1b876e6b8b6f70c6_ext_006_regular / task_group_01 / 18`，seed `9767902868084695732`。A：whole_route_check；B：group_feasible；整线及原预检均 PASS。
  - A 原始日志：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261017T105201Z\family_s15_1b876e6b8b6f70c6_ext_006_regular\proposals.jsonl`
  - B 原始日志：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261017T122223Z\family_s15_1b876e6b8b6f70c6_ext_006_regular\proposals.jsonl`

### 实际路线与耗时

B 成功 area_search 选中路线的绕行系数统计：`{"count": 142, "min": 1.0156738592739596, "p50": 1.1884387596706965, "p90": 1.947863081059921, "max": 3.3788060870993957}`。另有 3 个成员存在多重有序锚点定位，无法唯一确定区间，已排除在绕行系数统计外。
入口/作业锚点可能被 clean_joints 作为前向共线点清理。保留精确顶点匹配结果，并在实际折线段上以原数值精度 1e-6 m 唯一、有序定位，记录残差，累加实际路线弧长（含端点所在段的相应部分）。不以直线距离替代路线长度，不改变接受容差。
最大定位残差：9.094947017729282e-13 m。各组原 `multi_max_pairwise_ingress_heading_deg` 见 table_E.headings，原多向检查随 selected_checks 核验。

| 组 | 骨架耗时 p50 / p90 / max 秒 | attempt 总墙钟秒 | 续跑墙钟秒 | 源码稳定 |
|---|---|---|---|---|
| a | 41.424 / 1303.951 / 2180.599 | 4476.750 | 2076.687 | True |
| b | 42.041 / 362.783 / 547.602 | 871.094 | 0.000 | True |

耗时来自本机非隔离批次，不将 A/B 差异归因于单项代码修改；总 attempt 墙钟包括未完成部分的尝试开销。每骨架耗时和未完成详情见对照 JSON。

## 文件、attempt 与提交

- `p2_ab_baseline.json` / `.md`：本轮 A 基线。
- `p2_ab_comparison.json` / `.md`：六表、公共抽签分层、全部提案配对和恢复证据。
- `p2_primary_results.json`：主表和迁移简表。
- `p2_validation.json`、`p2_source_scope_audit.json`：测试和源码审计。
- `p2_tests_before/`、`p2_tests_after/`、`p2_tests_after_verified/`：原基线、首次失败和最终通过日志。

A 代码提交：`e9715af44872adee98d7dd4ef3ff4a2658ce7d5d`。
- `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261017T105201Z`：TIME_LIMIT_STOP，完成 31/32；registration/run_result/全部采用结果文件哈希见比较 JSON。
- `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261017T113244Z`：completed，完成 1/1；registration/run_result/全部采用结果文件哈希见比较 JSON。

B 代码提交：`26e00280280bd557c3294d6191200141bec410c2`。
- `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261017T122223Z`：completed，完成 32/32；registration/run_result/全部采用结果文件哈希见比较 JSON。

已完成阶段提交：

- G0：`e9715af44872adee98d7dd4ef3ff4a2658ce7d5d`。
- A 基线：`873c4fbe086d6bf2b13539c3ca0669ab466e755b`。
- G2/G3：`26e00280280bd557c3294d6191200141bec410c2`。
- 本报告与对照证据按 `FE-P2c evidence: area_search A/B planning comparison` 提交；最终本地/远端 SHA 在交付回复核验。

## 判定边界与停止点

本轮结果分类为 `P2_PLANNING_GAIN_CONFIRMED`。多向 area_search 接受率从 4.33% 增至 50.92%（+46.58 个百分点），含 area_search 骨架从 2/11 增至 10/11；同向提案与骨架结果不变。尽管正式连接终局失败 288→369、整线拒绝 714→1210，仍净增 1118 个最终合法提案（1142 个恢复、24 个反向损失）和 8 个完整多向骨架，符合规划收益门槛。
本轮仅做纯规划验证和指定离线测试，没有运行 M2 预演、联合 fastsim、M1 正式生成或量产。不外推五意图整体产率。未改 survey_area_unavailable，不合并、不打标签。普通推送审查分支后停止，由人工独立决定后续合并与配对仿真试点。
