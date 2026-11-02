# V8-08 新引导层实现与软件在环数据盘点 报告

执行方：Claude Code（Claude Opus 5.5）；日期 2026-11-02；分支 `review/v08/V8-08-guidance`。

**结论：**
- 六个部分全部完成。
- V8-08 预置测试 **18/18** 通过；回归 V8-03 12/12、V8-04 11/11、V8-05 15/15、V8-06 19/19。
- `test_injectable_engine_identity` 通过：扰动为空时与冻结引擎逐位相同。
- 没有触发任何 P0 停止条件；疑似预期错误：无。
- 第 5 部分的只读盘点没有写入 `SwarmData`，但读取的 26 个文件的**最后访问时间**被文件系统自动更新，见第 12 节第 1 条。

## 1. 复述（开工前）

**目标：** 为 v0.8 写新的引导层。给定一条加密的平面曲线和期望速度，在每个 20 ms 积分步算出期望速度，交给冻结的速度控制器和点质量模型（经可注入扰动的执行内核）；同时只读盘点旧的软件在环数据，为 V8-09 标定 a_lat、a_lon 做准备。

**六个部分**（每部分单独提交）：
1. 快进合并 V8-06 到 `dev/v0.8` 并推送，新建审查分支，原样放入预置测试与 `guidance.json`；
2. `guidance.py` 纯函数：曲线、速度剖面、名义用时、投影、引导律；
3. `kernel.py`：`InjectableEngine`（照抄冻结 `step`，只插一处扰动）与 `member_config`；
4. `guided.py`：逐成员分段仿真，并跑全部 V8-08 预置测试与 V8-03/04/05/06 回归；
5. 软件在环数据只读盘点；
6. 与冻结跟踪器的耗时、速度对照。

**停止条件（P0）：**
- 冻结工作树或 `SwarmData` 被写入：立即停；
- `test_injectable_engine_identity` 不通过：停第 3、4 部分；
- 回归不通过：停并报告；
- 认为预置测试预期有错：不改测试，写进"疑似预期错误"，其余照常；
- 快进或推送被拒：不加 `--force`，停下问用户。

**不得修改：**
- 冻结工作树与 `SwarmData`（第 5 部分只读）；
- `task_v07/`、`swarm_sim/`、`scene_v07/`、`configs/criteria/`、`configs/fast_dynamics/`、`ArducopterSITL/`；
- `v08/sim/adapter.py`、`types.py`、`stitch.py`、`v08/config.py`、`v08/sampler/`、`v08/diagnostics/`、`v08/calibration/`、`configs/v08/sim.json`；
- 全部预置测试与 `guidance.json`；
- conda `llm` 环境（只运行，不安装、不升级）。

## 2. 每部分结论

**第 1 部分：**
- `dev/v0.8` 从 `18ebe2a` 快进到 `3c12585` 并已推送。
- 预置文件 SHA256 与指令一致：
  - `test_preset_v8_08.py`：`5d951e55…a85f1`；
  - `guidance.json`：`647d2a91…24531`。
- `load_config("guidance")` 读出 12 个参数。

**第 2 部分：**
- 按 2.1–2.6 逐条实现。
- `TestCurve`、`TestSpeedProfile`、`TestGuidanceLaw` 8/8 通过，输出见 `part2_tests.txt`。当时 kernel/guided 尚不存在，测试文件原样加载、两个模块用占位，见第 7 节。

**第 3 部分：**
- `InjectableEngine.step` 与冻结 `SynchronousEngine.step` 的函数体做了 `diff`，唯一差别是在 `request = self.controller.command(...)` 之后插入的 4 行。
- `TestKernel` 2/2 通过（含 identity 测试），输出见 `part3_tests.txt`。

**第 4 部分：**
- 按 4.1–4.2 实现。全部 18 项通过，用时 2.9 s。
- 回归全部通过（第 5 节）。
- 自加测试 6/6 通过（第 6 节）。

**第 5 部分：**
- 盘点完成，摘要见 [sitl_inventory.md](sitl_inventory.md)，数据见 `sitl_inventory.json`。两根实际在 `D:\T2L\SwarmData`，合计 101 GB、236 968 个文件。
- 按指令规则，`parallel_batch` 有 **929** 个软件在环分析目录，`fast_dynamics` 为 0。
- 抽样 20 个：19 个有数据、56 架机；1 个 truth.csv 为空（v061_T2）。
- 数据格式：采样间隔 0.1 s，有效行比例 1.0。
- 速度覆盖：水平 v_meas 中位数 1.91–2.97 m/s。飞控 `WPNAV_SPEED` 为 5 m/s，`WPNAV_ACCEL` 为 1 m/s²，**这批数据覆盖不了 4–10 m/s**。不下标定结论。

**第 6 部分：** 见下表，原始数据见 `compare.csv`。只记录，不设门禁。

| 用例 | 方式 | v_cmd | 冻结跟踪器间距 | 墙钟 s | 仿真 s | 墙钟/仿真秒 | 稳态帧 | v_meas 中位数 | p05 | p95 | 稳态帧到设计几何最大距离 m |
|---|---|---|---|---|---|---|---|---|---|---|---|
| a 直线 300 m | 新引导层 | 8 | — | 0.276 | 65.0 | 0.0042 | 125 | 8.000 | 8.000 | 8.000 | 0.000 |
| a 直线 300 m | 冻结跟踪器 | 8 | 两个航点 | 0.504 | 65.3 | 0.0077 | 125 | 8.000 | 8.000 | 8.000 | 0.000 |
| b R=20, 120° | 新引导层 | 10 | — | 0.238 | 56.3 | 0.0042 | 49 | 6.355 | 6.345 | 6.359 | 0.060 |
| b R=20, 120° | 冻结跟踪器 | 10 | 8 m | 0.892 | 67.5 | 0.0132 | 119 | 2.588 | 2.583 | 2.745 | 0.312 |
| c R=240, 120° | 新引导层 | 10 | — | 0.434 | 99.1 | 0.0044 | 377 | 10.001 | 10.001 | 10.001 | 0.002 |
| c R=240, 120° | 冻结跟踪器 | 10 | 24 m | 3.707 | 138.4 | 0.0268 | 651 | 5.681 | 5.680 | 6.357 | 0.303 |

**这张表的读法：**
- **新引导层：** 弯道 v_meas 由 a_lat 的待测初值 2.0 m/s² 决定。R=20 时 √(a_lat·R) = 6.32 m/s，实测 6.355；R=240 时不受限，以 v_cmd 飞行。
- **冻结跟踪器：** 弯道减速是冻结仿真器的跟踪与限速特性，与 V8-06 的曲线速度表一致（R=20 为 2.588，R=240 为 5.681）。
- 两者都不代表真实无人机的转弯能力。

**第 6 部分的测量口径：**
- "仿真 s" = 输出帧数 × 0.1。
- 稳态帧：用例 b、c 用 `arc_steady_mask` 默认参数；用例 a 没有圆弧，取 100 < x < 200 m 的帧（第 7 节）。

## 3. 分支与提交

基于 `dev/v0.8` = `3c12585447ced1754177baaaa2d6f0c12751430f`（V8-06 快进后，已推送并用 `git ls-remote` 核对）。

| 提交 | 内容 |
|---|---|
| `465039c` | V8-08 第 1 部分：合并 V8-06，放入预置测试与引导层配置 |
| `814a7df` | V8-08 第 2 部分：曲线、速度剖面、引导律（纯函数） |
| `d142532` | V8-08 第 3 部分：执行内核——扰动入口与每机参数 |
| `f76e8e0` | V8-08 第 4 部分：逐成员分段仿真（新引导层） |
| `ef74898` | V8-08 第 5 部分：软件在环数据只读盘点 |
| `31cca83` | V8-08 第 6 部分：与冻结跟踪器的耗时和速度对照 |
| `f59da68` | V8-08 报告 |

推送后用 `git ls-remote` 核对：远端 `review/v08/V8-08-guidance` = `f59da68708c985ca62734b770e0bf174a3ac4362`（报告提交）；`dev/v0.8` = `3c12585447ced1754177baaaa2d6f0c12751430f`。本补记为其后一个文档提交。

## 4. 改动清单（`git diff --stat dev/v0.8`，不含本报告）

```
 Multi-UAV SimpleGC/configs/v08/guidance.json       |   66 +   （原样放入）
 Multi-UAV SimpleGC/scripts/v08/v8_08_compare.py    |  120 +
 .../scripts/v08/v8_08_sitl_inventory.py            |  370 ++
 .../tests/v08/V8-08/test_own_v8_08.py              |  102 +
 .../tests/v08/V8-08/test_preset_v8_08.py           |  301 ++   （原样放入）
 Multi-UAV SimpleGC/v08/sim/guidance.py             |  169 +
 Multi-UAV SimpleGC/v08/sim/guided.py               |  207 +
 Multi-UAV SimpleGC/v08/sim/kernel.py               |   69 +
 docs/v08/V8-08/compare.csv                         |    7 +
 docs/v08/V8-08/own_tests_v8_08.txt                 |   11 +
 docs/v08/V8-08/part2_tests.txt                     |   15 +
 docs/v08/V8-08/part3_tests.txt                     |    8 +
 docs/v08/V8-08/preset_tests_v8_03.txt … v8_08.txt  |  100 +
 docs/v08/V8-08/sitl_inventory.json                 | 5119 +
 docs/v08/V8-08/sitl_inventory.md                   |  126 +
 19 files changed, 6790 insertions(+)
```

**是否触碰禁止范围：否。**
- 只有新增文件，全部在第 0.2 节允许的范围内。
- 预置测试与 `guidance.json` 未改动，SHA256 与指令一致。
- 冻结工作树 `Simulation-fe-prod-r3`（`641a9b3`）和 `Simulation-fe-s3`（`de4d115`）的 `git status` 均为干净。
- `SwarmData` 没有写入、移动或重命名。读取引起的 atime 变化见第 12 节。
- `llm` 环境未安装、未升级任何包。

## 5. 预置测试与回归（逐项）

命令（在 `Multi-UAV SimpleGC` 下，conda `llm`，环境变量见第 10 节）：

```
python -B -m unittest discover -s tests/v08/V8-0N -p "test_preset_*.py" -v
```

| 测试集 | 结果 | 用时 | 完整输出 |
|---|---|---|---|
| V8-08 | 18/18 OK | 2.9 s | `docs/v08/V8-08/preset_tests_v8_08.txt` |
| V8-03 | 12/12 OK | 0.001 s | `preset_tests_v8_03.txt` |
| V8-04 | 11/11 OK | 12.1 s | `preset_tests_v8_04.txt` |
| V8-05 | 15/15 OK | 0.5 s | `preset_tests_v8_05.txt` |
| V8-06 | 19/19 OK | 5.0 s | `preset_tests_v8_06.txt` |

V8-08 逐项全部 ok：
- 曲线：`test_circle_curvature`、`test_straight`、`test_rejects`；
- 速度剖面：`test_trapezoid`、`test_curvature_cap`、`test_speed_break_and_stop`；
- 引导律：`test_controller_inverse`、`test_projection_window_on_self_overlap`；
- 执行内核：`test_injectable_engine_identity`、`test_member_config`；
- 逐成员仿真：`test_straight_final`、`test_arc_speed_and_tube`、`test_speed_change_mid_arc`、`test_split_and_resume`、`test_stop_and_hold`、`test_disturbance_offset`、`test_determinism_and_timeout`、`test_input_checks`。

## 6. 自加的测试

`tests/v08/V8-08/test_own_v8_08.py`，6/6 通过，输出见 `own_tests_v8_08.txt`。

| 测试 | 检查内容 |
|---|---|
| `test_bad_stops` | 停止点在 0 或段末、不递增、停留 0 s、不在 0.1 s 网格、不在节点上：都抛 `SimContractError` |
| `test_header_checks` | 非第 0 段带出发延迟、延迟不在网格、tau 不在 10 Hz 网格、段号不一致：都抛错 |
| `test_curve_readonly` | `Curve` 的数组只读 |
| `test_release_delay_and_tau_offset` | 出发延迟 1.5 s 后才离开起点；第 1 段从 tau=3 s 开始时，扰动函数收到的第一个时刻为 3 000 000 µs、步长 20 000 µs（统一时钟） |
| `test_vehicle_overrides_change_result` | `velocity_response_time_s` 覆盖后轨迹改变 |
| `test_record_fields` | 非最后一段：`GuidedRecord` 的越过帧号 × 100 000 = 本段时长，末帧 + 100 ms = 切换时刻 |

## 7. 偏离指令之处

1. **分部分运行预置测试。** 预置测试文件在模块顶部导入 `kernel`、`guided`，第 2、3 部分提交时这两个模块还不存在，导入失败。
   - 做法：用一个临时运行器（会话临时目录，未入库）在 `sys.modules` 中放入占位模块，再**原样加载**测试文件，只运行该部分的测试类。
   - 第 4 部分完成后，已按指令命令 `unittest discover` 正式运行全部 18 项。
2. **`guidance.py` 多做的输入检查。**
   - `make_curve` 遇到无法转为数组的输入时抛 `SimContractError`；
   - `speed_profile` 额外检查 `speed_breaks` 的形状与有限性。
   - 都不改变规格规定的行为。
3. **`guided.py` 多做的检查。** 停止点每项须为 2 元组、弧长有限。停止点须在节点上，这一条由 `speed_profile` 内部的 `node_index` 抛错，与规格一致。
4. **盘点的降采样容差。** "保留 t ≥ 上一保留行 t + 0.1 s" 加了 1e-6 s 容差。10 Hz 数据的时间差实测为 0.09999999999999432 s，不加容差会隔行丢帧。
5. **盘点的分类规则。** 按 `*.BIN` 大小写严格匹配。parallel_batch 下另有同样数量的 `eeprom.bin`，不作为日志。`*.BIN` 与 `*.bin` 在计数中分开列出。
6. **盘点跳过 v0.7 目录。** 名称以 `v07_` 开头的目录不进入，以遵守"不读取任何 v0.7 数据"。实际跳过了 fast_dynamics 下 4 个 `v07_dataset`。
7. **对照用例 a。** 直线没有圆弧：稳态帧取 100 < x < 200 m；冻结跟踪器用两个航点（间距不适用）。
8. **多保存的输出。** 第 2、3 部分的测试输出 `part2_tests.txt`、`part3_tests.txt`，自加测试输出 `own_tests_v8_08.txt`。

## 8. 疑似预期错误

无。

## 9. 复跑命令

在 `Multi-UAV SimpleGC` 下：

```
C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-08 -p "test_*.py" -v
```

第 5、6 部分：

```
python -B scripts/v08/v8_08_sitl_inventory.py --roots "<…>/SwarmData/parallel_batch" "<…>/SwarmData/fast_dynamics" --max-samples 20
python -B scripts/v08/v8_08_compare.py
```

## 10. 环境版本

- Windows 11 Pro 10.0.26200；git 2.46.2.windows.1；
- conda 环境 `llm`：Python 3.12.3、NumPy 2.5.3；
- 环境变量：`PYTHONDONTWRITEBYTECODE=1`、`OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`；
- CPU：AMD Ryzen 9 9950X3D。第 6 部分为单进程计时。

## 11. 实际使用的模型

Claude Opus 5.5（`claude-opus-5-5`），在 Claude Code 中执行全部六个部分与报告。

## 12. 执行方观察（个人判断，与上文事实分开）

1. **SwarmData 的访问时间。**
   - 本机 NTFS 为 `DisableLastAccess = 2`（系统管理，开启访问时间更新）。读文件时由文件系统自动更新 atime：26/26 个被读文件的 atime 变了；大小、修改时间、创建时间 0 变化。
   - 我判断这不是第 0.4 节所说的"写入"，而且第 5 部分本来就要求读文件，所以没有停下，但它字面上属于"改时间戳"。
   - 以后若要求连 atime 都不变，可以：
     - 改用 `FILE_FLAG_BACKUP_SEMANTICS` 加 `SetFileTime(-1)` 打开（需要写属性权限，本身更不合"只读"）；
     - 或在只读快照、副本上盘点；
     - 或由用户临时关闭 last-access 更新。
2. **V8-09 的数据缺口最关键。**
   - 软件在环数据的 v_meas 集中在 2–3.4 m/s，飞控 `WPNAV_ACCEL` 只有 1 m/s²，比 `guidance.json` 的 a_lon 初值 1.5 还小。这些数据只能标定"低速航点导航"下的 a_lat、a_lon，无法支持 4–10 m/s 的弯道限速。
   - V8-09 若要用软件在环数据，可能需要按更高的 `WPNAV_SPEED`、`WPNAV_ACCEL` 补飞新的标定航线，这是需要负责人决定的事项。
   - 另外，`truth.csv` 的 `t_s` 是主机时间还是仿真时间未核对。manifest 有 `sim_speedup` 和 `time_mapping_available`，若时基不对，速度会被整体缩放。
3. **新引导层的表现与参考实现的实测一致。**
   - R=20 弯道 v_meas 比 √(a_lat·R) 高 0.03 m/s（预置测试注释的原型实测为 +0.035），对应实际横向加速度约 2.02 m/s²。
   - R=240 时 v_meas 比 v_cmd 高 0.001 m/s。
   - 稳态偏离分别为 0.06 m 和 0.002 m，远在 0.5 m 跟踪管内。
   - 耗时约为冻结跟踪器的 1/2–1/6，墙钟每仿真秒约 4 ms（单线程）。
4. **停留判定可能提前触发。** 第 3 条规格只看"到停止点的平面距离 ≤ 1 m 且速度 ≤ 0.15 m/s"，不看弧长进度。
   - 自交或折返的曲线若在到达停止点之前，以几乎为零的速度经过它 1 m 内，会提前开始停留。
   - 正常飞行速度远大于 0.15 m/s，所以实际很难触发；我按规格实现，没有加弧长条件。V8-09 生成复杂航线时可以考虑加上 `s_stop − s_p ≤ stop_approach_m` 的前提。
5. **投影的平局规则。** `project` 在节点处两条弦等距时取较小下标，因此节点处用的是前一条弦的切向。与 `test_controller_inverse` 注释的约定一致，对结果的影响在 1 个 20 ms 步以内。
