# V8-15 间距压力用例与提速基础：执行报告

> **执行方：** Claude Code，模型 Claude Opus 5.5（`claude-opus-5-5`）。本项没有配置任何模型接入。
> **依据：** 《V8-15_间距压力用例与提速基础_执行指令_20261105.md》（下称"指令"）与《V8-15_GPT指令评价与裁定_20261105.md》（下称"附录"）。附录与指令冲突处以附录为准。原文归档在仓库根 `claude/v08/`。
> **基线：** `dev/v0.8` = `origin/dev/v0.8` = `2dbb2a45627b61ebad2eba5d4f16b311e05fe193`（第 1 部分实测）。
> **分支：** `review/v08/V8-15-separation`，从 2dbb2a4 新建。
> **开始时间：** 2026-11-05 04:4x（本机 Git Bash 显示时区 −0800）。结束时间与完成提交写在报告末尾。

## 0. 开工前复述

### 0.1 八个部分

| 部分 | 内容 | 交付 |
|---|---|---|
| 1 | 从已快进的 `dev/v0.8` 建审查分支 `review/v08/V8-15-separation`；锁定基线、输入与输出；预置测试原样落盘并记哈希 | 起点身份、冻结与输入快照、基线 `full_v14c` 全部文件 SHA256/大小/mtime_ns；附录裁定 2 的基线身份检查 |
| 2 | 合成测试与注入重做：已有覆盖直接运行；8.3 用真实局部证书/曲率 LP/梯形二分验证选队形；8.4 在真实运行器上注入采样间距、非目标警戒层、限制区三种违规，确认 attempt 0 被拒、attempt 1 被保留且落盘轨迹干净 | 新旧测试逐项结果、两级失败代码 |
| 3 | 只读分析 `full_v14c`：198 个保留合同的优化 XY、实测 XYZ 采样、实测插值三种成员对间距，按队形×拓扑×阶段分档；200 合同全部失败尝试的间距相关代码；阶段最低速度最坏样例的"末尾 20 s/途中"归类 | 不重新规划、优化或仿真 |
| 4 | 同一组 40 个中等耗时合同，分别用 8/16/24 进程各跑一次；逐合同耗时比、峰值内存；按规则选默认进程数并联动四处默认值与两个 CLI | `part4/selection.json`、`worker_choice.json`、`runtime_defaults.py` |
| 5 | 4 个不同合同单进程完整链路剖析：四阶段 cProfile 双 Top25、指定细项调用数与计时、`value_grad` 分项可归属占比与共享成本、AL 轮次、峰值内存 | 不提出任何提速方案 |
| 6 | 36 个压力合同（4 族 × 3 倾向 × 3 branch 种子）：先全部只骨架，再每倾向一个完整链路检查点，按预算公式决定剩余规模，再跑剩余完整链路 | 压力结果只作诊断 |
| 7 | 改过生产模块（默认进程数）时，用 `select_quick` 协议的 20 个快速合同、选定进程数，与 `full_v14c` 同键逐字节比较；已有测试回归；README 与 RUNNING 写日常流程 | `production_reproduction.json` |
| 8 | 报告、`reproduce.ps1`、逐部分提交，推送 `review/v08/V8-15-separation` 并核对远端 SHA | 不合并 dev，不推 main，不强推 |

### 0.2 冻结边界（指令 0.1–0.3）

- 不改运动生成、骨架、选队形、圈心数、LP、优化器、时间参考、跟踪引导、判据、标签、随机键派生。
- 不改 `configs/`、`v08/motion|sim|criteria|sampler|scene/`、合同类型、旧失败类别。
- 不恢复"生成—检验—换队形—重来"。
- 生产模块只允许接默认进程数：`runtime_defaults.py`、两个 CLI 的 parser 默认值、`run_batch` 与 `run_skeleton_batch` 的 workers 默认值。
- 冻结工作树 `Simulation-fe-prod-r3@641a9b3`、`Simulation-fe-s3@de4d115` 与 `SwarmData\v07_*` 的内容和 mtime 不变。
- `llm` 环境不装、不升级任何包。
- 不推 main、不强推、不 reset/rebase/stash、不覆盖既有输出。
- 生产缺陷只记录不修；预置测试不改预期。

### 0.3 四条停止条件（仅 U F.1 的四条 P0）

| P0 | 数什么 | 正常预期 | 触发即停 |
|---|---|---|---|
| P0-1 | 被保留尝试的实测共同可见 10 Hz 帧：间距、限制区、非目标设施警戒/保护层 | 违规 0；严格 `< 2 m` 才是违规 | 核验已失败却被保留 |
| P0-2 | 第 2 部分注入的 attempt 0 是否被保留，底层代码与顶层 stage/reason 是否正确 | 注入不保留，下一 attempt 被调用，最终载荷来自干净结果 | 忽略核验结论，或非目标警戒层失败未标 `constraint_violation` |
| P0-3 | 8/16/24 三批每个选定合同目录的完整文件集合与全部字节 | 40×3 次比较全部同键、同文件集、逐字节一致 | 任一不一致：该 worker 数不设为默认 |
| P0-4 | 有生产模块改动时，20 个快速合同目录与基线同键比较 | 20/20 逐字节一致 | 不一致：停止交付该生产改动 |

合同内排除清单为**空集合**。`contract.json`、`result.json`、`skeleton.json`、`optimized.json`、`failure_witness.json` 与 `tracks/*/*.npy` 全部逐字节比较。遥测、records、summary、日志等本来就在合同目录之外。

### 0.4 另外两条原则

- **压力结果只作诊断。** 压力集成功率、退让次数、速度与 profile 数字都不是门禁；36 个不要求全部成功，也不要求出现退让。
- **本项不跑全量。** 不执行 `--stage full` 或 `--stage diversity`，不跑 200+100；全量墙钟只按公式预测。

### 0.5 我对附录四条裁定的理解

1. **裁定 1（第 3 部分不重算 P0-1）。** `full_v14c` 的 P0-1 不再用冻结核验器逐合同重算，直接引用 V8-14 报告 C.3 中 V8-13 端到端预置测试 `test_preset_local_e2e.py` 对 `out\full_v14c` 的结果（3/3 通过），在本报告给出结果文件路径与哈希。第 3 部分仍做间距统计，但不把重算核验当作新的独立检查。压力集的 P0-1 由 `attempt_chain` 内的段核验与有效性检查保证。如果压力输出目录布局与生产相同，再把同一个 e2e 测试指向压力输出目录跑一遍；布局不兼容就写明原因，不改测试。
2. **裁定 2（基线身份先核实）。** `full_v14c` 是用 `335715c` 的代码跑出的。第 1 部分先查 `git diff --stat 335715c 2dbb2a4`：如果没有触及生产路径，照指令执行；如果触及，先用 8 进程跑 o01_d0、o08_d0 两个合同与 `full_v14c` 比较，不一致就停在第 4 部分开头报告基线身份问题，不进入三档测试。
3. **裁定 3（第 5 部分剖析拆成两次运行）。**
   - **cProfile 运行：** 4 个合同按指令 5.1 选取，只开 cProfile，不叠加行级跟踪。开跑前估算 Σ wall_s × 2；超过 90 分钟时，把"骨架最贵""优化最贵"两个合同换成 `skeleton_s`、`optimize_s` 排序 p90 位置的合同（并列按业务键），报告注明替换。
   - **行级计时运行：** 另起一次，只对两个中位数合同运行。`sys.settrace` 只在进入 `optimize_segment` 时安装、`finally` 卸载。单合同超过其基线 `wall_s` 的 6 倍，或总计超过 40 分钟，就停止行级计时、保存已采集部分、报告"部分采样"。
   - 两次运行的耗时分别报告；分项占比只取行级运行的结果。
4. **裁定 4（两处补充）。**
   - 第 4 部分每档预计 5–10 分钟；若 8 进程档超过 20 分钟，报告单合同耗时分布，照常继续，不是停止条件。
   - joint CLI 默认值从 1 改为选定值，只要第 7 部分 20 合同逐字节门禁通过就接受；旧 quick 分支硬编码 1、rerun 单进程两处保持不变。

另外，附录第 3 节提示：梯形二分顺序若与预置测试不同，作为"疑似预期错误"保存证据，不改测试；第一次运行的预置测试失败先区分预期错误还是实现缺陷。

## 1. 第 1 部分：分支、基线身份与输入锁定

- **起点：** 工作树开工时 `git status --porcelain` 为空。
  - `git rev-parse dev/v0.8` 与 `git fetch origin refs/heads/dev/v0.8:refs/remotes/origin/dev/v0.8` 后的 `origin/dev/v0.8` 都是 `2dbb2a45627b61ebad2eba5d4f16b311e05fe193`。
  - 审查分支此前不存在，已 `git switch -c review/v08/V8-15-separation` 新建。
- **附录裁定 2：** `git diff --stat 335715c 2dbb2a4` 共 19 个文件，**全部在 `docs/v08/V8-14/`**（REPORT 与 v14c 证据），没有 `Multi-UAV SimpleGC/` 下的任何文件。结论：未触及生产路径，`full_v14c` 可直接作为 2dbb2a4 代码的比较基线，照指令执行，不需要 2 合同预检。
- **环境：** PowerShell `7.6.9`。conda 环境读自项目 `.conda-env` = `llm`；Python 3.12.3、NumPy 2.5.3、SciPy 1.14.1（版本明细见 `env.txt`）。
  - **硬件：** AMD Ryzen 9 9950X3D，单插槽，**16 物理核 / 32 逻辑处理器**（`Win32_Processor`）；物理内存 63.65 GB。
- **快照：** [snapshot_part1.json](snapshot_part1.json)，由 [snapshot.py](snapshot.py) 生成。
  - 160 个登记输入的 SHA256/大小/mtime_ns 与 V8-14c 收尾快照逐项相等（`inputs_equal_v14c_end = true`）。
  - 116 个代码/配置/测试文件的 SHA256。
  - `SwarmData\v07_*` 22 个目录：每目录文件数、总字节、最大 mtime_ns。
  - 冻结工作树 `Simulation-fe-prod-r3` = 641a9b3、`Simulation-fe-s3` = de4d115，均干净。
  - 基线 `_handoff\2026-11-04_V8-14_skeleton\out\full_v14c` 全部 8551 个文件的 SHA256/大小/mtime_ns（只读）。
- **预置测试原样落盘：** 五个文件按指令 8.7 从指令原文代码块提取（UTF-8、LF、末尾一个换行），SHA256 与指令登记值**逐个相等**：

  | 文件 | SHA256 |
  |---|---|
  | `test_preset_numeric_protocol.py` | `e0df2b3a422d1d5441a6b0fbaee6fe88c68f62f294bd5a236a2c05f1fc246676` |
  | `test_preset_local_formation.py` | `94b9656691dca449d3cc0e18a2f4de7fa93a50a76b2a72095fdb63e1c08e528f` |
  | `test_preset_local_injection.py` | `a41603701f57aaeec69852be29452e243af4b3f239a15fc12236cb9326f22809` |
  | `test_preset_local_defaults.py` | `de3ff62b369556be957ccb5c567c3ed0256819de3930e1eda7f3e848013d2a9e` |
  | `test_preset_local_stress.py` | `68e31d083ef0715efe02d3f9cb90f81cdbcdbb49f8be4a62303c15b735e30290` |

- **附录的审计副本：** 附录第 0 节写"另存一份到 `traj2language_docs\审计\`"。我开工时该目录里没有 V8-15 文件；该目录不在本项写入白名单内，所以我没有写入，只在这里记录。

## 2. 第 2 部分：合成测试与注入重做

完整日志：[part2/tests_part2.txt](part2/tests_part2.txt)（脚本 [run_suites.sh](run_suites.sh)；每套写出命令、cwd、提交、线程变量与 `unittest -v` 全文，含 traceback）。

### 2.1 覆盖映射（已有测试直接运行，不抄写）

| 要求 | 引用的已有测试 | 结果 |
|---|---|---|
| 采样 1.9 m 失败；帧间 1.9 m、采样约 2.025 m 通过；释放前排除 | V8-11 `test_preset_v8_11_validity.py`：`test_parallel`、`test_interframe_near_miss`、`test_visibility_and_offsets` | 3/3 ok |
| 非目标警戒层代码、限制区闭边界 | V8-11 `test_preset_v8_11_segment.py::test_other_facility_alert`；`test_preset_v8_11_validity.py::test_boundary_is_inside` | 2/2 ok |
| 下游失败不退让；只有宽度查询能选下一个队形；唯一 20 次预算 | V8-13 `test_preset_numeric_flow.py` 四个方法 | 4/4 ok |
| LP 约束、曲率复核、可行性与目标 LP 一致、折返扫描 | V8-14 `test_extra_curvature_lp.py` 六个方法 | 6/6 ok |
| 时间跟踪批量等价 | V8-14 `test_extra_tracking_batch.py` | 3/3 ok |
| 保留/P0 及次数统计 | V8-13 `test_extra_checkpoint_v13c.py` | 6/6 ok |
| 精确证书 | V8-12 `test_preset_numpy_geometry.py::test_column_band_empty_certificate`、`test_narrow_legal_channel_is_not_proven_empty`；`test_preset_numpy_checkpoint.py::test_false_proof_triggers` | 3/3 ok |

### 2.2 本项预置测试（原样，未改预期）

| 文件 | 结果 | 说明 |
|---|---|---|
| `test_preset_numeric_protocol.py` | **5/5 ok** | 第一次运行 1 个 ERROR：我写的 `pair_minima` 在空数组上先 reshape 再判空（`cannot reshape array of size 0`）。这是新工具的实现错误，按指令 7 修正工具后重跑通过；预期未改 |
| `test_preset_local_formation.py` | **4/4 ok**（第一次运行即通过） | 真实 `propose_and_build → _band_probe → build_band_query → loop_query → band_certificate/shape_lp`；横排、梯形（二分顺序 10, 3, 6.5, 4.75, 5.625，返回 4.75）、纵列、全空四种都与手算一致；全空单次 `candidate_rejected`/`patrol_region`，最终分类 `approx_empty`。附录第 3 节担心的二分顺序不一致**没有出现** |
| `test_preset_local_injection.py` | **3/3 ok**（第一次运行即通过） | 见 2.3 |
| `test_preset_local_stress.py` | 本部分运行时 ImportError（`run_separation_v15` 尚未实现）= 前提未完成，不算通过；第 6 部分实现后的结果见第 6 节 | |
| `test_preset_local_defaults.py` | 本部分 skip（未设 `V8_15_WORKER_SELECTION`）；skip 不计为通过；第 4 部分选定后的结果见第 4 节 | |

### 2.3 注入重做（P0-2）——**未触发**

`test_preset_local_injection.py` 用 V8-11 合成圆场景，只替换公共抽签装配、规划、优化与跟踪结果供给，以及三个非门禁遥测函数。`run_contract`、`run_attempts`、`attempt_chain`、`stitch`、`verify_segments`、`visible_track`、`check_validity`、`_attempt_summary`、`save_contract` 全部是生产原函数。

| 注入（attempt 0） | 底层代码 | 顶层 stage / reason / code | 重做 |
|---|---|---|---|
| 末帧采样间距 1 m | `validity.codes` 含 `separation_violation`（段核验通过） | `validity` / `validity` / `candidate_rejected` | attempt 1 保留 |
| 非目标设施 fac_b 警戒层内一点 | 段 verdict `failures` 含 `("b", "other_facilities_within_limit", "constraint_violation")` | `verify_segments` / `segment_verification` / `candidate_rejected` | attempt 1 保留 |
| 限制区圆心一点 | `validity.codes` 含 `constraint_violation`（段核验通过） | `validity` / `validity` / `candidate_rejected` | attempt 1 保留 |

三种注入都断言了以下几点：
- 干净夹具先独立通过冻结核验器（段核验全通过，validity 通过，最小间距 10 m）。
- 规划只被调用 attempt 0、1 两次。
- 两次 attempt 中 `verify_segments` 与 `check_validity` 各被调用 2 次：段核验失败时 validity 仍执行，随后优先返回段核验失败。
- 记录 `attempts=2`、`post_optimization_failures=1`、`skeleton_failures=0`、`unknown_attempts=0`。
- 落盘的 `result.json.attempt_log` 的 ok 序列为 `[False, True]`：失败历史保留。
- 两个成员的 `tracks/<m>/p.npy` 与内存保留结果都逐值等于独立干净轨迹。

### 2.4 已有套件回归（U D.6）

| 套件 | 本次 | 基线（REPORT14 C.2） |
|---|---|---|
| V8-14 numeric | 17/17 | 17/17 |
| V8-14 extra | 14/14 | 14/14 |
| V8-14 local_geometry | 1/1 | 1/1 |
| V8-13 numeric | 20/20 | 20/20 |
| V8-13 extra | 8/8 | 8/8 |
| V8-12 全目录 | 37 通过、2 失败、1 跳过 | 37/2/1 |
| V8-11 全目录（覆盖映射所在） | 30/30 | — |

V8-12 的两个失败和一个跳过，按**测试名与原因**逐项对照 V8-14 日志 [tests_v14c_impl.txt](../V8-14/v14c/tests_v14c_impl.txt)，完全相同：
- `test_preset_local_devset::test_registered_files_hash_and_read_only`：`root_text` 为 None，即未设 `V8_12_DATA_ROOT`。
- `test_preset_numpy_checkpoint::test_each_diagnostic_threshold`：`'frechet' not found in ()`，即"同条件中位数 19 < 场景间距 20"。这是 V8-12 期的既有疑似预期错误。
- 跳过的是 `test_own_part2::TestFieldOnRealScene`，原因"需要 V8_12_DATA_ROOT"。

**补充：设置数据根后重跑 V8-12**，日志 [part2/tests_part2_v812_data.txt](part2/tests_part2_v812_data.txt)。
- 环境变量：`V8_12_DATA_ROOT = F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData`（resolve 后同一路径）。`V812_DATA_ROOT` 未设，`test_own_part3` 用其代码默认值，即同一 SwarmData。
- 两个数据测试都只读输入、用系统临时缓存。
- 结果 39/40：devset 测试通过，跳过的真实场景测试通过；仍失败的只有上面 `frechet` 那一项，原因相同。

## 3. 第 3 部分：只读分析 full_v14c

### 3.1 运行与口径

- **入口与输出：** [analyze_separation_v15.py](../../../Multi-UAV%20SimpleGC/tools/v08/analyze_separation_v15.py)（恢复对象用 [v15_artifacts.py](../../../Multi-UAV%20SimpleGC/tools/v08/v15_artifacts.py)，距离与分位用 [v15_metrics.py](../../../Multi-UAV%20SimpleGC/tools/v08/v15_metrics.py)）。
  - 输出 `_handoff\2026-11-05_V8-15_separation\out\analysis\`，8 进程按族派发，墙钟 85.6 s。
  - 日志 `logs\part3_analysis.log`。
  - 仓库副本 [part3/](part3/)：summary、by_group.csv、失败 attempt 行、速度样例、图；`pairs.csv`（7.2 MB，70576 行）留外部，哈希见 [part3/external_hashes.json](part3/external_hashes.json)。
- **只读：** 输入是基线 `full_v14c` 的 JSON/NPY，以及从 V8-14 运行根按内容复制到本项运行根的缓存。缓存 259 个文件在分析前后 SHA256/大小/mtime 完全相同（`logs\cache_before_part3.json` / `cache_after_part3.json`）。基线不写回（第 8 节快照复核）。
- **口径：**
  - **优化：** `optimize_checks._frames` 帧（`hold_s` 读自 `physical_limits(load_settings())`），XY 水平距离。
  - **实测：** `visible_track` 后的真实整数 `tau_us` 共同帧，三维距离，含已存末端保持帧。
  - **插值：** 只在相差 100000 µs 的相邻共同帧之间计算，并按两成员全部阶段/掉头边界切小区间，逐小区间解析求最小。
- **恢复正确性的两项内部核对：**
  - 用恢复对象调用生产 `phase_diagnostics`，198/198 与已存 `phase_metrics` **逐字节相同**（规范 JSON 比较）。
  - 每合同实测采样全程最小值，198/198 与保留 attempt 已存的 `validity.min_separation_m` **精确相等**。
- **P0-1（附录裁定 1）：** 不重算段核验与 validity，直接引用 V8-14 的 e2e 结果 [tests_v14c_full.txt](../V8-14/v14c/tests_v14c_full.txt)（SHA256 `c9973f7a12c3323fdd30f2fc4d7d553c6f4734d464dca25325ea2c2ea71f784b`）。该文件中 `RUN_OUT = …\out\full_v14c`，`test_preset_local_e2e.py` 3/3 ok：`test_every_retained_contract_with_frozen_verifiers` 用冻结 V8-11 核验器逐段独立重算了全部保留合同。本项分析另行确认：历史字段 `retained_p0_ok` 198 真 / 0 假（只作对照）；保留合同实测间距最小值 3.097 m，远高于 2 m。**P0-1 未触发。**

### 3.2 三种间距（198 个保留合同）

- **合同数：** 198 个保留合同中，14 个只有 1 名成员（没有成员对），184 个合同共 2657 个成员对。
- **无共同帧：** 0 个成员对（`empty_pairs` 为空）。
- **统计单位：** 每个样本 = 一个合同中一个成员对在某分档的最小值，不按帧数加权。

| 距离来源 | 成员对全程最小值：min / p10 / 中位数 / p90 / max (m) | 合同级最小值：min / p10 / 中位数 / p90 / max (m) |
|---|---|---|
| 优化 XY 采样 | **3.171** / 3.852 / 19.81 / 63.64 / 191.4 | 3.171 / 3.249 / 5.334 / 18.16 / 26.00 |
| 实测三维采样 | **3.097** / 3.883 / 19.80 / 63.64 / 191.4 | 3.097 / 3.247 / 5.312 / 18.12 / 25.99 |
| 实测三维插值 | **3.097** / 3.872 / 19.80 / 63.64 / 191.4 | 3.097 / 3.240 / 5.301 / 18.12 / 25.99 |

- **诊断预期对照（指令 0.5）：**
  - 优化后最小 3.171 m ≥ 3.0 m，没有出现"硬检查未生效"的迹象。
  - 实测最小 3.097 m ≥ 历史推导 2.69 m。
  - 逐成员对比较，插值最小值从不高于采样最小值（2657 对中 0 对反向）。二者之差最大 0.153 m（o38_d2 uav_05|uav_06：采样 3.383 m，插值 3.230 m）；全体最小值处两者相等，都是 3.097 m。

**按实际队形 × 拓扑：**

| 队形 | 拓扑 | 有成员对的合同 | 成员对 | 优化 XY 最小 | 实测采样最小 | 实测插值最小 | 实测采样中位数 |
|---|---|---|---|---|---|---|---|
| abreast | loop | 48 | 650 | 3.233 | 3.096 | 3.096 | 29.02 |
| abreast | retrace | 54 | 976 | 3.171 | 3.169 | 3.135 | 12.35 |
| column | loop | 21 | 313 | 3.304 | 3.320 | 3.303 | 21.71 |
| column | retrace | 18 | 184 | 3.504 | 3.478 | 3.478 | 27.77 |
| echelon | loop | 19 | 178 | 3.319 | 3.339 | 3.338 | 31.81 |
| echelon | retrace | 24 | 356 | 3.240 | 3.169 | 3.169 | 24.93 |

**按阶段**（各来源的最小值，以及出现的合同与成员对）：

| 分档 | 优化 XY | 实测采样 | 实测插值 |
|---|---|---|---|
| 汇合/进入 | 3.233（o24_d0 uav_05\|uav_07） | 3.096（同） | 3.096（同） |
| 巡逻 | 3.171（o34_d2 uav_01\|uav_04） | 3.169（o03_d4 uav_01\|uav_06） | 3.135（o34_d2 uav_01\|uav_04） |
| ├ turn 子分档（与巡逻重叠） | 3.171 / 3.235 / 3.210（a / b / 两者） | 3.198 / 3.242 / 3.169 | 3.135 / 3.206 / 3.169 |
| 撤离 | 5.445（o05_d1 uav_03\|uav_06） | 5.448 | 5.448 |
| 保持 | 15.13 | 15.11 | 15.11 |
| 跨阶段（mixed） | ≥ 14.44 | ≥ 14.42 | ≥ 14.42 |

- **说明：** 最危险的时刻在汇合/进入与巡逻（含掉头）。跨阶段的成员对都在 14 m 以上。
- **完整分布：** 全部分档的 n/min/p10/median/p90/max 见 [part3/summary.json](part3/summary.json) `overall.*.by_bin`，按队形×拓扑×阶段×来源的完整表见 [part3/by_group.csv](part3/by_group.csv)。
- **最坏 10 例：** 三种来源各一组，见 `summary.json` 的 `worst10`。实测插值最坏的是 o24_d0 uav_05|uav_07，3.097 m，t = 371.4 s，abreast/loop。
- **图：** [part3/separation_by_phase.png](part3/separation_by_phase.png)。turn 与巡逻重叠，图中用橙色区分。

### 3.3 失败 attempt（全部 200 合同）

- **总量：** 200 合同共 396 个 attempt，其中失败 198 个。
- **按 stage/reason：** skeleton 145（入圈 71、出圈 16、整体掉头空集 16、起点路由与边界穿越其余）；`optimize_monitoring/optimize_residual` 49；`optimize/optimize_residual` 4。
- **底层代码：** `monitoring:nominal_dwell` 27、`nominal_revisit` 23、`boundary_crossing` 1；`physical:dynamic` 3、`separation` 3、`turn_radius` 1。
  - 注意 `reason="optimize_residual"` 是顶层 reason，不是 stage。
- **间距相关：**
  - `physical_failures` 含 `kind="separation"` 的 attempt 共 **3** 个（o08_d2、o36_d0、o36_d1）。其中只含间距的 0 个，与其他物理失败（dynamic 等）混合的 3 个。
  - `validity.codes` 含 `separation_violation` 的 attempt **0** 个，与历史预期 0 一致。
  - 优化阶段失败缺 `physical_failures` 字段的 attempt 有 0 个。
- **"最坏约束为间距"的精确计数：N/A。** `_attempt_summary` 没有保存 AL 的最大约束键和每轮违反量（指令 11.7）；不重新优化，也不拿不同单位的残差排序。

### 3.4 阶段最低速度最坏样例

- **选样：** 按已存 `phase_metrics` 选出 patrol 或 egress 中 `measured_ratio < 0.8` 或 `measured_along_max_m > 10` 的样例，共 **967** 个（成员×阶段）。
- **重算：** 用同一批"参考速度 ≥ 0.5 m/s"的帧重新求值。967/967 的速度比与沿迹最大值都与已存值**逐位相等**。
- **结果：** 无 moving 样本（N/A）0 个。

| 阶段 | 末尾 20 s 内 | 途中 |
|---|---|---|
| 撤离 egress | **945** | **1** |
| 巡逻 patrol | 0 | **21**（7 个合同：o03_d4、o11_d1、o17_d4、o22_d1、o22_d4、o25_d4、o34_d2） |

**指定两例（由数据得出）：**

| 样例 | 阶段区间 (s) | 最低速度时刻 / 距阶段末尾 | 参考 / 实测最低速度 | 速度比 | 沿迹最大偏离 | 归类 |
|---|---|---|---|---|---|---|
| o34_d2 uav_08 patrol | [1807.6, 4492.2) | 3236.1 s / 1256.1 s | 4.138 / 1.674 m/s | 0.4045（= 已存 0.404） | 25.70 m | **途中** |
| o08_d4 uav_02 egress | [1379.7, 1886.5] | 1488.3 s / 398.2 s | 0.621 / 0.0011 m/s | 0.00179（= 已存 0.0018） | 37.86 m（= 已存 37.9） | **途中** |

- **撤离：** 946 个撤离样例中 945 个的最低速度出现在阶段末尾 20 s 内，与"终点刹停时间对不齐"的解释一致。
- **o08_d4 uav_02：** 是唯一的撤离途中样例，在距撤离结束约 398 s 处几乎停住（0.0011 m/s）。不能归为终点刹停，交审查。
- 每条样例的位置、参考/优化/实测速度、沿迹最大值位置见 [part3/speed_cases.json](part3/speed_cases.json)。

**说明：** 开发时我在 `out\` 下留下过一个因脚本错误中断、只建了空目录的 `dev_analysis_try1`，已删除。另一个 3 合同自检目录 `dev_analysis_try2` 保留。两者都是本项新建的开发输出，不是基线或既有产物。

## 4. 第 4 部分：进程数扩展测试（8 / 16 / 24）

### 4.1 名单与协议

- **名单：** [part4/selection.json](part4/selection.json)，由 `run_separation_v15.py --mode workers --select-to` 生成。
  - 输入是基线 `records.json` 的 200 条 `_pool_task` `wall_s`，包含失败合同；`records.json` 的 SHA256 一并入库。
  - p20 = 42.58 s，p80 = 147.66 s，闭区间内候选 M = 120。
  - 按 (wall_s, order, draw, branch) 排序后取下标 ⌊k·119/39⌋，得到 40 个合同；名单内基线耗时合计 3070 s，没有失败合同落入名单。
- **运行：** 8、16、24 三档依次各跑一次，2026-11-05 05:13:51 → 05:30:07，三批不重叠，脚本 [part4/run_part4.sh](part4/run_part4.sh)。
  - 每批先对名单涉及的族 `prewarm_cache`（单列计时 3.6–4.1 s）。
  - 按 group_size × map_side_m 降序、再按业务键，生成八元组 `("full", entry, draw, None, …, inf)`，交给生产 `run_pool_singles`（spawn、单合同动态派发）。没有调用 `full_stage`，deadline = ∞。
  - 测量探针 `measured_pool_task` 是顶层函数，只在 `run_pool_singles` 调用期间临时绑定到 `joint_monitoring._pool_task`，`finally` 恢复；子进程调用的是未修改的 `_pool_task`。
- **缓存：** 三档前后缓存 259 个文件 SHA256/大小/mtime 完全相同（`logs\cache_before_part4.json` / `cache_after_part4.json`）。另外每档 worker 阶段前后的（大小, mtime）差异都为空。
- **硬件：** [part4/cpu_info.json](part4/cpu_info.json)：单插槽 AM5，AMD Ryzen 9 9950X3D，**16 物理核 / 32 逻辑处理器**；物理内存 63.65 GB（68,348,276,736 B）。

### 4.2 结果（逐合同配对：r = t_W / t_8）

| W | 完整配对 | P0-3 逐字节一致 | I_W = median r | p90 r | 吞吐量 S = W/I | 派发后墙钟 | 含预热墙钟 | 合同忙碌和 | 并行效率 | 全机已用内存采样峰值 | 派发前 / 结束时 | worker 峰值工作集（最大 / 合计） |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 40/40 | **40/40** | 1.000（自比） | 1.000 | 8.00 | 487 s | 493 s | 3515 s | 0.902 | **76.0%**（524 样本） | 67.1% / 68.8% | 0.88 / 6.1 GiB |
| 16 | 40/40 | **40/40** | 0.950 | 1.234 | 16.85 | 263 s | 269 s | 3636 s | 0.863 | **79.6%**（303 样本） | 69.3% / 39.9% | 0.81 / 10.5 GiB |
| 24 | 40/40 | **40/40** | 1.148 | 1.346 | 20.90 | 204 s | 209 s | 3949 s | 0.805 | **55.6%**（245 样本） | 40.3% / 39.7% | 0.79 / 13.6 GiB |

- **P0-3 未触发。** 120 次比较（3 档 × 40 合同）都在两个 `contracts/<同一 id>` 之间进行，文件集合与全部字节一致，排除清单为空。证据见 `part4/workers_*/comparisons.json`。
- **原始配对：** 40 行见 [part4/paired_wall.csv](part4/paired_wall.csv)；完整表见 [part4/part4_table.json](part4/part4_table.json)。
- **I_W 与总墙钟比不同：** I_W 用的是逐合同配对比值的中位数，没有用两批总墙钟之比。总墙钟比是 487/263 = 1.85、487/204 = 2.39，它们包含尾部与派发效应。
- **内存口径：** 全机已用 = total − available，1 s 采样外加派发前、每次完成、结束时的事件样本，用 psutil 7.0.0（环境原有，未安装）。
  - 这是**采样峰值**，不声称捕获了采样间的瞬时尖峰。
  - worker 峰值来自各进程结束前自报的 `PeakWorkingSetSize`，按 PID 取最大值。表中"合计"只用来说明 worker 自身的量级，**不是**全机峰值。

### 4.3 内存测量的混杂因素（如实记录，交审查）

8 档和 16 档运行期间，本机有一个用户进程 `PBZ`，工作集约 15.7 GB（占物理内存约 24%）。它不是本项启动的进程，我没有干预。它在 16 档运行期间退出：16 档派发前 69.3%，结束时 39.9%；24 档全程 40–56%。

所以 8、16 两档的峰值（76.0%、79.6%）主要来自这个外部进程；24 档的 55.6% 是在它不在时测得的。我按指令 4.2 的明确要求，60% 规则直接用实测量、不扣除其他进程。

### 4.4 选定值：**24**（[part4/worker_choice.json](part4/worker_choice.json)，[analyze_part4.py](part4/analyze_part4.py) 调 `v15_metrics.choose_workers`）

- 合格档必须同时满足：数据完整、P0-3 通过、峰值内存 ≤ 60%。结果只有 24 合格；8、16 因内存（`memory_over_60pct`）落选。
- 在合格档中取 S 最大，即 24。
- 16 不合格，所以"24 相对 16 增益 < 10% 时取 16"不适用。即使 16 合格，S24/S16 = 20.90/16.85 = 1.240 ≥ 1.10，也不会触发。
- **结论的稳健性：** "选 24 而不选 8 或 16"不依赖 8、16 档的内存结论。但 24 档本身是否"内存合格"依赖 PBZ 当时不在。如果 PBZ 一类 15–16 GB 的进程与 24 进程批次同时运行，按 24 档的 worker 合计 13.6 GiB 加 PBZ 估算会超过 60%。这一点交审查判断；它不是停止条件。
- **物理核：** 24 > 16 物理核，24 进程依赖 SMT；I_24 = 1.148，表示同一合同在 24 进程下平均慢约 15%。

**全量墙钟预测（只写报告，不跑全量）：** T = 28273 × I_W / (W × 0.9)。
- 28273 s 是 V8-14c 全量（200 + 多样性 100）四个环节 `perf_counter` 墙钟之和，原报告称"CPU"，这里沿用该口径；本项没有测进程 CPU 时间。
- 选定 W = 24 时 T ≈ **1503 s（约 25 分钟）**。对照：W = 16 时 1865 s，W = 8 时 3927 s；V8-14c 实测为 8 进程 4765 s。
- 这 40 个是中等耗时合同，它们的膨胀比不能证明长尾合同也同比例。V8-14c 全量的尾部损失主要来自少数 500 s 以上的合同，预测可能偏乐观。
- 第 8 档超过 20 分钟的情形（附录裁定 4.1）没有出现：8 档派发后 487 s。

### 4.5 默认值联动（提交 ae7766d；属于生产模块改动，P0-4 门禁见第 7 节）

- **新增** `v08/runner/runtime_defaults.py`：只有 `DEFAULT_WORKERS = 24`，注释写明测量提交 52f3915、名单、选择结果与性能表路径；不含任何算法参数。
- **全部引用：** `git grep -n -E "workers|DEFAULT_WORKERS|--workers"` 的结果见 [part4/workers_references.txt](part4/workers_references.txt)，共 118 行，覆盖代码、测试、README、RUNNING。

| 位置 | 处理 | 分类 |
|---|---|---|
| `tools/v08/run_joint_monitoring.py` parser `--workers` 原 `default=1` | 改为 `DEFAULT_WORKERS`；用法说明加注 quick/rerun 仍单进程 | 修改 |
| `tools/v08/run_skeleton_monitoring.py` parser 原 `default=8` | 改为 `DEFAULT_WORKERS`；文件头示例不再写死 8 | 修改 |
| `joint_monitoring.run_batch(workers=8)` | 默认改为 `DEFAULT_WORKERS`；函数仍串行、不使用该参数（行为不变） | 修改 |
| `skeleton_monitoring.run_skeleton_batch(workers=8)` | 默认改为 `DEFAULT_WORKERS`；族级派发不变 | 修改 |
| `joint_monitoring.cli` quick 分支 `run_batch(..., workers=1)` | 不改（指令 4.3、附录裁定 4.2） | 历史保留 |
| `rerun_stage` 的 `"workers_source": 8, "workers_repeat": 1` | 不改：这是历史复跑事实 | 历史保留 |
| `full_stage(workers)`、`run_pool`/`run_pool_singles(workers)` | 只接收调用方传入的值，无默认 | 不涉及 |
| `tools/v08/run_separation_v15.py --workers` | 未给时读 `DEFAULT_WORKERS`；第 4 部分三档显式传 8/16/24 | 显式实验值 / 新入口默认 |
| `profile_monitoring_v15.py` | 单进程，不受默认值影响 | 显式实验值 |
| V8-13/V8-14 既有测试 | 没有任何 `workers` 引用，与指令 4.3 的 GitHub 搜索结论一致；V8-13 `test_preset_local_reproduction.py` 与历史 `rerun_reproduction.json` 的 8/1 不改 | 历史保留 |
| `Multi-UAV SimpleGC/README.md`、[RUNNING.md](RUNNING.md) | README 头部新增 v0.8 默认值说明；RUNNING 写实际默认值、来源、旧 quick 串行例外、名单快速命令、单进程 profile/rerun、日常小批量规则 | 修改（文档） |

- **预置测试** `test_preset_local_defaults.py`（设置 `V8_15_WORKER_SELECTION` 指向 [part4/worker_choice.json](part4/worker_choice.json)）**2/2 ok**。
  - `DEFAULT_WORKERS`、`run_batch`/`run_skeleton_batch` 的签名默认值、新入口解析默认值都等于 24。
  - 两个旧 CLI 不带 `--workers` 时传给 `cli` 的是 24，显式 `--workers 1` 能覆盖。

## 5. 第 5 部分：完整链路剖析（附录裁定 3：cProfile 与行级计时分两次运行）

入口 [profile_monitoring_v15.py](../../../Multi-UAV%20SimpleGC/tools/v08/profile_monitoring_v15.py)；汇总 [part5/summary.json](part5/summary.json)，四阶段双 Top25 见 [part5/top25.md](part5/top25.md)。
- 外部原始文件在 `_handoff\2026-11-05_V8-15_separation\out\{profile,profile_line}\<合同>\`：五个阶段 `.prof`、`merged.prof`、`result.json` 与复跑合同目录。各 `.prof` 的 SHA256 记在 summary 的 `prof_sha256`。
- **每个合同一个独立子进程**，峰值工作集即该合同的进程峰值。
- 剖析期间没有其他重计算在运行。
- **剖析合同的输出与基线逐字节一致**：cProfile 4/4、行级 2/2。说明探针没有改变计算。

### 5.1 选样（[part5/selection.json](part5/selection.json)）

- **四个合同：**
  - `skeleton_s` 最大：o23_d4（失败合同，20 attempt）。
  - `optimize_s` 最大且未选：o35_d3。
  - |wall_s − 中位数 68.552 s| 最小的两个：o05_d3、o16_d3。
- **附录裁定 3 估算：** Σ wall_s × 2 = 2514 s ≤ 90 分钟，**不替换**。
- **行级运行：** 两个中位数合同 o05_d3、o16_d3，单合同上限 = 6 × 基线 wall_s（约 410 s），总上限 40 分钟。
- **最贵合同**（选样前基线 wall_s 最大）：o23_d4。

### 5.2 cProfile 运行（2026-11-05 05:36:32 → 05:53:45）

| 合同 | 基线 wall（8 进程全量中） | 剖析 wall | 骨架 | 优化 | 仿真 | 核验 | 编排 | 峰值工作集 |
|---|---|---|---|---|---|---|---|---|
| o23_d4（失败，20 attempt，4 次进入优化） | 572.0 s | 453.7 s | 317.4 | 136.1 | 0 | 0 | 0.07 | 0.64 GiB |
| o35_d3（成功，8 attempt，7 次优化） | 547.8 s | 447.9 s | 161.6 | 241.6 | 35.5 | 5.9 | 3.2 | 1.43 GiB |
| o05_d3（成功，2 attempt） | 68.4 s | 60.7 s | 8.8 | 18.6 | 27.7 | 2.6 | 3.1 | 0.53 GiB |
| o16_d3（成功，1 attempt） | 68.7 s | 67.3 s | 9.5 | 17.1 | 36.6 | 1.8 | 2.1 | 0.46 GiB |

- **互斥口径：** 五个作用域墙钟都是互斥的，加和等于剖析墙钟（例如 o05_d3：60.65 s 对 60.73 s）。
- **剖析比基线快：** 基线是 8 进程全量中的值，有并行争用；剖析是单进程。剖析数字只用来排序与看占比，不用于第 4 部分的膨胀比或压力预算。
- **"CPU"口径：** 本项没有测进程 CPU 时间。

**骨架细项**（按固定源码定位；cumtime 有包含关系，不能相加）：

| 项 | o23_d4 | o35_d3 | o05_d3 | o16_d3 |
|---|---|---|---|---|
| `monitoring_turn.sample_joint_turn`（整体掉头） | 33 次 / 215.1 s | 8 次 / 55.5 s | 未调用（环绕） | 未调用 |
| 其中 `_points_ok` | 9234 次 / 89.9 s | — | — | — |
| `lp_feasible_pairs` / `_arc_feasible`（折返单调扫描） | 20 / 0.75 s；20 / 0.58 s | 3 / 0.00 s；未调用 | — | — |
| `shape_lp`（构造+求解） | 40 次 / 0.85 s | 16 / 0.76 s | 4 / 0.43 s | 2 / 0.40 s |
| `linprog`（来自 shape_lp） | 0.40 s | 0.25 s | 0.08 s | 0.04 s |
| LP 构造独占 = shape_lp − 其调用的 linprog | 0.45 s | 0.51 s | 0.35 s | 0.36 s |
| `_lp_basis` 调用 / 未命中（新进程首次） | 40 / 1 | 16 / 1 | 4 / 1 | 2 / 1 |
| `BandGeometry.__init__`（含 `radial_margins`） | 20 次 / 20.5 s | 8 / 10.8 s | 2 / 0.9 s | 1 / 1.0 s |
| `scene.exact.signed_distance` | 261817 次 / 149.7 s | 45106 / 37.4 s | 2605 / 0.46 s | 195 / 0.36 s |
| `scene.exact.clearance_values` | 245888 / 141.3 s | 42752 / 35.3 s | 96 / 0.33 s | 36 / 0.26 s |
| `scene.exact.polyline_clearance` | 190364 / 84.9 s | 33596 / 38.4 s | 80 / 0.23 s | 27 / 0.13 s |
| `scene.exact.chord_sdf_range` | 17117 / 50.2 s | 5227 / 28.9 s | 36 / 1.0 s | 15 / 1.1 s |
| 其中 `scene.exact._poly_sdf` 独占（tottime） | 92.3 s | — | — | — |

- **长尾在整体掉头：** 骨架最贵合同的骨架时间中，约 68%（215/317 s）在 `sample_joint_turn` 内，其下又以精确场景距离查询（`_poly_sdf`、`signed_distance`、`clearance_values`）为主。
- **LP 很便宜：** 曲率 LP 本身（构造 + 求解）全部不到 1 s。
- **折返单调扫描**（`lp_feasible_pairs`）在这四个合同中都不到 1 s。

**优化细项：**

| 项 | o23_d4 | o35_d3 | o05_d3 | o16_d3 |
|---|---|---|---|---|
| `optimize_segment` 调用（= 实际进入优化的 attempt） | 4 | 7 | 1 | 1 |
| `Prepared.value_grad` 实际调用（全部） | 1001 | 1910 | 261 | 361 |
| 　其中 L-BFGS 回调（经 `_compute_if_needed`） / `terms=True` 诊断 | 997 / 4 | 1903 / 7 | 260 / 1 | 360 / 1 |
| 　各轮 nfev 之和 | 997 | 1903 | 260 | 360 |
| value_grad 平均累计耗时 | 55.2 ms | 69.2 ms | 51.4 ms | 34.9 ms |
| `_blocks` 调用：来自 value_grad / 来自 constraint_values | 1001 / 8 | 1910 / 14 | 261 / 2 | 361 / 2 |
| `solve_joint` 累计 | 64.9 s | 151.3 s | 14.9 s | 14.0 s |
| `check_monitoring`（优化后语义硬检查）累计 | 61.6 s | 67.8 s | 2.9 s | 2.2 s |
| `check_physical` 累计 | 5.5 s | 10.0 s | 0.43 s | 0.31 s |

- **调用次数：** L-BFGS 回调次数恰好等于各轮 nfev 之和。其余调用全部是每次求解后一次 `terms=True` 诊断，不是用 nfev 推算出来的。
- **两个贵合同的硬检查占比：** o23_d4、o35_d3 中，`check_monitoring` 占优化阶段约 45% 与 28%。o35_d3 的 optimize 阶段 tottime 第一名是 `nominal_checks.revisit`，56 次共 52.4 s 独占；第二名是 `Prepared.geo.eval`（optimize.py:299），61792 次共 44.9 s 独占。

**AL 外循环：** 全部 13 次 `solve_joint`（4 + 7 + 1 + 1）都只用了 **1 个外轮**，第一轮硬检查即通过；o23_d4 的失败来自其他阶段，不是 AL 未收敛。
- 13 次中 9 次内层 `nit = 200`，即 `STOP: TOTAL NO. of ITERATIONS REACHED LIMIT`；其余 4 次是 `CONVERGENCE: REL_REDUCTION_OF_F_<=_FACTR`。
- 每轮的 nit/nfev/message/scipy_success/rho/value/max_violation/hard_passed/硬失败类别见 summary 的 `al`。完整 diagnostics（除两组控制点数组外的全部键）在外部 `result.json`。

### 5.3 行级计时运行（附录裁定 3；2026-11-05 05:53:45 → 05:55:30）

- **安装范围：** `sys.settrace` 只在 `optimize_segment` 内安装、`finally` 卸载；只对 `Prepared._blocks` 与 `Prepared.value_grad` 两个 code 对象产生行事件。
- **行号映射：** 运行时用语句文本锚点生成，与固定提交行号**零漂移**：_blocks 共享 ≤648、动力学 649–715、几何 716–726、间距 727–742；value_grad 的 `_blocks` 调用在 779，AL 累计在 782–792 并按当前 `k[0]` 归类。
- **扣除与核对：** 嵌套 `_blocks` 的时长从父间隔扣除。各类别都非负，加和等于 value_grad 调用总时长：差值分别为 0 与 −1.8e−15 s。
- **开销：** 每个事件约 170 ns，结果中**未扣除**。

| 合同 | 运行 wall / 基线 | 优化（跟踪中）墙钟 | 部分采样 | 行事件 | value_grad 调用（lbfgs / terms） | value_grad 总时长 |
|---|---|---|---|---|---|---|
| o05_d3 | 50.6 s / 68.4 s | 20.9 s | 否（上限 410 s） | 503,591 | 260 / 1 | 15.38 s |
| o16_d3 | 52.1 s / 68.7 s | 18.4 s | 否（上限 412 s） | 200,042 | 360 / 1 | 13.71 s |

**value_grad 时间的可归属占比**：直接归属 / 上界 = 直接 + 共享。共享包括 P/V/A/J 求值、`for` 头、联合梯度投影 804–805、预条件等，不拆分。

| 合同 | 间距 sep | 几何 geo | 动力学 v/t/n/j/turn | 共享 shared |
|---|---|---|---|---|
| o05_d3 | **14.6%**（上界 38.5%） | 42.3%（上界 66.2%） | 19.2%（上界 43.2%） | 23.9% |
| o16_d3 | **4.5%**（上界 29.8%） | 49.7%（上界 74.9%） | 20.5%（上界 45.8%） | 25.3% |

- **"间距项占比"的口径：** 在这两个中位数合同中，可直接归属到间距约束的时间占 value_grad 的 4.5–14.6%，上界 30–39%。
- **几何项是最大的直接归属类别。**
- 由 `constraint_values` 触发的 `_blocks` 另行统计（0.05–0.08 s），不进 value_grad 的分子分母。
- 以上占比只来自行级运行（裁定 3.3），不由约束个数推算。

**本节不提出、也不实施任何提速方案**（U D.4.4）。

## 6. 第 6 部分：压力合同集（2026-11-05 05:58 → 07:48）

**结论：** 36 个压力合同全部执行到完整链路。骨架 36/36 成功，完整链路 **33/36 成功**；3 个失败都是 20 次预算用尽（`budget_exhausted`），集中在 o17 的 abreast/echelon。33 个保留合同的冻结核验（V8-13 e2e 方法）全部通过，validity 33/33 一致，**P0-1 未触发**。退让成功样例 0 个。余量批次首跑被我按用户"先暂停"要求中断，重跑写入新目录 `rest_r2`；中断前完成的 6 个合同与重跑逐字节一致。

证据：[part6/summary.json](part6/summary.json)、[contracts.csv](part6/contracts.csv)、[by_bucket.csv](part6/by_bucket.csv)、[stress_selection.json](part6/stress_selection.json)、[checkpoint_plan.json](part6/checkpoint_plan.json)、[rest_plan.json](part6/rest_plan.json)、两份间距分析摘要、[stress_e2e.log](part6/stress_e2e.log)、[stress_rest_r2.log](part6/stress_rest_r2.log)，汇总脚本 [make_part6.py](part6/make_part6.py)。外部运行根 `out/stress_v15/{skeleton,checkpoint,rest(中断),rest_r2,analysis_checkpoint,analysis_rest}`。

### 6.1 名单（指令 6.1）

- 排序 `(-vehicle_count, 窄带最小宽度升序, order)`。窄带用 `BandGeometry` 360 行 × 2 m 径向网格与完整 base+patrol 约束，每行取最长原始区间，取 360 行最小宽度。40 族全部记录在 `stress_selection.json` 的 `families`。
- 前 6：o17（12 机，264 m）、o11（12 机，390 m）、o34（12 机，412 m）、o28（11 机，162 m）、o31（11 机，230 m）、o37（11 机，238 m）。**选中 [17, 11, 34, 28]**。
- 36 = 4 族 × {abreast, column, echelon} × branch {0,1,2}，公共 draw 固定 0。组 ID `stress_v15/<g0>/<prior>`，合同 ID `stress_o<order>_<prior>_s<seed>`。名单在首次运行前落盘。

### 6.2 三步执行与预算（指令 6.3）

| 步骤 | 合同 | 进程 | 调度墙钟 | 结果 | 全机内存峰值（起始） |
|---|---|---|---|---|---|
| 只骨架 | 36 | 24 | 470 s | 36/36 成功；attempts 1×20、2×5、3×2、4×2、5/7/8/10/11/15/16 各 1；单合同墙钟中位 53 s、最大 436 s | 55.4%（42.2%） |
| 检查点（每倾向首个骨架成功，按 (order,seed)） | 3：o11 abreast/column/echelon s0 | 3 | 207 s | 3/3 成功，均 1 次 attempt；T_f = 206/172/200 s | 66.6%（43.7%）※ |
| 余量（首跑，**中断**） | 6/33 完成 | 24 | — | 未写 records/summary，保留不动 | — |
| 余量重跑 `rest_r2` | 33 | 24 | **1300 s** | 30/33 成功 | 66.1%（40.0%）※ |

- **预算估计：** \(\widehat T_R = 294.6\) s（Σ=6363 s，W*=24，max=206 s），≤ 3600 s，不缩减，全部 33 个继续。
- **实测：** 调度墙钟 1300 s，是估计的 **4.4 倍**，但仍在 3600 s 内。原因是检查点都取自最快的 o11 族、且都是 1 次 attempt 成功；余量中有多次重做的长尾（o34_abreast_s0 12 次 attempt、1299 s，决定了调度墙钟）。这正是指令 6.3 所说"少量检查点不能保证长尾的预测精度"。
- ※ **内存（如实记录，交审查）：**
  - 检查点只有 3 个进程，各自峰值工作集 ≤ 1.06 GiB，合计 ≤ 3.2 GiB，但全机从 43.7% 涨到 66.6%，结束时仍为 62.6%。增量主要来自本项以外的进程。
  - `rest_r2` 单合同峰值工作集中位 1.10 GiB、最大 2.83 GiB，前 24 个峰值之和 30.0 GiB（假设同时达到峰值时的上界）。全机实测峰值 66.1%，起始 40.0%。
  - 结论：12 机合同在 24 进程下，**全机已用内存峰值超过第 4 部分 60% 的选定条件**，且这台机器空闲时已用约 27 GB。第 4 部分的 40 个合同是普通规模，这里是压力规模。此项不属于四条停止条件，不改已选默认值，交审查方判断是否需要对大机数合同另设进程上限。
- **中断首跑：** 中断前完成的 6 个合同（o11_abreast_s1、o11_column_s1、o17_abreast_s2、o17_column_s0、o17_column_s1、o17_echelon_s2）与 `rest_r2` 同名目录逐文件逐字节一致（各 64 个文件，`differing` 为空，见 summary 的 `interrupted_first_rest`）。

### 6.3 结果（按 (族, 倾向, 实际队形, 实际拓扑) 分档见 [by_bucket.csv](part6/by_bucket.csv)）

| 族 | 机数 | abreast | column | echelon | 合计 |
|---|---|---|---|---|---|
| o17 | 12 | **1/3** | 3/3 | **2/3** | 6/9 |
| o11 | 12 | 3/3 | 3/3 | 3/3 | 9/9 |
| o34 | 12 | 3/3 | 3/3 | 3/3 | 9/9 |
| o28 | 11 | 3/3 | 3/3 | 3/3 | 9/9 |

- **实际队形：** 全部成功合同都等于倾向，没有退让（实际队形 ≠ mapped_start 的成功合同 0 个，退让 attempt 0 个，骨架与完整链路都是 0）。
- **拓扑：** loop 与 retrace 都出现，逐档计数见 CSV。
- **完整链路 attempts：** 排序后为 1×13、2×7、3×3，以及 4、5、6、7、8、9、12、13、15、15、20、20、20 各一。单合同墙钟中位 359 s，最大 1299 s，36 个合计 15,959 s。
- **失败 attempt：** `rest_r2` 30 个保留合同加 3 个失败合同共 187 次 attempt，其中失败 157 次。
  - **骨架 127 次：** "没有可用的……"（成员起点路由、入圈/出圈直线等）88、`turn_joint_set_empty` 26、边界穿越 10、其他 3。
  - **优化 30 次：** `optimize_monitoring/optimize_residual` 29、`optimize/optimize_residual` 1。
  - **底层代码：** `monitoring:nominal_dwell` 20、`nominal_revisit` 8、`boundary_crossing` 5、`physical:turn_radius` 1。
  - 含物理间距失败的 attempt **0**，validity `separation_violation` **0**。检查点 3 个合同没有失败 attempt。
- **三个失败合同：**
  - **o17_abreast_s0：** 骨架失败 17 次，优化失败 3 次。
  - **o17_abreast_s1：** 骨架失败 19 次，优化失败 1 次。
  - **o17_echelon_s1：** 骨架失败 19 次，优化失败 1 次。
  - 三者的失败阶段都包含 ingress、turns，以及 start_route 或 egress。只骨架模式里这三个合同分别在第 4、11、16 次成功，但完整链路中那一次 attempt 的优化失败了，之后的 attempt 骨架又都失败，最终用尽 20 次。
- **确定性旁证：** 36/36 合同中，完整链路第一个越过骨架的 attempt 序号与只骨架模式的成功 attempt 序号相同。

### 6.4 间距（第 3 节同口径；33 个保留合同，2079 对）

| 指标 | 最小 | p10 | 中位 | p90 | 最大 |
|---|---|---|---|---|---|
| 优化 XY | 3.228 | 5.70 | 30.93 | 77.72 | 213.19 |
| 实测三维采样 | **3.130** | 5.67 | 30.90 | 77.72 | 213.19 |
| 实测相邻帧插值 | **3.130** | 5.67 | 30.90 | 77.72 | 213.19 |

- **最坏 5 例**（实测采样）：o28_echelon_s2 uav_06|uav_11 3.130 m（t=1766.4 s）、o28_echelon_s2 uav_06|uav_09 3.205 m、o17_echelon_s0 uav_01|uav_08 3.207 m、o28_echelon_s2 uav_09|uav_11 3.208 m、o34_abreast_s2 uav_02|uav_03 3.213 m，全部为 retrace 拓扑。
- 实测最小值都在巡逻阶段（`phase:patrol` min 3.130 m）。
- 与 full_v14c 对照：实测 3.097 m、优化 3.171 m；压力集分别为 3.130 m、3.228 m。全部 ≥ 2 m。分档明细见两份 analysis 摘要的 `overall.by_bin`，共同帧范围见 `pairs.csv`（外部）。
- **最低速度样例：** 撤离末 20 s 349 个；巡逻中途 4 个，都在 o28_abreast_s1（uav_02/05/06/10，实测最低约 3.95 m/s，为参考 4.06 m/s 的 0.973–0.975），属于沿航迹滞后的轻度降速，不是停住。

### 6.5 图（固定规则选取）

- **最拥挤成功**：[fig_crowded_success.png](part6/fig_crowded_success.png)，`stress_o17_echelon_s0`。12 机，在 12 机族中实测最小间距最小；保留 attempt 14，echelon、retrace，实测采样最小 3.207 m（uav_01|uav_08，t=1417.6 s，图中 ×）。turn 子区间橙色，与普通巡逻（绿）分色。11 机的 o28_echelon_s2（3.130 m）按"全员数降序"排在其后。
- **退让成功**：无此类样例（成功 33 个中实际队形 ≠ mapped_start 的 0 个）。未注入、未凑图。
- **失败**：[fig_failure.png](part6/fig_failure.png)，`stress_o17_abreast_s0`，即业务键最小的失败合同。最后一次 attempt 19 在骨架 start_route 阶段失败（uav_02 无可用起点路由），没有 failure_witness 曲线，也没有实测轨迹。图中给出能拿到的几何：目标 warning/alert 层、其他设施 alert、全员初始位置、最后一次 attempt 的抽签圆（ρ0=650 m，abreast/retrace，K=4），标题列出 20 次失败的阶段计数。

### 6.6 冻结核验与分析一致性

- V8-13 `test_every_retained_contract_with_frozen_verifiers` 分别以 `V8_13_RUN_OUT=.../checkpoint/run`（3 个）与 `.../rest_r2/run`（30 个）运行，均 **OK**，日志 [stress_e2e.log](part6/stress_e2e.log)。
- 环境变量：`V8_13_DATA_ROOT=SwarmData`、`V8_13_TEST_CACHE=<运行根>/cache`、`V8_13_DEVSET=docs/v08/V8-03/devset_v08.json`、`PYTHONPATH` 加入测试目录。
- 同文件另外两个方法依赖 quick/full 的计数布局，与压力目录不兼容，未运行（附录裁定 1）。
- 间距分析：validity 一致 3/3 与 30/30；阶段指标复算 30/30；空集合 0。

**本部分发现的工具问题：**
- `make_part6.py` 初版按 shapely 对象画圈层，但 `Facility.layers` 实际是几何字典（Circle/Polygon/BufferedPolygon），两张图因此漏画目标层；失败图初版只有空坐标轴。
- 已改为按字典绘制，并加入最后一次 attempt 的抽签几何后重新生成。只影响作图，不影响任何数值。
