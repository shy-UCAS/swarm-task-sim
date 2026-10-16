# S1.5 场景布局执行复述

本次以 `review/m3b-q2-failure@b035dfd66eb45709d400d953caa1692d23c8be63` 为基线，已新建 `v07-s15`。仅修改抽象随机场景中设施的相对布局，按指令实现精确基底距离、60 次二分挂接、布局重试、动态地图及 350 m 边距。所有有序设施对满足 R1；所有无序对满足 \(g_{ij}\geq-0.20W_{ij}\)。isolated 保持至少 40 m 间距，clustered 保持预警重叠图连通，linear 保持中心共线。采样过程中的失败提案按规定记录并重抽；输出违反 R1/R2 则立即按 P0 停止。

拟新增 `configs/scene/scene_s15_layout_r1.json`、`scene_v07/layout_s15.py`、`scene_v07/sampling_s15.py`、`scripts/summarize_v07_s15.py`、`tests/test_v07_scene_s15.py` 和旧修订哈希基准数据；仅在 `sampling.py`、`checks.py`、`batch.py` 与 `sample_v07_scenes.py` 接入 s1.5。独立检查器自行重算精确距离，不信任采样记录。设施实体、障碍物、雷达及初始状态等沿用 s1.2 的代码和参数；不改 SamplingPolicy 字段、sampling_s11.py、公共 schema 或第 6 节其余禁止修改项。

主种子来源为仓库外 `F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_scene/attempt_s12_20261013_s2_vertical/` 下各家族的 `provenance.json`，并非 attempt 根目录文件。已核对 300 份均使用 `master_seed=2026101307`；继续使用原 `family_seed(master_seed, candidate_index)` 派生方式和 0–299 候选编号。旧登记源只读，新数据写同一外部根目录下全新 `attempt_s15_<UTC>`。

执行顺序：改动前保存 s1/s1.1/s1.2 各 5 个固定种子的 canonical JSON SHA256；实施规定的测试 1–7；重跑 M1/M2/M3 既有短测试；先运行 30 候选无图快速检查，通过后才运行 300 候选及绘图、统计与代表图库。遵守接受率、回归、R1/R2 与 60 分钟全量墙钟止损，不调整数值、算法或测试预期。按 S15-1 至 S15-4 分四次提交，报告差异、异常和证据，推送 v07-s15 并核对远端完整 SHA 后停止。

冲突核对：未发现未解决冲突。AGENTS.md/README/CLAUDE.md 的停止于历史 M3、不推送及旧开发目录限制由本次用户明确执行 S1.5 并推送的指令覆盖；不启动 SITL，不执行 S2/Q2/Q3 或 fastsim。PowerShell 7.6.5 与项目 `.conda-env=llm` 已核实；沙箱内 Conda 启动及 Git 工作树元数据写入失败，通过工具授权边界执行已成功，未切换解释器。按第 10 节，复述写完直接继续。
