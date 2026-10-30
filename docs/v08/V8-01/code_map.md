# V8-01 §4 冻结生成器代码地图（只读）

对象：`Simulation-fe-prod-r3`（`fe/production-r3` @ `641a9b3`）。下文路径均相对 `Simulation-fe-prod-r3/Multi-UAV SimpleGC/`，写作 `文件:行`。

---

## 4.1 生产流水线调用链

### 入口

`scripts/run_v07_fe_production.py:743 main()` → `--worker-stage B|C --run-dir <批次目录> --skeleton <sid>`（`:754-761`）→ `worker_b(run_dir, sid)`（`:315`）或 `worker_c(run_dir, sid)`（`:380`）。调度器 `run_scheduler`（`:562`）用 `default_worker_command`（`:439-442`）为每个骨架起一个子进程（`python -B`），`cwd=PROJECT`，日志写 `<run_dir>/logs/{B|C}__<sid>.txt`（`:610-616`）；规划超时 3600 s、仿真超时 5400 s（`:53-54`），超时由调度器 kill 并写 TIMEOUT（`:630-645`）。仿真阶段只在一个抽签的 5 个意图全部 B 为 PASS 后入队（`_enqueue_c_tasks`，`:497-515`）。

### 规划阶段（B）

| 环节 | 函数（文件:行） | 说明 |
|---|---|---|
| 场景加载 | `run_v07_fe_production.py:71 _load_family(record)` | 读 `record["directory"]` 下 `public_scene.json`、`family_initial.json` 并核对 SHA256（目录来自 `registration.json` 的 `family_rows`，指向 `SwarmData/v07_scene/attempt_s15_…/family_s15_…`） |
| 规划入口 | `worker_b` → `task_v07/expansion/candidate_search.py:59 episode_candidate_pool(scene, descriptor, backend="unified")` → `task_v07/expansion/group_candidate_pool.py:92 independent_episode_pool` | 按 `group_id` 顺序对每个任务组独立建提案池（`:102-105`），再在笛卡尔积上随机抽组合（`:107-131`） |
| 组提案池 | `group_candidate_pool.py:32 build_group_pool` → `task_v07/unified/adapter.py:15 build_unified_pool` | 每组 200 个提案；每个提案：`draw_shape` → `route_group` → `plan_checks` → `assemble_skeleton` / `exclusion_policy` / `precheck`（`adapter.py:26-50`）。记录 `stage` 依次为 shape → connection → whole_route → group_feasible |
| TaskSpec / 公开分股 | `task_v07/unified/spec.py:174 build_spec` → `task_v07/expansion/public_approach_shape.py:8 public_approach_shape` | 公开分股（股数、各股相对方位、成员划分）；与意图无关 |
| 可行空间 | `task_v07/unified/free_space.py:162 free_space`、`:185 work_region`；`FreeSpace.planner`（`:115`，可视图路径规划，`task_v07/visibility.py`） | |
| 作业形态生成 | `task_v07/unified/shapes.py:1 draw_shape`（过境，`:21` 循环 20 次）；非过境走 `task_v07/unified/operation_shapes.py:156 draw_operation`（`:165` 循环 20 次），按执行方式分派：`search_shape`（`:76`）、`observation_shape`（`:131`）、`patrol_shape.py:95 patrol_shape`、`terminal_shapes.py:174 feint_shape`、`:209 intrusion_shape`；形态阶段末尾 `construction.py:69 precheck_operation`（进场线 + 撤离点预览） | |
| 进场、撤离、作业段连接 | 过境：`task_v07/unified/route.py:154 route_group`（`:164` 循环 10 次）；非过境：`task_v07/unified/operation_routes.py:26 route_operation`（`:35` 循环 10 次）。进场 `route.py:84 _approaches`；撤离：过境内联 `route.py:172-182`，非过境 `construction.py:37 retreat_endpoint`；作业段内连接 `operation_routes.py:16 connect` + `operation_shapes.py:13 round_corners` | 详见 §4.2 |
| 多股/多组协调 | 组内：`public_approach_shape`（股）+ `task_v07/unified/assign.py:5 assign`（股内按横向位置单调分配）；组间：`group_candidate_pool.py:110-131`（同目标方位 `candidate_constraints.py:5 bearing_allowed`、`episode_pipeline.py:32 assemble_episode`）、`candidate_search.py:32 choose_eligible`（同向长度比） | |
| 整航线检查 | `task_v07/unified/checks.py:68 plan_checks`；`FreeSpace.segment_issues`（`free_space.py:101-113`）；`task_v07/expansion/pipeline.py:100 precheck` | 禁区/障碍物余量、预警区访问次数、对齐段 100 m、汇合点距离、撤离点余量、终点间距等 |
| 写盘 | `worker_b`：`planning/<sid>/candidate_pool.pkl`（仅候选池非空时，`run_v07_fe_production.py:328-341`；内容 `pool[:5]` + 完整 `search` 报告）、`planning/<sid>/planning_result.json`（`:343-359`）、`status/B__<sid>.json`（`:360-366`） | |

### 仿真阶段（C）

`worker_c`（`run_v07_fe_production.py:380`）→ `scripts/run_v07_s2_episode_batch.py:176 run_episode_job(payload)` → `pair_result`（`scripts/run_m3_r3_r4.py:68`）→ 每个方式 `qc_episode`（`run_m3_r3_r4.py:90`）→ `qc/<sid>.json`、`status/C__<sid>.json`。

| 环节 | 函数（文件:行） | 说明 |
|---|---|---|
| 候选池载入 | `run_v07_s2_episode_batch.py:187-205` | 读 `candidate_pool.pkl`，核对 SHA256 与骨架身份 |
| 单机预演 | `task_v07/unified/rehearsal.py:61 rehearse` → 每个成员 `task_v07/execution.py:53 execute(group, {a:0}, only_agent=a, reference_version="r3")` → `rehearsal.py:16 evaluate_solos`（`task_v07/labels.py:169 measure` 逐机判定） | 最多 5 个候选（`calibration.max_rounds`，`:186,213`）依次试；失败类别 `rehearsal_failure` |
| 时刻安排 | `task_v07/unified/timing.py:159 select_timing` → `:142 episode_plan` → `:103 group_plan`（出发延迟抽取）；`task_v07/expansion/solo_spacing.py:65 solo_interval_check`（把单机 10 Hz 轨迹按延迟平移后求最小间距，阈值 2 m，`generator_v07_r1.json overlay.min_separation_m`） | 每个方式最多 20 次抽取（`redraw_budget_per_version`，`timing.py:70`），失败类别 `timing_conflict` |
| 联合仿真 | `run_v07_s2_episode_batch.py:268 execute(current, delays, time_budget=joint_budget(...), reference_version="r3")`（`task_v07/execution.py:53`） | 每个方式一次 |
| 判定与标签 | `write_result`（`run_v07_s2_episode_batch.py:116`）→ `labels.py:169 measure` → 多组 `task_v07/expansion/multi_labels.py:11 measure_groups` → 每组 `task_v07/criteria_labels.py:16 measure_criteria`；`labels.json` 由 `task_v07/io.py:69` 写；`prefix_labels.json` 由 `audit_episode`（`run_v07_s2_episode_batch.py:64-70`）写 | |
| 独立审计 | `run_v07_s2_episode_batch.py:45 audit_episode`：重新 `measure` 并比对、列置换不变性、`load_episode`、前缀标签、`scripts/audit_v07_s2_groups.py:30 audit_groups`（→ `independent_exact_audit.json`）、`task_v07/expansion/geometry_checks.py:26 exact_frame_geometry` + `scripts/audit_v07_s2_infrastructure.py audit_geometry`（→ `policy_geometry_audit.json`）；`:88 group_truncations`（→ `truncation_check.json`）；`worker_c` 中 `pair_result`、`qc_episode` | |
| 写盘 | `task_v07/io.py:56 write_episode`：`truth.csv`、`observations.csv`（`:60-61`）、`truth_10hz.npz`、`model_input.npz`、`frame_labels.npz`（`:62-67`）、`public_scene.json`、`labels.json`、`task.json`、`source.json`、`manifest.json`（`:68-79`）；`write_result` 另写 `metrics.json`（`:171`）；`run_episode_job` 另写 `episodes/<sid>/` 下 `candidate_pool.json`、`geometry_XX/*`（含每机 `single_agent_*.npz`）、`skeleton.json`、`planning_checks.json`、`timing_*.json`、`geometry_history.json`、`candidate_search.json`（`:205-260`），每个方式目录 `solo_overlay_comparison.json`（`:282`） | |

### 输入与输出

| 阶段 | 输入 | 输出位置 |
|---|---|---|
| B | `<run_dir>/registration.json`、`<run_dir>/descriptors/descriptors.json`（取 `sid` 那一条）、场景族目录的 `public_scene.json` / `family_initial.json`、冻结配置（`configs/generator/*.json`、`configs/criteria/criteria_v07_r1.json`） | `<run_dir>/planning/<sid>/`、`<run_dir>/status/B__<sid>.json` |
| C | 同上 + `<run_dir>/status/B__<sid>.json`（须 PASS）、`<run_dir>/planning/<sid>/planning_result.json` 与 `candidate_pool.pkl`；fastsim r3 配置 `configs/fast_dynamics/m3_r3_candidate_v1.json`（SHA256 核对，`swarm_sim/fast_dynamics/reference_r3.py:226-233`） | `<run_dir>/episodes/<sid>/`、`<run_dir>/qc/<sid>.json`、`<run_dir>/status/C__<sid>.json` |

### 输出路径由什么决定

- worker 的全部输出路径都由命令行参数 `--run-dir` 决定（`worker_b`：`:321`，`worker_c`：`:398` 的 `payload["out"] = run_dir/"episodes"`）；`run_episode_job` 只写 `payload["out"]` 之下。
- 新批次时 `--root`（默认 `DEFAULT_ROOT = PROJECT.parent.parent/"SwarmData"/"v07_first_edition"`，`:49`）+ `--run-id` 决定 `run_dir`；`_check_root` 只禁止写进项目工作树内部（`:141-146`）。
- 写死的路径只有输入侧：`BASELINE_PATH`（`:50`）、配置文件路径（`task_v07/unified/config.py:6`、`geometry_config.py:6`、`criteria.py:5`、`execution.py:16`、`reference_r3.py:216`），以及 `registration.json` 中登记的场景族绝对路径。
- `worker_c` 写 `qc/<sid>.json` 依赖批次目录里预先建好的 `qc/`（`_new_run`，`:213-214`）；`save_json`（`task_v07/io.py:16`）不建父目录。

**结论：可以在隔离目录中运行**——只需把 `registration.json`、`descriptors.json` 复制到隔离的 `run_dir`，即可直接调用 `worker_b(run_dir, sid)`；仿真阶段可按 `run_episode_job` 的步骤调用同一组函数（§5 的驱动 `scripts/v8_01_driver.py` 即如此）。

---

## 4.2 写死的衔接段与搜索预算

### 4.2.1 衔接段怎么构造

参数来源：`configs/generator/geometry_v07_r1.json`（下称 G）与 `configs/generator/generator_v07_r1.json`（下称 M）。

**入口（进场门）位置**

| 执行方式 | 固定了什么 | 位置 |
|---|---|---|
| 过境 transit | 方向 θ ~ U(G.transit.direction_deg=[0,360])；每股方向 = θ + 股相对方位；横向位置取可行弦区间的分位数 q ~ U(G.transit.chord_quantile=[0,1])；股内成员间距 = 场景族 `lateral_spacing_m`；入口 = 该平行线与预警区边界的交点；50% 概率（G.transit.bend_probability）在弦中点折转 U[10,30]°（G.transit.bend_angle_deg） | `shapes.py:22-59` |
| 其余（区域搜索/抵近观察/巡逻以外的门） | `gate_slots`：过目标中心的平行线（偏移 = 成员序号×`lateral_spacing_m`），方向指向中心，入口 = 与预警区边界交点 | `operation_shapes.py:37-52` |
| 巡逻 monitoring | 入口为预警区边界上与巡逻线相切方向的交点（`shared_tangent_parallel_lane`） | `patrol_shape.py:53-64,148-152` |
| 佯动/突入 | 入口沿门方向直线到作业段（`straight_parallel_lane`） | `terminal_shapes.py:201-202,232` |

**进场衔接（`route.py:84 _approaches`）**

- 同一股、同一 `entry_id` 的成员合成一个"块"（`:87-88`）；块中线 = 成员入口横向坐标的中点（`:94-98`）。
- 汇合点（collection）：块中线与"预警区向外偏移 `collection` 米"的轮廓的交点；`collection` ~ U(G.collection_clearance_m=[50,250])，每次衔接尝试重抽（`:165` / `operation_routes.py:36`）。
- 对齐点（lead）：入口前 G.alignment_length_m=100 m + 块半宽（`:104-106`）。
- 编队点（form-up）：从成员起点均值沿 `start_line` 的向内方向，依次试深度 `(max(100, 2·半宽+50), 100, 150, 200, 60)` m（**代码常量**，`:114`），取第一个可行且外部可视的点。
- 编队点 → 对齐点：外部可视图最短路径 `free.planner(half, exterior=True, reference_corridor=True).path`（`:110,120`），障碍物余量 = G.obstacle_margin_m 35 + G.corridor_half_width_factor 1.5×半宽 + G.corridor_pad_m 2（`free_space.py:126-127`）。
- 每机航线 = 参考折线按横向偏移平移（`offset_lane`，外侧圆弧弦误差 G.chord_error_m=1 m，`:47-81`），起点替换为该机的真实起点（`:129`）。
- 拒绝条件：对齐段被转弯吃掉（<100 m，`:132-134`）、入口前离预警区 <G.pre_entry_warning_clearance_m=10 m（`:135-142`）、车道燕尾（`:79-80`）、找不到外部路径（`:121-123`）、找不到编队点（`:118-119`）。

**作业段连接（非过境，`operation_routes.py:41-53`）**：`shared_tangent_parallel_lane`/`straight_parallel_lane` 直接 `[门, 作业起点]`；否则 `门 → 门内 100 m 对齐点 → 作业起点前 lateral_spacing 处 → 作业起点`，经内部可视图 `connect`（`:16-23`），再以半径 `lateral_spacing/2` 倒圆角（`round_corners`）。

**撤离**

- 过境（`route.py:172-182`）：沿出口方向（直弦方向或折转后方向）从作业终点射到"预警区外偏移 `retreat` 米"的轮廓；`retreat` ~ U[M.retreat.warning_clearance_m=50, G.retreat_clearance_max_m=300]，每次衔接尝试重抽（`:166`）；终点到所有预警区 ≥50 m 且在可行域内，否则 `retreat_outside_available_domain`。
- 其他方式（`construction.py:37-66 retreat_endpoint`）：名义出口方向依次旋转 `(0, 30, -30, 60, -60, 90, -90)`°（**代码常量**，`:46`），跳过朝内方向，取第一个满足"到所有预警区 ≥50 m 且可行"的终点；然后 `作业终点 → 作业终点外 lateral_spacing → 终点`，内部可视图连接并倒圆角（`operation_routes.py:55-62`）。突入（intrusion）无撤离段（`:55,63-64`）。
- 名义出口方向：区域搜索 = 作业终点相对目标中心的外向（`operation_shapes.py:114`）；抵近观察/佯动 = 门方向的反向（`:144`、`terminal_shapes.py:202`）；巡逻 = 最后一段切向（`patrol_shape.py:143-147`）。

**多股（同组内）**（`public_approach_shape.py:8-39`，键与意图无关）：
- 仅 `approach_mode == multi_direction` 时分股；成员 ≤5 时 2 股，否则随机 2 或 3 股（`:15`）。
- 2 股：相邻方位差 U[100,180]°；3 股：两个相邻差各 U[50,120]°（`:16-19`，**代码常量**）。
- 成员随机打乱后均分到各股（`:23-30`）；股内间距 = 场景族 `lateral_spacing_m`；股内成员与入口按横向坐标单调对应（`assign.py:5-23`）。
- 多向入口夹角只做诊断（`checks.py:180-185`，G.multi_heading_aim_deg=90 标注 diagnostic_only），不作为拒绝条件。

**多组（组间）**：
- 同目标的不同组，作业区方位差须 ≥ M.combination.same_target_bearing_min_deg=30°（`group_candidate_pool.py:114-119`；`bearing_allowed` 默认值 60° 在此被 30° 覆盖）。
- `same_direction` 抽签：每组进场长度不得超过该组可行最小值的 M.combination.same_direction_length_ratio_max=1.30 倍（`candidate_search.py:32-51`、`group_candidate_pool.py:132-139`）。
- 组间出发偏移 `between_group_offset_s` ~ U[0,90] s（`task_v07/expansion/sampling.py:50`），加到该组全部出发延迟上（`timing.py:148-150`）。

### 4.2.2 搜索预算类常量

| 名称 | 取值 | 位置 | 备注 |
|---|---|---|---|
| 每组提案数 `CANDIDATE_BUDGET` | 200 | `task_v07/expansion/candidate_search.py:18`；`group_candidate_pool.py:32,92` 默认参数 | G 中 `group_proposals: 200` **未被代码读取** |
| 组合预算 `COMBINATION_BUDGET` | 1000 | `group_candidate_pool.py:14` | G 中 `combination_budget: 1000` **未被代码读取** |
| 每个提案内的形态尝试 | 20 | G.`shape_attempts`（`shapes.py:21`、`operation_shapes.py:165`） | `patrol_band_too_narrow` 不重试，直接抛出（`operation_shapes.py:176`） |
| 每个提案内的衔接尝试 | 10 | G.`connection_attempts`（`route.py:164`、`operation_routes.py:35`） | |
| 编队点深度候选 | 5 个 | `route.py:114` | 代码常量 |
| 撤离方向旋转候选 | 7 个 | `construction.py:46` | 代码常量 |
| 单机预演/候选轮数 | 5 | M.`calibration.max_rounds`（`run_v07_fe_production.py:326`、`run_v07_s2_episode_batch.py:186,213`） | 候选池只保存前 5 个 |
| 每方式出发延迟抽取 | 20 | M.`timing.redraw_budget_per_version`（`timing.py:70`） | |
| 规划进程超时 | 3600 s | `run_v07_fe_production.py:53`（`--planning-timeout-s`） | |
| 仿真进程超时 | 5400 s | `run_v07_fe_production.py:54`（`--episode-timeout-s`） | |
| 联合仿真时限 | 最晚计划完成时刻 + max(120 s, 20%) | `task_v07/execution.py:169-195 completion_budget` | 超过即 `execution_status = timeout` |
| 数值二分次数 | 区域面积 32、佯动深度 36、突入深度 40 | `operation_shapes.py:93`、`terminal_shapes.py:193,226` | 求解精度，不是搜索预算 |

### 4.2.3 拒绝原因 → 抛出位置与触发条件

| 原因 | 位置 | 触发条件 |
|---|---|---|
| `connection_search_budget_exhausted` | `route.py:203`（过境）、`operation_routes.py:92`（其余） | 10 次衔接尝试（每次重抽汇合距离与撤离距离）全部抛出 `GeometryRejected`；子原因见下 |
| `shape_search_budget_exhausted` | `shapes.py:72`（过境）、`operation_shapes.py:178`（其余） | 20 次形态抽取全部失败（含形态阶段的进场线预检 `precheck_operation`） |
| `approach_length_ratio_exceeded` | `group_candidate_pool.py:137` | `same_direction` 抽签下，组合可行但某组进场长度 > 该组最小值 ×1.30 |
| `same_target_work_area_bearing` | `group_candidate_pool.py:118` | 同一目标的两组作业区方位差 <30° |
| `patrol_band_too_narrow` | `patrol_shape.py:100`（`operation_shapes.py:176` 直接上抛） | 巡逻带上界 = 预警偏移 − 35（`warning_inset_m`）−（n−1）×间距 < 下界 = 戒备偏移 + 30（`alert_clearance_m`）；只与成员数和场景有关，200 个提案全部同样失败 |
| `whole_route_check` | `adapter.py:36` | `plan_checks` 有任何问题（`checks.py:68-186`）；问题 code：`collection_clearance`（汇合点距预警区不在 [50,250] 或不可行，`:127-132`）、`terminal_endpoint_spacing`（终点两两间距 <2 m，`:157-162`）、`constraint_clearance`（航段离障碍/禁区不足余量，`free_space.py:111`）、`warning_visit_count`（进入目标预警区不是恰好 1 次，`:99-100`）、`pre_entry_warning_clearance`、`alignment_length`、`retreat_warning_clearance`、`retreat_clearance_max` 等 |
| `existing_output_precheck` | `adapter.py:43` | `pipeline.py:100 precheck` 不通过（全部记录中未出现） |
| 衔接子原因 `retreat_outside_available_domain` | `route.py:181` | 过境撤离终点到某预警区 <50 m 或不在可行域 |
| `alignment_consumed_by_lane_turn` | `route.py:133` | 车道内侧斜接使入口前直线段 <100 m |
| `no_exterior_connection` / `no_interior_connection` | `route.py:122` / `operation_routes.py:21` | 可视图找不到路径 |
| `lane_swallowtail` | `route.py:80` | 车道偏移后出现燕尾 |
| `retreat_endpoint_invalid` | `construction.py:66` | 7 个撤离方向都不合格 |
| `sub_metre_semantic_join` | `route.py:42` | 去重后出现 <1 m 的航段 |
| 形态子原因 `ingress_line_blocked` | `construction.py:71`、`patrol_shape.py:60,64` | 入口前 100 m+半宽 的进场线或门内段被障碍/禁区挡住 |
| `survey_area_unavailable` / `survey_insufficient_strips` / `survey_strip_unavailable` | `operation_shapes.py:91,103,108` | 区域搜索扇形面积不够 / 条带数少于成员数 / 条带与扇形交不成一段 |
| `patrol_arc_too_short` | `patrol_shape.py:116` | 可用巡逻弧 <150°（`arc_min_deg`） |
| `intrusion_contour_unavailable` / `intrusion_interior_unavailable` / `intrusion_endpoint_spacing` | `terminal_shapes.py:52,56,59,72` | 突入终点所在轮廓求不到 / 内部深度求不到 / 终点间距 < lateral_spacing |
| `work_segment_clearance` | `shapes.py:64`、`operation_shapes.py:171` | 作业段离障碍/禁区不足余量 |

各子原因的实际计数见 `rejection_subreasons.md`。

---

## 4.3 仿真执行接口（fastsim）

1. **入口**：`task_v07/execution.py:53 execute(skeleton, delays_s, *, only_agent=None, time_budget=None, route_switch=None, reference_version="r2")`。`reference_version="r2"` 用 `configs/fast_dynamics/m3_r2_20261013_v1.json`（SHA256 `94822513…`，`:55-57`），`"r3"` 用 `swarm_sim/fast_dynamics/reference_r3.py:226 candidate_config()` 读 `configs/fast_dynamics/m3_r3_candidate_v1.json`（SHA256 `0fe3efff…`，策略须为 `continuous_route_v3`，`:58-61`）。函数默认值是 r2；生产中由 `worker_c` 在 payload 里写死 `"reference_version": "r3"`（`run_v07_fe_production.py:401`），`run_episode_job` 读出后传给 `rehearse` 与联合 `execute`（`run_v07_s2_episode_batch.py:182,220,270`）。底层：`swarm_sim/fast_dynamics/engine.py:48 SynchronousEngine`、`route_tracker.py:154 RouteTracker`。
2. **输入**：
   - 参考航线 = 每机航点列表 `skeleton["references"][a]["points_enu_m"]`（N×3，`execution.py:66`）+ 一个标量巡航速度 `skeleton["cruise_speed_m_s"]`（`:76-77`）。不是带时间的参考轨迹。
   - **不能逐段/逐航点指定速度**：`RouteTracker(points, speed_m_s, …)` 只收一个速度（`route_tracker.py:162,178`），各转角的限速由几何自动求（曲率、加速度、加加速度上限，`:236-240`），前视制动（`:315-323`）。
   - 跟踪门限：航点见证圆半径 `gates = min(0.5, 0.2×相邻航段最短长度)`（`:215-216`）；偏离参考超过 `tracking_tube_m = 0.5 m` 时改为飞回当前图元起点（`:304-306`）。显式停车：转角 ≥175° 的航点记为 `stops`（`:221-222`），在该航点前减速并以端点速度律停到航点（`:302-303`）。航线高度必须恒定（`:168-169`）。
   - 中途悬停：`references[a]["intermediate_dwell"] = {"waypoint_index", "duration_s"}` 时换用 `task_v07/dwell.py:9 DwellRouteTracker`（`execution.py:79-85`）。
   - 另有 `route_switch`（`:67-72,100-110`）：在一个正的 10 Hz 时刻把指定飞机的航线换成新航线（新航线首点须与当时位置重合），用于中止分支重放。
3. **初始状态**：每机 `skeleton["initial_states"]` 的 `position_enu_m`、`velocity_enu_m_s`、`acceleration_enu_m_s2`（`execution.py:73-74` → `PlantState(p, v, a)`）。不从静止开始：生产骨架的初速度来自场景族 `family_initial.json`（例：`prod_f100_140/…353b8b5f…_ext_005/synchronous/task.json` 中 `uav_06` 初速 (1.28, −0.05, 0) m/s）。两个一阶滞后环节（速度响应 `velocity_response_time_s=0.475`、加速度响应 `response_time_s=0.1`）的内部状态就是 v 和 a；控制器与对象没有其他隐藏积分状态（`engine.py:94` 注释、`controllers.py:195-207`、`plants.py:155-177`）。跟踪器状态（当前图元、已见证航点、停车计时）不能从外部传入，只能由航线首点重建（`RouteTracker.__init__`，`route_tracker.py:162-189`）。
4. **等待与悬停**：
   - 出发延迟：`release = round((initial_settle_s + delay)·1e6)`，须在 10 Hz 网格上（`execution.py:86-88`）；`initial_settle_s = 20 s`（`task_v07/expansion/pipeline.py:25` 写入骨架）。释放前该机的期望速度由 `endpoint_velocity(p, 初始位置, …)` 给出，即保持/回到初始位置（`execution.py:116-120`）。
   - 中途定点停留：只有上述 `intermediate_dwell`（仅抵近观察使用），到点后速度 ≤0.15 m/s、距离 ≤1 m 持续 `duration_s` 再继续（`dwell.py:46-61`）。没有通用的"在任意点停留 T 秒"参数。
   - 终点：到达终点半径/速度并保持 `stop_hold_s` 后整段结束（`execution.py:149-156`）。
5. **多机**：同一个循环一起推进。`SynchronousEngine.step` 对全部飞机的 (N,3) 数组一次性求控制与积分（`engine.py:69-89`）；跟踪器命令与事件观测按机 Python 循环（`execution.py:118-120,127-128`）。**机间间距不在仿真中检查**：时刻安排阶段用平移单机轨迹预测（`solo_spacing.py:65`，2 m），仿真后在判定中算 `minimum_separation_m`（`criteria_labels.py:42-50`、`multi_labels.py:39-50`），<2 m 则 `generation_quality = generation_error`（`criteria.py:12-21`）。
6. **实现方式**：每个循环步（`execution.py:99-156`）：向量化求释放前期望速度；逐机 Python 调 `tracker.command`；**每步对每个跟踪器做事务快照**（`_snapshot_tracker` 复制 `__dict__`，`:23-29,125`）；向量化 `engine.step`（控制器 → 对象恒定加加速度积分，并按 10 Hz 生成样本）；逐机 `observe_segment`（对本步三次多项式求航点见证圆的进出根，`route_tracker.py:341-`、`references.py:258 _roots`）；若有控制事件早于步末则截断本步并回滚快照（`:129-143`）；对新样本向量化检查终点保持。积分步 `step_us = 20000`（r3 配置）。`_TRANSACTION_STATS` 记步数与回滚数（`:20,121,135`）。
7. **输出**：`engine.samples` 只保存 10 Hz 网格上的 `StateView(t_us, p, v, a)`，**降采样在 `engine.step` 内完成**（`engine.py:81-83`，`output_period_us = 100000`）；`execute` 返回 `agent_ids, time_us, p, v, a, end_us, execution_status, wall_s, release_s, config_sha256, time_budget`（`execution.py:157-166`）。20 ms 积分步的状态不保存。

§5.4 的续跑实验结果见报告。

---

## 4.4 判据（criteria/0.7-r1）

配置：`configs/criteria/criteria_v07_r1.json`（`task_v07/criteria.py:5`）。主实现 `task_v07/criteria_labels.py:16 measure_criteria`（每个任务组调用一次），多组汇总 `task_v07/expansion/multi_labels.py:11 measure_groups`，检测器 `task_v07/detectors.py`，诊断量 `task_v07/criteria_diagnostics.py`。

**时间范围的通用约束**：`measure(..., cutoff_s=None)` 只支持**前缀** `[0, cutoff)`（`criteria_labels.py:24-26`）；`validate_grid` 要求时间轴从 0 开始、步长 0.1 s（`labels.py:50-53`），所以不能直接对 `[t0, t1]`（t0>0）计算。`complete = cutoff_s is None and execution_status in (completed, timeout)`（`criteria_labels.py:23`）：前缀上"未发生"类条件取 `None`（`bounded`/`measurable`，`labels.py:45-47,113-114`），失败结论只在整段结束时给出（`observed_conditions_result`，`labels.py:105-110`）。

| 名称 | 输入 | 主体 | 时间范围 | 依赖指定信息 | 参数 |
|---|---|---|---|---|---|
| 圈层等级 `geometry_facts(..., layer_offsets)`（`criteria_labels.py:33-36`） | 逐帧位置、各设施圈层几何 | 单机×设施×帧 | 逐帧，可任意窗口 | 否 | 圈层偏移来自场景 |
| 作业区间 `work_mask`（`detectors.py:16`） | 对指定目标的圈层序列 | 单机 | 首次到最后一次 ≥预警层之间的全部帧；依赖窗口端点（窗口外的再进入会改变区间） | 指定目标 | — |
| 驻留 `dwell`（`detectors.py:32`） | 逐帧 xy、作业区间掩码 | 单机 | 滑动 20 s 窗，可在任意窗口内计算，但掩码取自 `work_mask` | 指定目标（经掩码） | `detectors.dwell`: window_s 20、radius_m 30、max_start_end_m 30 |
| 重访 `revisit`（`detectors.py:67`） | 逐帧 xy、速度、圈层、作业区间、**目标中心** | 单机 | 在给定帧序列内搜索；最小时间间隔用整段 `speed.max()` 计算（`:83`），窗口不同结果可能不同；方位覆盖按区间计算 | 指定目标（中心、圈层） | `detectors.revisit`: radius 30、min_departure 150、parallel_max 45°、antiparallel_min 135°、min_azimuth_coverage 120°、min_speed 0.5 |
| 覆盖 `coverage`（`detectors.py:132`）+ 组覆盖（`criteria_labels.py:175-183`） | 逐帧 xy、速度、圈层、障碍掩码、**生成时的搜索扇形 `skeleton["survey"]`** | 单机 → 组并集 | 累积量，可对任意帧子集计算 | 指定搜索区域（规划产物） | `detectors.coverage`: min_group_fraction 0.80、effective_speed_min 0.5 |
| 核心事件 `event`（`labels.py:60`） | 角色对应掩码的首帧：过境/巡逻=进入预警区，佯动=进入戒备区，突入=进入保护区，区域搜索=首个有效观测帧，抵近观察=预警层内首次驻留 | 单机 | 首次发生，前缀可算 | 角色（决定用哪个掩码）、指定目标 | — |
| 过境条件 entered_warning / single_warning_visit / no_dwell / no_revisit（`criteria_labels.py:67-74`） | 圈层、驻留、重访 | 单机 | 前两项前缀可得"已发生"；"恰好一次""未驻留""未重访"需整段结束 | 角色、指定目标 | 同上 |
| 区域搜索 effective_observation / no_revisit（`:75-85`） | 覆盖有效帧、重访 | 单机 | 同上 | 角色、搜索区域 | 同上 |
| 抵近观察 observation_dwell / no_revisit（`:86-93`） | 预警层内驻留 | 单机 | 驻留可在前缀确认 | 角色、目标 | dwell 参数 |
| 巡逻 patrol_revisit（`:94-97`） | 重访 | 单机 | 前缀可确认"已发生" | 角色、目标中心 | revisit 参数 |
| 佯动 entered_alert / single_alert_visit（`:98-103`） | 圈层 | 单机 | "恰好一次"需整段 | 角色、目标 | — |
| 突入 entered_protected / near_facility_contour（`:104-108`） | 圈层、到目标轮廓距离最小值 | 单机 | 前缀可确认"已发生" | 角色、目标 | `roles.intrusion.max_contour_distance_m` 50 |
| 撤出状态 ended_outside_warning（`:120-121`） | **最后一帧**的目标圈层 | 单机 | **依赖整段结束状态**（前缀为 None） | 指定目标 | — |
| 禁入 exclusion_policy_respected（`:126-130`） | 圈层 vs 角色允许最深层 | 单机 | "未违反"需整段 | 角色、目标 | `exclusion_max_layer`：other_facilities 1、transit 1、reconnaissance 1、monitoring 1、feint 2、intrusion 3 |
| 同步/递次 `coordination`（`labels.py:69`） | 组内各机核心事件时刻 | 编组 | 需要组内全部成员的核心事件都已发生，否则 `unknown` | 角色（决定核心事件）、组成员 | `coordination`: sync_window_s 10、batch_split_gap_s 20 |
| 与指定方式比对 `coordination_matches_assignment`、`batch_members_match_assignment`（`criteria_labels.py:187-191`） | 观测协同分类、**计划方式与计划批次** | 编组 | 同上 | 是（计划方式、批次） | — |
| 逼近方式分类 `approach_heading_deg` + `approach_classification`（`labels.py:117-152`、`criteria_labels.py:10-13`） | 首次进入预警区前 100 m 位移的航向；组内两两最大夹角 | 单机 → 编组 | 只需首次进入前的轨迹，前缀可算 | 指定目标（决定"进入预警区"） | `approach`: heading_distance_m 100、same_max_deg 30、multi_min_deg 60 |
| 组结论 member_contributions_complete / shared_coverage（`criteria_labels.py:172-183`） | 成员结论、覆盖并集 | 编组 | 继承成员 | 是 | — |
| 集群结论 primary_task_success / all_task_groups_complete / primary_target / between_group_timing（`multi_labels.py:63-106`） | 各组结论；突防取 `main_group_id` 组 | 集群 | 继承 | 是（主组 = 生成时指定的突入组） | — |
| 质量 `quality_facts`（`criteria.py:12`） | 最小机间距、障碍内帧数、出界帧数 | 集群 | 累积量，可窗口 | 否 | `quality.min_separation_error_m` 2.0 |
| 诊断（不作判据）`role_diagnostics`（`criteria_diagnostics.py:6`） | 作业期折返次数、撤离点到达、终点保持、过境进出方位、佯动最深点与回撤、巡逻圈数等 | 单机 | 大多依赖 `work_end`（最后一次在预警区内之后一帧） | 用到 `references`（终点、扫描端点、观察点） | `diagnostics`: reversal_angle_deg 135、reversal_lag_s 20 |

**prefix_labels.json**：由 `run_v07_s2_episode_batch.py:45 audit_episode` 生成（`:64-70`）。截断规则：`cutoff = min(组内已知核心事件时刻) − 0.1 s`（若该最小值 >0.2 s），否则 `cutoff = 1.0 s`；对 `t < cutoff` 的帧调用同一个 `measure(..., cutoff_s=cutoff)`，即**全部字段在前缀上重新计算**（complete=False，"未发生"类条件为 None），并断言前缀里没有核心事件。另有 `truncation_check.json`：每组在 `(最早核心事件 + 最晚作业结束)/2` 处截断，检查前缀不得判组成功（`:88-113`）。

**角色与执行方式枚举**

- 意图：`INTENTS = ("transit", "reconnaissance", "monitoring", "feint", "penetration")`（`task_v07/expansion/sampling.py:12`）。
- 角色：`ROLES = ("transit", "reconnaissance", "monitoring", "feint", "intrusion")`（`sampling.py:13`）。
- 执行方式：`transit`、`area_search`、`close_observation`、`monitoring`、`feint`、`intrusion`（角色→方式的允许表 `task_v07/unified/spec.py:182-183`；侦察在 `area_search`/`close_observation` 中随机取一，`sampling.py:115`）。代码中没有 `approach_observation`，对应的是 `close_observation`。判据分支 `role_kind`（`labels.py:22-38`）。
- **突防由哪些角色组成、在哪里组装**：`sampling.py:98 build_descriptor`——随机选一个单元为主单元（`:109`），主单元角色 = `intrusion`，其余单元按 0.5/0.3/0.2 取 `intrusion`/`feint`/`monitoring`（`:112-114`）；`merge_units`（`:59-83`）把同 (目标, 角色) 的单元合并为任务组；`derive_intent`（`:86-95`）规定：含 `intrusion` 且角色 ⊆ {intrusion, feint, monitoring} 即为 penetration。主组 = `main_group_id`，集群结论以主组为准（`multi_labels.py:84-89`）。

**可能对"迂回"有用的已有逐帧量（只列事实）**

| 量 | 存放位置 | 说明 |
|---|---|---|
| 逐帧 p、v、a（10 Hz） | `truth_10hz.npz`（`io.py:62`）、`truth.csv` | |
| 逐帧各设施圈层等级 | `frame_labels.npz` 的 `region_all_facilities`（T×N×F，0–3） | `criteria_labels.py:221-223` |
| 逐帧对指定目标的圈层 | `frame_labels.npz` 的 `region_assigned_target` | |
| 逐帧阶段码 | `frame_labels.npz` 的 `phase`（0 低速、1 接近、2 核心事件后、3 撤出、4 在终点） | `criteria_labels.py:155-158` |
| 进入预警区前 100 m 的航向 | `labels.json` → `task_groups.<g>.observed.approach_headings_deg`（每机）与 `approach_span_deg`、`approach_classification` | `criteria_labels.py:63,196-202` |
| 目标中心 | `labels.json` → `task_groups.<g>.observed.work_area_center_m` | 相对设施中心的逐帧方位角**未存盘**，可由 p 与此中心算出 |
| 过境进/出预警区方位角及差、预警区内累计转角 | `labels.json` 每机 `observed.contribution` 中 `entry_azimuth_deg`、`exit_azimuth_deg`、`entry_exit_azimuth_difference_deg`、`cumulative_turn_in_warning_deg` | `criteria_diagnostics.py:36-56` |
| 突入进入保护区时的方位角 | `entry_azimuth_deg` | `criteria_diagnostics.py:34-37` |
| 重访的方位覆盖角 | `contribution.revisit.azimuth_coverage_deg` | `detectors.py:120-127` |
| 作业期折返次数、到目标轮廓最小距离 | `contribution.work_reversal_count`、`minimum_contour_distance_m` | `criteria_diagnostics.py:17-21` |
| 巡逻观测圈数、组内扇区最大重访间隔（诊断） | `lap_count_observed`、`task_groups.<g>.observed.shared_revisit` | `criteria_diagnostics.py:94-136` |
| 逐帧到目标的有符号距离 | **未存盘**（`criteria_labels.py:57` 内部量） | |
