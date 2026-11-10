# V8-20 运行登记

当前第 1–8 部分执行检查完成，全部产物保留；最终研究接受待规划审查方复跑。下文旧停止状态和中间进度均为历史记录；最新结论见 REPORT 最后的成本裁定轮第 8 部分及 acceptance.json。不得重用既有输出目录。

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

新恢复命令与结果将登记全新 run/cost_ruling_r1；后台监控 session.json 指向新 cost_ruling 轮次。原门禁/单查询/失败交付证据均保留。

新裁定后的第 3 部分已通过：见 cost_ruling/part3_complete/checkpoint.json。下一步第 4 部分，保持监控；不得把最大补例 attempt 13 计为生产获胜。

第 4 部分本地检查通过，第二轮五旧意图门禁待运行；源码绑定和自检结果见 part4/pre_gate.json。每组单独通知后调用 run_old_intent_gate.py <intent> 4 --round r1，不覆盖既有输出。正式区域侦察预建和批次尚未运行。

第 4 部分完成：第二轮五意图 100/100 字节门禁通过，见 part4/checkpoint.json。下一步独立运行区域侦察 --stage prewarm（24 进程，先通知），通过后另开 --stage skeleton --prewarm-from <本轮 prewarm.json>，分别控制 2700/1800 秒墙钟。

第 5 部分完成：预建 1624.419810 s，骨架 83.007528 s，检查点 passed=True；正式输出见 acceptance.part5_checkpoint，使用同一 prewarm.json 分隔两项计时。

第 6 部分快批 20 完成，墙钟 94.992606 s，passed=True；检查点见 acceptance.part6_checkpoint。

第 7 部分完成：full+div 运行器 740.289784s；serial5 60.021166s；原样产物预置3/3、skip0。各阶段输出和完整合同 SHA 索引见 part7_cost_ruling/。使用 --prewarm-from 复用第 5 部分 prewarm.json，预建不重复计入 skeleton/quick/full。

最终监控已正常停止：F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-09_V8-20_area_search\run\system_monitor\monitor_cost_ruling_20261110T043453Z。资源摘要与索引见 part8_cost_ruling/。最终 SHA/远端核对见 F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-09_V8-20_area_search\run\delivery_cost_ruling_r1\final_push.json。如需复查异常，先读 run/RECOVERY.md、system_monitor/session.json/current_job.json 与最近一轮 telemetry/*.current_attempt.json；用 analyze_resources.py <监控目录> --out <全新摘要路径> 读取，保留原始 metrics.jsonl，不将坏尾行算成功。

完整生产命令见 part5_cost_ruling、part6_cost_ruling、part7_cost_ruling 的运行器与 watchdog.argv。各批次均明确 --prewarm-from <run/prewarm/area_cost_ruling_r1/prewarm.json>；预建仅含字段/弦/扇区，worker 缓存 miss 在进程内计算，不写共享缓存。复跑固定 --workers 1，比较目录不排除文件。
