# TaskSpec v3 通用接口

状态：`IMPLEMENTED_AND_TESTED`。WP-E 已实现连续模式 schema 2 编译、运行与双通道轨迹窗口，历史验收见 [WP-E 报告](v04_wp_e_milestone.md)。2026-10-10 当前扩展已包含三意图和 v0.6 元数据；实际运行证据见 [pilot 报告及暂停 B 复核](v0.6_pilot_report.md) 与 [生产停止报告](v0.6_production_stop_01.md)。生产在 296/900 个任务后规则停止，未形成正式导出集。

本文保留 v0.4 基础接口说明，侦察专用参数段落只描述对应意图/历史阶段；当前完整字段和拒绝规则以 `mission_v3.normalize_v3()`、各意图参数规范化函数及 `missions/v3/*_v06.json` 为准。当前 Git 核对 HEAD 为 `037ed7e`，不能把历史 WP-E 验收当作当前提交的重新测试。

## 数据结构与兼容边界

`swarm_sim.mission_v3.normalize_v3(spec)` 规范化深拷贝；`tasks.compile_task(spec)` 根据 schema 分派。v1/v2 的规范化和编译算法不经过注册表。`from_v2(spec, control_mode=...)` 是显式的示例编写工具，读取历史任务不会自动升级。

- `scenario`：`scene_id`、`origin`、`world`、`regions`、空 `restricted_regions`、`vehicles` 和 `platform`。平台能力对象沿用 v2 字段，移入 `scenario.platform`；只有平台 `id` 参与物理场景 family。
- `mission`：`intent`、`target_region_id`、布尔 `return_required`、`intent_params`。侦察参数为 `objective`、`coverage_required` 和 `observation_model`。
- `planner`：`name` 和 `params`。侦察参数沿用 v2，再增加默认 `0.0` 的 `lane_end_overshoot_m`。本里程碑拒绝非零值，等待后续有覆盖不足实测证据时按 WP-E 实现。
- `execution`：显式 `control_mode`；`waypoint_barrier_v1` 仅允许 `waypoint_hold_s`；`semantic_phase_route_v1` 仅允许 `terminal_hold_s` 和 `async_timing_tolerance`，其余公共字段沿用 v2。v3 可选 `phase_timeout_override_s` 只用于显式缩短阶段预算，范围 0.001–3600 s，省略时保持默认公式；该字段参与场景绑定。
- v0.6 执行扩展：`protocol_version`、`final_hold_s`、`firmware_version_timeout_s` 中任一出现时，三者必须齐备且协议为 `v0.6`。当前模板为最终悬停 2 秒、固件等待 10 秒；原 2 秒固件等待优化已撤回。未声明该组字段的旧任务不会自动升级。
- `flight_pattern` / `component_versions`：声明时需匹配意图允许的生产飞法、规划器版本及注册组件版本；当前 facts 为 `observer_facts_v06b`。这些是任务/来源元数据，不能作为公开轨迹特征。
- `family_id`、`family_scheme` 可以省略由规范化计算；显式填写时必须与 `scene_content_v1` 计算结果一致。它们由物理内容决定，与 mission/planner/execution、种子和名称无关。

未知字段、数值 bool、NaN/Inf、缺字段、未注册意图/规划器、意图与规划器不匹配、控制模式专属字段错配、手填 family 不符均在规范化时拒绝。矩形区域可有多个，但每个任务只指定一个目标区域；禁区仍只接受空列表。

## 注册与回调

`swarm_sim.registry` 提供不可变 `IntentSpec`、`PlannerSpec`、`PlanResult`。当前生产意图为 `reconnaissance`、`patrol`、`rapid_passage`，飞法为侦察 `equal_strip_lawnmower`／`equal_strip_rectangular_spiral`、巡逻 `staggered_same_loop`、快速通过 `line_abreast`。意图与对应规划器显式初始化，不从外部文件、环境变量或插件目录自动发现。`echelon` 只允许显式离线候选作用域，不生产登记。

| 接口 | 合同 |
|---|---|
| `get_intent(name)` / `get_planner(name)` | 未注册名称抛出明确 `ValueError` |
| `registered_intents()` / `registered_planners()` | 返回排序后的名称元组 |
| `temporary_registration(intent, planners=())` | 测试上下文；禁止覆盖已有项，异常退出也恢复此前注册表 |
| `IntentSpec.normalize_params(params)` | 返回校验后的意图参数对象 |
| `PlannerSpec.normalize_params(params, spec)` | 返回校验后的规划参数对象；可检查目标区域等跨字段约束 |
| `PlannerSpec.plan_routes(spec)` | 返回 `PlanResult(routes, assignments, diagnostics)` |
| `IntentSpec.evaluate_channel(scene, traces, windows, clocks)` | 返回 `{"conditions": {名称: true/false/null}, "metrics": {...}}`；禁止覆盖通用返航/任务成功字段 |
| `IntentSpec.behavior_labels(scene, truth_result)` | 返回 `planned_behaviors`、`observed_behaviors`；行为规则版本为具体验证器版本 |
| `IntentSpec.topology_signature(spec, planning)` | 返回意图专属拓扑签名；不参与物理 family |

`PlanResult.routes[agent][semantic_phase]` 是该阶段的二维 ENU 航点列表，允许空列表；每架飞机和每个注册语义阶段必须恰好出现一次。`assignments[agent]` 记录分区 ID 或 `None`，`diagnostics` 保存名义覆盖等规划专属诊断。每个点只接受有限的 `east_m`、`north_m`。通用编译层再执行世界边界、能力和间距检查。

侦察旧模式直接复用冻结的 `compile_execution_phases`，因此保留逐航点屏障、首个 observe 零长度段以及原来的语义映射。测试夹具可声明自己的语义阶段及服务阶段，通过同样的旧模式屏障机制编译；夹具只存在于测试上下文，不写入生产示例。

## 双通道验证

`evaluate_mission` 仅给 schema 3 增加分派，其 v2 函数体保留。v3 公共层负责事件窗口、返航检查、三值合成、SIM/FCU 独立调用和 `semantic_consistency`；侦察适配器复用原覆盖算法。数据时间线审计单独报告，缺项门禁交给质量层，不改变 v2 已有的“达到覆盖目标可形成正向证据”规则。

`labels.label_provenance.validator_versions` 记录具体意图规则版本；统一 `semantic_validation_version` 来自 v3 协议。一个通道的已知条件与另一通道相反时，即使总体任务都失败，也判 `disagree`。

连续模式的窗口由 `route_windows` 分别计算 SIM 和 FCU 通道的 `arrival_s`；从终点到点事件向后寻找首次距离/速度同时合格的采样，未找到时使用后续最近距离采样。SIM 水平速度由有效相邻位置按映射后的源时间作后向差分，不跨越缺口。服务止于 `arrival_s`，后续屏障等待不计服务。旧模式的窗口逻辑保留。

## 示例和验证

`missions/v3/` 新增三种几何各两种控制模式：`recon_shared_3uav`、`recon_smoke_2uav_north`、`recon_smoke_6uav`，文件后缀 `_barrier.json` 和 `_route.json`。

```powershell
conda run -n llm --no-capture-output python main.py plan missions/v3/recon_shared_3uav_barrier.json --output tmp_v04/recon_shared_3uav_barrier.json
conda run -n llm --no-capture-output python -m unittest discover -s tests -p test_task_v3.py -v
```

`_route.json` 可规范化、编译及校验。每个语义阶段对应一个执行阶段，空航线保留为不提供服务的 no-op；按原地确认完成后才记录 ready。航线任务项、时间间距、绑定及窗口详情见 [连续航线接口](continuous_route_schema_v1.md)。v1/v2 不自动迁移为新模式。
