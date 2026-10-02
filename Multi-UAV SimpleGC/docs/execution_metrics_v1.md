# 执行诊断接口与 A4 离线对照

状态：`IMPLEMENTED_AND_TESTED`。`swarm_sim.execution_metrics.compute_execution_metrics` 是纯函数，产物版本 `execution_artifacts_v1`；不改变控制指令、质量门槛和观测特征。v3 新窗口和连续运行接线仍等待 WP-E E3。

## 输入与输出

```python
compute_execution_metrics(scene, traces, windows, events=None,
                          metadata=None, time_epoch=None, nominal_arrivals=None)
```

`traces` 为每机公共导出网格上的 `(t, [E,N,U,vE,vN,vU])` 列表，无效记录为 `None`。不能传分析私有的结束插值支撑点。时间是相对主机秒；传 `metadata` 与 `time_epoch` 后，事件时刻按二者转换至相同时间基。`windows` 接受窗口列表或包含 `windows` 的对象。所有输入保持不变。

- `thresholds["0.3"]`、`thresholds["0.5"]`：每机停靠次数、原始区间、位置分类、静止时间比例、全机同步时间比例和共同停靠事件比例。
- `intermediate_waypoints`：非终点航点的停靠率、缺证据数，以及 2 m 内最低水平速度分布、逐点记录和按扫描线长度分组的分布。扫描线长度来自完整扫描线端点对，换线连接段的长度不会用作扫描线长度。
- `arrival_lag_s`：终点到达事件减去轨迹 `arrival_s`；没有匹配证据时 `available=false`，不把旧 `task_target_verified` 改名冒充到达。
- `barrier_wait_s`：有新窗口时采用 `end_s-arrival_s`；旧模式只报告标明来源的 `phase_finished` 事件代理值。
- `nominal_timing_deviation_s`：外部提供 `actual_s/nominal_s` 配对时报告偏差分布和 `max_abs_s`；当前旧模式没有定时参考，保持不可用。

全部指标使用 FCU 水平速度。SIM 日志没有直接速度字段，不能在此接口中默默当成同一通道。现有 WP-S 位置差分交叉核对保留其单独版本和局限。

## 停靠口径与未知值

停靠定义沿用 A4：速度严格小于阈值且首末采样时间差至少 0.2 s；超过 1.5 个采样周期的间隙和无效值会断开区间。时间重复或回退不在此模块修复。v3 去重由独立版本化观测处理器完成。

为精确复核 A4，次数在整个导出任务观测网格上计算；时间比例裁剪到所有有效语义窗口的最早开始与最晚结束。同步时间比例采用从窗口起点开始的采样网格，分母为 `round(duration / dt) + 1`，明确保留 A4 的端点口径。位置分类互斥：语义阶段终点优先，其次中间航点，然后其他位置。这解决旧模式 approach 终点与 observe 首点重合时的重复归类。

没有有效语义任务窗口、整架飞机缺少速度或时间轴失效时，该机停靠次数为 `null`。部分证据只保留观察到的次数，并标记 `stop_count_is_lower_bound=true`；静止和同步比例只有完整证据时才能给出数值。空证据不能当作零停靠。

共同停靠事件使用真正的全机区间交集。原 A4 用各机区间包络估计共同交集，在三机多区间桥接的特殊构造中会误报；旧包络值保留为 `audit_envelope_common_event_count`，新主指标为 `common_overlap_event_count`。本次历史数据两者未出现差异。

## 实际核验

运行 `scripts/verify_execution_metrics.py --output <tmp_v04 下不存在的新目录>`。脚本复制旧数据集 episode 的输入后复算，只读原文件，不导入或执行会写回审查目录的 A4 原脚本。

最终证据：`tmp_v04/wp_g/execution_metrics_final/execution_metrics_regression.json`。

- 处理 15/15 个 episode，共 60 架飞机实例。
- 原审查产物只有 14 个可对照 episode、57 架飞机实例。对这 14/14 个 episode，0.3 和 0.5 m/s 两阈值下每机停靠次数全部相同；同步时间比例最大绝对差为 **0.0**，共同事件数也全部相同。
- 失败运行 `20260930T153556Z_bf2d3529` 的 3 架飞机没有有效语义窗口，原 A4 因此跳过；新结果明确标记未知，既不补造参考值，也不算作比较通过。
- 80 份原始输入和审查文件的 SHA256 在复算前后保持一致；未启动 SITL。
- 9 项合成轨迹测试通过，包含手算停靠数、静止和同步比例、精确交集、未知值、扫描线长度分组及事件时间换算。

首次输出 `execution_metrics/` 因原参考少一条而停止，中间结果 `execution_metrics_complete/` 也保留。正式里程碑引用 `execution_metrics_final/`，避免把旧的诊断尝试误认为最终结论。
