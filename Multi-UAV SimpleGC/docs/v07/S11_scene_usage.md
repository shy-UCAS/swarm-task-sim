# v0.7 S1.1 抽样修订与诊断口径

本轮只修订场景抽样和新增诊断。公开 JSON 的 schema、字段、实体语义及单位保持
`traj2language.public_scene/0.7-s1.1`；`contract.py`、公开 JSON Schema 和
`geometry.py` 未修改。`checks.py` 仅增加路线诊断字段和检查输出版本号，
原有几何、余量、可达性和方位口径不变。没有接入 fastsim 或 SITL。

## 抽样

| 项目 | S1.1 规则 |
|---|---|
| 设施数 | 1/2/3 个的目标概率分别为 40%/35%/25%；不是配额或验收门禁。 |
| 地图边长 | 按设施数取 4000/5000/6000 m；公开世界边界保存真实大小。 |
| 设施形状和圈层 | 原 r4 的半径、凸轮廓尺寸及三层外扩初值不变，不重抽圈层来提高成功率。 |
| 设施位置 | 根据每个完整预警轮廓求可放入地图的平移范围，在其中构造孤立/成簇/串列；圈层与进场区至少保留原安全余量。 |
| 设施位置预算 | 同一设施集合和圈层最多 128 次中心构造；不换设施数、形状或圈层，不放宽任何验收条件。 |
| 限制区 | 先取 1–3 个请求槽位；每槽先抽一种位置类型，只重抽该槽的形状、位置和位置关联。每槽最多 48 次。成功槽保持原样，失败槽跳过并保存次数及原因。 |
| 雷达 | 在原设施旁/预警外缘的候选规则中，只保留地图内合法点；独立重试，最多 80 次。预算用尽时用已知地图内的同类边界/中心位置。 |
| 初始无人机 | 机数、共同高度/速度、间距、噪声初值范围和无标签编号原则不变。 |

设施旁限制区须与预警区部分重叠且不碰警戒区；设施之间限制区的中心选在
两设施预警轮廓之间的直线间隙或共同覆盖区，再检查其完整几何。
进场阻挡的中心选在进场区至设施的直线上，整个限制区在进场区安全余量之后、
预警轮廓之前，并确认原始几何实际挡住直线。所有类型都检查地图包含、
全部设施警戒区/禁飞区和进场区安全余量；不增加限制区间互不相交的门禁。

公开契约保留原有至少一个限制区的数量要求。若全部请求槽位用尽后均未放成，
候选以 `sampling_no_obstacle_placed` 拒绝，记录 `family_initial.json`、
`check_results.json`、`candidate_geometry.json` 和 PNG；不输出契约无效的
`public_scene.json`。设施位置预算用尽同样记为抽样失败。完整构造的地图
全部运行原有完整检查；不得以抽样期局部检查代替最终验收。

## 两项新增诊断

每个完整地图仍检查每个进场区到每个设施的示例路线，并增加：

- `straight_blocked_by_obstacle`：起终点直线是否进入至少一个原始限制区内部；
  边界相切不计阻挡。`blocking_obstacle_ids` 保存公开障碍 ID。
- `straight_blocked_with_margin`：直线是否被原有安全外扩障碍挡住，单列记录，
  不混入原始限制区阻挡比例。
- `straight_blocked_by_entry_blocker`：至少一个实际挡住该直线的障碍属于
  生成器侧的进场阻挡位置类型；不进入公开 JSON。
- `max_lateral_deviation_m`：示例折线路径到起终点无限直线的最大横向垂距。
  无可行路线时为 null，不伪装为零；直线路径为零。

设起终点为 \(a,b\)，折线顶点集合为 \(P\)，则

\[
d_{\perp}^{\max}=\max_{p\in P}\frac{|(b_x-a_x)(p_y-a_y)-(b_y-a_y)(p_x-a_x)|}{\|b-a\|}.
\]

垂距沿每条线段的最大值出现在顶点，故不需要人为插密采样。
summary 主统计使用接受地图的全部示例路线；横向偏离分布仅统计实际绕行路线
（路线长度/直线长度大于 \(1+10^{-9}\)）。这两项诊断及方位跨度均不影响接受/拒绝。

## 执行与重建

项目环境仍由 `.conda-env` 指定，当前为 `llm`。PowerShell 7 中执行：

```powershell
conda run -n llm --no-capture-output python -B -m unittest discover -s tests -p 'test_v07_scene*.py' -v
conda run -n llm --no-capture-output python -B scripts/sample_v07_scenes.py --candidates 300 --seed 2026101307 --sampling-revision s1.1
```

原 S1 与 S1.1 均可按种子重建；重建到新 attempt，不覆盖已有数据：

```powershell
# 原 S1
conda run -n llm --no-capture-output python -B scripts/sample_v07_scenes.py --candidates 1 --family-seed 17230448913791479827 --sampling-revision s1
# S1.1（使用原 family 保存的种子和预算）
conda run -n llm --no-capture-output python -B scripts/sample_v07_scenes.py --candidates 1 --family-seed 17230448913791479827 --sampling-revision s1.1 --obstacle-attempts 48
```

程序接口：`sample_family(seed, config, revision="s1.1", policy=SamplingPolicy(...))`；
`family_initial.json` 保存实际地图配置、抽样版本、预算、种子和各槽位尝试记录。
自定义设施/雷达预算时通过程序接口重建完整 policy。S1.1 生成器版本为
`traj2language.scene_sampler/0.7-s1.3`；family/map ID 使用 `s11` 前缀，
避免与原 S1 同种子、不同地图的 ID 混淆。这些字段均不进入公开场景。

## 输出与代表图

每轮自动创建外部 `SwarmData/v07_scene/attempt_*`，保存完整候选及失败，
不重写旧 attempt。summary 包含候选/接受/拒绝的设施数、布局、地图边长、
限制区数和机数分布，槽位跳过次数，新增路线诊断和采样/绘图耗时。

每轮选 16 张代表图：优先至少三张二设施、三张三设施、三张实际直线被
进场阻挡挡住的接受地图，再补充布局、绕行幅度和存在的拒绝例。
`representative_coverage` 保存实际配额核验结果；配额只决定展示，不拒绝地图。
原图保留各 family 文件夹中；代表图同时集中复制到 attempt 内的 `代表图库/`。
PNG 增加红色点线显示被原始限制区挡住的直线，路线仍为原可见图规划结果。

本轮只运行新增和修改相关的 S1/S1.1 测试，本地提交、不推送，完成后停在 S1.1。
