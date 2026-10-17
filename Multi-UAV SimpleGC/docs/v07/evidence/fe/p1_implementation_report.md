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

## 下一阶段

FE-P1a 提交后，以干净工作区运行七个指定骨架的 planning-only 快速检查。
调用原 run_v07_s15_yield.py，墙钟上限 720 秒；按指令三条停止条件评估。
快速检查表 A–E 将写入 p1_monitoring_quickcheck.md/json，并随 FE-P1b 提交。
