# v0.4 WP-G（G1–G4）里程碑报告

日期：2026-10-01。代码版本：`0.4.0-dev`。基线提交：`e13564b700934b481ad37cba053db9daabf9e4fa`。

**WP-G 已完成，状态 `IMPLEMENTED_AND_TESTED`；现在暂停，等待用户确认后再开始 WP-E。** 本结论仅覆盖通用层和离线验证，不代表连续模式生产运行已经完成。WP-E / WP-V 状态均为 `NOT_IMPLEMENTED`；本轮新增 SITL 运行为 **0 次**。

## 1. WP-S 确认及证据保留

用户已接受 `exact_duplicate_drop_v1`，明确确认 WP-S GO。新建独立 [GO 确认记录](v04_spike_go_confirmation.json)，保存用户确认原文、[复核报告](v04_spike_review_01.md)及离线复算汇总的路径和 SHA256。没有覆盖 `v04_spike_summary.json`、原两份 UNKNOWN 指标报告或其运行目录。

保护清单涵盖原有 `runs/`、`datasets/`、`generated/`、`verification/`、`audit_v04/` 和三份原 WP-S 文档，共 **4661/4661 份文件 SHA256 保持不变**。保护结果见 [preservation.json](../tmp_v04/wp_g/preservation.json)。`audit_v04/` 原脚本只作为只读参考，没有导入执行或写回。相邻 `SimpleGC/` 未修改。

本轮没有安装依赖、启动 SITL、提交或推送 Git。此前 WP-S 使用 2 次运行，本轮未消耗新的运行预算。

## 2. 实现清单

| 里程碑 | 状态 | 已实现内容与主要文件 |
| --- | --- | --- |
| G1 | IMPLEMENTED_AND_TESTED | `registry.py`、`mission_v3.py`、`reconnaissance.py`、`mission_evaluation_v3.py`；TaskSpec v3 严格规范化，意图/规划器注册表，侦察适配，旧屏障模式编译与双通道验证分派 |
| G2 | IMPLEMENTED_AND_TESTED | `families.py`、`scene_samplers.py`、`generation_v2.py`；物理场景 family、profile v2、场景/任务种子分离、同 family 共享干扰变量、所有意图和变体原子接受、可追溯拒绝原因 |
| G3 | IMPLEMENTED_AND_TESTED | `protocol.py`、`quality.py`、`dataset.py`、`episode_loader.py`、`observation_processing.py`；新协议、两级资格、导出/加载、混合控制模式显式开关、完整流去重接口与版本校验 |
| G4 | IMPLEMENTED_AND_TESTED | `dataset_audit_v3.py`、`execution_metrics.py`；按意图/模式分组的通用审计、意图专属指标、反事实完整性矩阵、编号/起点关系、拓扑分布、执行伪影指标及历史离线复核 |

旧入口只增加 schema/profile/protocol 分派。v1/v2 的规范化、规划、绑定、意图验证器、观测处理器和默认质量策略不经过 v3 的新路径。v2 离线分析追加独立 `execution_metrics.json` 诊断附件，不改变原有标签、语义结果、观测特征或资格门槛。

生产注册表仍只有 `reconnaissance` 意图。夹具意图和意图无关的夹具采样器只在测试上下文中注册，退出即注销。当前生产采样器 `strip_aligned_v1` 明确标注 `intent_agnostic=false`，拒绝多意图 profile；不将其描述成已经解决场景分布偏差。

接口文档：[TaskSpec v3](task_spec_v3.md)、[协议与观测](v04_protocol_v3.md)、[通用审计](v04_dataset_audit_interface.md)、[执行诊断](execution_metrics_v1.md)。

## 3. 用户补充要求的落实位置

完整计划补充见 [v04_stage01_plan_addendum.md](v04_stage01_plan_addendum.md)。

| 要求 | 本轮落实 | 后续接线 |
| --- | --- | --- |
| exact_duplicate_drop_v1 + full_stream_strict_v1 | G3 独立接口及 7 项测试通过；窗口外冲突/回退仍使整条流失效，未实现窗口资格放宽 | E3 接入真实 v3 分析 |
| 处理版本可追溯 | manifest/quality 合同包含四个版本字段；附件存在时核对时钟模型版本；跨产物矛盾拒绝 | E3 实际产生并传播这些记录 |
| 每次运行参数读回和 TX 请求日志 | 已写入 E2 验收要求：类型、sysid/component、缺项索引、发送前后主机时间、请求关联 ID 及结果 | E2 实现；当前 v3 run 明确拒绝，避免无记录运行 |
| 固件 SHA256、版本字符串、参数模板指纹 | 已写入 E2 门禁；固件或参数模板变化必须重做 WP-S 并重新确认 GO | E2 实现逐运行取证和指纹比对 |
| overshoot / arrival | overshoot 默认 0；未改原计划 7.5 的 arrival_s 定义 | E1/E3 按原定义实现连续执行/双通道窗口 |
| V03/V04/试生产最低过点速度分布 | G4 已有 2 m 邻域最低水平速度、有效/未知数及按完整扫描线长度分组接口和手算测试 | WP-V 报告填入真实运行数据，不能将本轮离线接口验证写成新 SITL 已通过 |

四个版本为 `observation_processing_version=v3_observation_v1`、`duplicate_policy_version=exact_duplicate_drop_v1`、`timeline_policy_version=full_stream_strict_v1`、`clock_model_version=passive_system_time_piecewise_v1`。

最终交叉审查补齐了 v3 证据一致性：运行失败不能同时声明运行完成；任务车辆集合必须与 manifest、每机质量记录一致；数据集中的意图、结果、时钟等级和资格必须与 episode 一致。反例测试验证即使重新计算文件哈希，这些矛盾仍会被拒绝。

## 4. 本轮实际单元与回归测试

环境：PowerShell 7.6.5，Conda `llm`，Python 3.12.3。修改前 **210/210** 项通过；最终 **282/282** 项通过，耗时 **16.338 s**，0 失败、0 错误、0 跳过。其中原 v0.3 为 150 项，此前 WP-S/复核增加 60 项，本轮增加 72 项。

逐测试 ID、结果、源码 SHA256 见 [unit_test_results.json](../tmp_v04/wp_g/unit_test_results.json)。本轮测试模块分别为：TaskSpec 18、生成器/family 16、协议/资格 10、观测 7、通用审计 10、执行诊断 9、暂停边界 2。以下 G 编号是验收项，不等于单个 unittest 数量。

| ID | 结果 | 本轮实际证据 |
| --- | --- | --- |
| G01 | PASS | mission/planner/execution 改变不影响 family；生成器改变非物理参数后物理场景不变；第 7 节保存了实际规范化和编译的例子 |
| G02 | PASS | 区域、起点、航向改变 family；飞机/区域编号和列表顺序不影响物理身份；六位小数量化及正负零/整浮点等价测试 |
| G03 | PASS | 同场景侦察与临时夹具意图生成相同 family、split、共享参数；再导出两意图合成 episode，审计无跨 split 泄漏，完整性矩阵完整 |
| G04 | PASS | 各对象层未知字段、全部数值叶子 bool/NaN/Inf、未注册项、意图/规划器错配、模式专属字段错配、family 不符均明确拒绝 |
| G05 | PASS | 三种几何 × 有/无返航共 6/6 组，与等价 v2 的执行阶段、目标点、语义映射和 planning 完全相同 |
| G06 | PASS | 注册表只含生产侦察；正常退出和异常退出均注销临时项；禁止覆盖现有注册项 |
| G07 | PASS | 手工轨迹下 v3 侦察结果与 v2 相同；夹具调用自身验证器，可使用自定义语义阶段；双通道三值逻辑和不一致证据测试通过 |
| G08 | PASS | 两意图同集成功；v2/v3 混合拒绝；混合模式默认拒绝、显式允许留痕；加载器检查版本与元数据矛盾 |
| G09 | PASS | 成功/失败/未知 × agree/disagree/unknown 均验证质量资格独立；质量合格的失败任务保留，benchmark=false；无效区间和缺口按机记录 |
| G10 | PASS | 10 项合成审计测试：通用/专属指标隔离、完整性矩阵、执行指标、未知值、编号关系、拓扑训练/测试重合、重复和泄漏、证据绑定 |
| G11 | PASS | profile/种子重放一致；所有意图与速度变体原子接受；拒绝原因归属明确；非中立采样器+多意图拒绝；同 family 共享参数和意图顺序不变性通过 |
| G12 | PASS | schema 1 生成器重新生成 100/100 个旧任务，生成产物 SHA256 与旧 manifest 全部一致 |

| ID | 结果 | 本轮实际证据 |
| --- | --- | --- |
| R01 | PASS | 最终全量测试中原有 150/150 项全部通过，按 Git 已跟踪测试文件识别 |
| R02 | PASS | 4 份根目录 mission + 100 份旧生成任务，共 104/104 份编译规范化哈希与修改前一致；100/100 份生成任务另与已存场景一致 |
| R03 | PASS | 15/15 个 v0.3 验证运行只读绑定校验通过 |
| R04 | PASS | 两个 v0.3 数据集共 15/15 个 episode；新加载器的完整返回结构与修改前的规范化哈希一致 |
| R05 | PASS | 15/15 个历史运行完整复制到新目录后重分析，labels 和 semantic_validation 所有原字段取值不变；15/15 个追加 execution_metrics 附件 |

R02–R05 正式结果见 [final_regression/legacy_regression.json](../tmp_v04/wp_g/final_regression/legacy_regression.json)。比较基准来自修改前快照与已存历史产物，不用新算法输出充当自己的期望值。R06 属于 E2，本轮未实施；不据此宣称 WP-E 验收完成。

测试中启动器、飞控和网络操作使用 mock；“完整性通过”与“合成 episode”都不表示一次真实飞行。G3 导出/加载两种模式的验证使用手工合成、哈希绑定的测试证据，文件位于临时目录，不进入生产数据集。

## 5. 已有 SITL 日志的离线复核

这是证据类别“对已有 SITL 日志的离线分析”。正式结果见 [execution_metrics_regression.json](../tmp_v04/wp_g/execution_metrics_final/execution_metrics_regression.json)。

| 项目 | 结果与分母 |
| --- | --- |
| 处理范围 | 15/15 个 episode，60 架飞机实例 |
| 有原 A4 基准 | 14 个 episode，57 架飞机实例 |
| 0.3 m/s 停靠数对照 | 57/57 架实例完全一致 |
| 0.5 m/s 停靠数对照 | 57/57 架实例完全一致 |
| 同步时间比例 | 14/14 个 episode 相同，最大绝对差 0.0，满足计划的 1e-6 容差 |
| 全机共同停靠事件数 | 14/14 个 episode 相同 |
| 无参考项 | 1/15 个 episode：20260930T153556Z_bf2d3529，3 架飞机无有效语义窗口，保持 UNKNOWN，不计入比较通过分母 |
| 复算源证据保护 | 80/80 份原输入/审查文件哈希不变；属于第 1 节更大保护集合的一部分 |

原 A4 脚本跳过无有效窗口的失败运行，因此实际只有 14 个参考。此次处理全部 15 个，既不伪造第 15 个参考，也不把缺窗口计成零停靠。R05 则仍覆盖该失败运行，并确认其原有判定不变。

执行指标版本为 `execution_artifacts_v1`。计数沿用 A4 的整个导出任务网格，比例使用明确的语义任务时间范围。部分轨迹的观察计数标为下界，不能混进完整统计；缺证据比例为 null。共同停靠事件改用真实全机区间交集，同时保留 A4 包络值供诊断，手算反例证明旧包络可能误报；本批历史数据两种算法的事件数没有差异。

E10 手算停靠数、同步比例和静止占比通过，属于 G4 要求的指标验证。arrival/名义时序接口的合成测试不替代 E3 的窗口实现与实测。

## 6. v3 示例与当前可执行能力

已新增六份示例：`missions/v3/recon_shared_3uav_{barrier,route}.json`、`recon_smoke_2uav_north_{barrier,route}.json`、`recon_smoke_6uav_{barrier,route}.json`。

本轮真正通过 CLI 执行了三份 barrier 示例的 `plan` 和 `validate`，共 **6/6 条成功**；另执行一次 route 计划请求，按预期拒绝并提示等待 E1，未产生伪装成可执行场景的输出。输出及返回码见 [examples_report.json](../tmp_v04/wp_g/examples/examples_report.json)。

```powershell
# 以下是离线计划命令；输出路径应不存在。
conda run -n llm --no-capture-output python main.py plan missions/v3/recon_shared_3uav_barrier.json --output tmp_v04/my_v3_barrier.json
conda run -n llm --no-capture-output python main.py validate tmp_v04/my_v3_barrier.json
conda run -n llm --no-capture-output python main.py generate generation_profiles/recon_pilot_v04.json --output tmp_v04/my_v3_generation
```

当前 profile v2 实际生成 **10 个任务、10 个不同 family**，32/32 个产物哈希验证通过，位于 `tmp_v04/wp_g/generated_v04_barrier/`。这是计划生成与可行性预检，没有飞行结果，不能称为“10 次试生产成功”。

`generation_profiles/recon_pilot_v04.json` 暂用 barrier 模板。WP-E 完成后必须显式切换 route 模板，保存新 profile 指纹，再做 V06 连续模式试生产。当前 v3 的 `run` 明确等待 E2，`analyze` 明确等待 E3；边界测试确认拒绝发生在启动进程或创建分析产物之前。

## 7. family 不变性的实测例子

以下十份任务均实际调用 `normalize_v3` 和 `compile_task`，保存了规范化任务及完整物理内容 SHA256。split 使用默认 `simplegc-v02` salt，例子均为 barrier 模式；这组数据用于说明家族关系，不是数据划分比例或类别性能实验。

| 实际变化 | family_id | split | 编译阶段数 |
| --- | --- | --- | --- |
| 原始 3 机任务 | scene_d168b91bd8159a8ae8b9 | test | 12 |
| 覆盖目标 0.9 → 0.8 | scene_d168b91bd8159a8ae8b9 | test | 12 |
| 不要求返航 | scene_d168b91bd8159a8ae8b9 | test | 11 |
| 扫描间距 4 → 3 m | scene_d168b91bd8159a8ae8b9 | test | 14 |
| 速度 3 → 2.5 m/s | scene_d168b91bd8159a8ae8b9 | test | 12 |
| 修改 task_id 和 seed | scene_d168b91bd8159a8ae8b9 | test | 12 |
| 车辆重新编号、修改 sysid 并倒序 | scene_d168b91bd8159a8ae8b9 | test | 12 |
| 区域宽度 54 → 55 m | scene_6f1cad6f1bc11d3903da | train | 12 |
| 首机东坐标 9 → 9.5 m | scene_5c5a0120f90b87159559 | train | 12 |
| 首机航向 0 → 90° | scene_db13355557c210d2b994 | train | 12 |

family 仅来自 origin、world、区域几何、起点/航向集合和平台 ID。它不包含任务名称、种子、意图、planner、execution 或飞机编号。平台能力上限不作为几何哈希字段；平台定义本身应通过平台 ID 版本化。

额外的合成两意图实验中，侦察和临时 `test_fixture` 都得到 `scene_d168b91bd8159a8ae8b9` / `test`；两个任务均失败但质量合格，完整性矩阵仍完整，`family_split_leaks={}`。实测摘要与十份任务均保存在上述 `examples/` 目录，夹具运行本体随临时目录清理，生产注册表恢复为仅侦察。

## 8. 本轮尝试记录及尚未完成部分

首次 A4 对照发现原报告少一个失败运行，初次输出停止并保留；随后修正比较分母和缺证据行为，在新的 `execution_metrics_final/` 中完成。此前 `execution_metrics/`、`execution_metrics_complete/` 均未覆盖。R05 早期结果也保留，正式报告使用加入缺窗口保护后的 `final_regression/`。

测试证据脚本第一次在启动测试前遇到 Git 安全目录检查，改为仅对该只读命令传入已核实仓库的 `safe.directory`，没有修改全局 Git 配置；随后实际执行的全量测试为 282/282 通过。

待用户确认后，下一步按顺序是：E1 连续语义航线编译、任务项/时间间距检查及绑定；E2 连续执行器、到点事件和逐运行固件/参数证据；E3 原计划 arrival 窗口、v3 观测处理接线和分析导出。之后才进入 WP-V 的 V03/V04/试生产，并加入扫描线长度分组的最低过点速度分布。

**本次停在 G4，不开始 WP-E，不安排新的 SITL 运行。**
