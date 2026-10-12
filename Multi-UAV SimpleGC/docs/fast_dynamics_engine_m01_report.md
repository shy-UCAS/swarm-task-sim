# 快速动力学引擎 M0/M1 实施与本地验收

日期：2026-10-12。**M0/M1 首包本地验收通过；下一包 M2 尚未实施。**（M2 进度补注见 §6：M2-00 仅建立本地检查点，M2 功能仍未实现。）开发目录为 `Simulation-dev/Multi-UAV SimpleGC`，Git 基线 `5e45637f2bf63054ed0ace2433fd7c9ea7b075ac`；本次实现未提交。依据[融合计划 r2](fast_dynamics_engine_implementation_plan.md)完成首包代码。本次没有启动 SITL、续跑历史批次、修改历史数据或执行提交、推送、PR、标签。

> **2026-10-12 证据位置迁移（M2-01，不改写历史验收结论）：** 本报告引用的 M1 证据树已按 M2-01 复制到仓库外并清理仓库内批量产物，`migration_id = m01_20261012_v1`。
>
> - 归档根：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/`
> - 逐文件映射与哈希（356 项）：[relocation_index.json](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/relocation_index.json>)，SHA256 `e023a4e3194f12790279710c3f2a785208a7165b1be736c5d55bdea0c5ccb55e`
> - 仓库侧小型索引：[verification/fast_dynamics_m01/migration_index.json](../verification/fast_dynamics_m01/migration_index.json)，SHA256 `96a3678d710e1a8093d008410ca2b55ecbde19ee55cb76ea3a3b9048fb6f7ad3`
> - 映射规则：`Multi-UAV SimpleGC/verification/fast_dynamics_m01/<相对路径>` ↔ `<归档根>/Multi-UAV SimpleGC/verification/fast_dynamics_m01/<相对路径>`
> - 迁移结果：356/356 文件逐字节复制并核验（30,216,091 字节）；清理 338 项显式候选（182 项跟踪文件 + 156 项被忽略载荷，29,521,505 字节）；仓库保留 18 项阶段级汇总/工具加上述索引。
> - **原验收日期、判定、数字和源身份全部不变。** 下表及 §3、§4 中指向被清理文件的链接已改为指向迁移后位置；被保留文件（`verification.json`、`mission_convergence.json`、`tests.json`、`numerical_core_evidence.json`、`step_halving_semantics.json`、`kernel_benchmark.json`、来源索引、划分安排、最终只读复核与采集脚本）的相对链接不变。

## 1. 实际交付范围

首包实现独立 `fast_dynamics_v1` 后端及一个既有双机快速通过任务的完整数据链。物理状态为 ENU 的 \((\mathbf p,\mathbf v,\mathbf a)\)，使用受限加速度、欧氏 jerk 约束和常 jerk 多项式积分；不直接裁剪实际位置或速度。七组配置严格验证字段，未实现的控制类型、观测模式或任务组合明确拒绝。

内部默认步长 \(h=0.02\,\mathrm{s}\)，统一整数微秒时钟；全部飞机读取同一快照再同步更新。模型输入输出为 10 Hz 半开网格 \([0,T)\)，帧数 \(\lceil10T\rceil\)，实际结束时刻独立保存。积分步内用多项式定位区域穿越和到达区间，内部支持轨迹保留终点、阶段事件和输出时刻。阶段屏障在全部飞机完成真实驻留的时刻截断最后一个积分步，避免步长取整引入额外时序误差。

M1 任务执行仅支持双机 `rapid_passage` / `line_abreast`、每阶段至多一个航段，从稳定空中状态开始。复用原 TaskSpec 编译航线、速度、到达容差、确认驻留和末端保持；先到飞机等待期间仍检查是否保持到达条件，失效则留下 reset 事件并重新确认。三意图、连续多航点和 2/3/4 机完整覆盖属于 M2。

数据链使用公共 `build_dataset`、`audit_dataset`、`describe_dataset`、`load_episode`，沿用既有几何阈值和三态语义。新协议单独声明引擎真值、理想合成观测与 `sim_clock`；固件为 `not_applicable`，未输出姿态、IMU、电机或起降证据。事实层为 `observer_facts_fast_dynamics_v1`，复用已有中文模板词汇。

## 2. 验证证据

最终自动验收 **406/406 通过**：旧清单 367/367（78.50 s）、新增 39/39（16.33 s），无失败、错误或跳过。新增内核 15 项、执行 10 项、数据链 14 项，包含不同 worker 数与派发顺序的规范轨迹/事件一致性。机器可读结果为 [verification.json](../verification/fast_dynamics_m01/final_verification_01/verification.json)，同目录 `completion.json` 已原子写入且绑定结果哈希。仿真及整个验证前后源码快照一致。

| 最终检查 | 结果 | 证据 |
| --- | --- | --- |
| 旧接口离线清单 | 367/367 通过 | [legacy_tests.log](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/Multi-UAV SimpleGC/verification/fast_dynamics_m01/final_verification_01/legacy_tests.log>)（已迁移） |
| 新内核、执行和公共数据链 | 39/39 通过 | [fast_dynamics_tests.log](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/Multi-UAV SimpleGC/verification/fast_dynamics_m01/final_verification_01/fast_dynamics_tests.log>)（已迁移） |
| 固定双机任务重复完整链 | 5/5 成功、各 294 帧、各 4 条中文描述、公共加载/审计通过 | [首个完整样本报告](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/Multi-UAV SimpleGC/verification/fast_dynamics_m01/final_verification_01/success_01/report.json>)（已迁移） |
| 真实语义失败 | 1/1 正确保留：1637 帧、完成执行、语义 false、质量 true、4 描述 | [semantic_failure/report.json](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/Multi-UAV SimpleGC/verification/fast_dynamics_m01/final_verification_01/semantic_failure/report.json>)（已迁移） |
| 超时未知 | 1/1 正确保留：1 帧、0.03 s、语义 null、质量 false、0 描述 | [unknown_timeout/report.json](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/Multi-UAV SimpleGC/verification/fast_dynamics_m01/final_verification_01/unknown_timeout/report.json>)（已迁移） |

已有独立基线与最终只读历史复核：

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 原离线 CI 清单基线 | 367/367 通过 | [baseline_ci.log](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/Multi-UAV SimpleGC/verification/fast_dynamics_m01/baseline_ci.log>)（已迁移） |
| 最终 DR130 金标准 | 260/260 通过 | [baseline_dr130.json](../verification/fast_dynamics_m01/final_historical_regression/baseline_dr130.json) |
| 最终 v0.5 示例公共加载 | 4/4，冻结附件前后哈希不变 | [baseline_v05_loader.json](../verification/fast_dynamics_m01/final_historical_regression/baseline_v05_loader.json) |
| 来源索引 | T1/T4 共 84 次运行、42 任务、14 family | [m0_source_index.json](../verification/fast_dynamics_m01/m0_source_index.json) |

这不是全量历史集成测试全部通过的声明。归档缺件和旧断言依赖仍按原 v0.6.1 报告解释；没有重造旧证据来消除历史失败。

## 3. 固定任务与负例

固定输入为 T1 的 `rapid_passage_0000_v00`，原字节副本在 [测试 fixture](../tests/fixtures/fast_dynamics/rapid_passage_0000_v00.json)，SHA256 为 `dd5beb91f5388991487aab15c07493f74075e5ea17d99225db7313b2412ee318`。两机从东侧进入，参考速度 \(2.5\,\mathrm{m/s}\)，飞行高度 8 m，不要求返航，最终保持 2 s。源任务仍是原 `v0.6`，执行产物使用新的后端协议，不改写输入冒充 SITL。

合格样本实际结束时刻为 **29.320364 s**，模型输入 \(x\) 形状为 \(294\times2\times6\)。可直接加载[episode 目录](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/Multi-UAV SimpleGC/verification/fast_dynamics_m01/final_verification_01/success_01/dataset/episodes/fast_m1_rapid_passage/>)（已迁移）；中文描述见[descriptions.json](<F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/Multi-UAV SimpleGC/verification/fast_dynamics_m01/final_verification_01/success_01/language/descriptions.json>)（已迁移）。

负例通过执行配置改变实际状态：水平速度能力设为 \(0.3\,\mathrm{m/s}\) 后完成缓慢穿越，触发既有区域低速驻留规则，任务语义失败而数据质量仍可合格；执行时长限制为 0.03 s 则保留真实超时和语义未知，不生成描述。另覆盖零时长、无完整阶段窗口、数值错误、错误网格、伪造来源/能力、任务/config 错配、重哈希后的标签/速度篡改和 timeout 改 completed。

每份最终产物绑定配置、种子、Python/NumPy 环境、Git 基线及实际源码文件内容 SHA256。仿真前后及导出时核对源码快照；执行器结果与写入任务、编译场景和配置必须一致。已声明的完成状态必须有相符的唯一实际终态事件和完整阶段证据。CLI 在仿真前建立新 attempt，错误保留输入、配置和失败记录，不写完成标记；现有目录不可复用。

## 4. 数值与性能的适用边界

单机起步、90°有限半径转弯、停止和驻留的 \(h\) 对 \(h/2\) 检查：位置差 p99 为 0.014973 m、最大 0.015004 m；速度差 p99 为 0.009772 m/s、最大 0.009920 m/s，均达到初始 0.02 工程目标。证据见 [numerical_core_evidence.json](../verification/fast_dynamics_m01/numerical_core_evidence.json)。这只是离散数值收敛，不能当作与 SITL 或真实飞行的误差。

实际双机完整任务对比 20 ms 与 10 ms：位置差 p99 **0.014808 m**、最大 0.014898 m；速度差 p99 **0.011917 m/s**、最大 0.012619 m/s；事件最大时间差 **0.004975 s**。同轴 294 帧均计入，无删除边界样本；两种步长分别验证任务语义为成功，双通道逐条件结果相同。见 [mission_convergence.json](../verification/fast_dynamics_m01/final_verification_01/mission_convergence.json)和[步长减半语义核验](../verification/fast_dynamics_m01/step_halving_semantics.json)。

内核基准固定 300 仿真秒，2/4/8/16 机各五次、单 worker、共享主机；热运行实时因子中位数分别为 **288.65 / 280.85 / 278.23 / 274.36**。4 机达到该内核用例的 100 倍目标。测量计入控制、积分和 10 Hz 内存采样，排除任务编译、分析、哈希、导出、描述和写盘。首轮为新进程第一次 episode，不包含解释器导入或操作系统冷缓存。硬件、CPU/内存负载、参数、重复分布及源码哈希见 [kernel_benchmark.json](../verification/fast_dynamics_m01/kernel_benchmark.json)。

完整链路另以同一固定双机任务测五次，外层计时覆盖输入加载、模拟、分析、重复校验、导出、审计、描述、公共加载和最终报告/完成标记写盘；不包含 Python 进程启动。结果只适用于这个 M1 开发用例，不能与 T4 的完整任务组成和质量条件等同，因此不登记“完整生产吞吐达到十倍”的通过结论。

五次耗时分别为 1.8305、1.8316、1.7953、1.7931、1.7810 s；后四次中位数 **1.7942 s**、p95 **1.8262 s**，对应此固定用例约 **2006.4 个合格 episode/小时**。它是重复同一任务的局部测量，不是新数据集的预测交付速率。

## 5. 复现入口

在项目根目录使用 PowerShell 7 和 `.conda-env` 中的 `llm` 环境。**M2-01 起输出受外部输出根约束**：`--output` / `--output-root` 指向仓库内的路径会被拒绝，缺省根为仓库同级的 `SwarmData/fast_dynamics`（可用环境变量 `FAST_DYNAMICS_OUTPUT_ROOT` 覆盖）。以下输出必须为全新目录：

```powershell
$engineEnv = (Get-Content -LiteralPath '.conda-env' -Raw).Trim()
# 缺省：在外部输出根下新建 attempt，目录名带 UTC 时间戳
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n $engineEnv --no-capture-output python -B scripts/run_fast_dynamics.py tests/fixtures/fast_dynamics/rapid_passage_0000_v00.json
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n $engineEnv --no-capture-output python -B scripts/verify_fast_dynamics_m01.py
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n $engineEnv --no-capture-output python -B scripts/benchmark_fast_dynamics.py --duration 300 --repeats 5 --agents 2 4 8 16 --output-root 'F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/benchmarks'
```

`run_fast_dynamics.py --config <json>` 接受 `engine`、`vehicle_profile`、`controller`、`observation`、`environment`、`execution`、`quality` 七组覆盖配置，完整默认值和最终配置进入产物。新增测试也登记进常规离线 workflow；本次只在本地执行，没有触发远端 CI。

## 6. 未完成项与下一包

M2 尚未开始：扩展连续航线跟踪、三意图四飞法、2/3/4 机、返航/释放/驻留和完整多机时序，并保留相同公共数据链与旧接口回归。M3 再做无新增噪声的校准和标准冻结，M4 才增加相关扰动、两种输出模式及 pilot，M5 使用未见 family 独立验收。

> **2026-10-12 补注（不改写本报告结论）：** 上段“M2 尚未开始”指本报告撰写时（M2-00 之前）的状态。此后 M2 已启动分阶段执行：M2-00 仅保存 M0/M1 本地检查点 `0f7c42d`，最终审阅结论 `PASS`；M2-01 及后续阶段未开始，**M2 飞行功能仍未实现**。进度见 [M2-00 阶段报告](fast_dynamics_m2/M2-00_report.md)与[审阅回执](fast_dynamics_m2/M2-00_review_03.md)。本报告其余结论、证据与未完成项不变。

T1/T4 的 14 个 family 全部预留为开发对照，跨后端、重复运行和参数变体保持同组；当前没有盲测 family。新样本一律 `training_eligible=false`，质量合格不等于已经获得正式训练资格。模型未校准，不声称验证了真实控制器、传感器或跨域泛化。内部支持轨迹的几何分析沿用已有分段线性判据，不能解释为完整刚体接触/碰撞模拟。

`integration_attempt_01` 是开发中间产物，保留其当时源码哈希供排查；最终交付以 `final_verification_01` 下的样本与完成标记为准，不用中间尝试替代最终契约验收。该中间样本在迁移后的读取实验中从新旧两个位置都按同一原因被拒绝（`inconsistent or unsupported source capabilities, units, seed or code identity`），这是其绑定的中间源码身份所致，不是迁移缺陷，见 [M2-01 阶段报告](fast_dynamics_m2/M2-01_report.md)。
