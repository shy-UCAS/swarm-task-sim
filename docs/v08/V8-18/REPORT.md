# V8-18 佯动单段执行报告

> 本次接续执行方：Codex（GPT-6；未读取更细模型标识），2026-11-08。代码基线为 `6dba0bc0a3813b6241fafb4c2b4f2d54a8e669b3`；本次从本地与远端一致的 `4da418298fe42d66fcbecd166cb782868d19b575` 接续。分支仅 `review/v08/V8-18-feint`。生产源码从 `8e22f064899cd8fd832f90558da282fb319eed05` 起未再改变。
>
> 项目只生成带标签的合成轨迹数据，供防御方意图识别研究使用：抽象几何、点质量运动学，无真实载具控制。佯动为进入目标警戒层一次、避开保护层并退出；规划只求可飞、可行与无冲突。

## 1. 当前交付状态

**指定运行检查点全部完成，未触发止损或三项P0。** 主批200/200、多样性100/100、五键单进程字节复跑5/5；保存后300合同全部独立复核。另有一项\(L=0\)原始观测字段口径问题明确留待审查（第7、8节）。这是执行方有记录的运行与复跑，审查方独立复跑尚未执行。

| 部分 | 状态与证据 |
|---|---|
| 1 输入、名单、快照、旧测试与预置落盘 | 前次已完成，`f687299`；[manifest](manifest.json)、[初始快照](snapshot_part1.json)、[旧测试基线](part1/tests_baseline.txt) |
| 2 通用掉头映射、第一轮旧意图门禁 | 已完成；监视/过境/突入各20/20字节一致，排除[]，见[part2](part2/) |
| 3 骨架、screened、剪枝与等价性 | 前次1,021,860候选三路差异0；本次谓词未变，依最新裁定不重跑，见[三路门禁](part3/turn_gate_summary.json) |
| 4 检查、实测1/1、白名单、第二轮门禁 | 前次完成；本次因共享预热分支变化重跑，三意图各20/20，排除[]，见[最新门禁](part5_lazy/) |
| 按需判空改造与新自加测试 | `8e22f06`，新增lazy4项通过；连同其余测试最终27通过、SceneGate1项未执行/替代证据；真实骨架1/2进程两键字节一致 |
| 5 200只骨架 | 完整200/200，208attempts，形状复核0/208，24进程墙钟2031.349s，全部止损未触发；`784b62f` |
| 6 20全链路快批 | 完整20/20，post中位0，优化耗时中位6.729s；保存后99成员冻结/事件复核通过；`59606dc` |
| 7 主批、多样性、五键复跑与四意图诊断 | 主200/200、多样性100/100，450有效对；5键105文件全同；200键四意图及969成员观测配对，`97fc871`，[part7](part7/) |
| 8 最终快照、报告与推送 | all_frozen_ok=true；29族155缓存文件全同；报告按最终实现重写，历史保留，[part8](part8/) |

所有结果属于执行方运行记录；执行方五键复跑与审查方独立复跑分别标注。

## 2. 依据、裁定与执行边界

四份依据按优先级递增：`V8-18_佯动单段_执行指令_20261106.md`、`V8-18_GPT指令评价与裁定_20261107.md`、`V8-18_成本检查点裁定_20261107.md`、`V8-18_预建改为按需判空_裁定_20261108.md`。原文件在 `_handoff/2026-11-06_V8-18_feint/`，身份见manifest、[四份裁定身份](part8/ruling_index.json)及历史证据；两份成本相关裁定原文副本保存在part8/rulings。

- 附录五条裁定继续适用：screened采用双向确定/中间精确；抽样按非空组合及联合记录，不要求A或种类边缘均匀；核心必要条件剪枝和确定性子集门禁；几何半径上界及实际横/纵形变支撑之并；其余冻结口径不变。
- 负下界反例仍保留。前次只依裁定1改了两处预置断言/模式，原新完整SHA及diff见[preset_ruling1.diff](part3/preset_ruling1.diff)；本次预置三文件及原extra文件均未修改。
- 2026-11-07成本裁定第2节继续有效：直线段分解、逐集合距离检查、门禁只取A非空格、以24进程三路门禁替代单进程SceneGate均已被接受；代码位置与原运行记录见历史报告。
- 第一次成本检查外推63.2分钟超过45分钟；第二次90分钟预建完成29/40族。这两次正确停止的证据保留在[part5](part5/)，未覆盖。最新裁定已取消全格预建、45分钟外推和90分钟上限。
- 当前采用随机排列候选格、按需判空；单进程三键快速骨架施加900秒上限，正式200骨架施加整批3600秒上限。A级整行剪枝的后续提速路线没有在本轮擅自实施。

范围仍为第0编组、圈外起步的最后单段feint。唯一预算20attempts；probe、格查询与组合认证不算attempt。无不可行排除名单；o17两键与o34_d3均正常计入feint分母。规划35/10/35米余量、3/2米间距口径、速度先验、求解器/Prepared/冻结判据均不改。`monitoring_turn.py`只调用不修改。

三条P0保持为：旧意图字节差异；保留结果的实测违规或warning/alert进入不为1/1；固定五键单进程字节复跑差异。触发即停并提交推送，不修复重跑；成功率、成本等按各节止损处理。

## 3. 当前实现与缓存

1. formation流确定槽位序，全部probe共用。
2. 每个probe先用原廉价入口条件取得按theta/h排序的候选格表，再从shape流调用一次permutation。
3. 沿排列按原`first_feasible(mode="screened", prune=True)`的固定规范顺序判定非空，取首个非空格；完整表全空才进入下一probe，梯形每次二分各走一次排列。
4. 在选中格内仍按原connect组合排列、`choose_joint_turn`、相容集合距离、K/logit、路由与speed顺序抽样。下游失败直接结束本次attempt。

均匀排列中首个非空格在全部非空格上均匀；判空不消耗RNG。单合同存在性memo只影响耗时，合同身份改变即清空，命中不改变排列、谓词或确定性载荷。入口表、单车道、距离场等几何缓存继续复用。

原29族共155个`cache/feint_v18`存在性文件只保留作证据，生产不再读写。初始/快速检查后/200骨架后/全部批次后SHA、大小、mtime及FT/MT/预置/owner散列核对见[最终核对](part8/preservation_final.json)、[preservation_before](part5_lazy/preservation_before.json)、[after_quickcheck](part5_lazy/preservation_after_quickcheck.json)、[after_skeleton](part5_lazy/preservation_after_skeleton.json)。首轮时间戳比较器的PowerShell自动类型转换假差异已分项确认并留证，未改缓存。

本次生产改动只有`feint_chords.py`、`intents/feint.py`、`run_feint_v18.py`，以及共享`joint_intent.py::_prewarm_family_feint`。后者只预热既有几何并登记人数，不再求格存在性。认证主体`feint_turn.py`未改。旧全格API保留供历史诊断，生产入口撤下cost-check/prewarm阶段。

计时、命中、完整走格下标与堆栈只在合同外；合同只保留确定性业务字段。比较排除清单始终[]。运行命令、24/1进程及路径见[RUNNING](RUNNING.md)。

## 4. 测试与旧意图保护

| 测试 | 本次结果/状态 | 预建影响与处理 |
|---|---|---|
| NumericPreset | 8/8通过 | 无预建依赖，文件未动 |
| InterfacePreset | 2/2通过 | 无预建依赖，文件未动 |
| SceneGatePreset | 未运行，以原三路门禁替代（依成本裁定） | 调用迭代/认证，不加载预建；skip不算通过 |
| ArtifactPreset | 3/3通过，142.143秒 | cache只供几何加载；不要求预建命中，断言未动 |
| 原extra | 10/10通过 | 无预建/命中/load_chord_set依赖，文件未动 |
| 新extra_lazy | 4/4通过 | 固定排列、全空退让、冷热RNG、真实1/2进程骨架字节对照 |

测试影响逐项检查：NumericPreset的8方法、InterfacePreset的2方法、原extra的10方法均不调用load_chord_set、不要求预建或cache命中。SceneGate直接调用gate_cells/认证迭代，不读格存在性缓存；Artifact的3方法只用cache加载几何和原实测核验，不断言预建/命中。新增lazy中冷热memo测试及1/2进程真实测试直接覆盖按需路径，其余两项是确定性桩。旧V8-17动态测试patch的是intrusion_chords，与本次feint改动无关；其余旧测试无feint预建命中预期。依赖旧预建或load_chord_set的测试清单为空；需改断言的测试清单为空。本轮测试调用路径无须改动。最终acceptance索引仅通过`--phase4-root`选择最新第二轮门禁目录，预置断言不改。

最终计数为27通过、SceneGate1项未执行/按已裁定证据替代，无失败。Artifact原文件SHA保持028620ee13f136efec275f2925ae7e8948b46e75d2c7fd91c58b3c9c86eeea52，日志[part7/test_preset_local_artifacts.log](part7/test_preset_local_artifacts.log)；Numeric/Interface/原extra/lazy日志在part5_lazy，源码SHA与名单见最终快照。

桩测试原文“第2、5个非空”与明确的“4空→1非空、两次调用”有序数歧义；本次以明确序列和调用次数为预期，非空下标设1、5，预置断言未涉及此歧义。真实对照o01_d0及伴随o01_d2在1/2进程下各3个合同文件集合/bytes全同，见[lazy_process_comparison](part5_lazy/lazy_process_comparison.json)；不替代正式五键复跑。

| 字节门禁 | 监视→full_v14c | 过境→full_transit_r2 | 突入→V8-17 full_r1 |
|---|---|---|---|
| 原第一轮 | 20/20 | 20/20 | 20/20 |
| 原第二轮 | 20/20 | 20/20 | 20/20 |
| 本次共享分支改动后重跑第二轮 | 20/20 | 20/20 | 20/20 |

全部递归比较文件集合和原始bytes，包括失败合同，排除[]。最新证据[monitoring](part5_lazy/gate_monitoring.json)、[transit](part5_lazy/gate_transit.json)、[intrusion](part5_lazy/gate_intrusion.json)。原基线身份与输入SHA见manifest；开发集SHA为`223e0e0d0745c3f72290da8e7260fa995a1ea18b37706f85ab8e5e99ea9f36e0`。

环境：PowerShell7.6.9，项目Conda llm，Python3.12.3、NumPy2.5.3、SciPy1.14.1、shapely2.0.7，四个BLAS线程变量均1，默认24/复跑1；未安装或升级依赖。已有NumPy/SciPy版本提示保留，测试实际结果如上。首次沙箱内conda启动受DLL限制未运行测试，之后以相同llm在沙箱外执行，无自动审批拒绝。

## 5. 快速检查与200骨架

三键单进程骨架均第1次attempt成功：o01_d0为4.234秒、走1/1981格；o02_d0为24.951秒、走3/2107格；o11_d1为37.888秒、走1/2748格。落盘后真实支撑之并/核心、base、完整穿越、掉头表、LP上界、进场、终点及字段扫描均通过，见[smoke复核](part5_lazy/smoke_lazy_audit_r1.json)。

o17_d1/d4集合诊断分别641.632/648.201秒，均12机横排起步，经10个probe、4个全空后在步长12.165685米梯形找到非空格；总走9989/10167格。两选中格均仅teardrop正负组合非空。逐probe表与走格下标见[queries_summary](part5_lazy/queries_summary.json)及两份原查询JSON。快速检查实际约23分钟；三键骨架均未触及900秒硬上限。

| 200骨架止损 | 实测 | 结论 |
|---|---|---|
| 成功率 \(<95\%\) | 200/200 | 未触发 |
| 人数档落后 \(>10\) 个百分点 | 110/110、56/56、34/34，差均0 | 未触发 |
| 成功attempts中位 \(>1\) | 1 | 未触发 |
| 形状复核失败率 \(>5\%\) | 0/208 | 未触发 |
| 整批墙钟 \(>3600\,\mathrm{s}\) | 运行器2031.349秒；守护2033.632秒 | 未触发 |

完整200唯一结果、异常0；192合同一次、8合同两次。8个普通拒绝为boundary_crossing3、reference/speed3、start_route2；全部200成功骨架使用弯曲LP，直线回退不设止损。原摘要/记录/分档见[part5_lazy](part5_lazy/)。

每合同墙钟（线性分位数）：均值52.324秒，中位18.957、p90 43.094、p95 61.225、最大1971.257；原运行器秩算法摘要原样保留。长尾o07_d2/d4为1971.257/1829.662秒，o17_d1/d4为901.371/937.999秒，均一次成功，未删除或换键。

261个probe走67277格，平均257.766格/probe、中位1；按200合同分摊全部attempt为336.385格/合同；29个完整判空；232个非空probe首个非空位置平均31.315、中位1（包括二分各次通过probe）。退让6合同：o07_d2/d4、o17_d1/d4、o36_d2/d4，含5次横排转梯形及1次原梯形缩步长。loose映射不计退让。

实现队形column46、abreast102、echelon52；teardrop80、u68、oblique52，正/负侧114/86。条件分层、A/R与各队形人数L分布见[skeleton_evidence](part5_lazy/skeleton_evidence_r1.json)。969成员完整折线以精确oracle计算protected最小SDF为10.0275129米，满足规划10米；合同禁用字段/路径扫描0处。

首次逐格存在性查询的粗筛计数：认证434112候选、直接拒绝38837次、覆盖点80998995、记录约束弦731084955、进入精确弦3508434。统计不含内存命中及组合随机抽样调用，不将其冒充所有生产调用的全覆盖统计。资源采样私有提交内存最高76.69GB（包含可换出页），物理可用曾为0.49GB；默认24未改。完整成本样本在[skeleton_resource_samples](part5_lazy/skeleton_resource_samples.jsonl)。

## 6. 快批20与保存后复核

完整20/20保留成功，运行器105.569秒；成功post中位0、优化累计耗时中位6.729397秒，无止损或P0。o07_d1前两次optimize_feint普通拒绝、第三次成功，其余19合同一次成功。原记录、选择与摘要见[part6](part6/)。

独立从NPY重建99成员，冻结段/有效性核验、两层进入退出1/1、序列化帧时刻与protected最深距离均通过；最小实测间距3.1086434481米、最小protected SDF14.4384501米。实测判据保持原冻结门槛，未改为规划10米。合同字段/路径扫描0处，见[磁盘复核](part6/disk_validation.json)。

## 7. 全量、五键复跑与四意图诊断

运行根`run/out/full_lazy_r1`。固定主200＋多样性100、24进程均完整，主200/200、多样性100/100成功；errors/incomplete/unsent/P0均[]。运行器墙钟1971.110729秒、派发1968.434044秒、仅几何预热2.645181秒，守护1973.094668秒；原7200秒合作预算不变。[原摘要](part7/full_summary.json)、[主记录](part7/full_records.json)、[多样性元数据](part7/diversity_records_metadata.json)、[原始身份索引](part7/source_index.json)。

| 主批/多样性止损 | 实测 | 结论 |
|---|---|---|
| 主成功率 \(<80\%\) | 200/200，无排除 | 未触发 |
| 任一人数/设施数/初速档落后 \(>20\) 个百分点 | 全部100%，档差均0 | 未触发 |
| 成功主合同post失败中位 \(>0\) | 0 | 未触发 |
| 归一化作业段Fréchet合并中位 \(<1\) | after34.3787713084，450有效对 | 未触发 |

人数档依次110/110、56/56、34/34；设施数1/2/3档85/85、85/85、30/30；初速[4,6)、[6,8)、[8,10]档67/67、61/61、72/72。成功attempts中位1、主批骨架普通失败10次均仅诊断。全量倾向→实现：column→column46、echelon→echelon47、loose→abreast43、abreast→abreast59、loose→echelon2、abreast→echelon3；全部200使用弯曲LP，未新增回退止损。

多样性10族各尝试10、成功10、可比较10，45有效种子对，共450；无NA。before合并中位34.3688904461，after34.3787713084。均用各自完整alert进入→退出参考曲线精确裁切、5米重采样、原族横向间距除一次、所有有效对合并取中位，不以退让步长归一。不把端点重合当作零长度或把族中位数再取中位。各族身份/计数/归一尺度与原始米值见full_summary及feint_report。

**保存后独立检查：** 从NPY重新构建主200＋多样性100共1429成员，原validity/segment全通过、两层进入退出1/1、帧时刻和protected最深SDF与序列化相同；合同字段/路径扫描0、P0[]、缺失[]。最小实测间距3.0490071222米（o37_d1），最小protected SDF14.4384500558米，见[全300复核](part7/disk_validation.json)。快批最小间距在第6节已据原逐合同JSON纠正：早先PowerShell摘要聚合曾报3.1223064米、全量曾报3.170666米；Python对全部非None数值取min分别为3.1086434481/3.0490071222米。原逐合同判断和轨迹始终正确，未重跑或改数据，见[聚合证据](part7/validation_metrics.json)。

**正式五键复跑：** 预登记o01_d0..d4，1进程，对主批24进程，5/5成功；文件数14、34、9、34、14，共105，递归集合与原始bytes全同、排除[]。守护55.499秒，见[reproduction](part7/rerun_reproduction.json)、[键表](part7/full_rerun_keys.json)、[守护](part7/rerun_watchdog.json)。没有清除缓存或按结果换键。原ArtifactPreset三项随后完整通过。

**四意图配对：** 200键outer join，common_field_diff_rows=[]、missing_field_rows=[]；按监视/过境/突入/佯动顺序，全链路SSSS197、FSSS2、SSFS1；骨架SSSS199、SSFS1。监视两次旧失败、突入o34_d3旧证书均保留，不删除该行或改变佯动分母。逐键成功/失败/attempts/倾向/实现和三种分档见[配对CSV](part7/four_intent_contracts.csv)、[分析JSON](part7/feint_report.json)。

**失败子类两表：** 第一表分母为全部48失败attempt，其中optimize_feint34；nominal_dwell32、boundary_crossing3。同attempt同子类去重，子类不互斥，35不必等于34。第二表分母36个有失败合同，取时间顺序第一个失败：optimize_feint|nominal_dwell22、optimize4、skeleton:boundary_crossing3、skeleton:reference/speed3、optimize_feint|boundary_crossing3、skeleton:start_route2；合计37可大于36。见[全部失败attempt子类](part7/all_failed_attempt_subreasons.csv)、[每合同时间首败](part7/first_failed_attempt_per_contract.csv)，不是每合同第一次优化失败。

**名义阶段时长：** 969成员中位数为release→alert入658.374814秒、alert入→出129.224774秒、alert出→移动end103.884952秒、travel890.368484秒。逐成员三段闭合残差最大4.55e-13秒；各段中位数不要求加成travel中位数。采用同一名义s→t插值；共同预保持20秒、末端保持2秒与成员release_delay另列，delay中位62.7、最大1685.9秒，均为业务时间。分位数与阶段速度完整保留在feint_report。

**形变与突入同成员观测：** [member_observables_paired.csv](part7/member_observables_paired.csv)有200合同/969成员，与V8-17同cid/member配对957个成功成员。突入使用原sigma与terminal_deceleration的名义/优化/实测起点、层和protected SDF，失败行保留None，不改突入算法、不增加起点分离阈值。佯动保存真实支撑开始点alert SDF、形变至核心名义时长、横/纵开始时刻及相对release时刻。771个真实形变成员开始点alert SDF最大-10.057764米（全部≤-10），形变至核心最小3.532747/中位28.950134秒，横向晚于纵向的时差中位7.155069秒；完整分布见[observables_summary](part7/observables_summary.json)。

**需要审查的原字段口径：** \(L=0\)的53合同/198成员原phase_metrics仍保存形式横/纵开始时刻，且106成员no_deformation=False。独立CSV按无真实形变将这类观测记为None（空单元），另存raw时刻/flag用于追溯；原合同和已通过复跑的bytes未改写。原analyzer的deformation统计属于未归一化raw口径，不能直接当真实形变总体。此项为诊断字段口径问题，未发现保留轨迹的物理/语义违规，不计三项P0；是否统一生产输出列入第8节审查事项。

## 8. 冻结、提交与审查事项

最终快照对part1首快照：all_frozen_ok=true，160个输入、22个v07目录、24个细粒度函数不变量全同；245模块中21处允许变化，无冻结模块变化、旧预置变化[]。本轮相对4da4182的预置三文件与FT/MT散列保持；生产源8e22f06后没有变化。旧监视/过境/突入基线8551/8651/8589个文件身份均同，两个冻结工作树HEAD及clean状态同。证据[最终快照](part8/snapshot_end_lazy_r1.json)、[对照](part8/snapshot_compare_end_lazy_r1.json)。

整个monitoring_turn.py首尾SHA256：`409fb67bf00de152f33f874f32c36965f7fb00c73dd839ab38c15897c955e9a3`。FT为`b5372389b94a822e94f12913258694a8f1b112b78d445a1e2c6bec739f2d3989`。29族155存在性文件SHA/大小/mtime全部相同、差异0；预置三文件及owner散列同，见[最终保留清单](part8/preservation_final.json)。owner为`d9c0022bf84636eb61d0b27a2f65bf3f6c490c738046087036f22b14cdf65bd0`，仍是工作区唯一未提交项，不删除、不提交。

| 本轮提交 | 内容与证据等级 |
|---|---|
| 8e22f064899cd8fd832f90558da282fb319eed05 | 按需实现、新测试，之后生产源码未变 |
| dd5a14a7569af7e04d56783d47c516938b027ba8 | 最新三意图字节门禁、三键smoke |
| 493f648292d8a8b5c1a1469cdd99b34cdb5d2842 | 两边缘集合诊断、测试与快速检查收口 |
| 784b62f697d867bc02a4d0fdff2bfeca65e3d4db | 200骨架完整检查点 |
| 59606dcd088803c6d8687558706de396652eb63a | 20快批及保存后独立核验 |
| 97fc87197ddee0673539e54ef0bc873bae2e780f | 第7部分全量/多样性/五键/配对证据 |
| 本报告所在的最终文档提交 | 第8部分最终快照、裁定身份、最终报告与历史归档；完整SHA及ls-remote结果写在交付回执 |

各部分均单独提交，只push `HEAD:refs/heads/review/v08/V8-18-feint`，每次ls-remote核对一致；未push main、未强推、未合并dev。最终回执为外部 `run/diagnostics/delivery_end_lazy_r1.json`，保存最终完整SHA、远端核对和工作区状态，避免报告内自引用其自身提交SHA。原始NPY、轨迹、完整曲线和cache留在run；Git只存报告、原记录元数据、小型诊断与身份索引。执行方历史见[REPORT_HISTORY_20261108](REPORT_HISTORY_20261108.md)，其中过期全格策略/成本限额均为历史，当前以本文为准。

### 原指令第12节疑点状态

| 项 | 当前状态及影响 |
|---|---|
| 12.1 负下界误拒 | 已由附录裁定1采用screened双向确定/中间精确；负下界反例、两处授权断言、三路差异0保留；本次不改 |
| 12.2 边缘/联合均匀冲突 | 已由附录裁定2接受格、非空组合、联合记录协议；按需首个非空在非空格均匀；不宣称A或种类边缘均匀 |
| 12.3 无监视局部W | 附录裁定3(a)接受几何必要上界；无经验W；SceneGate替代证据已裁定，不是待批事项 |
| 12.4 纵向支撑提前 | 附录裁定4接受真实横/纵支撑之并，MT只读；本次仍认证实际支撑；\(L=0\)原观测字段另列下方 |
| 12.5 离散撤离首站点 | 保留5米站点原语义，不改连续最短撤离 |
| 12.6 规划余量/冻结进入次数 | 规划protected10米，实测仍用冻结门槛；名义和保留前/保存后双层1/1另验；不混用 |
| 12.7 共享分支与白名单 | feint专用走廊/时序/报告/序列化接入，旧函数细粒度冻结；本次仅共享feint几何预热分支，已补第二轮门禁 |
| 12.8 旧配置残值 | 唯一20attempts；旧1800/quick10均不启用，24/1默认不变；7200合作预算保持 |

### 需要审查方判断的事项

1. **\(L=0\)生产观测字段是否统一为None。** 53合同/198成员存在形式时刻，106成员no_deformation=False。独立配对CSV已按真实形变口径规范化并保留raw；原生产合同、轨迹和复跑证据未改写。定位`v08/runner/feint_report.py::deformation_observables`。这一诊断口径问题尚未得到裁定，不将整个实现宣称无遗留问题。
2. **⑥之前提速与资源目标。** 本轮全部止损通过，但大编组骨架最大1971秒、私有提交内存采样最高76.69GB/可用物理曾0.49GB。最新裁定保留A级整行剪枝为后续提速方向，本轮未改认证或默认进程数；后续目标由审查方决定。
3. **自加桩测试序数歧义的文字确认。** 采用明确的4空→1非空、两次调用，非空下标1、5；与原文“第2、5个”序数表述有歧义，未影响真实门禁，也未改预置断言。
4. **粗筛计数覆盖范围。** 当前存在性遥测仅计首次判空，不含memo命中/组合随机抽样。若后续需要全调用成本分解，需另定诊断范围；已裁定的1021860候选等价证据仍有效。

本次没有代替审查方作通过裁定。所有上述数字为执行方记录；正式五键属于执行方已复跑，审查方独立复跑仍未执行。
