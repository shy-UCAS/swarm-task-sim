# S1.5 仿真试点报告（下游链路：规划 → M2 预演/时刻 → 联合 fastsim → M1 → 审计）

## 结论

（阶段 1 与阶段 2 完成后在此填写运行状态、严格配对结果、失败环节与 M1 实测事实；结论由审查方写，本报告只记录执行、数字与异常。）

## 性质与边界

这是一次**下游链路的端到端打通试点**，不是 M2/M1 合格性试验。三点限制：

1. **样本按规划成功筛出**：只取阶段 2 抽签附录中 `classification == "全成功"` 的抽签，因此结构上不会覆盖阶段 2 发现的形态层失败（如单组 intrusion + `same_direction` 的形状搜索饱和）。它能回答"链路在有利样本上跑不跑得通、M1 看不看得见该看的"，不能回答产率。
2. **独立样本只有 6 次抽签**：同一 `(family, slot)` 的 5 个意图共享同一次公共抽签（阶段 2 已逐对核实 32/32 完全一致），故 30 个骨架对应 6 个独立几何抽签。
3. **后端为 fastsim**，未做 SITL 校准；本试点不启动 SITL。

本试点不改动规划器、M1、M2 或 fastsim 的任何代码。

## 选样

### 规则

读 `docs/v07/evidence/s15/s15_yield_summary.json` 的 `draw_appendix`：在 `classification == "全成功"` 的抽签里，按 `approach_mode` 分两组（组序为 `approach_mode` 字符串升序），每组按 `family#slot` 字符串升序取前 3 次，共 6 次抽签；每次抽签的 5 个意图全部纳入，共 30 个骨架。实现见 `scripts/run_v07_s15_sim_pilot.py::select_draws`，清单落在仓库外 `SwarmData/v07_dataset/s15_sim_pilot_selection.json`。

### 选中的 6 次抽签

| approach_mode | family#slot | layout | 设施数 | 组数 | 各组成员数 |
|---|---|---|---|---:|---|
| multi_direction | `family_s15_1b876e6b8b6f70c6#slot1` | single | 1 | 1 | 10 |
| multi_direction | `family_s15_aa4c66be8e85d64d#slot0` | single | 1 | 1 | 9 |
| multi_direction | `family_s15_c713f51898e81011#slot0` | clustered | 3 | 1 | 10 |
| same_direction | `family_s15_1c267d4d7000043d#slot1` | clustered | 2 | 1 | 6 |
| same_direction | `family_s15_38bedc9d791d547b#slot1` | clustered | 2 | 1 | 7 |
| same_direction | `family_s15_79c93b22d09e8a7a#slot0` | clustered | 3 | 2 | 4 / 2 |

### 30 个骨架的 role/execution_method 计数

按骨架计；含多个 `task_group` 的骨架会出现在多个 role/execution_method 下，故各行之和大于 30。

| role/execution_method | 骨架数 |
|---|---:|
| feint/feint | 8 |
| monitoring/monitoring | 7 |
| intrusion/intrusion | 6 |
| transit/transit | 6 |
| reconnaissance/close_observation | 5 |
| **reconnaissance/area_search** | **2** |

### `reconnaissance/area_search` 判定与追加结论

30 个骨架中 `reconnaissance/area_search` 为 **2**，不为 0，因此**按补充规则不追加抽签**：阶段 2 仍为剩余 5 次抽签 / 25 个骨架，墙钟上限保持 4500 s。判定的完整记录（含计数、`area_search` 骨架清单、规则原文与否决理由）写入 `SwarmData/v07_dataset/s15_sim_pilot_selection.json` 的 `note` 字段。

两个 `area_search` 骨架的局限，读数时须注意：

- 只有 2 个骨架，样本少；
- `family_s15_1b876e6b8b6f70c6_ext_006_regular`（抽签 `family_s15_1b876e6b8b6f70c6#slot1`，single 布局、单组 10 名成员）为纯 area_search；
- `family_s15_79c93b22d09e8a7a_ext_001_regular`（抽签 `family_s15_79c93b22d09e8a7a#slot0`，clustered、3 设施、双组 4/2）的**同一骨架同时含 `reconnaissance/area_search` 与 `reconnaissance/close_observation`**，不是干净的单角色对照，其成败无法单独归因给 area_search。

## 执行

### 止损与阶段划分

按指令：先跑第 1 次抽签（`family_s15_1b876e6b8b6f70c6#slot1` 的 5 个骨架），上限 1500 s；出现 `P0ContractError`、进程异常，或 5 个骨架全部没有得到严格配对，就停下汇报。通过后再跑其余 5 次抽签（25 个骨架），上限 4500 s。

### 阶段 1（第 1 次抽签，5 个骨架）

```
scripts/run_v07_s15_sim_pilot.py \
    --skeletons-file <SwarmData>/v07_dataset/s15_sim_pilot_stage1.json --wall-limit-s 1500
```

attempt：`<SwarmData>/v07_dataset/attempt_s15sim_20261016T184726Z`。

| 项 | 值 |
|---|---|
| 状态 | `TIME_LIMIT_STOP`（到达 1500 s 上限） |
| 完成 | 4/5（`family_s15_1b876e6b8b6f70c6_ext_007_regular` 未跑完） |
| 墙钟 | 1500.1 s |
| 运行前后源码指纹一致 | 是 |
| 严格配对（同步与递次两版都成功） | 4/5 |
| 实测逼近方式与指定一致 | 8/8 次比较 |

止损三条核对：无 `P0ContractError`；无进程异常（唯一停止是墙钟上限）；5 个骨架中 4 个**已得到**严格配对，不满足"全部未配对"。**未触发止损，进入阶段 2。**

逐骨架（轮数 = `single_agent_calibration_rounds`）：

| skeleton_id | 意图 | 指定方式 | 严格配对 | 轮数 | 墙钟 s |
|---|---|---|---|---:|---:|
| `…6e6b8b6f70c6_ext_005_regular` | transit | multi_direction | 是 | 2 | 611.2 |
| `…6e6b8b6f70c6_ext_006_regular` | reconnaissance | multi_direction | 是 | 4 | 1120.2 |
| `…6e6b8b6f70c6_ext_007_regular` | — | multi_direction | 未跑完 | — | — |
| `…6e6b8b6f70c6_ext_008_regular` | feint | multi_direction | 是 | 2 | 685.5 |
| `…6e6b8b6f70c6_ext_009_regular` | penetration | multi_direction | 是 | 1 | 387.8 |

失败环节计数（链路顺序取第一个失败环节）：全为 0；唯一未配对的是**未跑完**，不是失败。

M1 实测事实（阶段 1 共 8 个 episode 行）：

- 实测逼近方式与指定一致 **8/8**；
- 驻留检出：`reconnaissance` 16/20 名参与成员、`feint` 20/20、`penetration` 9/20、`transit` 0/20；重访检出与观察驻留检出均为 0（本阶段无 monitoring 样本）；
- 实测最小机间距：min 2.196 m、p50 13.296 m、p90 15.744 m、max 15.754 m。

分阶段墙钟（4 个已跑完骨架，s；口径见统计脚本 P6 注）：

| 阶段 | min | p50 | max |
|---|---:|---:|---:|
| 规划 | 56.80 | 78.53 | 90.28 |
| 单机预演+时刻安排（合并） | 160.33 | 352.84 | 738.49 |
| 联合仿真 | 158.05 | 199.26 | 261.52 |
| M1 判定+审计+测量+写盘（合并） | 12.59 | 14.15 | 37.01 |
| 合计 | 387.78 | 648.36 | 1120.17 |

统计证据：[stage1/s15_sim_pilot_tables.md](../evidence/s15/sim_pilot/stage1/s15_sim_pilot_tables.md)、[stage1/s15_sim_pilot_summary.json](../evidence/s15/sim_pilot/stage1/s15_sim_pilot_summary.json)。

### 阶段 2（其余 5 次抽签，25 个骨架）

（完成后填写。）

## 提交范围

| 提交 | 内容 |
|---|---|
| `d3cbab3` S15-P1 | 试点入口脚本 `scripts/run_v07_s15_sim_pilot.py` |
| `b9950d2` S15-P2 | 试点统计脚本 `scripts/summarize_v07_s15_sim_pilot.py` |
| 待填 S15-P3 | 阶段 1 证据与本报告 |
| 待填 S15-P4 | 阶段 2 证据与报告收尾 |

分支 `v07-s15`；入口提交 `31dfcec65e648b4065387e842b3947f9df7c699e`；未推送到 `v07-scene`，未使用强制推送。
