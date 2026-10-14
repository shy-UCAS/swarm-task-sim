# S2 通用扩展基础设施交接

本轮按用户给出的备选范围实施：通用抽样、契约、精确几何校验、输入隔离、回调测试框架、索引和统计。角色航点编排由项目方实现；本轮不生成新轨迹，不进入 S3。

已通过的竖切入口、fastsim、既有判定器和 SITL 均未修改。本轮全部为新增文件。唯一规范仍为 [v07_spec_r4a1.md](v07_spec_r4a1.md)，既有竖切仍按原有口径使用。

## 运行

在本 worktree 的项目根目录，使用 PowerShell 7 和 `.conda-env` 指定的 `llm` 环境：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python -B scripts/run_v07_s2_infrastructure.py --scene-attempt 'F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_scene/attempt_s12_20261013_s2_vertical' --audit-existing 'F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/attempt_20261014T014017Z_15a6bf38' --workers 2
```

每次在仓库外 `SwarmData/v07_dataset/attempt_s2infra_<UTC>_<随机后缀>` 新建目录，文件采用独占创建。没有覆盖或迁移旧 attempt 的路径。审计旧样例只读，不重新飞行。省略 `--audit-existing` 会明确写 `not_run`。

此入口会选择 1/2/3 设施各两张、机数至少六架的 S1.2 接受地图；优先选直线被独立限制区阻挡者。不依据角色成功、速度或规划可行性挑选。当前六张均有直线被阻挡。

## 抽样及边界

`task_v07/expansion/sampling.py`：

- `sample_common(scene, family, slot)` 不接收意图参数。每个 family/slot 的公共候选被五类意图复用，使用 common random numbers；因此有限样本的逼近方式、初始任务单元、成员和目标也完全一致，不仅是总体分布相同。跨意图候选并非独立样本。
- 单元数均匀抽 1–3 后按人数截顶；每单元至少两架，全部飞机均分配一次。首目标均匀抽取，后续以 0.5 概率选首目标，否则在其余设施中均匀抽取。
- 同向/多向等概率抽取，至少 90° 仅作为待实现的多向几何约束保存。本轮没有实际方位跨度。
- 随机流按公共候选、角色标签、飞机列序分开。列序使用预分配的数字骨架槽，不读取角色、目标、成员排序或坐标；同步/递次请求共用同一骨架描述。
- `merge_units` 只按目标与规范化角色合并；保留首个单元的执行方式及组间偏移。批次字段不能拆组。组间偏移初值为 0–90 s 均匀抽样，仅为私有指定值，不宣称实测时序。
- `derive_intent` 检查指定角色组合，不是从轨迹推断行为。随机主单元只属于监督，不用于“观察到的主要目标”。
- family 完整快照、速度和高度保持不变；`validate_family_conditions` 可检测意图或骨架阶段对这些量的修改。
- 每图两次常规候选 × 五类，另有一个中止请求。中止请求不是已发生的中止事实。

## 角色编排接口

`task_v07/expansion/contracts.py`：

```python
class RolePlanner(Protocol):
    def plan(self, scene: dict, task_group: dict, role_parameters: dict) -> RouteBundle:
        ...

@dataclass(frozen=True)
class RouteBundle:
    waypoints_by_agent: dict       # agent_id -> [[east_m, north_m, up_m], ...]
    departure_delays_s: dict       # agent_id -> delay_s
```

`UnimplementedRolePlanner.plan` 明确抛出 `PlannerUnavailable`，不会返回空路线或假成功。接口返回值仅包含每机 ENU 航点及出发延迟；不返回标签或实际事实。

调用方将公共场景、合并后的一个任务组及私有角色参数交给项目方实现。角色参数需包含不可变 family 速度、高度和组员初值；这些量来自骨架的 `family_conditions`，不得重新采样。计划参数、测量结果和公共场景继续分开存储。

`validate_route_bundle` 检查返回 ID 与成员一致、有限三维航点、相邻距离至少 1 m，以及非负 0.1 s 网格延迟。`validate_pair` 要求整个骨架和每机航点完全相同，只有返回的出发延迟允许不同；构建配对时不得把时序计划写回共享骨架。它不证明延迟来自实际单机测量，也不保证航线的运动学可行性；这些属于项目方接入后的执行验收。

## 通用几何、输入和证据

`geometry_checks.py` 的生产判定只调用 `task_v07.geometry.geometry_facts`：

- `exact_frame_geometry` 接收完整 10 Hz 公共时钟轨迹，输出所有设施圈层、按 ID 目标圈层、限制区/世界边界/显式禁入策略违规帧和真值最小间距。未提供禁入策略时显式记录未检查，不推断角色豁免。
- 禁入策略形式是 `agent_id -> {facility_id: "warning" | "alert" | "protected"}`，约束该层及更内层。由调用方根据角色传入；必须覆盖每架飞机。
- 小于 2 m 只标记生成错误；不写任务结果。至少 2 m 仅统计。目标点的规划间距也不能代替实际机间距。
- `check_polyline` 只核验传入路径段与障碍/传入防护区的精确间距，不创建或改进路径。零余量时接触/相交也拒绝。
- `check_retreat_point` 同时检查全部设施预警区、限制区和地图边界；默认预警区外 200 m、障碍余量 35 m。

`scripts/audit_v07_s2_infrastructure.py` 是独立审计实现，用原始凸多边形的 GEOS 距离和解析圆，不调用权威几何函数或标签函数。检查逐帧形状、时轴、ID、各设施与目标层、限制区和间距。它不核验尚未实现的新角色事实。

`validate_model_input` 仅允许 `x/mask/t_s/agent_ids/scene`；场景使用既有封闭公开 JSON 契约。私有 family、骨架、种子、目标、角色、批次、计划和各类标签不可作为额外输入字段。列置换同时移动数据与 mask，用 agent ID 对齐；所有飞机共用原始时间原点。

## 角色判据、截断及交叉否定接口

`evaluation.py` 接收以下回调：

```python
Evaluator = Callable[[dict, dict, Evidence], Evaluation]
# 输入：公开场景、A 的私有检查模板、已导出的实际证据
# Evaluation(verdict="yes" | "no" | "unknown", facts={}, event_frames={}, reason="")
```

`Evidence` 仅含 ID、10 Hz 时轴、位置、速度及完整观测标志；不包含 B 的意图、指定批次或未来计划。截断在调用回调前物理切片，半开区间，数组只读；事件帧号超出可见范围触发 P0。回调仍须独立地从证据计算事实，不能从模板复制实测值；框架不能代替角色判据的实现和复核。

`truncation_check` 由调用方传入实测核心作业半程的截止时刻。它属于离线扰动测试，不能宣称在线时已知未来完成时刻。缺回调为 `not_run`，不是通过。

`cross_negation` 在同 family 内用 A 的模板判定 B 的实际轨迹，列出 20 个有向基础意图组合。对角线跳过，角色重叠不自动转成基础意图排他。实测 yes 记 FAIL；缺模板、回调或实际轨迹为 not_run。新测试中的通用终点见证只验证测试框架，不冒充六种角色方式的完整判据。

## 视图与文件

`views.py` 的 `make_views(records)` 只生成索引。成功配对要求两个版本实际任务成功、质量有效、独立复核通过、每个任务组的实测时序与指定一致，并且非时序条件摘要、飞机列序和场景摘要相同。family 内按五类成功配对数最小值平衡，稳定抽选；超额有效条目进扩展视图，失败与中止单列。待执行请求另列 pending，不占任何成功配额。

记录的摘要和审核状态必须由真实导出/审核调用产生，不能手工将 pending 改成 success。当前入口没有自动执行外部角色插件或计算新增角色成功标签；接入后需要新增该步骤。

输出文件：

- `registration.json`：选择规则、源地图摘要与 ID。
- `private_skeleton_descriptors.json`：66 个私有描述；禁止作模型输入。
- `episode_requests.json`：120 常规 + 6 中止待执行请求，无假 episode 路径。
- `views.json`：五个索引及逐 family 平衡计数。
- `cross_negation.json`：20 类组合及 960 条具体待验组合。
- `role_check_status.json`：缺失角色实现与测试状态。
- `existing_geometry_audit.json`：旧竖切的只读复核。
- `summary.json`、`report.md`：统计、运行耗时、未运行项。
- `verification.json`：本轮测试与代码摘要，交付时另存。

## 验证命令与待接入范围

```powershell
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python -B -m unittest discover -s tests -p 'test_v07_s2*.py'
```

本轮新增 33 项、关联原有 43 项，共 76 项通过。没有运行 M3 全量 CI、远端 CI 或 SITL；测试不导入 matplotlib。

完整 S2 扩展仍需项目方实现角色航线、执行适配、角色判据和新增事实的独立重算，并实际运行 120 + 6 条。实际方位、运动学可行性、条带分配、驻留撤离、时序与成败率、角色截断验收和交叉否定、轨迹/时序图均须在真实执行后报告。本轮成功的是通用基础设施，不代表完整 S2 扩展验收通过。
