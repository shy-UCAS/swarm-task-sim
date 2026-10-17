# D1 监视/时刻冲突诊断

数据源：
- `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261016T184726Z`
- `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261016T191411Z`

## 字段原始定义（取自源码）

- `core_times_s[a]`：`task_v07/unified/rehearsal.py::evaluate_solos` 取 `labels["agents"][a]["observed"]["core_event"]["t_s"]`，即 M1 在该单机预演轨迹上测得的**单机核心事件时刻**（事件按角色取名：transit/monitoring → `enter_warning_zone`，area_search → `scan_start`，close_observation → `observation_point_arrival`，feint → `enter_alert_zone`，intrusion → `enter_protected_zone`）。
- `completion_times_s[a]`：同一函数取 `run["time_us"][-1] / 1e6`（`execution_status == "completed"` 时，否则 null），即**单机预演轨迹的末帧时间**。
- 所以"撤离"区间 `completion_time < τ ≤ 末帧` 按定义宽度为 0，实际只可能出现前三个与"终点保持"，下文的分阶段计数会直接显示这一点。
- `closest_pair.t_s` 与 `frame_index` 来自 `task_v07/expansion/solo_spacing.py::minimum_spacing`，网格 10 Hz、`times` 为**联合时钟**；本机时刻 `τ = t_s − departure_delays_s[a]`，`τ<0` 段 `np.interp` 取首帧位形（起飞前等待）。

## family_s15_79c93b22d09e8a7a_ext_002_regular

- attempt：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261016T191411Z`
- 轮数：5

| 轮 | candidate_index | rehearsal.json | timing_selection.json | category | 预演耗时(mtime估) | 时刻耗时(mtime估) |
|---|---|---|---|---|---|---|
| geometry_00 | 414 | True | True | timing_conflict | 272.116 | 0.322 |
| geometry_01 | 806 | True | True | timing_conflict | 487.947 | 0.305 |
| geometry_02 | 467 | True | True | timing_conflict | 442.065 | 0.309 |
| geometry_03 | 708 | True | True | timing_conflict | 183.451 | 0.2 |
| geometry_04 | 859 | True | True | timing_conflict | 456.633 | 0.318 |

> 预演耗时 = mtime(rehearsal.json) − mtime(planning_checks.json)；时刻耗时 = mtime(timing_selection.json) − mtime(rehearsal.json)。这是 **mtime 估计**，不是被测代码的埋点。

### 每次被拒 draw 的机对与阶段

| 轮 | mode | draw | 机对 | minimum_m | t_s | τ（本机） | 阶段 | 同组 | 到各自组目标中心 m |
|---|---|---:|---|---:|---:|---|---|---|---|
| geometry_00 | synchronous | 0 | uav_03+uav_05 | 0.003614 | 972.8 | uav_03=951.7；uav_05=945.5 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 1 | uav_03+uav_05 | 0.003614 | 976.7 | uav_03=951.7；uav_05=947.7 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 2 | uav_03+uav_05 | 0.003614 | 977.0 | uav_03=951.7；uav_05=951.3 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 3 | uav_03+uav_05 | 0.003614 | 976.8 | uav_03=951.7；uav_05=951.2 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 4 | uav_03+uav_05 | 0.003614 | 972.9 | uav_03=951.7；uav_05=944.4 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 5 | uav_03+uav_05 | 0.003614 | 977.9 | uav_03=951.7；uav_05=950.0 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 6 | uav_03+uav_05 | 0.003614 | 973.6 | uav_03=951.7；uav_05=945.1 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 7 | uav_03+uav_05 | 0.003614 | 977.1 | uav_03=951.7；uav_05=951.5 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 8 | uav_03+uav_05 | 0.003614 | 976.9 | uav_03=951.7；uav_05=952.3 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 9 | uav_03+uav_05 | 0.003614 | 976.8 | uav_03=951.7；uav_05=952.8 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 10 | uav_03+uav_05 | 0.003614 | 975.8 | uav_03=951.7；uav_05=946.5 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 11 | uav_03+uav_05 | 0.003614 | 973.1 | uav_03=951.7；uav_05=943.5 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 12 | uav_03+uav_05 | 0.003614 | 976.6 | uav_03=951.7；uav_05=952.7 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 13 | uav_03+uav_05 | 0.003614 | 977.9 | uav_03=951.7；uav_05=948.8 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 14 | uav_03+uav_05 | 0.003614 | 975.7 | uav_03=951.7；uav_05=951.9 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 15 | uav_03+uav_05 | 0.003614 | 974.9 | uav_03=951.7；uav_05=945.3 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 16 | uav_03+uav_05 | 0.003614 | 976.3 | uav_03=951.7；uav_05=949.6 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 17 | uav_03+uav_05 | 0.003614 | 976.2 | uav_03=951.7；uav_05=948.0 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 18 | uav_03+uav_05 | 0.003614 | 977.3 | uav_03=951.7；uav_05=953.1 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | synchronous | 19 | uav_03+uav_05 | 0.003614 | 972.7 | uav_03=951.7；uav_05=947.6 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 0 | uav_03+uav_05 | 0.003614 | 1080.0 | uav_03=951.7；uav_05=1012.1 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 1 | uav_03+uav_05 | 0.003614 | 1161.4 | uav_03=1091.3；uav_05=934.8 | 终点保持/作业 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 2 | uav_03+uav_05 | 0.003614 | 1130.3 | uav_03=1021.3；uav_05=934.8 | 终点保持/作业 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 3 | uav_03+uav_05 | 0.003614 | 1088.1 | uav_03=1062.2；uav_05=934.8 | 终点保持/作业 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 4 | uav_03+uav_05 | 0.003614 | 1038.6 | uav_03=951.7；uav_05=1010.6 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 5 | uav_03+uav_05 | 0.003614 | 1026.4 | uav_03=1005.7；uav_05=934.8 | 终点保持/作业 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 6 | uav_03+uav_05 | 0.003614 | 1063.3 | uav_03=951.7；uav_05=952.5 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 7 | uav_03+uav_05 | 0.003614 | 1130.5 | uav_03=951.7；uav_05=1104.8 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 8 | uav_03+uav_05 | 0.003614 | 1092.4 | uav_03=987.2；uav_05=934.8 | 终点保持/作业 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 9 | uav_03+uav_05 | 0.003614 | 1099.5 | uav_03=1078.8；uav_05=934.8 | 终点保持/作业 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 10 | uav_03+uav_05 | 0.003614 | 977.2 | uav_03=951.7；uav_05=948.9 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 11 | uav_03+uav_05 | 0.003614 | 1098.3 | uav_03=1075.0；uav_05=934.8 | 终点保持/作业 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 12 | uav_03+uav_05 | 0.003614 | 1066.7 | uav_03=951.7；uav_05=952.7 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 13 | uav_03+uav_05 | 0.003614 | 1040.3 | uav_03=951.7；uav_05=1016.3 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 14 | uav_03+uav_05 | 0.003614 | 1199.4 | uav_03=951.7；uav_05=1028.0 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 15 | uav_03+uav_05 | 0.003614 | 1049.6 | uav_03=951.7；uav_05=1025.5 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 16 | uav_03+uav_05 | 0.003614 | 1180.4 | uav_03=1155.0；uav_05=934.8 | 终点保持/作业 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 17 | uav_03+uav_05 | 0.003614 | 1109.0 | uav_03=1010.4；uav_05=934.8 | 终点保持/作业 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 18 | uav_03+uav_05 | 0.003614 | 1034.7 | uav_03=951.7；uav_05=1007.9 | 作业/终点保持 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_00 | sequential | 19 | uav_03+uav_05 | 0.003614 | 1026.7 | uav_03=1004.6；uav_05=934.8 | 终点保持/作业 | True | uav_03=1496.2；uav_05=1496.2 |
| geometry_01 | synchronous | 0 | uav_02+uav_04 | 0.008170 | 2347.5 | uav_02=2328.3；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 1 | uav_02+uav_04 | 0.008170 | 2349.3 | uav_02=2329.1；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 2 | uav_02+uav_04 | 0.008170 | 2349.5 | uav_02=2330.5；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 3 | uav_02+uav_04 | 0.008170 | 2349.4 | uav_02=2331.7；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 4 | uav_02+uav_04 | 0.008170 | 2346.3 | uav_02=2328.8；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 5 | uav_02+uav_04 | 0.008170 | 2347.2 | uav_02=2328.1；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 6 | uav_02+uav_04 | 0.008170 | 2345.6 | uav_02=2327.2；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 7 | uav_02+uav_04 | 0.008170 | 2348.0 | uav_02=2332.2；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 8 | uav_02+uav_04 | 0.008170 | 2345.1 | uav_02=2326.7；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 9 | uav_02+uav_04 | 0.008170 | 2346.8 | uav_02=2329.4；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 10 | uav_02+uav_04 | 0.008170 | 2348.8 | uav_02=2332.7；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 11 | uav_02+uav_04 | 0.008170 | 2345.9 | uav_02=2329.4；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 12 | uav_02+uav_04 | 0.008170 | 2345.5 | uav_02=2327.1；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 13 | uav_02+uav_04 | 0.008170 | 2347.4 | uav_02=2330.2；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 14 | uav_02+uav_04 | 0.008170 | 2345.9 | uav_02=2329.7；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 15 | uav_02+uav_04 | 0.008170 | 2347.3 | uav_02=2328.8；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 16 | uav_02+uav_04 | 0.008170 | 2349.4 | uav_02=2333.4；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 17 | uav_02+uav_04 | 0.008170 | 2348.5 | uav_02=2331.0；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 18 | uav_02+uav_04 | 0.008170 | 2350.5 | uav_02=2329.0；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | synchronous | 19 | uav_02+uav_04 | 0.008170 | 2350.3 | uav_02=2331.9；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | sequential | 0 | uav_02+uav_04 | 0.008170 | 2346.1 | uav_02=2284.6；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | sequential | 1 | uav_02+uav_03 | 0.006446 | 2391.3 | uav_02=2261.1；uav_03=2324.7 | 作业/终点保持 | True | uav_02=1299.4；uav_03=1299.4 |
| geometry_01 | sequential | 2 | uav_02+uav_04 | 0.008170 | 2518.8 | uav_02=2500.7；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | sequential | 3 | uav_02+uav_03 | 0.006446 | 2460.1 | uav_02=2261.1；uav_03=2437.7 | 作业/终点保持 | True | uav_02=1299.4；uav_03=1299.4 |
| geometry_01 | sequential | 4 | uav_02+uav_03 | 0.006446 | 2463.4 | uav_02=2261.1；uav_03=2380.0 | 作业/终点保持 | True | uav_02=1299.4；uav_03=1299.4 |
| geometry_01 | sequential | 5 | uav_02+uav_04 | 0.008170 | 2412.0 | uav_02=2391.5；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | sequential | 6 | uav_02+uav_04 | 0.008170 | 2346.5 | uav_02=2330.6；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | sequential | 7 | uav_02+uav_04 | 0.008170 | 2438.9 | uav_02=2262.2；uav_04=2328.0 | 作业/终点保持 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | sequential | 8 | uav_02+uav_03 | 0.006446 | 2407.0 | uav_02=2261.1；uav_03=2305.3 | 作业/终点保持 | True | uav_02=1299.4；uav_03=1299.4 |
| geometry_01 | sequential | 9 | uav_02+uav_03 | 0.006446 | 2506.3 | uav_02=2261.1；uav_03=2489.1 | 作业/终点保持 | True | uav_02=1299.4；uav_03=1299.4 |
| geometry_01 | sequential | 10 | uav_02+uav_04 | 0.008170 | 2414.1 | uav_02=2393.2；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | sequential | 11 | uav_02+uav_04 | 0.008170 | 2396.2 | uav_02=2375.7；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | sequential | 12 | uav_02+uav_04 | 0.008170 | 2513.6 | uav_02=2497.1；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | sequential | 13 | uav_02+uav_03 | 0.006446 | 2392.5 | uav_02=2261.1；uav_03=2307.4 | 作业/终点保持 | True | uav_02=1299.4；uav_03=1299.4 |
| geometry_01 | sequential | 14 | uav_02+uav_04 | 0.008170 | 2410.1 | uav_02=2388.9；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | sequential | 15 | uav_02+uav_03 | 0.006446 | 2403.7 | uav_02=2261.1；uav_03=2309.3 | 作业/终点保持 | True | uav_02=1299.4；uav_03=1299.4 |
| geometry_01 | sequential | 16 | uav_02+uav_03 | 0.006446 | 2417.7 | uav_02=2261.1；uav_03=2395.8 | 作业/终点保持 | True | uav_02=1299.4；uav_03=1299.4 |
| geometry_01 | sequential | 17 | uav_02+uav_04 | 0.008170 | 2496.6 | uav_02=2478.1；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_01 | sequential | 18 | uav_02+uav_03 | 0.006446 | 2400.0 | uav_02=2261.1；uav_03=2320.5 | 作业/终点保持 | True | uav_02=1299.4；uav_03=1299.4 |
| geometry_01 | sequential | 19 | uav_02+uav_04 | 0.008170 | 2344.9 | uav_02=2326.8；uav_04=2327.9 | 终点保持/作业 | True | uav_02=1299.3；uav_04=1299.3 |
| geometry_02 | synchronous | 0 | uav_02+uav_03 | 0.014631 | 2610.5 | uav_02=2592.2；uav_03=2589.6 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 1 | uav_02+uav_03 | 0.014631 | 2611.5 | uav_02=2592.2；uav_03=2586.7 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 2 | uav_02+uav_03 | 0.014631 | 2610.3 | uav_02=2592.2；uav_03=2585.2 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 3 | uav_02+uav_03 | 0.014631 | 2609.0 | uav_02=2592.2；uav_03=2584.1 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 4 | uav_02+uav_03 | 0.014631 | 2608.8 | uav_02=2592.2；uav_03=2587.8 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 5 | uav_02+uav_03 | 0.014631 | 2610.4 | uav_02=2592.2；uav_03=2584.4 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 6 | uav_02+uav_03 | 0.014631 | 2609.7 | uav_02=2592.2；uav_03=2588.0 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 7 | uav_02+uav_03 | 0.014631 | 2607.1 | uav_02=2592.2；uav_03=2581.9 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 8 | uav_02+uav_03 | 0.014631 | 2609.7 | uav_02=2592.2；uav_03=2584.7 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 9 | uav_02+uav_03 | 0.014631 | 2608.7 | uav_02=2592.2；uav_03=2583.8 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 10 | uav_02+uav_03 | 0.014631 | 2607.4 | uav_02=2592.2；uav_03=2583.5 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 11 | uav_02+uav_03 | 0.014631 | 2607.8 | uav_02=2592.2；uav_03=2586.6 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 12 | uav_02+uav_03 | 0.014631 | 2609.7 | uav_02=2592.2；uav_03=2585.0 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 13 | uav_02+uav_03 | 0.014631 | 2608.5 | uav_02=2592.2；uav_03=2582.5 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 14 | uav_02+uav_03 | 0.014631 | 2607.5 | uav_02=2592.2；uav_03=2583.7 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 15 | uav_02+uav_03 | 0.014631 | 2609.8 | uav_02=2592.2；uav_03=2586.8 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 16 | uav_02+uav_03 | 0.014631 | 2607.3 | uav_02=2592.2；uav_03=2582.9 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 17 | uav_02+uav_03 | 0.014631 | 2608.8 | uav_02=2592.2；uav_03=2584.5 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 18 | uav_02+uav_03 | 0.014631 | 2612.8 | uav_02=2592.2；uav_03=2587.4 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | synchronous | 19 | uav_02+uav_03 | 0.014631 | 2609.7 | uav_02=2592.2；uav_03=2588.9 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | sequential | 0 | uav_01+uav_06 | 0.020225 | 1584.8 | uav_01=1494.7；uav_06=1544.6 | 作业/终点保持 | True | uav_01=1173.6；uav_06=1173.6 |
| geometry_02 | sequential | 1 | uav_03+uav_05 | 0.013904 | 2715.9 | uav_03=2646.0；uav_05=2487.8 | 终点保持/作业 | True | uav_03=1396.7；uav_05=1396.7 |
| geometry_02 | sequential | 2 | uav_03+uav_05 | 0.013904 | 2684.8 | uav_03=2576.0；uav_05=2487.8 | 终点保持/作业 | True | uav_03=1396.7；uav_05=1396.7 |
| geometry_02 | sequential | 3 | uav_03+uav_05 | 0.013904 | 2642.6 | uav_03=2616.9；uav_05=2487.8 | 终点保持/作业 | True | uav_03=1396.7；uav_05=1396.7 |
| geometry_02 | sequential | 4 | uav_02+uav_03 | 0.014631 | 2793.6 | uav_02=2592.2；uav_03=2706.9 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | sequential | 5 | uav_03+uav_05 | 0.013904 | 2580.9 | uav_03=2560.4；uav_05=2487.8 | 终点保持/作业 | True | uav_03=1396.7；uav_05=1396.7 |
| geometry_02 | sequential | 6 | uav_01+uav_06 | 0.020225 | 1572.4 | uav_01=1494.7；uav_06=1533.5 | 作业/终点保持 | True | uav_01=1173.6；uav_06=1173.6 |
| geometry_02 | sequential | 7 | uav_02+uav_03 | 0.014631 | 2768.0 | uav_02=2592.2；uav_03=2589.4 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | sequential | 8 | uav_02+uav_03 | 0.014631 | 2737.2 | uav_02=2592.2；uav_03=2632.2 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | sequential | 9 | uav_03+uav_05 | 0.013904 | 2654.0 | uav_03=2633.5；uav_05=2487.8 | 终点保持/作业 | True | uav_03=1396.7；uav_05=1396.7 |
| geometry_02 | sequential | 10 | uav_02+uav_03 | 0.014631 | 2612.2 | uav_02=2592.2；uav_03=2586.9 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | sequential | 11 | uav_03+uav_05 | 0.013904 | 2652.8 | uav_03=2629.7；uav_05=2487.8 | 终点保持/作业 | True | uav_03=1396.7；uav_05=1396.7 |
| geometry_02 | sequential | 12 | uav_01+uav_06 | 0.020225 | 1586.3 | uav_01=1494.7；uav_06=1543.2 | 作业/终点保持 | True | uav_01=1173.6；uav_06=1173.6 |
| geometry_02 | sequential | 13 | uav_02+uav_03 | 0.014631 | 2722.7 | uav_02=2592.2；uav_03=2634.3 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | sequential | 14 | uav_02+uav_05 | 0.023329 | 2660.8 | uav_02=2640.5；uav_05=2487.9 | 终点保持/作业 | True | uav_02=1396.6；uav_05=1396.6 |
| geometry_02 | sequential | 15 | uav_02+uav_03 | 0.014631 | 2733.9 | uav_02=2592.2；uav_03=2636.2 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | sequential | 16 | uav_03+uav_05 | 0.013904 | 2734.9 | uav_03=2709.7；uav_05=2487.8 | 终点保持/作业 | True | uav_03=1396.7；uav_05=1396.7 |
| geometry_02 | sequential | 17 | uav_03+uav_05 | 0.013904 | 2663.5 | uav_03=2565.1；uav_05=2487.8 | 终点保持/作业 | True | uav_03=1396.7；uav_05=1396.7 |
| geometry_02 | sequential | 18 | uav_02+uav_03 | 0.014631 | 2730.2 | uav_02=2592.2；uav_03=2647.4 | 作业/终点保持 | True | uav_02=1396.7；uav_03=1396.7 |
| geometry_02 | sequential | 19 | uav_03+uav_05 | 0.013904 | 2581.2 | uav_03=2559.3；uav_05=2487.8 | 终点保持/作业 | True | uav_03=1396.7；uav_05=1396.7 |
| geometry_03 | synchronous | 0 | uav_02+uav_03 | 0.007207 | 1208.5 | uav_02=1190.2；uav_03=1188.3 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 1 | uav_02+uav_03 | 0.007207 | 1209.5 | uav_02=1190.2；uav_03=1185.4 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 2 | uav_02+uav_03 | 0.007207 | 1208.3 | uav_02=1190.2；uav_03=1183.9 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 3 | uav_02+uav_03 | 0.007207 | 1207.0 | uav_02=1190.2；uav_03=1182.8 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 4 | uav_02+uav_03 | 0.007207 | 1206.8 | uav_02=1190.2；uav_03=1186.5 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 5 | uav_02+uav_03 | 0.007207 | 1208.4 | uav_02=1190.2；uav_03=1183.1 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 6 | uav_02+uav_03 | 0.007207 | 1207.7 | uav_02=1190.2；uav_03=1186.7 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 7 | uav_02+uav_03 | 0.007207 | 1205.1 | uav_02=1190.2；uav_03=1180.6 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 8 | uav_02+uav_03 | 0.007207 | 1207.7 | uav_02=1190.2；uav_03=1183.4 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 9 | uav_02+uav_03 | 0.007207 | 1206.7 | uav_02=1190.2；uav_03=1182.5 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 10 | uav_02+uav_03 | 0.007207 | 1205.4 | uav_02=1190.2；uav_03=1182.2 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 11 | uav_02+uav_03 | 0.007207 | 1205.8 | uav_02=1190.2；uav_03=1185.3 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 12 | uav_02+uav_03 | 0.007207 | 1207.7 | uav_02=1190.2；uav_03=1183.7 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 13 | uav_02+uav_03 | 0.007207 | 1206.5 | uav_02=1190.2；uav_03=1181.2 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 14 | uav_02+uav_03 | 0.007207 | 1205.5 | uav_02=1190.2；uav_03=1182.4 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 15 | uav_02+uav_03 | 0.007207 | 1207.8 | uav_02=1190.2；uav_03=1185.5 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 16 | uav_02+uav_03 | 0.007207 | 1205.3 | uav_02=1190.2；uav_03=1181.6 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 17 | uav_02+uav_03 | 0.007207 | 1206.8 | uav_02=1190.2；uav_03=1183.2 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 18 | uav_02+uav_03 | 0.007207 | 1210.8 | uav_02=1190.2；uav_03=1186.1 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | synchronous | 19 | uav_02+uav_03 | 0.007207 | 1207.7 | uav_02=1190.2；uav_03=1187.6 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 0 | uav_02+uav_04 | 0.010215 | 1251.9 | uav_02=1191.3；uav_04=1230.0 | 作业/终点保持 | True | uav_02=1391.2；uav_04=1391.2 |
| geometry_03 | sequential | 1 | uav_02+uav_03 | 0.007207 | 1319.5 | uav_02=1190.2；uav_03=1250.3 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 2 | uav_02+uav_04 | 0.010215 | 1355.5 | uav_02=1338.3；uav_04=1160.9 | 终点保持/作业 | True | uav_02=1391.2；uav_04=1391.2 |
| geometry_03 | sequential | 3 | uav_02+uav_03 | 0.007207 | 1388.3 | uav_02=1190.2；uav_03=1363.3 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 4 | uav_02+uav_03 | 0.007207 | 1391.6 | uav_02=1190.2；uav_03=1305.6 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 5 | uav_02+uav_03 | 0.007207 | 1209.8 | uav_02=1190.2；uav_03=1190.0 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 6 | uav_02+uav_04 | 0.010215 | 1206.3 | uav_02=1191.3；uav_04=1184.0 | 作业/终点保持 | True | uav_02=1391.2；uav_04=1391.2 |
| geometry_03 | sequential | 7 | uav_02+uav_03 | 0.007207 | 1366.0 | uav_02=1190.2；uav_03=1188.1 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 8 | uav_02+uav_03 | 0.007207 | 1335.2 | uav_02=1190.2；uav_03=1230.9 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 9 | uav_02+uav_03 | 0.007207 | 1434.5 | uav_02=1190.2；uav_03=1414.7 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 10 | uav_02+uav_03 | 0.007207 | 1210.2 | uav_02=1190.2；uav_03=1185.6 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 11 | uav_02+uav_03 | 0.007207 | 1209.8 | uav_02=1190.2；uav_03=1187.4 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 12 | uav_02+uav_04 | 0.010215 | 1350.3 | uav_02=1334.7；uav_04=1160.9 | 终点保持/作业 | True | uav_02=1391.2；uav_04=1391.2 |
| geometry_03 | sequential | 13 | uav_02+uav_03 | 0.007207 | 1320.7 | uav_02=1190.2；uav_03=1233.0 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 14 | uav_02+uav_04 | 0.010215 | 1246.8 | uav_02=1226.5；uav_04=1160.9 | 终点保持/作业 | True | uav_02=1391.2；uav_04=1391.2 |
| geometry_03 | sequential | 15 | uav_02+uav_03 | 0.007207 | 1331.9 | uav_02=1190.2；uav_03=1234.9 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 16 | uav_02+uav_03 | 0.007207 | 1345.9 | uav_02=1190.2；uav_03=1321.4 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 17 | uav_02+uav_04 | 0.010215 | 1333.3 | uav_02=1315.7；uav_04=1160.9 | 终点保持/作业 | True | uav_02=1391.2；uav_04=1391.2 |
| geometry_03 | sequential | 18 | uav_02+uav_03 | 0.007207 | 1328.2 | uav_02=1190.2；uav_03=1246.1 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_03 | sequential | 19 | uav_02+uav_03 | 0.007207 | 1207.4 | uav_02=1190.2；uav_03=1186.2 | 作业/终点保持 | True | uav_02=1391.1；uav_03=1391.1 |
| geometry_04 | synchronous | 0 | uav_03+uav_04 | 0.004411 | 2048.9 | uav_03=2027.4；uav_04=2022.3 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 1 | uav_03+uav_04 | 0.004411 | 2052.8 | uav_03=2027.4；uav_04=2024.4 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 2 | uav_03+uav_04 | 0.004411 | 2053.1 | uav_03=2027.4；uav_04=2024.5 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 3 | uav_03+uav_04 | 0.004411 | 2052.9 | uav_03=2027.4；uav_04=2024.4 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 4 | uav_03+uav_04 | 0.004411 | 2049.0 | uav_03=2027.4；uav_04=2023.6 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 5 | uav_03+uav_04 | 0.004411 | 2054.0 | uav_03=2027.4；uav_04=2027.7 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 6 | uav_03+uav_04 | 0.004411 | 2049.7 | uav_03=2027.4；uav_04=2025.0 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 7 | uav_03+uav_04 | 0.004411 | 2053.2 | uav_03=2027.4；uav_04=2026.1 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 8 | uav_03+uav_04 | 0.004411 | 2053.0 | uav_03=2027.4；uav_04=2028.8 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 9 | uav_03+uav_04 | 0.004411 | 2052.9 | uav_03=2027.4；uav_04=2027.0 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 10 | uav_03+uav_04 | 0.004411 | 2051.9 | uav_03=2027.4；uav_04=2024.0 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 11 | uav_03+uav_04 | 0.004411 | 2049.2 | uav_03=2027.4；uav_04=2024.2 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 12 | uav_03+uav_04 | 0.004411 | 2052.7 | uav_03=2027.4；uav_04=2028.1 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 13 | uav_03+uav_04 | 0.004411 | 2054.0 | uav_03=2027.4；uav_04=2027.5 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 14 | uav_03+uav_04 | 0.004411 | 2051.8 | uav_03=2027.4；uav_04=2026.8 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 15 | uav_03+uav_04 | 0.004411 | 2051.0 | uav_03=2027.4；uav_04=2024.6 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 16 | uav_03+uav_04 | 0.004411 | 2052.4 | uav_03=2027.4；uav_04=2023.9 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 17 | uav_03+uav_04 | 0.004411 | 2052.3 | uav_03=2027.4；uav_04=2024.7 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 18 | uav_03+uav_04 | 0.004411 | 2053.4 | uav_03=2027.4；uav_04=2023.8 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | synchronous | 19 | uav_03+uav_04 | 0.004411 | 2048.8 | uav_03=2027.4；uav_04=2019.4 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 0 | uav_03+uav_04 | 0.004411 | 2156.1 | uav_03=2027.4；uav_04=2130.9 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 1 | uav_03+uav_04 | 0.004411 | 2097.9 | uav_03=2027.4；uav_04=2072.1 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 2 | uav_03+uav_04 | 0.004411 | 2193.0 | uav_03=2083.6；uav_04=1995.1 | 终点保持/作业 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 3 | uav_03+uav_04 | 0.004411 | 2103.4 | uav_03=2077.1；uav_04=1995.1 | 终点保持/作业 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 4 | uav_03+uav_04 | 0.004411 | 2143.0 | uav_03=2055.7；uav_04=1995.1 | 终点保持/作业 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 5 | uav_03+uav_04 | 0.004411 | 2086.2 | uav_03=2065.1；uav_04=1995.1 | 终点保持/作业 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 6 | uav_03+uav_04 | 0.004411 | 2139.4 | uav_03=2027.4；uav_04=2113.8 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 7 | uav_03+uav_04 | 0.004411 | 2206.6 | uav_03=2027.4；uav_04=2088.7 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 8 | uav_03+uav_04 | 0.004411 | 2133.0 | uav_03=2027.4；uav_04=2105.3 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 9 | uav_03+uav_04 | 0.004411 | 2098.0 | uav_03=2076.9；uav_04=1995.1 | 终点保持/作业 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 10 | uav_03+uav_04 | 0.004411 | 2088.3 | uav_03=2062.4；uav_04=1995.1 | 终点保持/作业 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 11 | uav_03+uav_04 | 0.004411 | 2070.4 | uav_03=2046.7；uav_04=1995.1 | 终点保持/作业 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 12 | uav_03+uav_04 | 0.004411 | 2187.8 | uav_03=2072.4；uav_04=1995.1 | 终点保持/作业 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 13 | uav_03+uav_04 | 0.004411 | 2210.1 | uav_03=2121.1；uav_04=1995.1 | 终点保持/作业 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 14 | uav_03+uav_04 | 0.004411 | 2275.5 | uav_03=2027.4；uav_04=2186.3 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 15 | uav_03+uav_04 | 0.004411 | 2210.2 | uav_03=2111.9；uav_04=1995.1 | 终点保持/作业 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 16 | uav_03+uav_04 | 0.004411 | 2092.8 | uav_03=2067.0；uav_04=1995.1 | 终点保持/作业 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 17 | uav_03+uav_04 | 0.004411 | 2170.8 | uav_03=2071.8；uav_04=1995.1 | 终点保持/作业 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 18 | uav_03+uav_04 | 0.004411 | 2142.3 | uav_03=2058.9；uav_04=1995.1 | 终点保持/作业 | True | uav_03=1303.0；uav_04=1303.0 |
| geometry_04 | sequential | 19 | uav_03+uav_04 | 0.004411 | 2049.9 | uav_03=2027.4；uav_04=2025.9 | 作业/终点保持 | True | uav_03=1303.0；uav_04=1303.0 |

> 阶段判定：τ<0 起飞前等待；0≤τ<core_time 进场；core_time≤τ≤completion_time 作业；completion_time<τ≤末帧 撤离；τ>末帧 终点保持。core/completion 取自 `rehearsal.json`。冲突点取两机在 t_s 处位移后位置的**中点**，距离按场景平面（ENU 的 x、y）计算。

### 每轮 × 每 mode 的主导组合

| 轮 | mode | draw 数 | 主导（机对 → 阶段组合） | 次数 | 判定 |
|---|---|---:|---|---:|---|
| geometry_00 | sequential | 20 | uav_03+uav_05 → 作业+终点保持 | 10/20 | 分散 |
| geometry_00 | synchronous | 20 | uav_03+uav_05 → 作业+终点保持 | 20/20 | 结构性（与时刻无关） |
| geometry_01 | sequential | 20 | uav_02+uav_04 → 终点保持+作业 | 10/20 | 分散 |
| geometry_01 | synchronous | 20 | uav_02+uav_04 → 终点保持+作业 | 20/20 | 结构性（与时刻无关） |
| geometry_02 | sequential | 20 | uav_03+uav_05 → 终点保持+作业 | 9/20 | 分散 |
| geometry_02 | synchronous | 20 | uav_02+uav_03 → 作业+终点保持 | 20/20 | 结构性（与时刻无关） |
| geometry_03 | sequential | 20 | uav_02+uav_03 → 作业+终点保持 | 14/20 | 分散 |
| geometry_03 | synchronous | 20 | uav_02+uav_03 → 作业+终点保持 | 20/20 | 结构性（与时刻无关） |
| geometry_04 | sequential | 20 | uav_03+uav_04 → 终点保持+作业 | 13/20 | 分散 |
| geometry_04 | synchronous | 20 | uav_03+uav_04 → 作业+终点保持 | 20/20 | 结构性（与时刻无关） |

> 判定规则：同一机对 + 同一阶段组合在 20 次 draw 中出现 ≥15 次记为结构性。

### 冲突机对的空间量（不含时间）

| 轮 | 机对 | 两轨迹空间最近距离 m | 起点间距 m | 终点间距 m | 同组 |
|---|---|---:|---:|---:|---|
| geometry_02 | uav_01+uav_06 | 0.018858 | 77.234 | 0.053 | True |
| geometry_01 | uav_02+uav_03 | 0.016326 | 38.617 | 0.053 | True |
| geometry_01 | uav_02+uav_04 | 0.077263 | 57.926 | 0.008 | True |
| geometry_02 | uav_02+uav_05 | 0.056673 | 77.234 | 0.023 | True |
| geometry_04 | uav_03+uav_04 | 0.082579 | 19.309 | 0.004 | True |
| geometry_00 | uav_03+uav_05 | 0.046933 | 38.617 | 0.004 | True |

> 三条量均按 10 Hz 帧、两轨迹各取 5 帧降采样后在降采样点集上取最小值。

## family_s15_79c93b22d09e8a7a_ext_004_regular

- attempt：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261016T191411Z`
- 轮数：5

| 轮 | candidate_index | rehearsal.json | timing_selection.json | category | 预演耗时(mtime估) | 时刻耗时(mtime估) |
|---|---|---|---|---|---|---|
| geometry_00 | 615 | True | True | timing_conflict | 67.61 | 0.153 |
| geometry_01 | 799 | True | True | timing_conflict | 194.987 | 0.302 |
| geometry_02 | 740 | True | True | timing_conflict | 174.28 | 0.276 |
| geometry_03 | 826 | True | True | timing_conflict | 327.592 | 0.414 |
| geometry_04 | 167 | True | True | timing_conflict | 168.47 | 0.275 |

> 预演耗时 = mtime(rehearsal.json) − mtime(planning_checks.json)；时刻耗时 = mtime(timing_selection.json) − mtime(rehearsal.json)。这是 **mtime 估计**，不是被测代码的埋点。

### 每次被拒 draw 的机对与阶段

| 轮 | mode | draw | 机对 | minimum_m | t_s | τ（本机） | 阶段 | 同组 | 到各自组目标中心 m |
|---|---|---:|---|---:|---:|---|---|---|---|
| geometry_00 | synchronous | 0 | uav_01+uav_06 | 0.008211 | 1293.3 | uav_01=1255.2；uav_06=1258.8 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 1 | uav_01+uav_06 | 0.008211 | 1293.1 | uav_01=1255.2；uav_06=1256.7 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 2 | uav_01+uav_06 | 0.008211 | 1290.8 | uav_01=1255.2；uav_06=1254.1 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 3 | uav_01+uav_06 | 0.008211 | 1291.8 | uav_01=1255.2；uav_06=1252.6 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 4 | uav_01+uav_06 | 0.008211 | 1291.5 | uav_01=1255.2；uav_06=1256.3 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 5 | uav_01+uav_06 | 0.008211 | 1294.3 | uav_01=1255.2；uav_06=1256.1 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 6 | uav_01+uav_06 | 0.008211 | 1290.5 | uav_01=1255.2；uav_06=1251.4 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 7 | uav_01+uav_06 | 0.008211 | 1288.4 | uav_01=1255.2；uav_06=1249.6 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 8 | uav_01+uav_06 | 0.008211 | 1289.9 | uav_01=1255.2；uav_06=1254.3 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 9 | uav_01+uav_06 | 0.008211 | 1293.1 | uav_01=1255.2；uav_06=1254.5 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 10 | uav_01+uav_06 | 0.008211 | 1293.8 | uav_01=1255.2；uav_06=1253.8 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 11 | uav_01+uav_06 | 0.008211 | 1289.6 | uav_01=1255.2；uav_06=1252.6 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 12 | uav_01+uav_06 | 0.008211 | 1292.3 | uav_01=1255.2；uav_06=1256.3 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 13 | uav_01+uav_06 | 0.008211 | 1289.4 | uav_01=1255.2；uav_06=1251.1 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 14 | uav_01+uav_06 | 0.008211 | 1290.0 | uav_01=1255.2；uav_06=1249.9 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 15 | uav_01+uav_06 | 0.008211 | 1292.3 | uav_01=1255.2；uav_06=1252.8 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 16 | uav_01+uav_06 | 0.008211 | 1290.7 | uav_01=1255.2；uav_06=1253.3 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 17 | uav_01+uav_06 | 0.008211 | 1292.5 | uav_01=1255.2；uav_06=1255.5 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 18 | uav_01+uav_06 | 0.008211 | 1291.2 | uav_01=1255.2；uav_06=1252.0 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | synchronous | 19 | uav_01+uav_06 | 0.008211 | 1293.4 | uav_01=1255.2；uav_06=1256.5 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 0 | uav_01+uav_06 | 0.008211 | 1353.8 | uav_01=1255.2；uav_06=1319.3 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 1 | uav_01+uav_06 | 0.008211 | 1350.1 | uav_01=1255.2；uav_06=1310.3 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 2 | uav_01+uav_06 | 0.008211 | 1376.9 | uav_01=1255.2；uav_06=1338.5 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 3 | uav_01+uav_06 | 0.008211 | 1349.1 | uav_01=1255.2；uav_06=1313.1 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 4 | uav_01+uav_06 | 0.008211 | 1344.2 | uav_01=1310.9；uav_06=1247.6 | 终点保持/作业 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 5 | uav_01+uav_06 | 0.008211 | 1327.6 | uav_01=1289.7；uav_06=1247.6 | 终点保持/作业 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 6 | uav_01+uav_06 | 0.008211 | 1347.0 | uav_01=1255.2；uav_06=1311.6 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 7 | uav_01+uav_06 | 0.008211 | 1333.9 | uav_01=1298.4；uav_06=1247.6 | 终点保持/作业 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 8 | uav_01+uav_06 | 0.008211 | 1339.5 | uav_01=1255.2；uav_06=1300.6 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 9 | uav_01+uav_06 | 0.008211 | 1363.6 | uav_01=1327.9；uav_06=1247.6 | 终点保持/作业 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 10 | uav_01+uav_06 | 0.008211 | 1364.0 | uav_01=1255.2；uav_06=1324.1 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 11 | uav_01+uav_06 | 0.008211 | 1353.6 | uav_01=1315.8；uav_06=1247.6 | 终点保持/作业 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 12 | uav_01+uav_06 | 0.008211 | 1335.1 | uav_01=1255.2；uav_06=1297.3 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 13 | uav_01+uav_06 | 0.008211 | 1335.7 | uav_01=1301.3；uav_06=1247.6 | 终点保持/作业 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 14 | uav_01+uav_06 | 0.008211 | 1336.1 | uav_01=1301.6；uav_06=1247.6 | 终点保持/作业 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 15 | uav_01+uav_06 | 0.008211 | 1335.9 | uav_01=1297.6；uav_06=1247.6 | 终点保持/作业 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 16 | uav_01+uav_06 | 0.008211 | 1354.9 | uav_01=1255.2；uav_06=1317.9 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 17 | uav_01+uav_06 | 0.008211 | 1338.4 | uav_01=1255.2；uav_06=1303.4 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 18 | uav_01+uav_06 | 0.008211 | 1363.1 | uav_01=1255.2；uav_06=1327.0 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_00 | sequential | 19 | uav_01+uav_06 | 0.008211 | 1358.8 | uav_01=1255.2；uav_06=1320.1 | 作业/终点保持 | True | uav_01=1313.8；uav_06=1313.8 |
| geometry_01 | synchronous | 0 | uav_01+uav_06 | 0.052982 | 2699.6 | uav_01=2661.5；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 1 | uav_01+uav_06 | 0.052982 | 2701.5 | uav_01=2663.6；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 2 | uav_01+uav_06 | 0.052982 | 2701.8 | uav_01=2666.2；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 3 | uav_01+uav_06 | 0.052982 | 2704.3 | uav_01=2667.7；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 4 | uav_01+uav_06 | 0.052982 | 2700.3 | uav_01=2664.0；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 5 | uav_01+uav_06 | 0.052982 | 2703.3 | uav_01=2664.2；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 6 | uav_01+uav_06 | 0.052982 | 2704.2 | uav_01=2668.9；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 7 | uav_01+uav_06 | 0.052982 | 2703.9 | uav_01=2670.7；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 8 | uav_01+uav_06 | 0.052982 | 2700.7 | uav_01=2666.0；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 9 | uav_01+uav_06 | 0.052982 | 2703.7 | uav_01=2665.8；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 10 | uav_01+uav_06 | 0.052982 | 2705.1 | uav_01=2666.5；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 11 | uav_01+uav_06 | 0.052982 | 2702.1 | uav_01=2667.7；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 12 | uav_01+uav_06 | 0.052982 | 2701.1 | uav_01=2664.0；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 13 | uav_01+uav_06 | 0.052982 | 2703.4 | uav_01=2669.2；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 14 | uav_01+uav_06 | 0.052982 | 2705.2 | uav_01=2670.4；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 15 | uav_01+uav_06 | 0.052982 | 2704.6 | uav_01=2667.5；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 16 | uav_01+uav_06 | 0.052982 | 2702.5 | uav_01=2667.0；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 17 | uav_01+uav_06 | 0.052982 | 2702.1 | uav_01=2664.8；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 18 | uav_01+uav_06 | 0.052982 | 2704.3 | uav_01=2668.3；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | synchronous | 19 | uav_01+uav_06 | 0.052982 | 2702.0 | uav_01=2663.8；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | sequential | 0 | uav_01+uav_06 | 0.025660 | 2734.3 | uav_01=2635.7；uav_06=2696.1 | 作业/终点保持 | True | uav_01=1174.0；uav_06=1174.0 |
| geometry_01 | sequential | 1 | uav_01+uav_06 | 0.025660 | 2730.6 | uav_01=2635.7；uav_06=2687.1 | 作业/终点保持 | True | uav_01=1174.0；uav_06=1174.0 |
| geometry_01 | sequential | 2 | uav_01+uav_06 | 0.025660 | 2757.4 | uav_01=2635.7；uav_06=2715.3 | 作业/终点保持 | True | uav_01=1174.0；uav_06=1174.0 |
| geometry_01 | sequential | 3 | uav_01+uav_06 | 0.025660 | 2729.6 | uav_01=2635.7；uav_06=2689.9 | 作业/终点保持 | True | uav_01=1174.0；uav_06=1174.0 |
| geometry_01 | sequential | 4 | uav_01+uav_06 | 0.052982 | 2761.7 | uav_01=2728.4；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | sequential | 5 | uav_01+uav_06 | 0.052982 | 2745.1 | uav_01=2707.2；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | sequential | 6 | uav_01+uav_06 | 0.025660 | 2727.5 | uav_01=2635.7；uav_06=2688.4 | 作业/终点保持 | True | uav_01=1174.0；uav_06=1174.0 |
| geometry_01 | sequential | 7 | uav_01+uav_06 | 0.052982 | 2751.4 | uav_01=2715.9；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | sequential | 8 | uav_01+uav_06 | 0.025660 | 2720.0 | uav_01=2635.7；uav_06=2677.4 | 作业/终点保持 | True | uav_01=1174.0；uav_06=1174.0 |
| geometry_01 | sequential | 9 | uav_01+uav_06 | 0.052982 | 2781.1 | uav_01=2745.4；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | sequential | 10 | uav_01+uav_06 | 0.025660 | 2744.5 | uav_01=2635.7；uav_06=2700.9 | 作业/终点保持 | True | uav_01=1174.0；uav_06=1174.0 |
| geometry_01 | sequential | 11 | uav_01+uav_06 | 0.052982 | 2771.1 | uav_01=2733.3；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | sequential | 12 | uav_01+uav_06 | 0.025660 | 2715.6 | uav_01=2635.7；uav_06=2674.1 | 作业/终点保持 | True | uav_01=1174.0；uav_06=1174.0 |
| geometry_01 | sequential | 13 | uav_01+uav_06 | 0.052982 | 2753.2 | uav_01=2718.8；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | sequential | 14 | uav_01+uav_06 | 0.052982 | 2753.6 | uav_01=2719.1；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | sequential | 15 | uav_01+uav_06 | 0.052982 | 2753.4 | uav_01=2715.1；uav_06=2661.4 | 终点保持/作业 | True | uav_01=1173.9；uav_06=1173.9 |
| geometry_01 | sequential | 16 | uav_01+uav_06 | 0.025660 | 2735.4 | uav_01=2635.7；uav_06=2694.7 | 作业/终点保持 | True | uav_01=1174.0；uav_06=1174.0 |
| geometry_01 | sequential | 17 | uav_01+uav_06 | 0.025660 | 2718.9 | uav_01=2635.7；uav_06=2680.2 | 作业/终点保持 | True | uav_01=1174.0；uav_06=1174.0 |
| geometry_01 | sequential | 18 | uav_01+uav_06 | 0.025660 | 2743.6 | uav_01=2635.7；uav_06=2703.8 | 作业/终点保持 | True | uav_01=1174.0；uav_06=1174.0 |
| geometry_01 | sequential | 19 | uav_01+uav_06 | 0.025660 | 2739.3 | uav_01=2635.7；uav_06=2696.9 | 作业/终点保持 | True | uav_01=1174.0；uav_06=1174.0 |
| geometry_02 | synchronous | 0 | uav_01+uav_06 | 0.006194 | 2506.5 | uav_01=2468.4；uav_06=2470.8 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 1 | uav_01+uav_06 | 0.006194 | 2506.3 | uav_01=2468.4；uav_06=2468.7 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 2 | uav_01+uav_06 | 0.006194 | 2504.0 | uav_01=2468.4；uav_06=2466.1 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 3 | uav_01+uav_06 | 0.006194 | 2505.0 | uav_01=2468.4；uav_06=2464.6 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 4 | uav_01+uav_06 | 0.006194 | 2504.7 | uav_01=2468.4；uav_06=2468.3 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 5 | uav_01+uav_06 | 0.006194 | 2507.5 | uav_01=2468.4；uav_06=2468.1 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 6 | uav_01+uav_06 | 0.006194 | 2503.7 | uav_01=2468.4；uav_06=2463.4 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 7 | uav_01+uav_06 | 0.006194 | 2501.6 | uav_01=2468.4；uav_06=2461.6 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 8 | uav_01+uav_06 | 0.006194 | 2503.1 | uav_01=2468.4；uav_06=2466.3 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 9 | uav_01+uav_06 | 0.006194 | 2506.3 | uav_01=2468.4；uav_06=2466.5 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 10 | uav_01+uav_06 | 0.006194 | 2507.0 | uav_01=2468.4；uav_06=2465.8 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 11 | uav_01+uav_06 | 0.006194 | 2502.8 | uav_01=2468.4；uav_06=2464.6 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 12 | uav_01+uav_06 | 0.006194 | 2505.5 | uav_01=2468.4；uav_06=2468.3 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 13 | uav_01+uav_06 | 0.006194 | 2502.6 | uav_01=2468.4；uav_06=2463.1 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 14 | uav_01+uav_06 | 0.006194 | 2503.2 | uav_01=2468.4；uav_06=2461.9 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 15 | uav_01+uav_06 | 0.006194 | 2505.5 | uav_01=2468.4；uav_06=2464.8 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 16 | uav_01+uav_06 | 0.006194 | 2503.9 | uav_01=2468.4；uav_06=2465.3 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 17 | uav_01+uav_06 | 0.006194 | 2505.7 | uav_01=2468.4；uav_06=2467.5 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 18 | uav_01+uav_06 | 0.006194 | 2504.4 | uav_01=2468.4；uav_06=2464.0 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | synchronous | 19 | uav_01+uav_06 | 0.006194 | 2506.6 | uav_01=2468.4；uav_06=2468.5 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | sequential | 0 | uav_01+uav_06 | 0.006194 | 2567.0 | uav_01=2468.4；uav_06=2531.3 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | sequential | 1 | uav_01+uav_06 | 0.006194 | 2563.3 | uav_01=2468.4；uav_06=2522.3 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | sequential | 2 | uav_01+uav_06 | 0.006194 | 2590.1 | uav_01=2468.4；uav_06=2550.5 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | sequential | 3 | uav_01+uav_06 | 0.006194 | 2562.3 | uav_01=2468.4；uav_06=2525.1 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | sequential | 4 | uav_01+uav_06 | 0.040265 | 2531.5 | uav_01=2498.2；uav_06=2433.7 | 终点保持/作业 | True | uav_01=1229.2；uav_06=1229.2 |
| geometry_02 | sequential | 5 | uav_01+uav_06 | 0.040265 | 2514.9 | uav_01=2477.0；uav_06=2433.7 | 终点保持/作业 | True | uav_01=1229.2；uav_06=1229.2 |
| geometry_02 | sequential | 6 | uav_01+uav_06 | 0.006194 | 2560.2 | uav_01=2468.4；uav_06=2523.6 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | sequential | 7 | uav_01+uav_06 | 0.040265 | 2521.2 | uav_01=2485.7；uav_06=2433.7 | 终点保持/作业 | True | uav_01=1229.2；uav_06=1229.2 |
| geometry_02 | sequential | 8 | uav_01+uav_06 | 0.006194 | 2552.7 | uav_01=2468.4；uav_06=2512.6 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | sequential | 9 | uav_01+uav_06 | 0.040265 | 2550.9 | uav_01=2515.2；uav_06=2433.7 | 终点保持/作业 | True | uav_01=1229.2；uav_06=1229.2 |
| geometry_02 | sequential | 10 | uav_01+uav_06 | 0.006194 | 2577.2 | uav_01=2468.4；uav_06=2536.1 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | sequential | 11 | uav_01+uav_06 | 0.040265 | 2540.9 | uav_01=2503.1；uav_06=2433.7 | 终点保持/作业 | True | uav_01=1229.2；uav_06=1229.2 |
| geometry_02 | sequential | 12 | uav_01+uav_06 | 0.006194 | 2548.3 | uav_01=2468.4；uav_06=2509.3 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | sequential | 13 | uav_01+uav_06 | 0.040265 | 2523.0 | uav_01=2488.6；uav_06=2433.7 | 终点保持/作业 | True | uav_01=1229.2；uav_06=1229.2 |
| geometry_02 | sequential | 14 | uav_01+uav_06 | 0.040265 | 2523.4 | uav_01=2488.9；uav_06=2433.7 | 终点保持/作业 | True | uav_01=1229.2；uav_06=1229.2 |
| geometry_02 | sequential | 15 | uav_01+uav_06 | 0.040265 | 2523.2 | uav_01=2484.9；uav_06=2433.7 | 终点保持/作业 | True | uav_01=1229.2；uav_06=1229.2 |
| geometry_02 | sequential | 16 | uav_01+uav_06 | 0.006194 | 2568.1 | uav_01=2468.4；uav_06=2529.9 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | sequential | 17 | uav_01+uav_06 | 0.006194 | 2551.6 | uav_01=2468.4；uav_06=2515.4 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | sequential | 18 | uav_01+uav_06 | 0.006194 | 2576.3 | uav_01=2468.4；uav_06=2539.0 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_02 | sequential | 19 | uav_01+uav_06 | 0.006194 | 2572.0 | uav_01=2468.4；uav_06=2532.1 | 作业/终点保持 | True | uav_01=1229.1；uav_06=1229.1 |
| geometry_03 | synchronous | 0 | uav_01+uav_06 | 0.023184 | 3619.0 | uav_01=3580.9；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 1 | uav_01+uav_06 | 0.023184 | 3620.9 | uav_01=3583.0；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 2 | uav_01+uav_06 | 0.023184 | 3621.2 | uav_01=3585.6；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 3 | uav_01+uav_06 | 0.023184 | 3623.7 | uav_01=3587.1；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 4 | uav_01+uav_06 | 0.023184 | 3619.7 | uav_01=3583.4；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 5 | uav_01+uav_06 | 0.023184 | 3622.7 | uav_01=3583.6；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 6 | uav_01+uav_06 | 0.023184 | 3623.6 | uav_01=3588.3；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 7 | uav_01+uav_06 | 0.023184 | 3623.3 | uav_01=3590.1；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 8 | uav_01+uav_06 | 0.023184 | 3620.1 | uav_01=3585.4；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 9 | uav_01+uav_06 | 0.023184 | 3623.1 | uav_01=3585.2；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 10 | uav_01+uav_06 | 0.023184 | 3624.5 | uav_01=3585.9；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 11 | uav_01+uav_06 | 0.023184 | 3621.5 | uav_01=3587.1；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 12 | uav_01+uav_06 | 0.023184 | 3620.5 | uav_01=3583.4；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 13 | uav_01+uav_06 | 0.023184 | 3622.8 | uav_01=3588.6；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 14 | uav_01+uav_06 | 0.023184 | 3624.6 | uav_01=3589.8；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 15 | uav_01+uav_06 | 0.023184 | 3624.0 | uav_01=3586.9；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 16 | uav_01+uav_06 | 0.023184 | 3621.9 | uav_01=3586.4；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 17 | uav_01+uav_06 | 0.023184 | 3621.5 | uav_01=3584.2；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 18 | uav_01+uav_06 | 0.023184 | 3623.7 | uav_01=3587.7；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | synchronous | 19 | uav_01+uav_06 | 0.023184 | 3621.4 | uav_01=3583.2；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 0 | uav_01+uav_06 | 0.023184 | 3638.5 | uav_01=3539.9；uav_06=3597.3 | 作业/终点保持 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 1 | uav_01+uav_06 | 0.023184 | 3634.8 | uav_01=3539.9；uav_06=3588.3 | 作业/终点保持 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 2 | uav_01+uav_06 | 0.023184 | 3661.6 | uav_01=3539.9；uav_06=3616.5 | 作业/终点保持 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 3 | uav_01+uav_06 | 0.023184 | 3633.8 | uav_01=3539.9；uav_06=3591.1 | 作业/终点保持 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 4 | uav_01+uav_06 | 0.023184 | 3681.1 | uav_01=3647.8；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 5 | uav_01+uav_06 | 0.023184 | 3664.5 | uav_01=3626.6；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 6 | uav_01+uav_06 | 0.023184 | 3631.7 | uav_01=3539.9；uav_06=3589.6 | 作业/终点保持 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 7 | uav_01+uav_06 | 0.023184 | 3670.8 | uav_01=3635.3；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 8 | uav_01+uav_06 | 0.023184 | 3624.2 | uav_01=3539.9；uav_06=3578.6 | 作业/终点保持 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 9 | uav_01+uav_06 | 0.023184 | 3700.5 | uav_01=3664.8；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 10 | uav_01+uav_06 | 0.023184 | 3648.7 | uav_01=3539.9；uav_06=3602.1 | 作业/终点保持 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 11 | uav_01+uav_06 | 0.023184 | 3690.5 | uav_01=3652.7；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 12 | uav_01+uav_06 | 0.023184 | 3622.3 | uav_01=3542.4；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 13 | uav_01+uav_06 | 0.023184 | 3672.6 | uav_01=3638.2；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 14 | uav_01+uav_06 | 0.023184 | 3673.0 | uav_01=3638.5；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 15 | uav_01+uav_06 | 0.023184 | 3672.8 | uav_01=3634.5；uav_06=3577.8 | 终点保持/作业 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 16 | uav_01+uav_06 | 0.023184 | 3639.6 | uav_01=3539.9；uav_06=3595.9 | 作业/终点保持 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 17 | uav_01+uav_06 | 0.023184 | 3623.1 | uav_01=3539.9；uav_06=3581.4 | 作业/终点保持 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 18 | uav_01+uav_06 | 0.023184 | 3647.8 | uav_01=3539.9；uav_06=3605.0 | 作业/终点保持 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_03 | sequential | 19 | uav_01+uav_06 | 0.023184 | 3643.5 | uav_01=3539.9；uav_06=3598.1 | 作业/终点保持 | True | uav_01=1152.7；uav_06=1152.7 |
| geometry_04 | synchronous | 0 | uav_01+uav_06 | 0.021250 | 2509.1 | uav_01=2471.0；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 1 | uav_01+uav_06 | 0.021250 | 2511.0 | uav_01=2473.1；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 2 | uav_01+uav_06 | 0.021250 | 2511.3 | uav_01=2475.7；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 3 | uav_01+uav_06 | 0.021250 | 2513.8 | uav_01=2477.2；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 4 | uav_01+uav_06 | 0.021250 | 2509.8 | uav_01=2473.5；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 5 | uav_01+uav_06 | 0.021250 | 2512.8 | uav_01=2473.7；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 6 | uav_01+uav_06 | 0.021250 | 2513.7 | uav_01=2478.4；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 7 | uav_01+uav_06 | 0.021250 | 2513.4 | uav_01=2480.2；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 8 | uav_01+uav_06 | 0.021250 | 2510.2 | uav_01=2475.5；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 9 | uav_01+uav_06 | 0.021250 | 2513.2 | uav_01=2475.3；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 10 | uav_01+uav_06 | 0.021250 | 2514.6 | uav_01=2476.0；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 11 | uav_01+uav_06 | 0.021250 | 2511.6 | uav_01=2477.2；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 12 | uav_01+uav_06 | 0.021250 | 2510.6 | uav_01=2473.5；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 13 | uav_01+uav_06 | 0.021250 | 2512.9 | uav_01=2478.7；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 14 | uav_01+uav_06 | 0.021250 | 2514.7 | uav_01=2479.9；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 15 | uav_01+uav_06 | 0.021250 | 2514.1 | uav_01=2477.0；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 16 | uav_01+uav_06 | 0.021250 | 2512.0 | uav_01=2476.5；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 17 | uav_01+uav_06 | 0.021250 | 2511.6 | uav_01=2474.3；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 18 | uav_01+uav_06 | 0.021250 | 2513.8 | uav_01=2477.8；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | synchronous | 19 | uav_01+uav_06 | 0.021250 | 2511.5 | uav_01=2473.3；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 0 | uav_01+uav_06 | 0.021250 | 2543.6 | uav_01=2445.0；uav_06=2507.8 | 作业/终点保持 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 1 | uav_01+uav_06 | 0.021250 | 2539.9 | uav_01=2445.0；uav_06=2498.8 | 作业/终点保持 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 2 | uav_01+uav_06 | 0.021250 | 2566.7 | uav_01=2445.0；uav_06=2527.0 | 作业/终点保持 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 3 | uav_01+uav_06 | 0.021250 | 2538.9 | uav_01=2445.0；uav_06=2501.6 | 作业/终点保持 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 4 | uav_01+uav_06 | 0.021250 | 2571.2 | uav_01=2537.9；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 5 | uav_01+uav_06 | 0.021250 | 2554.6 | uav_01=2516.7；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 6 | uav_01+uav_06 | 0.021250 | 2536.8 | uav_01=2445.0；uav_06=2500.1 | 作业/终点保持 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 7 | uav_01+uav_06 | 0.021250 | 2560.9 | uav_01=2525.4；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 8 | uav_01+uav_06 | 0.021250 | 2529.3 | uav_01=2445.0；uav_06=2489.1 | 作业/终点保持 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 9 | uav_01+uav_06 | 0.021250 | 2590.6 | uav_01=2554.9；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 10 | uav_01+uav_06 | 0.021250 | 2553.8 | uav_01=2445.0；uav_06=2512.6 | 作业/终点保持 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 11 | uav_01+uav_06 | 0.021250 | 2580.6 | uav_01=2542.8；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 12 | uav_01+uav_06 | 0.021250 | 2524.9 | uav_01=2445.0；uav_06=2485.8 | 作业/终点保持 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 13 | uav_01+uav_06 | 0.021250 | 2562.7 | uav_01=2528.3；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 14 | uav_01+uav_06 | 0.021250 | 2563.1 | uav_01=2528.6；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 15 | uav_01+uav_06 | 0.021250 | 2562.9 | uav_01=2524.6；uav_06=2473.3 | 终点保持/作业 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 16 | uav_01+uav_06 | 0.021250 | 2544.7 | uav_01=2445.0；uav_06=2506.4 | 作业/终点保持 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 17 | uav_01+uav_06 | 0.021250 | 2528.2 | uav_01=2445.0；uav_06=2491.9 | 作业/终点保持 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 18 | uav_01+uav_06 | 0.021250 | 2552.9 | uav_01=2445.0；uav_06=2515.5 | 作业/终点保持 | True | uav_01=1345.9；uav_06=1345.9 |
| geometry_04 | sequential | 19 | uav_01+uav_06 | 0.021250 | 2548.6 | uav_01=2445.0；uav_06=2508.6 | 作业/终点保持 | True | uav_01=1345.9；uav_06=1345.9 |

> 阶段判定：τ<0 起飞前等待；0≤τ<core_time 进场；core_time≤τ≤completion_time 作业；completion_time<τ≤末帧 撤离；τ>末帧 终点保持。core/completion 取自 `rehearsal.json`。冲突点取两机在 t_s 处位移后位置的**中点**，距离按场景平面（ENU 的 x、y）计算。

### 每轮 × 每 mode 的主导组合

| 轮 | mode | draw 数 | 主导（机对 → 阶段组合） | 次数 | 判定 |
|---|---|---:|---|---:|---|
| geometry_00 | sequential | 20 | uav_01+uav_06 → 作业+终点保持 | 12/20 | 分散 |
| geometry_00 | synchronous | 20 | uav_01+uav_06 → 作业+终点保持 | 20/20 | 结构性（与时刻无关） |
| geometry_01 | sequential | 20 | uav_01+uav_06 → 作业+终点保持 | 12/20 | 分散 |
| geometry_01 | synchronous | 20 | uav_01+uav_06 → 终点保持+作业 | 20/20 | 结构性（与时刻无关） |
| geometry_02 | sequential | 20 | uav_01+uav_06 → 作业+终点保持 | 12/20 | 分散 |
| geometry_02 | synchronous | 20 | uav_01+uav_06 → 作业+终点保持 | 20/20 | 结构性（与时刻无关） |
| geometry_03 | sequential | 20 | uav_01+uav_06 → 作业+终点保持 | 11/20 | 分散 |
| geometry_03 | synchronous | 20 | uav_01+uav_06 → 终点保持+作业 | 20/20 | 结构性（与时刻无关） |
| geometry_04 | sequential | 20 | uav_01+uav_06 → 作业+终点保持 | 12/20 | 分散 |
| geometry_04 | synchronous | 20 | uav_01+uav_06 → 终点保持+作业 | 20/20 | 结构性（与时刻无关） |

> 判定规则：同一机对 + 同一阶段组合在 20 次 draw 中出现 ≥15 次记为结构性。

### 冲突机对的空间量（不含时间）

| 轮 | 机对 | 两轨迹空间最近距离 m | 起点间距 m | 终点间距 m | 同组 |
|---|---|---:|---:|---:|---|
| geometry_00 | uav_01+uav_06 | 0.009141 | 77.234 | 0.008 | True |

> 三条量均按 10 Hz 帧、两轨迹各取 5 帧降采样后在降采样点集上取最小值。

## family_s15_aa4c66be8e85d64d_ext_002_regular

- attempt：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261016T191411Z`
- 轮数：5

| 轮 | candidate_index | rehearsal.json | timing_selection.json | category | 预演耗时(mtime估) | 时刻耗时(mtime估) |
|---|---|---|---|---|---|---|
| geometry_00 | 64 | True | True | timing_conflict | 175.213 | 0.309 |
| geometry_01 | 48 | True | True | timing_conflict | 604.97 | 0.621 |
| geometry_02 | 57 | True | True | timing_conflict | 525.9 | 1.913 |
| geometry_03 | 49 | True | True | timing_conflict | 448.581 | 0.528 |
| geometry_04 | 75 | True | True | timing_conflict | 354.403 | 1.668 |

> 预演耗时 = mtime(rehearsal.json) − mtime(planning_checks.json)；时刻耗时 = mtime(timing_selection.json) − mtime(rehearsal.json)。这是 **mtime 估计**，不是被测代码的埋点。

### 每次被拒 draw 的机对与阶段

| 轮 | mode | draw | 机对 | minimum_m | t_s | τ（本机） | 阶段 | 同组 | 到各自组目标中心 m |
|---|---|---:|---|---:|---:|---|---|---|---|
| geometry_00 | synchronous | 0 | uav_03+uav_05 | 0.001905 | 1075.8 | uav_03=1019.4；uav_05=1023.5 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 1 | uav_03+uav_05 | 0.001905 | 1074.3 | uav_03=1019.4；uav_05=1022.8 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 2 | uav_03+uav_05 | 0.001905 | 1073.5 | uav_03=1019.4；uav_05=1021.9 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 3 | uav_03+uav_05 | 0.001905 | 1072.0 | uav_03=1019.4；uav_05=1019.3 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 4 | uav_03+uav_05 | 0.001905 | 1075.3 | uav_03=1019.4；uav_05=1022.6 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 5 | uav_03+uav_05 | 0.001905 | 1073.9 | uav_03=1019.4；uav_05=1020.0 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 6 | uav_03+uav_05 | 0.001905 | 1076.6 | uav_03=1019.4；uav_05=1024.4 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 7 | uav_03+uav_05 | 0.001905 | 1071.7 | uav_03=1019.4；uav_05=1020.3 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 8 | uav_03+uav_05 | 0.001905 | 1076.5 | uav_03=1019.4；uav_05=1024.4 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 9 | uav_03+uav_05 | 0.001905 | 1073.8 | uav_03=1019.4；uav_05=1021.5 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 10 | uav_03+uav_05 | 0.001905 | 1076.6 | uav_03=1019.4；uav_05=1027.4 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 11 | uav_03+uav_05 | 0.001905 | 1074.4 | uav_03=1019.4；uav_05=1020.9 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 12 | uav_03+uav_05 | 0.001905 | 1072.1 | uav_03=1019.4；uav_05=1022.0 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 13 | uav_03+uav_05 | 0.001905 | 1076.6 | uav_03=1019.4；uav_05=1024.7 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 14 | uav_03+uav_05 | 0.001905 | 1071.6 | uav_03=1019.4；uav_05=1020.0 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 15 | uav_03+uav_05 | 0.001905 | 1073.5 | uav_03=1019.4；uav_05=1021.5 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 16 | uav_03+uav_05 | 0.001905 | 1072.0 | uav_03=1019.4；uav_05=1018.5 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 17 | uav_03+uav_05 | 0.001905 | 1074.1 | uav_03=1019.4；uav_05=1021.2 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 18 | uav_03+uav_05 | 0.001905 | 1071.8 | uav_03=1019.4；uav_05=1018.1 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | synchronous | 19 | uav_03+uav_05 | 0.001905 | 1073.0 | uav_03=1019.4；uav_05=1023.7 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 0 | uav_03+uav_05 | 0.001905 | 1257.2 | uav_03=1203.7；uav_05=1011.4 | 终点保持/作业 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 1 | uav_03+uav_05 | 0.001905 | 1074.3 | uav_03=1019.4；uav_05=1021.0 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 2 | uav_03+uav_05 | 0.001905 | 1265.1 | uav_03=1089.9；uav_05=1011.4 | 终点保持/作业 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 3 | uav_03+uav_05 | 0.001905 | 1622.3 | uav_03=1296.7；uav_05=1011.4 | 终点保持/作业 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 4 | uav_03+uav_05 | 0.001905 | 1247.4 | uav_03=1019.4；uav_05=1021.7 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 5 | uav_03+uav_05 | 0.001905 | 1142.1 | uav_03=1085.8；uav_05=1011.4 | 终点保持/作业 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 6 | uav_03+uav_05 | 0.001905 | 1115.3 | uav_03=1060.1；uav_05=1011.4 | 终点保持/作业 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 7 | uav_03+uav_05 | 0.001905 | 1072.3 | uav_03=1019.4；uav_05=1019.9 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 8 | uav_03+uav_05 | 0.001905 | 1276.4 | uav_03=1222.4；uav_05=1011.4 | 终点保持/作业 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 9 | uav_03+uav_05 | 0.001905 | 1269.4 | uav_03=1019.4；uav_05=1025.5 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 10 | uav_03+uav_05 | 0.001905 | 1199.2 | uav_03=1058.2；uav_05=1011.4 | 终点保持/作业 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 11 | uav_03+uav_05 | 0.001905 | 1129.6 | uav_03=1019.4；uav_05=1076.3 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 12 | uav_03+uav_05 | 0.001905 | 1138.9 | uav_03=1019.4；uav_05=1084.9 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 13 | uav_03+uav_05 | 0.001905 | 1202.4 | uav_03=1019.4；uav_05=1072.8 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 14 | uav_03+uav_05 | 0.001905 | 1408.5 | uav_03=1019.4；uav_05=1189.8 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 15 | uav_03+uav_05 | 0.001905 | 1375.5 | uav_03=1242.2；uav_05=1011.4 | 终点保持/作业 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 16 | uav_03+uav_05 | 0.001905 | 1299.9 | uav_03=1019.4；uav_05=1247.0 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 17 | uav_03+uav_05 | 0.001905 | 1209.4 | uav_03=1154.0；uav_05=1011.4 | 终点保持/作业 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 18 | uav_03+uav_05 | 0.001905 | 1165.6 | uav_03=1061.6；uav_05=1011.4 | 终点保持/作业 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_00 | sequential | 19 | uav_03+uav_05 | 0.001905 | 1535.6 | uav_03=1019.4；uav_05=1349.2 | 作业/终点保持 | True | uav_03=1331.7；uav_05=1331.7 |
| geometry_01 | synchronous | 0 | uav_08+uav_09 | 0.005433 | 2357.8 | uav_08=1875.7；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 1 | uav_08+uav_09 | 0.005433 | 2356.4 | uav_08=1872.7；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 2 | uav_08+uav_09 | 0.005433 | 2357.3 | uav_08=1875.3；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 3 | uav_08+uav_09 | 0.005433 | 2357.9 | uav_08=1873.7；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 4 | uav_08+uav_09 | 0.005433 | 2357.4 | uav_08=1873.6；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 5 | uav_08+uav_09 | 0.005433 | 2360.2 | uav_08=1878.7；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 6 | uav_08+uav_09 | 0.005433 | 2358.1 | uav_08=1872.1；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 7 | uav_08+uav_09 | 0.005433 | 2359.5 | uav_08=1873.3；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 8 | uav_08+uav_09 | 0.005433 | 2360.5 | uav_08=1877.1；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 9 | uav_08+uav_09 | 0.005433 | 2355.9 | uav_08=1871.2；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 10 | uav_08+uav_09 | 0.005433 | 2359.1 | uav_08=1873.6；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 11 | uav_08+uav_09 | 0.005433 | 2361.3 | uav_08=1876.1；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 12 | uav_08+uav_09 | 0.005433 | 2359.9 | uav_08=1877.5；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 13 | uav_08+uav_09 | 0.005433 | 2356.9 | uav_08=1870.4；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 14 | uav_08+uav_09 | 0.005433 | 2360.3 | uav_08=1877.3；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 15 | uav_08+uav_09 | 0.005433 | 2357.3 | uav_08=1873.4；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 16 | uav_08+uav_09 | 0.005433 | 2361.0 | uav_08=1876.8；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 17 | uav_08+uav_09 | 0.005433 | 2360.1 | uav_08=1878.5；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 18 | uav_08+uav_09 | 0.005433 | 2356.2 | uav_08=1870.2；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | synchronous | 19 | uav_08+uav_09 | 0.005433 | 2358.1 | uav_08=1871.7；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 0 | uav_08+uav_09 | 0.005433 | 2766.1 | uav_08=2163.5；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 1 | uav_08+uav_09 | 0.005433 | 2358.7 | uav_08=1874.3；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 2 | uav_08+uav_09 | 0.005433 | 2396.4 | uav_08=1795.5；uav_09=1913.1 | 作业/终点保持 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 3 | uav_08+uav_09 | 0.005433 | 2551.5 | uav_08=2009.7；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 4 | uav_08+uav_09 | 0.005433 | 2455.9 | uav_08=1795.5；uav_09=1900.5 | 作业/终点保持 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 5 | uav_08+uav_09 | 0.005433 | 2359.1 | uav_08=1795.5；uav_09=1880.9 | 作业/终点保持 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 6 | uav_08+uav_09 | 0.005433 | 2406.4 | uav_08=1868.7；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 7 | uav_08+uav_09 | 0.005433 | 2416.7 | uav_08=1871.1；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 8 | uav_08+uav_09 | 0.005433 | 2572.8 | uav_08=2026.7；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 9 | uav_08+uav_09 | 0.005433 | 2472.3 | uav_08=1795.5；uav_09=1994.8 | 作业/终点保持 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 10 | uav_08+uav_09 | 0.005433 | 2441.2 | uav_08=1871.3；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 11 | uav_08+uav_09 | 0.005433 | 2705.1 | uav_08=1983.3；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 12 | uav_08+uav_09 | 0.005433 | 2424.1 | uav_08=1937.8；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 13 | uav_08+uav_09 | 0.005433 | 2491.3 | uav_08=2006.5；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 14 | uav_08+uav_09 | 0.005433 | 2794.0 | uav_08=2142.5；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 15 | uav_08+uav_09 | 0.005433 | 2779.7 | uav_08=2296.9；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 16 | uav_08+uav_09 | 0.005433 | 2518.3 | uav_08=1942.5；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 17 | uav_08+uav_09 | 0.005433 | 2427.3 | uav_08=1798.5；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 18 | uav_08+uav_09 | 0.005433 | 2464.4 | uav_08=1928.5；uav_09=1878.1 | 终点保持/作业 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_01 | sequential | 19 | uav_08+uav_09 | 0.005433 | 2811.6 | uav_08=1795.5；uav_09=2141.5 | 作业/终点保持 | True | uav_08=1172.4；uav_09=1172.4 |
| geometry_02 | synchronous | 0 | uav_01+uav_03 | 0.004767 | 1865.5 | uav_01=1566.8；uav_03=1567.5 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 1 | uav_01+uav_03 | 0.004767 | 1865.2 | uav_01=1566.8；uav_03=1568.7 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 2 | uav_01+uav_03 | 0.004767 | 1861.9 | uav_01=1566.8；uav_03=1566.2 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 3 | uav_01+uav_03 | 0.004767 | 1865.6 | uav_01=1566.8；uav_03=1571.4 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 4 | uav_01+uav_03 | 0.004767 | 1863.1 | uav_01=1566.8；uav_03=1565.6 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 5 | uav_01+uav_03 | 0.004767 | 1863.4 | uav_01=1566.8；uav_03=1567.3 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 6 | uav_01+uav_03 | 0.004767 | 1861.8 | uav_01=1566.8；uav_03=1563.0 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 7 | uav_01+uav_03 | 0.004767 | 1861.5 | uav_01=1566.8；uav_03=1567.6 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 8 | uav_01+uav_03 | 0.004767 | 1861.5 | uav_01=1566.8；uav_03=1562.8 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 9 | uav_01+uav_03 | 0.004767 | 1862.7 | uav_01=1566.8；uav_03=1566.7 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 10 | uav_01+uav_03 | 0.004767 | 1860.9 | uav_01=1566.8；uav_03=1562.1 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 11 | uav_01+uav_03 | 0.004767 | 1864.4 | uav_01=1566.8；uav_03=1567.8 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 12 | uav_01+uav_03 | 0.004767 | 1861.7 | uav_01=1566.8；uav_03=1567.4 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 13 | uav_01+uav_03 | 0.004767 | 1863.1 | uav_01=1566.8；uav_03=1564.3 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 14 | uav_01+uav_03 | 0.004767 | 1864.5 | uav_01=1566.8；uav_03=1570.7 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 15 | uav_01+uav_03 | 0.004767 | 1863.1 | uav_01=1566.8；uav_03=1567.4 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 16 | uav_01+uav_03 | 0.004767 | 1860.6 | uav_01=1566.8；uav_03=1566.4 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 17 | uav_01+uav_03 | 0.004767 | 1863.2 | uav_01=1566.8；uav_03=1566.9 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 18 | uav_01+uav_03 | 0.004767 | 1865.4 | uav_01=1566.8；uav_03=1571.4 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | synchronous | 19 | uav_01+uav_03 | 0.004767 | 1863.5 | uav_01=1566.8；uav_03=1568.3 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 0 | uav_01+uav_03 | 0.004767 | 2193.0 | uav_01=1566.8；uav_03=1897.9 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 1 | uav_01+uav_03 | 0.004767 | 1866.5 | uav_01=1566.8；uav_03=1570.0 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 2 | uav_01+uav_03 | 0.004767 | 1943.6 | uav_01=1566.8；uav_03=1526.8 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 3 | uav_01+uav_03 | 0.004767 | 2330.4 | uav_01=1566.8；uav_03=1763.2 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 4 | uav_01+uav_03 | 0.004767 | 1974.7 | uav_01=1678.8；uav_03=1505.1 | 终点保持/作业 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 5 | uav_01+uav_03 | 0.004767 | 1941.9 | uav_01=1566.8；uav_03=1644.0 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 6 | uav_01+uav_03 | 0.004767 | 1865.3 | uav_01=1566.8；uav_03=1568.5 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 7 | uav_01+uav_03 | 0.004767 | 1862.9 | uav_01=1566.8；uav_03=1568.4 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 8 | uav_01+uav_03 | 0.004767 | 2075.1 | uav_01=1566.8；uav_03=1779.5 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 9 | uav_01+uav_03 | 0.004767 | 1996.7 | uav_01=1640.8；uav_03=1505.1 | 终点保持/作业 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 10 | uav_01+uav_03 | 0.004767 | 2006.0 | uav_01=1566.8；uav_03=1623.4 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 11 | uav_01+uav_03 | 0.004767 | 2148.6 | uav_01=1566.8；uav_03=1796.8 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 12 | uav_01+uav_03 | 0.004767 | 1924.2 | uav_01=1566.8；uav_03=1563.1 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 13 | uav_01+uav_03 | 0.004767 | 1994.3 | uav_01=1566.8；uav_03=1569.7 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 14 | uav_01+uav_03 | 0.004767 | 2135.8 | uav_01=1839.7；uav_03=1505.1 | 终点保持/作业 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 15 | uav_01+uav_03 | 0.004767 | 2059.8 | uav_01=1566.8；uav_03=1684.9 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 16 | uav_01+uav_03 | 0.004767 | 2334.0 | uav_01=1566.8；uav_03=1811.9 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 17 | uav_01+uav_03 | 0.004767 | 2012.4 | uav_01=1566.8；uav_03=1715.4 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 18 | uav_01+uav_03 | 0.004767 | 1965.2 | uav_01=1566.8；uav_03=1619.6 | 作业/终点保持 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_02 | sequential | 19 | uav_01+uav_03 | 0.004767 | 2262.9 | uav_01=1644.9；uav_03=1505.1 | 终点保持/作业 | True | uav_01=1277.3；uav_03=1277.3 |
| geometry_03 | synchronous | 0 | uav_03+uav_05 | 0.004588 | 2102.3 | uav_03=1740.4；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 1 | uav_03+uav_05 | 0.004588 | 2101.5 | uav_03=1741.1；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 2 | uav_03+uav_05 | 0.004588 | 2101.6 | uav_03=1742.0；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 3 | uav_03+uav_05 | 0.004588 | 2102.7 | uav_03=1744.6；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 4 | uav_03+uav_05 | 0.004588 | 2102.7 | uav_03=1741.3；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 5 | uav_03+uav_05 | 0.004588 | 2103.9 | uav_03=1743.9；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 6 | uav_03+uav_05 | 0.004588 | 2102.2 | uav_03=1739.5；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 7 | uav_03+uav_05 | 0.004588 | 2101.4 | uav_03=1743.6；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 8 | uav_03+uav_05 | 0.004588 | 2102.1 | uav_03=1739.5；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 9 | uav_03+uav_05 | 0.004588 | 2102.3 | uav_03=1742.4；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 10 | uav_03+uav_05 | 0.004588 | 2099.2 | uav_03=1736.5；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 11 | uav_03+uav_05 | 0.004588 | 2103.5 | uav_03=1743.0；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 12 | uav_03+uav_05 | 0.004588 | 2100.1 | uav_03=1741.9；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 13 | uav_03+uav_05 | 0.004588 | 2101.9 | uav_03=1739.2；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 14 | uav_03+uav_05 | 0.004588 | 2101.6 | uav_03=1743.9；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 15 | uav_03+uav_05 | 0.004588 | 2102.0 | uav_03=1742.4；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 16 | uav_03+uav_05 | 0.004588 | 2103.5 | uav_03=1745.4；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 17 | uav_03+uav_05 | 0.004588 | 2102.9 | uav_03=1742.7；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 18 | uav_03+uav_05 | 0.004588 | 2103.7 | uav_03=1745.8；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | synchronous | 19 | uav_03+uav_05 | 0.004588 | 2099.3 | uav_03=1740.2；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 0 | uav_03+uav_05 | 0.004588 | 2295.8 | uav_03=1936.8；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 1 | uav_03+uav_05 | 0.004588 | 2103.3 | uav_03=1742.9；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 2 | uav_03+uav_05 | 0.004588 | 2303.7 | uav_03=1823.0；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 3 | uav_03+uav_05 | 0.004588 | 2660.9 | uav_03=2029.8；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 4 | uav_03+uav_05 | 0.004588 | 2275.7 | uav_03=1742.2；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 5 | uav_03+uav_05 | 0.004588 | 2180.7 | uav_03=1818.9；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 6 | uav_03+uav_05 | 0.004588 | 2153.9 | uav_03=1793.2；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 7 | uav_03+uav_05 | 0.004588 | 2102.4 | uav_03=1744.0；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 8 | uav_03+uav_05 | 0.004588 | 2315.0 | uav_03=1955.5；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 9 | uav_03+uav_05 | 0.004588 | 2293.9 | uav_03=1738.4；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 10 | uav_03+uav_05 | 0.004588 | 2237.8 | uav_03=1791.3；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 11 | uav_08+uav_09 | 0.005074 | 2381.9 | uav_08=1770.4；uav_09=1667.2 | 终点保持/作业 | True | uav_08=1195.0；uav_09=1195.0 |
| geometry_03 | sequential | 12 | uav_08+uav_09 | 0.005074 | 2100.9 | uav_08=1724.9；uav_09=1667.2 | 终点保持/作业 | True | uav_08=1195.0；uav_09=1195.0 |
| geometry_03 | sequential | 13 | uav_08+uav_09 | 0.005074 | 2168.1 | uav_08=1793.6；uav_09=1667.2 | 终点保持/作业 | True | uav_08=1195.0；uav_09=1195.0 |
| geometry_03 | sequential | 14 | uav_08+uav_09 | 0.005074 | 2470.8 | uav_08=1929.6；uav_09=1667.2 | 终点保持/作业 | True | uav_08=1195.0；uav_09=1195.0 |
| geometry_03 | sequential | 15 | uav_03+uav_05 | 0.004588 | 2414.1 | uav_03=1975.3；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 16 | uav_08+uav_09 | 0.005074 | 2195.1 | uav_08=1729.6；uav_09=1667.2 | 终点保持/作业 | True | uav_08=1195.0；uav_09=1195.0 |
| geometry_03 | sequential | 17 | uav_03+uav_05 | 0.004588 | 2248.0 | uav_03=1887.1；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 18 | uav_03+uav_05 | 0.004588 | 2204.2 | uav_03=1794.7；uav_05=1748.2 | 终点保持/作业 | True | uav_03=1195.0；uav_05=1195.0 |
| geometry_03 | sequential | 19 | uav_08+uav_09 | 0.008230 | 2501.9 | uav_08=1596.1；uav_09=1944.1 | 作业/终点保持 | True | uav_08=1195.0；uav_09=1195.0 |
| geometry_04 | synchronous | 0 | uav_01+uav_09 | 0.003569 | 1616.7 | uav_01=1133.6；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 1 | uav_01+uav_09 | 0.003569 | 1615.3 | uav_01=1132.5；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 2 | uav_01+uav_09 | 0.003569 | 1616.2 | uav_01=1136.7；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 3 | uav_01+uav_09 | 0.003569 | 1616.8 | uav_01=1133.6；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 4 | uav_01+uav_09 | 0.003569 | 1616.3 | uav_01=1135.6；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 5 | uav_01+uav_09 | 0.003569 | 1619.1 | uav_01=1138.1；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 6 | uav_01+uav_09 | 0.003569 | 1617.0 | uav_01=1137.6；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 7 | uav_01+uav_09 | 0.003569 | 1618.4 | uav_01=1139.3；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 8 | uav_01+uav_09 | 0.003569 | 1619.4 | uav_01=1140.3；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 9 | uav_01+uav_09 | 0.003569 | 1614.8 | uav_01=1134.5；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 10 | uav_01+uav_09 | 0.003569 | 1618.0 | uav_01=1139.5；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 11 | uav_01+uav_09 | 0.003569 | 1620.2 | uav_01=1138.2；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 12 | uav_01+uav_09 | 0.003569 | 1618.8 | uav_01=1139.5；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 13 | uav_01+uav_09 | 0.003569 | 1615.8 | uav_01=1135.1；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 14 | uav_01+uav_09 | 0.003569 | 1619.2 | uav_01=1137.1；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 15 | uav_01+uav_09 | 0.003569 | 1616.2 | uav_01=1135.5；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 16 | uav_01+uav_09 | 0.003569 | 1619.9 | uav_01=1141.7；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 17 | uav_01+uav_09 | 0.003569 | 1619.0 | uav_01=1138.2；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 18 | uav_01+uav_09 | 0.003569 | 1615.1 | uav_01=1132.1；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | synchronous | 19 | uav_01+uav_09 | 0.003569 | 1617.0 | uav_01=1135.9；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 0 | uav_01+uav_09 | 0.003569 | 2025.0 | uav_01=1214.4；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 1 | uav_01+uav_09 | 0.003569 | 1617.6 | uav_01=1133.5；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 2 | uav_01+uav_09 | 0.003569 | 1678.0 | uav_01=1116.8；uav_09=1195.2 | 作业/终点保持 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 3 | uav_01+uav_09 | 0.003569 | 2064.8 | uav_01=1116.8；uav_09=1391.9 | 作业/终点保持 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 4 | uav_01+uav_09 | 0.003569 | 1692.4 | uav_01=1212.1；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 5 | uav_01+uav_09 | 0.003569 | 1676.3 | uav_01=1116.8；uav_09=1198.6 | 作业/终点保持 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 6 | uav_01+uav_09 | 0.003569 | 1665.3 | uav_01=1182.4；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 7 | uav_01+uav_09 | 0.003569 | 1675.6 | uav_01=1195.1；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 8 | uav_01+uav_09 | 0.003569 | 1831.7 | uav_01=1139.0；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 9 | uav_01+uav_09 | 0.003569 | 1657.1 | uav_01=1116.8；uav_09=1180.1 | 作业/终点保持 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 10 | uav_01+uav_09 | 0.003569 | 1740.4 | uav_01=1116.8；uav_09=1177.8 | 作业/终点保持 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 11 | uav_01+uav_09 | 0.003569 | 1964.0 | uav_01=1197.8；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 12 | uav_01+uav_09 | 0.003569 | 1683.0 | uav_01=1141.2；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 13 | uav_01+uav_09 | 0.003569 | 1750.2 | uav_01=1138.3；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 14 | uav_01+uav_09 | 0.003569 | 2052.9 | uav_01=1572.4；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 15 | uav_01+uav_09 | 0.003569 | 2038.6 | uav_01=1361.2；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 16 | uav_01+uav_09 | 0.003569 | 2068.4 | uav_01=1116.8；uav_09=1428.7 | 作业/终点保持 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 17 | uav_01+uav_09 | 0.003569 | 1746.8 | uav_01=1116.8；uav_09=1198.1 | 作业/终点保持 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 18 | uav_01+uav_09 | 0.003569 | 1723.3 | uav_01=1140.5；uav_09=1137.5 | 终点保持/作业 | True | uav_01=1210.7；uav_09=1210.7 |
| geometry_04 | sequential | 19 | uav_01+uav_09 | 0.003569 | 1919.2 | uav_01=1116.8；uav_09=1249.6 | 作业/终点保持 | True | uav_01=1210.7；uav_09=1210.7 |

> 阶段判定：τ<0 起飞前等待；0≤τ<core_time 进场；core_time≤τ≤completion_time 作业；completion_time<τ≤末帧 撤离；τ>末帧 终点保持。core/completion 取自 `rehearsal.json`。冲突点取两机在 t_s 处位移后位置的**中点**，距离按场景平面（ENU 的 x、y）计算。

### 每轮 × 每 mode 的主导组合

| 轮 | mode | draw 数 | 主导（机对 → 阶段组合） | 次数 | 判定 |
|---|---|---:|---|---:|---|
| geometry_00 | sequential | 20 | uav_03+uav_05 → 终点保持+作业 | 10/20 | 分散 |
| geometry_00 | synchronous | 20 | uav_03+uav_05 → 作业+终点保持 | 20/20 | 结构性（与时刻无关） |
| geometry_01 | sequential | 20 | uav_08+uav_09 → 终点保持+作业 | 15/20 | 结构性（与时刻无关） |
| geometry_01 | synchronous | 20 | uav_08+uav_09 → 终点保持+作业 | 20/20 | 结构性（与时刻无关） |
| geometry_02 | sequential | 20 | uav_01+uav_03 → 作业+终点保持 | 16/20 | 结构性（与时刻无关） |
| geometry_02 | synchronous | 20 | uav_01+uav_03 → 作业+终点保持 | 20/20 | 结构性（与时刻无关） |
| geometry_03 | sequential | 20 | uav_03+uav_05 → 终点保持+作业 | 14/20 | 分散 |
| geometry_03 | synchronous | 20 | uav_03+uav_05 → 终点保持+作业 | 20/20 | 结构性（与时刻无关） |
| geometry_04 | sequential | 20 | uav_01+uav_09 → 终点保持+作业 | 12/20 | 分散 |
| geometry_04 | synchronous | 20 | uav_01+uav_09 → 终点保持+作业 | 20/20 | 结构性（与时刻无关） |

> 判定规则：同一机对 + 同一阶段组合在 20 次 draw 中出现 ≥15 次记为结构性。

### 冲突机对的空间量（不含时间）

| 轮 | 机对 | 两轨迹空间最近距离 m | 起点间距 m | 终点间距 m | 同组 |
|---|---|---:|---:|---:|---|
| geometry_02 | uav_01+uav_03 | 0.061401 | 92.812 | 0.005 | True |
| geometry_04 | uav_01+uav_09 | 0.042168 | 23.203 | 0.004 | True |
| geometry_00 | uav_03+uav_05 | 0.001737 | 46.406 | 0.002 | True |
| geometry_01 | uav_08+uav_09 | 0.012868 | 69.609 | 0.005 | True |

> 三条量均按 10 Hz 帧、两轨迹各取 5 帧降采样后在降采样点集上取最小值。

## family_s15_1b876e6b8b6f70c6_ext_007_regular

- attempt：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261016T184726Z`
- 轮数：2

| 轮 | candidate_index | rehearsal.json | timing_selection.json | category | 预演耗时(mtime估) | 时刻耗时(mtime估) |
|---|---|---|---|---|---|---|
| geometry_00 | 119 | True | True | timing_conflict | 579.236 | 0.843 |
| geometry_01 | None | False | False | None | — | — |

> 预演耗时 = mtime(rehearsal.json) − mtime(planning_checks.json)；时刻耗时 = mtime(timing_selection.json) − mtime(rehearsal.json)。这是 **mtime 估计**，不是被测代码的埋点。

- **未跑完**：停在 `geometry_01`。该轮已写出 ['skeleton.json', 'planning_checks.json']，缺 ['rehearsal.json', 'timing_selection.json', 'timing_calibration.json', 'planning_rejection.json']。

### 每次被拒 draw 的机对与阶段

| 轮 | mode | draw | 机对 | minimum_m | t_s | τ（本机） | 阶段 | 同组 | 到各自组目标中心 m |
|---|---|---:|---|---:|---:|---|---|---|---|
| geometry_00 | synchronous | 0 | uav_01+uav_06 | 0.001017 | 2846.6 | uav_01=2148.9；uav_06=2679.2 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 1 | uav_01+uav_06 | 0.001017 | 2851.5 | uav_01=2148.9；uav_06=2685.8 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 2 | uav_01+uav_06 | 0.001017 | 2850.6 | uav_01=2148.9；uav_06=2688.1 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 3 | uav_01+uav_06 | 0.001017 | 2847.8 | uav_01=2148.9；uav_06=2682.1 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 4 | uav_01+uav_06 | 0.001017 | 2848.8 | uav_01=2148.9；uav_06=2684.7 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 5 | uav_01+uav_06 | 0.001017 | 2849.5 | uav_01=2148.9；uav_06=2681.7 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 6 | uav_01+uav_06 | 0.001017 | 2847.3 | uav_01=2148.9；uav_06=2683.0 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 7 | uav_01+uav_06 | 0.001017 | 2847.7 | uav_01=2148.9；uav_06=2682.2 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 8 | uav_01+uav_06 | 0.001017 | 2846.8 | uav_01=2148.9；uav_06=2680.7 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 9 | uav_01+uav_06 | 0.001017 | 2851.4 | uav_01=2148.9；uav_06=2685.6 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 10 | uav_01+uav_06 | 0.001017 | 2847.0 | uav_01=2148.9；uav_06=2680.0 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 11 | uav_01+uav_06 | 0.001017 | 2847.4 | uav_01=2148.9；uav_06=2679.7 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 12 | uav_01+uav_06 | 0.001017 | 2849.9 | uav_01=2148.9；uav_06=2685.8 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 13 | uav_01+uav_06 | 0.001017 | 2849.0 | uav_01=2148.9；uav_06=2684.3 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 14 | uav_01+uav_06 | 0.001017 | 2847.2 | uav_01=2148.9；uav_06=2682.5 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 15 | uav_01+uav_06 | 0.001017 | 2848.6 | uav_01=2148.9；uav_06=2683.1 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 16 | uav_01+uav_06 | 0.001017 | 2849.6 | uav_01=2148.9；uav_06=2683.6 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 17 | uav_01+uav_06 | 0.001017 | 2849.6 | uav_01=2148.9；uav_06=2682.7 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 18 | uav_01+uav_06 | 0.001017 | 2851.6 | uav_01=2148.9；uav_06=2684.8 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | synchronous | 19 | uav_01+uav_06 | 0.001017 | 2848.6 | uav_01=2148.9；uav_06=2686.5 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 0 | uav_01+uav_06 | 0.001017 | 3158.5 | uav_01=2236.9；uav_06=2656.3 | 终点保持/作业 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 1 | uav_01+uav_06 | 0.001017 | 2850.6 | uav_01=2148.9；uav_06=2685.8 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 2 | uav_01+uav_06 | 0.001017 | 2918.5 | uav_01=2148.9；uav_06=2756.5 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 3 | uav_01+uav_06 | 0.001017 | 3055.9 | uav_01=2177.1；uav_06=2656.3 | 终点保持/作业 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 4 | uav_01+uav_06 | 0.001017 | 2878.8 | uav_01=2177.7；uav_06=2656.3 | 终点保持/作业 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 5 | uav_01+uav_06 | 0.001017 | 3366.4 | uav_01=2664.9；uav_06=2656.3 | 终点保持/作业 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 6 | uav_01+uav_06 | 0.001017 | 2934.0 | uav_01=2148.9；uav_06=2769.9 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 7 | uav_01+uav_06 | 0.001017 | 3218.4 | uav_01=2148.9；uav_06=2795.0 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 8 | uav_01+uav_06 | 0.001017 | 2847.9 | uav_01=2148.9；uav_06=2684.1 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 9 | uav_01+uav_06 | 0.001017 | 2980.8 | uav_01=2148.9；uav_06=2813.6 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 10 | uav_01+uav_06 | 0.001017 | 2985.9 | uav_01=2148.9；uav_06=2820.9 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 11 | uav_01+uav_06 | 0.001017 | 3119.0 | uav_01=2148.9；uav_06=2761.3 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 12 | uav_01+uav_06 | 0.001017 | 2909.8 | uav_01=2148.9；uav_06=2683.1 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 13 | uav_01+uav_06 | 0.001017 | 3156.2 | uav_01=2170.4；uav_06=2656.3 | 终点保持/作业 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 14 | uav_01+uav_06 | 0.001017 | 2944.7 | uav_01=2148.9；uav_06=2681.5 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 15 | uav_01+uav_06 | 0.001017 | 3150.2 | uav_01=2451.9；uav_06=2656.3 | 终点保持/作业 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 16 | uav_01+uav_06 | 0.001017 | 2940.2 | uav_01=2148.9；uav_06=2684.6 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 17 | uav_01+uav_06 | 0.001017 | 3083.1 | uav_01=2383.4；uav_06=2656.3 | 终点保持/作业 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 18 | uav_01+uav_06 | 0.001017 | 2884.7 | uav_01=2184.4；uav_06=2656.3 | 终点保持/作业 | True | uav_01=1401.8；uav_06=1401.8 |
| geometry_00 | sequential | 19 | uav_01+uav_06 | 0.001017 | 3177.4 | uav_01=2148.9；uav_06=2947.7 | 作业/终点保持 | True | uav_01=1401.8；uav_06=1401.8 |

> 阶段判定：τ<0 起飞前等待；0≤τ<core_time 进场；core_time≤τ≤completion_time 作业；completion_time<τ≤末帧 撤离；τ>末帧 终点保持。core/completion 取自 `rehearsal.json`。冲突点取两机在 t_s 处位移后位置的**中点**，距离按场景平面（ENU 的 x、y）计算。

### 每轮 × 每 mode 的主导组合

| 轮 | mode | draw 数 | 主导（机对 → 阶段组合） | 次数 | 判定 |
|---|---|---:|---|---:|---|
| geometry_00 | sequential | 20 | uav_01+uav_06 → 作业+终点保持 | 12/20 | 分散 |
| geometry_00 | synchronous | 20 | uav_01+uav_06 → 作业+终点保持 | 20/20 | 结构性（与时刻无关） |

> 判定规则：同一机对 + 同一阶段组合在 20 次 draw 中出现 ≥15 次记为结构性。

### 冲突机对的空间量（不含时间）

| 轮 | 机对 | 两轨迹空间最近距离 m | 起点间距 m | 终点间距 m | 同组 |
|---|---|---:|---:|---:|---|
| geometry_00 | uav_01+uav_06 | 0.028469 | 3900.953 | 0.001 | True |

> 三条量均按 10 Hz 帧、两轨迹各取 5 帧降采样后在降采样点集上取最小值。

## family_s15_38bedc9d791d547b_ext_007_regular

- attempt：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261016T191411Z`
- 轮数：4

| 轮 | candidate_index | rehearsal.json | timing_selection.json | category | 预演耗时(mtime估) | 时刻耗时(mtime估) |
|---|---|---|---|---|---|---|
| geometry_00 | 30 | True | True | timing_conflict | 637.438 | 0.786 |
| geometry_01 | 8 | True | True | timing_conflict | 656.846 | 0.557 |
| geometry_02 | 12 | True | True | timing_conflict | 928.579 | 0.758 |
| geometry_03 | 54 | True | True | None | 780.045 | 0.031 |

> 预演耗时 = mtime(rehearsal.json) − mtime(planning_checks.json)；时刻耗时 = mtime(timing_selection.json) − mtime(rehearsal.json)。这是 **mtime 估计**，不是被测代码的埋点。

- **未跑完**：停在 `geometry_03`。该轮已写出 ['skeleton.json', 'planning_checks.json', 'rehearsal.json', 'timing_selection.json', 'timing_calibration.json']，缺 ['planning_rejection.json']。

### 每次被拒 draw 的机对与阶段

| 轮 | mode | draw | 机对 | minimum_m | t_s | τ（本机） | 阶段 | 同组 | 到各自组目标中心 m |
|---|---|---:|---|---:|---:|---|---|---|---|
| geometry_00 | synchronous | 0 | uav_01+uav_02 | 0.000383 | 3262.5 | uav_01=3214.3；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 1 | uav_01+uav_02 | 0.000383 | 3261.4 | uav_01=3216.3；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 2 | uav_01+uav_02 | 0.000383 | 3259.8 | uav_01=3214.3；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 3 | uav_01+uav_02 | 0.000383 | 3257.5 | uav_01=3209.9；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 4 | uav_01+uav_02 | 0.000383 | 3257.4 | uav_01=3213.3；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 5 | uav_01+uav_02 | 0.000383 | 3258.8 | uav_01=3211.9；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 6 | uav_01+uav_02 | 0.000383 | 3258.5 | uav_01=3213.3；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 7 | uav_01+uav_02 | 0.000383 | 3261.7 | uav_01=3217.3；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 8 | uav_01+uav_02 | 0.000383 | 3257.4 | uav_01=3213.0；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 9 | uav_01+uav_02 | 0.000383 | 3258.3 | uav_01=3213.1；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 10 | uav_01+uav_02 | 0.000383 | 3260.8 | uav_01=3211.9；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 11 | uav_01+uav_02 | 0.000383 | 3259.2 | uav_01=3213.5；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 12 | uav_01+uav_02 | 0.000383 | 3258.3 | uav_01=3213.5；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 13 | uav_01+uav_02 | 0.000383 | 3262.0 | uav_01=3217.8；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 14 | uav_01+uav_02 | 0.000383 | 3260.2 | uav_01=3216.9；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 15 | uav_01+uav_02 | 0.000383 | 3261.9 | uav_01=3214.0；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 16 | uav_01+uav_02 | 0.000383 | 3257.8 | uav_01=3214.6；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 17 | uav_01+uav_02 | 0.000383 | 3262.3 | uav_01=3213.4；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 18 | uav_01+uav_02 | 0.000383 | 3258.6 | uav_01=3213.2；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | synchronous | 19 | uav_01+uav_02 | 0.000383 | 3262.0 | uav_01=3218.0；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 0 | uav_01+uav_02 | 0.000383 | 3539.9 | uav_01=3274.5；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 1 | uav_01+uav_02 | 0.000383 | 3422.2 | uav_01=3213.1；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 2 | uav_01+uav_02 | 0.000383 | 3259.0 | uav_01=3166.8；uav_02=3201.0 | 作业/终点保持 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 3 | uav_01+uav_02 | 0.000383 | 3332.4 | uav_01=3217.0；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 4 | uav_01+uav_02 | 0.000383 | 3461.9 | uav_01=3166.8；uav_02=3219.9 | 作业/终点保持 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 5 | uav_01+uav_02 | 0.000383 | 3512.3 | uav_01=3388.2；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 6 | uav_01+uav_02 | 0.000383 | 3405.1 | uav_01=3166.8；uav_02=3224.1 | 作业/终点保持 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 7 | uav_01+uav_02 | 0.000383 | 3295.8 | uav_01=3166.8；uav_02=3236.3 | 作业/终点保持 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 8 | uav_01+uav_02 | 0.000383 | 3474.7 | uav_01=3344.3；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 9 | uav_01+uav_02 | 0.000383 | 3258.0 | uav_01=3209.8；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 10 | uav_01+uav_02 | 0.000383 | 3463.0 | uav_01=3415.1；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 11 | uav_01+uav_02 | 0.000383 | 3502.9 | uav_01=3166.8；uav_02=3201.7 | 作业/终点保持 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 12 | uav_01+uav_02 | 0.000383 | 3316.5 | uav_01=3270.9；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 13 | uav_01+uav_02 | 0.000383 | 3444.8 | uav_01=3286.0；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 14 | uav_01+uav_02 | 0.000383 | 3393.7 | uav_01=3346.1；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 15 | uav_01+uav_02 | 0.000383 | 3263.0 | uav_01=3166.8；uav_02=3200.7 | 作业/终点保持 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 16 | uav_01+uav_02 | 0.000383 | 3298.8 | uav_01=3210.1；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 17 | uav_01+uav_02 | 0.000383 | 3488.4 | uav_01=3344.3；uav_02=3200.6 | 终点保持/作业 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 18 | uav_01+uav_02 | 0.000383 | 3586.1 | uav_01=3166.8；uav_02=3305.6 | 作业/终点保持 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_00 | sequential | 19 | uav_01+uav_02 | 0.000383 | 3555.5 | uav_01=3166.8；uav_02=3439.5 | 作业/终点保持 | True | uav_01=1304.5；uav_02=1304.5 |
| geometry_01 | synchronous | 0 | uav_03+uav_06 | 0.000353 | 3311.6 | uav_03=3251.3；uav_06=3251.8 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 1 | uav_03+uav_06 | 0.000353 | 3311.2 | uav_03=3251.3；uav_06=3247.3 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 2 | uav_03+uav_06 | 0.000353 | 3314.5 | uav_03=3251.3；uav_06=3250.1 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 3 | uav_03+uav_06 | 0.000353 | 3312.8 | uav_03=3251.3；uav_06=3248.6 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 4 | uav_03+uav_06 | 0.000353 | 3315.2 | uav_03=3251.3；uav_06=3250.6 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 5 | uav_03+uav_06 | 0.000353 | 3312.2 | uav_03=3251.3；uav_06=3251.4 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 6 | uav_03+uav_06 | 0.000353 | 3311.5 | uav_03=3251.3；uav_06=3246.7 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 7 | uav_03+uav_06 | 0.000353 | 3312.0 | uav_03=3251.3；uav_06=3251.7 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 8 | uav_03+uav_06 | 0.000353 | 3315.8 | uav_03=3251.3；uav_06=3251.8 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 9 | uav_03+uav_06 | 0.000353 | 3315.1 | uav_03=3251.3；uav_06=3254.8 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 10 | uav_03+uav_06 | 0.000353 | 3315.5 | uav_03=3251.3；uav_06=3254.2 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 11 | uav_03+uav_06 | 0.000353 | 3311.2 | uav_03=3251.3；uav_06=3249.2 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 12 | uav_03+uav_06 | 0.000353 | 3310.7 | uav_03=3251.3；uav_06=3247.2 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 13 | uav_03+uav_06 | 0.000353 | 3311.9 | uav_03=3251.3；uav_06=3251.1 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 14 | uav_03+uav_06 | 0.000353 | 3315.1 | uav_03=3251.3；uav_06=3250.1 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 15 | uav_03+uav_06 | 0.000353 | 3314.0 | uav_03=3251.3；uav_06=3250.3 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 16 | uav_03+uav_06 | 0.000353 | 3313.8 | uav_03=3251.3；uav_06=3249.1 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 17 | uav_03+uav_06 | 0.000353 | 3312.7 | uav_03=3251.3；uav_06=3252.3 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 18 | uav_03+uav_06 | 0.000353 | 3311.4 | uav_03=3251.3；uav_06=3246.8 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | synchronous | 19 | uav_03+uav_06 | 0.000353 | 3310.3 | uav_03=3251.3；uav_06=3247.2 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 0 | uav_03+uav_06 | 0.000353 | 3611.2 | uav_03=3550.2；uav_06=3218.3 | 终点保持/作业 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 1 | uav_03+uav_06 | 0.000353 | 3474.2 | uav_03=3251.3；uav_06=3365.2 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 2 | uav_03+uav_06 | 0.000353 | 3447.3 | uav_03=3251.3；uav_06=3333.1 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 3 | uav_03+uav_06 | 0.000353 | 3312.4 | uav_03=3251.3；uav_06=3249.8 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 4 | uav_03+uav_06 | 0.000353 | 3413.1 | uav_03=3301.8；uav_06=3218.3 | 终点保持/作业 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 5 | uav_03+uav_06 | 0.000353 | 3485.9 | uav_03=3422.4；uav_06=3218.3 | 终点保持/作业 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 6 | uav_03+uav_06 | 0.000353 | 3569.4 | uav_03=3251.3；uav_06=3509.5 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 7 | uav_03+uav_06 | 0.000353 | 3395.9 | uav_03=3251.3；uav_06=3287.7 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 8 | uav_03+uav_06 | 0.000353 | 3661.7 | uav_03=3519.3；uav_06=3218.3 | 终点保持/作业 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 9 | uav_03+uav_06 | 0.000353 | 3455.6 | uav_03=3284.3；uav_06=3218.3 | 终点保持/作业 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 10 | uav_03+uav_06 | 0.000353 | 3571.7 | uav_03=3376.9；uav_06=3218.3 | 终点保持/作业 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 11 | uav_03+uav_06 | 0.000353 | 3478.3 | uav_03=3416.0；uav_06=3218.3 | 终点保持/作业 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 12 | uav_03+uav_06 | 0.000353 | 3311.6 | uav_03=3251.3；uav_06=3247.5 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 13 | uav_03+uav_06 | 0.000353 | 3499.0 | uav_03=3251.3；uav_06=3367.7 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 14 | uav_03+uav_06 | 0.000353 | 3616.8 | uav_03=3510.6；uav_06=3218.3 | 终点保持/作业 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 15 | uav_03+uav_06 | 0.000353 | 3527.3 | uav_03=3251.3；uav_06=3252.0 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 16 | uav_03+uav_06 | 0.000353 | 3355.8 | uav_03=3251.3；uav_06=3291.6 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 17 | uav_03+uav_06 | 0.000353 | 3550.7 | uav_03=3336.9；uav_06=3218.3 | 终点保持/作业 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 18 | uav_03+uav_06 | 0.000353 | 3482.8 | uav_03=3251.3；uav_06=3418.9 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_01 | sequential | 19 | uav_03+uav_06 | 0.000353 | 3610.4 | uav_03=3251.3；uav_06=3302.7 | 作业/终点保持 | True | uav_03=1243.9；uav_06=1243.9 |
| geometry_02 | synchronous | 0 | uav_05+uav_06 | 0.000239 | 4252.5 | uav_05=4185.3；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 1 | uav_05+uav_06 | 0.000239 | 4256.6 | uav_05=4193.2；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 2 | uav_05+uav_06 | 0.000239 | 4257.1 | uav_05=4190.2；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 3 | uav_05+uav_06 | 0.000239 | 4256.9 | uav_05=4190.9；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 4 | uav_05+uav_06 | 0.000239 | 4257.3 | uav_05=4190.5；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 5 | uav_05+uav_06 | 0.000239 | 4253.5 | uav_05=4190.0；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 6 | uav_05+uav_06 | 0.000239 | 4257.5 | uav_05=4190.9；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 7 | uav_05+uav_06 | 0.000239 | 4253.0 | uav_05=4186.1；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 8 | uav_05+uav_06 | 0.000239 | 4256.7 | uav_05=4190.2；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 9 | uav_05+uav_06 | 0.000239 | 4253.0 | uav_05=4186.0；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 10 | uav_05+uav_06 | 0.000239 | 4254.0 | uav_05=4188.8；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 11 | uav_05+uav_06 | 0.000239 | 4254.7 | uav_05=4191.7；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 12 | uav_05+uav_06 | 0.000239 | 4256.2 | uav_05=4189.6；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 13 | uav_05+uav_06 | 0.000239 | 4253.5 | uav_05=4191.5；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 14 | uav_05+uav_06 | 0.000239 | 4257.7 | uav_05=4190.1；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 15 | uav_05+uav_06 | 0.000239 | 4256.4 | uav_05=4189.0；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 16 | uav_05+uav_06 | 0.000239 | 4257.4 | uav_05=4194.2；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 17 | uav_05+uav_06 | 0.000239 | 4253.1 | uav_05=4189.6；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 18 | uav_05+uav_06 | 0.000239 | 4257.3 | uav_05=4194.5；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | synchronous | 19 | uav_05+uav_06 | 0.000239 | 4255.8 | uav_05=4188.4；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 0 | uav_05+uav_06 | 0.000239 | 4585.6 | uav_05=4476.8；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 1 | uav_05+uav_06 | 0.000239 | 4301.7 | uav_05=4235.7；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 2 | uav_05+uav_06 | 0.000239 | 4306.9 | uav_05=4191.3；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 3 | uav_05+uav_06 | 0.000239 | 4255.3 | uav_05=4192.9；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 4 | uav_05+uav_06 | 0.000239 | 4387.5 | uav_05=4135.5；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 5 | uav_05+uav_06 | 0.000239 | 4460.3 | uav_05=4077.4；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 6 | uav_05+uav_06 | 0.000239 | 4387.2 | uav_05=4065.1；uav_06=4319.3 | 作业/终点保持 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 7 | uav_05+uav_06 | 0.000239 | 4300.9 | uav_05=4153.8；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 8 | uav_05+uav_06 | 0.000239 | 4636.1 | uav_05=4272.8；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 9 | uav_05+uav_06 | 0.000239 | 4430.0 | uav_05=4189.9；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 10 | uav_05+uav_06 | 0.000239 | 4546.1 | uav_05=4282.1；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 11 | uav_05+uav_06 | 0.000239 | 4452.7 | uav_05=4268.2；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 12 | uav_05+uav_06 | 0.000239 | 4256.8 | uav_05=4192.6；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 13 | uav_05+uav_06 | 0.000239 | 4324.0 | uav_05=4070.7；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 14 | uav_05+uav_06 | 0.000239 | 4591.2 | uav_05=4315.2；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 15 | uav_05+uav_06 | 0.000239 | 4468.0 | uav_05=4405.6；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 16 | uav_05+uav_06 | 0.000239 | 4256.9 | uav_05=4150.4；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 17 | uav_05+uav_06 | 0.000239 | 4525.1 | uav_05=4416.3；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 18 | uav_05+uav_06 | 0.000239 | 4462.4 | uav_05=4065.1；uav_06=4390.5 | 作业/终点保持 | True | uav_05=1487.6；uav_06=1487.6 |
| geometry_02 | sequential | 19 | uav_05+uav_06 | 0.000239 | 4500.4 | uav_05=4436.9；uav_06=4184.7 | 终点保持/作业 | True | uav_05=1487.6；uav_06=1487.6 |

> 阶段判定：τ<0 起飞前等待；0≤τ<core_time 进场；core_time≤τ≤completion_time 作业；completion_time<τ≤末帧 撤离；τ>末帧 终点保持。core/completion 取自 `rehearsal.json`。冲突点取两机在 t_s 处位移后位置的**中点**，距离按场景平面（ENU 的 x、y）计算。

### 每轮 × 每 mode 的主导组合

| 轮 | mode | draw 数 | 主导（机对 → 阶段组合） | 次数 | 判定 |
|---|---|---:|---|---:|---|
| geometry_00 | sequential | 20 | uav_01+uav_02 → 终点保持+作业 | 12/20 | 分散 |
| geometry_00 | synchronous | 20 | uav_01+uav_02 → 终点保持+作业 | 20/20 | 结构性（与时刻无关） |
| geometry_01 | sequential | 20 | uav_03+uav_06 → 作业+终点保持 | 11/20 | 分散 |
| geometry_01 | synchronous | 20 | uav_03+uav_06 → 作业+终点保持 | 20/20 | 结构性（与时刻无关） |
| geometry_02 | sequential | 20 | uav_05+uav_06 → 终点保持+作业 | 18/20 | 结构性（与时刻无关） |
| geometry_02 | synchronous | 20 | uav_05+uav_06 → 终点保持+作业 | 20/20 | 结构性（与时刻无关） |

> 判定规则：同一机对 + 同一阶段组合在 20 次 draw 中出现 ≥15 次记为结构性。

### 冲突机对的空间量（不含时间）

| 轮 | 机对 | 两轨迹空间最近距离 m | 起点间距 m | 终点间距 m | 同组 |
|---|---|---:|---:|---:|---|
| geometry_00 | uav_01+uav_02 | 0.049666 | 19.198 | 0.000 | True |
| geometry_01 | uav_03+uav_06 | 0.000654 | 19.198 | 0.000 | True |
| geometry_02 | uav_05+uav_06 | 0.020719 | 38.396 | 0.000 | True |

> 三条量均按 10 Hz 帧、两轨迹各取 5 帧降采样后在降采样点集上取最小值。

## family_s15_c713f51898e81011_ext_002_regular

- attempt：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261016T191411Z`
- 轮数：5

| 轮 | candidate_index | rehearsal.json | timing_selection.json | category | 预演耗时(mtime估) | 时刻耗时(mtime估) |
|---|---|---|---|---|---|---|
| geometry_00 | 162 | True | True | timing_conflict | 793.697 | 1.679 |
| geometry_01 | 97 | True | True | timing_conflict | 804.291 | 1.246 |
| geometry_02 | 39 | True | True | timing_conflict | 564.214 | 0.977 |
| geometry_03 | 46 | True | True | timing_conflict | 857.58 | 1.495 |
| geometry_04 | None | False | False | None | — | — |

> 预演耗时 = mtime(rehearsal.json) − mtime(planning_checks.json)；时刻耗时 = mtime(timing_selection.json) − mtime(rehearsal.json)。这是 **mtime 估计**，不是被测代码的埋点。

- **未跑完**：停在 `geometry_04`。该轮已写出 ['skeleton.json', 'planning_checks.json']，缺 ['rehearsal.json', 'timing_selection.json', 'timing_calibration.json', 'planning_rejection.json']。

### 每次被拒 draw 的机对与阶段

| 轮 | mode | draw | 机对 | minimum_m | t_s | τ（本机） | 阶段 | 同组 | 到各自组目标中心 m |
|---|---|---:|---|---:|---:|---|---|---|---|
| geometry_00 | synchronous | 0 | uav_05+uav_08 | 0.000545 | 3675.7 | uav_05=3087.2；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 1 | uav_05+uav_08 | 0.000545 | 3675.9 | uav_05=3088.8；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 2 | uav_05+uav_08 | 0.000545 | 3675.2 | uav_05=3090.3；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 3 | uav_05+uav_08 | 0.000545 | 3674.0 | uav_05=3086.1；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 4 | uav_05+uav_08 | 0.000545 | 3673.1 | uav_05=3084.8；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 5 | uav_05+uav_08 | 0.000545 | 3676.3 | uav_05=3086.3；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 6 | uav_05+uav_08 | 0.000545 | 3673.5 | uav_05=3087.8；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 7 | uav_05+uav_08 | 0.000545 | 3675.3 | uav_05=3085.4；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 8 | uav_05+uav_08 | 0.000545 | 3677.7 | uav_05=3087.7；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 9 | uav_05+uav_08 | 0.000545 | 3676.5 | uav_05=3090.9；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 10 | uav_05+uav_08 | 0.000545 | 3677.2 | uav_05=3091.8；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 11 | uav_05+uav_08 | 0.000545 | 3675.2 | uav_05=3089.6；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 12 | uav_05+uav_08 | 0.000545 | 3675.4 | uav_05=3089.6；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 13 | uav_05+uav_08 | 0.000545 | 3674.0 | uav_05=3086.2；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 14 | uav_05+uav_08 | 0.000545 | 3675.6 | uav_05=3089.7；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 15 | uav_05+uav_08 | 0.000545 | 3676.4 | uav_05=3089.2；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 16 | uav_05+uav_08 | 0.000545 | 3673.0 | uav_05=3084.1；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 17 | uav_05+uav_08 | 0.000545 | 3677.5 | uav_05=3087.4；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 18 | uav_05+uav_08 | 0.000545 | 3673.4 | uav_05=3085.5；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | synchronous | 19 | uav_05+uav_08 | 0.000545 | 3673.4 | uav_05=3086.9；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 0 | uav_05+uav_08 | 0.000545 | 3980.9 | uav_05=3396.2；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 1 | uav_05+uav_08 | 0.000545 | 3982.7 | uav_05=3350.6；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 2 | uav_05+uav_08 | 0.000545 | 3715.8 | uav_05=3087.3；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 3 | uav_05+uav_08 | 0.000545 | 3728.4 | uav_05=3142.9；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 4 | uav_05+uav_08 | 0.000545 | 3675.5 | uav_05=3015.2；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 5 | uav_05+uav_08 | 0.000545 | 3673.1 | uav_05=3082.9；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 6 | uav_05+uav_08 | 0.000545 | 3826.8 | uav_05=3151.4；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 7 | uav_05+uav_08 | 0.000545 | 3825.9 | uav_05=3132.3；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 8 | uav_05+uav_08 | 0.000545 | 3745.4 | uav_05=3037.9；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 9 | uav_05+uav_08 | 0.000545 | 3790.2 | uav_05=3153.7；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 10 | uav_05+uav_08 | 0.000545 | 4022.8 | uav_05=3270.5；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 11 | uav_05+uav_08 | 0.000545 | 3729.8 | uav_05=3144.2；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 12 | uav_05+uav_08 | 0.000545 | 3923.0 | uav_05=3004.9；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 13 | uav_05+uav_08 | 0.000545 | 3891.1 | uav_05=3043.8；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 14 | uav_05+uav_08 | 0.000545 | 3844.6 | uav_05=2980.4；uav_08=3040.1 | 作业/终点保持 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 15 | uav_05+uav_08 | 0.000545 | 3866.0 | uav_05=3032.2；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 16 | uav_05+uav_08 | 0.000545 | 3677.7 | uav_05=3087.5；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 17 | uav_05+uav_08 | 0.000545 | 3834.0 | uav_05=3248.8；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 18 | uav_05+uav_08 | 0.000545 | 4016.4 | uav_05=3267.9；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_00 | sequential | 19 | uav_05+uav_08 | 0.000545 | 3949.4 | uav_05=3233.3；uav_08=3016.0 | 终点保持/作业 | True | uav_05=1157.4；uav_08=1157.4 |
| geometry_01 | synchronous | 0 | uav_08+uav_10 | 0.000151 | 3675.8 | uav_08=3285.7；uav_10=3082.1 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 1 | uav_08+uav_10 | 0.000151 | 3676.0 | uav_08=3285.7；uav_10=3079.0 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 2 | uav_08+uav_10 | 0.000151 | 3675.3 | uav_08=3285.7；uav_10=3080.6 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 3 | uav_08+uav_10 | 0.000151 | 3674.1 | uav_08=3285.7；uav_10=3077.4 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 4 | uav_08+uav_10 | 0.000151 | 3673.2 | uav_08=3285.7；uav_10=3077.7 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 5 | uav_08+uav_10 | 0.000151 | 3676.4 | uav_08=3285.7；uav_10=3077.2 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 6 | uav_08+uav_10 | 0.000151 | 3673.6 | uav_08=3285.7；uav_10=3078.4 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 7 | uav_08+uav_10 | 0.000151 | 3675.4 | uav_08=3285.7；uav_10=3079.8 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 8 | uav_08+uav_10 | 0.000151 | 3677.8 | uav_08=3285.7；uav_10=3084.2 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 9 | uav_08+uav_10 | 0.000151 | 3676.6 | uav_08=3285.7；uav_10=3077.8 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 10 | uav_08+uav_10 | 0.000151 | 3677.3 | uav_08=3285.7；uav_10=3081.5 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 11 | uav_08+uav_10 | 0.000151 | 3675.3 | uav_08=3285.7；uav_10=3081.6 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 12 | uav_08+uav_10 | 0.000151 | 3675.5 | uav_08=3285.7；uav_10=3081.5 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 13 | uav_08+uav_10 | 0.000151 | 3674.1 | uav_08=3285.7；uav_10=3076.2 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 14 | uav_08+uav_10 | 0.000151 | 3675.7 | uav_08=3285.7；uav_10=3078.7 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 15 | uav_08+uav_10 | 0.000151 | 3676.5 | uav_08=3285.7；uav_10=3078.3 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 16 | uav_08+uav_10 | 0.000151 | 3673.1 | uav_08=3285.7；uav_10=3079.6 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 17 | uav_08+uav_10 | 0.000151 | 3677.6 | uav_08=3285.7；uav_10=3080.1 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 18 | uav_08+uav_10 | 0.000151 | 3673.5 | uav_08=3285.7；uav_10=3079.9 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | synchronous | 19 | uav_08+uav_10 | 0.000151 | 3673.5 | uav_08=3285.7；uav_10=3078.1 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 0 | uav_08+uav_10 | 0.000151 | 3981.0 | uav_08=3285.7；uav_10=3228.5 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 1 | uav_08+uav_10 | 0.000151 | 3982.8 | uav_08=3285.7；uav_10=3340.7 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 2 | uav_08+uav_10 | 0.000151 | 3715.9 | uav_08=3285.7；uav_10=3073.5 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 3 | uav_08+uav_10 | 0.000151 | 3728.5 | uav_08=3285.7；uav_10=3079.9 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 4 | uav_08+uav_10 | 0.000151 | 3764.8 | uav_08=3374.9；uav_10=3030.8 | 终点保持/作业 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 5 | uav_08+uav_10 | 0.000151 | 4063.8 | uav_08=3676.3；uav_10=3030.8 | 终点保持/作业 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 6 | uav_08+uav_10 | 0.000151 | 3826.9 | uav_08=3285.7；uav_10=3079.3 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 7 | uav_08+uav_10 | 0.000151 | 3837.2 | uav_08=3296.9；uav_10=3030.8 | 终点保持/作业 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 8 | uav_08+uav_10 | 0.000151 | 3745.5 | uav_08=3285.7；uav_10=3146.4 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 9 | uav_08+uav_10 | 0.000151 | 3810.3 | uav_08=3305.7；uav_10=3030.8 | 终点保持/作业 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 10 | uav_08+uav_10 | 0.000151 | 4022.9 | uav_08=3285.7；uav_10=3341.2 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 11 | uav_08+uav_10 | 0.000151 | 3793.9 | uav_08=3349.7；uav_10=3030.8 | 终点保持/作业 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 12 | uav_08+uav_10 | 0.000151 | 3923.1 | uav_08=3285.7；uav_10=3275.3 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 13 | uav_08+uav_10 | 0.000151 | 4018.2 | uav_08=3412.7；uav_10=3030.8 | 终点保持/作业 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 14 | uav_08+uav_10 | 0.000151 | 3961.2 | uav_08=3426.3；uav_10=3030.8 | 终点保持/作业 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 15 | uav_08+uav_10 | 0.000151 | 4019.0 | uav_08=3438.6；uav_10=3030.8 | 终点保持/作业 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 16 | uav_08+uav_10 | 0.000151 | 3677.8 | uav_08=3285.7；uav_10=3080.8 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 17 | uav_08+uav_10 | 0.000151 | 3834.1 | uav_08=3285.7；uav_10=3239.3 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 18 | uav_08+uav_10 | 0.000151 | 4016.5 | uav_08=3285.7；uav_10=3311.4 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_01 | sequential | 19 | uav_08+uav_10 | 0.000151 | 3949.5 | uav_08=3285.7；uav_10=3351.2 | 作业/终点保持 | True | uav_08=1189.7；uav_10=1189.7 |
| geometry_02 | synchronous | 0 | uav_04+uav_09 | 0.000085 | 3242.4 | uav_04=2526.2；uav_09=2530.1 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 1 | uav_04+uav_09 | 0.000085 | 3239.3 | uav_04=2526.2；uav_09=2527.5 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 2 | uav_04+uav_09 | 0.000085 | 3239.0 | uav_04=2526.2；uav_09=2525.9 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 3 | uav_04+uav_09 | 0.000085 | 3241.4 | uav_04=2526.2；uav_09=2529.6 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 4 | uav_04+uav_09 | 0.000085 | 3240.3 | uav_04=2526.2；uav_09=2528.3 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 5 | uav_04+uav_09 | 0.000085 | 3240.6 | uav_04=2526.2；uav_09=2524.6 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 6 | uav_04+uav_09 | 0.000085 | 3236.9 | uav_04=2526.2；uav_09=2524.3 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 7 | uav_04+uav_09 | 0.000085 | 3242.4 | uav_04=2526.2；uav_09=2530.2 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 8 | uav_04+uav_09 | 0.000085 | 3239.1 | uav_04=2526.2；uav_09=2522.2 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 9 | uav_04+uav_09 | 0.000085 | 3237.8 | uav_04=2526.2；uav_09=2522.1 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 10 | uav_04+uav_09 | 0.000085 | 3238.9 | uav_04=2526.2；uav_09=2522.5 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 11 | uav_04+uav_09 | 0.000085 | 3238.0 | uav_04=2526.2；uav_09=2525.4 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 12 | uav_04+uav_09 | 0.000085 | 3239.0 | uav_04=2526.2；uav_09=2522.6 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 13 | uav_04+uav_09 | 0.000085 | 3239.4 | uav_04=2526.2；uav_09=2523.0 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 14 | uav_04+uav_09 | 0.000085 | 3240.3 | uav_04=2526.2；uav_09=2523.7 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 15 | uav_04+uav_09 | 0.000085 | 3242.2 | uav_04=2526.2；uav_09=2525.1 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 16 | uav_04+uav_09 | 0.000085 | 3240.8 | uav_04=2526.2；uav_09=2527.9 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 17 | uav_04+uav_09 | 0.000085 | 3241.0 | uav_04=2526.2；uav_09=2527.6 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 18 | uav_04+uav_09 | 0.000085 | 3237.7 | uav_04=2526.2；uav_09=2522.5 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | synchronous | 19 | uav_04+uav_09 | 0.000085 | 3238.3 | uav_04=2526.2；uav_09=2524.3 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 0 | uav_04+uav_09 | 0.000085 | 3419.1 | uav_04=2634.9；uav_09=2482.3 | 终点保持/作业 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 1 | uav_04+uav_09 | 0.000085 | 3617.6 | uav_04=2526.2；uav_09=2660.7 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 2 | uav_04+uav_09 | 0.000085 | 3240.5 | uav_04=2529.7；uav_09=2482.3 | 终点保持/作业 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 3 | uav_04+uav_09 | 0.000085 | 3346.9 | uav_04=2526.2；uav_09=2578.1 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 4 | uav_04+uav_09 | 0.000085 | 3271.0 | uav_04=2556.0；uav_09=2482.3 | 终点保持/作业 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 5 | uav_04+uav_09 | 0.000085 | 3852.6 | uav_04=2526.2；uav_09=3077.1 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 6 | uav_04+uav_09 | 0.000085 | 3393.7 | uav_04=2526.2；uav_09=2525.3 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 7 | uav_04+uav_09 | 0.000085 | 3390.3 | uav_04=2526.2；uav_09=2612.3 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 8 | uav_04+uav_09 | 0.000085 | 3471.5 | uav_04=2688.1；uav_09=2482.3 | 终点保持/作业 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 9 | uav_04+uav_09 | 0.000085 | 3293.0 | uav_04=2526.2；uav_09=2578.9 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 10 | uav_04+uav_09 | 0.000085 | 3496.4 | uav_04=2531.6；uav_09=2482.3 | 终点保持/作业 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 11 | uav_04+uav_09 | 0.000085 | 3713.2 | uav_04=2526.2；uav_09=2777.6 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 12 | uav_04+uav_09 | 0.000085 | 3711.2 | uav_04=2526.2；uav_09=2828.7 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 13 | uav_04+uav_09 | 0.000085 | 3389.5 | uav_04=2526.2；uav_09=2673.7 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 14 | uav_04+uav_09 | 0.000085 | 3590.4 | uav_04=2873.8；uav_09=2482.3 | 终点保持/作业 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 15 | uav_04+uav_09 | 0.000085 | 3484.2 | uav_04=2526.2；uav_09=2769.3 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 16 | uav_04+uav_09 | 0.000085 | 3321.5 | uav_04=2526.2；uav_09=2609.2 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 17 | uav_04+uav_09 | 0.000085 | 3401.4 | uav_04=2526.2；uav_09=2576.1 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 18 | uav_04+uav_09 | 0.000085 | 3585.8 | uav_04=2526.2；uav_09=2664.8 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_02 | sequential | 19 | uav_04+uav_09 | 0.000085 | 3667.9 | uav_04=2526.2；uav_09=2763.0 | 作业/终点保持 | True | uav_04=1054.8；uav_09=1054.8 |
| geometry_03 | synchronous | 0 | uav_05+uav_08 | 0.000165 | 3840.0 | uav_05=3429.4；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 1 | uav_05+uav_08 | 0.000165 | 3840.2 | uav_05=3431.0；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 2 | uav_05+uav_08 | 0.000165 | 3839.5 | uav_05=3432.5；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 3 | uav_05+uav_08 | 0.000165 | 3838.3 | uav_05=3428.3；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 4 | uav_05+uav_08 | 0.000165 | 3837.4 | uav_05=3427.0；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 5 | uav_05+uav_08 | 0.000165 | 3840.6 | uav_05=3428.5；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 6 | uav_05+uav_08 | 0.000165 | 3837.8 | uav_05=3430.0；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 7 | uav_05+uav_08 | 0.000165 | 3839.6 | uav_05=3427.6；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 8 | uav_05+uav_08 | 0.000165 | 3842.0 | uav_05=3429.9；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 9 | uav_05+uav_08 | 0.000165 | 3840.8 | uav_05=3433.1；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 10 | uav_05+uav_08 | 0.000165 | 3841.5 | uav_05=3434.0；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 11 | uav_05+uav_08 | 0.000165 | 3839.5 | uav_05=3431.8；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 12 | uav_05+uav_08 | 0.000165 | 3839.7 | uav_05=3431.8；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 13 | uav_05+uav_08 | 0.000165 | 3838.3 | uav_05=3428.4；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 14 | uav_05+uav_08 | 0.000165 | 3839.9 | uav_05=3431.9；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 15 | uav_05+uav_08 | 0.000165 | 3840.7 | uav_05=3431.4；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 16 | uav_05+uav_08 | 0.000165 | 3837.3 | uav_05=3426.3；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 17 | uav_05+uav_08 | 0.000165 | 3841.8 | uav_05=3429.6；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 18 | uav_05+uav_08 | 0.000165 | 3837.7 | uav_05=3427.7；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | synchronous | 19 | uav_05+uav_08 | 0.000165 | 3837.7 | uav_05=3429.1；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 0 | uav_05+uav_08 | 0.000165 | 4145.2 | uav_05=3738.4；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 1 | uav_05+uav_08 | 0.000165 | 4147.0 | uav_05=3692.8；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 2 | uav_05+uav_08 | 0.000165 | 3880.1 | uav_05=3429.5；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 3 | uav_05+uav_08 | 0.000165 | 3892.7 | uav_05=3485.1；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 4 | uav_05+uav_08 | 0.000165 | 3839.8 | uav_05=3357.4；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 5 | uav_05+uav_08 | 0.000165 | 3837.4 | uav_05=3425.1；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 6 | uav_05+uav_08 | 0.000165 | 3991.1 | uav_05=3493.6；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 7 | uav_05+uav_08 | 0.000165 | 3990.2 | uav_05=3474.5；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 8 | uav_05+uav_08 | 0.000165 | 3909.7 | uav_05=3380.1；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 9 | uav_05+uav_08 | 0.000165 | 3954.5 | uav_05=3495.9；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 10 | uav_05+uav_08 | 0.000165 | 4187.1 | uav_05=3612.7；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 11 | uav_05+uav_08 | 0.000165 | 3894.1 | uav_05=3486.4；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 12 | uav_05+uav_08 | 0.000165 | 4087.3 | uav_05=3347.1；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 13 | uav_05+uav_08 | 0.000165 | 4055.4 | uav_05=3386.0；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 14 | uav_05+uav_08 | 0.000165 | 4026.8 | uav_05=3340.5；uav_08=3836.6 | 作业/终点保持 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 15 | uav_05+uav_08 | 0.000165 | 4030.3 | uav_05=3374.4；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 16 | uav_05+uav_08 | 0.000165 | 3842.0 | uav_05=3429.7；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 17 | uav_05+uav_08 | 0.000165 | 3998.3 | uav_05=3591.0；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 18 | uav_05+uav_08 | 0.000165 | 4180.7 | uav_05=3610.1；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |
| geometry_03 | sequential | 19 | uav_05+uav_08 | 0.000165 | 4113.7 | uav_05=3575.5；uav_08=3794.6 | 终点保持/作业 | True | uav_05=1197.4；uav_08=1197.4 |

> 阶段判定：τ<0 起飞前等待；0≤τ<core_time 进场；core_time≤τ≤completion_time 作业；completion_time<τ≤末帧 撤离；τ>末帧 终点保持。core/completion 取自 `rehearsal.json`。冲突点取两机在 t_s 处位移后位置的**中点**，距离按场景平面（ENU 的 x、y）计算。

### 每轮 × 每 mode 的主导组合

| 轮 | mode | draw 数 | 主导（机对 → 阶段组合） | 次数 | 判定 |
|---|---|---:|---|---:|---|
| geometry_00 | sequential | 20 | uav_05+uav_08 → 终点保持+作业 | 19/20 | 结构性（与时刻无关） |
| geometry_00 | synchronous | 20 | uav_05+uav_08 → 终点保持+作业 | 20/20 | 结构性（与时刻无关） |
| geometry_01 | sequential | 20 | uav_08+uav_10 → 作业+终点保持 | 12/20 | 分散 |
| geometry_01 | synchronous | 20 | uav_08+uav_10 → 作业+终点保持 | 20/20 | 结构性（与时刻无关） |
| geometry_02 | sequential | 20 | uav_04+uav_09 → 作业+终点保持 | 14/20 | 分散 |
| geometry_02 | synchronous | 20 | uav_04+uav_09 → 作业+终点保持 | 20/20 | 结构性（与时刻无关） |
| geometry_03 | sequential | 20 | uav_05+uav_08 → 终点保持+作业 | 19/20 | 结构性（与时刻无关） |
| geometry_03 | synchronous | 20 | uav_05+uav_08 → 终点保持+作业 | 20/20 | 结构性（与时刻无关） |

> 判定规则：同一机对 + 同一阶段组合在 20 次 draw 中出现 ≥15 次记为结构性。

### 冲突机对的空间量（不含时间）

| 轮 | 机对 | 两轨迹空间最近距离 m | 起点间距 m | 终点间距 m | 同组 |
|---|---|---:|---:|---:|---|
| geometry_02 | uav_04+uav_09 | 0.030152 | 22.627 | 0.000 | True |
| geometry_00 | uav_05+uav_08 | 0.049409 | 6586.223 | 0.001 | True |
| geometry_01 | uav_08+uav_10 | 0.030714 | 6556.336 | 0.000 | True |

> 三条量均按 10 Hz 帧、两轨迹各取 5 帧降采样后在降采样点集上取最小值。

## family_s15_1c267d4d7000043d_ext_005_regular

- attempt：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15sim_20261016T191411Z`
- 轮数：1

| 轮 | candidate_index | rehearsal.json | timing_selection.json | category | 预演耗时(mtime估) | 时刻耗时(mtime估) |
|---|---|---|---|---|---|---|
| geometry_00 | 62 | True | True | None | 63.467 | 0.008 |

> 预演耗时 = mtime(rehearsal.json) − mtime(planning_checks.json)；时刻耗时 = mtime(timing_selection.json) − mtime(rehearsal.json)。这是 **mtime 估计**，不是被测代码的埋点。

- 对照组（严格配对成功），不进入被拒 draw 的分阶段统计。

## 结论表

| 骨架 | 轮 | mode | 主导机对 | 主导阶段组合 | 同组/跨组 | 结构性/分散 |
|---|---|---|---|---|---|---|
| family_s15_79c93b22d09e8a7a_ext_002_regular | geometry_00 | sequential | uav_03+uav_05 | 作业+终点保持 | 同组 | 分散 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | geometry_00 | synchronous | uav_03+uav_05 | 作业+终点保持 | 同组 | 结构性 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | geometry_01 | sequential | uav_02+uav_04 | 终点保持+作业 | 同组 | 分散 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | geometry_01 | synchronous | uav_02+uav_04 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | geometry_02 | sequential | uav_03+uav_05 | 终点保持+作业 | 同组 | 分散 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | geometry_02 | synchronous | uav_02+uav_03 | 作业+终点保持 | 同组 | 结构性 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | geometry_03 | sequential | uav_02+uav_03 | 作业+终点保持 | 同组 | 分散 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | geometry_03 | synchronous | uav_02+uav_03 | 作业+终点保持 | 同组 | 结构性 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | geometry_04 | sequential | uav_03+uav_04 | 终点保持+作业 | 同组 | 分散 |
| family_s15_79c93b22d09e8a7a_ext_002_regular | geometry_04 | synchronous | uav_03+uav_04 | 作业+终点保持 | 同组 | 结构性 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | geometry_00 | sequential | uav_01+uav_06 | 作业+终点保持 | 同组 | 分散 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | geometry_00 | synchronous | uav_01+uav_06 | 作业+终点保持 | 同组 | 结构性 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | geometry_01 | sequential | uav_01+uav_06 | 作业+终点保持 | 同组 | 分散 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | geometry_01 | synchronous | uav_01+uav_06 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | geometry_02 | sequential | uav_01+uav_06 | 作业+终点保持 | 同组 | 分散 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | geometry_02 | synchronous | uav_01+uav_06 | 作业+终点保持 | 同组 | 结构性 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | geometry_03 | sequential | uav_01+uav_06 | 作业+终点保持 | 同组 | 分散 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | geometry_03 | synchronous | uav_01+uav_06 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | geometry_04 | sequential | uav_01+uav_06 | 作业+终点保持 | 同组 | 分散 |
| family_s15_79c93b22d09e8a7a_ext_004_regular | geometry_04 | synchronous | uav_01+uav_06 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | geometry_00 | sequential | uav_03+uav_05 | 终点保持+作业 | 同组 | 分散 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | geometry_00 | synchronous | uav_03+uav_05 | 作业+终点保持 | 同组 | 结构性 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | geometry_01 | sequential | uav_08+uav_09 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | geometry_01 | synchronous | uav_08+uav_09 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | geometry_02 | sequential | uav_01+uav_03 | 作业+终点保持 | 同组 | 结构性 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | geometry_02 | synchronous | uav_01+uav_03 | 作业+终点保持 | 同组 | 结构性 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | geometry_03 | sequential | uav_03+uav_05 | 终点保持+作业 | 同组 | 分散 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | geometry_03 | synchronous | uav_03+uav_05 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | geometry_04 | sequential | uav_01+uav_09 | 终点保持+作业 | 同组 | 分散 |
| family_s15_aa4c66be8e85d64d_ext_002_regular | geometry_04 | synchronous | uav_01+uav_09 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_1b876e6b8b6f70c6_ext_007_regular | geometry_00 | sequential | uav_01+uav_06 | 作业+终点保持 | 同组 | 分散 |
| family_s15_1b876e6b8b6f70c6_ext_007_regular | geometry_00 | synchronous | uav_01+uav_06 | 作业+终点保持 | 同组 | 结构性 |
| family_s15_38bedc9d791d547b_ext_007_regular | geometry_00 | sequential | uav_01+uav_02 | 终点保持+作业 | 同组 | 分散 |
| family_s15_38bedc9d791d547b_ext_007_regular | geometry_00 | synchronous | uav_01+uav_02 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_38bedc9d791d547b_ext_007_regular | geometry_01 | sequential | uav_03+uav_06 | 作业+终点保持 | 同组 | 分散 |
| family_s15_38bedc9d791d547b_ext_007_regular | geometry_01 | synchronous | uav_03+uav_06 | 作业+终点保持 | 同组 | 结构性 |
| family_s15_38bedc9d791d547b_ext_007_regular | geometry_02 | sequential | uav_05+uav_06 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_38bedc9d791d547b_ext_007_regular | geometry_02 | synchronous | uav_05+uav_06 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_c713f51898e81011_ext_002_regular | geometry_00 | sequential | uav_05+uav_08 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_c713f51898e81011_ext_002_regular | geometry_00 | synchronous | uav_05+uav_08 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_c713f51898e81011_ext_002_regular | geometry_01 | sequential | uav_08+uav_10 | 作业+终点保持 | 同组 | 分散 |
| family_s15_c713f51898e81011_ext_002_regular | geometry_01 | synchronous | uav_08+uav_10 | 作业+终点保持 | 同组 | 结构性 |
| family_s15_c713f51898e81011_ext_002_regular | geometry_02 | sequential | uav_04+uav_09 | 作业+终点保持 | 同组 | 分散 |
| family_s15_c713f51898e81011_ext_002_regular | geometry_02 | synchronous | uav_04+uav_09 | 作业+终点保持 | 同组 | 结构性 |
| family_s15_c713f51898e81011_ext_002_regular | geometry_03 | sequential | uav_05+uav_08 | 终点保持+作业 | 同组 | 结构性 |
| family_s15_c713f51898e81011_ext_002_regular | geometry_03 | synchronous | uav_05+uav_08 | 终点保持+作业 | 同组 | 结构性 |

**3 个未跑完的骨架均为 monitoring。**
