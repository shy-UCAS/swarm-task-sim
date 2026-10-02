# Multi-UAV SimpleGC

基于本机 ArduCopter SITL 的多无人机实验框架。当前代码版本为 **0.4.0-dev（阶段 0–1 验收完成）**。既有 v1/v2 支持 1～6 架飞机独立启动、共享矩形区域任务、分阶段并行执行、驻留确认、自动降落，以及 SIM 真值、时间诊断和按任务族组织的数据集。v3 已接通按语义阶段连续执行、逐运行参数与固件核验、双通道轨迹窗口及分析。

## v0.4 里程碑

WP-S 已由用户确认 GO，独立记录见 [GO 确认记录](docs/v04_spike_go_confirmation.json)，原 UNKNOWN 报告保持原样。WP-G G1–G4 已获用户确认，历史结果见 [WP-G 报告](docs/v04_wp_g_milestone.md)。WP-E 实现和原离线验收见 [WP-E 报告](docs/v04_wp_e_milestone.md)。V1 获确认后，已按授权完成 V06 的 10 场景试生产。

当前状态：离线测试 **430/430** 通过；V06 **10/10** 完成且质量合格，数据集导出、审计、加载及 v0.3 分布对照均通过。本轮预算 10/10，无重试；阶段 0–1 累计 SITL 为 19 次。最终结论、终点驻留与 arrival_s 限制、证据和停止边界见 [阶段 0–1 最终报告](docs/v0.4_stage01_implementation_and_verification.md)。现停止，未开始阶段 2。

V1 的 AC4 使用版本化相对名义进度判据，原绝对偏差保留作诊断；V05 保持受控失败状态。完整对照见 [AC4 v2 / V1 里程碑](docs/v04_ac4_v2_milestone.md)，定义见 [AC4 v2 说明](docs/ac4_timing_v2.md)。原 [V1 停止报告](docs/v04_v1_milestone.md)、[首次续跑停止报告](docs/v04_v1_resume_milestone.md)及其运行、台账保持原样；τ、名义模型、间距检查和飞控参数未调整。V06 独立 profile 为 [recon_pilot_v04_v06.json](generation_profiles/recon_pilot_v04_v06.json)。

v3 已支持严格任务规范化、注册表、按物理场景生成 family、profile v2、两级样本资格、导出/加载和通用审计。生产意图仍只有侦察。观测分析采用 `exact_duplicate_drop_v1 + full_stream_strict_v1`，相关产物绑定四个处理版本；旧处理器和默认质量策略保留。

```powershell
# 纯计划检查，不启动 SITL；输出路径必须不存在。
conda run -n llm --no-capture-output python main.py plan missions/v3/recon_shared_3uav_barrier.json --output tmp_v04/my_v3_barrier.json
conda run -n llm --no-capture-output python main.py validate tmp_v04/my_v3_barrier.json
conda run -n llm --no-capture-output python main.py generate generation_profiles/recon_pilot_v04.json --output tmp_v04/my_v3_generation
```

`semantic_phase_route_v1` 编译为 schema 2 航线场景，每条航线上限 100 点，去除小于 0.05 m 的航段；时间感知间距检查及容忍量写入规划元数据。v3 运行前核对已确认 WP-S 的固件和参数模板指纹，并逐机读回完整参数。固件或模板变化须重新执行 WP-S。接口见 [连续航线](docs/continuous_route_schema_v1.md)、[TaskSpec v3](docs/task_spec_v3.md)、[协议与观测](docs/v04_protocol_v3.md)、[审计](docs/v04_dataset_audit_interface.md)、[执行诊断](docs/execution_metrics_v1.md)和[计划补充](docs/v04_stage01_plan_addendum.md)。

新任务接口、规划边界和命令见 [TaskSpec v2 说明](docs/task_spec_v2.md)；本轮实际测试、实跑、失败与限制见 [v0.3 实现与验证记录](docs/v0.3_implementation_and_verification.md)。示例可编译不等于任意参数配置均已实测通过。

数值质量策略沿用 [v0.2.2补丁说明.md](v0.2.2补丁说明.md)。旧任务架构见 [第二轮迭代方案与验证说明.md](第二轮迭代方案与验证说明.md)，其中实跑结果保留为 0.2.0 的历史记录。[改进方案与验证说明.md](改进方案与验证说明.md) 是 0.1 版记录；复制时保留的 `框架架构与仿真能力说明.md` 描述改造前版本。

## v0.3 共享区域任务

### 桌面回放与计划预览

```powershell
conda run -n llm --no-capture-output python replay.py
```

打开已有运行即可查看责任区、计划路线、实际轨迹、高度曲线和执行事件，支持时间轴、暂停及倍速。也可单独打开任务 JSON 预览计划。该界面只读本机记录，不启动 SITL。操作与数据含义见 [回放界面说明](docs/replay_viewer.md)。

### 任务执行

一份 TaskSpec v2 描述一个公共区域，经等宽条带分区和单调身份分配，形成各机进入、往复扫描与可选返回路线；仍使用现有执行场景 schema 1 和最多 100 个 AUTO 阶段。真实覆盖以有效服务窗口中的实际轨迹在公共网格上的并集计算，SIM 为主判据，FCU 独立复核，失败与未知结果分别保存。

```powershell
$EnvName = (Get-Content .conda-env -Raw).Trim()
conda run -n $EnvName --no-capture-output python main.py plan missions/recon_smoke_3uav.json --output scenarios/my_recon_v03.json
conda run -n $EnvName --no-capture-output python main.py validate scenarios/my_recon_v03.json
conda run -n $EnvName --no-capture-output python main.py run scenarios/my_recon_v03.json --quality-policy quality_policies/default_v022.json

# 仅生成和预检；此命令不启动 SITL。
conda run -n $EnvName --no-capture-output python main.py generate generation_profiles/recon_pilot_v03.json --output generated/my_recon_v03
```

执行小批量任务清单使用 `scripts/run_mission_list.py --max-runs ...`；冻结输入、逐次 attempt、失败和恢复证据均保留。`load_episode()` 只将 `observations.csv` 的六个 ENU 位置/速度列加载为模型输入，标签单独返回。`inspect-dataset` 提供具有明确分母的数据体检，不报告单类别分类准确率。

当前范围是一种理想几何区域观察任务、固定高度和轴对齐矩形，非空禁区明确拒绝。v2 上传和起飞保持使用 BRAKE，AUTO 航点控制保持到几何驻留确认结束；v1 的 LOITER 行为保留。具体规则和资格协议见 TaskSpec v2 文档。

## 0.2 任务数据生成

```powershell
# 三机点访问、矩形巡逻、理想几何覆盖扫描
conda run -n llm --no-capture-output python main.py run scenarios/task_point_visit_3uav.json
conda run -n llm --no-capture-output python main.py run scenarios/task_patrol_3uav.json
conda run -n llm --no-capture-output python main.py run scenarios/task_coverage_3uav.json

# TaskSpec -> 新场景文件；输出路径应不存在
conda run -n llm --no-capture-output python main.py plan tasks/patrol_3uav.json --output scenarios/my_patrol.json
```

任务运行结束会自动导出版本化分析：`observations.csv`、`truth.csv`、`clock_models.json`、`labels.json`、`quality.json` 等。`analyze <run目录>` 可重分析历史数据；`dataset <多个run目录> --output <新目录>` 按 `family_id` 整组划分并保留失败样本。标签、数据质量和飞行是否完整结束分别记录。任务模式的退出成功要求通过 `benchmark_eligible` 门槛。

0.2.2 将时钟残差划分为 `strict`（不超过 20 ms）、`acceptable`（不超过 50 ms）、`failed` 和 `unknown`。默认合格集接受前两档，但仍要求任务、数据、真值、执行状态和间距检查全部通过；`strict_benchmark_eligible` 提供更严格的子集。这些残差不是绝对同步精度保证。

`run/batch/analyze` 支持 `--quality-policy quality_policies/default_v022.json`。策略内容及 SHA256 随分析和数据集保存。旧分析缺少策略信息时，需要显式重新分析；不同策略的结果不能混合导出。重新分析会新建目录并更新 `analysis_latest.json`，保留原始运行元数据和旧分析。直接运行 `analyze` 使用当前默认策略，复现实验时应明确指定策略文件。

时钟处理是被动估计，参考仍为事件驱动 AUTO 航点。观测是已知身份的合作式飞控遥测，几何覆盖不代表真实相机或雷达探测。

## 环境

项目 `.conda-env` 指定 `llm`。当前验证环境为 Windows、Python 3.12.3、pymavlink 2.4.50。SITL EXE 和 DLL 已随工程提供；本次改造没有安装依赖。`requirements.txt` 声明 pymavlink，`requirements-dev.txt` 额外提供可选的 pytest；标准库 `unittest` 可直接运行全部测试。当前项目验证过的路径不要求直接安装 NumPy。

仓库已配置 Windows / Python 3.12 的 GitHub Actions 逻辑测试，尚未验证远端执行结果；它不启动真实 SITL。

## 快速开始

在本工程目录的 PowerShell 7 中执行：

```powershell
conda run -n llm --no-capture-output python main.py validate scenarios/demo_2uav.json
conda run -n llm --no-capture-output python main.py run scenarios/demo_2uav.json
```

无需先运行旧版 `ConsoleApp1.exe`，新入口会管理自己的 SITL 进程。`swarm.py` 是同等入口；默认端口从 19100 起，每架间隔 10。每次运行使用全新的目录和参数状态，结束后回收本次启动的进程。

```powershell
# 单机或六机验证
conda run -n llm --no-capture-output python main.py run scenarios/demo_1uav.json
conda run -n llm --no-capture-output python main.py run scenarios/demo_6uav.json

# 顺序重复实验，输出不会覆盖
conda run -n llm --no-capture-output python main.py batch scenarios/demo_2uav.json --repeat 2

# 只检查旧轨迹，不执行，不擅自将时间索引解释成秒
conda run -n llm --no-capture-output python main.py audit loadData/uav_trajectories_persistent_20260213_164652.json

# 单元与回归测试
conda run -n llm --no-capture-output python -m unittest discover -s tests -v
```

CLI 退出码：`run/batch` 的 0 表示通过门槛，1 表示执行、质量或任务验证未通过；输入/配置错误通常为 2。无 TaskSpec 的旧航点场景沿用基础门槛：完整结束、各机有效位置覆盖率至少 99%、未发现接近风险。有 TaskSpec 的任务还要求真值覆盖、时钟诊断、真值间距与任务语义检查通过。v2 还要求双通道语义一致和生命周期资源约束通过；不同标签/资格协议不能混合导出。`analyze/dataset` 返回 0 仅表示分析/导出操作成功，样本是否合格需读取结果。

## 场景定义

参考 `scenarios/demo_2uav.json`。`origin` 包含公共经纬度与海拔基准，所有 `east_m/north_m/up_m` 使用该公共坐标系。所有飞机在相同地面海拔生成，起飞后才释放第一航段。

- `vehicles`：独立 ID、MAVLink sysid、初始东西/南北位置及朝向。
- `phases`：每阶段必须为每架飞机配置一个目标点；全部完成后进入下一阶段。
- `speed_m_s`：目标航行速度，第一版限制 0.5～15 m/s，不是到达时刻约束。
- `hold_s`：到达航点后的等待时长。
- `takeoff_alt_m`：准备阶段的起飞相对高度。
- `timeout_s`：从运行开始计时的整个场景超时，包含启动与降落。
- `max_gap_s`：过期遥测判断和离线插值的最大间隔。
- `min_separation_m`：初始点预检及飞行阶段离线距离检查阈值。

支持区域被限制在原点东/北各 ±2000 m；坐标换算使用局部 WGS84 线性近似，不用于跨区域精密测量。运行倍速固定为 1。旧轨迹文件不能直接作为新场景使用，需要确认时间单位、处理跳点并转换为本场景结构。

## 输出

每次运行在 `runs/<scenario_id>_<UTC时间>_<随机后缀>/` 下输出：

| 文件 | 内容 |
|---|---|
| `scenario.json` | 验证并补全默认值后的场景 |
| `metadata.json` | 执行状态、参数、版本、源码/固件摘要、端口、PID、阶段发送偏差、进程回收结果 |
| `events.jsonl` | 连接、准备、阶段释放、完成、降落和失败事件 |
| `raw/<agent>.jsonl` | 原始 MAVLink 消息、源时间字段和高精度本机接收时间 |
| `samples.csv` | 按共同主机时间采样的多机位置、速度、姿态、消息年龄、有效标记和 `position_invalid_reason` |
| `processed.csv` | 飞行阶段统一采样的 ENU 位置/速度，长表格式和缺失掩码 |
| `quality.json` | 覆盖率、最近距离、接近风险、是否满足基础质量门槛 |
| `sitl/<agent>/` | 独立参数、日志和持久化状态 |

`analysis_latest.json` 指向最新 `analysis_v<代码版本>_*` 目录，其 `quality.json` 才是本次离线分析的完整质量报告。它包含时钟分级、默认/严格合格标记，以及按原始消息统计的异常原因（全程和评估窗口分别统计）。三个观测出口使用相同的内容过滤规则；离线插值不会跨过被拒绝的样本或超长缺口。v2 还导出共享地图、分工、语义窗口、双通道验证和生命周期约束。运行根目录的 `quality.json` 是运行时结果，历史重分析不会回写它。

失败运行保留已有原始数据和错误信息。准备阶段失败时不生成 `processed.csv`；任务阶段全部完成、但后续降落失败时可以导出已完成的飞行窗口，`usable` 仍为 false。

## 兼容性与边界

`main.py` 已改为上述子命令入口。旧单机批量执行仍可通过 `python flyControl.py` 显式调用，保留旧 JSON 格式，但不具备新的多机保障和质量报告。

阶段同步不是物理仿真锁步；主机时间重采样不是飞控源时钟同步；独立实例不包含共享碰撞动力学、气流交互或在线避碰。不要把高层队形/意图标签直接视为已实现的闭环控制。

## v0.4 WP-S：连续 AUTO 航线先行试验

`scripts/spike_continuous_route.py` 是独立试验入口，复用当前起飞、BRAKE 上传和 AUTO 执行。它按进近、整段侦察、返航三个阶段运行，读取固件和完整参数表，并保存原始 MAVLink 与 SIM 日志。当前正式 TaskSpec v1/v2、执行器和数据协议保持不变；试验结果不导出为正式数据集。

```powershell
# 启动一次本机三机试验；WP-S 要求两次重复，最多三次，禁止无界重试
conda run -n llm --no-capture-output python scripts/spike_continuous_route.py

# 只分析事先制作的 WP-S 复核副本，不启动 SITL；复制步骤见 WP-S 报告
conda run -n llm --no-capture-output python scripts/spike_continuous_route.py --analyze-only tmp_v04/spike_review_01
```

新证据保存在 `runs/spike_v04_*`。其中 `scenario.json` 是未改动的 v2 参考场景，实际执行航线以 `spike_plan.json` 为准；`spike_metrics.json` 提供 S-a 至 S-g 和单次 `criteria/verdict`，`waypoint_events.json/csv` 保存全部原始到点事件，`spike_waypoints.csv` 给出逐航点结果。两次重复的合并判定见 [WP-S 报告](docs/v04_spike_continuous_route.md)，基线核对见 [M0 报告](docs/v04_baseline_check.md)。

试验 CLI 的退出码 0 表示运行及离线分析完成，1 表示运行失败，2 表示离线分析失败；**GO/NO-GO 必须读取指标报告，不能以退出码 0 替代**。覆盖与最近距离使用被动源时钟对齐，其残差不代表绝对同步精度。WP-S、WP-G 和 V1 已获用户确认；V06 已完成 10 次试生产，阶段 0–1 的最终结论见上方报告。
