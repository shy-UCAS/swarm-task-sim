# Traj2Language v0.7 S2 修订轮执行与验收记录

本轮以 `S2_revision_handoff_ec86137.md` 为有效入口；旧第二段交接第 3 节、条件—审计表及执行记录继续有效，冲突以本轮入口与用户当前澄清为准。

**执行已完成，分布验收目标未达到。** 任务 0、1、A–I、后置诊断和可生成图件均已执行；新全量完整成功配对为 16/60（修订前 31/60），保留 33 条常规及 3 条中止轨迹。五种意图均未达到 60%；监视没有可用样本，主对照为 0。交叉否定 88 项实际执行全为“否”，872 项未覆盖。151 项测试、22 条固定回归、37 条独立审计及两个骨架的 1/2 进程实测比较通过；这些正确性结果不代表分布问题已解决。

[完整统计与 12 张实测图](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_revision_full_report_20261015T053115Z_a3b834e8.md>)；[交叉否定“是”证据附录（本次为空）](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v07scene/Multi-UAV SimpleGC/docs/v07/S2_revision_cross_yes_20261015T053115Z_a3b834e8.md>)。本记录包含修订前、规划冒烟、修订后四维矩阵、参数分布、回归变化清单与捷径检查。

## 范围与用户澄清

- 这是防御方意图识别的抽象合成轨迹研究，改动服务于样本分布与标签口径；不改 fastsim、冻结配置、竖切行为或 SITL。
- **监视时长只测量，不是修改目标。** 任务 I 后仅用仿真时长预测意图的捷径检查只作诊断；不为缩短时长改变圈数、原允许环线半径范围或任何角色参数。任务 C 的半径在原允许连续范围内随机抽样。
- 用户在任务 B 回归期间补充任务 C：固定作业参数在指定区间内用骨架私有流抽样；已有区间抽样保留。包括佯攻 35%–65% 深度及每机 ±3%、突击 25 m 至当前布局可行最大深度减 10 m、观察点外侧 40–65 m/驻留 25–55 s/等概率悬停或盘旋、监视 2/3 圈与顺逆向、搜索面积/张角/重叠率、可行过境弦位置、每骨架 35–70 m 接近绕障余量。此时尚未进入 G，全部并入 C；这是参数区间化，角色判据不变，也不以缩短监视时长为目的。最终报告分别记录候选抽样与保留样本的取值分布。
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
| `family_s12_4d13d93f9171c446_ext_000_regular/sequential` | transit | 0.000000000 → 0.000000000 | 不适用 → 不适用 | success → success | success → success |
| `family_s12_4d13d93f9171c446_ext_000_regular/synchronous` | transit | 0.000000000 → 0.000000000 | 不适用 → 不适用 | success → success | success → success |
| `family_s12_4d13d93f9171c446_ext_001_regular/sequential` | new_roles | 0.000000000 → 21.786117641 | 不适用 → 不适用 | success → success | success → success |
| `family_s12_4d13d93f9171c446_ext_001_regular/synchronous` | new_roles | 0.000000000 → 21.831215555 | 不适用 → 不适用 | success → success | success → success |
| `family_s12_4d13d93f9171c446_ext_003_regular/sequential` | new_roles | 0.000000000 → 59.052891831 | 不适用 → 不适用 | success → success | success → success |
| `family_s12_4d13d93f9171c446_ext_003_regular/synchronous` | new_roles | 0.000000000 → 59.053363655 | 不适用 → 不适用 | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_000_regular/sequential` | transit | 180.000000000 → 180.000000000 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_000_regular/synchronous` | transit | 180.000000000 → 180.000000000 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_002_regular/sequential` | new_roles | 179.274159527 → 168.049454824 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_002_regular/synchronous` | new_roles | 179.273939916 → 168.049454823 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_003_regular/sequential` | new_roles | 180.000000000 → 179.999999976 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_003_regular/synchronous` | new_roles | 180.000000000 → 179.999999976 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_004_regular/sequential` | new_roles | 180.000000000 → 179.999979952 | True → True | success → success | success → success |
| `family_s12_aa4c66be8e85d64d_ext_004_regular/synchronous` | new_roles | 180.000000000 → 179.999982278 | True → True | success → success | success → success |

本次新角色 10 条完整结果均仍为成功；部分前缀已观测到预警进入，所以多向条件从未知变为真。新角色冻结模板按旧核心事件口径生成，因此新多向条件及其组/集群结果即使变为失败也属于预期；这是真实轨迹按新定义重算的预期变化，不是标签矛盾或 P0。完整轨迹数组、模型输入、帧级标签、角色事实、任务模板与校时证据继续严格比较。

过境核心事件本来就是进入预警区，测量位置没有改变；其数值末位变化来自把旧“跨过 100 m 的整帧起点”改为精确插值起点，定义文字也同步更新。

[逐机航向、定义、全量字段差异和哈希清单](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_regress_20261015T032231Z_960ffbf5/warning_entry_transition_inventory.json>)；[完整固定回归比较](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_regress_20261015T032231Z_960ffbf5/regression_comparison.json>)。

## 任务 B：扩展撤离距离参数化

扩展规划器显式传入所有预警区外缘至少 100 m 的撤离要求，覆盖径向角色、监视、区域搜索、过境和中止分支。几何检查和旧调用默认仍为 200 m；冻结回归模板不重写。限制区与世界边界的 35 m 硬余量不变。独立审计继续读取模板所声明的撤离要求并从实际轨迹核对。

- S2 测试 **129/129 PASS**，20.036 s；新增边界测试覆盖 100 m、旧默认 200 m、其他设施预警区和 35 m 限制区余量。
- 固定回归 **22/22 PASS**，1106.325 s，8 进程；22 份标签逐字节一致，内容差异 0。
- 证据：[任务 B 回归比较](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_regress_20261015T034229Z_28f81419/regression_comparison.json>)。
- 同时修正报告换行与“同向不适用多向条件”的显示，不改任何判据。

## 任务 C：连续候选与作业参数区间化

新扩展骨架每次构造 200 个私有连续候选；随机流按骨架、任务组、候选序号派生。固定回归继续执行冻结模板，不重新布置航点。候选先通过原有全部几何检查，再用两种时序的名义整 episode 间距预筛；同向要求每个任务组各自的接近路程总和均不超过该组在可行池中最短值的 115%，按私有随机顺序校时。真实延迟的整 episode 检查不通过则换候选，最多 5 轮。几何池、逐轮校时、最后候选计数分别落盘，不覆盖已有证据；所有候选耗尽按规划间距拒绝记录并保留逐轮原因。

进入方位、作业方位、站位横向偏移、集结点外距、监视半径/相位、搜索张角/面积、过境弦位置等改为连续抽样。原始成员、速度、任务分配、走廊宽度公式与角色成败条件不变。C 阶段仍使用原规划间距 6 m，任务 E 再统一提升到 10 m。

| 参数 | C 的实现口径 |
|---|---|
| 佯攻 | 每组警戒带深度比例 \(U(35\%,65\%)\)，每机再加 \(U(-3\%,3\%)\)；原规划允许范围及实际 `depth_in_band` 的 30%–70% 条件均保持，成败判据不变 |
| 突击 | 每组 U(25 m, 当前站位布局可行最大深度减 10 m)；最大深度由各成员横向起点及向外等距轮廓根的共同可达深度确定，其他几何/间距约束继续独立检查 |
| 抵近观察 | 观察点在警戒外缘外 U(40 m,65 m)，计划驻留 U(25 s,55 s)，悬停/小半径盘旋等概率；30 m 观察半径保持，最短驻留始终等于计划时长的 80% |
| 悬停执行 | 任务编排把路线分成抵达、稳定驻留、继续离开三个阶段；驻留从 10 Hz 实测稳定位置/速度计时，冻结 plant/tracker 不改；名义间距插值也包含这段静止时间 |
| 小半径盘旋 | 在原 30 m 观察盘内生成与计划驻留时间对应的多边形圆弧；真实驻留仍从轨迹计算，不用计划值代替 |
| 监视 | 原有随机 2/3 圈和顺逆方向规则保留；环线半径在原允许范围内均匀抽样并受原环带/净空检查；全组同环同方向、相位错开，重访条件不变 |
| 区域搜索 | 面积 U(0.2,0.6) km²、张角 U(30°,90°)、条带重叠率 U(15%,30%)；原覆盖率及条带证据判据不变 |
| 过境 | 连续方位与弦偏移；每任务组共用一次私有 U(0,1) 位置抽样，映射到各股方位对应的可行弦区间。保留计划弦长至少 430 m、进出方位差至少 95° 的可行条件；实际判据仍为 400 m/90° |
| 接近绕障余量 | 每骨架私有抽样 U(35 m,70 m)，组间共用；在原走廊半宽余量公式中代替固定 35 m 基值，35 m 硬下限保持 |

- S2 测试 **137/137 PASS**，19.189 s；覆盖真实冻结后端悬停、名义间距中的驻留、200 候选计数、115% 边界以及最多 5 轮校时。
- 六角色候选集成验证各 200 次，无单机或联合仿真：过境可选 14、抵近观察 24、监视 0、佯攻 9、突击 7、区域搜索 5。监视实例的 190 次环线几何拒绝和 10 次原重访估计拒绝如实保留，不放宽条件。本次仅是 C 的集成实例检查，不是 G 的全 60 骨架规划冒烟。
- 证据：[六角色候选检查](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2_revision_C_geometry_probe_20261015T040422Z_037992b0/probe_summary.json>)。
- C 固定回归 **22/22 PASS**，1111.806 s，8 进程；22 份标签逐字节一致，内容差异 0。[完整比较](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_regress_20261015T040533Z_c5d8f655/regression_comparison.json>)。

## 任务 D：公共分股与相对进入方位

在 D 的固定回归期间复核有效基础 §3.2-9、§3.3，发现 C 初稿误把原 24 s 对应的 19.2 s 固定阈值沿用于可变驻留，并将 115% 按整个 episode 汇总。两者均需纠正为原要求：计划驻留的 80%、每任务组分别满足 115%。此前 C 只做候选几何检查与冻结模板回归，没有生成采用错误阈值的新标签数据。修正后增加独立阈值审计及反例测试，并重新运行完整固定回归；不更改原角色判据或既有历史证据。

分股流仅由 family 标识及抽样种子、公共槽位、排序后的成员集合派生；不读取基础意图、角色、目标、列种子、时序版本或扩展骨架编号。成员 2–5 时固定 2 股，至少 6 时等概率 2/3 股；两股差 U(100°,180°)，三股相邻差分别 U(50°,120°)，总顺序跨度至少 100°。整体旋转仍来自 C 的私有几何候选。多向实际判据保持至少 90°。

把这些量放入意图相关私有流会在生成前直接制造“分股形态—意图”的联系；公共键保证同一条件下五种意图以及同步/递次版本共用抽样值。可行性筛选仍可能造成保留分布偏差，因此 H/I 后继续报告实际跨度和类别比例，不能用公共抽样正确替代保留分布检查。

- S2 测试 **141/141 PASS**，25.906 s；覆盖角色/目标/列种子/扩展编号变化不影响公共键、成员顺序不影响抽样、分股数与方位范围，以及真实规划上下文确实接入公共槽位和三股方位。
- 全 60 登记骨架的 **95 个任务组公共键审计 PASS**；相同 family/公共槽位/成员集合的实际登记组完全一致，没有执行仿真。
- 下表为登记公共条件的**计划最大两两夹角**，不是实测航向；三股的顺序角度和可测圆周最大夹角分别保存。实测分布在新全量后补充。

| 角色/方法 | 股数 | 组数 | 最小° | 中位° | P90° | 最大° |
|---|---|---|---|---|---|---|
| area_search | 2 | 5 | 110.270 | 111.748 | 159.917 | 164.904 |
| area_search | 3 | 2 | 128.671 | 138.602 | 146.546 | 148.533 |
| close_observation | 2 | 2 | 132.507 | 135.078 | 137.135 | 137.649 |
| close_observation | 3 | 1 | 143.903 | 143.903 | 143.903 | 143.903 |
| feint | 2 | 11 | 110.270 | 137.649 | 164.904 | 179.838 |
| feint | 3 | 3 | 128.671 | 143.903 | 147.607 | 148.533 |
| intrusion | 2 | 6 | 102.670 | 110.386 | 137.772 | 163.795 |
| intrusion | 3 | 2 | 143.903 | 146.218 | 148.070 | 148.533 |
| monitoring | 2 | 8 | 110.270 | 135.078 | 165.843 | 168.032 |
| monitoring | 3 | 3 | 128.671 | 143.903 | 147.607 | 148.533 |
| transit | 2 | 7 | 110.270 | 132.507 | 157.424 | 164.904 |
| transit | 3 | 3 | 128.671 | 143.903 | 147.607 | 148.533 |

[逐组公共键、成员与方位审计](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2_revision_D_public_shape_20261015T042442Z_da713839/public_shape_audit.json>)。

D 首次固定回归 **22/22 PASS**，1110.813 s，22 份标签逐字节一致，内容差异 0；证据 `attempt_s2x_regress_20261015T042508Z_729d03c7/regression_comparison.json`。

C 两处纠正后的 S2 测试 **143/143 PASS**，19.631 s。新增测试覆盖逐组路程上限，并用实际规划模板和 10 Hz 合成证据确认 55 s 计划对应 44 s 最短驻留；故意把模板阈值改回 19.2 s 时，独立审计能够检出模板与生产标签共同使用错误阈值。修正后的固定回归 **22/22 PASS**，1173.423 s，22 份标签逐字节一致，内容差异 0；[完整比较](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_regress_20261015T044440Z_0fb8f8a7/regression_comparison.json>)。

## 任务 E：规划间距统一为 10 m

新扩展骨架显式声明规划阈值 10 m，名义预筛、单机测时后的同步/递次整 episode 检查及引用该骨架的中止分支共用该值；驻留段纳入插值。通用函数旧默认 6 m 和冻结模板保持，实测小于 2 m 的生成错误判据不变。

在进入 G 之前同时补齐 C 的执行细节：过境每任务组只抽一次弦位置分位数，再映射各股的可行区间；抵近观察点、佯攻深度点与转向点按基础 §3.3 分别检查原有独立间距，不能由远处撤离终点的间距代替。这些是抽样粒度与既有几何约束的实现补齐，不改变角色结果条件。

- S2 测试 **146/146 PASS**，18.225 s；覆盖两版 10 m 拦截及旧默认、各股可行弦区间中的共同分位数、作业点间距反例。
- 固定回归 **22/22 PASS**，1030.462 s，8 进程；22 份标签逐字节一致，内容差异 0。[完整比较](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_regress_20261015T050529Z_98167400/regression_comparison.json>)。

## 任务 F：中止引用按同地图固定顺序回退

原登记常规突防引用规划失败时，按骨架编号升序遍历同地图其余常规突防骨架；不额外限制 family。原引用可用时保留，生成错误不被重分类为规划失败。全部同地图候选规划失败时记 not_run。原引用、选择结果、替换标志、逐候选状态和原因写入全量中止配对登记及每条中止的 reference_selection.json。

S2 测试 **150/150 PASS**，19.270 s；新增四例覆盖原引用保留、跨 family 的同地图升序回退、全部规划失败、生成错误不触发回退。本任务只修改中止引用编排，没有修改共享规划或 labels.measure；固定轨迹回归沿用刚完成的 E 结果。实际六条中止的替换与结果在 H 登记。

<!-- revision-planning-smoke -->
## 任务 G：全 60 骨架规划冒烟

规划代码提交 `58ebec723d4653eb0489900314283d27569de630`；证据目录 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s2_revision_planning_20261015T052414Z_dcc71e6e`。
只做连续候选纯几何、两种时序的名义整 episode 间距预筛及同向 115% 路程筛选；没有单机测时或联合仿真。规划可行不代表最终任务成功。本步不设通过门槛。

可行 19/60；每骨架尝试至少 200 个候选，实际单机仿真数 0。

### 规划可行率：approach_mode

| 意图 | 条件 | 可行/登记 | 可行率 |
|---|---|---|---|
| 过境 | same_direction | 3/5 | 60.00% |
| 过境 | multi_direction | 1/7 | 14.29% |
| 侦察 | same_direction | 3/5 | 60.00% |
| 侦察 | multi_direction | 3/7 | 42.86% |
| 游弋监视 | same_direction | 0/5 | 0.00% |
| 游弋监视 | multi_direction | 0/7 | 0.00% |
| 佯动 | same_direction | 2/5 | 40.00% |
| 佯动 | multi_direction | 3/7 | 42.86% |
| 突防 | same_direction | 1/5 | 20.00% |
| 突防 | multi_direction | 3/7 | 42.86% |

### 规划可行率：facility_count

| 意图 | 条件 | 可行/登记 | 可行率 |
|---|---|---|---|
| 过境 | 1 | 1/4 | 25.00% |
| 过境 | 2 | 2/4 | 50.00% |
| 过境 | 3 | 1/4 | 25.00% |
| 侦察 | 1 | 3/4 | 75.00% |
| 侦察 | 2 | 2/4 | 50.00% |
| 侦察 | 3 | 1/4 | 25.00% |
| 游弋监视 | 1 | 0/4 | 0.00% |
| 游弋监视 | 2 | 0/4 | 0.00% |
| 游弋监视 | 3 | 0/4 | 0.00% |
| 佯动 | 1 | 3/4 | 75.00% |
| 佯动 | 2 | 1/4 | 25.00% |
| 佯动 | 3 | 1/4 | 25.00% |
| 突防 | 1 | 3/4 | 75.00% |
| 突防 | 2 | 1/4 | 25.00% |
| 突防 | 3 | 0/4 | 0.00% |

### 规划可行率：group_count

| 意图 | 条件 | 可行/登记 | 可行率 |
|---|---|---|---|
| 过境 | 1 | 3/7 | 42.86% |
| 过境 | 2 | 1/4 | 25.00% |
| 过境 | 3 | 0/1 | 0.00% |
| 侦察 | 1 | 6/7 | 85.71% |
| 侦察 | 2 | 0/4 | 0.00% |
| 侦察 | 3 | 0/1 | 0.00% |
| 游弋监视 | 1 | 0/7 | 0.00% |
| 游弋监视 | 2 | 0/4 | 0.00% |
| 游弋监视 | 3 | 0/1 | 0.00% |
| 佯动 | 1 | 5/7 | 71.43% |
| 佯动 | 2 | 0/4 | 0.00% |
| 佯动 | 3 | 0/1 | 0.00% |
| 突防 | 1 | 3/3 | 100.00% |
| 突防 | 2 | 1/7 | 14.29% |
| 突防 | 3 | 0/2 | 0.00% |

### 规划可行率：maximum_group_size

| 意图 | 条件 | 可行/登记 | 可行率 |
|---|---|---|---|
| 过境 | 2–3 | 0/0 | 未登记 |
| 过境 | 4–6 | 0/2 | 0.00% |
| 过境 | ≥7 | 4/10 | 40.00% |
| 侦察 | 2–3 | 0/0 | 未登记 |
| 侦察 | 4–6 | 0/2 | 0.00% |
| 侦察 | ≥7 | 6/10 | 60.00% |
| 游弋监视 | 2–3 | 0/0 | 未登记 |
| 游弋监视 | 4–6 | 0/2 | 0.00% |
| 游弋监视 | ≥7 | 0/10 | 0.00% |
| 佯动 | 2–3 | 0/0 | 未登记 |
| 佯动 | 4–6 | 0/2 | 0.00% |
| 佯动 | ≥7 | 5/10 | 50.00% |
| 突防 | 2–3 | 0/1 | 0.00% |
| 突防 | 4–6 | 1/4 | 25.00% |
| 突防 | ≥7 | 3/7 | 42.86% |

[全部候选与淘汰原因索引](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2_revision_planning_20261015T052414Z_dcc71e6e/diagnostics.json>)；修订前、规划、修订后并排对照将在任务 I 后汇总。

## 任务 H：冻结与新全量执行

冻结前 S2 测试 **151/151 PASS**，17.634 s；全量入口、报告、图件与后续诊断模块导入通过（语法警告按错误检查）。最后一次共享规划修改的固定回归为 E：22/22 PASS，内容差异 0。此后只修改中止引用编排、诊断和报告工具，没有改变规划几何或角色判据。

从本次提交后的干净工作树新建 attempt，以 8 进程执行 60 常规骨架/120 时序请求及 6 条中止；不复用历史轨迹。实际冻结提交号由运行入口写入 registration.json。进程对比独立重跑两个登记骨架，其中固定包含一个多任务组；优先选有保留轨迹的配对，若多任务组均未生成则只比较该骨架规划输出，并明确实测未覆盖。任务 I 完成前不运行两项捷径分类器。

### H 实际结果

新全量目录为 [attempt_s2x_final_20261015T053115Z_a3b834e8](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8>)，冻结提交 `b7de35d71a60ada8dd4ab5055aac6cebc2f3035e`。从干净工作树执行，主运行 8 进程，连同独立 1/2 进程复跑总墙钟 3085.068 s；运行期间没有修改代码，没有复用历史轨迹。126 个登记请求均有唯一结果。

| 意图 | 完整成功配对 | 保留常规轨迹 | 非设计任务失败 | 组内时序一致 |
|---|---|---|---|---|
| 过境 | 4/12 | 8 | 0/8 | 10/10 |
| 侦察 | 5/12 | 11 | 0/11 | 11/11 |
| 游弋监视 | 0/12 | 0 | 未测得 | 未测得 |
| 佯动 | 4/12 | 8 | 0/8 | 8/8 |
| 突防 | 3/12 | 6 | 0/6 | 6/6 |
| 合计 | 16/60 | 33 | 0/33 | 35/35 |

常规请求中 86 条规划拒绝、34 条实际执行；其中 1 条递次轨迹实测最小间距为 0.689364 m，按原小于 2 m 质量规则排除，保留其同步版本。该轨迹任务标签成功且独立审计通过，质量错误没有被改写为角色任务失败。最终为 16 个完整成功配对及 1 条单独保留的同步轨迹。

6 条中止中，`8412c1cdb40e54b1`、`aa4c66be8e85d64d`、`f2adfbfae12fbbad` 三个 family 的原 `ext_004` 引用可用，均生成预期任务失败、实际撤离的中止轨迹；前缀逐字节一致帧数分别为 4897、8224、7506。其余三个 family 按固定顺序尝试同地图 `ext_004`、`ext_009` 后均规划失败，记 not_run。本次实际引用替换数为 0，不能把回退机制已实现写成实际替换成功；[引用选择记录](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/abort_pairing_registration.json>)保存了每次尝试。

37 条主运行实飞轨迹（34 常规、3 中止）独立审计全部通过，圈层差异、目标差异、事件/数值事实差异、未覆盖条件均为 0。按任务组计算的截断检查为 36 PASS、3 not_run；后者均为设计中止主组缺少核心作业区间，不计为通过。

视图为主对照 0、扩展 33、中止 3、失败 0、待审计 0；单独排除规划拒绝 86、生成错误 1、not_run 3。视图及排除表无重无漏覆盖 126 个请求。主对照按每个 family 的五意图成功配对数最小值平衡；监视在全部 family 缺失，故每个 family 的平衡额度均为 0。扩展 33 条不代表五意图主对照可用。

1/2 进程对比重新执行 `5024cb2ccea653ae/ext_000`（多任务组）及 `4d13d93f9171c446/ext_000`（单任务组），共 4 组时序轨迹比较。候选、校时、规划记录、标签及实际数组内容差异为 0，PASS；仅规划比较项为 0，未用缺轨迹替代实测覆盖。复跑轨迹不进入上述成功率、审计或训练视图计数。[进程比较](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/process_comparison.json>)、[执行摘要](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/execution_summary.json>)。

### G 与 H 的淘汰阶段核对

G 与 H 全 60 个骨架的 200 次候选尝试、筛选摘要、候选顺序和拒绝计数一致。19 个有可选候选的骨架中，两个在真实延迟检查后耗尽可选池：`4d13/ext_003` 的候选 163 同步/递次最小间距为 7.0070/8.1395 m，候选 141 为 7.7324/16.0870 m；`aa/ext_009` 仅有候选 13，其两版为 1.2331/22.1591 m。每个候选都有版本低于 10 m。两者分别尝试 2 轮、1 轮，不是“耗尽五轮”。第三个配对损失是 `8412/ext_001` 的上述实飞质量错误：规划两版均为 16.4937 m，通过规划检查。曾有单机核心事件或终点保持缺失的三个骨架均在第二轮成功，没有骨架最终因单机校时失败耗尽五轮而淘汰。

监视的 2400 个候选全部在首个任务组几何阶段被拒绝：1493 次闭环无法满足原环带、限制区净空与禁入策略的合并检查，903 次原重访几何估计不满足，4 次集结点不可用；没有候选进入 10 m 间距预筛，不能把监视零样本归因于任务 E。合并原因不足以进一步区分某个障碍的独立贡献。其他典型零成功组合：侦察多任务组的 1000 个候选中，531 次扇区面积、246 次集结点、108 次成队航段拒绝；佯动多任务组为 679 次集结点、138 次成队航段、127 次撤离点拒绝；三设施突防为 600 次集结点、89 次监视环线、50 次进入策略拒绝；三任务组过境的 200 个候选均为平行弦块不可用。计数为每候选首个拒绝原因，不同诊断维度互相重叠，不能相加，也不是数学无解证明。

本轮低成功率和图件缺口如实保留，继续任务 I 及之后的诊断，不调整角色判据、监视圈数或半径范围以追求通过。

## 任务 I：960 项交叉否定

按同 family、同公共槽位、不同基础意图的有向比较及两版时序交叉，960 项均有登记结果：88 项实际执行，全部为“否”（PASS）；FAIL 0、组级“是”证据 0、未知 0；872 项因 A 或 B 缺少有效成功配对记 not_run。总体状态为 INCOMPLETE，不能把已执行项全部通过表述为 960 项全部通过。此次实际检查的 88 个组成员集合均完全一致，没有需要交集映射的实际执行项。

修订前实际执行 232 项、not_run 728；本轮为 88、872，覆盖下降与完整成功配对由 31 降到 16 一致。任务 I 已结束，之后才执行两项 family 留一捷径检查；检查结果仅作诊断，不据此修改监视时长或角色参数。[完整交叉否定登记](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/cross_negation.json>)。

<!-- revision-post-I-diagnostics -->
## 任务 I 后：修订前—规划—修订后对照与捷径诊断

四维分母均为 60；多组骨架规模按最大组分档。规划可行率与实飞成功配对率含义不同，三列并列只用于定位淘汰阶段。

### approach_mode

| 意图 | 条件 | 修订前成功/登记 | G 规划可行/登记 | 修订后成功/登记 |
|---|---|---|---|---|
| 过境 | same_direction | 3/5 | 3/5 | 3/5 |
| 过境 | multi_direction | 5/7 | 1/7 | 1/7 |
| 侦察 | same_direction | 2/5 | 3/5 | 2/5 |
| 侦察 | multi_direction | 2/7 | 3/7 | 3/7 |
| 游弋监视 | same_direction | 0/5 | 0/5 | 0/5 |
| 游弋监视 | multi_direction | 3/7 | 0/7 | 0/7 |
| 佯动 | same_direction | 4/5 | 2/5 | 1/5 |
| 佯动 | multi_direction | 4/7 | 3/7 | 3/7 |
| 突防 | same_direction | 3/5 | 1/5 | 1/5 |
| 突防 | multi_direction | 5/7 | 3/7 | 2/7 |


### facility_count

| 意图 | 条件 | 修订前成功/登记 | G 规划可行/登记 | 修订后成功/登记 |
|---|---|---|---|---|
| 过境 | 1 | 4/4 | 1/4 | 1/4 |
| 过境 | 2 | 2/4 | 2/4 | 2/4 |
| 过境 | 3 | 2/4 | 1/4 | 1/4 |
| 侦察 | 1 | 2/4 | 3/4 | 3/4 |
| 侦察 | 2 | 0/4 | 2/4 | 1/4 |
| 侦察 | 3 | 2/4 | 1/4 | 1/4 |
| 游弋监视 | 1 | 2/4 | 0/4 | 0/4 |
| 游弋监视 | 2 | 0/4 | 0/4 | 0/4 |
| 游弋监视 | 3 | 1/4 | 0/4 | 0/4 |
| 佯动 | 1 | 3/4 | 3/4 | 3/4 |
| 佯动 | 2 | 2/4 | 1/4 | 1/4 |
| 佯动 | 3 | 3/4 | 1/4 | 0/4 |
| 突防 | 1 | 3/4 | 3/4 | 2/4 |
| 突防 | 2 | 4/4 | 1/4 | 1/4 |
| 突防 | 3 | 1/4 | 0/4 | 0/4 |


### group_count

| 意图 | 条件 | 修订前成功/登记 | G 规划可行/登记 | 修订后成功/登记 |
|---|---|---|---|---|
| 过境 | 1 | 6/7 | 3/7 | 3/7 |
| 过境 | 2 | 2/4 | 1/4 | 1/4 |
| 过境 | 3 | 0/1 | 0/1 | 0/1 |
| 侦察 | 1 | 3/7 | 6/7 | 5/7 |
| 侦察 | 2 | 0/4 | 0/4 | 0/4 |
| 侦察 | 3 | 1/1 | 0/1 | 0/1 |
| 游弋监视 | 1 | 2/7 | 0/7 | 0/7 |
| 游弋监视 | 2 | 1/4 | 0/4 | 0/4 |
| 游弋监视 | 3 | 0/1 | 0/1 | 0/1 |
| 佯动 | 1 | 5/7 | 5/7 | 4/7 |
| 佯动 | 2 | 2/4 | 0/4 | 0/4 |
| 佯动 | 3 | 1/1 | 0/1 | 0/1 |
| 突防 | 1 | 3/3 | 3/3 | 3/3 |
| 突防 | 2 | 4/7 | 1/7 | 0/7 |
| 突防 | 3 | 1/2 | 0/2 | 0/2 |


### maximum_group_size

| 意图 | 条件 | 修订前成功/登记 | G 规划可行/登记 | 修订后成功/登记 |
|---|---|---|---|---|
| 过境 | 2–3 | 0/0 | 0/0 | 0/0 |
| 过境 | 4–6 | 0/2 | 0/2 | 0/2 |
| 过境 | ≥7 | 8/10 | 4/10 | 4/10 |
| 侦察 | 2–3 | 0/0 | 0/0 | 0/0 |
| 侦察 | 4–6 | 1/2 | 0/2 | 0/2 |
| 侦察 | ≥7 | 3/10 | 6/10 | 5/10 |
| 游弋监视 | 2–3 | 0/0 | 0/0 | 0/0 |
| 游弋监视 | 4–6 | 0/2 | 0/2 | 0/2 |
| 游弋监视 | ≥7 | 3/10 | 0/10 | 0/10 |
| 佯动 | 2–3 | 0/0 | 0/0 | 0/0 |
| 佯动 | 4–6 | 2/2 | 0/2 | 0/2 |
| 佯动 | ≥7 | 6/10 | 5/10 | 4/10 |
| 突防 | 2–3 | 1/1 | 0/1 | 0/1 |
| 突防 | 4–6 | 1/4 | 1/4 | 0/4 |
| 突防 | ≥7 | 6/7 | 3/7 | 3/7 |


### 修订后已登记但零成功的组合

候选计数与单机校时轮次属于不同层次，均保留来源，不能当作独立骨架数或无解证明。

| 意图 | 维度/条件 | 成功/登记 | 最终类别 | 前三项保存的拒绝原因 |
|---|---|---|---|---|
| 游弋监视 | approach_mode/same_direction | 0/5 | {'geometry_infeasible': 5} | closed_orbit_cannot_clear_exact_restrictions_and_alert_policy: 530; nominal_revisit_geometry_infeasible: 470 |
| 游弋监视 | approach_mode/multi_direction | 0/7 | {'geometry_infeasible': 7} | closed_orbit_cannot_clear_exact_restrictions_and_alert_policy: 963; nominal_revisit_geometry_infeasible: 433; random_warning_collection_unavailable: 4 |
| 游弋监视 | facility_count/1 | 0/4 | {'geometry_infeasible': 4} | closed_orbit_cannot_clear_exact_restrictions_and_alert_policy: 603; nominal_revisit_geometry_infeasible: 197 |
| 游弋监视 | facility_count/2 | 0/4 | {'geometry_infeasible': 4} | closed_orbit_cannot_clear_exact_restrictions_and_alert_policy: 408; nominal_revisit_geometry_infeasible: 392 |
| 游弋监视 | facility_count/3 | 0/4 | {'geometry_infeasible': 4} | closed_orbit_cannot_clear_exact_restrictions_and_alert_policy: 482; nominal_revisit_geometry_infeasible: 314; random_warning_collection_unavailable: 4 |
| 佯动 | facility_count/3 | 0/4 | {'planning_spacing_rejection': 1, 'geometry_infeasible': 3} | random_warning_collection_unavailable: 556; all-warning-exterior_retreat_unavailable: 139; nominal_whole_episode_spacing: 55 |
| 突防 | facility_count/3 | 0/4 | {'geometry_infeasible': 4} | random_warning_collection_unavailable: 600; closed_orbit_cannot_clear_exact_restrictions_and_alert_policy: 89; warning_ingress_policy_or_clearance: 50 |
| 过境 | group_count/3 | 0/1 | {'geometry_infeasible': 1} | continuous_parallel_chord_block_unavailable: 200 |
| 侦察 | group_count/2 | 0/4 | {'geometry_infeasible': 4} | sampled_sector_area_does_not_fit_original_band: 335; random_warning_collection_unavailable: 245; form_up_leg_blocked: 108 |
| 侦察 | group_count/3 | 0/1 | {'geometry_infeasible': 1} | sampled_sector_area_does_not_fit_original_band: 196; sector_clearance: 3; random_warning_collection_unavailable: 1 |
| 游弋监视 | group_count/1 | 0/7 | {'geometry_infeasible': 7} | closed_orbit_cannot_clear_exact_restrictions_and_alert_policy: 842; nominal_revisit_geometry_infeasible: 558 |
| 游弋监视 | group_count/2 | 0/4 | {'geometry_infeasible': 4} | closed_orbit_cannot_clear_exact_restrictions_and_alert_policy: 547; nominal_revisit_geometry_infeasible: 249; random_warning_collection_unavailable: 4 |
| 游弋监视 | group_count/3 | 0/1 | {'geometry_infeasible': 1} | closed_orbit_cannot_clear_exact_restrictions_and_alert_policy: 104; nominal_revisit_geometry_infeasible: 96 |
| 佯动 | group_count/2 | 0/4 | {'geometry_infeasible': 4} | random_warning_collection_unavailable: 556; form_up_leg_blocked: 138; all-warning-exterior_retreat_unavailable: 59 |
| 佯动 | group_count/3 | 0/1 | {'geometry_infeasible': 1} | random_warning_collection_unavailable: 123; all-warning-exterior_retreat_unavailable: 68; nominal_whole_episode_spacing: 4 |
| 突防 | group_count/2 | 0/7 | {'geometry_infeasible': 6, 'planning_spacing_rejection': 1} | random_warning_collection_unavailable: 823; form_up_leg_blocked: 143; closed_orbit_cannot_clear_exact_restrictions_and_alert_policy: 140 |
| 突防 | group_count/3 | 0/2 | {'geometry_infeasible': 2} | random_warning_collection_unavailable: 346; nominal_whole_episode_spacing: 30; warning_ingress_policy_or_clearance: 8 |
| 过境 | maximum_group_size/4–6 | 0/2 | {'geometry_infeasible': 2} | continuous_parallel_chord_block_unavailable: 200; retreat_point_invalid: 111; lead_in_or_run_out_unavailable: 51 |
| 侦察 | maximum_group_size/4–6 | 0/2 | {'geometry_infeasible': 2} | sampled_sector_area_does_not_fit_original_band: 306; sector_clearance: 47; random_warning_collection_unavailable: 38 |
| 游弋监视 | maximum_group_size/4–6 | 0/2 | {'geometry_infeasible': 2} | closed_orbit_cannot_clear_exact_restrictions_and_alert_policy: 290; nominal_revisit_geometry_infeasible: 106; random_warning_collection_unavailable: 4 |
| 游弋监视 | maximum_group_size/≥7 | 0/10 | {'geometry_infeasible': 10} | closed_orbit_cannot_clear_exact_restrictions_and_alert_policy: 1203; nominal_revisit_geometry_infeasible: 797 |
| 佯动 | maximum_group_size/4–6 | 0/2 | {'geometry_infeasible': 2} | random_warning_collection_unavailable: 301; all-warning-exterior_retreat_unavailable: 88; nominal_whole_episode_spacing: 5 |
| 突防 | maximum_group_size/2–3 | 0/1 | {'geometry_infeasible': 1} | random_warning_collection_unavailable: 191; all-warning-exterior_retreat_unavailable: 7; warning_reference_leg_invalid: 2 |
| 突防 | maximum_group_size/4–6 | 0/4 | {'geometry_infeasible': 3, 'planning_spacing_rejection': 1} | random_warning_collection_unavailable: 507; closed_orbit_cannot_clear_exact_restrictions_and_alert_policy: 140; warning_reference_leg_invalid: 41 |


### 目标对照（仅诊断，不作为停机门槛）

| 意图 | 骨架成功率 | 达到 60% | 同向成功率 | 多向成功率 | 绝对差/百分点 | 两方式均有成功 | 差值不超过 20 |
|---|---|---|---|---|---|---|---|
| 过境 | 33.33% | False | 60.00% | 14.29% | 45.714 | True | False |
| 侦察 | 41.67% | False | 40.00% | 42.86% | 2.857 | True | True |
| 游弋监视 | 0.00% | False | 0.00% | 0.00% | 0.000 | False | True |
| 佯动 | 33.33% | False | 20.00% | 42.86% | 22.857 | True | False |
| 突防 | 25.00% | False | 20.00% | 28.57% | 8.571 | True | True |


### 保留轨迹的逼近方式比例

| 意图 | 登记同向占比 | 修订前同向/总数 | 修订前同向占比 | 修订后同向/总数 | 修订后同向占比 | 修订后相对登记偏差/百分点 |
|---|---|---|---|---|---|---|
| 过境 | 41.67% | 6/16 | 37.50% | 6/8 | 75.00% | 33.333 |
| 侦察 | 41.67% | 4/8 | 50.00% | 5/11 | 45.45% | 3.788 |
| 游弋监视 | 41.67% | 0/6 | 0.00% | 0/0 | 无可用分母 | 未测得 |
| 佯动 | 41.67% | 8/17 | 47.06% | 2/8 | 25.00% | -16.667 |
| 突防 | 41.67% | 6/17 | 35.29% | 2/6 | 33.33% | -8.333 |


### 实测进入预警区前 100 m 航向跨度

以下以保留常规轨迹中的任务组为单位，同步/递次分别计数；缺失事件不补值。

| 角色 | 逼近方式 | 股数 | N | 最小 | 中位 | P90 | 最大 |
|---|---|---|---|---|---|---|---|
| area_search | multi_direction | 2 | 4 | 110.502 | 131.469 | 152.436 | 152.436 |
| area_search | multi_direction | 3 | 2 | 128.671 | 128.671 | 128.671 | 128.671 |
| area_search | same_direction | 1 | 3 | 0.000 | 0.000 | 0.000 | 0.000 |
| close_observation | same_direction | 1 | 2 | 0.000 | 0.000 | 0.000 | 0.000 |
| feint | multi_direction | 2 | 2 | 110.502 | 110.502 | 110.502 | 110.502 |
| feint | multi_direction | 3 | 4 | 128.671 | 136.287 | 143.903 | 143.903 |
| feint | same_direction | 1 | 2 | 0.000 | 0.000 | 0.000 | 0.000 |
| intrusion | multi_direction | 2 | 2 | 110.502 | 110.502 | 110.502 | 110.502 |
| intrusion | multi_direction | 3 | 2 | 143.903 | 143.903 | 143.903 | 143.903 |
| intrusion | same_direction | 1 | 2 | 0.000 | 0.000 | 0.000 | 0.000 |
| transit | multi_direction | 2 | 2 | 110.502 | 110.502 | 110.502 | 110.502 |
| transit | same_direction | 1 | 8 | 0.000 | 0.000 | 0.000 | 0.000 |


### 作业参数实际取值与塌缩诊断

all_attempted_draws 为候选尝试（后续组可能因前组拒绝而未抽样）；selected_for_execution 为完成校时后实际选中的骨架；retained_skeletons_once 为至少保留一个时序版本的骨架。这两个阶段去除了同步/递次重复，组级参数每组一次，佯攻成员扰动和过境计划弦指标按每机展开。接近净空按骨架抽样，保存到各组及候选的值会重复，N 不是独立随机抽样次数。measured_retained_episodes 为真实轨迹单机事实，包含两个时序版本；各行明确计数单位。sample 数为 0/1 时不能证明未塌缩。角色结果条件均未因这些分布调整。监视圈数/方向保留原有随机规则。

| 阶段 | 角色 | 参数 | 计数单位 | N/不同值数 | 最小/P10/中位/P90/最大 | 诊断 |
|---|---|---|---|---|---|---|
| all_attempted_draws | area_search | approach_obstacle_clearance_m | 候选组记录（同骨架共用净空值） | 1803/9 | 35.102 / 35.102 / 48.949 / 69.613 / 69.613 | noncollapsed |
| all_attempted_draws | area_search | collection_clearance_m | 候选中的任务组参数记录 | 1803/1803 | 150.218 / 203.960 / 394.582 / 601.176 / 649.764 | noncollapsed |
| all_attempted_draws | area_search | sector_angle_deg | 候选中的任务组参数记录 | 1803/1803 | 30.031 / 36.609 / 60.389 / 84.461 / 89.993 | noncollapsed |
| all_attempted_draws | area_search | sector_area_m2 | 候选中的任务组参数记录 | 1803/1803 | 200116.478 / 241364.853 / 399322.012 / 561073.427 / 599093.113 | noncollapsed |
| all_attempted_draws | area_search | strip_overlap_fraction | 候选中的任务组参数记录 | 1803/1803 | 0.150 / 0.165 / 0.226 / 0.285 / 0.300 | noncollapsed |
| all_attempted_draws | close_observation | approach_obstacle_clearance_m | 候选组记录（同骨架共用净空值） | 616/6 | 36.999 / 46.714 / 52.380 / 54.965 / 69.613 | noncollapsed |
| all_attempted_draws | close_observation | collection_clearance_m | 候选中的任务组参数记录 | 616/616 | 150.168 / 191.929 / 382.625 / 594.899 / 649.814 | noncollapsed |
| all_attempted_draws | close_observation | observation_alert_clearance_m | 候选中的任务组参数记录 | 616/616 | 40.030 / 42.327 / 53.015 / 62.902 / 64.999 | noncollapsed |
| all_attempted_draws | close_observation | planned_observation_dwell_s | 候选中的任务组参数记录 | 616/616 | 25.067 / 28.562 / 40.099 / 51.771 / 54.973 | noncollapsed |
| all_attempted_draws | feint | approach_obstacle_clearance_m | 候选组记录（同骨架共用净空值） | 2897/17 | 38.244 / 41.881 / 58.645 / 69.708 / 69.708 | noncollapsed |
| all_attempted_draws | feint | collection_clearance_m | 候选中的任务组参数记录 | 2897/2897 | 150.329 / 201.822 / 401.538 / 599.010 / 649.917 | noncollapsed |
| all_attempted_draws | feint | feint_group_depth_fraction | 候选中的任务组参数记录 | 2897/2897 | 0.350 / 0.383 / 0.503 / 0.620 / 0.650 | noncollapsed |
| all_attempted_draws | feint | feint_member_depth_fraction | 候选中的单机计划值 | 21509/21509 | 0.320 / 0.383 / 0.502 / 0.620 / 0.679 | noncollapsed |
| all_attempted_draws | intrusion | approach_obstacle_clearance_m | 候选组记录（同骨架共用净空值） | 2473/12 | 40.450 / 41.881 / 56.316 / 67.778 / 68.833 | noncollapsed |
| all_attempted_draws | intrusion | collection_clearance_m | 候选中的任务组参数记录 | 2473/2473 | 150.277 / 199.533 / 397.264 / 598.964 / 649.941 | noncollapsed |
| all_attempted_draws | intrusion | intrusion_endpoint_depth_m | 候选中的任务组参数记录 | 2473/2473 | 25.010 / 29.282 / 46.252 / 81.427 / 169.739 | noncollapsed |
| all_attempted_draws | intrusion | intrusion_feasible_max_depth_m | 候选中的任务组参数记录 | 2473/2473 | 39.817 / 59.065 / 82.900 / 151.607 / 181.621 | noncollapsed |
| all_attempted_draws | monitoring | approach_obstacle_clearance_m | 候选组记录（同骨架共用净空值） | 2567/14 | 36.671 / 37.234 / 58.455 / 67.807 / 67.922 | noncollapsed |
| all_attempted_draws | monitoring | collection_clearance_m | 候选中的任务组参数记录 | 2567/2567 | 150.029 / 196.932 / 408.473 / 600.292 / 649.943 | noncollapsed |
| all_attempted_draws | monitoring | orbit_radius_m | 候选中的任务组参数记录 | 2567/2567 | 309.884 / 521.148 / 727.188 / 968.016 / 1131.196 | noncollapsed |
| all_attempted_draws | transit | approach_obstacle_clearance_m | 候选组记录（同骨架共用净空值） | 2480/12 | 35.220 / 38.228 / 59.674 / 67.533 / 68.089 | noncollapsed |
| all_attempted_draws | transit | collection_clearance_m | 候选中的任务组参数记录 | 2480/2480 | 150.084 / 198.008 / 395.804 / 600.592 / 649.908 | noncollapsed |
| all_attempted_draws | transit | transit_chord_position_fraction | 候选中的任务组参数记录 | 2480/2480 | 0.001 / 0.097 / 0.490 / 0.896 / 1.000 | noncollapsed |
| measured_retained_episodes | close_observation | dwell_s | 保留轨迹中的单机（同步/递次分别计） | 14/2 | 52.300 / 52.300 / 52.300 / 52.400 / 52.400 | noncollapsed |
| measured_retained_episodes | feint | depth_fraction_in_alert_band | 保留轨迹中的单机（同步/递次分别计） | 76/32 | 0.327 / 0.339 / 0.483 / 0.508 / 0.525 | noncollapsed |
| measured_retained_episodes | intrusion | maximum_protected_depth_m | 保留轨迹中的单机（同步/递次分别计） | 58/58 | 29.844 / 29.949 / 30.494 / 31.224 / 31.377 | noncollapsed |
| measured_retained_episodes | monitoring | lap_count_observed | 保留轨迹中的单机（同步/递次分别计） | 0/0 | 未测得 / 未测得 / 未测得 / 未测得 / 未测得 | unmeasured |
| measured_retained_episodes | transit | chord_length_m | 保留轨迹中的单机（同步/递次分别计） | 76/38 | 1246.190 / 1339.340 / 1473.385 / 1797.663 / 1840.914 | noncollapsed |
| measured_retained_episodes | transit | entry_exit_azimuth_difference_deg | 保留轨迹中的单机（同步/递次分别计） | 76/57 | 95.611 / 98.870 / 110.827 / 119.834 / 124.553 | noncollapsed |
| retained_skeletons_once | area_search | approach_obstacle_clearance_m | 组记录（同骨架共用净空值） | 5/5 | 35.102 / 39.405 / 48.949 / 61.362 / 62.793 | noncollapsed |
| retained_skeletons_once | area_search | collection_clearance_m | 骨架中的任务组参数记录 | 5/5 | 219.104 / 254.567 / 440.786 / 578.490 / 597.696 | noncollapsed |
| retained_skeletons_once | area_search | sector_angle_deg | 骨架中的任务组参数记录 | 5/5 | 66.901 / 67.052 / 76.627 / 86.130 / 89.188 | noncollapsed |
| retained_skeletons_once | area_search | sector_area_m2 | 骨架中的任务组参数记录 | 5/5 | 260485.098 / 278880.336 / 326506.227 / 374566.161 / 377212.164 | noncollapsed |
| retained_skeletons_once | area_search | strip_overlap_fraction | 骨架中的任务组参数记录 | 5/5 | 0.157 / 0.178 / 0.214 / 0.261 / 0.286 | noncollapsed |
| retained_skeletons_once | close_observation | approach_obstacle_clearance_m | 组记录（同骨架共用净空值） | 1/1 | 46.714 / 46.714 / 46.714 / 46.714 / 46.714 | insufficient_n |
| retained_skeletons_once | close_observation | collection_clearance_m | 骨架中的任务组参数记录 | 1/1 | 599.130 / 599.130 / 599.130 / 599.130 / 599.130 | insufficient_n |
| retained_skeletons_once | close_observation | observation_alert_clearance_m | 骨架中的任务组参数记录 | 1/1 | 55.337 / 55.337 / 55.337 / 55.337 / 55.337 | insufficient_n |
| retained_skeletons_once | close_observation | planned_observation_dwell_s | 骨架中的任务组参数记录 | 1/1 | 39.412 / 39.412 / 39.412 / 39.412 / 39.412 | insufficient_n |
| retained_skeletons_once | feint | approach_obstacle_clearance_m | 组记录（同骨架共用净空值） | 4/4 | 51.343 / 53.534 / 59.021 / 66.185 / 69.094 | noncollapsed |
| retained_skeletons_once | feint | collection_clearance_m | 骨架中的任务组参数记录 | 4/4 | 285.112 / 290.794 / 356.605 / 463.160 / 486.303 | noncollapsed |
| retained_skeletons_once | feint | feint_group_depth_fraction | 骨架中的任务组参数记录 | 4/4 | 0.351 / 0.365 / 0.444 / 0.494 / 0.495 | noncollapsed |
| retained_skeletons_once | feint | feint_member_depth_fraction | 骨架中的单机计划值 | 38/38 | 0.323 / 0.337 / 0.478 / 0.502 / 0.523 | noncollapsed |
| retained_skeletons_once | intrusion | approach_obstacle_clearance_m | 组记录（同骨架共用净空值） | 3/3 | 56.002 / 58.279 / 67.386 / 68.544 / 68.833 | noncollapsed |
| retained_skeletons_once | intrusion | collection_clearance_m | 骨架中的任务组参数记录 | 3/3 | 448.625 / 459.643 / 503.713 / 603.894 / 628.939 | noncollapsed |
| retained_skeletons_once | intrusion | intrusion_endpoint_depth_m | 骨架中的任务组参数记录 | 3/3 | 27.181 / 27.531 / 28.933 / 29.567 / 29.725 | noncollapsed |
| retained_skeletons_once | intrusion | intrusion_feasible_max_depth_m | 骨架中的任务组参数记录 | 3/3 | 66.512 / 69.013 / 79.016 / 102.452 / 108.311 | noncollapsed |
| retained_skeletons_once | monitoring | approach_obstacle_clearance_m | 组记录（同骨架共用净空值） | 0/0 | 未测得 / 未测得 / 未测得 / 未测得 / 未测得 | unmeasured |
| retained_skeletons_once | monitoring | orbit_radius_m | 骨架中的任务组参数记录 | 0/0 | 未测得 / 未测得 / 未测得 / 未测得 / 未测得 | unmeasured |
| retained_skeletons_once | transit | approach_obstacle_clearance_m | 组记录（同骨架共用净空值） | 5/4 | 38.228 / 38.614 / 39.193 / 47.704 / 51.099 | noncollapsed |
| retained_skeletons_once | transit | collection_clearance_m | 骨架中的任务组参数记录 | 5/5 | 188.738 / 192.916 / 328.216 / 560.884 / 596.271 | noncollapsed |
| retained_skeletons_once | transit | transit_chord_position_fraction | 骨架中的任务组参数记录 | 5/5 | 0.133 / 0.263 / 0.639 / 0.884 / 0.916 | noncollapsed |
| selected_for_execution | area_search | approach_obstacle_clearance_m | 组记录（同骨架共用净空值） | 5/5 | 35.102 / 39.405 / 48.949 / 61.362 / 62.793 | noncollapsed |
| selected_for_execution | area_search | collection_clearance_m | 骨架中的任务组参数记录 | 5/5 | 219.104 / 254.567 / 440.786 / 578.490 / 597.696 | noncollapsed |
| selected_for_execution | area_search | sector_angle_deg | 骨架中的任务组参数记录 | 5/5 | 66.901 / 67.052 / 76.627 / 86.130 / 89.188 | noncollapsed |
| selected_for_execution | area_search | sector_area_m2 | 骨架中的任务组参数记录 | 5/5 | 260485.098 / 278880.336 / 326506.227 / 374566.161 / 377212.164 | noncollapsed |
| selected_for_execution | area_search | strip_overlap_fraction | 骨架中的任务组参数记录 | 5/5 | 0.157 / 0.178 / 0.214 / 0.261 / 0.286 | noncollapsed |
| selected_for_execution | close_observation | approach_obstacle_clearance_m | 组记录（同骨架共用净空值） | 1/1 | 46.714 / 46.714 / 46.714 / 46.714 / 46.714 | insufficient_n |
| selected_for_execution | close_observation | collection_clearance_m | 骨架中的任务组参数记录 | 1/1 | 599.130 / 599.130 / 599.130 / 599.130 / 599.130 | insufficient_n |
| selected_for_execution | close_observation | observation_alert_clearance_m | 骨架中的任务组参数记录 | 1/1 | 55.337 / 55.337 / 55.337 / 55.337 / 55.337 | insufficient_n |
| selected_for_execution | close_observation | planned_observation_dwell_s | 骨架中的任务组参数记录 | 1/1 | 39.412 / 39.412 / 39.412 / 39.412 / 39.412 | insufficient_n |
| selected_for_execution | feint | approach_obstacle_clearance_m | 组记录（同骨架共用净空值） | 4/4 | 51.343 / 53.534 / 59.021 / 66.185 / 69.094 | noncollapsed |
| selected_for_execution | feint | collection_clearance_m | 骨架中的任务组参数记录 | 4/4 | 285.112 / 290.794 / 356.605 / 463.160 / 486.303 | noncollapsed |
| selected_for_execution | feint | feint_group_depth_fraction | 骨架中的任务组参数记录 | 4/4 | 0.351 / 0.365 / 0.444 / 0.494 / 0.495 | noncollapsed |
| selected_for_execution | feint | feint_member_depth_fraction | 骨架中的单机计划值 | 38/38 | 0.323 / 0.337 / 0.478 / 0.502 / 0.523 | noncollapsed |
| selected_for_execution | intrusion | approach_obstacle_clearance_m | 组记录（同骨架共用净空值） | 3/3 | 56.002 / 58.279 / 67.386 / 68.544 / 68.833 | noncollapsed |
| selected_for_execution | intrusion | collection_clearance_m | 骨架中的任务组参数记录 | 3/3 | 448.625 / 459.643 / 503.713 / 603.894 / 628.939 | noncollapsed |
| selected_for_execution | intrusion | intrusion_endpoint_depth_m | 骨架中的任务组参数记录 | 3/3 | 27.181 / 27.531 / 28.933 / 29.567 / 29.725 | noncollapsed |
| selected_for_execution | intrusion | intrusion_feasible_max_depth_m | 骨架中的任务组参数记录 | 3/3 | 66.512 / 69.013 / 79.016 / 102.452 / 108.311 | noncollapsed |
| selected_for_execution | monitoring | approach_obstacle_clearance_m | 组记录（同骨架共用净空值） | 0/0 | 未测得 / 未测得 / 未测得 / 未测得 / 未测得 | unmeasured |
| selected_for_execution | monitoring | orbit_radius_m | 骨架中的任务组参数记录 | 0/0 | 未测得 / 未测得 / 未测得 / 未测得 / 未测得 | unmeasured |
| selected_for_execution | transit | approach_obstacle_clearance_m | 组记录（同骨架共用净空值） | 5/4 | 38.228 / 38.614 / 39.193 / 47.704 / 51.099 | noncollapsed |
| selected_for_execution | transit | collection_clearance_m | 骨架中的任务组参数记录 | 5/5 | 188.738 / 192.916 / 328.216 / 560.884 / 596.271 | noncollapsed |
| selected_for_execution | transit | transit_chord_length_m | 骨架中的单机计划值 | 38/38 | 1246.813 / 1344.958 / 1474.096 / 1794.141 / 1841.734 | noncollapsed |
| selected_for_execution | transit | transit_chord_position_fraction | 骨架中的任务组参数记录 | 5/5 | 0.133 / 0.263 / 0.639 / 0.884 / 0.916 | noncollapsed |
| selected_for_execution | transit | transit_entry_exit_azimuth_difference_deg | 骨架中的单机计划值 | 38/38 | 95.621 / 98.989 / 110.851 / 119.804 / 124.572 | noncollapsed |
| selected_for_execution | transit | transit_lateral_offset_m | 骨架中的单机计划值 | 38/38 | -618.301 / -576.119 / 504.388 / 599.002 / 623.272 | noncollapsed |


| 阶段 | 角色 | 参数 | 计数单位 | 取值计数 | 不同值数 | 诊断 |
|---|---|---|---|---|---|---|
| all_attempted_draws | close_observation | observation_dwell_method | 候选中的任务组参数记录 | {'small_circle': 324, 'hover': 292} | 2 | noncollapsed |
| all_attempted_draws | monitoring | monitoring_laps | 候选中的任务组参数记录 | {'3': 1367, '2': 1200} | 2 | noncollapsed |
| all_attempted_draws | monitoring | monitoring_rotation_sign | 候选中的任务组参数记录 | {'-1.0': 1000, '1.0': 1567} | 2 | noncollapsed |
| retained_skeletons_once | close_observation | observation_dwell_method | 骨架中的任务组参数记录 | {'hover': 1} | 1 | insufficient_n |
| retained_skeletons_once | monitoring | monitoring_laps | 骨架中的任务组参数记录 | {} | 0 | unmeasured |
| retained_skeletons_once | monitoring | monitoring_rotation_sign | 骨架中的任务组参数记录 | {} | 0 | unmeasured |
| selected_for_execution | close_observation | observation_dwell_method | 骨架中的任务组参数记录 | {'hover': 1} | 1 | insufficient_n |
| selected_for_execution | monitoring | monitoring_laps | 骨架中的任务组参数记录 | {} | 0 | unmeasured |
| selected_for_execution | monitoring | monitoring_rotation_sign | 骨架中的任务组参数记录 | {} | 0 | unmeasured |


### 两项 family 留一捷径检查

固定深度 2、叶节点至少 3 样本的浅层决策树，不调参。同步/递次同属一个 family 留出折。时长是仿真时间轴，不是墙钟；监视时长只作测量，不作为优化目标。五类均匀随机参考 20%，另报告训练折多数类基线。

保留样本类别数：{'过境': 8, '侦察': 11, '游弋监视': 0, '佯动': 8, '突防': 6}。缺失类别：['游弋监视']。缺少类别时，20% 仅为理论五类参考，所得准确率不能解释为完整五类泛化性能。

| 特征 | 准确率 | 宏平均召回率 | family 平均准确率 | 多数类基线 | 随机参考 |
|---|---|---|---|---|---|
| duration_only | 21.21% | 23.11% | 18.17% | 33.33% | 20% |
| approach_group_facility_only | 24.24% | 23.30% | 23.44% | 33.33% | 20% |


#### duration_only：逐折

| 留出 family | 训练/测试 | 准确率 | 多数类基线 |
|---|---|---|---|
| family_s12_4d13d93f9171c446 | 29/4 | 25.00% | 50.00% |
| family_s12_5024cb2ccea653ae | 31/2 | 0.00% | 0.00% |
| family_s12_8412c1cdb40e54b1 | 24/9 | 33.33% | 33.33% |
| family_s12_aa4c66be8e85d64d | 25/8 | 12.50% | 25.00% |
| family_s12_f2adfbfae12fbbad | 23/10 | 20.00% | 40.00% |


#### approach_group_facility_only：逐折

| 留出 family | 训练/测试 | 准确率 | 多数类基线 |
|---|---|---|---|
| family_s12_4d13d93f9171c446 | 29/4 | 50.00% | 50.00% |
| family_s12_5024cb2ccea653ae | 31/2 | 0.00% | 0.00% |
| family_s12_8412c1cdb40e54b1 | 24/9 | 22.22% | 33.33% |
| family_s12_aa4c66be8e85d64d | 25/8 | 25.00% | 25.00% |
| family_s12_f2adfbfae12fbbad | 23/10 | 20.00% | 40.00% |


### 主对照与交叉否定覆盖变化

| 项目 | 修订前 | 修订后 |
|---|---|---|
| 主对照条数 | 10 | 0 |
| 交叉否定实际执行项 | 232 | 88 |
| 交叉否定 not_run | 728 | 872 |


所有比例与捷径结果只作诊断；不足样本、单值参数、低成功率和未执行项如实保留。不得将缺失样本视为通过，也不得根据此检查缩短监视时长或放松角色条件。

[完整数值、逐候选参数、逐折预测与来源](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/revision_diagnostics/diagnostics.json>)。

## 完成核对与结论的边界

所有五意图成功率分别为 33.33%、41.67%、0%、33.33%、25%，均未达到 60%。同向/多向成功率差分别为 45.71、2.86、0、22.86、8.57 个百分点；监视的差值为零只是两边均无成功样本，不能解释为满足双方式覆盖。过境和佯动的差值也未满足 20 个百分点目标。分布偏差仍在，主对照与交叉否定覆盖均比修订前下降。

已保存的全部候选抽样参数均出现多个取值，驻留方式有悬停/盘旋，监视圈数有 2/3，方向有顺/逆；这只确认抽样实现没有固定为单值。实际选中及至少保留一版的参数中，佯攻为 4 组（组深度 35.139%–49.518%）、突击为 3 组（终点深度 27.181–29.725 m）、区域搜索为 5 组（面积 0.260485–0.377212 km²、张角 66.901°–89.188°、重叠率 15.653%–28.618%）、过境为 5 组（弦位置分位数 0.133–0.916），均有多个计划取值。抵近观察仅 1 组：警戒外侧 55.337 m、计划驻留 39.412 s、悬停；其分布证据不足。监视选中/保留均为 0，无法确认实际参数分布或测量本轮监视时长，不以旧数据或候选计划代替。

参数表的 N 是明确列出的记录单位，不等于独立抽样次数；每骨架净空以及原监视圈数/方向会在多个候选中重复出现。同步/递次只在实测事实表分别计数，计划参数已去除此重复。实测同向跨度接近零；多向可测跨度约 110.502°–152.436°，有三股实例，但部分角色/股数仅有一个独立骨架。两版之间的浮点微差不代表新增几何形态。

两项捷径检查均在 I 之后运行，使用 33 条保留常规轨迹、5 个有样本的 family，分别正确 7/33、8/33；未达到 11/33 的训练折多数类基线。缺少监视类别及样本规模有限，结果不能证明五类完整数据已无捷径风险。本轮没有为缩短时长改变监视圈数、原半径允许范围或任何角色参数。

诊断运行使用 NumPy 2.5.3、SciPy 1.14.1、scikit-learn 1.5.2。SciPy 导入时提示其声明要求 NumPy 至少 1.23.5 且小于 2.3.0，与当前版本不符；分类器正常退出并保存逐折预测，准确率计数已从保存结果复核，但保留这一依赖兼容性限制。没有修改 Conda 环境，也没有重新调参挑选结果。

实际生成 12 张图：四种有样本意图各 2 张俯视图（含同向/多向；过境含多任务组）、三股图 1 张、中止/常规并排图 1 张、配对时序图 2 张。已目视检查各角色、两种逼近、三股、多任务组、中止及两组时序的代表图，坐标、图例与实测标记可读。8 项覆盖缺口包括监视的各类图与同向展开图，以及侦察、佯动、突防的多任务组图；这些条目有重叠，不是 8 个独立骨架缺口。未生成样本没有用规划图或旧轨迹补充。[图件来源与缺口清单](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_s2x_final_20261015T053115Z_a3b834e8/figures/figure_coverage.json>)。

H 后只补充报告与参数统计单位，未修改生成器或重标轨迹。共享规划最后一次修改后的固定回归仍为 E 的 22/22 PASS；冻结时 S2 测试 151/151 PASS。冻结配置 SHA256 仍为 `94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193`。所有任务按阶段本地提交，不推送；不以达成分布目标为理由更改角色定义或放松判据。
