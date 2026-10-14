# S2 第二段后续：条件 → 独立审计项

既有单机与任务组条件继续采用 [四角色修复报告](S2_expansion_phase2_repair_report.md) 的完整对照表。区域搜索复用其中已有的 `effective_observation`、`scan_lane_evidence`、`no_alert_entry`、`shared_coverage` 以及公共撤离、终点保持、禁入、成员贡献和多向跨度条件，没有增加或放松条件。

以下两项聚合条件已在多组试点 10 条实飞及单组补验 2 条实飞中通过独立审计，差异与未覆盖条件均为 0；其中多组试点有 1 条实测间距不足 2 m 的生成错误，审计通过不意味着该条可进入训练视图。实际证据以每条 episode 的 `independent_exact_audit.json` 为准。

| 层级 | result.conditions 条件 | 独立审计实现与依据 |
|---|---|---|
| 集群 | all_task_groups_complete | `scripts/audit_v07_s2_groups.py`：逐组独立调用条件审计，聚合独立组结果；不复制生产侧集群结果 |
| 集群 | assigned_role_composition_matches | 同脚本：独立实现规范角色组合到基础指定意图的映射，对照登记的指定意图；该项是指定任务一致性，不冒充可见行为 |

多组测量只通过 `labels.measure` 逐组计算事件与事实，再组装集群。独立审计不导入 `task_v07`，从同一 10 Hz 真值重算全部设施圈层、每组角色事实、组内时序批次、跨组最小间距、主要目标及组间事件顺序。不同角色的事件先后不解释为同步协同或因果关系。

任何实际出现但没有对应独立项的单机、组级或集群条件都返回 `P0_STOP`。代码接入后的覆盖数量和差异数必须由实际审计记录给出。
