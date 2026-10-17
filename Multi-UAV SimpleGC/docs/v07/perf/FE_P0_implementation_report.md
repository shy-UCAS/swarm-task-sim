# P0 性能优化实施报告

**最终结论：PASS。** G0、G3、G2、G4 通过；G1 经预检按规则跳过。规划总体中位耗时改善 20.90%，监视单机改善 41.30%，全部指定输出对照通过。

## 版本与本机环境

- 基线 SHA：`09279c2501002a670e77ed4db7b9f9ab0cb71c73`；只读 base：`Simulation-v07scene/Multi-UAV SimpleGC`。
- perf 分支：`perf/v07-first-edition-p0`；工作树：`Simulation-perf`，与原工作树同级，数据路径自动落在同级 `SwarmData/v07_dataset`。
- 接受最终验证的源码 HEAD：`c1675cd62f0c5d110593f87ac3b372661eef4dde`。G4 交付提交只补充报告、证据和对照脚本的文件完整性防护，生产源码指纹与该 HEAD 一致。
- 交付 HEAD 是本报告所属的 `FE-P0-G4` 提交。推送后完整本地/远端 SHA 和最终差异清单记录在 [`final_delivery.json`](F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/perf_fe_p0_20261017_g4_bench/final_delivery.json)，避免在提交内容内自引用提交哈希。
- PowerShell 7.6.5；项目 `.conda-env=llm`；Python 3.12.3、NumPy 2.5.3、Shapely 2.0.7；AMD Ryzen 9 9950X3D，16 核/32 逻辑处理器。未安装新依赖。
- 本机适配沿用本会话已批准的方式：不重复 fetch，复用本地精确基线；`31dfcec..09279c2` 在 task_v07、swarm_sim、configs 的差异为空。P1 分支未合并，基线和 P1 工作区均干净。

## 门禁与等价性

| 门禁 | 状态 | 证据 |
|---|---|---|
| G0 | PASS | 12 组/100 项基线测试；6 单机+1 同步联合 R0 与存档完全一致；两次独立进程规划一致 |
| G3 | PASS | E1–E5；4 项快照测试；31 单机+6 联合重放共 37 项一致；100 项回归无新失败 |
| G1 | SKIPPED | max(saved_within)=1.2246%，saved_family=9.0138%，未达到 15% |
| G2 | PASS | 80000 随机线段+20000 随机点；边界用例；两种真实图结构；3 个规划样本完全一致 |
| G4 | PASS | 100 项既有+7 项新增测试通过；30 次正式运行；9 对规划、12 次重放全部一致；两项性能门槛通过 |

G1 未实现，因此没有新增 visibility_cache.py 或缓存测试；FreeSpace 未改。实际新增两个测试模块，共 7 项，均在 G4 重跑通过。G3 监视同步长仿真也已完成，未使用超时降级。
规划比较只递归删除 wall_s、planning_wall_s 或以 _wall_s 结尾的键；保留键名清单、严格类型/数值/列表顺序比较。实际删除键清单见 parity JSON。没有改判据、随机消费顺序、预算、积分或导出频率。

## G3 静态前提

- E1 PASS：command 位于快照前；快照到回滚只调用 observe_segment；observe_sample 位于事务后。 定位：`task_v07/execution.py:83-107`, `task_v07/dwell.py:41-61`。
- E2 PASS：witnesses.append(event) 与 events.extend(emitted)，未修改已有元素。 定位：`swarm_sim/fast_dynamics/route_tracker.py:337-434`。
- E3 PASS：全仓 Python 的 .witnesses/.events 写入已核对。执行相关列表只有构造、deepcopy 赋值及追加；replay_viewer 的排序、诊断 RNG 的 events、测试假对象属于不同类型。已有测试读取或 deepcopy 切片，没有改 tracker 的旧元素。 定位：`G3_event_writes_search.txt`。
- E4 PASS：同一新 event 字典加入 witnesses 与 emitted 后进入 events；deepcopy 使用共享 memo。新快照保留元素身份，S1 检验 is 共享。 定位：`swarm_sim/fast_dynamics/route_tracker.py:194-201`, `swarm_sim/fast_dynamics/route_tracker.py:350-355`, `swarm_sim/fast_dynamics/route_tracker.py:433`。
- E5 PASS：tracker 构造及使用局限于 execute；dwell_trackers 只保存整数。循环局部 t 在回滚后读取前即重新绑定；events 不持有 tracker。Dwell 的内层引用封装在 wrapper 内，递归恢复。新增 snapshots 是私有事务引用，不导出。 定位：`task_v07/execution.py:40-49`, `task_v07/execution.py:67-101`。

定位行号为基线版本；全仓搜索保存在 G3_event_writes_search.txt。S1 用真实积分步检查属性/列表身份、列表内容、内层 tracker、stage/since_us 与 witness 共享；S2 普通多拐点、驻留、多机夹具分别覆盖 6、6、2 次回滚，新旧步数与指定字段完全一致。

## G1 预检

| 组/样本 | 规划秒数 | saved_within |
|---|---:|---:|
| family_s15_1c267d4d7000043d_ext_005_regular | 17.524 | 0.0000% |
| family_s15_1c267d4d7000043d_ext_006_regular | 21.156 | 0.0000% |
| family_s15_1c267d4d7000043d_ext_009_regular | 14.769 | 1.2246% |
| family_s15_1b876e6b8b6f70c6_ext_006_regular | 52.461 | 0.0000% |

A 组同进程顺序运行 005、006、009；B 组在另一进程运行 1b876…006。同一键对应图的 vertices/adjacency 一致。A 组跨骨架可省比例 9.0138%，因此按规则跳过缓存。真实有效 view 与原场景保存在 FE_P0_real_view.json、FE_P0_real_scene.json。

## G2 几何验证

圆、Polygon、BufferedPolygon 的正/负/零 buffer、重叠障碍物均覆盖；margin 为 0 和 35。包括解析圆相切和多边形扩展边界两侧的小偏移。测试中的参考 free/_visible_uncached 与基线逐字一致，仅更改函数名；已核对字面内容。
四组场景各用固定种子 20261016 比较 20000 条线段和 5000 个点，无反例。真实有效 view（margin=0）和原规划 scene（margin=35）的 vertices/adjacency 完全相同。世界和端点检查顺序、障碍物顺序、原精确阈值及 path 均保持不变。

## G4 性能

测量开始前、结束后均未发现其他 v07 任务。每个任务及每次重复使用全新子进程，第二轮反转 base/perf 顺序；没有跨任务预热。仅任务本体计时，不含进程启动、导入和结果对照。下表单位为秒，括号为三次运行的最小–最大值。

| 项目 | base 中位数（范围） | perf 中位数（范围） | 加速比 | 耗时改善 |
|---|---:|---:|---:|---:|
| 过境规划（1c267…005） | 25.407（23.927–27.039） | 19.628（19.018–21.155） | 1.294 | 22.75% |
| 突防规划（1c267…009） | 21.354（20.931–23.428） | 20.097（18.957–23.094） | 1.063 | 5.89% |
| 多向区域搜索规划（1b876…006） | 84.940（78.516–88.069） | 66.249（60.248–66.660） | 1.282 | 22.00% |
| 监视单机（排序首成员 uav_01） | 48.965（44.900–52.301） | 28.743（23.909–29.685） | 1.704 | 41.30% |
| 过境 synchronous 联合执行 | 54.480（46.718–66.939） | 46.561（35.012–52.090） | 1.170 | 14.54% |

规划门槛口径：先取每个骨架三次运行的中位数，再对三个骨架取中位数，计算 \(1-\operatorname{median}(T_{perf})/\operatorname{median}(T_{base})\)。结果为 **20.90% ≥ 15%**；三个骨架中位耗时之和的改善另报为 **19.53%**。监视单机为 **41.30% ≥ 20%**。
突防规划单项仅改善 5.89%；不能把总体改善解释为每个样本都达到 15%。联合执行的三次耗时波动较大，完整范围已列出，不以最佳单次代表收益。

### 诊断计数与内存

| perf 项目 | G2 exact_calls / skipped | G3 steps / rollbacks | base / perf 峰值内存最大值（MiB） |
|---|---:|---:|---:|
| 过境规划（1c267…005） | 141075 / 113510 | 0 / 0 | 69.4 / 69.3 |
| 突防规划（1c267…009） | 162351 / 80580 | 0 / 0 | 72.3 / 72.7 |
| 多向区域搜索规划（1b876…006） | 527923 / 645347 | 0 / 0 | 148.4 / 148.3 |
| 监视单机（排序首成员 uav_01） | 0 / 0 | 77166 / 215 | 53.4 / 53.1 |
| 过境 synchronous 联合执行 | 0 / 0 | 48470 / 134 | 54.6 / 54.5 |

G2 计数只包括障碍物查询，不包括世界检查。base 没有这些诊断字段，worker 中的零值/空字典表示未计量，不能解释为没有工作。G1 未实施，hits/misses/evictions/build_wall_s 不适用。内存来自可用的 psutil/Windows peak_wset，覆盖进程启动、导入、任务与结果保存/对照的全进程高水位，不是纯任务内存。

## 源码范围、异常与后续

- 仅改两处生产文件：execution.py 的事务快照/恢复，visibility.py 的包围盒预筛选。其他新增文件为指定脚本、测试和 docs/v07/perf 证据。源码旧/新 SHA256 及对应验证见 FE_P0_source_manifest.json。
- 冻结配置 SHA256 仍为 `94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193`。历史测试、历史证据、M1/M2、dwell.py、swarm_sim、P1 三个文件及配置均未修改。C4 允许的源码指纹变化已逐项登记，没有借此豁免实际测试失败。
- 新增诊断字段时曾出现基准脚本缩进错误，5 个 G3 作业未保存 parity；这些记录原样保留，修正工具后在全新 replay_repair 目录重跑全部通过。它们未作为成功证据计入。另为规划对照补充了必需输出缺失时失败的检查，结束后重新核对全部 9 对正式规划输出。两项均为测试工具问题，未改算法来迎合结果。
- 所有门禁均在规定时间内完成，近似门禁耗时另见 FE_P0_gate_times.json。没有触发算法反例、容差放宽或范围外修改；未解决问题：无。本机三轮耗时存在波动，性能结论限于本报告列出的样本与环境。
- 推送只限 perf/v07-first-edition-p0，不强推、不合并、不删除 base、不启动 32 次抽签重测或批量生产。P1 合并与后续完整重测留待人工审查。

## 证据入口

- FE_P0_baseline.json：G0 基线与 R0/确定性证据。
- FE_P0_parity_results.json：G0–G4 精确等价检查及回归记录。
- FE_P0_benchmark.json：所有 30 次测量、统计口径、诊断计数与内存。
- FE_P0_source_manifest.json：源码指纹和 C4 等价证据映射。
- 外部原始输出根：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset`；本轮目录均以 `perf_fe_p0_20261017_` 开头，正式基准为 `perf_fe_p0_20261017_g4_bench`。

## 提交差异

以下为最终暂存内容相对基线的 diff --stat，提交后对应 `git diff --stat 09279c2..HEAD`。

```text
 Multi-UAV SimpleGC/docs/v07/perf/FE_P0_G1_precheck.json                        |  840 +++++++++++
 Multi-UAV SimpleGC/docs/v07/perf/FE_P0_baseline.json                           |  638 ++++++++
 Multi-UAV SimpleGC/docs/v07/perf/FE_P0_benchmark.json                          | 2363 ++++++++++++++++++++++++++++++
 Multi-UAV SimpleGC/docs/v07/perf/FE_P0_environment.json                        |   17 +
 Multi-UAV SimpleGC/docs/v07/perf/FE_P0_gate_times.json                         |   18 +
 Multi-UAV SimpleGC/docs/v07/perf/FE_P0_implementation_report.md                |  164 +++
 Multi-UAV SimpleGC/docs/v07/perf/FE_P0_parity_results.json                     | 4069 ++++++++++++++++++++++++++++++++++++++++++++++++++++
 Multi-UAV SimpleGC/docs/v07/perf/FE_P0_real_scene.json                         |  305 ++++
 Multi-UAV SimpleGC/docs/v07/perf/FE_P0_real_view.json                          |  121 ++
 Multi-UAV SimpleGC/docs/v07/perf/FE_P0_source_manifest.json                    |   38 +
 Multi-UAV SimpleGC/docs/v07/perf/G2_broadphase_tests.txt                       |   14 +
 Multi-UAV SimpleGC/docs/v07/perf/G2_geometry_parity.json                       |   63 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_event_writes_search.txt                    |   68 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_regression.json                            |   74 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_snapshot_tests.txt                         |   10 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_static_preconditions.json                  |   39 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_test_fast_dynamics_core.txt                |   20 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_test_fast_dynamics_execution.txt           |   21 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_test_fast_dynamics_execution_m2.txt        |   19 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_test_fast_dynamics_m3_postfreeze.txt       |   13 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_test_fast_dynamics_tracking.txt            |   17 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_test_v07_m1_criteria.txt                   |   27 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_test_v07_m2_timing_rehearsal.txt           |   21 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_test_v07_m3_fix_connections.txt            |   10 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_test_v07_m3_fix_entry.txt                  |    9 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_test_v07_m3_fix_patrol_entry.txt           |    6 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_test_v07_m3_integration.txt                |    9 +
 Multi-UAV SimpleGC/docs/v07/perf/G3_test_v07_m3b_geometry.txt                  |   14 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_machine_end_check.json                     |    5 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_machine_idle_check.json                    |    5 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_regression.json                            |   86 ++
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_fast_dynamics_core.txt                |   20 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_fast_dynamics_execution.txt           |   21 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_fast_dynamics_execution_m2.txt        |   19 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_fast_dynamics_m3_postfreeze.txt       |   13 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_fast_dynamics_tracking.txt            |   17 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_v07_m1_criteria.txt                   |   27 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_v07_m2_timing_rehearsal.txt           |   21 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_v07_m3_fix_connections.txt            |   10 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_v07_m3_fix_entry.txt                  |    9 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_v07_m3_fix_patrol_entry.txt           |    6 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_v07_m3_integration.txt                |    9 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_v07_m3b_geometry.txt                  |   14 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_v07_perf_tracker_snapshot.txt         |   10 +
 Multi-UAV SimpleGC/docs/v07/perf/G4_test_v07_perf_visibility_broadphase.txt    |   14 +
 Multi-UAV SimpleGC/docs/v07/perf/baseline_test_fast_dynamics_core.txt          |   20 +
 Multi-UAV SimpleGC/docs/v07/perf/baseline_test_fast_dynamics_execution.txt     |   21 +
 Multi-UAV SimpleGC/docs/v07/perf/baseline_test_fast_dynamics_execution_m2.txt  |   19 +
 Multi-UAV SimpleGC/docs/v07/perf/baseline_test_fast_dynamics_m3_postfreeze.txt |   13 +
 Multi-UAV SimpleGC/docs/v07/perf/baseline_test_fast_dynamics_tracking.txt      |   17 +
 Multi-UAV SimpleGC/docs/v07/perf/baseline_test_v07_m1_criteria.txt             |   27 +
 Multi-UAV SimpleGC/docs/v07/perf/baseline_test_v07_m2_timing_rehearsal.txt     |   21 +
 Multi-UAV SimpleGC/docs/v07/perf/baseline_test_v07_m3_fix_connections.txt      |   10 +
 Multi-UAV SimpleGC/docs/v07/perf/baseline_test_v07_m3_fix_entry.txt            |    9 +
 Multi-UAV SimpleGC/docs/v07/perf/baseline_test_v07_m3_fix_patrol_entry.txt     |    6 +
 Multi-UAV SimpleGC/docs/v07/perf/baseline_test_v07_m3_integration.txt          |    9 +
 Multi-UAV SimpleGC/docs/v07/perf/baseline_test_v07_m3b_geometry.txt            |   14 +
 Multi-UAV SimpleGC/scripts/bench_v07_fe_p0.py                                  |  408 ++++++
 Multi-UAV SimpleGC/task_v07/execution.py                                       |   40 +-
 Multi-UAV SimpleGC/task_v07/visibility.py                                      |   50 +-
 Multi-UAV SimpleGC/tests/test_v07_perf_tracker_snapshot.py                     |  100 ++
 Multi-UAV SimpleGC/tests/test_v07_perf_visibility_broadphase.py                |  111 ++
 62 files changed, 10222 insertions(+), 6 deletions(-)
```
