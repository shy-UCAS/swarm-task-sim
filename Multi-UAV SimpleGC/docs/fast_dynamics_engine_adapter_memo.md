# 快速动力学 M0：适配备忘与开发来源登记

日期：2026-10-12。依据[融合计划 r2](fast_dynamics_engine_implementation_plan.md)实施 M0/M1。旧代码基线为 `5e45637f2bf63054ed0ace2433fd7c9ea7b075ac`；本次实现未提交，执行身份另由产物中的实际源码内容哈希绑定。本文登记接入选择和校准安排，M1 实际测试与样本以[交接登记](fast_dynamics_engine_kickoff.md)为准；证据树已于 M2-01 迁移到仓库外 `SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/`，映射与哈希见[迁移索引](../verification/fast_dynamics_m01/migration_index.json)及 [M2-01 报告](fast_dynamics_m2/M2-01_report.md)。没有启动 SITL、重分析历史数据或重新划分旧数据集。

## 1. 首包能力与版本

新后端独立声明 `simulation_backend=fast_dynamics`、`protocol_version=fast_dynamics_v1`、`engine_version=0.1.0`、`plant_model=point_mass_jerk_v1`、`time_base=sim_clock`。语义协议为 `multi_intent_validation_fast_dynamics_v1`，资格协议为 `fast_dynamics_quality_v1`，约束版本为 `airborne_mission_limits_fast_dynamics_v1`，事实版本为 `observer_facts_fast_dynamics_v1`。这些身份与源 TaskSpec 的 `v0.6` 字段分别保存；不改写源任务以伪装成历史运行。

M1 仅接通既有 `rapid_passage` / `line_abreast` 的空中任务范围：`lifecycle_scope=airborne_mission`。初始 ENU 位置来自场景水平位置与任务飞行高度，初速度、初加速度为零；任务接近、穿越和末端驻留由实际动力学执行。没有真实起降、姿态、IMU、电机、碰撞接触、估计器闭环或新增随机扰动。理想合成观测是同一引擎真值的投影；双通道规则复核不构成两个独立物理来源。三意图四飞法、随机观测和规模化生产是后续里程碑。

外部状态为 ENU 的 \((\mathbf p,\mathbf v)\)，单位分别为 m 和 m/s；内部保存净平动加速度 \(\mathbf a\)（m/s²）及受限 jerk（m/s³）。加速度不是加速度计读数。未模拟量 absent/unsupported，不填全零有效姿态或 IMU。控制器读取理想真值，观察通道不反向改变飞行。

整数时钟决定积分和输出，主机钟只计性能。输出网格为 \(t_k=k/10\)、\(0\le t_k<T\)，帧数 \(N=\lceil10T\rceil\)，结束时刻 \(T\) 单独保存。标签/事实使用含终点的内部支持轨迹；10 Hz 模型输入仍严格半开。零时长为空且不可用于常规训练/配对。旧 SITL 的端点和时间解释保持原样。

## 2. 从输入到消费者的适配表

以下旧耦合来自本地源码检查；“接入”是首包的明确责任分派，不表示后续能力全部完成。

| 输入或产物 | 原消费者/耦合 | 时间与单位 | M0/M1 接入 |
| --- | --- | --- | --- |
| TaskSpec `scenario/mission/planner/execution` | `tasks.compile_task`、`mission_v3`、意图注册表；execution 仍有 AUTO/固件字段 | ENU m、m/s、s；`heading_deg` 为源配置角度 | 原样读取、哈希绑定并复用编译器；执行只选被支持字段，固件/端口/起降字段不成为引擎证据 |
| 编译 `phases[].routes`、speed、hold、start delays | `runner_v3` 原本上传 MAVLink 航线、等待主机事件 | 每机 ENU 路径，仿真秒 | 新离线状态机读取路径；同步世界快照后统一提交状态，不启动旧 runner |
| 实际状态与阶段事件 | `route_windows` 原本依赖 FCU/SIM 和终端任务事件 | 仿真 tick、ENU m/m/s | 独立窗口适配器读取实际 phase started/arrived/hold ended；按支持轨迹再次核验到达距离与水平速度 ≤0.3 m/s；不把计划到达当事实 |
| `support_truth.csv` / `support_observations.csv` | `mission_evaluation_v3._channel`、注册意图几何验证器、返航规则、facts | 仿真秒；包含阶段边界和结束时刻，初始实现为积分频率 | 复用现有阈值与三态结果；用有界 `simulation_clock` 直接时间接口，不建立 FCU 被动时钟；来源写引擎真值/合成观测 |
| `truth.csv` / `observations.csv` | `episode_loader` 固定六维特征；历史 truth 只有位置 | 固定 10 Hz，\([0,T)\)，ENU m/m/s | 观测保留 `t_s/agent_id/valid` 及六维字段；真值/支持样本只供监督和核验；不得进入模型输入 |
| 质量与能力证据 | `quality.episode_quality_eligibility` 原要求 clock quality，sim_source 还要求 firmware 为 true | 时钟完整性、有限值、速度/积分/轨迹约束 | 显式 fast 协议分派；模型/config/source 哈希和真实数值/记录检查取代来源门禁；固件/机载参数/FCU 时钟为 `not_applicable` 并说明原因 |
| `manifest.json` / `labels.json` / 语义附件 | `protocol.validate_artifact_protocol` 核对六个协议字段、附件、来源和资格一致性 | 仿真秒，版本不可隐式猜测 | 新协议注册，缺少来源/能力或错误证据拒绝；任务成败、数据质量、双通道一致分别判断；unknown 不记为通过 |
| dataset 导出 | `dataset.build_dataset` 校验源 manifest、质量策略与统一协议；按 family 哈希 split | 源时间契约随 episode 保存 | 新分析产物走显式分派；一个数据集拒绝静默混合 fast 与 SITL；输出新目录，不回写历史 latest |
| dataset 审计 | `dataset_audit.audit_dataset` 校验完整性、协议和 family 泄漏 | 不重新求动力学 | 审计新产物真实附件与哈希；保留失败/未知记录、分母及拒绝原因 |
| 事实和中文描述 | `observer_facts_v0` 原文写 SIM/FCU；`language_v0` 按语义版本限定事实版本 | 仿真秒、双通道逐事实核验 | 显式事实来源版本；复用语义词汇/模板，来源为引擎真值和理想合成观测；只为质量合格且一致的样本生成描述 |
| 模型加载/公开区域 | `load_episode`、`load_public_scene` | \(x\in\mathbb R^{T\times N\times6}\)、mask、t_s；目标四角 ENU | 协议分派后仍只输出六维观测；无效样本零填充且 mask=false；公开区域仍只白名单四角，任务/事件/真值/quality/family 不作为输入 |

`route_windows` 的历史真值水平速度由位置后差分构造、观测速度来自 FCU；`mission_evaluation_v3` 和 facts 的旧来源文字不能直接沿用。首包通过独立支持轨迹与窗口入口解决这一耦合，保留原意图判据。半开终点不能靠给输出多塞一帧解决，否则会破坏新契约。

## 3. 固定双机输入及字段映射

首包固定选取现有 T1 bundle 的 `rapid_passage_0000_v00`。这是一份已存在的双机输入，不是将三机模板删一架重造的任务。来源根：

`F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/parallel_batch/v061_T1_k2_s1_seed2026100812/bundle/`

| 来源 | 文件/值 | SHA256 |
| --- | --- | --- |
| 原始任务 | `missions/rapid_passage_0000_v00.json` | `dd5beb91f5388991487aab15c07493f74075e5ea17d99225db7313b2412ee318` |
| 原始编译场景 | `scenes/rapid_passage_0000_v00.json` | `ae7e659aa8225c9f446c681653cd8e6db2fc04a9448facc30a2313fa982b25b1` |
| 规范物理场景 | `scene_content_v1` | `74f9c65a90cdb4ffd5eda2e19ad9fada0f1137f06ae58f909d966bfa8e62f8b5` |
| family | `scene_74f9c65a90cdb4ffd5ed` | 来自上行哈希，不按 run ID 另分 family |

具体映射如下：

| 源字段 | 固定任务值 | 执行/下游用途 |
| --- | --- | --- |
| `scenario.vehicles[].id/east_m/north_m` | uav_01：(35.5683, 3.8932)；uav_02：(39.1878, 15.0171) | 稳定身份与初始水平位置；实际精度读取 JSON 原值 |
| `execution.takeoff_alt_m` | 8 m | 空中初始化高度；不由此生成起飞事件 |
| `execution.speed_m_s` | 2.5 m/s | 参考速度，实际速度由动力学产生 |
| `mission.intent` / `flight_pattern` | rapid_passage / line_abreast | 指定标签与编译路径；不证明任务成功 |
| `planner.params.entry_side` | east | 规划从东入场；观测进入方向从轨迹独立计算 |
| `p00_approach.routes` | 终点 E=27.7990；N=1.4386 / 14.9131；U=8 | 实际接近与阶段屏障 |
| `p01_transit.routes` | 终点 E=−8.5929；同一 N/U | 实际穿越；没有中间必须悬停的航点 |
| `mission.return_required` | false | 首包样本没有返回阶段；不能宣称已验证完整返航覆盖 |
| `execution.arrival_tolerance_m` / `confirmation_dwell_s` | 1 m / 0.5 s | 实际到达/确认窗口；不改原研究含义 |
| `execution.final_hold_s` | 2 s | 实际末端驻留，结束时刻独立保存 |
| `execution.max_gap_s/min_separation_m` | 0.5 s / 5 m | 原证据缺口与任务间距上下文；质量门禁另以新协议明确声明 |

## 4. M0 只读来源索引与划分

机器可读登记位于 [m0_source_index.json](../verification/fast_dynamics_m01/m0_source_index.json)，初始划分安排位于 [m0_evaluation_split.json](../verification/fast_dynamics_m01/m0_evaluation_split.json)。采集脚本 [collect_baseline.py](../verification/fast_dynamics_m01/collect_baseline.py)核对 T1/T4 bundle 的任务和场景字节 SHA256，重算规范场景哈希并检查 family 绑定；只读清单和既有产物，不重分析轨迹。

索引逐运行登记 batch/run、task/scene 路径和哈希、规范场景、family、重复组、意图/飞法、时间协议、质量、成败、一致性、飞机数量、候选可计算指标与附件可用性、既有诊断使用状态。可计算指标登记表示已有对应类型的产物，实际计算前仍须检查公共时间轴及逐通道有效区间；时钟缺失或证据不足的运行保留并排除对应指标。T1/T4 的 84 次运行、252 架次合并为 42 个任务、14 个 family：每任务两次重复，每 family 六次运行（3 意图 × 2 批次）。原始 dataset 中的 train/validation/test 值仅保留来源记录，新引擎校准用途全部为 `development_reference`，不把这些已看过的任务当盲测。

这是 T1/T4 首批索引，不是 r1/r2 全量来源普查。M3 引入 r1/r2 或算法线已有资料前，须先将这些来源按 `scene_content_v1` 及规范场景哈希合并，补上既有训练/调参使用状态。相同 family 的不同意图、后端、速度参数、随机 realization、窗口和重复运行继承同一分组。缺少用途历史的来源先保持未分配，不推断为未见测试集。

M0 将全部 14 family 预留开发；校准与开发验证的内部细分尚未冻结，最终测试集为空且状态为待获得未见 family。后续选择前做精确 family/scene 哈希交集检查，并登记平移、编号变化等几何近重复筛查规则；当前索引中的保守规则使用现有规范精度，不代表完成了大规模近重复搜索。最终外部评估需要新的未见来源，当前没有新增 SITL 授权。

重复运行先在任务内汇总，再按任务或 family 等权；不将相关帧、飞机或重复执行当独立样本。每项结果同时给任务、family、运行、飞机分母及排除原因。

## 5. 校准指标与方法预登记

M1–M3 关闭新增过程、风和观测噪声。M3 先保存未校准 profile 的全任务结果，再按直线响应 → 转弯/驻留 → 多机阶段时序的顺序辨识。一次只增加能够由开发证据辨识的参数；SITL 时钟异常、约 2% 速度残差不得拟合成新引擎阻力或速度缩放。

| 指标组 | 计算/对齐方法 | 分母、异常及冻结要求 |
| --- | --- | --- |
| 直线启停与稳态 | 起步/刹车时间、速度分布、超调；真值位置导数另声明差分/滤波窗口与误差 | 按速度、机数和任务分层；SIM 位置导数不是瞬时传感器读数 |
| 转弯与驻留 | 有限转弯半径、终点位置/速度、驻留时长；控制参数与参考参数分别辨识 | 不用弧长对齐掩盖时间差；支持不足记 unknown |
| 路径形状 | 同阶段、同航段/圈次内单调弧长匹配，报告平均/p95/最大横向偏差与纵向进度 | 报匹配覆盖率、未匹配部分、端点及驻留；禁止跨圈最近点匹配 |
| 时间与多机关系 | 总时长、阶段时长、相对出发/到达、等待、顺序、最小间距 | 使用原共同仿真秒；间距不能从各机独立形状对齐轨迹计算 |
| 语义/事实 | 真值与观测逐条件、运动槽位、unknown、事实错误和标签翻转 | 全任务生成/质量率与共同合格子集并报；边界附近和远离边界分别统计 |
| 观测误差 | 位置/速度残差、相关性、滞后、缺失段 | 与动力学校准分开；保留 FCU 速度残差来源未知的限制 |
| 计算性能 | 内核仿真秒/主机秒；加载到描述完整链路任务/小时与合格 episode/小时 | 内核不将机数重复计入分子；M4 两种输出模式分别报告 |
| 后续研究 | macro-F1、槽位、事实错误率、检索；固定预算和模型的跨后端对照 | 仅 M5 未见 family 测试；开发结果不替代外部泛化结论 |

M3 冻结 `calibration_metrics.json`、`evaluation_split.json`、`acceptance_contract.json` 及其哈希，包含参数搜索范围/预算/种子/停止条件、阈值的研究后果和测量精度依据、数值误差带、重复次数和按 family 重采样的不确定性方法。候选“98% 一致、5% 时长、1 m 横向、0.5 m 间距”不自动采用。M1 步长收敛目标只是数值工程检查，不等于达到 SITL 真实性精度。

## 6. 旧接口回归基线及复现

环境：PowerShell 7.6.5；项目 `.conda-env=llm`，Python 3.12.3、NumPy 2.5.3。沙箱内 conda 首次因 Windows DLL 重定位无法启动，使用同一 conda/environment 的经批准沙箱外执行后可运行，没有切换 Python 环境或安装依赖。

当前首次基线：现有 `unit-tests.yml` 的 35 个模块 **367/367 通过**，耗时 105.504 s；完整日志 [baseline_ci.log](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/Multi-UAV SimpleGC/verification/fast_dynamics_m01/baseline_ci.log>)（M2-01 已迁移）。Windows 真实 symlink 因权限走既有 mock 分支，junction 用真实文件系统验证通过。此清单不是全量历史集成测试。DR130 **260/260 通过**、无元数据排除；v0.5 示例 **4/4 加载通过**，每个示例全部附件的前后哈希与冻结清单一致。结果记录于 [baseline_checks.json](../verification/fast_dynamics_m01/baseline_checks.json)、[DR130](../verification/fast_dynamics_m01/baseline_dr130.json)与[加载指纹](../verification/fast_dynamics_m01/baseline_v05_loader.json)，DR130 生成输出在全新临时目录。此次源库文件检查前后没有变化；它是集成前基线，不替代最终新代码回归。

复现命令（当前工作目录为项目根；复跑使用新的 `--output`，已有结果文件会被拒绝覆盖）：

```powershell
$engineEnv = (Get-Content -LiteralPath '.conda-env' -Raw).Trim()
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = 'tests'
$ciText = Get-Content -LiteralPath '../.github/workflows/unit-tests.yml' -Raw -Encoding UTF8
$modules = [regex]::Matches($ciText, "'test_[a-z0-9_]+'") | ForEach-Object { $_.Value.Trim("'") }
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n $engineEnv --no-capture-output python -B -m unittest -v @modules
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n $engineEnv --no-capture-output python -B 'verification/fast_dynamics_m01/collect_baseline.py' --output 'verification/fast_dynamics_m01/post_integration_baseline'
```

历史全套未通过项仅按 [v0.6.1 实施报告](v0.6.1_time_report.md)分类登记，本次没有重跑全套或修复旧证据：`test_task_v3` 的仅双意图旧断言；`test_parameter_comparison_v2`、`test_wp_p_protocol` 的外部归档依赖；`test_v05_batch_controller` 的冻结源码哈希；`test_v05_r12_controllers`、`test_v05c_validation_controller` 的旧 VP1 状态假设。历史报告为 1 failure + 5 errors，在当时未修改基线复现；不可把历史失败数当作本次新代码的实测失败数。
