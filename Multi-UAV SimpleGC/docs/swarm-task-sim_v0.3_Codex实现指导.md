# swarm-task-sim v0.3：交给 Codex 的代码实现指导

> **执行目标：实现代码、测试和可核查产物，不是再输出一份方案说明。**  
> 将当前多机执行后端扩展为“一个共享区域任务 → 多机分工 → 实际轨迹 → 群级任务验证 → 数据集”的最小闭环。  
> 本轮只实现 `reconnaissance` 的**理想几何区域观察子任务**，不实现复杂战术行为或真实传感器探测。

- 文档日期：2026-09-30。
- 仓库：`shy-UCAS/swarm-task-sim`。
- 本文核对的 `main` 提交：`0ea70a2ae08cf76d2b34322fa47e466659a20bdf`。
- 当前工程版本：`0.2.2`；工作目录：`Multi-UAV SimpleGC/`。
- 不修改相邻的原始 `SimpleGC/`。
- 来源边界：第 1 节记录已读取源码支持的现状；后续接口、算法、测试与分期是**本轮拟新增的实现要求**，不是当前已有能力。
- 本文件编写时读取了仓库源码，但未在用户的 Windows 环境重新执行测试或 SITL。提交说明中的“63 项测试通过”是待 Codex 本地复核的基线，不是本文重新实测的结果。

## 0. 先执行这些规则

### 0.1 工作方式

1. 先阅读仓库及项目中的 `AGENTS.md`、`CLAUDE.md`、`.conda-env`，确认实际工作目录和 Python 环境。
2. 检查 `git status --short`、当前提交和分支。保留用户已有未提交修改，不执行破坏性恢复、清理、强制覆盖或强制推送。
3. 若本地提交不同于上述基线，先核对相关差异。保留已存在且正确的实现，不盲目重新写一套同名模块。
4. 先运行原有测试，再开始改动。区分既有失败、环境问题和本轮引入的回归。
5. 按本文里程碑依次完成；每步同时补测试、更新接口文档，避免先堆完整目录再发现调用链不通。
6. 默认只修改本地代码、生成隔离的测试和运行产物。不自动推送、创建远端 PR、打发布 tag 或删除旧证据。
7. 新命令、新函数和示例均须实际实现；最终报告不得把“计划新增”“静态检查通过”“模拟测试通过”写成“SITL 已运行通过”。

PowerShell 环境检查示例：

```powershell
# 从仓库根目录开始。先阅读实际存在的仓库级指引。
git status --short
git rev-parse HEAD
Set-Location 'Multi-UAV SimpleGC'
Get-Content AGENTS.md
$EnvName = (Get-Content .conda-env -Raw).Trim()
conda run -n $EnvName --no-capture-output python --version
conda run -n $EnvName --no-capture-output python -m unittest discover -s tests -v
```

环境缺失时报告阻塞，不静默改用 `base`。不要为本轮引入 ROS、Gazebo、飞控升级、强化学习框架或大型规划依赖。

### 0.2 测试与进程权限边界

只运行本项目管理器创建的本机 SITL 实例，不连接真实飞行器或任意外部飞控。故障注入只针对本轮创建的进程、临时输入和复制后的日志，不对原始运行目录做篡改测试，不按进程名称批量杀死所有 `arducopter`。

默认先做纯逻辑测试，再做少量本机 SITL 验证。不得直接启动上百个场景或多批并行仿真。Windows 二进制不能执行的环境，只完成可运行部分并明确标注集成验证阻塞。

---

## 1. 已核对的现状与真正需要补的缺口

以下均以本文固定提交为准。源码来源入口见文末。

| 位置 | 当前源码支持的事实 | 本轮应如何处理 |
|---|---|---|
| `swarm_sim/tasks.py::compile_task()` | 只接受 TaskSpec v1 的 `point_visit / rectangle_patrol / coverage_scan`；同一相对路线平移到每架飞机初始点 | 保留 v1；新增面向共享任务的 v2 编译分支 |
| `tasks.py::validate_task_binding()` | 通过重新编译 TaskSpec 与完整执行场景比较，防止任务/航点脱节 | 为新版本保留等价绑定检查，不能直接关闭 |
| `swarm_sim/scenario.py::validate()` | 执行场景 schema 为 1；1～6 机、1～100 个执行阶段；每阶段必须覆盖所有 agent | 复用该接口，不擅自扩机或放宽阶段限制 |
| `scenario.py::mission_for()` | 一个执行阶段对应速度命令和一个目标航点、驻留 | 新规划器最终必须适配此结构，不假定后端能直接执行任意路线列表 |
| `swarm_sim/runner.py::run_scene()` | 阶段并发释放、全机屏障；含 `task_spec` 时直接读取旧 `task_spec['task']` 的驻留规则 | 必须做版本分派；仅新增 JSON 文件会在这里断链 |
| `swarm_sim/evaluation.py::evaluate_task()` | `assigned_intent` 来自旧任务类型；覆盖率以每架飞机自己的局部矩形计算 | 新增群级几何任务验证，不直接改写旧标签含义 |
| `swarm_sim/analysis.py::analyze_run()` | 区分 FCU 观测与 BIN SIM 真值；当前任务验证只传入 FCU 轨迹 | 新任务增加双通道验证及清晰的主判据 |
| `swarm_sim/quality.py` | 分级时钟诊断、统一策略哈希、默认/严格合格集 | 冻结数值策略；不以放宽门槛使新任务“通过” |
| `swarm_sim/dataset.py::build_dataset()` | 校验来源和产物哈希，拒绝混合质量策略，按 `family_id` 划分；无训练加载器 | 保留防护；补新语义协议及最小加载器 |
| `swarm.py` | 已有 `plan / validate / run / batch / analyze / dataset / audit` | 优先扩展现有入口，避免再造一套运行命令 |

**当前是可审计的多机几何任务执行器，不是已经完成的高级意图 benchmark。** 本轮核心改动应集中在任务、规划、验证和数据接口；底层进程、消息接收、时钟与控制流程以复用为主。[S1–S8]

---

## 2. 本轮范围：先交付核心闭环，再交付小规模生成能力

### 2.1 A 阶段：必须先完成的四个工作包

- A1：语义层级、TaskSpec v2 及兼容规则。
- A2：共享场景结构、统一平台能力配置和有边界的可行性检查。
- A3：共享区域分区、单机路线生成、多机执行阶段适配。
- A4：群级覆盖验证、双通道证据、标签和数据导出接通。

A 阶段完成意味着：**一份手写的共享区域 MissionSpec 能完成真实的计划—执行—验证闭环。** 不是只完成四个模块的孤立单元测试。

### 2.2 B 阶段：A 通过后继续完成

- B1：确定性的场景生成器、任务清单、有限批处理与断点续跑。
- B2：最小数据加载器、小规模数据体检和发布前报告。

B 阶段完成意味着：不再手工逐份修改 JSON，就能生成多个独立场景族、保留失败、导出可读取的数据。

### 2.3 本轮明确收紧的边界

这些是把前面对话变成可实现任务时的范围约束：

- **1～6 机**：1 机用于退化测试，3 机作为主验证，6 机做少量扩展验证。不沿用对话中尚未支持的“3～8 机”。
- 一种同构多旋翼平台、公共地面海拔、固定观察高度、局部平面场景。
- 一个共享的轴对齐矩形观察区。支持东西/南北两种扫描方向；不做任意多边形覆盖。
- 最小流程先支持 `approach → observe → return`，其中返回可配置。`deploy / regroup` 可在词表中预留，但未实现时不得宣称发生了 `split / merge`。
- `restricted_regions` 只接受空集合。非空时明确拒绝并给出不支持的原因；不要在 schema 中接受后又忽略。禁区路径搜索下一阶段单独做。
- 继续 AUTO＋执行阶段屏障；不引入 GUIDED 高频目标流、主动 TIMESYNC 或物理锁步。
- 不实现六类意图、不训练分类模型、不调用 LLM、不做雷达/视觉探测、噪声/风场、在线重分配或闭环编队。

**只有一种任务时，分类准确率没有意义。** 本轮报告任务生成成功率、覆盖、数据质量、多样性和资源开销，不把单类别 100% 当作 baseline 结果。

---

## 3. 语义合同：目的、原语、计划和实际结果必须分开

### 3.1 本轮术语

| 概念 | 本轮定义 |
|---|---|
| Mission Intent | `reconnaissance`：在本文限定下，执行指定区域的理想几何观察任务 |
| Objective | `area_coverage`：覆盖给定共享区域达到阈值；可附加返回条件 |
| Task Primitive | 实现步骤，如到点、驻留、往复扫描；不是任务意图本身 |
| Planned Phase | 编排时指定的 `approach / observe / return` |
| Planned Behavior | 计划采用的行为，不等于实际观测证据 |
| Observed Behavior | 根据执行轨迹与明确判据计算出的事件；允许未知或未验证 |
| Mission Success | 实际轨迹是否满足任务完成条件，取 `true / false / null` |
| Benchmark Eligibility | 任务、数据、时钟、安全与本轮约束检查共同决定的样本资格 |

`reconnaissance` 只是任务指派的语义标签。几何覆盖验证只能证明**在声明的理想模型中完成了区域覆盖**，不能证明真实侦察探测率，更不能证明从轨迹唯一识别了隐藏战术意图。

### 3.2 标签规则

1. 保留 `requested_intent`，仿真失败时不能改成别的任务。
2. 分开保存 `planned_behaviors`、`observed_behaviors`、`planned_phases` 与实际执行时间窗口。
3. 路线被规划成覆盖，不代表覆盖成功；运行结束也不代表任务成功。
4. `split / merge` 不能从 JSON 配置直接复制为 `true`。本轮没有可靠几何检测器时，记为 `not_evaluated`，不得伪造。
5. “所有飞机前往同一个点”不是可接受的汇合实现。将来做 regroup 时，必须是安全区域内不同终点或间距合格的队形。
6. 命令阶段窗口是执行日志证据，不能冒充模型从轨迹推断出的行为边界。
7. 以后生成自然语言时，任务指令可以来自 MissionSpec，完成式描述必须来自实际验证结果。当前仅保留这些接口，不生成文本。

---

## 4. 向后兼容：保留旧 v1，新增 v2，不原地修改历史含义

### 4.1 推荐的分派方式

保留外部函数名 `compile_task(spec)`，内部按版本分派：

```python
# 拟新增结构示意，不是当前源码。
def compile_task(spec):
    if spec.get('schema_version') == 1:
        return compile_task_v1(spec)  # 保持现有输入、默认值和编译结果
    if spec.get('schema_version') == 2:
        return compile_shared_mission_v2(spec)
    raise ValueError('unsupported TaskSpec schema_version')
```

v2 编译结果仍使用现有执行场景 `schema_version=1`、`vehicles` 和 `phases`；任务来源保存在 `task_spec` 内，版本为 2。**任务格式版本和执行场景格式版本是两件事，不要求同时升级。**

新编译结果附加：

- `semantic_plan`：语义阶段与执行阶段的映射、每机任务角色和有效服务区间的计划定义。
- `planning`：算法版本、分区、每机路线、预检指标和未验证项。
- `family_id`：继承顶层任务族，不能在执行器中重新生成。

### 4.2 绑定检查

`validate_task_binding(scene)` 必须对 v1/v2 都生效：从保留的、规范化 TaskSpec 重新编译，比较所有影响执行、标签和验证的内容。

编译必须是确定性纯函数：不读取当前时间、不生成随机 UUID、不依赖 dict 的偶然顺序，不受机器绝对路径影响。随机采样只发生在生成器，并写成完整 TaskSpec 后再编译。

不能用以下“修复”绕过绑定：

- 删除新场景的 `task_spec`。
- 给 v2 填一个伪造的旧 `task.type=coverage_scan`。
- 只比 `task_id` 或仅比一份可同步篡改的 hash。
- 为了兼容新元数据，完全跳过重新编译比较。

### 4.3 历史数据

旧任务仍导出原来含义的 `assigned_intent`，不得把旧 `coverage_scan` 自动改标为 `reconnaissance`。v2 使用新标签 schema，并声明 `task_kind=mission_v2`。

旧运行的 raw、BIN、metadata、既有分析和数据集都不能覆盖。重新分析仍建立新目录。版本升级不等于修改历史标签真值。

---

## 5. 拟新增 TaskSpec v2：先固定一个完整可运行的示例

以下 JSON 是**本轮拟实现的接口示例**，不是当前 v0.2.2 可接受的输入。数值是初始开发配置，不代表已经验证过的飞行性能；Codex 必须实际编译、预检和运行后才能报告可用。

建议路径：`missions/recon_shared_3uav.json`。

```json
{
  "schema_version": 2,
  "task_id": "recon_shared_demo_3uav",
  "family_id": "recon_base_scene_demo_001",
  "seed": 42,
  "scenario": {
    "scene_id": "shared_rectangle_demo",
    "origin": {"lat": 30.0, "lon": 120.0, "alt_msl_m": 12.0},
    "world": {
      "east_bounds_m": [-100.0, 100.0],
      "north_bounds_m": [-100.0, 100.0],
      "flight_up_bounds_m": [3.0, 40.0]
    },
    "regions": [
      {
        "id": "R1",
        "type": "rectangle",
        "min_east_m": 0.0,
        "min_north_m": 0.0,
        "width_m": 54.0,
        "height_m": 30.0
      }
    ],
    "restricted_regions": [],
    "vehicles": [
      {"id": "uav_01", "sysid": 1, "east_m": 9.0, "north_m": -15.0, "heading_deg": 0.0},
      {"id": "uav_02", "sysid": 2, "east_m": 27.0, "north_m": -15.0, "heading_deg": 0.0},
      {"id": "uav_03", "sysid": 3, "east_m": 45.0, "north_m": -15.0, "heading_deg": 0.0}
    ]
  },
  "mission": {
    "intent": "reconnaissance",
    "objective": "area_coverage",
    "target_region_id": "R1",
    "coverage_required": 0.90,
    "return_required": true,
    "observation_model": {
      "type": "ideal_horizontal_disk",
      "radius_m": 4.0,
      "height_tolerance_m": 1.0,
      "grid_m": 1.0,
      "activation": "observe_phase_only"
    }
  },
  "planner": {
    "name": "equal_strip_lawnmower_v1",
    "partition_axis": "east",
    "assignment": "monotone_entry_order",
    "lane_spacing_m": 4.0,
    "tracking_margin_m": 1.0
  },
  "platform": {
    "id": "basic_multirotor_nominal_v1",
    "max_speed_m_s": 6.0,
    "max_climb_rate_m_s": 2.0,
    "max_horizontal_accel_m_s2": 3.0,
    "max_path_length_m": 1000.0,
    "max_airborne_time_s": 900.0,
    "reserve_time_s": 60.0,
    "dynamics_validation": "execution_proxy_only"
  },
  "execution": {
    "backend": "AUTO",
    "takeoff_alt_m": 8.0,
    "speed_m_s": 3.0,
    "waypoint_hold_s": 0.5,
    "arrival_tolerance_m": 1.0,
    "confirmation_dwell_s": 0.5,
    "record_hz": 10,
    "max_gap_s": 0.5,
    "min_separation_m": 5.0,
    "timeout_s": 1200.0,
    "ready_timeout_s": 90.0
  }
}
```

### 5.1 校验要求

对 v2 的各层对象递归校验允许字段，不能只查顶层。拒绝重复身份、未知区域、非有限数、布尔值冒充数值、空参与者、非法枚举、零面积、越界区域以及不支持的任务。

`world.flight_up_bounds_m` 是飞行高度范围，不用于判定地面生成高度为非法。公共原点及 MSL/ENU 约定继续复用现有实现。

`platform` 是统一平台的名义能力配置；`dynamics_validation` 明确声明哪些动力学约束只能做执行后代理检查。不要把登记了加速度上限写成“静态规划已经证明动力学可行”。

所有算法、观察模型和语义验证规则都记录稳定版本；改变语义时升级对应版本，不仅修改注释。

---

## 6. 模块组织：新增少量模块，避免大规模搬迁

推荐以下职责划分，文件名允许按实际工程小幅调整，但每个职责必须有唯一主要实现：

| 文件 | 拟实现内容 |
|---|---|
| `swarm_sim/mission_schema.py` | TaskSpec v2、ScenarioSpec、MissionSpec 的严格校验与规范化 |
| `swarm_sim/capability.py` | 名义平台能力、规划预算、执行后约束结果 |
| `swarm_sim/mission_planning.py` | 共享区域分割、单机路径、身份分配、执行阶段编译 |
| `swarm_sim/mission_evaluation.py` | 独立的共享区域验证、双通道结果、语义窗口 |
| `swarm_sim/generation.py` | 确定性采样、家族/变体记录、任务清单 |
| `swarm_sim/episode_loader.py` | 只读取白名单观测特征，输出序列与掩码 |
| `scripts/run_mission_list.py` | 有限顺序批处理、attempt 记录、断点续跑 |

尽量保持新增 Python 模块仍在 `swarm_sim/` 当前层级，减少现有源码哈希收集只遍历 `*.py` 带来的遗漏。确实新增子包时，必须同步升级源码溯源收集并补测试。

共享数值几何函数可以提取到一个小模块，但不要让验证器调用“规划器预计已经覆盖”的结果。允许共享坐标、距离等基础数学函数，不共享最终成功标签。

---

## 7. A1：Schema 与兼容接线

必须修改的真实入口不止 `tasks.py`：

| 入口 | 必须接通的行为 |
|---|---|
| `swarm.py::plan` | 同一个 `plan` 命令接受 v1 和 v2，写出当前执行场景 |
| `swarm.py::validate` | 校验执行场景及版本化任务绑定 |
| `runner.py::run_scene` 开始处 | 校验 v2 绑定，不能退化成无标签旧航点模式 |
| `runner.py` 阶段确认 | 不再无条件读取 `task_spec['task']`；根据 v1/v2 获取容差、驻留和当前阶段目标 |
| `runner.py` 输出资格 | v2 的语义验证/分析失败时，`usable` 与命令退出码必须失败 |
| `analysis.py::analyze_run` | 分派 v1/v2 验证，保存不同标签协议 |
| `dataset.py::build_dataset` | 识别语义协议，不把 v1 原语标签与 v2 任务标签混成一种分类标签 |

建议新增小型内部适配函数，例如 `get_target_confirmation(scene, phase, agent_id)`，返回本执行阶段的容差、确认驻留和角色。控制器只接收数值要求，不需要知道“侦察”含义。

保持 v1 编译结果不变；若提取原语路径函数，必须通过历史 TaskSpec 编译结果快照回归。

**A1 验收：** 原有测试通过；v2 合法输入可规范化；v2 非法输入明确拒绝；v1 行为未改变；新字段没有仅被保存而未参与下游。

---

## 8. A2：能力、地图与预算检查

### 8.1 必须实施的检查

- 共享区域、生成位置及计划航点位于声明的世界边界内，并满足执行后端局部范围限制。
- 指令速度不超过平台名义速度上限，也不超过现有执行接口的范围。
- 名义每机路线长度包含进入、覆盖和返回，不仅计算覆盖条带。
- 时间预算包含全机屏障等待、航点驻留、额外确认驻留、起飞准备和降落开销的明确估计。
- 起点、执行阶段路径及待机点满足声明的最小间距预检。
- 超限、无法分区或超过 100 个执行阶段时，规划失败并报告具体原因。
- 时间、路径预算超过平台约束时不得偷偷提高能力值、减小安全间距或放宽覆盖阈值。

### 8.2 三种数值不能混淆

1. **名义路线长度**：根据参考航点计算，不是实际飞行距离。
2. **名义时间下界/估计**：基于指令速度、驻留和屏障建立，不是可执行证明。
3. **执行后结果**：由实际记录计算的飞行长度、时间、观测速度及代理加速度。

每个执行阶段的时间估计至少考虑：

```text
阶段耗时估计 = max_i(该机航段长度 / 指令速度 + 航点驻留 + 确认驻留)
整个任务估计 = 各阶段估计之和 + 生命周期开销估计
```

加速、转弯、控制响应和通信开销使实际值不同。若给出额外经验裕量，明确记录来源和数值，不将它称为严格上界。

### 8.3 加速度与续航的边界

当前 AUTO 参考没有逐点到达时刻，不能对一个不存在的 `p_ref(t)` 计算加速度并声称满足约束。

本轮可以用 FCU 速度变化计算**执行后加速度代理量**，但必须记录采样、缺口、时基、差分方法；不跨异常屏障或长缺口，不把它说成 SIM 真值加速度。数据不足时返回 `not_verified`。

将能力报告至少拆成：

```text
command_limits          指令/范围检查
nominal_budget          路径与时间预算检查
executed_limits         可从实际数据检验的约束
proxy_dynamics          代理动力学诊断
unverified_constraints  尚未证明的约束
```

`max_airborne_time_s` 是本轮资源代理约束，不是电池电化学模型；飞行半径、累计航程和航时不是同一个量。保留返程与资源余量，不把单程可达误认为任务可完成。

本轮默认不将未经校准的差分加速度阈值作为合格样本硬门槛；如任务要求“已证明严格动力学可行”，应明确拒绝该要求，而不是报告通过。

**A2 验收：** 每个受支持约束有调用位置、失败路径和测试；每个尚未验证的约束明确列出；静态报告不能出现无依据的 `fully_feasible=true`。

---

## 9. A3：共享区域规划器与 AUTO 适配

### 9.1 正确的输入输出

输入是一个公共区域 `R` 和 N 架飞机，不是 N 个围绕初始点的小矩形。

```text
Mission: observe R
  → 把 R 分成责任区 R1...RN
  → 将责任区分配给具体 agent
  → 为每架机生成进入、扫描、返回路线
  → 编译成现有 AUTO 执行阶段
```

责任区来自共享目标区域。无人机初始点只影响任务分配与进入/返回路线，不能继续用 `spawn + same_route_offset` 定义所有观察区。

### 9.2 最小分区与分配算法

1. 按 `partition_axis` 将矩形划为 N 个等宽条带，保存每个条带的公共 ENU 边界。
2. 检查条带面积为正、无内部重叠、并集等于共享区域。浮点边界使用明确容差。
3. 根据条带入口的横向顺序和飞机起点的对应顺序做单调匹配；用稳定 agent ID 打破平局。不以 Python 输入顺序暗中决定任务。
4. 为条带生成往复扫描路线，支持东西/南北两种方向。
5. 从每机初始位置生成进入段；需要返回时，回到本机独立返回点。本轮默认返回到各自生成点上方的准备高度，再由旧后端 LAND。
6. 预检进入、覆盖、返回及等待位置的全部机间间距。拒绝会产生冲突且当前规划器无法解决的样本，不临时引入复杂避碰。

“等宽条带＋单调分配”是本轮规则基线，不要求最优任务分配。

### 9.3 覆盖几何与安全间距不能互相破坏

不能机械地在每个条带边界留一个巨大安全空白，再仍然宣称可覆盖 90%。扫描间距、观察半径、条带宽度、边缘覆盖与多机间距必须共同预检。

至少保存：名义全局覆盖率、最小阶段路径间距、各机路径长度和执行阶段数量。名义覆盖率用于规划检查，**不能作为执行后覆盖标签**。

共用边界本身不代表同一时刻撞机；但当前没有精确到达时间，因此优先采用保守的同阶段路径间距检查。检查不通过时拒绝并解释，不以任意时间插值假定两机不会同时到达。

`tracking_margin_m` 用于显式扩大名义规划所需间隔，例如要求名义间距至少为 `min_separation_m + 2 × tracking_margin_m`。这只是规划裕量，不能保证真实跟踪误差永远小于该值；执行后仍检查实际间距。

### 9.4 不同飞机航点数不同时，怎样兼容旧屏障

现有执行器要求每个执行阶段都有每架机的一个目标。适配器应：

- 按语义阶段组织每机路线，再以执行步索引编译。
- 某架机在该语义阶段的路线较短时，在经过安全预检的终点驻留等待，而不是删除该 agent、放置空目标、复制另一架机的终点或跳过屏障。
- 给等待目标记录 `role=idle_padding`，不把这些填充阶段算作新的扫描服务、访问任务或有效工作量。
- 对活动航段和等待点一起检查安全距离；返回阶段也不能跨过仍在等待的邻机。
- 每个执行阶段仍使用唯一名字，如 `leg_000`；语义映射独立保存在 `semantic_plan` 中。
- 超过现有 100 阶段限制时拒绝该方案。不要靠偷偷修改 `scenario.py` 上限通过。

保留并量化当前“每航点停留＋全机屏障＋额外确认”的控制特征，例如记录等待总时长和填充阶段数。这些可能成为数据捷径，不能被解释为自然形成的群体协调。

### 9.5 路径原语复用

可以从旧 `compile_task()` 中提取纯路径生成函数，或新增共享路径工具，但必须确保 v1 输出不变。不要通过调用完整旧任务编译器、再手工篡改其坐标或 `task_spec` 来模拟新任务。

### 9.6 计划与验证产物

`planning` 至少包含：

```text
planner_name / planner_version
allocation_method
region_partitions
agent_to_partition
per_agent_reference_routes
semantic_to_execution_phase_map
nominal_global_coverage
per_agent_path_length_m
nominal_time_estimate_s
nominal_min_clearance_m
idle_padding_steps
feasibility_checks
unverified_constraints
```

计划元数据禁止作为未来轨迹模型的输入。

**A3 验收：** 改变共享区域的位置，所有对应路径一起迁移；只改变某架机的生成点，不会把其责任区迁移到别处；路线真正由区域分解得到；编译结果可直接交给现有 `run`，无需人工改 JSON。

---

## 10. A4：群级任务验证器

### 10.1 全局覆盖率的定义

在共享区域 R 建立**统一的一套网格中心**。网格只定义一次，不能由各机分别建立后平均。

对满足高度、有效性和观察激活条件的实际轨迹，以固定半径圆盘及允许的相邻采样线段近似，计算每架机覆盖的网格集合 `U_i`：

```text
U_all = union(U_1, U_2, ..., U_N)
global_coverage_ratio = len(U_all) / total_grid_cells
```

对矩形使用等面积单元中心，报告网格分辨率、单元数和观察模型版本。以后改非均匀网格时必须改成面积加权；本轮不扩展。

禁止使用：

- 各机 coverage_ratio 的简单平均代替全局并集。
- 覆盖次数相加而不去重。
- 名义参考路线代替实际执行路线。
- 通过 `phase_finished` 或 `task_target_verified` 直接判定覆盖成功。

至少输出每机覆盖、全局覆盖、重复覆盖单元比例、各机移除后的全局覆盖下降量、参与观察的飞机数。最后两项是诊断，不默认要求每架贡献相同。

### 10.2 观察窗口与缺失证据

本轮观察模型只在声明的 `observe` 服务区间激活。进入和返回阶段不会因为偶然经过目标区而自动计入任务覆盖。

根据执行事件和 `semantic_plan` 构造**每机实际服务窗口**；未开始、未完成、等待填充等情况明确处理。窗口来源标为 `execution_events + compiled_semantic_plan`，不称为从运动中识别出来的阶段。

沿用 v0.2.2 的异常样本屏障和长缺口规则：

- 无效位置不参与覆盖。
- 超出高度容差不参与覆盖，并中断该段有效连接。
- 不跨缺口、异常点或服务关闭窗口连接线段。
- 若窗口边界在采样之间，只允许在已有有效、同一证据段内截取；不能跨缺失段补齐边界。
- `idle_padding` 不额外算一条服务航段。

虚拟观察激活是生成系统的已声明规则，不是实际相机开关的遥测。未来跨任务比较时，不应只改变隐藏激活状态、保持完全相同的可见轨迹，却要求轨迹模型唯一推断不同标签。

### 10.3 真值侧主判据与 FCU 侧复核

**本轮新增设计：** v2 的几何任务主判据使用已对齐的 SIM 真值位置；FCU 位置运行同一验证器作为观测侧复核。v1 保留原来依据 FCU 位置的判据。

建议保存：

```text
mission_success                 v2 真值侧任务结果
mission_success_observation     FCU 观测侧结果
semantic_consistency            agree / disagree / unknown
mission_metrics.truth
mission_metrics.observation
label_provenance
```

若真值缺失，不能回退 FCU 后仍写 `basis=SIM_truth`。观测侧可以单独得到结果，但真值侧必须是 `null`，默认数据集不纳入。

SIM 位置来自现有 BIN SIM 通道；不要求本轮补真值速度。真实与观测侧共用几何规则，却分别读取对应轨迹，不能把一侧结果复制为另一侧。

### 10.4 成功与未知的逻辑

任务结果按预先声明的任务条件判断：

```text
coverage_success = 全局覆盖达到阈值
return_success   = 未要求返回，或各机返回条件有实际证据满足
mission_success  = 三值逻辑 AND(coverage_success, return_success)
```

对于覆盖这个单调累计量，已有有效证据达到阈值，可以支持覆盖成功，即使另有缺失；但整体数据质量仍可能不合格。覆盖未达阈值且有可能影响结论的缺失证据，返回 `null`；完整证据下未达阈值才返回 `false`。

同一时刻一个明确失败和另一个未知条件并存时，整体条件已经失败；不能因为存在未知而掩盖已知失败。

**单机漏扫、另一机补上时，群级覆盖可成功。** 不要求每架都走完规划器原先分给它的所有扫描航点。每机执行状态、局部覆盖和偏离情况作为诊断保留。

运行状态、任务完成和样本资格继续分离：任务覆盖达标但降落失败，可能 `coverage_success=true`，但默认 `benchmark_eligible=false`。

### 10.5 安全、资源与样本资格

保留原 `quality.eligibility()` 的基础门槛，再对 v2 增加明确的附加门槛：

```text
v2_eligible = 既有默认合格条件
              AND 新任务几何验证成功
              AND 真值/观测语义复核一致且成功
              AND 本轮声明为硬约束的世界边界、路径/时间资源检查通过
```

`strict_benchmark_eligible` 仍是默认合格集的子集，不用新规则放宽时钟要求。

任务语义验证和安全/资源检查分别保存，不能为了复用一个布尔值而隐藏失败原因。动力学代理诊断若未被定义为硬门槛，写明其未纳入资格判断；不得声称全部物理能力约束已经被验证。

世界边界及完整航时检查需要准备到降落的证据，不能只用目前截出的第一航段到最后航段窗口充当“全程”。可以从现有 raw/BIN/events 计算；证据不足明确未知，不强求扩大模型输入窗口。

### 10.6 不伪造执行行为标签

本轮最低要求是：保存编排阶段、实际服务窗口、覆盖证据、返回证据以及成功状态。

不强制输出 `split / merge / formation_change=true`。未实现的行为检测器保持空结果或 `not_evaluated`；这比从计划直接复制更正确。Schema 可以预留行为记录格式：

```json
{
  "name": "coverage",
  "agent_ids": ["uav_01", "uav_02", "uav_03"],
  "status": "verified",
  "evidence_basis": "SIM_truth_positions",
  "rule_version": "shared_coverage_v1"
}
```

上面是格式示意，`verified` 必须由实际结果填入。

**A4 验收：** 对手工构造的互补覆盖、重复覆盖、缺证据、未达阈值、返回失败和双通道不一致样本，结果全部符合上述定义；新真实运行能导出独立语义验证结果。

---

## 11. 版本、manifest 和数据集兼容

### 11.1 版本不得只改 README

本轮涉及几类独立版本：

- 工程代码版本：开发中可用 `0.3.0-dev`；完成验证后再统一为 `0.3.0`。
- TaskSpec：旧 v1、新 v2。
- 执行场景 schema：仍复用 1。
- 语义标签 schema 与 `ontology_version`：为 v2 明确新增。
- `semantic_validation_version` 与 `eligibility_protocol_version`：记录新验证/资格逻辑。
- 数值 `quality_policy`：保持 v0.2.2 默认内容及哈希，除非另行明确改变规则。

同一个质量策略哈希，不等于标签协议、评估上下文或分析算法全部相同。本轮必须把这些维度写清楚，不能仅凭 policy hash 宣称不同任务或版本可直接比较。

### 11.2 拟新增产物

在新的分析目录中，建议增加：

```text
mission.json                 规范化任务目标与观察模型
shared_scene.json            公共区域、平台、初始条件
allocation.json              规划器的责任区与角色分配
semantic_plan.json           编排阶段到执行阶段的映射
semantic_validation.json     真值/FCU 两侧的任务证据和三值结果
execution_constraints.json   世界边界、资源与代理动力学检查
phase_windows.json           实际窗口与边界来源
```

这些文件都纳入 `manifest.artifact_sha256`；任务源、编译结果和生成配置纳入来源记录。

现有 `observations.csv` 的六个位置/速度特征和掩码契约尽量不变。新增语义只进入标签与辅助文件，不能混入观测列。

### 11.3 数据集协议

- 继续先验证所有输入，再创建数据集目录；不能以“尽量导出”为由静默跳过损坏样本。
- v1/v2 的 label schema 或 eligibility protocol 不兼容时，明确拒绝混合导出，提示分开导出。不要偷偷给旧样本补高级意图。
- 同一协议下，任务的覆盖阈值、目标大小等可以不同，但必须在每条样本的 evaluation context 中可追溯。若研究比较要求它们固定，由预先定义的数据集 profile 检查。
- 失败/未知样本全部留存，默认训练集合通过资格字段过滤；失败重试不能覆盖原尝试。
- `analysis_latest.json` 仍保留，但正式导出记录所选分析目录和 manifest 哈希。后续重分析不应静默改变已经导出的数据集。

---

## 12. B1：确定性的共享场景生成器

### 12.1 生成器只做已支持的事情

A 阶段通过后，增加 `generate` 子命令。建议接口：

```text
python main.py generate <generation_profile.json> --output <new_directory>
```

生成器根据 profile 的 `master_seed` 和场景索引创建局部随机源，不使用全局随机状态。输出完整 TaskSpec v2、编译场景和清单；输入相同、生成器版本相同，应得到相同规范化内容。

第一版随机化：2～6 机、共享矩形的位置/大小、起点间距与进入侧、扫描轴、允许范围内的速度、是否返回。优先保持路线对该后端可执行，不追求任意随机布局。

本轮不生成带禁区、异构能力、在线补位或未支持意图的样本。

### 12.2 家族、场景与模板不要混成一个概念

```text
base_scene_id       一次独立采样的基础场景实例
family_id           该基础场景及其派生版本共用的分组标识
variant_id          同基础场景的旋转、参数改写等派生编号
planner_template_id 路线生成策略/模板版本
attempt_id          同一任务的一次执行尝试
```

同一基础实例的重试、语言改写、噪声版、派生窗口和未来反事实分支继承 `family_id`；不能按每次运行 UUID 重新分组。

**不要把所有 `equal_strip_lawnmower_v1` 样本都放进一个 family。** 模板留出是另一种评测维度，应单独用 `planner_template_id` 管理。

`family_id` 可由生成器版本、master seed 和基础场景索引确定；同时保存基础场景的规范化哈希。它只防止已知派生关系泄漏，不能宣称自动识别所有语义近重复。

### 12.3 失败与重采样

预检失败保留候选参数、拒绝原因和候选编号；限制每个基础场景最多尝试次数。不要无限采样直到成功，也不要仅保留“飞成的漂亮轨迹”。

区分：

- 生成候选被规划拒绝。
- 同一编译任务的 SITL 执行失败。
- 分析失败。
- 语义失败。
- 数据门槛失败。

执行重试必须使用同一任务，保持 family 和输入哈希不变。改了输入再尝试是新变体，不是同一次 retry。

### 12.4 小规模顺序批处理

新增任务清单执行脚本，复用 `run_scene()`；不要改变现有 `batch --repeat` 的含义。

每条清单任务保存输入哈希、状态、attempt 列表、输出目录和失败原因。先提供顺序执行、手动恢复和有限重试，不实现多组 SITL 场景并行。

恢复时验证成功结果的 manifest，匹配输入及执行配置后才跳过；不能只看“目录存在”或一个 SUCCESS 字符串。质量策略变更也不能继续把旧资格结论当作本次结论。

默认不自动重试语义/规划失败。可重试的环境失败限定次数，每次独立目录并保留失败；达到预算后停止并报告。

---

## 13. B2：最小数据加载器和体检

### 13.1 加载器接口

建议新增 `load_episode()`，用标准库即可先返回规则的嵌套列表；没有必要为数据整理立即引入训练框架。

```python
# 拟新增返回约定。
{
    'x': ...,              # [T, N, 6]，顺序固定为 ENU 位置/速度
    'mask': ...,           # [T, N]
    't_s': ...,            # [T]
    'agent_ids': ...,      # [N]，仅作为索引映射
    'targets': ...,        # 与 x 分离的监督目标
    'metadata': ...        # family/split/来源等审计信息
}
```

只从 `observations.csv` 白名单列构造 `x`。不能把 task、truth、reference、目标分配、执行阶段名、成功标记、文件名或 ID 编码拼进观测特征。

检查重复 `(t_s, agent_id)`、非单调时间、未知 agent、特征列缺失与异常数值。缺失项可以填零用于容器表示，但必须 `mask=false`，不得把零值伪装成有效位置。

默认返回未标准化数据；以后训练时只用训练集拟合归一化参数。滑窗不是本轮强制要求；实现时必须从已经分配 split 的整条 episode 派生，不重新划分。

### 13.2 数据体检指标

输出机器可读汇总，至少包含：

- 独立基础场景/家族数、attempt 数、各 split 的家族和样本数量。
- 规划通过率、执行完成率、语义通过率、默认/严格资格率，各自明确分母。
- 全局覆盖率、每机覆盖贡献、重复覆盖、路径长度、任务耗时、阶段数和屏障等待分布。
- 观测/真值有效比例、时钟诊断分级、间距与约束失败原因。
- 无人机数量、矩形尺寸、扫描轴、起点布局、速度、返回选择等多样性统计。
- 重复规范化输入、同族跨 split 检查、近似模板集中度的简单诊断。

单一 `reconnaissance` 不做多类分类准确率。当前体检集也不能证明轨迹中存在足够高级语义；后续至少加入另一任务及反捷径对照才开始识别实验。

### 13.3 批量规模分三级

1. **逻辑层：** 默认生成约 100 份候选任务，完成编译/预检，不启动 SITL。
2. **集成层：** 先运行少量 2/3/6 机任务及重复场景，核对完整闭环。
3. **数据试生产：** 集成通过后执行约 10 个独立场景，再决定是否扩到 100～200 个。首次不能直接自动启动 100～200 次实跑。

稳定哈希不保证小数据集刚好 70%/15%/15%。不通过反复改变 split salt 或替换种子来美化划分；如需固定划分清单，应在训练前发布并冻结。

---

## 14. 必须新增的测试矩阵

测试不以数量充数。每个测试要有独立预期，不能只断言结果对象非空、再拿被测函数的输出作为标准答案。下面的编号在最终报告中逐项给出 PASS / FAIL / NOT_RUN。

| ID | 测试 | 预期 |
|---|---|---|
| C01 | 原有 v1 三类任务编译回归 | 规范化结果与基线一致，不被新任务语义污染 |
| C02 | v1 原有全部逻辑测试 | 通过；环境阻塞单独报告 |
| C03 | v2 合法配置 | 得到确定性规范化输入和执行场景 |
| C04 | v2 各层未知字段、NaN/Inf、bool 数值、非法枚举 | 在进入 SITL 前拒绝 |
| C05 | 非空禁区、未知目标区域、重复 agent/sysid | 明确拒绝，不能静默略过 |
| C06 | 修改编译后的航点、分区、区域或语义映射 | 绑定校验失败 |
| C07 | 重复编译、输入 dict 顺序改变 | 相同语义输入得到相同规范化结果 |
| P01 | N=1/2/3/6 的矩形分割 | 正面积、无内部重叠、并集等于 R |
| P02 | 平移共享目标区域 | 责任区和覆盖路线按共享区域迁移 |
| P03 | 单独改变无人机生成点 | 不把共享目标区域变成该机局部区域 |
| P04 | 打乱 vehicles 顺序 | 分配可解释且确定，不依赖列表偶然顺序 |
| P05 | 东西/南北两扫描方向 | 路线均有合理名义覆盖；方向变化不改变任务标签 |
| P06 | 不同路径长度、终点驻留填充 | 每执行阶段包含全部 agent；idle 不伪装成服务 |
| P07 | 进入/返回路径交叉、等待点危险 | 拒绝或明确规划失败，不靠执行时运气 |
| P08 | 过小区域、过细扫描导致超过阶段上限 | 明确拒绝，不放宽后端限制 |
| P09 | 指令速度超限、路径/时间预算超限 | 在静态检查时拒绝 |
| P10 | 平台加速度字段存在但无时间参考 | 报告代理/未验证范围，不宣称静态证明通过 |
| V01 | 两机各覆盖互补的一半 | 各自约 50%，全局约 100% |
| V02 | 两机重复覆盖同一半 | 全局仍约 50%，不能相加成 100% |
| V03 | 一机局部未完成、另一机补齐全局 | 群级覆盖成功；局部诊断仍如实记录 |
| V04 | 全部输入只有计划路线，无实际执行证据 | 不能验证成功 |
| V05 | 实际轨迹完整，但覆盖低于阈值 | `mission_success=false`，或明确 coverage 子条件失败 |
| V06 | 阈值未达且缺失关键区间 | `null`，不能跨缺口补成功 |
| V07 | 已有有效覆盖达标，但另有数据缺失 | 覆盖子条件可 true；数据资格独立判定 |
| V08 | 超高度、服务未开启、idle padding | 不计入观察覆盖 |
| V09 | 子网格异常点、长缺口、窗口跨边界 | 不被重采样重新连接成有效覆盖/驻留 |
| V10 | 返回要求 true，但未回到本机返回点 | 任务失败或证据不足；不能因覆盖达标直接通过 |
| V11 | 仅命令/确认事件存在，无位置证据 | 不得自动宣判几何成功 |
| V12 | SIM 与 FCU 轨迹故意产生不同结果 | 分别输出，`semantic_consistency=disagree`，默认集排除 |
| V13 | SIM 缺失，FCU 完整 | 真值侧未知，不冒充独立真值验证 |
| V14 | 改变网格分辨率的简单可手算区域 | 结果符合声明的离散模型，报告分辨率影响 |
| D01 | 新语义文件/任务来源被修改 | manifest/绑定检查能拒绝 |
| D02 | 重试和派生变体 | family 不变，attempt 独立，失败不覆盖 |
| D03 | v1 原语与 v2 mission 不兼容协议混合导出 | 明确拒绝或按明确配置分开，不静默重标 |
| D04 | 不同 quality policy 混合 | 保留现有拒绝行为 |
| D05 | 任务输入相同而语义验证版本不同 | 记录版本；不把不同结果悄悄当作同一协议 |
| D06 | 加载器接收含标签/真值的目录 | x 仅来自允许的观测列 |
| D07 | 重复行、缺 agent、非法时间、无效值 | 明确报错或按约定 mask，不静默生成有效样本 |
| D08 | 同族的失败、重试、窗口、变体 | split 一致，不以 run_id 重新切分 |
| B01 | 相同 profile/seed 重复生成 | 规范化任务相同；运行 UUID 可不同 |
| B02 | 有限候选采样失败 | 记录拒绝原因并结束，不无限循环 |
| B03 | 批处理人工中断后恢复 | 已验证成功条目不重跑；未完成条目可恢复 |
| B04 | 目录存在但产物不完整/哈希损坏 | 不当作成功跳过 |
| B05 | 只生成一个 mission 类别 | 不输出无意义的分类准确率 |

### 14.1 独立验证器的最低测试要求

V01/V02/V03 必须使用手工构造且预期可计算的轨迹或覆盖集合，不通过运行同一个规划器生成“正确答案”。增加至少一个“运行 completed 但语义失败”的案例，防止成功判据被进程状态替代。

### 14.2 真实 SITL 最小矩阵

在纯逻辑测试通过后，用本地可用环境执行：

| 场景 | 最小目的 |
|---|---|
| 3 机共享区域观察＋返回 | 证明新任务到数据导出的主调用链接通 |
| 相同 3 机输入再运行一次 | 检查初始化、运行隔离、family 和进程回收 |
| 不同扫描轴的 2 机任务 | 检查不是只硬编码一个 demo |
| 小区域 6 机任务 | 验证现有规模范围内的新适配；不可运行时明确 NOT_RUN |
| 一次受控失败 | 验证超时/分析失败/资格失败不会被静默变成成功 |

对每次运行记录任务/场景哈希、代码版本、固件证据、运行 ID、耗时、覆盖、双通道一致性、质量等级、退出码和进程清理结果。

1 次成功只证明该场景可运行，不写成“稳定支持任意布局”。预检失败也应保留；不能通过关闭飞控检查或篡改验证阈值获得通过。

---

## 15. 实施顺序与每步交付物

### M0：建立基线，不新增功能

交付 `docs/v03_baseline_check.md`：当前提交、工作区状态、原有测试实测、环境与可运行边界。若与本文基线不同，列出差异。

### A1：语义 Schema 与版本分派

建议提交主题：`feat(ontology): add mission TaskSpec v2 with legacy compatibility`。

交付 v2 校验、示例、v1/v2 分派、绑定回归、schema 文档。此时可以尚不实飞，但不能假装任务已执行。

### A2：共享场景与能力检查

建议提交主题：`feat(scenario): add shared regions and scoped capability checks`。

交付公共地图、统一平台能力、预算报告和明确未验证项。先用纯逻辑测试验证范围与拒绝行为。

### A3：共享区域规划和执行适配

建议提交主题：`feat(recon): compile shared-area allocation to AUTO phases`。

交付等宽分区、单调分配、扫描路径、填充等待、全路线预检，以及 `runner` 对 v2 的正确接线。运行一个小型共享任务确认控制链路。

### A4：群级任务验证和数据闭环

建议提交主题：`feat(validation): add shared coverage evidence and mission dataset export`。

交付真值/FCU 双通道验证、三值语义、附加资格门槛、版本化产物和防泄漏/防篡改测试。完成主真实 SITL 验证。

**A 阶段退出条件：** 不靠手改航点、标签或 quality，单个共享任务能一键计划、执行、验证和导出。若 A 不通过，不进入批量生成。

### B1：生成器和有限清单运行

建议提交主题：`feat(generator): add deterministic mission families and bounded batch execution`。

交付 generation profile、任务/场景清单、候选拒绝记录、有限运行、attempt 账本和恢复功能。

### B2：加载器、体检和最终验证

建议提交主题：`feat(dataset): add observation-only loader and v03 pilot audit`。

交付加载器、体检报告、完整测试结果和发布说明。先小规模试生产，再讨论扩大数据量。

上述主题是建议的本地开发单元，不要求自动进行 Git 提交或推送。若本次执行预算不足，停在完成的里程碑，逐项列出未做内容，不写“v0.3 已完成”。

---

## 16. CLI 与示例文档要求

以下命令是本轮应接通或新增的目标接口。实现后用真实输出更新 README；**当前代码未实现的命令不能只写进文档。**

```powershell
$EnvName = (Get-Content .conda-env -Raw).Trim()

# 已有 plan 入口扩展支持 TaskSpec v2。
conda run -n $EnvName --no-capture-output python main.py plan missions/recon_shared_3uav.json --output scenarios/recon_shared_3uav_v03.json
conda run -n $EnvName --no-capture-output python main.py validate scenarios/recon_shared_3uav_v03.json

# 继续通过已有执行入口；数值质量策略明确指定。
conda run -n $EnvName --no-capture-output python main.py run scenarios/recon_shared_3uav_v03.json --quality-policy quality_policies/default_v022.json

# 拟新增：仅生成和预检，不自动启动 SITL。
conda run -n $EnvName --no-capture-output python main.py generate generation_profiles/recon_pilot_v03.json --output generated/recon_pilot_v03

# 拟新增脚本：限制本次真实仿真条数，默认顺序执行。
conda run -n $EnvName --no-capture-output python scripts/run_mission_list.py generated/recon_pilot_v03/mission_list.json --max-runs 3

# 拟新增：续跑前校验既有成功证据。
conda run -n $EnvName --no-capture-output python scripts/run_mission_list.py generated/recon_pilot_v03/mission_list.json --max-runs 3 --resume

# 原有测试入口保留。
conda run -n $EnvName --no-capture-output python -m unittest discover -s tests -v
```

`analyze / dataset` 继续支持已有运行目录；新增 v2 信息随版本化分析导出。说明 `run` 成功、`analyze` 操作成功和样本合格分别是什么意思，保持已有退出码概念，不把分析一个失败场景的操作成功写成任务成功。

`generate` 输出清单要包含候选总数、接受数、拒绝数及原因；部分候选被拒绝不一定是程序故障，但不能无提示少生成数据。

---

## 17. 必须避免的实现偏差

1. **仅把 `coverage_scan` 改名为 `reconnaissance`。** 必须真正以公共 R 分配责任区、验证全局并集。
2. **重写底层而没有共享任务。** 不为本轮重构 MAVLink、飞控固件、时钟或进程体系。
3. **新 TaskSpec 有了，runner 仍只读旧 `task` 字段。** 必须端到端追踪版本分派。
4. **独立规划 N 条路线，没有联合检查。** 进入、扫描、等待、返回都要校验机间路径关系。
5. **所有无人机汇到同一坐标。** 本轮返回必须使用各自独立位置。
6. **共享覆盖取各机比例平均。** 必须统一网格做并集去重。
7. **复制计划为实际行为。** 计划和观测结果分字段保存，不伪造 split/merge。
8. **把名义能力登记当成可行性证明。** 静态、执行后代理、尚未验证的部分明确分开。
9. **改阈值把失败变成成功。** 失败保留；规则变动先版本化和说明，不临时改完只报通过。
10. **只存通过样本。** 候选拒绝、执行失败、分析失败和语义失败都有账本。
11. **所有同类任务共用一个 family。** 家族是同源基础实例，不是任务类别或规划器模板。
12. **每个 retry/window 生成新 family。** 派生样本必须继承原 family。
13. **先生成几千条再做加载器。** 少量端到端产物先验证可被读取、无隐含标签输入。
14. **用一类任务的分类准确率证明数据有效。** 本轮只做数据与任务体检。
15. **把独立 SITL＋统一时钟说成物理锁步或实时分布式协同。** 本轮是集中式预规划分工＋独立飞控执行，边界不变。

---

## 18. 最终提交给用户的报告

最终交付代码之后，生成 `docs/v0.3_implementation_and_verification.md`，至少包含：

### 18.1 实现清单

| 要求/测试 ID | 状态 | 源码函数 | 测试 | 实跑/产物证据 | 剩余问题 |
|---|---|---|---|---|---|

状态只用 `IMPLEMENTED_AND_TESTED / IMPLEMENTED_NOT_RUN / PARTIAL / NOT_IMPLEMENTED / BLOCKED` 等明确值，不用模糊“基本支持”。

### 18.2 端到端调用链

追踪至少一个真实的共享任务：

```text
TaskSpec v2
→ schema 校验
→ 共享区域与分配
→ 每机路径
→ AUTO 执行阶段与绑定
→ SITL
→ 原始观测与 SIM 真值
→ 时间/质量处理
→ 群级双通道语义验证
→ 带来源的 labels/quality
→ dataset 导出
→ observation-only loader
```

给出实际文件路径、调用函数和产物目录，不以流程图代替代码证据。

### 18.3 验证结果

区分以下四类：

- 本轮实际运行的单元/回归测试。
- 手工合成证据的语义测试。
- 读取历史 SITL 日志进行的离线分析。
- 本轮新代码真正启动的 SITL 集成运行。

报告失败及未运行项，说明所有占用进程如何回收。对未实测的参数范围不做推广性结论。

### 18.4 已知限制

至少说明：理想观察圆盘、固定高度、矩形区域、单一任务、规则分区、AUTO 阶段屏障、被动时间映射、无物理碰撞、无在线避碰、无真实探测成功率、无意图可辨识性保证。

---

## 19. 本轮完成定义

仅当以下条件同时满足，才宣布本轮闭环完成：

- [ ] 新旧 TaskSpec 分派与绑定正常，旧行为和历史证据未被破坏。
- [ ] 一个共享区域真正被分配给多机，路径不再是围绕生成点复制同一任务。
- [ ] 进入、覆盖、等待和返回能编译到现有执行接口。
- [ ] 有明确的地图、指令、路径/时间预算预检及未验证项说明。
- [ ] 新的多机共享任务已有本轮真实 SITL 运行证据。
- [ ] 全局覆盖由实际轨迹并集计算，重复覆盖不会虚增。
- [ ] 真值侧与 FCU 侧任务结果独立计算，成功/失败/未知被正确保留。
- [ ] 新标签与样本资格未绕过旧数据质量保护。
- [ ] manifest 覆盖新产物；协议与版本可追溯，旧原语数据不自动改标。
- [ ] 生成器确定性、候选/尝试留存、家族关系和 split 正确。
- [ ] 至少一个正式导出 episode 能被加载器读成 `[T,N,6]` 与掩码。
- [ ] 小规模体检完成；没有报告单类别分类准确率来代替验证。

**本轮不以“实现更多意图或更复杂仿真”为目标，而以“一种共享区域任务的可验证数据闭环”作为完成标准。**

---

## 20. 固定源码来源与使用说明

以下入口在编写本文时通过 GitHub 连接读取，均固定到同一提交，便于 Codex 核对。新设计要求以本文相应章节为准；这些来源只说明基线实现，不代表后续功能已经存在。

- [S1 — 当前基线提交](https://github.com/shy-UCAS/swarm-task-sim/commit/0ea70a2ae08cf76d2b34322fa47e466659a20bdf)：版本变更和作者报告的验证范围。
- [S2 — tasks.py](https://github.com/shy-UCAS/swarm-task-sim/blob/0ea70a2ae08cf76d2b34322fa47e466659a20bdf/Multi-UAV%20SimpleGC/swarm_sim/tasks.py)：三种旧任务、平移路线、静态预检和绑定。
- [S3 — scenario.py](https://github.com/shy-UCAS/swarm-task-sim/blob/0ea70a2ae08cf76d2b34322fa47e466659a20bdf/Multi-UAV%20SimpleGC/swarm_sim/scenario.py)：执行场景限制和单阶段任务接口。
- [S4 — runner.py](https://github.com/shy-UCAS/swarm-task-sim/blob/0ea70a2ae08cf76d2b34322fa47e466659a20bdf/Multi-UAV%20SimpleGC/swarm_sim/runner.py)：阶段屏障、任务确认和运行资格接线。
- [S5 — evaluation.py](https://github.com/shy-UCAS/swarm-task-sim/blob/0ea70a2ae08cf76d2b34322fa47e466659a20bdf/Multi-UAV%20SimpleGC/swarm_sim/evaluation.py)：旧几何任务验证、逐机覆盖和三值结果。
- [S6 — analysis.py](https://github.com/shy-UCAS/swarm-task-sim/blob/0ea70a2ae08cf76d2b34322fa47e466659a20bdf/Multi-UAV%20SimpleGC/swarm_sim/analysis.py)：双通道导出、任务验证调用和 manifest。
- [S7 — quality.py](https://github.com/shy-UCAS/swarm-task-sim/blob/0ea70a2ae08cf76d2b34322fa47e466659a20bdf/Multi-UAV%20SimpleGC/swarm_sim/quality.py)：时钟诊断分级、策略哈希和资格判据。
- [S8 — dataset.py](https://github.com/shy-UCAS/swarm-task-sim/blob/0ea70a2ae08cf76d2b34322fa47e466659a20bdf/Multi-UAV%20SimpleGC/swarm_sim/dataset.py)：来源核验、策略一致性与 family split。
- [S9 — swarm.py](https://github.com/shy-UCAS/swarm-task-sim/blob/0ea70a2ae08cf76d2b34322fa47e466659a20bdf/Multi-UAV%20SimpleGC/swarm.py)：现有 CLI 入口。
- [S10 — AGENTS.md](https://github.com/shy-UCAS/swarm-task-sim/blob/0ea70a2ae08cf76d2b34322fa47e466659a20bdf/Multi-UAV%20SimpleGC/AGENTS.md)：项目环境调用要求。

对话设计依据：用户提供的 `ChatGPT-代码进度分析评价-20260930-0549.md` 中，下一阶段的核心是共享区域任务、任务分解、可行性检查、群级覆盖和数据导出。本文将这些设计拆成明确工作包，并补充了源码接线、旧数据兼容、验证证据和实施范围约束；不把过去的建议视为已经实现的代码。
