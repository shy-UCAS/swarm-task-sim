# V8-12 第 5 部分（已取消，未完成）：已产生结果的汇总

**状态：** 用户在第 5 部分运行中途取消该部分（改用联合时空优化方案）。本文只汇总取消前**已经完成**的仿真、拼接、段核验和有效性检查结果，原样保留，不补跑、不修复；没有对这些结果做任何重算，数字全部取自 `_handoff\2026-11-02_V8-12_monitoring\out\{quick,full}\contracts\*.json`（不入库）。

## 1. 停在哪里

- **快速 10 合同（`--stage quick`）：完整跑完。** 执行 10/10，保留 10/10，复跑逐位一致 10/10，P0 停止无，墙钟 1618 s（预算 7200 s）。`out/quick/summary.json` 已写出。
- **全量（`--stage full --rerun-every 4`）：被取消中断。** 队列 166 个合同（第 4 部分成功的 176 个去掉快速 10 个），取消前**已完成 25 个**，第 26 个（`o31_d0`）正在仿真时被终止，没有写出结果 JSON；`out/full/` 里没有 `summary.json`（进程被终止，汇总是在批次结束时才写的）。其余 140 个**未运行**。
- **合计：已完成 35 个合同**（占第 4 部分成功的 176 个的 19.9%）；其中 `quick` 10、`full` 25。
- 取消前运行的代码是提交 `bc6a679`（快速阶段）和 `dd968e3`（全量阶段，增加 `--rerun-every`）；两者都已在审查分支上。
- `out/full/contracts/` 里有 25 个合同的 JSON 和 25 个轨迹 NPZ，没有半成品（`o31_d0` 没有 JSON 也没有 NPZ）；这些文件原样保留，没有清理；第 4 部分的 `out/plan` 没有被改动。

## 2. 总览（已完成的 35 个合同）

| 项 | 数值 |
|---|---|
| 保留（通过全部门禁）| 35/35 |
| 通过段核验（`verify_segments(...)[0].passed`）| 35/35（未通过的条件：无）|
| 仿真 attempt 总数 / 其中失败 | 35 / 0（每个合同首次仿真即通过，没有候选失败，没有重试）|
| 同键复跑 | 一致 17；待复跑 18（全量阶段按 `i % 4 == 0` 规则只复跑队列中每 4 个里的 1 个，其余未被选中）；不一致 0 |
| 实测最小间距（10 Hz 采样，门禁 ≥ 2 m）| 最小 3.450 m（有两机以上的 31 个合同；其余 4 个是单机，没有成员对）|
| 实测最小间距（帧间插值，仅诊断）| 最小 3.449 m |
| 跟踪管横向偏差（诊断，管半径 0.5 m）| 151 个成员：最大 0.589 m（o17_d0 uav_01）；各成员 p95 的最大值 0.0117 m；超管帧数 41/2322269 |
| 限制区内帧数 / 世界外帧数 / 非目标设施 alert 以上帧数 | 0 / 0 / 0 |
| 变速冲高（实测速度超过相邻两档期望速度最大值的正差，诊断）| 最大 0.427 m/s，151/151 个成员为正 |
| 相邻帧速度差（诊断，V8-10 参照 0.277 m/s）| 全程最大 0.372 m/s；仅变速站点区间内最大 0.273 m/s |
| 边界进出：超出计划穿越次数的成员数 / alert 层进出 / 驻留拒绝 | 0/151 / 0 / 0 |
| 首次执行墙钟（仿真 + 诊断，含读入）| 合计 1901 s；单合同 10–146 s |

**说明。** 相邻帧速度差的全程最大值 0.372 m/s 在每个成员上几乎相同（0.37206–0.37208），我核对了全部 151 个成员：最大值的位置都在释放后 1 s 以内，即起飞加速段，不是变速站点；只看变速站点区间内最大 0.273 m/s。这是诊断数值，不是门禁；本次没有对它设阈值。

**跟踪管有超出 0.5 m 的帧。** 快速 10 个合同没有；全量已完成的 25 个里有成员超出，明细见下表。跟踪管在本项只作诊断（附录裁定 11：不触发重做，不新增门禁），所以这些合同仍被保留；超出的成员在段核验、间距、限制区、层级上都没有问题。

| 合同 | 成员 | 超 0.5 m 帧数 | 最大偏差(m) | 首次超出：时刻(s) / 进度 s(m) / 期望速度档(m/s) / 位置 xy(m) |
|---|---|---:|---:|---|
| o17_d0 | uav_01 | 9 | 0.589 | 1518.9 / 11181 / 8.64 / (2828, 2733) |
| o17_d0 | uav_02 | 8 | 0.581 | 1521.7 / 11686 / 8.64 / (2828, 2733) |
| o17_d0 | uav_03 | 8 | 0.584 | 1530.2 / 11157 / 8.64 / (2828, 2733) |
| o17_d0 | uav_04 | 8 | 0.583 | 1524.6 / 11449 / 8.64 / (2828, 2733) |
| o17_d0 | uav_12 | 8 | 0.585 | 1527.3 / 11882 / 8.64 / (2828, 2733) |

## 3. 逐合同结果

列：设施数 | 编组人数 | 拓扑 | 实际队形 | 名义总时长(s) | 状态 | 仿真 attempt 数 | **是否通过段核验** | **未通过的条件** | **实测最小间距：10 Hz 采样 / 帧间插值（m；单机为 —）** | **跟踪偏差：成员最大 / 各成员 p95 的最大 / 超 0.5 m 帧数（m、m、帧）** | 复跑 | 首次执行墙钟(s)

| 合同 | 阶段 | 设施 | n | 拓扑 | 队形 | 时长 | 状态 | attempt | 段核验通过 | 未通过条件 | 最小间距 采样/插值 | 跟踪偏差 | 复跑 | 墙钟 |
|---|---|---:|---:|---|---|---:|---|---:|---|---|---|---|---|---:|
| o01_d0 | quick | 1 | 2 | retrace | column | 1734 | retained | 1 | 是 | 无 | 9.674 / 9.668 | 0.169 / 0.0024 / 0 | equal | 35 |
| o01_d1 | quick | 1 | 6 | retrace | column | 1650 | retained | 1 | 是 | 无 | 14.136 / 14.135 | 0.115 / 0.0063 / 0 | equal | 81 |
| o01_d2 | quick | 1 | 1 | retrace | echelon | 1274 | retained | 1 | 是 | 无 | — / — | 0.235 / 0.0117 / 0 | equal | 10 |
| o01_d3 | quick | 1 | 6 | loop | echelon | 1740 | retained | 1 | 是 | 无 | 23.843 / 23.843 | 0.084 / 0.0005 / 0 | equal | 78 |
| o01_d4 | quick | 1 | 2 | retrace | echelon | 1392 | retained | 1 | 是 | 无 | 23.833 / 23.833 | 0.174 / 0.0038 / 0 | equal | 21 |
| o02_d0 | quick | 2 | 9 | retrace | column | 1361 | retained | 1 | 是 | 无 | 5.756 / 5.755 | 0.286 / 0.0050 / 0 | equal | 127 |
| o02_d1 | quick | 2 | 4 | retrace | column | 1704 | retained | 1 | 是 | 无 | 6.510 / 6.496 | 0.127 / 0.0031 / 0 | equal | 53 |
| o03_d0 | quick | 3 | 4 | retrace | column | 1587 | retained | 1 | 是 | 无 | 12.070 / 12.067 | 0.104 / 0.0023 / 0 | equal | 53 |
| o11_d3 | quick | 2 | 8 | retrace | column | 1783 | retained | 1 | 是 | 无 | 10.769 / 10.769 | 0.130 / 0.0035 / 0 | equal | 115 |
| o17_d1 | quick | 2 | 12 | retrace | column | 1520 | retained | 1 | 是 | 无 | 3.450 / 3.449 | 0.187 / 0.0021 / 0 | equal | 146 |
| o04_d0 | full | 1 | 2 | loop | echelon | 1796 | retained | 1 | 是 | 无 | 16.162 / 16.162 | 0.084 / 0.0010 / 0 | equal | 25 |
| o05_d0 | full | 2 | 9 | retrace | column | 1575 | retained | 1 | 是 | 无 | 12.677 / 12.672 | 0.084 / 0.0016 / 0 | pending（not_selected_by_rerun_policy） | 104 |
| o06_d0 | full | 1 | 6 | loop | echelon | 1644 | retained | 1 | 是 | 无 | 13.027 / 13.027 | 0.084 / 0.0008 / 0 | pending（not_selected_by_rerun_policy） | 67 |
| o07_d0 | full | 1 | 6 | retrace | column | 1375 | retained | 1 | 是 | 无 | 10.973 / 10.972 | 0.120 / 0.0012 / 0 | pending（not_selected_by_rerun_policy） | 64 |
| o08_d0 | full | 2 | 1 | retrace | column | 1766 | retained | 1 | 是 | 无 | — / — | 0.174 / 0.0062 / 0 | equal | 11 |
| o09_d0 | full | 1 | 2 | retrace | abreast | 1683 | retained | 1 | 是 | 无 | 21.500 / 21.500 | 0.159 / 0.0025 / 0 | pending（not_selected_by_rerun_policy） | 29 |
| o10_d0 | full | 1 | 5 | loop | abreast | 1651 | retained | 1 | 是 | 无 | 8.913 / 8.910 | 0.084 / 0.0011 / 0 | pending（not_selected_by_rerun_policy） | 61 |
| o12_d0 | full | 1 | 2 | retrace | column | 1525 | retained | 1 | 是 | 无 | 12.597 / 12.597 | 0.093 / 0.0030 / 0 | pending（not_selected_by_rerun_policy） | 22 |
| o13_d0 | full | 3 | 1 | loop | abreast | 1745 | retained | 1 | 是 | 无 | — / — | 0.083 / 0.0004 / 0 | equal | 14 |
| o14_d0 | full | 3 | 3 | loop | column | 1656 | retained | 1 | 是 | 无 | 17.785 / 17.784 | 0.086 / 0.0012 / 0 | pending（not_selected_by_rerun_policy） | 36 |
| o15_d0 | full | 1 | 1 | retrace | echelon | 1412 | retained | 1 | 是 | 无 | — / — | 0.147 / 0.0045 / 0 | pending（not_selected_by_rerun_policy） | 11 |
| o16_d0 | full | 2 | 4 | retrace | column | 1731 | retained | 1 | 是 | 无 | 7.749 / 7.749 | 0.225 / 0.0018 / 0 | pending（not_selected_by_rerun_policy） | 55 |
| o17_d0 | full | 2 | 5 | loop | column | 1673 | retained | 1 | 是 | 无 | 18.289 / 18.289 | 0.589 / 0.0013 / 41 | equal | 64 |
| o18_d0 | full | 3 | 6 | retrace | column | 1664 | retained | 1 | 是 | 无 | 7.631 / 7.630 | 0.157 / 0.0029 / 0 | pending（not_selected_by_rerun_policy） | 76 |
| o19_d0 | full | 1 | 3 | loop | echelon | 1412 | retained | 1 | 是 | 无 | 25.761 / 25.761 | 0.084 / 0.0017 / 0 | pending（not_selected_by_rerun_policy） | 32 |
| o20_d0 | full | 1 | 10 | loop | column | 1758 | retained | 1 | 是 | 无 | 4.050 / 4.049 | 0.143 / 0.0006 / 0 | pending（not_selected_by_rerun_policy） | 141 |
| o21_d0 | full | 3 | 5 | loop | echelon | 1765 | retained | 1 | 是 | 无 | 24.781 / 24.781 | 0.084 / 0.0006 / 0 | equal | 63 |
| o22_d0 | full | 2 | 4 | retrace | echelon | 1685 | retained | 1 | 是 | 无 | 10.639 / 10.637 | 0.094 / 0.0019 / 0 | pending（not_selected_by_rerun_policy） | 47 |
| o23_d0 | full | 1 | 4 | retrace | column | 1774 | retained | 1 | 是 | 无 | 8.756 / 8.756 | 0.166 / 0.0022 / 0 | pending（not_selected_by_rerun_policy） | 48 |
| o24_d0 | full | 1 | 4 | retrace | column | 1762 | retained | 1 | 是 | 无 | 19.171 / 19.169 | 0.117 / 0.0023 / 0 | pending（not_selected_by_rerun_policy） | 51 |
| o25_d0 | full | 1 | 4 | loop | abreast | 1675 | retained | 1 | 是 | 无 | 4.696 / 4.695 | 0.083 / 0.0005 / 0 | equal | 47 |
| o26_d0 | full | 3 | 4 | loop | abreast | 1671 | retained | 1 | 是 | 无 | 16.038 / 16.036 | 0.104 / 0.0016 / 0 | pending（not_selected_by_rerun_policy） | 44 |
| o27_d0 | full | 2 | 2 | retrace | abreast | 1474 | retained | 1 | 是 | 无 | 22.386 / 22.386 | 0.138 / 0.0011 / 0 | pending（not_selected_by_rerun_policy） | 21 |
| o29_d0 | full | 2 | 2 | loop | abreast | 1742 | retained | 1 | 是 | 无 | 16.207 / 16.207 | 0.084 / 0.0004 / 0 | pending（not_selected_by_rerun_policy） | 24 |
| o30_d0 | full | 1 | 2 | retrace | column | 1631 | retained | 1 | 是 | 无 | 8.362 / 8.360 | 0.219 / 0.0046 / 0 | equal | 24 |

## 4. 没有做的事和这份汇总的局限

- **没有跑完：** 全量 140 个合同未运行，所以没有第 5 部分要求的完整数字：全量成功率、按设施数/限制区数/人数/拓扑/队形的核验失败率、驻留拒绝单列、修复前后多样性、总仿真耗时，以及对每个保留合同的复跑覆盖（18 个待复跑）。
- **没有候选失败，因此没有失败条件分布：** 已完成的 35 个合同全部首次仿真通过，所以「核验失败率及条件分布」「驻留拒绝」「重试链」在这个样本里都没有数据，不能据此说失败率是 0：样本是快速 10 个（按覆盖规则选，含最大编组 12 人）加全量队列最前面的 25 个（按 draw 轮转、order 递增，draw 0 的各族）。
- **没有做独立复核：** 第 4 部分对规划曲线做过 shapely 独立复核；第 5 部分对实测轨迹的 shapely 独立复核脚本已写好但**没有运行**（取消在先）。上面的限制区、间距、层级数字都来自 V8-11 的 `verify_segments`/`check_validity` 和运行器的诊断，没有第二个预言机。
- **快速阶段的重试语义没有被检验：** 因为没有任何候选失败，`try_segment` 的「从 a+1 接着用 20 次预算」路径只由单元测试（`test_own_part5.py`）用桩覆盖，没有被真实失败触发过。
- **预置测试：** `test_preset_local_simulation.py`（SHA256 `ef4acb7a…08f3`，原样）运行 1/1 通过，33.9 s，完整输出在 `tests_part5_preset.txt`。
- **审查方在取消前给的三项裁定**（多样性缺种子按失败报告；checkpoint 预置测试 1 项失败接受；下游失败触发的队形退让单列）里，退让统计已在第 4 部分记录上算出：176 个保留计划中 71 个（40.3%）实际队形不同于起点，其中 71 个全部由下游几何失败触发（turns 65、patrol_shape 16、start_route 14、ingress 7、separation 5、egress 3、boundary_crossing 1 条触发记录），路径 abreast→column 40、echelon→column 20、abreast→echelon 11；实际队形 column 102 / abreast 40 / echelon 34。该统计没有进入正式报告章节，因为第 5 部分已取消。
