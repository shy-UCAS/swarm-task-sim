# v0.8 过境单段：运行说明（V8-16 起）

> 适用分支：`review/v08/V8-16-transit` 及其后的 `dev/v0.8`。命令都在 `Multi-UAV SimpleGC` 目录、PowerShell 7、conda `llm` 环境下运行。
> 先设线程变量：`$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'`。

## 1. 进程数

- 默认进程数仍是 `DEFAULT_WORKERS = 24`（`v08/runner/runtime_defaults.py`，V8-15 选定，V8-16 未改）。新入口 `tools/v08/run_transit_v16.py` 的 `--workers` 也读取同一常量。
- **同时运行大内存程序时加 `--workers 16`；机器空闲时沿用默认 24。** 依据《V8-15_审查意见_20261105.md》第 3 节。显式 `--workers 16` 只影响这一次运行，不写回默认。
- 全机内存 60% 规则已由 R15 降为诊断，不在 V8-16 重选进程数。
- `--stage rerun` 固定单进程。

## 2. 日常迭代

日常只跑"只骨架 + 20 合同快批"；全量 200 + 100 是规划审查方明确要求的验收，后续日常不自动重复。

```powershell
# 只骨架 200（预建弦集合 → 24 进程派发；检查点含附录裁定 1 的直线回退止损项）
& C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B tools/v08/run_transit_v16.py --stage skeleton --devset <devset_v08.json> --data-root <SwarmData> --cache <运行根>\cache --out <新目录>
# 20 合同全链路快批（select_quick 既有名单）
& C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B tools/v08/run_transit_v16.py --stage quick --devset <devset_v08.json> --data-root <SwarmData> --cache <运行根>\cache --out <新目录>
# 监视 20 合同字节门禁（V8-15 名单入口，真实 24 进程）
& C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B tools/v08/run_separation_v15.py --mode production-quick --baseline <full_v14c> --devset <devset_v08.json> --data-root <SwarmData> --cache <运行根>\cache --out <新目录> --workers 24
```

- **缓存：** 过境弦集合在派发前预建到 `<cache>\transit_v16\<场景缓存键>\<目标>_<查询身份>.json`；各族一个预建进程，写各自文件；派发阶段 worker 只读，缺失时进程内计算、不写回（summary 的 `chord_cache` 记命中/现算次数）。
- **退出码：** 0 完成且未触发；2 诊断检查点触发；3 未完成；4 保留段 P0 违规或复跑字节不一致；1 参数/路径错误。

## 3. 一键复现

`reproduce.ps1 -Scope tests|quick|acceptance|diagnostics`，路径从同目录 `manifest.json` 读取，先校验实际路径与名单；`tests` 不启动任何批次，`acceptance` 才运行全量 200 + 100 与 5 键复跑。
