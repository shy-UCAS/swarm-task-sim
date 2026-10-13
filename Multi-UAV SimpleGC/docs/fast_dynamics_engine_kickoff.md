# 快速动力学引擎：本地开发交接

> **2026-10-13 最新停止点：M3 默认参数基线完成，等待用户确认。** r2 排除 T1/T4 的14个 family 后固定为200个调参、86个内部留出 family（非严格盲测）。调参组282个合格参考已由fastsim重飞：281次完成、1次短段巡逻见证停滞超时；槽位首要一致率210/226，15条扫描另确认存在采样密度敏感性。已提出前置修复、四参数调校和数值标准，本轮未实际调参。M2-02B两组继续封存；参数冻结后仍须另行通知才执行内部留出和高速合成检查。47.549秒性能暂接受，不再优化，不启动SITL。见[基线与停止报告](fast_dynamics_m3_baseline_report.md)；本补注优先于下方历史状态。本地提交，不推送。

> **2026-10-12 后续：覆盖几何已提速；M3 在身份映射处停止。** 20 条旧 run 重算的 120 个 JSON 完全一致，12 正例通过；4 机扫描 47.549 秒，未达 30 秒，剩余瓶颈仅报告。512 离线测试、DR130 260 项、v0.5 四例通过。当前 M2-02B 新种子来源的 213 个校准任务与 r2 同名但身份全部不符，禁止以同名替代参考；冻结划分不变，不启动 SITL，不进入 M3 b/c。详见[性能与映射报告](fast_dynamics_coverage_performance_report.md)。此补注优先于下方历史状态，本轮本地提交，不推送。

> **2026-10-12 最新状态：M2 已完成并停止。** 已修复实际计划阶段标签；固定 12 正例＋4 状态变化负例完整链全部通过，16 条质量合格、64 条描述。离线测试 502/502、DR130 260/260、v0.5 示例 4/4；后处理仅复用相同语义计算，19 个导出文件逐字节不变。用户授权本地提交，不推送；未进入 M3。详见[本轮完成报告](fast_dynamics_m2/M2_runtime_resume_report.md)（含字段来源表、覆盖与耗时）；旧 P0 和历史产物保留。本补注优先于下文历史阶段状态与旧暂停说明。

更新：2026-10-12，对应**融合修订版 r2**。本文件是新窗口的工作入口；完整设计见 [实现计划](fast_dynamics_engine_implementation_plan.md)，实际交付与最终测试见 [M0/M1 报告](fast_dynamics_engine_m01_report.md)。**M0/M1 已本地实现，最小双机完整数据链已接通，M0/M1 最终本地验收已通过。M2 已启动分阶段执行：M2-00（保存 M0/M1 本地检查点）已建立提交 `0f7c42d` 并通过 Codex 最终审阅（`PASS`）；M2-01（M1 证据迁移与外部输出约束）已执行完毕、已获 Codex 最终 `PASS`、已提交 `16b7cb7`；M2-02B 新来源补充已获 PASS，M2-03 已执行并完成本轮设计修复待审，M2-04 及后续未开始，M2 飞行功能（三意图四飞法、2/3/4 机、完整多机时序）尚未实现，校准与生产验收也未完成。** r2 是计划修订号，与 SITL 生产 r2 无关。

## 1. 这次要做什么

用户决定先在本机实现第一阶段批量多机轨迹生成的快速后端。M0/M1 已采用 Python + NumPy、共同仿真时钟、受限加速度/加加速度的三维运动模型，**接通最小双机快速通过任务的分析、导出、审计、事实/描述和加载链**。当前只支持空中任务、理想合成观测和六维输入；下一包 M2 补齐三意图四飞法。SITL 保留为已有对照及未来外部测试来源，校准与研究验收仍未完成。

- 开发目录：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-dev/Multi-UAV SimpleGC/`。Git 根为上一级 `Simulation-dev`，不要在当前聊天可能默认打开的 `Simulation` 冻结目录开发。
- **仅本地开发、测试和记录；不推送、建 PR 或打标签，本地提交仅限用户明确启动阶段时按指南保存上一轮获准差异，也不以远端 CI 作为本阶段继续开发的前置条件。** 用户以后明确要求发布时再执行发布流程。
- 不启动 SITL，不恢复旧批次，不准备 r3。未来新引擎的离线合成测试与本地 pilot 按实现里程碑推进，不能冒充旧批次重跑。
- 此次实现的历史开发基线为 `5e45637f2bf63054ed0ace2433fd7c9ea7b075ac`，M0/M1 实现已保存到本地检查点 `0f7c42d`。当前HEAD为 a46f034，未提交项为 M2-03 设计修复、摘要、回执与入口说明；具体以 git status 和本阶段报告为准，执行身份另有源码内容哈希；不要为了得到“干净工作区”执行 reset/clean 或覆盖它们。

## 2. 当前真实进展

| 项目 | 当前结果 | 如何使用 |
| --- | --- | --- |
| v0.5 | 260 次运行已冻结，252/260 质量合格，1,008 条描述 | 历史数据只读；开发仓库带 4 个完整示例 |
| v0.6 三意图 | 侦察、巡逻、快速通过及四种生产飞法已实现；r1 296/900、r2 465/900 后停止 | 任务/规划/语义可复用；两批不恢复、不 finalize |
| 并行基础设施 | 规则暂停、只读进度、持久化重试、子集 prepare、可配置基础端口已实现 | 正式与子集 prepare 的 `--base-port` 缺省均为 19100；新后端不必依赖端口 |
| v0.6.1 时间契约 | 已实现并发布 `v0.6.1-time`，标签对应代码 `bd1f40a` | 显式协议；公共飞控源时间、10 Hz 仿真网格、速度时间单位换算、参考机确定性顺延 |
| T1：K=2、1 倍 | 最终复核通过；42/42 已执行，41/42 质量合格，已 finalize | pilot、非训练；开发对照 |
| T2：K=2、2 倍 | 11/42 后规则暂停，5/11 合格；声明 2 倍实际约 1.21 倍，未通过 | 保留失败；不续跑；T3/T3+ 已取消 |
| T4：K=4、1 倍 | 42/42 已执行，41/42 合格，全部组门槛通过并 finalize | 最高已通过的 SITL 配置 |
| T5：K=6、1 倍 | 15/42 后规则暂停、自然排空，9/15 合格、6/15 时钟不可用；未 finalize | 失败收尾；T6 未准备、未运行；自动检查已暂停 |
| 快速动力学引擎 | M0 适配/来源索引与 M1 内核、双机快速通过完整数据链已本地落地；M0/M1 最终本地验收已通过；M2-00 已把 M0/M1 实现作为本地检查点提交 `0f7c42d` | **先核对 M0/M1 报告；M2-00 已通过最终审阅（`PASS`），M2-01 已获 Codex 最终 PASS、已提交 `16b7cb7`；M2-02B 新来源补充已获 PASS，M2-03 已执行并修复待审，M2-04 未开始，M2 飞行功能尚未实现；未校准、非训练** |

这里 \(K\) 是同时执行的多机任务数，不是单个任务的飞机数。上述运行采用非独占条件；后台 ChatGPT/Chrome/Edge 可以常驻，不能沿用旧说明的机器独占门槛。T1 在调大页面文件前运行，不能把各组资源统计当成完全相同环境下的因果实验。

SITL 备用推荐为 v0.6.1、K=4、1 倍、首批分片错峰 30 主机秒：整体 48.075819、稳态 46.483148 合格 episode/小时。按稳态任务吞吐外加实测错峰/收尾，900 任务约 18 小时 52 分，900 合格 episode 约 19 小时 32 分；内部换任务空档的未来累计、prepare/finalize 等未计入。这是历史测试外推，**不构成准备 r3 的安排，也不是新引擎性能**。

最新已提交代码的历史验收：[CI 38231824715](https://github.com/shy-UCAS/swarm-task-sim/actions/runs/38231824715)，367 项离线测试通过；来源为 T5 收尾回执。本次集成前本地基线也通过该清单，DR130 260/260、四个旧示例 4/4；新增数值、执行、产物与最终旧接口回归以 [M0/M1 报告](fast_dynamics_engine_m01_report.md)为准。全量历史集成测试含已记录的归档/旧断言依赖，见 [v0.6.1 实施报告](v0.6.1_time_report.md)，不能说全部测试均通过。

## 3. 必读顺序与代码地图

1. [根 README](../../README.md)、[根 CLAUDE](../../CLAUDE.md)、项目 [AGENTS](../AGENTS.md) 和 `.conda-env`。
2. 本文件、**[M0/M1 报告](fast_dynamics_engine_m01_report.md)**、[适配备忘](fast_dynamics_engine_adapter_memo.md)与 **[完整实现计划](fast_dynamics_engine_implementation_plan.md)**，尤其第 2–7 节的适配、时间、接口、数据与验收。
3. [系统架构](system_architecture_overview.md)、[现有数据契约](data_contract_v0.md)；明确“现有 SITL 已实现”与“新后端拟议”范围。
4. 遇到来源/门槛问题时查 [v0.6.1 实施报告](v0.6.1_time_report.md)、[最终验证报告](v0.6.1_time_validation_report.md) 的对应最终结论；其中旧运行前授权、历史停止点不作为当前任务。

| 目的 | 实际代码入口 | 接入注意 |
| --- | --- | --- |
| 任务、意图、航线 | `swarm_sim/registry.py`、`mission_v3.py`、`route_planning.py` | 复用编译输出，不复制规划结果作执行标签 |
| 采样与 family | `generation_v2.py`、`families.py` | 同源 family 的各意图、后端及参数变体保持同一 split |
| 既有执行语义 | `runner_v3.py`、`route_timing.py` | 阅读阶段含义；新建离线执行器，不启动 MAVLink/SITL |
| 时间与分析 | `time_contract.py`、`analysis_v3.py`、`truth.py` | 新引擎统一 tick，不伪造 FCU 参考机或被动时钟模型 |
| 语义与质量 | `mission_evaluation_v3.py`、`route_windows.py`、`quality.py`、`protocol.py` | 几何规则可适配；FCU/SIM 来源和固件门禁需要独立后端契约 |
| 数据、描述与加载 | `dataset.py`、`episode_loader.py`、`observer_facts_v0.py`、`language_v0.py` | 当前输入六维 ENU 位置/速度；不能只换同名 CSV 绕过协议检查 |

代码路径在上表后五行均相对 `swarm_sim/`。现已新增 `swarm_sim/fast_dynamics/`：契约/整数时钟、受限 jerk 平动、速度响应、参考/实际阶段执行、理想观测及产物/语义适配；本地完整链入口为 `scripts/run_fast_dynamics.py`。源任务固定为 `tests/fixtures/fast_dynamics/rapid_passage_0000_v00.json`，来源及哈希见适配备忘。

## 4. 首包实施范围：M0 + M1

以下保留首包实施要求，代码已按此范围落地；最终测试和未完成项由 M0/M1 报告收口。下一包 M2 扩任务覆盖，不重复重建首包：

1. M0 先写短设计备忘和产物适配表，逐项查明现有输入、消费者、时间/单位、来源门禁和最小改动；冻结首版后端身份、整数时钟、状态字段与配置。新 `sim_clock` 不制造 FCU 恒等时钟；新增契约，旧协议保持原解释。新网格采用 \([0,T)\)，帧数 \(\lceil10T\rceil\)，结束时刻独立保存；旧 SITL 端点规则不改。
2. 按计划第 9 节实现实际需要的最小模块；首选简单速度响应与受限 jerk 的平动模型，用测试决定是否增加位置反馈。未用到的执行器/刚体/IMU 只声明替换边界，不建立空插件框架。
3. 实现状态 \((\mathbf p,\mathbf v,\mathbf a)\)、加速度/jerk 约束及常 jerk 步内积分。不要靠直接裁剪位置/速度制造一致性，不伪造姿态、比力或电机真值。
4. 用直线起停、有限半径转弯和驻留构造单机用例；完成解析轨迹、约束、网格边界、重复性及减半步长测试。首版从空中任务开始，显式声明不包含真实起降过程。
5. M1b 固定选取一个既有双机快速通过任务，保留输入哈希，补齐该例需要的实际阶段执行与事件；通过新协议适配走完分析→导出→审计→事实/描述→加载。至少一个合格样本有完整描述，另测失败/未知路径，不伪造标签或起降/固件证据。这不代表三意图全覆盖。
6. 对公共协议/loader 的最小分派改动，在本阶段执行新来源检查及旧示例、DR130 等适用回归；区分既有历史测试失败，不改冻结证据。保存配置、种子、模型版本、未提交源码内容哈希及测试/基准。100 倍实时、10 倍完整吞吐仍只是目标。

首包完成条件是**单机数值证据 + 最小双机端到端样本**。目前确定性内核及执行/来源测试已落地，减半步长的公共采样位置/速度 2 cm / 2 cm/s 工程目标已通过；最小双机链产生可加载观测和四条描述，精确帧数、时长及最终测试数量见报告。上述结果不证明 SITL 真实性、生产吞吐或训练资格。下一包 M2 扩到三意图四飞法及完整多机时序；M3 做无新增噪声的基线、分步校准并冻结参数/验收；M4 增加共享风场、相关观测误差、强度扫描、两种输出模式及先小后大的 pilot；M5 执行未见 family 的独立验收。工作量规划约 12–20 人日，未实测。按里程碑记录范围和验证，不通过 GitHub 发布推进。

关键验收约束：T1/T4 是同源 42 任务、14 family，先合并来源再划分，统一作开发对照；路径按阶段/圈次内弧长比较，时间与多机间距另在原公共轴比较。98% 标签一致、时长 5% 等是外部计划的候选值，不自动采用；全任务合格率与边界任务差异一起报告，最终测试前冻结标准。风/观测 profile 在 family 内共享，RNG 不由 intent 选择，测量值不要求跨不同轨迹相同。

带标签模式先贯通；M4 的无标注预训练模式可省去描述等计算，但必须有独立能力声明、质量和 family/split，不把未计算标签写成通过。两种模式吞吐分别报告。完整定义以融合计划 `3–7 为准。

未来升级遵循 `Reference → Controller → Actuator → Plant → Observer` 的分层；加速度请求、机体力/力矩、电机指令分别定义能力。通用状态视图保留位置/速度、可选姿态/角速度/比力和来源；内部状态维数可变化。六自由度、传感器闭环、C++ 加速均按研究需求和 profile 证据逐项增加。

## 5. 本机环境与检查命令

Windows 使用 PowerShell 7；已验证路径为 `C:/Users/shy/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe`。新窗口先核对版本和目录：

```powershell
$PSVersionTable.PSVersion
Set-Location 'F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-dev'
git status --short
git log -1 --oneline
Set-Location 'Multi-UAV SimpleGC'
$engineEnv = (Get-Content -LiteralPath '.conda-env' -Raw).Trim()
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n $engineEnv --no-capture-output python -B -c "import sys; print(sys.executable); print(sys.version)"
```

当前 `.conda-env` 为 `llm`，本地验证使用 Python 3.12.3 / NumPy 2.5.3。`requirements.txt` 现声明 `pymavlink==2.4.50` 和 `numpy==2.5.3`；本机复用该环境已可用的 NumPy，不切到 base 或改用另一工程环境。

首包完整链入口（**M2-01 起输出只能落在仓库外**；不启动 SITL）：

```powershell
$engineEnv = (Get-Content -LiteralPath '.conda-env' -Raw).Trim()
$fastAttemptOutput = 'F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m1_smoke'
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n $engineEnv --no-capture-output python -B scripts/run_fast_dynamics.py tests/fixtures/fast_dynamics/rapid_passage_0000_v00.json --output-root $fastAttemptOutput
```

入口拒绝仓库内输出、已存在的 attempt 与经联接越界的路径，并在创建任何产物前报错；失败 attempt 保留，不覆盖旧证据。输出根缺省为仓库同级的 `SwarmData/fast_dynamics`，可用 `--output-root` 或环境变量 `FAST_DYNAMICS_OUTPUT_ROOT` 覆盖；省略 `--output` 时自动取带 UTC 时间戳的新目录（`run_fast_dynamics.py`、`verify_fast_dynamics_m01.py`、`benchmark_fast_dynamics.py` 一致）。可用 `--config <JSON>` 提供严格配置，七组为 `engine`、`vehicle_profile`、`controller`、`observation`、`environment`、`execution`、`quality`；未知字段报错。M1 只接受双机单段 `line_abreast` 快速通过任务，观察与环境分别限定 `ideal` / `zero_disturbance`。`scripts/benchmark_fast_dynamics.py` 是独立性能检查入口；100 倍等目标不能从单个样本耗时宣称达成。

已有离线冒烟入口（不启动 SITL）：

```powershell
$env:PYTHONPATH = 'tests'
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n $engineEnv --no-capture-output python -B -m unittest test_publication_runtime test_v061_time_axis test_v061_protocol
```

完整的无归档依赖模块清单见 [unit-tests.yml](../../.github/workflows/unit-tests.yml)，可在本地使用其 unittest 清单，不执行其中 fetch/push 或安装步骤来冒充测试。新增内核先跑有意义的定向测试；触及公共协议/loader/语义时再覆盖对应旧回归。DR130 与 v0.5 示例按已有验证脚本和只读输入执行，不能为修复历史测试重造旧数据。

## 6. 证据、输出与已知问题

- v0.5 归档：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation/`，只读。
- v0.6/v0.6.1 批次：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/parallel_batch/`，T1/T4 的已导出数据和 T2/T5 的失败尝试均保留原状。各组 ID 为 `v061_T1_k2_s1_seed2026100812`、`v061_T2_k2_s2_seed2026100812`、`v061_T4_k4_s1_seed2026100812`、`v061_T5_k6_s1_seed2026100812`。
- 只读复核入口：`SwarmData/agent_work/v061_validation/`。T5 收尾回执在其 `v061_T5_k6_s1_seed2026100812/T5_FINAL_RECEIPT.json`；监测终态在 `followup_scale_20261012_v1/monitoring_mode.json`，为 `CLOSED_T5_FAIL_T6_NOT_RUN`、自动检查 `PAUSED`。旧续接脚本不再作为开发入口。
- 新引擎轻量测试写入全新的临时目录。**M2-01 已把 M1 证据树迁移到仓库外**：`SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/`（356 文件、30,216,091 字节逐字节核验；仓库只保留 18 项阶段级汇总/工具加小型 [`migration_index.json`](../verification/fast_dynamics_m01/migration_index.json)）。逐文件映射与哈希见该归档根下的 `relocation_index.json`；新增样本、dataset、原始日志、基准与失败证据一律写外部输出根的全新 attempt，仓库内输出会被入口拒绝。不得覆盖现有 batch、分析、导出或语言目录。
- `Simulation-dev-wip` 保存另一会话工作，不作为本次修改范围。新窗口若发现真实 SITL 批次又在运行，应先核对其保护范围；本交接不授权边跑旧批次边改受保护源码。
- P2：FCU 速度与位置差分约 −1.8% 至 −2.1% 残差、时间修正尚余约 0.3–0.4 个百分点未解释，见数据契约。不要将这些量硬编码为新引擎机体阻力或速度缩放。
- P3：检查 SIM 通道是否同样存在尺度差；评估 Linux/WSL2 上的 SITL 稳定加速。两项仍是待办，不与本地 M0/M1 捆绑实施。
- 已反复查看的 42 个配对任务只能作开发对照；最终跨引擎泛化测试需另外冻结未参与校准的 family。

## 7. 实施登记及下一窗口提示词

| 阶段 | 当前状态 | 后续需登记 |
| --- | --- | --- |
| 评估与融合修订 r2 | 已完成；原计划已随 M0/M1 检查点提交，当前进度补注尚未提交 | Claude 方案借鉴及纠错已写入主计划，入口已同步 |
| M0 / M1 | 已本地实现；M0/M1 最终本地验收已通过 | [适配备忘](fast_dynamics_engine_adapter_memo.md)、[最终实施报告](fast_dynamics_engine_m01_report.md)中的数值/完整链/回归结果；证据树已迁移到 `SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/`，仓库内只留 18 项汇总/工具与[迁移索引](../verification/fast_dynamics_m01/migration_index.json) |
| M2-00 | 已建立本地检查点 `0f7c42d`；记录经 `attempt_03_record_fix` 修正后 Codex 最终 `PASS` | [M2-00 阶段报告](fast_dynamics_m2/M2-00_report.md)、[最终审阅回执](fast_dynamics_m2/M2-00_review_03.md) |
| M2-01 | 已执行：M1 证据迁移、外部输出根约束与路径保护；**Codex 最终 PASS**，已提交 `16b7cb7` | [M2-01 阶段报告](fast_dynamics_m2/M2-01_report.md)、[摘要](../verification/fast_dynamics_m2/M2-01_summary.json) |
| M2-02 | 历史修复结论 BLOCKED（旧来源合格候选 0），保留原记录 | [修复报告](fast_dynamics_m2/M2-02_report.md)、[复核回执](fast_dynamics_m2/M2-02_review_02.md) |
| M2-02B | 用户授权新来源，输入冻结与复核 PASS；校准/盲测各 71 接纳 family | [报告](fast_dynamics_m2/M2-02B_report.md)、[回执](fast_dynamics_m2/M2-02B_review.md) |
| M2-03 | 设计与规格已执行并由 Codex 修复；静态交叉核查完成，AWAITING_REVIEW；M2-04 未开始 | [修复报告](fast_dynamics_m2/M2-03_report.md)、[设计](fast_dynamics_m2/M2-03_design.md)、[测试规格](fast_dynamics_m2/M2-03_test_spec.md) |
| M3 / M4 / M5 | 未开始 | 依次为确定性校准、扰动与生产试验、独立验收 |

M2 采用“DeepSeek 分阶段执行、Codex 逐轮审阅”的流程，使用 [M2 分阶段实施与审阅指南](fast_dynamics_engine_m2_staged_guide.md)。**当前进度：M2-00 已建立本地检查点 `0f7c42d` 并通过最终审阅（`PASS`）；M2-01 已执行完证据迁移与外部输出约束，已获 Codex 最终 `PASS`；M2-02B 新来源补充已获 PASS，M2-03 已执行并完成本轮设计修复待审，M2-04 及后续未开始，M2 飞行功能尚未实现。** 由用户逐次启动，完成一个小阶段后停止审阅。指南中的本地检查点提交、外部证据迁移和留出登记，仅在对应阶段被用户明确启动后执行。M2-01 之后的输出一律落在仓库外：入口拒绝仓库内路径、已存在 attempt 与联接越界。

以下是原有连续开发提示词的历史记录；采用上述分阶段流程时，以指南及用户指定的当前阶段为准，不使用本段自动推进 M2：

> 在 `F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-dev` 开发。先读根 README、CLAUDE、项目 AGENTS、`Multi-UAV SimpleGC/docs/fast_dynamics_engine_kickoff.md`、`docs/fast_dynamics_engine_m01_report.md` 和完整实现计划融合修订版 r2。保留未提交实现、测试、文档与证据，先核对 M0/M1 最终验收和未完成项，再推进下一包 M2 的三意图四飞法、2/3/4 机和完整多机时序，沿用首包完整数据链。只做本地实现和验证，不提交、推送或打标签；不启动 SITL、不续跑 T2/T5、不运行 T6、不准备 r3、不改历史数据。新后端显式版本化，按 family 合并来源防泄漏；校准、训练资格和性能目标不当已验收结果。


2026-10-12 M2-01 历史收口补注：M2-01 最后 ID 前置校验已由 Codex 完成，针对性检查 66/66 通过；M2-01 已获 PASS 并保存到 `16b7cb7`；原 M2-02 来源阻塞已由获准的 M2-02B 新来源补充解除，该历史节点的下一步为 M2-03 设计（现已执行并修复待审，以头部为准）。见 [最终回执](fast_dynamics_m2/M2-01_review_03.md)与[M2-02 任务计划](fast_dynamics_m2/M2-02_instruction.md)。
