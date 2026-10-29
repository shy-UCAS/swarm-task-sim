**S3-min 开工核验与待确认实施方案**

状态：PREPARATION_COMPLETE_AWAITING_CONFIRMATION。本文件记录第 0 节要求的准备与复述；S3 实现、T1–T14 和 Q0–Q4 尚未执行，不能视为验收通过。

依据：C:\Users\shy\Downloads\S3_数据加载与模板中文描述_指令.md。第 0 节要求完成环境和工作树后，复述字段、锚点、测试、快速检查，等待用户确认，确认后才实现。

**环境与读取边界**

| 项目 | 本次核实结果 |
|---|---|
| 工作树 | F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-s3 |
| 项目目录 | F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-s3\Multi-UAV SimpleGC |
| 分支 | fe/s3-language-loader |
| 起点及准备阶段 HEAD | debfadf6b4af446981e9cdbda081f2413962a190 |
| 创建方式 | 从指定 Simulation-fe-prod-r3 的固定提交创建同级独立 worktree；未改动来源工作树项目文件 |
| 初始状态 | git status --short 为空 |
| Shell | PowerShell 7.6.5；后续命令不加载用户 profile |
| Python 环境 | 新工作树 .conda-env = llm；Python 3.12.3；NumPy 2.5.3；未安装或升级依赖 |
| 允许读取的生产运行 | SwarmData\v07_first_edition\pilot_f000_005 |
| 完成状态 | manifest.json 存在；progress.completed = progress.total = 90；active / pending 均为空；P0_STOP.json 不存在 |
| 保留集合 | 60 条 episode；6 个保留 draw；每个“意图 × 时刻模式”有 6 条 |
| family 实际分母 | 登记 5 个 family；保留集合来自 4 个 family，另一个 family 的两个 draw 均 C_NOT_PAIRED |
| 第二批 | 未读取 pilot_f005_020 |
| 本阶段写入 | 仅新增本准备文档；未写 S3 模块、模板、脚本或测试，未写生产数据，未导出 |
| 执行范围 | 未运行仿真、规划、SITL、生产脚本或训练 |

run manifest SHA256：
491252c0ac1cd9b71b72e117848849f78f0df847f6a5429d0027275d9d799fe1

registration SHA256：
02fe3d84f3df46646e2c25a4b63313b4d03ff0ee3d8e754cd7dc329add5d2fe0

已读取的 episode 都先对其 manifest 与运行清单的 SHA256 进行核对。主核验样例的全部产物还通过了原 load_episode 的哈希校验。尚未进行 Q0 的全部 60 条产物校验。

**真实字段核验：第 6 节**

主样例为：
F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_first_edition\pilot_f000_005\episodes\family_s15_79c93b22d09e8a7a_ext_001_regular\sequential\labels.json

其 episode manifest SHA256 为 097f3f2dc8a558bdba6de2f764c82d567aa71d1af98147c3487f77c8cfb39e24；labels SHA256 为 e5d4d9089b7b103b1feb81ccf0f8726284a52e1460c4e5612613245c230c71e7。

本样例有 6 架、2 个编组：task_group_01 为区域搜索，4 架，目标 facility_03；task_group_02 为抵近观察，2 架，目标 facility_01。因此同一条真实 episode 可覆盖全部通用字段及 coverage / observation_dwell 两类条件字段。表中 {g}、{a}、{f} 分别表示实际 group_id、agent_id、编组的 assigned.target；写出事实记录时必须展开成具体 JSON Pointer。

| 事实 | labels.json 实际路径及计算 | 主样例核实结果 |
|---|---|---|
| n_agents | /agents 的键数量 | 6 |
| n_groups | /task_groups 的键数量 | 2 |
| cluster_intent | /cluster/assigned/intent | reconnaissance；只用于目标及意图句绑定，不进入输入 |
| cluster_status | /cluster/result/status | success |
| n_members | /task_groups/{g}/observed/members 的长度 | 分别 4、2 |
| role | /task_groups/{g}/assigned/role | 两组均 reconnaissance |
| execution_method | /task_groups/{g}/assigned/execution_method | area_search、close_observation |
| target_id | /task_groups/{g}/assigned/target | facility_03、facility_01；字段名确为 target |
| facility_no | 对上述 target 严格解析 facility_数字 | 3、1；不合法格式报错 |
| entered_warning_all | 对 observed.members 每个成员读取 /agents/{a}/observed/regions_by_facility/{f}/warning/entered_observed，全部严格为 True | 两组全部 True |
| approach_class | /task_groups/{g}/observed/approach_classification | 两组 same_direction |
| from_sector | /task_groups/{g}/observed/approach_headings_deg，实际类型是 agent_id → 角度的映射；取其成员角度做圆周均值、转为来向并分八扇区 | 第一组航向约 238.6404°，来向东北；第二组约 24.1619°，来向西南 |
| coordination | /task_groups/{g}/observed/coordination/classification | 两组 sequential |
| batch_count | 仅 sequential，读取 /task_groups/{g}/observed/coordination/batches 的长度 | 两组均 2 |
| group_status | /task_groups/{g}/result/status | 两组 success |
| coverage_pct | 仅 area_search，/task_groups/{g}/observed/shared_coverage/coverage_fraction；按原公式取最接近的 5% | 第一组 0.9836196564123052 → 100；第二组 shared_coverage 为 null，不读取 coverage_fraction |
| dwell_s | 仅 close_observation，各成员 /agents/{a}/observed/contribution/observation_dwell/total_duration_s 取中位数，再按原公式取整 | 第二组两个成员均 57.2 s → 60 s |
| exit_state | 非 intrusion 时读取 /agents/{a}/result/conditions/ended_outside_warning；全 True / 全 False / 其余分别 all_outside / all_inside / mixed | 两组 all_outside |

该文件定位：task_groups 从 1007 行开始；area_search 的 execution_method 在 1026 行、成员在 1094 行、coordination 在 1135 行、coverage_fraction 在 1148 行、headings 在 1157 行、approach_classification 在 1173 行；第二组 execution_method 在 1198 行、coordination 在 1289 行、headings 在 1300 行、approach_classification 在 1312 行；cluster 在 1323 行。uav_06 的 observation_dwell 在 947 行、total_duration_s 在 953 行、ended_outside_warning 在 1001 行。

另核实以下真实样例以覆盖六种执行方法和 intrusion 例外：
- family_s15_38bedc9d791d547b_ext_005_regular/sequential：transit。
- 同 family 的 ext_006_regular/sequential：close_observation。
- 同 family 的 ext_007_regular/sequential：monitoring。
- 同 family 的 ext_008_regular/sequential：feint。
- 同 family 的 ext_009_regular/sequential：两组 penetration，其中 task_group_02 的 role / execution_method 为 intrusion；没有 ended_outside_warning，按指令 exit_state 直接为 None，不把缺字段当 False。

以上路径均在第一批 episodes 目录内。未发现第 6 节要求的字段路径或已有函数与指令不一致。指令中的“5 个 family”是登记范围，保留集合的实际 family 数是 4；不改变抽取集合或划分规则。

**slots 的来源与计算**

| slot | 计算和来源 |
|---|---|
| n_agents、n_groups | 同上 /agents、/task_groups |
| approach_mode_cluster | 汇总全部编组 observed.approach_classification：全 same_direction → same；任一 multi_direction → multi；其余 unknown |
| from_sector | 只有单编组且 same_direction 才保留该编组来向；多编组为 null |
| deepest_layer | 逐编组按其 assigned.target，读取成员 regions_by_facility 下 warning / alert / protected 的 entered_observed，映射为 1 / 2 / 3，未进入为 0，取最大；不采用其他设施或 planned 字段 |
| coordination_cluster | 全部 observed.coordination.classification 相同则保留，否则 mixed |
| exit_cluster | 汇总非 intrusion 成员 ended_outside_warning，全 True 为 all_outside，否则 other |
| intent | /cluster/assigned/intent |

主样例的 slots 应为 n_agents=6、n_groups=2、approach_mode_cluster=same、from_sector=null、deepest_layer=1、coordination_cluster=sequential、exit_cluster=all_outside、intent=reconnaissance。各项保留参与计算的具体 JSON Pointer。

public_scene 的实际顶层键为 coordinate_system、entities、entry_zones、schema_version、units、world。设施位于 entities，目标设施身份用 id，圈层另有 facility_id。模型 scene 原样使用公开场景；不合入 labels、task、source。

**归一化锚点复述：第 8 节**

原加载函数 task_v07/io.py:92 的签名为 load_episode(root, agent_ids=None)，返回键正好是 INPUT_KEYS（第 13 行）：x、mask、t_s、agent_ids、scene。它校验 manifest 中全部产物后，从 observations.csv 还原观测数组；S3 复用此接口，不用直接读 npz 绕过它。主样例实际输入 x 形状为 [7142, 6, 6]，mask 为 [7142, 6]；真值 p、v、a 为 [7142, 6, 3]。

1. 逐成员 release_s：task.initial_settle_s 加 source.departure_delays_s[agent_id]；误差阈值 \(10^{-6}\) s 内必须落在 0.1 s 网格。
2. endpoint：task.references[agent_id].points_enu_m 最后一个三维点；不能使用二维距离。
3. stop_radius / stop_speed / stop_hold：优先使用 task 顶层 stop_*，缺省才使用 terminal_*；与 task_v07/execution.py:92–94 一致。
4. 在 truth_10hz 的 time_us / p / v 上计算每帧是否同时满足三维终点距离、三维速度和释放时刻要求。按 agent_ids 映射列，不能假设字典顺序等于数组列顺序。
5. t_c：从最后一帧向前找连续满足条件的后缀的第一帧。最后一帧必须满足条件，后缀帧数必须至少为 \( \operatorname{round}(stop\_hold\times10)+1 \)。不能使用首次经过终点或中途停留的起点。
6. visible_end = t_c + stop_hold；成员区间 [release_s, visible_end]，两端都包括。
7. episode 的 t0 为最早 release_s，t1 为最晚 visible_end；保留闭区间 [t0,t1] 的帧，保存首尾帧索引（明确为两端包含）。
8. t_s_n 是保留的原时间减 t0；成员在可见区间外 mask=False，x 的六个通道全部为 0，按 T8 的要求执行；可见处 x 逐值保持原观测。agent_ids 与 scene 不变。
9. 每个成员必须有可见帧；t_c 后可见时长必须恰为 stop_hold；中途驻留和作业折返保持可见；可见 x 与平移后的时间能逐帧对应 raw。
10. 索引保存上述锚点，正式加载直接使用保存的锚点；测试从真值独立重算。task 与真值只参与锚点计算，不进入输入或中文描述。

主样例 task.json:6 是 initial_settle_s=20；18–20 行分别为 stop_radius_m=15、stop_speed_m_s=1.5、stop_hold_s=1。7–9 行 terminal_* 则是 2 s、1 m、0.15 m/s，两组参数不同，必须按优先级取值。source.json:284 为顶层 departure_delays_s；例如 uav_02 延迟 108.4 s，因此 release_s=128.4 s。准备阶段未执行完整归一化，未宣称真实后缀停留不变量已验收。

**描述、划分与输入隔离的实施规则**

六类角色句按 execution_method 选择；先判断 observed/result 门控，门控不满足直接省略整句。按 group_id 排序，每个编组的第一句有明确主语；单编组用“该编组”，多编组用“第i编组（m架）”。approach 省略时，把主语放在该编组实际首句，避免句子无主语。严格采用指令中的全部模板和取整规则，不润色模板。

每个事实存 JSON Pointer，每句存 type、template_id、text、values、fact_refs。独立验证器从原 labels 和公开场景重算绑定值，不把渲染器或保存的 facts 自己比较自己。所有模板和输出均做指令规定的禁用词检查。

train/val 每条生成 3 个 A 组变体；test 主评估 1 个 B 组变体，另加 1 个标记 diagnostic_template_A=true 的 A 组变体。种子按指令中的 episode_key 与 variant 计算。模板全文、门控和规则不自行修改。

family 哈希规则保持不变。根据保留清单只读预计算，实际为：
| family | u | 划分 | episode 数 |
|---|---:|---|---:|
| family_s15_38bedc9d791d547b | 0.2882676033768803 | train | 10 |
| family_s15_79c93b22d09e8a7a | 0.7353079172316939 | val | 20 |
| family_s15_c713f51898e81011 | 0.8703451119363308 | test | 20 |
| family_s15_ef1ed9ff0b0e7013 | 0.7970854777377099 | val | 10 |

即 train/val/test 为 10/30/20 条；这是清单预计算，正式导出须复核。不为了平衡数量重划分 family。

输入严格只有 INPUT_KEYS；描述、slots、intent、family_id、split 由 load_targets 单独返回。导出只保存索引、事实、描述和锚点，不复制轨迹数组。

**T1–T14 的具体构造**

| 测试 | 夹具与断言计划 |
|---|---|
| T1 | 合成 heading 映射：0°→西、90°→南；把来向 22.4°、22.6° 转回航向输入，验证东/东北边界；359°和1°的圆周均值验证跨零方向。 |
| T2 | 从合成成功编组出发，分别改变 group_status、entered_warning_all、exit_state、coordination；验证对应句型被整句省略，同时覆盖 approach 省略后的首句主语。 |
| T3 | 参数化五种 cluster intent 与 success/failure/unknown；成功使用正确中文名和 conforms，其他只用 insufficient。 |
| T4 | 显式断言 coverage 0.874→85、0.876→90；dwell 4→10、74→70、75→80，锁定 Python round 口径。 |
| T5 | 同一合成 episode 分别指定 train/val/test；逐句检查模板组、变体数及诊断标记，主测试集不混入 A 组。 |
| T6 | 扫描全部真实模板和渲染结果；在临时模板副本注入禁用词，确认被拒绝，原模板不修改。 |
| T7 | 用独立验证器根据绑定的具体 JSON Pointer 重算值；渲染后只篡改合成 labels 的一个事实值，确认定位不一致；不让验证器信任缓存 facts。 |
| T8 | 两成员、0.1 s 网格、不同 release、已知中途停留和不同终点连续后缀；精确断言 t_c / visible_end / t0 / t1、首时刻为0、mask、不可见处全部通道为0、末端恰好保留 stop_hold、中途驻留仍可见，以及 raw 帧对应关系。 |
| T9 | 分别构造最后一帧不满足停止条件、连续后缀比所需帧数少一帧；均应抛 P0。另覆盖释放时刻不在网格的拒绝路径。 |
| T10 | 在测试临时目录构造符合既有格式的最小 episode 并调用加载入口；验证返回键严格等于 INPUT_KEYS，公开 scene 递归不含意图/角色/assigned/target 键，目标与输入分离。 |
| T11 | 固定 family_id 重复计算、同 family 多 draw/intent/mode 混排，验证划分不变且全部同组。 |
| T12 | 临时 run/episode：篡改 episode manifest 的哈希；分别缺少 run manifest、progress 未完成、active/pending 非空、存在 P0_STOP；验证 P0 或指令规定的退出码3。还验证导出目录已存在时拒绝覆盖。 |
| T13 | 在允许的 S3 输出区域使用两个全新、不覆盖的导出目录，对同一第一批数据各导出一次；episodes.jsonl 与 descriptions.jsonl 逐字节比较。无外部数据时仅此类集成测试可明确 skip。 |
| T14 | 用已核实的 ext_009_regular/sequential 多编组突防样例，验证“第1编组（m架）…该编组…”结构和 group_id 顺序；无外部数据时说明原因再 skip。当前数据存在，验收应实际运行。 |

以上是 14 类测试要求，具体 unittest 方法可能多于 14；报告分别列出覆盖编号与真实执行数，不混淆两者。T1–T12 只用测试自建临时数据；所有测试都用 python -B -m unittest -v 模块名，PYTHONPATH 设置为当前项目根和 tests 目录。

**Q0–Q4 顺序和通过标准**

| 顺序 | 执行内容 | 标准 |
|---|---|---|
| Q0 | 对唯一允许的第一批检查完成状态，从 retained_episodes 逐条校验 episode manifest 哈希，再通过既有加载器校验产物；核对每个 draw 的意图和时刻版本。 | 60 条全部有效，6个 draw × 5意图 × 2模式严格齐全；任何哈希不符即 P0 停止。 |
| Q1 | 导出到 F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_first_edition_s3\s3_dev_f000_005；执行 T1–T14，包括额外新目录的重复导出检查。 | 测试全部通过；禁用词0；绑定不一致0；目录存在则拒绝，不能覆盖重跑。 |
| Q2 | 按意图×模式报告 raw 末端停留、normalized 的 t_c 后可见时间、成员可见时长、归一化 episode 长度的中位数和 p90，列出真实 stop_hold。 | 诊断统计完整、分母清楚，不增加指标门槛。按指令采用成员级口径；episode 长度随成员登记，并明确其为成员加权统计，同时标注独立 episode 数。归一化不变量仍必须满足。 |
| Q3 | 输出 samples_for_review.md，每个意图同步/递次各1条，包含多编组；列事实表和 A/B 描述。 | 样例覆盖齐全且可追溯；供人工审阅通顺与准确性，不把自动检查冒称人工批准。 |
| Q4 | 全部60条调用 raw / normalized load_inputs 以及 load_targets，记录耗时。 | 各视图内部 x、mask、t_s 的时间维匹配，成员与通道数一致；normalized 允许按定义裁剪时间长度，检查其与 raw 的对应帧一致、不可见处x为0；输入/目标字段隔离正确。 |

任一真正失败按第 15 节保存证据、提交推送后停止。自己新写脚本的实现错误限额 3 次，单独 fix(s3): 提交并补失败路径测试；不能借修复改变模板、门控或归一化定义。这里尚未动用修复额度。

**确认后的任务列表**

- [x] 通读指令并确认边界。
- [x] 新建固定起点的独立工作树并核实环境。
- [x] 真实 episode 字段和现有加载接口核验。
- [x] 写出锚点、T1–T14、Q0–Q4 计划。
- [ ] 用户确认第 0 节复述。
- [ ] 新增 task_v07/s3 模块。
- [ ] 新增原样模板配置与测试。
- [ ] 新增导出脚本，单进程执行 Q0–Q4。
- [ ] 写 S3_report.md，记录真实测试计数、诊断、样例路径与限制。
- [ ] 按模块/模板/测试/脚本和文档分批提交，打印并核对分支后再 commit。
- [ ] 非强制推送 fe/s3-language-loader，核对远端与本地 SHA，停止。

已知限制将如实保留：仅完整 episode、登记仅5个 family而保留只有4个、样本不足以评估划分；出发前等待通过各成员可见起点及共同时间轴保留协调信息。第二批、仿真和训练不在本轮执行范围。
