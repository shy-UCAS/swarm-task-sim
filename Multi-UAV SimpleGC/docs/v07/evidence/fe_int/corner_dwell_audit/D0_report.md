# D0：拐点减速与 M1 驻留归因及受控对照实验

本报告执行用户正文及优先修订 R0–R5。总体结论：**EXPERIMENT_INVALID**。G0–G2 已通过，G3 在 probe_02 的原版 A 组终速门禁失败后停止；仅完成 1/7 对有效 A/B。已执行的 B 组独立精度结论为 **TRACKING_ACCURACY_PRESERVED**。未完成探针不计入有效对照，不据此作总体因果判断。所有单机结果标记 `solo_probe` / `EXPERIMENTAL_REFERENCE_NOT_FROZEN`。

## 第一章：输入完整性

固定基线 `81f804a969192790d89100528e3f802bc06446b1`；分支 `fe/corner-dwell-audit`。启动时目标工作树与分支均不存在，按 R0 创建同级工作树，核对 HEAD、分支和初始干净状态。相对 `92068b9` 的 task_v07、swarm_sim、configs 差异为空；未合入 P2。

工作目录：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-corner-audit\Multi-UAV SimpleGC`。DEFAULT_DATA 为 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset`，已确认存在。输入为 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261017T071447Z`；新增原始数据独立保存在 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\fe_corner_dwell_20261017T144144Z`。

环境：PowerShell 7.6.5；conda llm，Python 3.12.3、NumPy 2.5.3、Shapely 2.0.7。未安装或升级依赖。

核验 30 骨架、60 episode、480 个 agent-episode、240 个去重骨架成员。五类输入文件完整；truth 与 frame_labels 的时间轴、成员顺序一致，10 Hz 网格、维度、有限值、组唯一映射与参考路线全部通过。同一骨架成员的 synchronous/sequential 参考几何一致。

M3 冻结配置 SHA256：`94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193`。全部受保护源码、既有测试、历史 QC 及 60×5 个输入文件哈希登记于 D0_source_manifest.json，最终复核未改变。

| 关键文件 | SHA256 |
| --- | --- |
| swarm_sim/fast_dynamics/route_tracker.py | 7eab9e56ba3b04ec593663ac47b18a838f25f9af8b7f66ce50c6ee36275c323e |
| task_v07/criteria_labels.py | bb52b3dd559285f827df64d0c205ef1fefd5ffc3387a880118f41b5633db0ffe |
| task_v07/detectors.py | 741669e343cde547167c4962f3834d2cb0945da7b7c0a6a4b7f83167b85e9c47 |
| task_v07/execution.py | 22baaf8252e4807effa5a2a40c154c10d96a959b53cfe36d11ba360a0fc84d26 |
| scripts/qc_v07_fe_pre_freeze.py | d37ebdb4be3effe4fb66a74a4b844ec077cfa0634bfe4e7752f7fb91a00bce9d |
| scripts/qc_v07_fe_speed_profile.py | a901b7bc45228b9f53df7a9a39e01071acf39fd7e6e8a9e6a0b8de304c643b43 |

## 第二章：M1 驻留判据

沿用原始 `load_criteria()` 和 `work_mask()`：窗口为 \(20\,s\)，10 Hz 闭区间 \([b,b+200]\) 共 \(201\) 帧；水平首尾位移 \(\|p_{b+200}-p_b\|\le30\,m\)，相对窗口均值的最大半径 \(\max_k\|p_k-\bar p\|\le30\,m\)。`speed < 1.0 m/s` 仅用于分析，不是 M1 判据。

324 个正式阳性见证窗口逐一通过闭区间、保存时间、工作窗、首尾位移及集中半径核验。阴性不构造虚假窗口。按固定排序取 2 个佯动阳性、2 个过境阴性、2 个抵近观察阳性，原检测器重算字段与保存标签完全相同。

首个见证窗口与 union_frame_intervals 分开记录。见证窗口端点跨度为 20 秒；低速诊断按每帧 0.1 秒累计，201 帧全低速时为 20.1 秒，二者不能混用。每个阳性窗口的速度 min/p10/p50/max、实际航程、最低帧、连续低速区间及 union 持续时间均已保存。

## 第三章：转角参考速度上限

从真实 RouteTracker 原语读取 cap，使用原 `_curvature_bounds()` 校验分解。冻结 \(H=0.475+0.1=0.575\,s\)，\(d=\min(0.25,0.1L_{i-1},0.1L_i)\)。全部 CURVE 满足 \(v_{cap}\le d/H+10^{-9}\)，且 \(d/H\le0.435\,m/s\)。这是静态参考速度限制，不是实际飞机瞬时速度。

S2：240 条唯一成员路线共 8247 个内部顶点，其中 CURVE 8132、EXPLICIT_STOP 115，本批无 STRAIGHT。

| 类型 | 数量 | curve cap min/p50/max (m/s) | d/H min/p50/max (m/s) | curve cap<1 比例 |
| --- | --- | --- | --- | --- |
| CURVE_LT_45 | 7849 | 0.182990 / 0.434783 / 0.434783 | 0.182990 / 0.434783 / 0.434783 | 1.000000 |
| CURVE_45_TO_90 | 225 | 0.205448 / 0.434783 / 0.434783 | 0.205448 / 0.434783 / 0.434783 | 1.000000 |
| CURVE_90_TO_175 | 58 | 0.009521 / 0.221570 / 0.355755 | 0.434783 / 0.434783 / 0.434783 | 1.000000 |
| EXPLICIT_STOP_175_PLUS | 115 | — / — / — | — / — / — | — |

显式停车不存在曲线 cap，表中用“—”表示；其退出速度为 0。角度档仅供统计，不用于 B 组分档控制。

## 第四章：正式驻留窗口归因

S1：数量单位为 agent-episode；唯一成员路线另列。匹配计数只在正式阳性首窗口内统计，同一窗口可同时匹配曲线与停车。

| role / execution_method | agent-episode / 唯一路线 | 阳性 / 比例 | 曲线匹配 | 停车匹配 | 无顶点 | 多类型 | 多顶点 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| feint / feint | 104 / 52 | 104 / 100.00% | 104 | 0 | 0 | 104 | 104 |
| intrusion / intrusion | 84 / 42 | 42 / 50.00% | 0 | 0 | 42 | 0 | 0 |
| monitoring / monitoring | 100 / 50 | 96 / 96.00% | 56 | 96 | 0 | 56 | 70 |
| reconnaissance / area_search | 28 / 14 | 14 / 50.00% | 10 | 4 | 0 | 8 | 8 |
| reconnaissance / close_observation | 68 / 34 | 68 / 100.00% | 14 | 54 | 0 | 0 | 0 |
| transit / transit | 96 / 48 | 0 / 0.00% | 0 | 0 | 0 | 0 | 0 |

佯动 104/104 阳性窗口均匹配普通曲线，但也全部为多顶点、多角度类型匹配，不能唯一指向某个活动原语。监视 96 个阳性全部匹配显式停车，56 个同时匹配普通曲线。抵近观察的 68 个阳性中 54 个匹配显式停车。侵入 42 个阳性均无 3 m 内顶点；过境为 0/96。不同角色的阳性不能一概解释为普通转角引起的异常。

S3 汇总：下表覆盖全部 324 个正式首窗口；每项列 min/p50/max。

| 指标 | min / p50 / max |
| --- | --- |
| 首尾位移 m | 10.236598 / 29.630993 / 29.992658 |
| 水平航程 m | 29.656747 / 52.625297 / 75.548179 |
| 最低速度 m/s | 0.000009 / 0.000991 / 0.521013 |
| p50 速度 m/s | 0.011901 / 1.735174 / 4.631262 |
| 低速帧比例 | 0.129353 / 0.427861 / 0.776119 |

S3 固定示例：按 (skeleton_id, mode, agent_id) 升序，取前 3 个阳性窗口。匹配距离为所有窗口帧到内部航点的最小距离，完整索引与各顶点 cap 见 JSON。

| 窗口 | 位移 m | 航程 m | 速度 min/p50 | 低速比例 | 曲线/停车数 | 最近距离 m | 顶点:cap m/s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| family_s15_1b876e6b8b6f70c6_ext_006_regular / sequential / uav_02 | 29.925398 | 68.757372 | 0.499917 / 4.631262 | 0.134328 | 3 / 0 | 0.006942 | 7:0.434783, 8:0.434783, 9:0.434783 |
| family_s15_1b876e6b8b6f70c6_ext_006_regular / sequential / uav_03 | 29.767544 | 68.664417 | 0.500920 / 4.630796 | 0.139303 | 3 / 0 | 0.012545 | 8:0.434783, 9:0.434783, 10:0.434783 |
| family_s15_1b876e6b8b6f70c6_ext_006_regular / sequential / uav_04 | 29.939192 | 60.567936 | 0.506281 / 3.372491 | 0.169154 | 4 / 0 | 0.007078 | 30:0.434783, 31:0.434783, 32:0.434783, 33:0.434783 |

G2 JSON 包含全部 324 个阳性窗口 S3、480 条成员记录和 240 条去重路线。匹配保留全部 3 m 内顶点，另外保留低速帧匹配；score 使用帧集合去重，不能将重合匹配重复计数。最近顶点不自动等于正在执行的原语。

## 第五章：实验性 A/B

R1 干预应用于全部 \(10^{-8}\,rad<\theta<175^\circ\) CURVE：\(v_{trial}=\min(v_{cruise},\sqrt{a_{max}/(2\kappa)},(j_{max}/(2(\kappa^2+\kappa_s)))^{1/3})\)，只去掉 \(d/H\)。无 45° 分档、无倍数和参数扫描。原曲线几何、显式停车、原语顺序、node_index 和航点见证保持不变；exit_cap 按原 `_build()` 末尾规则重算。

A 无 monkeypatch；B 在独立子进程内通过 patch.object 临时替换 _build，退出恢复。只读返回事件追踪取得实际 tracker，统计事务回滚后已提交的 witness；没有包装或替换 observe_segment。拆分驻留路线映射回原航点，保留子跟踪器原始记录，并排除出发段对已见证驻留节点的再次获取。

在任何 A/B 开始前锁定 7 个 synchronous 探针。选择文件 SHA256：`fc35b6cad14736c30bcd644ee78462a81a1a407658865ac0b5052540b823ca87`，外部副本与运行后哈希一致。佯动按 R2 任意 CURVE 条件及 score 确定性排序，优先不同 family；监视按指定索引排序取前两名，不要求阳性。

| 探针 | 类型 | skeleton_id | 成员 | score | 执行状态 |
| --- | --- | --- | --- | --- | --- |
| probe_01 | feint | family_s15_1b876e6b8b6f70c6_ext_008_regular | uav_03 | 34 | A+B 有效 |
| probe_02 | feint | family_s15_38bedc9d791d547b_ext_008_regular | uav_05 | 34 | A 终速门禁失败，B 未运行 |
| probe_03 | feint | family_s15_c713f51898e81011_ext_003_regular | uav_01 | 34 | 未运行 |
| probe_04 | transit_control | family_s15_1b876e6b8b6f70c6_ext_005_regular | uav_01 | — | 未运行 |
| probe_05 | observation_control | family_s15_1c267d4d7000043d_ext_006_regular | uav_01 | 0 | 未运行 |
| probe_06 | monitoring | family_s15_1b876e6b8b6f70c6_ext_007_regular | uav_01 | 9 | 未运行 |
| probe_07 | monitoring | family_s15_1b876e6b8b6f70c6_ext_007_regular | uav_02 | 8 | 未运行 |

A1 与 A2 的 time_us、p、v 数据类型和字节以及 execution_status 均与对应历史 single_agent 存档完全一致。三个实际执行臂的初始 p/v/a 均逐值等于原输入。未改输入、时间预算、积分器或冻结参数。

唯一有效配对 probe_01：

| 指标 | A 原版 | B 去除 d/H |
| --- | --- | --- |
| execution_status | completed | completed |
| M1 detected | True | True |
| M1 union 总时长 s | 25.6 | 25.6 |
| 首窗口 s | 1212.2–1232.2 | 1211.6–1231.6 |
| 低速事件数 | 20 | 20 |
| 每公里低速事件数 | 3.126320 | 3.126315 |
| 运动窗低速时间占比 | 0.025434 | 0.025030 |
| 单机运动窗总时长 s | 1435.100000 | 1434.300000 |
| 全导出轨迹时长 s | 1435.900000 | 1435.100000 |
| 真实最大水平速度 m/s | 4.632649 | 4.632649 |
| 真实最大水平加速度 m/s² | 3.749601 | 3.749601 |
| 终点位置误差 m | 0.037122 | 0.037683 |
| 终点速度 m/s | 0.138633 | 0.136800 |
| 基础物理检查 | PASS | PASS |
| 内部航点 witness / 航点数 比值 | 1.000000 | 1.000000 |
| 最大横向偏差 m | 0.130297 | 0.130297 |
| p99 横向偏差 m | 0.023483 | 0.024441 |
| tracking_tube_m | 0.500000 | 0.500000 |
| 超管道帧数 | 0 | 0 |

低速统计直接复用既有 qc_speed_report 的 analyse_member：V_LOW=V_MOVE=1.0 m/s；运动窗从首个 speed>1 到最后一个 speed>1 的帧闭区间，低速为 speed<1，不设最短时长。全导出时长另列，避免与运动窗混淆。每帧横向偏差使用真实位置到原 points_enu_m 前两维参考折线的最短距离。

A/B 均见证 19/19 个内部航点，比例为 1。B 最大横向偏差 0.1302965552 m，小于 0.5 m；最大帧索引 9，时间 0.9 s，最近参考线段端点索引 [0,1]，无超标帧或遗漏航点。B 的 19 个曲线条目中 18 个 cap 实际变化，另 1 个仍由其余上界限制；逐曲线角度、old/new cap、d/H 主导情况与实际单机首窗口低速匹配见 D0_probe_results.json 和 D0_final_audit.json。

probe_01 的 M1 阳性和 25.6 秒 union 总时长均未改变，首窗口整体提前 0.6 秒。运动窗缩短 0.8 秒，低速事件仍为 20 个，低速时间比例从 2.543377% 降到 2.502963%。这些是该单一样本的描述结果，不能称为消除了 M1 驻留。

停止原因：probe_02 A 已完成且与存档逐位一致，但终速为 **0.15929467451992158 m/s > 0.15 m/s**；终点位置误差 0.034763710166274754 m < 1 m，其余基础检查通过。正文 5.8 要求 A/B 均符合 terminal_speed_m_s，故没有执行 B2 或后续探针，没有换用较宽阈值继续。

原执行器实际优先使用 stop_speed_m_s=1.5 m/s、stop_radius_m=15 m；本次指令要求验收的是 terminal_speed_m_s=0.15 m/s、terminal_radius_m=1 m。这解释了原存档 completed 与本轮严格门禁不一致；它并非 B 引入的问题，也不是重放不一致。七个历史单机存档终点事实已做只读复核，记录于 D0_final_audit.json；未运行探针的历史事实不能算作新 A/B 结果。

G3 墙钟 102.14 秒，小于 1800 秒；停止并非超时。有效配对 1/7；probe_02 只有 A，probe_03–07 均未运行，共 6 个未完成探针，全部排除在有效 A/B 分母之外。没有续跑、补选或参数扫描。

验证记录：新增分析单测 16 项，既有 tracking 12 项、core 15 项、M1 criteria 8 项，共 **51/51 通过、0 skip**，全部通过 python -B -m unittest -v <模块> 执行。测试日志及完整命令见 D0_test_results.json。原有测试文件和断言未修改。新增测试按 R1 覆盖 10°、45°、90°、174° 全部 CURVE 干预及 175°/180° 停车不变。

过程异常透明记录：G2 首次在 JSON 写出时遇到 NumPy 标量序列化错误；仅修正新增分析工具的 JSON 标量转换并完整重跑 G2，数值计算未改变，当时尚未开始 A/B。原错误保留在外部 G2_initial_serialization_error.txt。最终审计确认脚本哈希与 G3 注册一致、选择锁不变、生产及输入哈希不变。D0_final_audit 的 PASS 仅表示保存结果与保护性审计通过，不表示本实验技术门禁通过。

## 第六章：最终分类

整体技术状态与归因状态均为 **EXPERIMENT_INVALID**，不授予 D0_TECHNICAL_PASS。基线复现成功，但第二个 A 组未满足指定终速合同，剩余计划未完成。因此不能证明或否定“普通转角参考限速是非预期 M1 驻留的重要来源”。

单独的跟踪精度分类为 **TRACKING_ACCURACY_PRESERVED**，适用范围严格限定为唯一已执行的 B1：全部航点被见证且最大横向偏差不超过 tracking_tube_m。没有将此结论外推到 B2–B7。未发生精度下降；代码将精度分类与基础物理检查分开，精度下降本身不会中断效果统计。

静态证据支持 d/H 普遍限制普通曲线参考速度，以及佯动阳性窗口与曲线邻近低速存在关联。唯一有效配对没有观察到 M1 阳性或持续时间变化，但本轮整体中止，不能把一个配对的描述性结果升级为完整批次 CORNER_CAP_EFFECT_NOT_OBSERVED，更不能宣称策略有效或正式可用。后续需人工先确认 terminal 与实际 stop 参数的验收合同；本轮不自行修改。

## 第七章：限制

- 未改变任何正式生产源码、配置、既有测试、历史 QC、标签或 episode；未修改其他工作树项目文件，未合并 P2。
- 单机实验不是完整多机碰撞、任务质量或系统合同验收，且监视与两个对照探针尚未运行。
- 临时策略未通过 M3 独立验证；不以 10 Hz 加速度差分声称连续时间 jerk 合同通过。
- B 组数据不得作为 First Edition 正式训练数据，也不得覆盖既有数据。
- 所有逐帧新数据留在独立外部 attempt；本提交只含允许的新增脚本、测试、诊断 JSON 和报告。
- 普通推送后停止，等待人工审查；不启动正式生产或完整 30 骨架重跑。
