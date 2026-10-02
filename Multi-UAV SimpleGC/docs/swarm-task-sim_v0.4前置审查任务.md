# swarm-task-sim：v0.4 前置源码审查任务（交给 Claude Code 执行）

## 0. 你的角色与本次目标

你是一名**只读审查员**。仓库是 `shy-UCAS/swarm-task-sim`，当前源码版本应为 0.3.0，主工程目录为 `Multi-UAV SimpleGC/`（目录名含空格）。

项目背景（只用于理解每个检查项为什么重要，不需要你做设计决策）：

- 这是一个基于 ArduCopter SITL 的多无人机"任务 → 规划 → 执行 → 验证 → 数据集"生成器，目标是构建**无人机集群意图识别 benchmark**。
- v0.3 已完成单一意图 `reconnaissance / area_coverage` 的闭环。
- 下一步 v0.4 计划加入第二类意图（倾向 Patrol），形成双类别数据。
- 外部审查（只读过部分源码和文档）提出了若干怀疑：执行层可能在每个航点产生全机同步停靠；若干模块把"只有侦察一类"写死；样本协议和多样性可能引入捷径。**你的任务是用源码和已有实验数据逐条证实、否定或修正这些怀疑。**

本次**不是**实现任务。不要修复任何问题，只报告事实、证据和改动范围估计。

---

## 1. 硬性规则

1. **不得修改**仓库内任何已有文件，包括源码、测试、文档、`runs/`、`datasets/`、`generated/`、`verification/` 下的任何内容。
2. **不得启动 SITL**：禁止执行 `main.py run`、`main.py batch`、`scripts/run_mission_list.py`，以及任何会启动 arducopter 进程的命令。
3. **不得** `git add / commit / push`，不得切换分支。
4. 允许的操作：
   - 阅读源码、文档、JSON、CSV；
   - `git log / git show / git rev-parse` 等只读 git 命令；
   - 运行全部单元测试：`conda run -n llm --no-capture-output python -m unittest discover -s tests -v`（在 `Multi-UAV SimpleGC/` 目录下）；
   - 编写**只读分析脚本**读取已有数据，在内存中调用规划/编译函数做干跑（dry-run）。
5. 所有你新建的文件（分析脚本、中间结果、最终报告）**只能**放在仓库根目录下新建的 `audit_v04/` 文件夹中。任何需要输出目录的函数（例如 `generation.generate`）只能指向 `audit_v04/tmp/` 下的新目录。
6. **证据优先于文档**：文档、README、验证报告里的描述只能作为线索，结论必须以源码和实际数据为准。如果文档与源码不一致，单独记录。
7. 每条结论必须标注状态：`证实` / `否定` / `部分成立` / `无法确定`，并附证据（`文件路径:行号` + 不超过 10 行的代码摘录，或脚本计算出的具体数字）。不能确定的写明缺什么证据，不要猜测。

---

## 2. 开始前的基线信息（写进报告开头）

- `git rev-parse HEAD` 的完整提交号，以及 `git log --oneline -n 10`。
- 源码中的 `__version__` 值及其所在文件。
- Python 包的实际目录名（预计是 `swarm_sim/`，以实际为准）以及模块清单。
- 运行全部单元测试，报告通过/失败/跳过数量（v0.3 报告声称 140 项全部通过）。如有失败，贴出失败名称和摘要。
- 确认以下数据目录是否存在，以及各自包含的 episode 数量：
  - `verification/v03_pilot_final_20260930/dataset/`
  - `verification/v03_integration_20260930/dataset_final/`
  - `generated/recon_pilot_v03_20260930/`

以上路径均相对于 `Multi-UAV SimpleGC/`。若不存在，搜索相近目录并说明。

---

## 3. 审查项

优先级：A 组最高，其次 C、B、D。时间有限时，先保证 A 组和 C 组完整。

### A 组：执行层是否在每个航点产生全机同步停靠（最高优先级）

**A1. 规划编译：一个航点是否等于一个执行阶段**

- 阅读 `mission_planning.compile_execution_phases`，确认它是否按航点下标逐个生成 `leg_xxx` 阶段，每个阶段为每架飞机指定一个目标点。
- 对 `missions/recon_shared_3uav.json`、`recon_smoke_3uav.json`、`recon_smoke_2uav_north.json`、`recon_smoke_6uav.json`，在内存中调用编译函数，报告：每个任务的 `execution_phase_count`、approach / observe / return 各占多少阶段、扫描线数 `lanes`，以及每机的 `idle_padding_steps`。

**A2. 运行器：每个阶段的执行流程**

- 阅读 `runner.run_scene` 中对 `scenario["phases"]` 的循环，写出每个阶段的完整步骤顺序（上传 → 放行 → 执行 → 到点确认 → 下一阶段），并标注哪些步骤需要等待全部飞机完成。

**A3. 飞控交互：每个航段上传什么、模式如何切换**

- 阅读 `vehicle.py` 中的 `prepare_airborne`、`upload`、`execute`、`confirm_target`（以实际函数名为准），以及 `scenario.mission_for`。报告：
  - 每个航段上传的 AUTO 任务包含哪些 MAVLink 任务项（命令类型、参数，尤其是航点驻留时间是否写在任务项里）；
  - BRAKE / AUTO / LOITER 在 v2 流程中的切换时机；
  - `confirm_target` 的判定逻辑：到达容差、连续驻留时长、超时，以及它是否要求飞机静止。
- 阅读 `tasks.target_confirmation`，报告 v2 下到达容差和驻留时长从哪里取值。
- 报告以下文件中 `waypoint_hold_s`、`confirmation_dwell_s`、`arrival_tolerance_m`、`speed_m_s`、`lane_spacing_m` 的实际取值：`missions/recon_shared_3uav.json`、三个 smoke 任务，以及 `generation_profiles/recon_pilot_v03.json` 所使用的模板。
- 在 SITL 参数文件中搜索与航点导航相关的参数（如 `WPNAV_*`、`WP_*`），列出被显式设置的值。若没有显式设置，写明"使用固件默认值"。

**A4. 实测验证：用已有数据量化停靠（不启动 SITL）**

在 `audit_v04/` 下编写脚本，读取 `verification/v03_pilot_final_20260930/dataset/episodes/*/` 和 `verification/v03_integration_20260930/dataset_final/episodes/*/` 中的 `observations.csv`、`phase_windows.json`、`semantic_plan.json`（或等价文件），对每个 episode 计算：

1. **水平速度** $\|v_{xy}\| = \sqrt{v_e^2 + v_n^2}$，仅使用 `valid=1` 的行。
2. **停靠段**：$\|v_{xy}\| < 0.3$ m/s 且持续至少 1.0 s 的连续区间。另用 0.5 m/s 阈值重算一遍做敏感性对照。
3. **每架飞机的停靠段数量**，并与该 episode 的 `execution_phase_count` 比较。
4. **静止时间占比**：停靠段总时长 ÷ 任务窗口总时长。任务窗口取第一个 approach 阶段开始到最后一个阶段结束；如果无法从产物确定窗口，就用整个 `observations.csv` 时间范围，并注明。
5. **同步停靠比例**：在多少比例的时间里所有飞机同时处于停靠段；在多少个停靠事件中全部飞机的停靠区间存在共同重叠。
6. **航段长度序列**：从规划产物（参考路线）中取出每机相邻航点之间的距离序列，报告其模式（例如"长—短—长—短"交替）。

输出：

- 一张每 episode 一行的汇总表；
- 任选一个三机 episode，画出各机 $\|v_{xy}\|$ 随时间变化的曲线，叠加阶段边界竖线，保存为 `audit_v04/speed_profile_<run_id>.png`。如无绘图库，改为输出 CSV，并在报告中用文字描述。

**A5. 每个运行的时间构成**

- 读取上述 episode 对应原始运行目录的 `metadata.json` 和 `events.jsonl`，报告 `elapsed_s`。
- 用事件时间戳把每次运行拆分为：SITL 启动与连接、起飞准备、各阶段的上传 + 放行等待、各阶段的飞行、到点确认驻留、降落、收尾。给出中位数和范围。
- 统计全部运行中，"上传 + 确认驻留 + 屏障等待"占任务阶段总时长的比例。

**A6. 改为"每机整段连续航线"的改动范围（只评估，不实现）**

设想改动：在每个语义阶段（approach / observe / return）内，把每架飞机的完整路线作为一个 AUTO 任务一次性上传，屏障只保留在语义阶段边界。请评估：

- 需要修改哪些函数（规划编译、运行器循环、到点确认、服务窗口 / `phase_windows` 的生成、`mission_evaluation` 中观察服务窗口的界定、`validate_task_binding`、相关测试）；
- 现有代码中是否已有可复用的多航点上传能力（例如 v1 路径或 `mission_for` 是否支持多个航点）；
- 预计影响的测试数量；
- 最大的技术风险（例如：服务窗口如何从"阶段事件"改为"航点到达事件"；AUTO 模式下 MISSION_ITEM_REACHED 等消息能否可靠记录）。

---

### B 组：样本协议与模型输入

**B1. 观测窗口覆盖范围**

- 阅读生成 `observations.csv` 的代码（预计在 `recording.py` 或 `analysis.py`，以实际为准），确认其起止时刻依据哪个事件，例如 `flight_epoch`、`airborne_ready`、`mission_end`、`landing_started`。
- 用一个实际 episode 验证：第一行和最后一行的 `t_s`、`up_m` 是否显示起飞爬升或降落下降；观测时长与 `metadata.json` 的 `elapsed_s` 之比。

**B2. 时间网格**

- 确认各机是否在同一个主机时间网格上采样，即每个 `t_s` 是否对所有 agent 都有一行。统计 mask 为 false 的比例。

**B3. 坐标与零填充**

- 报告各 episode 的 `east_m / north_m / up_m` 取值范围。
- 确认 `episode_loader.load_episode` 不做任何归一化。
- 判断零填充值 (0, 0, 0) 是否落在真实轨迹的取值范围之内，即零填充是否与合法位置混淆。

**B4. 智能体顺序是否携带空间角色**

- 在 `generated/recon_pilot_v03_20260930/` 的全部任务上（必要时在内存中重新编译），统计：按 agent ID 排序后的第 k 个 agent，是否总是被分配到第 k 个条带（`strip_k`）。报告一致的比例。
- 说明加载器的 agent 排序规则。

**B5. 序列长度分布**

- 报告各 episode 的帧数 T，以及 T 与飞机数、`return_required`、扫描线数之间的关系。

---

### C 组："只有侦察一类"的写死位置（决定 v0.4 重构范围）

**C1. 全仓库检索**

- 在源码和测试中检索以下字符串，按文件列出出现位置和用途：`reconnaissance`、`area_coverage`、`shared_coverage`、`recon_`、`equal_strip_lawnmower`、`monotone_entry_order`、`coverage_ratio`、`partition_axis`。
- 把每处归类为：(a) 任务本体/枚举限制；(b) 协议版本常量；(c) 生成器/采样器；(d) 验证器/指标；(e) 数据审计；(f) 测试；(g) 其他。

**C2. family 标识**

- 在 `generation.generate` 中确认 `family_id` 的构造方式，以及 `family_namespace` 的哈希包含哪些 profile 字段（是否包含 `template_spec`）。
- 做一个内存干跑：使用同一 `master_seed` 和 `base_index`，仅修改 `template_spec` 中一个无关字段（例如 `planner.tracking_margin_m` 或 `mission` 中某个数值），比较两次生成的 `family_id` 是否相同。输出目录放在 `audit_v04/tmp/`。
- 用 `dataset.family_split` 计算：若同一物理场景分别产生 `recon_<id>` 和 `patrol_<id>` 两个 family 字符串，它们被分到同一 split 的概率。可对 100 个 base_id 实测比例。

**C3. 协议**

- 阅读 `protocol.py`，列出全部协议字段及其当前常量值。
- 列出 `dataset.build_dataset`、`episode_loader.load_episode`、`analysis` 中对协议的全部校验点。
- 回答：如果新增一个 Patrol 任务，并使用不同的 `semantic_validation_version`，在哪一步会被拒绝？`mission.intent` 本身是否是协议字段？要让两类意图共存于一个数据集，最少需要改动哪些常量或函数？

**C4. 任务 schema**

- 在 `mission_schema.normalize_mission` 中找出 `intent`、`objective`、`planner.name`、`assignment`、`observation_model` 的取值限制位置。
- 说明新增 `intent=patrol` 时需要修改的校验分支。

**C5. 场景采样器与随机起点的干跑实验（重要）**

- 在 `generation._sample` 中确认：区域尺寸是否由飞机数决定（`count × strip_width`）；生成点是否放在各自未来条带的中线上；`entry_sides` 的默认值；`heading_deg` 是否固定。
- **干跑实验**：保持区域参数分布不变，把飞机生成点改为"与意图无关"的随机布局（不按条带对齐）。至少测试以下三种布局，每种 200 个样本：
  1. 区域一侧随机散布；
  2. 区域外随机方向的随机散布；
  3. 紧凑编队，整体随机平移和旋转。
  
  对每个样本在内存中调用 `compile_task`（不启动 SITL），统计接受率和拒绝原因分布。拒绝原因如路径交叉、间距不足、预算超限、阶段数超限等，按异常消息归类。
- 说明 `monotone_entry_order` 在随机布局下是否容易产生交叉的进入路径。

**C6. 数据审计的侦察专用部分**

- 列出 `dataset_audit.audit_dataset` 中哪些指标只对侦察有意义，哪些是通用的。
- 确认 `_content_hash` 只能检测去掉身份字段后完全相同的输入。

**C7. 样本资格的粒度**

- 确认 `benchmark_eligible` 是否只在 episode 级别定义，是否存在任何窗口级或前缀级的资格字段，以及 `mission_success` 在资格判断中的位置。

---

### D 组：多样性与近重复

**D1. 拓扑签名分布**

- 对 `generated/recon_pilot_v03_20260930/` 的全部 100 个任务，计算拓扑签名 `(飞机数, partition_axis, lanes, return_required)`，其中 `lanes = ceil(条带宽度 / lane_spacing_m)`。报告不同签名的数量和频数。
- 再报告"轴等价"版本，即把 east / north 视为同一拓扑后的签名数量。

**D2. 跨 split 的签名重叠**

- 用 `dataset.family_split`（默认 salt）计算每个 family 的 split。报告：test 中的 family 有多少比例的拓扑签名在 train 中出现过。

**D3. 连续参数抖动幅度**

- 报告条带宽度、扫描长度、进入距离、区域位置、速度的实际采样范围，以及同一拓扑签名内各参数的相对标准差。

---

## 4. 报告要求

把最终报告写到 `audit_v04/audit_report.md`，结构如下：

```markdown
# swarm-task-sim v0.4 前置审查报告

## 0. 基线
- HEAD 提交、版本号、包目录、测试结果、数据目录核对

## 1. 结论总表
| 编号 | 被审查的怀疑 | 状态（证实/否定/部分成立/无法确定） | 一句话结论 | 关键证据位置 |

## 2. 逐项结果
### A1 ……
- 状态：
- 证据：（文件:行号 + 摘录，或数字/表格）
- 对 v0.4 的影响：
- 改动范围估计（如适用）：
（A1 到 D3 逐项）

## 3. 文档与源码不一致之处
| 文档位置 | 文档描述 | 源码实际 | 影响 |

## 4. 审查中额外发现的问题
（不在清单内、但你认为会影响多类别 benchmark 有效性的问题，同样给出证据）

## 5. 未能完成的项目及原因

## 6. 附录
- 分析脚本清单（audit_v04/ 下的文件名及用途）
- 完整数据表
```

写作要求：

- 用中文撰写；代码标识符保持原样。
- 数字给出具体值和分母，例如"7/10 个 episode"，不要只写"大部分"。
- 不要提出完整的设计方案，只在"改动范围估计"中列出涉及的函数和文件。
- 报告控制在可读长度内；冗长的原始表格放进附录或单独的 CSV 文件。

完成后，在终端输出报告路径和结论总表。
