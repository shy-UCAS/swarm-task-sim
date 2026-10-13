# 覆盖几何提速与 M3 来源核对

日期：2026-10-12（本机时间）。覆盖几何改动已完成并验证；30 秒性能目标未达到。**M3 在来源映射处停止，尚未运行未校准基线或提出基于实测的调参门槛。** 用户最新指令要求任务不属于 r2 时立即停止 M3，且不新建 SITL 批次。

## 1. 实际改动

`swarm_sim/mission_evaluation.py` 新增 `_covered_cells`：对轨迹点按横坐标建立索引，对线段使用保守包围盒筛选，再用 NumPy 批量计算距离。接近半径阈值的结果退回原 `math.dist` / `_segment_distance` 标量判据；特殊大坐标也使用原实现。仍比较原来的 `radius_m + EPS`，没有用平方距离替换判定。

网格中心、枚举顺序、网格分辨率、高度带、有效服务窗口、点/线段证据、采样密度、语义阈值及成功/未知口径均未改变。有效点计数仍来自全部原始证据。模型、跟踪器、动力学参数及上轮语义复用机制没有修改；语义版本保持不变。

新增 `scripts/verify_coverage_geometry.py`，只读旧开发 run，重算标签、语义验证、阶段窗口，经过公开加载、审计和描述入口，向新目录保存结果并比较字段和文件字节。新增 10 项几何测试并加入离线 CI。

## 2. 等价性证据

基线来自 `SwarmData/fast_dynamics/m2/M2_runtime_20261012/attempt_02_resume/`：`acceptance_01` 的 12 正例＋4 负例，及 `baseline_four_patterns` 的 4 条性能基线。原始数据未改写。

| 比较 | 结果 |
| --- | --- |
| 20 条旧 run 的所有标签、判定、覆盖计数及派生字段 | 完全一致 |
| 每条的 labels、semantic_validation、phase_windows JSON | 60/60 文件逐字节一致 |
| 每条重新生成的 facts、descriptions、language_manifest JSON | 60/60 文件逐字节一致 |
| 浮点不同字段 / 最大差值 | 0 个 / 0；差异表为空 |
| 12 正例重新飞行后的轨迹、事件、标签、语义、窗口、质量、约束、任务和规划 | 144/144 文件逐字节一致 |
| 原始覆盖格定义、每机/并集/重复计数、leave-one-out 比例 | 包含在上述完整标签比较中，全部一致 |

144 文件比较每条包括 observations、truth、support_truth、support_observations、events、labels、semantic_validation、phase_windows、quality、execution_constraints、task、compiled_scene。新运行的源码来源哈希和新路径不同，**不宣称整个新 attempt 的所有文件逐字节相同**；20 条旧 run 的重新派生产物确实全部逐字节相同。

## 3. 12 正例完整链耗时

单位：主机秒。前值取已通过的上一轮验收，后值为本轮全新目录串行重飞；两边都启用相同语义复用。范围包括任务/配置读取、动力学、分析、导出、审计、事实/描述、加载、最终落盘，不含 Python 进程启动。测量期间未并发运行本轮回归或其他性能任务；桌面并非独占，多次重复的统计置信区间未测，因此非几何任务的小幅涨跌不解释为优化收益。

| 飞法 | 机数 | 修改前 | 修改后 | 前/后 |
| --- | ---: | ---: | ---: | ---: |
| 往返扫描 | 2 | 16.741 | 6.693 | 2.50 |
| 往返扫描 | 3 | 55.395 | 14.652 | 3.78 |
| 往返扫描 | 4 | 289.253 | 47.549 | 6.08 |
| 回字形 | 2 | 8.844 | 4.496 | 1.97 |
| 回字形 | 3 | 32.226 | 9.156 | 3.52 |
| 回字形 | 4 | 116.956 | 16.048 | 7.29 |
| 巡逻 | 2 | 15.351 | 17.600 | 0.87 |
| 巡逻 | 3 | 19.840 | 20.913 | 0.95 |
| 巡逻 | 4 | 51.885 | 49.342 | 1.05 |
| 横队快速通过 | 2 | 1.989 | 2.348 | 0.85 |
| 横队快速通过 | 3 | 5.375 | 4.707 | 1.14 |
| 横队快速通过 | 4 | 14.715 | 12.771 | 1.15 |
| **合计** | **12 条** | **628.569** | **206.275** | **3.05** |

12/12 完整链通过，成功判定和质量状态保持。4 机往返扫描 **47.549 秒，未达到 30 秒目标**；4 机回字形为 16.048 秒。没有降低采样或跳过任何检查来达标。

另对 4 机往返扫描做一次分段剖析，总计 41.504 秒。该次带计时包装、另一个 run ID，不替代上表的正式比较值。耗时前五个互斥阶段：

| 阶段 | 秒 |
| --- | ---: |
| describe_dataset：事实与描述生成，含内部加载/验证 | 17.910 |
| run_mission：动力学执行 | 10.637 |
| write_episode：分析与写出 | 6.936 |
| audit_dataset：审计 | 2.049 |
| 最后一次 load_episode | 1.985 |

第六项 build_dataset 为 1.969 秒。内部计时（与上表重叠，不相加）：覆盖几何 8 次仅 **0.620 秒**；实际语义计算 1 次 2.814 秒；约束计算 7 次 8.583 秒；支持轨迹读取 6 次 1.545 秒。剩余耗时主要位于事实/描述、动力学和校验链，本轮按要求只报告，未进一步优化。

## 4. 测试与实际局限

- 新增几何测试 10/10：手算边界、相邻浮点、零长段、不跨缺口连接、非整格尺寸、随机/旋转/平移和极端尺度对原标量 oracle、重复/乱序证据、1 与 2 个独立进程输出一致。
- 完整离线 CI：44 模块，**512/512**，0 skip，118.571 秒，exit 0；其中包括旧高度带、缺测屏障、窗口裁剪及多机覆盖手算用例。
- DR130：**260/260**，differences=[]；v0.5：一个测试实际检查 **4/4** 个冻结示例，特征、标签及旧元数据均保持。
- Windows 路径测试中 3 个 junction 实际执行；3 个 symlink 因系统权限限制使用已有模拟解析分支，不宣称真实 symlink 创建成功。
- 本轮验收和计时使用 1 worker；几何单元验证比较 1/2 进程。没有引入新的多进程生产或 M3 批处理实现，也没有将此单元结果说成 213 个任务的并行验证。

## 5. M3：参考来源与冻结划分不匹配

当前有效入口仍为 `verification/fast_dynamics_m2/evaluation_split_current.json`，未改变任何划分。它指向 `split_2026101202_m2_02b_v1`：**generation_seed=2026101203**、校准 71 family/213 任务、盲测 71 family/213 任务，状态 `FROZEN_INPUTS_ONLY`，明确 `reference_episode_available=false`。

这与早期“从 r2 其余 family 划分”的设想不同：M2-02 复核发现原 r2 全部 family 已有开发诊断使用，因此 M2-02B 经授权生成新的、排除历史关联的来源。原 BLOCKED 划分保留，未被重新启用。过程见 [M2-02B 报告](fast_dynamics_m2/M2-02B_report.md) 第 1、4 节和 [复核回执](fast_dynamics_m2/M2-02B_review.md) 第 3 节。

按照本轮补充指令，只读 r2 `plan.json` 和两个分片 `ledger.json` 的身份/尝试顺序字段，比较当前校准任务与 r2 的 mission_id、family、规范场景哈希和任务文件哈希：

| 映射项 | 结果 |
| --- | ---: |
| r2 计划 / family / 台账尝试 | 900 / 300 / 465 |
| 当前校准任务 / family | 213 / 71 |
| mission_id 同名 | 213/213 |
| family 对应 | 0/213 任务（0/71 family） |
| 规范场景哈希对应 | 0/213 |
| 任务文件哈希对应 | 0/213 |
| 可建立同一规划的逐运行配对 | **0/213** |
| 已评估参考运行质量 | **0；未读取运行结果** |

例：校准 `patrol_0001_v00` 属于 `scene_f1639c2bcab56cac5efa`，不能因 r2 同名就将不同场景的飞行作为其参考。213 条逐项身份和同名 r2 身份保存在外部 `mapping_01/mapping.json`。

**停止状态：BLOCKED_SOURCE_IDENTITY_MISMATCH。** 这不是“213 个 r2 尝试缺失/不合格”；根本没有与这 213 个校准输入同源的 r2 计划项，不能进入质量筛选。未打开 r2 的 run/analysis/result 文件，未打开 r1，未打开盲测任务内容或运行结果，未执行任何校准/盲测飞行，没有新建 SITL。共享划分元数据中的组名和身份用于筛选，未用来调整分组。

因此 M3 b 的判定/运动槽位一致率、时长误差、弧长横向偏差、速度与间距分布均为 **未计算**，不是零误差；也未进行时钟换算或用固定 2.5% 缩放替代各运行自己的时钟模型。M3 c 依赖这些基线证据，本轮没有据空数据选择参数、提出已验证的数值通过标准或开始调参。下一步必须先明确与当前冻结来源匹配的参考证据，或由用户明确另行决定评估来源；不能自行切回旧划分、替换 family 或将 T1/T4 充当校准集。

## 6. 证据、复现与提交

外部证据根：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/performance/coverage_geometry_20261012/attempt_01/`。包含 `equivalence_20/verification.json`、20 条重算 JSON、`timings_12/` 全链产物、`timing_comparison.json`、`profile_n4.json`、原始日志与脚本、`mapping_01/mapping.json`、DR130 和 CI 日志。仓库只保留本报告、小型摘要、代码与测试。

复现：项目 `.conda-env=llm`、PowerShell 7；以下 Python 命令均通过 `conda run -n llm --no-capture-output python -B` 执行，输出目录必须全新。

```text
scripts/verify_coverage_geometry.py --baseline <旧acceptance_01/verification.json> --baseline <旧baseline_four_patterns/verification.json> --output <新外部目录>
<证据根>/run_timings.py <全新证据根>  # 只选择 registered_cases 中 12 个正例
<证据根>/profile_n4.py              # 固定本脚本旁 profile_n4 新目录；复跑先复制脚本到新目录
-m unittest -v <.github/workflows/unit-tests.yml 中的 44 模块>
scripts/diagnostics/v06_offline_checks.py golden --output <新外部目录>
-m unittest -v test_v06_data_contract.V06DataContractTests.test_four_frozen_v05_examples_preserve_all_features_targets_and_old_metadata
```

首次沙箱内 Conda 启动遇到 Windows DLL 重定位错误，未执行测试；使用正常权限边界后成功。第一次身份核对脚本将 `relative_path` 误写为 `relative`，读到索引即停止，日志/脚本保留；第二版修正键名后完成核对，没有打开运行结果。

提交前空白检查发现本轮新建摘要 JSON 被 Windows 文本写入转换成 CRLF；仓库 `* -text` 不自动规范化，因此只将该未发布摘要转为 UTF-8/LF 后重新检查。失败检查日志保留，既有证据和任何被比较产物均未改写。

起点为 `codex/fast-dynamics` 的 `4b045f2e3d74ff60c26e8b7d6a27570ce6a79e4f`；本轮代码和报告按显式白名单做本地提交，不推送。两个既有 M2-03 `.backup` 文件继续保留且不纳入提交。最终提交 SHA 记录在外部 `local_commit.json`，本报告与实现位于同一提交。
