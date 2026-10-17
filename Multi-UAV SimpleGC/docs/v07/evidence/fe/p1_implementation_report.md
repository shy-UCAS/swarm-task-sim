# FE-P1 监视撤离修复实施记录

基线：09279c2501002a670e77ed4db7b9f9ab0cb71c73。分支：fe/monitoring-retreat。
工作树：Simulation-fe-p1；Conda：llm。详见 p1_environment.json。

## 实现

- 每股车道共用第 0 条车道末段的单位行进方向，保留原外法线作为外向参考。
- retreat_endpoint 仅在 slot 存在 exit_outward_normal 时跳过朝内方向。
- 非 intrusion 组使用现有 overlay.min_separation_m 进行组内终点间距必要条件检查。
- 未更改随机数调用、预算、配置、M1/M2 或 fastsim 源码。
- 示例先访问倒数第二个点再检查长度，无法正确处理短路径；实现先检查长度，再计算末段，使用指定的 patrol_tail_undefined。
- 修改范围为指定三个函数、一个新测试文件、一个新统计脚本及本证据目录。
- 既有测试断言修改：无。

## 基线与回归

| 测试文件 | 基线通过 | 修改后通过 |
| --- | --- | --- |
| test_v07_m3b_geometry | 9/9 | 9/9 |
| test_v07_m3_fix_patrol_entry | 1/1 | 1/1 |
| test_v07_m3_integration | 4/4 | 4/4 |
| test_v07_m2_timing_rehearsal | 10/10 | 10/10 |
| test_v07_fe_monitoring_retreat | 不适用 | 6/6 |

全部通过，无新增失败。原始输出见 baseline_*.txt、after_*.txt 和对应 JSON。
使用 python -B -m unittest -v <模块>，避免直接执行 M2 文件时覆盖历史 qa_results.json。
M2 指定回归包含原有短仿真 fixture；未启动真实骨架单机预演、联合试点或批量生产。

新增测试覆盖 full/arc、偶数/奇数折返、多股、1 m 拒绝与 2 m 边界、
朝内方向过滤仅对带外向参考的 slot 生效，以及退化末段拒绝。
统计脚本用旧 attempt 自比较验证相同已完成集合接受率相等，且正确标注未完成项。

## 快速检查结果

FE-P1a：01eb76c400fa79e4534a859d2f3a4165bd453b79。
本次 attempt：SwarmData/v07_dataset/attempt_s15yield_20261017T053528Z。
墙钟 293.563 秒；7/7 完成且均有候选，运行期间源码哈希稳定，未完成数 0。

- 所选候选的 8 个监视组，组内最小终点距离范围 20.303519–28.022777 m；
  全部不低于 2 m 且不低于 0.99 倍 lateral_spacing_m。
- 监视接受率：旧 1290/1600（80.625%），新 1239/1600（77.4375%），
  下降 3.1875 个百分点，未低于旧接受率的一半。
- 非监视角色 terminal_endpoint_spacing 触发 0。
- 监视拒绝提案中，terminal_endpoint_spacing 涉及 54 个提案；
  retreat_endpoint_invalid 涉及 6 个，inward_rotation_skipped 涉及 86 个。
  递归出现次数与提案去重数分开列在表 D，避免重复证据导致计数歧义。
- 所有停止条件均未触发，判定 PASS；低间距诊断项 0。
- 候选数存在下降：79c93b22…ext_004 从 5 降至 1，
  c713f518…ext_002 从 173 降至 149；完整比较见表 A。
  不据此扩大修复范围，也不把规划 PASS 表述为完整仿真 PASS。

统计表：p1_monitoring_quickcheck.md/json。
独立重算所有 10 个组选中候选终点距离，与统计表一致；
来源文件 SHA256 和执行稳定性见 p1_run_validation.json。

## 交付边界

FE-P1b 保存快速检查证据。只推送 fe/monitoring-retreat，核对远端提交后停止。
未合并任何分支；未启动真实骨架的单机预演、联合仿真试点或批量生产。
原 Simulation-v07scene 保持 v07-s15 @ 09279c2 且工作区干净。
