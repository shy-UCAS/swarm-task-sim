# M1 第 0 步复述（已确认）

2026-10-15 用户确认：按新版指令 T5 重访确认时刻为 \(580.1\pm0.1\,\mathrm{s}\)；监视圈层核心事件与重访证据分别保存；开始 C1–C12，Q0 通过后推送检查点 1。下文保留第 0 步原始核对记录。

已核对基线 `v07-scene@54842c2` 并完成指定阅读。只改带 `exclusion_policy` 的扩展骨架标签并重标；竖切旧标签、规划器、执行器、fastsim、S1、公共抽样不动。

**共同口径。** 用 10 Hz 真值；圈层 \(L\)、有符号轮廓距离 \(d\) 仅取自 `geometry_facts`。负判据检查首次至最后一次目标 \(L\ge1\) 的作业段。全程对其他设施要求 \(L\le1\)；目标上限：过境／侦察／监视为 1，佯动为 2，突击为 3。前缀沿用 `measurable`／`bounded`；`completed`、`timeout` 均为完整观察。

| 角色 | 正判据 | 负判据 | 终态 | 核心事件起点 `t_s` |
|---|---|---|---|---|
| 过境 | 目标 \(L\ge1\) 恰为一个连续区间 | 无驻留、无重访 | 目标 \(L=0\) | 首次预警进入；`enter_warning_zone` |
| 区域搜索 | 单机有有效观察；组足迹覆盖率 \(\ge0.80\) | 无重访 | 同上 | 首次有效观察；`scan_start` |
| 抵近观察 | 有驻留窗口且窗口全在目标 \(L=1\) | 无重访 | 同上 | 最早合格驻留窗口起点；`observation_point_arrival` |
| 监视 | 作业段存在巡视重访 | 无 | 同上 | 首次预警进入；`enter_warning_zone` |
| 佯动 | 出现目标 \(L=2\)，且 \(L\ge2\) 恰为一个连续区间 | 无 | 同上 | 首次警戒进入；`enter_alert_zone` |
| 突击 | 出现目标 \(L=3\)，且最小 \(d\le50\,\mathrm{m}\) | 无 | 不要求 | 首次禁飞区进入；`enter_protected_zone` |
| 中止主编组 | 进目标警戒区，转折后退出目标预警区 | 全程未进禁飞区 | 目标 \(L=0\) | 按定义缺失；另存中止事实 |

**三个检测器。** 驻留：给定帧集内连续 201 帧，全部位置距窗口均值及窗口首尾距离均 \(\le30\,\mathrm{m}\)；返回最早起点、起点加 \(20\,\mathrm{s}\) 的确认时刻、合格窗口并集时长。重访：两端均在给定帧集且目标 \(L=1\)，端点距离 \(\le30\,\mathrm{m}\)，期间离首点最远 \(\ge150\,\mathrm{m}\)，两端速度均 \(\ge0.5\,\mathrm{m/s}\)，航向夹角 \(\le45^\circ\) 或 \(\ge135^\circ\)，绕设施中心的方位覆盖（整周减最大圆周间隙）\(\ge120^\circ\)；先最小化 \(t_2\)，再最小化 \(t_1\)。空间索引找近邻，再按 \(t_2-t_1\ge2(150-30)/v_{\max}\) 过滤。覆盖：声明区域内、速度 \(\ge0.5\,\mathrm{m/s}\)、目标 \(L=1\) 且不在限制区的帧有效，沿用 `survey` 足迹和网格，组内取并集。

**拟改／新建文件（均相对项目根）。**

- 新建 `configs/criteria/criteria_v07_r1.json`、`task_v07/detectors.py`、`scripts/audit_v07_m1_detectors.py`、`tests/test_v07_m1_criteria.py`、`scripts/relabel_v07_m1.py`。
- 修改 `task_v07/labels.py`、`task_v07/expansion/{multi_labels,views,abort_measurement}.py`、`scripts/audit_v07_s2_{roles,conditions,groups}.py`、`scripts/audit_v07_abort_facts.py`、`scripts/evaluate_v07_s2_cross.py`。`scripts/audit_v07_s2_exact.py` 按需加新版分派，保留旧审计；`scripts/run_v07_s2_episode_batch.py` 仅补 `write_result` 字段。
- 新建 `docs/v07/v07_spec_r4a1_errata.md`、`docs/v07/m1/M1_report.md`、`docs/v07/evidence/m1/` 下 Q0／Q1 证据；派生数据写独立 `SwarmData/v07_dataset/relabel_m1_<UTC时间戳>/`，不提交大数据。

**不一致与待决。**

1. **T5 预期冲突。** 网格帧 1126、5801（\(t_1=112.6\,\mathrm{s}\)、\(t_2=580.1\,\mathrm{s}\)）均在目标环带，速度均为 \(8\,\mathrm{m/s}\)；距离约 \(29.908\,\mathrm{m}\)，航向差约 \(2.856^\circ\)，期间离首点最远约 \(1200\,\mathrm{m}\)，方位覆盖约 \(357.144^\circ\)，时间差 \(467.5\,\mathrm{s}>30\,\mathrm{s}\)。已满足全部重访条件，故最早确认不晚于 \(580.1\,\mathrm{s}\)；首圈完成却为 \(112.5+150\pi\approx583.739\,\mathrm{s}\)，与 §8.3 误差 \(\le0.2\,\mathrm{s}\) 冲突。仅作解析核对，未改预期／阈值，待裁定。
2. **事件存放口径。** 按 C4，拟让监视 `core_event` 的 `t_s`、`t_confirm` 同取预警进入，另存重访 \(t_1\)、\(t_2=t_{\mathrm{confirm}}\)；P2 可有进入事件而无重访事件，待确认解释。
3. **已有明确覆盖的差异。** 设计 §2.2 未写驻留首尾距离，按本指令 §7.2 已批准勘误补足；设计 §9 的“不推送”和 §7.3 的竖切标签变化，分别以本指令 §10 的检查点推送、§1 的竖切旧路径不改为准。

当前只新增本复述；遵照指令 §3“写完后停下，等用户确认后再继续”，尚未进入 C1–C12。
