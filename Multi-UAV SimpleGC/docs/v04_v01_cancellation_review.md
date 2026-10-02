# V01 参数读回取消时间线复核

复核日期：2026-10-02（America/Los_Angeles）。本报告仅读取旧运行，不启动 SITL、不修改生产代码或参数、不修改原运行判定。

## 结论

uav_01 的 1105/1202 是读回工作线程收到统一取消时保存的消费进度，不是原始接收线程收到的总项数。直接证据为附件错误 `RuntimeError: uav_01: run cancelled` 且 `timed_out=false`。uav_02、uav_03 已完成 1202 项读回，随后各自的旧比较器因 `STAT_RESET` 差异拒绝，主线程触发统一清理。

因此可排除“本次因 uav_01 等满 30 s 仍未读完而超时失败”的解释。不能据此保证该机在不取消时一定完整读回，也不能证明链路永不丢包。

## 原始时间线

运行：`verification/v04_v1_20261001/runs/recon_shared_demo_3uav_20261001T182936Z_6bca981d`。统一时间零点为 `run_epoch_monotonic_s=59886.742596`，下表均为运行开始后的秒数；没有混用 FCU 时间、UTC 或事件写盘时间。

| 时间 / s | 对象 | 原始证据 |
|---:|---|---|
| 11.693259000 | uav_02 | PARAM_REQUEST_LIST send_before；firmware_parameters.json requests |
| 11.693753800 | uav_01 | PARAM_REQUEST_LIST send_before；firmware_parameters.json requests |
| 11.694309300 | uav_03 | PARAM_REQUEST_LIST send_before；firmware_parameters.json requests |
| 12.207680400 | uav_02 | last raw PARAM_VALUE；raw/uav_02.jsonl:2854 index=1201 |
| 12.220605400 | uav_03 | last raw PARAM_VALUE；raw/uav_03.jsonl:2854 index=1201 |
| 12.251340400 | uav_03 | parameter_readback_complete；events.jsonl; read complete, comparator not yet accepted |
| 12.252638100 | uav_02 | parameter_readback_complete；events.jsonl; read complete, comparator not yet accepted |
| 12.253669200 | uav_03 | readback worker finally finished；firmware_parameters.json finished_monotonic_s |
| 12.255271300 | uav_02 | readback worker finally finished；firmware_parameters.json finished_monotonic_s |
| 12.255879900 | swarm | run_failed: STAT_RESET；events.jsonl |
| 12.258688200 | uav_01 | readback worker finally finished；firmware_parameters.json finished_monotonic_s |
| 12.259647900 | uav_01 | last raw PARAM_VALUE；raw/uav_01.jsonl:2841 index=1162 |

原日志没有 `cancel.set()` 专用事件。由旧源码（与原 metadata 内 SHA256 完全一致）调用顺序，只能把该调用约束在 **12.255879900–12.258688200 s**，区间宽 2.808 ms：先记录 `run_failed`，然后在 `finally` 设置取消；uav_01 的 `client.check()` 观察取消并报错，其工作线程随后记录结束时间。不得把 `run_failed` 时刻冒充精确取消时刻。

## 1105 项快照与 1163 项原始接收

| 飞机 | 消费快照 | 原始唯一索引 | PARAM_REQUEST_LIST 到工作线程结束 / s | 最后 PARAM_VALUE / s |
|---|---:|---:|---:|---:|
| uav_01 | 1105/1202 | 1163 | 0.564934 | 12.259647900 |
| uav_02 | 1202/1202 | 1202 | 0.562012 | 12.207680400 |
| uav_03 | 1202/1202 | 1202 | 0.559360 | 12.220605400 |

uav_01 的消费快照为索引 0–1104；raw 实际保留索引 0–1162，共 1163 个唯一项。索引 1105–1162 的 58 项已由接收线程落入 raw，但没有进入终止时的消费快照；索引 1163–1201 的 39 项在保存的 raw 中缺失。最后一个包为 `RC16_MIN`，见 `raw/uav_01.jsonl:2841`。

该机在 `run_failed` 时刻之前 raw 已收到 1113 个唯一项，在读回工作线程结束前已收到 1141 个。最后 raw 接收比工作线程结束晚 0.960 ms，也晚于取消区间上界，符合“取消消费任务后，接收线程直到 client.close 才退出”的旧实现。

接收线程记录 PARAM_VALUE 后将其放入 inbox；读回线程每批读取前先执行 `client.check()`，每轮最多等待 50 ms。统一取消能使读回线程在处理下一批前退出，而接收线程独立继续工作。日志没有记录每批消费边界，不能把 1104 号包的接收时刻当作消费快照时刻。

三机的实际参数列表读回阶段均在约 0.56 s 时结束，远短于独立的 30 s 参数列表读回预算，未触发 5 s 的缺项重读。参数列表发送前约 10 s 是 `AUTOPILOT_VERSION` 查询等待；超时后采用已验证二进制版本字符串，再单独建立参数读回 deadline。这 10 s 不能算成 PARAM_VALUE 传输耗时。

## STAT_RESET 独立换算

按用户确认的定义，将原参数值作为自 2016-01-01 00:00:00 UTC 起的秒数直接换算，不调用新比较器。每次运行三机的该值相同，结果如下。

| 运行 | 原始值 | 换算 UTC | 元数据启动 UTC | 差值 / s | ±300 s |
|---|---:|---|---|---:|---|
| spike_v04_20261001T153235Z_5eddb7ae | 339262368 | 2026-10-01T15:32:48+00:00 | 2026-10-01T15:32:35.876403+00:00 | +12.123597 | 通过 |
| spike_v04_20261001T153806Z_42150c31 | 339262688 | 2026-10-01T15:38:08+00:00 | 2026-10-01T15:38:06.282036+00:00 | +1.717964 | 通过 |
| recon_shared_demo_3uav_20261001T182936Z_6bca981d | 339272992 | 2026-10-01T18:29:52+00:00 | 2026-10-01T18:29:36.418436+00:00 | +15.581564 | 通过 |

9 份参数快照中的 STAT_RESET 均满足本次 ±300 s 合理性范围；V01 的 uav_01 整体读回仍不完整，此处只确认该字段合理，不能使整份读回通过。三个换算值与实例启动时间相符。由于这些值经 PARAM_VALUE 的 float32 传输，当前位置的量化间距为 32 s，不能将 2–16 s 的差值解释成精确的初始化延迟。

## 保存与可复核性

诊断产物：`tmp_v04/wp_v_resume_20261002/cancellation_diagnosis.json`，包含原始行号、全部请求、边界时刻、各机快照/原始计数、9 项换算和哈希。复算脚本为 `tmp_v04/wp_v_resume_20261002/diagnose_cancellation.py`；输出使用拒绝覆盖规则。

对两次 WP-S 和失败 V01 的全部 118 个文件进行 SHA256 前后核对，均保持不变。旧控制/读回/接收源码保存于 `tmp_v04/wp_v_resume_20261002/cancellation_source_snapshot`，三份快照的 SHA256 与失败运行元数据中的源码指纹一致，后续生产修正不会改变本报告的因果依据。

**失败 V01 继续保持 failed，仍计入 V1 预算一次；本复核没有补齐数据、重新分析或改判该运行。**
