"""Report fragment executed by package_part7 after all required evidence has passed."""
def table_dist(data, names):
    lines = ["| 指标 | n | min | p50 | p90 | max |", "|---|---|---|---|---|---|"]
    for name in names:
        d = data.get(name)
        if d:
            fmt = lambda v: "N/A" if v is None else f"{v:.9g}"
            lines.append("| " + " | ".join([name, str(d["n"])] + [fmt(d.get(k)) for k in ("min", "p50", "p90", "max")]) + " |")
    return "\n".join(lines)

dist, extra = analysis["retained_distributions"], supp["distributions"]
phase_table = table_dist(dist, ("close_ingress_s", "warning_before_dwell_s", "dwell_s", "warning_after_dwell_s", "close_exit_s", "closure_residual_s", "pre_release_hold_s", "terminal_hold_s", "release_quantization_s"))
observed_table = table_dist(dist, ("observation_start_minus_arrival_s", "observation_confirm_minus_arrival_plus_window_s", "observation_confirm_minus_departure_s", "member_arrival_span_s", "pd_min_pair_distance_m", "nominal_endpoint_distance_m", "measured_endpoint_distance_m", "measured_min_separation_during_member_dwell_m", "measured_dwell_point_max_error_m", "max_target_layer", "end_target_layer"))
tracking_table = table_dist(extra, ("tracking_max_frame_pos_err_m", "tracking_max_step_pos_err_m", "main_measured_min_separation_m", "diversity_measured_min_separation_m", "measured_warning_entry_minus_nominal_entry_s", "measured_warning_exit_minus_nominal_exit_s", "main_optimization_s_all_attempts", "diversity_optimization_s_all_attempts"))
failure = analysis["failure_tables"]
failure_text = "\n".join(f"- {key}: `{json.dumps(value, ensure_ascii=False, sort_keys=True)}`" for key, value in failure.items())
gaps = {key: max((float(b["gap"]) for b in metrics[key].values()), default=None) for key in ("facility_gap", "speed_gap", "group_gap")}
report = (DOC / "REPORT.md").read_text(encoding="utf-8")
line = next(x for x in report.splitlines() if x.startswith("> **当前状态："))
report = report.replace(line, "> **当前状态：第1–7部分完成。主批200/200、多样性100/100成功，独立落盘复核全部通过，450对归一Fréchet中位数88.256；固定5键串行合同bytes全部一致。第8部分独立产物预置与最终冻结快照待执行。**")
report += f'''

## 7. 全量、5键复跑与五意图诊断——完成

第6部分提交`ca7a46912607807c39c7103e265a78e9c24413c1`已推并核对。正式全量前，单进程原生多样性o02_d0_b0（9成员）成功，before/after各163点、唯一in/out、磁盘复核通过，27.280722秒；该诊断不计正式100合同。随后24进程主200＋多样性100按固定名单完整运行，无补抽、豁免、异常、未派发或缺记录。运行前后通知用户，生产运行源码与第二轮门禁相同，没有新增共享修改；下述专用分析CLI修正不影响任何生产路径。

| 全量止损项 | 实测 | 触发线 | 结论 |
|---|---|---|---|
| 主批成功率 | {summary['main_successes']}/200，{metrics['success_rate']:.6f} | <80% | 通过 |
| 设施/速度/实际人数最大档差 | {gaps['facility_gap']} / {gaps['speed_gap']} / {gaps['group_gap']} | 任一>20个百分点 | 通过 |
| 成功合同post失败中位数 | {metrics['post_optimization_failures_median']} | >0 | 通过 |
| 所有有效对合并归一Fréchet中位数 | {metrics['frechet_pooled_median']:.9f}，{metrics['frechet_pairs']}对 | <1或无有效配对 | 通过 |
| 已保留违规/落盘不一致 | 0，全部300已独立复核 | >0为P0 | 通过 |

多样性{summary['diversity_successes']}/100成功，10族各10分支完整，450个有效对；scope全部为close_observation_warning_entry_to_exit_v19。每对距离除原公共横向间距一次后合并取中位数，已从全部block原距离独立重算，与原生值逐值一致；没有先取族中位数或按驻留时间重复加权。native派发与报告墙钟{native['dispatch_wall_s']:.6f}秒；包含启动及全部磁盘复核的包装器墙钟{watch['wall_s']:.6f}秒。此前454秒预建仅复用文档，没有再执行或再次计入本段墙钟；原7200秒合作退出预算未改。

### 固定5键单进程复跑

全量开始前登记o01_d0..o01_d4，用原rerun_stage固定1进程重跑，包装器{repeat_watch['wall_s']:.6f}秒。5/5合同递归文件集合及全部原bytes相同，排除[]；不只比较成功字段，不重选键。P0清单[]。[reproduction](part7/rerun_r1/reproduction.json)保存逐文件证据。

### 五意图配对与失败原因

固定200键外连接，五列完整保留，旧突入o34_d3仍在其原失败列，不迁移为新意图豁免。公共成员/目标/速度/先验队形差异0。close/transit最终保留几何分类为`{json.dumps(dict(classifications), ensure_ascii=False, sort_keys=True)}`；相同retained attempt的几何差异0。不同retained attempt逐项保存格、队形、LP/回退、连接、speed events、驻留站点和ticks；不能把不同attempt的差异解释为同一次几何改变。第3部分原oracle的同attempt RNG前缀证明仍单独保留。

失败表覆盖主200和多样性100全部失败attempt，同attempt同子类去重；“每合同第一次失败”只看第一次失败attempt，若它不是语义阶段则不在第二张语义表计数：

{failure_text}

上述值及逐行配对见[analysis](part7/analysis/)。原生post计数由所有300个结果的明确optimization_entered标记独立重算并逐项一致；成功attempt不计失败，骨架和物理/语义失败分开。主批8次骨架普通失败不从分母排除。特殊o17_d1/o17_d4/o34_d3均按主批正常计数，详见各合同及配对行。

### 五段名义时间与实测诊断

进场、预警内驻留前、驻留、驻留后至出圈、撤离依次为[r,t_in]、[t_in,t_a]、[t_a,t_b]、[t_b,t_out]、[t_out,e]，使用分侧站点时间映射。以下为成功成员分布，单位秒，释放前20秒与末端2秒单列，不重复计入五段：

{phase_table}

首次20秒驻留确认相对名义区间的偏差、成员ta跨度和距离仅作诊断，不设置额外同步/检测误差/间距阈值。首个冻结窗口来自frame_index/confirm_frame_index，20秒确认不当作整个Td结束。nominal_endpoint_distance与measured_endpoint_distance分别列出：

{observed_table}

其中member_arrival_span_s每个成功合同仅一个样本，n=300；其他成员指标按n列所示统计。初版分析CLI把合同跨度再逐成员加入，错误得到n=1729（300合同＋1429成员），p50=4.714135918、p90=14.973256549秒。依据第3部分检查点裁定新增第4节，直接修正本项新增专用分析CLI：逐成员循环不再重复计入该合同级字段，不改生产代码、冻结对象、定义、阈值、随机数或预置。修正后n=300、p50=2.647968622、p90=13.381367724秒，max仍28.600800817秒。快速检查从每个保存结果的各成员nominal_arrival_s独立重算max−min，全部分布值一致；除这一分布外，所有诊断及五意图配对前后完全一致。旧r1保存在analysis_before_fix，新r2为analysis；[修正审计](part7/analysis/arrival_span_fix.json)保留前后源SHA、数值和检查结果。只改专用分析文件，不涉及任何共享文件或旧意图代码路径，所以第二轮门禁不需重跑；生产stage的完整源码SHA彼此及第二轮门禁仍相同。最终源码与该生产SHA的唯一差别为此分析CLI一行统计修正，合同全树排除仍[]。

所有成功成员实测warning进入1次、目标最深层1、末层0；限制区/其他设施圈层与间距由冻结完整段/有效性另验。原始首次进入/首个False退出微秒、驻留首窗口和ticks全保留；合并时长tick直方图见supplemental，时长全在定义域内。追踪、整段间距及全部attempt优化成本如下（成员距离以米、其余按字段单位）：

{tracking_table}

两类成本/缓存计数全在合同外；冷/热最大查询另见第3部分，正式预建/只骨架另见第5部分，不混为单车道或生产优化耗时。本部分全部P0清单[]。证据[part7/summary.json](part7/summary.json)、全量/复跑watchdog、disk_verification、两张失败表、五意图200行及完整原始输出SHA索引齐全。大轨迹和作业段曲线仍留本地run，不推送。独立预置9.3和最终冻结快照留下一部分完整执行。
'''
(DOC / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
