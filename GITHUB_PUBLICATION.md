# Git 发布与归档说明

2026-10-07，精简发布已通过 [PR #1](https://github.com/shy-UCAS/swarm-task-sim/pull/1) 合并到远端 main；本机新开发目录已建立。当前状态见[根目录 README](README.md)。冻结原仓库的 main 保持在 `8eaf583bc5a946e935d8ff0f410cb798fda6a6e8`，
全部运行证据、原判定和未推送提交继续保留。发布候选以远端 main 的
`b9307bd256ef787c5e494f71dc38cf673cb138df` 为父提交，汇总当前代码、配置和报告，避免把 9 个含完整运行数据的
本地提交作为发布分支的祖先。

## 发布内容

- 源码、单元测试、任务/场景/质量配置、固定版本 SITL 依赖。
- 正式 v05c 任务输入、原始台账、停止快照、验收摘要及历史报告。
- B001、B002、B037、B098 共 4 个 byte-for-byte episode 示例及 sample_index.json。
- 数据发布索引和逐文件分类清单 github_publication_inventory.csv。

完整 raw JSONL、飞控 BIN/eeprom、execution、analyses、runtime_snapshot、全量导出与描述层
不在发布候选中。文件没有从本机删除。分类清单中的 archive_local 表示从发布树中排除，
不表示已经上传到外部存储或形成独立完整数据归档。Git bundle 备份的是已跟踪历史，
不包含工作区中从未跟踪的文件。

## 使用边界

示例用于格式查看和加载检查，不能作为训练/评测数据集。原始 family、判定、哈希和
split 都保留在 sample_index.json；没有重新划分数据。保留的报告和台账可能引用未包含的
历史证据路径或原机器绝对路径；重现历史集成验收需要恢复对应完整归档。
完整的历史测试套件也可能依赖这些归档，精简副本不承诺脱离归档通过全套测试。
此次整理没有启动 SITL，没有修改生成代码、阈值、门禁或冻结判定。

## Git 操作边界

原 main 不做 reset/rebase/filter，不切换到精简分支，不从原工作区执行 git rm。
新 .gitignore 仅属于发布候选；原冻结工作区用 .git/info/exclude 忽略本地准备目录。
只加 .gitignore 不能清理已跟踪文件，所以候选提交的树已经排除清单中的大文件。
原始历史仍在冻结分支和 bundle 中，因此原 .git 体积不会因本次准备缩小。

发布候选仍继承远端现有历史；远端 main 已经有约 2.19 GiB 的展开文件树。
候选当前文件树缩小不等于整个克隆历史同样变小。如以后需要清理已发布历史，
应另外决定历史重写或新建代码仓库，本次没有执行这两项操作。

发布前已核实远端 main，用户明确授权后仅推送发布分支，并在 GitHub 检查通过后合并。
合并提交为 `cc4bcb77f4b9dde2d6d993e582ed6ec1edb801bb`；未推送冻结分支或原来的 9 个本地数据提交。
后续在新开发目录围绕 main 工作，不需要继续同步临时整理分支。

发布候选的 GitHub Actions 运行 15 个不依赖完整历史归档的测试模块（本机共 141 项）；
完整历史集成测试仍保留源码，需要完整证据才能运行。原冻结 workflow 未修改。

## 运行依赖补齐与验证

补齐两组 WP-S 基线共 6 个 JSON（474,774 字节），其来源受原确认链的 SHA256 约束。
这些文件原先存在本机但没有进入冻结 Git 提交；此次原样纳入候选，不更改门禁、参数或判定。
其余运行数据继续被忽略，基线目录中的 raw.jsonl 也仍被忽略。
从候选 Git 树导出到独立目录后，141/141 项测试、真实固件/参数预检、
两种意图的任务规划与校验、4/4 个 episode 加载通过。检查未启动 SITL。
验证记录见 Multi-UAV SimpleGC/docs/github_publication_checks_runtime.json，
新电脑的环境和数据边界见 Multi-UAV SimpleGC/docs/github_migration.md。
离线通过不代表已经在另一台物理电脑进行实际飞行，也不支持脱离完整归档接续历史批量控制器。
