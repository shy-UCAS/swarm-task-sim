# M3 第 0 步复述（待用户确认）

**基线与范围。** 当前分支 `v07-scene`，完整 HEAD 为 `7aab263b201aa016c93d966e5b68bb1290c4f630`，与 M3 计划一致。开始核对时已跟踪文件无修改，仅有用户提供的未跟踪文件 `docs/v07/m3/M3_instruction_unified_geometry.md`；保留原状。沿用项目 `.conda-env` 指定的 Conda `llm`，已实际核实解释器 `C:\Users\shy\anaconda3\envs\llm\python.exe`、Python 3.12.3，Shapely 可用，命令使用 PowerShell 7。本次仅完成计划 §3 核对及本复述；确认后只实施 M3a（C1–C8），不做 M3b、M4、弱斥力或真实无人机控制。

**数据流与过境形态。** 从已登记 descriptor／任务组构造 TaskSpec，固定身份、成员、目标、执行方式、family 条件、公共分股、参数分布及几何种子；场景和初始状态独立传入，规格不保存新生成航点。随后计算角色自由空间与作业可行区间，抽取过境形态，按物理位置在既有分股内分配成员到槽位，再连接初始位置、集结、对齐、作业、撤离，精确检查整条折线，输出真实模板及 RouteBundle。后者为每成员 `[K,3]` ENU 航点、零初始延迟；身份及列顺序沿用 descriptor，接入现有组／episode 装配，再交 M2 预演与时刻逻辑、M1 实测标签和审计。

过境是穿过目标预警环带的通行弦：方向 \(U(0^\circ,360^\circ)\)，弦位置分位 \(U(0,1)\) 映射到可行区间，以 0.5 概率加入一个 \(10^\circ\!–30^\circ\) 折点；全航线只访问目标预警区一次，不主动驻留或重访。沿用 family 的速度、高度、横向间距；集结距目标预警区外缘 50–250 m，首次进入前至少 100 m 对齐，撤离点在所有预警区外 50–300 m。限制区／地图边界余量 35 m、禁入圈层余量 10 m；同向走廊按 \(35+1.5\times\text{编组半宽}+2\) m，曲线弦高误差不超过 1 m、相邻航点至少 1 m。多向最大成对进场航向差瞄准 ≥90°，不改 M1 ≥60° 分类门槛，不增加成功条件。保留每组 200 提案、1000 组合、局部作业 20／连接 10 次、5 轮预演及每版 20 次时刻抽样；同目标方位差 30°、同向接近路程 130% 规则不变。

**模块与接线（路径相对项目目录；同一行并列文件省略共同目录）。**

| 位置 | 拟实施／复用方式 |
|---|---|
| 新建 `task_v07/unified/spec.py`、`free_space.py`、`shapes.py` | 独立规格、可行域／精确等距线、形态提案；M3a 只开放过境形态。几何子流沿用组级派生种子，再按 `unified-geometry-r1:{proposal_index}` 派生，不含时刻模式、draw 或列号。 |
| 新建 `task_v07/unified/assign.py`、`route.py`、`checks.py`、小型 `adapter.py` | 复用公共分股，物理位置排序、ID 打破并列；共享连接、真实元数据和逐点／逐段检查。复用 `geometry.geometry_facts`、`ExactVisibilityPlanner`，在私有视图内缩地图，不把非凸带孔自由空间当凸设施，不重复膨胀余量。 |
| 新建 `configs/generator/geometry_v07_r1.json` | 仅存新增几何参数与版本；已有 M2 参数直接读取原配置。 |
| 修改 `task_v07/expansion/group_candidate_pool.py`；必要的入口透传涉及同目录 `candidate_search.py`、`scripts/run_v07_s2_episode_batch.py` | `build_group_pool` 的新入口调用上述链，返回原有 `index/cost/skeleton/bundle/checks/bearing_deg/target_id`；cost 为真实接近段长度、bearing 为真实作业方位。新后端失败或遇未支持角色明确拒绝／报错，不调用旧 `Context`、`draw_role` 或其角色逻辑；旧路径仅允许显式 legacy 回归选择，并以 G11 哨兵测试验证无回退。 |
| 原样复用 `pipeline.assemble_skeleton`、`episode_pipeline.assemble_episode`、候选组合与 `choose_eligible` | 保持成员、目标、公共条件、配对合同和选择规则；模板显式填写 `retreat_warning_minimum_m=50`，避免旧默认 200 m，endpoint 与实际末点一致。已核对 `evaluation/role_evaluation`、`criteria_diagnostics`、`group_truncations`、`abort_planning` 的字段读取；不虚构其他角色字段，不声称已验证中止执行。 |
| 新建 `tests/test_v07_m3_geometry.py`、`tests/test_v07_m3_integration.py`、`scripts/run_v07_m3_checks.py`，M3 专用小试入口 | 执行 G1–G7 的适用部分、G8 过境、G10 适用部分、G11–G12；G9 及其他角色专属分支留待 M3b。固定输入、结果与报告按计划写入 `docs/v07/evidence/m3/` 和 `M3_report.md`。 |

冻结且不修改：S1 场景资产及公共合同，`sampling.py`、`public_approach_shape.py`、身份／列置换／配对及输入白名单，`criteria_v07_r1.json` 与 M1 检测器、标签、审计数学定义，`unified/rehearsal.py`、`timing.py`、`generator_v07_r1.json`，`execution.py`、fastsim 内核及冻结配置、`terminal_*`／`stop_*` 语义。只适配新几何输出与入口，不改判据、预算或测试预期。

**固定输入。** 按 §8.1 读取 `docs/v07/evidence/m2/qd_summary.json` → Q-D `attempt_m2_trial_20261016T022948423699Z/registration.json` → `descriptor_attempt`：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s2infra_20261014T023604Z_d2566191`。以其中 `private_skeleton_descriptors.json` 的 `base_intent`、`common_draw.approach_mode` 为准，同格第二个取 regular 集合中 skeleton_id 稳定排序的首个不同项；不使用历史成败筛选。关联三个 family 的场景、初态共六份文件均与源登记 SHA256 一致。

| 逼近 | skeleton_id | 用途 |
|---|---|---|
| 同向 | `family_s12_5024cb2ccea653ae_ext_000_regular` | Q2 + Q3 固定 |
| 同向 | `family_s12_4d13d93f9171c446_ext_000_regular` | Q2 同格首个不同项 |
| 多向 | `family_s12_f2adfbfae12fbbad_ext_000_regular` | Q2 + Q3 固定 |
| 多向 | `family_s12_4d13d93f9171c446_ext_005_regular` | Q2 同格首个不同项 |

确认后先做四骨架纯规划 Q2，再做上述两个固定骨架 Q3；不复用 Q-D 旧航线、不换样本。Q3 最多 8 进程、墙钟硬上限 30 分钟，两个骨架均须严格成功配对、实测时序及递次批次成员／顺序一致、所有组完成且质量／独立审计通过；复核预演不一致为 0，调用 `_paired()`、`make_views()`，不要求 primary 非零。C1–C8 分别提交，以 `M3-C1:` 至 `M3-C8:` 开头；通过后报告提交范围并推送检查点 1 到 `v07-scene`，随即停止等待静态审查。

**差异与未决。** 无新的实质冲突或无法执行项。已读 M3 计划全文、设计 r1.2 第 3、4、7、8、9 章以及 M1/M2 指令和报告。设计滞后按以下已批准依据处理：驻留首尾距离引用 [M1 §7.2](../m1/M1_instruction_criteria_r1.md) 与 [M1 已确认复述](../m1/00_restatement.md)；T5 为 580.1 s（±0.1 s），监视核心事件取进入预警区、重访另存 t1/t2、P2 未知，沿用 M1 批准口径；设计 §7.1 的旧时刻调用、§4.5 的失败分类、§9 的不推送表述，以 [M2 指令](../m2/M2_instruction_timing_rehearsal.md)、已验收 M2 实现及本轮明确推送授权为准，不改旧竖切标签路径。单调分配不视为全程无交叉证明。上述附注不重定义判据。

**当前停止点：** 用户本轮“先复述然后停下”优先于计划 §1／§3 的直接继续表述。本次未实施 C1–C8、未运行测试或仿真、未提交或推送。等待确认后再继续；后续自编工具错误自行修复并记录，P0、必须修改冻结内容、固定输入无法确定或超墙钟上限才停下汇报。

**后续批准补注。** 用户已确认本复述并授权实施 C1–C8：默认新后端，旧规划器仅显式 `legacy`，保留依赖旧规划器的测试并报告其选择修改；Q2 的四个固定骨架必须全部通过整航线检查，15 分钟内不通过则停在 Q2 并给出拒绝分布与最接近通过的提案明细；Q2/Q3 逐骨架记录进场最大成对航向差、实测最小间距、规划耗时、提案数，仅作诊断。Q2 不运行仿真，因此实测最小间距记为 null 并注明未执行。
