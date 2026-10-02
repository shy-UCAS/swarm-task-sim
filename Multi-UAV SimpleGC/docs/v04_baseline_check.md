# v0.4 阶段 0–1：M0 基线核对

- 核对日期：2026-10-01。
- M0 状态：`IMPLEMENTED_AND_TESTED`；R01：`PASS`。
- 实施依据：`C:/Users/shy/Downloads/swarm-task-sim_v0.4_阶段0-1实施计划.md`，先执行 M0 和 WP-S；WP-S 完成后按第 0.1、5.6 节暂停，等待用户确认 GO / NO-GO。
- 此文档只报告基线核对。WP-S 的新运行和结论另见 `docs/v04_spike_continuous_route.md`，不能从本报告推断连续航线已通过 SITL 验证。

## 1. 工作目录、版本和环境

| 项目 | 开工时实际值 |
|---|---|
| Git 根目录 | `F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation` |
| 修改范围 | `Multi-UAV SimpleGC/`；相邻原始 `SimpleGC/` 不修改 |
| 分支 | `main` |
| HEAD | `e13564b700934b481ad37cba053db9daabf9e4fa` |
| 与计划指定基线的差异 | 无 |
| 工程版本 | `swarm_sim/__init__.py` 中 `0.3.0`；M0 不修改版本 |
| 项目配置 | 已读取本项目 `AGENTS.md`、`CLAUDE.md`、`.conda-env`；前两者规定使用项目指定的 Conda 环境 |
| Conda 环境 | `llm` |
| Shell | PowerShell 7.6.5 |
| Shell 路径 | `C:/Users/shy/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe` |

开工时 `git status --short` 没有已跟踪文件修改，存在以下用户未跟踪内容：

- `Multi-UAV SimpleGC/LLM Chat/`
- `Multi-UAV SimpleGC/audit_v04/`
- `Multi-UAV SimpleGC/docs/swarm-task-sim_v0.4前置审查任务.md`

这些内容保留原状。`audit_v04/` 只读，不修改、删除或提交。Git 检查提示用户级 `C:/Users/shy/.config/git/ignore` 读取权限不足，但 HEAD、分支及工作区状态查询返回成功；未修改 Git 配置。

## 2. R01：本轮实际执行的原有测试

执行位置为项目根目录，使用 `llm` 环境；命令为：

```powershell
& 'C:\Users\shy\anaconda3\Scripts\conda.exe' run -n llm --no-capture-output python -m unittest discover -s tests -v
```

根执行代理在任何生产代码改动之前实际运行上述测试，终端会话 `50681`，退出码为 0。输出摘要：

```text
Ran 150 tests in 9.651s

OK
```

结论：150/150 项测试通过，基线没有观察到失败。本核对代理未重复执行这批测试。此结果属于“本轮实际运行的单元测试和回归测试”，不属于新代码 SITL 实跑证据。

## 3. 计划第 2 节源码位置复核

以下位置均以开工 HEAD 的实际源码核对，共 10 处；表内为事实说明，不是源码摘录。

| 项目 | 实际源码位置 | 核查结果 |
|---|---|---|
| 逐航点编译 | `swarm_sim/mission_planning.py:50–84`，内层循环 `:60–79` | 按语义阶段和航点下标逐个生成执行阶段，每架飞机每阶段一个目标；计划行号仍准确 |
| 重复 observe 首点 | `swarm_sim/mission_planning.py:132–136` | approach 为 scan 首点，observe 仍含完整 scan，重复点存在；旧路径冻结 |
| 全机屏障 | `swarm_sim/runner.py:68–80`、`:94–113` | 上传、AUTO 执行和目标确认依次调用 parallel；放行延迟为 0.3 秒；计划行号仍准确 |
| 单目标任务项 | `swarm_sim/scenario.py:97–105` | home 占位、变速、单 NAV_WAYPOINT 共 3 项；hold 从 target 读取，示例任务为 0.5 秒；param3 为 0 |
| 上传模式 | `swarm_sim/vehicle.py:217–218`；`swarm_sim/runner.py:28`、`:86–88` | v2 共享任务开启 record_lifecycle，上传进入 BRAKE；不是 LOITER |
| 多项上传能力 | `swarm_sim/vehicle.py:225–252` | upload 逐项响应请求，不限于当前 mission_for 的 3 项结构，可由独立试验脚本复用 |
| 完成判据 | `swarm_sim/vehicle.py:257–274` | execute 等待 mission_count - 1 的 MISSION_ITEM_REACHED；中间到点消息目前保存在原始日志中 |
| 到点确认 | `swarm_sim/vehicle.py:283–318` | 采用距离及持续时间判据，不要求水平速度为零；不能直接当作真实停住时刻 |
| family 构造 | `swarm_sim/generation.py:130–135` | 命名空间包含任务模板，family 带 recon_ 前缀；计划引用略偏移，应以实际 :130 起始为准 |
| 资格依赖 | `swarm_sim/quality.py:82–88` | benchmark_eligible 的条件包含 mission_success is True；计划行号仍准确 |

额外接线核对：`Vehicle._receive` 在 `swarm_sim/vehicle.py:73–105` 是 MAVLink 唯一接收者，原始日志含 `recv_monotonic_s`；实例管理器位于 `swarm_sim/processes.py`，支持独立运行目录并且只回收自己启动的进程。WP-S 可复用这些接口而不改变生产执行路径。

## 4. 历史证据只读清点

已读取两个历史数据集的 episode manifest，并检查其中 `run_directory` 存在：15/15 个源运行目录均存在。这里只核对目录及已有结果，没有执行重新分析，也没有覆盖历史产物。

| 数据集 | episode 数 | 既有运行状态 |
|---|---:|---|
| `verification/v03_integration_20260930/dataset_final` | 5 | 4 completed，1 controlled_ready_timeout failed |
| `verification/v03_pilot_final_20260930/dataset` | 10 | 10 completed |
| 合计 | 15 | 14 completed，1 failed |

已清点的运行 ID：

| 来源 | run_id |
|---|---|
| integration | `20260930T152031Z_08eff45d` |
| integration | `20260930T152358Z_56f3a95a` |
| integration | `20260930T152726Z_85b2bcb7` |
| integration | `20260930T152929Z_faff6f17` |
| integration（受控失败） | `20260930T153556Z_bf2d3529` |
| pilot | `20260930T153623Z_af3f4fcd` |
| pilot | `20260930T153848Z_46d1aaa3` |
| pilot | `20260930T154116Z_ed102766` |
| pilot | `20260930T155237Z_12275488` |
| pilot | `20260930T155457Z_200822e7` |
| pilot | `20260930T155726Z_bd656d6a` |
| pilot | `20260930T160032Z_3eb54ff1` |
| pilot | `20260930T160246Z_f7b6895d` |
| pilot | `20260930T160457Z_bcd46846` |
| pilot | `20260930T160719Z_a58405a9` |

WP-S 的覆盖率对照优先使用 `verification/v03_integration_20260930/verification.json` 中同几何的 `three_primary` 和 `three_repeat`：两次运行各自的 SIM、FCU 全局覆盖率都是 1.0，即 4/4 个通道结果为 1.0。该数字来自已有产物，不是本轮重算。

审查基准优先采用 `audit_v04/report_A_supplement.md` 对原报告的修正：静止时间占比中位数 0.0808 的样本数为 14，阈值为水平速度小于 0.3 m/s 且持续至少 0.2 秒；全机共同重叠停靠事件为 126/137。`A4_final.py` 和 `A4_addendum.py` 同时存在 1.0 秒与 0.2 秒口径，后续正式移植必须明确对照产物，不能混用。受控失败没有有效任务窗口，不能作为零停靠成功样本。

后续需要重分析历史日志时，先复制到新建的 `tmp_v04/` 子目录；本次 M0 没有复制或重分析。R02–R06 的完整兼容性验收留到计划指定的后续里程碑，不能凭目录存在判定通过。

## 5. WP-S 的固件与参数边界

- 当前可执行文件：`ArducopterSITL/arducopter.exe`，4,449,656 字节。
- 本轮实际计算的 SHA256：`0c0c1be702858dad5ed07e319efffda641cfc358423a65608ff949d3becc8532`；与 5/5 个 v0.3 集成运行记录一致。
- 默认参数模板：`ArducopterSITL/copter.parm`。已读模板，没有显式 WPNAV_* 或 WP_* 设置；生成的各实例参数文件为其运行目录下 `sitl/<agent>/defaults.parm`，由管理器另外追加 SYSID_THISMAV、LOG_DISARMED。
- 模板未设置某项不等于已经知道该项实际值。WP-S 必须从每个已连接 SITL 实例读回全部 WPNAV_*，记录来源与参数清单完整性；不得用当前版本文档的默认值代替实测。
- 本轮从上述二进制的 ASCII 字节中只读提取到版本字符串 `ArduCopter V4.0.4-dev (de791682)`，字节偏移为 2,232,184；读取没有启动该可执行文件。WP-S 应把此来源与二进制哈希一同记录，并可请求 AUTOPILOT_VERSION 补充运行时证据；不得从文件名猜测固件版本。
- 最小参数读回策略是通过现有 Vehicle.send / inbox 请求参数列表，依据 param_count、param_index 核查完整性，缺项有界重读；不要增加另一个 recv_match 消费者，也不要写入参数。
- 全部 MISSION_ITEM_REACHED、GLOBAL_POSITION_INT 和模式相关消息已经由唯一接收线程写入 raw JSONL。试验结束后可从原始接收时间离线抽取，按实际放行区间关联所属航线，不能把消费消息的时刻当作原始收到时刻。
- WP-S 只启动本项目管理器创建的本机实例，运行预算默认 2 次、最多 3 次；新产物进入独立新目录。M0 没有启动 SITL，预算消耗为 0。

## 6. M0 结论

基线提交与计划一致，150/150 项原有测试通过，至少 5 处源码引用要求已完成 10 处复核，历史 15 个 episode 的源目录全部存在，当前固件哈希与既有集成证据一致。可以进入独立 WP-S 试验；未据此宣布 WP-G、WP-E、WP-V 已实现或通过。
