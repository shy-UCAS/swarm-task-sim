# M2-02 审阅回执（2026-10-12）

**结论：FIX_REQUIRED。M2-03 尚未放行。**

900 项源身份、7 批次同源关系及 12 格真实开发任务登记成立。当前划分虽然能够用自身字段重算，却不符合预登记的 family ID 输入约定；使用史审计还存在短 ID 漏检和台账跨来源同名混淆。71/72 划分不能作为已获批准的留出。修复仅限来源审计、划分及记录，不实现飞行功能。

## 1. 被审身份与审阅范围

Git 根为 `F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-dev`；项目为其 `Multi-UAV SimpleGC` 子目录。

| 对象 | 本轮实测身份 |
| --- | --- |
| 分支 / HEAD | `codex/fast-dynamics` / `16b7cb740d081f7c66e73ed80eff4c7bad8dbb5f` |
| 父提交 | `57cca914f2e8b414e8820a1f08f6fd900f912d36` |
| HEAD 统计 | 203 文件，+1,918 / −36,847 |
| `main` / `origin/main` | 均为 `5e45637f2bf63054ed0ace2433fd7c9ea7b075ac` |
| 审阅前跟踪文件 diff | 空；M2-02 的 16 个新文件尚未提交 |
| `M2-02_report.md` | `2e22c5a8be888b082fa056b2bec0896cdce25a4756e7cc374c2dc692b0aa610c` |
| `M2-02_summary.json` | `81a7b0772f19aca1a2cb08823fa478a730f25fa9d23316ae18b00dd9b755509c` |
| `evaluation_split.json` | `5cc963fd817aa3c92ea3d813b049c7467f1458eaa41065664b637d196e25ba0f` |
| `coverage_matrix.json` | `2479970093a060d4f68bac5f749d7c463fbf1880a02aa8ce98cd7e80af9d564a` |

执行证据只读：`SwarmData/fast_dynamics/m2/M2-02/attempt_01/` 及 `SwarmData/fast_dynamics/splits/split_2026101202/`。

独立审阅证据：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m2/review/M2-02/review_01/`。

- `review_metadata.py`：独立复算源身份、按来源归属台账、比较两种 component_id 输入、核对 12 格及身份别名扫描。
- `metadata_checks.json`、`identity_alias_scan.json`、`review_metadata.log`：原始核查结果，运行 exit 0。
- `review_identity_manifest.json`：绑定被审文件、执行脚本、独立审阅脚本/结果及本回执的字节、SHA256。

使用 PowerShell 7.6.5、项目 `.conda-env=llm`，独立 Python 命令为：

```text
C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m2/review/M2-02/review_01/review_metadata.py
```

审阅只核对身份、执行存在性、来源用途、静态结构和算法；没有运行快速引擎、SITL、M3 或训练，没有查看候选的飞行成败、轨迹、标签、描述或性能结果。文本扫描只提取身份 token 和文件路径，不记录周围结果内容；个别遗漏文件另核对顶层字段名称及历史生产脚本/文档，以判断它们是否只是名册枚举。未证明所有仓库外活动均已纳入，也未重跑 M0/M1 验收或 431 项业务回归。

## 2. 已完成且可保留的部分

1. 7 个批次 `mission_list.json` 实测字节同一，SHA256 均为 `d83f0cf404e402169391580d80511f9af0cb029aa74ba6370650096ec2f525a0`；900 项 TaskSpec 原始 SHA256 与规范场景身份独立复核，0 不符。
2. 12 份 fixture 合计 37,763 字节，与原来源逐份相同。实际意图、飞法、scenario 机数构成 12 个不同单元，确实覆盖四组合 × 2/3/4 机；来源均为 T1/T4 开发资料。正例尚未执行，负例 `NOT_RUN` / `actual_result=null`，没有把源成功标签复制为新结果。
3. 当前图的 `rmission` / `pmission` 命名空间修正有作用；320 个分量、当前精确关联规则及已声明的几何近重复局限可追溯。旧错误产物保留而不作正式依据的做法适当。
4. 当前 143 候选按现有字段能复算出 71/72；去重、排序、种子和 rank 运算本身成立。但这是内部一致性验证，不能替代第 3 节的输入契约验证。
5. 本轮未改业务代码或旧迁移数据，没有发现对 M0/M1 引擎能力的直接破坏。主要风险是后续研究划分和使用史被错误解释。

## 3. 必须修复的问题

### R1：component_id 输入并非预登记的 family ID

依据 `M2-02_instruction.md` B.5，应序列化分量中的 family ID。项目 `swarm_sim/families.py` 的 `scene_family_id` / `family_record` 定义该 ID 为 `scene_` 加规范哈希前 20 位；名册和覆盖矩阵也使用这种 ID。

实际 `build_split.py` 把 `canonical_scene_sha256` 加入 `families`，再传给 `component_id`；仓库 `evaluation_split.json` 的 `family_ids` 因而存储 64 位完整场景哈希。两个字段被混用了，报告却声称逐字执行原约定。

独立检查：320/320 个 component_id 与按实际 `scene_*` family ID 序列化的值不同。在保持原 143 候选、相同分量关系及种子不变的对照下，82/143 个分量改变 calibration/blind 归属。这个数字只是错误影响分析，不是已批准的新划分。

修复目标：分开 `family_id`、`family_scheme`、`canonical_scene_sha256`；显式映射并检查短 ID 冲突。组件和 rank 必须按原指令的 family ID 算。算法文字也应包含去重，不能继续只写 `sorted(family_ids)`。

保留现有 v1 原字节，登记其为本回执拒绝的版本；修正版使用新版本/新外部目录并说明 supersedes 关系。种子仍为 `2026101202`，只允许根据修正后的身份和使用史做一次确定性计算；不得为了保留 71/72、原分组或任务比例而选池、换种子或反复重抽。

### R2：使用史还不能支撑 candidate_eligible 与 quarantine=0

**R2a：短 family ID 漏检。** `audit_v2.py` 的 `ALL_FAMILIES` 是完整场景哈希，引用扫描仅执行完整哈希的文本匹配，没有搜索项目通常写入报告的 `scene_*` ID。“仅 17 个 family 被引用”实际只表示完整哈希引用。

独立身份扫描在近似相同的已登记目录中扫描 29,975 文件（另排除本阶段自身产物，避免自引用污染）：完整哈希命中 17 个 family，短 ID 命中 302 个 family；当前 143/143 候选均有未被原方法记录的短 ID 路径。本批 320 family 的短 ID 映射没有冲突。

可复核示例：`scene_00608e56b0cf5a95c683` 对应完整哈希 `00608e56b0cf5a95c68398586f129bf921d81360a6b551888e54c13eb910cb99`，出现在：

- `SwarmData/reviews/v06_deepseek_audit_20261009/production_turns.json`；
- `SwarmData/v06_pauseA_20261008/planning/planning_report.json`；
- `SwarmData/v06_pauseA_20261008/planning_final/planning_report.json`；
- `SwarmData/v06_pauseA2_20261008/planning/planning_report.json`。

这**不等于 143 个候选都已用于调参**。生成输入和自动枚举可以按已登记规则排除，但已有几何审计/规划检查是否构成开发诊断，须按来源用途分别核实，不能因仅有短 ID 而无视。`production_turns.json` 是 900 行、含 family/pattern/turn 等字段的历史审计表，并非 `mission_list.json`。现阶段不能用“完整哈希未命中”证明从未使用。

修复目标：同时识别短 ID 和完整哈希，按明确映射归属；任务名只有在 batch/profile 已知时才能作为辅助证据。输出逐文件扫描/排除清单（路径、字节、哈希、用途和排除理由），排除本阶段新报告与新划分。区分自动名册、离线规划准入、开发诊断/调参、训练/生产和无法确认用途。用途不明的相关泄漏分量进入 quarantine；不能把“没找到”一律当二值未使用。

**R2b：台账仍按裸 mission_id 合并。** `audit_v2.py` 使用 `usage[attempt['mission_id']]` 合并全部主名册与 pilot 台账；`build_split.py` 又只用 `roster_members` 查询该字典。图节点虽然修正了，台账归属没有同步修正，pilot 分量的真实执行记录也因此未直接归到自身。

独立按各批次 mission_list 对台账身份解析，发现 30 个裸 mission_id 对应多个规范场景身份。当前登记台账全为 finished；当前 143 候选按正确身份连接也没有 finished 记录。因此暂未发现该缺陷改变这 143 个候选的“执行过”结论，但既有 pilot/主名册用途证据的归属方法仍有错误。

修复目标：先用 `(batch/profile, mission_id)` 定位对应源任务，再映射 family/规范场景，按正确身份合并同源重复运行。记录执行存在性与开发/训练使用用途两个维度。pilot 实际执行与仅规划必须分开，缺台账或无法归属不得默认为未执行。

报告原来排除的 2 个“仅规划引用”分量已经在留出外；无需仅为改角色名称强制转为 quarantine。要解决的是其他未审清的引用，而不是机械把所有规划表中的 family 全列已用。审清后实际候选数量可能变化，不能预设仍为 143。若剩余可确认候选分量不足 2，按指南报告 BLOCKED 并停止，不打开飞行结果补证。

### R3：负例方案的实施条件需要更准确地登记

12 组只是方案，保持 NOT_RUN 是正确的。侦察方案却以“降低速度，超过阶段预算/截止”为产生覆盖失败的机制：当前执行器有整体 timeout，未证明它会产生质量合格、可判定的 `mission_success=false`；未完成执行与语义失败必须分开，不能把超时直接算作已满足负例。巡逻方案写入 `execution.start_delay_s`，该字段不在当前 `ExecutionConfig`；已有阶段路由使用 `start_delays_s`。

修复目标：登记这些为“待 M2 设计确认的故障/配置方案”，列明现有字段或拟新增接口、作用飞机和阶段、如何保持完整观测及质量合格、可能产生 null/timeout 的风险与替代方案。尚不能确认机制时明确 pending，不承诺其必定为 false。不得在本阶段实现故障注入、修改语义门槛或运行飞行。设计确认留在后续获准的阶段；rapid 低速机制的既有来源可以保留。

### R4：证据身份与后续数据可用性登记

报告头部将 `M2-01_review_03.md` 的 SHA256 写成 `d5fa9a...`；该值实际属于 `M2-00_review_03.md`。M2-01 最终回执实际为 `9805bacc219c84f477006235d13ac8ae3d87c9f74f7c01dc628e57420c131168`。核对报告、摘要及相关上游引用，一次纠正全部身份绑定。

当前 143 个候选在已登记台账中均没有执行记录。这次冻结的是 TaskSpec/family 的未来用途预登记，不能视为已有 71/72 份可供 M3 比较的 SITL 轨迹。补充安全元数据层的数据可用性记录：已有源任务、是否有已登记执行、对照 episode 是否已确认、pending collection 原因；未确认的写 unknown，未采集的写 planned_only。明确后续 M3 数据准备缺口，不能为补齐数据擅自启动 SITL，也不能把生产训练 family 临时移入盲测。

## 4. 验证要求及实际局限

修复复审需有独立、小型身份测试，至少覆盖：

1. 同裸任务名、不同 batch/profile/规范场景不会共享台账；同源跨批次运行可合并，pilot finished 正确归属。
2. 仅短 family ID 引用可被发现，短 ID 冲突不会静默择一；自动枚举和确切诊断引用按不同用途处理，未知引用触发局部 quarantine。
3. 关联链的传递性与开发角色传播：开发 A 通过关联连到 B、B 再连到候选 C，则整分量不进 calibration/blind；不能只在 320 个单-family 现成分量上验证互斥。
4. 使用实际 `scene_*` ID 的固定序列化字节、component_id、rank 有预期值；顺序/重复不影响分组，固定输入重算一致。
5. 12 格验证直接比较四合法组合 × 三机数的完整笛卡尔积，拒绝重复/漏格；不是只分别比较意图集合、机数集合和总数。
6. 原版保留、新版来源/方法/排除清单均绑定哈希；成功、未知、质量不合格、未执行字段没有被混用。

本轮未要求无限扩展几何近重复搜索；已登记 base 谱系与规范场景关联可以作为有限规则，但其局限必须保留。当前 19 项自检不能发现错误字段的自洽序列化，也没有验证台账命名空间和短 ID 引用处理，不能据此放行。

## 5. 可直接转发的本阶段修复指令

```text
只修复 M2-02，依据 docs/fast_dynamics_m2/M2-02_review.md 的 R1–R4。
本回执结论 FIX_REQUIRED；没有 M2-03 授权。不改业务引擎，不运行飞行/SITL/M3。

0. 先验证 HEAD=16b7cb740d081f7c66e73ed80eff4c7bad8dbb5f 和回执第1节四份文件哈希。
   在仓库外全新 attempt_02_repair 目录保存原报告/摘要/划分/矩阵、原方法及引用审计的副本与哈希。
   原 attempt_01 和 splits/split_2026101202 保持只读。
   登记原划分版本因审阅发现实现错误而未获批准，不能继续称为有效留出。

1. 先修身份和使用史，再重算划分。
   分开 family_scheme、实际 family_id、完整 canonical_scene_sha256，验证别名映射/冲突。
   台账先按 batch/profile+mission_id 连接对应来源，再归并同 family。
   pilot 实际执行与仅规划分开；同裸名字不能共享执行证据。
   引用扫描同时支持短 family ID 与完整场景哈希，排除本阶段自身产物。
   对遗漏的 planning_report、production_turns 等按安全用途元数据审计，
   输出逐文件含哈希的扫描/排除清单，并将自动枚举、规划准入、开发诊断、训练、未知分开。
   不读取候选轨迹、标签、成败、质量或性能结果。
   未审清用途的相关分量 quarantine；已用于开发/训练的整个关联分量排除。
   不要求把所有短 ID 引用视为使用，也不允许无完整哈希就视为从未使用。

2. 按修正后的合格分量和实际 family_id，逐字执行原种子2026101202的算法。
   Unicode排序去重 -> ensure_ascii=True/紧凑JSON -> UTF-8 SHA256组件ID -> rank -> floor(G/2)。
   方法/输出使用新版本和新外部目录；保留原版及 supersedes/拒绝原因。
   不换种子、不挑比例、不以原71/72或原分组为目标。
   新版仓库摘要可替换旧交付，但原字节副本和哈希必须可追溯。
   若可确认合格分量G<2，报告BLOCKED并停止，不造出一个完整划分。

3. 12份真实开发任务保持原字节。修订负例说明：侦察速度/预算机制、巡逻延迟接口
   明确为现有字段或待设计方案，作用对象、失败目标、null/timeout风险和质量要求分别登记。
   尚未确认的机制写pending；全部actual_result=null、execution_status=NOT_RUN。
   不用超时/不完整冒充质量合格的语义false，不改标签、阈值或删观测。

4. 更正M2-01最终回执哈希。增加数据可用性登记，区分TaskSpec预留和已有SITL对照。
   不新增SITL采集，不调入已用于训练的family来补盲测。
   报告真实候选/排除/quarantine计数、方法局限及后续采集缺口。

5. 完成回执第4节六类静态验证，使用小型合成身份用例，不运行快速引擎。
   报告修复前后对照、运行命令、源文件与输出哈希；失败日志保留不覆盖。
   同步必要入口中的当前状态，旧验收结论保持历史含义，不改旧受保护证据。
   不提交、不push、不amend、不进入M2-03。
   完成后AWAITING_REVIEW（输入不足则BLOCKED），停止等待Codex复审。
```

## 6. 对四个审阅问题的回答

- **完成了什么：**本地检查点、同源名册身份核查和真实 12 格任务登记可保留；固定运算的内部一致性也已证明。
- **缺什么：**符合预登记字段的组件 ID、可信的跨来源台账和引用用途判定，以及负例/数据可用性/上游回执的准确登记。
- **是否破坏既有能力：**没有发现业务代码或 M1 数据迁移受到破坏；风险集中在留出污染与研究证据解释，不能用现有自检覆盖过去。
- **是否足以继续：**否。先完成本阶段修复复审；本回执不提供 M2-03 执行许可。
