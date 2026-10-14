# S2 最小竖切修复版使用说明

本入口仅覆盖规范 §14 S2 第 1、2 步：单任务组的抽象保护区访问、区域搜索及其同步/递次配对。已有 fastsim 内核、控制器、跟踪器、冻结参数和旧标签路径不修改。本轮结果与已隔离的首轮 attempt 分开存储。

## 运行与输入

在本项目的 Conda 环境 llm 中运行：

```powershell
& 'C:\Users\shy\anaconda3\Scripts\conda.exe' run -n llm --no-capture-output python -B scripts/run_v07_s2_minimal.py --scene-attempt 'F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_scene/attempt_s12_20261013_s2_vertical'
```

默认选取 S1.2 候选 226 和 209，保留其各 4 架飞机、初始状态、公共速度/高度、完整公开场景。每次在仓库外 SwarmData/v07_dataset 下创建带 UTC 时间与随机后缀的新 attempt，不修改旧输出。

冻结配置为 configs/fast_dynamics/m3_r2_20261013_v1.json，文件 SHA256 必须为 94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193。物理/控制参数及配置文件保持冻结。S2.3 在执行适配层按每机单独飞行的 10 Hz 完成时刻加出发延迟计算本条预计完成时间，使用最大值再加 120 s 或 20%（取大者）作为上限；不再沿用 600 s 固定截断。若达到本条上限仍未完成，缺失事件保持 unknown，未完成角色条件记 failure。

## 权威几何与独立复核

task_v07.geometry.geometry_facts 是 task_v07 唯一权威几何查询。圆的距离解析计算；凸多边形计算原始每条线段的垂足距离及精确内外符号。没有用圆弧离散化来判定成员关系。

设点到原始设施闭合区域的有符号距离为 \(s(p)\)，区域内为负；各层外扩距离为 \(d_3<d_2<d_1\)。闭边界圈层判断使用 \(s(p)\le d_i\)，从外到内覆盖。位于原始轮廓内部的点自动落在最内层。禁飞区进入深度为 \(\max(0,d_3-s(p))\)。圈层逐帧码、区域事件、保护区深度、搜索作业环带判据共同使用这份结果。

规划的径向边界也查询同一函数；搜索区和撤离点的区域包含/净空不用 buffer 离散化。ContourAnnularSector 由原始轮廓的两条精确外扩等距线与两条角边界共同定义；成员判定依原始轮廓距离与半平面完成。直线与精确外扩轮廓的相交区间通过原始多边形、边矩形及顶点圆盘的解析并集计算；不使用圆弧多边形。

新的 v0.7 可见图以原始轮廓的精确支撑线交点作为候选航点，每条连边通过精确原始轮廓距离检查。没有用近似多边形承担成员/距离判据。圆弧多边形渲染只在 scripts/v07_s2_plotting.py 中调用。

scripts/audit_v07_s2_exact.py 不导入权威几何函数或标签提取器：独立用圆解析距离和 GEOS 原始多边形距离，从导出的 10 Hz 真值重算所有设施圈层，并核对相对指定设施的逐帧层级、区域首次进入/帧数、核心事件、扫描端点顺序/时长/覆盖、撤离到达/悬停、深度、机间距和剔除政策。同时逐行比较 truth.csv 与 truth_10hz.npz 的时间、ID、状态。

每条 episode 在继续下一条前保存 independent_exact_audit.json。全批另保存 independent_full_frame_audit.json；只有全部精确复核通过后才写完成 summary。旧 attempt 始终保持 P0 隔离。

## S2.3 侦察扫描尺度与撤离

扫描区域取目标设施警戒外缘到预警外缘之间的轮廓环带扇区，内外均预留 35 m（30 m 规划余量加 5 m 跟踪余量）。角度在 30°–90°，面积在 0.2–0.6 km²。候选扇区对世界边界、其他设施警戒区及独立限制区使用精确距离与 Lipschitz 空间界限证明净空；不能证明的候选不采用，不放宽几何条件。

扇区面积用精确径向边界的极坐标积分估计，16/32 阶 Gauss 复算差异不大于 0.1 m²。此积分仅用于尺度与报告，点是否属于扫描区始终使用精确解析条件。

观察足迹为水平各向同性圆盘，半径 \(r=0.5h\)，相邻平行扫描条带中心线的间距 \(s=2r\times0.8\)。各机分配连续条带并往返扫描；直线条带按精确扇区裁剪，短于可用长度的候选不采用。覆盖网格间距为 \(\min(r/2,\sqrt{A}/50)\)，组级覆盖阈值仍为 0.90。

扫描时长是实际首个有效观察帧到最后一个按序扫描端点到达帧之间的时差；未观察到完整端点序列时为 null。另报告有效观察帧的累计时长。完成扫描后的撤离轨迹不计入覆盖量。端点序列长度按真实条带数确定，不再固定为四个端点。

撤离点位于目标预警区精确外扩 200 m 的边界，各机到达本机撤离点后悬停 2 s。角色条件增加 reached_retreat_point；到达事件必须发生在已观察到的扫描完成之后，前缀不得宣称未来到达。终点容差与悬停速度阈值沿用既有定义。

## 按完整航线完成时间设置期限

先单独执行每机完整航线，在 10 Hz 网格测量核心开始事件与完成终点悬停的时间。对配对版本使用
\[
T_{\mathrm{end,plan}}=\max_i\left(T_{i,\mathrm{solo,finish}}+\Delta_i\right),\qquad
T_{\max}=T_{\mathrm{end,plan}}+\max(120,\;0.2T_{\mathrm{end,plan}}).
\]
上限向上取整到 0.1 s，保存于 source.json 的 execution_time_budget 和 metrics.json 的 time_budget。这里的单机完成时间包含公共初始等待和末端悬停，不能用核心开始时刻代替。

首次单机飞行尚无完成测量，使用明确记录的保守运行保护预算（等待、两倍名义行程时间、每航段 10 s 转弯预算和终点悬停，再加同样余量）。它只防止仿真无限执行；出发延迟依旧完全来自真实核心事件，标签仍只看 10 Hz 导出轨迹。

## 其余角色的尺度约定（暂未执行）

骨架私有 role_geometry_parameters 保存由实际设施圈层导出的后续参数：监视等距环线的轮廓外扩量取警戒/预警外扩量中点；抵近观察外扩量为警戒外扩量加 1–2 倍规划余量；过境预警区内弦长至少 400 m。它们仅为后续实现约定，本轮没有生成监视、抵近或过境任务。

## 三类结果分开

- result：只由角色条件及组级共享覆盖/多向条件计算，不用时序是否符合指定代替任务成败。
- observed.timing_diagnostics：实测时序是否符合指定、实测批次成员是否符合指定。缺事件返回 unknown。
- generation_quality：从同一 10 Hz 真值计算最小机间距；小于 2 m 记 generation_error，并从 retained_episode_index.json 排除，原始错误样例保留于 excluded_episode_index.json。间距至少 2 m 只报告，不影响角色任务结果。

15 m 是突击各机终点的规划最小间距，不再用于执行任务判定。一般障碍/世界边界的观测违规计数单独记录。数据质量、角色结果和时序结果不互相覆盖。

## 随机时序

每个骨架仍先进行四次独立单机执行，在导出的 10 Hz 网格实测“开始核心作业”时间。公共物理等待为 20 s，保留初始速度，不直接移动轨迹时间戳。

同步目标事件时刻在公共中心上对每机独立加 \(U(-3,3)\) 秒抖动。递次批数从 2 到成员数均匀抽取；随机打乱成员后随机选择非空切分，所有批次至少 1 架；批中心间隔独立抽 \(U(40,90)\) 秒，每机同样加 \(U(-3,3)\) 秒抖动。时间随机子流与列置换子流分别命名，随机种子只存在监督/来源字段。

出发延迟等于目标事件时刻减单机实测事件时刻。延迟一次量化到 0.1 秒网格，量化误差不超过 0.05 秒；原始连续抽样值及可执行网格值均保留。任何批内量化目标时间极差都必须不大于 10 秒。实测事件和批次始终由各版本重新执行后的轨迹提取。

assigned.timing 包含 batch_count、batch_sizes、batch_by_agent、batch_centers_s、inter_batch_gaps_s、jitter_s、target_event_times_s、target_event_times_grid_s、departure_delays_s 和测时来源。单机/任务组/集群三层均可关联到指定安排。指定值不会用于补齐观察事实。

## 输出与加载

每个 episode 包含：

- truth.csv、observations.csv：fastsim ENU 六维 CSV 字段，共同 10 Hz 半开时间轴。
- model_input.npz、public_scene.json：六维扰动观测及完整公开矢量地图。
- labels.json、frame_labels.npz：三层指定/观察/结果及逐帧圈层、阶段等监督。
- task.json、source.json：骨架、单机测时、延迟、噪声与来源等特权信息。
- topdown.png、metrics.json、prefix_labels.json、independent_exact_audit.json。

task_v07.io.load_episode 只返回 x、mask、t_s、agent_ids、scene；load_pair 检查同一骨架、场景与列序一致。标签、真实目标、角色、编组、批次和种子不进入默认模型输入。

attempt 根目录的 labels_full.md / all_episode_labels.json 提供全部标签全文；gallery.md 包含 8 张轨迹图和 4 张配对时序图。数据仍为开发样例，training_eligible=false，不宣称高速 SITL 或真实飞控验证。

相关测试运行命令：

```powershell
& 'C:\Users\shy\anaconda3\Scripts\conda.exe' run -n llm --no-capture-output python -B -m unittest discover -s tests -p 'test_v07_s2*.py' -v
```

两个历史见证帧和完整原始轮廓保存在 tests/fixtures/v07_boundary_witnesses.json。测试覆盖各层边界内外 \(10^{-6}\) m、内外深度、精确航段净空、间距口径、随机时序范围/复现/非空人数以及独立审计的单帧损坏检测。
