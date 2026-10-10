# SwarmTaskSim：工程进度与新会话交接

**请新会话先读本文件。v0.5 已完成并冻结；v0.6 三意图实现、两路 pilot 与暂停 B 复核已完成，正式生产 r1 在 296/900 个任务后因台账持久化失败而规则停止，未收尾，保留为证据；用户已决定修复持久化后以同一 profile、同一种子另建 r2 批次从头运行，r2 准备中。后续开发在 `Simulation-dev`，v0.5 完整归档在原 `Simulation`，新增大型数据在仓库外 `SwarmData`。没有等待自动执行或自动续跑的仿真任务。**

本文件最后核对日期为 **2026-10-10**，核对基线为 `main=037ed7e`，并只读核对了 pilot30 与正式生产台账及现存清单。它记录项目当前状态、能力和资料入口，不代替源码、规则或原始证据。文中本机绝对路径仅适用于原开发电脑；其他电脑需要安装环境，并另行取得完整数据归档。

## 1. 工程已经做到哪一步

本项目通过 ArduCopter SITL 生成多无人机任务轨迹、质量标记、双通道语义标签和中文描述，供算法链路开发使用。包内历史版本字符串仍为 `0.5.0-dev`，不代表当前任务协议或开发里程碑：代码已支持 v0.6 三意图协议，v0.5 生产数据已完成并冻结，v0.6 正式生产数据集尚未形成。

| 阶段 | 已完成内容 | 当前状态 |
|---|---|---|
| 早期框架与 v0.2 | 单机/多机执行、点访问、巡逻、覆盖、轨迹记录与质量检查 | 代码及历史说明保留 |
| v0.3–v0.4 | 共享区域分工、TaskSpec、连续航线、family 划分、双通道验证、执行诊断及离线回放 | 作为现有框架基础；旧报告是对应阶段记录 |
| v0.5 | 侦察与边界巡逻双意图；验证、20 次试生产、240 次批量运行；导出、审计、描述、加载验收 | 已完成，停在暂停 2，已冻结 |
| Git 发布与迁移 | 精简代码发布，补齐运行基线，独立目录验证，PR 合并及建立新开发目录 | 已完成；[PR #1](https://github.com/shy-UCAS/swarm-task-sim/pull/1) |
| v0.6 实现与 pilot | 三意图协议、四种生产飞法、整族接受、两路并行；20 任务与 30 任务 pilot 已收尾并复核；快速通过阈值冻结，事实层 v06b 修复已提交并通过离线验收 | pilot30 登记 30/30、质量合格 29/30、语义一致 29/30，含一次真实人工暂停续跑；[pilot 报告及暂停 B 复核](Multi-UAV%20SimpleGC/docs/v0.6_pilot_report.md)；[pilot20 报告](Multi-UAV%20SimpleGC/docs/v0.6_parallel_pilot_report.md) |
| v0.6 正式生产 | `v06_production900_seed2026100812` 已准备并执行两段，期间完成一次人工暂停续跑 | 296/900 个不同任务已有终态记录（completed 288、failed 8）；台账持久化 `WinError 5` 触发规则停止；未完成、未 finalize、未导出，停在暂停 C；[生产停止报告](Multi-UAV%20SimpleGC/docs/v0.6_production_stop_01.md) |

v0.6 暂停 1 当时的验收记录：新增测试 63/63、CI 离线清单 204/204 通过；全量 721/726 通过，5 项历史证据依赖错误在原始基线复现。文件行数、八类测试、未解决项及数据目录示例见 [暂停 1 报告](Multi-UAV%20SimpleGC/docs/v0.6_parallel_pause1_report.md)。

历史沿革：分片暂停 1 已复核通过，当时补充测试后并行测试 65/65 通过；随后路径守卫修复又扩充测试，上述数字是各阶段历史验收记录，不是当前代码的测试总数。r1 摸底停止结论见[历史报告](Multi-UAV%20SimpleGC/docs/v0.6_intent_registry_stop_report.md)；r2 诊断与 DR130 金标准在 `8369df9` 提交，[摘要](Multi-UAV%20SimpleGC/verification/v06_prechecks_20261007/README.md)在 `21f427a` 归档。取消的是当时提出的意图模块化重构，不是撤销当前已有注册表或三意图能力。pilot20 使用 10 family／20 任务／2 路、种子 `2026100701`，已收尾：完成 20/20、质量合格 20/20、语义一致 19/20；用户据此采用两路。其执行方式差异见[报告](Multi-UAV%20SimpleGC/docs/v0.6_parallel_pilot_report.md)，该批次不用于训练。

后续已执行进展：A2 按独立飞法子流及整族接受规则完成 300 family／900 任务离线规划（清单规划拒绝 0/900），见[A2 报告](Multi-UAV%20SimpleGC/docs/v0.6_pauseA2_report.md)。pilot30 使用种子 `2026100811`、`v0.6-pauseA3`／`0dffcd8`，登记 30/30，质量与语义一致均为 29/30；最终保留 30 个 episode，29 个有描述，共 116 条。暂停 B 冻结快速通过六项阈值，事实层累计转向修复在 `a345f27` 提交，12/12 离线验收通过；旧 pilot 文件与判定未改写。正式生产使用种子 `2026100812`、`v0.6-pilot`／`762a303`，296 次尝试、无重试；质量合格 287/296、语义一致 289/296、时钟不可用 1/296。因 `control.json.tmp` 替换 `control.json` 被拒绝而规则停止，604 个计划任务未运行。已有逐尝试证据保留，但不存在完成的正式生产数据集或描述层；不得直接 resume、清除停止原因或补飞。用户复核后已决定：修复持久化缺陷后另建 r2 批次重跑，见第 8 节。

本次文档核对的开发 HEAD 为 **`main=037ed7e`**（正式生产停止报告提交）；生产运行基线为 **`v0.6-pilot=762a303a0482725fc794eef093f023549e3f2712`**，pilot30 实际运行基线为 `v0.6-pauseA3=0dffcd8`。这三个身份不能混同；尚未打 `v0.6-production` 标签。并行开发 [PR #2](https://github.com/shy-UCAS/swarm-task-sim/pull/2) 已合并。后续以 `git log -1`、标签指向和工作区状态为准，不把历史测试或 CI 记录当作当前 HEAD 的重新验收。

v0.5 的最终计数如下，**260 次只包含试生产与正式批量，不包含更早的开发/验证运行**：

| 范围 | 完成运行 | 质量合格 | 两种意图均合格的场景 |
|---|---:|---:|---:|
| 试生产 PP01–PP20 | 20/20 | 20/20 | 10/10 |
| 批量 B001–B240 | 240/240 | 232/240 | 112/120 |
| 合计 | 260/260 | 252/260（96.92%） | 122/130（93.85%） |

- 全量导出保留 **260 个 episode**，其中 **8/260 质量不合格**，保留原判并标记 `episode_quality_eligible=false`；没有通过删掉失败记录来提高统计结果。
- 中文描述覆盖 **252/252 个合格且语义一致的 episode**，共 **1,008 条描述**；跳过的 8 个 episode 与质量不合格记录一致。
- 最终 11/11 项验收门通过；审计未发现 family 跨集合泄漏或未解释问题。
- 迁移时，本机独立目录及新开发目录各通过 **141/141 项离线测试**，固件/参数预检、两种意图的规划校验、4/4 个示例加载通过；GitHub 分支、PR、合并后 main 的三次 CI 均成功。此结果不是“全套历史测试通过”或“另一台物理电脑已实飞”。

计数和异常依据：[v0.5 最终报告](Multi-UAV%20SimpleGC/docs/v0.5_final_report.md)、[最终验收](Multi-UAV%20SimpleGC/verification/v05_batch_20261002/acceptance.json)、[最终台账](Multi-UAV%20SimpleGC/verification/v05_batch_20261002/control.json)。

## 2. 当前框架能实现什么

主要流程是：**任务/场景配置 → 规划路线 → 本机 SITL 执行 → 观测与真值分析 → 标签/质量/描述 → episode 加载**。

| 能力 | 当前实现与边界 |
|---|---|
| 多机任务执行 | 框架已有 1～6 机运行能力；当前三意图 profile 使用 2/3/4 机。管理独立 SITL 进程、任务上传、起飞、执行、降落及清理 |
| 三意图与四种生产飞法 | 侦察 `equal_strip_lawnmower`／`equal_strip_rectangular_spiral`；巡逻 `staggered_same_loop`；快速通过 `line_abreast`。同一 family 配对生成三个意图；斜队 `echelon` 未达到准入门槛，不生产登记 |
| 任务与场景生成 | 支持 TaskSpec v3 编译、按 profile/种子采样；先独立抽定各意图飞法，三者都规划通过才整族发布；A2 清单为 300 family／900 个有效规划 |
| 双通道判定 | 分别依据 SIM 真值和 FCU 观测核验任务语义，记录成功、失败、未知及两通道一致性 |
| 质量与执行诊断 | 检查时钟、有效观测、真值间距、机载任务参数；输出有序路线进度、圈数、时序偏差、过点速度等 |
| 分片并行 | 按 family 分片，独立目录与端口、全局停止与预算、人工暂停排空及续跑、统一收尾；pilot20、pilot30 已收尾，正式生产两路运行 296 个任务后规则停止；K=2 指两个多机任务并行 |
| 数据导出与审计 | 按 family 划分 train/validation/test；绑定 manifest 和 SHA256；检查划分泄漏、完整性与分布 |
| 中文描述 | 质量合格且语义一致的 episode 才生成事实及四份模板描述；当前代码使用 `observer_facts_v06b`／`pattern_detector_v06b`，旧 pilot 语言层保持原版本；不是自由文本模型生成 |
| 数据加载 | `load_episode()` 返回时间、六维 ENU 位置/速度、掩码、标签和元数据；v0.5 示例兼容，新字段缺省处理；不自动归一化或训练分类器。已知限制（审查 P2-02，本次不处理）：当前代码拒绝加载事实层版本不同的旧 v0.6 数据（如 pilot30 的 30 个 episode），需用对应运行提交 `0dffcd8` 加载 |
| 离线回放 | `replay.py` 可查看已有运行的轨迹、事件和保存结果；不启动仿真、不重算原判定。完整轨迹回放需要原始运行目录 |

能力限制：覆盖采用理想几何观察模型，不是真实相机/雷达；SITL 不模拟碰撞，安全依据实际间距证据判断。当前侦察两种飞法、巡逻和快速通过各一种，形态仍可能成为意图强线索；规划飞法不等于可靠识别出的观测运动模式。矩形螺旋通常输出 `unclear`，生产中也有退化为往返的 P2 个案，见停止报告 §9。被动时钟拟合不能证明绝对同步精度；本工程未提供模型训练或意图识别准确率，四路未验证。正式生产 r1 暴露了台账原子替换的瞬态占用风险；r2 修复已加入共享冲突退避重试、worker 改读分配文件和只读进度快照，尚未经过实跑。296 次运行不能替代完整 900 任务数据集。详见[架构概览](Multi-UAV%20SimpleGC/docs/system_architecture_overview.md)与[生产停止报告](Multi-UAV%20SimpleGC/docs/v0.6_production_stop_01.md)。

## 3. 新开发仓库和旧冻结仓库分别是什么

| 项目 | 新开发目录 `Simulation-dev` | 旧冻结目录 `Simulation` |
|---|---|---|
| 本机位置 | `F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-dev` | `F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation` |
| 用途 | 后续开发、测试、提交和推送 | 完整 v0.5 证据归档、历史回放与复核 |
| Git 基线 | 2026-10-07 从 GitHub main 克隆，迁移完成提交 `cc4bcb77f4b9dde2d6d993e582ed6ec1edb801bb` | main 冻结在 `8eaf583bc5a946e935d8ff0f410cb798fda6a6e8`；另有 `codex/v05-frozen-20261007` |
| 代码与报告 | 保留 v0.5 最终源码、配置、报告、必要台账和输入 | 保留冻结代码及完整开发历史 |
| 运行数据 | 4 个完整 episode 示例、6 个启动校验必需的 WP-S 基线 JSON；不含全量原始运行 | 原始遥测、飞控日志、所有运行、历史/新版本分析、全量导出和描述层 |
| 本机迁移完成时体积 | 文件树约 161.4 MiB，含 `.git` 合计约 244.1 MiB，不计缓存 | 整理前项目文件约 22.35 GiB，Git 历史另约 7.73 GiB；后又增加备份和发布准备文件 |

GitHub 仓库是公开的：[shy-UCAS/swarm-task-sim](https://github.com/shy-UCAS/swarm-task-sim)。发布分支 `codex/github-publication-20261007` 已经合并，后续围绕 `main` 开发，无需长期同步整理分支。原目录的 9 个大数据提交没有合入远端；不要再将它们推送或合入新开发分支。

本机新目录采用 `--depth 1 --single-branch` 浅克隆，避免下载旧大数据历史。GitHub 既有历史没有重写，所以其他电脑普通完整克隆仍可能下载较大历史。上述提交号和体积是迁移时基线，后续请以 `git status`、`git log -1` 为准。

本仓库另挂一个 git worktree：`Simulation-dev-wip`（分支 `wip/episode-player`，基于 `762a303`），保存另一会话未完成的 episode 播放器与可视化代码。**生产批次运行期间不得在 `Simulation-dev` 中开发**（受保护文件哈希会变化），新功能在该 worktree 中进行。

旧目录依然有价值，并未废弃。**不移动、删除或覆盖原运行、原分析、失败记录与受保护文件；需要复核时读取归档，新的分析输出另存。**

## 4. 新工程具体包含什么

```text
Simulation-dev/
├─ README.md                       # 本文件：当前状态与新会话入口
├─ CLAUDE.md                       # 工作约束与恢复顺序
├─ .github/workflows/              # 发布版本的离线 CI
├─ github_publication_inventory.csv # 逐文件保留/排除清单
├─ GITHUB_PUBLICATION.md           # 发布整理依据和边界
├─ SimpleGC/                      # 历史单机框架，日常优先用多机工程
└─ Multi-UAV SimpleGC/
   ├─ swarm_sim/                  # 生成、执行、分析、质量、标签、描述、加载核心
   ├─ scripts/、tests/             # 控制/复核脚本与测试
   ├─ missions/、tasks/、scenarios/ # 任务与场景配置
   ├─ generation_profiles/、quality_policies/
   ├─ ArducopterSITL/             # 固定版本 EXE、DLL、参数模板
   ├─ replay_viewer/、replay.py    # 离线回放入口
   ├─ docs/                       # 规则、历史报告、最终报告及接口说明
   ├─ examples/v05_episodes/      # 4 个原样 episode 与 sample_index.json
   ├─ runs/spike_v04_.../         # 仅两组预检基线，每组 3 个 JSON
   ├─ verification/               # 保留的台账、验收、清单等；不是全量运行库
   └─ tmp_v05/                    # 保留的正式生成输入及部分轻量复核资料
```

正式 v05c 任务输入在 `Multi-UAV SimpleGC/tmp_v05/dr_v05c/generated_130/`。目录存在不代表其中所有历史大文件都已发布；准确范围见 [数据发布索引](Multi-UAV%20SimpleGC/docs/v0.5_data_release_index.json) 和 [文件分类清单](github_publication_inventory.csv)。

示例入口：[sample_index.json](Multi-UAV%20SimpleGC/examples/v05_episodes/sample_index.json)。其中 B001 为合格侦察、B002 为合格巡逻；B037 因时钟映射不可用而质量不合格；B098 在降落阶段失败而质量不合格，其任务语义仍成功。四条均保留原状态、family 和来源划分，不能当作新训练集或完整数据集。

## 5. 旧仓库能查到哪些数据，去哪里找

下表所有相对路径都以 **旧归档的 `Simulation/Multi-UAV SimpleGC/`** 为起点。新仓库可能也有同名台账或 manifest，但不一定有它引用的完整数据。

| 想查什么 | 旧归档位置 |
|---|---|
| 全部 260 个导出 episode，包括 8 个不合格记录 | `verification/v05_batch_20261002/dataset/episodes/<run_id>/` |
| 全量清单、family、划分、质量资格与哈希 | `verification/v05_batch_20261002/dataset/dataset_manifest.json` |
| 1,008 条中文描述及事实依据 | `verification/v05_batch_20261002/dataset_language_zh_v0/descriptions.json`、`language_manifest.json`、`facts/<run_id>.json` |
| B001–B240 的运行路径、尝试、成功/失败与质量记录 | `verification/v05_batch_20261002/control.json` |
| 批量原始运行：遥测、事件、采样、飞控日志 | `verification/v05_batch_20261002/execution/`，精确路径从台账的 `run_directory` 读取 |
| 批量最终选用的外部分析 | `verification/v05_batch_20261002/analyses/`，精确绑定见 `analysis_selections.json` 与台账 `analysis_directory` |
| 试生产 PP01–PP20 及接续记录 | `verification/v05_r12b_pp_20261002/`，以及它引用的 `v05_r12_pp_20261002/` 历史目录 |
| VP/VR 验证和历史重分析 | `verification/v05c_validation_20261002/`、`verification/v05_r12_validation_20261002/`、`tmp_v05/r12*` |
| 停止、修复、重评和旧判定 | `docs/v0.5_*stop*.md`、台账历史说明、`control_B001_stop.json` / `control_B037_stop.json` / `control_B098_stop.json` |
| 时序偏差分布和最终统计依据 | `tmp_v05/v05_final_20261004/`；运行日志在 `tmp_v05/batch_execution_20261002/` |
| 更早 v0.2–v0.4 的实验与回放 | `runs/`、`datasets/`、`verification/v03_*`、`verification/v04_*`、`tmp_v04/`，按对应阶段报告定位 |

不要把 `B037` 当成文件夹名：批量编号与时间戳式 `run_id` 不同。下面是只读定位 B037 的例子（换电脑后修改归档根路径）：

```powershell
$archiveProject = 'F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation/Multi-UAV SimpleGC'
$ledger = Get-Content -LiteralPath (Join-Path $archiveProject 'verification/v05_batch_20261002/control.json') -Raw -Encoding utf8 | ConvertFrom-Json
$record = $ledger.records | Where-Object logical_index -eq 36 | Select-Object -First 1
$record | Select-Object run_id, intent, run_directory, analysis_directory, episode_quality_eligible
$episodePath = Join-Path $archiveProject ('verification/v05_batch_20261002/dataset/episodes/' + $record.run_id)
Get-Content -LiteralPath (Join-Path $episodePath 'quality.json') -Raw -Encoding utf8
```

原始运行目录通常有 `metadata.json`、`scenario.json`、`samples.csv`、`events.jsonl`、`raw/`、`sitl/`，用于追溯完整运行。导出 episode 是分析后的数据包，每条现有示例含 24 个文件，重点包括：

| 文件 | 用途 |
|---|---|
| `observations.csv` | FCU 观测位置/速度及有效掩码，模型输入来源 |
| `truth.csv`、`truth_source.csv`、`truth_provenance.json` | 仿真真值及来源，用于监督/验证；不能当作观测输入泄漏给模型 |
| `labels.json`、`semantic_validation.json` | 任务标签及双通道语义核验 |
| `quality.json`、`clock_models.json` | 质量资格、软标记和时钟原因 |
| `task.json`、`mission.json`、`shared_scene.json` | 任务定义、场景与任务背景 |
| `manifest.json` | 版本、family、资格与产物 SHA256 |
| `execution_metrics.json`、`ac4_timing_v3.json`、`phase_windows.json` | 执行指标、时序诊断和阶段窗口 |

完整数据集保留不合格 episode；训练或评测前应显式检查 `episode_quality_eligible` 和所需标签资格。加载成功不等于质量合格。中文描述层位于 dataset 的同级目录，不在每个 episode 内；新仓库的 4 个示例不包含全量描述层。

回放请在新工程调用 `replay.py`，选择归档中的原始运行目录；导出的 episode 不能直接当成 `samples.csv` 全生命周期回放目录。界面能力和数据口径见 [回放说明](Multi-UAV%20SimpleGC/docs/replay_viewer.md)。某份新报告引用的路径缺失时，先在归档定位，不重新运行仿真来“补齐”旧证据。

## 6. 当前环境与安全的检查入口

本机：Windows、PowerShell 7、Conda 环境 `llm`、Python 3.12.3、pymavlink 2.4.50。先读取项目 `.conda-env` 和 `AGENTS.md`；新电脑需要自行创建环境并安装 `requirements.txt`，界面额外需要 `requirements-gui.txt`。不要把本机安装路径当成所有电脑的默认值。

在**新仓库根目录**执行 Git 命令：

```powershell
git status --short
git branch --show-current
git log -1 --oneline
```

然后进入 `Multi-UAV SimpleGC`，以下命令只做帮助、预检测试和任务规划，不起飞：

```powershell
Set-Location 'Multi-UAV SimpleGC'
$EnvName = (Get-Content .conda-env -Raw).Trim()
$env:PYTHONPATH = 'tests'
conda run -n $EnvName --no-capture-output python -m unittest test_publication_runtime test_run_provenance
conda run -n $EnvName --no-capture-output python main.py --help
conda run -n $EnvName --no-capture-output python main.py plan missions/v3/recon_route_v05.json --output tests/.tmp/readme_recon_plan.json
conda run -n $EnvName --no-capture-output python main.py validate tests/.tmp/readme_recon_plan.json
```

规划输出必须是新文件；若已存在，换一个名字。当前离线 CI 模块清单见 [CI 配置](.github/workflows/unit-tests.yml)，已包含原发布检查以及 `test_parallel_batch`、`test_parallel_worker`、`test_parallel_finalize`、`test_parallel_file_sizes`。141/141 是迁移时的历史结果，204/204 是分片暂停 1 时的历史结果；当前测试数量与通过情况应引用对应提交的检查记录，不把历史数字当成当前总数。本次仅核对交接文档，未重新执行测试。全量 `unittest discover` 中有依赖完整历史归档的集成测试，不能把精简目录缺数据导致的失败直接当成算法退化。

真正的 `run`、`batch`、批量控制器 `next` 会启动仿真，必须依据当前用户任务执行；不要从旧交接文件推断新的运行授权。旧台账含绝对路径和证据哈希，不能直接复制为新批量的控制状态。

## 7. 冻结规则和容易误读的地方

- v0.5 定位是算法链路开发数据集。正式 profile 为 `dual_intent_v05c.json`，终点驻留 `terminal_hold_s=0`（`integer_seconds_v1`），起始航向固定为 0。
- 正式分析使用 `ordered_route_progress_v2`、`perimeter_revisit_v2` 和 `multi_intent_validation_v3`；旧实现、旧分析与旧判定保留。不要用默认版本的重分析静默替换最终选定分析。
- 最终停止口径区分“已确认违规”和“无法核实”；单次质量不合格计入异常窗口，时序偏差/过点速度等执行指标作为诊断。具体定义和来源见 [当前有效规则](Multi-UAV%20SimpleGC/docs/v0.5_当前有效规则.md) 与 [r1.2 系列补充](Multi-UAV%20SimpleGC/docs/v0.5_r1.2_addendum.md)。
- 8 个不合格运行中，7 个是时钟映射不可用；B098 是降落阶段运行未完成。未知不能改成通过，任务成功也不能替代 episode 质量合格。
- 历史规则、阶段报告或旧 README 中的“停在 B037/B098”“继续 B002–B240”“待导出”等，是当时的进度。**当前进度以本文件、最终报告和最终台账为依据，不能据此重启旧批量。**
- 当前全量导出实际保留 260 个 episode，并用标记区分 252 个合格项；不要套用早期文档中“导出自然排除”的设想来解释最终数据。
- `.claude/progress/` 快照是本机辅助信息，被 Git 忽略；另一台电脑从 GitHub 克隆后应先读本文件，不依赖必须存在的本地快照。
- 源码、配置、报告和必要基线进 Git；完整新增运行、缓存和大数据按 `.gitignore` 留在本地或另行归档。Git bundle 只备份已跟踪历史，不等于已保存全部未跟踪原始数据。

## 8. 新对话如何恢复，以及下一步是什么

恢复顺序：本 README → Git 状态和 `CLAUDE.md` → [生产停止报告](Multi-UAV%20SimpleGC/docs/v0.6_production_stop_01.md) → [pilot 报告及暂停 B 复核](Multi-UAV%20SimpleGC/docs/v0.6_pilot_report.md) → [r2 起始指令](Multi-UAV%20SimpleGC/docs/v06_r2_kickoff.md) → 独立审查报告 `SwarmData/reviews/v06_deepseek_audit_20261009/audit_report.md`（仓库外）→ 本次任务涉及的规则、接口、源码和证据；涉及 v0.5 时读[冻结最终报告](Multi-UAV%20SimpleGC/docs/v0.5_final_report.md)。完整轨迹复核先确认归档或 SwarmData 可用，不把报告摘要当成重新核验过原始数据。

可以把下面这段作为新对话的第一条消息：

> 请先读根 README、CLAUDE.md 并核对 Git，恢复 v0.5 冻结归档、v0.6 三意图与事实层 v06b、两次两路 pilot，以及正式生产 296/900 后规则停止的状态。区分当前开发 HEAD、pilot 运行 SHA 和生产运行标签。先读生产停止报告与 pilot 复核结论，说明证据位置及当前暂停 C；不自动 run/resume/prepare/finalize，不清除停止原因，不改写旧证据。

r1 批次 `v06_production900_seed2026100812` 以 296/900 个任务终态记录结束，`completed=false`、`finalized=false`、`paused=false` 且有 `stopped_reason`；**规则停止不是人工暂停，不能直接 `--resume`**，该批次保持原状作为证据，不补飞、不 finalize、不修改台账。快速通过六项阈值冻结，最终悬停为 2 秒，固件版本等待已恢复 10 秒。

**下一步（用户已决定）：** 修复台账持久化缺陷后，用同一 profile `generation_profiles/tri_intent_v06_production.json`、同一主种子 `2026100812` 重新准备 r2 批次 `v06_production900r2_seed2026100812`，从头运行 900 个任务；修复提交经远端 CI 通过后打标签 `v0.6-production-r2`。r2 任务清单须与 r1 逐条一致。prepare 后停下，由用户启动运行。v0.5 无待执行生产任务；所有 pilot 不并入训练数据。

独立审查（`SwarmData/reviews/v06_deepseek_audit_20261009/audit_report.md`）P2 项处理状态：本次处理 P2-03、P2-04（pilot 报告末尾追加勘误）、P2-05（prepare 块 Int64）、P2-06（状态文档更新）；仍未处理 P2-01（交叉否定逐项反例）、P2-02（加载器历史版本兼容）、P2-07（仓库历史大文件）。另记 P2：续跑时台账重放约 20 分钟、回字形窄条带退化。

后续里程碑完成、规则改变或目录迁移时，同步更新本文件中的状态、计数、验证范围和证据入口。完整变更历史保留在 Git 和对应报告中，避免只有某个聊天窗口知道项目进展。

## 9. 常用资料入口

- [v0.5 最终报告](Multi-UAV%20SimpleGC/docs/v0.5_final_report.md)：最终计数、异常、描述样例、时序分布与已知限制。
- [v0.5 当前有效规则](Multi-UAV%20SimpleGC/docs/v0.5_当前有效规则.md)：规则来源及后续补充；阶段性进度须结合最终报告解读。
- [暂停 1 报告](Multi-UAV%20SimpleGC/docs/v0.5_r1.2b_pause1_report.md)：试生产验收和历史细节。
- [迁移与环境说明](Multi-UAV%20SimpleGC/docs/github_migration.md)：安装和独立目录预检。
- [发布整理说明](GITHUB_PUBLICATION.md)、[数据索引](Multi-UAV%20SimpleGC/docs/v0.5_data_release_index.json)：Git 内容与归档边界。
- [TaskSpec v3](Multi-UAV%20SimpleGC/docs/task_spec_v3.md)、[回放说明](Multi-UAV%20SimpleGC/docs/replay_viewer.md)：接口及可视化使用。
- [迁移前离线验证记录](Multi-UAV%20SimpleGC/docs/github_publication_checks_runtime.json)：当时 141 项检查及独立路径验证的记录。
- [v0.6 并行使用说明](Multi-UAV%20SimpleGC/docs/v0.6_parallel_usage.md)：分片控制器、数据根和收尾入口。
- [v0.6 并行暂停 1 报告](Multi-UAV%20SimpleGC/docs/v0.6_parallel_pause1_report.md)：实现阶段的离线验收及历史证据限制。
- [v0.6 两路试跑报告](Multi-UAV%20SimpleGC/docs/v0.6_parallel_pilot_report.md)：20 任务计数、语义不一致定位、吞吐及诊断。
- [v0.6 正式计划](Multi-UAV%20SimpleGC/docs/v06_formal_plan.md)：原计划及执行状态说明；pilot 与暂停 B 已完成，生产已运行但规则停止，尚未完成/冻结；末尾 P3 待办未执行。
- [v0.6 三十任务 pilot 试跑报告](Multi-UAV%20SimpleGC/docs/v0.6_pilot_report.md)：30/30 计数、八项事后分析、人工暂停续跑实测，以及事实层 `null` 槽位诊断与修复的离线验收。
- [v0.6 上一批停止报告](Multi-UAV%20SimpleGC/docs/v0.6_pilot_stop_01.md)：`v06_pilot30_seed2026100811` 因 `parameter_firmware` 立即停止的原因、时间线与影响。
- [v0.6 正式生产停止报告](Multi-UAV%20SimpleGC/docs/v0.6_production_stop_01.md)：296 次运行、台账持久化失败、质量/语义分项、暂停续跑核对、数据不可收尾的边界及待复核建议。
- [v0.6 运行命令](Multi-UAV%20SimpleGC/docs/v0.6_formal_run_commands.md)：历史启动流程与当前停止状态；禁止对已停止生产批次直接 run/resume/finalize。
- [数据生成系统框架概览](Multi-UAV%20SimpleGC/docs/system_architecture_overview.md)：架构、模块职责、完整数据流与当前能力边界。
- [r2 起始指令](Multi-UAV%20SimpleGC/docs/v06_r2_kickoff.md)：生产 r2 的修复范围、测试要求、提交与 prepare 步骤（任务记录）。
- 独立审查报告：`SwarmData/reviews/v06_deepseek_audit_20261009/audit_report.md`（仓库外）；P2-01～P2-07 的处理状态见第 8 节。

## 10. v0.5 冻结版本位置

- 完整冻结归档：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation`。
- 冻结 Git 提交：`8eaf583bc5a946e935d8ff0f410cb798fda6a6e8`（简称 `8eaf583b`）；包含最终报告 §c 的原因更正。
- 数据集清单：归档 `Multi-UAV SimpleGC/verification/v05_batch_20261002/dataset/dataset_manifest.json`。
  SHA256：`2ac8c17583ec93a43ef31f64a7bbfa2fd16355f58c4929b2cf88f990ee9df707`。
- 描述层清单：归档 `Multi-UAV SimpleGC/verification/v05_batch_20261002/dataset_language_zh_v0/language_manifest.json`。
  SHA256：`79da5becf717e988bea4027deebd0cad9b3850c88e731bada2ccd43569a7eb8c`。
- **算法线只从归档只读取数**。模型输出、缓存、派生结果与新分析写到归档之外；不得改写源 episode、原标签、描述或判定。
- 2026-10-07 可追溯性核对：归档全量 **661/661** 测试通过；发布 CI 为原 139 项加新增 2 项，共 141 项，另外 522 项仍保留但未纳入 CI，不全是归档依赖测试。
- 实际发布差异除忽略规则/基线外还包括 CI、新基线测试、发布文档和 4 个 episode 示例；核心生产代码与原配置/测试一致。完整差异及未纳入 CI 测试分类、九个提交、数据哈希核验见 [拆分可追溯性报告](Multi-UAV%20SimpleGC/docs/v0.5_repository_traceability_20261007.md)。
- 归档外备份清单：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-backup-manifests/20261007-traceability/archive_sha256.csv`，覆盖 52,493 个文件、29.97 GiB；清单本身 10.87 MiB。排除 .git，包含未跟踪/忽略文件和 .git-publication 中的已有 bundle；完整范围及清单 SHA256 见报告。

## 11. 数据版本登记表

数据集清单一律指该版本 `dataset/dataset_manifest.json` 的 SHA256；描述层另列 `language/language_manifest.json`。用途是硬约束：标为 pilot 的批次不得并入训练数据集。

| 数据版本 | 用途 | 位置 | 规模 | 数据集清单 SHA256 | 状态与边界 |
|---|---|---|---|---|---|
| v0.5 全量 260（PP01–PP20 + B001–B240） | 算法链路开发数据集（正式） | 归档 `Simulation/Multi-UAV SimpleGC/verification/v05_batch_20261002/dataset/` | 260 episode，质量合格 252、语义一致 253 | `2ac8c17583ec93a43ef31f64a7bbfa2fd16355f58c4929b2cf88f990ee9df707` | 已冻结；描述层 SHA256 `79da5becf717e988bea4027deebd0cad9b3850c88e731bada2ccd43569a7eb8c` |
| v0.6 pilot 20（`v06_pilot20_20261007_seed2026100701`） | **pilot：仅用于并行方案验证，不用于训练** | `SwarmData/parallel_batch/v06_pilot20_20261007_seed2026100701/dataset/`（仓库外，与 `prepare_inputs/` 同根） | 20 episode，质量合格 20、双通道语义一致 19 | `510f788140f240863a8ace68776568739d2716456379df0ca6a804e42169c0c1` | 已收尾（`completed=true`、`finalized=true`、`stopped_reason=null`）；描述层 SHA256 `b2a128bd69aab29e0308570446f2f1024896f68ab38122168799cf382490e8b6`，76 条描述 / 19 episode、跳过 1；该批次绑定提交 `c07840f`，本次 CI 路径守卫修复后，用新代码对它做完整性复检会出现 `protected_sha256` 受保护哈希失配，属于预期，不重跑、不改写冻结计划 |
| v0.6 pilot 30（`v06_pilot30b_seed2026100811`） | **pilot：三意图及暂停续跑验证，不用于训练** | `SwarmData/parallel_batch/v06_pilot30b_seed2026100811/dataset/` | 30 episode，质量合格 29、语义一致 29，失败运行 1 | `38af46be0bb0ffbc4e26b0ee94c37abdfd6dbee207cd9e360747d50c77998af1` | 已收尾；描述层 SHA256 `04edebd0c6e682354d3d04ed57783bb2761fa487ec46ea4b907947bfd4f5a43e`，116 条/29 episode、跳过 1；运行 `0dffcd8`，旧事实版本 v06 保留，v06b 离线验收另存 |
| v0.6 正式生产停止批次（`v06_production900_seed2026100812`） | 正式生产尝试；**当前仅保留运行证据，不是已完成训练数据集** | `SwarmData/parallel_batch/v06_production900_seed2026100812/`，逐尝试证据在 `shards/` | 计划 900 任务；已运行 296，质量合格 287、语义一致 289；无重试 | **不存在：未 finalize、未导出** | 运行 `762a303`／`v0.6-pilot`；`completed=false`、`finalized=false`、台账保存失败规则停止；无正式描述层，不直接 resume、不覆盖重建 |

pilot20 细节见[两路试跑报告](Multi-UAV%20SimpleGC/docs/v0.6_parallel_pilot_report.md)，pilot30 及 v06b 验收见[pilot 报告](Multi-UAV%20SimpleGC/docs/v0.6_pilot_report.md)，生产停止证据见[停止报告](Multi-UAV%20SimpleGC/docs/v0.6_production_stop_01.md)。本次复算 pilot30 两份清单 SHA256 与上表一致；生产台账 296 条及未导出状态与报告一致。停止批次行是证据登记，不代表已有正式数据集版本。
