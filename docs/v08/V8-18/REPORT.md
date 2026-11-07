# V8-18 佯动单段：执行报告

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

