# V8-13 联合时空轨迹优化：监视单段 — 报告

执行日期 2026-11-03 起。开发工作树 `Simulation-v08`，审查分支 `review/v08/V8-13-joint-opt`。
本报告随各部分逐步补全；最终提交号以 `git ls-remote` 输出为准（见对话回报）。

**实际使用的模型：** Claude Opus 5.5（`claude-opus-5-5`），Claude Code 桌面版。

## 结论（先看这里）

> **2026-11-04 V8-13b 返工：** 结果见文末"V8-13b"一节，优先于下方第 4–6 节关于第 3–5 部分的结论。标定通过；快速批次 20/20 成功，检查点 2 因成功合同尝试次数中位数 2.5 > 1 触发，停在第 4 部分。

**状态：第 1、2 部分完成；第 3 部分实现完成但数值标定无合格权重（"优化设置未确定"）；第 4 部分代码与预置测试完成、快速集已选定，但 20 合同完整链路因权重缺失未运行，检查点 2"未完成"；第 5 部分未开展。** 没有触发任何 P0；两个止损检查点：检查点 1 明确未触发，检查点 2 未形成数据。

- **检查点 1（未触发）：** J ∈ {2,4,6,8,10,14} × 11 个合法格点（附录 9.1）全部完成，J=2 最大积分步跟踪误差 0.0862 m ≤ 0.5 m；\(J_{\rm plan}=14\) m/s³，实测管 0.0971 m，已写入 `configs/v08/joint_opt.json`。
- **第 3 部分：** \(\lambda_j=1.858\times10^{-5}\)（E/Q 中位数，5 格有效）；μ = 2^k，k = 0…52 无合格向量。k ≤ 3 对向互换间距残差（低于 3 m）；k = 4–12 互换在 h=0.5 时硬检查已满足但 500 次迭代用完；k ≥ 13 线搜索异常终止。补充诊断（k = 4/8/12/16 全夹具）显示圆障碍与 4/12 人大夹具在 500 次内都不收敛。7 个权重未写入配置；`test_preset_numeric_optimizer.py` 报前提未完成（0/7 运行）。
- **第 4 部分：** 指令 4.1 列出的旧时长拒绝、间距拒绝、下游退让、圈数/穿行压缩、重抽循环全部删除，队形只由宽度决定（`width_then_build`）；`test_preset_numeric_flow` 4/4、`test_preset_numeric_checkpoint` 5/5、`test_preset_numeric_tracking` 4/4 通过。快速集 o01–o09、o11 × draw 0/1 已确定；快速批次因前提未完成退出码 3。
- **疑似预期错误：** 无。
- **边界：** 160 个登记输入文件 SHA256/大小/mtime 不变；冻结工作树 HEAD 不变且干净；未写 `SwarmData\v07_*`；未在 `llm` 安装包；未推 `main`、未强推。
- **需要规划审查方决定：** 在"有限平方罚 + L-BFGS-B 一次 + ftol=ε、gtol=√ε、500 次"这套组合下标定不出权重。是否改变收敛判定、λ_j 规则、迭代上限或约束求解形式，见第 10 节执行方观察 1、6。

## 1. 开工复述与执行前提

### 1.0 依据文件

原件在 `_handoff\2026-11-03_V8-13_joint-opt\`，原样归档到仓库 `claude/v08/`：

| 文件 | 行数 | SHA256 |
|---|---|---|
| `V8-13_联合时空轨迹优化_监视单段_执行指令_20261103.md`（下称"指令"） | 1964 | `87779e0845209b82dced333df7cc7d4a04c91e7ec7d3a3a2be67b5ad4a21d93a` |
| `V8-13_GPT指令评价与裁定_20261103.md`（下称"附录"） | 58 | `573ccf8314d37ed7ddf38570891ae4c819c907637da54f82c86fd263960ebc0d` |

**材料优先级：** 附录第 3、4 节 → 指令（其余部分）。指令内部：U → J47–50 → C12 → r4 → 协作规程。

### 1.1 目标

把监视单段的运动链路改为"随机任务骨架 → 单编组联合时空优化（固定时间，均匀三次样条，L-BFGS-B 一次求解）→ 逐成员按时间跟踪仿真 → 拼接 → V8-11 段核验与实测有效性检查"。骨架保留语义和多样性，物理约束交给优化；1800 s 编组时长上限取消，只作对照统计。只做登记开发集 40 族的监视单段、公共抽签第 0 组；不生产正式数据集，不扩多段。

### 1.2 五个部分

| 部分 | 内容 | 止损 |
|---|---|---|
| 1 | 快进合并 V8-12 固定提交 `cb6b58e`（第 5 部分已取消的后续提交 `bc6a679/dd968e3/73714b4` 不合并）、推 `dev/v0.8`、建审查分支、归档指令、锁定预置测试哈希、基线测试 | — |
| 2 | `v08/sim/tracking.py` 新时间跟踪层；合成参考（S 曲线直线/刹停、近圆、U 形）在 J∈{2,4,6,8,10,14} 下实测；定 \(J_{\rm plan}\) | **检查点 1**：J=2 最大跟踪误差 > 0.5 m 即停 |
| 3 | `v08/motion/optimize.py`、`optimize_checks.py`：稀疏三次样条、端点与直线法向等式消元、带状 Cholesky 预条件、解析梯度、单次 L-BFGS-B；合成数值标定定 \(\lambda_j\) 与 \(\mu=2^k\) 罚权；写 `configs/v08/joint_opt.json` | 标定无合格向量则不进第 4 部分 |
| 4 | 删旧控制流（时长拒绝、间距拒绝、下游退让、圈数/穿行压缩、重抽）；`skeleton.py` 宽度先定再一次构造；`joint_monitoring.py` 唯一 20 次全链路预算；快速集 10 族 × 2 合同完整端到端（单进程） | **检查点 2**：成功 <16/20、成功尝试中位数 >1、优化耗时中位数 >60 s、任何误收 |
| 5 | 40 族 × 5 = 200 合同 8 进程；5 合同单进程逐字节复跑；同条件多样性 10 族 × 10 种子；分布、三图、报告 | 超过 2 h 停派发并在已完成处汇报 |

### 1.3 两个检查点

- **检查点 1（2.4 节）：** 测量全集（按附录裁定 9.1 的合法格点）中 J=2 的最大水平跟踪误差（积分步口径）> 0.5 m 触发；恰 0.5 合格；J=2 未测/欠覆盖为"未完成"，不是通过。触发即停在第 2 部分，提交、推送、汇报。
- **检查点 2（4.4 节）：** 20 合同分母固定；四项严格比较，任一触发即停在第 4 部分，报告所有触发项，提交、推送、汇报。

### 1.4 冻结范围

不写：冻结工作树 `Simulation-fe-prod-r3`（`641a9b3`，开工时干净）、`Simulation-fe-s3`（`de4d115`，开工时干净）；`SwarmData\v07_*`（只读，内容与 mtime 不变）。只导入：`task_v07/`、`scene_v07/`、`swarm_sim/`、`configs/criteria/`、`configs/fast_dynamics/`、`configs/generator/geometry_v07_r1.json`。不改：`v08/sim/` 已有文件、`v08/criteria/`、`v08/config.py`、`v08/sampler/`、`v08/diagnostics/diversity.py`、已有配置、已有测试、`v08/runner/monitoring.py`、`monitoring_report.py`。只允许按 0.2 节白名单新增文件，并只在 4.1 节范围内修改 `v08/motion/intents/monitoring.py`、`v08/motion/plan.py`。conda `llm` 只运行不装包；不扰动动力学、不覆盖每机参数、不调 \(\tau,k_{\rm pos}\)。不推 `main`、不强推。

### 1.5 20 次共享预算

一个合同固定一次公共抽签与一次监视合同；每个 attempt 只递增 `RngKey.attempt`，依次走"骨架 → 联合优化（一次 L-BFGS-B）→ 每成员跟踪仿真 → 拼接 → 段核验 → 有效性检查"，全部通过才成功。20 次预算贯穿整条链路；不允许 `plan_segment` 内部 20 次再套外层 20 次，不允许优化器内多次求解择优，不允许下游失败后改队形/圈数/穿行数。

### 1.6 第 9 节未决项与本次处理依据

第 9 节 6 项已由附录第 3 节裁定（见 1.7）；本次按裁定实现，不再作为未决项。若实现中出现裁定未覆盖的新情况，按"记录后继续"处理，写入第 8 节。

### 1.7 我对附录第 3 节（对指令第 9 节的裁定）的理解

1. **9.1 J=2 与圆弧：** 恒速圆弧 \(\|j\|=a_n^2/v\)。圆弧案例对每个 (J, v) 取 \(a_n=\min(3,\sqrt{J v})\)，标注"受 J 约束"，这是合法格点而非冒充；例 J=2、v=4 时 \(a_n=\sqrt8\approx2.83\)。直线 S 曲线、U 形、刹停仍按指令 2.2 原协议。每个 J 的测量全集 = 这些合法格点（包括 U 形的 4、6、\(\sqrt{45}\) 三档）；检查点 1 与 \(J_{\rm plan}\) 都只在这个全集上判定。实现上：圆弧缩放的目标法向值由 3 改为 \(a_n(J,v)\)，其余构造（K 倍增、峰值核对）不变；若 \(a_n(J,v)<3\) 则在行内标 `jerk_limited=true`。
2. **9.2 有限罚函数残差：** 加入"优化目标缓冲"（工程余量，Project Instructions 第五节第 7 条第三类）。**只用于罚函数阈值**：间距罚用 3.25 m；几何罚余量 world 36 m、alert 11 m、障碍 36 m；速度、法向、切向加速度、jerk 罚的上限各乘 0.95。**硬检查仍用原阈值** 3 / 35 / 10 / 35 m 和原动力学上限（12、3、2、\(J_{\rm plan}\)），不放宽。第 3 部分标定须报告"缓冲前残差"（即相对于原阈值的残差，同时报相对缓冲阈值的残差）分布；残差超过缓冲时如实报告失败，不得加大缓冲。实现上：几何罚中 `lower_clearance` 已减去 minimum_m（35/10），因此缓冲余量以"额外 1 m"进入罚函数：\(g_c-1\)，归一化尺度 \(m_c\) 用 36/11；配置中记录缓冲值及来源。
3. **9.3 固定时间与有限 jerk：** 时间分配保持固定，不改 release/end。贴近骨架是软目标，jerk 受限导致的平滑以几米内的沿航向偏离体现，由优化器吸收。直线法向钳定与相邻语义段冲突时如实报 `optimize_equalities_inconsistent`。若它在快速检查中导致止损，按检查点 2 停下汇报，不自行改时间或表示方式。
4. **9.4 名义结束时刻：** 同意指令 3.2：移动样条终点 = release + travel（`Nominal.travel_s`），不含 hold；2 s 终端保持由跟踪层在首次满足终止条件后追加。
5. **9.5 标定范围：** 同意：跟踪管 0.5 m 只在检查点 1 使用，生产中只作诊断；物理有效性以仿真后实测 2 m 门禁与段核验为准。
6. **9.6 优化后编组参考：** 同意 5.4 定义 \(c_{\rm after}(s)=c_{\rm before}(s)+\frac1N\sum_i[p^{\rm opt}_i(t_i(s))-s_i(t_i(s))]\)，用于合并 Fréchet 阈值；逐成员同 ID 前后距离另报。

### 1.8 我对附录第 4 节（数值机制简化）的理解

1. **取消硬检查的动态数值容差：** 指令 3.5 节 \(\eta_q=\gamma_nS_q\) 与 `optimize_numerical_uncertain` 原因码均取消。所有硬检查直接用 float64 与原阈值比较（如 \(d\ge3\)、\(\|v\|\le12\)），不加也不减任何容差；缓冲已经在阈值与优化结果之间留出 0.25 m / 1 m / 5% 的余地。
2. **连续几何认证改为弦高界：** 不做 Bezier 细分。对每条样条，在绝对 0.1 s 时刻点（以及移动起止端点）形成折线，对每个区间（相邻时刻点之间）的弦用冻结 `polyline_clearance` 求精确余量，再减去弦高上界 \(a_{\max}\Delta t^2/8\)，\(a_{\max}\) 取该区间内样条加速度范数的实际最大值（三次样条加速度在每个节点区间内线性，取区间端点范数最大值即为该区间上界）。结果 ≥ 原阈值（即 `polyline_clearance` 返回值减弦高界 ≥ 0，因 `polyline_clearance` 已减 minimum_m）即通过。world 内 35、所有障碍外 35、所有 alert 外 10 逐个做。
3. **动力学连续极值：** 保留按节点区间解析求极值（速度二次、加速度一次、jerk 常量），极值候选为区间端点与导数实根；比较时不加数值容差（同第 1 条）。
4. **其余数值设置照原指令：** L-BFGS-B 的 maxiter=500、maxls=20、maxfun=10001、maxcor=10、ftol=ε、gtol=√ε；带状 Cholesky 预条件化（含舍入保护）；初始化一次确定性破对称；权重按 3.4 节合成标定（\(\lambda_j\) = E/Q 中位数；其余六项共同 \(\mu=2^k\)）。

### 1.9 已知的旧预期冲突（不升级为本项阻塞）

V8-12 报告记录 `tests/v08/V8-12/test_preset_numpy_checkpoint.py::test_each_diagnostic_threshold` 第 4 断言（逐族 Fréchet）与 V8-12 附录"合并中位数"裁定冲突，为已裁定的疑似预期错误。本项不运行 V8-12 全目录测试，不把这一已知失败当作新阻塞。

### 1.10 运行位置

- 指令 0.4 节规定运行根 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-03_V8-13_joint_opt\`（下划线），与指令包所在目录 `2026-11-03_V8-13_joint-opt`（连字符）不同。按指令原文使用下划线目录作运行根，指令包目录不写入。
- 登记清单 `docs/v08/V8-03/devset_v08.json`（仓库根）。

## 2. 第 1 部分：快进合并与基线

**环境：** Windows 11 Pro 10.0.26200；PowerShell 7.6.9；conda `llm`：Python 3.12.3、NumPy 2.5.3、SciPy 1.14.1（导入时警告"需要 NumPy <2.3.0，检测到 2.5.3"；L-BFGS-B 冒烟正常，`BSpline.design_matrix` 存在）、shapely 2.0.7；BLAS 为 SciPy 自带 scipy-openblas 0.3.34（NumPy 构建配置见 `env.txt`）；CPU AMD64 Family 26 Model 68，32 逻辑核。单线程环境变量 `OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1`。完整记录：[env.txt](env.txt)。本机 SciPy `_minimize_lbfgsb` 默认 `maxcor=10, maxls=20` 已在 `env.txt` 中打印核对。

**Git：**

| 步骤 | 结果 |
|---|---|
| 开工前 | 工作树干净，HEAD `73714b4`（`review/v08/V8-12-monitoring`）；本地与远端 `dev/v0.8` 均为 `4d2cf5df48187671f0dd9aa0018a69adac829911`；`dev/v0.8` 是 `cb6b58e` 的祖先 |
| `git merge --ff-only cb6b58e30b622514a0e48be53a6fba1ed9d00f8f`（在 `dev/v0.8`） | Fast-forward `4d2cf5d..cb6b58e` |
| `git push origin dev/v0.8` | `4d2cf5d..cb6b58e  dev/v0.8 -> dev/v0.8` |
| `git ls-remote origin refs/heads/dev/v0.8` | `cb6b58e30b622514a0e48be53a6fba1ed9d00f8f refs/heads/dev/v0.8` |
| `git switch -c review/v08/V8-13-joint-opt` | 新建，基于 `cb6b58e`（远端此前无同名分支） |

V8-12 分支上 `cb6b58e` 之后的 `bc6a679`、`dd968e3`、`73714b4`（第 5 部分，已取消）未合并。

**预置测试锁定（第 6 节原样提取，UTF-8 无 BOM、LF、末尾一个换行）：** 6 个文件的 SHA256 与指令 6.8 表逐一相同。

| 文件 | SHA256 | 与 6.8 一致 |
|---|---|---|
| `test_preset_numeric_tracking.py` | `477579cf687876c53f5b373c5682a3a0c8803f463e0bcb12fedbdfa93fe64db5` | 是 |
| `test_preset_numeric_optimizer.py` | `a71714814c7a0f3f3a0e18613655b86ec80cf68240dcdb016ccf31e3db0abe40` | 是 |
| `test_preset_numeric_flow.py` | `9dcf2ef778f642ab8581e8eac565c757d83a804a0b813d22d91b12570c664969` | 是 |
| `test_preset_numeric_checkpoint.py` | `b7aaaccc7e8aa92fc8c83a5156a500e79d2e52ebee46547c190b49740b9c6a68` | 是 |
| `test_preset_local_e2e.py` | `200293b688a562bc2e96fd7366a73addc4150033ed18ac6d0323d9a09db4d166` | 是 |
| `test_preset_local_reproduction.py` | `ffe54a7b56f30605eeea2b8cbc5b695d897948c10b2ecb53a449bc291fb75890` | 是 |

**基线测试**（cwd = `Multi-UAV SimpleGC`，完整输出 [tests_part1.txt](tests_part1.txt)）：

| 命令 | 结果 | 退出码 |
|---|---|---|
| `python -B -m unittest discover -s tests/v08/V8-08 -p "test_*.py" -v` | 24/24 OK | 0 |
| `python -B -m unittest discover -s tests/v08/V8-11 -p "test_preset_*.py" -v` | 30/30 OK | 0 |
| `python -B -m unittest discover -s tests/v08/V8-12 -p "test_preset_numpy_geometry.py" -v` | 4/4 OK | 0 |

## 3. 第 2 部分：按时间跟踪与检查点 1

**结论：检查点 1 未触发（J=2 最大误差 0.0862 m ≤ 0.5 m），测量 complete。\(J_{\rm plan}=14\) m/s³，实测管（J=14 行）0.0971 m。** 已写入 `configs/v08/joint_opt.json`（`kind=pending_measurement`，source 含证据哈希与测量代码提交 `145a85a`）。规划 D_lane 仍为 3 m。

**实现：**
- `v08/sim/tracking.py`：`TimeReference`、`reference_velocity`（\(u_{xy}=v_{\rm ref}+\tau a_{\rm ref}+k_{\rm pos}(p_{\rm ref}-p_{xy})\)，\(u_z=k_{\rm pos}(h-p_z)\)，每个 20 ms 积分步按绝对时刻求参考）、`run_tracking_segment`（冻结 `member_config()` 无覆盖、无扰动；释放须在 0.1 s 网格且 = 20 s + 0.1 s 网格延迟；参考起点距当前位置 ≤ 1e-6 m、高度一致；移动结束后首次满足 1 m / 0.15 m/s 才开始 2 s 保持；预算 \(B=1.1(T-r)+30+r+2\) 向上取整到帧，超出为 `sim_timeout`；final 的 `end_state/executed_switch_tau_us=None`；`pieces` 放 `TrackingRecord`，含积分步/输出帧两套误差、核心饱和比例、积分末态）、`select_jerk_plan`（任一行未完成或缺 J=2 行即 `incomplete`；J=2 > 0.5 触发；否则取最大合格 J，不假设单调）。
- `v08/diagnostics/joint_calibration.py`：三类合成参考（直线 S 曲线兼刹停/保持、近圆、U 形），均从静止起、含 20 s 预释放与 2 s 保持；所有峰值从最终系数按区间多项式求连续极值（`optimize_checks.dynamic_extrema`）。
- `tools/v08/run_joint_monitoring.py --stage tracking`：薄入口。

**构造事实：**
- 直线：七段 S 曲线 → 内部单节点、两端钳制的三次 B 样条，Greville 点带状插值；各段多项式复核残差（无量纲）≤ 4.5e-13；缩放后峰值恰为 A=2、J、V（全部 24 例）。
- 近圆：按附录 9.1 只有 (J=2, V=4) 受 J 约束（\(\sqrt{8}=2.828<3\)）。恒速段 jerk = \(a_n^2/v\) 恰为 J，smoothstep 起止过渡使峰值 jerk 严格大于 J，K 倍增不能终止（与指令 2.2"9/V>J 不做无意义倍增"同理），故此格不倍增，保持峰值速度、空间与时间同乘 \(f=\sqrt{j_{\rm peak}/J}\)，**实际法向 2.744 m/s²（请求 2.828）**、jerk 2.000、切向 0.728，如实报告，见第 8 节偏离。其余 23 个近圆格点 K=1 即满足切向 ≤ 2、jerk ≤ J，实际法向 3.000（舍入超 1 ulp 时同法吸收）。拟合用均匀三次 B 样条、原型节点 1 s，静止端点按 \(c_0=c_1=c_2=p(0)\)（末端同理）精确消元，法方程带状求解。
- U 形：先按实际最小曲率半径归一到 15 m（首末节点区间由精确消元是直线、v→0 处浮点残差会造出伪曲率，故最小半径在 \([h,T-h]\) 上求），再取 \(\alpha=\max(V_b/V,\sqrt{A_{nb}/3},\sqrt{A_{tb}/2},\sqrt[3]{J_b/J})\)。三档实际峰值：V=4.000/6.000/6.708，法向 0.742/1.781/2.313——速度是约束项，最大法向未到 3（1 s 节点拟合的半圆在低速端曲率最大），如实报告。

**每个 J 一行**（积分步口径；完整 66 例见 [part2/cases.json](part2/cases.json)，汇总 [part2/summary.json](part2/summary.json)，运行日志 [part2/tracking_run.log](part2/tracking_run.log)）：

| J (m/s³) | 例数 | complete | 最大位置误差 m（积分步 / 输出帧） | 最大速度误差 m/s | 最坏案例 | 核心加速度/jerk 饱和比例最大 | 超时 |
|---|---|---|---|---|---|---|---|
| 2 | 11/11 | 是 | 0.0862 / 0.0861 | 见 summary | 近圆 V=4（受 J 约束） | 0 / 0 | 0 |
| 4 | 11/11 | 是 | 0.0971 / 0.0971 | 见 summary | 近圆 V=4 | 0 / 0 | 0 |
| 6 | 11/11 | 是 | 0.0971 / 0.0971 | 见 summary | 近圆 V=4 | 0 / 0 | 0 |
| 8 | 11/11 | 是 | 0.0971 / 0.0971 | 见 summary | 近圆 V=4 | 0 / 0 | 0 |
| 10 | 11/11 | 是 | 0.0971 / 0.0971 | 见 summary | 近圆 V=4 | 0 / 0 | 0 |
| 14 | 11/11 | 是 | 0.0971 / 0.0971 | 见 summary | 近圆 V=4 | 0 / 0 | 0 |

直线案例误差随 J 从 0.062（J=2）增至 0.072 m（J=14）；近圆在 J≥4 各行相同（这些格点不受 J 约束，参考与 J 无关）。所有案例 `status=ok`，窗口（预释放、加速、匀速/减速、结束后、保持）分项误差在 cases.json 的 `measurement.windows`。`select_jerk_plan` 输出 `{"triggered": false, "j_plan": 14.0, "reason": "selected"}`。

**局限：** 66 个合成参考下的事实，不证明所有三次样条都在 0.5 m 管内（附录 9.5）；生产中管只作诊断。

**测试：** `test_preset_numeric_tracking.py` 4/4 OK（[tests_part2.txt](tests_part2.txt)，退出码 0）。

## 4. 第 3 部分：联合时空优化器与数值标定

**结论：优化器、解析梯度与独立硬检查已实现并通过数学自检（中心差分 24/24 坐标一致）；但按指令 3.4 的合成标定协议，μ = 2^k（k = 0…52，上限 2^k ≤ 1/ε）中没有任何一组权重让全部"应成功"夹具在 h=1 与 h=0.5 下同时"通过独立硬检查且 L-BFGS-B 正常收敛"。按指令 3.4 报告"优化设置未确定"：7 个权重不写入配置，不进入快速批次（第 4 部分检查点 2 因此"未完成"，第 5 部分未运行）。** 这不是第 0.5 节的 P0，也不是两个止损检查点之一；是标定协议本身规定的前提未形成。

### 4.1 实现（`v08/motion/optimize.py`、`optimize_checks.py`）

- **表示：** 每成员均匀三次 B 样条，节点 \(h(-3,\dots,M+3)\)、\(M=\lceil T/h\rceil\)、控制点 \(M+3\)，评价域截在 \([0,T]\)，\(T\) 不舍入、不延长；区间内用均匀三次基矩阵 \(M_B\) 及其逐阶导数（与 Cox–de Boor 同一组基）构造 CSR（每行 4 个非零）。`SplineTrajectory.evaluate/pva` 域外 p 保持端点、导数为零；端点校验取域内单侧值。
- **等式：** 两端 p/v/a 与语义直线法向 \(n^\top(c_k-q)=0\)（对与开区间相交的全部基函数支撑）统一写成行；按变量连通块（零系数不建边，x/y 自然分块）做带主元 QR，秩阈值 \(\epsilon\max(m,n)\sigma_{\max}\)；残差超界返回 `optimize_equalities_inconsistent` 与 A/b/秩/残差见证。零右端的块精确得到零特解（合成直线测试的 y 控制点精确为 0）。
- **代价：** 按指令 3.3 八项；评价点为"绝对 0.1 s 网格 ∪ 移动端点 ∪ 节点"、梯形权重，除以 \(\sum_iT_i\)；平滑与 jerk 罚按节点区间解析求和；间距只取共同可见（释放至移动结束 + 2 s 保持）的整数 10 Hz 帧，除以共同帧总时长。**附录裁定 9.2 缓冲**：间距罚阈值 3.25 m、几何罚在 `lower_clearance`（已减 35/10）上再留 1 m 且归一尺度 36/11、速度/法向/切向/jerk 罚上限 ×0.95；硬检查用原阈值。
- **距离场梯度：** 在新文件中按 `field.values[name]` 四角数组算双线性值与梯度（不改 field.py），格外按 \(g(\Pi p)-\|p-\Pi p\|\) 延拓；边界格导数与 `_locate` 相同（右侧格，最右用左侧）。
- **预条件：** \(H_0=Z^\top G Z\)（\(G\) 为贴近 + \(\lambda_j\) 平滑的精确 Hessian），按成员带状 Cholesky；舍入保护 \(\epsilon\|H_0\|_\infty I\) 只在分解失败时加并报告（本次未触发）；失败返回 `optimize_conditioning`。
- **初值：** 带等式加权最小二乘骨架投影（解析一步）；一次确定性破对称：成员对在 \(d<3.25\) 且相对位置与相对速度精确共线（叉积为 0）的帧上，沿相对速度左法向（零相对速度用 ENU x 轴）各推缺口一半；障碍按骨架切向法向中余量增大的一侧（横向梯度精确为 0 取左法向）推缺口；按基权重分配到控制点，经消元坐标投影回等式零空间。初始化前后系数存入 `diagnostics`。
- **求解：** `scipy.optimize.minimize(method="L-BFGS-B", jac=True)` 一次；maxiter 500、maxls 20、maxfun 10001、maxcor 10、ftol ε、gtol √ε。软件不成功 → `optimize_not_converged`；收敛但硬检查不过 → `optimize_residual`。
- **硬检查 `check_physical`（附录第 4 节简化）：** 端点/直线等式残差 ≤ √ε·max(1,max|c|)（只用于等式，与预置测试同口径）；动力学按区间求 |v|、|a_t|、a_n、|j| 连续极值（端点 + 导数分子多项式全部根的实部：多取候选只会多算真实函数值，不会高估，也不漏近重根峰值），直接与 12/2/3/J_plan 比较；几何为 0.1 s 时刻点折线的 `polyline_clearance` 精确弦余量减 \(a_{\max}\Delta t^2/8\)（节点落在 0.1 s 网格上，每条弦都在单个节点区间内，加速度线性，\(a_{\max}\) 取弦两端加速度范数较大者）≥ 0；间距为共同可见整数 10 Hz 帧最小距离 ≥ 3 m。无数值容差，`optimize_numerical_uncertain` 已取消。

### 4.2 标定协议与结果

完整记录 [part3/numerics.json](part3/numerics.json)（每候选 × 夹具 × h 的迭代数、终止原因、最大投影梯度、贴近 RMS/最大、各项残差相对原阈值与缓冲阈值、端点误差、耗时、峰值内存），运行日志 [part3/numerics_run.log](part3/numerics_run.log)，逐 k 摘要 [part3/numerics_summary_by_k.txt](part3/numerics_summary_by_k.txt)。

**标定集**（第 6.2 节构造在 `joint_calibration` 内独立重写，不从测试导入）：常值 8.3 s、常值 2000.3 s、语义直线（无冲突）、对向互换、圆障碍、超法向加速度（允许失败）、交叉参考 4/12 人 × 1000/2000 s（N/2 对互换直线，第 k 对横向平移 3k m，长度 4 m/s × 时长）。

**\(\lambda_j\)（E/Q 中位数）：** 排除恒定夹具与 E ≤ ε·⟨‖s‖²⟩/L0² 的格点（附录取消了 3.5 节 γ_n 界，此处用最简单的相对舍入界），有效 5 格：

| 夹具 | h | E | Q | E/Q |
|---|---|---|---|---|
| line_equality | 1 | 3.549e-11 | 1.910e-06 | 1.858e-05 |
| line_equality | 0.5 | 7.313e-14 | 1.901e-06 | 3.846e-08 |
| head_on_swap | 1 | 7.013e-13 | 2.755e-07 | 2.546e-06 |
| excess_normal | 1 | 9.890e-02 | 9.068e-02 | 1.091 |
| excess_normal | 0.5 | 7.344e-02 | 10.93 | 6.719e-03 |

\(\lambda_j=1.858\times10^{-5}\)。其余 15 格（恒定 4 格、E 在舍入界内 11 格）排除。

**μ = 2^k 搜索（k = 0…52；同一 k 下首个应成功夹具失败即判该 k 不合格，其余夹具记"未运行"）：**

| k | 首个失败 | 现象（缓冲前残差 = 相对原阈值） |
|---|---|---|
| 0–2 | head_on_swap h=1，`optimize_residual` | L-BFGS-B 按梯度准则正常收敛，但 10 Hz 最小间距 2.08 / 2.50 / 2.82 m < 3 m（有限罚残差，9.2） |
| 3 | head_on_swap h=1，`optimize_residual` | 间距 3.014 m 已合格，法向加速度峰值超 3 m/s² 0.012 |
| 4–12 | head_on_swap h=0.5，`optimize_not_converged` | 硬检查本身全满足（间距 3.12–3.25 m，动力学低于上限），但 500 次迭代用完未达 ftol=ε / gtol=√ε；同 k 下 h=1 正常收敛 |
| 13、17、19–52 | head_on_swap h=1，`optimize_not_converged` | `ABNORMAL_TERMINATION_IN_LNSRCH`（9–164 次迭代）；间距 ≈ 3.25 m、动力学满足 |
| 14–16、18 | head_on_swap h=0.5，`optimize_not_converged` | 500 次上限或线搜索异常 |

常值、长时常值、语义直线三类夹具在所有 k 下两种 h 都通过（nit=0，独立再现误差为 0）。圆障碍与交叉大夹具在选择流程中一次都未轮到（每个 k 都在互换处先失败）；4.3 的补充诊断给出它们的表现。**残差超过缓冲的情况只出现在 k ≤ 3**（间距残差 −0.92…+0.01 m 相对 3 m）；k ≥ 4 时间距残差均落在缓冲内，失败全部来自收敛判据。按附录不加大缓冲。

**开发期观察（未进入选择）：** 以临时权重手动探查圆障碍夹具，几何罚单独存在时 94 次迭代收敛；加入法向/切向/jerk 罚后，在 \(\lambda_j\approx10^{-8}\) 需 4000–7000 次迭代，\(\lambda_j=1\) 也需约 1000–1400 次。原因是 \(\lambda_j\) 很小时预条件只覆盖贴近项，骨架投影绕行后的高频动力学罚在 y 坐标下严重病态（指令 3.4 所说的 \(h^{-6}\)）。

### 4.3 补充诊断（不参与选择）

在 k = 4、8、12、16（λ_j 同上）上把全部 10 个夹具 × 两种 h 都跑一次，不因前面失败跳过；只用于解释，不参与 μ 选择、不写配置。完整记录 [part3/diagnostic.json](part3/diagnostic.json)，逐行摘要 [part3/diagnostic_summary.txt](part3/diagnostic_summary.txt)。

| 夹具 | k=4 | k=8 | k=12 | k=16 |
|---|---|---|---|---|
| 常值 8.3 s / 2000.3 s、语义直线（h=1、0.5） | 全部通过 | 全部通过 | 全部通过 | 全部通过 |
| 对向互换 h=1 / h=0.5 | 通过 / 500 次未收敛（间距 +0.12） | 通过 / 500 次未收敛（+0.24） | 通过 / 500 次未收敛（+0.25） | 通过 / 500 次未收敛（+0.25） |
| 圆障碍 h=1 / h=0.5（精确余量） | 余量 −41.6 / −41.6 m | −16.3 / −13.2 m，500 次 | +2.1 / +1.4 m，500 次 | +3.8 / +4.0 m，500 次 |
| 超法向加速度（允许失败） | 通过 / 通过（动力学满足上限） | 通过 / 500 次 | 线搜索异常 / 500 次 | 线搜索异常 / 线搜索异常 |
| 交叉 4 人 × 1000/2000 s | 间距 −1.0～−1.1 m | 间距 −0.12～−0.14 m，500 次 | 间距 −0.0（比 3 m 低舍入量级），500 次 | 同左 |
| 交叉 12 人 × 1000/2000 s | 间距 −2.0 m | −1.2～−1.4 m，500 次 | −0.4～−2.0 m，500 次 | h=1 −0.0；h=0.5 −1.3 m 且切向超 1.02 m/s² |

（"间距"一列为 10 Hz 最小间距减 3 m；圆障碍一列为精确余量 = 到圆的距离 − 35 m。）

要点：
- 圆障碍夹具在 k ≥ 12 时几何已满足原 35 m，但两种 h 都在 500 次时未收敛；与 4.2 开发期观察一致。
- 交叉大夹具按"第 k 对横向平移 D_lane = 3 m"构造，相邻两对同向成员的参考间距恰为 3 m，低于 3.25 m 缓冲，所以间距罚在整段时间都激活。k ≥ 12 时 4 人夹具的间距停在 3 m 以下一个舍入量级（硬检查按原阈值直接比较，判失败）；12 人夹具在 h=0.5 时更差。所有大夹具在 500 次内都未收敛；12 人 × 2000 s、h=0.5（95 928 变量）单次求解约 38–52 s。
- 四个 k 下没有任何一个让全部应成功夹具通过，与 4.2 的结论一致。

### 4.4 测试

`test_preset_numeric_optimizer.py`：**setUpClass 报前提未完成**（`load_settings` 抛 `SettingsIncomplete`：7 个权重缺键），7 个测试方法 0 个运行，退出码 5。这是指令第 6 节"测量配置未齐全时数值求解测试应明确报前提未完成，不能默认补数"的情形，不是疑似预期错误。完整输出 [tests_part3.txt](tests_part3.txt)。开发期用临时权重对同一梯度夹具做的中心差分自检：24 个坐标全部在 \(\epsilon^{1/3}(1+|fd|+|g|)\) 内（非预置测试结论）。

## 5. 第 4 部分：骨架改造、端到端与检查点 2

**结论：代码改造完成，预置测试 6.3 4/4、6.4 5/5 通过；快速集已按 4.3 节规则确定并落盘；但因第 3 部分优化设置未确定，20 合同完整链路未运行，检查点 2 状态为"未完成"（不是"通过"，也不是"触发"）。第 5 部分未开展。**

### 5.1 删除与改动（对照指令 4.1；完整 diff [part4/skeleton_refactor.diff](part4/skeleton_refactor.diff)，两文件 +178/−382）

| 旧位置（cb6b58e） | 改动 |
|---|---|
| `build_candidate(…, duration_only=False)` 及占位计划分支 | 删除参数与分支；一次构造完整骨架 |
| 名义总时长 `duration > nominal_budget_s` 拒绝 | 删除；`nominal_duration_s` 照常记录 |
| 连续时间间距拒绝（`continuous_minimum`） | 删除调用与导入；`required_separation_m` 记 None |
| 名义重访/驻留/圈层筛查拒绝 | 改为只记录（`wit["screen"]`）；硬检查移到优化后 `check_monitoring` |
| `_budget_ok`、`_inner_edge`、`_time_for_length`、`BUDGET_SLACK`、`_find_ring` 的预算过滤与预算区分类 | 全部删除；`_find_ring` 只按几何/走廊/覆盖，圈心候选由调用方一次抽出、供所有队形共用 |
| `_Setup.__init__` 按 1800 s 生成 `self.sev` | 删除；速度事件在 `build_candidate` 中按 \(T_{\rm upper}\)（参考曲线、恒 4 m/s、v0=v_end=0 的 `speed_profile`+`nominal_time`）一次 `draw_speed_events` 再 `map_speed_events`；保存 T_upper、事件、映射误差；提案已给事件时不重抽 |
| `_Build` 的 `self.sev`、`assemble(duration_only)` | 删除 |
| `_is_budget`、`_shift_spec`、`_delta_for_mean`、`_repair_budget`、`REPAIR_ITERS`、`BUDGET_TARGET` | 删除 |
| `_finish_loop`（lap_lo 试造、slack/cap、重抽圈数、laps_fallback_to_min） | 用原 spec 的 laps 一次 prepare/assemble |
| `_finish_retrace`（缩穿行数、allowed 循环、半径内移） | 用原 traversals 一次 prepare/assemble |
| `RETREAT_STAGES`、`propose_and_build` 的下游退让链 | 删除；`propose_and_build` 只经 `skeleton.width_then_build(chain, width_probe, build)` 选队形并构造一次 |
| `_draw_loop`/`_draw_arc` 的 `N_REDRAWS` 重抽 | 删除；一个 attempt 一套形状，α 缩放保留并记账 |
| 梯形 `b*(.75,.5,.33)` 阶梯 | `_echelon_payload`：先试 b；否则候选 b_lat = 单车道极坐标可行带每段径向区间宽 /(n−1)、落在 [3,b) 内，按降序二分找最大可行值，并以真实 `_find_ring` 核对 |
| `plan.py:_final_failure` 的时长下界近似为空分支 | 删除；新增 `final_failure` 包装供新 runner；`plan_segment` 保留但 V8-13 runner 不调用 |

新增记录：`witnesses["target_id"]`、`witnesses["turn_ranges"]`（折返掉头的圆弧图元 → 各成员曲线弧长区间，供优化后曲率复核）。删除的旧原因字段：`duration_budget`、`budget_region`、`budget_repair_shape`、`separation`（骨架级）、`nominal_revisit/nominal_dwell/nominal_layers`（骨架级）、`laps_budget_cap`、`laps_fallback_to_min`、`traversals_budget_cap`、`radius_shift_budget`。

**函数级调用图（生产）：** `run_contract` → `run_attempts`（唯一 20 次）→ `attempt_chain`：`plan_attempt` → `propose_and_build` → `width_then_build`（`width_probe` → `_find_ring` / `_echelon_payload`；`build` → `_build_with_ring` → `_draw_loop|_draw_arc` → `_finish_loop|_finish_retrace` → `_Build.prepare/assemble` → `build_candidate`）→ `optimize_segment`（`references_from_skeleton` → `solve_joint`（含 `check_physical`）→ `check_monitoring`）→ 每成员 `run_tracking_segment` → `stitch` → `verify_segments` → `visible_track` + `check_validity`。下游失败退让为 0 由 `test_downstream_failure_does_not_change_formation` 与源码 AST 检查证明。

**`check_monitoring`（优化后语义硬检查）：** 冻结 `crossing_analysis`（不传 skip_ranges）在 0.1 s 时刻点折线上重查单次直线穿越、两侧 10 m、目标入圈前 100 m、未穿越部分离边界 10 m；折返掉头圆弧区间（按骨架名义时间映射）的连续最小曲率半径 ≥ 15/8/25 m；终点离所有 warning ≥ 50 m；释放至移动结束 + 2 s 的 10 Hz p/v 调 `screen_member`（重访、无驻留、圈层 ≤ 1）。优化样条 C²，速度非零处曲率连续，不存在"不连续异号曲率接点"，按 C12 连续曲率变号豁免，不另查过渡直线。

**真实数据冒烟（非结果）：** order 1–2 的 4 个合同前 1–3 个 attempt 正常构造，名义时长 1899–3648 s（不再被 1800 截断），T_upper 3223–5505 s，`references_from_skeleton` 给出每成员语义直线区间。

### 5.2 快速集（指令 4.3）

[part4/quick_selection.json](part4/quick_selection.json)：o01、o02、o03、o04、o05、o06、o07、o08、o09、o11 各 draw 0、1（20 个 key）。覆盖：设施数 1 档 12、2 档 6、3 档 2 个合同；机数最大族 order 11（12 机）入选；初始指令速度 < 5.5 的合同 3 个（o01_d0 5.36、o05_d1 4.36、o09_d1 5.11）。只用公共抽签元数据，未做规划选样。

### 5.3 检查点 2

**未完成。** `load_settings` 因 7 个权重缺键抛 `SettingsIncomplete`；CLI 写 `summary.json`（`precondition: incomplete`）并以 3 退出（[part4/summary.json](part4/summary.json)、[part4/quick_run.log](part4/quick_run.log)）。20 个合同的成功数、尝试中位数、优化耗时中位数、P0 均无数据，不能写成通过或触发。

**开发冒烟（非检查点数据，临时权重 k=8，o01_d0 第 0 个 attempt）：** 骨架 3.9 s；联合优化 7509 变量、14.7 s，500 次迭代用完（`optimize_not_converged`），另有 uav_06 在终点刹停处切向加速度 2.164 > 2 m/s²（固定名义时间 + 两端 a=0 + 有限 jerk 的 9.3 现象）；该 attempt 未进入仿真。只说明生产链路可执行。

### 5.4 测试与回归（[tests_part4.txt](tests_part4.txt)）

| 测试 | 结果 |
|---|---|
| V8-13 `test_preset_numeric_tracking.py` | 4/4 OK |
| V8-13 `test_preset_numeric_flow.py` | 4/4 OK |
| V8-13 `test_preset_numeric_checkpoint.py` | 5/5 OK |
| V8-13 `test_preset_numeric_optimizer.py` | 前提未完成（setUpClass），0 运行 |
| V8-13 `test_preset_local_e2e.py` | 未运行：没有 quick/full 输出目录 |
| V8-13 `test_preset_local_reproduction.py` | 本阶段不适用（第 5 部分） |
| V8-08 全部 | 24/24 OK |
| V8-11 预置 | 30/30 OK |
| V8-12 `test_preset_numpy_geometry.py` / `test_preset_numpy_motion.py` | 4/4、7/7 OK |
| V8-12 `test_own_part3.py`（V8-12 执行方自加） | 1/3 OK、2 失败：断言 `nominal_duration_s ≤ 1800`，正是决定 50 取消的旧行为；未修改该旧测试 |

**输入与冻结范围：** 160 个登记输入文件的 SHA256/大小/mtime 与 V8-12 第 2 部分快照逐项一致（[inputs_snapshot_part4.json](inputs_snapshot_part4.json)）；`Simulation-fe-prod-r3`（641a9b3）、`Simulation-fe-s3`（de4d115）HEAD 不变且干净；未写 `SwarmData\v07_*`。

## 6. 第 5 部分

**未开展。** 前提不满足（检查点 1 通过；检查点 2 未完成）。`--stage full|diversity|rerun` 入口返回 3 并提示需检查点后接入；8 进程调度、复跑比较、多样性与三张图均未实现运行路径、未运行。

## 7. 分支与提交

| 项 | 值 |
|---|---|
| V8-12 快进 | `dev/v0.8`：`4d2cf5d` → `cb6b58e30b622514a0e48be53a6fba1ed9d00f8f`（`git ls-remote` 核对远端一致）；`bc6a679/dd968e3/73714b4` 未合并 |
| 审查分支 | `review/v08/V8-13-joint-opt`，基于 `cb6b58e` |
| 第 1 部分 | `8c578f0` 归档指令、锁定预置测试、基线 |
| 第 2 部分 | `145a85a` 跟踪层与测量；`b1c8046` J_plan/实测管配置与报告 |
| 第 3 部分 | `8e9c46c` 优化器、硬检查、标定（优化设置未确定） |
| 第 4 部分 | `658dea4` 骨架改造、运行器、检查点函数、快速集 |
| 收尾 | 本报告所在提交（见对话中 `git ls-remote` 结果） |

没有推 `main`，没有强制推送；V8-13 未合并到 `dev/v0.8`。

## 8. 改动清单、偏离、疑似预期错误与设计问题

**改动文件（相对 `Multi-UAV SimpleGC/`，均在 0.2 节白名单内）：** 新增 `v08/sim/tracking.py`、`v08/motion/optimize.py`、`v08/motion/optimize_checks.py`、`v08/motion/skeleton.py`、`v08/runner/joint_monitoring.py`、`v08/runner/joint_report.py`、`v08/diagnostics/joint_calibration.py`、`configs/v08/joint_opt.json`、`tests/v08/V8-13/test_preset_*.py`（6 个，原样）、`tools/v08/run_joint_monitoring.py`；修改 `v08/motion/intents/monitoring.py`、`v08/motion/plan.py`。仓库根新增 `claude/v08/V8-13_*`（指令归档）与 `docs/v08/V8-13/`。`git diff --stat cb6b58e` 见 [diff_stat.txt](diff_stat.txt)。未改 `v08/sim/` 已有文件、`v08/criteria/`、`config.py`、`sampler/`、`diversity.py`、旧 runner、已有配置与已有测试。

**偏离指令之处（均已在正文说明）：**
1. 近圆 (J=2, V=4) 受 J 约束格点：附录给定 \(a_n=\sqrt{8}\)，但 smoothstep 起止过渡使峰值 jerk 严格大于 J，指令 2.2 的 K 倍增无法终止。我不倍增，而是保持峰值速度、空间与时间同乘 \(\sqrt{j_{\rm peak}/J}\) 使 jerk ≤ 2；实际法向 2.744（请求 2.828）。这一格的误差 0.086 m 是 J=2 行的最大值，远低于 0.5 m，不影响检查点结论。
2. U 形最小曲率半径只在 \([h,T-h]\) 上求：首末节点区间由静止端点精确消元，数学上是直线；v→0 时浮点残差会造出伪曲率。
3. 近圆/U 形原型拟合的端点等式用均匀样条静止端点的精确消元（\(c_0=c_1=c_2\)）代替一般 KKT；数学上等价。
4. \(\lambda_j\) 的"机器舍入噪声"排除界用 \(\epsilon\langle\|s\|^2\rangle/L_0^2\)（指令所指的 3.5 节 γ_n 界已被附录取消）。
5. 障碍破对称不只在"横向梯度精确为零"时触发，而是对初值上所有违反缓冲的评价点，沿骨架法向中余量增大的一侧推缺口（横向梯度为零才取左法向）。理由：双线性距离场的格子取法使中心线上横向梯度不为零但极小，若只在精确为零时推，圆障碍夹具会沿航向挤压。该改动未能改善圆障碍夹具的迭代数（见 4.2 开发期观察）。
6. 运行根目录按指令 0.4 用 `_handoff\2026-11-03_V8-13_joint_opt\`（下划线），与指令包目录名（连字符）不同。
7. `run_batch` 目前只有单进程路径（快速批次本就规定单进程）；8 进程调度属第 5 部分，未实现。

**疑似预期错误：** 无。6 个预置测试原样放置，SHA256 与 6.8 一致；已运行的 13 个测试方法全部通过；`test_preset_numeric_optimizer.py` 因前提未完成未运行，不是预期错误；`test_preset_local_*` 未到运行阶段。

**第 9 节疑似设计问题的处理状态：**

| 项 | 裁定方 | 处理 |
|---|---|---|
| 9.1 | 附录第 3 节 | 按合法格点测量，见第 3 节及偏离 1 |
| 9.2 | 附录第 3 节 | 已加缓冲；标定显示 k ≤ 3 时残差超缓冲（如实报告，未加大缓冲），k ≥ 4 时残差在缓冲内但收敛判据不满足 |
| 9.3 | 附录第 3 节 | 时间固定；开发冒烟中出现终点刹停处切向超限（2.164 > 2），即该问题的表现；未改时间或表示 |
| 9.4 | 附录第 3 节 | 移动样条终点 = release + travel；2 s 保持由跟踪层追加 |
| 9.5 | 附录第 3 节 | 管只作检查点 1 与诊断 |
| 9.6 | 附录第 3 节 | 定义已采纳；第 5 部分未运行，未计算 |
| **新：收敛判据与有限罚的组合** | 待规划审查方 | 见第 10 节执行方观察 1；按指令 3.4 停在"优化设置未确定"，未自行更改 ftol/gtol/maxiter、λ_j 规则或求解形式 |

## 9. 复跑命令与环境

在 `Multi-UAV SimpleGC` 下（PowerShell 7），先设 `$env:OMP_NUM_THREADS=1; $env:OPENBLAS_NUM_THREADS=1; $env:MKL_NUM_THREADS=1; $env:NUMEXPR_NUM_THREADS=1`，Python 统一前缀 `C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B`：

```powershell
python -B tools/v08/run_joint_monitoring.py --stage tracking --out "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-03_V8-13_joint_opt/out_rerun/tracking"
python -B tools/v08/run_joint_monitoring.py --stage numerics --out "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-03_V8-13_joint_opt/out_rerun/numerics"
python -B tools/v08/run_joint_monitoring.py --stage quick --devset "../docs/v08/V8-03/devset_v08.json" --data-root "F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData" --cache "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-03_V8-13_joint_opt/cache" --out "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-03_V8-13_joint_opt/out_rerun/quick" --workers 1
```

预期：tracking 退出 0（检查点 1 未触发，J_plan=14）；numerics 退出 3（`selected=null`，耗时约 3 分钟）；quick 退出 3（写出相同 `quick_selection.json` 后报前提未完成）。

云端纯数值测试（无需真实数据与 shapely）：

```powershell
python -B -m unittest discover -s tests/v08/V8-13 -p "test_preset_numeric_tracking.py" -v
python -B -m unittest discover -s tests/v08/V8-13 -p "test_preset_numeric_flow.py" -v
python -B -m unittest discover -s tests/v08/V8-13 -p "test_preset_numeric_checkpoint.py" -v
```

环境：Windows 11 Pro 10.0.26200；PowerShell 7.6.9；conda `llm`：Python 3.12.3、NumPy 2.5.3、SciPy 1.14.1（导入时警告"需要 NumPy <2.3.0"；L-BFGS-B、BSpline、PPoly、solve_banded/cholesky_banded 实测可用）、shapely 2.0.7；scipy-openblas 0.3.34；AMD64 32 逻辑核；单线程环境变量如上。本项随机性只来自既有 `RngKey`/`rng_for`。

## 10. 执行方观察（与事实分开）

1. **标定失败的主因是"有限罚 + 极严收敛判据 + 固定 500 次"的组合，不是可行性。** 互换夹具 k=4–12 在 h=0.5 时，硬检查本身已经满足（间距 3.12–3.25 m），只是 500 次迭代内没有把相对下降做到 ε；k ≥ 13 时罚项刚度大，线搜索在 ε 精度下失败。若审查方希望这条链路能走下去，可考虑的方向（需要上层裁定，我没有采用）：(a) 收敛判定以"硬检查通过 + 有限"为准、软件状态只记录；(b) ftol/gtol 放宽到与物理精度相称的值；(c) 改用约束形式（增广拉格朗日或 SLSQP 类）或分段求解；(d) λ_j 的 E/Q 规则在光滑合成参考上给出 ~1e-5，使预条件几乎不覆盖 jerk，建议以动力学罚的尺度另定 λ_j。
2. 圆障碍夹具在开发期探查中需要 1000–7000 次迭代，即使互换问题解决，它在 500 次内大概率也不能收敛；大编组夹具（12 人 × 2000 s，h=0.5 约 9.6 万变量）一次评价约 64 ms，500 次迭代约 40–60 s，接近检查点 2 的 60 s 中位数阈值。
3. 骨架改造后名义时长普遍超过 1800 s（冒烟中 1899–3648 s），骨架随之更长，联合优化变量数与 12 人编组的间距对数相应增加；这对第 5 部分的 2 小时预算是实际压力。
4. V8-12 执行方自加测试 `test_own_part3.py` 的两条 `≤ 1800 s` 断言随决定 50 失效，建议后续工作项正式退役或改写这两条（本项不改旧测试）。
5. 第 2 部分所有 J 行都合格（最大 0.097 m），J_plan 取到 14 = 冻结核心上限；直线案例误差随 J 只从 0.062 增到 0.072 m，说明在 0.5 m 管下 jerk 不是跟踪的约束项。
6. 交叉大夹具的构造（相邻两对横向平移恰为 D_lane = 3 m）使同向邻居的参考间距从头到尾都低于 3.25 m 缓冲，间距罚全程激活；这类夹具实际在测"把整片编组撑开 0.25 m"，与"交叉互换"本意不同。若审查方复核标定集，建议平移步距取 D_lane 加缓冲或更大。

## V8-13b：按规划审查方求解形式裁定返工（2026-11-04）

依据 `_handoff\2026-11-03_V8-13_joint-opt\V8-13b_优化器求解形式裁定_20261104.md`（原样归档 `claude/v08/`，SHA256 `69a5b0e8f36d6db8b3d2af1d386da3fa53e27d74fe7ef3a4af3767de6e258293`）。裁定第 2 节优先；其余照 V8-13 指令与附录。止损与 P0 规则不变。

### V8-13b.0 结论（先看这里）

**状态：按裁定返工后，第 3 部分标定通过；第 4 部分快速批次 20 合同全部完成，检查点 2 触发一项（`attempts`：成功合同尝试次数中位数 2.5 > 1），按规则停在第 4 部分，未做第 5 部分。** 没有触发任何 P0。

| 检查点 2 项（U D.3.4，严格比较） | 实测 | 结果 |
|---|---|---|
| 成功 < 16/20 | 20/20 | 未触发 |
| 成功合同尝试次数中位数 > 1 | **2.5**（1×7、2×3、3×3、4×3、5、6、8、9 各 1） | **触发** |
| 单合同优化耗时中位数 > 60 s | 19.7 s（20 个合同全部进入优化；最大 85.4 s） | 未触发 |
| 保留段违反 P0 门禁 | 0（`retained_p0_violations=[]`；6.5 节冻结 V8-11 核验对 20 个保留合同独立复核 3/3 通过） | 未触发 |

**重复尝试的来源（62 次 attempt 中失败 42 次，[v13b/part4/attempt_analysis.txt](v13b/part4/attempt_analysis.txt)）：** 34 次是骨架随机构造失败（巡逻形状 17、折返掉头 8、起点路由 4、边界穿越 3、入圈 1、出圈 1）；8 次是优化后的语义硬检查失败（掉头曲率半径低于 8/25 m 6 次、驻留 3 次、重访 1 次；同一 attempt 可同时多项）。**联合优化的物理硬检查、仿真、段核验、有效性检查没有一次失败。** 检查点 2 的触发主要来自骨架构造层：V8-12 在单个 attempt 内部有 `N_REDRAWS` 重抽与下游退让，这些失败被吸收在 1 次 attempt 里；V8-13 第 4.1 节按要求删除了这些循环，失败就显式落到 20 次预算上。


### V8-13b.1 我对裁定第 2 节的理解与落实

| 条 | 理解 | 落实位置 |
|---|---|---|
| 2.1 PHR 增广拉格朗日 | 目标 f = F_ref + λ_j F_smooth；不等式 g_k ≤ 0 逐采样点（同 V8-13 3.3 的点：0.1 s 网格 ∪ 端点 ∪ 节点；jerk 每节点区间一个；间距为共同可见 10 Hz 帧），阈值为缓冲值：间距 (3.25−d)/3、几何 −(g_c−1)/m_c（m_c 取 3.3 节的 35/10）、速度/法向/切向/jerk 上限 ×0.95；L = f + (ρ/2)Σ max(0,g+λ/ρ)² − Σλ²/(2ρ)，Σ 为逐约束直接求和（不加积分权）；λ=0、ρ=1；每轮内层 L-BFGS-B maxiter 200、SciPy 默认 ftol/gtol、热启动；每轮后原阈值硬检查（V8-13 3.6 + 附录第 4 节），过则停；否则 λ ← max(0, λ+ρg)，最大违反量 max_k max(g_k,0) 未降到上一轮的 1/4 以下则 ρ×10（首轮与初值比）；最多 8 轮；成功 = 有限且硬检查全过，SciPy success 只记录；用完仍不过 → `optimize_residual`（附最坏约束）。预条件、破对称、等式消元不变。 | `v08/motion/optimize.py`（`_blocks`、`value_grad`、`update_multipliers`、`max_violation`、`solve_joint`） |
| 2.2 λ_j = 1 | 取消 E/Q；配置 `weight_smooth=1`（definitional） | `configs/v08/joint_opt.json` |
| 2.3 取消 μ 搜索 | 固定设置把全部夹具在 h=1、0.5 各跑一次；h=1 下应成功夹具全过即通过；h=0.5 只诊断 | `joint_calibration.calibrate_optimizer` |
| 2.4 大夹具 | 相邻成员对横向平移 15 m，保留对向交叉 | `joint_calibration.CROSS_LATERAL_M` |
| 2.5 参考加速度留余量 | 骨架名义时间以 a_lat_ref = 2.7、a_lon_ref = 1.8 调同一个 `speed_profile`：通过 `member_nominal(..., guidance=reference_guidance())` 传参（`LoadedConfig.values` 的副本），不改 `v08/sim/`、`nominal.py`、`connect.py`、冻结配置；`build_candidate` 的释放延迟改用 monitoring.py 内与 `connect.release_delays` 同算法、只换 guidance 的 `_release_delays_ref`；T_upper 与 `map_speed_events` 也用同一参考参数；`references_from_skeleton` 与 `check_monitoring` 的名义时间同源 | `skeleton.reference_guidance`、`intents/monitoring.py` |
| 2.6 旧 1800 s 断言 | 删除 `tests/v08/V8-12/test_own_part3.py` 中两条 `nominal_duration_s ≤ 1800`（依据决定 50）；同文件 `rec["duration_s"] ≤ 1800` 那条位于已不会进入的 `radius_shift_budget` 分支内，不在裁定所列两条之中，未动 | 该测试文件 |

**与裁定无关、为可运行而做的实现改动（不改数学）：**
- 连续动力学极值改为向量化（批量伴随矩阵求根；候选点规则与逐区间版相同）。300 条随机样条与 66 条第 2 部分参考上与逐区间版逐值一致（最大相对差 6.2e-16），3600 区间耗时 0.064 s 对 3.96 s。逐区间版保留为 `dynamic_extrema_loop`。
- `SplineTrajectory.pva` 标量快路径（预存每区间多项式系数）；跟踪器每个积分步只取一次参考（原来取两次，数值完全相同）。
- 第 5 部分运行器、复跑比较、多样性编组参考曲线（指令 5.4 定义）、5.5 分布与三图；失败合同另存最后一个 attempt 的骨架/优化/违规见证（`failure_witness.json`，确定性载荷）。

### V8-13b.2 第 3 部分重新标定（通过）

固定设置（`configs/v08/joint_opt.json` SHA256 `f4cb99514eaf5b9f9751e52d02ca7a938bc3a9cd62753102e331d4282ad4a7c1`），10 个夹具 × h=1、0.5 各一次（[v13b/part3/numerics.json](v13b/part3/numerics.json)、[numerics_run.log](v13b/part3/numerics_run.log)）：

| 夹具 | h=1（判定） | h=0.5（诊断） |
|---|---|---|
| 常值 8.3 s / 2000.3 s、语义直线 | 通过，1 轮，0 次迭代 | 通过 |
| 对向互换 | 通过，1 轮 19 次，间距 3.23 m | 通过，1 轮 31 次 |
| 圆障碍 | 通过，2 轮 400 次（第 1 轮最大违反 0.31，ρ→10 后通过） | 通过，2 轮 400 次 |
| 超法向加速度（允许失败） | 通过（λ_j=1 下平滑成近静止，动力学在上限内） | 通过 |
| 交叉 4 人 × 1000/2000 s（15 m 平移） | 通过，1 轮 10–16 次，0.2–0.35 s | 通过 |
| 交叉 12 人 × 1000/2000 s | 通过，1 轮 3–11 次，0.9–1.5 s | 通过 |

h=1 下应成功夹具全部通过硬检查 → 标定通过。预置 `test_preset_numeric_optimizer.py` 7/7 通过（V8-13 时因前提未完成未运行）。

### V8-13b.3 第 4 部分快速批次

快速集与 V8-13 相同（`quick_selection.json` 逐字节一致）：o01–o09、o11 × draw 0/1。单进程，墙钟 2051 s。输出 `_handoff\2026-11-03_V8-13_joint_opt\out\quick_v13b\`（393 MB，原始轨迹不入库）；入库 [v13b/part4/records.json](v13b/part4/records.json)、[summary.json](v13b/part4/summary.json)、[quick_run.log](v13b/part4/quick_run.log)。

**分布（[v13b/part4/distributions.txt](v13b/part4/distributions.txt)，20 个成功合同、99 个成员）：**
- 骨架→优化水平偏离（移动期，10 Hz 评价点）：逐成员最大值 p10/p50/p90/max = 2.43 / 2.79 / 3.32 / 3.47 m，RMS p50 0.11 m；
- 每合同成功 attempt 的内层迭代：p50 = 200（第 1 轮用满 maxiter 后硬检查即通过），最少 35；
- 名义时长 1767–3649 s，19/20 超过旧 1800 s（只作对照）；
- 各阶段耗时（成功合同合计全部 attempt）：骨架 3–33 s、优化 5.9–85 s、仿真 8–153 s、核验 0.4–19 s；仿真随人数线性增长（12 人约 130–150 s）。

**测试（[tests_v13b_part4.txt](tests_v13b_part4.txt)）：** `numeric_flow` 4/4、`numeric_checkpoint` 5/5、`local_e2e`（quick 输出，冻结 V8-11 `verify_segments` 与 `check_validity` 独立重算）3/3。`local_reproduction` 属第 5 部分，未运行。

**边界：** 160 个登记输入 SHA256/大小/mtime 与 V8-12 快照一致（[v13b/inputs_snapshot_v13b.json](v13b/inputs_snapshot_v13b.json)）；冻结工作树 HEAD 不变且干净；未写 `SwarmData\v07_*`；未装包；未推 `main`、未强推。

### V8-13b.4 未做与已备

- 第 5 部分未运行（检查点 2 触发）。代码已备好（8 进程 spawn 池、2 h 截止与合作退出、复跑逐字节比较 `reproduction.json`、多样性 10 族 × 10 种子与 5.4 节编组参考曲线、合并 Fréchet、`full_checkpoint`、5.5 节分布与三图），**均未在真实数据上执行**，不能视为已验证。
- 快速批次运行时的 `result.json` 还没有逐成员偏离/跟踪统计字段（这些字段是在批次进行中为第 5 部分加入的，只影响记录，不影响算法）；上面的偏离分布取自 `optimized.json` 的优化诊断。

### V8-13b.5 测试汇总

| 测试 | 结果 |
|---|---|
| V8-13 预置 tracking / optimizer / flow / checkpoint | 4/4、7/7、4/4、5/5 |
| V8-13 预置 local_e2e（quick） | 3/3 |
| V8-13 预置 local_reproduction | 未运行（第 5 部分） |
| V8-08 / V8-11 预置 / V8-12 geometry / motion / own_part3 | 24/24、30/30、4/4、7/7、3/3（own_part3 已按 2.6 删两条断言） |

预置测试 6 个文件 SHA256 不变。疑似预期错误：无。按 2.4 要求检查：预置测试中没有写死旧夹具构造、μ 搜索或 E/Q 规则的断言；`test_head_on_swap`、`test_circle_obstacle_exact_clearance` 仍对 h=0.5 断言成功，这与 2.3"h=0.5 只作诊断"不冲突（本次两者都通过）。

### V8-13b.6 提交

| 提交 | 内容 |
|---|---|
| `525f502` | V8-13b 第 3 部分：增广拉格朗日、λ_j=1、15 m 大夹具、参考加速度 0.9、删两条 1800 s 断言、重新标定 |
| 本节所在提交 | 第 4 部分快速批次证据、第 5 部分运行器（未运行）、报告 |

### V8-13b.7 复跑命令

在 `Multi-UAV SimpleGC` 下，conda `llm`，单线程环境变量同第 9 节：

```powershell
python -B tools/v08/run_joint_monitoring.py --stage numerics --out "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-03_V8-13_joint_opt/out_rerun/numerics_v13b"
python -B tools/v08/run_joint_monitoring.py --stage quick --devset "../docs/v08/V8-03/devset_v08.json" --data-root "F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData" --cache "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-03_V8-13_joint_opt/cache" --out "F:/CASIA/Drone Swarm Situational Awareness Algorithm/_handoff/2026-11-03_V8-13_joint_opt/out_rerun/quick_v13b" --workers 1
```

预期：numerics 退出 0（约 11 s）；quick 退出 2（检查点 2 触发 `attempts`，约 35 分钟）。

### V8-13b.8 执行方观察（与事实分开）

1. 优化器这一层在返工后已经不是瓶颈：20 个合同里联合优化从未因物理硬检查失败，优化耗时中位数 19.7 s。检查点 2 的触发来自骨架随机构造（34/42 次失败）和少量优化后语义检查（8/42）。
2. 第 4.1 节删除单 attempt 内重抽是正确的方向，但它把 V8-12 时代隐藏在 attempt 内部的构造失败率直接暴露为 attempt 数。若审查方希望"尝试中位数 ≤ 1"成立，可能需要的是骨架层（巡逻形状 α 缩放后仍无解、折返掉头放置、起点路由）的确定性可行集合改进，而不是再动优化器；这需要裁定，我没有改。
3. 优化后掉头曲率半径不足的 6 次全部是略低于下界（斜切 7.0–7.3 m < 8 m；泪滴 23.1–23.3 m < 25 m）：优化在固定时间下略微"抄近"转弯。可考虑把转弯曲率也作为增广拉格朗日约束、或在掉头区间加贴近权；同样需要裁定。
4. 驻留/重访失败（4 次）说明优化后的曲线偶尔改变了冻结检测器的判定；这类失败目前只能靠重试吸收。
