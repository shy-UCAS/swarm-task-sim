# FE-INT：P1 + P0 合并与 30 骨架试点重跑

试点状态：`completed`；完成 30/30，严格配对 30/30；主意图为监视的完成 / 配对 / 总数为 6 / 6 / 6。

## 合并、环境与回归

- 合并提交：`4c15846603b26d614819080dcf8d3dc54a47d73c`；父提交：17c5be07f88e9297f0ba4f9a43d033aa32fe64fd, ae672570c8ea6818f90ce7a367f9b2c79391735c。
- 试点入口提交：`f176dc997dd063ce1330913dbd07e10aa43f673e`，分支 `fe/first-edition-int`。
- 相对基线 09279c2，生产源码恰好改动 5 个文件，各自与 P1/P0 来源提交逐字节一致。
- 回归：113/113，15 模块，耗时 129.204 s。P1 基线 24 项已含在 100 项基线中。
- PowerShell 7.6.5；Conda llm；Python 3.12.3 / NumPy 2.5.3 / Shapely 2.0.7；未安装或升级依赖。
- 原有运行、统计脚本与算法未作任何集成期修改；外部监督程序记录在 supervision_runner.py。

## 执行登记

- 原始结果：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261017T071447Z`。
- 监督日志：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\fe_int_supervision_20261017T071446Z`。
- 同一选样文件、同一 30 个唯一 ID；8 个工作进程，单次墙钟上限 4500 s；实际 4035.063 s。
- 源码/配置/测试文件指纹共核对 785 次；前后一致：True；硬停止事件：None。
- 未完成：无。未完成样本保留在 30 个分母中。

## 新旧对比

| 指标 | 旧基线 | 合并后 |
|---|---|---|
| 完成骨架 / 30 | 27 | 30 |
| 严格配对 / 30 | 24 | 30 |
| 五意图全配对抽签 / 6 | 1 | 6 |
| 失败环节计数（按链路顺序，mode 行） | 0/0/6/0/0/0/0 | 0/0/0/0/0/0/0 |
| 监视：完成 / 严格配对 / 6 | 3 / 1 / 6 | 6 / 6 / 6 |
| 实测逼近方式一致 | 56/56 | 74/74 |
| 最小机间距 min / p50 / max（m） | 2.196 / 15.739 / 22.069 | 2.070 / 15.739 / 22.069 |
| 合计墙钟（s） | 6000.126 | 4035.063 |
| 共同有效样本墙钟 p50 / p90 / max（s） | 268.001 / 675.271 / 1384.913 | 277.883 / 681.677 / 796.011 |

失败环节顺序：规划 / 单机预演 / 时刻叠加间距 / 联合执行超时 / 联合执行质量 / M1 角色判据 / 审计。计数单位是同步、递次版本行，不能当作独立骨架数。
主意图监视为 6 个；含监视组共 7 个，停止条件同时覆盖混合意图骨架。

## 结果解读

本次集成冒烟通过：6 个主监视骨架全部首轮严格配对；重点 ext_004 以 1 个有效候选、1 轮校准成功。总墙钟从 6000.126 s 降至 4035.063 s，完成数从 27 增至 30，严格配对从 24 增至 30。

共同 24 个有效耗时样本中，p50 增加 3.69%，p90 增加 0.95%，最大值降低 42.52%。因此本次不能证明常见骨架普遍提速，也不能把总墙钟差直接归为 P0 的收益。旧试点分 5+25 两批，本次 30 个一次提交，并发排队条件不同；没有隔离实验，不能确定各因素的贡献。

6 个主监视骨架的本次校准轮数均为 1；另外 2 个非监视骨架各有一次中间 timing_conflict，第二轮均成功。它们的冲突机对终点相距超过 1.5 km，不满足监视终点小于 2 m 的硬停止条件。

## 耗时口径与解释边界

两次均有完成记录的交集为 27 个。其中 24 个两次都有有效耗时，以同一组 ID 重算双方分位数；ID 与缺失名单在 comparison.json。
旧基线的 3 个 infeasible 骨架没有记录完整耗时，run_result.wall_s 中的 0 是缺失字段求和产生的占位值，不是零耗时。逐骨架表将此类值显示为 NA，原始记录不改写。
旧试点分两次运行，上限合计 6000 s；本次单次 4500 s。总墙钟变化混合了完成数量、排队和截断差异，不能仅用预算差宣称性能提升。P1 与 P0 的贡献不拆分。
本结果仍是 6 次抽签、以规划全成功为选样前提的集成冒烟测试；fastsim 未经 SITL 校准，不构成生产验收或完整 32 次抽签结果。

## 逐骨架对比

| skeleton_id | 主意图 | 旧状态 | 旧轮数 | 旧墙钟 s | 新状态 | 新轮数 | 新墙钟 s |
|---|---|---|---|---|---|---|---|
| family_s15_1b876e6b8b6f70c6_ext_005_regular | transit | 严格配对 | 2 | 611.238 | 严格配对 | 2 | 601.873 |
| family_s15_1b876e6b8b6f70c6_ext_006_regular | reconnaissance | 严格配对 | 4 | 1120.167 | 严格配对 | 1 | 492.307 |
| family_s15_1b876e6b8b6f70c6_ext_007_regular | monitoring | 未完成 | 1（部分记录） | NA | 严格配对 | 1 | 1661.596 |
| family_s15_1b876e6b8b6f70c6_ext_008_regular | feint | 严格配对 | 2 | 685.472 | 严格配对 | 2 | 637.025 |
| family_s15_1b876e6b8b6f70c6_ext_009_regular | penetration | 严格配对 | 1 | 387.775 | 严格配对 | 1 | 394.022 |
| family_s15_1c267d4d7000043d_ext_005_regular | transit | 严格配对 | 1 | 187.888 | 严格配对 | 1 | 241.460 |
| family_s15_1c267d4d7000043d_ext_006_regular | reconnaissance | 严格配对 | 1 | 154.201 | 严格配对 | 1 | 205.224 |
| family_s15_1c267d4d7000043d_ext_007_regular | monitoring | 严格配对 | 3 | 1384.913 | 严格配对 | 1 | 796.011 |
| family_s15_1c267d4d7000043d_ext_008_regular | feint | 严格配对 | 1 | 177.587 | 严格配对 | 1 | 226.268 |
| family_s15_1c267d4d7000043d_ext_009_regular | penetration | 严格配对 | 1 | 117.011 | 严格配对 | 1 | 154.413 |
| family_s15_38bedc9d791d547b_ext_005_regular | transit | 严格配对 | 1 | 245.448 | 严格配对 | 1 | 215.818 |
| family_s15_38bedc9d791d547b_ext_006_regular | reconnaissance | 严格配对 | 1 | 265.801 | 严格配对 | 1 | 221.485 |
| family_s15_38bedc9d791d547b_ext_007_regular | monitoring | 未完成 | 4 | NA | 严格配对 | 1 | 1198.309 |
| family_s15_38bedc9d791d547b_ext_008_regular | feint | 严格配对 | 1 | 315.701 | 严格配对 | 1 | 311.844 |
| family_s15_38bedc9d791d547b_ext_009_regular | penetration | 严格配对 | 1 | 252.027 | 严格配对 | 1 | 305.164 |
| family_s15_79c93b22d09e8a7a_ext_000_regular | transit | 严格配对 | 1 | 182.908 | 严格配对 | 1 | 188.724 |
| family_s15_79c93b22d09e8a7a_ext_001_regular | reconnaissance | 严格配对 | 1 | 569.492 | 严格配对 | 1 | 611.188 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | monitoring | synchronous:infeasible; sequential:infeasible | 5 | NA | 严格配对 | 1 | 686.227 |
| family_s15_79c93b22d09e8a7a_ext_003_regular | feint | 严格配对 | 1 | 229.020 | 严格配对 | 1 | 250.602 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | penetration | synchronous:infeasible; sequential:infeasible | 5 | NA | 严格配对 | 1 | 509.318 |
| family_s15_aa4c66be8e85d64d_ext_000_regular | transit | 严格配对 | 1 | 160.590 | 严格配对 | 1 | 214.859 |
| family_s15_aa4c66be8e85d64d_ext_001_regular | reconnaissance | 严格配对 | 1 | 197.266 | 严格配对 | 1 | 215.857 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | monitoring | synchronous:infeasible; sequential:infeasible | 5 | NA | 严格配对 | 1 | 663.760 |
| family_s15_aa4c66be8e85d64d_ext_003_regular | feint | 严格配对 | 1 | 270.200 | 严格配对 | 1 | 212.478 |
| family_s15_aa4c66be8e85d64d_ext_004_regular | penetration | 严格配对 | 1 | 189.921 | 严格配对 | 1 | 153.866 |
| family_s15_c713f51898e81011_ext_000_regular | transit | 严格配对 | 1 | 650.773 | 严格配对 | 1 | 700.814 |
| family_s15_c713f51898e81011_ext_001_regular | reconnaissance | 严格配对 | 1 | 550.635 | 严格配对 | 1 | 590.299 |
| family_s15_c713f51898e81011_ext_002_regular | monitoring | 未完成 | 4（部分记录） | NA | 严格配对 | 1 | 2744.702 |
| family_s15_c713f51898e81011_ext_003_regular | feint | 严格配对 | 1 | 651.468 | 严格配对 | 1 | 722.265 |
| family_s15_c713f51898e81011_ext_004_regular | penetration | 严格配对 | 1 | 530.994 | 严格配对 | 1 | 602.632 |

## 新失败明细

无最终失败记录。

### 中间轮次拒绝（包含后续重试成功的骨架）

| 骨架 | 轮次 | category | detail |
|---|---|---|---|
| family_s15_1b876e6b8b6f70c6_ext_005_regular | geometry_00 | timing_conflict | version exhausted its independent timing draw budget |
| family_s15_1b876e6b8b6f70c6_ext_008_regular | geometry_00 | timing_conflict | version exhausted its independent timing draw budget |

### 时刻冲突与对应轮次的终点间距

| 骨架 | 轮次 | 模式 | 冲突机对 | 同组 | 终点间距 m | 含监视组 |
|---|---|---|---|---|---|---|
| family_s15_1b876e6b8b6f70c6_ext_005_regular | geometry_00 | synchronous | uav_01,uav_05 | True | 2418.492 | False |
| family_s15_1b876e6b8b6f70c6_ext_005_regular | geometry_00 | synchronous | uav_07,uav_08 | True | 2397.889 | False |
| family_s15_1b876e6b8b6f70c6_ext_008_regular | geometry_00 | synchronous | uav_03,uav_08 | True | 1545.328 | False |
| family_s15_1b876e6b8b6f70c6_ext_008_regular | geometry_00 | synchronous | uav_02,uav_05 | True | 1517.126 | False |

终点坐标取冲突所在 geometry 轮次 skeleton.json 的组内 references.endpoint_enu_m；这里按轮次、模式、机对去重展示，逐 draw 记录保留在 supervision/timing_conflicts.json。

## ext_004 专项

`family_s15_79c93b22d09e8a7a_ext_004_regular`：严格配对；完成校准轮数 1；候选池大小 1。
候选顺序：[101]；候选预算 200；搜索尝试数 600。候选池大小与尝试数不是同一指标。
该骨架主意图为 penetration，包含 monitoring 组，已纳入监视终点冲突监督。

## 交付与异常

- 监督异常：None；统计异常：[]。
- 证据：merge_verification.json、environment.json、regression.json、comparison.json、sim_pilot/、supervision/。
- 仅向 fe/first-edition-int 进行普通推送（非强制）；不合入 v07-s15/main，不删除工作树，不启动区域搜索修复或批量重测。
