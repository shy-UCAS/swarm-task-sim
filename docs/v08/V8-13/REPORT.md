# V8-13 联合时空轨迹优化：监视单段 — 报告

执行日期 2026-11-03 起。开发工作树 `Simulation-v08`，审查分支 `review/v08/V8-13-joint-opt`。
本报告随各部分逐步补全；最终提交号以 `git ls-remote` 输出为准（见对话回报）。

**实际使用的模型：** Claude Opus 5.5（`claude-opus-5-5`），Claude Code 桌面版。

## 结论（先看这里）

（各部分完成后补写；见文末各节。）

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
