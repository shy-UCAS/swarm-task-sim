# M2 第 0 步复述

基线：`v07-scene` / `e1fca53`。已读指定材料，本步只复述。

## 新的单骨架流程

1. **选组合**：沿用每组 200 候选、最多 1000 个无放回组合；同目标方位差改为 \(30^\circ\)，同向路程上限改为 130%。删除指定两处恒速门禁，保留角色内部及独立接口检查。无合格组合记 `geometry_pool_empty`；每骨架最多 5 轮，各取下一组合。
2. **预演**：稳定 20 s、零延迟单飞，由 M1 `labels.measure` 读取本机结果和事件起点。成员非成功、事件缺失或全组搜索足迹并集覆盖率小于 0.80，记 `rehearsal_failure`，附成员与条件名，换组合。完成时刻缺失不拒绝；联合预算全员完成时用实测值，否则整体用保守估计。
3. **时刻与叠加**：按 §5.2 公式及指定 `timing_v3` 种子，分别生成两版计划、加入组间偏移、量化至 0.1 s。同步只抽抖动；递次另抽批数、切点和间隔。批内跨度须不超过 10 s，全部飞机叠加间距须至少 2 m。每版独立尝试 `draw=0…19`，取首个通过者；冲突只重抽该版、不改几何。任一版耗尽记 `timing_conflict`，附版本、最小间距和机对，换组合。
4. **联合执行**：两版均通过才仿真；标签只取联合真值，经审计、写盘、`load_pair` 与白名单检查。记录预演、接受 draw／拒绝次数、抖动跨度／批数／间隔、执行状态、预演不一致成员与条件，以及单机记录结束前后的间距预测误差。耗尽后顶层取最后实际失败类别，置 `exhausted=true`，保留逐轮历史。

参数集中到新配置；扩展骨架新增停止字段 15 m／1.5 m/s／1 s，仍要求跟踪器完成，原 `terminal_*`、抵近驻留及竖切默认行为不变；撤离余量改为 50 m。C13 仅改审计：完整性独立取自 source 执行状态，completed/timeout 均完整，并核对真值帧数与标签声明。角色几何、M1 判据、fastsim、公共抽样、旧时刻函数不改，中止不改不跑。

Q-A/B/C 后推检查点 1；Q-D 固定 quick B 的 10 骨架、8 进程，60 分钟硬停并保存、不重跑，完成后推检查点 2。P0 停止；已知低成功率、预演不一致只记录。条款分别提交，原 attempt 只读。

## 拟涉及文件（相对项目根目录）

- **新增**：`configs/generator/generator_v07_r1.json`；`task_v07/unified/{__init__,config,rehearsal,timing}.py`；`scripts/{replay_v07_m2,run_v07_m2_trial}.py`；`tests/test_v07_m2_timing_rehearsal.py`；M2 报告与小体量证据。
- **修改**：`task_v07/execution.py`；`task_v07/expansion/{pipeline,episode_pipeline,group_candidate_pool,candidate_search,solo_spacing}.py`；`scripts/{run_v07_s2_episode_batch,audit_v07_m1}.py`；相关审计测试。现有 `regression` 固定 22 条，仅比较竖切 8 条的轨迹字节与标签字段。

## 待确认与已知文档差异

- **Q-B 成功类别未定义**：三类均为失败。建议另设 `status=passed/rejected`，通过行 `category=null`，拒绝行限三类，待确认。
- **Q-B 缺输入**：23 个目录仅 20 个保存单机轨迹；以下三个无 NPZ、无校准记录，仅有骨架与规划检查（`FAST_B_STOP.json` 证实中断在途任务）：
  - `family_s12_4d13d93f9171c446_ext_006_regular/geometry_02`
  - `family_s12_4d13d93f9171c446_ext_007_regular/geometry_01`
  - `family_s12_5024cb2ccea653ae_ext_002_regular/geometry_00`
  建议重放 20 轮，其余记 `input_missing`、不归为行为失败、不补仿真；与“全部行算完”不符，待确认。已有 NPZ 的执行状态可由校准记录的完成时刻恢复。
- 设计仍缺 §2.2 驻留勘误，§9 仍写“不推送”；依 M2 §2 注明，以 M1 已批准判据及 M2 §10 为准。

**停在第 0 步，等待确认；尚未修改实现、运行测试或仿真。**
