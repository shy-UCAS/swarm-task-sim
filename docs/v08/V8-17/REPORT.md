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
