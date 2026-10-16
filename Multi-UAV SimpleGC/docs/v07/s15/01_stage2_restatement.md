# 阶段 2（S1.5 现有规划器体检）执行复述

## 将新建的文件

| 文件 | 内容 |
|---|---|
| `scripts/run_v07_s15_descriptors.py` | 第 1 步：校验基线地图 SHA256，按确定性规则选 24 个 family，抽样 240 条 regular 骨架描述，写出登记目录 |
| `scripts/run_v07_s15_yield.py` | 第 2 步：复用既有 `descriptor_jobs` 与 `run_stage("q2", ...)` 跑批量纯规划，写 `registration.json` / `run_result.json` |
| `scripts/summarize_v07_s15_yield.py` | 第 3 步：只读统计，写 `docs/v07/evidence/s15/s15_yield_summary.json` 与 `s15_yield_tables.md` |
| `docs/v07/evidence/s15/s15_yield_summary.json`、`s15_yield_tables.md` | 表 T1–T6 的数字证据 |
| `docs/v07/s15/S15_stage2_report.md` | 阶段 2 报告 |
| `docs/v07/s15/01_stage2_restatement.md`（本文） | 开工前复述 |

仓库外新目录：`<SwarmData>/v07_dataset/attempt_s15desc_<UTC时间>/`（第 1 步）与
`<SwarmData>/v07_dataset/attempt_s15yield_<UTC时间>/`（第 2 步）。不修改 `task_v07/`、`configs/`、
`scene_v07/` 下任何文件，也不修改任何已有脚本；不运行 fastsim、单机预演、联合仿真或 Q3。

## 复用的函数（只调用，不复制、不修改）

- `scripts/run_v07_s2_expansion.py::descriptor_jobs(infra, skeleton_ids, out)`：读
  `registration["source_attempt"]` 下的 `candidates.json` 与 `private_skeleton_descriptors.json`，
  逐 family 复核 `row["source_sha256"]`，返回 `{scene, descriptor, planner, out, scope}` 任务列表。
- `scripts/run_v07_m3b_trial.py::run_stage("q2", jobs, out, deadline, completed, rows)`：8 进程
  `ProcessPoolExecutor` 调 `planning_job`，逐骨架写 `proposals.jsonl`、`candidate_pool.json`、
  `planning_result.json`，有合格组合时另写 `selected_skeleton.json`、`selected_checks.json`；
  截止到点抛 `TimeoutError`。
- `scripts/run_v07_m3b_trial.py::runtime_hashes()`：`task_v07/**/*.py` + `scripts/*.py` +
  `configs/**/*.json` 的 SHA256 表，用于启动前后一致性判定。
- `task_v07.expansion.sampling.sample_family_descriptors((scene, family, 2))`：返回 11 条描述
  （10 条 `regular` + 1 条 `aborted`），只保留 `regular`。
- `scene_v07.geometry.to_shape(geometry, 64)`：预警区几何转多边形；配合 shapely 的
  `intersects` 与交集长度判定作业段是否进入预警区。

`run_v07_m3b_trial.py::main` 不调用（它绑定 `docs/v07/evidence/m3b/m3b_inputs.json` 与 900 s 预算，
且 Q3 要求干净工作树）；只按指令复用上列三个模块级函数。`independent_episode_pool` 的
`budget=200`、`COMBINATION_BUDGET=1000` 均为规划器内置默认值，不传参、不修改。

## 口径实现的确定点

- 选择规则：`candidates.json` 中 `accepted == true` 且 `vehicle_count >= 6`，按
  `single`/`isolated`/`clustered`/`linear` 四层，各取 `candidate_index` 最小的 6 个。实测四层
  均有 ≥ 6 个候选（93/46/49/53），故不触发"不足 6 个"分支。
- 24 个 family × 10 条 regular 描述 = 240 个骨架。
- 4.3 归因只遍历 `record["rejection"]` 子树；`rejection` 为 `None` 的接受行不参与归因。
- 4.4 只对有 `selected_skeleton.json` 的骨架统计；`facility_count == 1` 记 `not_applicable`，
  缺 `references` 或 `work_points_enu_m` 记 `not_available`。

## 发现的冲突与已按保守理解处理的歧义

1. **`facility_count` 不在 `family_initial.json` 中。** 该文件的键为 config、cruise_speed_m_s、
   facility_sampling、family_id、generator_version、initial_states、lateral_spacing_m、layout、
   layout_config_sha256、layout_s15、map_id、map_side_m、observation_profile、obstacle_placements、
   obstacle_sampling、radar_placements、sampling_policy、sampling_revision、sampling_seed、
   schema_version、task_altitude_m、vehicle_count。处理：以实际地图
   `public_scene.json` 中 `type == "facility"` 的实体数为准，并对全部选中的 family 交叉核对
   `candidates.json` 的 `facility_count` 与 `len(family_sampling.links) + 1`；三者不一致即记为异常。
   300 个候选上三种来源已全部一致（`single` 恒为 1 个设施，其余为 2–3）。
2. **`selected_skeleton.json` 里 `"references"` 出现两次。** 顶层 `references` 与
   `group_skeletons[gid]["references"]` 同时存在且内容相同（已用 r2/m3b 证据逐字节比对）。
   处理：递归收集所有 `references` 字典并按 agent 去重合并（首次出现优先），避免同一成员被计两次；
   成员到组的归属用描述里的 `task_groups` 判定，从而确定"该组的目标"。
3. **`run_stage` 的 `deadline` 是 `time.monotonic()` 口径**，不是墙钟秒数。第 2 步按
   `deadline = time.monotonic() + wall_limit_s` 传入，保证 `--wall-limit-s` 语义正确。
4. **`rejection` 字段在旧 legacy 后端可能缺失**（`_build_legacy_group_pool` 只对
   `*_search_budget_exhausted` 写 `rejection`）。本阶段的 `planning_job` 走 unified 后端；实测
   m3b q2 的 7200 行 `proposals.jsonl` 中 `rejection` 0 缺失。第 3 步仍按第 5 节统计不可解析比例，
   超过 5% 即停下汇报。
5. **指令文件本身当前未被跟踪。** `git status --porcelain --untracked-files=all` 非空会阻塞第 2 步的
   干净工作树门槛，故先以独立提交登记指令文件与本文，再进入 S15-Y1–Y4。
6. **`--limit 16` 取 `skeleton_id` 排序前 16 个。** 每个 family 有 10 条描述，因此这 16 个骨架只来自
   字典序最小的 2 个 family，布局覆盖有限。按指令字面执行，并在报告"异常"中写明。

## 开工前核对

`git diff --quiet b035dfd66eb45709d400d953caa1692d23c8be63 HEAD -- task_v07 configs/generator`
无差异（exit 0），规划器与 M3b 修复轮一致；当前 HEAD `0ec79e71a78745de9a129886440d1f54532edc53`，
分支 `v07-s15`，`.conda-env = llm`，Python 3.12.3。除上述第 5 条（需先提交）外**未发现需要停止的冲突**，
按第 7 节直接继续。
