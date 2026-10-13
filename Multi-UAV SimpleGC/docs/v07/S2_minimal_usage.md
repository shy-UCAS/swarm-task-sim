# S2 最小竖切修复版使用说明

本入口仅覆盖规范 §14 S2 第 1、2 步：单任务组的抽象保护区访问、区域搜索及其同步/递次配对。已有 fastsim 内核、控制器、跟踪器、冻结参数和旧标签路径不修改。本轮结果与已隔离的首轮 attempt 分开存储。

## 运行与输入

在本项目的 Conda 环境 llm 中运行：

```powershell
& 'C:\Users\shy\anaconda3\Scripts\conda.exe' run -n llm --no-capture-output python -B scripts/run_v07_s2_minimal.py --scene-attempt 'F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_scene/attempt_s12_20261013_s2_vertical'
```

默认选取 S1.2 候选 226 和 209，保留其各 4 架飞机、初始状态、公共速度/高度、完整公开场景。每次在仓库外 SwarmData/v07_dataset 下创建带 UTC 时间与随机后缀的新 attempt，不修改旧输出。

冻结配置为 configs/fast_dynamics/m3_r2_20261013_v1.json，文件 SHA256 必须为 94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193。600 秒上限保持不变；随机递次批次过晚可能导致执行超时，缺失事件保持 unknown，完整超时窗内未完成的角色条件记 failure。

## 权威几何与独立复核

task_v07.geometry.geometry_facts 是 task_v07 唯一权威几何查询。圆的距离解析计算；凸多边形计算原始每条线段的垂足距离及精确内外符号。没有用圆弧离散化来判定成员关系。

设点到原始设施闭合区域的有符号距离为 \(s(p)\)，区域内为负；各层外扩距离为 \(d_3<d_2<d_1\)。闭边界圈层判断使用 \(s(p)\le d_i\)，从外到内覆盖。位于原始轮廓内部的点自动落在最内层。禁飞区进入深度为 \(\max(0,d_3-s(p))\)。圈层逐帧码、区域事件、保护区深度、搜索作业环带判据共同使用这份结果。

规划的径向边界也查询同一函数；搜索区和撤离点的区域包含/净空不用 buffer 离散化。新的 v0.7 可见图以原始轮廓的精确支撑线交点作为候选航点，每条连边通过精确原始轮廓距离检查。没有用近似多边形承担成员/距离判据。圆弧多边形渲染只在 scripts/v07_s2_plotting.py 中调用。

scripts/audit_v07_s2_exact.py 不导入权威几何函数或标签提取器：独立用圆解析距离和 GEOS 原始多边形距离，从导出的 10 Hz 真值重算所有设施圈层，并核对相对指定设施的逐帧层级、区域首次进入/帧数、核心事件、深度、机间距和剔除政策。同时逐行比较 truth.csv 与 truth_10hz.npz 的时间、ID、状态。

每条 episode 在继续下一条前保存 independent_exact_audit.json。全批另保存 independent_full_frame_audit.json；只有全部精确复核通过后才写完成 summary。旧 attempt 始终保持 P0 隔离。

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
