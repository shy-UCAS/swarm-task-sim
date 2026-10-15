# Traj2Language v0.7 S2 修订轮执行与验收记录

本轮以 `S2_revision_handoff_ec86137.md` 为有效入口；旧第二段交接第 3 节、条件—审计表及执行记录继续有效，冲突以本轮入口与用户当前澄清为准。

## 范围与用户澄清

- 这是防御方意图识别的抽象合成轨迹研究，改动服务于样本分布与标签口径；不改 fastsim、冻结配置、竖切行为或 SITL。
- **监视时长只测量，不是修改目标。** 任务 I 后仅用仿真时长预测意图的捷径检查只作诊断；不为缩短时长改变圈数、原允许环线半径范围或任何角色参数。任务 C 的半径在原允许连续范围内随机抽样。
- 编队形态及走廊宽度规则保持；语义条件不放松。规划间距改为 10 m 不改变实测小于 2 m 的生成错误判据。
- 每个任务本地提交，不推送；仅标签与实测矛盾、模型输入泄漏、现有功能损坏或意图相关公共抽样/速度变化触发 P0 提前停止。失败、低产率和目标未达如实报告。

## 任务 0：接手基线

- 指定基线：`ec86137`。实际 HEAD：`ffb2c0261200a3e75c1792c5bcd889b27040519b`，分支 `v07-scene`。
- `ec86137..ffb2c02` 只新增旧数据离线偏差分析脚本 `scripts/analyze_v07_s2_sampling_bias.py` 与报告 `docs/v07/S2_phase2_sampling_bias_audit_20261014_verified.md`；生成器、标签、执行、固定回归和测试文件没有变化。保留该已有提交，不重置分支。
- 接手时已跟踪文件干净，唯一未跟踪文件是用户指定的本轮交接入口；与“HEAD 为 ec86137、完全干净”的字面状态有上述差异，已明确登记。
- PowerShell 7.6.5；项目 `.conda-env` 为 `llm`。受限沙箱启动 Conda 出现 DLL 重定位错误，改为沙箱外运行同一环境，没有切换解释器或修改依赖。
- S2 测试：`python -B -m unittest discover -s tests -p 'test_v07_s2*.py'`，**120/120 PASS**，26.164 s。
- 三组固定回归：`attempt_s2x_regress_20261015T025544Z_e1874339`，6 进程，**22/22 PASS**，1211.758 s，内容差异 0。竖切 8 条和新角色 10 条的标签逐字节相同；过境 4 条仅有既有基准允许的 `work_end_s` 字段与对应哈希变化。
- 冻结配置 SHA256 实查为 `94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193`，未变化。

## 执行顺序

0 基线 → 1 修订前四维诊断 → A 预警进入口径/生成/独立审计 → B 撤离距离 → C 连续随机候选 → D 公共分股与方位差 → E 规划间距 → F 中止引用回退 → G 全 60 骨架仅规划冒烟 → H 冻结全量重跑与进程对比、视图 → I 960 项交叉否定 → 捷径诊断、完整报告与图件。

任务 1 的组规模按每个骨架**最大任务组成员数**分档；已有离线报告按“含某规模组”跨档计数，不能直接复制为本轮矩阵。

各任务实际完成证据依次记录在下文；修订后的正式样本和成功率以任务 H 的全量 attempt 为准。

<!-- revision-matrices:修订前 -->
## 修订前：四维骨架成功率

来源：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s2x_final_20261014T164338Z_4f85aaa3`，生成提交 `e8fe856e51e8aa7b4b38697f811793e32fe22dd1`。
成功要求两种时序均生成、任务成功、质量有效且独立审计通过。每个维度的总分母均为 60 个骨架；规模按最大组分档，各档互斥，不跨档重复。未登记组合不计为零成功。

### 意图 × 逼近方式

| 意图 | 条件 | 成功/登记 | 成功率 |
|---|---|---|---|
| 过境 | same_direction | 3/5 | 60.00% |
| 过境 | multi_direction | 5/7 | 71.43% |
| 侦察 | same_direction | 2/5 | 40.00% |
| 侦察 | multi_direction | 2/7 | 28.57% |
| 游弋监视 | same_direction | 0/5 | 0.00% |
| 游弋监视 | multi_direction | 3/7 | 42.86% |
| 佯动 | same_direction | 4/5 | 80.00% |
| 佯动 | multi_direction | 4/7 | 57.14% |
| 突防 | same_direction | 3/5 | 60.00% |
| 突防 | multi_direction | 5/7 | 71.43% |

### 意图 × 设施数

| 意图 | 条件 | 成功/登记 | 成功率 |
|---|---|---|---|
| 过境 | 1 | 4/4 | 100.00% |
| 过境 | 2 | 2/4 | 50.00% |
| 过境 | 3 | 2/4 | 50.00% |
| 侦察 | 1 | 2/4 | 50.00% |
| 侦察 | 2 | 0/4 | 0.00% |
| 侦察 | 3 | 2/4 | 50.00% |
| 游弋监视 | 1 | 2/4 | 50.00% |
| 游弋监视 | 2 | 0/4 | 0.00% |
| 游弋监视 | 3 | 1/4 | 25.00% |
| 佯动 | 1 | 3/4 | 75.00% |
| 佯动 | 2 | 2/4 | 50.00% |
| 佯动 | 3 | 3/4 | 75.00% |
| 突防 | 1 | 3/4 | 75.00% |
| 突防 | 2 | 4/4 | 100.00% |
| 突防 | 3 | 1/4 | 25.00% |

### 意图 × 合并后任务组数

| 意图 | 条件 | 成功/登记 | 成功率 |
|---|---|---|---|
| 过境 | 1 | 6/7 | 85.71% |
| 过境 | 2 | 2/4 | 50.00% |
| 过境 | 3 | 0/1 | 0.00% |
| 侦察 | 1 | 3/7 | 42.86% |
| 侦察 | 2 | 0/4 | 0.00% |
| 侦察 | 3 | 1/1 | 100.00% |
| 游弋监视 | 1 | 2/7 | 28.57% |
| 游弋监视 | 2 | 1/4 | 25.00% |
| 游弋监视 | 3 | 0/1 | 0.00% |
| 佯动 | 1 | 5/7 | 71.43% |
| 佯动 | 2 | 2/4 | 50.00% |
| 佯动 | 3 | 1/1 | 100.00% |
| 突防 | 1 | 3/3 | 100.00% |
| 突防 | 2 | 4/7 | 57.14% |
| 突防 | 3 | 1/2 | 50.00% |

### 意图 × 最大任务组成员数

| 意图 | 条件 | 成功/登记 | 成功率 |
|---|---|---|---|
| 过境 | 2–3 | 0/0 | 未登记 |
| 过境 | 4–6 | 0/2 | 0.00% |
| 过境 | ≥7 | 8/10 | 80.00% |
| 侦察 | 2–3 | 0/0 | 未登记 |
| 侦察 | 4–6 | 1/2 | 50.00% |
| 侦察 | ≥7 | 3/10 | 30.00% |
| 游弋监视 | 2–3 | 0/0 | 未登记 |
| 游弋监视 | 4–6 | 0/2 | 0.00% |
| 游弋监视 | ≥7 | 3/10 | 30.00% |
| 佯动 | 2–3 | 0/0 | 未登记 |
| 佯动 | 4–6 | 2/2 | 100.00% |
| 佯动 | ≥7 | 6/10 | 60.00% |
| 突防 | 2–3 | 1/1 | 100.00% |
| 突防 | 4–6 | 1/4 | 25.00% |
| 突防 | ≥7 | 6/7 | 85.71% |

### 已登记但零成功的组合

以下候选原因来自保存的拒绝记录；次数是候选计数，不能解释为独立骨架数或数学无解证明。

- 游弋监视 × 逼近方式=same_direction：0/5；最终类别 `{"geometry_infeasible": 5}`；主要原因：`orbit_phase_approach_unavailable` × 1977；`same_direction_parallel_phase_entries_do_not_fit` × 1215；`closed_orbit_cannot_clear_exact_restrictions_and_alert_policy` × 360。
- 侦察 × 设施数=2：0/4；最终类别 `{"geometry_infeasible": 4}`；主要原因：`sector_area` × 576；`insufficient_strips` × 267；`offset_lane_swallowtail` × 93。
- 游弋监视 × 设施数=2：0/4；最终类别 `{"geometry_infeasible": 4}`；主要原因：`orbit_phase_approach_unavailable` × 1977；`same_direction_parallel_phase_entries_do_not_fit` × 879；`closed_orbit_cannot_clear_exact_restrictions_and_alert_policy` × 240。
- 过境 × 合并后任务组数=3：0/1；最终类别 `{"geometry_infeasible": 1}`；主要原因：`no_valid_parallel_chord_block` × 216。
- 侦察 × 合并后任务组数=2：0/4；最终类别 `{"kinematic_infeasible": 1, "geometry_infeasible": 3}`；主要原因：`sector_area` × 720；`form_up_leg_blocked` × 50；`reference_leg_invalid` × 16。
- 游弋监视 × 合并后任务组数=3：0/1；最终类别 `{"geometry_infeasible": 1}`；主要原因：`same_direction_parallel_phase_entries_do_not_fit` × 288；`closed_orbit_cannot_clear_exact_restrictions_and_alert_policy` × 72。
- 过境 × 最大任务组成员数=4–6：0/2；最终类别 `{"geometry_infeasible": 2}`；主要原因：`no_valid_parallel_chord_block` × 216；`retreat_point_invalid` × 178；`lane_route_check` × 38。
- 游弋监视 × 最大任务组成员数=4–6：0/2；最终类别 `{"geometry_infeasible": 2}`；主要原因：`same_direction_parallel_phase_entries_do_not_fit` × 288；`closed_orbit_cannot_clear_exact_restrictions_and_alert_policy` × 120；`whole episode actual-delay constant-speed estimate below 6m` × 1。

[逐骨架证据与来源哈希](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2_revision_before_20261015T032100Z/diagnostics.json>)。

## 任务 A：预警进入口径与新回归基准

扩展骨架逐机定位本任务组目标预警区的首次进入帧，在 10 Hz 路径上精确回溯 100 m 并在线段内插值，取回溯起点到进入帧的位移航向。任一成员缺证据则组跨度未知；多向阈值仍为 90°，同向只作诊断。角色核心事件与成功条件不变。

同向通过同侧编队走廊进入，多向分股进入；随后用既有可见图在目标预警区内展开，保留禁入政策、35 m 限制区余量及走廊宽度规则。监视保持同一环线、同一绕行方向和原圈数/半径范围，时序仍按原第一圈核心事件的单机实测计算。

126 项测试通过；固定回归 22/22 PASS，未解释内容差异 0，1093.778 s。竖切 8 条逐字节一致。
旧比较基准：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s2x_regress_20261015T025544Z_e1874339`；本轮新扩展角色/过境回归基准：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s2x_regress_20261015T032231Z_960ffbf5`。

| 冻结骨架/时序 | 类型 | 旧跨度° → 新跨度° | 多向条件 | 组结果 | 集群结果 |
|---|---|---|---|---|---|
| `family_s12_4d13d93f9171c446_ext_000_regular/sequential` | transit | 0.000000000 → 0.000000000 | 未知 → 未知 | success → success | success → success |
| `family_s12_4d13d93f9171c446_ext_000_regular/synchronous` | transit | 0.000000000 → 0.000000000 | 未知 → 未知 | success → success | success → success |
| `family_s12_4d13d93f9171c446_ext_001_regular/sequential` | new_roles | 0.000000000 → 21.786117641 | 未知 → 未知 | success → success | success → success |
| `family_s12_4d13d93f9171c446_ext_001_regular/synchronous` | new_roles | 0.000000000 → 21.831215555 | 未知 → 未知 | success → success | success → success |
| `family_s12_4d13d93f9171c446_ext_003_regular/sequential` | new_roles | 0.000000000 → 59.052891831 | 未知 → 未知 | success → success | success → success |
| `family_s12_4d13d93f9171c446_ext_003_regular/synchronous` | new_roles | 0.000000000 → 59.053363655 | 未知 → 未知 | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_000_regular/sequential` | transit | 180.000000000 → 180.000000000 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_000_regular/synchronous` | transit | 180.000000000 → 180.000000000 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_002_regular/sequential` | new_roles | 179.274159527 → 168.049454824 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_002_regular/synchronous` | new_roles | 179.273939916 → 168.049454823 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_003_regular/sequential` | new_roles | 180.000000000 → 179.999999976 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_003_regular/synchronous` | new_roles | 180.000000000 → 179.999999976 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_004_regular/sequential` | new_roles | 180.000000000 → 179.999979952 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_004_regular/synchronous` | new_roles | 180.000000000 → 179.999982278 | True → True | success → success | success → success |

新角色冻结模板按旧核心事件口径生成，因此新多向条件及其组/集群结果可以变为失败；这是真实轨迹按新定义重算的预期变化，不是标签矛盾或 P0。完整轨迹数组、模型输入、帧级标签、角色事实、任务模板与校时证据继续严格比较。

过境核心事件本来就是进入预警区，测量位置没有改变；其数值末位变化来自把旧“跨过 100 m 的整帧起点”改为精确插值起点，定义文字也同步更新。

[逐机航向、定义、全量字段差异和哈希清单](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_regress_20261015T032231Z_960ffbf5/warning_entry_transition_inventory.json>)；[完整固定回归比较](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_regress_20261015T032231Z_960ffbf5/regression_comparison.json>)。
