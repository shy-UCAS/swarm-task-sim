# V8-06 仿真器标定 报告

- 工作项：V8-06（里程碑 ③ 单段原型，验证与标定类）；执行日期 2026-11-02；执行方：Claude Code（Windows 主机），实际模型 Claude Opus 5.5（`claude-opus-5-5`）。
- 依据：`_handoff/2026-11-02_V8-06_sim-calibration/V8-06_仿真器标定_执行指令_20261102.md`（下文"指令"）。
- 用语：`v_cmd` 指交给仿真器的期望巡航速度（`MemberPiece.speed_m_s`）；`v_meas` 指仿真输出 10 Hz 帧的水平速度模长。弯道上 `v_meas` 低于 `v_cmd` 是**冻结仿真器的跟踪与限速特性**，本报告中的任何数值都不代表真实无人机的转弯能力。

---

## 1. 红旗与需要负责人决定的事项

### 1.1 红旗

**无。** 按指令 4.9 的判定逐条核对（`calibration_result.json` 的 `red_flags` 为空列表）：

| 编号 | 条件 | 结果 |
|---|---|---|
| F1 | C 中某个 (形状, v_cmd) 没有 R_safe ≤ 100 m | 12 个组合都有，R_safe 为 10–20 m（第 3.5 节） |
| F1 | B 中任何一次判为驻留 | 0/48 |
| F1 | A 中 R ≥ 60 m 的任何一次判为驻留 | 0/308。A 中判为驻留的 21 次都在 R ≤ 25 m、s ≤ 3 m |
| F2 | A、B、C、E 中 R ≥ 15 m（B 全部）有 status ≠ ok | 0 次。全部 930 次中只有 1 次不是 ok：A 的 R = 10 m、s = 2 m、v_cmd = 10，结果为 `sim_timeout`；R < 15 m，按定义不算红旗 |
| F2 | E-a 中 continuation 有 dev_curve_max > 0.5 m | 0/72，最大 0.433 m |
| F3 | A 中某个 R ≥ 15 m 没有可用间距 | 0/19，每个 R 都有可用间距 |

### 1.2 需要负责人决定的事项（不是红旗）

1. **分段点在弯道上时重启跟踪器造成速度鼓包（E-a）。**
   - continuation 方式：bump 中位数 1.26 m/s，p95 3.53 m/s，最大 3.79 m/s（R = 240 m，(10, 10)，弧上 v_meas 从约 5.7 升到 9.46 m/s）；dip 最大 0.34 m/s；dev_curve_max 全部 ≤ 0.433 m。越过帧上与整段仿真的差值为 0（dv_at = dp_at = 0），鼓包出现在第二个小段重启之后。
   - straight 方式：bump 最大 5.16 m/s，dip 最大 3.95 m/s（v_meas 最低降到 0.04 m/s）；72 次中有 12 次 dev_curve_max > 0.5 m，最大 2.44 m。
   - 数据见 `Ea_runs.csv`，汇总见 `calibration_result.json` 的 `boundary_on_arc`。
2. **best_s 下 ripple > 0.05 的 R**：19 个 R 中有 14 个，分别是 10（0.557）、20（0.063）、50（0.267）、60（0.052）、80（0.391）、100（0.063）、120（0.065）、160（0.138）、240（0.119）、360（0.344）、480（0.088）、720（0.320）、1000（0.071）、1500（0.059）。ripple 大主要是 p95 偏高，即航点之间有加速，第 8 节第 2 条有说明。
3. **min 模型检验中 |err| > 0.1 m/s 的 (R, v_cmd)**：无。最大 |err| 为 0.021 m/s（R = 80 m，v_cmd = 4）。
4. **B 中 T_meas / T_model − 1 超出 ±10% 的仿真**：无，24 次自适应间距的范围是 −5.0% 到 +1.0%。
5. **（执行方补充，指令未列）B 的自适应间距在变曲率曲线上超出跟踪管。** 24 次自适应间距仿真中有 16 次 dev_curve_max > 0.5 m，中位数 0.668 m，最大 2.18 m（ρ0 = 300，[(75, 3, 0)]，有反曲点）。原因推测是 best_s 表在定半径圆弧上测得，用局部曲率半径选间距时，在曲率变化快或接近反曲点（R_local → ∞，间距取到 64 m）的地方，弦太长。B 的时间模型仍然准确（见上条），但这个间距规则如果直接用于生成，会违反 0.5 m 跟踪管。要不要改规则（例如按一段弧上的最小曲率半径取间距）需要负责人决定。数据见 `B_runs.csv` 的 `dev_curve_max` 列。

---

## 2. 复述

用合成的抽象几何航线测量冻结点质量仿真器（r3 配置，经 V8-04 适配层）的执行情况。航线包括直线、圆弧、极坐标闭合曲线、U 形、V150 和泪滴形掉头。测得的结果作为后续生成规则的来源：弯道 v_meas 与航点间距的关系、跟踪偏差、掉头不被判为驻留的最小半径、延伸段长度、分段点或变速点在弯道上时的连续性、名义用时模型的误差。测出来的数值好不好不算实现失败。

**四个部分：**
1. 快进合并 V8-05，放入预置测试；
2. 写标定工具 `v08/calibration/` 和脚本 `scripts/v08/v8_06_calibration.py`，跑预置测试，并跑 V8-03/04/05 回归；
3. 冒烟检查（止损点）；
4. 正式标定：A → D → derive1 → B、C、E、H → derive2。

**两种速度：** `v_cmd`（期望）与 `v_meas`（实测），所有表都写明。

**停止条件：**
- 冻结工作树或 `SwarmData\v07_*` 被写入；
- 冒烟未通过，则不进第 4 部分；
- 预置测试预期疑似有错，则该项停下。

**红旗 F1–F3：** 跑完整个网格，但不据此推出规则，在报告开头列出。严禁为了避开红旗而改判据、网格或剔除样本。

**不得修改：**
- 冻结工作树和 `SwarmData\v07_*`；
- `task_v07/`、`swarm_sim/`、`scene_v07/`、`configs/criteria/`、`configs/fast_dynamics/`；
- `v08/sim/`、`v08/config.py`、`v08/sampler/`、`v08/diagnostics/`、`configs/v08/`；
- 已有预置测试；
- `llm` 环境（不安装、不升级任何包）。

不推 `main`，不强制推送。

---

## 3. 每个实验的结论

### 3.1 冒烟检查（第 3 部分）

11 个用例 17 次仿真全部 `ok`。附录 C 的 43 项检查（含 11 项 status）全部在容差内，驻留判定一致，最大偏差 0.0005。耗时投影：墙钟/仿真秒的最大值 0.0304 × 1.2 × 190 000 / 12 进程 = 0.16 h ≤ 3 h。**通过**，进入第 4 部分。数据见 `smoke.csv`、`timing_smoke.json`。

### 3.2 实验 A：定半径圆弧（456 次）与 derive1 曲线速度表

19 个 R 都有可用间距（v_cmd = 10、status ok、稳态 dev_curve_max ≤ 0.5 m）。下表的 `v_curve` 是 (R, best_s, v_cmd = 10) 稳态帧 **v_meas** 的中位数；`dev_*` 取 v_cmd = 4/6/8/10 中的最大值。

| R (m) | best_s (m) | v_curve = v_meas 中位数 (m/s) | ripple | dev_curve_max (m) | dev_poly_max (m) |
|---|---|---|---|---|---|
| 10 | 4 | 1.734 | 0.557 | 0.384 | 0.461 |
| 15 | 6 | 2.220 | 0.018 | 0.235 | 0.248 |
| 20 | 8 | 2.588 | 0.063 | 0.312 | 0.245 |
| 25 | 8 | 2.766 | 0.029 | 0.286 | 0.237 |
| 30 | 8 | 2.853 | 0.032 | 0.263 | 0.219 |
| 40 | 10 | 3.172 | 0.040 | 0.276 | 0.228 |
| 50 | 12 | 3.333 | 0.267 | 0.346 | 0.243 |
| 60 | 12 | 3.609 | 0.052 | 0.276 | 0.232 |
| 80 | 16 | 3.790 | 0.391 | 0.371 | 0.246 |
| 100 | 16 | 4.281 | 0.063 | 0.286 | 0.244 |
| 120 | 16 | 4.417 | 0.065 | 0.262 | 0.224 |
| 160 | 20 | 4.963 | 0.138 | 0.308 | 0.252 |
| 240 | 24 | 5.681 | 0.119 | 0.303 | 0.252 |
| 360 | 32 | 6.200 | 0.344 | 0.348 | 0.251 |
| 480 | 32 | 6.896 | 0.088 | 0.260 | 0.222 |
| 720 | 48 | 7.468 | 0.320 | 0.389 | 0.251 |
| 1000 | 48 | 8.730 | 0.071 | 0.286 | 0.245 |
| 1500 | 64 | 9.400 | 0.059 | 0.331 | 0.251 |
| 2500 | 64 | 10（实测 9.99998，≥ 9.9 记为 10） | 0.0002 | 0.205 | 0.176 |

- 结论：在冻结仿真器的跟踪与限速特性下，弯道 v_meas 随 R 单调增加。v_cmd = 10 时，R = 240 m 约为 5.7 m/s，R = 1000 m 约为 8.7 m/s，R ≥ 2500 m 才不受限。这一关系替代 r3 6.6 中不成立的 R_min(v) 公式。规则就是这张表加 `interp_log`，没有拟合公式。
- min 模型检验：对 v_cmd = 4/6/8，err = v_meas 中位数 − min(v_cmd, v_curve(R))，57 行中最大 |err| = 0.021 m/s。
- A 中 21 次判为驻留，全在 R ≤ 25 m 且 s ≤ 3 m（best_s 下 0 次）。
- 1 次 `sim_timeout`：R = 10 m，s = 2 m，v_cmd = 10。
- 数据：`A_runs.csv`、`curve_table.json`。

### 3.3 实验 D：直线（44 次）

| v (m/s) | c(v) 起步耗时 (s) | h(v) 终点刹停与保持 (s) | 冲出 (m) | L_e,min (m) |
|---|---|---|---|---|
| 4 | 0.8 | 3.2 | 0.064 | 6 |
| 6 | 1.0 | 3.4 | 0.101 | 8 |
| 8 | 1.3 | 6.4 | 1.234 | 10 |
| 10 | 1.6 | 8.4 | 3.926 | 12 |

- 这里的 v 指 v_cmd；在直线上 v_meas 稳态与 v_cmd 相同。
- 延伸段：L_e ≥ L_e,min(v) 时 dv_win ≤ 0.005 m/s 且 dp_win ≤ 0.005 m。v = 10、L_e = 12 时为 0.0043 m/s / 0.0027 m，L_e ≥ 15 时逐位为 0；L_e 较短时，例如 v = 10、L_e = 2，dv_win 为 4.0 m/s，dp_win 为 5.6 m。
- **建议延伸段长度 `proposed_extension_length_m` = 15 m**：网格中严格大于 max_v L_e,min(v) = 12 m 的最小值。当前配置为 30 m。
- 直线变速 penalty（v_cmd 从 v1 变到 v2，相对瞬时变速模型）：4→10 为 +0.6 s，10→4 为 −1.7 s，6→8 为 +0.15 s，8→6 为 −0.17 s。
- 数据：`D_runs.csv`。

### 3.4 实验 B：连续变曲率闭合曲线（48 次）

- 48 次全部 `ok`，0 次驻留。验证集 8 条曲线没有重抽（重抽次数 0）。
- **固定间距**：间距越大，稳态 v_meas 越高，但偏差也越大。间距 16 m 时 dev_curve_max ≤ 0.29 m；32 m 时 8 次中 6 次 > 0.5 m；48 m 时 8 次全部 > 0.5 m，最大 2.41 m。
- **自适应间距**（spacing = `interp_log(R_local, R_m, best_s)`，24 次）：
  - v_meas / v_model 的中位数为 0.99–1.02，p05 最低 0.74，p95 最高 1.46，即瞬时有偏离；
  - **T_meas / T_model − 1 为 −5.0% 到 +1.0%**；T_naive（弧长 / v_cmd）在 v_cmd = 10 时比 T_meas 短 17–43%；
  - dev_curve_max > 0.5 m 的有 16/24 次，见第 1.2 节第 5 条。
- 数据：`B_runs.csv`；4 条主网格自适应间距的轨迹在 `traces/B_main_*_sadaptive.npz`。

### 3.5 实验 C：掉头与驻留误报（120 次）

R_safe（网格中最小的 R，使它和所有更大的 R 都不被冻结驻留检测器判为驻留；间距为 best_s(R)）：

| 形状 \ v_cmd | 4 | 6 | 8 | 10 |
|---|---|---|---|---|
| U | 20 | 20 | 20 | 20 |
| V150 | 15 | 15 | 15 | 10 |
| 泪滴 | 20 | 20 | 20 | 20 |

- 判为驻留的只有 R ≤ 15 m 的情形：U 和泪滴的 R = 10、15 m；V150 的 R = 10 m（v_cmd = 4/6/8）。
- 弯道上 v_meas 的最小值几乎与 v_cmd 无关，由 R 和间距决定，例如 R = 20 m 时约 2.4 m/s。这正是冻结仿真器的跟踪与限速特性：掉头时间不随 v_cmd 缩短，所以低半径掉头在任何 v_cmd 下都会被判为驻留。
- dev_path_max 最大 0.395 m。
- 数据：`C_runs.csv`。

### 3.6 实验 E：分段点、变速点在弯道上或弯道前（252 次）

**E-a（156 次）按 (R, mode) 汇总**（速度为 v_meas 相对于目标速度 v_target = min(v_cmd, v_curve(R))，单位 m/s）：

| R (m) | mode | dev_curve_max (m) | bump 最大 | dip 最大 | dv_at 最大 | dev > 0.5 m 次数 / 12 |
|---|---|---|---|---|---|---|
| 30 | straight | 2.220 | 4.00 | 2.82 | 3.42 | 4 |
| 30 | continuation | 0.306 | 1.97 | 0.07 | 0 | 0 |
| 60 | straight | 2.442 | 4.83 | 3.53 | 4.18 | 6 |
| 60 | continuation | 0.353 | 2.39 | 0.08 | 0 | 0 |
| 120 | straight | 1.751 | 5.16 | 3.95 | 4.65 | 1 |
| 120 | continuation | 0.355 | 2.99 | 0.07 | 0 | 0 |
| 240 | straight | 0.923 | 4.29 | 3.94 | 4.18 | 1 |
| 240 | continuation | 0.433 | 3.79 | 0.34 | 0 | 0 |
| 480 | straight | 0.280 | 3.10 | 0.11 | 3.09 | 0 |
| 480 | continuation | 0.377 | 3.02 | 0.06 | 0 | 0 |
| 1000 | straight | 0.286 | 1.27 | 0.07 | 1.29 | 0 |
| 1000 | continuation | 0.418 | 1.27 | 0.33 | 0 | 0 |

- 结论：前置探查中的现象得到证实。
  - **straight 延伸**在弯道中途分段会出现急刹，v_meas 最低 0.04 m/s，并偏离设计曲线，最大 2.44 m。
  - **continuation 延伸**时，越过帧上与整段仿真逐位相同，偏差都在 0.5 m 内；但第二个小段重启跟踪器后仍有速度鼓包，最大 +3.79 m/s。continuation 的 dev_curve_max 略高于 straight 中不出事故的情形（v_cmd = 4 时约 0.42 m 对 0.30 m）。
- **E-b 连接直线最小长度 s_a,min (m)**（分段点后直线 s_a 再进入圆弧，只能用直线延伸段）：

| v_cmd \ R (m) | 30 | 60 | 120 | 240 |
|---|---|---|---|---|
| 6 | 10 | 20 | 20 | 40 |
| 10 | 20 | 20 | 20 | 40 |

  s_a 不足时差别很大，例如 R = 30 m、s_a = 0、v = 10 时 dv_win 为 7.7 m/s，dev_curve_max 为 3.67 m。表中几项"满足"的 s_a 有 1e-14 量级的非零差（浮点舍入），远低于 0.005 的门槛。
- 数据：`Ea_runs.csv`、`Eb_runs.csv`；E-a 中 dev_curve_max 最大的 3 次的轨迹在 `traces/Ea_*.npz`。

### 3.7 实验 H：1 mm 微扰敏感性（10 次）

5 个用例：A 的 R = 60 与 R = 240；B 的 ρ0 = 300、[(75, 3, 0)]、自适应间距；C 的 U 形 R = 20、泪滴 R = 20（即 R_safe(形状, 10)）。在共同时刻、τ ≥ τ_r、原样仿真的非终端区帧上，dp_max ≤ 0.001 m，也就是初始的 1 mm 偏移没有放大，没有用例超过 0.05 m。泪滴为 0.00046 m，因为起点在终端区内，起点附近的帧被排除了。数据见 `H_runs.csv`、`traces/H_*.npz`。

### 3.8 derive2：时间模型（"实验 I"）与跟踪偏差

T_model = Σ 元素长度 / min(v_cmd, v_curve(R_元素)) + c(v_cmd) + h(v_cmd)；T_naive = 路径长度 / v_cmd；T_active 为释放后的仿真时长。

| 实验 | n | T_active/T_model − 1：中位数 | p95 | 最小 | 最大 | T_active/T_naive：中位数 | p95 | 最大 |
|---|---|---|---|---|---|---|---|---|
| A（best_s） | 76 | −0.0001 | +0.034 | −0.064 | +0.038 | 1.29 | 2.18 | 2.22 |
| B（自适应，整条曲线） | 24 | −0.011 | +0.005 | −0.058 | +0.012 | 1.18 | 1.64 | 1.77 |
| C | 120 | −0.002 | +0.019 | −0.055 | +0.028 | 1.49 | 2.03 | 2.16 |
| E（整段参照） | 60 | +0.006 | +0.019 | −0.006 | +0.024 | 1.16 | 1.61 | 1.79 |

- 结论：用曲线速度表加 c、h 的时间模型，误差在 −6.4% 到 +3.8% 之间；忽略弯道减速的 T_naive 最多低估约 2.2 倍。按指令，不提出 δ_sim、C 的取值。逐行数据见 `time_model_rows.json`。
- 跟踪偏差：
  - A 在 best_s 下 dev_curve_max ≤ 0.389 m、dev_poly_max ≤ 0.461 m；
  - C 的 dev_path_max ≤ 0.395 m（C 没有 dev_curve_max 列，用 dev_path_max 代替）；
  - E-a 分段的 dev_curve_max 中位数 0.301 m，最大 2.44 m（straight）；
  - E-b 中位数 0.292 m，最大 3.67 m（s_a = 0）；
  - B 全部 48 次中位数 0.585 m，最大 2.41 m。
- 汇总见 `calibration_result.json` 的 `tracking_deviation`。

---

## 4. 分支与提交

- 合并：`dev/v0.8` 从 `0d525ef` 快进到 `18ebe2a`（V8-05），已推送；`git ls-remote` 核对远端 `dev/v0.8` = `18ebe2a`。
- 分支 `review/v08/V8-06-sim-calibration`，基于 `18ebe2a`：

| 提交 | 说明 |
|---|---|
| `ec46f3b` | V8-06 第 1 部分：合并 V8-05，放入预置测试 |
| `08e4d0b` | V8-06 第 2 部分：标定工具 |
| `ececce7` | V8-06 第 3 部分：冒烟检查 |
| `9ce6161` | V8-06 第 4 部分：实验 A、D 与 derive1（曲线速度表、直线参数） |
| `0501591` | V8-06 第 4 部分：实验 B、C、E、H 与 derive2（建议值文件） |
| `68ec76e` | V8-06 报告 |

- 推送后的提交号：首次推送后 `git ls-remote` 核对远端 `review/v08/V8-06-sim-calibration` = `68ec76e6d40e9d9dd2527665e9f85e8e24ec5398`；本行所在的补记提交随后推送（只改本报告）。
- `calibration_result.json` 的 `source_commit` 为运行 derive2 时的 HEAD `9ce6161`。标定代码自 `08e4d0b` 起未改动：各 `timing_*.json` 的 `code_sha256` 一致，即 A/D 时 HEAD 为 `ececce7`，B–H 时为 `9ce6161`，两者的代码文件相同。

## 5. 改动文件清单

`git diff --stat dev/v0.8`（本报告提交前）共 66 个文件，全部为新增，+13 011 行。traces 之外：

```
 Multi-UAV SimpleGC/scripts/v08/v8_06_calibration.py
 Multi-UAV SimpleGC/tests/v08/V8-06/test_preset_v8_06.py
 Multi-UAV SimpleGC/v08/calibration/{__init__,geometry,metrics,runner}.py
 docs/v08/V8-06/{A,B,C,D,Ea,Eb,H}_runs.csv, smoke.csv
 docs/v08/V8-06/curve_table.json, calibration_result.json, time_model_rows.json
 docs/v08/V8-06/timing_{smoke,A,B,C,D,E,H}.json
 docs/v08/V8-06/preset_tests_v8_0{3,4,5,6}.txt
 docs/v08/V8-06/traces/*.npz（38 个，共约 1.4 MB）
```

- **是否触碰禁止范围：否。**
  - `git diff --name-only dev/v0.8` 不含 `task_v07/`、`swarm_sim/`、`scene_v07/`、`configs/`、`v08/sim/`、`v08/config.py`、`v08/sampler/`、`v08/diagnostics/`、`tests/v08/V8-03|04|05`。
  - `Simulation-fe-prod-r3`、`Simulation-fe-s3` 的 `status --porcelain` 均为空。
  - 没有读写 `SwarmData`。
  - `allow_continuation_extension()` 只在 `with` 块内替换 `v08.sim.adapter._check_piece`，`finally` 中还原；预置测试 `test_continuation_check_scoped` 验证了正常退出和异常退出两种情况下都会还原。

## 6. 预置测试

- `test_preset_v8_06.py`：SHA256 `3c8e80afa984a802b9ff283bc1110b0176a911685c53584581d9bf88e077f81b`，与指令一致。
- **19/19 通过**（5.9 s）：

| 类 | 测试 | 结果 |
|---|---|---|
| TestGeometry | arc_points、distance_to_path、distance_to_polyline、interp_log、polar、polar_adaptive、shape_teardrop、shape_turn_and_waypoints、shape_turn_u | 9 × ok |
| TestMetrics | arc_steady_mask、dwell_detector_definition、polar_progress_and_away、speed_and_overshoot | 4 × ok |
| TestRunnerPure | compare_runs、config_with、continuation_check_scoped、continuation_piece_waypoints | 4 × ok |
| TestSimProperties | continuation_split_exact_at_crossing、straight_split_equals_unsplit | 2 × ok |

- 回归：V8-03 12/12、V8-04 11/11、V8-05 15/15，全部通过。
- 命令（在 `Multi-UAV SimpleGC` 下）：`python -B -m unittest discover -s tests/v08/V8-0x -p "test_preset_*.py" -v`。
- 完整输出：`preset_tests_v8_06.txt`、`preset_tests_v8_03.txt`、`preset_tests_v8_04.txt`、`preset_tests_v8_05.txt`。

## 7. 自加的测试、偏离指令之处、疑似预期错误

**自加的测试：** 无。提交第 2 部分前，用一个临时脚本（在 scratchpad 中，不入库）把每类分析各跑一次，排查明显的错误。

**偏离指令之处及原因：**
1. `runner.config_with` 遇到 sim 配置中没有的参数名时抛 `KeyError`（防止拼写错误悄悄生效）。返回对象的 `sha256`、`path` 照"其余字段不变"保留原文件的值，因此它们**不反映**替换后的取值。
2. `metrics.py` 另加 `dwell_result`，返回冻结检测器的完整结果，供 C 的 `dwell_t_s` 使用；`dwell_detected` 基于它实现。`geometry.py` 另加公开辅助函数 `arc_relative_angle`。
3. `Ea_runs.csv`、`Eb_runs.csv` 中也收录了整段参照的行（`mode = unsplit`），并在列尾加了 `T_active_s` 列；`Eb_runs.csv` 另加 `mode` 列。原因是 derive2 的时间模型需要 E 整段参照的 T_active，而指令列出的列中没有它。
4. `curve_table.json` 的 `dev_curve_max_at_best_m`、`dev_poly_max_at_best_m` 取 best_s 下四个 v_cmd 的最大值，与 derive2 第 2 条的口径一致。另外加了几个键：`dev_poly_max_at_best_m`、`v_meas_med_at_best_raw_m_s`、`usable_spacings_m`、`excluded_R_m`、`selection_rule`、`min_model_check`、`overshoot_m_by_v`、`speed_change_penalty_s`。
5. `calibration_result.json` 另加了几个键：`proposed_extension_length_note`、`decision_items`、`tracking_deviation`、`excluded_R_m`；时间模型的逐行数据另存为 `time_model_rows.json`。
6. `smoke.csv` 采用长表格式，每行一个指标，列为 case、experiment、description、metric、value、reference、tolerance、passed。
7. `H_runs.csv` 的 `t_first_over_5cm_s` 约定为统一时钟 τ / 1e6（含释放前 20 s）。本次没有用例触发，所以该列为空。
8. `B_runs.csv` 的 `T_model_s` 只计 φ ∈ [π/3, 2π] 这一段（与 T_meas 对应），derive2 的时间模型对整条曲线另算。
9. `timing_*.json` 中每次仿真的 `wall_s` 只计 `fly` / `fly_split` 调用本身，不含随后的指标计算。
10. 操作记录：第一次在后台启动 B–H 时用了本机不存在的 `/usr/bin/time`，四个阶段都没有启动，没有产生任何输出；随后改用 shell 的 `time` 重跑，所以只有一次正式运行。

**疑似预期错误：** 无。

## 8. 复跑命令与环境

冒烟阶段（在 `Multi-UAV SimpleGC` 下，PowerShell 7）：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'
C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B scripts/v08/v8_06_calibration.py --stage smoke --workers 1
```

其余阶段把 `--stage` 依次换成 `A`、`D`、`derive1`、`B`、`C`、`E`、`H`、`derive2`，默认 12 个进程。

| 项 | 值 |
|---|---|
| Python / NumPy / shapely | 3.12.3（conda-forge）/ 2.5.3 / 2.0.7 |
| CPU | AMD Ryzen 9 9950X3D 16-Core Processor（32 逻辑处理器） |
| 进程数 | 冒烟 1；第 4 部分 12 |
| 第 4 部分 | 930 次仿真，189 993 仿真秒，各阶段墙钟合计 764 s（A 352 s、B 170 s、C 48 s、D 10 s、E 161 s、H 23 s） |
| 实际使用的模型 | Claude Opus 5.5（`claude-opus-5-5`） |

---

## 9. 执行方观察（个人判断，与上文事实分开）

1. **弯道 v_meas 主要由航点间距决定。** 只要偏差在跟踪管内，同一间距在不同 R 下的 v_meas 非常接近：
   - s = 12 m 时约 3.6–3.7 m/s；
   - s = 16 m 时约 4.4–4.5 m/s；
   - s = 24 m 时约 5.7–5.8 m/s；
   - s = 32 m 时约 6.9 m/s；
   - s = 48 m 时约 8.7 m/s。

   R 的作用主要是通过 0.5 m 跟踪管限制最大可用间距（约 3√R 以内）。这与前置探查中"间距约 1.5√R"的经验式方向一致，但这只是描述，不作为规则。
2. **best_s 用 p05 选择，避开了"中位数被抬高"的间距，但没有避开 p95 偏高。** 例如 R = 80 m 时 best_s = 16 m，p05 为 3.76 m/s，而 ripple 为 0.39。如果后续需要平稳的 v_meas，可以考虑同时约束 ripple。这属于规则设计，交给负责人。
3. **E-a continuation 的鼓包看起来与 R 无关，与"重启前后的目标速度差"有关。** v_cmd = 10 时，bump 约等于 v_cmd 与 v_curve(R) 的差（R = 240 m 时 10 − 5.7 ≈ 4.3，实测 3.8；R = 1000 m 时 10 − 8.7 ≈ 1.3，实测 1.27）；v_cmd = 4 且 v_cmd ≤ v_curve(R)（R ≥ 120 m）时没有鼓包（bump < 0）；v_cmd = 4 而 R = 30、60 m 时 bump 为 1.0、0.38 m/s，也约等于 v_cmd − v_curve（1.15、0.39）。推测是重启后的跟踪器在第一条腿上没有前一航点的转角信息，先按 v_cmd 加速，到下一航点才受限。这只是推测，未查跟踪器源码。如果属实，"变速点不放在弯道上，或者放在弯道上时 v_cmd ≤ v_curve(R)"会是一个简单的生成约束。
4. **E-b 的 s_a,min（10–40 m）与 D 的 L_e,min（6–12 m）在同一量级**，但 R = 240 m 时需要 40 m。这可能与大半径弧上较长的弦（24 m）有关。如果规则要写成与 R 无关的单一值，40 m 足够覆盖本网格。
5. **H 中 1 mm 微扰没有放大。** 至少在这 5 个单机用例上，冻结仿真器对初始位置不敏感。V8-03 转来的联合仿真 18.5 m 偏差，更可能来自联合仿真本身的耦合，而不是单机跟踪器的混沌。这一点本次没有直接验证。
6. **第 1.2 节第 5 条（B 自适应间距超出跟踪管）是我认为对后续生成影响最大的发现。** best_s 表只适用于定半径圆弧；用在变曲率的连续曲线上时，大约 2/3 的仿真超出 0.5 m 跟踪管。
