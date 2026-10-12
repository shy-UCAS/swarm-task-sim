# M2-01 可转发执行指令

本文件仅提供下一阶段指令，不表示已经开始执行。用户将下方指令发送给执行模型后，才启动 M2-01。

```text
我现在只授权执行 M2-01：迁移 M1 证据并约束快速引擎的外部输出。完成后停止，等待 Codex 审阅，不进入 M2-02。

工作目录：
F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-dev/Multi-UAV SimpleGC
Git 根：其父目录 Simulation-dev
外部输出根：
F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics

先阅读根 README、CLAUDE、项目 AGENTS、.conda-env，以及：
docs/fast_dynamics_engine_m2_staged_guide.md 的通用指令与 M2-01；
docs/fast_dynamics_m2/M2-00_review_03.md 的最终 PASS 回执；
docs/fast_dynamics_m2/M2-00_report.md 和 verification/fast_dynamics_m2/M2-00_summary.json。
原 M0/M1 检查点为 codex/fast-dynamics / 0f7c42d8688880b1d8e1a416184383a94a5ae123。

1. 阶段起点与本地检查点
   核对当前分支、HEAD、工作区、PASS回执及其所绑定的差异/报告/摘要哈希。
   不重复建分支，不重建M0/M1检查点。若有本轮放行范围外的新修改，保留并辨明归属。
   本次启动授权按指南将M2-00已获PASS的文档修订、报告、摘要、三轮回执和本指令
   用显式文件白名单保存为新的本地提交；检查staged diff，不使用无筛选git add -A。
   不amend、不reset、不改写0f7c42d、不push、不打标签。登记新检查点SHA。
   旧回执中的工作树哈希是提交前历史状态，提交后diff变空是正常的，不回填旧回执。

2. 冻结迁移源清单
   为 verification/fast_dynamics_m01 的全部文件记录相对路径、字节数、SHA256。
   当前预期为356文件、30,216,091字节；实际有变化时先定位并记录，不能盲按数量删除。
   已批准分类清单：
   SwarmData/fast_dynamics/m2/M2-00/attempt_02_repair/evidence_classification.json
   SHA256 = fc2a4e66d46f95d9da8f2e7923675c3ef6ac24cf425873a321751d1f48f55b3c
   原文件拟保留18项；外置182项跟踪文件，加156项忽略载荷，共338个清理候选。
   8个逐样本completion、2个单例*_config均外置；阶段级completion随阶段汇总保留。
   逐项复核分类路径与源文件，不能只依赖扩展名、目录匹配或.gitignore。

3. 先复制并核验，暂不删源
   在 SwarmData/fast_dynamics/m01_archive/<全新migration_id>/ 复制完整356项证据树，
   包括失败、中间attempt、日志、所有原始清单，以及将在仓库保留的18项副本。
   比较相对路径集合、逐文件SHA256、总字节数；任何不一致都保留原件并停止清理。
   原证据保持字节不变，不更新旧manifest、completion、源身份、标签或latest指针。

4. 验证新位置确实可用
   从新路径验证M1成功、真实失败、超时未知样本的公共加载/审计等适用消费者，
   确认5次成功性能证据、最终回归、来源索引及中间attempt都可追溯。
   不能因为消费者仍通过旧绝对路径读到仓库载荷，就认定迁移通过。
   必要时记录实际读取路径，或增加显式路径解析/独立relocation索引及针对性测试，
   证明样本证据读取落在新归档内；业务源码从项目读取不受此限制。
   历史run_directory等保留其来源含义，新存储位置写独立索引，不全树替换路径。
   若需重新导出，派生结果写全新目录，不覆盖或冒充原始副本。
   不为迁移放宽完整性校验或破坏旧协议调用；如果必须扩大协议改动，报告最小问题。

5. 验证通过后才清理
   只清理显式清单内、外部副本已逐项验证且新位置可用的338个候选文件。
   删除前检查解析后的绝对路径位于本项目 verification/fast_dynamics_m01 内，
   拒绝目录联接/路径逃逸；用单一PowerShell路径流程，不拼接其他shell执行删除。
   保留已批准18项，另增小型迁移摘要/索引。旧Git历史保持不变。
   更新M0/M1报告、入口和链接，标明新绝对位置、migration_id和哈希；
   历史验收日期、结果与源身份不变。任何验证失败都不删除对应原件。

6. 新输出只能进入外部根
   修改 run_fast_dynamics、benchmark_fast_dynamics、verify_fast_dynamics_m01 等必要入口，
   保证样本、dataset、原始日志、基准及失败证据写外部输出根的全新attempt。
   规范化路径后检查归属，拒绝仓库内输出、已存在attempt以及联接导致的越界；
   错误要在创建部分产物之前明确返回。配置错误/真实运行失败保留适当失败证据。
   不改变原SITL入口，也不把机器绝对路径硬编码进公共库、导致其他环境无法使用。
   输出根的配置与默认行为要写明；测试使用外部隔离目录，不全局修改系统TEMP。
   原有M1测试/库API仍需兼容，不能为让路径测试通过而删除验证或修改任务成功规则。

7. 必要验证和交付
   跑路径保护正反例、迁移相关消费者回归、一个M1完整链冒烟及受影响的既有测试。
   不重跑无关大规模实验，不开展M2-02数据筛选或盲测读取。
   每次尝试使用新目录，失败保留；绑定输入、配置、执行源码及结果哈希。
   仓库只留代码、必要小型输入fixture、报告和小型JSON，原始测试/运行证据放外部。
   报告迁移前后文件数/字节/哈希、新路径、实际清理清单、保留清单、公共链结果、
   路径测试结果、实际命令/退出码/失败项、业务改动范围和最终工作树状态。
   写 docs/fast_dynamics_m2/M2-01_report.md 与
   verification/fast_dynamics_m2/M2-01_summary.json，状态AWAITING_REVIEW。
   本轮新代码/迁移变更留待审阅，不自行提交或宣布PASS，完成后立即停止。

Windows使用PowerShell 7，首次核对版本；Python按项目.conda-env经conda run运行。
外部目录权限受限时走正常权限机制，不回写仓库绕过限制。
不修改冻结Simulation、Simulation-dev-wip和旧SITL证据；不启动SITL、续跑旧批次、
准备r3、推送、PR、M2-02或M3。不扩展飞行功能、控制算法或语义阈值。
```
