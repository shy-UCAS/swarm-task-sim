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
  - 插值最小值没有低于采样最小值超过 0.04 m：最大的差在 o34_d2 uav_01|uav_04，插值 3.135 m，采样 3.169 m 那一档。

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
