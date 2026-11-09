# V8-20 运行登记

当前完成第 1 部分。后续只允许按主指令与附录顺序，在前置检查通过后使用全新目录。当前 acceptance.json 尚无门禁/生产索引，不是完整验收证明。禁止重跑已有 r1 输出或覆盖接受基线。

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
