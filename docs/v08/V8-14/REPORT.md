# V8-14 监视骨架可行集合化：执行报告

> 执行方：Claude Code（模型 Claude Opus 5.5，`claude-opus-5-5`）。指令：`claude/v08/V8-14_监视骨架可行集合化_执行指令_20261104.md`（下称"指令"），裁定附录：`claude/v08/V8-14_GPT指令评价与裁定_20261104.md`（下称"附录"；其第 3 节优先于指令对应内容）。上层要求 U：`claude/v08/V8-14_监视骨架可行集合化_上层任务要求_20261104.md`。

## 0. 开工复述（开工前写，未经实测）

### 0.1 附录第 3 节各裁定的理解

**裁定 1（取代指令 2.2 的全局 e、2.3 的宽度判定与取值公式）：局部证书。**
1. 每个方位的可行区间不再各自取"最长一段"，而是先在极坐标连通分量（沿用 V8-13 `_components` 的跨方位相邻重叠合并）上选定**同一个分量**，每个方位取该分量在本行的区间（同一行若有多段属于该分量，取其中最长者，同长取较小 lo）；这样相邻方位的区间来自同一连通片，不会出现相邻两行各取一段、交集为空。
2. 管区间：对给定车道半跨 D，在第 j 方位所选区间内，取精确余量 ≥ D + q + η 的**最长连续子区间** [L⁺_j, U⁺_j]；取消指令"必须包含父区间中点"的要求（指令 8 节"补充接口约定"里 `parent_intervals` 的中点规则也随之取消，改为父区间内最长子段）。q = Δr/2 + 2R*·sin(Δφ/4)，η = 2ε_f（ε_f 从 `S.cg_patrol.field.eps` 读取），定义同指令。
3. 局部交集：A_j = max_{k∈N(j)} L⁺_k，B_j = min_{k∈N(j)} U⁺_k，N(j) = {j−2,…,j+2}（循环；折返弧在弧端夹取）。
4. 队形可行的**唯一判定**：所有 j 都有 A_j ≤ B_j；取代 "hi − lo ≥ W + 2e"。选队形（倾向→梯形→纵列、梯形横向步长二分）与形状构造共用这一判定与同一份证书。全局 e_g、e_s、e 只作诊断字段保留，不参与判定或取值。
5. 取值：r_j = A_j + u(φ_j)(B_j − A_j)；之后按指令 2.3 把 360 个 r_j 直接作为三次周期 B 样条控制值（正基函数平均，不调用插值系数）。
6. 证明：任意方位 φ（最近网格行 j）的平滑值是 {r_k : k∈N(j)} 的凸组合，而 r_k∈[A_k,B_k]⊂[L⁺_j,U⁺_j]（因 j∈N(k)）。故参考线在 [L⁺_j,U⁺_j] 内，各车道余量 ≥ q+η ≥ 0；D 只计一次。实现中 `lower_m/upper_m` 即 L⁺/U⁺（预置测试 8.1 的常数/两级夹具中二者与 lo+D+e_g、hi−D−e_g 数值相同）。
7. 预期（附录第 2 节云端实测）：单机/纵列约 91% 的目标可行，大编组按退让链退让；第 6 部分 D.5 四个阈值不变。

**裁定 2（11.1）：** "射线与边界只交一次"只用于目标设施的警戒层、预警层；其他设施、障碍、protected 等几何仍按多区间精确处理（精确余量逐点+逐弦，不假设单交点）。

**裁定 3（11.2）：** 由裁定 1 取代。"区间内"指参考线及各车道留在物理可行区间与欧氏管之内；不要求平滑后仍保留未消耗的余量。

**裁定 4（11.3，掉头联合查询规模）：** 取代指令 3.2 的参数格范围与"全部枚举后抽"：
1. 半径上界 R ≤ R₀ + (hi_j − lo_j)，hi_j − lo_j 为掉头处方位行的可行区间宽度（R₀ = 1.05R_min，步长 2 m）。
2. 接回点只取与掉头处弧长距离 ≤ 2(hi_j − lo_j) + 2L 的 1° 方位点。
3. 每个（类别×侧向）组合：用 connect 流对其整个参数格（R × 接回点 × h₀ × h₁）做**一次均匀随机排列**，按顺序认证，取第一个通过者——与"全枚举后均匀抽一个"同分布；排列走完无可行者则该组合为空。之后在非空组合中等概率选一个。不设搜索次数上限；空集照实记录。认证谓词内部按"核心→展开直线→曲率→走廊"短路并缓存子结果，只省计算、不改变谓词。

**裁定 5（11.4）：** 接受"K 个独立均匀分位数 → logit"的先验（等价标准 logistic），不加振幅常数。

**裁定 6（11.5）：** 先用独立稠密 KKT 预置测试核验现有初值（已含 jerk 平滑项）；若通过则保留，本项只做共线语义直线合并与诊断。

**裁定 7（11.6）：** 阶段最低速度只在**参考速度 ≥ 0.5 m/s** 的时段统计（0.5 m/s 来自判据有效观测速度），端点起停不计。这与预置测试 8.3 `test_phase_ratio_and_along_projection` 末尾"参考最小速度为 0 时比值为 None、原因 reference_min_zero"的断言冲突，按用户要求写入"疑似预期错误"，该项停下（不改测试、不为通过而改口径），其余继续。

**裁定 8（11.8）：** 折返弧的可行端点对按**相对目标设施中心的真实方位覆盖 ≥ 120°** 筛选，覆盖由弧上采样点在骨架阶段精确算出；参数方位跨度只作诊断。每次接回后的下一次单向穿行同样按真实方位覆盖 ≥ 120° 筛选接回点。环绕拓扑闭合一圈，不受影响。

**裁定 9（11.7）：** 完整骨架的实测与止损由第 6 部分"只构造骨架"检查承担。

### 0.2 七部分、边界与止损

| 部分 | 内容 |
|---|---|
| 1 | 按提交号快进合并 `0d2f0a3` 到 `dev/v0.8` 并推送；建 `review/v08/V8-14-skeleton`；归档材料；预置测试原样落盘并核哈希；冻结哈希与基线测试 |
| 2 | 同一局部证书选队形并在环带内直接构造周期形状（删除 α 扫描生产调用） |
| 3 | 收拢—单车道掉头—接回—展开整体可行集合（裁定 4 的随机排列抽样），变队形成员映射 `member_map_v14` 贯穿下游 |
| 4 | 核验平滑初值；合并相邻共线语义直线；阶段速度/沿迹偏离诊断（裁定 7 口径） |
| 5 | 巡逻段 Fréchet；`optimization_entered` 计数；quick/full 同一口径；依赖测试同步 |
| 6 | 40 族 × draw 0–4 = 200 合同、8 进程、只构造骨架；D.5 四项止损（成功率 <95%、任一人数档低于总体 >10 个百分点、成功合同骨架尝试中位数 >1、形状复核失败率 >5%，严格比较）。**任一触发：停在第 6 部分，提交、推送、汇报，不做第 7 部分** |
| 7 | 快速 20 合同 → 全量 200 + 多样性 100 → 5 合同单进程复跑 |

- **冻结边界：** 不写 `Simulation-fe-prod-r3`、`Simulation-fe-s3`、`SwarmData\v07_*`；`v08/sim/`、`v08/criteria/`、`v08/config.py`、`v08/sampler/`、`v08/scene/`、`v08/diagnostics/diversity.py`、已有配置、`optimize_checks.py` 不改；`optimize.py` 的目标/AL 形式/缓冲/权重/容差不改；旧测试只按 8.5 替换 `test_quick_exact_boundaries`；conda `llm` 只运行不装包；不推 `main`、不强推。
- **唯一预算：** 每合同 20 次 attempt（`joint_monitoring.BUDGET`），内层（环带证书、掉头参数格排列认证）不计合同 attempt，没有第二个合同循环。
- **停止条件**只按指令 0.4（P0）；第 6、7 部分的诊断止损触发只停后续昂贵阶段，不写成物理判据失败。
- **第 11 节未决项：** 11.1–11.8 已由附录裁定 2–9 处理；11.7 的完整真实原型仍未由规划审查方完成，由第 6 部分实测替代（裁定 9）。

### 0.3 预置测试与附录的冲突（疑似预期错误，开工时识别）

| 测试 | 断言 | 冲突的裁定 | 处理 |
|---|---|---|---|
| 8.3 `test_phase_ratio_and_along_projection` 末 2 条 | 参考最小速度 0 → `measured_ratio is None`、`ratio_reason == "reference_min_zero"` | 裁定 7：只统计参考速度 ≥ 0.5 m/s 的时段，端点停车样本不计 → 该夹具比值为 1 | 按裁定 7 实现；该断言预期失败，列入"疑似预期错误"，不改测试 |

其余预置断言与附录不直接冲突的说明见第 8 节（例如 8.4 的"先全集认证后抽"辅助函数仍按测试实现，生产按裁定 4 使用排列抽样；8.1 的 `admissible_arcs` 参数方位跨度函数保留为诊断，生产按裁定 8 筛选真实方位覆盖）。

## 1. 第 1 部分：固定基线、分支与预注册

- **工作树与环境：** `git worktree list --porcelain` 核实开发工作树为 `Simulation-v08`；PowerShell 7.6.9；Python 3.12.3、NumPy 2.5.3、SciPy 1.14.1、shapely 2.0.7、OpenBLAS 0.3.34（scipy-openblas）、AMD64 Family 26（32 逻辑核）；运行前设 `OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1`（[env.txt](env.txt)）。
- **基线与合并：** 开工时分支 `review/v08/V8-13-joint-opt`、HEAD `0d2f0a35adcb90df31a15b210f89a13c7d499c9f`、工作树干净；`dev/v0.8` 原在 `cb6b58e`（V8-12）。`git merge-base --is-ancestor` 确认可快进，执行 `git merge --ff-only 0d2f0a35adcb90df31a15b210f89a13c7d499c9f`，推送 `dev/v0.8`；`git ls-remote` 显示远端 `refs/heads/dev/v0.8 = 0d2f0a35adcb90df31a15b210f89a13c7d499c9f`。从它建立 `review/v08/V8-14-skeleton`。没有合并更晚的提交。
- **R13 合并前提：** R13 要求"合并前由用户运行报告中的抽样复跑命令补足'已复跑'"。本地找到 `_handoff/2026-11-03_V8-13_joint_opt/out_rerun/user_rerun_20261104/reproduction.json`（写入时间 2026-11-04 09:11）：以 `out/full_v13c_r3` 为源、单进程复跑 o01_d0–o01_d4，5/5 `bytes_equal=true`、文件集合一致。目录名表明是负责人复跑，但执行人身份在本地无法核验，因此记为"**有产物、待负责人确认**"，不由执行方升级为"已复跑"。按指令不把它作为 P0。
- **归档：** `claude/v08/` 新增本指令、附录、U、R13、预演清单、分层协作规程（B13、C13 已在该目录）。
- **预置测试：** 按 UTF-8/LF 从指令提取 7 个代码块，SHA256 与指令 8.9 表逐一一致（26ad7b06…、0dfc7d99…、b0d83416…、7e1f5bcd…、13cfb95e…（8.5 方法块）、3a568714…、68e5d017…）。6 个文件原样放入 `tests/v08/V8-14/`；8.5 方法块原文存 [preset_8_5_method.txt](preset_8_5_method.txt)。
- **授权旧测试修订（8.5）：** `tests/v08/V8-13/test_preset_numeric_checkpoint.py` 只替换 `test_quick_exact_boundaries` 方法；修改前 SHA256 `b7aaaccc7e8aa92fc8c83a5156a500e79d2e52ebee46547c190b49740b9c6a68`（git blob 6bfd669），修改后 `c5270d0e676168b64a2f4002b6c82e97c2d82d2d1955396b41e6d087ab64ffab`；diff 见 [old_test_8_5.diff](old_test_8_5.diff)，其余四个方法与 imports、`row` 字节不变。
- **冻结与输入快照：** [snapshot_part1.json](snapshot_part1.json)：160 个登记输入的 SHA256/大小/mtime_ns 与 V8-13c 快照逐项一致；冻结工作树 `Simulation-fe-prod-r3`=641a9b3、`Simulation-fe-s3`=de4d115，均干净；另存 90 个代码/配置/测试文件哈希。
- **基线测试**（[tests_part1.txt](tests_part1.txt)）：V8-13 numeric 预置（替换后）20/20 通过；V8-13 extra 8/8 通过；V8-13 checkpoint 原文件（替换前）4/5，失败一项即 `test_quick_exact_boundaries` 第 26 行旧口径断言（"授权指令修订"，与 R13 云端结果一致）；V8-14 numeric 预置 4 个文件在实现前导入失败（errors=4，预期）。
- **固定提交事实核对：**
  1. `Prepared._ls_grad_c` 已同时含位置项 \(B_0^\top W(B_0C-S)/L_0^2\) 与 \(\lambda_j D_3^\top\Lambda D_3 C/J_0^2\)，`_least_squares` 用预条件器同一 `cho_solve_banded`（`optimize.py` L552–568）；`Prepared.x_ls` 已是破对称前的属性（L415）。
  2. `quick_checkpoint` 已用 `post_optimization_failures`；`full_checkpoint` 仍用成功合同总 `attempts` 中位数 > 1（`joint_report.py` L111 起）；`run_contract` 的 post 计数按 `stage != "skeleton"` 推断（L252），没有进入优化事件标志。
  3. 成员派生 `derive_members` 与 Fréchet 重建 `group_reference_curves` 都假设整条路径常数槽位 `(l, d)`。

## 2. 第 2 部分：沿可行带直接构造（局部证书）

- **新增** `v08/motion/monitoring_band.py`：`grid_error_m`、`band_certificate`（裁定 1 局部证书：A_j=max L⁺、B_j=min U⁺ 于 N(j)={j−2..j+2}，可行 ⇔ 全部 A_j≤B_j；e_g/e_s/e 仅诊断）、`construct_band`（r_j=A_j+u(φ_j)(B_j−A_j)，360 控制值正基平均，弧外为最近弧端幽灵值）、`cubic_blend`、`admissible_arcs`（参数跨度，生产只作诊断）、`radial_intervals`/`radial_margins`（逐点 `clearance_values` + 逐弦 `chord_sdf_range` 精确余量，全部约束多区间处理）、`run_components`（与 V8-13 `_components` 同一重叠合并规则）、`coverage_lower_bound_deg`（裁定 8：真实目标方位覆盖下界）、`certified_arc_pairs`、`BandGeometry`/`loop_query`/`retrace_query`/`build_band_query`。纯数值部分导入不加载 shapely，几何惰性导入。
- **修改** `v08/motion/intents/monitoring.py`：删除 `ALPHA_SCAN`、`_scale_alpha`、`_find_ring`、`_draw_loop`、`_draw_arc(_once)`、`_draw_radius`、`_spline_from_radii`、旧 `_echelon_payload` 及刚性掉头 `_build_turn`/`_draw_retrace_turns`；新增 `_band_probe`（同一批 6 个圈心，先验拓扑→另一拓扑 forced）、`_draw_shape`（只抽一次：分量/弧端点对 → K → K 个均匀分位数 → logit → 直接构造 → 一次原 `_ring_ok`）、`_ring_audit`（失败时只读分原因：curvature / lane_geometry / dwell）、新 `_echelon_payload`（b → 3 → 二分至区间宽 ≤ 2/(n−1) m，返回已认证下端）。圆心仍用 `_center_candidates`（警戒区内均匀，包围盒拒绝采样）。
- **折返弧（裁定 8）**：对每个分量的每个连续方位段列出全部端点对；端点只知落在 [L⁺,U⁺] 内，用"射线上设施方位单调、极值在段端点"取 4 种端点组合中最小的展开增量作真实覆盖下界，≥120° 且弧证书（端部邻域夹取）通过者才入集合；在全部已认证端点对中用 shape 流均匀抽一对。全圆分量的弧跨度 1…359 行。
- **确定性**：分阶段耗时不写入任何 witness/proposal，改由 `last_attempt_timing()` 遥测通道提供（初版把耗时写进 witness，被 V8-12 自加复现测试 `test_plan_is_independently_valid_and_reproducible` 抓到，已修正）。
- **提交说明**：`monitoring.py` 中第 3 部分的整体掉头、变队形成员派生接入点与本部分改动在同一文件、互相依赖，随本次提交一同落地（`monitoring_turn.py` 一并加入）；第 3 部分提交补测试与实测记录。
- **测试**（[tests_part2.txt](tests_part2.txt)）：V8-14 `numeric_band` 6/7（唯一失败 `test_pure_import_does_not_load_shapely`：第 4/5 部分的 `v08.diagnostics.monitoring_skeleton` 尚未建立）；`numeric_turn_flow` 1/1；`local_geometry` 1/1；V8-13 numeric 20/20、extra 8/8；V8-12 全目录 37/40（2 失败与基线相同：数据根环境变量前提、已裁定的逐族 Fréchet 断言；1 skip）。
- **冒烟实测（执行方观察，非检查点）**：o01 d0–d2 首个 attempt 成功（6–16 s/attempt，掉头集合 3–4 s）；o02 d0/d2（9 机横排，D=60.6 m）连续 `patrol_shape_audit`：原因为曲率与驻留。定位：该例管上界 U⁺ 在相邻方位突降约 100 m（第 291–295 行 1182→1084→1026→990 m），B_j 随之突降，360 控制点正基平滑后参考线局部曲率 κ≈0.070 m⁻¹（半径 14 m），小于车道半跨 60 m，车道越过曲率中心。这是指令 2.3 末段明确"未由宽度证明、待实测"的性质，不是实现错误；未改构造。

## 3. 第 3 部分：收拢—单车道掉头—接回—展开整体可行集合

- **`v08/motion/monitoring_turn.py`**（代码随第 2 部分提交落地，见上）：
  - `collapse_length_m`：\(L_{\min}=\max\{3Dv_{\rm cmd,max}/(2v_\perp^*),\ 1.5\Delta l_*,\ \sqrt{6D/\kappa_*}\}\)，\(v_\perp^*=\sqrt{(0.95\times12)^2-10^2}=5.474\) m/s（`joint_opt.buffer_dynamic_factor`、`member_config().vehicle_profile.max_speed_xy_m_s`、`monitoring.speed_max_m_s`），\(\kappa_*=\)`path.kappa_limit(0.5,0.2)`=0.38 m⁻¹，\(L=2(1+\lfloor L_{\min}/2\rfloor)\)；纵列且 Δl=0 时 L=0。例：12 机横排 b=25 m（D=137.5 m）L≈378 m。
  - `sample_joint_turn`（裁定 4）：每（类别×侧向）组合参数格 = R∈{R₀+2k ≤ R₀+W_j}（R₀=1.05R_min，W_j 为掉头方位行原始区间宽）× 接回点（1° 网格、弧长距离 ≤ 2W_j+2L、下一次穿行真实目标方位覆盖 ≥120°（端点精确）、下一次穿行长度 ≥ 2l*（形变支撑无重叠））× (h₀,h₁) 5×5；connect 流对整个格做一次 `permutation`，按序认证取第一个通过者；`choose_joint_turn` 再在非空组合中等概率选一组。认证谓词 = 收拢直线成员车道 ∧ 核心 ∧ 展开直线成员车道（精确逐弦余量 ≥ 拱高界 \(\delta=(6D/L^2)\cdot0.5^2/8\)）∧ 接回 Bézier 曲率 ≤ min(1/(1.05R_min), κ*)（筛选参数点）∧ 筛选点精确余量 ≥0 ∧ 0.5 m 采样全部弦精确余量 ≥0；核心与接回为单车道，其 0.5 m 采样与最终参考同一图元采样，故弦检查即最终检查。子结果按 R、接回点、(R,接回点) 缓存，只省计算。统计每组合 `grid_total/visited/core_pruned/expand_pruned/connector_pruned/full_certified`。
  - `derive_deforming_members`：q_i(s)=s+l_i(s)，l 的收拢三次段在 [s_A−l*, s_B−l*]、展开段在 [s_D+l*, s_E+l*]；d̃(q) 只在 A→B、D→E 上按 H 变化，[s_B,s_D] 恒 0；节点 = 参考节点 ∪ 事件站点 ∪ q(标记站点)；二分求逆；严格单调与零长弦检查。
- **`monitoring.py` 接入**：`build_reference_parts`/`turn_schedule` 从参考采样区间读出每次掉头的 s_A/s_B/s_D/s_E；`build_candidate` 改用变队形车道，速度事件映射改为 `interp(q_i(s_c+s_rel), lane.s_ref, lane_cum)`；`_turn_ranges_v14` 覆盖核心与接回（不含收拢/展开直线）；`witnesses["member_map_v14"]`（schema `member-map-v14`，逐成员 reference_s / shifted_reference_s / member_s（含起点连接长度）/ lateral_m / turn_mask / patrol_member_s）与 `turn_schedule_v14`。旧提案（无 `turn_parts`）退化为常数槽位。
- **自加测试** `tests/v08/V8-14/test_extra_turn_members.py` 5/5（[tests_part3.txt](tests_part3.txt)）：直线解析夹具上映射严格单调、核心 d̃≡0 且成员落在参考线、到 B 前已收为纵列、`1+l'>0`、反函数；排列首通过者在 4 个可行元素上频率 0.25±0.01（40000 次）；非空组合等概率选组。预置 `numeric_turn_flow` 1/1。
- **原型核对**（`out/prototype/verify_turns_r1`，只构造骨架，o01/o03/o04/o06/o07/o11 × d0–d2，脚本 [part3/verify_turns.py](part3/verify_turns.py)）：对每个成功骨架按 8.7 同一口径独立重算成员映射单调、turn_mask 内横向为 0、全部 base 约束（整条成员曲线）与 patrol 约束（巡逻裁切段）精确余量 ≥0。结果见第 6 节前的补记。
