# v0.7 S1 场景接口与本地使用

> 本文记录原 S1。当前默认抽样为 S1.1，见 [S11_scene_usage.md](S11_scene_usage.md)。
> 重建原 S1 时显式选择 `--sampling-revision s1`。

本实现只覆盖 `v07_spec_r4a1.md` 第 14 节 S1。所有文件为新增，不接入
fastsim、旧规划器、判定器或 SITL；本轮不运行 M3 清单或全量回归。

## 环境、采样与重建

从 `Multi-UAV SimpleGC/.conda-env` 读取环境名；当前为 `llm`。
S1 独立依赖见 `scene_v07/requirements.txt`，测试补充依赖见
`tests/v07_scene_requirements.txt`。既有项目 `requirements.txt` 不作修改。
本轮本机已经安装这些版本，不需要安装或改变环境。

在项目目录用 PowerShell 7 执行：

```powershell
conda run -n llm --no-capture-output python -B -m unittest discover -s tests -p 'test_v07_scene*.py' -v
conda run -n llm --no-capture-output python -B scripts/sample_v07_scenes.py --candidates 300 --seed 2026101307 --sampling-revision s1
```

输出默认到仓库外 `SwarmData/v07_scene/attempt_<UTC时间>_<随机后缀>/`。
每次自动创建新 attempt；指定 `--attempt-name attempt_名称` 也必须不存在。
既有 attempt 不覆盖、不续写，批次中途失败保留已完成产物。

按单个 family 的种子重建（新的 attempt，不覆盖原图）：

```powershell
conda run -n llm --no-capture-output python -B scripts/sample_v07_scenes.py --candidates 1 --family-seed 17230448913791479827 --sampling-revision s1
```

原 S1 程序接口为 `sample_family(seed, SceneConfig(...), revision="s1")`。原始配置保存在
`family_initial.json`，重建须使用相同配置、生成器版本与几何库版本。
默认 CLI 使用本轮默认配置；自定义配置用程序接口重建。
family 子种子由主种子和候选序号的 SHA256 独立派生，与执行顺序无关。
浮点数不舍入；UTF-8 JSON 固定键序与换行，拒绝非有限数。

## 文件与可见性

每个候选（包含被拒地图）有以下文件：

| 文件 | 内容与用途 |
|---|---|
| `public_scene.json` | 模型可见的权威矢量场景；schema、ENU、单位、边界、进场区、全部设施、三层区域、限制区、雷达。 |
| `family_initial.json` | 生成器侧：family/map ID、种子、配置、机数、各机初始位置/速度/加速度、公共高度/速度、间距、观测参数、布局与实体位置采样信息。 |
| `provenance.json` | 生成器侧：主种子、候选序号、family 种子及派生规则。 |
| `check_results.json` | 检查侧：接受/拒绝、原因、每个进场区到每个设施的示例航线、可行方位统计。 |
| `topdown.png` | 开发检查图，包含示例航线、方位弧段、种子和拒绝原因；不作为公开模型输入。 |

attempt 根目录有 `summary.json`、`candidates.json`、`representatives.json`
及 `gallery.md`。统计同时保留候选、接受和拒绝分布；种子、检查结果、
规划航线及整个 family 文件均不进入公开模型输入。

公开契约 `traj2language.public_scene/0.7-s1.1` 有递归白名单和
`scene_v07/public_scene.schema.json`。实体类型为 `facility`、
`protection_zone`、`hard_constraint_obstacle`、`radar`。进场区和世界
边界是独立的几何记录。圈层的 `facility_id` 是公开几何关联，
不是任务目标分配。没有目标、任务组、角色、批次或意图；没有采样种子
或 family/map ID。每个设施恰有 protected / alert / warning 三层。

几何类型：Circle（圆心、半径）、Polygon（凸轮廓顶点，隐式闭合）、
BufferedPolygon（原始凸轮廓 + 欧氏外扩距离）、Point（雷达位置）。
原生几何描述为权威表示；圆角无需用拟合多边形替换。长度用米，ENU
水平坐标为 east/north；速度为 m/s，加速度为 \(m/s^2\)，角度单位按字段声明。
`arcs_deg` 是检查文件中明确标注的度，公开单位中的 angle 为 rad。

## 几何、绕行和方位口径

设施圆半径 20–60 m，凸多边形外接直径 100–400 m；设施数 1–3。
圈层按设施轮廓外扩：内层 50–150 m，中层再加 150–400 m，
外层再加 300–800 m。其他设施内层和中层不得相交。
孤立布局的预警区域互不相交；成簇布局的预警相交图必须连通；
串列布局的设施中心共线。单设施记为 single。

限制区数 1–3，圆半径 100–400 m或凸多边形外接直径 200–800 m。
进场阻挡、设施旁（预警区部分重叠）、设施之间（至少两设施）按同一
无意图采样规则选择；每个候选只采样一次，不为通过检查重抽。
限制区不得与内层/中层相交，不得覆盖进场区；其安全外扩亦不得截入
进场区。完整设施圈层及实体要求留在地图内，不静默裁切；这项完整轮廓
约束和进场安全余量检查属于本轮明确记录的几何口径。

规划仅对独立限制区外扩 30 m，合并重叠障碍后建可见图，Dijkstra
求图上最短路。防护区域不会入障碍集合；地图外不可绕行。
圆使用每象限 8 段的外切包络；凸多边形外扩采用均匀法向及各轮廓边
法向的精确支撑半平面交集，使路径不切入权威圆角。对半径
430 m 的圆，包络顶点最大超出约 2.08 m；多边形 30 m 圆角最大
超出约 0.146 m。报告的最短路针对该保守多边形，不能宣称是解析
圆弧上的绝对最短路。几何合法性检查每象限 64 段，使用包络作
不相交和地图包含检查；极近边界可能出现保守拒绝。数值容差为
\(10^{-7}\) m。

每个进场区用中心点规划到每个设施的内部参考点；进场区为凸形且
整区不与安全障碍相交，区内初始点可先连到该中心。
初始状态不按任务标签产生，关联 ID 随机打乱，且所有飞机共享高度。

方位在每个设施预警轮廓外 30 m 处按 \(5^\circ\) bin 的中点采样。
每个方位要求进场区能到达该点，且该点到设施内部参考点的径向段
不穿安全障碍。保存逐进场区掩码和所有进场区共同可行的弧段，
以 east 方向为 0°、逆时针。弧段端点是采样 bin 边界；覆盖不是
连续区间的数学认证。圆周跨 0° 的区间分成两段，最大连续跨度
按圆周连接计算。跨度只统计和画图，不作为拒绝门禁。

未指定数值的工程初值：公共高度 100–150 m、进场区宽 360 m/深
100 m；初始速度在公共巡航速度的 0–25% 内随机取向内运动，
初始加速度为零；不虚构姿态或旋转动力学。它们都不是冻结参数。
雷达采样 1–3 个，仅保存位置和 family 级噪声初值；S1 不生成观测。

## 本轮边界

机数 4–12、巡航速度 4–10 m/s、横向间距 15–25 m。
不采样 r4a-1 已取消的 family 编组数/规模，也不采样任务单元、
成员分配、角色、目标或协同时间。本轮场景可达性仅是名义二维几何
结论；S2 再检查 fastsim 实际运动能力与多机全过程约束。
