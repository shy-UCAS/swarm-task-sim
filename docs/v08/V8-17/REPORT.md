# V8-17 突入单段：执行报告

> 执行方：Claude Code（模型 Opus 5.5，`claude-opus-5-5`）。基线 `d9a317832d7dd166610d8d6e515cf80bec5ce903`（dev/v0.8），审查分支 `review/v08/V8-17-intrusion`。
> 依据：`_handoff\2026-11-06_V8-17_intrusion\V8-17_突入单段_执行指令_20261106.md`（以下称"指令"，SHA256 `a6411c34…0b81`）和《V8-17_GPT指令评价与裁定_20261106.md》（以下称"附录"）。两者冲突时以附录为准。
> 本报告逐部分如实填写"完成 / 失败 / 未执行"。证据等级分三档："代码已写"、"有记录"（执行方第一次运行）、"已复跑"。

## 0. 开工复述

### 0.1 范围（指令第 1 部分要求的开工复述）

- **只做第 0 编组的单段突入**：公共抽签与监视、过境同键，只把唯一 TaskSpec 的 intent 换成 `intrusion`。不做多段、圈内开始、多编组、分股、成员差异、终端横向收拢，也不改优化器。
- **代码基线固定为 d9a3178**：用显式 refspec 获取，不随远端最新提交漂移。
- **两轮字节门禁**：第 2 部分、第 4 部分各跑一次监视与过境 20 合同快批，分别与 `full_v14c`、`full_transit_r2` 同键逐字节比较。合同目录排除清单为 `[]`。
- **先求可行集合，再抽样**：精确终点集合 → 均匀取格 → 均匀取 σ → 按长度均匀取终点 → 在相容的 D 中均匀取一个。
- **进场禁止提前入圈**：路由约束为 intrusion base＋目标 warning 外 10 m，entry_planner 把目标 warning 外扩 10+Δ。完成的进场折线再做精确检查。
- **唯一 20 次预算**：由现有 run_attempts 管理；下游失败不退队形、不重抽格/σ/终点。
- **o34_d3 的排除只用于成功率与档差**：原始 200 行全部保留；只有成功率和档差用 199 作分母，其他统计各用各自的对象。
- 已授权的工作不再请负责人二次批准。

### 0.2 八个部分

| 部分 | 内容 | 验收 |
|---|---|---|
| 1 | 分支、输入登记、冻结快照、旧测试基线、预置测试散列 | 文件齐全，散列可核对；不宣称新测试已通过 |
| 2 | 穿越边界表 `crossing_boundaries`、intrusion 合同与三个分派；监视与过境第一轮字节门禁 | 两意图各 20/20 逐字节一致 |
| 3 | 精确最深点与终点区间、单车道缓存与格组合、σ 网格、终端纵向压缩、曲线范围与 LP、进场与按成员终点装配、圆形不可行证书 | 实现、解析测试、单格查询日志、证书；尚不宣称全链路验收 |
| 4 | 优化后语义检查 `check_intrusion`、名义预筛 `screen_intrusion_member`、实测三层进入次数、冻结核验接入、白名单序列化、测试；第二轮两意图字节门禁 | 预置测试结果，两意图各 20/20 逐字节一致 |
| 5 | 200 合同只骨架（24 进程），前置快速检查（含 45 组组合一致性门禁），止损检查点 | 成功率（199 分母）≥95%、档差 ≤10 个百分点、attempts 中位数 ≤1、形状审计失败 ≤5%、直线回退 ≤50% |
| 6 | 四键全链路 smoke 后，20 合同全链路快批（24 进程），止损检查点 | 成功 ≥16/20、post 失败中位数 ≤0、optimization_s 中位数 ≤60 s、保留 P0 违规 0 |
| 7 | 200＋100 全量、5 合同单进程复跑、三意图配对与诊断 | 成功率 ≥80%、档差 ≤20 个百分点、post 中位数 ≤0、作业段 Fréchet 合并中位数 ≥1；5/5 逐字节一致 |
| 8 | 报告、RUNNING、快照、提交、推送审查分支 | 远端 SHA 与本地一致 |

每部分单独提交。第 5、6、7 部分开始前先做快速检查；任何一项不达标就停在该检查点，提交、推送失败版本，然后汇报。

### 0.3 三条停止条件（P0，指令 0.4 / U F.1）

1. **监视或过境快批字节不一致**：两轮门禁中，各 20 个同键合同的全部文件（含失败合同、见证 JSON、全部 NPY）必须逐字节一致，排除清单 `[]`。
2. **保留结果违规**：只看保留尝试。实测间距、限制区、圈层任一违规，保存结果与冻结核验不一致，或任一保留成员实测的三层进入次数不为 1/1/1。被正确拒绝的失败尝试不算。
3. **单进程复跑不一致**：预登记的 5 键（o01_d0–o01_d4）单进程复跑，必须与 24 进程输出逐字节一致，失败键也不替换。

触发任一条：立即停下，保存证据，提交并推送当前版本，然后汇报，**不自行修复后重跑**。第 5–7 部分的成功率、耗时、多样性属于止损检查点，不升级为 P0。

### 0.4 附录三条裁定

1. **终点压缩发生在哪里（指令第 12 节第 7 项）：不加约束，只作诊断。** 上层要求中"压缩只发生在保护层内的减速段"属于表述失误，应理解为"压缩发生在终点附近的减速段"。它是推论，不是约束：不加时间耦合，不改优化器。
   - 量级：终点在保护层内 ≥10 m；按 1.8 m/s² 从 10 m/s 刹停约需 28 m，所以制动开始点最多可能在保护边界外约 18 m。
   - 报告"优化制动开始所在圈层"分布，以及制动开始点到保护边界的有符号距离分布。不设门槛，记为 P2。
2. **预置测试夹具不全时怎么办：**
   - 失败原因是夹具缺字段（AttributeError/KeyError，与被测逻辑无关）时，只在夹具里补最少的字段。不改断言、预期值或被测调用；补的值取自 d9a3178 源码默认值或真实场景，并注明来源；登记修改前后的 SHA256，在 REPORT 中贴出 diff 并逐行说明原因。
   - 失败原因是预期值本身时，按指令第 9 节处理：保存手算证据，暂停该项，其他独立项继续，交回审查。
   - 切线例：`endpoint_interval` 在 y=65 时必须返回单点区间 (0.0, 0.0)。若 `line_sublevel` 对切线返回空，由 `endpoint_interval` 自行处理，不改 `line_sublevel`。
3. **确认两处取值：**
   - σ 网格为 k/20，且 σ·b ≥ 6 m；o34_d3 的 b=15.91 m，σ_min=0.40。
   - 耗时只如实记录；不为赶时间跳过第 5.1 节的快速检查，也不跳过 45 组组合一致性门禁。

---

## 1. 第 1 部分：分支、输入、基线 —— 完成

- **分支：** `git fetch origin refs/heads/dev/v0.8:refs/remotes/origin/dev/v0.8` 后，`origin/dev/v0.8` 与 `d9a3178^{commit}` 均为 `d9a317832d7dd166610d8d6e515cf80bec5ce903`；从该提交新建 `review/v08/V8-17-intrusion`。之前不存在同名分支；开工时工作区无改动。
- **manifest：** [manifest.json](manifest.json)，由 [make_manifest.py](make_manifest.py) 生成。逐项核对结果：
  - 开发集 SHA256 = `223e0e0d…36e0`，与 V8-16 manifest 一致；40 族的每族输入散列一致；5 个配置的散列一致。
  - 基线 `full_v14c` 的 tree SHA 与 V8-16 登记一致（8551 文件，保留 198）。
  - 基线 `full_transit_r2` 有 8651 文件、200 合同、保留 200，tree SHA 已登记。
  - 快批 20 键与指令第 1 节第 6 条逐一相同，且不含 o34_d3；全量 200 键与两个基线的键集合相同。
  - 多样性 100 键、复跑 5 键（o01_d0–o01_d4）、smoke 4 键、边缘例 2 键均已登记。
- **环境：** Python 3.12.3、NumPy 2.5.3、SciPy 1.14.1、shapely 2.0.7、Windows-11-10.0.26200；BLAS 线程全部为 1，见 [part1/env.txt](part1/env.txt)。SciPy 对 NumPy 版本的 UserWarning 与 V8-16 相同，属既有环境现象。
- **快照：** [snapshot.py](snapshot.py) 原样导入 V8-16 快照工具，另加 8 个过境/共享函数体的细粒度散列、V8-16 预置测试 SHA 和 `full_transit_r2` 的全部文件，输出 [snapshot_part1.json](snapshot_part1.json)。
  - 160 个输入与 v14c 末快照相同；模块文件 227 个；细粒度不变量 15/15 可取；v07_* 目录 22 个。
  - 两个冻结工作树：fe-prod-r3@641a9b3、fe-s3@de4d115，均 clean。
- **旧测试基线：** [part1/tests_baseline.txt](part1/tests_baseline.txt)，用 V8-16 同一套件清单（[run_suites.sh](run_suites.sh)）。结果与 V8-16 最终日志 `part9/tests_final.txt` 相比：
  - 失败项相同，都是 V8-12 的两项历史失败：`test_registered_files_hash_and_read_only`、`test_each_diagnostic_threshold`。带数据根时为 1 项。
  - 有两处差异，都只是环境变量没设置导致 skip，不是新失败：V8-15 `test_preset_local_defaults` 缺 `V8_15_WORKER_SELECTION`，V8-16 `test_extra_*` 跳过 1 项。
- **预置测试：** 3 个文件按指令第 9 节原样落盘到 `Multi-UAV SimpleGC/tests/v08/V8-17/`（提取脚本 [extract_presets.py](extract_presets.py)）。SHA256 与指令附带的 `instruction_static_check.json` 逐一相同：
  - numeric `eca9adfc…8478`
  - local_geometry `5066c4a0…7c19`
  - local_artifacts `cbad45eb…d389`

  **这些测试此时尚未运行。**
- **外部运行根：** `_handoff/2026-11-06_V8-17_intrusion/run/`，下设 cache、out、diagnostics、logs。

## 2. 第 2 部分：通用层与第一轮字节门禁 —— 完成

**代码（提交 2）：**
- `layer_limits.constraints_for_task` 新增 `crossing_boundaries`：
  - 构造：先 `dict(warnings)`，再按目标上限追加深层边界。上限 2 追加 alert，上限 3 依次追加 alert、protected。键名为 `__crossing__<target>::<layer>`，冲突时末尾加 `#`。
  - 不变的部分：base 与 warnings 的构造、顺序、对象。
  - 键到层名的映射：另由 `crossing_layer_keys(cons)` 给出，只写入突入见证。
- `optimize._optimize_segment_intent` 只把 `references_from_skeleton(warnings=cons["warnings"])` 改为 `cons["crossing_boundaries"]`；监视分支仍用旧 warnings。
- `single_intent`：
  - 新增 `intrusion_mission`：先调用 `monitoring_mission`，再只替换唯一 TaskSpec 的 intent。
  - `validate_single_mission` 接受 transit 与 intrusion，并显式确认实际 intent 与 `final=True`。
  - `GENERATION_INTENTS` 和 `mission_for_intent` 加入 intrusion。
- `intent_dispatch`：intrusion 的三个分派分别指向 `intents.intrusion.propose_and_build`、`optimize_checks.check_intrusion`、`nominal_checks.screen_intrusion_member`。本部分提交时这三个是**明确抛 NotImplementedError 的未完成分支**，不返回假成功；第 3、4 部分补齐。

**测试（执行方运行，有记录）：** 预置 `test_crossing_table_all_seven_intents`（七种意图的边界表；detour 仍抛 ValueError；`#` 转义碰撞反例）与 `test_mission_and_dispatch` 2/2 通过，夹具未修改。完整测试结果见第 4 部分。

**第一轮字节门禁（phase 2）：** 用 [run_gates.sh](run_gates.sh) 运行，24 进程，同一环境与输入，新缓存根 `run/cache`。比较对象是每个 `contracts/<id>/` 的递归文件集合和原始 bytes，排除清单 `[]`，失败合同也比较。

| 意图 | 运行 | 基线 | 结果 | 证据 |
|---|---|---|---|---|
| monitoring | `run_separation_v15.py --mode production-quick` → `run/out/monitor_regression_2` | `full_v14c` | **20/20 逐字节一致**，records 键集合相同 | [part2/gate_monitoring.json](part2/gate_monitoring.json) |
| transit | `run_transit_v16.py --stage quick` → `run/out/transit_regression_2` | `full_transit_r2` | **20/20 逐字节一致**，records 键集合相同；快批检查点 20/20 成功、无触发 | [part2/gate_transit.json](part2/gate_transit.json) |

运行日志见 [part2/gates_2.log](part2/gates_2.log)：开始于 05:36:52，监视结束于 05:41:26，过境结束于 05:49:44。过境用新缓存，弦集合预建占了大部分时间。门禁开始时代码为提交 1 加第 2 部分未提交改动（日志首行记录 dirty 数与 diff stat）。门禁期间只新建了不被监视/过境导入的突入专用文件，没有修改共享文件。

## 3. 第 3 部分：突入骨架 —— 代码已写，解析测试与单格查询已运行（有记录）；尚不宣称全链路验收

**新增：**
- `v08/motion/intrusion_numeric.py`（模块导入只依赖 NumPy/标准库；场景几何惰性导入）：
  - `deepest_station`：圆用投影公式；凸多边形穿过时用分段线性下包络极值枚举，并列取最小 x；不穿过时逐边求直线到线段的最近点；BufferedPolygon 取原多边形的 argmin。
  - `endpoint_interval`：取 I_p ∩ I_c ∩ (−∞, x_*]。不设 contour 下界；切线时得到单点区间，属合法结果。
  - `sigma_values`：横排只取 1.0；其余取 k/20，且要求 σ·b ≥ 6。
  - 区间工具：`normalize_intervals`、`intersect_two`、`intersect_endpoint_sets`。
  - `prefix_endpoint_set`：其他设施 warning 允许终点停在其深处，不套用过境 `_band_ok`。
  - `draw_feasible`：依次抽格、σ、终点（按区间总长度均匀抽）、相容的 D_c，每步只抽一次。
  - `preentry_clearance_ok`：逐弦精确检查，等号算合法。
  - `circle_infeasibility_certificate`：在规定 σ 网格下判断必要条件。
  - `clip_lanes`：按单成员 Slots 调用原 `derive_members`，成员域为 [s_c + l_i, s_e + σ l_i]。
- `v08/motion/intrusion_chords.py`：
  - 车道结果：用 `IntrusionLane` 包装原 Lane，不往 Lane 上动态挂属性。同一航向的一批车道用 `sublevel_many` 批量求 I_p、I_c 和目标 alert/protected 的 0 次水平集，与单车道计算是同一逐元素运算。最深点逐车道解析求值。
  - 格组合 `assess_cell` / `assess_formation`：
    - E_i 截到包含入圈点的同一合法 run。
    - 预留起点取 min(x_c, x_in − 210) + l_i。
    - 其他设施 warning 用前缀区间并约束。
    - 对每个 σ 平移 −σ l_i 后求交，再对 D 求并。
  - 缓存：`intrusion_v17/` 独立目录，身份版本 `v17-intrusion-chords-1`。身份包含 intent、ctx.cache_key、目标与全部圈层几何、`constraints_identity(base)`、槽位偏移（float.hex）、σ 网格以及全部常数。
  - `assess_intrusion_bundle`：抽中格的精确弦检查。
- `v08/motion/intents/intrusion.py`：
  - `propose_and_build`：宽度先定队形，再一次抽样，然后依次做精确弦检查、corridor 加至多一次 LP、曲线精确审计、`plan_starts`（`transit._transit_route` → `entry_planner`）、进场折线逐弦精确检查（`preentry_exact`），最后调用共享 `build_candidate`。
  - 同模块提供 `finish_candidate`（build_candidate 的突入分支）、`formation_probe_sequence`、`final_failure`、`infeasibility_certificate`、`last_attempt_timing`、`draw_summary`。

**共享文件按意图参数化，过境默认分支的语句与顺序不变：**
- `transit_chords`：`transit_base` / `base_field` / `collect_phys_grid` / `get_lanes` / `_sample_lanes` 增加 `intent="transit"`。过境沿用原缓存键，intrusion 用独立键。
- `corridor_rows`：仅在 `task.intent == "intrusion"` 时取 I = I_w ∩ (−∞, I_a^lo]，其中 I_a 是 alert 的 +(10+D) 正次水平集。
- `intents/transit.py`：
  - `TransitSetup` 按 task.intent 选择 base；cg_route 名称为 `<intent>_preentry`，过境仍为原名。
  - `build_candidate` 按 `proposal["intent"]` 分支：成员域用 `member_lanes`，逐成员检查与见证交给 `finish_candidate`。参考、起点拼接、速度事件、释放延迟和成员装配仍然共享。
- `nominal_checks.screen_intrusion_member`：骨架只用它作名义预筛记录。它的实现与第 4 部分的检查同源，所以同一提交写入。

**测试（执行方运行，有记录）：** 预置纯数值测试 8/8 通过，见 [part3/tests_numeric.txt](part3/tests_numeric.txt)。

**单格查询与证书**（[part3/queries.json](part3/queries.json)，`run_intrusion_v17.py --stage queries`，单进程）：
- **o34_d3**（family_s15_3968861533cf6dd7 / facility_02，12 机，b = 15.909074683887699 m）：圆形证书成立。
  - 参数：R = 21.21490313131122，R_p = 126.98022013174577，Q = 66.21490313131122，σ_min = 0.4。
  - 纵列/梯形跨度 69.99992860910588 > Q；横排跨度 174.99982152276468 > 2Q = 132.42980626262244。
  - 三种队形均被否定，合同以 proven_infeasible、attempts = 0 结束，与指令 3.7 的数值一致。
- **o17_d1 / o17_d4**（12 机，loose 映射为横排，Polygon 目标）：各有 1 个可行格，共 8870 格。不可行原因：no_endpoint 6864、no_target_crossing 1934、target_depth_lt_10 68、no_sigma_endpoint 3。U C.2 的原型参照为"边缘各 5 格"；二者口径不同（近似原型对精确集合），不作为验收值。
- **四个 smoke 键**的第一个 probe 均非空：

  | 键 | 可行格 / 总格 |
  |---|---|
  | o01_d0 | 522 / 9222 |
  | o01_d1 | 455 / 9222 |
  | o02_d0 | 314 / 10370 |
  | o11_d0 | 633 / 11320 |

**开发中的单合同试跑（scratch，不作证据）：** 四键骨架各在第 1 次 attempt 成功，均为弯曲 LP。o01_d0 的全链路在第 1 次 attempt 成功，冻结核验通过；实测两成员三层进入次数都是 1/1/1；合同 JSON 中计时键 0 处。正式 smoke 见第 5、6 部分。

**性能修正（行为不变）：** `deepest_station` 的多边形分支由 Python 双循环改为同一浮点运算的向量化枚举，按升序 unique 后取 argmax，并列仍取最小 x。车道的次水平集改为整批计算。o02_d0 的单车道几何耗时从 63 s 降到 0.7 s，抽样结果不变（σ、x_e、格数相同）。

## 4. 第 4 部分：检查、冻结核验接入、保存、测试与第二轮门禁 —— 完成

**代码（提交 4）：**
- `optimize_checks.check_intrusion`：在优化后的实际样条上用 `_grid_times` 求值。
  - 边界：对完整轨迹用 crossing_boundaries 调用冻结 `crossing_analysis`。目标 warning/alert/protected 每层方向必须恰为 `["in"]`；边界检查本身的失败照报。
  - 终点：contour SDF ≤ **50**（取自冻结 `roles.intrusion.max_contour_distance_m`），protected SDF ≤ −10。
  - 名义判据：对释放到移动结束再加 2 s 保持的 10 Hz 帧调用 `screen_intrusion_member`。
  - 失败 kind 固定为十类：terminal_contour、terminal_protected、boundary_crossing、target_layer_crossing、nominal_start_inside、nominal_layer_regression、nominal_multiple_visits、nominal_not_entered、nominal_layers、nominal_dwell，并保存原始数值。
  - 不检查所有 warning 外 50 m，不要求出圈，不调用 revisit。
- `nominal_checks.screen_intrusion_member`（第 3 部分已写）：
  - 进入次数按 False→True 计数，首帧为 True 也计一次；首次进入时刻取整数 time_us。
  - dwell 检查覆盖释放后的整个窗口。
  - 9 个固定 conditions。
- `joint_monitoring.attempt_chain`（只改两处）：
  - intrusion 的遥测分派；
  - 冻结 `verify_segments` 与 `check_validity` 都通过之后、返回 ok=True 之前，调用 `intrusion_report.measured_members` 复算实测三层进入次数。不是 1/1/1 时按普通失败处理，stage = `measured_intrusion_entries`，消耗本次 attempt。
- `joint_intent`：
  - `run_contract` 支持 intrusion：mission、final_failure、draw_summary、阶段诊断都按 intent 分派。运行前做圆形证书（attempts = 0）。
  - intrusion 的 `retained_p0_ok` = `JM._retained_p0` 与全体成员实测进入次数均为 1。
  - result.json 增加 `intrusion` 块（σ、x_e、逐成员 entry_counts / first_entry_us / end_contour_m / min_contour_m），失败时为 None。
  - 机械提取 `save_intent_contract`，旧 `save_transit_contract` 保留为包装，过境不补任何字段。
  - `prewarm_all(..., intent=)`；`run_selected` 和 `full_stage` 的预建、多样性、Fréchet、检查点都按 intent 分派。`full_stage` 另报 `diversity_complete`。
- `transit_report`：
  - `member_phase_times`、`phase_durations`、`group_reference_curves`、`frechet_blocks` 增加仅限关键字的 `intent="transit"`。
  - 机械提取 `phase_diagnostics(res, *, intent, ctx)`，旧 `phase_diagnostics_transit` 包装它。
  - intrusion 的终端减速诊断：名义末端严格递减段；优化/实测制动开始点所在圈层，以及到保护边界的有符号距离。
- `skeleton_transit`：机械提取 `run_intent_skeleton_contract` / `run_intent_skeleton_batch`，旧过境包装保留。intrusion 的检查点用 `intrusion_report.skeleton_checkpoint`。
- `intrusion_report`：
  - `skeleton_checkpoint`：名单只影响成功率与档差；
  - `measured_members`；
  - `full_checkpoint`：名单只影响成功率与档差；另报原始 200 口径。
- 新 CLI `tools/v08/run_intrusion_v17.py`：stage 包括 smoke / queries / chord-gate / skeleton / quick / full / rerun，内部显式传 `intent="intrusion"`，不另写进程池。
- 运行说明 [RUNNING.md](RUNNING.md)：写明默认 24 进程、复跑固定 1。

**测试（执行方运行，有记录；均未修改预置文件，夹具未补字段）：**

| 套件 | 结果 | 日志 |
|---|---|---|
| 预置 `test_preset_numeric_v17.py`（SHA `eca9adfc…8478`） | 8/8 通过 | [part4/tests_v17.txt](part4/tests_v17.txt) |
| 预置 `test_preset_local_geometry_v17.py`（SHA `5066c4a0…7c19`） | 5/5 通过 | 同上 |
| 预置 `test_preset_local_artifacts_v17.py`（SHA `cbad45eb…d389`）：`RegressionPreset` | 1/1 通过，覆盖四道门禁 | 同上 |
| 同文件 `ArtifactsPreset`（3 个方法） | **未执行**：`V8_17_OUT` 未设置，skip。快批与全量完成后再运行 | 同上 |
| 自加 `test_extra_local_v17.py` | 4/4 通过：上限 1 边界表与 warnings 同键同序同对象；过境缓存键不变；控制流注入（下游故意失败时每个 attempt 只抽一次格/σ/终点，LP ≤ 1 次，失败后不再 probe 队形，下一 attempt 只有 attempt 键递增）；o01_d0 保存后重读，实测事件与 result.json 一致，合同 JSON 中计时键 0 处 | 同上 |
| 旧套件（V8-16 同一清单） | 与第 1 部分基线完全相同：只有 V8-12 两项历史失败（带数据根时 1 项），其余全过；两处 skip 原因同基线 | [part4/tests_old_suites.txt](part4/tests_old_suites.txt) |

**V8-16 测试传播（指令 4.4 第 2 条）：** 核对 S 的 V8-16 预置文件，确实没有"cons 精确键集合"或"intrusion 分派必须抛错"之类的断言，所以不修改旧测试。V8-16 预置文件的 SHA 保持不变（见首尾快照），detour 不支持的旧测试仍通过。新键与新分派由 V8-17 预置测试和自加测试覆盖。

**第二轮字节门禁（phase 4，第 3、4 部分全部代码就位后运行）：**

| 意图 | 运行 | 结果 | 证据 |
|---|---|---|---|
| monitoring | `run/out/monitor_regression_4` 对 `full_v14c` | **20/20 逐字节一致** | [part4/gate_monitoring.json](part4/gate_monitoring.json) |
| transit | `run/out/transit_regression_4` 对 `full_transit_r2` | **20/20 逐字节一致** | [part4/gate_transit.json](part4/gate_transit.json) |

日志见 [part4/gates_4.log](part4/gates_4.log)，开始于 05:59，结束于 06:05:47。四道门禁的清单是 [regression_gates.json](regression_gates.json)。停止条件 1 未触发。

## 5. 第 5 部分：200 合同只骨架 —— 完成，止损检查点未触发

### 5.1 昂贵运行前的快速检查（全部达标后才启动 200 合同）

| 检查 | 结果 | 证据 |
|---|---|---|
| 第 9 节数值与几何测试、旧 curve_lp 测试（V8-16 numeric 套件内）、两意图两轮字节门禁 | 全部通过（第 4 部分） | part4/ |
| U C.3 四键骨架 smoke（o01_d0、o01_d1、o02_d0、o11_d0） | 4/4 在第 1 次 attempt 成功，均为弯曲 LP，每个 attempt 抽样 1 次、LP 1 次；合同 JSON 中计时键 0 处 | [part5/smoke_skeleton_check.json](part5/smoke_skeleton_check.json)；输出根 `run/out/smoke/skeleton_r1` |
| ↳ 终点公式 | 相邻槽位终点实测距离与 \(\sqrt{[\sigma(l_i-l_j)]^2+(d_i-d_j)^2}\) 的最大误差 ≤ 1.9e-12 m。纵列 o01_d1：σb = 0.3×23.843 = 7.153 m；o11_d0：0.35×19.381 = 6.783 m；横排 o02_d0：b = 15.157 m | 同上 |
| ↳ 事件键 | 每成员都有 warning < alert < protected < terminal 的弧长，以及 `terminal_x`；终点 contour ≤ 45、protected ≤ −10、不越过最深点，全部成立 | 同上 |
| 边缘例与名单查询 | o34_d3 圆形证书成立；o17_d1、o17_d4 各 1 个可行格，不加入排除名单 | [part3/queries.json](part3/queries.json) |
| **45 组组合一致性门禁**（指令 5.1 / U D.8） | 前 5 个登记族 × 人数 {1, ⌈N/2⌉, N} × σ ∈ {1, 0.5, min Σ}，**45/45 逐格完全相同**。比较内容：每格的存在性与原因、D 子集、终点区间端点、规范顺序，以及 cells/reasons/n_cells。五族总人数 6/9/6/7/9，与指令一致。另加的横排 σ=1 与梯形最小横向步长 σ=min Σ 共 10 组也全部相同（总计 55/55）。组合路径累计 29.5 s，直算路径 1049.4 s | [part5/chord_gate.json](part5/chord_gate.json)、[part5/chord_gate.log](part5/chord_gate.log) |

### 5.2 运行与名单

`run_intrusion_v17.py --stage skeleton --workers 24`，输出根 `run/out/skeleton/skeleton_r1`。散列见 [part5/skeleton_hashes.txt](part5/skeleton_hashes.txt)，日志见 [part5/skeleton_r1.log](part5/skeleton_r1.log)。
- 时间：06:22:08 开始，06:23:12 结束，墙钟 62.2 s。其中预建 41.1 s（40 族、194 个查询全部新写，查询构建 CPU 合计 574 s），派发 21.1 s。最慢的预建族为 o11 31.8 s、o13 26.4 s、o03 25.1 s。
- 指令估算为预建约 8 分钟、派发小于 1 分钟；实际更快，主要因为车道几何改成了批量计算。估算不是门槛。
- 缓存：派发阶段 `cache_hits` = 216，`cache_misses_computed` = **0**，worker 未计算任何车道（lanes_computed = 0）。
- 原始 200 行全部保留，200 个合同目录。
  - o34_d3：`proven_infeasible`，attempts = 0。
  - 名单外没有出现其他证书。

### 5.3 止损检查点（[part5/skeleton_summary.json](part5/skeleton_summary.json)、[part5/skeleton_by_bin.csv](part5/skeleton_by_bin.csv)）

| 止损项 | 阈值 | 实测 | 触发 |
|---|---|---|---|
| 名单外成功率 | < 95% | **199/199**（原始 200 口径 199/200） | 否 |
| 人数档比总体低 | > 10 个百分点 | 三档 110/110、56/56、33/33，档差均为 0 | 否 |
| 成功骨架 attempts 中位数 | > 1 | 1 | 否 |
| 形状审计失败 attempts / 全部骨架 attempts | > 5% | 0/202 | 否 |
| 成功骨架直线回退比例 | > 50% | 0/199 | 否 |

设施数档（85/85、84/84、30/30）与初速档（67/67、60/60、72/72）的档差也都是 0；分母不含 o34_d3。

### 5.4 正常预期的逐项报告（[part5/skeleton_stats.json](part5/skeleton_stats.json)）

- **attempt 失败：** 202 个骨架 attempt 中 199 个成功，3 个失败：
  - o27_d0 两次 `boundary_crossing`：成员擦边 graze_or_touch_band，边界为 facility_01 warning；第 3 次 attempt 成功；
  - o25_d0 一次 `reference/speed`：参考曲线有一条长 3.2e-13 m 的退化弦，不满足引导接口；第 2 次成功。

  都是普通候选失败。异常 0，缺标记 0。
- **实现队形 × 倾向：** abreast→abreast 62、column→column 46、echelon→echelon 46、loose→abreast 44、loose→echelon 1。U C.2 扫描也只有 1 例 loose→echelon，这里同样是 1 例（不设门槛）。
- **退让与抽样：** 下游触发的退让为 0。梯形二分缩小横向步长 2 例、宽度退让 1 例，均发生在形状抽样之前。每个 attempt 的 shape 抽取次数都是 1（202/202），LP 调用次数都是 1。
- **σ：**
  - 分布：1.0 有 111 例，其余从 0.95 到 0.30 都有出现。
  - 纵列 σ<1 占 43/46，梯形 45/47；横排只取 1.0。
- **终点：** 957 个成员终点全部满足 contour ≤ 45、protected ≤ −10、不越过最深点。其中 394 个在设施轮廓内（负 contour 距离合法）。contour SDF 范围为 [−117.17, 44.98] m，终点两两最小距离 6.25 m。
- **直线回退：** 0/199，全部为弯曲 LP。
- **名义预筛（只记录，不拒绝）：** 957 个成员中 934 个通过。未通过的 23 个成员（11 个合同）只有 `no_dwell_window` 一项。
  - 抽查 o19_d4、o22_d3、o04_d2：dwell 都发生在**目标 0 层（进 warning 之前的进场段）**，离移动终点 250–480 s，窗口内速度 2.9–5.4 m/s，与终点保持无关。
  - 这 11 个合同不在快批 20 键内。优化后由 `check_intrusion`（nominal_dwell）与冻结核验（no_dwell_window）硬筛，届时会表现为进入优化后的普通失败。本项不加骨架拒绝，记入第 10 节"执行方观察"。

## 6. 第 6 部分：快批 20 —— 完成，止损检查点未触发

### 6.1 前置：U C.3 四键全链路 smoke

`run_intrusion_v17.py --stage smoke --smoke-level chain`，输出根 `run/out/smoke/chain_r1`，日志 [part6/smoke_chain_r1.log](part6/smoke_chain_r1.log)。
- o01_d0、o01_d1、o02_d0、o11_d0 **4/4 在第 1 次 attempt 全链路成功**。保留 P0 违规 0，实现异常 0。
- 新检查确实执行了：attempt_log 中有 `measured_intrusion_entries`，全为 1/1/1；semantic 检查结果为空列表。
- 合同 JSON 中计时键 0 处，见 [part6/smoke_chain_check.json](part6/smoke_chain_check.json)。
- **保存后重读：** 用预置 `ArtifactsPreset.test_disk_tracks_frozen_verification_and_events` 对 smoke 输出单独运行（该方法不依赖 stage），1/1 通过，没有 skip，见 [part6/smoke_chain_disk_check.txt](part6/smoke_chain_disk_check.txt)。重读后核对的内容：冻结 `verify_segments`、`check_validity`、实测间距 ≥ 2 m；三层进入次数为 1/1/1，首次进入帧与 result.json 一致；min contour ≤ 50。

### 6.2 运行

`run_intrusion_v17.py --stage quick --workers 24`，输出根 `run/out/quick/quick_r1`（散列见 [part6/quick_hashes.txt](part6/quick_hashes.txt)，日志见 [part6/quick_r1.log](part6/quick_r1.log)）。
- 键：用 `select_quick` 协议重算的 20 键与 manifest 登记的快批键完全相同，不含 o34_d3（[part6/quick_selection.json](part6/quick_selection.json)）。
- 时间：06:26:47 开始，墙钟 53.4 s，其中预建 4.0 s（全部读已有文件），派发 49.4 s。
- 缓存：`cache_hits` 20，`cache_misses_computed` **0**。

### 6.3 止损检查点（[part6/quick_summary.json](part6/quick_summary.json)、[part6/quick_stats.json](part6/quick_stats.json)）

| 止损项 | 阈值 | 实测 | 触发 |
|---|---|---|---|
| 成功数 | < 16/20 | **20/20**（全部第 1 次 attempt） | 否 |
| 成功合同 post_optimization_failures 中位数 | > 0 | 0；`attempts_undetermined` = false | 否 |
| 每合同 optimization_s 中位数 | > 60 s | **6.45 s**（最小 2.79、p90 17.8、最大 23.6 s）；进入优化的合同 20/20 | 否 |
| 保留 P0 违规 | > 0 | 0 | 否 |

### 6.4 其他记录

- **ArtifactsPreset 前两个方法**（指令 9 节：快批先运行这两个），用 `V8_17_OUT=quick_r1` 运行，**2/2 通过**（[part6/tests_artifacts_quick.txt](part6/tests_artifacts_quick.txt)）：
  - `test_keys_common_conditions_and_no_timers`：20 键与登记名单一致；8 个公共字段与 full_v14c、full_transit_r2 同键相同；全部合同 JSON 递归无计时键；attempts 在 [1, 20] 内。
  - `test_disk_tracks_frozen_verification_and_events`：对 20 个保留合同从磁盘重读，冻结核验、有效性与三层进入事件全部通过。
  - 该文件的 `test_five_serial_repeats` 和全量口径检查属于第 7 部分，**尚未执行**。
- **失败 attempt：** 0；semantic 子原因的分布为空。
- **实现队形与 σ：** 横排 9 例（σ=1）、纵列 7 例（σ ∈ {0.3, …, 1.0}）、梯形 3 例（σ 0.5/0.55/0.8）。全部为弯曲 LP。
- **阶段时长**（99 个成员，名义映射）：
  - ingress（释放到 warning 入点）中位数 564.8 s，inside（入点到终点）中位数 197.4 s，travel 中位数 772.7 s；
  - 两段相加与 travel 的残差最大 2.3e-13 s；
  - release delay 中位数 83.8 s。共同预保持 20 s 与终点保持 2 s 不计入以上时长。
- **附录裁定 1 诊断（P2，不设门槛）：** 优化轨迹的制动开始点，指样本末端连续严格递减速度段的起点。
  - 所在圈层：保护层（3 层）98 个，警戒层（2 层）1 个。
  - 到保护边界的有符号距离：中位数 −77.0 m，p90 −41.6 m，最大 **+14.1 m**（警戒层那一例，在附录估计的"保护边界外最多约 18 m"范围内）。
  - 名义末端严格递减段持续时间见 quick_stats.json。实测轨迹末端有保持段，"严格递减至终点"的定义取不到起点，记 None，不作结论。
- **阶段速度**（复用 phase_metrics，参考速度 ≥ 0.5 m/s 的同一批样本）：数值见 quick_stats.json 的 `phase_speed`，本项没有已证实的数值门槛。
  - ingress 段：参考最低 0.54 m/s，优化/参考最低速比中位数 0.158，实测/参考 0.092。这类低比值出现在释放后起步加速、参考速度刚超过 0.5 m/s 的样本上；V8-16 的过境也有同口径现象，这里不外推结论。
  - inside 段：优化比中位数 0.40，含末端减速。

**第 6 部分完成；按负责人指示在此停下，等待通知后再执行第 7 部分（全量 200+100、5 键单进程复跑、三意图配对）。**

## 7. 第 7 部分：全量、复跑与诊断 —— 完成，止损与 P0 均未触发

负责人确认机器空闲后才开始运行。

### 7.1 前置检查与运行

- **前置条件：** 骨架与快批检查点已放行（第 5、6 部分）；预置测试与两轮字节门禁可核对；缓存已预建；磁盘保存重读已成功；复跑 5 键在全量开始前已写入 `rerun_keys.json`（[part7/rerun_keys.json](part7/rerun_keys.json)，o01_d0–o01_d4，按 (order, draw) 字典序取前 5 个，不按结果挑选）。
- **全量：** `run_intrusion_v17.py --stage full --workers 24`，输出根 `run/out/full/full_r1`，散列见 [part7/full_hashes.txt](part7/full_hashes.txt)，日志见 [part7/full_r1.log](part7/full_r1.log)。
  - 时间：09:08:10 开始，墙钟 312.5 s；预建 4.6 s（194 个查询全部读已有文件，**新写 0**），派发 307.8 s；并行效率 0.91。
  - 缓存：`cache_hits` 310，`cache_misses_computed` **0**。7200 s 合作退出预算没有用到，unsent 和 incomplete 都为空。
  - 各阶段 CPU 合计：优化 2727 s、仿真 3299 s、骨架 513 s、核验 31 s。
- **完整性：** 主合同 200/200 有结果（`complete = true`），多样性 100/100 有结果（`diversity_complete = true`），两者分开检查；合同目录分别有 200 和 100 个。异常 0。
- **单进程复跑：** `--stage rerun`，固定 1 进程，输出根 `run/out/rerun/rerun_r1`，日志见 [part7/rerun_r1.log](part7/rerun_r1.log)。
  - **5/5 逐字节一致**（[part7/reproduction.json](part7/reproduction.json)）。逐合同的文件数分别为 14/34/9/34/14，`file_sets_equal` 与 `bytes_equal` 全部为真，排除清单 `[]`。
  - 停止条件 3 未触发。

### 7.2 全量止损检查点（[part7/full_summary.json](part7/full_summary.json)）

| 止损条件 | 阈值 | 实测 | 触发 |
|---|---|---|---|
| 成功率 | < 80% | **199/199**（原始 200 口径 199/200，唯一失败是 o34_d3 proven_infeasible） | 否 |
| 任一非空档比总体低 | > 20 个百分点 | 人数三档 110/110、56/56、33/33；设施数三档 85/85、84/84、30/30；初速三档 67/67、60/60、72/72；档差均为 0 | 否 |
| 成功合同 post 失败次数中位数 | > 0 | 0（`attempts_undetermined` = false） | 否 |
| 作业段 Fréchet 合并中位数 | < 1 | **74.83**（after），可比较对 450；before 为 74.83 | 否 |

**保留 P0（停止条件 2）：**
- 保留尝试的违规为 0：`retained_p0_violations = []`，主合同与多样性都是。
- 957 个保留成员（主合同）的实测三层进入次数**全部为 1/1/1**。
- 预置 `test_disk_tracks_frozen_verification_and_events` 对 199 个保留合同逐一从磁盘重读，用冻结 `verify_segments` / `check_validity` 复核，全部通过。

### 7.3 预置测试最终运行（[part7/tests_v17_final.txt](part7/tests_v17_final.txt)）

| 文件 | 结果 |
|---|---|
| `test_preset_numeric_v17.py` | 8/8 通过 |
| `test_preset_local_geometry_v17.py` | 5/5 通过 |
| `test_preset_local_artifacts_v17.py` | **4/4 通过，无 skip**：四道门禁 RegressionPreset；`test_keys_common_conditions_and_no_timers`（全量口径：200 键为 40 族 × draw 0–4，多样性 100，o34_d3 为 proven_infeasible，三意图公共字段一致，合同 JSON 中无计时键）；`test_disk_tracks_frozen_verification_and_events`；`test_five_serial_repeats` |
| 自加 `test_extra_local_v17.py` | 4/4 通过 |

**合计：17 个预置测试 17/17 通过（执行方运行，有记录）。**

### 7.4 Fréchet、时长与速度（[part7/analysis_report.json](part7/analysis_report.json) 的 `intrusion` 段）

- **Fréchet：**
  - 口径：scope 为 `intrusion_warning_to_terminal_v17`，从唯一的目标 warning 入点裁切到编组曲线末端，按 5 m 弧长重采样。每族用 b 归一一次后合并取中位数。
  - 覆盖：10 族 × 10 branch 全部成功、全部可比较，每族 45 对，没有 N/A。
  - 端点距离单列报告（中位数 738 m），不设门槛。
- **阶段时长**（957 个成员，名义映射）：
  - ingress 中位数 533.8 s（p10 230.3、p90 985.1）；
  - inside 中位数 171.4 s（p10 110.8、p90 278.2）；
  - travel 中位数 698.4 s；两段相加与 travel 的残差最大 2.3e-13 s；
  - release delay 中位数 66.4 s。共同预保持 20 s 与终点保持 2 s 另列，不计入上述时长。
  - 合同名义时长中位数：突入 818.9 s，过境 952.0 s，监视 2811.6 s。
- **阶段速度**（phase_metrics，参考速度 ≥ 0.5 m/s 的同一批样本）：
  - ingress：参考最低 0.54 m/s，优化/参考最低速比中位数 0.158，实测/参考 0.093；沿迹偏离中位数 2.67 m，最大 6.97 m。
  - inside：优化比中位数 0.33，实测比 0.26（含末端减速）；沿迹偏离中位数 1.33 m，最大 11.7 m。
  - 这些比值没有已证实的数值门槛，不作合格判定。
- **终端减速（附录裁定 1，P2，无门槛）：**
  - 名义末端严格递减段时长中位数 4.24 s，范围 [2.29, 5.60] s。
  - 优化制动开始点所在圈层：**保护层 949/957，警戒层 8/957**。
  - 到保护边界的有符号距离：中位数 −75.5 m，p90 −27.8 m，最大 **+15.3 m**，没有超出附录估计的"保护边界外约 18 m"。
  - "终点前间距收紧"按附录列入突入与佯动的可观测差异清单，供 ⑥ 防捷径检查使用。

### 7.5 三意图逐格与失败子原因（[part7/three_intent_contracts.csv](part7/three_intent_contracts.csv)、[part7/analysis_report.json](part7/analysis_report.json)）

- **配对口径：** 原始 200 键对 full_v14c、full_transit_r2、突入全量做 outer join；骨架结果分别来自 skeleton_v14b、skeleton_transit_r3、本次 skeleton_r1。
  - 公共字段（group_id、member_ids、target_id、initial_speed_m_s、formation_prior、group_size、facility_count）不一致的行 **0**，缺字段的行 0。
  - group_id 在 full records 中不存在，改取同意图骨架记录；分析工具里有注明。
- **全链成功模式**（顺序为监视/过境/突入）：

  | 模式 | 合同数 | 说明 |
  |---|---|---|
  | SSS | 197 | 三者都成功 |
  | FSS | 2 | 监视在 V8-14 两例失败，都在 9–12 人档 |
  | SSF | 1 | 突入只有 o34_d3 失败 |

  骨架模式为 SSS 199、SSF 1（o34_d3）。
- **名单与边缘例：**
  - o34_d3：监视、过境均第 1 次 attempt 成功；突入为 proven_infeasible，attempts = 0。
  - o17_d1、o17_d4：三意图全链都成功；突入骨架和全链都是 1 次 attempt、σ = 1.0（横排）；同键监视全链分别用了 5 次和 6 次 attempt。
- **attempts**（全部合同）：突入中位数 1、p90 1、最大 6；过境中位数 1、p90 2；监视中位数 1、p90 4。
- **突入失败子原因**（两张表，口径不混用）：
  - **表 1**（全部失败 attempt，同一 attempt 内同一 kind 只计一次）：语义 kind 只有 `nominal_dwell`，23 次；失败类别为优化语义 23、骨架 4、优化物理 0、仿真后 0（含 `measured_intrusion_entries` 0）。
  - **表 2**（每个合同的第一次失败 attempt，分母 = 有失败的 13 个合同）：

    | 阶段与 kind | 合同数 |
    |---|---|
    | `optimize_intrusion\|nominal_dwell` | 11 |
    | `skeleton:boundary_crossing` | 1 |
    | `skeleton:reference/speed` | 1 |

  - 这 11 个 nominal_dwell 合同，正是第 5 部分骨架名义预筛检出进场段 dwell 的那 11 个，后续 attempt 全部成功。
- **对照：** 过境首次失败为 `optimize_transit|nominal_dwell` 18 例。监视为 `optimize_monitoring|nominal_dwell` 14、`nominal_revisit` 5，骨架类 41。dwell 是三意图共有的主要语义子原因。
- **分档全链成功：** 9–12 人档监视 32/34、过境 34/34、突入 33/34；其他档三者都满分，详见 `success_by_bin_full`。成功率差和时长差只作诊断，不人为配平。

## 8. 第 8 部分：快照、改动范围与提交

### 8.1 提交与分支

- **基准：** `d9a317832d7dd166610d8d6e515cf80bec5ce903`（dev/v0.8，通过显式 refspec 获取后核对）。
- **审查分支：** `review/v08/V8-17-intrusion`。只推送了这一个分支，没有推 main、没有强制推送、没有合并 dev。
- **各部分提交**（时间为本地提交时刻，2026-11-06）：

| 部分 | 提交 | 时刻 |
|---|---|---|
| 1 | 0e808fa | 05:31 |
| 2 | 950d772 | 05:50 |
| 3 | cf3134b | 05:59 |
| 4 | ff7e18a | 06:06 |
| 5 | 7bd5550 | 06:24 |
| 6 | f4a6d50 | 06:28（按负责人指示在此暂停） |
| 7 | e36d353 | 09:17 |
| 8 | 本报告所在提交，见文末 ls-remote 核对 | — |

### 8.2 改动文件（`git diff --stat d9a3178 HEAD -- "Multi-UAV SimpleGC"`：22 个文件，+3037 / −102）

- **新增：**
  - `v08/motion/intrusion_numeric.py`、`v08/motion/intrusion_chords.py`、`v08/motion/intents/intrusion.py`、`v08/runner/intrusion_report.py`
  - `tools/v08/run_intrusion_v17.py`、`tools/v08/analyze_intrusion_v17.py`
  - `tests/v08/V8-17/`：3 个预置测试加 1 个自加测试
- **修改（都在指令 0.2 允许的范围内）：**

| 文件 | 改动行数 |
|---|---|
| `layer_limits.py` | +25 |
| `single_intent.py` | 31 |
| `intent_dispatch.py` | 11 |
| `optimize.py` | **3 行**：只改 `_optimize_segment_intent` 的边界表参数 |
| `optimize_checks.py` | +89，只新增 |
| `nominal_checks.py` | +49，只新增 |
| `transit_chords.py` | 52 |
| `intents/transit.py` | 25 |
| `joint_monitoring.py` | +11：只加 intrusion 遥测分派和实测进入检查 |
| `joint_intent.py` | 171 |
| `skeleton_transit.py` | 84 |
| `transit_report.py` | 114 |

- 下列文件不需要修改，实际也没有修改：监视构造文件、`transit_numeric.py`、`formation.py`、`shared_routes.py`、`skeleton.py`、默认进程数。

### 8.3 首尾快照（[snapshot_part1.json](snapshot_part1.json) → [snapshot_end.json](snapshot_end.json)，比较结果 [snapshot_compare.json](snapshot_compare.json)）

- **以下各项首尾完全相同：**
  - 160 个登记输入；
  - 22 个 `SwarmData/v07_*` 目录的统计；
  - 两个冻结工作树（fe-prod-r3@641a9b3、fe-s3@de4d115，都 clean）；
  - `full_v14c` 的全部 8551 个文件、`full_transit_r2` 的全部 8651 个文件；
  - 29 个 V8-11 至 V8-15 预置测试，6 个 V8-16 预置/自加测试；
  - 15 个细粒度函数体：`check_monitoring`、`solve_joint`、`Prepared`、`prepare_problem`、`monitoring_constraints`、`revisit`、`screen_member`、`check_transit`、`screen_transit_member`、`curve_lp`、`exact_curve_audit`、`derive_members`、`route_to_slot`、`references_from_skeleton`、`crossing_analysis`。
- `configs/`、`task_v07/`、`v08/criteria/`、`v08/sim/` 下没有任何文件变化，可以确认判据、优化器求解核心、输入和环境都没有改动。
- conda `llm` 环境没有安装或升级任何包；运行版本与 manifest 登记一致（Python 3.12.3、NumPy 2.5.3、SciPy 1.14.1、shapely 2.0.7）。

### 8.4 一条可复制的负责人复跑命令

在 `Multi-UAV SimpleGC` 目录、PowerShell 7 下先设置四个线程变量（见 [RUNNING.md](RUNNING.md)），然后运行：

```powershell
& 'C:\Users\shy\anaconda3\Scripts\conda.exe' run -n llm --no-capture-output python -B tools/v08/run_intrusion_v17.py --stage quick --devset 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08\docs\v08\V8-03\devset_v08.json' --data-root 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData' --cache 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-06_V8-17_intrusion\run\cache' --out 'F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-06_V8-17_intrusion\run\out\quick\<新目录>' --workers 24
```

完整的分阶段命令见 RUNNING.md 第 2 节。全量、复跑与门禁按检查点逐条执行。

### 8.5 实际耗时（墙钟）

| 部分 | 实际耗时 | 计算 |
|---|---|---|
| 1 | 约 20 分钟 | 含通读两份材料 |
| 2 | 约 20 分钟 | 门禁 13 分钟（新缓存预建占大头） |
| 3 | 约 10 分钟 | 实现大部分在第 2 部分门禁运行期间并行完成 |
| 4 | 约 7 分钟 | 门禁 6 分钟 |
| 5 | 约 18 分钟 | 组合门禁 17 分钟（直算路径 1049 s），200 骨架 62 s |
| 6 | 约 4 分钟 | smoke 56 s，快批 53 s |
| 7 | 约 10 分钟 | 全量 312 s，复跑 37 s |

- 合计开发约 1.5 小时、计算约 45 分钟，不含 06:28–09:08 按负责人指示的暂停。
- 计算时间低于 U B 的估算，主要原因是车道几何的批量化，以及缓存在派发前全部预建。
- 估算只是记录，没有为缩短耗时裁减任何检查或名单。

### 8.6 证据等级

- 第 2、4 部分的门禁、第 5–7 部分的批次、17 个预置测试和 4 个自加测试：都由执行方运行，属于"有记录"。
- 5 合同单进程复跑与 24 进程输出逐字节一致：执行方在同一环境的第二次独立运行，用来证明可复现；但它不等于规划审查方的"已复跑"。按 G 的规程，P0 验收的"已复跑"仍需审查方执行。

## 9. 偏离指令之处与处理

1. **第 2 部分提交里的 intrusion 骨架文件是桩：**
   - 门禁开始时 `intents/intrusion.py` 是明确抛 NotImplementedError 的桩。之后为了并行开发，在工作区写入了完整实现，但这个文件不被监视/过境导入。
   - 提交 2 时把桩版本原样提交，提交 3 才放入完整实现，所以提交 2 与门禁运行时的代码状态一致。
2. **CRLF 事故（已修复，未进入任何提交）：** 第 2 部分首次编辑时，用 Python 文本模式写文件，把 4 个 LF 文件改成了 CRLF。在提交前发现，已逐字节恢复为 LF；之后所有共享文件改动都按字节读写。
3. **性能修正属于"行为不变"的实现细节：** `deepest_station` 的多边形分支改为向量化枚举，车道次水平集改为整批 `sublevel_many`。两者与逐元素/逐对计算是同一组浮点运算；四键抽样结果改动前后完全相同，45 组组合门禁也用同一实现的 memo=True/False 两条路径逐格核对。
4. **分析工具的数据来源：** 全量 `records.json` 里的 attempt_log 是精简版，没有 semantic_failures。三意图子原因统计改为读取各合同 `result.json` 中完整的确定性 attempt_log；三个意图的基线都有这些文件，所以不存在"旧证据未记录"的语义失败。
5. **实测制动开始点：** 指令只定义了名义末端递减段，并要求报告"优化制动开始所在圈层"。实测轨迹末端有保持段，"严格递减至终点"的定义取不到起点，所以实测项记 None，只报优化与名义两项。

**疑似预期错误：** 没有发现。17 个预置测试的预期值全部与实现一致，夹具没有补任何字段（裁定 2 的流程未被触发）。

## 10. 第 12 节各项是否被实测进一步确认，以及执行方观察

**第 12 节各项：**
- **七种意图上限：** 由预置测试确认；detour 仍抛 ValueError。
- **最深点不唯一：** 由矩形平台的预置测试确认，并列取最小 x。
- **"两两距离"：** smoke 实测相邻终点距离与公式的误差 ≤ 1.9e-12 m；非相邻、梯形都按公式计算。全量终点两两最小距离 6.25 m（骨架）。
- **o34_d3：** 证书数值与第 12 节一致；名单外 199 个合同没有出现证书。
- **圈层尺度摘要：** 按实际输入计算，未拒绝任何输入。
- **压缩只在保护层内（附录裁定 1）：** 实测优化制动开始点 949/957 在保护层，8/957 在警戒层，最远在保护边界外 15.3 m，与附录估计的约 18 m 一致。**这仍是诊断项，不是约束，也没有被"证明"。**
- **突入 base 与进场：** 名义硬筛和保留前的实测检查双重保险。957/957 成员实测三层进入次数都是 1/1/1；进场精确检查 `preentry_exact` 在全量中没有出现失败。
- **终点 50/45/最小距离 50：** 三者分开实现。骨架终点 contour SDF 最大 44.98（≤ 45）；优化后的 50 由预置测试的等号例和 50.5 拒绝例确认。
- **其他 warning 深穿越：** 用前缀区间并实现，有预置解析测试覆盖。
- **210 m 预留：** 按源码公式实现。
- **穿越时刻口径：** 终点集合用 line_sublevel；名义映射用 crossing_analysis；实测事件用 10 Hz 首帧，三者分开保存。
- **LP 与精确审计：** 全量没有直线回退（骨架 0/199，快批与全量全部为弯曲）。
- **旧测试传播：** V8-16 预置文件的 SHA 保持不变。
- **共享文件冻结边界：** 两轮字节门禁各 20/20。
- **弦缓存身份：** 使用独立的 `intrusion_v17/` 目录与 float.hex 身份。
- **全量完成性：** 200 与 100 分别检查。
- **墙钟污染：** 递归扫描全部合同 JSON 为 0 处，5/5 复跑逐字节一致。
- **原型覆盖：** 四例 smoke 与 45 组门禁补充了覆盖。

**执行方观察（与事实分开）：**
1. **进场段名义 dwell 是突入唯一的语义失败来源。** 11 个合同的第 1 次 attempt 在优化后被 `nominal_dwell` 拒绝，后续 attempt 都成功，因此 post 失败中位数仍为 0。
   - 骨架阶段的名义预筛已经提前标出了这 11 个合同。
   - dwell 位于目标 0 层的进场路由内：20 s 窗口内位移不超过 30 m，速度 2.9–5.4 m/s，看上去是起点到集合槽位的转弯段。
   - 过境（18 例）和监视（14 例）同样以 nominal_dwell 为主。
   - 这是共享路由的现象，不在本项修改范围内。
2. **o17_d1/d4 的精确可行格只有各 1 格**（U C.2 原型为 5 格）。两者仍能成功，但同一合同在不同 branch 下的终点几何多样性可能很低。本项多样性 10 族不含 o17，未实测。
3. **ingress 阶段的速度比**（优化 0.158、实测 0.093）都出现在释放后刚起步、参考速度略高于 0.5 m/s 的样本上，口径与 V8-16 相同。在这个口径下，比值更多反映起步加速，而不是途中低速。
4. **多样性的 Fréchet before 与 after 几乎相等**（74.83 对 74.83）。优化位移对编组曲线的平均影响很小。

## 11. 需要审查方判断的事项

1. **进场段 nominal dwell：** 三意图共有，突入 11/199 个合同的首次 attempt 因此被拒绝。要不要在后续工作项中，在路由或速度事件层面给出构造机制，而不是靠 attempt 重试吸收？本项按指令只记录、不改路由。
2. **附录裁定 1 的诊断结果：** 8/957 个成员的制动开始点在警戒层，最远 +15.3 m。是否确认维持 P2、不设门槛，并把"终点前间距收紧"列入 ⑥ 的可观测差异清单？
3. **o17 边缘例的低多样性：** 每合同只有 1 个可行格。是否需要单独做多样性抽查，或调整边缘族的统计口径？
4. **两处"行为不变"的性能实现**（向量化最深点、批量次水平集）：执行方用解析预置测试和 45 组门禁做了核对。审查方是否需要逐位独立复核？
5. **共享文件参数化的方式：** 在 `build_candidate` 里按 intent 分支，并把突入的逐成员检查交给 `intrusion.finish_candidate`；共享的 `corridor_rows` 只在 intrusion 分支取新上界。是否符合"机械提取、不复制第二套算法"的要求？两轮字节门禁只能证明过境与监视的行为没变，不能证明代码组织方式合适。
6. **"已复跑"等级：** 门禁、全量和 5 键复跑都由执行方运行（有记录）。P0 的"已复跑"需要审查方在本机或云端独立执行。
7. **公共字段 group_id 的来源：** 三意图配对时，因为 full records 不含 group_id，改从骨架 records 取，其余公共字段都取自全量记录。是否接受这种口径？预置的产物测试另外直接比较了 contract.json 中的 group_id，对 200 键全部一致。

---

**推送核对：** 第 8 部分报告提交 `c045545c31adcee0d9a55be247dcf651bf9a584d` 推送后，`git ls-remote origin refs/heads/review/v08/V8-17-intrusion` 返回同一 SHA。本行随后单独提交，该提交的远端核对见执行方的最终回报。
