# SwarmTaskSim：工程进度与新会话交接

**请新会话先读本文件。当前 v0.5 数据生成与收尾已完成并冻结；GitHub 精简发布及本机开发目录迁移也已完成。后续开发在 `Simulation-dev`，完整历史数据在原 `Simulation`。没有等待自动执行的仿真任务。**

本文件最后核对日期为 **2026-10-07**。它记录项目当前状态、能力和资料入口，不代替源码、规则或原始证据。文中本机绝对路径仅适用于原开发电脑；其他电脑需要安装环境，并另行取得完整数据归档。

## 1. 工程已经做到哪一步

本项目通过 ArduCopter SITL 生成多无人机任务轨迹、质量标记、双通道语义标签和中文描述，供算法链路开发使用。当前源码版本为 `0.5.0-dev`，v0.5 生产数据的状态为完成并冻结。

| 阶段 | 已完成内容 | 当前状态 |
|---|---|---|
| 早期框架与 v0.2 | 单机/多机执行、点访问、巡逻、覆盖、轨迹记录与质量检查 | 代码及历史说明保留 |
| v0.3–v0.4 | 共享区域分工、TaskSpec、连续航线、family 划分、双通道验证、执行诊断及离线回放 | 作为现有框架基础；旧报告是对应阶段记录 |
| v0.5 | 侦察与边界巡逻双意图；验证、20 次试生产、240 次批量运行；导出、审计、描述、加载验收 | 已完成，停在暂停 2，已冻结 |
| Git 发布与迁移 | 精简代码发布，补齐运行基线，独立目录验证，PR 合并及建立新开发目录 | 已完成；[PR #1](https://github.com/shy-UCAS/swarm-task-sim/pull/1) |
| v0.6 | 新增独立分片入口、全局预算/停止/恢复与统一收尾，配套离线测试和 CI 大小门禁 | 实施到“暂停 1”；未运行仿真，试跑待复核；[使用说明](Multi-UAV%20SimpleGC/docs/v0.6_parallel_usage.md) |

v0.6 暂停 1：新增测试 63/63、CI 离线清单 204/204 通过；全量 721/726 通过，5 项历史证据依赖错误在原始基线复现。文件行数、八类测试、未解决项及数据目录示例见 [暂停 1 报告](Multi-UAV%20SimpleGC/docs/v0.6_parallel_pause1_report.md)。

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
| 多机任务执行 | 框架已有 1～6 机运行能力；v0.5 正式 profile 使用 2/3/4 机。管理独立 SITL 进程、任务上传、起飞、执行、降落及清理 |
| 双意图任务 | 侦察使用 `parallel_strips` 扫描策略，巡逻使用 `perimeter_loop` 边界绕行策略；同一基础场景生成两种意图，保留共同 family |
| 任务与场景生成 | 支持 TaskSpec 编译、场景预检、按 profile/种子生成任务清单；正式 v05c 输入已保存 |
| 双通道判定 | 分别依据 SIM 真值和 FCU 观测核验任务语义，记录成功、失败、未知及两通道一致性 |
| 质量与执行诊断 | 检查时钟、有效观测、真值间距、机载任务参数；输出有序路线进度、圈数、时序偏差、过点速度等 |
| 数据导出与审计 | 按 family 划分 train/validation/test；绑定 manifest 和 SHA256；检查划分泄漏、完整性与分布 |
| 中文描述 | 根据已保存事实和版本化规则模板生成描述，核对一致性；不是自由文本模型生成 |
| 数据加载 | `load_episode()` 返回时间、各机六维 ENU 位置/速度、有效掩码、标签和元数据；不自动训练分类器 |
| 离线回放 | `replay.py` 可查看已有运行的轨迹、事件和保存结果；不启动仿真、不重算原判定。完整轨迹回放需要原始运行目录 |

能力限制：覆盖指标采用理想几何观察模型，不是真实相机/雷达；SITL 不模拟碰撞，安全依据真值间距判断。每个意图目前只有一种主要策略，策略形态可能成为强线索；阶段边界精度约 1 s。该工程没有给出意图识别准确率；新增分片控制器仍待真实仿真验证。更多限制见最终报告 §g。

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

规划输出必须是新文件；若已存在，换一个名字。141 项发布检查的模块清单见 [CI 配置](.github/workflows/unit-tests.yml)。全量 `unittest discover` 中有依赖完整历史归档的集成测试，不能把精简目录缺数据导致的失败直接当成算法退化。

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

恢复顺序：本 README → Git 状态和 `CLAUDE.md` → [最终报告](Multi-UAV%20SimpleGC/docs/v0.5_final_report.md) → 本次任务涉及的规则、接口、源码和证据。涉及完整历史轨迹时先确认归档可用；归档不可用就明确缺少哪些证据，不把报告摘要当成已经重新核验过原始数据。

可以把下面这段作为新对话的第一条消息：

> 请先读仓库根目录 README.md，核对当前 Git 分支/提交，并恢复工程上下文。说明 v0.5 已完成哪些工作、当前框架能做什么、新开发仓库与旧冻结归档各包含哪些内容。按需要读取最终报告和有效规则，区分旧阶段指令与当前任务。先汇报恢复结果，不自动启动仿真、批量生成或改写旧证据。

当前没有待执行的 v0.5 生产任务。v0.6 分片代码已停在暂停 1，下一步先复核代码、测试和停止边界，再由用户确定试跑方案及授权；不自动进入试跑或正式生产。

后续里程碑完成、规则改变或目录迁移时，同步更新本文件中的状态、计数、验证范围和证据入口。完整变更历史保留在 Git 和对应报告中，避免只有某个聊天窗口知道项目进展。

## 9. 常用资料入口

- [v0.5 最终报告](Multi-UAV%20SimpleGC/docs/v0.5_final_report.md)：最终计数、异常、描述样例、时序分布与已知限制。
- [v0.5 当前有效规则](Multi-UAV%20SimpleGC/docs/v0.5_当前有效规则.md)：规则来源及后续补充；阶段性进度须结合最终报告解读。
- [暂停 1 报告](Multi-UAV%20SimpleGC/docs/v0.5_r1.2b_pause1_report.md)：试生产验收和历史细节。
- [迁移与环境说明](Multi-UAV%20SimpleGC/docs/github_migration.md)：安装和独立目录预检。
- [发布整理说明](GITHUB_PUBLICATION.md)、[数据索引](Multi-UAV%20SimpleGC/docs/v0.5_data_release_index.json)：Git 内容与归档边界。
- [TaskSpec v3](Multi-UAV%20SimpleGC/docs/task_spec_v3.md)、[回放说明](Multi-UAV%20SimpleGC/docs/replay_viewer.md)：接口及可视化使用。
- [迁移前离线验证记录](Multi-UAV%20SimpleGC/docs/github_publication_checks_runtime.json)：当时 141 项检查及独立路径验证的记录。

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
