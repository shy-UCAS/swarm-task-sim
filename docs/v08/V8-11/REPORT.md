# V8-11 窗口版判据、段核验与实测有效性检查：报告

执行日期 2026-11-02。开发工作树 `Simulation-v08`，审查分支 `review/v08/V8-11-criteria`。

## 1. 复述（开工前）

- **目标：** 把规划审查方已写好的判定模块放进仓库并运行，不自己写算法。
  1. 时间预算入配置：`budget_factor` 0.1、`budget_const_s` 30 s。
  2. 窗口版判据：在任意一段帧上复用 v0.7 冻结检测器；窗口取整条 v0.7 样本时，结果必须与 `labels.json` 逐项一致（P0 回归门禁）。
  3. 实测有效性检查：同时可见成员的采样最小间距 ≥ 2 m、不进入限制区，帧间插值距离只作诊断。
  4. 段核验：逐段、逐成员核验本段意图，失败按 r4 13.4 归类。
- **三个部分，各自单独提交：** (1) 快进合并 V8-10 并换 `guidance.json`，跑 V8-08（24 项）与 V8-04（11 项）；(2) 放 8 个文件，跑预置测试（5+8+3 项），先快速回归 10 条，退出码为 0 才跑全量 200 条；(3) 放 3 个文件，跑段核验测试（14 项）及全部预置测试（30 项）。
- **停止条件：** 数据目录有写入或冻结工作树不干净；第 1 部分换配置后 V8-08/V8-04 有不通过；任一部分预置测试不通过；快速回归退出码非 0（不跑全量、不做第 3 部分）；全量回归退出码非 0（写完报告提交，不做第 3 部分）。停下时不改代码、不改测试，如实报告。
- **不得修改：** 冻结工作树 `Simulation-fe-prod-r3`（`641a9b3`）、`Simulation-fe-s3`（`de4d115`）；`SwarmData\v07_*`（只读）；`task_v07/`、`scene_v07/`、`swarm_sim/`、`configs/criteria/`、`configs/fast_dynamics/`（只导入）；`v08/sim/`、`v08/config.py`、`configs/v08/sim.json`、`tests/v08/` 下已有测试；指令包全部文件（原样放入）；conda `llm` 环境（只运行不安装）。不推 `main`，不强制推送。

## 2. 各部分结论

| 部分 | 结论 | 提交 |
|---|---|---|
| 1 合并 V8-10，写入时间预算参数 | 通过。`dev/v0.8` 快进 `03ac333` → `2bbe8ad` 并已推送；换配置后 V8-08 24/24、V8-04 11/11 通过 | `d8d4f6d` |
| 2（一）窗口版判据与有效性检查 | 通过。8 个文件 SHA256 全部一致；预置测试 window 5/5、validity 8/8、regress 3/3 | `c0da1ef` |
| 2（二）v0.7 回归 | 通过。快速（10 条）退出码 0；全量（200 条）退出码 0，零差异 | `dd1595d` |
| 3 段核验 | 通过。3 个文件 SHA256 一致；段核验 14/14，`tests/v08/V8-11` 全部预置测试 30/30 | `2124623` |

没有触发任何停止条件。

## 3. 回归结果表

### 3.1 汇总

| 阶段 | 样本数 | 读到数（`verified`） | 成员数 | 编组数 | 未结束样本数 | 差异数 | `data_unchanged` | `list_ok` | 退出码 | 脚本耗时 | 外层耗时 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 快速 | 10 | 10 | 75 | 14 | 0 | 0 | true | true | 0 | 28.6 s | 31 s |
| 全量 | 200 | 200 | 1440 | 276 | 0 | 0 | true | true | 0 | 439.8 s | 450 s |

- 加载错误 `load_errors`：两阶段均为空列表。
- 清单 SHA256：全量 `6f05e38ee49e14ddeb9cf4917569b0cd934be6ca42b18135ea4aa7b9667af16a`；快速 `37c0318a6a851773f10653500205f8b5fe0fe5cb6aec7a47e129739ee14d43c6`（脚本内置值，`list_ok` 为真即与之相符）。
- 样本目录内被核对大小与修改时间的文件数：快速 160，全量 3200。
- 全量与指令"预期"逐条对照：`list_ok` 真 ✓；`samples` = `verified` = 200 ✓；`members` = 1440 ✓；`mismatch_count` = 0 ✓；`data_unchanged` 真 ✓；`by_kind` 覆盖 transit、area_search、close_observation、monitoring、feint、intrusion ✓。

### 3.2 按意图的编组数（`by_kind`，各项之和等于编组数）

| 阶段 | transit | area_search | close_observation | monitoring | feint | intrusion | 合计 |
|---|---|---|---|---|---|---|---|
| 快速 | 4 | 1 | 1 | 3 | 3 | 2 | 14 |
| 全量 | 53 | 22 | 26 | 59 | 67 | 49 | 276 |

### 3.3 每个比较项的比较次数（`compared`）

| 层级 | 比较项 | 快速 | 全量 |
|---|---|---|---|
| 成员 | `conditions` | 75 | 1440 |
| 成员 | `status` | 75 | 1440 |
| 成员 | `core_event` | 75 | 1440 |
| 成员 | `dwell` | 75 | 1440 |
| 成员 | `revisit` | 75 | 1440 |
| 成员 | `work_end_s` | 75 | 1440 |
| 成员 | `regions_by_facility` | 75 | 1440 |
| 成员 | `obstacle_outside_counts` | 75 | 1440 |
| 成员 | `approach_heading_deg` | 75 | 1440 |
| 成员 | `observation_dwell`（仅抵近观察） | 9 | 161 |
| 成员 | `coverage_member`（仅区域侦察） | 6 | 108 |
| 编组 | `group_conditions` | 14 | 276 |
| 编组 | `group_status` | 14 | 276 |
| 编组 | `shared_coverage`（仅区域侦察） | 1 | 22 |
| 样本 | `minimum_separation_m` | 10 | 200 |
| 样本 | `member_min_separation_m` | 10 | 200 |
| 样本 | `hard_obstacle_sample_count` | 10 | 200 |

### 3.4 差异清单

两阶段 `mismatch_count` 均为 0，`mismatch_fields` 为空，`regress_*_mismatches.csv` 只有表头行（`episode_id,scope,field,recorded,computed`）。无差异可列。

### 3.5 结果文件（均已提交，单个文件远小于 5 MB，无需列出未提交项）

`docs/v08/V8-11/` 下：`regress_quick.json`、`regress_quick_mismatches.csv`、`regress_quick_progress.txt`、`regress_full.json`、`regress_full_mismatches.csv`、`regress_full_progress.txt`。原始输出同时保留在 `_handoff\2026-11-02_V8-11_criteria\out\`。

## 4. 分支与提交

| 项 | 值 |
|---|---|
| 审查分支 | `review/v08/V8-11-criteria` |
| 基于 | `2bbe8ad`（= V8-10 审查分支末尾 = 合并后的 `dev/v0.8`） |
| `dev/v0.8` | 推送前 `03ac333`，推送后 `2bbe8ad`（快进；`git ls-remote` 核对为 `2bbe8ad328cb9fa19a9284b634bedfbc8e5e5db0`） |
| 第 1–3 部分提交 | `d8d4f6d`、`c0da1ef`、`dd1595d`、`2124623` |
| 推送后远端（第 3 部分后，`git ls-remote` 核对） | `2124623cf546558003cf1662614a34e57a37974a` |
| `main` | 未推送；远端仍为 `bb262b3b8e679613ce6c13ff205c15fd88b1d10d` |
| 报告提交 | 报告文件无法写入自己的提交号；报告提交与推送后的分支头见 `git log` / `git ls-remote origin refs/heads/review/v08/V8-11-criteria` |

## 5. 改动清单

`git diff --stat dev/v0.8`（取自第 3 部分提交 `2124623`，报告提交前）：

```
 .../configs/v08/criteria_segment.json              |  51 +++++
 Multi-UAV SimpleGC/configs/v08/guidance.json       |  12 +-
 Multi-UAV SimpleGC/scripts/v08/v8_11_regress.py    | 212 +++++++++++++++++++++
 Multi-UAV SimpleGC/tests/v08/V8-11/synth_v8_11.py  | 149 +++++++++++++++
 .../tests/v08/V8-11/test_preset_v8_11_regress.py   | 127 ++++++++++++
 .../tests/v08/V8-11/test_preset_v8_11_segment.py   | 173 +++++++++++++++++
 .../tests/v08/V8-11/test_preset_v8_11_validity.py  | 158 +++++++++++++++
 .../tests/v08/V8-11/test_preset_v8_11_window.py    | 205 ++++++++++++++++++++
 Multi-UAV SimpleGC/v08/criteria/__init__.py        |   1 +
 Multi-UAV SimpleGC/v08/criteria/segment.py         | 138 ++++++++++++++
 Multi-UAV SimpleGC/v08/criteria/validity.py        | 121 ++++++++++++
 Multi-UAV SimpleGC/v08/criteria/window.py          | 210 ++++++++++++++++++++
 docs/v08/V8-11/regress_full.json                   |  43 +++++
 docs/v08/V8-11/regress_full_mismatches.csv         |   1 +
 docs/v08/V8-11/regress_full_progress.txt           |  10 +
 docs/v08/V8-11/regress_quick.json                  |  43 +++++
 docs/v08/V8-11/regress_quick_mismatches.csv        |   1 +
 docs/v08/V8-11/regress_quick_progress.txt          |   1 +
 docs/v08/V8-11/tests_part1.txt                     |  53 ++++++
 docs/v08/V8-11/tests_part2.txt                     |  46 +++++
 docs/v08/V8-11/tests_part3.txt                     |  89 +++++++++
 21 files changed, 1838 insertions(+), 6 deletions(-)
```

（V8-10 的改动在 `dev/v0.8` 合并时已进入基线，不在此统计内。）`guidance.json` 的 diff 只有 6 行，即 `budget_factor`（0.5 → 0.1）、`budget_const_s`（60 → 30）两项的取值、类别（`pending_measurement` → `engineering_margin`）和来源说明。

**是否触碰禁止范围：** 否。
- `git diff --name-only dev/v0.8` 中没有 `task_v07/`、`scene_v07/`、`swarm_sim/`、`configs/criteria/`、`configs/fast_dynamics/`、`v08/sim/`、`v08/config.py`、`configs/v08/sim.json`、`tests/v08/V8-0*` 下的路径。
- 冻结工作树：开始前与第 2、3 部分提交后各查一次，`git status --porcelain` 均为空；头提交 `Simulation-fe-prod-r3` = `641a9b3`、`Simulation-fe-s3` = `de4d115`。
- `SwarmData\v07_*`：回归脚本前后快照 `data_unchanged` 为真（快速 160 个、全量 3200 个文件的大小与修改时间无变化）；另在全部回归结束后检查，`v07_*` 目录下最近 240 分钟内修改过的文件数为 0。所有回归输出写在 `_handoff\...\out\`。
- conda `llm` 环境：只运行，未安装、升级任何包。

## 6. 指令包文件 SHA256 对照（附录 A）

指令包源文件和放入仓库后的文件，各计算一次，与附录 A 逐个比对，12/12 一致。

| 放入位置（相对 `Multi-UAV SimpleGC/`） | SHA256 | 与附录 A |
|---|---|---|
| `configs/v08/guidance.json` | `4183109ae556194a0ba1d25c5f6dbbf7bd622d8e15ac1076631b245b16091378` | 一致 |
| `v08/criteria/__init__.py` | `c3677c76a2ecc2b13ab24a83b2800da91502093d3deb224e8aa24679627bd4e8` | 一致 |
| `v08/criteria/window.py` | `447c4cd96b1f312f19d866b8c1f7606ec13f22d4a7fdff36a7b16651b05fed6f` | 一致 |
| `v08/criteria/validity.py` | `9386726267561dff1fbdcec1ac973db82f4c13902013410275a809e13a061675` | 一致 |
| `scripts/v08/v8_11_regress.py` | `f22e46135adcc6c24c237b1f7a7c3c7198b005873a3c0a956543fbe8f846cf69` | 一致 |
| `tests/v08/V8-11/synth_v8_11.py` | `cb0f2776305b4660181de5776cb3da4a8d784b0c8f982e4cb7b33bdf742a4049` | 一致 |
| `tests/v08/V8-11/test_preset_v8_11_window.py` | `41b29cba8cb19257f36896fcf947f8c553e40313ed391be14991b6ee5fd81f9c` | 一致 |
| `tests/v08/V8-11/test_preset_v8_11_validity.py` | `77697d61b50b1854c91ed1d492bbd6c908cdcb92c7b46d6713ec71894f84735c` | 一致 |
| `tests/v08/V8-11/test_preset_v8_11_regress.py` | `51673188414f04eda97cec614e27c65644614ea21956bac65ac5b9a45b1c1bd4` | 一致 |
| `configs/v08/criteria_segment.json` | `45b2bee8f836c517ad0c730025a74762a0fc42487c8a6d4727af5a175a6e934a` | 一致 |
| `v08/criteria/segment.py` | `41842820521d56e4f5cdb61a4d958a37088349a44b472942c04b5ceff38585a1` | 一致 |
| `tests/v08/V8-11/test_preset_v8_11_segment.py` | `0e4961c1a7363c3f70ece1d4cef9de700fb1c54d6373deb7a46c0ec5979de513` | 一致 |

## 7. 测试逐项结果

命令均在 `Multi-UAV SimpleGC` 目录下，环境变量 `PYTHONDONTWRITEBYTECODE=1`、`OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`，前缀为 `C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B`。

| 阶段 | 命令（`python -B -m unittest discover` 之后） | 结果 | 耗时 | 输出位置 |
|---|---|---|---|---|
| 1 | `-s tests/v08/V8-08 -p "test_*.py" -v` | 24/24 通过 | 3.490 s | `tests_part1.txt` |
| 1 | `-s tests/v08/V8-04 -p "test_*.py" -v` | 11/11 通过 | 12.688 s | `tests_part1.txt` |
| 2 | `-s tests/v08/V8-11 -p "test_preset_v8_11_window.py" -v` | 5/5 通过 | 1.291 s | `tests_part2.txt` |
| 2 | `-s tests/v08/V8-11 -p "test_preset_v8_11_validity.py" -v` | 8/8 通过 | 0.078 s | `tests_part2.txt` |
| 2 | `-s tests/v08/V8-11 -p "test_preset_v8_11_regress.py" -v` | 3/3 通过 | 0.997 s | `tests_part2.txt` |
| 3 | `-s tests/v08/V8-11 -p "test_preset_v8_11_segment.py" -v` | 14/14 通过 | 1.230 s | `tests_part3.txt` |
| 3 | `-s tests/v08/V8-11 -p "test_preset_*.py" -v` | 30/30 通过 | 3.668 s | `tests_part3.txt`（追加） |

预置测试的方法（完整输出在上述文件）：

- window（5）：`test_full_windows`、`test_prefix_windows`、`test_time_shift`、`test_dwell_anywhere`、`test_invalid_inputs`
- validity（8）：`test_parallel`、`test_interframe_near_miss`、`test_interp_not_above_sampled`、`test_visibility_and_offsets`、`test_matches_v07`、`test_boundary_is_inside`、`test_outside_world_record_only`、`test_invalid`
- regress（3）：`test_zero_mismatch`、`test_detects_tampering`、`test_list`
- segment（14）：`test_values`、`test_monitoring_then_intrusion`、`test_area_search_group`、`test_close_observation_dwell_allowed`、`test_pre_release_frames_excluded`、`test_monitoring_hover`、`test_other_facility_alert`、`test_target_too_deep`、`test_feint_not_exited`、`test_final_not_withdrawn`、`test_transit_starts_inside`、`test_coverage_short`、`test_close_observation_too_short`、`test_contract_errors`

## 8. 偏离指令之处；疑似预期错误

**偏离：**
1. 执行方为 Claude Sonnet 5.5（`claude-sonnet-5-5`），指令的"建议执行模型"是低价模型（DeepSeek 即可）。该建议非停止条件。
2. `tests_part1.txt` 开头加了两行说明（Python 版本、命令）和每条命令后的 `exit_code_*=` 行，不是测试器的原始输出。`tests_part2.txt`、`tests_part3.txt` 同样在每条命令前后加了命令行和 `exit_code_*=` 行。`tests_part3.txt` 依指令第 3 部分第 3 步包含两次运行（先 segment 单文件，再全部预置测试），所以段核验的 14 项在文件里出现两次。
3. 命令通过 Git Bash 而非 PowerShell 发出，conda 与 Python 命令行相同。
4. 回归脚本本身带一个 `list_sha256` 内置清单校验，第 2.3 节没有单独列它；已在 3.1 写出。

**疑似预期错误：** 无。

**其他与指令估时的差别（事实，不算偏离）：** 快速回归 28.6 s（指令估约 1 分钟）；全量回归 439.8 s（估 5–15 分钟）。

## 9. 复跑命令（给用户）

全量回归，输出到 `out_rerun`（脚本自动创建目录并写 `regress_full.json`、`regress_full_mismatches.csv`、`regress_full_progress.txt`；JSON 和 CSV 同名会覆盖，进度文件为追加写入（`v8_11_regress.py` 第 191 行），所以请用新目录）：

```
cd "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08\Multi-UAV SimpleGC"
$env:PYTHONDONTWRITEBYTECODE="1"; $env:OMP_NUM_THREADS="1"; $env:OPENBLAS_NUM_THREADS="1"; $env:MKL_NUM_THREADS="1"
C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B scripts/v08/v8_11_regress.py --data-root "F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData" --stage full --out "F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-02_V8-11_criteria\out_rerun"
```

退出码：0 全部一致；2 有差异；3 样本读不到或清单 SHA256 不符；4 数据目录大小或修改时间有变化。预期输出 `samples`=`verified`=200、`members`=1440、`mismatch_count`=0、`data_unchanged`=true。

## 10. 环境版本

| 项 | 值 |
|---|---|
| Python | 3.12.3（conda-forge，MSC v.1938，64 位）；conda 环境 `llm` |
| NumPy | 2.5.3 |
| shapely | 2.0.7 |
| conda | 26.1.1 |
| 系统 | Windows 11 Pro 10.0.26200 |
| 实际使用的模型 | Claude Sonnet 5.5（`claude-sonnet-5-5`） |

## 11. 执行方观察（与上文事实分开）

- 全量回归的 20 条一档用时很不均匀：累计 13、28、39、57、235、399、405、412、421、439 s，即相邻档约 13、15、11、18、**178**、**164**、6、7、9、18 s。第 81–120 条这两档慢了一个数量级，之后又回到每档 6–18 s。快速回归（前 10 条）用时 28.6 s。我没有对这一现象做过任何诊断，只能判断它不影响正确性（差异为 0、数据未变动），原因不明；可能与磁盘读取或系统后台负载有关，这只是猜测。
- 本次回归的样本里，`unsettled_samples` 为 0，即 200 条都是已结束样本。指令 2.2 节提到的"未结束窗口上的恰好一次"沿用 v0.7，这条路径没有被本次回归覆盖（预置测试里有无覆盖我没有核实）。
- 快速集（10 条）包含全部六个意图，但区域侦察和抵近观察各只有 1 个编组，`shared_coverage` 只比较了 1 次；全量里是 22 次。快速检查点对这两类的把关较弱。
- `dev/v0.8` 已按指令第 1 部分第 2 步推送到 `2bbe8ad`（快进）。
