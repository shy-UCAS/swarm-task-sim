# M3 阶段报告

## M3b 实施记录（进行中，未宣称检查点 2 通过）

M3a 静态审查已通过。用户重新导出的设计文件已原样单独提交为 `136bd9bcd8b56a4b9c99e341b51c72dac97cabcc`，SHA256 为 `df54ba872ddb0cccb8fc97e2e9ae59f126109126452b088c1debfe95822a6c09`；该提交不属于 C9–C14。

**用户批准的几何变更。** 监视整环、弧段均使用整组成员两两不同、相邻相差 family 间距的等距巡视线。各分股按 split_index 占连续半径块，股内由参考进场／巡视横向车道的转弯内外关系保持成员与圈号连续；整环同向，弧段原地折返且不换线。最内线在按整组宽度收窄的既定允许区间内均匀抽取，空区间以 `patrol_band_too_narrow` 拒绝。替代旧共线／50 m 切入点间隔及复述中的跨股复用半径；不改 M1、M2 或 fastsim。新自由空间直接调用既有 `exclusion_policy`。

C9 只读诊断完成：包括脚本准备在内 114.25 s，6/6 个已登记失败机次哈希一致，仿真 0 次。六次均存在持续 1975.9–2533.6 s 的低速停滞，邻近扫描航点（距离约 0.684 m，邻接转角约 68.74–71.17°），并非缺少撤离终点。停滞事实已确认；跟踪器游标未保存，唯一根因仍为 `unresolved`，不能宣称精确定位内部卡死节点。新扫描连接采用切线圆弧平滑并保留条带／离场证据，不新增最大转角门槛、不改冻结控制器。证据：[m3_c9_legacy_stall_diagnosis.json](../evidence/m3/m3_c9_legacy_stall_diagnosis.json)。

后续门禁：完整 Q2 在最终代码上运行 20 个骨架，共用 900 s 窗口；任一格或任一固定 Q3 骨架无候选即停。完整 Q3 在脚本、几何、接线、配置已提交后开始，先运行固定多向侦察／监视（≤1800 s），均严格配对后再运行其余 8 个；两步共 ≤5400 s、8 进程。运行期间不改几何；修正后须重跑完整 Q2 与受影响 Q3。完成前不推送检查点 2、不启动 M4。

### M3b 条款与已完成短验证

| 条款 | 函数／运行入口 | 验证 |
|---|---|---|
| C9 | `diagnose_v07_m3_legacy_stall`、`operation_shapes.search_shape/nominal_coverage` | 六个旧机次只读；精确扇区、名义覆盖、整路线合规 |
| C10 | `observation_shape`、`route_operation` | 拼接去重后真实中间驻留索引，原有驻留／终止参数 |
| C11 | `patrol_shape`、`parallel_paths`、`m3b_diagnostics.round_evidence` | 整环／弧段固定成员车道；多边形真实等距；不足 150° 与收窄空区间拒绝；全程 M2 叠加复用及阶段定位 |
| C12 | `terminal_shapes.feint_shape` | 连续半圆转向，无计划驻留；精确深入参数与单次警戒区访问 |
| C13 | `terminal_shapes.intrusion_shape` | 终点有符号距离、family 横向间距、混合组现有装配合同 |
| C14 | `run_v07_m3b_checks`、`run_v07_m3b_trial`、`summarize_v07_m3b` | 20／10 输入登记、47 项短测试、双阶段止损及只读诊断；完整 Q2/Q3 尚待执行 |

`python -B scripts/run_v07_m3b_checks.py unit`：47/47 通过，跳过 0；39 个冻结文件哈希均与 M3a 登记一致。M3b 未新增 legacy 后端选择修改；M3a 已列出的两项显式 legacy 回归保留。G11 的不支持方式用例改为真正未知的 `unsupported_method`，继续验证显式拒绝与 P0 传播，不再把已实现的监视当成未知方式。六种默认请求均在旧 Context／draw_role 被禁止调用时获得合格候选。

M3b 的“不要求 primary 非零”仍专指 `make_views(records)` 返回的 `counts.primary`，即 `views.primary` 中的 episode 条目数；10 个固定骨架的严格成功配对门槛不变。

### M3b 异常与未决（实施期间）

- 新侵入模块首次测试误用了配置字段名 `endpoint_signed_distance_m`，已改为实际 `endpoint_distance_m`，未改参数值。
- 新路由分派首次要求旧形态字典含 `kind`，导致原 G7 测试报错；已从 TaskSpec 提供缺省方式，原测试预期未改。
- 监视测试发现偏移车道内侧转角可能消耗参考对齐段；在连接阶段按既有 100 m 要求检查实际车道并使用原局部预算重试，未增加余量或门槛。
- 监视全程叠加、各角色冻结 fastsim 跟踪及缺失分支补试仍须等待 Q2 门禁后的实际 Q3，不能以纯几何测试声称已通过。
- 阶段定位采用实际位置到计划航段的精确投影，保留并列最近航段与歧义；不冒称已保存跟踪器内部状态。巡视线到达时刻用预警事件之后首次接近巡视起点的局部距离极小点估计，并同时给出偏离距离。

以下为保留的检查点 1 报告。

状态：M3a C1–C8 已完成，38/38 项模块／短回归通过，跳过 0；Q2 四个固定骨架全部通过。Q3 两个固定过境骨架各产生一个严格成功配对，共 4 条联合轨迹，实测时序、质量与独立审计全部通过。Q2 含修复累计约 323.19 s，Q3 613.46 s，均未超上限。检查点 1 就绪；停止在 M3a，等待静态审查，不启动 M3b、M4 或弱斥力。

基线为 `v07-scene@7aab263b201aa016c93d966e5b68bb1290c4f630`，Python 环境为项目 Conda `llm`（Python 3.12.3），使用 PowerShell 7。固定输入、配置与冻结源码哈希见 [m3_inputs.json](../evidence/m3/m3_inputs.json)；批准口径及差异引用见 [00_restatement.md](00_restatement.md)。Q3 启动提交为完整 SHA `f39c32c45fa42404c898fdf27ec2f4c64a9420b0`，当时未提交的运行脚本和几何源码哈希另存 attempt 的 `registration.json`，不能仅用该提交号代替运行源码版本。

“不要求 primary 非零”指 `make_views(records)` 返回的 `counts.primary`（即 `views.primary` 的 episode 条目数）可以为 0，因为仅含过境的固定小试未形成同一 family 内五意图齐全的均衡配对；两个固定骨架的严格配对要求不变。

## 条款与验证

| 条款 | 实现／证据 | 状态 |
|---|---|---|
| C1 | `geometry_config.load_geometry`、`run_v07_m3_checks.register_inputs`；`m3_inputs.json` | 完成，来源六份资产哈希一致 |
| C2 | `spec.build_spec/validate_spec/proposal_seed`；G1 | 完成，规格独立、身份／参数／种子校验 |
| C3 | `free_space/work_region/offset_curve/chord_intervals`；G3、G5、G6 | 完成，圆／凸多边形、空域与精确原始实体查询 |
| C4 | `assign.assign`；G2 | 完成，既有分股内物理排序、列置换不变 |
| C5 | `route.route_group/offset_lane/clean_joints`；G7、G10 | 完成，共享连接、短圆弧离散及真实元数据 |
| C6 | `checks.plan_checks/warning_visits`；G4–G6 | 完成，逐点／逐段见证、单次访问与对齐检查 |
| C7 | `shapes.draw_shape`、`adapter.build_unified_pool`、`build_group_pool`；G8、G11 | 完成，默认 unified、显式 legacy、无回退 |
| C8 | `run_v07_m3_trial`、`summarize_v07_m3`；G12、Q2/Q3 | 38 项测试、Q2 4/4、Q3 严格配对 2/2 通过 |
| C9–C14 | M3b | 未授权、未执行 |

## 测试与固定输入结果

`conda run -n llm --no-capture-output python -B scripts/run_v07_m3_checks.py --unit`：最终 38/38 通过，跳过 0，耗时 32.77 s；包含 M3 的 18 项测试、M1/M2 短测试和两项旧池回归。G1–G7、G10 的过境适用部分、G8 直弦／单折点／同向／多向、G11–G12 均覆盖；G9 和其他角色分支留待 M3b。证据：[m3a_checks.json](../evidence/m3/m3a_checks.json)，前次 37 项结果保留为 `m3a_checks_before_corridor_fix.json`。新几何经冻结 fastsim 的集成证据复用下述 Q3，不以名义轨迹替代实测。

仅修改以下两项原测试的后端选择，没有删除、跳过或改变断言：

- `tests/test_v07_s2_search_revision.py::SearchEvidenceTests.test_empty_first_group_does_not_censor_other_group_budgets`：传 `backend='legacy'`，仍验证三组各 200 提案。
- `tests/test_v07_s2_revision_continuous.py::ContinuousRevisionTests.test_every_registered_candidate_is_counted_without_calibration`：正常与不足预算调用均传 `backend='legacy'`，仍验证 200 提案、拒绝统计及小于 200 的预算错误。

Q2 入口：`python -B scripts/run_v07_m3_trial.py q2`。首轮 128.93 s，四个骨架均执行完，但 `4d13…ext_005` 没有合格组合；没有进入 Q3。定位并修复短圆弧实现错误后，使用 `q2 --q2-origin <首轮 attempt>` 重跑，继续使用首轮启动的同一个 900 s 窗口。第二轮 113.10 s，四个均通过；包括修复在内累计约 323.19 s。每轮总计 1200 个组提案，两轮合计 2400；每次运行仍严格保持每组 200 提案，未增加单轮预算或改变抽样分布。

| 固定 skeleton_id | Q2 | 提案数 | 合格组合数 | 规划耗时 s | 多向计划最大夹角 ° | 实测最小间距 |
|---|---|---:|---:|---:|---:|---|
| `family_s12_5024cb2ccea653ae_ext_000_regular` | PASS | 400 | 455 | 112.634 | 不适用（同向） | 未测（纯规划） |
| `family_s12_4d13d93f9171c446_ext_000_regular` | PASS | 200 | 46 | 14.930 | 不适用（同向） | 未测（纯规划） |
| `family_s12_f2adfbfae12fbbad_ext_000_regular` | PASS | 200 | 21 | 45.451 | 110.502457 | 未测（纯规划） |
| `family_s12_4d13d93f9171c446_ext_005_regular` | PASS | 400 | 1000 | 36.506 | 132.506779 | 未测（纯规划） |

合格组合数为有限组合及同向路程选择后的数量。角度取选中方案各组既有分股平均进场方向的最大成对夹角，再取骨架内最大值；仅记录，不作成功门禁。各组具体值及逐骨架诊断见 [m3a_q2.json](../evidence/m3/m3a_q2.json)。首轮拒绝分布和各组最接近通过提案的完整检查保留在 [m3a_q2_before_arc_fix.json](../evidence/m3/m3a_q2_before_arc_fix.json)，完整逐提案记录在对应外部 attempt 的 `proposals.jsonl`。

Q2 首轮 attempt：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_m3a_q2_20261016T053420703012Z`；修复后 attempt：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_m3a_q2_20261016T053750791416Z`。均只规划，没有单飞／联合仿真。

Q3 入口：`conda run -n llm --no-capture-output python -B scripts/run_v07_m3_trial.py q3`。仅运行登记中的两个骨架，使用两个工作进程（未超过 8）；每骨架实际 1 轮，合计 20 次单飞、4 次联合执行。每骨架最多 5 轮、每版 20 次时刻抽样的冻结预算不变。实际墙钟 613.457 s，低于 1800 s。输出为 `F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_m3a_q3_20261016T054018076747Z`；大体量真值、标签及单飞数据仅保留在该目录，未提交 Git。

| 固定 skeleton_id | 结果／实际轮数／拒绝原因 | 提案数 | 规划耗时 s | 单飞数 | 多向实测最大夹角 ° | 同步／递次实测最小间距 m |
|---|---|---:|---:|---:|---:|---|
| `family_s12_5024cb2ccea653ae_ext_000_regular` | 严格配对 PASS；1 轮；无轮次拒绝 | 400 | 126.128 | 11 | 不适用（同向） | 6.381581 / 15.636662 |
| `family_s12_f2adfbfae12fbbad_ext_000_regular` | 严格配对 PASS；1 轮；无轮次拒绝 | 200 | 45.971 | 9 | 110.504873 | 4.008570 / 3.626602 |

规划耗时包括组候选生成和组合搜索，不等于整个骨架的预演／执行耗时。航向差、间距、耗时、尝试提案数均作为诊断记录，未增加门禁。逐轮与逐 episode 结果见 [m3a_trial.json](../evidence/m3/m3a_trial.json)，独立复核见 [m3a_acceptance.json](../evidence/m3/m3a_acceptance.json)。

只读核验入口：`conda run -n llm --no-capture-output python -B scripts/summarize_v07_m3.py`。对实测 `core_event.t_s` 用十进制数独立重分批；6/6 个“任务组 × 时刻版”分类一致，3/3 个递次组的批次成员与顺序一致。同步最大跨度为 4.7 s，递次各批最大跨度为 1.8 s，最小批间空隙为 42.3 s。4/4 条联合轨迹全部组完成、执行状态 `completed`、`quality_valid=true`、独立审计 `PASS`；复用原 `_paired()` 得到 2/2 严格配对。40 个“成员 × episode”的预演状态不一致数与条件差异数均为 0。

原 `make_views()` 计数为 `primary=0 / extended=4 / aborted=0 / failed=0 / pending=0`。两个 family 均只有过境配对，其余意图计数为 0，因此各 family 的 `pairs_per_intent=0`；这是既有均衡规则的实际结果，没有更改配对或视图资格。

M2 单飞叠加的最小间距预测误差按“预测减实测”记录如下。结束前表示机对双方均未超过各自平移后的单飞末帧，结束后表示至少一方超过；位置误差是另一项诊断，不能混称最小间距误差。

| 骨架／时刻版 | 单飞结束前最小间距误差 m | 结束后最小间距误差 m | 全程位置误差最大值 m |
|---|---:|---:|---:|
| `5024…ext_000` 同步 | -0.0000000013 | -0.00009992 | 0.537365 |
| `5024…ext_000` 递次 | -0.0000000007 | -0.00033723 | 0.537365 |
| `f2ad…ext_000` 同步 | 0.00588137 | -0.00000026 | 0.982351 |
| `f2ad…ext_000` 递次 | -0.0000000281 | 0.00026300 | 0.985942 |

四条轨迹的预测／实测间距质量分类一致。过境风格诊断共 40 个成员机次，驻留检出 0/40、重访检出 0/40、作业折返总数 0；无异常样本需归因。实际最小间距范围为 3.626602–15.636662 m（4 条质量有效联合轨迹），未将这些诊断另设为成功门槛。

提出／接受几何参数见 [m3a_geometry_parameters.json](../evidence/m3/m3a_geometry_parameters.json)，包括局部形态抽样、整航线合格提案的方向／弦分位／折点分布，以及选中方案连接参数。局部形态抽样次数与每组 200 个完整提案分别计数；接受后的条件分布不宣称无偏。完整提案与拒绝证据仍在 Q2 attempt 的候选池和 journal 中。

## 依赖与冻结检查

新生产调用为 `build_group_pool → build_unified_pool → spec/free_space/shapes/assign/route/checks → assemble_skeleton/precheck`，再复用原有独立组组合、`choose_eligible`、episode 装配、M2 预演／时刻／执行与 M1 审计。新路径不调用旧 `Context/draw_role` 或旧角色规划器；仅复用 `formation_corridors.start_line` 这个不依赖角色的地图边界函数。偏移车道实现放在新模块中，以 1 m 弦高误差替换旧固定角步离散，未继承旧名义恒速间距门禁。实际间距仍由冻结 M2 叠加和 M1 实测判定。

39 份冻结源码／配置的哈希与 C1 登记一致。角色判据、时刻种子与抽样、公共条件／分股、列置换、输入白名单、配对／视图规则、fastsim 配置及执行停止语义未修改。G11 检查默认调用、显式 legacy、未支持角色报错与 P0 原样传播；G2 检查列置换下每个物理 ID 的路线一致。

过境的直弦／单折点及同向／多向均已有静态和实际执行覆盖：Q3 同向骨架的第 1 组为约 29.008258° 单折点，第 2 组为直弦；多向骨架为直弦。共享连接、对齐、撤离均经冻结 fastsim 执行。其他五种执行方式（区域搜索、抵近观察、监视、佯动、突击）、驻留、监视整环／弧段及中止正式运行未执行，不能据此声称完整 M3 关闭。

单成员走廊修正发生在 Q3 启动后。最终源码下定点重放四个已接受方案的六个组提案，路线点数组 6/6 完全一致、整航线检查 6/6 通过；两个 Q3 的 `geometry_00/skeleton.json` 与 Q2 相应选中骨架 SHA256 一致。证据：[m3a_corridor_recheck.json](../evidence/m3/m3a_corridor_recheck.json)，命令为 `conda run -n llm --no-capture-output python -B scripts/dev/check_v07_m3_singleton_corridor.py`。该证据把最终实现与已实飞路线连接起来；未重跑全候选池或仿真，Q2 全池拒绝／分布统计仍明确属于修正前的原 attempt，不能当作最终源码下重生成的全池统计。

## 异常与未决

- 输入登记脚本初次将 `multi_labels.py` 误写在 `task_v07/`，已修正为 `task_v07/expansion/` 并重新登记；没有运行仿真或改变输入。
- C3 单元测试暴露 NumPy 当前版本不接受二维 `cross`，改用等价二维行列式，测试预期不变。
- C6 新检查发现 C5 参考走廊末段未包含实际过境方向；补齐参考入口直线，并修正恰在边界处开始下一航段时的入场长度计算。首次 C6 提交先于测试失败结果的核对，随后以独立 C6 修复提交纠正；13 项模块测试通过后才继续。
- Q2 首轮定位到连接车道短圆弧端点间距为 0.554 m、0.427 m 等，违反 ≥1 m 航点合同。仅对此类连接圆弧使用切线交点近似，并检查相对圆弧误差仍 ≤1 m；保留真实转角，不删除作业形态折点。未改余量、判据、抽样概率或给定测试预期；修复后四骨架在原止损窗口内全部通过。
- 后续复核发现半宽为 0 的参考走廊分支漏用了既定 2 m 构造余量（应为 37 m，而非普通点路径的 35 m）。增加显式参考走廊标志及边界单测，配置数值未变；既有选中方案相关单成员实际障碍净空最低为 99.507766 m，定点重放证明路线完全不变，详见上节证据及适用边界。
- 报告工具最初用只允许新建文件的 `save_json` 覆写已有测试摘要，导致一次 38 项测试均通过后，报告写入仍以 `FileExistsError` 退出。改为原子替换，保留前次摘要，完整重跑 38 项后退出码为 0；只读汇总重跑也成功。未因此补跑 Q2/Q3。
- 提交检查发现自编 JSON 写入工具在 Windows 下隐式写成 CRLF，触发仓库空白检查；改为显式 LF，规范化本轮仓内证据的换行并更新摘要哈希，数值与外部原始运行证据不变。
- 本轮开始时设计文档已有未提交修改（补入驻留首尾距离及检查点推送口径），内容与已批准决定一致；保留该用户修改，未纳入实现提交。
- Q2 门禁采用用户补充的四骨架全部通过，预算 900 s；Q3 为两个固定骨架严格成功配对，预算 1800 s。失败时保留原始证据，不改判据、余量或分布。

## 提交与停止位置

本检查点范围为基线 `7aab263b201aa016c93d966e5b68bb1290c4f630` 之后、从 `8e7b682` 开始到本报告所属的 `M3-C8` 检查点提交，最终完整 SHA 随推送回执交付。各条款独立提交，C5/C6 的实现修正另有以对应条款号开头的提交；范围包括独立几何配置及新模块、最小后端接线、两项旧测试显式选择 legacy、M3 测试／运行／报告工具和小体量证据。未纳入本轮开始前已有的设计文档修改。

本阶段没有未满足的验收项；全池统计版本限制已明确记录。推送检查点 1 至 `v07-scene` 后停止，等待静态审查。
