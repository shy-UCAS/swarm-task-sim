# V8-04 逐成员分段仿真与统一时钟拼接 报告

- 工作项：V8-04（里程碑 ③ 单段原型，实现类）；执行日期 2026-11-01；执行方：Claude Code（Windows 主机）。
- 依据：`_handoff/2026-11-01_V8-04_sim-adapter/V8-04_逐成员分段仿真与统一时钟拼接_执行指令_20261101.md`（下文"指令"），以及用户在对话中的补充说明（以本指令为准；允许快进合并并推送 `dev/v0.8`、推送本审查分支；推送被拦时停下询问）。

---

## 0. 复述与环境

### 0.1 任务复述

本任务实现 v0.8 的仿真适配层：每个成员单独交给冻结的点质量仿真器执行，同一段内的速度小段之间、段与段之间从 (p, v, a) 续跑，再把各成员的结果拼到编组统一时钟（10 Hz，微秒）上，供 V8-06 标定和 V8-08 之后的运动生成使用。四个部分：（1）快进合并 V8-03 并推送 `dev/v0.8`，在三份说明文件开头插入附录 C；（2）`configs/v08/sim.json`、`v08/config.py` 与数据对象 `v08/sim/types.py`；（3）`stitch`：按 r3 8.4 检查连续性并拼接，不填充不对齐；（4）`run_member_segment`：记录跟踪器的经过时刻、延伸段、越过帧切段、逐小段续跑。停止条件：冻结工作树或 `SwarmData\v07_*` 被写入；`test_recording_is_bitwise_identity_and_witnesses_all_nodes` 不通过则停第 4 部分；认为预置测试预期有错则该项停下报告。不得修改：冻结工作树 `Simulation-fe-prod-r3`、`Simulation-fe-s3`，`SwarmData\v07_*`（本任务不读不写），仓库中 `task_v07/`、`swarm_sim/`、`scene_v07/`（只导入；对 `task_v07.execution.RouteTracker` 的替换只在调用期间生效），conda `llm` 环境，预置测试与 `sim.json`。

### 0.2 合并与环境

| 项 | 结果 |
|---|---|
| 开工前 | 开发工作树、`Simulation-fe-prod-r3`、`Simulation-fe-s3` 的 `status --porcelain` 均为空；`dev/v0.8` = `6c171d7` |
| 合并 V8-03 | `fetch origin refs/heads/review/v08/V8-03-offline-check:…` 后 `merge --ff-only` 成功，`dev/v0.8` = `97e757f` |
| 推送 `dev/v0.8` | 成功（`6c171d7..97e757f`）；`git ls-remote` 核对远端 `dev/v0.8` = `97e757f7d37f13e80d0ac11997a33d16620f935f` |
| 审查分支 | 从 `dev/v0.8`（`97e757f`）新建 `review/v08/V8-04-sim-adapter` |
| 预置文件 SHA256 | `sim.json` = `e5e2e91f…a3e91d`，`test_preset_v8_04.py` = `e3ff9847…7f9f23c`，放入仓库后与指令一致 |
| 运行环境 | `conda run -n llm --no-capture-output python -B`；Python 3.12.3（conda-forge）、NumPy 2.5.3；`PYTHONDONTWRITEBYTECODE=1`、`OMP/OPENBLAS/MKL_NUM_THREADS=1` |
| 停止条件 | **未触发** |

---

## 1. 每部分结论

| 部分 | 结论 | 证据 |
|---|---|---|
| 1 合并与说明文件 | **完成。** 三份文件开头插入附录 C 原文并空一行；去掉插入段后其余字节与 `97e757f` 中的原文件逐字节相同 | 提交 `47c7eda` |
| 2 配置与数据对象 | **通过**，`-k TestConfig` 2/2 | `preset_tests_part2.txt`，提交 `3a1be18` |
| 3 统一时钟拼接 | **通过**，`-k TestStitch` 3/3 | `preset_tests_part3.txt`，提交 `3c2f101` |
| 4 逐成员分段仿真 | **通过**，`-k TestRecordedExecute -k TestRunMemberSegment` 6/6；全部 11 项 11/11 | `preset_tests_part4.txt`、`preset_tests_all.txt`，提交 `74ab2e2` |

第 4 部分的补充测量（预置测试 `test_split_on_straight_leg_matches_unsplit_and_does_not_brake` 的同一用例，单独脚本运行，未提交）：

| 速度 | 切段与不切段的最大位置差 | 切换时刻 τ | 经过时刻（本地） | 越过帧 | 丢弃帧 |
|---|---|---|---|---|---|
| 6 m/s | 3.214e-11 m | 69.0 s | 68.852882 s | 690 | 84 |
| 10 m/s | 4.193e-07 m | 55.9 s | 55.769388 s | 559 | 115 |

与指令所述规划审查方云端实测（3e-11 m、4e-7 m）一致。

---

## 2. 分支与提交

| 提交 | 内容 |
|---|---|
| `47c7eda` | V8-04 第 1 部分：合并 V8-03，三份说明文件补当前规则 |
| `3a1be18` | V8-04 第 2 部分：配置与数据对象 |
| `3c2f101` | V8-04 第 3 部分：统一时钟拼接与连续性检查 |
| `74ab2e2` | V8-04 第 4 部分：逐成员分段仿真 |
| 本报告所在提交 | V8-04 报告 |

推送后的远端提交号：`c1a73350627ed466a4bb8068e43c72b85cf42a59`（报告提交 `V8-04 报告`；`git ls-remote origin refs/heads/review/v08/V8-04-sim-adapter` 核对一致）。本行由随后的补记提交写入；补记提交只改本文件，其提交号以远端分支头为准。

## 3. 改动文件清单

`git diff --stat dev/v0.8...HEAD`（本报告所在提交的统计）：

```
 CLAUDE.md                                          |   5 +
 Multi-UAV SimpleGC/AGENTS.md                       |   5 +
 Multi-UAV SimpleGC/CLAUDE.md                       |   5 +
 Multi-UAV SimpleGC/configs/v08/sim.json            |  36 ++++
 .../tests/v08/V8-04/test_preset_v8_04.py           | 231 ++++++++++++++++++++
 Multi-UAV SimpleGC/v08/__init__.py                 |   1 +
 Multi-UAV SimpleGC/v08/config.py                   |  48 +++++
 Multi-UAV SimpleGC/v08/sim/__init__.py             |   1 +
 Multi-UAV SimpleGC/v08/sim/adapter.py              | 234 +++++++++++++++++++++
 Multi-UAV SimpleGC/v08/sim/stitch.py               |  82 ++++++++
 Multi-UAV SimpleGC/v08/sim/types.py                |  84 ++++++++
 docs/v08/V8-04/REPORT.md                           | 145 +++++++++++++
 docs/v08/V8-04/preset_tests_all.txt                |  16 ++
 docs/v08/V8-04/preset_tests_part2.txt              |   7 +
 docs/v08/V8-04/preset_tests_part3.txt              |   8 +
 docs/v08/V8-04/preset_tests_part4.txt              |  11 +
 16 files changed, 919 insertions(+)
```

全部在指令第 0.2 节范围内。`task_v07/`、`swarm_sim/`、`scene_v07/` 无改动（`git diff --stat HEAD -- …` 为空）。

## 4. 预置测试

命令（在 `Multi-UAV SimpleGC` 下）：`conda run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-04 -p "test_preset_*.py" -v [-k 类名]`

| 类 | 测试 | 结果 |
|---|---|---|
| TestConfig | test_sim_config_values_and_kinds | 通过 |
| TestConfig | test_config_rejects_bad_kind_and_missing_source | 通过 |
| TestRecordedExecute | test_recording_is_bitwise_identity_and_witnesses_all_nodes | 通过 |
| TestRunMemberSegment | test_single_final_piece_equals_frozen_execute | 通过 |
| TestRunMemberSegment | test_split_on_straight_leg_matches_unsplit_and_does_not_brake | 通过 |
| TestRunMemberSegment | test_crossing_uses_route_progress_not_first_half_plane_hit | 通过 |
| TestRunMemberSegment | test_speed_change_pieces_in_one_segment | 通过 |
| TestRunMemberSegment | test_contract_violations_raise | 通过 |
| TestStitch | test_async_switch_two_members | 通过 |
| TestStitch | test_duplicate_gap_and_state_mismatch_raise | 通过 |
| TestStitch | test_structure_errors_raise | 通过 |

输出文件：`preset_tests_part2.txt`、`preset_tests_part3.txt`、`preset_tests_part4.txt`、`preset_tests_all.txt`（本目录）。

## 5. 自加的测试

无。

## 6. 偏离指令之处及原因

1. **报告单独一个提交**：指令要求每部分一个提交，报告未指定归属，放在第 4 部分之后的独立提交中；推送后再用一个补记提交写入远端提交号（同 V8-01、V8-03 的做法）。
2. **续跑小段的起点检查时机**：第 0 段第 0 个小段与每段第 0 个小段的起点在运行前检查；同一段内后续小段的起点依赖前一小段的越过帧状态，只能在执行到该小段时检查，违反时同样抛 `SimContractError`（此前的小段已经执行过）。
3. **越过方向所用的航线**：越过判定的来向 `u` 与段末点取自实际交给仿真器的航线（续跑小段已替换第 0 点平面坐标）。只有 `end_index == 1` 时与原航线不同。

## 7. 疑似预期错误

无。

## 8. 复跑命令

```
cd "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08\Multi-UAV SimpleGC"; C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B -m unittest discover -s tests/v08/V8-04 -p "test_preset_*.py" -v
```

应得 `Ran 11 tests`、`OK`。

## 9. 运行信息

| 类 | 项数 | 单独运行耗时 |
|---|---|---|
| TestConfig | 2 | 0.004 s |
| TestRecordedExecute | 1 | 2.2 s |
| TestRunMemberSegment | 5 | 14.5 s |
| TestStitch | 3 | 0.001 s |
| 全部 | 11 | 17.9 s |

冻结工作树最终 `status --porcelain`：`Simulation-fe-prod-r3` 为空，`Simulation-fe-s3` 为空。开发工作树 `status --porcelain --ignored` 无 `__pycache__` 等遗留文件。

---

## 10. 执行方观察（个人判断，与上文事实分开）

- 非最后一段的小段仍会让冻结仿真器跑完延伸段并在末端停稳才返回（例如 10 m/s 用例丢弃 115 帧），越过帧之后的计算都被丢弃。目前单小段耗时不到 1 s，如果 V8-06 之后小段数量很大，这部分会成为可测的开销；冻结 `execute` 不提供提前停止的接口，本任务没有处理。
- `PieceRecord.tau_end_us` 在"有越过帧"时等于下一小段起点，在 `sim_timeout` 或最后小段时等于最后保留帧时刻，两种含义差一帧。按指令实现，使用方需注意。
