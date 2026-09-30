# TaskSpec v2：共享区域任务接口与使用说明

本文对应代码版本 `0.3.0`。接口示例不等于实飞性能承诺；本轮实际运行、失败和未验证项以 [实现与验证记录](v0.3_implementation_and_verification.md) 为准。

## 1. 支持的任务与边界

一个公共矩形观察区域由 1～6 架同构多旋翼分工完成。执行过程为 `approach → observe → return`，返回可关闭。每架飞机使用本机独立 ArduCopter SITL，任务由 Python 集中预规划，最终仍编译为已有 AUTO 航点阶段。标准入口的仿真计算和数据分析都在当前电脑执行，启动时不调用外部仿真服务器。

当前只接受 `reconnaissance / area_coverage`：固定观察高度、公共地面海拔、公共 ENU 坐标、一个轴对齐矩形、理想水平圆盘观察模型。它描述几何区域观察，不代表真实相机/雷达探测或从轨迹识别出的隐藏意图。

未实现任意多边形、非空禁区、障碍绕行、在线任务协商/重分配、在线避碰、共享碰撞动力学、物理锁步、噪声/风场或真实传感器。`restricted_regions` 必须为空；声明不支持的约束会被拒绝，不会被忽略。

## 2. 任务格式与执行场景格式

完整输入示例为 [recon_shared_3uav.json](../missions/recon_shared_3uav.json)。其 54 m × 30 m 区域、3 机、1 m 到达容差等数值保留自指导示例。另有较小的逻辑/集成验证输入：

| 文件 | 公共区域 | 分区方向 | 飞机数 |
|---|---|---|---|
| [recon_smoke_3uav.json](../missions/recon_smoke_3uav.json) | 36 m × 8 m | east | 3 |
| [recon_smoke_2uav_north.json](../missions/recon_smoke_2uav_north.json) | 8 m × 24 m | north | 2 |
| [recon_smoke_6uav.json](../missions/recon_smoke_6uav.json) | 72 m × 8 m | east | 6 |

v2 顶层只允许以下字段，全部要求显式提供。各层递归拒绝未知字段、缺失字段、非有限数、布尔值冒充数字、重复身份和不支持的枚举。

| 字段 | 含义与约束 |
|---|---|
| `schema_version` | 整数 `2`，表示任务格式 |
| `task_id` | 本次任务定义的安全标识符，1～64 个字母/数字/下划线/连字符 |
| `family_id` | 基础任务族标识符；派生变体与重试必须继承，用于整组数据划分 |
| `seed` | 0～\(2^{63}-1\) 的整数，记录输入来源；编译器本身不采样 |
| `scenario` | 公共地图、原点、区域和车辆 |
| `mission` | 任务语义、完成条件和观察模型 |
| `planner` | 确定性的规则规划算法与间距裕量 |
| `platform` | 同构平台名义能力和资源限制 |
| `execution` | 当前 AUTO 后端执行参数 |

`compile_task()` 根据任务版本分派。v2 编译结果仍是执行场景 `schema_version=1`，并携带规范化的 `task_spec.schema_version=2`、`family_id`、`planning` 和 `semantic_plan`。任务格式版本和执行场景版本不能混淆。

`validate_task_binding()` 会重新编译保留的任务，比较完整执行场景。修改航点、责任区或语义映射之后必须回到任务输入修改并重新规划，不能直接改编译结果绕过绑定。规范化按 agent ID 排序，数值字段统一为浮点数；ID、版本与种子保持相应原始类型。

旧 v1 的 `point_visit / rectangle_patrol / coverage_scan` 输入、编译结果和标签含义保留。旧 `coverage_scan` 不自动重标成 `reconnaissance`。

## 3. `scenario`：共享地图

| 字段 | 结构与约束 |
|---|---|
| `scene_id` | 安全场景标识符 |
| `origin` | `lat / lon / alt_msl_m`；纬度 −80～80°，经度 −179～179°，海拔 −400～8000 m |
| `world` | `east_bounds_m / north_bounds_m / flight_up_bounds_m`，每项是严格递增的二元素数组 |
| `regions` | 恰好一个矩形，字段为 `id / type / min_east_m / min_north_m / width_m / height_m`；`type=rectangle` |
| `restricted_regions` | 只接受 `[]` |
| `vehicles` | 1～6 项；每项 `id / sysid / east_m / north_m / heading_deg`，仅 `heading_deg` 可省略，默认 0 |

所有地面位置和计划航点使用同一个公共 ENU 原点。世界东/北范围必须在后端各 ±2000 m 内；矩形正面积并完整位于世界内；生成点也必须在世界内。`sysid` 为 1～250 的唯一整数，agent ID 唯一且最多 48 字符。

`flight_up_bounds_m` 在 3～100 m 内，约束稳定飞行高度；地面生成点不受其下限限制。起飞与降落阶段的实际检查应用水平边界和高度上限，稳定飞行阶段再应用高度下限。当前没有地形接触/穿透的物理验证。

## 4. `mission`、`planner` 与观察规则

`mission` 的字段为：

| 字段 | 当前值或约束 |
|---|---|
| `intent` | `reconnaissance` |
| `objective` | `area_coverage` |
| `target_region_id` | 必须引用唯一共享矩形 |
| `coverage_required` | 0.01～1 的目标覆盖比例 |
| `return_required` | 严格布尔值；true 时要求回到各自生成点上方的准备高度 |
| `observation_model` | `type / radius_m / height_tolerance_m / grid_m / activation` |

观察模型仅支持 `type=ideal_horizontal_disk`、`activation=observe_phase_only`。水平半径、网格尺寸与高度容差必须为正；全局网格最多 10000 个单元。网格按矩形长度分别向上取整单元数，再均分为等面积单元，以单元中心判断覆盖。

`planner` 字段固定为 `name / partition_axis / assignment / lane_spacing_m / tracking_margin_m`：

- `name=equal_strip_lawnmower_v1`、`assignment=monotone_entry_order`。
- `partition_axis=east`：沿东西轴分成等宽条带，扫描直线沿南北方向。
- `partition_axis=north`：沿南北轴分成等宽条带，扫描直线沿东西方向。
- 根据生成点在分区轴上的顺序分配条带；相同坐标以稳定 agent ID 打破平局。输入车辆列表顺序不决定分配。
- 每个条带使用居中的等距往复扫描线，线数由条带宽度和 `lane_spacing_m` 决定；扫描间距不能大于观察直径。
- 区域和条带宽度必须大于两倍到达容差。不能为适配过小区域而自动降低安全间距。

责任区由公共区域划分。改变生成点会影响进入/返回路线和身份分配，不会把观察区变成围绕每架飞机生成点的局部矩形。

## 5. 安全预检、平台与预算

`platform` 只接受 `id=basic_multirotor_nominal_v1`，并显式提供 `max_speed_m_s / max_climb_rate_m_s / max_horizontal_accel_m_s2 / max_path_length_m / max_airborne_time_s / reserve_time_s / dynamics_validation`。当前 `dynamics_validation=execution_proxy_only`，不接受“已证明严格动力学可行”的要求。

规划器检查生成位置、进入、扫描、待机和返回的全部同阶段路径。它按两架飞机可以在各自线段上独立推进的最小几何距离检查，要求名义间距至少为 \(d_{\min}+2m_{\mathrm{tracking}}\)。这比假设两机同步匀速经过路径更保守。检查失败即拒绝，不自动寻找绕行，也不假设两机到达时刻恰好避开冲突。

名义路线长度包含进入、观察、可选返回，以及起飞/降落的垂直长度。名义阶段估计为 \(\max_i(L_i/v+h+d)\)，其中 \(h\) 为航点驻留，\(d\) 为额外确认驻留。总估计还计入准备时间、起飞爬升下界、30 s 稳定裕量和 30 s 降落裕量。后两项是明确列出的工程估计，不是经过校准的耗时上界。

每机名义完整路径不能超过 `max_path_length_m`；名义空中时间加 `reserve_time_s` 不能超过 `max_airborne_time_s`；整个时间估计不能超过 `timeout_s`。报告分别保存 `command_limits`、`nominal_budget`、`executed_limits`、`proxy_dynamics` 和 `unverified_constraints`。

AUTO 路线没有预定到达时刻，静态规划不证明加速度、转弯动力学或实际跟踪误差。实际轨迹另做边界、路径长度和航时检查；FCU 速度差分的加速度只是代理诊断，默认不作为未经校准的硬资格门槛。这里的航时限制是资源代理，不是电池模型。

## 6. `execution` 与阶段适配

| 参数 | 范围或含义 |
|---|---|
| `backend` | `AUTO` |
| `takeoff_alt_m` | 3～100 m，并位于世界飞行高度范围内；同时作为固定观察高度 |
| `speed_m_s` | 0.5～15 m/s，且不超过平台名义上限 |
| `waypoint_hold_s` | 0～60 s，AUTO 航点驻留 |
| `arrival_tolerance_m` | 0.2～5 m，独立几何到达容差 |
| `confirmation_dwell_s` | 0～60 s，额外连续几何确认驻留 |
| `record_hz` | 1～50 Hz |
| `max_gap_s` | 0.05～5 s，有效采样连接的最大间隔 |
| `min_separation_m` | 0.1～1000 m，基础间距阈值 |
| `timeout_s` | 10～3600 s，包含准备、任务和降落的整个运行期限 |
| `ready_timeout_s` | 10～300 s，准备阶段期限 |

每个执行阶段必须包含全部 agent；最多 100 个阶段。某架飞机在语义阶段的路线较短时，使用自身上一安全终点等待，并标记 `role=idle_padding`、`service_enabled=false`。等待点参加路径间距检查，但不会计作观察服务或新增工作量。

v2 起飞稳定和上传航段期间使用 BRAKE 保持；航段使用 AUTO，完成航点后继续由 AUTO 保持直到独立几何驻留确认完成。下一次上传再进入 BRAKE。该适配避免在当前 SITL 默认低油门条件下，屏障间切入 LOITER 导致高度下降。旧 v1 的 LOITER 行为保留。

`semantic_plan.execution_phases` 按阶段名保存 `semantic_phase`，以及每机的 `role / service_enabled / partition_id`。观察服务从本机该阶段的 AUTO 确认事件开始，以该机目标确认事件结束；缺少 AUTO 确认时使用已记录的发送事件并标明来源。提前到达后的 observe 阶段屏障等待和确认驻留可计入服务；确认结束后的调度等待、进入、返回和 idle padding 不计入服务。这是声明的虚拟服务开关，不是相机遥测或运动识别结果。

## 7. 实际验证、标签与数据资格

v2 对 SIM 真值和 FCU 观测分别运行相同几何规则。主 `mission_success` 来自 SIM，`mission_success_observation` 来自 FCU，`semantic_consistency` 为 `agree / disagree / unknown`。计划覆盖率仅是静态诊断，不作为实际成功标签。

在公共网格 \(G\) 上，以有效高度和观察服务窗口内的实际轨迹计算每机覆盖集合 \(U_i\)，全局覆盖为 \(|\bigcup_i U_i|/|G|\)。重复覆盖不累加；输出每机贡献、移除该机后的覆盖下降量和重复覆盖比例。

任务结果保留三值：有充分证据满足条件为 `true`；证据完整且条件未满足为 `false`；不足以确定为 `null`。已观察到覆盖达标时，即使另有缺口，覆盖子条件仍可为 true，但数据质量资格独立决定。返回要求还需要实际位置与连续驻留证据，命令事件本身不能证明成功。无效点、长缺口、超观察高度和服务关闭边界不会被插值重新连成覆盖线段。

`requested_intent` 始终保留任务指派；`planned_behaviors / planned_phases` 与实际几何结果分开。`split / merge / formation_change` 当前记为 `not_evaluated`。

数值质量策略继续使用 v0.2.2：时钟残差 strict ≤20 ms、acceptable ≤50 ms，默认集接受两者；缺少时钟证据为 unknown。默认资格还要求任务完成、观测/真值有效性、间距、生命周期资源检查和双通道语义一致通过。时钟残差不是绝对同步误差界。

生命周期检查使用解锁确认至落地的保守代理区间，和任务观测窗口分开；缺失生命周期不能默认为通过，已有违规证据仍能判失败。任务成功、运行 `completed` 与 `benchmark_eligible` 是不同字段。

## 8. 分析产物与兼容协议

每次分析建立新的 `analysis_v<代码版本>_*` 目录，保留原始 raw/BIN、metadata 和已有分析；`analysis_latest.json` 指向新分析。原始仿真版本与分析版本分别记录，历史记录不会因升级被改标。

v2 在原有 observations、truth、clock、labels、quality、task 等文件之外增加：

| 产物 | 内容 |
|---|---|
| `mission.json`、`shared_scene.json` | 任务条件、公共地图与平台 |
| `allocation.json`、`semantic_plan.json` | 名义分工、规划预检和阶段服务映射 |
| `phase_windows.json` | 每机实际事件窗口、屏障等待和调度等待 |
| `semantic_validation.json` | 两通道实际覆盖/返回及三值结果 |
| `execution_constraints.json` | 生命周期范围、路径/航时与代理动力学 |
| `lifecycle_clock_models.json` | 全生命周期的独立被动时钟拟合 |

清单记录产物与使用到的原始证据 SHA256。即使 BIN 因时间戳异常无法提供真值，该文件仍受来源哈希保护。重新分析也检查 `scenario.json` 与 `metadata.scenario` 一致。

数据集同时检查质量策略和 `task_kind / ontology_version / label_schema_version / semantic_validation_version / eligibility_protocol_version / execution_constraints_version`。不兼容协议必须分开导出；旧 v1 与新 v2 不静默混成同一标签任务。数据按 family 整组划分；小样本不保证恰好 70%/15%/15%。

`load_episode()` 返回未标准化的嵌套列表 `x[T,N,6]`、`mask[T,N]`、时间、agent IDs、独立 targets 和 metadata。六个输入特征固定为 ENU 位置/速度；任务、参考路线、SIM 真值和成功标签不会进入 x。缺失项填零但 mask=false；重复行、未知 agent、非法时间和非有限值被拒绝。

加载器按完整 episode 返回，不自动裁剪滑动窗口、不拟合归一化参数，也不训练识别模型。以后派生窗口仍须继承来源 family 和 split，不能把同一条轨迹的窗口重新随机划分。

## 9. 命令示例

在多机工程目录的 PowerShell 7 中执行；环境取自 `.conda-env`，当前为 `llm`。以下输出路径应尚不存在。命令展示的是已实现接口，不表示所有示例已经实跑通过。

```powershell
$EnvName = (Get-Content .conda-env -Raw).Trim()

# 只规划和验证，不启动 SITL。
conda run -n $EnvName --no-capture-output python main.py plan missions/recon_smoke_3uav.json --output scenarios/my_recon_v03.json
conda run -n $EnvName --no-capture-output python main.py validate scenarios/my_recon_v03.json

# 本机真实 SITL，自动记录、分析并回收本次拥有的进程。
conda run -n $EnvName --no-capture-output python main.py run scenarios/my_recon_v03.json --quality-policy quality_policies/default_v022.json

# 仅采样和预检；默认 profile 定义 100 个基础场景，每个最多 3 次候选。
conda run -n $EnvName --no-capture-output python main.py generate generation_profiles/recon_pilot_v03.json --output generated/my_recon_v03

# 在单任务闭环验证之后，顺序启动最多 3 次尝试；不自动运行整个清单。
conda run -n $EnvName --no-capture-output python scripts/run_mission_list.py generated/my_recon_v03/mission_list.json --max-runs 3 --quality-policy quality_policies/default_v022.json
conda run -n $EnvName --no-capture-output python scripts/run_mission_list.py generated/my_recon_v03/mission_list.json --max-runs 3 --quality-policy quality_policies/default_v022.json --resume

# 全部逻辑与回归测试。
conda run -n $EnvName --no-capture-output python -m unittest discover -s tests -v
```

生成输出包括冻结 profile、逐候选输入与拒绝原因、接受任务/编译场景、任务清单和哈希清单。变体继承 family，attempt 使用独立目录；失败不覆盖。恢复前校验输入、代码、固件、数值策略、已选分析和全部证据；目录存在不等于可以跳过。重试仅对显式配置的暂时性环境失败开放，不自动重试语义失败以筛掉失败样本。

每次调用最多执行 10 次尝试，`--max-runs` 包括重试次数。可以重复提供 `--mission-id` 从冻结清单选择一个子集；ID 必须存在且不重复，执行顺序始终按原清单。选择集写入执行上下文，`--resume` 必须再次提供相同 ID 集合。若要换选择集或代码，使用新的 `--output`；没有 `--mission-id` 时选择整份清单，但仍受本次尝试数限制。

```powershell
# ID 以实际生成清单为准；独立输出避免与上面的完整清单账本混用。
conda run -n $EnvName --no-capture-output python scripts/run_mission_list.py generated/my_recon_v03/mission_list.json --mission-id recon_0000_v00 --mission-id recon_0001_v00 --max-runs 1 --output generated/my_recon_v03/selected_execution
conda run -n $EnvName --no-capture-output python scripts/run_mission_list.py generated/my_recon_v03/mission_list.json --mission-id recon_0000_v00 --mission-id recon_0001_v00 --max-runs 1 --output generated/my_recon_v03/selected_execution --resume
```

```powershell
# 替换为真实运行目录；不同语义协议分别导出。
$RunA = 'runs/<实际运行目录>'
conda run -n $EnvName --no-capture-output python main.py analyze $RunA --quality-policy quality_policies/default_v022.json
conda run -n $EnvName --no-capture-output python main.py dataset $RunA --output datasets/my_recon_v03
conda run -n $EnvName --no-capture-output python main.py inspect-dataset datasets/my_recon_v03 --output datasets/my_recon_v03_audit.json
```

`inspect-dataset` 可附加 `--generation-manifest` 与 `--attempt-ledger`，使规划/执行通过率包含生成候选与未导出尝试；否则报告明确限定为已导出样本。只有一个任务类别时不报告分类准确率。

`run/batch` 的 0 表示通过资格门槛，1 表示执行或资格未通过；输入错误通常为 2。`analyze/dataset` 的 0 只表示操作成功，不能替代读取样本资格。`generate` 的 0 也不保证全部候选通过，应读取接受/拒绝计数。
