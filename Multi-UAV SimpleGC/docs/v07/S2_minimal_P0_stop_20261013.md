# S2 最小竖切 P0 停止报告（2026-10-13）

**状态：P0_STOP。本轮按用户停止规则结束，未完成 S2 验收。**

8 个 episode 已生成，但最终独立复核发现逐帧圈层标签与公开矢量几何的精确判定不一致。全 attempt 暂不用于验收、训练或评测。生成 summary 的 completed 仅表示生成结束，停止结论以同目录 P0_STOP.json 为准。

## 已确认缺陷

新模块 `task_v07/labels.py:29` 用 `to_shape(geometry,64)` 的离散圆弧判断 BufferedPolygon 成员关系。精确多边形距离不大于 buffer_m 的判断与其在两个 10 Hz 导出帧上不一致：

| Episode | 时间 | 飞机 | 设施 | 保存圈层 | 精确圈层 |
|---|---:|---|---|---|---|
| 二设施突防同步版 | 336.9 s | uav_03 | facility_02 | 圈外 | 预警区 |
| 二设施突防同步版 | 479.3 s | uav_04 | facility_02 | 圈外 | 预警区 |

发现后停止：未改判据、未修复、未再生成或继续回归。现有 fastsim 内核、冻结配置、原规划器、旧判定器与 SITL 路径没有改动。

后续恢复时需在新增标签模块使用权威轮廓的精确成员关系，增加这两个边界见证回归，并在新 attempt 重新验证。此项尚未执行。

## S1.2 已完成

- 候选 300，接受 300：100%。
- 设施数 1 / 2 / 3：116 / 110 / 74。
- 独立限制区相交对数：0（保守外包轮廓复核）。
- 保留成功槽位，一种类型耗尽预算后尝试其余类型，全部失败才跳过。原 S1/S1.1 路径保留；原 S1.1 的 283 个接受样本逐位重建通过。
- 耗时 49.920 s，未画全量图片。

## 已生成但隔离的 S2 草稿

地图为 S1.2 候选 226（单设施）和 209（二设施），均使用原有四机初始状态。两个意图共享该 family，任务单元数均为 1，设施指向通过独立于意图的公共子流抽取。每个骨架抽一次随机列置换，配对复用。

执行复用冻结配置 SHA256 `94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193` 的 SynchronousEngine / RouteTracker。引擎 20 ms 更新；所有标签、最小间距、探针诊断均从 100 ms 半开导出网格测量。初始状态不重置，先共同物理等待 20 s，独立单机实飞测时，再使用出发延迟重飞两个版本。未按路程除以速度计算延迟。

突防采用互异终点，规划方位跨度 120°，终点最小间距分别 122.903 / 56.783 m。最小相邻航点距离全批 4.730 m。侦察为一个矩形区域四等宽条带；覆盖是理想各向同性半径 35 m 足迹、10 m 网格的共享代理指标，阈值 0.90，不声称相机识别结果。scan_start 是实际处于本机条带/预警环带、未进入限制区且速度至少 0.5 m/s 的首个网格样本。

同步窗口 10 s；相邻事件间隔大于 20 s 划批，每批整体跨度必须不大于 10 s。指定递次批次间隔 60 s。实测批次独立形成并与指定成员划分比较。

下表是生成时的诊断记录，**不是最终验收结论**：

| 设施数 | 任务 | 指定 | 实测 | 事件极差 s | 实际最小间距 m | 记录结果 | 单条全流程 s |
|---:|---|---|---|---:|---:|---|---:|
| 1 | penetration | synchronous | synchronous | 0.0 | 17.023 | success | 17.039 |
| 1 | penetration | sequential | sequential | 60.0 | 15.228 | success | 17.634 |
| 1 | reconnaissance | synchronous | synchronous | 0.0 | 6.488 | failure | 22.252 |
| 1 | reconnaissance | sequential | sequential | 60.0 | 16.972 | success | 25.545 |
| 2 | penetration | synchronous | synchronous | 0.0 | 21.116 | success | 25.761 |
| 2 | penetration | sequential | sequential | 60.0 | 21.116 | success | 26.815 |
| 2 | reconnaissance | synchronous | synchronous | 0.0 | 16.240 | success | 29.728 |
| 2 | reconnaissance | sequential | sequential | 60.0 | 20.133 | success | 30.614 |

单设施侦察同步版在 105.6 s 的 uav_01/uav_02 间距为 6.488 m，低于本轮 15 m 规划间距，已标为任务失败；另外两架的单机结果保持独立成功。此非 P0 约束违规按用户规则继续执行，没有挽救单个版本或重换骨架。

3 个短航段转弯探针在 4 / 7 / 10 m/s 的导出轨迹最大偏差为 0.102 / 0.475 / 4.041 m。结果仅代表冻结 fastsim，不代表高速 SITL 校准。

生成总耗时 197.454 s（实际精确值见 summary.json），包含 3 个探针、16 次独立单机测时、8 个 episode、标签/导出/加载、8 张俯视图及 4 张配对时序图。单条全流程包括该条执行/导出/标签/画图/审计，加上半份共享骨架构造及四机测时成本；未计开发时间和最终独立复核。

## 测试与输出

停止前 58 项原有 v0.7 场景测试、18 项新增 S1.2/S2 测试通过。已有测试覆盖缺事件、因果截断、按 ID 的列置换、配对白名单、独立终点、实际间距和扫描开始；尚未覆盖上述圆弧近似边界缺陷。没有运行全量回归、M3 离线 CI 或远端 CI。

- S1.2：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_scene\attempt_s12_20261013_s2_vertical`
- S2 隔离 attempt：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_20261013T164924Z_c284e609`
- `P0_STOP.json`：精确错误见证与停止决定。
- `all_episode_labels.json`、`labels_full.md`：8 条标签全文，均为隔离草稿。
- `gallery.md`：8 张实际轨迹图与 4 张核心事件时序图。
- `truth.csv` / `observations.csv` 沿用 fastsim ENU 六维 CSV 字段；新版协议 swarm_defense_v07a 由 task_v07.io.load_episode 加载。旧加载器保持不变。
- 模型输入只含 x、mask、t_s、agent_ids 和 scene；规划、测时种子、任务标签、真值和 family/skeleton 标识保存在监督/来源文件。默认观测为按雷达距离微扰的位置和速度，互相独立采样且配对复用噪声子流。

本地提交保存停止快照，不推送，不进入五类扩展。
