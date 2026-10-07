# v0.5 最小双意图数据契约（`data_contract_v0`）

本契约适用于 v0.5 修订版 r1、r1.1 及 [r1.2/r1.2a/r1.2b 补充](v0.5_r1.2_addendum.md)下生成的侦察、巡逻 `mission_v3` 数据集和独立的 `language_zh_v0` 描述层。r1.1 新增 `random_spawn_v2` 与 `dual_intent_v05b`；[v05c 续补](v0.5_r1.1_v05c_addendum.md)仅在该采样器中增加固定初始航向策略。原 `dual_intent_v05`、`dual_intent_v05b`、`dual_intent_v05c` profile、DR、诊断、VP1 原始运行/分析及其 r1 FAIL 判定作为独立档案保留，不覆盖或改写；PP08 原运行、两版分析和原停止判定也保留，后续重分析与新判定另存。数据集的单位是完整 episode；描述层只引用已经导出的、经过哈希核对的 episode。本文规定算法侧能使用的输入、监督标签、划分和版本核对，不把验证器或规划器的内部证据混入模型输入。

## 1. 模型输入

`swarm_sim.episode_loader.load_episode(episode_dir)` 读取 `observations.csv`，返回 \(x\in\mathbb{R}^{T\times N\times 6}\)、\(mask\in\{0,1\}^{T\times N}\)、`t_s` 和 `agent_ids`。六个未归一化的 ENU 特征依次为 `east_m`、`north_m`、`up_m`、`ve_m_s`、`vn_m_s`、`vu_m_s`；采样网格为 10 Hz。缺失的飞机/时刻位置填零，且对应 `mask=false`，零填充值不能当作实测位置。速度与位置来自合作式 FCU 遥测；SIM 真值只供监督与核对。当前加载器不执行归一化，消费方如需归一化，必须仅用训练 family 拟合变换参数，并在验证/测试中冻结。

`agent_ids` 用于关联同一架飞机的时间序列。v0.5 场景生成器随机分配编号；编号不携带预设空间排序含义，也不得把其字符或数字后缀当作位置、角色或意图特征。`t_s` 是相对运行时间。公开场景信息仅允许目标区域矩形的四个水平 ENU 角点。`swarm_sim.episode_loader.load_public_scene(episode_dir)` 只返回四个 `(east_m, north_m)` 坐标对，按西南、东南、东北、西北排序，形状为 `(4, 2)`；它核对 `task.json` 的 episode 附件哈希，并根据 `mission.target_region_id` 选择目标矩形。不得把 `task.json` 或 `shared_scene.json` 整体输入模型。当前 `load_episode` 不把矩形自动加入 `x`。

r1.1 的 `random_spawn_v2` 与意图无关，只生成 `line` 横队；机数按基础场景编号循环取 \(N=[2,3,4]_{i\bmod 3}\)，不随同一基础场景的候选重抽改变。目标区域宽、高分别为 \(N u_x\) 和 \(N u_y\)，其中 \(u_x,u_y\) 独立均匀采样于 \([11,16]\,\mathrm{m}\)。相较原 `random_spawn_v1`，区域尺寸范围扩大，机数从独立随机抽取改为按层轮流分配。v0.5 新 profile **不包含集群编队**：同时出发的阶段放行机制，加上 \(\tau\) 时间窗内的间距检查，在当前名义规划判据中排斥前后跟随的布局；原 DR 中四机集群 64 个候选均不可行，61 个首先在 approach 阶段违反间距。这个结论针对当前采样、规划和时序规则，不宣称所有集群布局在物理上不可行。

v05c 的 `heading_policy="fixed_zero"` 使所有飞机的初始航向为 \(0^\circ\)。采样器仍按原顺序抽取每架飞机的航向随机数，随后丢弃该值；因此同一种子、同一基础场景和候选序号下，除航向以及依赖航向的 `family_id` 外，采样参数和规划结果应与 v05b 逐一相同。`heading_policy` 缺失时保留 v05b 的均匀随机航向行为。固定航向是 v0.5 验证与试生产的运行约束，不是增加给模型的输入字段。

## 2. 标签与监督对象

`labels.json` 给出 episode 级指定意图（`reconnaissance` / `patrol`）、任务结果、SIM/FCU 双通道语义指标与一致性，`label_provenance.validator_versions` 记录意图验证器版本。`observer_facts_v0` 将这些整理为 `labels.assigned_intent`、`labels.return_required` 和 `labels.mission_result`；后者保留 `success` 及各有效子条件，例如侦察的覆盖/返航，巡逻 `perimeter_revisit_v2` 的最大重访间隔/返航。v2 中每段经过次数照常计算输出，只作记录，不参与成功判定；每段经过次数不少于 \(K\times N\) 的条件以及据此生成的失败句型停用。旧 `perimeter_revisit_v1` 分析保留原子条件和原判定，不能静默按 v2 解释。**任务成功与否是单独的结果标签，不能由样本是否质量合格推断。**失败 episode 只要质量合格、双通道语义一致，仍可有描述。

`phase_windows.json` 的逐机阶段窗口只作标签或离线分析，不是轨迹输入。描述层的 `segments` 是群体阶段段落，起止时间由各机 `start_s`、`arrival_s` 的中位数汇总，并带 `boundary_source`；`events` 可记录 `first_boundary_coverage`、`first_complete_lap` 等已验证时刻。阶段和事件均是监督/解释字段，不能作为模型输入。约 1 秒的阶段边界精度以及 `arrival_s` 的兜底来源需随证据一起解释，不能把边界写成精确模式切换时刻。

## 3. 三类信息严格分开

| 类别 | 例子 | 可如何使用 |
| --- | --- | --- |
| 任务标签 | 指定意图、要求返航、任务各子条件结果 | 监督与评估；不能伪装成轨迹中直接“看见”的事实 |
| 仿真模型指标 | `coverage_ratio` | 需同时附 `coverage_model`，例如理想水平圆盘观察模型；它不是物理相机或传感器的实测覆盖 |
| 轨迹可见事实 | `num_uavs`、进入方位、检测出的运动模式、轨迹可证的返航、逐机圈数 | 可在通过逐项 SIM/FCU 核对后写成“观察到”；不同通道不一致的事实不得进入任何描述 |

`observed_pattern` 必须由版本化的 `pattern_detector_v0` 从主阶段轨迹判出，可能为 `perimeter_loop`、`parallel_strips` 或 `unclear`；不得用指定意图反推观察模式。扫描方向 `scan_orientation` 从轨迹的直线段提取，不读取规划剖分轴。`return_observed` 从返航轨迹判断，取 `true` / `false` / `null`，不得直接使用“不要求返航即成功”的验证器结果。巡逻逐机圈数来自按顺序的航线进度映射，不能由群级边界经过次数替代。连续值须按既定 2% 或 0.5 s 容差逐项跨通道比较。

## 4. 描述文件与绑定

执行 `python main.py describe <dataset_dir> --output <sibling_output_dir>` 后，描述输出位于数据集之外的新目录，原数据集不修改。`language_manifest.json` 包含 `dataset_manifest_sha256`、描述/事实/模板版本、episode 和描述计数，以及 `artifact_sha256`。`facts/<episode_id>.json` 保存可生成描述 episode 的 `observer_facts_v0`：`labels`、`observed`、`model_metrics`、`segments`、`events`、`channel_check`、`provenance`。`descriptions.json` 的结构为：

```json
{
  "schema_version": 1,
  "language_version": "language_zh_v0",
  "templates_version": "templates_zh_v0",
  "dataset_manifest_sha256": "<SHA256>",
  "descriptions": [
    {
      "description_id": "<identifier>",
      "episode_id": "<identifier>",
      "text": "<中文描述>",
      "episode_split": "train",
      "template_partition": "train",
      "sentences": [
        {"template_id": "<identifier>", "text": "<一句话>", "fact_ids": ["<引用的事实路径>"]}
      ],
      "facts_version": "observer_facts_v0",
      "template_version": "templates_zh_v0"
    }
  ],
  "skipped": [
    {"episode_id": "<identifier>", "episode_split": "validation", "reason": "<跳过原因>"}
  ]
}
```

只有 `episode_quality_eligible=true` 且 `semantic_consistency="agree"` 的 episode 可生成描述，预期每个生成 3 条 train 模板措辞和 1 条 test 模板措辞；其余 episode 每个只保留一条带原因的 `skipped` 记录。每句记录模板 ID 与事实 ID 供核对，文本不得泄漏飞机编号、分配关系、条带编号、航点、规划器名称、执行事件或任务 ID。数值、枚举、意图措辞与事实不一致，或引用双通道有分歧的事实时，描述必须拒绝输出。消费方先核对数据集 manifest 的 SHA256 与描述 manifest 中的绑定值，再核对输出文件哈希；原数据集内容改变后须拒绝沿用原描述。

## 5. 两个独立划分维度

`episode_split` 来自 `dataset_manifest.json` 中对 `family_id` 的确定性划分（目标比例 train/validation/test 为 70/15/15；小数据集不保证实得比例）。同一原始场景的意图变体、重试和派生窗口必须继承同一 family，不能跨划分。`template_partition` 只决定中文措辞来自 train 组还是 test 组；模板组不重叠，绝不改变 episode 所属场景划分。

| `episode_split` | `template_partition` | 使用边界 |
| --- | --- | --- |
| train | train | 唯一允许的正式训练组合 |
| train | test | 仅用于措辞泛化诊断，不能称为场景测试 |
| validation | 任意 | 验证，不能回流训练 |
| test | 任意 | 测试，全部不得参与训练 |

尤其不能因为同一 test family 的描述使用了 train 模板，就将其纳入训练。评估时须同时报告 family 划分和模板划分，避免混淆场景泛化与措辞泛化。

## 6. 禁止作为模型输入的字段

禁止输入任务定义文件、规划产物、`semantic_plan`、执行事件、真值轨迹、验证器内部结果、`execution_metrics`、质量字段、`family_id`、随机种子及由这些字段直接派生的答案提示。质量字段只用于筛选；`family_id` 只用于划分及泄漏检查；任务/语义/事件/执行附件只用于标签、描述校验与审计。`episode_id`、`description_id`、`template_id` 和 `agent_ids` 的字符串形式只用于关联，不得作为捷径特征。公开区域角点是本条唯一明确放行的场景几何白名单。

## 7. 样本筛选和结果统计

意图样本以 `episode_quality_eligible` 为质量门槛，不能用 `mission_success` 取代它；任务成功率在质量合格样本中按 `mission_success` 单独统计。描述层再要求 `semantic_consistency="agree"`。应分别公布全部 episode、质量合格 episode、质量合格且语义一致 episode、描述成功和跳过数，不能把缺失/不一致的事实或未知时钟解释成通过。失败任务不得自动被丢弃或被写成另一子条件失败。

r1.2 已完成验证及 PP01–PP08 所用的历史策略 `v05_acceptance_r1_2` 分为硬、软两类：参数与固件、机载任务参数、受保护文件哈希、真值最小机间距低于 `min_separation_m`、零长度航段，以及完整证据证明巡逻圈数不等于计划 \(K\)，为硬门禁；验证运行任一通道任务失败或语义不一致也为硬门禁；未分类异常影响或无法判断是否影响数据、标签、描述正确性时停止。该历史策略与原判定保持不变。AV-1、AV-2、AC4 的 \(D>\tau\) 或 \(D\) 不可计算、圈数为 `null` 仅标记并报告，不影响 `episode_quality_eligible`，未知不可宣称通过。SITL 不模拟机体碰撞，机间安全通过真值间距直接判断；\(D\) 是规划时序假设的诊断指标。

从 PP09 起至批量结束采用 [r1.2b 当前有效规则](v0.5_当前有效规则.md)：单次仅参数与固件、机载任务参数、受保护哈希、真值机间距、基础设施故障或磁盘不足可停止；任务失败、标签不一致、圈数不符等语义结果、episode 质量不合格和新异常保留标记，不逐次停止。整体唯一停止条件是本阶段最近至多 20 次运行中，异常运行达到 5 次；异常定义为任务失败、标签不一致、episode 质量不合格三者的逻辑或，同一运行触发多项只计 1 次。未满 20 次用已有全部；试生产 PP09 起计、不纳入 PP01–PP08，批量重新计，两阶段互不累计。当前接续授权要求以新版本控制器和独立台账实施该规则，并执行至暂停 1；旧 `v05_acceptance_r1_2` 及其判定保持不变，不能静默解释为新策略。最终试生产/批量验收及质量资格计算照常执行，软标记不得直接改变质量资格。

已携带 r1.2 策略的分析/episode，其软门禁标记位于质量附件 `quality.json.validation_policy.soft_flags`，与 `validation_policy.version="v05_acceptance_r1_2"`、`stage`、`hard_checks`、`hard_failures`、`individual_pass`、`episode_quality_eligible` 一起保存。各标记含 `code`、`status`、`channel`、`phase`、`agent_id`、`value`、`threshold`、`reason`，AC4 的 `source` 区分主值/事件交叉核对；只列触发或未知项，原数值与完整证据仍在相应 AC4、执行指标附件。`external_checks_required` 明列须由控制台账核对的受保护文件、冻结输入/固件身份、基础设施与磁盘，不能以分析层通过代替。此质量附件由 manifest 哈希绑定。`individual_pass` 是该版本策略的阶段验收结果，不能替代任务标签或质量资格。r1.2b 已完成的 7 次巡逻外部离线分析未传 `acceptance_policy`，因此不附带 `validation_policy`，只给出新语义判定；原软标记仍在各自旧分析中保留，不能把新附件缺少策略误读为“无软标记”或“新门禁通过”。质量与诊断字段不属于模型输入。汇总数字需附分母；暂停 1 软标记按意图汇总，已有阶段分布直接引用。

## 8. 消费方版本与完整性检查

加载前须核对数据集 `schema_version=2`，episode manifest 的哈希、质量策略指纹 `quality_policy_sha256`，以及数据集与 episode 完全一致的语义协议六字段：`task_kind=mission_v3`、`ontology_version=multi_intent_mission_v1`、`label_schema_version=3`、`semantic_validation_version`、`eligibility_protocol_version=multi_intent_quality_v1`、`execution_constraints_version=multi_intent_execution_limits_v2`。`semantic_validation_version` 在显式选择 `perimeter_revisit_v2` 的新分析中为 `multi_intent_validation_v3`，同批侦察也须显式选择相同协议；旧 `multi_intent_validation_v2` 及 `perimeter_revisit_v1` 继续支持并保存原语义。不同统一协议或质量策略不能默默混合导出。`load_episode(..., verify_hashes=True)` 执行基础附件和协议校验，但消费方仍须检查其自身所需的事实与描述版本。续接导出需要显式绑定新的外部分析路径，不能为方便导出而覆盖原分析或修改旧 latest 指针。

v0.5 route 分析还须核对 `observation_processing_version=v3_observation_v1`、`duplicate_policy_version=exact_duplicate_drop_v1`、`timeline_policy_version=full_stream_strict_v1`、`clock_model_version=passive_system_time_piecewise_v1`、`ac4_timing_version=ac4_relative_progress_timing_v3`、`execution_artifacts_version=execution_artifacts_v2`，以及 `labels.json` 的 `label_provenance.validator_versions`。历史 `route_progress_version=ordered_route_progress_v1` 保留；r1.2 新分析明确使用 `ordered_route_progress_v2`，匹配前一节点时刻之后第一次有效经过内最近样本，进入/离开滞回半径为 \(3.0/3.5\,\mathrm{m}\)，不能静默混用 v1/v2 结果。描述消费方另核对 `observer_facts_v0`、`pattern_detector_v0`、`templates_zh_v0`、`language_zh_v0` 和 manifest SHA256；版本变更不能把旧指标或旧描述当作同一口径。

## 9. 与论文 Stage B 字段的对应

| Stage B 所需信息 | 本轮提供情况 |
| --- | --- |
| 轨迹和时间戳 | 已提供合作式 FCU 遥测轨迹与 10 Hz 相对时间 |
| 任务标签 | 已提供 episode 级指定意图、任务结果及子条件 |
| 关键时刻意图 | **未提供**；只有 episode 级意图、阶段段落和部分经验证事件，不能充当时刻级意图标签 |
| 集群标签 | **未提供** |
| 地理环境 | 只有目标区域矩形；不是丰富地图或真实地理语义 |
| 设施 | **未模拟** |
| 天气 | **未模拟**，无风 |

这些缺项不得用默认值、规划内部信息或推测文本补成虚构的观测字段。

## 10. 数据集定位与已知限制

本轮产出的是**算法链路开发用的最小数据集**，用途是让"轨迹 → 编码器 → 桥接 → LLM → 描述"整条链路跑起来。它**不能**用来报告意图识别准确率，原因包括：

- 每种意图只有一种执行策略；
- 侦察在区域内部飞，巡逻沿边界飞，空间位置本身就可能让分类变得很容易；
- 两类意图的时长分布不同，没有做均衡；
- 没有捷径探针，也没有分布外测试划分。

这些都属于后续"可信 benchmark"阶段的工作。

本轮仍使用合作式 FCU 遥测、已知身份、理想化观察模型和公开矩形区域，不代表真实传感器、复杂设施或天气条件。语义阶段采用屏障，转角切弯、匀速名义时序与 `arrival_s` 兜底可能影响阶段边界和时序解释；`arrival_s=trajectory_min_distance` 不保证已经低速或稳定悬停。若数据集的时钟等级只达到 `acceptable`，不能宣称已满足严格同步基准。尚无窗口级样本、统一归一化、近重复检测或分布外测试划分。以上限制及本轮实际验证中新增的限制，以暂停 1 合并报告和最终报告中的实测证据为准；不能预先声称 SITL 验证已通过。

r1.2 正式固定终点驻留 `terminal_hold_s=0`，语义为 `integer_seconds_v1`，取消 VP4 和 HD；v0.4 实际执行驻留为 0 是本决定的依据。初始航向固定为 \(0^\circ\)，阶段边界约 \(1\,\mathrm{s}\) 的精度仍是已知限制。各运行进场航程、名义时长、出发/到达时刻和初始航向到进场终点方向的转角列入暂停 1 的诊断附件，不参与门禁或选例，不作为输入特征。

v0.5 的 v05c 验证与试生产只支持 \(0^\circ\) 初始航向，不支持随机初始航向。历史 v05b VP1 显示 `SIM_PLD_YAW` 读回值与 `--home` 航向相关；目前这是基于三机读回对应关系的**推断**，尚未建立固件内部映射或大于 \(180^\circ\) 航向的实测规则。`wp_s_parameter_comparison_v2` 保持不变，任何未解释的参数差异仍阻止起飞。将来若要支持随机航向，必须先取得航向大于 \(180^\circ\) 时 `SIM_PLD_YAW` 如何取值的实测证据，再建立与航向绑定的版本化参数比较规则；不能把该参数无条件放入豁免名单。
