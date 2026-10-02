# v0.4 WP-E 里程碑：连续航线执行与双通道分析

日期：2026-10-01。文档状态：WP-E 离线验收 PASS。依据：原阶段 0–1 实施计划第 7、9 节及 `docs/v04_stage01_plan_addendum.md`。本报告记录进入 WP-V 前的离线验收；随后真实运行的失败和暂停状态见 [V1 里程碑报告](v04_v1_milestone.md)。

**WP-E 的 E1–E3 已实现，E01–E10 和 R01–R06 离线验收通过。最终全回归实测为 344/344 PASS，包含原有 150/150 PASS；此前 338 项中间快照继续保留。交叉审查补充了名义到点事件上界、放行前超时的空观测区间，以及终点事件早于 AUTO 确认的时序处理。本报告所用新增证据均为单元测试、mock、合成轨迹或历史数据副本离线分析，WP-E 离线阶段新增 SITL 为 0 次。这不表示 V01–V05 或 AC-1 至 AC-6 已实跑通过，也不表示阶段 0–1 全部完成。**

**随后 V01 的真实启动暴露 E2 参数分类缺口：比较器把 `STAT_RESET` 统计状态当成固定配置，从而在起飞前拒绝运行。因此结论是“离线 E/R 验收 PASS，实际可运行性未通过”，而非只剩等待实跑。当前暂停，不修改分类规则、不自动重试。**

软件版本为 `0.4.0-dev`，表示开发中的接口版本；版本号不是实跑验收结论。用户已授权 E1–E3 验收后进入 V01–V05，最多 6 次 SITL，V05 之后暂停；V06 不在当前授权内。

## 1. 证据与适用范围

| 证据 | 实际结果 | 用途 |
| --- | --- | --- |
| `tmp_v04/wp_e/pre_tests.json`、`baseline.json` | 编辑前 282 项测试通过；保存历史文件保护哈希 | 修改前基线 |
| `tmp_v04/wp_e/unit_test_results.json` | 2026-10-01T18:20:33Z；338/338 PASS；19.984 s；原有 150/150 PASS | 中间全量离线验收快照；逐项 test ID、模块计数和源码 SHA256 均保留，最终边界修正须另有最终测试记录 |
| `tmp_v04/wp_e/unit_test_results_final.json` | 2026-10-01T18:29:02Z；344/344 PASS；21.222 s；原有 150/150 PASS | 最终三类边界修正后的全量测试；71/71 个记录的源码/测试文件哈希与当前文件一致 |
| `tmp_v04/wp_e/offline_acceptance.json` | 机器记录的 E01–E10、R01–R06 全部 PASS | 进入 V1 前生成的离线门禁，不含 V1 结果 |
| `tmp_v04/wp_e/pre_sitl_preservation.json` | 7994/7994 个受保护文件未改变，`changed=[]` | 在进入真实运行前核对历史证据保护快照 |
| `tmp_v04/wp_e/legacy_regression/legacy_regression.json` | R02：104；R03：15；R04：2 个数据集共 15；R05：15，均 PASS | 旧任务、绑定、加载和旧字段稳定性 |
| `tmp_v04/wp_e/v2_mixed_analysis/compatibility.json` | 两个真实历史 episode 的分析前后版本混合导出及加载 PASS | 用户提出的 v2 混合兼容性问题 |
| `tests/test_route_analysis_integration.py` | 手工源证据经过 schema 2 分析、导出和加载，PASS | v3 连续模式离线完整数据链；不算真实 SITL |
| `tmp_v04/wp_e/route_profile_preflight/generation_manifest.json` | route profile 纯生成 10/10 接受、10 个任务、0 个候选拒绝 | profile 切换后的编译预检；没有运行这些任务，不计作 V06 |
| `verification/v04_v1_20261001/records.json` | 已准备 V01–V05 计划清单；本报告不据准备清单填实测结果 | 下一里程碑记录入口 |

测试环境为项目 `.conda-env` 指定的 `llm`，Python 3.12.3，PowerShell 7.6.5。测试工具不安装依赖，不改变默认数值质量策略。旧 WP-S UNKNOWN 报告、后续独立复核、用户 GO 确认及 WP-G 报告各自保留，不能用本报告替换或追改它们。

相对于本轮编辑前 282 项基线，新增的 62 项测试分布为：`test_route_planning` 15、`test_runner_v3` 8、`test_run_provenance` 9、`test_route_windows` 17、`test_analysis_v3` 9、`test_route_timing` 3、`test_route_analysis_integration` 1。总数来自最终实际测试结果文件，不将 mock 次数或离线报告行数重复计为测试。

最终测试记录的文件 SHA256 为 `ba3837cd8904049d4b1254d4c0d9ca1ed9021aa9db7dfa3d7685aa9c7f445969`；保护核对记录的文件 SHA256 为 `46d3e8fef2799e24a57e238a40fa0563c5ad7e4a105aca28e6319230097198b4`。两者保留原文件，本文不替代机器门禁记录。

## 2. E1：从逐航点阶段改为语义阶段航线

`mission_v3.compile_mission_v3` 按控制模式分派。旧 `waypoint_barrier_v1` 保留 schema 1 编译和语义窗口；`semantic_phase_route_v1` 调用 `route_planning.compile_continuous_mission`，生成 schema 2。注册意图的每个语义阶段对应一个执行阶段，侦察默认是 approach、observe、return；`return_required=false` 时不生成 return。

`route_planning.clean_route` 从本机该阶段起点开始，顺序删除距离小于 0.05 m 的重复点，保留原规划索引，避免 approach 终点在 observe 开头再执行一次。每机每阶段最多 100 个航点，100 合法、101 拒绝。空航线保留该语义阶段，但角色为 `hold_no_op`、`service_enabled=false`，显式保存起点和终点；它不通过填充重复飞行动作来凑齐航点数。

`scenario.route_mission_for` 生成 HOME、DO_CHANGE_SPEED 和航点任务项。中间航点的 hold 为 0，最后一个航点使用 `terminal_hold_s`。schema 2 场景、路线、语义映射、规划元信息和名义时序受 TaskSpec 绑定校验；修改它们而不重编译会被拒绝。

`route_planning.time_aware_phase_clearance` 使用不超过 0.5 m 的弧长采样，比较名义时间差在 \(\tau\) 内的两机位置；\(\tau=\max(\tau_{\min}, fT_{\mathrm{phase}})\)。阶段时长包括末端 hold 和几何确认驻留。先到达终点的飞机和 no-op 飞机继续占据终点直到阶段结束，不能在名义到达后从间距检查中消失。结果保存每机路径长度、逐航点名义到达时间、每阶段 \(\tau\)、最小名义间距与最接近点对。

这仍是匀速规划模型和离散几何预检；真实飞控转弯、加减速、到点事件延迟与名义时序偏差必须由 WP-V 检验。`lane_end_overshoot_m` 保持 0；非零外延当前明确拒绝，本轮没有以改变几何争取覆盖率。

## 3. E2：阶段级执行、事件及逐运行预检

`runner.run_scene` 按绑定 TaskSpec 版本分派。v1/v2 的运行路径保持原控制行为；v3 进入 `runner_v3.run_scene_v3`，在其中根据 schema 1/2 选择旧逐点任务形状或新连续航线形状。连续模式每个语义阶段执行一次上传、统一放行、飞行和几何确认，不在中间航点建立全机屏障。阶段之间继续保留全机确认与等待。

| 运行证据 | 定义或行为 |
| --- | --- |
| `phase_release_scheduled.release_t` | 计划放行时间；窗口使用该值，不能用写日志的时间替代 |
| `phase_start_sent` | 调用模式切换前的发送侧事件 |
| `phase_auto_confirmed` | 收到 AUTO 心跳确认后的时刻；作为非空航线本机窗口起点 |
| `waypoint_reached` | 接收线程记录全部 seq；`t=recv_monotonic_s-run_epoch`，保留绝对接收时刻、phase、seq、route_index、planner_index、terminal |
| `phase_no_op_started` | no-op 在放行时刻开始，不上传空任务、不伪造 AUTO |
| `phase_no_op_ready` | 原地 `confirm_target` 几何和驻留要求真正完成后记录；确认失败不会生成 ready |
| `metadata.phase_timing` | 每阶段上传、执行、放行等待、确认、总时长、预算及其比例；异常阶段也保存已完成的测量 |

所有参数请求继续通过 Vehicle 的单一接收线程和消息收件箱处理。每次 v3 运行在起飞前重新读取完整参数表，保存每机数量、缺项、状态、全参数表及 WPNAV_*。`firmware_parameters.json` 由本次 `metadata.run_provenance.parameter_evidence.sha256` 绑定；分析 manifest 也绑定运行附件。

每次 PARAM_REQUEST_LIST、重发及 PARAM_REQUEST_READ 补读均记录 TX 请求类别、用途、目标 sysid/component、缺项索引、关联 ID、发送前后单调时间及成功/异常状态。首次响应时间不冒充发送时间；超时和发送失败仍保存已经收到的部分表和请求记录。任一飞机预检失败，所有飞机都不得进入起飞步骤。

固件及参数模板通过 `run_provenance.verified_wp_s_baseline` 追溯到用户 WP-S GO 确认和两次原始试验的哈希链。每次启动前校验二进制 SHA256、版本字符串和参数模板 SHA256，启动后再次核对文件指纹。**固件或参数模板改变时，必须重新执行 WP-S 并取得新的 GO，不能复用旧确认直接生产运行。** 参数读回变化也逐项记录；SYSID、随 home 初始化的磁偏角及精降参考位置等已声明实例差异给出解释，未解释差异拒绝继续。

真实 V01 发现这份初始分类过严：已接受的两次 WP-S 中，`STAT_RESET` 已分别为 339262368 和 339262688；本次 V01 为 339272992，uav_02/03 的完整参数表都记录该值。二进制和参数模板哈希仍与已确认基线相同，不能把这次拒绝解释为固件或模板发生了变化。当前代码没有擅自新增统计状态豁免；这项生产参数分类缺口、修正规则及重新验证预算留在 V1 报告中审阅。

固件版本请求支持真实 AUTOPILOT_VERSION 响应；未回应时只允许明确记录唯一二进制版本字符串、偏移及哈希作为来源。该回退不能称为运行时读回成功；收到运行时版本却与二进制身份冲突时拒绝。

阶段超时由名义阶段时长的 3 倍加 30 s 与场景剩余预算取小值。受绑定的 `phase_timeout_override_s` 只能缩短这一预算，不能延长。失败保存 metadata、events、参数证据和分析结果，并关闭本次拥有的客户端、记录器与 SITL 子进程；本轮用 mock 验证，真实清理退出码留 WP-V 测量。

## 4. E3：双通道窗口、观测处理和验证器

### 4.1 arrival 与服务范围

`route_windows.build_route_windows` 分别接受 FCU 和 SIM 轨迹，分别计算窗口。`phase_windows.json` schema 2 的 `channels.observation` 与 `channels.truth` 保存完整窗口；顶层 `windows` 是明确标记为 observation 的兼容视图，不表示两个通道共享到达结果。

非空航线的 `start_s` 来自本机 AUTO 确认；`end_s` 来自下一阶段统一放行时间，最后一阶段使用 mission end。缺失正常结束证据时只保留标明不完整的运行结束回退，不能认证为完整窗口。

从该阶段终点 `waypoint_reached` 事件**向后**搜索有效采样，取第一个同时满足终点距离容差和 \(\lVert v_{xy}\rVert\le0.3\,\mathrm{m/s}\) 的时刻作为 `arrival_s`，来源为 `trajectory_stop`。直到阶段结束仍不满足时，取这个后续范围内的最近距离采样，来源为 `trajectory_min_distance`，并明确 `arrival_verified=false`。没有事件锚点则不能构造服务窗口；有事件而无后续位置仅保存 `event_fallback`，仍未验证。事件较晚时不反向搜索更早停住的位置；事件较早时也不直接把事件当物理到达。

终点事件只要落在本阶段 release 与阶段结束之间，就可以成为合法锚点，即使 AUTO 确认心跳更晚才被控制线程接收；不能因为确认延迟丢掉这条原始事件。仍严格执行从事件向后的首次联合条件，不把到达时间推迟到 start 来掩盖问题。若据此得到 `arrival_s < start_s`，完整窗口保存真实到达值，同时标记 `chronology_valid=false`、窗口不完整；服务视图的起止均置为 null，不能生成倒置服务区间。失效时间轴不会因扩大事件锚点范围而恢复。

窗口保存 `arrival_source`、原因、完整性、终点和中间航点子事件。no-op 用显式 started/ready 事件建立就地窗口，`arrival_s=start_s`，始终关闭服务；返航成功仍要求独立的几何与驻留证据。

`service_window_view` 将注册为服务阶段的范围限制为 \([start_s,arrival_s]\)。屏障等待 \([arrival_s,end_s]\) 不参与观察覆盖；return 的几何驻留检查使用完整返航窗口，因此不会因为到达截断而丢失确认驻留。barrier 模式继续使用旧 `execution_windows` 定义，但通过注册表调用意图验证器。

### 4.2 SIM 速度的来源和限制

SIM 日志没有这里所需的直接水平速度字段。FCU 分支使用报告速度，版本为 `fcu_horizontal_velocity_v1`；SIM 分支对相邻有效位置做后向差分，正式分析有可用时钟映射时使用映射回源时间的时间差，版本为 `sim_horizontal_backward_difference_source_v1`。

SIM 的派生量是采样区间平均速度，不能解释为瞬时速度传感器读数。首个有效点没有可用差分速度，invalid 和超过 `max_gap_s` 的缺口都断开差分，不从 FCU 借用速度。独立接口无源时钟时的 host 时间差分另标 `sim_horizontal_backward_difference_host_v1`；正式 v3 分析没有可用时钟时不靠该接口回退恢复一条已失效轨迹。每个窗口记录 `speed_processing_version`、`speed_time_basis` 和限制说明。

### 4.3 四个观测版本与全流规则

| 字段 | 本轮固定值 |
| --- | --- |
| `observation_processing_version` | `v3_observation_v1` |
| `duplicate_policy_version` | `exact_duplicate_drop_v1` |
| `timeline_policy_version` | `full_stream_strict_v1` |
| `clock_model_version` | `passive_system_time_piecewise_v1` |

`analysis_v3.analyze_run_v3` 先对全流做显式处理，再拟合时钟并重采样。相同源时刻且完整消息内容相同的重复包保留首包；raw 不变，审计记录原始行号、处理动作和数量。同时间内容冲突、源时间回退、非法时间或接收逆序仍使相关整条流失效，不能裁掉窗口外异常来恢复资格。SYSTEM_TIME 异常使相应时钟不可用。

四版本写入分析 manifest、quality、观测处理审计及相关语义附件；跨产物不一致，即使重新计算附件哈希也必须拒绝。`invalid_intervals` 只说明无效观测和缺口，不实现窗口级资格。v1/v2 继续使用旧观测与时钟路径、旧数值质量策略。

### 4.4 用户问题：具体意图验证器版本在哪里

**具体意图的验证器版本在 `labels.json` 的 `label_provenance.validator_versions`。** 当前侦察值为 `{"reconnaissance": "shared_coverage_v2"}`，由注册的 `IntentSpec.validator_version` 写入。它与通用 v3 语义协议版本是不同字段；不能用顶层 `semantic_validation_version` 代替具体规则的身份。

`mission_evaluation_v3.evaluate_mission_v3` 分别调用注册意图的 `evaluate_channel`，统一组合返航条件，输出双通道成功值、逐条件结果和 `semantic_consistency`。任务成功与 `episode_quality_eligible`、`benchmark_eligible` 分开计算；执行指标是独立诊断附件，不加入六维模型输入。失败运行即使在起飞前结束、没有 raw 或正常事件，也可以分析、导出为 UNKNOWN 和不合格质量，不凭空生成零停靠或成功标签。

交叉审查补充两项分析边界：`route_timing.nominal_arrival_evidence` 的航点配对同时限制在该阶段 release、下一阶段 release、mission end 和真实 run end 内，不能用阶段结束后的迟到事件填满名义时序证据；缺失配对保持 UNKNOWN。运行在已安排但尚未到达的 release 时刻之前超时时，分析记录 `observation_window.status=not_started`、原因 `scheduled_release_after_run_end`，输出空 grid 和 0 duration，保留原 metadata；不能导出负时长。存在互相矛盾的正常 mission end 则明确拒绝。

## 5. 用户问题：v2 修改前后分析能否混合

已用真实历史 SITL 产物副本验证，而不只检查函数签名：

| 副本 | run_id | analysis_version | execution_metrics |
| --- | --- | --- | --- |
| `pre_metrics_v03` | `20260930T152031Z_08eff45d` | `0.3.0` | 无 |
| `post_metrics_v04` | `20260930T152358Z_56f3a95a` | `0.4.0-dev` | 有 |

这两个 episode 成功写入 `tmp_v04/wp_e/v2_mixed_analysis/mixed_dataset` 并由加载器读取。每个 episode 的 `x`、`mask`、`t_s`、`agent_ids`、`targets` 五组数据与导出前完全相同。该步骤是“历史分析副本混合导出”，没有启动 SITL，也没有对原运行重新分析。

二者继续使用 `mission_v2 / shared_mission_v1 / label schema 2 / shared_coverage_v2 / shared_quality_v1 / execution_limits_v2` 协议。可选 `execution_metrics.json` 的有无不会改变 v2 协议或模型输入；有附件时仍按其版本与哈希核验。这不意味着可以随意混入不同语义协议、不同质量策略或不一致版本的产物，相关拒绝测试继续通过。

## 6. E01–E10 逐项验收

下表 PASS 的证据类型是纯逻辑、合成输入或 mock，不是对真实飞行的提前承诺。完整 test ID 和实际运行状态见 `unit_test_results_final.json`。

| ID | 状态 | 源码 | 实际测试与结论 | 实跑边界 |
| --- | --- | --- | --- | --- |
| E01 | PASS | `route_planning.clean_route`、`compile_route_phases` | `test_route_planning` 的 5 个 E01 用例：一语义阶段一阶段、去首点/内部重复、索引保留、no-op 关闭服务、可省略 return | 跟踪误差留 WP-V |
| E02 | PASS | `scenario.route_mission_for` | `test_E02_mission_item_order_params_and_final_hold`：顺序、数量、各项参数、中间 hold=0、末端 hold 正确 | 飞控实际语义已有 WP-S 前置证据；生产链仍需 V02 |
| E03 | PASS | `route_planning.time_aware_phase_clearance` | 同时交叉拒绝、相隔超过 \(\tau\) 接受、终点停留/no-op 占位、最大 0.5 m 采样、共享三机场景通过 | 名义时序偏差和真值间距留 AC-4 |
| E04 | PASS | `route_planning.clean_route` | `test_E04_exact_100_waypoints_allowed_101_rejected` | 只验编译边界 |
| E05 | PASS | `runner_v3.execute_phases`、运行分派 | schema 1/2 生成不同任务形状；no-op 不上传、不 AUTO；ready 需要确认成功 | 阶段级运行用 mock |
| E06 | PASS | Vehicle 单一接收线程中的到点记录 | `test_E06_R06_single_receive_owner_records_all_seq_without_extra_mode_commands`：全部 seq 和原始接收时刻保留，不增加模式命令 | 实测事件完整性留 WP-V |
| E07 | PASS | `route_windows`、`mission_evaluation_v3` | 17 个 E07 用例覆盖双通道独立、事件早晚、距离/速度联合条件、fallback、缺事件、no-op、服务排除等待、源时间差分、缺口、返航驻留及 AUTO 确认延迟/倒置服务保护 | 采样分辨率限制仍存在 |
| E08 | PASS | `runner_v3.phase_time_budget`、`run_scene_v3` | 预算不能放宽；mock 阶段超时保留失败证据并清理拥有的进程；单机参数失败阻止全机起飞 | 真实受控失败留 V05 |
| E09 | PASS | schema 2 验证及 `tasks.validate_task_binding` | `test_E09_binding_rejects_route_metadata_and_timing_tampering` | 路线、映射、时序篡改均拒绝 |
| E10 | PASS | `execution_metrics.compute_execution_metrics` | 9 项执行指标测试，包括手算停靠数、静止/同步比例、阈值/时长/缺口、互斥分类和共同交集反例 | 对本批新运行的独立复算留 AC-6 |

`test_route_analysis_integration` 还验证一条手工编写源观测的成功 schema 2 链：分析、双通道标签、版本化附件、导出和加载。源轨迹不是由被测规划器产出后拿来当“正确答案”。

## 7. R01–R06 逐项回归

| ID | 状态 | 实际分母与结果 | 证据 |
| --- | --- | --- | --- |
| R01 | PASS | 原有 150/150；总测试 344/344 | `unit_test_results_final.json.R01` 及逐 test 记录 |
| R02 | PASS | 4 个旧示例 + 100 个已生成任务，共 104/104 与基线匹配；100/100 与已存场景匹配 | `legacy_regression.json.R02` |
| R03 | PASS | 15/15 个旧运行绑定校验通过 | `legacy_regression.json.R03` |
| R04 | PASS | 2 个旧数据集，共 15/15 episode 的新加载结果与基线相同 | `legacy_regression.json.R04` |
| R05 | PASS | 15/15 个旧运行仅在新副本上重新分析；原 `labels.json` 和 `semantic_validation.json` 字段无差异，新增诊断为追加 | `legacy_regression.json.R05`，含失败运行 `20260930T153556Z_bf2d3529` |
| R06 | PASS | 到点诊断不增加控制命令；旧分析忽略新增到点事件和未知事件，原输出一致 | `test_runner_v3` 两个 R06 用例 |

历史副本重分析位于 `tmp_v04/wp_e/legacy_regression/legacy_copies`。原 run、dataset、audit 和旧报告不作为输出目的地；`baseline.json` 保留受保护文件的修改前哈希，`pre_sitl_preservation.json` 实测 7994 个文件全部未改变。R05 的 PASS 不能改写原数据质量等级或将旧失败变成成功。

## 8. 已实现的能力与下一步门禁

当前可执行接口已包括：v3 规范化与注册表、连续路线编译及绑定、时间感知名义间距检查、单机到点子事件、阶段级执行、逐次固件/参数证据、双通道 arrival 和服务窗口、v3 观测处理、两级质量资格、分析导出与加载。主要新增实现位置如下：

| 文件 | 入口 |
| --- | --- |
| `swarm_sim/route_planning.py:130` | `compile_route_phases`；`:218` 为 `compile_continuous_mission` |
| `swarm_sim/runner_v3.py:43` | `execute_phases`；`:142` 为 `run_scene_v3` |
| `swarm_sim/run_provenance.py:44` | WP-S 哈希链；`:116` 为逐次参数/版本读取 |
| `swarm_sim/route_windows.py:88` | `build_route_windows`；`:200` 为服务视图；`:214` 为双通道窗口产物 |
| `swarm_sim/mission_evaluation_v3.py:27` | 意图分派与双通道组合；具体验证器身份写入 label provenance |
| `swarm_sim/analysis_v3.py:43` | v3 分析主链与四版本传播 |
| `swarm_sim/route_timing.py:5` | 逐航点原始到点接收时间相对阶段 release，与名义时间及该阶段 \(\tau\) 配对 |

进入 V1 后仍须逐项记录，不得用本报告的离线 PASS 代替实测：

1. V01 旧 barrier 3 机一次，V02 相同场景 route 两次，V03 2 机北向一次，V04 6 机一次，V05 受控失败一次。每次独立目录，最多六次；不得自动追加调参试验。
2. AC-1 按 V02–V04 全部中间点合并计算，单次结果同时报告；缺失不能当作未停靠。AC-2 检查每机停靠数；AC-3 检查双覆盖和一致性；AC-4 检查真值间距及逐阶段名义偏差；AC-5 检查零长度航段；AC-6 做独立停靠复算。
3. `scripts/verify_v04_v1.py` 已准备只读 JSON/Markdown 核验接口；输入 run 清单，输出仅允许新 `tmp_v04` 目录。它复制 A4 最小停靠检测，未导入或执行原审查脚本、未调用生产执行指标作参考；空清单返回 NOT_RUN / UNKNOWN。V01/V02 对照与 V03/V04 按完整扫描线长度分组的 2 m 邻域最低过点速度均保留有效分母、未知数和通道版本。V01 barrier 沿用旧窗口、没有第 7.5 节的轨迹 arrival 字段，因此其 `arrival_lag_s` 应为 UNKNOWN；对照表必须保留这个缺失，不从阶段结束事件伪造完整到达滞后。
4. 任一计划验收未满足就报告实测并停止，不修改停靠阈值、质量策略、飞控参数或几何来取得通过。V05 完成后暂停，等待确认后才可 V06；此处不宣称试生产或阶段 0–1 最终验收完成。

`generation_profiles/recon_pilot_v04.json` 已按补充计划从 barrier 模板切换为 `missions/v3/recon_shared_3uav_route.json`。在新的 `tmp_v04/wp_e/route_profile_preflight` 目录仅生成并预检：10 个 base、10 个 candidate、10 个任务全部接受，拒绝数为 0。manifest 保存的规范化 profile SHA256 为 `070c722a43f2ae751199ad1ee78354e6f636a0580ed42bdf964419247b9ca80c`；源 profile 文件字节 SHA256 为 `8b61b8fce6dc214de4909f7b41d4a4d4040cef0bed0ae83f39f9ef179b6a1c4e`，二者口径不同。此次没有执行这 10 个任务，也没有完成或启动 V06。

WP-E 离线验收之后，V01 已实际尝试一次，在起飞前因 `STAT_RESET` 参数读回差异被预检拒绝，耗时 12.343 s；三架本次拥有的 SITL 都保存了退出码 1，未起飞。当前真实验证已暂停，其结果不能被本报告的 PASS 覆盖。预算已用 1/6；若保留失败记录后仍完成原来的六次矩阵，需要新增一次授权、总预算为 7，不能自行重试。运行证据和后续未运行项统一见 [V1 里程碑报告](v04_v1_milestone.md)。

复核离线接口可在项目根目录使用 `conda run -n llm --no-capture-output python -m unittest discover -s tests -v`。核验已有 V 清单可使用 `conda run -n llm --no-capture-output python scripts/verify_v04_v1.py verification/v04_v1_20261001/records.json --output tmp_v04/wp_v/<新的报告目录>`；该命令不启动 SITL，已有目录会被拒绝。
