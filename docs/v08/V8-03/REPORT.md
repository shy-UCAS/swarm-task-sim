# V8-03 离线核对报告

- 工作项：V8-03（里程碑 ③ 单段原型，验证类）；执行日期 2026-11-01；执行方：Claude Code（Windows 主机）。
- 依据：`_handoff/2026-11-01_V8-03_offline-check/V8-03_离线核对_执行指令_20261101.md`（下文"指令"）。
- 本目录的结果文件由 `Multi-UAV SimpleGC/scripts/v08/v8_03_offline_check.py` 生成，原始输出在 `_handoff/2026-11-01_V8-03_offline-check/out/`。
- 数据路径一律相对数据根目录 `SwarmData`。

---

## 0. 复述与环境

### 0.1 任务复述

本任务只读 v0.7 首版 9 个批次的已有记录，回答 v0.8 生成器开工前的两个前提，并登记开发场景集。三个部分：（1）清单与开发场景集——按冻结划分规则统计场景族、保留抽签、保留样本，核对与预期计数一致，从 192 个有保留抽签的 train 场景族中按盐值取 40 个，并核对其场景文件 SHA256；（2）成员动力学独立（判定一）——延迟为 0 的成员，联合仿真与单机预演的窗口内位置误差最大值 ≤ 0.05 m；（3）出发平移（判定二）——延迟 > 0 的成员，同一误差 ≤ 0.05 m；另做交叉核对，确认读到的文件与生产记录 `position_error_max_m` 一致。停止条件（只列 P0）：`SwarmData\v07_*` 被写入或冻结工作树不干净；第 4 节计数/清单/抽样与预期不一致；开发场景集场景文件 SHA256 与登记值不同；判定一不通过（快速检查不通过则不跑全量）。不得修改：冻结生成器 `Simulation-fe-prod-r3`、`Simulation-fe-s3`、`SwarmData\v07_*` 下一切、conda `llm` 环境、仓库已有文件和预置测试；只新增指令第 0.2 节所列文件。

### 0.2 第 1 节核对结果

| 项 | 结果 |
|---|---|
| 冻结工作树 `Simulation-fe-prod-r3` | `fe/production-r3` @ `641a9b3a851fb0494f13a479ef0a6df5a0f17f79`；开始时 `status --porcelain` **为空** |
| 开发工作树 `Simulation-v08` 开始时 | `dev/v0.8` @ `bb262b3`，`status --porcelain` 为空 |
| `git fetch origin` | 成功，但本仓库的 `remote.origin.fetch` 只配置了 `main` 等 4 个分支，未生成 `origin/review/v08/V8-01-diagnosis`。改用 `git fetch origin refs/heads/review/v08/V8-01-diagnosis:refs/remotes/origin/review/v08/V8-01-diagnosis` 取到该引用（未改配置），= `6c171d7`。它是 `bb262b3` 之后的 2 个提交（`d857312`、`6c171d7`），只新增 `docs/v08/V8-01/` 下 22 个文件 |
| 合并 V8-01 + 推送 `dev/v0.8` | **推迟完成**。开工时 `merge --ff-only` 与 `push origin dev/v0.8` 在同一条命令中提交执行，被本机 Claude Code 权限分类器拒绝（推送属于对外发布），整条命令未执行；按指令 1.2 的失败分支从 `bb262b3` 继续。全部核对完成、本地提交后，用户在对话中明确同意推送与合并，随后执行 `merge --ff-only origin/review/v08/V8-01-diagnosis`（快进成功，`dev/v0.8` = `6c171d7`）和 `push origin dev/v0.8`（`bb262b3..6c171d7`，`git ls-remote` 核对远端 `dev/v0.8` = `6c171d79a57409b26f6124146ac29bbcd777782b`） |
| 审查分支 | 先从 `dev/v0.8`（`bb262b3`）新建 `review/v08/V8-03-offline-check`；合并后把唯一的本地提交变基到 `dev/v0.8`（`6c171d7`）之上（无冲突，改动文件不变） |
| 运行环境 | `conda run -n llm --no-capture-output python -B`；Python 3.12.3（conda-forge）、NumPy 2.5.3；设置 `PYTHONDONTWRITEBYTECODE=1`、`OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1` |
| 运行前快照 | 当时合并未做，`v8_01_snapshot.py` 由 `git show origin/review/v08/V8-01-diagnosis:docs/v08/V8-01/scripts/v8_01_snapshot.py` 取到 `_handoff/…/scripts/`（不提交），生成 `out/snapshot_before.json`（用时 188 s） |

### 0.3 是否触发停止条件

**未触发任何停止条件。** 但需注意：判定一**没有参与成员**（200 条样本 1440 个成员的出发延迟全部 > 0），结果为"无法判定"，不是"通过"；P0 前提"成员动力学独立"在本任务中**未得到验证**。见 1.2 节。

---

## 1. 每项结论

### 1.1 第 4 节：清单与开发场景集

**结论：全部计数与预期一致；开发场景集与附录 A 逐项、逐位置一致；40 个场景族的场景文件 80/80 SHA256 与登记值一致；两份抽样清单的 SHA256 与预期一致。**

| 项 | 实际（total / train / val / test） | 预期 | 一致 |
|---|---|---|---|
| 场景族 | 300 / 222 / 36 / 42 | 300 / 222 / 36 / 42 | 是 |
| 至少一个保留抽签的场景族 | 256 / 192 / 31 / 33 | 256 / 192 / 31 / 33 | 是 |
| 保留抽签 | 417 / 310 / 51 / 56 | 417 / 310 / 51 / 56 | 是 |
| 保留样本 | 4170 / 3100 / 510 / 560 | 4170 / 3100 / 510 / 560 | 是 |
| train 保留样本 base_intent × mode 10 格 | 每格 310，无其他取值 | 每格 310 | 是 |

- 出现在多个批次描述中的场景族：0 个；manifest 中重复的 `draw_key`：0 个。
- 开发场景集：候选 192 个；ID 以 `\n` 连接的 SHA256 = `f773cdf1ccea88c98bc064c2b8c6d12aa70b5cb93e25cb468629472bfa98dc52`（与预期一致），与附录 A 不一致的位置：0。
- 场景文件：40/40 `scene_files_verified = true`；缺失 0，SHA256 不同 0，无登记行 0。`directory_rel` 均为 `v07_scene/attempt_s15_20261016T144107Z/<family_id>`（取路径中 `SwarmData` 之后部分，分隔符写作 `/`）。
- 全量抽样 200 条，SHA256 = `6f05e38e…af16a`（一致）；共 1440 个成员（与附录 B 后的 1440 一致）。快速清单 10 条，SHA256 = `37c0318a…d43c6`（一致），与附录 B 的 episode_id、批次、机数逐条一致。
- 证据：`inventory_summary.json`、`families.csv`、`devset_v08.json`/`.csv`、`sample_episodes.json`。

**开发场景集分布诊断（只报告，不做调整）：**

| 维度 | 40 族 | 192 族候选 |
|---|---|---|
| 布局 single / linear / clustered / isolated | 17 / 8 / 5 / 10 | 68 / 46 / 41 / 37 |
| 设施数 1 / 2 / 3 | 17 / 17 / 6 | 68 / 71 / 53 |
| 机数分档 4–5 / 6–8 / 9–11 / ≥12 | 4 / 18 / 15 / 3 | 40 / 85 / 51 / 16 |

逐值机数分布见 `inventory_summary.json` 的 `devset_diagnostics`。

### 1.2 判定一：成员动力学独立

**结论：无法判定。** 快速检查 10 条样本 75 个成员、全量 200 条样本 1440 个成员中，出发延迟为 0 的成员数都是 **0**（全量延迟最小值 5.3 s）。判定一没有参与成员，`pass = null`。按停止条件的字面（"判定一不通过"）未触发，所以继续跑了全量；但 P0 前提没有被这组样本检验到。

- 证据：`quick_results.json`、`full_results.json` 的 `judgement_1_zero_delay`、`delay_coverage`。

### 1.3 判定二：独立 + 出发平移

**结论：不通过。** 延迟 > 0 的 1440 个成员中，窗口内位置误差最大值 `pos_err_max_m` 的最大值为 **18.550 m**（阈值 0.05 m），中位数 0.305 m；1341/1440 个成员超过 0.05 m。

| 统计（1440 个成员的 `pos_err_max_m`） | 值 (m) |
|---|---|
| 最大 | 18.5497（`family_s15_40f2a315fe462d42_ext_003_regular_synchronous` / `uav_07`，延迟 46.8 s） |
| 第 50 / 90 / 95 / 99 百分位 | 0.3050 / 0.6935 / 0.8408 / 1.0748 |

按层（成员数，最大值，中位数，单位 m）：

| 层 | 成员 | 最大 | 中位数 |
|---|---|---|---|
| transit / synchronous | 147 | 1.0723 | 0.2931 |
| transit / sequential | 140 | 1.1723 | 0.2984 |
| reconnaissance / synchronous | 138 | 1.0099 | 0.3432 |
| reconnaissance / sequential | 131 | 1.1793 | 0.2640 |
| monitoring / synchronous | 158 | 1.1221 | 0.2932 |
| monitoring / sequential | 145 | 1.1761 | 0.3458 |
| feint / synchronous | 156 | 18.5497 | 0.3536 |
| feint / sequential | 135 | 1.1177 | 0.3633 |
| penetration / synchronous | 148 | 1.0819 | 0.2944 |
| penetration / sequential | 142 | 1.0572 | 0.2943 |

误差最大的 20 个成员（`full_results.json` → `judgement_2_detail.top20`）：

| episode_id | agent | 延迟 (s) | pos_err_max_m | vel_err_max_m_s |
|---|---|---|---|---|
| family_s15_40f2a315fe462d42_ext_003_regular_synchronous | uav_07 | 46.8 | 18.5497 | 7.368 |
| family_s15_40f2a315fe462d42_ext_003_regular_synchronous | uav_08 | 63.9 | 18.4619 | 7.332 |
| family_s15_4033c6515db45ec1_ext_001_regular_sequential | uav_01 | 74.2 | 1.1793 | 2.930 |
| family_s15_d5c092fa63a8d8d3_ext_007_regular_sequential | uav_05 | 292.5 | 1.1761 | 2.925 |
| family_s15_353b8b5f4cae79d3_ext_005_regular_sequential | uav_02 | 256.9 | 1.1723 | 2.918 |
| family_s15_9d4a976f2ea7b27c_ext_003_regular_synchronous | uav_01 | 79.9 | 1.1221 | 2.829 |
| family_s15_9d4a976f2ea7b27c_ext_007_regular_synchronous | uav_01 | 76.8 | 1.1221 | 2.829 |
| family_s15_055e9333b067d2bc_ext_007_regular_synchronous | uav_02 | 439.2 | 1.1177 | 2.821 |
| family_s15_055e9333b067d2bc_ext_008_regular_sequential | uav_02 | 467.5 | 1.1177 | 2.821 |
| family_s15_40f2a315fe462d42_ext_003_regular_synchronous | uav_05 | 292.4 | 1.1067 | 2.801 |
| family_s15_bb353df3a3977ad1_ext_001_regular_sequential | uav_01 | 83.6 | 1.0905 | 2.772 |
| family_s15_eb306b5e9968647e_ext_007_regular_synchronous | uav_03 | 88.2 | 1.0852 | 2.762 |
| family_s15_eb5a54aaedfbbc81_ext_007_regular_synchronous | uav_04 | 29.2 | 1.0819 | 2.756 |
| family_s15_eb5a54aaedfbbc81_ext_009_regular_synchronous | uav_04 | 31.8 | 1.0819 | 2.756 |
| family_s15_6af8e2b8ab8f838d_ext_009_regular_synchronous | uav_08 | 73.5 | 1.0765 | 2.746 |
| family_s15_3b2aa3baa13c043a_ext_005_regular_synchronous | uav_05 | 87.5 | 1.0723 | 2.739 |
| family_s15_3b2aa3baa13c043a_ext_008_regular_sequential | uav_05 | 136.6 | 1.0723 | 2.739 |
| family_s15_40f2a315fe462d42_ext_003_regular_synchronous | uav_03 | 289.1 | 1.0615 | 2.719 |
| family_s15_0c732d87d623efeb_ext_000_regular_synchronous | uav_03 | 40.3 | 1.0572 | 2.711 |
| family_s15_0c732d87d623efeb_ext_007_regular_sequential | uav_03 | 56.1 | 1.0572 | 2.711 |

速度误差：1440 个成员 `vel_err_max_m_s` 最大 7.368 m/s，第 95 百分位 2.283 m/s。

**误差出现在哪一段（补充诊断 `--stage diag`，不属于指令第 5.3 节判定；证据 `diag_results.json`、`diag_members.csv`）：** 把同一窗口按联合时刻相对释放时刻（`t − 延迟`）分为释放前、释放后 10 s 内、其余三段：

| 段 | 最大 (m) | 中位数 (m) | 第 95 百分位 (m) | > 0.05 m 的成员 |
|---|---|---|---|---|
| 释放前（与单机第 0 帧比较） | 1.1793 | 0.3046 | 0.8344 | 1338 / 1440 |
| 释放后 10 s 内 | 1.1793 | 0.3046 | 0.8344 | 1338 / 1440 |
| 释放 10 s 之后 | 18.5497 | 0.00156 | 0.0380 | 52 / 1440 |

- 1440 个成员中，1424 个的窗口内误差最大值出现在释放前，16 个出现在释放 10 s 之后，0 个在释放后 10 s 内（两段最大值相差约 1e-11 m，取先者）。
- 联合轨迹第 0 帧速度：1440/1440 个成员不为 0（中位数 0.803 m/s，最大 2.450 m/s）；单机预演第 0 帧速度与联合轨迹第 0 帧速度逐成员相等（1440/1440）。
- 释放 10 s 之后超过 0.05 m 的 52 个成员分布在 19 条样本中（monitoring/synchronous 32 个，monitoring/sequential 11 个，其余 9 个）；其中超过 0.5 m 的只有 3 个：上表前两名（同一条 feint 样本，最大误差位于释放后约 520 s 和 500 s、窗口结束前约 64 s）和 `family_s15_eb306b5e9968647e_ext_007_regular_synchronous` / `uav_02`（0.659 m）。

### 1.4 交叉核对

**结论：通过，200/200 条样本差值为 0。** 每条样本各成员 `full_pos_err_max_m` 的最大值与生产记录 `solo_overlay_comparison.json` 的 `position_error_max_m` 之差绝对值的最大值为 **0.0 m**（容差 1e-9 m）。快速检查 10/10 同样为 0.0。说明轮次目录、编号对应、延迟对应均读对。来源不一致 0 条，文件缺失 0 条，读取失败 0 条；描述项 `agent_ids`、`departure_delays_s` 键与 `truth_10hz.npz` 的 `agent_ids` 集合全部一致。

### 1.5 延迟覆盖

| 项 | 值 |
|---|---|
| 延迟为 0 / 大于 0 的成员 | 0 / 1440 |
| 延迟最小 / 最大 | 5.3 s / 1200.7 s |
| 第 50 / 90 / 99 百分位 | 147.0 / 510.8 / 859.9 s |
| 延迟 < 10 s 的成员 | 11 |

### 1.6 终点保持段诊断（供 V8-04）

| 项 | 值 |
|---|---|
| 有终点保持段（窗口之后还有联合帧）的成员 | 1240 / 1440 |
| `post_end_disp_max_m` 最大 / 第 95 百分位 / 中位数 | 3.338 / 2.897 / 0.235 m |
| `post_end_frames` 最大值 | 24980 帧 = 2498.0 s |
| 单机 `execution_status` | `completed` 1440 |

---

## 2. 分支与提交

- 基于提交：`6c171d7`（合并 V8-01 后的 `dev/v0.8`；核对计算本身在 `bb262b3` 上完成，两者之间只差 `docs/v08/V8-01/`，不影响本任务脚本与数据）。
- 审查分支：`review/v08/V8-03-offline-check`，内容提交 `docs(v08): V8-03 离线核对（动力学独立、出发平移、开发场景集）`。
- 推送后的远端提交号：`0123f8554035be44d2516944b399cbf19f3a7a14`（内容提交；`git ls-remote origin refs/heads/review/v08/V8-03-offline-check` 核对一致）。本行由随后的补记提交写入；补记提交只改本文件，其提交号以远端分支头为准。

## 3. 改动文件清单

`git diff --stat dev/v0.8...HEAD`（`REPORT.md` 所在提交的统计）：

```
 .../scripts/v08/v8_03_offline_check.py             |  773 +++++
 .../tests/v08/V8-03/test_preset_v8_03.py           |  143 +
 docs/v08/V8-03/REPORT.md                           |  265 ++
 docs/v08/V8-03/devset_v08.csv                      |   41 +
 docs/v08/V8-03/devset_v08.json                     |  562 ++++
 docs/v08/V8-03/diag_members.csv                    | 1441 ++++++++
 docs/v08/V8-03/diag_results.json                   |  875 +++++
 docs/v08/V8-03/families.csv                        |  301 ++
 docs/v08/V8-03/full_members.csv                    | 1441 ++++++++
 docs/v08/V8-03/full_progress.txt                   |   10 +
 docs/v08/V8-03/full_results.json                   | 3480 ++++++++++++++++++++
 docs/v08/V8-03/inventory_summary.json              |  165 +
 docs/v08/V8-03/preset_tests.txt                    |   17 +
 docs/v08/V8-03/quick_members.csv                   |   76 +
 docs/v08/V8-03/quick_results.json                  |  439 +++
 docs/v08/V8-03/sample_episodes.json                | 1802 ++++++++++
 docs/v08/V8-03/timing_diag.json                    |    4 +
 docs/v08/V8-03/timing_full.json                    |    4 +
 docs/v08/V8-03/timing_inventory.json               |    4 +
 docs/v08/V8-03/timing_quick.json                   |    4 +
 20 files changed, 11847 insertions(+)
```

全部为新增文件，均在指令第 0.2 节范围内（`scripts/v08/v8_03_offline_check.py`、`tests/v08/V8-03/test_preset_v8_03.py`、`docs/v08/V8-03/` 下报告与结果）。没有单个文件超过 5 MB。`snapshot_before.json`、`snapshot_after.json` 按指令不提交，留在 `_handoff/…/out/`。

## 4. 预置测试

- 复制后 SHA256：`91c67f8b231f1d7cd7fa1fa15105259a18cebe3b60a10aa614e2815a240114af`（与指令一致，与 `preset/` 原文件一致）。
- 命令（在 `Multi-UAV SimpleGC` 下）：`conda run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-03 -p "test_preset_*.py" -v`
- 结果：**12/12 通过**。完整输出：`preset_tests.txt`。

| 测试 | 结果 |
|---|---|
| test_family_split_known_values | 通过 |
| test_devset_order_key | 通过 |
| test_select_devset_takes_smallest_keys | 通过 |
| test_select_devset_rejects_duplicates_and_short_lists | 通过 |
| test_sample_key | 通过 |
| test_zero_delay_identical | 通过 |
| test_shift_and_post_end | 通过 |
| test_frames_before_release_use_first_solo_sample | 通过 |
| test_in_window_perturbation | 通过 |
| test_full_error_matches_clamped_interpolation | 通过 |
| test_delay_off_grid_raises | 通过 |
| test_bad_time_axis_raises | 通过 |

加入 `--stage diag` 后重跑一次，仍为 12/12 通过。

## 5. 自加的测试

无。

## 6. 偏离指令之处及原因

1. **V8-01 的合并与 `dev/v0.8` 推送推迟到核对完成之后**：开工时被权限分类器拒绝，按指令 1.2 的失败分支从 `bb262b3` 继续；用户同意后补做，审查分支随之变基到 `6c171d7`。见 0.2 节。
2. **取 V8-01 远端引用的方式**：仓库 fetch 配置不含 review 分支，用显式引用规格取到 `origin/review/v08/V8-01-diagnosis`，未改配置。
3. **审查分支在用户同意后推送**：见第 2 节。
4. **新增补充诊断 `--stage diag`**：判定二不通过后，为说明误差出现在哪一段，在同一脚本中加了 `diag_member` 与 `--stage diag`，输出 `diag_results.json`、`diag_members.csv`。它不改变第 3 节函数和 inventory/quick/full 的任何输出：加入后在暂存目录用最终脚本重跑 inventory、quick、full，9 个结果文件与 `out/` 中的逐字节相同（`timing_*` 与 `full_progress.txt` 含耗时，不比较）。
5. **`snapshot_after.json` 在本地提交之前生成**：指令要求推送后再做；所有数据读取在快照前已结束，之后的提交、变基、推送只涉及仓库，先做快照以便写入本报告。
6. **判定一结果为"无法判定"时仍跑了全量**：停止条件写的是"判定一不通过"，`pass = null` 不属于不通过；全量也用于确认整个抽样中是否有延迟为 0 的成员（结果：没有）。
7. **路径分隔符**：`directory_rel` 与报告中的相对路径用 `/`。

## 7. 疑似预期错误

- 预置测试：无。
- 指令第 5.3 节判定一的前提是抽样中存在"出发延迟为 0 的成员"。实际 200 条样本 1440 个成员的延迟全部 > 0（最小 5.3 s），判定一没有样本可用。这不是计算错误，而是抽样设计与判定口径之间的预期不符，需规划审查方确认。
- 指令第 5.1 节引用 V8-01 续跑实验"位置最大差 4.4 mm"作为预期量级；本次窗口内误差中位数为 0.305 m。二者测量口径不同（续跑实验 vs 联合/单机对照），这里只列出事实差异。

## 8. 复跑命令

```
C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08\Multi-UAV SimpleGC\scripts\v08\v8_03_offline_check.py" --stage quick --data-root "F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData" --out "F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-01_V8-03_offline-check\out_rerun"
```

运行后应打印 `quick: OK`。然后执行：

```
Get-FileHash "F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-01_V8-03_offline-check\out\quick_results.json", "F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-01_V8-03_offline-check\out_rerun\quick_results.json" -Algorithm SHA256
```

两个哈希都应为 `4762691AB303A2C2F6735AC09B7FEFBB1FE5F2838F169A51262ABB4F56F1CBCB`。（执行方已在暂存目录用最终脚本做过同样的重跑，inventory/quick/full 的 9 个结果文件逐字节相同；正式的"已复跑"由用户执行。）

## 9. 环境与运行

| 项 | 值 |
|---|---|
| Python / NumPy | 3.12.3（conda-forge）/ 2.5.3 |
| 各阶段耗时 | inventory 1.6 s；quick 2.2 s；full 38.5 s（200 条，每 20 条进度见 `full_progress.txt`）；diag 6.5 s；每次快照约 3 分钟 |
| 快照比较 | `snapshot_before.json` 与 `snapshot_after.json` 的 22 个 `v07_*` 目录逐目录一致（文件数、总字节数、最新修改时间、最新文件路径均相同） |
| 冻结工作树最终 `status --porcelain` | 空（头提交仍为 `641a9b3`） |

---

## 10. 执行方观察（个人判断，与上文事实分开）

- 判定二的超阈值几乎全部来自释放前后的起步段：联合仿真中，成员在释放前并不是静止在起点——第 0 帧带有非零初速度（与单机预演第 0 帧相同），之后在释放前回到起点；而单机预演从 t=0 起就带着这个初速度出发。释放前段误差与 \(v_0^2\) 的相关系数约 0.976（由 `diag_members.csv` 计算，未写入结果文件），看起来像初速度带来的一段制动/回位距离。若此解释成立，"整体推迟出发只是平移"在起步段不成立，原因在初始状态而非成员间相互作用；但这需要读冻结代码确认，本任务没有读。
- 释放 10 s 之后，绝大多数成员误差在毫米到厘米量级（中位数 1.6 mm，第 95 百分位 3.8 cm），与指令预期的"积分步切分差异"量级大体一致；但仍有 52 个成员超过 0.05 m，其中 monitoring 占 43 个；feint 样本 `family_s15_40f2a315fe462d42_ext_003_regular_synchronous` 的 `uav_07`、`uav_08` 在释放约 500 s 后偏离 18.5 m，属于另一类现象，值得单独查看。
- 判定一在 v0.7 数据中可能根本没有可用样本（本抽样 1440/1440 延迟 > 0）。若要检验 P0 前提，可能需要另找延迟为 0 的成员，或对全部 3100 条 train 样本统计是否存在延迟为 0 的成员。
