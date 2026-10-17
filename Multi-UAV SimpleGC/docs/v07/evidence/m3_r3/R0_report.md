# M3-r3 R0 核验与阻断报告

R0：**BLOCKED**。R1–R4 未执行，未启动仿真、未改生产算法、未集成 P2。

候选工作树：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-m3r3`。
分支：`fe/m3-r3-p2-candidate`。核验时算法基线：`81f804a969192790d89100528e3f802bc06446b1`。

## 已核实的证据

- llm：Python 3.12.3、NumPy 2.5.3、Shapely 2.0.7；无依赖安装或升级。
- 282/282 个 tuning 任务均完成身份、原始输入哈希、SITL 参考哈希、r2 产物哈希、冻结配置及配对指标核验；共登记 8196 个输入文件。
- 对冻结的逐任务 SITL/r2 摘要调用原 `paired_metrics()`，结果与历史 `paired.json` 精确相同。
- 原 `aggregate_pairs()` 汇总与冻结记录精确相同；原 `tiers().hard.passed` 为 true。
- 未重新从原始 CSV 重建历史摘要，也未重跑任何历史飞行；CSV 等证据的历史 SHA256 已逐文件核验。
- 本轮未访问 M2-02B 封存样本，未读取 M3 internal 任务运行产物或重跑 internal；仅读取原 split 身份登记与公开冻结说明。

| r2 对 SITL 的冻结基线 | 核验数值 |
|---|---:|
| 成功一致率 | 282/282 |
| 观测成功一致率 | 282/282 |
| 整体运动一致率（原 reference-known 分母） | 226/226，双通道相同 |
| 总时长绝对相对误差 median | 0.0157049968819699 |
| 总时长绝对相对误差 p95 | 0.07934581069684277 |
| observe 时长绝对相对误差 median | 0.02074701727528907 |
| 最低转弯速度绝对差 median | 0.7874061877393959 m/s |
| 横向误差任务级 p95 汇总 median | 0.40636257193666003 m |

这些是 r2 历史基线，不是新 r3 A/B 结果。observe 指标使用原有 98 项适用分母；转弯指标使用 188 项，94 项直线任务没有转弯，未填零或改写原统计定义。

## 阻断原因与待明确口径

`equal_strip_rectangular_spiral` 共 56 个任务，其 SITL 真值和观测运动槽位全部为 `unclear`，两通道的 reference-known 分母均为 0，一致率均为 null。

原 `tiers()` 设该项 `applicable=false, passed=null`，只要求没有明确 false，因此历史整体 hard PASS 正确。这不等于该模式的一致率达到 0.95。本轮指令同时要求分模式门槛均满足，以及缺少必需指标时 BLOCKED，且禁止自行批准例外。当前证据不足以决定是否允许沿用原门禁的 N/A 适用性规则，故停止；不是 r3 算法实测失败。

需用户明确矩形螺旋模式能否按原 M3 规则保留 N/A，并使当前完整性条款与其一致；或提供同任务身份、符合既定规则的有效验收依据。未自行把未知算正确，未将整体运动率代替该模式，也未改 M1、观察器或阈值。

R0 在此阻断，`R0_validation_plan.json` 是审计登记草案，不是后续执行的已冻结计划。R2 的历史 282 项全集、原功能子集及 28800 秒预算已登记；R1/R3 完整测试清单与 R4 的 30+8 输入文件绑定尚未完成。R4 21600 秒预算保留。必须解决口径、完成这些登记并重新核验 R0 后，才能冻结新计划哈希、进入 R1。

## 门禁与证据

- `R0/gate.json`：程序化门禁，必需指标缺失为 null，状态 BLOCKED；next_stage 为 null。
- `pipeline_state.json`：R0 已执行并阻断；R1–R4 均为依赖阻断、executed=false。
- `R0_validation_plan.json`：全部输入完整路径/SHA256、逐任务身份、原门槛、基线和不可评估任务清单。
- 外部审计目录：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\fast_dynamics\m3\m3_r3_r0_20261017_audit01`。
- 外部 `audit.json`、`tuning_tasks.json`、`input_manifest.json` 的哈希绑定于 R0 gate。
- `scripts/audit_m3_r3_r0.py`：只读审计入口，拒绝覆盖已有 attempt/gate，不包含仿真或推进 R1 的代码。

## 核验器测试及执行记录

4 项合成测试通过，覆盖历史 hard PASS 与新缺指标阻断的差别、候选 unclear 不缩小参考分母、可计算指标，以及 FAIL/BLOCKED 不推进。现有测试断言均未修改，未声称已完成 R1 fastsim 回归。

第一次使用 `tests.test_m3_r3_r0_audit` 模块名发生导入错误，未执行测试。随后按项目目录布局设置 PYTHONPATH 为项目和 tests 两个目录，使用 `python -B -m unittest -v test_m3_r3_r0_audit`，4/4 通过。

审计脚本用退出码 2 表示非 PASS 停止；conda 包装显示非零状态，不是审计进程崩溃。完整证据已经原子写入。未推送、未合并稳定分支、未正式冻结、未启动量产。当前不建议正式冻结；先解决 R0，再按原阶段门禁推进。
