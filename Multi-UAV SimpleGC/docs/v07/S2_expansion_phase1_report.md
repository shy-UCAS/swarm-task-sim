# S2 扩展第一段报告：管道打通、竖切回归与过境试点

日期 2026-10-14（UTC）。分支 `v07-scene`。唯一规范仍为 [v07_spec_r4a1.md](v07_spec_r4a1.md)。

## 结论

| 项目 | 结果 | 证据位置（`SwarmData/v07_dataset/`） |
|---|---|---|
| 竖切 8 条经新管道回归 | PASS：8/8 `labels.json` 逐字节一致；`task.json`、NPZ、CSV 等内容差异 0 | `attempt_s2x_regress_20261014T043921Z_cb2d1502/regression_comparison.json` |
| 过境试点 2 骨架 × 2 时序 | 4/4 执行完成，任务结果均为成功，质量有效 | `attempt_s2x_p1_20261014T045634Z_ee6ddc6f/` |
| 实测时序与指定一致 | 4/4（分类与批次成员均一致） | 同上 `summary.json` |
| 半程截断 | 4/4 PASS：完整轨迹判“是”，截断后判“未知” | 各 episode `truncation_check.json` |
| 独立全帧复核 | 圈层差异 0、目标圈层差异 0、过境事实差异 0；共 553,497 次设施帧比较 | 各 episode `independent_exact_audit.json` |
| 禁入策略实测 | 违规帧 0；限制区帧 0；越界帧 0 | 各 episode `policy_geometry_audit.json` |
| 1/2 进程对比 | PASS：4 条 episode 及 2 个骨架内容差异 0 | `summary.json` → `process_count_check` |
| 测试 | v07 全部 147/147；其中 S2 相关 89/89（原 76 + 新 13） | 本地命令见末节 |

试点数据仍是开发样例：`training_eligible=false`；4–10 m/s 属于 fastsim 外推，没有经过 SITL 验证。

## 管道与改动

管道按步骤执行：读取私有骨架描述 → `RolePlanner` → 执行前检查 → 单机实飞测时 → 出发延迟 → 同步/递次配对实飞 → 10 Hz 导出 → 标签 → 复核。

执行、测时、期限、标签和导出使用竖切的同一组函数：`execute`、`departure_delays`、`completion_budget`、`measure`、`write_episode`。

核心事件只有一个来源，即 `task_v07.labels.measure`。单机测时与配对标签都在 10 Hz 导出网格上调用它。

新增文件：

- `task_v07/expansion/role_planners.py`：
  - 竖切适配层，包装原 `build_skeleton`，不改动其行为；
  - 过境规划器 `TransitPlanner`。
- `task_v07/expansion/pipeline.py`：骨架组装、禁入策略、执行前检查和执行步骤。
- `task_v07/expansion/role_evaluation.py`：截断与交叉否定的判据回调。回调只调用 `measure`，不从模板复制实测值。
- `scripts/run_v07_s2_expansion.py`：两个子命令，`regression` 与 `pilot`。
- `scripts/audit_v07_s2_roles.py`：过境独立复核。不导入 task_v07；圈层用 GEOS 原始轮廓或解析圆计算，中心用鞋带公式，航向回绕用复指数，事实全部重新实现。
- `scripts/v07_s2x_plotting.py`：角色 episode 俯视图。
- `tests/test_v07_s2_expansion.py`：13 项测试。

修改的既有模块（均已验证竖切输出不变）：

- `task_v07/labels.py`
  - 分支键从 `base_intent` 改为任务组 `role`（`role_kind`）。竖切的突击和区域搜索两支映射不变。
  - 新增过境分支。
  - 撤离点事件从“侦察专用”推广为“非突击且 `retreat_required`”。
  - 只有带 `exclusion_policy` 的扩展骨架会增加以下内容：
    - `exclusion_policy_respected` 条件；
    - `labels/0.7-s2x.1` 版本号；
    - 组级 `approach_mode`、`work_area_center_m` 和每机 `entry_azimuths_deg`。
  - `multi_direction_span` 改为按指定逼近方式触发；竖切突击没有该字段，默认按多向处理，保持原行为。
- `task_v07/io.py`：`write_episode` 增加可选参数 `scope`，默认值为竖切原文。
- `task_v07/expansion/geometry_checks.py`：
  - `check_polyline` 与 `check_retreat_point` 内置 \(10^{-6}\) m 数值容差；
  - 零余量接触仍判为不合格；
  - 各补了一个“恰好相切/恰好在边界”的测试。

## 竖切回归

新管道通过适配层重跑 8 条竖切，与原 attempt `attempt_20261014T014017Z_15a6bf38` 逐文件比较：

- 比较的文件：`labels.json`、`prefix_labels.json`、`task.json`、`source.json`、`manifest.json`、`public_scene.json`、`independent_exact_audit.json`、三个 NPZ、两个 CSV，以及骨架级 `skeleton.json`、`timing_calibration.json` 和单机 NPZ。
- 内容差异：0。

允许的元数据差异逐项列出：

| 文件 | 字段 | 类别 |
|---|---|---|
| `source.json` | `simulation_wall_s` | 墙钟耗时 |
| `manifest.json` | `artifact_sha256.source.json` | 上项导致的文件哈希变化 |
| `timing_calibration.json` | `single_flight_wall_s`、`geometry_and_single_flights_wall_s` | 墙钟耗时 |
| `independent_exact_audit.json` | `directory` | 输出路径 |

**规则 5（撤离点）违规标注，按原样保留，不重做：**

- 违规对象：`family_s12_b0c036776dcaff71_s2r3_sk01`（双设施图的区域搜索），同步与递次两条。
- 违规内容：uav_03、uav_04 的撤离点位于 facility_02 预警区内，到预警区边界的有符号距离分别为 −214.8 m 和 −205.5 m。
- 原因：竖切只检查了目标设施的预警区。
- 其余 6 条：2 条 PASS，4 条突击不适用。
- 标注写入 `regression_comparison.json` 的 `rule5_retreat_point_check`。回归只记录执行前检查，不拦截；第二段新的区域搜索规划器必须检查所有设施的预警区。

**固定检查：** 每次修改 `labels.measure` 后，都运行 `regression` 子命令，要求 PASS。本报告的回归在最后一次修改 `labels.py` 之后运行。

## 过境规划口径

| 项目 | 规划值 | 判据值 |
|---|---|---|
| 预警区内弦长 | ≥430 m | ≥400 m |
| 进出点相对设施中心方位差 | ≥95° | ≥90° |
| 区内低速（<0.5 m/s）最长持续 | — | ≤2 s |
| 区内累计转向 | 直线弦 | <180° |
| 弦线与警戒区 | 外扩 35 m 规划余量后不相交 | 按禁入策略，进入即判失败 |
| 撤离点 | 设施预警区外 210 m（余量 10 m） | `check_retreat_point` 检查全部设施预警区 ≥200 m、限制区 ≥35 m；悬停 ≥2 s |

**同向逼近：**

- 全组走同一侧的平行弦，弦间距等于 family 横向间距（15–25 m 范围内）。
- 来自同一进场区的成员共享一条可见图航线，该航线的规划余量为 35 m + 1.5 × 编组半宽 + 2 m。
- 共享航线起点先沿垂直于起始边的方向飞出约 100 m，再接入可见图。
- 各机按自己的横向偏移飞行，转弯内侧用尖角连接，外侧用圆弧连接（每段 ≤30°）。
- 偏移后的每条航线都单独做执行前检查。

**多向逼近：**

- 两侧反向平行的弦位于设施两侧，组内各弦互不相交。
- 两侧成员相对设施中心的进入方位相差约 180°。

**多向统一口径：** 以作业区中心为圆心，测量各成员首次进入作业区的方位，跨度须 ≥90°。过境的作业区中心取设施中心。骨架中记录指定值（`approach_geometry`），标签中记录实测值（`entry_azimuths_deg`、`approach_span_deg`）。

**接近段约束：** 接近段把目标预警区与所有警戒区视为障碍，因此唯一的一次预警区访问就是弦本身。

## 过境试点结果

骨架按“各逼近方式中第一个单组过境描述”选取，不按可行性筛选。

| 骨架 | 地图 | 机数 | 速度 m/s | 逼近 | 目标 |
|---|---|---:|---:|---|---|
| A `family_s12_4d13d93f9171c446_ext_000_regular` | 3 设施、成簇布局 | 7 | 7.42 | 同向 | facility_01（圆） |
| B `family_s12_aa4c66be8e85d64d_ext_000_regular` | 1 设施 | 9 | 8.40 | 多向 | facility_01（凸多边形） |

| episode | 弦长 m | 方位差 ° | 进入方位跨度 ° | 误入警戒区 | 区内低速/转向 | 实测时序 | 事件极差 s | 最小间距 m | 时长 s |
|---|---|---|---:|---|---|---|---:|---:|---:|
| A 同步 | 1479–1647 | 107.1–127.1 | 10.0 | 否 | 0 s / 0° | 同步 | 3.6 | 22.19 | 871.9 |
| A 递次 | 1479–1647 | 107.1–127.1 | 10.0 | 否 | 0 s / 0° | 递次 3 批，与指定一致 | 115.0 | 22.49 | 983.3 |
| B 同步 | 1639–1794 | 99.0–111.4 | 185.4 | 否 | 0 s / 0° | 同步 | 5.3 | 21.52 | 791.0 |
| B 递次 | 1639–1794 | 99.0–111.4 | 185.4 | 否 | 0 s / 0° | 递次 5 批，与指定一致 | 248.1 | 23.09 | 1029.5 |

补充说明：

- 所有成员都到达了撤离点，悬停时长 ≥2.0 s。
- A 的弦穿过了 facility_02 的预警区（成簇布局中预警区重叠）。这符合规则 4，因为策略只禁止进入其他设施的警戒区和禁飞区。
- 半程截断点取实测作业区间 \([\min_i t_{\mathrm{core},i},\ \max_i t_{\mathrm{exit},i}]\) 的中点：A 为 722.8 s 和 778.2 s，B 为 646.8 s 和 766.0 s。截断前缀中弦长、出区、绕圈三项条件均为 null，组判为“未知”。
- 耗时：
  - 单条端到端 120.7–135.2 s，其中包括分摊的骨架规划与单机测时 49.5–57.6 s；
  - 2 进程试点总耗时 269.9 s；
  - 1 进程复跑 419.8 s；
  - 全入口共 689.6 s。

图：

- 俯视图 A（同向）：`attempt_s2x_p1_20261014T045634Z_ee6ddc6f/family_s12_4d13d93f9171c446_ext_000_regular/synchronous/topdown.png`
- 俯视图 B（多向）：`.../family_s12_aa4c66be8e85d64d_ext_000_regular/synchronous/topdown.png`
- 配对时序图：`.../family_s12_aa4c66be8e85d64d_ext_000_regular/timing_pair.png`；A 的同名文件也已生成。

## 异常与处理

1. **相切航段被误拒。** 竖切的可见图航段与外扩边界精确相切，实测净空为 34.99999999999997 m，原检查会判为不合格。已在两个基础设施函数内部加入 \(10^{-6}\) m 容差。
2. **首轮过境试点的间距问题。**
   - 现象：首轮试点（attempt `attempt_s2x_p1_20261014T044237Z_cc8e4104`）中，A 同步版本的最小间距只有 7.04 m。
   - 原因：共享航线有一个约 144° 的急转弯，外侧车道用斜切连接时，离转角只剩 \(22.8\cos 72^\circ\approx 7.0\) m。
   - 修复：外侧连接改为圆弧，并补了测试。复跑后最小间距为 22.19 m。
   - 首轮 attempt 保留不删，结论以复跑为准；它不低于 2 m，属于记录项，不是生成错误。
3. **失败的回归 attempt 保留。** 前两次回归 attempt 保留不删：`..._041507Z_910bfcb0` 因执行前检查拦截未执行完，`..._041917Z_dd0577f9` 因 `task.json` 键顺序不同未通过。

## 已知限制

- A 的两个进场区编组在汇入弦之前各自飞行。共享航线可以消除同一障碍拐点处的车道交汇，但两组之间的会合只靠实测间距检查，规划层没有约束。
- 多向过境采用两侧方案：同一侧内各机的进入方位相差约 5°，总跨度来自两侧之间。
- 俯视图终点处的机号文字会重叠，仅影响观感。
- 时长 791–1030 s，超出 r4 的 5–12 分钟参考。这是统计结果，不是失败门槛。

## 第二段待办（等待确认）

1. 实现抵近观察、游弋监视、佯攻三个规划器与判据；新增事实各补一套独立复核。
2. 区域搜索改为新规划器：检查全部设施预警区；按扇区中心记录进入方位，支持多向。
3. 突防多组（主编组为突击）：
   - 掩护组与主编组针对同一设施时，作业几何错开扇区；
   - 多组逐组调用 `measure`；
   - 由角色组合推出集群意图并与指定核对。
4. 中止变体。
5. 运行 120 + 6 条，生成视图索引，完成交叉否定 960 项和全部统计与图件。

## 复现命令

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python -B -m unittest discover -s tests -p 'test_v07*.py'
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python -B scripts/run_v07_s2_expansion.py regression --workers 2
& 'C:/Users/shy/anaconda3/Scripts/conda.exe' run -n llm --no-capture-output python -B scripts/run_v07_s2_expansion.py pilot --workers 2
```
