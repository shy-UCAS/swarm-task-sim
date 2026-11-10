# V8-22 监视共用进场重生成执行报告

本轮结论：第 0–4 步验收条件全部满足，可按指令快进合并。

运行源码提交：`448d20440c49da267f24fb39fbb974563f6ab0b3`；父链 `412125f → e2f6ee1`。执行方未修改生成器、其余五意图、冻结判据或配置。

外部运行根：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-10_V8-22_monitoring_entry\run`。后台资源监控沿用 V8-20 脚本，原始证据留在本轮 `run/system_monitor/`。
资源监控共 3427 条采样，坏行 0，采样错误 0；最低可用内存 19.836 GiB。
原始监控正常停止，摘要见 [资源证据](evidence/resources.json)，原始样本保留在本轮 handoff。


**第 0 步：双版本完整测试与旧数据诊断。**

两边均以 `pytest -p no:cacheprovider tests/v08` 运行，基线为 e2f6ee1，审查版为 448d204。
基线：{'passed': 356, 'skipped': 28, 'failed': 3, 'error': 5}；审查版：{'passed': 359, 'skipped': 28, 'failed': 3, 'error': 5}。
已有测试结果差异为 0；新增 V8-22 的 3 项解析测试均通过。失败、错误与跳过分别保留，不计为通过。

| 两边共同的失败/错误测试 | 状态 | 原因 |
|---|---|---|
| `tests.v08.V8-12.test_preset_local_devset.TestRegisteredDevset::test_registered_files_hash_and_read_only` | failed | AssertionError: unexpectedly None : 本地测试前提：显式数据根；缺数据不能skip后声称通过 |
| `tests.v08.V8-12.test_preset_numpy_checkpoint.TestCheckpoint::test_each_diagnostic_threshold` | failed | AssertionError: 'frechet' not found in () : 上层D.4：同条件中位数19<场景间距20 |
| `tests.v08.V8-13.test_preset_local_e2e.LocalEndToEndPreset::test_every_retained_contract_with_frozen_verifiers` | error | failed on setup with "KeyError: 'V8_13_RUN_OUT'" |
| `tests.v08.V8-13.test_preset_local_e2e.LocalEndToEndPreset::test_keys_and_attempt_budget` | error | failed on setup with "KeyError: 'V8_13_RUN_OUT'" |
| `tests.v08.V8-13.test_preset_local_e2e.LocalEndToEndPreset::test_quick_coverage_or_full_draws` | error | failed on setup with "KeyError: 'V8_13_RUN_OUT'" |
| `tests.v08.V8-13.test_preset_local_reproduction.ReproductionPreset::test_five_bytewise_reproductions` | failed | KeyError: 'V8_13_RUN_OUT' |
| `tests.v08.V8-14.test_preset_local_artifacts.LocalArtifactsPreset::test_completed_keys_and_event_counts` | error | failed on setup with "KeyError: 'V8_14_RUN_OUT'" |
| `tests.v08.V8-14.test_preset_local_artifacts.LocalArtifactsPreset::test_retained_skeleton_geometry_and_actual_maps` | error | failed on setup with "KeyError: 'V8_14_RUN_OUT'" |

共同跳过项及新增测试的完整名单见 [测试证据](evidence/tests.json)。本轮保留原测试，没有修改或排除测试。

**第 1 步：五意图字节门禁。**

| 意图 | 一致合同 | 比较文件 | 不同文件 | 墙钟秒 |
|---|---:|---:|---:|---:|
| transit | 20/20 | 575 | 0 | 58.753 |
| intrusion | 20/20 | 575 | 0 | 47.434 |
| feint | 20/20 | 575 | 0 | 102.675 |
| close_observation | 20/20 | 575 | 0 | 106.984 |
| area_search | 20/20 | 575 | 0 | 96.687 |

合计 100/100；文件 2875；排除清单 `[]`。使用固定键及 `v08.runner.joint_monitoring.compare_dirs`。完整清单见 [门禁证据](evidence/gates.json)。

**第 2–3 步：监视快批、全量与多样性。**

| 批次 | 成功/总数 | 保留 P0 违规 | start_route 失败尝试 | measured_monitoring_entries 失败尝试 | 队形退让 |
|---|---:|---:|---:|---:|---:|
| 快批（原串行入口） | 20/20 | 0 | 0 | 0 | 0 |
| 全量（24 进程） | 198/200 | 0 | 2 | 0 | 0 |
| 多样性（同次全量派发） | 100/100 | 0 | 3 | 0 | 0 |

`--stage full` 原入口一次派发 200 个主批和 100 个多样性合同，输出分别为 `run/full` 与 `run/full/diversity`；未单独调用其不支持的 diversity 分支。多样性没有独立墙钟，不将同一次运行拆成两次计时。

quick 实测运行器墙钟：1400.461 秒；请求进程数 1；退出码 0。

full_and_diversity 实测运行器墙钟：2767.145 秒；请求进程数 24；退出码 0。

rerun 实测运行器墙钟：209.709 秒；请求进程数 1；退出码 0。

快批逐项止损：`{"retained_p0_zero": true, "complete": true, "successes_ge_17": true, "measured_entry_failed_attempts_le_2": true, "start_route_failed_attempts_le_10": true}`。

全量逐项止损：`{"retained_p0_zero": true, "complete": true, "successes_ge_185": true, "group_gap_le_10pp": true, "diversity_successes_ge_90": true, "diversity_retained_p0_zero": true, "diversity_complete": true}`。

| 全量人数档 | 成功/总数 | 成功率 | 比总体低的百分点 |
|---|---:|---:|---:|
| 1-4 | 110/110 | 100.00% | -1.00 |
| 5-8 | 55/56 | 98.21% | 0.79 |
| 9-12 | 33/34 | 97.06% | 1.94 |

作业段合并 Fréchet/该族横向间距中位数：优化后 75.919236（旧值 75.694970）；优化前 75.919375。

队形退让按成功合同的 `formation.start != formation.realized` 计数；loose 倾向的映射单列在原记录中，不算退让。

快批失败尝试按阶段：`{"optimize_monitoring": 4, "skeleton": 4}`；骨架子阶段（仅骨架失败）：`{"boundary_crossing": 1, "egress": 1, "ingress": 2}`。
快批失败尝试按原始合同原因：`{"optimize_residual": 4, "成员 uav_01 边界穿越不合规：graze_or_touch_band（设施 facility_02）": 1, "没有可用的入圈直线与连接": 2, "没有可用的出圈直线与终点": 1}`；最终失败合同原因：`{}`。

全量失败尝试按阶段：`{"optimize": 3, "optimize_monitoring": 55, "skeleton": 120}`；骨架子阶段（仅骨架失败）：`{"boundary_crossing": 9, "egress": 18, "ingress": 75, "start_route": 2, "turns": 16}`。
全量失败尝试按原始合同原因：`{"optimize_residual": 58, "turn_joint_set_empty：收拢—掉头—接回—展开整体可行集合为空": 16, "成员 uav_01 边界穿越不合规：graze_or_touch_band（设施 facility_02）": 3, "成员 uav_02 边界穿越不合规：graze_or_touch_band（设施 facility_01）": 2, "成员 uav_03 没有可用的起点路由": 1, "成员 uav_06 没有可用的起点路由": 1, "成员 uav_06 边界穿越不合规：graze_or_touch_band（设施 facility_02）": 2, "成员 uav_09 边界穿越不合规：graze_or_touch_band（设施 facility_01）": 1, "成员 uav_11 边界穿越不合规：graze_or_touch_band（设施 facility_01）": 1, "没有可用的入圈直线与连接": 75, "没有可用的出圈直线与终点": 18}`；最终失败合同原因：`{"20 次随机构造用完预算": 2}`。

多样性失败尝试按阶段：`{"optimize_monitoring": 17, "skeleton": 8}`；骨架子阶段（仅骨架失败）：`{"ingress": 3, "reference/speed": 2, "start_route": 3}`。
多样性失败尝试按原始合同原因：`{"optimize_residual": 17, "参考曲线不满足引导接口：第 10737 条弦与前一条方向差 3.1168691485099185 rad 超过 0.2 rad": 1, "参考曲线不满足引导接口：第 35020 条弦与前一条方向差 3.0985828767791013 rad 超过 0.2 rad": 1, "成员 uav_01 没有可用的起点路由": 1, "成员 uav_05 没有可用的起点路由": 1, "成员 uav_08 没有可用的起点路由": 1, "没有可用的入圈直线与连接": 3}`；最终失败合同原因：`{}`。

失败原因取自原始合同 `result.json`，精简 `records.json` 未保存原因字段。优化判据明细按记录条数另列于 [失败原因证据](evidence/failure_reasons.json)，一个失败尝试可对应多名成员的多条明细。

保存后冻结重核使用两个单线程进程，墙钟 994.226 秒，与全量运行器的部分汇总时间重叠；全部输入文件内容哈希在核验前后及最终检查点再次核对一致。

合同 JSON 中计时、缓存命中、PID、主机路径与 traceback 的扫描无命中，见 [载荷审计](evidence/payload_audit.json)。

保存后逐个重读成功合同的全部成员数组，调用冻结 `verify_segments`、`check_validity`，检查 10 Hz 时间线、保存结果一致性及每成员实测预警进入一次。完整逐项结果见 `evidence/quick.json` 和 `evidence/full.json`。

**三方进场诊断。**

| 数据 | 成功合同数 | 进入次数异常合同/成员 | 集合前入圈合同 | 首次入圈跨度 \(P_{50}/P_{90}\)，秒 | 释放至首次入圈 \(P_{50}/P_{90}\)，秒 | 首次入圈时距编组中心均距 \(P_{50}/P_{90}\)，米 |
|---|---:|---:|---:|---:|---:|---:|
| 旧监视 | 198 | 83/303 | 86 | 15.20/507.84 | 384.90/857.51 | 37.45/723.22 |
| 过境参照 | 200 | 0/0 | 0 | 7.85/33.07 | 638.10/1130.73 | 23.04/49.79 |
| 新监视全量 | 198 | 0/0 | 9 | 6.25/25.33 | 661.65/1137.88 | 22.77/49.47 |

诊断完全沿用随指令提供的只读脚本。仅统计成功且保存骨架的合同；距编组中心指标只统计同帧至少两成员可见的合同，样本数见 [诊断证据](evidence/entry_diagnostics.json)。

原脚本对新全量给出的“集合前入圈”标记为 9 个合同、21 名成员，原值完整保留。
只读影响定位确认：这 21 名成员的全轨迹集合中心最近帧全部落在撤离阶段；首次入圈均晚于保存的集合站点时刻，最小间隔 18.176822 秒。
入圈前实测轨迹距各自集合槽位的最小距离，21 人中的最大值为 0.428031 米。原脚本使用的是全轨迹距编组中心最近帧，因撤离时再次接近中心产生标记，不能直接等同于进场早于集合。
该诊断脚本和原始输出均未修改；逐成员时刻、相位与槽位证据见 [标记核对](evidence/collection_marker_audit.json)。规定的预警进入次数 P0 仍按每成员严格为 1 判定。

**第 4 步：单进程复跑。**

预先登记的 5 个业务键全部逐文件、逐字节一致，排除清单 `[]`。

源批次实际为 24 进程、复跑实际为 1 进程；原 reproduction.json 的 workers_source 字段固定写 8，保留该历史元数据，实际进程数以命令、源批 summary 与 watchdog 为准。

另利用本轮已生成的单进程快批与 24 进程全量同键作只读对照：20/20 合同、575 个文件逐字节一致，排除 `[]`。该对照不替代上述预选 5 键正式复跑。

**新输出目录。**

- 监视全量：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-10_V8-22_monitoring_entry\run\full`
- 多样性：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-10_V8-22_monitoring_entry\run\full\diversity`
- 监视快批：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-10_V8-22_monitoring_entry\run\quick`
- 单进程复跑：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-10_V8-22_monitoring_entry\run\rerun`

四份 V8-17..20/owner_rerun.json 的内容哈希保持不变，保留为未跟踪文件，不加入本次提交。旧全量、其余五意图输出、冻结工作树和 SwarmData 均作为只读输入。

全部合并条件逐项列于 [acceptance.json](acceptance.json)。提交、审查分支远端核对及条件合并后的 dev/v0.8 SHA 另写本轮外部推送回执，避免自引用提交号。
