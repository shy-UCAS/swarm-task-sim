# v0.7 first_edition 批量生产使用说明

本说明对应 `fe/production-r3` 分支上的生产脚本。生产只生成本地合成轨迹数据集；运动后端是点质量运动学模型，4–10 m/s 未做 SITL 校准。不控制真实无人机，不启动 SITL。

## 前置条件

- Windows + PowerShell 7。
- Python 环境：conda `llm`，调用方式：
  ```powershell
  & C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B ...
  ```
- 工作树：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-prod-r3`，分支 `fe/production-r3`。
- 工作树必须干净；新建运行会拒绝 `git status --porcelain` 非空的情况。
- 数据目录在仓库外：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\`。
- 已冻结基线：`Multi-UAV SimpleGC/docs/v07/s15/S15_frozen_baseline.json`（300 个 family）。
- 生产参考：fastsim r3，`reference_r3.CONFIG_SHA256 = 0fe3efff6f97ed88c665374d0280aef571b92399ac3711184f13e5c6a3de3b30`。
- 生产不做训练/测试划分，不生成中文描述，不导出训练数据。

## 命令

在 `Multi-UAV SimpleGC` 目录下执行：

```powershell
# 干跑：只执行阶段 A，不启动 worker，不写 planning/episodes/status
& C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B `
  scripts/run_v07_fe_production.py --run-id <ID> --families <START>:<END> --dry-run `
  --root "F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_first_edition_checks"

# 正式生产
& C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B `
  scripts/run_v07_fe_production.py --run-id <ID> --families <START>:<END> --workers 14 `
  --root "F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_first_edition"

# 断点续跑
& C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B `
  scripts/run_v07_fe_production.py --run-id <ID> --resume --workers 8 `
  --root "F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_first_edition"

# 重新生成报告
& C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B `
  scripts/run_v07_fe_production.py --run-id <ID> --report `
  --root "F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_first_edition"
```

`--families START:END` 按 `S15_frozen_baseline.json` 的 `candidate_index` 取半开区间 `[START, END)`，升序处理，不按机数过滤。每个 family 固定 2 个公共条件抽签槽、5 个意图，最多 10 个 regular descriptor；aborted 子集丢弃。

`--root` 默认为 `<ROOT>\SwarmData\v07_first_edition`。正式运行前建议先用 `--dry-run` 和一个小批量（例如 `--families 0:20`）确认环境。

`--workers` 默认为 14。`--planning-timeout-s`（默认 3600）和 `--episode-timeout-s`（默认 5400）是测试专用参数，生产时不要修改。

## 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 全部任务终态，报告生成成功 |
| 1 | 调度器或 harness 自身错误；失败运行目录保留 |
| 2 | P0：配置 SHA、审计、源码指纹或注册契约失败；写 `P0_STOP.json` |
| 3 | 启动被拒绝：run_id 已存在、family 范围与已有运行相交、工作区不干净、HEAD/code_hashes 与登记不符、参数非法 |
| 130 | 收到 SIGINT/SIGBREAK，优雅停止；不写运行中任务的 status |

## 输出目录

```
<root>/<run_id>/
  registration.json          运行登记（版本、family、descriptor、SHA）
  code_hashes.json           启动时的完整源码指纹
  descriptors/descriptors.json
  planning/<sid>/planning_result.json, candidate_pool.pkl
  episodes/<sid>/<mode>/...  与 R4 相同的 episode 结构
  qc/<sid>.json              每个骨架的 qc_episode 结果列表
  status/B__<sid>.json, status/C__<sid>.json
  logs/<stage>__<sid>.txt
  progress.json
  manifest.json, stats.json, stats.md
  _aborted/                  仅续跑时出现：被中断任务的残留目录与 status tmp
  P0_STOP.json               仅 P0 时出现
```

`manifest.json` 中只有 `retained_episodes` 可以进入下游；`non_retained_episodes` 只用于诊断。抽签级保留规则是全有或全无：同一抽签 5 个意图的 C 全部 `PAIRED` 才保留 10 条 episode；任一 `NOT_PAIRED`、`TIMEOUT` 或 `ERROR`，该抽签所有 episode 都不保留。统计结果不影响保留。

## 中断与续跑

- 调度器同时处理 `SIGINT` 和 Windows `SIGBREAK`，走同一条优雅停止路径：kill 全部子进程 → 写 `progress.json` → 退出码 130。
- 中断时**不会**为正在运行的任务写 status（包括 `ERROR`/`TIMEOUT`）；这些任务保持无 status。
- `--resume` 先校验 HEAD 与 `code_hashes()` 是否等于登记值；有 status 的任务不重跑。
- 无 status 但存在残留目录的任务，整体移入 `_aborted/<UTC>/<stage>/<sid>/`；`status/*.tmp` 移入 `_aborted/<UTC>/status_tmp/`；不删除残留。
- 续跑允许使用不同的 `--workers`。
- 非中断情况下 worker 退出但没有写 status：调度器写 `ERROR`，detail 为 `WORKER_EXIT_WITHOUT_STATUS` 并附 returncode，抽签按规则丢弃。

## 实测耗时

- S1b 等价性：3 个骨架、3 workers，B 规划 36.6–43.2 s，C 仿真 193.7–569.3 s，总墙钟 624.2 s。
- S2 冒烟：1 个 family、2 个抽签、10 个 B 任务、8 workers，总墙钟 358.8 s，run 目录约 14.27 MB；该 family 两个抽签各有一个 B `REJECT`（`shape_search_budget_exhausted`），因此没有 C/episode；中断/续跑机制已在该 B 阶段验证。
- 全量规模参考：300 family × 2 抽签 × 5 意图 = 3000 个骨架；按阶段 2 约 62.5% 抽签保留率估算，约 375 个抽签、3750 条 episode。正式批量由用户分批运行。

## 已知限制

- 点质量运动学模型；4–10 m/s 未做 SITL 校准；M3 已知 10 m/s 高速用例约 4 m 冲出、四机汇聚最小间距 2.931 m，不能宣称高速规划合格。
- 不启动 SITL；不访问 M2-02B 封存留出集；不重跑 M3 内部留出集。
- 不冻结、不打标签、不合并稳定分支。
- 生产代码只改动了 `rehearse`、`run_episode_job`、`write_result` 三处传参路径；规划器、判据、审计、场景、`views.py` 未改。
