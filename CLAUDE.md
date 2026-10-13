# 项目交接与本地开发约束

> **2026-10-13 最新停止点：M3 前置修复 A 的字段一致性门禁未通过。** 已改用与 SITL 相同的 10 Hz 导出网格提取 fastsim 事实；M2 的 16 条重算中，两条扫描识别改善，四条快速通过的 turning_rad／inside_dwell_s 也改变，超出“其余字段逐字节一致”的批准范围。532 项离线测试、DR130 260 项和 v0.5 四例通过。代码本地保存，尚未放行 A；未推进短段修复 B、282 条新基线、调参或参数冻结。用户已批准冻结后连续执行内部留出与高速检查，但当前须先解决 A 的验收范围冲突。M2-02B 两组继续封存，不启动 SITL、不推送。见[本轮停止报告](Multi-UAV%20SimpleGC/docs/fast_dynamics_m3_fix_a_stop_report.md)；本补注优先于下方历史状态。

> **2026-10-12 后续：覆盖几何提速完成验证，M3 在来源映射处停止。** 当前冻结 M2-02B 的 213 个校准任务与 r2 只有名称相同，family/场景/输入哈希均不匹配。不得据同名任务配对，不改冻结划分，不启动 SITL；M3 b/c 尚未执行。20 条旧 run 的 120 个 JSON 完全一致；12 正例通过，512 离线测试及旧路径回归通过。4 机扫描 47.549 秒，性能目标未达到，不做范围外优化。见[本轮报告](Multi-UAV%20SimpleGC/docs/fast_dynamics_coverage_performance_report.md)，本补注优先于历史说明。用户授权本地提交，不推送。

> **2026-10-12 最新状态：M2 已完成并停止。** 已修复实际计划阶段标签；固定 12 正例＋4 状态变化负例完整链全部通过，16 条质量合格、64 条描述。离线测试 502/502、DR130 260/260、v0.5 示例 4/4；后处理仅复用相同语义计算，19 个导出文件逐字节不变。用户授权本地提交，不推送；未进入 M3。详见[本轮完成报告](Multi-UAV%20SimpleGC/docs/fast_dynamics_m2/M2_runtime_resume_report.md)（含字段来源表、覆盖与耗时）；旧 P0 和历史产物保留。本补注优先于下文历史阶段状态与旧暂停说明。

更新于 2026-10-12，核对代码基线 `5e45637f2bf63054ed0ace2433fd7c9ea7b075ac`。先读根 [README](README.md)，再读 [快速引擎开发交接](Multi-UAV%20SimpleGC/docs/fast_dynamics_engine_kickoff.md) 与 [实现计划](Multi-UAV%20SimpleGC/docs/fast_dynamics_engine_implementation_plan.md)。

## 当前方向和边界

- 现有代码已实现 SITL 的 v0.6.1 时间契约；快速引擎 M0/M1 已本地落地，包含适配备忘/独立契约、确定性内核、双机快速通过完整数据链与回归。M0/M1 最终本地验收已通过，先读 [M0/M1 报告](Multi-UAV%20SimpleGC/docs/fast_dynamics_engine_m01_report.md)核对结果和未完成项。**M2 已启动分阶段执行：M2-00 已建立本地检查点 `0f7c42d`，最终审阅 `PASS`（见最新放行回执）；M2-01（M1 证据迁移与外部输出约束）已执行、已获 Codex 最终 `PASS`、已提交 `16b7cb7`；M2-02B 新来源补充已获 PASS，M2 飞行功能尚未实现，不能宣称三意图四飞法、校准或生产验收已完成。** 进度见 [M2-00 报告](Multi-UAV%20SimpleGC/docs/fast_dynamics_m2/M2-00_report.md)、[M2-01 报告](Multi-UAV%20SimpleGC/docs/fast_dynamics_m2/M2-01_report.md)与[审阅回执](Multi-UAV%20SimpleGC/docs/fast_dynamics_m2/M2-00_review_03.md)。
- 用户当前要求仅本地开发、测试、记录，暂不推送、建 PR、打标签或以远端 CI 作为推进条件；本地提交仅限用户明确启动 M2 阶段时按指南做的检查点提交（M2-00 与 M2-00 记录修正已用此例外：`0f7c42d`、`57cca91`，后续阶段启动时方可提交上一轮获准差异）。保留已有未提交文档和新计划，不 reset/clean。**M2-01 起，快速引擎的样本、dataset、原始日志、基准与失败证据只能写仓库外的全新 attempt（缺省根为仓库同级 `SwarmData/fast_dynamics`），入口会拒绝仓库内路径、已存在 attempt 与联接越界；M1 证据树已迁移到 `SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/`。**
- 开发位置为 `Simulation-dev/Multi-UAV SimpleGC`。原 `Simulation` 是冻结归档；`Simulation-dev-wip` 属另一会话；两者不作为本阶段写入范围。大型历史证据在仓库外 `SwarmData`。
- 不启动 SITL，不续跑旧批次，不准备 r3。新引擎本地合成验证按实现里程碑执行，使用独立输出及新后端来源身份。

## 现状摘要

v0.5 已冻结 260 次运行，252 次质量合格。v0.6 三意图及四种生产飞法已实现，r1 在 296/900、r2 在 465/900 后停止，均未 finalize。v0.6.1 已发布 `v0.6.1-time`（实现 `bd1f40a`），支持公共源时间、确定性参考机、10 Hz 仿真网格及速度换算；正式和子集 prepare 支持 `--base-port`，缺省 19100。

T1（K2×1）与 T4（K4×1）最终通过，各 42/42 执行、41/42 质量合格并 finalize；T2（K2×2）11/42 后规则暂停、不通过；T3/T3+ 取消；T5（K6×1）15/42 后规则暂停，9/15 合格、6/15 时钟不可用，排空后停止，不 finalize、不恢复；T6 未准备未运行。自动检查已暂停。分母、证据和标准纠错见 [最终验证报告](Multi-UAV%20SimpleGC/docs/v0.6.1_time_validation_report.md) 的最终章节及仓库外收尾回执。

本机实际条件为**非独占**，后台应用可以常驻，旧独占门槛已由用户取代。SITL 备用推荐 K4×1、首批错峰 30 主机秒，r3 尚未准备。不能从历史报告的运行前授权重新启动任务。

## 环境与检查

Windows 使用 PowerShell 7，首次检查 `$PSVersionTable.PSVersion`。已验证路径：`C:/Users/shy/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe`。

Python 前读取项目 `.conda-env`（当前 `llm`）和 `AGENTS.md`；使用本机 `C:/Users/shy/anaconda3/Scripts/conda.exe run -n <环境> --no-capture-output python -B ...`。不自动切换 base。新引擎已在 `requirements.txt` 声明 `numpy==2.5.3`；本地使用 Python 3.12.3 / NumPy 2.5.3。入口为项目 `scripts/run_fast_dynamics.py`，仅输出到全新目录，配置严格分为七组。

Git 状态在 `Simulation-dev` 根检查，Python 通常在 `Multi-UAV SimpleGC` 执行。无归档依赖的离线测试清单在 `.github/workflows/unit-tests.yml`；远端历史 367 项通过绑定 `5e45637`，不代表新本地代码已测试。全量历史集成测试的既有依赖/断言失败见 v0.6.1 实施报告。

## 研究与证据规则

- P0 研究正确性（模型输入、标签/描述、family 划分、时间/坐标、完整性与可复现）优先于 P1 当前里程碑；P2 记录诊断，P3 扩展按计划触发，不提前实现完整飞控。
- 遇到异常先回答“它会让哪项研究结果出错”；无法判断时做一轮影响定位。不得绕过冻结验收门槛或改写失败判定。规则误报先判断必要性，再考虑删除、简化或降级诊断，最后才加例外；更改冻结规则须有当前用户依据。
- 旧原始数据、分析、标签、语言产物、台账和受保护证据不修改、不删除；派生结果另存并绑定来源。不通过补飞、重试洗掉失败。
- 任务成功、数据质量、语义一致分别判断；未知不能填通过。报告按结论、异常、证据位置组织，计数带分母，并说明测量范围、版本和局限。
- 新后端用独立 `sim_clock` 与来源协议，不伪造 FCU、SIM、固件或未实现的姿态/IMU。六维输入兼容不代表旧协议校验自动兼容。
- 当前 T1/T4 为同源 42 任务、14 family，只作开发对照；先合并来源/重复测量再划分。同一 family 跨意图、后端、参数变体不得泄漏；98% 一致等候选阈值不自动成为门槛。
- 新输出为半开网格，旧端点规则保持；M3 先做确定性校准，M4 才增加共享环境/观测扰动与两类输出。未提交实现以执行文件内容哈希绑定来源，不要求先提交才能测试。
- 如以后重新运行 SITL 批次，期间不得修改它绑定的受保护源码；本阶段不使用旧监测器/控制器作为开发入口。
- 正文内公式使用 `\(...\)`；代码摘录从源码原样核对并标注位置，不能把提案当实现。

## 每个本地里程碑完成后

更新 `docs/fast_dynamics_engine_kickoff.md` 的实施登记、根 README 当前范围及必要契约，记录改动、实际测试、失败/未完成项与下一个工作包。完整设计在实现计划中维护，历史 SITL 报告保留原判。本地工作可连续推进，不需要先发布 GitHub。


2026-10-12 M2-01 历史收口补注：M2-01 最后 ID 前置校验已由 Codex 完成，针对性检查 66/66 通过；M2-01 已获 PASS 并保存到 `16b7cb7`；原 M2-02 来源阻塞已由获准的 M2-02B 新来源补充解除，该历史节点的下一步为 M2-03 设计（现已执行并修复待审，以头部为准）。见 [最终回执](Multi-UAV%20SimpleGC/docs/fast_dynamics_m2/M2-01_review_03.md)与[M2-02 任务计划](Multi-UAV%20SimpleGC/docs/fast_dynamics_m2/M2-02_instruction.md)。
