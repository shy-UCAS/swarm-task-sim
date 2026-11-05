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

## 4. 第 4 部分：初值核验、语义直线合并、阶段诊断

- **初值（裁定 6）：** 预置 `test_initial_matches_independent_dense_kkt` 用 SciPy BSpline 独立构造稠密 KKT（含 jerk 项 \(\lambda_j=1\)、J₀=14、L₀=3、端点 p/v/a 等式），与 `prep.coeffs(prep.x_ls)` 在 √ε 量级一致，**通过**。固定提交初值已是 \(H_0z=b\) 的解，`_ls_grad_c`/`_least_squares` 保持不变，不重标权重。
- **语义直线合并：** `skeleton.merge_semantic_lines(lines, *, knot_s, tol_m=1e-6)`：逐成员按 (t0,t1,序号) 排序，只合并时间相邻、单位切向叉积 ≤ γ₈、点到支撑线 ≤ 1e-6 m、间隙严格 < 4h 的段；沿用最早段点/切向，meta 记来源、原区间、gap、最大共线残差。`optimize_segment` 只对等式输入合并一次（`lines` = 合并后、`lines_raw` = 原始；`optimized.json` 两者都存）；`crossing_analysis` 与几何判据仍用完整原曲线。
- **阶段诊断：** `v08/diagnostics/monitoring_skeleton.py::phase_metrics`（裁定 7：只在参考速度 ≥ 0.5 m/s 的样本上取三者最低速度与比值，端点起停不计；无此类样本记 `no_moving_reference_samples`；全部样本的参考最低速度另记 `reference_min_all_samples_m_s`；沿迹偏离为一维投影 \(\max|(p-p_{ref})\cdot\hat t_{ref}|\)，零速时用成员名义曲线切向）。`joint_monitoring.phase_diagnostics` 按 `member_map_v14.patrol_member_s` 的名义时间切三段（[release, 首巡逻站点)、[首, 末)、[末, 移动结束]，最后阶段含终点），网格为实测 10 Hz 帧（tau_us 与 TimeReference 同钟，release 取整差另记），collect 时刻为子标记；成功合同写入 `phase_metrics`。
- **测试**（[tests_part4.txt](tests_part4.txt)）：`numeric_initial` 3/3；`numeric_band` 7/7（导入隔离项随诊断模块建立而通过）；`numeric_metrics` 导入失败（第 5 部分的 `attempt_counters`、`skeleton_checkpoint` 尚未实现）；V8-13 numeric 20/20、extra 8/8。

**第 3 部分原型核对结果（补记，`out/prototype/verify_turns_r1`，[part3/verify_turns_r1.json](part3/verify_turns_r1.json)）：** 18 个合同中 12 个在预算内得到成功骨架（其中 9 个折返、3 个环绕；折返共用到 teardrop/u/oblique 三类、左右两侧，无 `turn_joint_set_empty`）；12 个成功骨架的独立核对 **0 项失败**（映射严格单调、turn_mask 内横向偏移恰为 0、整条成员曲线的 base 约束与巡逻裁切段的 patrol 约束精确余量全部 ≥0）。153 个 attempt 中失败 141 次：`patrol_shape_audit` 139 次（原因全部含 curvature，73 次同时含 dwell）、`egress` 1 次、`obstacle:obstacle_02` 1 次。这只是原型量级，正式检查点见第 6 节。

## 5. 第 5 部分：口径统一与依赖传递

- **巡逻段 Fréchet：** `group_reference_curves` 改为读取构造时保存的编组参考（`plan.reference_xy`，参考弧长 = `collect_s` + 累计弧长）与 `member_map_v14`，只取 [patrol_start, patrol_end] 并精确插入两端点；\(t_i(s)\) = 成员映射 reference_s→member_s 后按该成员名义弧长—时间插值；before/after 各自按自己的几何弧长用 `monitoring_skeleton.patrol_resample` 5 m 重采样（补尾端点）。`frechet_blocks` 每对另报巡逻起/终点距离与最大值（`endpoint_m`，不从 Fréchet 扣除），块标 `scope: patrol_segment_v14`；合并中位数仍用原 `pooled_frechet`（跨族合并、无配对为 None）。
- **优化后失败次数：** `attempt_chain` 在调用 `optimize_segment` **之前**置 `optimization_entered=True`（经 `entry_flag` 同步，异常路径也携带），骨架失败返回 False；`_attempt_summary` 保存该标记、`skeleton_stage` 与 `shape_audit_failed`。新增 `joint_report.attempt_counters`（post / skeleton / unknown，缺标记计 unknown 不填 0）；`run_contract` 用它计数，任一失败 attempt 缺 bool 标记时 `post_optimization_failures=None`。`full_checkpoint` 改为与快速同一口径：成功合同 post 中位数 > 0 触发（`attempts`），缺字段记 `attempts_undetermined`；成功合同总尝试中位数改名 `success_attempts_median_diagnostic`。`run_batch`/`full_stage` 的 `complete` 把 unknown attempt、post 未确定计为未完成；quick CLI 未完成返回 3（不再走"triggered 为空即 0"）。
- **`rg` 依赖清单**（`QUICK_ATTEMPT_MEDIAN|success_attempts|post_optimization_failures|frechet|curve_before|curve_after|alpha_tried|R_lo|d_max`）：

| 位置 | 处理 |
|---|---|
| `joint_report.QUICK_ATTEMPT_MEDIAN` | 保留为历史诊断名，不再用于任何触发（注释标明） |
| `joint_report.quick_checkpoint` 的 post 中位数 | 保留（V8-13c 已是新口径）；`optimization_s>0` 推断的计数改名 `contracts_with_optimization_time_diagnostic` |
| `joint_report.full_checkpoint` 的 `success_attempts_median` | 已改：触发改用 post 中位数，旧值改名 `success_attempts_median_diagnostic` |
| `joint_report.distributions` 的 `success_attempts` | 已改名 `success_attempts_diagnostic`，另加 `post_optimization_failures` 分布 |
| `joint_monitoring.run_contract` post/skeleton 计数 | 已改：按 `optimization_entered` 事件（`attempt_counters`） |
| `joint_monitoring.group_reference_curves`、`curve_before/curve_after`、`frechet_blocks` | 已改：巡逻段、成员映射、各自弧长重采样、端点距离另报 |
| `joint_monitoring.full_stage` 的 `post_optimization_failures_median` | 保留（新口径字段） |
| `alpha_tried` / `ALPHA_SCAN` / `R_lo` / `d_max`（旧 `monitoring.py`） | 生产代码已删除；`runner/monitoring.py::rho_record` 读取 `alpha` 的旧 V8-12 记录函数冻结不用（V8-13/14 运行器不调用） |
| `v08/diagnostics/diversity.py::discrete_frechet` | 冻结，原样调用 |
| 历史 V8-13 报告 | 不修改 |

- **测试**（[tests_part5.txt](tests_part5.txt)）：V8-14 numeric 16/17，唯一失败 `test_phase_ratio_and_along_projection` 第 2 组断言（`1.0 is not None`）——即开工时登记的**疑似预期错误**（与裁定 7 冲突，见第 8 节），未改测试；其余 metrics 5 项（入口事件计数、quick/full 同口径、骨架成功率与人数档严格边界、attempt/形状分母、巡逻裁切）全部通过。V8-14 extra 5/5；V8-13 numeric 20/20（含 8.5 授权替换方法）、extra 8/8。
- **接线冒烟（执行方说明）：** 为确认第 7 部分代码路径在变队形骨架上可运行，在 `out/prototype/chain_smoke_o01_d0` 只跑了 **1 个合同**（o01_d0）的全链路，非批次、不计入任何检查点（[part5/chain_smoke_o01_d0.log](part5/chain_smoke_o01_d0.log)）：1 次 attempt 成功、`optimization_entered=True`、post=0；两成员三阶段诊断与巡逻段编组曲线（各 1530 点）正常生成。

## 6. 第 6 部分：只构造骨架的止损检查点 —— **触发，停在第 6 部分**

**命令**（代码目录，`OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1`）：
`python -B tools/v08/run_skeleton_monitoring.py --devset <仓库根>/docs/v08/V8-03/devset_v08.json --data-root "F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData" --cache "<运行根>\cache" --out "<运行根>\out\skeleton" --workers 8`；运行根 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-04_V8-14_skeleton`。2026-11-04 19:05:05 → 19:16:08（墙钟 662 s），**退出码 2（诊断触发）**。缓存由 V8-13 运行根 `cache` 复制（按几何键复用）。产物：`out\skeleton\{records.json, attempts.jsonl, summary.json, by_bin.csv, failures.csv, contracts\, telemetry\}`；仓库内副本 [part6/](part6/)（records/summary/by_bin/failures/运行日志/分析脚本与输出）。

**完整性：** 200/200 合同完成，业务键唯一，0 个实现异常、0 个 error 记录，`complete = true`。

### 6.1 U D.5 四项（严格比较，Fraction）

| 条件 | 分子/分母 | 实测 | 边界 | 结果 |
|---|---|---|---|---|
| 骨架合同成功率 < 95% | 140/200 | 70.0% | 190/200 不触发 | **触发** |
| 任一人数档比总体低 > 10 个百分点 | 1–4：106/110（96.4%）；5–8：29/56（51.8%）；9–12：5/34（14.7%） | 最大差 55.3 个百分点（9–12）；5–8 档差 18.2 | 恰 10 不触发 | **触发** |
| 成功合同骨架尝试中位数 > 1 | 140 个成功合同 | 1.0（75 个首次成功） | 恰 1 不触发 | 未触发 |
| 形状复核失败率 > 5%（分母为全部骨架 attempt） | 1456/1630 | 89.3% | 100/2000 不触发 | **触发** |

成功合同尝试次数直方：1×75、2×20、3×11、4×3、5×8、6×6、7×4、8×3、9/10/11/13/15/18 各 1、14×2、19×2。

### 6.2 分档、失败阶段与队形

- **设施数档：** 1 设施 63/85（74.1%）、2 设施 52/85（61.2%）、3 设施 25/30（83.3%）。**初速档：** [4,6) 45/67（67.2%）、[6,8) 39/61（63.9%）、[8,10] 56/72（77.8%）。（[part6/by_bin.csv](part6/by_bin.csv)）
- **attempt 级阶段（1630 次）：** `skeleton_ok` 140、`patrol_shape_audit` 1456、`start_route` 15、`ingress` 8、`egress` 7、`boundary_crossing` 3、`obstacle:obstacle_02` 1；**`turns`（turn_joint_set_empty）0 次**、`patrol_region`（证书为空）0 次。60 个失败合同最终分类均为 `budget_exhausted`（20 次用完）。
- **形状复核原因：** 1456 次全部含 `curvature`，其中 639 次同时含 `dwell`；没有一次 `lane_geometry`（栅格车道越界）——局部证书保证的几何部分实测无反例。1456 次中 **1431 次参考线最小曲率半径 ≤ 车道半跨 D**（车道越过曲率中心）；曲率失败的 D 中位数 58.3 m，参考最小曲率半径中位数 14.9 m。按队形：横排 1062/1140、梯形 394/435、**纵列 0/55**。按人数档：1–4 人 234/360、5–8 人 644/685、9–12 人 578/585。
- **队形与退让：** 140 个成功合同的实际队形为横排 63、纵列 46、梯形 31，**全部等于起点队形，没有一次宽度退让**（局部证书在这些圈心上对宽队形都成立）。梯形步长 15.3–23.8 m（中位数 19.7 m）。60 个失败合同的先验均非纵列（横排 28、梯形 16、loose 16），其 1200 次 attempt 只用过横排/梯形；先验为纵列的 46 个合同 46/46 成功。拓扑：环绕 51、折返 89。
- **证书诊断量（1630 个 attempt；指令 2.2 全局量，仅诊断）：** q 10.1–22.0 m；η = 7.071 m（= 2ε_f，ε_f = 5√2/2 m）；e_g 中位数 91.7 m（p90 243 m），e_s 中位数 46 m（p90 208 m），全局 e 中位数 141 m（p90 449 m），与附录第 2 节"e 中位数约 148 m"量级一致；局部证书最小余量 min(B−A) 中位数 196 m。
- **整体掉头集合（裁定 4）：** 193 次掉头全部找到；非空组合数中位数 6（最少 2）；单组合参数格 3.1 万–160 万（中位数 35.8 万），排列访问到第一个通过者的格点数中位数 105（p90 1249，最多 28.8 万）。掉头查询每 attempt 1.4–57 s（中位数 7.9 s）。
- **耗时：** 每 attempt 0.25–72 s（中位数 1.5 s）；每合同 2.6–90 s（中位数 20 s）；批次 662 s / 8 进程。

### 6.3 保留骨架复核（预置 8.7）

`test_preset_local_artifacts.py` 在 `out\skeleton` 上 **2/2 通过**（[tests_part6.txt](tests_part6.txt)）：200 条记录、业务键唯一、每条 `attempt_log` 长度 = attempts ≤ 20、形状失败逐条重计一致；140 个成功骨架逐个以冻结 `polyline_clearance` 独立重算整条成员曲线的 base 约束与巡逻裁切段的 patrol 约束，余量全部 ≥ 0；成员映射严格单调、turn_mask 内横向偏移恰为 0、成员集合完整。

### 6.4 结论

止损三项触发（成功率、人数档、形状复核率）；按指令 6.2 与用户要求，**停在第 6 部分，不运行第 7 部分**。这是诊断止损，不是物理判据失败，也不是 P0：保留骨架几何复核全部通过，没有输入、判据、冻结范围或确定性问题。

## 7. 第 7 部分：**未运行（第 6 部分止损）**

快速 20 合同、全量 200 + 多样性 100、5 合同单进程复跑均未运行；依赖它们的产物测试（`test_preset_local_artifacts` 的 quick/full 目录、V8-13 `test_preset_local_e2e.py`、`test_preset_local_reproduction.py`）标"未运行：第 6 部分止损"，测试未删除。第 7 部分代码（optimization_entered、阶段诊断、巡逻段 Fréchet、full 口径）已实现并有单元测试；第 5 部分记录的 1 合同接线冒烟不是第 7 部分的任何检查。drawn/retained 的 KS、Cramér's V 属第 7 部分，未计算。

## 8. 疑似预期错误、疑似设计问题与偏离

### 8.1 疑似预期错误（预置测试与附录裁定冲突；测试未改，该项停下）

- **8.3 `test_phase_ratio_and_along_projection` 末两条断言**：夹具参考速度 [2, 2, 0]，断言 `measured_ratio is None`、`ratio_reason == "reference_min_zero"`。裁定 7 规定只在参考速度 ≥ 0.5 m/s 的时段统计、端点起停不计，按裁定该夹具的比值为 1.0（实测 `AssertionError: 1.0 is not None`）。实现按裁定 7；该测试保持失败，等待规划审查方更新预期。同一方法前 4 条断言（0.5、1.0、沿迹 3、沿迹 2）通过。

### 8.2 与裁定不直接冲突、但需审查方知悉的预置测试口径

- **8.4 `certify_joint_candidates` / `choose_joint_turn`**：测试锁定"先全集认证、后抽样"的辅助函数，按测试实现并通过；生产按裁定 4 用"每组合一次随机排列、取第一个通过者"（`sample_joint_turn`），二者同分布（自加测试验证排列首通过者均匀）。`choose_joint_turn` 在生产中用于"非空组合等概率选一组"。
- **8.1 `admissible_arcs`**：按测试实现参数方位跨度规则并通过；生产按裁定 8 不用它筛选，只作诊断。
- **指令 8 "补充接口约定"的 parent 中点规则**：按裁定 1.2 取消，`radial_intervals(parent_intervals=…)` 取父区间内最长子段；预置测试未覆盖该分支。

### 8.3 疑似设计问题（实测证据；执行方未自行变通）

1. **局部证书只保证几何，不约束参考线曲率；宽队形因此在形状复核大面积失败，而队形退让从不发生。** 1456 次形状复核失败全部是曲率（1431 次参考最小曲率半径 ≤ D），纵列 0/55 失败。机理（o02_d0 a0 定位）：管上界 U⁺ 在相邻 1° 方位可突降约 100 m（障碍或他设施预警边被射线掠射，或"最长子段"在两段之间切换），A_j/B_j 是 5 行窗口的 max/min，形成台阶；360 控制点的正基平均只把台阶抹平到约 1–4°，在 ρ≈1000 m 处对应几十米尺度，参考线局部曲率半径约 15 m，小于横排半跨（中位数 58 m）。选队形只看局部证书（几何），证书对宽队形成立，退让链不被触发；下游曲率失败按规定又不能回到队形选择——于是 9–12 人档 5/34、5–8 人档 29/56。候选方向（需规划审查方裁定，执行方未实现）：(a) 把"参考曲率半径 > D 且车道曲率 κ/(1−κd) ≤ κ*"纳入队形可行判定，使退让由同一检验触发；(b) 在 [A_j, B_j] 内做受曲率约束的平滑（凸 QP）代替正基平均；(c) 降低几何平滑分辨率（更少控制点）并重证支撑集与凸包性质。三者都会改变指令 2.3 的固定方法或 U D.1.2 的判定，属于设计决定。
2. **大编组横排的收拢长度。** 按指令 3.1 的公式 L ≈ 2.74D，12 机横排 b=25 m 时 L ≈ 378 m（收拢、展开各一段）。本批次掉头集合没有出现空集（193/193），但成功的 9–12 人骨架只有 5 个，大编组折返的掉头可放置性实际没有被充分检验。
3. **全局 e 的量级。** e 中位数 141 m、p90 449 m，证实附录第 2 节的判断（原指令 2.2 的全局判定会大量误拒），裁定 1 的局部证书是必要的；本批次 `patrol_region`（证书为空）0 次。

### 8.4 执行中的偏离与说明

- 第 2、3 部分代码同在 `monitoring.py` 且互相依赖，随第 2 部分提交一同落地；第 3 部分提交为测试与原型核对。
- 接回点额外要求"下一次穿行长度 ≥ 2l*"：指令 3.3 要求两次掉头的形变支撑无重叠放置，执行方把它放进接回点集合，而不是事后拒绝。
- 掉头 Q 在 NODE_TOL_M 内且切向一致时为空连接，此时该 (R, 接回点) 的 25 个 (h₀, h₁) 格点几何相同，仍按 25 个格点计入均匀排列（保持参数格结构一致）；只影响泪滴在弧端接回的权重。
- 收拢/展开直线上的成员车道检查要求精确余量 ≥ 拱高界 δ = (6D/L²)·0.5²/8（插入节点时折线偏差的上界），不是经验容差。
- 骨架诊断不进确定性载荷：耗时只走 `last_attempt_timing()`、`telemetry/` 与 `attempts.jsonl` 的 timing 字段。

## 9. 修改清单、数字来源与复跑

- **`git diff --stat 0d2f0a3 HEAD -- "Multi-UAV SimpleGC"`**：18 个文件，+2844/−345。新增 `v08/motion/monitoring_band.py`、`v08/motion/monitoring_turn.py`、`v08/diagnostics/monitoring_skeleton.py`、`v08/runner/skeleton_monitoring.py`、`tools/v08/run_skeleton_monitoring.py`、`tests/v08/V8-14/`（6 个预置原样 + 1 个自加）；修改 `v08/motion/intents/monitoring.py`、`v08/motion/skeleton.py`、`v08/motion/optimize.py`（只有语义直线合并接入 6 行）、`v08/runner/joint_monitoring.py`、`v08/runner/joint_report.py`、`tests/v08/V8-13/test_preset_numeric_checkpoint.py`（仅 8.5 授权方法）。全部在 0.2 白名单内；`tools/v08/run_joint_monitoring.py` 未改。
- **冻结核对**（[snapshot_part1.json](snapshot_part1.json) / [snapshot_part6_start.json](snapshot_part6_start.json) / [snapshot_part6_end.json](snapshot_part6_end.json)）：160 个登记输入 SHA256/大小/mtime 三次一致；69 个冻结模块/配置/旧测试文件哈希不变（`v08/sim|criteria|sampler|scene|contract`、`configs/`、`config.py`、`diversity.py`、`optimize_checks.py`、`formation/path/nominal/connect/plan.py`、`runner/monitoring*.py`、V8-03…V8-12 测试）；冻结工作树 641a9b3、de4d115 干净；`SwarmData\v07_*` 目录集合不变，未写入。未在 `llm` 安装包；未推 `main`、未强推。
- **数字来源：** 360 方位 / 2 m（U C.2/D.1）；q = Δr/2 + 2R*·sin(Δφ/4)，R* 为圈心到目标预警外接框最远角；η = 2·`S.cg_patrol.field.eps` = 7.071 m；K ∈ U{4..8}（monitoring.spline_basis_min/max）；N_CENTERS = 6；预算 20；R_min 15/8/25 m（monitoring.turn_*_min_m）×1.05；MIN_STRAIGHT_M = 6 m；h 格 5×5（旧 `_build_turn` grid=5）；v⊥* = √(11.4² − 10²) = 5.474 m/s；κ* = 0.95·0.2/0.5 = 0.38 m⁻¹；方位覆盖 120°（criteria revisit）；阶段速度门 0.5 m/s（criteria coverage.effective_speed_min_m_s）；Fréchet 5 m。优化器全部设置与 `configs/v08/joint_opt.json` 相同、未改。
- **预置测试汇总**（以 [tests_part6.txt](tests_part6.txt) 为最终记录）：V8-14 numeric 16/17（失败 1 = 8.1 所列疑似预期错误）；local_geometry 1/1；local_artifacts（skeleton 目录）2/2；extra 5/5；V8-13 numeric 20/20（含 8.5 授权替换）、extra 8/8；V8-12 全目录 37/40（2 失败与基线相同，见 [tests_part2.txt](tests_part2.txt)）。V8-14 artifacts 的 quick/full 目录、V8-13 e2e/reproduction：**未运行（第 6 部分止损）**。
- **负责人复跑命令**（PowerShell 7，`Multi-UAV SimpleGC` 目录，新输出目录不得已存在）：

```powershell
$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'
C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B tools/v08/run_skeleton_monitoring.py --devset "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08\docs\v08\V8-03\devset_v08.json" --data-root "F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData" --cache "F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-04_V8-14_skeleton\cache" --out "F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-04_V8-14_skeleton\out\skeleton_owner_rerun" --workers 8
```

预期：约 11 分钟，退出码 2，检查点 `["success_rate","group_gap","shape_audit"]`、140/200、1456/1630；`records.json` 应与 `out\skeleton\records.json` 逐字节一致（确定性载荷；timing 只在 attempts.jsonl/telemetry）。执行方未做该字节对比，属于待复跑项。
- **环境：** Windows 11、PowerShell 7.6.9、Python 3.12.3、NumPy 2.5.3、SciPy 1.14.1、shapely 2.0.7、OpenBLAS 0.3.34、AMD64 Family 26（32 逻辑核）；执行模型 Claude Opus 5.5（`claude-opus-5-5`）。

## 10. 执行方观察（与上文事实分开）

- 局部证书本身工作正常：形状复核中没有一次几何（栅格车道）失败，`patrol_region` 0 次，掉头整体集合 193/193 非空，保留骨架独立复核全部通过。剩下的失败几乎全部是同一个机理：证书允许的参考线太"折"，宽队形的内侧车道越过曲率中心。
- 纵列 0/55 复核失败、先验纵列 46/46 成功，说明问题集中在"队形宽度与参考曲率的耦合"，不在环带、圈心或掉头。若审查方选择 8.3 第 1 条的方向 (a)，预计退让会大量发生（宽队形 → 梯形 → 纵列），人数档偏差可能转为队形分布偏差，届时需要另看队形的 drawn/retained 分布。
- 掉头参数格规模大（中位数约 36 万/组合），但裁定 4 的排列首通过者使访问格点中位数约百个；最坏单次掉头查询 57 s，没有成为批次瓶颈。

## 11. 提交与远端核对

| 部分 | 提交 |
|---|---|
| 1 | d3c0d1e |
| 2（含第 3 部分接入点） | 135bc69 |
| 3 | 5b41569 |
| 4 | 573a6a4 |
| 5 | bb36c0f |
| 6（运行前代码） | d10936d |
| 6（结果与报告） | 6b5ece4 |

推送后 `git ls-remote origin`：`refs/heads/review/v08/V8-14-skeleton = 6b5ece4ddf9e8cbdf7e6dda436bf0e2916236a8e`、`refs/heads/dev/v0.8 = 0d2f0a35adcb90df31a15b210f89a13c7d499c9f`（本节自身随下一提交推送，最终分支头以该提交为准）。本项未合并进 `dev/v0.8`。

---

# V8-14b：曲率约束形状构造（返工，2026-11-04）

> 依据：`claude/v08/V8-14b_曲率约束形状构造裁定_20261104.md`（SHA256 `30d71c93…cc16d88`）。只改裁定第 3 节各条，其余照 V8-14 指令与附录。上文第 0–11 节为 V8-14 原执行记录，保留不改。

## B.1 实现（提交 `a1396b6`）

- **形状 = 曲率约束线性规划（3.1）**：`monitoring_band.shape_lp`。半径为 M = 120 控制点（3°）的周期三次 B 样条；在每个方位行 j 与相邻两行中点（中点区间取两行交集，曲率 A 取两行较大者）上约束 A ≤ ρ ≤ B 与 −κ_max·A² ≤ ρ − ρ'' ≤ κ_max·A²；目标最小化 Σ_j |ρ(φ_j) − t_j|，t_j = A_j + u(φ_j)(B_j − A_j)，u 为裁定 5 的 K 基 logistic 随机函数（引入松弛变量）；`scipy.optimize.linprog(method="highs")`（SciPy 1.14.1 已在 `llm`，未装包）。基矩阵由冻结 `path.periodic_radius_derivs` 逐列求值，与生产采样同一函数。κ_max = min(κ*/(1+κ*D), 1/(1.05·15 + D))，κ* = `kappa_limit(0.5, 0.2)` = 0.38 m⁻¹，1.05 = `joint_opt.buffer_turn_factor`，15 = `monitoring.turn_u_min_m`。
- **复核（3.1.5）**：`exact_curvature_review` 在 1440/圈 方位上用 κ = (ρ² + 2ρ'² − ρρ'')/(ρ² + ρ'²)^{3/2} 检查 |κ|(D + 15.75) ≤ 1 与 |κ|/(1 − |κ|D) ≤ κ*；之后照常运行原 `_ring_ok` 三项；任一失败计 `patrol_shape_audit`（原因 `exact_curvature` / 原三项）。
- **选队形（3.2）**：`loop_query`/`retrace_query` 在局部证书（A_j ≤ B_j，仍为必要部分）之上要求同一线性规划可行（零目标）；构造用同一约束集加目标求解。梯形步长二分不变，判定换成该检验。
- **折返弧的可行集合**：弧的位置约束用弧证书（邻域在弧端夹取）；曲率线性化中的 A 取方位段级局部交集，使"弧可行"对子弧单调（子弧位置约束只放宽、曲率约束不变）。于是：整圈/整段 LP 可行 ⇒ 全部端点对可行；否则按起点单调扫描（先试最远候选、倍增 + 二分）求每个起点的最远可行终点，结果与逐对求解相同（自加测试穷举核对）。
- **授权测试修订（3.3）**：`test_phase_ratio_and_along_projection` 末两条断言改为 `measured_ratio == 1.0`、`ratio_reason is None`；文件 SHA256 `b0d83416…2cc5f6` → `05d31c4e…05eb2ee`，diff 见 [v14b_test_3_3.diff](v14b_test_3_3.diff)。其余预置测试未改。
- **自加测试** `tests/v08/V8-14/test_extra_curvature_lp.py` 6/6：κ_max 公式；台阶夹具上 LP 解满足行/中点区间与线性化曲率约束；LP 解通过精确复核、紧跟 100 m 台阶的曲线被拒绝；圆上 κ = 1/R 与 κ(D+15.75)=1 边界；同一 (A,B,κ_max) 下可行性 LP 与带目标 LP 同判且覆盖可行/不可行；折返单调扫描与逐对穷举一致。
- **测试**（[tests_v14b_impl.txt](tests_v14b_impl.txt)）：V8-14 numeric 17/17、local_geometry 1/1、extra 11/11；V8-13 numeric 20/20、extra 8/8；V8-12 37/40（2 失败与基线相同）。

**偏离说明：** 裁定 3.1.1 要求折返弧用"同间隔的夹持样条"。冻结的 `path.py` 只有周期 `spline_arc` 图元（采样、曲率、成员派生都经由它），新增夹持图元需要改冻结文件。执行方改为：折返弧同样用 120 控制点（3°）的周期样条，只在弧所在方位段施加约束与目标，支撑之外的控制值不影响飞行段（取最近已用控制值，仅为数组完整）。在弧上它与同间隔均匀样条的函数空间相同，差别只在弧端不夹持；需审查方确认是否接受。

## B.2 第 6 部分重跑 —— **未触发**（提交 `1ae7646`）

命令同第 6 节，输出 `out\skeleton_v14b`；2026-11-04 20:56:57 → 21:09:52（773 s，8 进程），**退出码 0**。200/200 完成、0 异常、`complete = true`。仓库副本 [v14b/part6/](v14b/part6/)。

| 条件（严格） | 实测 | 结果 |
|---|---|---|
| 成功率 < 95% | 200/200 | 未触发 |
| 任一人数档低于总体 > 10 个百分点 | 1–4：110/110；5–8：56/56；9–12：34/34 | 未触发（差 0） |
| 成功合同骨架尝试中位数 > 1 | 1.0（直方：1×159、2×23、3×8、4×4、5×3、6×1、8×2） | 未触发 |
| 形状复核失败率 > 5% | 0/282 | 未触发 |

- **attempt 级阶段（282 次）：** `skeleton_ok` 200、`ingress` 44、`start_route` 15、`boundary_crossing` 9、`egress` 9、`turns`（整体掉头集合为空）5；形状复核 0、`patrol_region` 0。设施档 85/85、85/85、30/30；初速档 67/67、61/61、72/72。
- **精确曲率：** 282 个进入复核的形状最小曲率半径 17.2–394 m（中位数 93 m），全部满足 κ(D+15.75) ≤ 1 与车道曲率 ≤ κ*；线性化未出现一次不保守的反例。
- **队形：** 200 个合同全部未退让（抽签倾向 → 实际：1–4 人 column→column 31、echelon→echelon 28、loose→abreast 26、abreast→abreast 25；5–8 人 abreast 27、echelon 11、column 10、loose→abreast 8；9–12 人 loose→abreast 11、abreast 10、echelon 8、column 5）。梯形步长 15.2–24.3 m（中位数 20.7 m）。与裁定第 2 节原型"12 机横排 44/69 需退让"不同：生产中每 attempt 有 6 个圆心候选，且环绕不可行时可改折返，宽队形总能在某个圆心上找到可行 LP。
- **耗时：** 每 attempt 0.55–151 s（中位数 11.2 s）；LP 每 attempt 2–1291 次（中位数 2），LP 墙钟 0.013–28.9 s（中位数 0.047 s）；单次构造 LP 5–50 ms（中位数 26 ms）；掉头查询中位数 9.5 s（最长 142 s）；批次 773 s。
- **保留骨架复核：** 预置 8.7 在 `out\skeleton_v14b` 上 2/2 通过（[tests_v14b_part6.txt](tests_v14b_part6.txt)）。
