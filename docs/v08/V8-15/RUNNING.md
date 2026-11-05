# v0.8 监视单段：运行说明（V8-15 起）

> 适用分支：`review/v08/V8-15-separation` 及其后的 `dev/v0.8`。命令都在 `Multi-UAV SimpleGC` 目录、PowerShell 7、conda `llm` 环境下运行。
> 先设线程变量：`$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'`。

## 1. 默认进程数

- **当前默认值：`DEFAULT_WORKERS = 24`**，保存在 `v08/runner/runtime_defaults.py`。
- **来源：** V8-15 第 4 部分在本机测得：AMD Ryzen 9 9950X3D，16 物理核 / 32 逻辑处理器，63.65 GB 内存。同一组 40 个中等耗时合同分别用 8/16/24 进程运行，按"逐合同耗时比中位数 → 吞吐量 W/I、全机已用内存采样峰值 ≤ 60%、24 相对 16 增益 < 10% 时取 16"的规则选定。证据见 [part4/worker_choice.json](part4/worker_choice.json) 与 [REPORT.md](REPORT.md) 第 4 节。
- **换机器后**这个值不自动适用，应在新机器上用同一协议重测。

| 入口 | 默认值 | 说明 |
|---|---|---|
| `tools/v08/run_joint_monitoring.py --workers` | `DEFAULT_WORKERS` | 原为 1。**注意：** `--stage quick` 分支在 `joint_monitoring.cli` 里硬编码 `workers=1`、`run_batch` 本身串行，所以旧 quick 仍是单进程（历史保留）。`--stage full` 用此值作为进程数 |
| `tools/v08/run_skeleton_monitoring.py --workers` | `DEFAULT_WORKERS` | 原为 8；族级派发不变 |
| `joint_monitoring.run_batch(workers=…)` | `DEFAULT_WORKERS` | 函数仍串行，不使用该参数（行为不变） |
| `skeleton_monitoring.run_skeleton_batch(workers=…)` | `DEFAULT_WORKERS` | |
| `tools/v08/run_separation_v15.py --workers` | `DEFAULT_WORKERS` | 名单快速入口（下节）真实按此进程数派发 |
| `--stage rerun`、第 5 部分剖析 | 单进程 | 复跑与 profile 必须单进程，不随默认值变化 |

## 2. 日常迭代：只骨架检查 + 20 合同快速批次

全量 200 + 多样性 100 **只在规划审查方明确要求的验收时运行**。日常迭代只跑下面两项。

**(a) 只骨架检查**（40 族 × 5 draw，不优化不仿真）：

```powershell
C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B tools/v08/run_skeleton_monitoring.py --devset "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08\docs\v08\V8-03\devset_v08.json" --data-root "F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData" --cache "<运行根>\cache" --out "<运行根>\out\skeleton_<日期>"
```

**(b) 20 合同快速批次（按选定进程数并行）**：用 `select_quick` 的确定性协议从 40 族 × 5 draw 中选出 20 个合同，用名单派发器按 `DEFAULT_WORKERS` 并行运行，并与指定基线逐合同逐字节比较：

```powershell
C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B tools/v08/run_separation_v15.py --mode production-quick --baseline "<基线全量目录>" --devset "F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-v08\docs\v08\V8-03\devset_v08.json" --data-root "F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData" --cache "<运行根>\cache" --out "<运行根>\out\production_quick_<日期>"
```

- **输出：**
  - `quick_selection.json`：名单。
  - `run\contracts\<id>\`：确定性载荷。
  - `run\{records,summary,comparisons}.json`。
  - `production_reproduction.json`：逐合同 `file_sets_equal`/`bytes_equal`/`differing`，排除清单为空。
- **退出码：** 0 = 全部逐字节一致；4 = 有差异。
- **与旧 `run_joint_monitoring.py --stage quick` 的区别：** 名单相同，但旧入口串行运行、不和基线比较，并在 quick 检查点上判阈值。新入口真实并行，只做字节比较。快速检查点统计请看新输出的 `records.json`，或继续用旧入口。

## 3. 本项的其他实验入口（只供复现 V8-15）

| 模式 | 用途 |
|---|---|
| `run_separation_v15.py --mode workers --keys <part4/selection.json> --workers 8\|16\|24` | 进程数扩展测试（每档一个新目录） |
| `run_separation_v15.py --mode stress-skeleton\|stress-checkpoint\|stress-rest --stress-root <根>` | 压力合同三步（第 6 部分） |
| `profile_monitoring_v15.py --mode cprofile\|line --selection <part5/selection.json>` | 单进程剖析（第 5 部分） |
| `analyze_separation_v15.py` | 只读分析既有全量（第 3 部分） |

`reproduce.ps1` 给出一键复现命令（`-Scope tests` / `-Scope quick`）。
