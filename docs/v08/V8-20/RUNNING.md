# V8-20 运行登记

当前第 1、2 部分完成，第 3 部分成本检查点未过，已停止全部后续计算。acceptance.json 记录第一轮五意图门禁及停止证据；本分支未获完整验收。第 4–7 部分未执行，不得自动续跑或覆盖原输出。

工作树：F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-v08
代码工作目录：该工作树 Multi-UAV SimpleGC
Conda：C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B
Shell：C:/Users/shy/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe
开发集：仓库 docs/v08/V8-03/devset_v08.json
只读数据根：F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData
产物/独立缓存根：本任务 handoff/2026-11-09_V8-20_area_search/run

四线程环境变量 OMP_NUM_THREADS、OPENBLAS_NUM_THREADS、MKL_NUM_THREADS、NUMEXPR_NUM_THREADS 均为 1；PYTHONDONTWRITEBYTECODE=1。默认 24 进程、正式复跑 1。每次启动 24 进程前后通知用户。

第 1 部分命令：从代码工作目录用上列 Conda 调用本任务 part1_snapshot.py。它使用全新 run/snapshot/part1_r1，不能原地复用。脚本仅读取冻结对象、输入与接受基线；写本任务外部证据及本次 V8-20 文档/预置。完整输出与散列见 manifest.json。

第 2 部分先运行 test_preset_numeric_v20.py、合同/独立参考自加测试和受影响旧测试，再进入第一轮五意图门禁。第 9.2 预置等待第 3/4 部分接口；第 9.3 等全部产物齐全才运行。未运行或 skip 不记通过。

只推 review/v08/V8-20-area-search；push 后必须 ls-remote 核对完整 SHA。三份 owner_rerun.json 不动、不提交；不推 main、不强推、不合并 dev。

重启后资源监控与恢复状态见 REPORT 末尾、本目录 monitor_resources.ps1/analyze_resources.py，以及本任务外部 run/system_monitor/session.json。监控不进入 contracts；原中断监视 r1 保留，接续使用 r2。

第 2 部分现已通过：13 项新测试、168 项相关旧测试、100 合同第一轮字节门禁。复现旧意图门禁使用本目录 run_old_intent_gate.py <intent> 2 --round <全新字母数字轮次>，仍须先开启资源监控。阶段入口未实现前不得运行新意图生产。

当前停止于第 3 部分成本检查点。不要直接续跑第 4–7 部分；完整检查、实测、缺项与停止理由见 REPORT 和 part3/checkpoint.json。所有进程已停，监控已刷盘正常退出。PowerShell 读取 UTC ISO 时间做间隔计算时用 ConvertFrom-Json -DateKind String，避免自动转为 DateTime 后再次 Parse 丢失时区；主实测耗时始终来自 Python perf_counter。

第 3 部分已保存并推送为 5a37cf7efe7d5b9a6f5a555541e03c5cf8cec60d。第 8 部分仅失败交付回执；最终提交与远端核对见本任务外部 run/part8/final_push.json。
