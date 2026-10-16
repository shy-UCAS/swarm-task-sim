# 阶段 2：S1.5 上的现有规划器体检（只规划、只统计）

放置位置：`docs/v07/s15/S15_stage2_yield_instruction.md`
分支：在 `v07-s15` 上继续（当前 HEAD `0ec79e71a78745de9a129886440d1f54532edc53`，标签 `v0.7-s15-frozen`）。只推 `v07-s15`，不推 `v07-scene`，不使用强制推送。

## 0. 项目性质（照录）

本项目是防御方视角的意图识别研究。生成器只产出抽象随机几何场景中带标签的合成轨迹数据集，运动后端为点质量运动学模型，不控制任何真实无人机。本阶段只运行已有的几何规划检查，并对结果做统计，不涉及仿真、任务效果或任何针对防御的优化。

## 1. 目标与边界

**目标：** 在冻结的 S1.5 地图上，用现有规划器（含 F1–F4、F2b 修复）跑纯规划检查，统计各意图的规划成功率与拒绝原因，作为下一阶段设计的依据。

**本阶段只做：** 写三个新脚本（骨架登记、批量规划、统计），先跑快速检查，再跑正式批次，提交统计证据后停下。

**严格禁止：**
- 修改 `task_v07/`、`configs/`、`scene_v07/` 下的任何文件，以及任何已有脚本。只允许**新建**本指令列出的三个脚本和证据文件。
- 运行 fastsim、单机预演、联合仿真或 Q3。
- "顺手"修复规划器或统计中看到的问题。看到异常只记录，不修改。
- 按规划成败挑选、替换或剔除骨架。

开工前核对：`git diff --quiet b035dfd66eb45709d400d953caa1692d23c8be63 HEAD -- task_v07 configs/generator` 必须无差异（证明规划器与 M3b 修复轮一致）。不一致就停下汇报。

## 2. 第 1 步：骨架登记脚本 `scripts/run_v07_s15_descriptors.py`

**输入：** `docs/v07/s15/S15_frozen_baseline.json`（下称"基线"）。

**1) 校验地图：** 对下面选中的每个 family，重新计算其 `public_scene.json` 与 `family_initial.json` 的 SHA256，必须与基线 `families[i].sha256` 一致；不一致即抛出 `P0ContractError` 并停止。

**2) 选择地图（确定性规则，不看规划结果）：**
- 读取基线 `external_attempt_path` 下的 `candidates.json`；只取 `accepted == true` 且 `vehicle_count >= 6` 的记录。
- 按 `layout` 分为四层：`single`、`isolated`、`clustered`、`linear`。
- 每层按 `candidate_index` 升序，取前 **6** 个，共 24 个 family。某层不足 6 个时，取该层全部，并在登记中写明实际数量。

**3) 生成骨架描述：** 对每个选中的 family，调用已有函数
`task_v07.expansion.sampling.sample_family_descriptors((scene, family, 2))`，
只保留 `subset == "regular"` 的描述（每个 family 10 个：2 个公共抽签槽 × 5 个意图），丢弃 `aborted`。预计共 240 个骨架描述。

**4) 输出（仓库外新目录）：** `<SwarmData>/v07_dataset/attempt_s15desc_<UTC时间>/`，其中：
- `registration.json`，格式必须与现有 `scripts/run_v07_s2_expansion.py::descriptor_jobs` 读取的格式一致：
  - `source_attempt`：基线中的 `external_attempt_path`；
  - `selected`：每个 family 一行，包含 `candidate_index`、`family_id`、`layout`、`facility_count`、`vehicle_count`、`source_sha256`（两个文件名 → SHA256）。
  - 另加：`selection_rule`（照抄上面第 2 条）、`baseline_sha256`（基线文件自身的 SHA256）、`entry_commit`、`per_layout_counts`。
- `private_skeleton_descriptors.json`：全部 regular 描述，按 `skeleton_id` 排序。

**5) 自检：** 用 `descriptor_jobs(<该目录>, [全部 skeleton_id], <临时目录>)` 能成功构造任务列表，且数量等于描述数。

## 3. 第 2 步：批量规划脚本 `scripts/run_v07_s15_yield.py`

**直接复用已有函数，不复制、不修改：**
- 任务列表：`scripts/run_v07_s2_expansion.py::descriptor_jobs`
- 并行运行：`scripts/run_v07_m3b_trial.py::run_stage`，以 `"q2"` 模式调用。它内部用 8 进程调用 `scripts/run_v07_m3_trial.py::planning_job`，每个骨架在 `<attempt>/<skeleton_id>/` 下写出 `proposals.jsonl`、`candidate_pool.json`、`planning_result.json`，有合格组合时还写 `selected_skeleton.json` 与 `selected_checks.json`。
- 源码指纹：`scripts/run_v07_m3b_trial.py::runtime_hashes`

**参数：** `--descriptors <第1步目录>`、`--limit <N>`（只跑按 skeleton_id 排序的前 N 个；不传则全部）、`--wall-limit-s <秒>`。

**流程：**
1. 启动前要求工作区完全干净（`git status --porcelain --untracked-files=all` 为空），否则拒绝运行。
2. 新建 `<SwarmData>/v07_dataset/attempt_s15yield_<UTC时间>/`，写 `registration.json`：入口提交 SHA、`runtime_sha256`、描述目录及其 `private_skeleton_descriptors.json` 的 SHA256、选中的 skeleton_id 列表、`limit`、`wall_limit_s`、8 进程、"每组 200 提案、组合预算 1000（规划器内置值，未改）"。
3. 调用 `run_stage("q2", jobs, out, deadline, completed, rows)`。
4. 结束后再算一次 `runtime_hashes()`，必须与启动时一致，否则判为 P0。
5. 写 `run_result.json`：状态（`completed` / `TIME_LIMIT_STOP` / `ERROR_STOP` / `P0_STOP`）、完成与未完成的 skeleton 列表、总墙钟、每个骨架的 `planning_wall_s`。

## 4. 第 3 步：统计脚本 `scripts/summarize_v07_s15_yield.py`

只读第 1、2 步的输出和 S1.5 地图文件，输出 `docs/v07/evidence/s15/s15_yield_summary.json` 和 `docs/v07/evidence/s15/s15_yield_tables.md`。**口径如下，逐条照做。**

### 4.1 每个骨架的属性

`intent = descriptor.base_intent`；`approach_mode = descriptor.common_draw.approach_mode`；`layout`、`facility_count`、`map_side_m` 取自该 family 的 `family_initial.json`；`success = planning_result.json` 中 `eligible_combinations > 0`。

### 4.2 每个组提案的属性

数据来源为 `proposals.jsonl` 的每一行，一行即一个组提案。
- `group_id`，`role` 与 `execution_method`：按 `group_id` 在描述的 `task_groups` 中查得。
- `member_count = len(members)`，分桶为 `2–3`、`4–5`、`≥6`。
- `accepted`：`record["reason"] is None`。

### 4.3 被拒提案的归因（只用终止拒绝证据）

只遍历该行 `record["rejection"]` 这个子树（含其中全部嵌套的列表和字典），不看其他字段。在子树中递归收集：
- (a) 所有键名恰为 `"entity_id"` 的字符串值；
- (b) 所有同时含有 `"clearances_m"`（字典）和 `"required_m"`（数值）的字典里，`clearances_m` 中数值 `< required_m` 的那些键名。

每个收集到的实体 ID，按下列顺序归类（设 `T` 为该组的 `target_id`）：

| 条件 | 类别 |
|---|---|
| ID 等于 `T`，或以 `T + "_"` 开头 | `target_facility` |
| 以 `"facility_"` 开头，且以 `"_alert"` 或 `"_protected"` 结尾 | `other_facility_inner` |
| 以 `"facility_"` 开头，且以 `"_warning"` 结尾 | `other_facility_warning` |
| 以 `"obstacle_"` 开头 | `obstacle:<placement>`，其中 placement 在 `family_initial.json` 的 `obstacle_placements` 里按 `obstacle_id` 查得（`entry_blocking` / `facility_side` / `between_facilities`） |
| 等于 `"world"` | `world_boundary` |
| 其他 | `other:<原ID>` |

一个提案可以同时属于多个类别（多标签）。一个实体都没收集到时，记为 `unattributed:<record["reason"]>`。

每个统计表同时给两种计数：**多标签计数**（各类别出现的提案数）和**互斥签名计数**（把该提案的类别集合排序后用 `+` 连接作为键）。

### 4.4 作业段进入非目标预警区（只统计，不设规则）

只对有 `selected_skeleton.json` 的骨架统计。在该文件中递归找到键 `"references"`（agent → 参考信息），对每名成员取 `"work_points_enu_m"`，按顺序连成折线（只用 x、y）。对其所属组的目标以外的每个设施，取其 `*_warning` 圈层的几何，用 `scene_v07.geometry.to_shape(geometry, 64)` 转为多边形，判断折线与多边形是否满足 `intersects`，且交集长度 > 1e-6 m。
- 输出：每个骨架是否有成员的作业段进入非目标预警区，以及进入的成员数 / 总成员数。
- 只有 1 个设施的地图记为 `not_applicable`。找不到 `references` 或 `work_points_enu_m` 时记为 `not_available`，不要猜测字段。

### 4.5 输出表格（分母一律写出）

- **T1** 骨架成功率：`intent × layout`，单元格写"成功数/总数（百分比）"；另加一行"各布局内五意图成功率的最大值/最小值之比"。
- **T2** 骨架成功率：`intent × approach_mode`；以及 `intent × facility_count`。
- **T3** 组提案接受率：`role/execution_method × layout`，以及 `role/execution_method × member_count 分桶`，单元格写"接受数/提案数"。
- **T4** 被拒提案归因：按 `role/execution_method` 分行、按 4.3 的类别分列，给多标签计数；另按 `layout` 分行再出一张；互斥签名取前 15 名。
- **T5** 作业段进入非目标预警区：`intent × layout`（仅多设施布局），写"进入骨架数/统计骨架数"。
- **T6** 每个骨架规划墙钟的分布（min / p50 / p90 / max），按意图分列。

只出数字，**不写解释、不下结论、不提修复建议**；结论由审查方写。

## 5. 运行顺序与止损

1. **快速检查（≤ 10 分钟）：** 第 1 步全量登记 → 第 2 步 `--limit 16 --wall-limit-s 600` → 第 3 步对这 16 个骨架出表。停止条件（任一满足即停下汇报，不进入下一步）：
   - 任何 `P0ContractError`，或源码指纹在运行前后不一致；
   - 任何骨架以异常结束（`ERROR_STOP`）；
   - 统计脚本对任一提案无法按 4.3 解析（例如找不到 `rejection` 字段），且这种情况超过 5%。
   - 另外，按 16 个骨架的平均墙钟估算全量时间：若预计超过 45 分钟，就按每层地图数从 6 降到 4（各层仍取 `candidate_index` 最小的那几个），重新登记后再跑全量，并在报告中写明。
2. **正式批次（预计 20–40 分钟）：** 第 2 步不加 `--limit`，`--wall-limit-s 2700`；超时即为 `TIME_LIMIT_STOP`，用已完成的部分出统计，并在报告中写明完成比例。
3. **统计：** 第 3 步对正式批次出全部表格。

## 6. 提交与报告

每项单独提交，提交信息以 `S15-Y` 开头：
1. `S15-Y1` 骨架登记脚本；
2. `S15-Y2` 批量规划脚本；
3. `S15-Y3` 统计脚本；
4. `S15-Y4` 快速检查与正式批次的证据（JSON、表格）和报告 `docs/v07/s15/S15_stage2_report.md`。

报告内容只包括：执行了什么（附命令）、外部目录路径、选中的 24 个 family 列表、运行状态和墙钟、T1–T6 表格（可直接引用 tables.md）、异常与处理。推送 `v07-s15`，报告提交范围和远端 HEAD 的完整 SHA，然后停下。

## 7. 规则

- 本指令给定的选择规则、口径、表格定义不得自行更改。认为有歧义时，选更保守的理解，并在报告"异常"中写明。
- 自编脚本中的编程错误（路径、字段名、格式、Windows 换行）直接修复，在报告中记录，不必停下。
- 除第 5 节的止损条件外，遇到任何需要修改第 1 节"严格禁止"范围的情况，都要停下汇报。
- 开工前写约半页 `docs/v07/s15/01_stage2_restatement.md`（拟新建的文件、复用的函数、发现的冲突）。**无冲突就直接继续**，有冲突就停下。
