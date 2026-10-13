# M2 恢复实施与最终验收

日期：2026-10-12。本轮依据用户明确批准恢复 P0 修复和连续实施的指令执行；基线为 `codex/fast-dynamics / a46f034`。状态：**M2_COMPLETE，固定范围代码与测试验收通过**。本报告不替换 [此前 P0 停止记录](M2_runtime_report.md)，旧 `attempt_01` 原样保留。

本轮证据根：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m2/M2_runtime_20261012/attempt_02_resume/`。验收只使用已登记的 12 个 T1/T4 开发任务；4 个负例分别配在各飞法的双机任务上。没有扩充验收输入、读取留出数据、启动 SITL 或进入 M3。

## 修复及影响范围

`adapter.py::analyze_semantics` 的 `planned_phases` 改为遍历实际 `scene.phases`，按其对应的已编译 `semantic_plan.execution_phases` 取语义阶段，再保持顺序去重。注册表 `semantic_phases` 仍是合法阶段词汇表，不再充当本条任务的计划事实。

独立测试读取原字节的真实往返扫描 2 机和 3 机 TaskSpec，分别断言 `return_required=false/true`，直接写死预期 `[approach, observe]` 与 `[approach, observe, return]`。测试在尚未执行飞行时也检查计划阶段，避免将“计划”误改为“已执行”。验收脚本另外从实际编译场景的阶段记录检查导出标签，不调用适配器辅助函数生成预期。

`build_dataset` 原样复制 `labels.json`，`load_episode.targets` 暴露整个标签对象，因此错误阶段会进入模型监督目标。它不进入六维观测特征 `x`。当前 `extract_observer_facts`、描述模板和内部 `_SentencePlan.slots` 不读取 `planned_phases` 或 `planned_behaviors`；要求返航取 TaskSpec 的 `return_required`，观察到返航取轨迹，二者分开。此次修复会改变数据集哈希及由其确定的模板变体种子，因而不同运行的措辞可能变化，但不是把错误阶段传入描述。

只读核对 M1 的 `success_01` 至 `success_05`、`semantic_failure`、`unknown_timeout` 共 7 条最终样本：全部 `return_required=false`，实际编译 `[approach, transit]`，旧标签却为 `[approach, transit, return]`。**7/7 受同一目标字段缺陷影响**，保留原产物和冻结 M1 读取兼容，不重跑或改写历史。完整位置及逐条记录见外部 `m1_impact.json`。历史加载/审计通过只证明旧契约自洽，不能抵消这一已知标签问题。

## 字段来源表（只读梳理）

`T`＝编译后任务及其规范 TaskSpec；`M`＝实测轨迹、真实执行事件和仿真钟；`R`＝意图注册表及对应注册验证器常量。组合表示判定同时需要这些来源。路径、哈希、协议版本、模板词句等不是任务事实，单独标为“工程元数据”，不强行冒充上述三种事实来源。`C` 代表 `truth/observation` 两个通道；`A` 代表机号；`[]` 代表每个元素。同类字段合并在一行，适用于 `labels.json` 及导出后的同名字段；辅助证据文件也在表末列出。外部 `field_inventory_final.json` 保留实际叶字段清单。

| 文件／字段（嵌套路径适用于每个元素） | 来源 | 实际生成依据及事实边界 |
|---|---|---|
| labels：`requested_intent`、`assigned_intent`、`objective` | T | 规范 TaskSpec 选定的意图与目标；注册表负责校验，不是从轨迹推断隐藏意图 |
| labels：`planned_phases[]` | T | **本轮修复**：实际编译阶段的有序去重结果；可选返航不存在时不得写入 |
| labels：`planned_behaviors[]` | R＋T | 按已编译意图选择固定计划类别 `area_scan/perimeter_loop/direct_passage`；三类都对应必有的服务阶段，不是已观察结果，也不包含可选返航 |
| labels：`observed_behaviors[].name`、`rule_version` | R | 注册的被评估行为名与实际调用的验证器版本；巡逻实际为 `perimeter_revisit_v2` |
| labels：`observed_behaviors[].agent_ids[]` | T | 编译车辆集合，不是从注册表写死机数 |
| labels：`observed_behaviors[].status`、`min_segment_visits`、`max_revisit_gap_s` | M＋T＋R | 由实际覆盖／通过／重访度量及正式条件产生；`verified/failed/unknown` 保留三值区别 |
| labels：`observed_behaviors[].evidence_basis` | 工程元数据 | 声明快速动力学真值位置及服务窗口；不伪装成独立传感器 |
| labels：`mission_success`、`mission_success_observation`、`semantic_consistency`、`mission_metrics.C.mission_success` | M＋T＋R | 双通道实际度量与任务条件的合取／一致性；理想观察派生于 plant，不是独立证据源 |
| labels：`run_status` | M | 真实执行完成或超时状态，与任务语义成功分开 |
| labels：`schema_version`、`task_kind`、`label_provenance.{requested_intent,mission_success,mission_success_observation,scope,semantic_adapter_version,semantic_validation_version}` | 工程元数据 | 标签结构、来源声明和实现协议；没有把版本字符串当轨迹事实 |
| labels：`label_provenance.validator_versions.*` | R | 本条任务实际选用的注册验证规则，巡逻明确为 v2 |
| `mission_metrics.C.coverage.{requested_grid_m,cells,nx,ny,cell_width_m,cell_height_m,required_ratio}` | T | 区域尺寸、观察网格和所需覆盖率；均为模型／任务参数，不是覆盖结果 |
| `coverage.{model,model_version,discretization,area_weighting}` | R | 注册观察模型及网格解释常量 |
| `coverage.{covered_cells,global_coverage_ratio,repeated_cells,repeated_coverage_cell_ratio,repeated_fraction_of_covered,observing_agents,evidence_complete,success}` | M＋T＋R | 实际高度合格的点／线段对网格覆盖、重复覆盖与完成证据；不由名义路线赋值 |
| `coverage.per_agent.A.{covered_cells,coverage_ratio,evidence_complete,leave_one_out_coverage_drop,missing_service_windows,valid_service_points}` | M＋T＋R | 每机实际有效观察、证据缺口和移除此机后的覆盖变化 |
| `coverage.per_agent.A.service_windows` | T | 编译服务窗口条数；是否实际开始／完成另由事件和 evidence 字段决定 |
| `mission_metrics.C.return_to_launch.required`、`per_agent.A.{target,required_dwell_s}` | T | 是否要求返航、原始起点和要求驻留时长 |
| `return_to_launch.success`、`per_agent.A.{success,longest_dwell_s,nearest_m,evidence_complete,source_duration_available,reason}` | M＋T＋R | 按实际返航窗口、位置与驻留判定；`required=false` 时 success 为条件豁免的 true，**不表示实测返航**，此时 `per_agent` 为空 |
| `return_to_launch.per_agent.A.dwell_allowance_s` | T＋M | 记录周期在本条实际时钟上的允许余量，不是驻留测量值 |
| `return_to_launch.per_agent.A.time_basis` | 工程元数据 | `sim_clock_seconds`，不沿用 FCU 时间声明 |
| `mission_metrics.C.perimeter_revisit.{segment_count,required_visits_per_segment,nominal_revisit_interval_s,allowed_gap_s}` | T | 区域周长、分段长度、任务圈数、机数、计划速度与 gap factor；要求访问次数仅作诊断 |
| `perimeter_revisit.segments[].{segment_id,side,piece,start_xy_m,end_xy_m,length_m}` | T | 编译任务区域和 standoff 得出的周界分段几何 |
| `perimeter_revisit.{service_window_s,evidence_complete,evidence_issues,group_segment_visit_counts,min_segment_visits,max_revisit_gap_s,loop_segment_coverage,visits_pass,max_gap_pass,patrol_success,per_agent_laps_observed,first_boundary_coverage_time_s,first_complete_lap_time_s}` | M＋T＋R | 真实访问、初始／内部／末尾重访间隔与有序路线证据；v2 正式条件只含 `max_gap`，`visits_pass` 不决定成功 |
| `perimeter_revisit.segments[].{count,observed_lower_bound,initially_occupied_by,max_gap_s,max_gap_types}`、`visits[].{agent_id,start_s,end_s}`、`gaps[].{kind,duration_s,from_s,to_s}` | M＋T＋R | 真实轨迹进入各任务分段产生的访问与间隔；机号指向 T 中车辆 |
| `perimeter_revisit.per_agent_progress.A.{per_agent_laps_observed,first_complete_lap_time_s,evidence_complete,issues}` | M＋T＋R | 按展开路线的顺序实测经过节点，不能用计划圈数代替观察圈数 |
| `per_agent_progress.A.node_evidence[].{route_index,seq,nominal_s,cumulative_arc_length_m}` | T | 对应编译路线的索引、名义到达时刻和名义弧长，字段名保留“名义”含义 |
| `node_evidence[].{actual_s,match_distance_m,evidence_status,search_after_s,visit_interval_s,visit_ordinal,visit_count}` | M＋T＋R | 实际经过时刻、距离和访问顺序；未匹配则 unknown，不用名义时间补齐 |
| `node_evidence[].sample_only`、`perimeter_revisit.{version,success_conditions,visit_count_role}` | R | 验证规则声明：只采用实际样本证据；v2 的条件和访问次数诊断角色 |
| `mission_metrics.C.{per_agent_laps_observed,first_boundary_coverage_time_s,first_complete_lap_time_s}` | M＋T＋R | 同一巡逻实测结果的顶层映射，并非另一组计算 |
| `mission_metrics.C.rapid_passage.{version,thresholds.*}`、`per_agent.A.version` | R | `boundary_margin_m/max_cross_track_m/max_path_chord_ratio/low_speed_m_s/max_low_speed_duration_s/max_backtrack_m` 等冻结规则阈值，不是实测值 |
| `rapid_passage.{success,evidence_complete}`、`per_agent.A.{success,evidence_complete,entry_side,exit_side,crossed,inside_dwell_s,max_cross_track_m,backtrack_m,turning_rad,path_chord_ratio,interior_excursions,issues}`、`conditions.{entered,opposite_exit,straight,no_dwell,no_loop}` | M＋T＋R | 真实轨迹相对任务区域的几何和运动判定；字段中的实测 `max_cross_track_m` 与 thresholds 下同名阈值严格分开 |
| 导出 `observations.csv/truth.csv`：`t_s,agent_id,valid,east_m,north_m,up_m,ve_m_s,vn_m_s,vu_m_s`；support CSV 另有 `ae_m_s2,an_m_s2,au_m_s2` | M（机号为 T） | 真实状态、记录网格和有效掩码；当前 ideal observer 与 truth 相同，未添加传感器独立性 |
| `load_episode.{x,mask,t_s,agent_ids}` | M（机号为 T） | 仅从六维 observation 特征及掩码加载，10 Hz 半开网格；不混入意图、计划路线或真值标签 |
| `load_episode.targets.*` | 同上述 labels 各字段 | 整个 labels 对象原样导出，**包含 planned_phases**；作为监督目标而非观测输入 |
| `metadata.{family_id,family_scheme,control_mode,flight_pattern}`、dataset entry 的 `scenario_id,intent,agent_ids` | T | 编译任务／规范场景身份及执行方式；family 派生与当前校准／盲测划分是不同概念 |
| `metadata.{mission_success,semantic_consistency,episode_quality_eligible,benchmark_eligible,strict_benchmark_eligible,end_us,duration_s,invalid_intervals}`、manifest 的 `run_status,frames,clock_quality` | M＋T＋规则 | 实际状态、实际时长、质量／资格门槛；`strict_benchmark_eligible=false` 与 `training_eligible=false` 还受未校准后端政策约束 |
| metadata／manifest：`run_id,analysis_version,task_kind,ontology_version,label_schema_version,semantic_validation_version,eligibility_protocol_version,execution_constraints_version,quality_policy_sha256,evaluation_context,split,feature_columns,normalized,missing_row_policy,source_directory,protocol_version,simulation_backend,time_base,time_policy,lifecycle_scope,training_eligible,execution_mode,config_schema_version,behavior_version,reference_version,executor_version,component_versions` 及观察／去重／时间线／时钟／路线进度／AC4／执行产物处理版本字段 | 工程元数据 | 运行、协议、特征结构、策略和处理方式；`split` 是旧导出器按 family+salt 的数据集分桶，**不是 M3 冻结的 calibration/blind 分组**；本批全部是开发任务 |
| `dataset_manifest.episodes[]` 的同名任务／结果字段 | T／M，同前两行 | 复制已校验 episode manifest，不用注册表构造任务事实 |
| dataset manifest：`schema_version,quality_policy,quality_policy_sha256,semantic_protocol,mixed_semantic_protocols,mixed_quality_policies,split_salt,split_method,identity_policy,missing_family_policy,training_input,privileged_outputs,limitation,family_scheme,control_modes,allow_mixed_control_modes,mixed_control_modes,time_base,simulation_backend,time_policy,training_eligible`；entry 的 `source_analysis_directory,source_run,analysis_manifest_sha256,directory,simulator_version`；`counts.*` | 工程元数据；counts 为已导出实际条目聚合 | 导出规则、目录、版本与实得分母；`counts` 的质量／成功计数聚合相应 M 字段，不代表新执行任务 |
| facts：`labels.assigned_intent,labels.return_required`；`labels.mission_result.{success,conditions.*}` | T；M＋T＋R | 前两项是任务声明，后两项是实测条件；巡逻 v2 没有把 visits 作为正式失败条件 |
| facts：`observed.{num_uavs,entry_side,exit_side,observed_pattern,scan_orientation,loop_direction,per_agent_laps_observed,return_observed,max_revisit_gap_s,crossed,inside_dwell_s,turning_rad}` | M＋T＋检测规则 | 来自轨迹和实际窗口，几何检测阈值为规则常量；没有直接复制 flight_pattern 或计划 laps 作为 observed 值 |
| facts：`model_metrics.coverage_ratio`；`model_metrics.coverage_model` | M＋T＋R；T＋R | 前者为实测覆盖结果，后者声明采用的模型、半径和网格，不是实测传感器参数 |
| facts：`segments[].{id,kind}`、`start_s,end_s`；`events[].{id,kind,t}` | T／工程命名；M | 段类来自实际编译阶段；边界与事件时刻来自各机实测窗口和巡逻指标，不补造缺失边界 |
| facts：`facts_version,segments[].boundary_source,events[].boundary_source,channel_check.*,provenance.*` | 工程元数据＋实际通道核对结果 | 字段来源、检测参数、逐字段核对及差异记录；不把常量的匹配政策当作已匹配事实 |
| 内部描述槽位：`n,side,orientation,direction,ratio,gap,laps`；`model` | M／M＋T＋R；T＋R | 从上述已核对 facts 填入；方向等经语言字典转换，模型名是明确的模型声明 |
| 描述：`descriptions[].text,sentences[].text,fact_ids` | 上述 facts 来源＋模板常量 | 每句话有 fact_ids 绑定；不读取 planned_phases，不能用计划行为代替观察行为 |
| 描述：`description_id,episode_id,episode_split,template_partition,facts_version,template_version,sentences[].template_id`；外层 `schema_version,language_version,templates_version,dataset_manifest_sha256,skipped.*`；language manifest 所有字段 | 工程元数据／实际导出计数 | 运行与模板身份、独立模板划分、来源哈希及跳过原因；无新增任务事实 |
| 辅助附件：`task.json,compiled_scene.json,allocation.json` | T＋规划规则常量 | 原任务与编译结果，包含名义路线／时间，禁止作为 observation 特征使用 |
| 辅助附件：`events.json,phase_windows.json,semantic_validation.json,execution_constraints.json,quality.json` | M＋T＋对应验证规则，版本／声明为工程元数据 | 实测事件、窗口、质量、物理限制和语义证据；其 planned terminal/role 等字段仍来自 T，实际时刻与判定来自 M |
| 辅助附件：`source.json,manifest.json` 的来源哈希、Git 基线、config、seed、capabilities、环境、诊断和资格说明；`test_harness.json` | 工程元数据＋实际执行诊断 M | 执行配置与物理故障注入的可追溯证据；不把能力声明当作实际姿态／IMU 或独立观察数据 |

结论：除已修复的 `planned_phases` 外，未发现另一个将注册表可选词汇直接写成本条任务事实的字段。固定 `planned_behaviors` 是计划类别；观察行为的状态、巡逻圈数、覆盖率和相对时序仍由实测证据决定，没有因审计而更改注册验证器或阈值。

## 后处理剖析与唯一优化

一次三机往返扫描的分段剖析，全链 343.052 s，仿真 4.426 s。以下为互不重叠的五个后处理阶段（从慢到快），避免把嵌套调用累计时间重复相加：

| 阶段 | 修改前耗时 / s |
|---|---:|
| `describe_dataset` | 98.659 |
| `write_episode` | 97.323 |
| `audit_dataset` | 47.939 |
| 最后一次 `load_episode` | 47.831 |
| `build_dataset` | 46.856 |

跨上述阶段，完全相同输入的 `analyze_semantics` 调用 7 次，累计 331.110 s，占全链约 96.5%。只引入一次 pipeline 作用域内、单条缓存的语义计算复用：键为 scene、完整实测 traces、events、end_s、status 经 JSON 规范序列化的字节，字典键排序，不按路径／mtime 命中、不使用数值近似比较；返回深副本，作用域退出即释放。文件读取、哈希、契约、数值和质量检查仍执行。M1／SITL 验证计算不使用此缓存。`--no-semantic-reuse` 可复现未优化基线。未调整覆盖几何、轨迹采样密度、阈值或飞行算法，没有其他性能优化。

实际逐字节证明：保留本轮剖析的原始 run，将其 dataset/language 两个目录移入 `byteproof_before/` 原字节存档，然后从同一不可变 run、在相同逻辑路径重新导出（确保目录字符串和模板种子也一致）。**19/19 文件、6,536,669 字节完全一致，未做字段删减或规范化；audit 对象也一致**。范围包含数据集所有附件、标签、manifest、facts 和 descriptions。原 run 未改写；wall-time 报告和完成标记是运行测量，不纳入“确定性数据逐字节相同”的声明。证明文件为外部 `byteproof.json`，原始副本可直接读取。

仅从现存 run 开始的后处理，未优化五次语义计算改为一次计算、四次命中：`build_dataset=50.810 s`、`audit_dataset=0.877 s`、`describe_dataset=3.751 s`、最后 `load_episode=0.734 s`，总计 56.172 s。该口径不含仿真及初次 `write_episode`，不混称全链耗时。

## 验证过程中的问题

`data_tests_01.log` 中 15 个测试有 2 个子用例断言失败：篡改标签在前置 eligibility 检查已被正确拒绝，测试却只接受后置 semantic-claims 文案。保留原测试后，另加直接篡改 planned_phases 且重写其哈希的用例，在复用开／关两种情况下都到达语义重算比较并被拒绝；`data_tests_02.log` 的 16/16 通过。没有放宽生产验证，也没有覆盖失败日志。

## 最终覆盖与实际飞行证据

**M2_COMPLETE：12/12 正例成功，4/4 状态变化负例按预期失败；16/16 执行完整、质量合格、双通道一致、审计无问题；64/64 描述生成并通过事实约束。** 验收及逐条回读见外部 acceptance_01/verification.json、acceptance_readback.json。

| 飞法 | 2 机正例 | 3 机正例 | 4 机正例 | 2 机负例 |
|---|---|---|---|---|
| 往返扫描 | true／通过 | true／通过 | true／通过 | false／通过 |
| 回字扫描 | true／通过 | true／通过 | true／通过 | false／通过 |
| 同环巡逻 | true／通过 | true／通过 | true／通过 | false／通过 |
| 并列快速通过 | true／通过 | true／通过 | true／通过 | false／通过 |

负例的“通过”表示实际语义失败符合预期，不是把失败改标成成功；3/4 机负例不在用户修订后的分母内。四个负例保持原始任务、成功阈值和完整观察输出：

- 两种扫描：仅执行参考高度作平滑上升／下降，实际峰值分别 9.25555 m、9.25544 m；在服务高度带外执行原 EN 路线，再恢复高度完成原终点条件。覆盖率分别 0.116667、0.132045，均小于任务要求 0.9，质量仍合格。
- 巡逻：仅 patrol 阶段速度参考乘 0.4；实测完整 3 圈，最长重访间隔 52.900 s 超过 39.234 s 条件，max_gap=false。没有改圈数或重访阈值。
- 快速通过：仅把水平速度能力配置为 0.3 m/s；实际峰值 0.300420 m/s（在既有数值容差内），区域内低速持续约 73.627／73.645 s，no_dwell=false，仍有真实进入和对侧离开证据。

真实巡逻任务的计划／观察圈数：2 机为 3 圈，3 机与 4 机均为 2 圈；本报告依据输入及实际证据，不沿用早期文档的统一 3 圈概括。对应正例最长重访间隔为 25.367／26.720／26.350 s，均满足各自任务限值。回字扫描真实输入是窄单环，实际覆盖率均为 1.0，但观察模式检测为 unclear，描述如实保持不确定，没有硬写成检测到回字。往返扫描 3/4 机观察模式为 parallel_strips，双机为 unclear。

12 个真实输入均未配置时间错峰。135 ms 非整步错峰、等待期继续积分、先确认后离开并撤销驻留、阶段屏障、最终驻留与超时由实际 plant 的合成边界测试覆盖；不把合成注入说成真实任务本身带有时间错峰。180° 折返等边界同样单独动态测试，不扩充真实验收清单。

## 关键测试与旧路径回归

- 仓库离线 CI 清单 43 模块：**502/502 通过，0 跳过，129.834 s，exit 0**。本机三个 junction 用例使用真实文件系统联接；三个 symlink 场景因 Windows 创建权限不足使用既有测试的解析 mock，不能声称实际 symlink 创建通过。
- 其中连续路线动态测试 11 项；多机执行 14 项；M2 窗口、数据链与本轮修复／复用测试 16 项。覆盖直角、短段、重复点、闭环、防跳圈、折返停车、终点停止、\(h\) 与 \(h/2\) 轨迹及事件比较、错峰、阶段释放、驻留撤销、超时、版本分派、标签篡改拒绝。
- 针对性 M2 数据测试单独 16/16；真实返航／不返航输入预期直接写在测试中。缓存测试覆盖参数变化、返回对象修改、禁用、嵌套、异常退出，以及重新计算哈希后的错误计划阶段仍被拒绝。
- SITL **旧路径的离线回归**：DR130 **260/260**、无差异；v0.5 **4/4** 冻结示例的全部 features、targets 和旧 metadata 保持一致（由一个集成测试逐项检查四个样本）。未启动 SITL，也不宣称做过实飞／固件回归。

## 单条全流程耗时

以下均为 wall time 秒，包含任务读取、仿真、分析、导出、审计、描述、加载和完成文件写入，不含 Python 进程启动。四类修改前／后使用同一双机输入和同一物理配置；“修改前”已修好 planned_phases，只关闭语义复用，因而对比的是唯一性能优化。串行执行，测试回归另行运行；本机仍是非独占环境，各一条测量不能当作生产吞吐承诺。

| 飞法（同一 2 机正例） | 复用前 / s | 复用后 / s | 倍率 |
|---|---:|---:|---:|
| 往返扫描 | 82.290 | 16.741 | 4.92 |
| 回字扫描 | 35.305 | 8.844 | 3.99 |
| 同环巡逻 | 23.141 | 15.351 | 1.51 |
| 并列快速通过 | 2.477 | 1.989 | 1.25 |

额外剖析的同一三机往返扫描：343.052 s → 55.395 s，约 6.19 倍。之前 P0 批次记录的 348.621 s 保留为历史，不作为本次干净对照的前值。

| 飞法 | 机数 | 正例仿真计算 / s | 正例全链 / s | 同机负例全链 / s |
|---|---:|---:|---:|---:|
| 往返扫描 | 2 | 2.673 | 16.741 | 10.648 |
| 往返扫描 | 3 | 4.814 | 55.395 | 不要求 |
| 往返扫描 | 4 | 10.747 | 289.253 | 不要求 |
| 回字扫描 | 2 | 1.845 | 8.844 | 7.654 |
| 回字扫描 | 3 | 2.419 | 32.226 | 不要求 |
| 回字扫描 | 4 | 4.453 | 116.956 | 不要求 |
| 同环巡逻 | 2 | 7.718 | 15.351 | 31.038 |
| 同环巡逻 | 3 | 8.611 | 19.840 | 不要求 |
| 同环巡逻 | 4 | 17.607 | 51.885 | 不要求 |
| 并列快速通过 | 2 | 0.797 | 1.989 | 12.233 |
| 并列快速通过 | 3 | 1.370 | 5.375 | 不要求 |
| 并列快速通过 | 4 | 4.064 | 14.715 | 不要求 |

16 条验收全链墙钟合计 690.142 s。除验收16条外，性能基线4条和剖析1条仍来自同一登记清单，单独存放且不扩大验收分母；byteproof 只重做同一 run 的后处理，不生成新飞行。单元测试内部仿真执行次数未单独计量。

去重后四机往返扫描仍需 289.253 s、四机回字扫描 116.956 s；覆盖几何处理仍明显慢于积分。按用户要求只报告，没有更改算法、网格、阈值或采样来提速。

## 收尾与停止范围

本轮没有新的 P0。代码、测试和报告保存到本地 codex/fast-dynamics 分支；不推送、不开 PR、不打标签。外部 local_commit.json 记录完成提交的 SHA。验收产物中的 Git 字段是执行前 a46f034 基线，source_sha256 记录当时实际未提交的运行实现；提交只保存同一实现，不把报告提交误称为另一次验收。

保留原 P0 记录、M1 历史产物、所有性能基线及首轮失败测试日志。仓库仅保存代码、必要文档和小型摘要；原始轨迹、dataset、语言文件、剖析和日志均在本轮外部目录。M2 到此完成并停止；M3 校准、盲测、扰动模型、训练资格和更大场景扩展均未执行。
