# V02 arrival_s 兜底与航段耗时只读诊断

版本：`v04_arrival_and_segment_diagnostics_v1`；运行：`20261002T083751Z_3874072a`。

本报告不改变 arrival_s、名义模型、τ、验收门禁或任何旧产物。全部 18 个双通道窗口已逐一复现原 arrival_s；表中只展开 11 个兜底窗口。

## 口径

原定义在终点 waypoint_reached 接收事件至阶段结束之间搜索，以三维终点距离 ≤1 m 且水平速度 ≤0.3 m/s 的首个样本作为 arrival_s；没有最短悬停持续时间要求。SIM 速度来自 10 Hz 对齐位置的后向差分，分母为时钟模型反演后的源时间差。FCU 用其报告的水平速度。两者独立计算，不相互替代。

下表的低速持续时长仅累加至少 0.2 s 的连续样本跨度（≤0.3 m/s），不施加 1 m 距离限制；因此可识别在容差外的低速停留。最后一个采样到阶段结束不足 0.1 s 的尾段不外推。此值是 sampled evidence，不能证明整个尾段一直静止。

## 兜底窗口逐项结果

| 通道/飞机/阶段 | 搜索区间 s | 最小三维距离 m | 最低速度 m/s | 距离内/低速/同时满足样本 | 低速持续总时长 s | 直接原因 |
|---|---|---:|---:|---|---:|---|
| truth/uav_01/p00_approach | 8.056–9.554 | 0.389 | 0.404 | 12/0/0 | 0.000 | 搜索区间没有 ≤0.3 m/s 样本 |
| truth/uav_03/p00_approach | 8.042–9.554 | 0.334 | 0.402 | 11/0/0 | 0.000 | 搜索区间没有 ≤0.3 m/s 样本 |
| truth/uav_01/p01_observe | 78.704–80.198 | 0.239 | 0.391 | 10/0/0 | 0.000 | 搜索区间没有 ≤0.3 m/s 样本 |
| truth/uav_03/p01_observe | 78.640–80.198 | 0.202 | 0.491 | 11/0/0 | 0.000 | 搜索区间没有 ≤0.3 m/s 样本 |
| truth/uav_01/p02_return | 97.767–98.794 | 0.203 | 1.214 | 6/0/0 | 0.000 | 搜索区间没有 ≤0.3 m/s 样本 |
| truth/uav_02/p02_return | 97.653–98.794 | 0.409 | 0.980 | 7/0/0 | 0.000 | 搜索区间没有 ≤0.3 m/s 样本 |
| truth/uav_03/p02_return | 97.717–98.794 | 0.194 | 1.033 | 7/0/0 | 0.000 | 搜索区间没有 ≤0.3 m/s 样本 |
| observation/uav_03/p01_observe | 78.640–80.198 | 0.033 | 0.328 | 10/0/0 | 0.000 | 搜索区间没有 ≤0.3 m/s 样本 |
| observation/uav_01/p02_return | 97.767–98.794 | 0.232 | 1.118 | 5/0/0 | 0.000 | 搜索区间没有 ≤0.3 m/s 样本 |
| observation/uav_02/p02_return | 97.653–98.794 | 0.341 | 0.939 | 6/0/0 | 0.000 | 搜索区间没有 ≤0.3 m/s 样本 |
| observation/uav_03/p02_return | 97.717–98.794 | 0.127 | 0.984 | 6/0/0 | 0.000 | 搜索区间没有 ≤0.3 m/s 样本 |

原因仅按可观测条件分类；阈值未通过本身不能证明差分噪声。JSON 还保存最小距离/速度所在时刻、该时刻的另外一个量、低速区间端点及其距离范围、最终连续低速时长和未采样尾长。不能把短观察尾段解释成原定义中不存在的最短悬停要求。

## 航段主分类（加总为三机累计，非阶段墙钟时长）

| 通道 | 类别 | 航段数 | 名义合计 s | 最近点合计 s | 事件合计 s |
|---|---|---:|---:|---:|---:|
| observation | approach | 3.000 | 16.639 | 27.700 | 24.062 |
| observation | lane_change | 12.000 | 14.400 | 27.500 | 31.185 |
| observation | return | 3.000 | 45.572 | 55.506 | 52.543 |
| observation | scan | 15.000 | 150.000 | 183.338 | 175.922 |
| truth | approach | 3.000 | 16.639 | 27.400 | 24.062 |
| truth | lane_change | 12.000 | 14.400 | 27.800 | 31.185 |
| truth | return | 3.000 | 45.572 | 55.506 | 52.543 |
| truth | scan | 15.000 | 150.000 | 182.538 | 175.922 |

实际最近点按各阶段内 10 Hz 三维距离最小样本确定，同距取首个样本，33 个节点在每个通道内均顺序单调。每段用相邻最近点的时间差（首段从阶段放行）计算；事件通道用相邻原始到点事件差。扫描/换线按原规划点索引分组。这里的采样与姿态/时钟误差不允许把小于约 0.1 s 的差异解释成精确动力学效应。

## 每个航段

| 通道/飞机/阶段 | seq | 类别 | 长度 m | 名义 s | 最近点 s | 事件 s | 最近点增量 s |
|---|---:|---|---:|---:|---:|---:|---:|
| truth/uav_01/p00_approach | 2 | approach | 16.639 | 5.546 | 9.100 | 8.056 | 3.554 |
| observation/uav_01/p00_approach | 2 | approach | 16.639 | 5.546 | 9.200 | 8.056 | 3.654 |
| truth/uav_02/p00_approach | 2 | approach | 16.639 | 5.546 | 9.200 | 7.964 | 3.654 |
| observation/uav_02/p00_approach | 2 | approach | 16.639 | 5.546 | 9.300 | 7.964 | 3.754 |
| truth/uav_03/p00_approach | 2 | approach | 16.639 | 5.546 | 9.100 | 8.042 | 3.554 |
| observation/uav_03/p00_approach | 2 | approach | 16.639 | 5.546 | 9.200 | 8.042 | 3.654 |
| truth/uav_01/p01_observe | 2 | scan | 30.000 | 10.000 | 13.846 | 11.816 | 3.846 |
| truth/uav_01/p01_observe | 3 | lane_change | 3.600 | 1.200 | 2.300 | 2.575 | 1.100 |
| truth/uav_01/p01_observe | 4 | scan | 30.000 | 10.000 | 11.600 | 11.473 | 1.600 |
| truth/uav_01/p01_observe | 5 | lane_change | 3.600 | 1.200 | 2.500 | 2.669 | 1.300 |
| truth/uav_01/p01_observe | 6 | scan | 30.000 | 10.000 | 11.800 | 11.376 | 1.800 |
| truth/uav_01/p01_observe | 7 | lane_change | 3.600 | 1.200 | 2.200 | 2.605 | 1.000 |
| truth/uav_01/p01_observe | 8 | scan | 30.000 | 10.000 | 11.600 | 11.355 | 1.600 |
| truth/uav_01/p01_observe | 9 | lane_change | 3.600 | 1.200 | 2.300 | 2.755 | 1.100 |
| truth/uav_01/p01_observe | 10 | scan | 30.000 | 10.000 | 12.100 | 12.526 | 2.100 |
| observation/uav_01/p01_observe | 2 | scan | 30.000 | 10.000 | 13.946 | 11.816 | 3.946 |
| observation/uav_01/p01_observe | 3 | lane_change | 3.600 | 1.200 | 2.200 | 2.575 | 1.000 |
| observation/uav_01/p01_observe | 4 | scan | 30.000 | 10.000 | 11.700 | 11.473 | 1.700 |
| observation/uav_01/p01_observe | 5 | lane_change | 3.600 | 1.200 | 2.400 | 2.669 | 1.200 |
| observation/uav_01/p01_observe | 6 | scan | 30.000 | 10.000 | 11.800 | 11.376 | 1.800 |
| observation/uav_01/p01_observe | 7 | lane_change | 3.600 | 1.200 | 2.300 | 2.605 | 1.100 |
| observation/uav_01/p01_observe | 8 | scan | 30.000 | 10.000 | 11.600 | 11.355 | 1.600 |
| observation/uav_01/p01_observe | 9 | lane_change | 3.600 | 1.200 | 2.300 | 2.755 | 1.100 |
| observation/uav_01/p01_observe | 10 | scan | 30.000 | 10.000 | 12.100 | 12.526 | 2.100 |
| truth/uav_02/p01_observe | 2 | scan | 30.000 | 10.000 | 13.746 | 11.863 | 3.746 |
| truth/uav_02/p01_observe | 3 | lane_change | 3.600 | 1.200 | 2.300 | 2.591 | 1.100 |
| truth/uav_02/p01_observe | 4 | scan | 30.000 | 10.000 | 11.700 | 11.450 | 1.700 |
| truth/uav_02/p01_observe | 5 | lane_change | 3.600 | 1.200 | 2.300 | 2.590 | 1.100 |
| truth/uav_02/p01_observe | 6 | scan | 30.000 | 10.000 | 11.700 | 11.428 | 1.700 |
| truth/uav_02/p01_observe | 7 | lane_change | 3.600 | 1.200 | 2.300 | 2.475 | 1.100 |
| truth/uav_02/p01_observe | 8 | scan | 30.000 | 10.000 | 11.700 | 11.477 | 1.700 |
| truth/uav_02/p01_observe | 9 | lane_change | 3.600 | 1.200 | 2.300 | 2.487 | 1.100 |
| truth/uav_02/p01_observe | 10 | scan | 30.000 | 10.000 | 11.900 | 12.510 | 1.900 |
| observation/uav_02/p01_observe | 2 | scan | 30.000 | 10.000 | 13.846 | 11.863 | 3.846 |
| observation/uav_02/p01_observe | 3 | lane_change | 3.600 | 1.200 | 2.200 | 2.591 | 1.000 |
| observation/uav_02/p01_observe | 4 | scan | 30.000 | 10.000 | 11.700 | 11.450 | 1.700 |
| observation/uav_02/p01_observe | 5 | lane_change | 3.600 | 1.200 | 2.300 | 2.590 | 1.100 |
| observation/uav_02/p01_observe | 6 | scan | 30.000 | 10.000 | 11.800 | 11.428 | 1.800 |
| observation/uav_02/p01_observe | 7 | lane_change | 3.600 | 1.200 | 2.200 | 2.475 | 1.000 |
| observation/uav_02/p01_observe | 8 | scan | 30.000 | 10.000 | 11.700 | 11.477 | 1.700 |
| observation/uav_02/p01_observe | 9 | lane_change | 3.600 | 1.200 | 2.400 | 2.487 | 1.200 |
| observation/uav_02/p01_observe | 10 | scan | 30.000 | 10.000 | 12.000 | 12.510 | 2.000 |
| truth/uav_03/p01_observe | 2 | scan | 30.000 | 10.000 | 13.846 | 11.893 | 3.846 |
| truth/uav_03/p01_observe | 3 | lane_change | 3.600 | 1.200 | 2.300 | 2.527 | 1.100 |
| truth/uav_03/p01_observe | 4 | scan | 30.000 | 10.000 | 11.600 | 11.429 | 1.600 |
| truth/uav_03/p01_observe | 5 | lane_change | 3.600 | 1.200 | 2.400 | 2.646 | 1.200 |
| truth/uav_03/p01_observe | 6 | scan | 30.000 | 10.000 | 11.700 | 11.397 | 1.700 |
| truth/uav_03/p01_observe | 7 | lane_change | 3.600 | 1.200 | 2.300 | 2.528 | 1.100 |
| truth/uav_03/p01_observe | 8 | scan | 30.000 | 10.000 | 11.600 | 11.434 | 1.600 |
| truth/uav_03/p01_observe | 9 | lane_change | 3.600 | 1.200 | 2.300 | 2.737 | 1.100 |
| truth/uav_03/p01_observe | 10 | scan | 30.000 | 10.000 | 12.100 | 12.495 | 2.100 |
| observation/uav_03/p01_observe | 2 | scan | 30.000 | 10.000 | 13.846 | 11.893 | 3.846 |
| observation/uav_03/p01_observe | 3 | lane_change | 3.600 | 1.200 | 2.400 | 2.527 | 1.200 |
| observation/uav_03/p01_observe | 4 | scan | 30.000 | 10.000 | 11.600 | 11.429 | 1.600 |
| observation/uav_03/p01_observe | 5 | lane_change | 3.600 | 1.200 | 2.300 | 2.646 | 1.100 |
| observation/uav_03/p01_observe | 6 | scan | 30.000 | 10.000 | 11.800 | 11.397 | 1.800 |
| observation/uav_03/p01_observe | 7 | lane_change | 3.600 | 1.200 | 2.200 | 2.528 | 1.000 |
| observation/uav_03/p01_observe | 8 | scan | 30.000 | 10.000 | 11.700 | 11.434 | 1.700 |
| observation/uav_03/p01_observe | 9 | lane_change | 3.600 | 1.200 | 2.300 | 2.737 | 1.100 |
| observation/uav_03/p01_observe | 10 | scan | 30.000 | 10.000 | 12.200 | 12.495 | 2.200 |
| truth/uav_01/p02_return | 2 | return | 45.572 | 15.191 | 18.502 | 17.569 | 3.311 |
| observation/uav_01/p02_return | 2 | return | 45.572 | 15.191 | 18.502 | 17.569 | 3.311 |
| truth/uav_02/p02_return | 2 | return | 45.572 | 15.191 | 18.502 | 17.455 | 3.311 |
| observation/uav_02/p02_return | 2 | return | 45.572 | 15.191 | 18.502 | 17.455 | 3.311 |
| truth/uav_03/p02_return | 2 | return | 45.572 | 15.191 | 18.502 | 17.519 | 3.311 |
| observation/uav_03/p02_return | 2 | return | 45.572 | 15.191 | 18.502 | 17.519 | 3.311 |

## 转角与终点减速邻域（覆盖层，不与主分类相加）

转角取内部航点周围 2 m 的连续三维邻域，名义时间取相邻两段各 2 m（受段长截断）除以名义速度；终点减速取最后航段终点周围 5 m 至最近点。这只是局部耗时诊断，不把整段增量归因于转弯或减速。覆盖层跨越相邻段，不能再加到上表总耗时。终点最近点至阶段结束的尾长单独保留，也不能全部声称为悬停。

| 通道/飞机/阶段 | 转角 seq | 角度 ° | 邻域实际 s | 邻域名义 s |
|---|---:|---:|---:|---:|
| truth/uav_01/p01_observe | 2 | 90.000 | 2.000 | 1.333 |
| truth/uav_01/p01_observe | 3 | 90.000 | 2.500 | 1.333 |
| truth/uav_01/p01_observe | 4 | 90.000 | 2.100 | 1.333 |
| truth/uav_01/p01_observe | 5 | 90.000 | 2.500 | 1.333 |
| truth/uav_01/p01_observe | 6 | 90.000 | 2.000 | 1.333 |
| truth/uav_01/p01_observe | 7 | 90.000 | 2.500 | 1.333 |
| truth/uav_01/p01_observe | 8 | 90.000 | 1.900 | 1.333 |
| truth/uav_01/p01_observe | 9 | 90.000 | 2.700 | 1.333 |
| observation/uav_01/p01_observe | 2 | 90.000 | 1.900 | 1.333 |
| observation/uav_01/p01_observe | 3 | 90.000 | 2.600 | 1.333 |
| observation/uav_01/p01_observe | 4 | 90.000 | 2.100 | 1.333 |
| observation/uav_01/p01_observe | 5 | 90.000 | 2.500 | 1.333 |
| observation/uav_01/p01_observe | 6 | 90.000 | 2.000 | 1.333 |
| observation/uav_01/p01_observe | 7 | 90.000 | 2.500 | 1.333 |
| observation/uav_01/p01_observe | 8 | 90.000 | 1.900 | 1.333 |
| observation/uav_01/p01_observe | 9 | 90.000 | 2.700 | 1.333 |
| truth/uav_02/p01_observe | 2 | 90.000 | 1.800 | 1.333 |
| truth/uav_02/p01_observe | 3 | 90.000 | 2.700 | 1.333 |
| truth/uav_02/p01_observe | 4 | 90.000 | 1.800 | 1.333 |
| truth/uav_02/p01_observe | 5 | 90.000 | 2.800 | 1.333 |
| truth/uav_02/p01_observe | 6 | 90.000 | 1.600 | 1.333 |
| truth/uav_02/p01_observe | 7 | 90.000 | 2.800 | 1.333 |
| truth/uav_02/p01_observe | 8 | 90.000 | 1.700 | 1.333 |
| truth/uav_02/p01_observe | 9 | 90.000 | 2.700 | 1.333 |
| observation/uav_02/p01_observe | 2 | 90.000 | 1.900 | 1.333 |
| observation/uav_02/p01_observe | 3 | 90.000 | 2.700 | 1.333 |
| observation/uav_02/p01_observe | 4 | 90.000 | 1.700 | 1.333 |
| observation/uav_02/p01_observe | 5 | 90.000 | 2.800 | 1.333 |
| observation/uav_02/p01_observe | 6 | 90.000 | 1.600 | 1.333 |
| observation/uav_02/p01_observe | 7 | 90.000 | 2.900 | 1.333 |
| observation/uav_02/p01_observe | 8 | 90.000 | 1.800 | 1.333 |
| observation/uav_02/p01_observe | 9 | 90.000 | 2.800 | 1.333 |
| truth/uav_03/p01_observe | 2 | 90.000 | 2.000 | 1.333 |
| truth/uav_03/p01_observe | 3 | 90.000 | 2.400 | 1.333 |
| truth/uav_03/p01_observe | 4 | 90.000 | 1.900 | 1.333 |
| truth/uav_03/p01_observe | 5 | 90.000 | 2.600 | 1.333 |
| truth/uav_03/p01_observe | 6 | 90.000 | 1.900 | 1.333 |
| truth/uav_03/p01_observe | 7 | 90.000 | 2.600 | 1.333 |
| truth/uav_03/p01_observe | 8 | 90.000 | 2.000 | 1.333 |
| truth/uav_03/p01_observe | 9 | 90.000 | 2.700 | 1.333 |
| observation/uav_03/p01_observe | 2 | 90.000 | 2.100 | 1.333 |
| observation/uav_03/p01_observe | 3 | 90.000 | 2.500 | 1.333 |
| observation/uav_03/p01_observe | 4 | 90.000 | 2.000 | 1.333 |
| observation/uav_03/p01_observe | 5 | 90.000 | 2.600 | 1.333 |
| observation/uav_03/p01_observe | 6 | 90.000 | 1.900 | 1.333 |
| observation/uav_03/p01_observe | 7 | 90.000 | 2.600 | 1.333 |
| observation/uav_03/p01_observe | 8 | 90.000 | 2.000 | 1.333 |
| observation/uav_03/p01_observe | 9 | 90.000 | 2.700 | 1.333 |

| 通道/飞机/阶段 | 末端 5 m 实际 s | 名义 s | 最近点至阶段结束 s |
|---|---:|---:|---:|
| truth/uav_01/p00_approach | 2.300 | 1.667 | 0.454 |
| observation/uav_01/p00_approach | 2.300 | 1.667 | 0.354 |
| truth/uav_02/p00_approach | 2.400 | 1.667 | 0.354 |
| observation/uav_02/p00_approach | 2.400 | 1.667 | 0.254 |
| truth/uav_03/p00_approach | 2.300 | 1.667 | 0.454 |
| observation/uav_03/p00_approach | 2.300 | 1.667 | 0.354 |
| truth/uav_01/p01_observe | 2.300 | 1.667 | 0.398 |
| observation/uav_01/p01_observe | 2.300 | 1.667 | 0.298 |
| truth/uav_02/p01_observe | 2.200 | 1.667 | 0.698 |
| observation/uav_02/p01_observe | 2.300 | 1.667 | 0.498 |
| truth/uav_03/p01_observe | 2.300 | 1.667 | 0.498 |
| observation/uav_03/p01_observe | 2.400 | 1.667 | 0.298 |
| truth/uav_01/p02_return | 2.200 | 1.667 | 0.094 |
| observation/uav_01/p02_return | 2.100 | 1.667 | 0.094 |
| truth/uav_02/p02_return | 2.200 | 1.667 | 0.094 |
| observation/uav_02/p02_return | 2.100 | 1.667 | 0.094 |
| truth/uav_03/p02_return | 2.200 | 1.667 | 0.094 |
| observation/uav_03/p02_return | 2.200 | 1.667 | 0.094 |

输入保护：53 个文件前后 SHA256 一致；旧运行及其分析目录未写入。
