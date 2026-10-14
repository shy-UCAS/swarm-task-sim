# S2 第二段修复与试飞报告（进行中）

当前完成 P0 修复与验证，正在继续交接第 8 节；未达到四角色试飞达标标准。

## P0 修复与证据

- 已知答案合成轨迹测试 2/2 通过：佯攻警戒带深度 75 m、比例 0.5；监视最后有效巡视帧之后终点保持 3 s。
- 旧真值重算：attempt_s2x_p0_relabel_20261014T115331Z_66ea5323，8 条 episode 全部独立审计 PASS，事实与圈层差异 0，未覆盖条件 0。
- 佯攻 9 机深度恢复为 237.089–242.802 m。监视保持时长沿用竖切首末帧时间差 (帧数−1)/10；前轮诊断以帧数/10 多计 0.1 s，本轮更正为 2.0–348.3 s，原见证保留。
- 固定回归：attempt_s2x_regress_20261014T115539Z_7b917ac6，12/12 PASS，竖切 8 条逐字节一致，内容差异 0；过境 4 条采用当前基准 attempt_s2x_p1_20261014T063446Z_5f0ab712，由适配层执行冻结骨架。
- 过境预期变化：增加每机 observed.work_end_s（完整与前缀）；相应标签哈希更新；独立审计报告新增条件映射与全部依据事实。其余轨迹、时序、原有语义和几何无变化。

## 条件 → 独立审计项

审计脚本 scripts/audit_v07_s2_conditions.py 不导入 task_v07。每个 episode 保存 condition_audit_map；任一实际条件没有独立对应项，返回 P0_STOP。所有原圈层由解析圆 / GEOS 原轮廓独立重算。

| 角色/作用域 | result.conditions 条件 | 独立审计项 |
|---|---|---|
| 过境 | entered_warning / exited_warning | 独立预警区进入、退出帧与 work_end |
| 过境 | chord_length / entry_exit_azimuth_difference | 独立进出坐标、弦长与方位夹角 |
| 过境 | no_stop_in_warning / no_loop_in_warning | 低速最长区间、速度航向累计转向 |
| 抵近观察 | reached_observation_point / minimum_dwell / no_alert_entry | 观察半径成员关系、最长连续驻留、警戒进入 |
| 监视 | started_orbit / completed_laps / stayed_in_band | 位置/航向/速度持续见证、累计方位圈数、巡视帧环带关系 |
| 监视（组） | shared_revisit | 全组上环线至首人离线窗口、36 方位扇区重访间隔与阈值 |
| 佯攻 | entered_alert / depth_in_band / no_protected_entry | 精确警戒进入、轮廓距离深度与比例、禁飞进入 |
| 佯攻 | retreat_direction | 精确轮廓距离最小时刻、离开预警区、历史回落与下降帧比例 |
| 突击 | entered_protected / required_depth | 禁飞进入、精确禁飞深度 |
| 区域搜索 | effective_observation / scan_lane_evidence / no_alert_entry | 足迹有效帧、按序条带端点、全部设施警戒关系 |
| 区域搜索（组） | shared_coverage | 独立生成检查网格、实际足迹联合覆盖 |
| 全部扩展角色 | own_endpoint_hold | 实测 work_end 后的终点距离、速度、连续保持时长 |
| 非突击 | reached_retreat_point | 实测 work_end 后本机终点首次到达 |
| 全部扩展角色 | exclusion_policy_respected | 独立全设施圈层与每机明确禁入策略 |
| 任务组 | member_contributions_complete / multi_direction_span | 独立单机条件结果、实测核心事件前最后 100 m 航向与最大夹角 |

## 诊断骨架授权

4d13d93f 的原多组突防骨架没有现成单组替代。按用户明确授权，后续确定性提取主突击组，使用独立诊断 ID 与 diagnostic_only=true；保持其目标、成员、family 速度/高度/初态及原列序中的相对顺序。其他组成员不参与飞行；不写回基础设施描述符，不进入视图、成功率统计或交叉否定。全量仍使用原多组骨架。

## 继续顺序

共享编队走廊 → 数字槽位多向分股 → 精确作业点 → 恢复监视 2–3 圈与全航线双版本 6 m 拦截 → 净空/时长修复 → 规划冒烟 → 8 骨架试飞与截断/俯视图 → 达标汇报。
