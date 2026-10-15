# Traj2Language v0.7 S2 修订轮执行与验收记录

本轮以 `S2_revision_handoff_ec86137.md` 为有效入口；旧第二段交接第 3 节、条件—审计表及执行记录继续有效，冲突以本轮入口与用户当前澄清为准。

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
| 佯攻 | 每组警戒带深度比例 U(35%,65%)，每机再加 U(-3%,3%)；保持原 30%–70% 规划允许范围，成败判据不变 |
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
