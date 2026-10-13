# M2-00 阶段报告：保存 M0/M1 本地 Git 检查点

- 阶段 / attempt：**M2-00 / attempt_01**；原修订为 `attempt_02_repair`；当前最终修订为 Codex 执行的 `attempt_03_record_fix`
- 状态：**PASS**（Codex 按用户要求直接完成剩余记录修正并核验；最终回执 [M2-00_review_03.md](M2-00_review_03.md)）
- 上一轮 PASS 回执：不适用（首阶段）；本轮审阅回执 [M2-00_review.md](M2-00_review.md)，结论 `FIX_REQUIRED`，SHA256 `8390d3fe093cdd1b213b8d03888882f69d61a566709d4a9d337c31c9d39c2578`
- 撰写日期：2026-10-12；修订日期：2026-10-12（America/Los_Angeles）
- 依据：[M2 分阶段实施与逐轮代码审阅指南](../fast_dynamics_engine_m2_staged_guide.md)、[M0/M1 实施报告](../fast_dynamics_engine_m01_report.md)、[适配备忘](../fast_dynamics_engine_adapter_memo.md)
- 摘要 JSON：[M2-00_summary.json](../../verification/fast_dynamics_m2/M2-00_summary.json)
- 修订范围：审阅 R1（提交边界说明）、R2（任务/仿真登记口径）、R3（入口状态）；业务代码、测试、依赖、提交与历史证据均未改动，修订记录见 §15。修订前的被审版本原样保存在外部 `attempt_02_repair/M2-00_report.reviewed.md`（SHA256 与回执一致）。

## 1. 实际完成范围

本阶段只做 M0/M1 基线入版本库，不实现任何 M2 功能、不迁移证据、不改脚本输出策略。

| 指南 M2-00 条目 | 实际结果 |
| --- | --- |
| 1. 只读检查 Git 根、分支、HEAD、三类清单与说明 | 已完成：Git 根 `Simulation-dev`，起始分支 `main`、HEAD `5e45637`；起始无 staged 内容；20 个已修改跟踪文件 + 223 个未跟踪文件 |
| 2. 使用合适本地开发分支 | 已完成：新建 `codex/fast-dynamics`（自 `5e45637`，切换前后工作区条目数均为 243，未丢弃任何修改） |
| 3. 准备显式提交清单 | **部分符合**：243 个文件按显式清单入版本库、清单可复核；但本轮把“.gitignore 可见集合”当成提交边界，未做用途白名单，偏差与逐项分类登记见 §3.1（审阅 R1） |
| 4. 创建本地检查点提交 | 已完成：`0f7c42d8688880b1d8e1a416184383a94a5ae123`，父 `5e45637`；**未 push、未打标签、分支无 upstream**；按审阅 R1 处置边界保留该提交，不 amend/reset/filter-repo |
| 5. 未提交大数据保留原处，只读核对清单 | 已完成：28,077,989 字节留在工作区，未删除、未移动；只读核对现有 completion/manifest，未改写任何旧 manifest |
| 6. 写报告与摘要，停止等审阅 | 本文件（修订版）与摘要 JSON；状态 `AWAITING_REVIEW` |

**本阶段没有重跑 M0/M1 验收。** 报告里出现的 367/406/260/4 等数字都是 M0/M1 历史基线，不是本次实测；本次只有第 5 节的恢复性冒烟测试是新执行结果，且该测试实际执行了 M1 仿真，登记见第 6 节。

## 2. Git 身份与分支

| 项目 | 值 |
| --- | --- |
| 分支 | `codex/fast-dynamics`（本阶段新建；此前不存在同名分支，现有分支仅 `main`、`codex/v06-parallel-shards`、`wip/episode-player`） |
| 基线 / 父提交 | `5e45637f2bf63054ed0ace2433fd7c9ea7b075ac` |
| 检查点提交 | `0f7c42d8688880b1d8e1a416184383a94a5ae123` |
| 提交统计 | 243 files changed, 54273 insertions(+), 95 deletions(-) |
| `main` | 仍为 `5e45637`（未移动，未 reset） |
| `origin/main` | 仍为 `5e45637`（本阶段未 fetch、未 push、未建 PR、未打标签） |
| 分支 upstream | 无（`no upstream configured`） |
| reflog | 仅两条：`branch: Created from HEAD (5e45637)`、`commit: 0f7c42d` |
| 工作区（attempt_01 检查点提交后的历史快照） | 当时跟踪文件无未提交改动；此项不表示后续修订仍为空 diff。当前文档差异及哈希见 §16 和摘要的当前工作树字段。 |

提交信息按项目 `git-commit-message` 约定写成 Markdown 分节（H1 标题 + `## 变更说明` + `## 关联`），因此 Git subject 行以 `# ` 开头：

```text
# feat(fast-dynamics): 落地 M0/M1 内核与双机完整数据链
```

## 3. 提交清单构成与排除边界

| 类别 | 文件数 | 字节 | 内容 |
| --- | --- | ---: | --- |
| 引擎包 | 11 | 78,085 | `swarm_sim/fast_dynamics/*.py` |
| 公共接口分派 | 9 | 162,343 | `dataset.py`、`dataset_audit_v3.py`、`episode_loader.py`、`language_templates_v0.py`、`language_v0.py`、`mission_evaluation.py`、`observer_facts_v0.py`、`protocol.py`、`quality.py` |
| 测试与 fixture | 4 | 34,459 | `test_fast_dynamics_core/execution/artifacts.py` + `tests/fixtures/fast_dynamics/rapid_passage_0000_v00.json` |
| 脚本 | 3 | 24,819 | `run_fast_dynamics.py`、`verify_fast_dynamics_m01.py`、`benchmark_fast_dynamics.py` |
| 文档 | 14 | 311,559 | 5 份新计划/报告（本指南、实现计划、适配备忘、交接、M0/M1 报告）+ 根与项目入口文档 |
| 依赖与 CI | 2 | 3,562 | `requirements.txt`（新增 `numpy==2.5.3`）、`.github/workflows/unit-tests.yml`（登记 3 个新模块） |
| 证据（Git 可见；**不全是汇总**，逐项分类见 §3.1） | 200 | 2,138,102 | `verification/fast_dynamics_m01/` 下 199 个 JSON + `collect_baseline.py`；其中 180 个是 8 个逐 episode/attempt 目录的记录 |
| **合计** | **243** | **2,752,929** | 最大单文件 210,493 字节 |

清单来源为 `git diff --name-only` ∪ `git ls-files --others --exclude-standard`，写入外部 `intended_files.txt`，再以 `git add -- <显式清单>` 暂存；**未使用 `git add -A`**。暂存后核对：暂存集合与预期集合完全一致（243/243），无被忽略文件混入。

排除项完全沿用仓库既有 `.gitignore` 策略（代码/配置/报告入库、完整仿真数据留在本地），不是本阶段新定的边界：

| 排除项（均在 `verification/fast_dynamics_m01/` 下） | 文件数 | 字节 | 既有规则 |
| --- | ---: | ---: | --- |
| `*.csv`（支持轨迹与观测） | 64 | 27,313,964 | `/Multi-UAV SimpleGC/verification/**/*.csv` |
| `*.log` | 4 | 135,674 | `/Multi-UAV SimpleGC/verification/**/*.log` |
| `dataset*/` 树内 JSON（白名单外） | 88 | 628,351 | `/Multi-UAV SimpleGC/verification/**/dataset*/**`（保留 `dataset_manifest.json` 等） |
| **合计** | **156** | **28,077,989** | 全部仍在工作区原处，待 M2-01 迁移 |

证据树整体为 356 文件 / 30,216,091 字节；其中 200 文件 / 2,138,102 字节进入本次提交，156 文件 / 28,077,989 字节仍为本地数据。提交后再次核对工作区证据树仍为 **356 文件 / 30,216,091 字节**（逐字节未动）。

**待 M2-01 处理的已知一致性风险：** 本次提交的 200 个证据文件与其被排除的 CSV/dataset 载荷在同一目录树内；`completion.json`、`manifest.json` 等记录的文件清单仍指向工作区绝对路径与全部载荷哈希。M2-01 必须按原样整树复制到 `SwarmData/fast_dynamics/m01_archive/<新ID>/`、逐文件校验后，再删除仓库内批量产物并保留阶段级脚本与汇总；本阶段未删除、未移动、未改写任何旧 manifest，也未把提交 SHA 写回旧清单。

### 3.1 提交边界偏差登记（审阅 R1 修订）

审阅结论（`FIX_REQUIRED` R1）：提交包含逐样本标签、事件、描述等 JSON，不能整体称为“小型汇总”；`.gitignore` 决定 Git 默认看见什么，不代表用户允许提交什么；把“全部已修改文件 + 全部 Git 可见未跟踪文件”装入显式数组，仍没有完成按用途筛选，数组形式不自动满足白名单要求。本轮如实登记这项执行偏差，不辩解、不追认为合规。

事实（与回执 §3 R1 一致）：进入 `0f7c42d` 的 200 个证据文件中，**180 个位于 8 个逐 episode/attempt 结果目录，共 1,443,395 字节**，其中既有 report/manifest，也有实际 `run/analysis/labels.json`、`events.json`、`compiled_scene.json`、`language/descriptions.json`、事实层文件等逐样本载荷。

逐项分类规则：只作用于单一 attempt/episode 的文件＝**拟外置**；汇总整个阶段或属工具的文件＝**拟保留**。

| 分类 | 文件数 | 字节 | 内容 |
| --- | ---: | ---: | --- |
| `keep_stage_summary`（拟保留） | 18 | 694,586 | 来源索引、划分安排、数值收敛与步长减半证据、内核基准、集成前基线与最终只读复核副本、阶段级 `verification.json`/`tests.json`/`completion.json`/`mission_convergence.json`、采集脚本 `collect_baseline.py` |
| `externalize_sample_payload`（拟外置·逐样本载荷） | 126 | 771,141 | 逐样本标签、事件、场景、任务快照、分配、约束、阶段窗口、质量、语义核验、来源、dataset 清单、中文描述、事实层 |
| `externalize_sample_bookkeeping`（拟外置·逐尝试记录） | 56 | 672,375 | 逐尝试 `attempt.json`、`completion.json`、`config.json`、`report.json`、运行元数据、分析清单与索引；另含阶段目录下 2 个单例配置快照 |
| **合计** | **200** | **2,138,102** | 拟外置合计 **182 文件 / 1,443,516 字节**（180 逐 episode 文件 + 2 个单例配置） |

逐项清单（路径、字节、SHA256、类别、用途理由）在外部证据根：`attempt_02_repair/evidence_classification.json`（机器可读）与 `evidence_classification.md`（人可读表），生成脚本 `classify_evidence.py`。**该分类清单已获审阅批准；复制、校验和清理仍需用户启动 M2-01 后按阶段指令执行**；本轮不迁移、不删除、不改 `.gitignore`。

两项分类已由 [第二轮回执](M2-00_review_02.md) 批准，最终复核维持：

1. 8 个逐样本/逐尝试 `completion.json` 随对应载荷外置；阶段级 `final_verification_01/completion.json` 仍随阶段汇总留库。
2. `final_verification_01/semantic_failure_config.json` 与 `unknown_timeout_config.json` 随单例外置。

批准范围为保留 18、外置 182 项，加 156 项忽略载荷共 338 个清理候选。只有 M2-01 完整复制、逐文件校验并证明新位置可独立使用后才清理，本轮未迁移或删除。
历史影响与边界：这 182 个文件已进入 `0f7c42d` 的对象历史；M2-01 清理**最新树**不会把它们从 Git 历史中移除。本阶段按回执要求保留 `0f7c42d`，不 amend / reset / filter-repo，也不把“JSON 体积小”当作后续留库理由。

M2-01 更新说明：提交边界一旦按用途划分，M2-01 的清理范围应为——仓库内跟踪的 182 个拟外置文件 + 156 个被忽略的 CSV/日志/dataset 载荷，合计 338 文件；保留 §3.1 表中的 18 个阶段级汇总/工具文件。

## 4. 源身份

- 恢复检查涉及的 29 个代码/测试/fixture/依赖/工作流文件逐文件 SHA256 见外部 `source_snapshot.txt`，该清单文件 SHA256 为 `38c5d0cf401a0d5e018aaa7719cde22f676142c247ed3fd033143e8c45a91b2f`。
- attempt_01 提交时 243 个文件逐文件 `sha256`（当时工作区内容）与 Git blob SHA1 见外部 `checkpoint_manifest.json`；核对结果 **243/243 工作区字节 == 暂存 blob 字节**。仓库根 `.gitattributes` 为 `* -text`（保留精确字节），因此本次提交不引入行尾规范化，产物内记录的源哈希仍对应提交内容。
- 提交 SHA 与 M0/M1 报告中的“原验收源哈希”是两个不同身份：本次只登记提交 SHA，未据此改写任何历史 manifest 或验收结论。

## 5. 执行命令、退出码与测试结果

工作目录：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-dev`（Python 步骤在 `Multi-UAV SimpleGC`）。
环境：PowerShell 7.6.6；`.conda-env` = `llm`，Python 3.12.3 / NumPy 2.5.3（未切换 base、未安装依赖）。
外部证据根：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m2/M2-00/attempt_01/`。

| 步骤 | 命令（要点） | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 起点检查 | `git status --porcelain -uall`、`git diff --cached --name-only`、`git branch`、`git log -1` | 0 | 无 staged；20 修改 + 223 未跟踪；HEAD `5e45637` |
| 建立分支 | `git switch -c codex/fast-dynamics` | 0 | 切换前后工作区条目数 243 不变 |
| 建清单 | `git diff --name-only` / `git ls-files -o --exclude-standard` | 0 | 243 项，2,752,929 字节 |
| 暂存 | `git add -- @files` | 0 | 暂存集合与预期集合一致；无忽略文件混入 |
| 提交 | `git commit -F <外部消息文件>` | 0 | `0f7c42d`，243 文件 |
| 提交后核对 | `git show --name-only`、`git status --porcelain -uall`、`git ls-files -o -i` | 0 | 提交含 243 文件；工作区无跟踪改动；156 个被忽略数据仍在 |

**测试结果（只有恢复性冒烟，不是 M0/M1 验收）：**

| 尝试 | 方法 | 结果 |
| --- | --- | --- |
| A（已取代） | `git archive` 全树导出 176,138,240 字节 + `tar -xf` | 3,220/3,223 文件解出；3 个非 ASCII 文件名报 `Invalid empty pathname`（bsdtar 限制）。超大中间 tar 与部分解包树已删除（体积大、复现成本低），错误与结论保留在 `commands.log` |
| B | 定向导出 `swarm_sim/tests/missions/scripts/requirements/.conda-env` 后运行 3 个新模块 | `Ran 39 tests`，**errors=7**：`ValueError: cannot find source Git baseline`（`artifacts.py::_git_revision()` 要求运行位置在 Git 仓库内，导出目录不在） |
| C（正式恢复证据） | `git worktree add --no-checkout --detach <外部路径> 0f7c42d` + cone 稀疏检出（`swarm_sim`、`tests`、`missions`、`scripts`）+ `git checkout` | `Ran 39 tests in 26.383s` → **OK（39 通过、0 失败、0 错误、0 跳过）**；退出码 0；测试后该工作树 `git status` 干净；随后 `git worktree remove --force`，`git worktree list` 恢复为原有两条 |

说明：39 项即 M0/M1 报告的“新增 39 项”（内核 15、执行 10、数据链 14），是**测试用例数而不是 episode 数**。它只证明检查点提交可恢复出可运行实现，**不替代** 367 项旧清单、DR130 260 项、v0.5 示例 4/4 或 406/406 的 M0/M1 验收，本阶段没有重跑这些。

原始日志与局限：`restore_check_b/restore_tests.log`（B 失败原文）、`restore_check_c/restore_tests.log`（C 通过原文）为原样输出；`commands.log` 是**事后汇总**，不是原始完整终端输出；尝试 A 的原始 tar 与部分解包树已删除，只剩说明文件。因此**不能**说“三个 attempt 的全部原始证据都已保留”——A 的过程只能靠汇总与错误信息复核，本轮不重造 A 的日志、也不重跑整个恢复过程。

## 6. 任务执行、仿真与数据使用登记（审阅 R2 修订）

结论口径：**本轮没有开展任何独立 M2 任务批次**（没有 M2 覆盖矩阵运行、没有新增任务、没有生产批次、没有 M2 语义适配），**但确实执行了 M1 恢复性测试内的真实仿真**，并在临时目录生成过 episode、dataset 与中文描述。原报告“没有运行任何任务 / 没有产生 episode/dataset/描述”的口径与测试源码不符，本版更正。

| 项目 | 实际登记 |
| --- | --- |
| 独立 M2 实验 / 新任务 / 生产批次 | **无**（0 个 M2 任务） |
| 测试内仿真 | **有**：`run_mission` 在 3 个测试模块中共 11 处调用点（core 0、execution 7、artifacts 4）；其中 execution 的 worker 一致性用例在 1/2 worker 下各再执行一次，1 处为“未实现范围拒绝”负例 |
| 测试内产物 | **有**：`write_episode` 3 处调用点、`build_dataset` 3 处、`describe_dataset` 3 处、`audit_dataset` 2 处（均在 artifacts 模块），全部写在 `TemporaryDirectory` 内并在 `tearDown` 清理；本轮结束后仓库与系统临时目录都不保留产物 |
| 实际执行次数 / episode 数 / 描述条数 | **未计量**：原日志只记录 39 个测试用例，不记录 `run_mission` 次数、episode 数或描述条数，无法从日志准确还原；按回执要求不填 0、也不给推测值。39 = 测试用例数（core 15 + execution 10 + artifacts 14） |
| 覆盖矩阵单元 | 全部 `NOT_RUN`，本阶段不做任何能力声明 |

测试读取的输入与实际用途（区分“读取”“执行”“历史结果”“未来留出”）：

| 输入 | 身份 | 实际用途 |
| --- | --- | --- |
| `tests/fixtures/fast_dynamics/rapid_passage_0000_v00.json` | SHA256 `dd5beb91f5388991487aab15c07493f74075e5ea17d99225db7313b2412ee318`；对应 M0 索引中的开发 family `scene_74f9c65a90cdb4ffd5ed` | 由 `test_fast_dynamics_execution.py` 和 `test_fast_dynamics_artifacts.py` 两个模块读取并**实际执行**；`test_fast_dynamics_core.py` 使用合成数值状态，不读取该 fixture。测试场景包括：正常完成链、0.3 m/s 低速语义失败、0.03 s 超时未知、10 ms 半步长、agent 顺序与 worker 一致性、等待期再确认等。用途是 **M1 恢复性冒烟**，不是独立 M2 研究实验或生产批次 |
| `missions/v3/rapid_passage_route_v06.json` | 3 机 `rapid_passage` 任务 | 只被“未实现范围拒绝”用例读取，`run_mission` 按 M1 范围抛 `ValueError("two-vehicle")`；**读取但未成功执行**，不计为已覆盖能力 |
| 历史 SITL 运行结果、已导出数据集、语言产物（`SwarmData/parallel_batch/` 等） | 冻结证据 | **未读取**：测试只使用临时目录内由本轮新生成的产物 |
| 未来 `calibration` / `blind_holdout` 数据 | 尚未建立（M2-02 才冻结） | **未读取**；但“集合不存在”不等于“经过计算验证的零交集”，见 §11 |

## 7. 产物

外部证据根（绝对路径，均为本阶段新建）：

```text
F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m2/M2-00/attempt_01/
  commands.log                    本阶段命令与输出要点
  intended_files.txt              243 项显式提交清单
  excluded_ignored_files.txt      156 项排除清单（含字节）
  checkpoint_manifest.json        243 项 path/字节/sha256/blob SHA1/exact
  source_snapshot.txt             29 个代码文件 sha256（清单 sha256 见第 4 节）
  commit_message.txt              实际提交信息原文
  restore_check_b/                定向导出树 + B 失败日志
  restore_check_c/restore_tests.log  C 通过日志（工作树已移除）
  restore_check/ATTEMPT_A_SUPERSEDED.md  尝试 A 的说明（产物已删除）

F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m2/M2-00/attempt_02_repair/   本次审阅修复
  M2-00_report.reviewed.md          修订前被审版本，SHA256 4b007704…4bb0（与回执一致）
  M2-00_summary.reviewed.json       修订前被审摘要，SHA256 c9166101…8ba0（与回执一致）
  M2-00_review.receipt.md           审阅回执副本，SHA256 8390d3fe…2578
  classify_evidence.py              分类脚本（只读仓库，规则见 §3.1）
  evidence_classification.json      200 项逐项分类（路径/字节/SHA256/类别/用途）
  evidence_classification.md        同一分类的人可读表
  repair_log.md                     本轮修复过程、命令、事实核对与结束状态
```

仓库内产物：本报告 `docs/fast_dynamics_m2/M2-00_report.md`、审阅回执 `docs/fast_dynamics_m2/M2-00_review.md`（审阅者写入）与摘要 `verification/fast_dynamics_m2/M2-00_summary.json`，均为未提交、待复审的文件，单个远小于 256 KiB。

## 8. 与上阶段相比

- 新增能力：无（本阶段不实现功能，审阅也确认不需要改引擎/控制器/适配器/loader）。
- 新增可追溯性：M0/M1 实现、测试、入口文档与小型证据摘要现在可从本地提交 `0f7c42d` 恢复；此前只存在于工作区。
- 回归：只跑恢复性冒烟 39 项（见第 5、6 节），未跑旧清单/DR130/v0.5 示例/406 项；工作区代码内容与提交前逐字节一致，因此不影响 M0/M1 报告结论。
- 需要重跑的旧证据：无（未改代码）。若审阅要求修改已提交内容，须以新提交而非 amend 处理，并按指南以新 attempt 出结果。
- 入口登记（审阅 R3 修订）：原入口写着“M2 指南仅编写完成、未执行任何 M2 阶段”。本版已按回执更新 `docs/fast_dynamics_engine_kickoff.md`、本指南的进度补注、根与项目 README、根 `CLAUDE.md`，并在 M0/M1 报告加日期化补注；两处入口均写明“M2-00 检查点已建立、审阅 `FIX_REQUIRED`、等待说明修订后复审；M2-01 未开始；M2 飞行功能尚未实现”，并链接阶段报告与回执。未改写任何 M0/M1 历史验收结论。

## 9. 资源

| 项目 | 值 |
| --- | --- |
| 阶段墙钟 | attempt_01 约 05:27–05:41、attempt_02_repair 约 05:56 开始、结束时间未记录（America/Los_Angeles） |
| 独立 M2 任务数 / 生产运行数 | 0 / 0 |
| 测试内仿真 | 有，次数未计量（见第 6 节），产物写在临时目录并已清理 |
| 涉及文件 | 提交 243；被忽略数据 156；恢复检查另复制 257（B）与 288（C，已删）；本次仅改报告、摘要与入口文档，新增外部分类清单 |
| 外部证据体积 | attempt_01 6,527,248 字节；attempt_02_repair 275,281 字节（分类清单 + 被审版本副本 + 修复记录） |
| 临时占用 | 尝试 A 的 176 MB tar 与解包树已删除；C 的检出已随工作树移除 |

## 10. 异常与失败 attempt

| 现象 | 影响 | 处理 | 证据 |
| --- | --- | --- | --- |
| 索引查询一度把 2 个中文文件名判为不匹配 | 测量工具问题，不是内容差异 | 未加 `core.quotepath=false` 导致；改为显式该选项后 243/243 全部匹配 | `checkpoint_manifest.json`（`all_exact_match=true`） |
| 尝试 A：`tar -xf` 对 3 个非 ASCII 文件名报 `Invalid empty pathname` | 仅影响解包工具；不影响提交内容 | 改用定向导出（B）与 Git 工作树（C） | `commands.log` |
| 尝试 B：7 个 artifacts 测试报 `cannot find source Git baseline` | 导出目录不在 Git 仓库内，引擎按设计要求基线 | 保留失败日志；改用真实 Git 工作树（C）验证恢复 | `restore_check_b/restore_tests.log` |
| 尝试 C 首次全量检出报 `Filename too long`（v03 深层路径） | 环境路径长度限制，与本提交无关 | `git worktree prune` 清理悬挂登记；改 cone 稀疏检出 + `core.longpaths=true` | `commands.log` |
| 从未发生 | — | 无 push、无 tag、无 fetch、无 reset/clean/stash、未删改历史数据、未启动 SITL | 第 2 节 refs 与 reflog |

## 11. 留出保护（审阅 R2 修订）

本阶段未建立、未修改、也未使用任何划分。按实际登记口径：

- `calibration` / `blind_holdout` 集合**尚未建立**（指南安排由 M2-02 冻结），因此本轮**没有做过交集计算**。“集合不存在”不等于“经过计算验证的零交集”，本报告不把它写成泄漏验证。
- 没有读取未来留出数据的证据：测试只读取固定 fixture（开发 family `scene_74f9c65a90cdb4ffd5ed`）与一个读取后即被拒绝的 3 机任务；历史 SITL 结果、已导出数据集与语言产物均未被读取。
- 测试读取的 fixture 属 M0 已登记的 `development_reference`；T1/T4 的 14 个 family 目前全部是开发对照，本阶段没有把它们重新划分为留出。
- `m0_source_index.json`、`m0_evaluation_split.json` 等文件只是被提交，内容没有被解析用于任何开发决策。

## 12. 本修订提交的审阅范围（最终已完成）

请重点核查：

1. 修订后的说明是否与实际一致：§3.1 分类计数与逐项清单、§6 仿真/产物/未计量登记、§8 入口登记，以及它们在摘要 JSON 中的对应字段。
2. 提交边界分类提案是否批准：拟保留 18 文件 / 694,586 字节、拟外置 182 文件 / 1,443,516 字节；两项原待决问题已批准按外置处理，见第二轮回执与 §3.1。
3. M2-01 的清理范围是否按 §3.1 执行（跟踪的 182 个拟外置文件 + 156 个被忽略载荷，共 338 文件），并确认最新树清理不影响 `0f7c42d` 历史。
4. R2 的登记口径是否满足要求：独立 M2 实验为 0、测试内仿真与临时产物如实承认、执行次数按“未计量”填写而非 0 或推测值、输入用途按“读取/执行/历史结果/未来留出”分开。
5. 本轮范围是否克制：`git diff HEAD --stat` 中 `swarm_sim/`、`scripts/`、`tests/`、`requirements.txt` 均为空，HEAD 仍为 `0f7c42d`，无新提交、无 amend、无 push。
6. 环境事实：本机在长路径根目录做全量检出会触发 `Filename too long`，独立复核需 `core.longpaths=true` 或稀疏检出。

## 13. 未完成项

| 未完成项 | 原因 / 归属 |
| --- | --- |
| M1 证据迁移到仓库外、relocation 索引、按 §3.1 清理仓库内产物 | 已获放行，待用户启动 M2-01 |
| `fast_dynamics` 运行/基准/验证入口的外部输出根约束与拒绝覆盖 | 指南划给 M2-01 |
| family 预划分、12 个真实任务登记、初始覆盖矩阵 | M2-02 |
| 三意图四飞法、连续跟踪、2/3/4 机、数值/确定性/性能收口 | M2-03…M2-12 |
| 分类决定 | 已批准，见 §3.1；M2-00 无遗留待决项，实际迁移留给 M2-01 |

## 14. 下一步

**M2-00 已获 Codex 最终 PASS。** 等待用户将 [M2-01 指令](M2-01_instruction.md) 交给执行模型；本轮不执行 M2-01，不迁移、不删除、不提交、不 amend、不 push。

## 15. 历史修订记录（attempt_02_repair，状态为当时记录）

| 项 | 内容 |
| --- | --- |
| 时间与目录 | 2026-10-12；外部 `SwarmData/fast_dynamics/m2/M2-00/attempt_02_repair/` |
| 审阅基线 | 分支 `codex/fast-dynamics`、提交 `0f7c42d`（本轮未变）；`main` / `origin/main` 仍为 `5e45637` |
| 被审版本 | 报告 SHA256 `4b007704c4ea3e7038d8d9e51d71afb37053eb822157489cca2c5fb46e4b4bb0`、摘要 SHA256 `c9166101c2bc24a97128498ca2e8a32686415620dd83e85ea73722b2d22f8ba0`；副本与回执值逐字节一致 |
| R1 修订 | 更正“小型汇总”表述；新增 §3.1、`evidence_classification.json/md`（200 项，含路径/字节/SHA256/类别/用途）；登记 `.gitignore` 不能代替用途白名单；说明历史不因最新树清理而回退 |
| R2 修订 | 更正“无任务/无仿真/无 episode/dataset/描述”口径；新增 §6 登记测试内仿真与临时产物、执行次数未计量、输入用途（含读取后被拒绝的 3 机任务）；§5 注明 A 的原始产物已删除且 `commands.log` 为事后汇总；§9 更正运行计数；§11 更正留出口径 |
| R3 修订 | 更新 `docs/fast_dynamics_engine_kickoff.md`（含实施登记表与指南段）、本指南进度补注、根 README、项目 README、根 `CLAUDE.md`，并在 M0/M1 报告加日期化补注；均写明 M2-00 已建检查点、审阅 `FIX_REQUIRED`、待修订后复审、M2-01 未开始、M2 飞行功能未实现 |
| 未做 | 未改业务代码/测试/依赖/`.gitignore`；未提交、未 amend、未 push；未迁移、未删除任何 M1 证据；未重跑 39 项或 M0/M1 验收；未创建或删除 worktree |
| 状态 | 仍为 `AWAITING_REVIEW`，等待 Codex 复审 |

## 16. Codex 最终修正与放行（attempt_03_record_fix）

用户明确要求 Codex 直接完成第二轮回执的记录修复。修订前的 6 份入口文档、报告、摘要及两轮回执，共 10 文件，已原样备份至外部 `SwarmData/fast_dynamics/m2/M2-00/attempt_03_record_fix/before/`；逐文件哈希见 `before_manifest.json`。

- 当前记录与 attempt_01 提交后的历史快照已分开；当前跟踪差异只含 6 份文档。
- 固定 fixture 只由 execution、artifacts 两个模块读取；core 使用合成数值状态。实际执行次数仍未计量，没有重跑测试。
- 根/项目 README、kickoff 的历史基线、当前检查点、旧 CI 归属和本地提交条件已对齐；未记录的结束时间不再填占位符。
- 分类维持保留 18、外置 182 项；逐样本 completion 与单例配置外置，338 项只是 M2-01 经复制校验后的清理候选。
- HEAD 仍为 `0f7c42d`，业务代码、测试、脚本、依赖和旧证据未修改；本轮不提交、不迁移、不删除、不启动后续阶段。
- 最终结果为 **PASS**，见 [最终回执](M2-00_review_03.md)。这是 Codex 实际静态核验后的放行，不是执行模型自行批准。下一阶段使用 [M2-01 指令](M2-01_instruction.md)。

当前跟踪差异按 Git 根命令 `git diff --binary --no-ext-diff --no-color HEAD --` 的 stdout 原始字节计算 SHA256（未跟踪报告/摘要/回执另行绑定）：
`19dc69cc4275705d97f95af3398607f33a4a3efaccf6345d78906b09a2e1c9c9`

差异字节数：30274。实际核验与最终文件哈希见本轮外部 `validation.json`。
