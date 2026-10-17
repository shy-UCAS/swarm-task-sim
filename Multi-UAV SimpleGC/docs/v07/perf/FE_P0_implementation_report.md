# P0 性能优化实施报告

基线：09279c2501002a670e77ed4db7b9f9ab0cb71c73。开发分支：perf/v07-first-edition-p0。

本机适配：只读 base 复用 Simulation-v07scene；新建同级 Simulation-perf，使用项目 .conda-env 指定的 llm 环境。P1 分支不合并、不改动。输出在同级 SwarmData/v07_dataset 的全新 perf_fe_p0 目录。按本会话已批准的本机适配跳过重复 fetch；基线与存档来源三处源码差异为空。

G0 PASS：12 组共 100 项基线测试通过；6 单机及 1 同步联合重放与归档完全一致；突防样本两次独立进程规划一致。只剔除指定墙钟字段，精确比较结果见 FE_P0_baseline.json。

后续门禁待执行。
