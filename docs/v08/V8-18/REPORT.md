# V8-18 佯动单段：执行报告

> **2026-11-08 接续状态：** Codex 从本地/远端一致的 `4da418298fe42d66fcbecd166cb782868d19b575` 接续。最新《预建改为按需判空裁定》取代全格预建、45 分钟外推与 90 分钟预建上限；生产改用 shape 流排列廉价入口候选格、按需取首个非空格。第 1–12 节为前两次执行的历史证据，当前实现、测试与检查点见第 13 节。

> 执行方：Claude Code（模型 Opus 5.5，`claude-opus-5-5`）。基线 `6dba0bc0a3813b6241fafb4c2b4f2d54a8e669b3`（dev/v0.8），审查分支 `review/v08/V8-18-feint`。
> 依据：`_handoff\2026-11-06_V8-18_feint\V8-18_佯动单段_执行指令_20261106.md`（以下称"指令"，SHA256 `59744c24…7c30`）和 `V8-18_GPT指令评价与裁定_20261107.md`（以下称"附录"）。两者冲突时以附录为准。
> 本报告逐部分如实填写"完成 / 失败 / 未执行"。证据等级分三档："代码已写"、"有记录"（执行方第一次运行）、"已复跑"（审查方独立复跑）。

## 0. 开工复述

### 0.1 范围（指令第 1 部分要求的开工复述）

- **固定提交：** 代码基线固定为 `6dba0bc`（dev/v0.8），用显式 refspec 获取，不随远端漂移。
- **只做第 0 编组的单段佯动：** 从圈外开始、作为最后一段。公共抽签与监视/过境/突入同键，只把唯一 TaskSpec 的 intent 换成 `feint`。入口沿用突入/过境，整体掉头调用监视数值构件（`monitoring_turn.py`），出口沿用过境终点口径。不做圈内切换、出口弯曲、终端压缩、其他意图、多段，也不改优化器求解形式。
- **三意图两轮字节门禁：** 第 2 部分、第 4 部分各跑一次监视、过境、突入的 20 合同快批，分别与 `full_v14c`、`full_transit_r2`、V8-17 `full_r1` 同键逐合同递归比较文件集合与原始 bytes，排除清单 `[]`。共 3×2×20。
- **唯一 20 次 attempt 预算：** 由现有 `run_attempts`（`joint_monitoring.BUDGET`）管理。不加骨架间距拒绝、1800 s 时长拒绝、搜索次数上限、失败后换格/换队形、优化器外的重试。集合预建、组合查询、队形 probe 不计 attempt。
- **先求集合，后抽样：** 每格先在完整有限网格上求"存在一个完整可行掉头"的存在性证明（预建只存存在性，不把首个可行证明当生产抽样结果）；生产时按 formation → 格 → 组合 permutation → 非空组合等概率 → 相容 \(D_c\)、K、logit 分位数 → 路由 → 速度的固定 RNG 顺序抽样。
- **MT 只读：** `v08/motion/monitoring_turn.py` 只可调用，不得修改；整个文件散列登记在冻结快照中，首尾核对。
- **无不可行排除名单：** 佯动预登记不可行名单为空。`o17_d1`、`o17_d4` 正常计数并单列；突入的 `o34_d3` 证书不迁移到佯动。
- **第 12 节两处疑点：** 指令第 12.1 节（负下界拒绝与精确等价冲突）、第 12.2 节（A/种类边缘分布）在指令下发时尚待裁定；附录裁定 1、裁定 2 已对两者作出正式裁定（见 0.4）。

### 0.2 八个部分

| 部分 | 内容 | 验收 |
|---|---|---|
| 1 | 分支、输入/名单登记、冻结快照（含整个 MT）、旧测试基线、预置测试原样落盘与散列 | 文件齐全，散列可核对；不宣称新代码已通过测试 |
| 2 | `turns_from_skeleton` 掉头表进入优化外层；feint 合同与分派；第一轮三意图字节门禁 | 掉头映射测试；三意图各 20/20 逐字节一致 |
| 3 | 佯动可行集合（入口格、A/R 网格、整体掉头完整认证）、抽样、入口 LP、距离场粗筛（`screened`）与等价门禁、裁定 3 剪枝 | 完整集合/抽样/装配、解析预置测试、单格查询、粗筛对照差异 0 |
| 4 | `check_feint`、`screen_feint_member`、实测保留前两层 1/1 门禁、白名单保存、测试；第二轮三意图字节门禁 | 预置/自加测试日志、冻结快照不变、三意图各 20/20、保存后实测复核 |
| 5 | 裁定 3(c) 成本检查点（前 5 族预建外推）后，200 合同只骨架（24 进程），止损检查点 | 成功率 ≥95%、人数档差 ≤10 个百分点、成功合同 attempts 中位数 ≤1、形状复核失败率 ≤5% |
| 6 | 20 合同全链路快批（24 进程），止损检查点 | 成功 ≥16/20、成功合同进入优化后失败中位数 ≤0、优化耗时中位数 ≤60 s、保留 P0 违规 0 |
| 7 | 200＋100 全量、5 合同单进程复跑、四意图配对与诊断 | 主批成功率 ≥80%、各档差 ≤20 个百分点、post 中位数 ≤0、作业段 Fréchet 合并中位数 ≥1；复跑 5/5 逐字节一致 |
| 8 | 报告、RUNNING、快照、提交、推送审查分支 | 远端 SHA 与本地一致 |

每部分单独提交。第 3 部分的等价门禁、裁定 3 的成本检查点，以及第 5、6、7 部分开始前的快速检查和止损检查点，任一项不达标就停在该检查点，提交、推送当前版本，然后汇报，不继续跑后面的批次。

### 0.3 三条停止条件（P0，指令 0.4 / U F.1）

1. **任一旧意图快批不逐字节一致：** 监视、过境、突入 × 两轮 × 20 同键合同，递归比较全部文件（含失败合同、JSON、NPY），排除清单 `[]`。
2. **保留结果违规：** 只看保留尝试及其全部成员。实测间距、限制区、圈层任一违规，段核验与落盘不一致，或实测预警、警戒进入次数不是 1/1。被正确拒绝的普通失败不算。
3. **单进程复跑不一致：** 预登记 5 键（`o01_d0`–`o01_d4`）1 进程复跑与 24 进程输出逐字节比较，失败键也不替换。

触发任一条：立即停下，保存证据，提交并推送当前版本，然后汇报，**不自行修复后重跑**。成功率、计算成本、多样性等属于第 5–7 部分止损检查点，不升级为 P0；粗筛等价是算法验收前提，不另列为 P0。

### 0.4 附录五条裁定

1. **裁定 1：粗筛采用 `screened` 模式（两头确定、中间精确），不实现 `upper_literal`。**
   - 在实际成员折线上按 ≤5 m 弧长取覆盖点（保留事件端点），覆盖半径 \(q=2.5\) m。下界 \(\ell(p)=\hat c(p)-\varepsilon_f\)（即现有 `lower_clearance`），上界 \(u(p)=\hat c(p)+\varepsilon_f\)，\(\varepsilon_f=\sqrt{50}/2\)。
   - \(\ell(p)\ge q\)：该点覆盖的折线段直接通过；\(u(p)<0\)（\(p\) 在折线上）：整个候选直接拒绝；其他：对覆盖段调用精确 `polyline_clearance`。两种直接判定都可靠，`screened` 与 `exact` 按构造逐个相同。
   - 等价门禁仍保留，用于检查实现错误；差异必须为 0，否则停在第 3 部分检查点汇报。
   - **授权修改两处预置断言（其余预置测试不动）：** ① `test_preset_numeric_v18.py::test_negative_lower_bound_is_not_infeasibility` 最后一行改为 `self.assertTrue(clearance_passes(cons, xy, mode="screened", field=field))`，注释改为"负下界不是不可行，`screened` 交给精确判定"；② `test_preset_local_geometry_v18.py::test_all_candidates_coarse_equals_exact` 的 `mode="upper_literal"` 改为 `mode="screened"`。两份文件修改前后的 SHA256 都登记，diff 贴在本报告并注明"依裁定 1"。缓存身份记录 `screened` 模式与新版本号。
2. **裁定 2：抽样分布按监视协议，** 格均匀 → 非空（种类×侧向）组合等概率 → 组合内可行 \((A,R)\) 记录均匀；不要求 A 或种类的边缘分布严格均匀。报告把 A（或最深点到保护边界的距离）与种类的实测分布列为诊断，不声称严格均匀。
3. **裁定 3：控制枚举成本。**
   - (a) **先用中心线必要条件剪枝，再完整认证：** 核心段全员在单车道上，中心线即成员车道；核心采样点须满足警戒 SDF ≤ −10、保护 SDF ≥ 10，并用 base 场上界确定拒绝。任一不满足直接拒绝；它是必要条件，不改变可行集合，由 (b) 门禁覆盖。
   - (b) **等价门禁用确定性子集：** `iter_certification_cases` 产生门禁子集（5 族 × 3 种人数；每组格按规范顺序等间隔至多 24 格，含可行与空格；每格 6 组合全取；A 取每第 4 个网格点（20 m）；R 取 \(k\in\{0,1,2,4,8,16,32,\ldots\}\) 不超过上界）。比较 `exact`、`screened`、剪枝＋`screened` 三条路径，两两逐个相同；报告候选总数、可行/拒绝数、墙钟（可 24 进程并行）。
   - (c) **成本检查点：** 跑 200 个合同前先预建前 5 个登记族，按族机数加权外推全部 40 族预建墙钟（24 进程）。**外推超过 45 分钟就停在检查点汇报**每格耗时、空格比例、剪枝命中率，不得自行改用别的策略；不超过 45 分钟才继续。
4. **裁定 4：** 半径上界接受指令按警戒圈外接框推出的必要上界，不另设经验上界；形变支撑接受"横向、纵向两类实际支撑之并都必须在警戒层内"。可行合同数可能因此低于原型估计，止损阈值不变，触发就如实停在检查点。
5. **裁定 5：** 第 12.5–12.8 节按指令处理；`o17_d1`、`o17_d4` 正常计数，单列报告。

---

## 1. 第 1 部分：分支、输入、名单、快照、测试基线 —— 完成

- **分支：** `git fetch origin refs/heads/dev/v0.8:refs/remotes/origin/dev/v0.8` 后，`git rev-parse '6dba0bc^{commit}'` 为 `6dba0bc0a3813b6241fafb4c2b4f2d54a8e669b3`；`git switch -c review/v08/V8-18-feint 6dba0bc0…` 新建分支。开工前本地与远端均无同名分支（`git branch -a --list '*V8-18*'`、`git ls-remote origin 'refs/heads/review/v08/V8-18*'` 均为空）。工作区开工时唯一未提交项是上一任务留下的 `docs/v08/V8-17/owner_rerun.json`（未跟踪，保留不动，不提交）。
- **manifest：** [manifest.json](manifest.json)，由 [make_manifest.py](make_manifest.py) 生成。核对结果：
  - 开发集 SHA256 为 `223e0e0d…36e0`，与指令登记值及 V8-17 manifest 相同；40 族输入散列、`configs/v08/*.json` 散列与 V8-17 manifest 完全相同。
  - 三个基线：`full_v14c`（200 合同，保留 198）、`full_transit_r2`（200，保留 200）、V8-17 `full_r1`（200，保留 199）。`full_r1/records.json` 与 `summary.json` 的 SHA256 与 V8-17 `part7/full_hashes.txt` 相同；监视、过境基线目录树散列与 V8-17 manifest 相同。三者的 200 键均等于主批名单。
  - 名单：快批 20（`o01..o09,o11` × draw 0/1，与指令一致）、主批 200、多样性 100（10 族 × branch 0..9）、复跑 5（`o01_d0..o01_d4`）、原型 3 键、边缘 2 键。数量 20/200/100/5 不按结果重选。
  - `known_infeasible` 为 `[]`。
- **冻结快照：** [snapshot_part1.json](snapshot_part1.json)，由 [snapshot.py](snapshot.py)（沿用 V8-17/V8-16 工具）生成：160 个输入文件（与 V8-14c 末快照一致）、237 个模块文件、24 个细粒度函数体（V8-16 的 7 个＋V8-17 的 8 个＋本项新增 9 个突入/监视掉头函数）、`v07_*` 22 个目录统计、两冻结工作树 HEAD 与干净状态、整个 `monitoring_turn.py`（SHA256 `409fb67b…e9a3`），以及三基线的全部文件身份（监视 8551、过境 8651、突入 8589）。
- **环境：** [part1/env.txt](part1/env.txt)：Python 3.12.3、NumPy 2.5.3、SciPy 1.14.1、shapely 2.0.7、scipy-openblas 0.3.34，四个线程变量为 1。默认进程数 `DEFAULT_WORKERS = 24`，复跑 1。
- **旧测试基线：** [part1/tests_baseline.txt](part1/tests_baseline.txt)，由 [run_suites.ps1](run_suites.ps1) 在 PowerShell 7 中逐条执行 V8-17 `run_suites.sh` 与 `run_v17_tests.sh` 清单里的 Python 命令（指令 1.3 不要求使用 bash）。结果与 V8-17 第 1 部分基线相同：V8-12 两项历史失败（`test_registered_files_hash_and_read_only`、`test_each_diagnostic_threshold`）、带数据根一项（`test_each_diagnostic_threshold`）；V8-15 `test_extra_*` 无测试（exit=5）；其余全部通过；V8-17 三个可离线运行的文件 8+5+4 全过。
- **预置测试：** 由 [extract_presets.py](extract_presets.py) 从指令第 9 节原样取出，三份 SHA256 与作者静态复核记录（`author_static_review.json`）一致：`test_preset_numeric_v18.py` `37e0f99b…914c`、`test_preset_local_geometry_v18.py` `df210a76…0c39`、`test_preset_local_artifacts_v18.py` `028620ee…ea52`。作者状态为"未经运行"；执行方的运行日志在后续部分另列。裁定 1 授权的两处断言修改在第 3 部分进行并登记。

## 2. 第 2 部分：通用层与第一轮三意图门禁 —— 完成

- **掉头表进入优化（指令 2.1）：** 新增 `v08/motion/optimize.py::turns_from_skeleton(skeleton, maps, monitoring_values)`，与监视分支 `optimize_segment` 中的运算逐句相同：成员排序、成员 rows 原顺序、`key is None` 跳过、`np.interp(s, nom.curve.s, nom.t_nodes) + nom.release_s`、R 取 `monitoring_values[key]`（未知 key 直接 `KeyError`，不默认半径）。`_optimize_segment_intent` 只把 `JointProblem(..., ())` 改为传该结果（取值 `load_config("monitoring").values`）；`references_from_skeleton` 仍传 `cons["crossing_boundaries"]`；监视分支未改。过境/突入骨架见证的 `turn_ranges` 为 `{}`，结果仍为 `()`，不增加任何输出字段。
  - 执行方手工核对（scratch 脚本，非测试）：预置测试 9.1 的解析例返回 `(("m", 21.0, 24.0, 15.0),)`，`witnesses={}` 与 `turn_ranges={}` 均返回 `()`。正式测试在预置测试文件全部可导入后（第 3 部分）运行。
- **合同与分派（指令 2.2）：** `contract/single_intent.py` 新增 `feint_mission`（`monitoring_mission` 后仅 `replace` 唯一 TaskSpec 的 intent）；`GENERATION_INTENTS`、`validate_single_mission`、`mission_for_intent` 增加 feint；`motion/intent_dispatch.py` 的 `SUPPORTED` 与三个分派函数显式增加 feint 分支（指向第 3–4 部分实现的 `intents.feint.propose_and_build`、`check_feint`、`screen_feint_member`，按调用时惰性导入，旧意图不导入它们）；`runner/joint_intent.py` 的 `INTENTS` 增加 feint（`run_contract` 的 feint 运行分派在第 4 部分接入）。圈层直接调用 `constraints_for_task`：feint 目标上限 2，base 为 world、障碍、目标 protected 外 10 m、其他设施 alert 外 10 m，`crossing_boundaries` 为 warnings 加目标 alert，未改。
- **测试影响搜索：** `grep -rn "SUPPORTED|GENERATION_INTENTS|INTENTS|problem.turns|.turns ==|turns, ()|feint" tests/v08`（排除 V8-18）：没有断言意图元组等于三元组、也没有断言 `problem.turns == ()` 的旧测试；含 feint 的旧测试只涉及冻结判据（V8-11）与七意图圈层表（V8-16/17，feint 上限 2 未改）。`skeleton_builder`/`semantic_checker` 的 `assertIs` 旧断言只涉及监视/过境/突入，不受影响。
- **第一轮门禁（指令 2.3）：** [run_gates.ps1](run_gates.ps1) 在提交 `ecf6b41` 上（工作区只有未跟踪的 `owner_rerun.json` 与 `part2/`）依次运行三个现有 CLI（24 进程），输出在运行根 `out\gates_2\{monitoring,transit,intrusion}`；[gate_compare.py](gate_compare.py) 逐合同递归比较文件集合与原始 bytes，排除 `[]`，两边都须存在 `contract.json`。日志 [part2/gates_2.log](part2/gates_2.log)。

| 意图 | CLI | 基线 | 结果 | 比较文件数 |
|---|---|---|---|---|
| 监视 | `run_separation_v15.py --mode production-quick` | `full_v14c` | 20/20 文件集合与 bytes 全同 | 575 |
| 过境 | `run_transit_v16.py --stage quick` | `full_transit_r2` | 20/20 | 575 |
| 突入 | `run_intrusion_v17.py --stage quick` | V8-17 `full_r1` | 20/20 | 575 |

  逐合同明细与首个差异（均为 `null`）在 [part2/gate_monitoring.json](part2/gate_monitoring.json)、[part2/gate_transit.json](part2/gate_transit.json)、[part2/gate_intrusion.json](part2/gate_intrusion.json)。三份 records 的键集合都等于登记的快批 20 键。门禁运行期间执行方只新建了旧意图不导入的 `feint_turn.py`、`feint_chords.py`，未改任何已有文件。
- **耗时：** 监视 5.5 分钟、过境 9.1 分钟（新缓存根的预建占大头）、突入 1.8 分钟。

## 3. 第 3 部分：佯动骨架 —— 代码完成；解析预置测试通过；等价门禁见 3.6

### 3.1 实现位置与复用

| 环节 | 实现 |
|---|---|
| 入口格、A 网格、A 级入口检查、存在性预建、缓存、门禁子集 | 新增 `v08/motion/feint_chords.py`（`cell_entry`、`centerline_A`、`entry_at_A`、`first_feasible`、`assess_formation`、`query_identity`、`load_chord_set`、`prewarm_feint`、`gate_cells`、`iter_certification_cases`）；单车道、次水平集、沿线采样、collect_phys 直接调用 `transit_chords`（`intent="feint"`） |
| 粗筛、支撑认证、抽样、候选网格、完整认证 | 新增 `v08/motion/feint_turn.py`（`clearance_passes`、`support_pieces`、`deformation_passes`、`sample_turn_grid`、`candidate_grid`、`keypoint_mask`、`certify_candidate`、`formation_params`、`window_reference`） |
| 一次提案、参考、成员、finish、失败分类 | 新增 `v08/motion/intents/feint.py`；`T.build_candidate` 的 feint 回调（`build_reference` / `member_lanes` / `finish_candidate`），速度事件按 `lane.s_group → lane_cum` 映射；旧意图原表达式未动 |
| 入口 LP 范围 | `transit_chords.corridor_rows` 两处 `task.intent == "intrusion"` 扩到 `("intrusion", "feint")`，其他运算不变 |
| 掉头构件 | 只调用 `monitoring_turn` 的 `_core`、`collapse_length_m`、`column_offsets`、`derive_deforming_members`、`choose_joint_turn`、`KINDS/SIDES`；未修改 MT |

`L` 由 `collapse_length_m` 按 S `_turns_v14` 同一参数取得（间距 `slots.spacing_m`、物理 vmax 取 `member_config().vehicle_profile.max_speed_xy_m_s`、command vmax 取 monitoring、动态因子取 joint_opt、曲率界 `kappa_limit(curve_spacing_m, max_turn_per_chord_rad)`）；`l* = max(|l_i|, |l_i^col|)`，与 MT 返回值逐一断言相等。半径网格 \(R=1.05R_{\min}+2k\)，上界 U/泪滴 \(D_a/2\)、斜切 \(D_a/[2\sin(5\pi/12)]\)（\(D_a\) = 目标 alert 外接框对角线），没有经验截断（裁定 4.1）。

### 3.2 认证谓词（`certify_candidate`，exact / screened / 剪枝+screened 三路同一谓词）

1. **格级（解析精确，与模式无关）：** 每条成员车道目标 warning 一次正长度穿越且深 10 m、入圈点所在合法 run（transit 同一 5 m 采样/下界规则）；集合候选 \(D_c\) 预检（参考点 SDF ∈ [50, 250]、全部槽位过 feint collect_phys、210 m 预留起点不早于 run）；A 网格为中心线 alert −10 区间内的全局 5 m 倍数（数学 ceil/floor）。
2. **A 级：** 成员实际支撑起点 \(X_i=A+l_i-l^*\)（车道坐标；纵向支撑起点早于 A，指令 12.4）在本车道 alert −10 区间内且不越过入圈 run；\(A+d_i n\)（q = s_A 的成员节点）在 alert −10 内、protected +10 外；B（每个成员都经过的横向 0 节点）在中心线 alert −10 内；其他 warning 在 [x_c + l_i, X_i] 上整段离带或完整深穿，逐 D 过滤。
3. **出口：** \(E+d_i n_{out}\) 与支撑终点 \(X=l^*+l_i\)（出口车道坐标）在 alert −10 内、protected +10 外；出口车道合法 run（同一规则）、最后成员出目标 warning 的编组站点 \(s_0\) 起每 5 m 的离散首个终点（全员距所有 warning ≥ 50 m、未离开本条 run、\(x \ge l^*\) 即展开完成），终点精确 SDF ≥ 50 复核（指令 12.5 离散口径）。
4. **完整：** `derive_deforming_members` 在支撑窗口参考（入口直线 → 收拢 → 核心 → 展开 → 出口直线，0.5 m 采样，schedule 弧长从该参考的图元接点下标计算）上派生实际成员车道；拼接入口/出口直线段（弦 ≤ 5 m，直线几何精确）得到全成员折线。检查：收拢/展开横向与纵向支撑之并（端点插入后裁切）与整个核心在 alert −10 内、protected +10 外，支撑对全部 crossing boundaries `sense=0, minimum=10`；全折线 feint base；完整 `crossing_analysis`（不传 `skip_ranges`）且目标 warning、alert 方向各恰 `["in","out"]`；各更大 \(D_c\) 只多一段同一直线上的入口延长弦，逐成员 base 精确（格级已查其带与槽位条件）。
5. **剪枝（prune=True，裁定 3(a)）：** 完整认证前加三项必要条件：核心关键点解析区间（alert −10 内、protected +10 外，`sublevel_many` 向量化于全部 (A, R)）、中心线核心 0.5 m 采样点精确 SDF、base 距离场上界 < 0 确定拒绝。核心全员在单车道上，这些点都在每个成员折线上，只省计算。

record 含 `theta_idx/h_m/x_in/collect_D_candidates/A_m/kind/side/radius_m/L_m/l_star_m/primitives/landmarks_xy/collect_D_compatible/terminal_xy/terminal_x/schedule/certificate`，无计时。

### 3.3 粗筛 `screened`（裁定 1）

`clearance_passes(mode="screened")`：对 field 中同名同几何的每项约束，沿折线以 ≤ 5 m 弧长取覆盖点（含两端），读 `lower_clearance` 得 ℓ（已减 \(\varepsilon_f\)）、上界 \(u=\ell+2\varepsilon_f\)；任一有限 \(u<0\) 直接拒绝；全部 \(\ell\ge 2.5\) 直接通过；其余覆盖点 \([s-2.5, s+2.5]\) 所触及的全部弦调用同一精确 `chord_sdf_range`/`margin_from_range`。栅格外（\(\ell=-\infty\)）按不确定处理，不拒绝。单点同理（不确定则精确 SDF）。`upper_literal` 未实现，传入即 `ValueError`。缓存身份记 `mode="screened"`、`prune=True` 与版本 `v18-feint-cells-1` / `v18-feint-turn-1`。

### 3.4 抽样（裁定 2，指令 3.4）

formation 流定槽位 → shape 流 `integers(0, len(cells))` 选格 → connect 流按 KINDS×SIDES 对每组完整 (A, R) 网格 `permutation(n)` 一次、依排列认证取首个通过（无候选组合不调用 RNG）→ `MT.choose_joint_turn` → shape 流在记录相容 \(D_c\) 中均匀选一个、再抽 K 与 logit 分位数 → connect 流路由 → speed 流。生产认证与预建同一谓词（screened + 剪枝）。抽中的格若同谓词下六组合全空，记 `feint_turn_consistency` 普通失败并留证，不换格。分布性质按裁定 2：格均匀、非空组合等概率、组内可行记录均匀，不声称 A 或种类边缘严格均匀。

### 3.5 预置测试与授权修改

- 依裁定 1 修改两处断言，修改前后 SHA 与 diff 见 [part3/preset_ruling1.diff](part3/preset_ruling1.diff)：
  - `test_preset_numeric_v18.py`：`37e0f99b…914c` → `15c4985f…d499`（`test_negative_lower_bound_is_not_infeasibility` 最后一行改为 `assertTrue(clearance_passes(cons, xy, mode="screened", field=field))`，注释改为"负下界不是不可行，screened 交给精确判定（依裁定 1）"）。
  - `test_preset_local_geometry_v18.py`：`df210a76…0c39` → `7fd9485d…bd60`（`mode="upper_literal"` → `mode="screened"`）。
  - 夹具未补任何字段；其余预置断言未改。
- 执行方运行（有记录）：`test_preset_numeric_v18.py` 8/8 通过；`test_preset_local_geometry_v18.py` 中 `InterfacePreset` 2/2 通过，`SceneGatePreset` 在未设环境变量时 skip（记为未执行，设变量后的运行见 3.6）；自加 `test_extra_local_v18.py` 10/10 通过（screened 与 exact 在 400 条随机折线上 0 差异、裁切端点、空组合不耗 RNG、空窗口与进 protected 反例、实测事件手算、白名单）。

### 3.6 等价门禁（裁定 1、3(b)）—— 通过，差异 0

- **命令：** `run_feint_v18.py --stage turn-gate --workers 24`，提交 `7116815`，输出根 `run\diagnostics\turn_gate_r1`（完整逐格 `turn_gate.json`）；摘要 [part3/turn_gate_summary.json](part3/turn_gate_summary.json)，日志 [part3/turn_gate.log](part3/turn_gate.log)。
- **对象：** 前 5 个登记族 draw 0 目标；纵列人数 {1, ⌈N/2⌉, N}（主对照 15 组，与预置测试 9.2 同一构造）＋全部人数横排、最小步长 3 m 梯形（自加 10 组），共 25 组。每组按规范顺序在 A 网格非空的格中等间隔取 24 格（可行与空格都包含：436 格有可行候选，164 格全拒绝）；每格 6 组合全取；A 取每第 4 个网格点（20 m）；R 取 \(k\in\{0,1,2,4,8,16,\ldots\}\) 不超过上界。
- **结果：** 候选总数 **1,021,860**；三条路径可行数均为 **163,045**（拒绝 858,815）；`exact` vs `screened`、`exact` vs 剪枝＋`screened`、`screened` vs 剪枝＋`screened` 三组两两差异均为 **0**，首个差异为 `null`。
- **粗筛统计（`screened` 路径）：** 覆盖点 2,200,632,137，被覆盖弦 4,326,077,759，进入精确的弦 3,770,337（约 0.087%），上界 < 0 直接拒绝的约束判定 93,825 次。
- **exact 路径的拒绝首因（候选数）：** `entry_run_ends_before_support` 320,638、`collapse_start_outside_alert` 114,312、`support_corner_outside_band` 108,903、`deformation_support` 98,801、`lane_blocked_in_target` 98,340、`collapse_end_outside_alert` 53,284、`no_terminal` 24,066、`expand_end_outside_band` 18,846、`no_collect_candidate` 18,720、`exit_blocked` 2,843、`base_clearance` 62。
- **墙钟：** 1,637 s（24 进程；各组 CPU 秒见摘要 `per_group.wall_s`，三条路径合计）。
- **预置 `SceneGatePreset`（单进程、exact vs screened）：** 已在后台启动，结果写 [part3/tests_scene_gate.txt](part3/tests_scene_gate.txt)；在其结束前不宣称该预置测试通过（见第 4 部分登记）。

### 3.7 单格查询与单骨架（开发核对，有记录）

- `o01_d0`（2 机纵列，L = 0）：航向 0、3 的全部 403 / 954 格逐格存在性查询约 2 s / 4 s；单骨架第 1 次 attempt 成功（U 形 R = 29.75 m、A = −170 m，6 个组合均非空，名义预筛两层 1/1，最深 protected SDF ≈ 45.3 m）。
- `o02_d0`（9 机横排，L = 168 m，l* = 60.63 m）：航向 0 的 449 格约 20 s、可行 20 格；单骨架第 1 次 attempt 成功（泪滴 R = 28.25 m、A = −5 m，非空组合 4）。L = 168 m 与 U 例相同。
- 合同 JSON 递归扫描（预置测试 9.3 同一键表）：计时/缓存命中/路径类键 0 处。
- 以上是开发期诊断，输出在 `run\diagnostics\dev_smoke_2`，不是第 5 部分的正式快速检查。

## 4. 第 4 部分：检查、实测事件、保存、测试与第二轮门禁 —— 完成（预置 SceneGate 仍在运行，见 4.4）

### 4.1 优化后与名义检查

- `optimize_checks.check_feint`：照 `check_transit` 的 `_grid_times`、10 Hz 含末端保持采样与返回结构；在优化后曲线上对实际 feint `crossing_boundaries` 做完整 `crossing_analysis`（目标 warning、alert 各 `["in","out"]`，保留违规明细），终点全员离所有 warning ≥ `retreat_clearance_m`（50 m），再调用 `screen_feint_member`；不重新求解。子类：`boundary_crossing`、`target_layer_crossing`、`terminal_clearance`、`nominal_start_inside`、`nominal_not_entered`、`nominal_multiple_visits`、`nominal_layers`、`nominal_dwell`、`nominal_end_inside`（同一成员同子类只记一次）。
- `nominal_checks.screen_feint_member`：原 `layer_levels`、`dwell`，不调用 revisit；七个 condition 键与指令 4.1 表一致；空窗口的首帧/次数/最大层/末帧条件为 False；进入/退出索引与首次退出取法按指令；`min_protected_sdf_m` 为整窗 `signed_distance(protected).min()`。
- 骨架阶段名义预筛只记录（见证 `screen`），不拒绝。

### 4.2 实测保留前门禁

- `feint_report.measured_members`：窗口 `tau_us ≥ release_us[m]` 且 `segment_index == 0`；contour SDF ≤ 偏移判层；独立复算 warning/alert 进入与退出事件、末帧全部设施层、最深 protected SDF；`all_single` 要求全体成员两层进入、退出各恰 1。
- 接在 `joint_monitoring.attempt_chain` 的冻结 `verify_segments([SegmentTask(0, "feint", target)])`、`check_validity` 之后、`ok=True` 之前；非 1/1 为普通失败 `stage="measured_feint_entries"`、`code="candidate_rejected"`，占已有一次 attempt。`run_contract` 对保留结果再从实测轨迹重算一次事件写入 `result.json["feint"]`，并与原保留门禁合成 `retained_p0_ok`。
- 落盘后从 NPY 重读的独立复核由预置测试 9.3（`test_disk_events_validity_and_no_timing`）在快批/全量后执行。

### 4.3 运行器、保存与白名单

- 分派：`joint_intent`（`_intent_module`、`run_contract`、`save_intent_contract`、`_pool_task` 的缓存计数与多样性曲线、`_prewarm_family_feint`、`full_stage` 检查点）、`skeleton_transit`（模块分派、骨架记录、检查点）、`transit_report`（`member_phase_times`/`phase_durations`/`phase_diagnostics`/`group_reference_curves`/`frechet_blocks` 的 feint 分支）、`joint_monitoring.attempt_chain`（遥测与实测门禁）。骨架检查点用 `feint_report.skeleton_checkpoint`（包装监视公共检查点，200、无排除）；全量用 `feint_report.full_checkpoint`（包装 `joint_report.full_checkpoint`）。不调用 `intrusion_report` 的排除名单或直线回退阈值；直线回退只作诊断。
- `result.json["feint"]` 白名单：`turn{kind,side,radius_m}`、`formation{prior,start,realized,lateral_step_m,mapped_from_loose,retreated}`、`members[m]{entry_counts,first_entry_us,first_exit_us,min_protected_sdf_m}`；失败为 `null`；失败见证另含 `measured_feint`。`retreated` 只在队形链退让或梯形步长缩减时为真，loose→abreast 映射不算。
- proposal/witness 只放确定性业务数据；计时（`chord_set_s`、`turn_sample_s`、`corridor_s`、`lp_s`、`route_s`、`candidate_s`、`attempt_s`）只进 `S.timing` → 目录外 telemetry。开发期 smoke 合同 JSON 递归扫描（预置 9.3 同一键表）计时/缓存/路径键 0 处。

### 4.4 测试

| 文件 | 结果 | 日志 |
|---|---|---|
| `test_preset_numeric_v18.py`（依裁定 1 修改后 SHA `15c4985f…`） | 8/8 通过 | [part4/tests_v18.txt](part4/tests_v18.txt) |
| `test_preset_local_geometry_v18.py`（`7fd9485d…`） | `InterfacePreset` 2/2 通过；`SceneGatePreset` 未设变量时 skip = 未执行 | 同上 |
| 同上，设 `V8_18_DEVSET/DATA_ROOT/CACHE` 的 `SceneGatePreset` | 运行中（单进程，15 组纵列 exact vs screened） | [part3/tests_scene_gate.txt](part3/tests_scene_gate.txt) |
| `test_preset_local_artifacts_v18.py` | 未执行（需全量后的 `V8_18_ACCEPTANCE`） | — |
| `test_extra_local_v18.py`（自加） | 10/10 通过 | [part4/tests_v18.txt](part4/tests_v18.txt) |
| 旧套件（V8-11 至 V8-17，PowerShell 逐条） | 与第 1 部分基线完全相同：V8-12 两项、带数据根一项历史失败；V8-15 extra 无测试；其余通过 | [part4/tests_old_suites.txt](part4/tests_old_suites.txt) |

- **测试传播（指令 4.4）：** 第 2 部分已登记搜索结果（无断言 `problem.turns == ()` 的旧测试）。预置 9.2 `test_outer_solver_receives_turns` 在真实外层上核对：feint 传入 `(("m", 21.0, 24.0, 15.0),)`，过境/突入为 `()`。开发链 `o01_d0` 的 `skeleton.json` 见证 `turn_ranges` 两成员各一行 `("u", sa, sb, "turn_u_min_m")`，经 `turns_from_skeleton` 进入 `JointProblem.turns`。

### 4.5 第二轮三意图门禁 —— 20/20 × 3

在提交 `a09a833`（全部 feint 代码已接入；工作区仅未跟踪的 `owner_rerun.json` 与新文档）运行 [run_gates.ps1](run_gates.ps1) `4`，日志 [part4/gates_4.log](part4/gates_4.log)：监视、过境、突入各 **20/20** 文件集合与 bytes 全同（[part4/gate_monitoring.json](part4/gate_monitoring.json)、[part4/gate_transit.json](part4/gate_transit.json)、[part4/gate_intrusion.json](part4/gate_intrusion.json)），排除 `[]`。耗时 6.0 / 1.4 / 1.2 分钟。

### 4.6 冻结快照

[part4/snapshot_part4.json](part4/snapshot_part4.json) 与第 1 部分快照比较（[part4/snapshot_compare.json](part4/snapshot_compare.json)，[snapshot_compare.py](snapshot_compare.py)）：160 个输入、`v07_*` 统计、两冻结工作树、24 个细粒度函数体（含 `solve_joint`、`Prepared`、`prepare_problem`、`check_transit`、`check_intrusion` 等）、整个 `monitoring_turn.py`、三基线全部文件身份均不变；`task_v07/`、`v08/criteria/`、`v08/sim/`、`configs/` 无改动；旧预置测试无改动。改动文件即第 0.2 节允许范围内的 20 个。

### 4.7 开发链核对（有记录，非正式批次）

`o01_d0` 单合同全链路（`run\diagnostics\dev_chain_1`）：第 1 次 attempt 成功，冻结段核验与有效性通过，实测两成员 warning/alert 进入、退出各 1，`retained_p0_ok=True`；阶段时长三段闭合残差 0；合同 JSON 计时/缓存/路径键 0 处。

## 5. 第 5 部分：200 合同只骨架 —— **未执行：停在裁定 3(c) 成本检查点（外推 63.2 分钟 > 45 分钟）**

### 5.1 快速检查（200 合同前）

| 检查 | 结果 | 证据 |
|---|---|---|
| 数值/接口预置测试（单进程） | `test_preset_numeric_v18.py` 8/8、`InterfacePreset` 2/2、自加 10/10 通过 | [part4/tests_v18.txt](part4/tests_v18.txt) |
| 粗筛全候选对照（裁定 3(b)） | 1,021,860 候选三路两两差异 0；墙钟 1,637 s（24 进程）独立报告 | 第 3.6 节 |
| 三个原型键单骨架 smoke、o17_d1/d4 集合诊断 | 见 5.3（检查点停止时的状态如实登记） | [part5/quickcheck.log](part5/quickcheck.log) |
| 两次抽样同一谓词 | 预建 `first_feasible` 与生产 `sample_turn_grid` 都调用 `certify_candidate(mode="screened", prune=True)`；缓存身份记模式与剪枝 | 代码 `feint_chords.CERT_MODE/CERT_PRUNE` |
| 支撑在 alert 内、掉头表非空、无计时 | 开发链 `o01_d0` / smoke：支撑之并与核心认证通过、`turn_ranges` 非空并进入 `JointProblem.turns`、合同 JSON 计时键 0 处 | 第 3.7、4.7 节 |

### 5.2 裁定 3(c) 成本检查点 —— **触发**

- **命令：** `run_feint_v18.py --stage cost-check --workers 24`（提交 `c3c4051`），与生产相同的 `prewarm_all(intent="feint")`：前 5 个登记族各一个预建进程，按确定性 probe 序列预建全部 5 个 draw 的佯动可行格（screened + 剪枝，找到即停）。输出根 `run\diagnostics\cost_check_r1`；摘要 [part5/cost_check_summary.json](part5/cost_check_summary.json)，日志 [part5/cost_check.log](part5/cost_check.log)。
- **外推方法：** 5 族墙钟之和 ÷ 5 族机数之和 = 每机成本（252.9 s/机）；乘以 40 族各自 `vehicle_count`，再按最长处理时间优先（LPT）排到 24 个进程上取最大负载。
- **结果：** 实测 5 族并行墙钟 2,940 s；外推 40 族总 CPU 时间 82,447 s（326 机）、**外推墙钟 3,794 s（63.2 分钟）**，下界（总量 ÷ 24 与单族最大值取大）3,435 s（57.3 分钟）；**> 2,700 s（45 分钟），触发**。按裁定停在检查点，没有启动 200 合同骨架、快批和全量，也没有改用其他策略。

| 族 | 机数 | 各 draw 第 0 组人数 | 查询数 | 预建墙钟 s | 格数 | 可行格 | 空格比例 | 每格平均 s |
|---|---|---|---|---|---|---|---|---|
| o01 | 6 | 2, 6, 1, 6, 2 | 5 | 310 | 46,110 | 8,032 | 82.6% | 0.0067 |
| o02 | 9 | 9, 4, 9, 9, 4 | 4 | 2,938 | 41,178 | 6,453 | 84.3% | 0.0713 |
| o03 | 6 | 4, 4, 1, 2, 4 | 5 | 2,705 | 49,512 | 16,073 | 67.5% | 0.0546 |
| o04 | 7 | 2, 4, 7, 4, 2 | 5 | 860 | 39,630 | 14,638 | 63.1% | 0.0217 |
| o05 | 9 | 9, 2, 7, 9, 2 | 5 | 2,545 | 45,278 | 12,391 | 72.6% | 0.0562 |
| 合计 | 37 | | 24 | 9,358（CPU） | 221,708 | 57,587 | **74.0%** | **0.0422** |

- **剪枝命中率：** 关键点解析剪枝拒绝 4,238,922,849 个 (A, R) 组合，进入逐候选认证 607,430 个，命中率 **99.986%**；中心线核心精确 SDF 再剪去数千个（各查询 `prune_core_exact`）。逐候选认证中的主要拒绝首因为 `support_corner_outside_band`、`expand_end_outside_band`、`deformation_support`（见摘要各查询 `stats`）。
- **成本集中处：** 9 机横排查询（o02 的 3 个、o05 的 2 个）各 600–1,400 s，空格比例最高；这些格需要把完整有限网格走完才能判空，且每格有数万个通过关键点剪枝的候选进入 A 级/出口/形变检查。o03 的 4 机梯形/横排查询每格也较慢（排在每格 0.05 s 量级）。
- **测量条件：** 本机 32 逻辑核、16 物理核、63.7 GB；检查点运行期间另有 3 个单进程任务（预置场景门禁测试、原型 smoke、集合诊断）同时运行，墙钟可能因此略高，未单独扣除。
- **未做的事：** 没有修改剪枝/认证/枚举顺序后重跑检查点；粗筛、剪枝、谓词全部保持第 3 部分门禁通过时的版本。

### 5.3 快速检查在检查点停止时的状态

- **原型键单骨架 smoke**（`--stage smoke --smoke-level skeleton`，输出根 `run\out\smoke\skeleton_r1`，摘要 [part5/smoke_skeleton_check.json](part5/smoke_skeleton_check.json)）：
  - `o01_d0`（2 机纵列，L = 0）：第 1 次 attempt 成功，U 形 R = 29.75 m、A = −170 m，非空组合 6，LP 弯曲（`lp_status=0`），两成员名义预筛通过，`turn_ranges` 非空，进场精确检查通过。
  - `o02_d0`（9 机，loose → abreast，L = 168 m，l* = 60.63 m）：第 1 次 attempt 成功，泪滴 R = 28.25 m、A = −5 m，非空组合 4，LP 弯曲，9 名成员名义预筛全部通过。
  - `o11_d1`：在成本检查点触发后由执行方停止，**未完成**（该族 worker 内存中重算可行格约 40 分钟仍未结束）。
  - 两份已落盘合同 JSON 递归扫描：计时/缓存/路径键 0 处。
- **o17_d1、o17_d4 集合诊断**（`--stage queries`）：排在 smoke 之后，**未执行**（检查点触发后停止）。
- **预置 `SceneGatePreset`（单进程）：** 在第 3 部分后台启动，成本检查点触发后由执行方停止，**未执行完、无结果**，不能记为通过；同一构造的 15 组纵列已包含在 3.6 的 24 进程三路门禁中（差异 0），但那是执行方工具而非该预置测试本身。

## 6–7. 第 6、7 部分 —— 未执行

第 5 部分停在裁定 3(c) 成本检查点，按执行规则不启动 200 合同骨架、20 合同快批、200＋100 全量、5 键复跑与四意图配对。`test_preset_local_artifacts_v18.py` 因此也未执行（无 `V8_18_ACCEPTANCE`）。为后续准备的工具已提交但未运行：`docs/v08/V8-18/make_acceptance.py`、`tools/v08/analyze_feint_v18.py`。

## 8. 快照、改动范围与提交

- **改动范围：** `git diff --stat 6dba0bc HEAD -- "Multi-UAV SimpleGC"`：21 个文件，+3360 / −22；全部在指令 0.2 允许范围内（新增 `feint_turn.py`、`feint_chords.py`、`intents/feint.py`、`feint_report.py`、`run_feint_v18.py`、`analyze_feint_v18.py`、`tests/v08/V8-18/` 四个文件；修改 `optimize.py`、`single_intent.py`、`intent_dispatch.py`、`intents/transit.py`、`transit_chords.py`、`nominal_checks.py`、`optimize_checks.py`、`joint_monitoring.py`、`joint_intent.py`、`skeleton_transit.py`、`transit_report.py`）。`monitoring_turn.py` 未改。
- **首尾快照：** [snapshot_part1.json](snapshot_part1.json) → [snapshot_end.json](snapshot_end.json)，比较 [snapshot_compare_end.json](snapshot_compare_end.json)：冻结范围、输入、三基线、24 个细粒度函数体、整个 MT 首尾一致（`all_frozen_ok: true`）。
- **提交：** 第 1 部分 `f687299`；第 2 部分 `ecf6b41`（代码）、`f5b0e94`（门禁证据）；第 3–4 部分代码 `7116815`；第 3 部分证据 `a09a833`；第 4 部分证据 `c3c4051`；第 5 部分检查点停止见本次提交。每次推送后用 `git ls-remote origin refs/heads/review/v08/V8-18-feint` 核对远端 SHA 与本地一致。
- **工作区：** 唯一未提交项为上一任务的 `docs/v08/V8-17/owner_rerun.json`（未跟踪，按要求不提交）。

## 9. 偏离指令之处与处理

1. **认证折线的直线段采样：** 完整认证在支撑窗口内用 MT 派生的实际成员车道（0.5 m 参考），窗口外的入口/出口直线段以 ≤ 5 m 弦拼接（直线几何精确）。生产 `build_candidate` 仍用完整 0.5 m 参考派生全部成员，并在 `finish_candidate` 对实际折线（含 LP 段与起点连接）重新做全部精确检查；两者是同一几何、不同顶点集，差异只可能影响 `crossing_analysis` 对穿越弧长的线性插值估计。预建与生产抽样调用同一 `certify_candidate`，谓词一致。
2. **相容 \(D_c\) 的求法：** 对最小相容 \(D_c\) 的全成员折线做完整检查，更大 \(D_c\) 只检查同一直线上的入口延长弦（base 精确），带与槽位条件已在格级/ A 级逐 D 检查。这是对"每个集合候选完整几何"的等价分解（延长段在直线上、槽位在全部 warning 外 ≥ 10 m），未单独做全折线对照验证。
3. **门禁子集中格的取法：** 裁定 3(b) 的"等间隔取至多 24 格"在"A 网格非空"的格中取（A 网格为空的格没有候选，取了也不产生对照）；24 格中可行与全拒绝的都有（436 / 164）。
4. **新增 CLI 阶段 `cost-check`：** 指令第 8 部分的阶段表没有它；为执行裁定 3(c) 新增，内部调用与生产相同的 `prewarm_all(intent="feint")`。
5. **快速检查与门禁测试未跑完：** 见 5.3；均如实记为未完成/未执行。

## 10. 第 12 节疑点状态

| 疑点 | 裁定状态 | 本项处理 |
|---|---|---|
| 12.1 负下界拒绝与精确等价 | 已裁定（裁定 1） | 实现 `screened`，不实现 `upper_literal`；三路门禁 1,021,860 候选差异 0；两处预置断言按授权修改并登记 |
| 12.2 A/种类边缘分布 | 已裁定（裁定 2） | 按监视协议抽样；不声称边缘严格均匀；分布诊断需要 200 合同骨架，因检查点停止未产生 |
| 12.3 半径上界 W | 已裁定（裁定 4.1） | 用 alert 外接框推出的必要上界，无经验截断 |
| 12.4 纵向支撑早于 A、晚于 E | 已裁定（裁定 4.2） | 认证横向与纵向支撑之并；可行率影响未能在 200 合同上测量 |
| 12.5–12.8 | 已裁定（裁定 5） | 终点离散首站、不改冻结判据、旧意图分支未误用（不调用突入排除名单/直线回退门槛）、配置残留不启用 |

## 11. 需要审查方判断的事项

1. **成本检查点触发后的方向（裁定 3(c)）：** 外推 63.2 分钟 > 45 分钟。成本主要来自大编组（9 机横排）查询中的空格：完整有限网格走完才能判空，每格有数万个通过关键点剪枝的候选进入 A 级/出口/形变检查。是否放宽时间上限、接受更长的一次性预建（缓存可复用于后续全部批次），或授权某种不改变可行集合的进一步剪枝/实现提速（例如把 A 级与出口检查也向量化到 (A, R) 网格、在 A 级先按成员支撑起点区间整体裁掉 A 区间），需要裁定。执行方没有自行改动。
2. **认证折线直线段采样与相容 \(D_c\) 分解（第 9 节第 1、2 项）** 是否可接受为与指令文本等价的实现。
3. **门禁子集只在 A 网格非空的格中取格（第 9 节第 3 项）** 是否符合裁定 3(b) 的本意。
4. **预置 `SceneGatePreset` 的运行方式：** 单进程运行时间估计数小时（15 组 × 两路）；是否接受 24 进程三路门禁作为同构造的替代证据，或要求在后续批次中完整单进程运行。
5. **o11_d1 与 o17 两例的集合诊断** 尚未完成，需在恢复后补跑。


---

## 12. 成本检查点裁定（2026-11-07）与恢复执行

> 依据：`_handoff\2026-11-06_V8-18_feint\V8-18_成本检查点裁定_20261107.md`（以下称"成本裁定"），补充并优先于指令与附录。

### 12.1 裁定摘要

- 停在检查点正确；**接受一次性主批预建，不改算法**；主批预建上限放宽到 **90 分钟**（24 进程墙钟），超过即停下汇报，不得自行改策略。
- 第 11 节五项：(1) 按上条处理，提速留到 ⑥ 之前；(2) 两处实现分解都接受，条件是每个集合距离各自的集合点检查逐个做（代码位置见 12.2）；(3) 门禁子集只在 A 网格非空的格里取，接受；(4) 24 进程三路门禁作为 `SceneGatePreset` 的替代证据，条件见 12.3；(5) o11_d1 smoke 与 o17 两例诊断在主批预建后读缓存补跑。
- 提速路线（⑥ 之前做，本项不实施）：在 A 一级做与 R、种类、侧向无关的必要条件检查（收拢段 A→B 中心线在 alert 内 ≥ 10 m、protected 外 ≥ 10 m；入口车道合法到 A），整行剪掉；采用时须重跑三路门禁。

### 12.2 成本裁定第 2 节第 2 项：代码位置

| 内容 | 位置（`Multi-UAV SimpleGC/`，提交 `5667284` 起未改） |
|---|---|
| (i) 形变窗口外直线段按 ≤ 5 m 弦拼接 | `v08/motion/feint_turn.py:589`（入口段 `_line_points(p_in, …)`）、`:595`（出口段 `_line_points(p_out, …)`）、`:596`（与窗口车道拼接）；弦长常数 `STRAIGHT_STEP_M = 5.0` |
| (ii) 每个集合距离各自的集合点检查（逐 D 向量化，非只查最小 D） | `v08/motion/feint_chords.py:102`（参考点目标 warning SDF ∈ [50, 250]）、`:105`（各槽位 `collect_phys`）、`:107`（210 m 预留起点不早于入圈 run）；A 级逐 D 的其他 warning 带检查 `:158–167` |
| (ii) 最小 D 全检、更大 D 只检入口延长弦 | `v08/motion/feint_turn.py:576`（`D0` = 最小相容 D，全成员折线完整检查）、`:612–623`（其余 D 逐成员检查 `[slot(D), slot(D0)]` 延长弦的 feint base 精确余量） |

### 12.3 成本裁定第 2 节第 4 项：`SceneGatePreset` 状态

- **状态：未运行，以三路门禁替代（依成本裁定）。** 不写"通过"。第 3 部分曾在后台启动该单进程测试，成本检查点触发后由执行方停止，未产生结果（[part3/tests_scene_gate.txt](part3/tests_scene_gate.txt)）。
- **同口径说明：** 预置测试 `tests/v08/V8-18/test_preset_local_geometry_v18.py:88` 用 `formation_slots(group, ctx.family, key, formation="column")` 构造槽位，`:90` 遍历 `FC.iter_certification_cases(ctx, task, slots)`，`:92–93` 分别调用 `FT.certify_candidate(..., mode="exact")` 与 `mode="screened"`，比较 `feasible`。三路门禁 `tools/v08/run_feint_v18.py:68–81`（`_gate_setup`）对 15 组主对照用同一族、同一 draw 0 目标、同一人数与 `formation="column"` 构造槽位，`:111` 遍历同一 `FC.iter_certification_cases`，`:115–117` 调用同一 `FT.certify_candidate`（exact、screened、剪枝＋screened），逐候选比较 `feasible`；另加 10 组横排/梯形。结果见 3.6（1,021,860 候选，差异 0）。

### 12.4 主批预建（成本裁定 §4 第 2 步）—— **超过 90 分钟上限，停在检查点**

- **命令：** `run_feint_v18.py --stage prewarm --workers 24`（新增阶段，内部调用与生产相同的 `prewarm_all(intent="feint")`，提交 `a422447`），写入既有运行根 `cache\feint_v18`；开始 2026-11-08 00:48:25，机器上无其他大任务。日志 [part5/prewarm_main.log](part5/prewarm_main.log)。
- **结果：** 到 90 分钟（02:18:33，墙钟 5,408 s）时 **29/40 族完成**（217/326 机），**11 族未完成**：o07（11 机）、o11（12）、o12（9）、o19（9）、o23（9）、o26（7）、o28（11）、o33（9）、o34（12）、o37（11）、o40（9），合计 109 机。按成本裁定停止预建（终止进程），没有改策略。逐族状态（查询文件数、可行格数、内部构建秒数、最后写入时刻）见 [part5/prewarm_main_status.json](part5/prewarm_main_status.json)。
- **观察：** 未完成的基本是 9–12 机的大族，与第 5.2 节"成本集中在大编组空格"一致；o17 与 o36 因梯形二分 probe 分别写了 13 与 23 个查询文件。前 5 族文件来自第 5.2 节成本检查（身份核对后复用）。
- **缓存状态：** 已完成族的文件按原子落盘保留在 `cache\feint_v18`，后续可直接复用；未完成族没有半成品文件（无 `.tmp` 残留）。`prewarm.json`/`prewarm_summary.json` 因进程被终止未写出。
- **未执行：** 按用户指示的顺序，o11_d1 骨架 smoke 与 o17_d1/o17_d4 集合诊断须在主批预建完成后读缓存补跑；o11 族未完成，因此未补跑。第 5–8 部分的 200 合同骨架、快批、全量、复跑均未执行。

### 12.5 需要审查方判断的事项（本轮）

1. 主批预建 90 分钟内完成 29/40 族。是否：(a) 再放宽上限、在已有 29 族缓存基础上只补 11 族（预计还需约 1 小时，按已完成大族的单族耗时推断，未实测）；或 (b) 先实施成本裁定第 3 节的 A 级整行剪枝提速（须重跑三路门禁），再预建剩余族。执行方未自行选择。
2. 已完成 29 族的缓存身份不依赖本次是否中断；若采用 (b) 改动剪枝，缓存身份中的认证版本/剪枝字段会变化，已有文件将不再被命中（需重新预建）。

## 13. 按需判空裁定（2026-11-08）与本次接续

### 13.1 当前依据、身份与范围

- 依次读取执行指令、GPT 附录、2026-11-07 成本裁定、2026-11-08 按需判空裁定，后读优先。2026-11-07 成本裁定第 2 节的实现分解、门禁取格及替代证据裁定继续有效；全格预建、45 分钟外推和 90 分钟主预建上限已被最新裁定取代。
- 本次执行方：Codex（GPT-6，未从环境获取更细模型标识）；PowerShell 7.6.9、项目 `.conda-env=llm`。按用户指定 refspec fetch 后，本地和远端均为 `4da418298fe42d66fcbecd166cb782868d19b575`。`owner_rerun.json` 是唯一原有未跟踪文件，保留且不暂存。
- 生产流程：廉价入口候选格按 theta/h 规范排序 → 每个 probe 一次 shape permutation → 沿排列用原 `first_feasible(screened, prune=True)` 取首个非空格 → 原组合抽样与下游链。全空才进入下一 probe；梯形二分每一步独立排列。下游失败直接结束本次 attempt。
- 单合同存在性 memo 的身份包含完整查询身份与格；合同键改变即重建该 memo，命中不消耗 RNG。廉价入口表、解析车道和距离场仍可复用。`feint_turn.py`、`first_feasible` 的认证逻辑、screened、MT 和冻结求解参数均未改。
- 本次源码只改 `v08/motion/feint_chords.py`、`v08/motion/intents/feint.py`、`v08/runner/joint_intent.py::_prewarm_family_feint`、`tools/v08/run_feint_v18.py`，新增 `tests/v08/V8-18/test_extra_lazy_v18.py`；同步本 REPORT 与 RUNNING。共享运行器只把 feint 预建改为既有几何场预热及人数登记，因此第二轮三意图门禁必须重跑。三路等价门禁依最新裁定不重跑，原 1,021,860 候选、差异 0 的证据继续有效。
- 历史 `assess_formation/load_chord_set/prewarm_feint` API 保留供历史诊断；当前生产、smoke、queries 不调用。CLI 撤掉 `cost-check/prewarm` 阶段，避免继续使用已取消的预建流程。

### 13.2 测试影响清单与测试结果

| 测试 | 对预建/命中/load_chord_set 的依赖 | 处理与本次结果 |
|---|---|---|
| V8-18 `test_preset_numeric_v18.py` 8 项 | 无；只测数值、组合抽样与检查点 | 原文件与断言不动；8/8 通过 |
| V8-18 `InterfacePreset` 2 项 | 无；真实优化外层入参与圈层 | 原文件与断言不动；2/2 通过 |
| V8-18 `SceneGatePreset` 1 项 | 直接调用 `iter_certification_cases/certify_candidate`，不加载预建 | 不改调用或断言；未运行，以原三路门禁替代（依 2026-11-07 成本裁定第 2 节第 4 项）；本次测试发现时 skip 不计通过 |
| V8-18 `ArtifactPreset` 3 项 | `cache` 仅供加载几何；禁止 cache_hits 等键进入合同；不要求命中或预建 | 不动文件与断言；正式快批/全量/复跑后运行 |
| 原自加 `test_extra_local_v18.py` 10 项 | 无预建、命中或 load_chord_set 依赖 | 文件与断言不动；10/10 通过 |
| 新自加 `test_extra_lazy_v18.py` | 按需判空与真实进程对照 | 4/4 通过；含裁定 (a)(b)(c) 与冷热 RNG 检查 |
| 旧 V8-17 `test_extra_local_v17.py` 的动态输入用例 | patch 的是 `intrusion_chords.load_chord_set` 和突入 probe | 与 feint 改动无关；不改路径或断言 |
| 其余旧测试 | 无 feint 全格预建、磁盘命中或 load_chord_set 预期 | 不改 |

- 本次合计 **24 项通过、1 项 SceneGate skip（不算通过）**。预置三文件及原自加文件均没有修改，不需要修改预置断言或调用路径。日志见 [part5_lazy/tests_lazy_r2.log](part5_lazy/tests_lazy_r2.log)、[numeric](part5_lazy/test_preset_numeric_v18.py_lazy_r1.log)、[geometry](part5_lazy/test_preset_local_geometry_v18.py_lazy_r1.log)、[extra](part5_lazy/test_extra_local_v18.py_lazy_r1.log)。首个沙箱内 conda 启动被 Windows DLL 限制拦截，测试未运行；其后用沙箱外相同 llm 环境完成，无依赖安装或版本调整。
- 裁定 (c) 用共享骨架运行器的真实 spawn 进程池，workers=1 与 2；对 `o01_d0` 及伴随键 `o01_d2` 的完整合同文件集合及 bytes 比较，**2/2 一致，排除 []**，两键两种进程数均第 1 次 attempt 成功。证据 [lazy_process_comparison.json](part5_lazy/lazy_process_comparison.json)，原轨迹/合同保留在 `run/diagnostics/lazy_process_test_r1/`。这项不替代正式 5 键 24/1 复跑。
- 裁定 (a) 原文“第 2、5 个非空”若按序数解释会与其明确写出的 `4（空）→1（非空）` 冲突；自加测试以明确要求的排列、选中下标 1 与两次判空为预期，非空下标设为 1、5。预置测试未涉及此歧义，也没有修改预期。留给审查方核对文字口径。

### 13.3 缓存保留证据

旧 29 族的 155 个格存在性文件（含文件大小、SHA256、UTC 修改时刻）见 [preservation_before.json](part5_lazy/preservation_before.json)。全部原样保留，生产不再读写 `cache/feint_v18`。同一证据登记了 MT、完整 feint_turn、预置三文件与 owner_rerun 的原散列；各检查点后核对。

### 13.4 检查点进度

- 按需改造与自加测试：已完成，单独提交。
- 共享文件改动后的第二轮三意图门禁：监视/过境/突入各 20/20 逐字节一致，排除 []。
- 单进程快速检查：三个骨架 smoke 均第 1 次 attempt 成功，落盘精确重验通过；两个边缘集合诊断已完成，均经梯形缩减找到非空格。单合同骨架超过 900 s 停。
- 第 5 部分：200/200 骨架成功、208 attempts、检查点无触发，24 进程墙钟2031.349 s；完整证据见13.8。
- 第 6/7/8 部分：依前置检查点逐项推进，未执行部分不宣称通过。


### 13.5 共享文件改动后的第二轮三意图门禁 —— 通过

代码绑定 `8e22f064899cd8fd832f90558da282fb319eed05`；命令脚本 [run_gates_lazy.ps1](run_gates_lazy.ps1) 使用三个既有 CLI、24 进程、原输入与原三个基线，任何运行或比较非零即停止。输出根 `run/out/gates_lazy_r1/`，日志和比较索引在 `part5_lazy/`。

| 意图 | 原基线 | 字节一致 | 排除 | 证据 |
|---|---|---|---|---|
| 监视 | `full_v14c` | 20/20 | [] | [gate_monitoring.json](part5_lazy/gate_monitoring.json) |
| 过境 | `full_transit_r2` | 20/20 | [] | [gate_transit.json](part5_lazy/gate_transit.json) |
| 突入 | V8-17 `full_r1` | 20/20 | [] | [gate_intrusion.json](part5_lazy/gate_intrusion.json) |

三组均比较递归文件集合和全部原始 bytes，包含失败合同，不以成功数代替比较。监视自启动至比较约 311 s，过境运行器墙钟 63.95 s、突入 55.18 s；原六组门禁记录不覆盖。无 P0。

### 13.6 单进程快速检查：骨架 smoke —— 通过

命令由 [run_bounded.ps1](run_bounded.ps1) 对每个固定键调用 `run_feint_v18.py --stage smoke --smoke-level skeleton --contract-keys <键> --workers 1`。每键 900 s 墙钟监视；守护进程只终止自身派生进程树，保留输出。

| 键 | 成功 / attempts | 骨架墙钟 s | 廉价候选格 | 排列走格数 / 首个非空位置 | 实现队形 | 掉头 |
|---|---|---|---|---|---|---|
| o01_d0 | True / 1 | 4.234 | 1981 | 1 / 1 | column | oblique，+1，R=46.4 m |
| o02_d0 | True / 1 | 24.951 | 2107 | 3 / 3 | abreast（loose 映射） | teardrop，+1，R=30.25 m |
| o11_d1 | True / 1 | 37.888 | 2748 | 1 / 1 | abreast（loose 映射） | oblique，+1，R=302.4 m |

三键无队形退让、无异常。排列平均走 5/3 个格，三个 probe 都非空；非空格规范下标分别 799、520、1186。完整命令、启动/结束 UTC、含 conda 启动的守护墙钟 6.30/27.13/40.18 s 见 `part5_lazy/o*_smoke_watchdog.json`。骨架运行输出分别在 `run/out/smoke_lazy_r1_<键>/`。

用 [collect_lazy_evidence.py](collect_lazy_evidence.py) 从已保存骨架重建实际成员支撑，逐个精确检查：形变两类支撑之并及核心、完整 base、完整 crossing_analysis 的 warning/alert 一入一出、掉头表非空、LP 上界、初始连接不提前入 warning、终点全部 warning 外 50 m。**全部通过**，合同递归扫描计时/缓存/路径键及路径值 **0 处**。详见 [smoke_lazy_audit_r1.json](part5_lazy/smoke_lazy_audit_r1.json)。这是首次执行方记录，非审查方独立复跑。

### 13.7 两键集合诊断与快速检查闭合 —— 完成

o17_d1、o17_d4 均为第 0 组 12 机、初始横排，原横向间距 24.331049769681087 m。单进程按真实 shape 键分别运行；两者均经横排判空、梯形二分后找到非空格，选定梯形步长 12.16568544790984 m。这里只确认集合非空，不把它记为骨架或全链路成功。

| probe | 队形 / 横向步长 m | 候选格数 | d1 走格 / 非空位置 | d4 走格 / 非空位置 |
|---|---|---|---|---|
| 1 | abreast / — | 2189 | 2189 / 全空 | 2189 / 全空 |
| 2 | echelon / 24.331050 | 1447 | 1447 / 全空 | 1447 / 全空 |
| 3 | echelon / 3.000000 | 1867 | 15 / 15 | 10 / 10 |
| 4 | echelon / 13.665525 | 1854 | 1854 / 全空 | 1854 / 全空 |
| 5 | echelon / 8.332762 | 1862 | 2 / 2 | 1 / 1 |
| 6 | echelon / 10.999144 | 1862 | 51 / 51 | 85 / 85 |
| 7 | echelon / 12.332334 | 1855 | 1855 / 全空 | 1855 / 全空 |
| 8 | echelon / 11.665739 | 1859 | 171 / 171 | 820 / 820 |
| 9 | echelon / 11.999037 | 1859 | 1690 / 1690 | 1146 / 1146 |
| 10 | echelon / 12.165685 | 1858 | 715 / 715 | 760 / 760 |

- o17_d1：查询 641.632 s（含组合诊断），守护墙钟 646.375 s；10 个 probe、4 个全空、总走 9,989 格。o17_d4：648.201 s，守护墙钟 653.109 s；10 个 probe、4 个全空、总走 10,167 格。无异常。完整逐格下标、各 probe 首因统计、选中格与六组合结果见 [o17_d1_queries.json](part5_lazy/o17_d1_queries.json)、[o17_d4_queries.json](part5_lazy/o17_d4_queries.json)；摘要 [queries_summary.json](part5_lazy/queries_summary.json)。
- 两键选中格均只有 teardrop 正负两组合非空，U/oblique 四组合为空；不要求种类边缘均匀。两个边缘诊断不排除出主批分母。
- 两键合计 20 个 probe、走 20,156 格，平均 1007.8 格/probe（包括 8 个完整判空 probe）；这与宽度边界附近非空格稀少相符，不能用全局约 4 格的估计代替实测。
- 快速检查实际约 23 分钟，其中边缘集合诊断约 21.5 分钟；指令“约15分钟”为估计。三个单合同骨架均小于 38 s，没有触发单骨架 900 s 硬上限。查询没有新增次数或时间拒绝。
- 快速检查后 155 个缓存文件的 SHA256、大小、UTC 修改时刻全部不变；feint_turn、MT、预置三文件、owner_rerun 散列不变，见 [preservation_after_quickcheck.json](part5_lazy/preservation_after_quickcheck.json)。首轮核对脚本因 PowerShell 将 ISO 时间字符串自动解析为 DateTime，造成字符串比较的假差异；分项核对 SHA/大小/UTC ticks 均相同后，用 `ConvertFrom-Json -DateKind String` 修正比较器。未改缓存或生产数据，原错误比较证据保留 [preservation_comparison_attempt_r1.json](part5_lazy/preservation_comparison_attempt_r1.json)。
- 数值/接口/自加测试、三意图门禁、三键骨架及两键集合诊断前提完整。接下来执行 200 合同骨架（24 进程），原第 5.2 节四止损及 3600 s 墙钟上限均保持。


### 13.8 第 5 部分：200 合同骨架（24 进程）—— 完整通过

命令：[run_bounded.ps1](run_bounded.ps1) `-Stage skeleton -Name skeleton_lazy_r1 -Workers 24 -LimitSeconds 3600`；代码仍为 `8e22f06` 的生产实现，执行时文档提交 `493f648`。输出 `run/out/skeleton_lazy_r1/`，原始 200 键完整、唯一、无排除。守护开始/结束 UTC 为 11:38:17 / 12:12:10，含 conda 启动墙钟 2033.632 s；运行器墙钟 2031.349 s。没有超时或 P0。

| 止损项 | 实测 | 严格阈值 | 结论 |
|---|---|---|---|
| 成功率 | 200/200 = 100% | <95% | 未触发 |
| 第 0 组人数档差 | 1–4机 110/110，5–8机 56/56，9–12机 34/34；档差均0个百分点 | 任一低于总体 >10个百分点 | 未触发 |
| 成功合同 attempts 中位数 | 1；192 合同一次、8 合同两次 | >1 | 未触发 |
| 形状复核失败率 | 0/208 | >5% | 未触发 |
| 整批墙钟 | 2033.632 s（守护口径） | >3600 s | 未触发 |

原检查点 `complete=True, triggered=[]`，异常 0；208 个 attempts 为 200 成功、3 次 boundary_crossing、3 次 reference/speed、2 次 start_route 普通拒绝。全部 200 成功骨架使用弯曲 LP，直线回退仅作诊断，无额外回退门槛。证据：[skeleton_summary.json](part5_lazy/skeleton_summary.json)、[skeleton_records.json](part5_lazy/skeleton_records.json)、[skeleton_by_bin.csv](part5_lazy/skeleton_by_bin.csv)。

**每合同骨架墙钟分布（秒）：** mean 52.324、min 4.884、p25 13.245、median 18.957、p75 27.257、p90 43.094、p95 61.225、max 1971.257。附加分位数用 NumPy 线性分位数；运行器原摘要按其原秩算法保留（例如 p50 19.012）。最慢六键：o07_d2 1971.257、o07_d4 1829.662、o17_d4 937.999、o17_d1 901.371、o36_d4 375.255、o36_d2 261.147，均第 1 次 attempt 成功。

900 s 限制按最新裁定第 4 节步骤 2 施加于三个单进程快速骨架 smoke（均小于38 s）；本节步骤3整批施加3600 s墙钟上限。200批次中的上述长尾耗时全部保留，不删键、不换参数或进程数。

**排列与队形：** 全部实际 attempts 共 261 个 probe、走 67,277 格，平均257.766格/probe、中位1、p90 1446、最大2670；29个probe完整判空，232个非空probe的首个非空位置平均31.315、中位1、最大1690（包含梯形二分各次通过probe，并非232个合同）。退让6合同：o07_d2/d4、o17_d1/d4、o36_d2/d4；其中5个由横排转梯形，另1个原梯形缩步长。loose→abreast的映射不计退让。实现队形 column46、abreast102、echelon52。完整倾向/实现表与逐probe下标、步长、计时见 [skeleton_evidence_r1.json](part5_lazy/skeleton_evidence_r1.json)。

**形状与几何：** teardrop80、u68、oblique52；正侧114、负侧86。非空组合数量条件分层、A及半径分布、按队形/人数的L分布均在附加证据中，不声称A或种类边缘严格均匀。以完整成员折线对目标protected调用 `polyline_clearance(..., sense=1, minimum_m=0, fast_far_m=None)`，969成员的最小SDF为10.02751291261876 m，中位52.7745 m，全部达到规划10 m余量；这是骨架精确折线值，实测另验。全部合同JSON递归计时/缓存/路径键与绝对路径值扫描 **0处**。

**粗筛遥测范围：** 首次逐格存在性查询进入完整认证434,112候选，记录直接拒绝38,837次、覆盖点80,998,995、约束弦核验计数731,084,955、进入精确弦3,508,434；A/关键点必要条件剔除原计数13,433,503,223。以上仅计第一次存在性计算，不含内存命中和组合随机抽样中的调用；弦计数沿screened原计数定义，不冒充所有网格或所有生产调用的全覆盖统计。等价性仍由原1,021,860候选三路门禁差异0支持。

**成本与缓存：** 几何预热40族，格存在性查询0、新写格文件0；155个旧文件散列/大小/mtime及FT/MT/预置/owner散列仍全同，见 [preservation_after_skeleton.json](part5_lazy/preservation_after_skeleton.json)。资源样本见 [skeleton_resource_samples.jsonl](part5_lazy/skeleton_resource_samples.jsonl)：采样中私有提交内存最高76.69 GB（含可换出页，不等于常驻物理内存），可用物理内存曾为0.49 GB；长尾由少数大编组/梯形二分主导。默认24保持，没有清缓存、改谓词或重新抽运行名单。

本节为执行方首次运行记录。第5部分检查点完整通过后进入第6部分快批20；正式全链路与单进程五键复跑仍待执行。
