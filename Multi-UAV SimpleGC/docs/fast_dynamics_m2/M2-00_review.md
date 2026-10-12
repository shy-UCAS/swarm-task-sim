# M2-00 审阅回执：FIX_REQUIRED

审阅日期：2026-10-12。审阅对象：M2-00 / attempt_01。

**结论：FIX_REQUIRED。M0/M1 本地检查点的核心目标已经实现，未发现本轮破坏代码或已核验 M1 证据；但提交边界和测试范围的汇总不准确，入口状态也未同步。先完成本文件的有限修复，再复审，不进入 M2-01。**

本次仅执行只读 Git/文件/哈希/日志/测试源码核查并编写审阅回执；没有修改业务代码、提交、迁移、启动 SITL、运行 M2 任务或读取盲测结果。没有独立重跑 39 项测试，也没有重跑全部 M0/M1 验收。

## 1. 审阅身份与证据绑定

项目根：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-dev/Multi-UAV SimpleGC`。

外部执行证据根：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m2/M2-00/attempt_01/`。

| 对象 | 核验值 |
| --- | --- |
| 分支 | `codex/fast-dynamics`，无 upstream |
| 被审提交 | `0f7c42d8688880b1d8e1a416184383a94a5ae123` |
| 父提交 | `5e45637f2bf63054ed0ace2433fd7c9ea7b075ac` |
| 提交 tree | `dfd67f0495ebf76aea52bb9d0a429b7927a5369a` |
| 审阅前跟踪文件 diff | 空；`git diff --quiet` 返回 0 |
| 阶段报告 SHA256 | `4b007704c4ea3e7038d8d9e51d71afb37053eb822157489cca2c5fb46e4b4bb0` |
| 阶段摘要 SHA256 | `c9166101c2bc24a97128498ca2e8a32686415620dd83e85ea73722b2d22f8ba0` |
| 实施指南 SHA256 | `4b9b43b9aed3955ffaa40f19854c6470065b1316bcb66f69f91e6fc76e39a7b6` |
| `checkpoint_manifest.json` SHA256 | `8a549d9c143a99d2cad8fa41c3717f21d65e9ae21c67daaaf4f7e1a322fb5c2f` |
| `source_snapshot.txt` SHA256 | `38c5d0cf401a0d5e018aaa7719cde22f676142c247ed3fd033143e8c45a91b2f` |
| `commands.log` SHA256 | `0227f94471ee07143377c42e348de15a13bcf788765a66dff2de7ab89eb661c4` |
| C 恢复测试日志 SHA256 | `783052606f4b1a5c4c91c8ba0a011f1d596a2ec09c56eaf71e50dc06e1ed18d1` |
| `tests/test_fast_dynamics_artifacts.py` SHA256 | `233431ef4e1e74ffc608f21f5d358bcfab49e87430b03162bd6de868b29a3f3f` |
| `tests/test_fast_dynamics_execution.py` SHA256 | `869efc1689a110d90b6f9b53edb93e82563d65b55ededc9c8d206c4e7dfcf958` |

报告修订后哈希自然改变；本回执保留原值作为本轮审阅身份，不跟随新报告回填。

## 2. 已独立核验的结果

| 检查 | 实际结果 | 说明 |
| --- | --- | --- |
| 提交清单与 Git 对象 | 243/243 一致 | `diff-tree` 的文件集合与 manifest 完全一致 |
| 每文件身份 | 243/243 一致 | 重算当前 SHA256；Git `hash-object`、提交 blob 与 manifest 均匹配 |
| 工作区跟踪修改 | 无 | 审阅前只有阶段报告/摘要目录为未跟踪 |
| M1 证据树 | 356 文件、30,216,091 字节 | 与报告计数一致；计数本身不等于逐字节证明 |
| M1 最终验收源码 | 68/68 哈希匹配 | 读取 `final_verification_01/verification.json` 的源码清单并重算 |
| M1 最终样本分析产物 | 7 个 manifest、98/98 哈希匹配 | 重算各 `artifact_sha256` 指向的实际文件，包含被忽略载荷 |
| M1 完成标记 | 8/8 匹配 | 核对最终 verification 与各 report 的 completion 绑定 |
| C 恢复测试日志 | 39 个测试条目；`Ran 39 tests in 26.383s`；`OK` | 执行者提供的测试证据，非本审阅者重跑 |
| B 失败日志 | 39 项、7 errors | 错误栈对应 `_git_revision()` 缺少 Git 基线，报告的原因合理 |
| 本地 refs/worktrees | 符合报告 | main/origin/main 仍为父提交；工作树为开发区及既有 wip 两条 |

因此，“已保存可恢复的 M0/M1 代码检查点”有充分证据。C 的独立工作树已移除，审阅无法重新检查其当时环境；当前源码匹配、原日志和 Git 对象共同支持恢复性结论，但不能把原日志说成审阅者独立复跑。

本地 refs/reflog 未显示远端变更，也与“没有推送”的执行声明一致；**仅靠本地 refs 不能证明历史上绝无 fetch/push/PR 操作**。本轮未联网查询远端，不将这项声明升级为全面审计结论。

## 3. 必须修复的三项

### R1：提交文件按扩展名和 .gitignore 归类，误把逐样本载荷说成汇总

定位：`M2-00_report.md` 第 18、55、69–71 行及 `M2-00_summary.json` 的 `commit_inventory`。对应指南 M2-00 第 3、4 条。

报告称“批量 episode/dataset…排除”，但提交的 200 个证据文件中，有 **180 个文件位于 8 个逐 episode 结果目录，共 1,443,395 字节**。这些文件既有 report/manifest，也有实际 `run/analysis/labels.json`、`events.json`、`compiled_scene.json`、`language/descriptions.json`、事实文件等，不能整体称为“小型结果摘要”。例如：

- `verification/fast_dynamics_m01/final_verification_01/success_01/run/analysis/labels.json`
- `verification/fast_dynamics_m01/final_verification_01/success_01/run/analysis/events.json`
- `verification/fast_dynamics_m01/final_verification_01/success_01/language/descriptions.json`

`.gitignore` 决定 Git 默认看见什么，不代表用户允许提交什么。将“所有已修改文件 + 所有 Git 可见未跟踪文件”装入显式数组，仍没有完成按用途筛选；数组形式不自动满足白名单要求。

影响：当前提交确实保存了实现，但并未严格遵守“仓库只保留汇总”的边界；M2-01 不能继续按“JSON 小就留库”处理，否则逐样本语义载荷仍会留在仓库。

**修复目标：** 如实登记这项偏差，按内容列出待外置/待保留清单，并说明清理最新树不会清除已存在 Git 历史。不要将 180 个文件全部称为不合规文件，它们内部的摘要与载荷还须逐项分类。

**处置边界：** 本审阅不要求为这约 1.44 MB 的逐样本目录文件重写历史。保留 `0f7c42d`，不 amend/reset/filter-repo。修复本轮说明后，M2-01 再按已批准流程复制、核验和清理最新树；这不等于宣称原提交边界符合要求。本轮不提前执行迁移或删除。

### R2：“没有运行任何任务/生成任何 episode”与实际测试源码矛盾

定位：`M2-00_report.md` 第 108、142、159 行；摘要的 `mission_results`、`holdout_protection`。

实际证据：

- `tests/test_fast_dynamics_execution.py:64` 读取固定 TaskSpec；第 65 行及后续测试实际调用 `run_mission`，还包括半步长、顺序/worker 等执行。
- `tests/test_fast_dynamics_artifacts.py:33` 读取 fixture，第 34 行运行任务；第 46 行写 episode，第 53 行导出 dataset，第 74 行生成描述。第 83、104 行还实际运行超时和低速失败状态。
- 这些测试名出现在 C 的 39 项通过日志中。测试使用 `TemporaryDirectory`，结束清理不代表从未生成过产物。

这些是合理的 **M1 恢复性测试**，不构成擅自推进 M2。问题在于报告把“没有单独开展 M2 实验/生产批次”错误扩大为“没有任何仿真、轨迹、标签或 family 使用”。这种统计口径若沿用到后续阶段，会使数据使用登记失真。

**修复目标：** 区分独立 M2 任务批次与测试内仿真；登记测试实际读取的输入和用途，承认生成并清理了临时 episode/dataset/描述。任务执行次数未被原日志计量时填“未计量/无法从日志准确还原”，不能补造精确数，也不能填 0。39 是测试用例数，不是 episode 数。

已知 M1 fixture 对应开发 family `scene_74f9c65a90cdb4ffd5ed`；另检查拒绝范围测试读取的 `missions/v3/rapid_passage_route_v06.json`，按实际读取/接受执行情况登记，不把读取输入与成功运行混为一谈。没有证据表明读取了未来盲测，但尚未建立集合时，不能把“集合不存在”写成经过计算验证的零交集。

另外，A 的原 tar/解包树已删除，`commands.log` 自述是事后汇总而非原始完整输出。保持这种局限说明，不能再说“三个 attempt 的全部原始证据都已保留”；无需重造 A 的日志或重跑整个恢复过程。

### R3：当前入口仍声称任何 M2 阶段都未执行

定位：`docs/fast_dynamics_engine_kickoff.md:126`。阶段报告已经主动指出此问题。

“M2 飞行功能尚未实现”仍正确；“未执行任何 M2 阶段”在 M2-00 建立检查点后已不正确。这会使下一个执行窗口重复建分支或提交，削弱逐阶段流程的入口作用。

**修复目标：** 更新 kickoff 及确实存在同类断言的当前入口，写清“M2-00 检查点已建立，审阅 FIX_REQUIRED，等待说明修订后复审；M2-01 未开始；M2 功能尚未实现”，并链接本回执与阶段报告。指南开头的“编写本文件时尚未执行”可保留为有日期的历史说明，但需区分当前进度；不全局改写 M0/M1 历史验收记录。

## 4. 不要求修复/不构成阻塞的事项

- 提交 subject 的 `# ` 不影响代码恢复或本阶段目标，不要求改提交信息，不要求 amend。
- B 失败而 C 通过，是已解释的恢复路径差异；本轮不要求将产物写入改成脱离 Git 也可运行。
- 未重跑 367 项旧清单、DR130、旧示例或完整 406 项，不违反只保存检查点的本阶段范围。不能把历史结果列成本次实测即可。
- 没有迁移数据和修改输出入口，是正确的阶段边界，继续保留给 M2-01。
- 本次没有发现需要修改引擎、控制器、适配器或公共 loader 的问题。

## 5. 可直接转发给 DeepSeek 的修复指令

```text
仅修复 M2-00 的审阅问题，不进入 M2-01。
先读 docs/fast_dynamics_m2/M2-00_review.md，结论为 FIX_REQUIRED。
基线保持 codex/fast-dynamics 的 0f7c42d8688880b1d8e1a416184383a94a5ae123。

1. 修正 M2-00_report.md 和 M2-00_summary.json 的提交边界说明：
   200个证据文件不全是汇总；180个位于逐episode目录，包含标签/事件/描述等载荷。
   只读逐项分类，生成“拟保留汇总/脚本”和“拟外置逐样本载荷”的明确清单，
   每项有路径、用途、字节数、SHA256和分类理由。大清单放全新外部 repair attempt，
   仓库只留小型汇总/链接。登记 .gitignore 不能代替用途白名单这一执行偏差。
   说明这些文件已进入0f7c42d历史；后续清理最新树不会清除历史。
   本轮不迁移、不删除、不修改旧M1产物，不改.gitignore，不重写Git历史。

2. 核对3个恢复测试模块的实际调用，纠正“无任务/无仿真/无episode/dataset/描述”。
   写明没有开展独立M2任务批次，但执行了M1测试内仿真和临时完整链。
   登记实际测试输入及开发用途；精确调用数未经计量就填未知/未计量，不能填0或猜数。
   区分读取TaskSpec、执行任务、读取历史结果及未来留出数据，不用空集合冒充泄漏验证。
   保留B失败和C通过；A原产物已删、命令日志为汇总等局限如实注明，不伪造原始日志。
   将此前报告/摘要先保存到外部repair attempt并核对本回执列出的原SHA256，再修订。

3. 更新kickoff及实际需要更新的当前入口，写明M2-00检查点已建但待修复复审，
   M2-01未开始，M2飞行功能尚未实现。链接阶段报告和本review。
   不把本轮提前写成PASS，不篡改历史M0/M1验收结论。

4. 本轮只改上述报告、摘要、入口文档，新增分类证据；不改业务代码/测试/依赖。
   无需重跑39项或完整M0/M1，也无需创建或删除worktree。
   做文档/JSON/路径/计数/哈希一致性检查，证明HEAD未变、业务代码差异为空。
   旧attempt_01与本review保留；新报告补修订记录，状态仍为AWAITING_REVIEW。
   不提交、不amend、不push，不执行M2-01。完成后停止，等待Codex复审。
```

本轮修复通过后可放行到 M2-01；不会因报告更正要求重复实现 M0/M1。下一阶段执行仍需用户发送明确启动指令，本回执不构成迁移授权。
