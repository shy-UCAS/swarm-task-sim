# M2-03 设计冻结修订：连续跟踪、共同事件与旧产物兼容

状态：**AWAITING_REVIEW**。2026-10-12，Codex 直接修复 attempt_03。
本文是 M2 后续实现契约，生产代码仍是 M1。本轮没有调用飞行引擎或执行 M2 任务；不能把这句话扩展到 attempt_01 曾运行的 55 项 M1/语义回归。

依据：[阶段指南](../fast_dynamics_engine_m2_staged_guide.md)、[本阶段指令](M2-03_instruction.md)、[第二轮复审](M2-03_review_02.md)。旧错误设计、回执及原始证据均保留。本修订统一替换互相冲突的方案；新增字段、状态和算法均是设计，尚未成为可用能力。

## 0. 身份、范围与本轮决定

- HEAD 为 `a46f034cbad21dfee670c0a76c2f0939c0572055`；本轮不提交、不改业务代码/CI/冻结输入、不进入 M2-04。
- 12 个开发输入仍由 `coverage_matrix.json` 绑定；当前留出入口仍为 `evaluation_split_current.json`，旧划分不恢复，不读取校准/盲测输入或结果。
- 原文“折线投影 + 圆弧参考 + 历史最大进度”替换为**统一实际弧长的直线/五次 Bézier 原语**，物理路线证据与控制预览分开。这是设计修正，未改任务规划器或原始航点。
- 当前 12 格全部为每阶段恒定规划高度；**EN 有序路线进度与 U 服务条件分开**。U 始终是真实积分状态；原终点到达仍检查完整 3D 距离和速度。一般变高度路线不在本设计支持域，不能默默投成二维。
- 七种阶段状态与一个跟踪子状态；个人完成不依赖全机屏障。候选步仅提交同一多项式的前缀，确认依赖 epoch。
- 公共配置保留现有七组，拟新增一个 reference 组、七个字段。测试故障只由明确绑定的外部 harness 施加，不增加任意 inject_* 公共开关。
- 版本兼容按实际 M1 身份注册；历史中间坏样本继续拒绝，不能批量修写归档。
- 完整静态证据位于仓库外 `SwarmData/fast_dynamics/m2/M2-03/attempt_03_codex_repair/`。本轮静态时长、合成谓词结果不代表闭环质量、期限或真实任务通过。




## 1. A：从已有开发任务提取契约

### 1.1 历史提取方式与本轮复核

只使用 `coverage_matrix.json` 绑定的 12 个 T1/T4 开发 TaskSpec，逐文件核对原字节与来源，然后**静态**调用 `swarm_sim.tasks.compile_task`（`swarm_sim/tasks.py:29-38`，v3 走 `mission_v3.compile_mission_v3`，`swarm_sim/mission_v3.py:241-274`），不运行任何快速飞行引擎。

- 提取脚本：`SwarmData/fast_dynamics/m2/M2-03/attempt_01/extract_contracts.py`
- 原始日志：同目录 `extract_contracts.stdout.log`、`summarize_contracts.stdout.log`、`analyze_geometry.stdout.log`、`probe_profile.stdout.log`
- 旧 profile_probe 及其时间结论已被本轮第2节新模型取代；其原字节仅作为历史失败证据。
- 结构化结果：`static_contracts.json`、`static_contracts_summary.md`、`geometry_facts.json`、`profile_probe.json`

历史静态提取结果、本轮复核：12/12 单元原字节与 `coverage_matrix.json` 登记的 SHA256 一致，且与其 `original_path` 指向的 T1 批次输入逐字节一致；`problems=0`。

### 1.2 编译产物的真实字段与调用路径

| 结构 | 实际字段 | 来源 |
| --- | --- | --- |
| `scene["phases"][i]` | `name`（如 `p01_observe`）、`semantic_phase`、`routes`（`{agent: [{east_m,north_m,up_m}...]}`）、`speed_m_s`、`terminal_hold_s`，可选 `start_delays_s` | `route_planning.py:201-205` |
| `scene["semantic_plan"]["execution_phases"][name]` | `semantic_phase`、`agents[agent]` = `role`、`service_enabled`、`partition_id`、`waypoint_planner_indices`、`start_point`、`terminal_point` | `route_planning.py:196-206` |
| 每机角色取值 | `approach/observe/patrol/transit/return`（非空路线）或 `hold_no_op`（空路线） | `route_planning.py:196`；角色表 `registry.py:43-44` |
| 控制模式 | `control_mode == "semantic_phase_route_v1"` 走 `compile_continuous_mission` | `mission_v3.py:249-251`、`route_planning.py:272-304` |
| 零长/重复点清理 | `clean_route`：与前一点距离 < `ZERO_LENGTH_EPSILON_M=0.05` m 的点被删除并登记索引 | `route_planning.py:19,28-41` |
| 到达要求 | `target_confirmation(scene, phase, agent)` → `tolerance_m`、`dwell_s`（`idle_padding` 为 0）、`role` | `tasks.py:131-139` |
| 名义时序 | `scene["planning"]["nominal_phase_timing"][phase]["per_agent_waypoint_arrival_s"]`（匀速代理，非飞行保证） | `route_planning.py:233-247` |
| 组件版本 | `component_versions()`：planner/validator/facts/templates | `registry.py:52-59` |

编译期已成立的三条硬约束（M2 必须沿用，不得放宽）：

1. 每条清理后航段长度 \( \ge 0.05 \) m，否则 `sample_route` 直接拒绝（`route_planning.py:44-66`）；
2. 每机每阶段航点数 \( \le 100 \)（`route_planning.py:21,39-40`）；
3. 阶段级时间感知净空检查必须通过（`route_planning.py:91-177`、`213-269`），它按**名义匀速**+错峰+驻留评估，不代表实际动力学净空。

### 1.3 路线—角色—阶段映射（三意图四飞法）

| 意图 / 飞法 | 编译阶段 | 服务阶段 | 路线形状（实际编译结果） | 角色集合 |
| --- | --- | --- | --- | --- |
| reconnaissance / equal_strip_lawnmower | `p00_approach` → `p01_observe` →（`return_required` 时）`p02_return` | observe | 每机独占一条等宽条带；lane 中心线往返，lane 间用一条横向连接段（90° 两次） | approach / observe / return |
| reconnaissance / equal_strip_rectangular_spiral | 同上 | observe | 条带内缩后向内矩形环；本批三格 spiral 全部为**单环闭合**（首尾点重合） | approach / observe / return |
| patrol / staggered_same_loop | `p00_approach` → `p01_patrol` →（可选）`p02_return` | patrol | 同一矩形环按 `laps` 圈展开；各机入口弧长错开 \(P/N\)；环首点每圈重复一次 | approach / patrol / return |
| rapid_passage / line_abreast | `p00_approach` → `p01_transit` →（可选）`p02_return` | transit | 每阶段单航段 | approach / transit / return |

- 服务判定（`service_enabled`）只由「该阶段语义 ∈ `intent.service_phases` 且该机路线非空」决定（`route_planning.py:196`、`registry.py:43-44`），**不能假设每阶段所有飞机都是服务机**。
- 返航语义：规划的 `return` 路线终点是**任务规定的空中位置**（通常为起点上方高度），不是降落（`patrol.py:189`、`reconnaissance.py:101-103`）。
- 等待语义：某机在某阶段路线为空时得到 `hold_no_op`，其 `terminal_point` 等于 `start_point`（`route_planning.py:195-197`）；该机**仍需满足该阶段的到达/驻留确认**（`tasks.py:131-139` 只对 `idle_padding` 给 0 驻留，连续模式下不存在该角色）。

### 1.4 12 格真实几何事实（attempt_01 提取，本轮重编译核对）

| 单元 | 阶段数 | 服务阶段 | 单机最大航点 | 最大直角数 | 最短航段 (m) | 闭合环 | 重复点 | 返航 |
| --- | ---: | --- | ---: | ---: | ---: | --- | --- | --- |
| reconnaissance__equal_strip_lawnmower__n2 | 2 | observe | 8 | 6 | 3.711 | 否 | 无 | 无 |
| reconnaissance__equal_strip_lawnmower__n3 | 3 | observe | 6 | 4 | 3.864 | 否 | 无 | 有 |
| reconnaissance__equal_strip_lawnmower__n4 | 3 | observe | 8 | 6 | 3.416 | 否 | 无 | 有 |
| reconnaissance__equal_strip_rectangular_spiral__n2 | 2 | observe | 5 | 3 | 6.475 | 是 | 1（首尾） | 无 |
| reconnaissance__equal_strip_rectangular_spiral__n3 | 2 | observe | 5 | 3 | 7.812 | 是 | 1（首尾） | 无 |
| reconnaissance__equal_strip_rectangular_spiral__n4 | 2 | observe | 5 | 3 | 4.171 | 是 | 1（首尾） | 无 |
| patrol__staggered_same_loop__n2 | 2 | patrol | 16 | 12 | 1.162 | 是（3 圈） | 18 | 无 |
| patrol__staggered_same_loop__n3 | 2 | patrol | 11 | 8 | **0.106** | 是（2 圈） | 7 | 无 |
| patrol__staggered_same_loop__n4 | 3 | patrol | 11 | 8 | 5.295 | 是（2 圈） | 7 | 有 |
| rapid_passage__line_abreast__n2 | 2 | transit | 2 | 0 | 8.148 | 否 | 无 | 无 |
| rapid_passage__line_abreast__n3 | 2 | transit | 2 | 0 | 9.669 | 否 | 无 | 无 |
| rapid_passage__line_abreast__n4 | 3 | transit | 2 | 0 | 9.755 | 否 | 无 | 有 |

由此得到的开发输入边界（后续阶段必须知道的事实）：

1. **12 格里没有任何 180° 折返**；直角、圆角与多圈是常态，折返只能由合成边界用例覆盖。
2. **最短真实航段 0.106 m**（patrol n3 / `uav_01` 入口后第一段），小于 3 m/s 下半个输出周期（0.15 m）；短段处理必须真实存在。
3. **本批 spiral 全部退化为单环闭合**，且 `cross_strip_inset_m=3.5`、`inward_step_m=4.0`，环宽 7.81–51.96 m、环高 4.17–7.81 m，最小维度 \( \le 2 \times 4.0 \) m，属于**窄环**。
4. **patrol 环首点是空间重复点**（每圈重复一次，最多 4 次），必须靠展开进度区分圈次。
5. **12 个编译场景全部没有 `start_delays_s`**：现有 planner 不产生 `phase_start_delays_s`（`route_planning.py:203-205` 支持该钩子，patrol 的错峰目前是**空间入口弧长**错开，见 `patrol.py:157-158,239-242`）。因此「非整步错峰」在 M2 只能作为**受控测试注入**用例，不能声明为真实任务特性。
6. 观察阶段的第一个 planner 航点恒被 `clean_route` 删除（`removed_planner_waypoint_indices` 全部为 `[0]`）：阶段起点与上一阶段终点重合是**设计常态**，不是异常。

---



## 2. 单机连续跟踪：几何、证据与控制分别定义

### 2.1 原始任务与几何构造

本节公式的 d_max、f、tracking tube、τ、k_p、k_d 分别取第4.2节 reference 配置的 corner_cut_max_m、corner_leg_fraction、tracking_tube_m、preview_time_s、position_gain_per_s、velocity_damping；数值均是默认值，不能忽略传入的合法更小/不同值。预览弧长硬帽0.2m与preview_time_s默认0.2s是不同单位；原节点门、175°阈值和折返停止阈值是行为版本常数。

以编译后的每机阶段点列 \(P_0,P_1,\ldots,P_N\) 为原始有序节点；多圈已经展开，不按坐标去重、不循环重置索引。仅编译器的既有 clean_route 可去除相邻近重复点；内部原语构造器遇到真正零长边拒绝，正长度 0.001 m 的合成输入不是零长错误。显式 hold_no_op 没有非零路线，见第 3 节。

在 EN 平面，内点 \(V=P_i\) 的入/出单位向量为 \(u,w\)，邻边长 \(L_-,L_+\)，转向角 \(\Delta\)。同向共线保持直线；\(\Delta\ge175^\circ\) 采用停车折返，禁止构造趋于奇异的圆角。其余内点采用
\[
d=\min(d_{\max},fL_-,fL_+),\qquad d_{\max}=0.25\ \mathrm m,\quad f=0.1.
\]
令 \(E=V-du,\ X=V+dw\)，五次 Bézier 控制点为
\[
(E,\ E+du/3,\ E+2du/3,\ X-2dw/3,\ X-dw/3,\ X).
\]
\(B(t)=\sum_{k=0}^5 {5\choose k}(1-t)^{5-k}t^k C_k,\ t\in[0,1]\)。
连接直线分别在 E/X 截断。所有控制点位于 E/V/X 的凸包内，所以曲线距 V 不超过 d，距原折线也不超过 d；150° 等一般转角同样成立。相邻拐角总切除不超过边长的 20%，很短的正长度直线仍保留。

端点切向分别为 u/w，\(B'(0)=5du/3,\ B'(1)=5dw/3\)，两端 \(B''=0\)，按弧长连接时曲率连续到零。此处不再使用旧圆弧公式，也不把原折线长度当作弯曲原语长度。

每条原语统一用实际弧长
\[
s(t)=\int_0^t\|B'(\xi)\|\,d\xi,\qquad
S_i=\sum_{j<i}\ell_j,\quad \sigma=S_i+s.
\]
直线使用自身欧氏长度，Bézier 使用该积分和单调反解；原节点/原边/lap 身份作为旁表保留。生产实现采用自适应求积/细分，绝对误差目标 \(10^{-9}\) m、相对 \(10^{-9}\)，参数反解必须报告弧长残差与括区间；未收敛时显式数值失败，不用固定阶结果静默通过。这是实现验收目标，不宣称浮点差值就是严格区间证明。

本轮静态模型对真实路线使用 64 阶 Gauss；独立 256 阶核查真实 155 条弯曲原语差值不超过 \(2.22\times10^{-16}\) m。合成 174.9° 的差值为约 \(1.19\times10^{-6}\) m，未过独立诊断的 \(10^{-8}\) m 门槛；该记录保留，不能把 90° 的收敛泛化。上述自适应规格针对这一数值局限，未运行新的生产求积器。

### 2.2 四类量与真实路线资格

每机保存：
1. 当前原语索引 i（只增）、原始节点见证游标 k（只增，带展开圈次）。
2. 当前**实测投影** \(s_m\)，允许因回退减小。
3. 已取得的最大合法证据 \(\sigma_{\rm witnessed}\)，不可由时间积分、期望速度或控制参考增加。
4. 控制预览 \(s_q\)，可以在当前原语内领先，永远不用于授予路线完成。

只在当前原语求 EN 最近点。直线用向量投影；Bézier 枚举 \((B(t)-p_{EN})\cdot B'(t)=0\) 的所有有效根和两端（最高九次），以距离最小选取，并用离上次局部参数最近、再参数较小的确定顺序破同距；不得在全路线/下一圈搜索最近点。
\[
e_\perp=p_{EN}-C_i(s_m),\qquad e_{\perp,\mathrm{norm}}=\|e_\perp\|.
\]
沿向投影超出线段的量不能冒充横向误差。只有当前原语管道 \(e_{\perp,\mathrm{norm}}\le0.5\) m 内的实际位置可增加局部证据；离开后走恢复控制，不以较远航点吸引位置并跳过旧段。管道用于进度证据，实际 EN 跟踪验收仍不放宽既有 1 m 门槛。

对每个原始节点设置 EN 见证门
\[
g_k=\min(0.5,\ 0.2\min(\text{该节点存在的相邻正边长}))\ \mathrm m.
\]
由**已提交的实际 dense 轨迹**与节点圆盘交点取得见证，按 k 顺序、真实根时刻消费；相邻门不重叠，首尾同坐标也必须等待所有中间门。不能由 leg_advanced/route_complete 事件本身证明到过门。参考曲线在顶点邻域内，因为 \(d\le g_k/2\)，无须改变门半径来允许切角。

普通非停车内部原语推进必须有实际见证：在当前原语的出口截面，实际 EN 轨迹沿正切方向越过出口平面且横向距出口不超过管道半径；保存进入该原语后首次合法越面的根，按时间消费。当前原语已向正方向离开但丢失见证时执行恢复，不直接假定已走完。候选同一步可能有多个很短原语，只有实际连续曲线逐个满足相应门/截面、根顺序及当前原语资格时才可在同一时间事务内推进；不按“步长足够大”批量跳段。实现须检测根与切点，不能只读 10 Hz 观测。

原点获取：实际进入阶段的 p/v/a 不覆盖；不在原 P0 的门内时先向该原起点获取控制，满足门后才激活第一个原语。记录真实获取段，不把初始偏移当已完成路线。phase_started瞬间如果实际位置已在P0门内，当场记录仅P0的见证，不等待新圆盘边界根；闭环同坐标末门不能一并取得。正常路线若在中途回退，当前原语实测投影可以回退，控制从实测位置恢复；跨回前一原语时向当前原语起点恢复，不降低展开索引或重复授予旧门。

末原语采用有限终点门捕获，不要求浮点 \(\sigma=L\) 精确相等。只有按序拿齐所有原始节点门、已经到达最后原语、真实位置进入原末门时才授予 route_complete；不再等待渐近投影刚好等于 L。非零闭环起点即使满足终点空间条件，也因中间门尚未取得而不完成。显式 no-op 在 phase_started 后直接具备路线资格，但仍有原目标的 3D 到达、dwell、hold。

route_complete 是路线历史证据；已合法取得后离开终点，保留该资格，但撤销当前到达/确认/保持 epoch，不能通过屏障。旧反例中的“历史累计进度29.95”不等于真实末门见证：若从未到过门而处于 (30,100)，不得完成；若真实到过 (29.95,0) 再飞到 (30,100)，路线资格可保留、当前到达必不成立。

### 2.3 控制请求（提案，尚未证明闭环性能）

正常跟踪只使用当前原语，不跨下一个拐角预瞄。记正切 T、实际沿向 \(v_t=v_{EN}\cdot T(s_m)\)、\(a_t=a_{EN}\cdot T(s_m)\)，采用
\[
\ell=\min\{0.2,\ 0.1\ell_i,\ \max(0.001,\max(0,v_t)\tau+
\tfrac12\max(0,a_t)\tau^2)\},\quad \tau=0.2\ {\rm s},
\]
\[
s_q=\min(\ell_i,\max(0,s_m)+\ell),\quad q=C_i(s_q).
\]
预览只激励控制，静止时的 0.001 m 不写入物理证据。以第 2.4 节参考速度包络 \(v_g(s)\) 定义
\[
v^{raw}_{EN}
=v_g(s_q)T(s_q)+k_p(q-p_{EN})
-k_d\{v_{EN}-v_g(s_m)T(s_m)\}.
\]
\(k_p=1.25\,{\rm s}^{-1}, k_d=0.25\)。只夹限**期望 EN 速度**至 min(当前原语参考上限、任务 phase speed、profile 上限)；不能夹限真实速度、位置或加速度。Bézier 内参考上限为恒定弯道上限，直线为 phase/profile 上限。U 正常参考来自原规划高度的 endpoint_velocity 分量，再经原上下速度能力；本设计不额外给 U 虚假到达资格。外部harness只在正常参考生成之后、VelocityController之前组合请求：R4保持基底原目标/路线控制，按已登记序列覆盖U期望参考并限制EN暂停/恢复；B9仅按其保持偏置规则组合。route_complete分支不会绕过尚在lowering的harness。全部注入结束后完全交还原参考；从未直接操作p/v/a。

控制器仍走 VelocityController.command → AccelerationENU → PointMassJerkPlant，保留真实联合能力约束。

起点/原语恢复有有限获取域：半径取 min(tracking_tube_m,0.2×当前原语正长度)。实际位置进入该起点球门后，即使沿切线的未夹限投影仍略负，也结束恢复并允许受限前向预览；实测投影仍取0且不发额外进度。只有在此域外且落在原语起点之后方才触发该恢复分支，禁止要求负投影必须精确归零。初始P0取得门见证后同样遵守此域，恢复时p/v/a仍真实积分。

恢复、末点捕获、等待/保持使用既有 endpoint_velocity 控制族，目标分别为当前原语入口、原终点或相位进入时保持点；不将实际 p/v/a 投影回参考。特别是实际位置已在普通原语出口前方但未获得合法出口见证时，必须恢复至该原语入口的有限获取域，重新沿该原语运动，不能选择出口/当前最近点作恢复目标而永远等不到正向穿面。恢复回入口后只重新启用当前原语出口检测，已取得的原节点历史见证不删除；不得把回到出口附近直接当新见证。原语出口附近如果直接前瞻到端点，仍由实际截面/节点见证推进，参考端点不算执行完成。

折返 \(\Delta\ge175^\circ\) 是有限捕获出口，明确不要求正向越过停车顶点的出口平面：取得当前原节点门见证且实际EN进入 min(0.25,g_k)m 捕获邻域时进入 executing 内 corner_rest，向原顶点的真实 3D 目标制动；EN 距离不超过 \(\min(0.25,g_k)\) m、速度范数不超过 0.001 m/s、加速度范数不超过 0.01 m/s²，连续 0.05 s 后消费该停车端点并激活反向原语，无须再等正向出口平面交点。原 p/v/a 全部继承，近零阈值是物理停止判据，不是赋值清零。未满足就继续受控等待，受同一 deadline 限制。不用停转事件或采样位置重复来替代速度/加速度证据。

实现顺序伪代码（每机只计算请求；所有机共同积分）：

```text
read common committed snapshot and current epoch
check global deadline first
if phase not started: hold actual entry anchor
elif explicit hold_no_op: route_complete=true; terminal controller
elif not initial_gate_witnessed: acquire original P0
elif route_complete: original 3D terminal controller; Q and terminal_reference_sequence_finished decide confirmation per section 3.1
elif corner_rest: control original corner; continuous stop predicate; consume finite stop exit when true
else:
  project actual EN onto current primitive only
  if passed ordinary exit plane without valid witness or outside configured tube or (behind activated start and outside finite acquisition gate): recovery to current primitive entrance
  else: compute bounded local preview and desired EN/U above
compose registered external harness into final desired references, without editing actual state
candidate dense step computed once for all agents
detect original node gates, primitive exit crossings, stop/arrival predicates
commit only the common prefix; update witnesses from this prefix in time order
new preview/request may use updated witnesses only on the next candidate
```

这给出控制请求，不给出“必然跟踪成功”的保证。闭环响应滞后、非零阶段进入加速度、动态管道误差、真实联合 a/j 和恢复耗时仍必须由 M2-04/05 独立测试；静态参考的物理上界不能替代这些测试。

### 2.4 联合曲率/jerk 与有界参考时间

匀速圆弧必要界 \(\min(\sqrt{ar},(jr^2)^{1/3})\) 只保留为诊断：旧短半径 \(r=0.106227234/2\) 对应约 0.282597 m/s，不再是本 Bézier 轨迹的规定速度。不存在 0.40 m/s 最低速度保证。

对 Bézier 的每个参数小区间，用导数 Bernstein 凸包求：
- 沿入/出向量平分线的正投影下界 \(m\le\|B'\|\)；
- 二、三阶导数范数上界 \(b_2,b_3\)。

若无法认证 \(m>0\)，继续细分或显式数值拒绝，不除以近零。可使用保守界
\[
K=\max b_2/m^2,\qquad
K_s=\max\{b_3/m^3+3b_2^2/m^4\}.
\]
则曲率绝对值 \(|\kappa|\le K\)、\(|d\kappa/ds|\le K_s\)。曲线上恒速，使用
\[
v_b=\min\left(V,\sqrt{\frac{A_{xy}/2}{K}},
\left[\frac{J/2}{K^2+K_s}\right]^{1/3}\right).
\]
法向加速度不超过 \(A_{xy}/2\)，jerk 范数上界 \((K^2+K_s)v_b^3\le J/2\)。曲线上不同时施加满额切向加速。直线参考采用 \(A_t=A_{xy}/4,\ J_t=J/4\) 的对称 S 曲线，进入/离开弯道时切向加速度为零；弯道两端曲率为零，所以加速度连续。jerk 可以有有限跳变，不能有加速度脉冲。参考与实际状态分开，最终实际 3D plant 约束仍是质量验收依据。

直线两速度 \(u,v\) 间，\(\delta=|v-u|\)，
\[
a_p=\min(A_t,\sqrt{J_t\delta}),\quad
t_j=a_p/J_t,\quad t_a=\delta/a_p-t_j,\quad
T=2t_j+t_a,\quad D=(u+v)T/2.
\]
\(\delta=0\) 单独返回零转换时间/距离。每条直线求可行峰值速度，使前后两段转换距离之和不超过实际直线长度，剩余为巡航。前向/后向扫描降低节点速度、弯道两端取同一速度，直到全部转换可行；端点/折返点为零。求解不收敛时失败，不采用未经来源支持的常数减速时间。

这是有限 jerk 的**理想参考**构造；不宣称生产速度控制器必然跟随，也不把参考预算相加当实际状态验收。旧 \(a_n=3,a_t=1.2\) 的反例合量 3.231099 大于3，已撤销。原 \(r=2,\Delta=150^\circ\) 的几何偏差反例不通过放宽到2m消除，而由新凸包界≤0.25m避免。

### 2.5 静态证据与理想时长

本轮 path_static_model.py / path_static_verify.py / path_static_verification.json 为可执行外部模型，52/52 检查；其中原投影/闭环/启动几条是常量反例演示，不是对尚不存在的 tracker 的测试。
另有独立 ordered_gate_oracle_02.py：13/13 分段线性合成解析门见证检查（闭环、重复圈、回退、短段、斜切、远离路线、无运动、no-op）。它不调用生产跟踪器；折返几何通过仍不能证明物理停车。首轮 oracle 曾错误要求“到过终点后离开应清除路线历史”，修正后另存 02，原失败保留。

独立 math_independent_review 核查253条直线、155条曲线、408个连接点和87条逐机阶段路线。8组诊断中7通过，1为上文通用近折返求积精度；真实12格时长核对一致。默认 \(A_t=0.75,J_t=2,V=3\) 时，60m静止到静止直线理想时间24.375s。

各格以**全机**逐阶段的 motion+dwell+hold+delay 取最大值作为理想屏障，再求阶段和：

| 飞法 | 2机(s) | 3机(s) | 4机(s) |
| --- | ---: | ---: | ---: |
| lawnmower | 94.173126 | 114.911992 | 197.762972 |
| rectangular_spiral | 58.699806 | 69.272841 | 77.238595 |
| patrol | 194.953540 | 173.347862 | 291.638681 |
| rapid_passage | 29.529173 | 34.341442 | 84.057094 |

假设每阶段开始/结束 v/a 为零、恒定规划高度、无故障、无真实控制滞后/捕获/驻留重置损耗。87条明细在JSON，不能把这些数字称为动态实测、全流程 wall_time、600s deadline 保证或新基准成绩。旧 245.9/248.4s 不能继续作为“修正后已验证最大值”。真实全流程计时在后续实际覆盖阶段登记。




## 3. 共同时间状态与事件契约

### 3.1 七种相位状态与独立跟踪子状态

每机每阶段顶层状态只有七种：`waiting_release`、`waiting_delay`、`executing`、`arrival_confirming`、`holding`、`done`、`phase_timeout`。停车折返 `corner_rest` 是 `executing` 内的跟踪子状态，不另算第八个相位状态；其进入、停止确认、出站均受同一全局 deadline 和共同时间切分约束。

阶段只有一个共同 `phase_end`，没有每机独立的 `phase_end`。个人 `hold_complete` 可以先后出现，其证据在共同屏障通过前可撤销。`done` 的含义是“本机当前完成、等待其他机”，不是冻结状态或永远完成。

任务截止时刻（相对于 mission 起点）为
\[
D=\operatorname{us}\!\left(\min(\text{config.execution.max_duration_s},
\text{TaskSpec.execution.timeout_s})\right).
\]
`phase_deadline` 在本设计中只是活动阶段引用该同一 \(D\) 的别名，**不是新增的公共阶段超时字段**。所有活跃状态、跟踪子状态和屏障首先检查 \(t\ge D\)：到期转 `phase_timeout`，任务结束为 timeout；不得先启动、先确认、先完成屏障再检查截止。恰在 \(D\) 完成的候选也按 timeout 处理；有效完成必须早于 \(D\)。这是拟议 M2 行为，不能伪称 M1 原事件规则已如此实现。

设共同阶段释放时刻为 \(r\)，每机的相位动作请求时刻为 \(s_a=r+\operatorname{us}(\text{start_delay}_a)\)。请求值必须可精确表示为整数微秒。共同屏障前尚未激活的下一阶段为 waiting_release；本阶段激活后，\(r\le t<s_a\) 为 waiting_delay；\(t=s_a<D\) 发 `phase_started` 并进入 executing。不存在“先达到请求时刻，才进入延迟等待”的守卫。

路线资格 `route_complete_a` 来自第2节的真实有序路线证据，不由终点距离授予。空路线只能由编译器明确登记的 hold_no_op 分支在个人 phase_started 时授予资格；之前仅有编译期 no-op 身份，不提前完成动作。非零闭环在起点静止仍不具备资格。路线已完整走完后，离开终点区域只撤销确认/驻留证据，保留已完成的路线证据并执行终点恢复控制，不要求伪造重走整圈。

到达空间/速度谓词为
\[
Q_a(t)=
\bigl(\|\mathbf p_a(t)-\mathbf P_{N,a}\|\le R_a\bigr)
\land
\bigl(\|\mathbf v_a(t)\|\le V_{\rm arrival}\bigr),\quad
R_a=\min(\text{target tolerance}_a,\text{config arrival radius}).
\]
这里用原始三维终点、真实三维速度；不改任务阈值，不把偏置参考当新终点。只有 `phase_started`、`route_complete`、\(Q_a\) 和下述已登记参考序列完成守卫都成立才允许开始终点确认。

拟议 `terminal_reference_sequence_finished_a`：normal、能力限制和B9确认失效测试中恒为true；仅注册的R4高度序列在raising/scan/lowering中为false。该机完整7s下降参考结束、UP偏置归零且原参考实际重新接管的共同时间切点才设true并登记harness事件。此时再以真实原3D目标开始新的arrival/dwell，不回溯到先前Q已满足的时间。它只阻止未结束参考动作的提前完成，不修改Q、route证据或直接发布成功；B9不能以harness active伪造reset，仍须真实Q失效。若恢复时刻不早于deadline，deadline优先。

每机保持时长为
\[
H_a=\max(\text{phase.terminal_hold_s},\text{config.execution.terminal_hold_s})
+\mathbf 1_{\rm last\ phase}\text{TaskSpec.execution.final_hold_s}.
\]
确认 dwell 取现有 `target_confirmation`。个人状态与屏障分开：

| 起点 | 前置条件（deadline 优先已检查） | 结果 |
| --- | --- | --- |
| waiting_release | 前序阶段共同屏障成立，本阶段激活 | phase_released；进入 waiting_delay，随后检查个人 \(s_a\) |
| waiting_delay | \(t=s_a\) | phase_started；executing；不改真实 p/v/a |
| executing | 路线完整、参考序列已结束且 \(Q_a\) 开始持续成立 | arrival_confirming；记录新 epoch 的 arrival_entered |
| arrival_confirming | 同一连续有效区间达到 dwell | holding；phase_arrived，含义仍是确认完成 |
| holding | 同一连续有效区间再达到 \(H_a\) | done；phase_hold_ended，仅个人完成 |
| arrival_confirming / holding / done | \(Q_a\) 失效 | epoch 加一；phase_confirmation_reset；清空 arrival/confirmed/hold_complete；executing 的终点恢复分支 |
| 任意活跃状态或跟踪子状态 | \(t\ge D\) | phase_timeout，禁止新的成功屏障 |
| 全体当前 done | 同一 \(t<D\) 时各机 \(Q_a(t)\) 仍成立且证据属于各自当前 epoch | 唯一 phase_ended；下一阶段可在同一 \(t\) 释放 |

持续区间在 dwell/hold 到期的同一时刻失效，失效优先，不授予确认或个人完成。已经写出的历史事件保留，通过 reset 的 `revoked_epoch` 标记撤销，不删除旧事件。零 dwell/hold 的状态闭包为 entered → confirmed → hold_complete，有限次同刻转换后检查屏障；不得为它添加一整步，也不得形成零时间循环。

等待期间所有飞机继续在共同快照上接受控制和积分。waiting_delay 保持实际相位进入时的保持目标；路线完成后，executing 的终点捕获、arrival_confirming、holding、done 都使用同一个终点保持控制族。仅改变证据状态不必改控制模式；真正切换（开始跟踪、折返停车/出站、终点捕获、受控注入开始/结束、下一阶段释放）必须按下节在共同时间生效。无论状态是否数值变化，每架机都参与积分，禁止覆盖/冻结实际 p/v/a。

### 3.2 候选多项式、前缀提交与控制生效

实际代码 `PointMassJerkPlant.step` 的 jerk 包含
\[
\mathbf j=\operatorname{limit}\!\left(
(\mathbf a_{\rm target}-\mathbf a_0)/\max(\tau_a,H),j_{\max}\right).
\]
因此先按长步定位事件，随后以缩短的 dt 重跑同一步并不保证得到同一条轨迹。已定位事件必须属于最后提交的那条多项式，不能混用两次控制/jerk 计算。

后续实现采用以下算法；当前的 `SynchronousEngine.truncate_last_step` 已展示保留原多项式前缀的能力，但 M2 的试算/事务封装仍待实现：

1. 在共同时间 \(t_0\) 取得所有机的不可变 p/v/a、控制模式与 epoch 快照。名义控制步界为 \(b\)，已知释放/注入开始结束/截止等调度边界先把候选跨度限制为 \(H\le b-t_0\)。
2. 全机控制只使用该快照，**一次**算出候选常 jerk 段。候选段需保留生成它的 \(H\)、请求、jerk 与源码身份，且尚不向外发布后缀轨迹或状态事件。此处不是每机各自前进一步。
3. 从这条候选段计算全部相关连续事件，选择最早控制变化/屏障的可用公共整数微秒 \(\tau\)，且 \(\tau\le t_0+H\)。共同状态严格取原候选多项式在 \(\tau\) 的值。不得把 dt 换成 \(\tau-t_0\) 后重新生成“前缀”。
4. 只提交前缀；所有机和公共网格同时截断。未提交后缀的输出、support 和拟议事件全部丢弃，不能污染日志或状态。若沿用现有 `step + truncate_last_step` 形式，所有其他可变执行器记录须同样事务化；未来加入隐藏积分器/随机状态时，未证明可回退前不得使用这种实现。
5. 在 \(\tau\) 的共同快照上处理事件因果闭包，再重新计算全机控制。新候选使用本次剩余名义周期 \(b-\tau\) 或更早已知边界为 \(H_{\rm next}\)；到 \(b\) 后推进下一个名义控制步界。此时重新求 jerk 只影响未来，不回算已提交历史。若状态事件不改变控制也不触发屏障，可仅增加原多项式的 dense 证据，不切断该段。
6. 首次结果仍须在 \(h\) 与 \(h/2\) 上比较。前缀一致性解决的是事件属于实际轨迹的问题，不保证后续新控制方案已动态收敛。

仅用现有默认 \(\tau_a=0.25\) 掩盖 dt 依赖是不充分的。纯解析检查取 \(\tau_a=0.002\) s、请求加速度 0.1、长步 0.02 s、切点 0.005 s：长步 jerk 为 5，缩短后重算会饱和到 8，位置分别为 \(1.0416667\times10^{-7}\) 和 \(1.6666667\times10^{-7}\) m。二者不同，证明必须保留原段前缀。

### 3.3 根、整数时钟与同微秒因果

常 jerk 段位置是三次、速度是二次；距离平方减半径平方最高六次，速度平方减阈值平方最高四次。分别求根、合并并检查各开区间，保留端点切触/重根情况。固定 11 点或任意固定采样点不能替代根/区间检测。

真实根相对段起点的高精度偏移属于诊断 `detected_offset_s`；公共事件和控制生效使用整数 `t_us`。给定已隔离根的数值括区间，采用不早于根的首个整数微秒作为候选生效点，重新以**同一候选多项式**检查该点与右侧守卫。仅当根位置的误差界足以唯一决定微秒格点（或根已按明确误差准则认证为整数边界）才能写确定时刻，否则细化隔离或显式报数值不确定，不能随意 round 掩盖。诊断保留括区间及不超过 1 µs 的量化上界。

确认起点取有效区间内第一个整数微秒；持续 dwell/hold 也以整数时长计算，且其间整个连续谓词必须成立。在不到 1 µs 的短暂进入后退出中，没有可用整数确认时刻时只保留 transient 诊断，不能授予确认。曾经 done 的机若在相邻整数点之间短暂退出后重新进入，仍要增加 epoch、撤销旧 dwell，不能仅检查两端都满足而保留 done。

对会改控制的事件，`t_us` 是实际控制生效时刻；若连续根在其之前，单独记录 `detected_offset_s` 与量化界，不能把检测根和生效时刻写成同一个精确量。同一微秒内多个连续事件按实际根顺序保留因果；到共同整数时刻，以所有经过的 invalidation 更新 epoch，再根据当前有效区间授予新的 entered/confirmed/hold。短暂退出后重新进入也不能恢复旧 epoch。

事件至少拟增加：`phase_index`、`event_seq`（任务内单调）、`epoch`（逐相位逐机）、`revoked_epoch`（reset 时）、`detected_offset_s`（适用时）、`effective_time_policy`。这些是 M2 拟议事件结构，不表示 M1 已存在。事件序列在共同时间批次内确定性生成：

- deadline 同刻最高优先，发 timeout 后不发新的成功转换。
- 非超时点先处理已有确认的失效/epoch，再处理释放和当前有效区间；
- entered → confirmed → hold_complete 的依赖按顺序发生；
- 所有机更新完成后检查共同屏障，再释放下一阶段。
- 时间不同的连续根先按根时间处理；同一逻辑批次内独立飞机按规范 agent ID 排序。真正同根的失效优先于成功。任务/阶段级事件 `agent_id=null`；缺相位的任务事件 `phase_index=null`，排序不依赖把 null 与字符串直接比较。
- 完成的日志按 `(t_us,event_seq)` 展示；`event_seq` 由上述规则产生，与源字典/机数组顺序无关，不以 event_name 字母序替代因果顺序。

M2 adapter 必须使用当前相位/agent/epoch 的确认链，以及有效的事件 ID 引用；不能沿用 `t_us >= last_reset` 作为充分条件。M1 reader 保留原有版本路径，后续 M2 分派实现须与完整版本设计一同验证。

### 3.4 时刻含义与不变量

| 字段 / 事件 | 含义 |
| --- | --- |
| requested_release / actual_release / phase_released | 全阶段唯一请求及实际激活时刻 \(r\)，即上一阶段共同结束，首阶段为 0 |
| requested_start_a | 个人开始动作请求 \(s_a=r+\mathrm{delay}_a\)，并非 phase_end |
| actual_start_a / phase_started | 实际开始执行动作；合法未超时输入中等于 \(s_a\) |
| motion_start_a / phase_motion_started | 释放后实际速度首次超过登记运动阈值；若释放时已超过阈值，时刻取 actual_start 并记 already_moving_at_release；无运动时为 null |
| arrival_a / phase_arrival_entered | 当前 epoch 的路线完成与到达谓词开始持续成立的时刻 |
| confirmed_a / phase_arrived | arrival + 原任务 dwell，确认连续有效后才产生 |
| hold_complete_a / phase_hold_ended | confirmed + \(H_a\)，仅本机完成，可在屏障前撤销 |
| phase_end / phase_ended | 全机同一时刻有效完成后的唯一屏障；下一阶段可同刻开始；超时时本阶段不存在成功 phase_end |

必有 \(r\le s_a=\text{actual_start}_a\le arrival_a\le confirmed_a\le hold\_complete_a\le phase\_end<D\)，但仅对已产生且未撤销的完整成功链适用。motion_start 是独立可空诊断，不塞入这条全局链：no-op 可 null；非零进入速度不需要伪造阈值穿越；延迟期保持产生的真实运动记作独立保持诊断，不冒充本阶段动作已经开始。phase_end 的表达式是**当前有效 epoch** 的 \(\max_a(hold\_complete_a)\)，并在该共同时刻重新验证所有到达谓词；不能对全历史事件取最大值。

### 3.5 六组静态事件过程

以下时间单位全为 **µs 的离散合成时钟**，用于状态推理，不是实际飞行证据；精确完整事件行见 state_contract_checks_02.json。

| 用例 | 给定过程 | 必须得到的结果 |
| --- | --- | --- |
| done 后离开 | A 在 10 entered、20 confirmed、30 hold_complete，35 失效；B 在 40 entered、50 confirmed、60 hold_complete；A 在 65 重新 entered、75 confirmed、85 hold_complete | A 在 35 reset 为 epoch 1；60 不能释放；共同 phase_end 只有一次、为 85 |
| 个人延迟越过 deadline | phase release 0、请求 A=50、deadline=40 | 40 只有 timeout，不出现 phase_started；另逐项检查所有七态及 corner_rest 子态在 deadline 同刻都超时 |
| no-op | 编译空路线资格 true；p 等于原目标、v/a 为 0；dwell=10、hold=20 | 0 entered、10 confirmed、30 hold_complete/phase_end；motion_start=null |
| 非零进入速度 | 0 激活、请求动作 7；延迟保持期及 7 时 v=0.2；20 才满足到达；dwell=10 | motion_start=7 且 origin=already_moving_at_release；无位置/速度覆盖；30 confirmed/hold_complete/phase_end |
| 零 dwell/hold | 12 时已开始、路线资格和到达有效，二者时长都为 0 | 同刻 entered → confirmed → hold_complete → phase_end，有序有限闭包，无额外积分延迟 |
| 同微秒 reset/confirm | A 在 t=10 的 epoch 0 已个人完成，但 B 未完成；A 短暂退出/重入均量化到 10，dwell/hold=0；B 于 11 完成 | A epoch 0 全部撤销；t=10 按 event_seq 先 reset 再 epoch 1 entered/confirmed/hold；只有 epoch 1 可用于 11 的共同屏障。按 t>=last_reset 会错误保留两次 arrival，必须被拒 |



## 4. 版本、配置与严格读取兼容（设计提案）

本节冻结后续实现契约，不声称 M2 reader/config 已实现。M2-04 只实现参考基础及合成测试，M2-05 集成执行器；**M2-06** 才按本节实现 artifacts、版本化 adapter 和公共消费者兼容。不得通过删除相等校验、忽略未知字段或补写历史 manifest 取得兼容。

### 4.1 真实 M1 身份与拟议 M2 身份

M1 值由源码静态提取，并与 M2-01 已确认的七个最终样本 source/manifest 元数据核对。`semantic_adapter_version` 是已有字段，不得重新称为新增或将真实旧值改名。

| 位置 / 含义 | 已有 M1 确值 | M2 提案 |
|---|---|---|
| manifest.protocol_version | `fast_dynamics_v1` | 保留数据/时钟家族名；不代表两代 reader 相同 |
| source.engine_version / manifest.simulator_version | `0.1.0` | `0.2.0` |
| source.plant_model | `point_mass_jerk_v1` | 保留 |
| source.controller_version | `velocity_response_v1` | 保留其已有方程；改变组件方程须另升版本 |
| source.observer_version | `ideal_kinematics_v1` | 保留 |
| source.integrator_version | `constant_jerk_v1` | 保留 |
| source.task_adapter_version | `frozen_compiled_v3_v1` | 保留，原输入编译几何不变 |
| source.diagnostics.reference_version | `endpoint_velocity_v1` | `continuous_route_v2` |
| source.diagnostics.executor_version | `airborne_rapid_passage_m1` | `airborne_multi_intent_m2` |
| source.semantic_adapter_version | `fast_dynamics_semantic_adapter_v1` | `fast_dynamics_semantic_adapter_v2` |
| manifest.analysis_version | `fast_dynamics_semantic_adapter_v1` | `fast_dynamics_semantic_adapter_v2` |
| phase_windows.window_version、每窗source、labels.label_provenance.semantic_adapter_version | `fast_dynamics_semantic_adapter_v1` | `fast_dynamics_semantic_adapter_v2` |
| manifest.component_versions.facts / 实际facts_version | `observer_facts_fast_dynamics_v1` | `observer_facts_fast_dynamics_v2` |
| source/manifest.config_schema_version | 两处均不存在 | 两处均为 `fast_dynamics_config_v2` |
| source/manifest.behaviour_version | 两处均不存在 | 两处均为 `m2_continuous_v2` |
| source/manifest.execution_mode | 两处均不存在 | 两处显式相等，为 `normal` 或 `test_reference_fault` |
| source.calibration_status | `uncalibrated_M1_baseline` | `uncalibrated_M2_baseline` |
| manifest.evaluation_context | `local_development_uncalibrated_M1` | `local_development_uncalibrated_M2` |
| source.intended_use / manifest.training_eligible | `local_development` / `false` | 保留，不能因 M2 功能扩展取得训练资格 |
| source.rng | `{algorithm:PCG64, consumed:false, reason:"M1 deterministic; disturbances disabled"}` | `{algorithm:PCG64, consumed:false, reason:"M2 deterministic; disturbances disabled"}` |

reference/executor 从已有 diagnostics 位置取值，不虚构 M1 顶层字段。M2 若冗余记录顶层身份，必须与 diagnostics 相等。行为版本包含本设计的有序 EN 路径证据、U 控制、终点全3D确认、共同屏障和 epoch 事件顺序；不能仅凭外层 `fast_dynamics_v1` 把新行为当作 M1。

完整六字段语义协议：

| 字段 | M1 | M2 提案 |
|---|---|---|
| task_kind | `mission_v3` | 同 M1 |
| ontology_version | `multi_intent_mission_v1` | 同 M1 |
| label_schema_version | 整数 `3` | 同 M1 |
| semantic_validation_version | `multi_intent_validation_fast_dynamics_v1` | `multi_intent_validation_fast_dynamics_v2` |
| eligibility_protocol_version | `fast_dynamics_quality_v1` | 同 M1 |
| execution_constraints_version | `airborne_mission_limits_fast_dynamics_v1` | 同 M1 |

M2 单独登记 semantic_validation_version，以标识新的事件/窗口解析和三意图支持范围。质量与原几何阈值含义未改变。TaskSpec 内自己的 execution.protocol_version 和 planner/validator/facts/templates 原字节不改；后端 facts 身份写在外部产物。M2-06 同步 supported_protocols、artifacts、dataset、audit、loader、facts、language 的明确分派，不改旧 SITL 分支，不增加混合协议绕过入口。

### 4.2 M1 七组 22 字段保持；M2 增加 reference 七字段

M1 的完整序列化形状如下。数值是**默认值**，不是全部历史样本的固定值；合法的 0.3m/s 能力配置和 0.03s timeout 配置必须仍可读取。

| 组 | 现有字段、默认值与单位 |
|---|---|
| engine | `step_us=20000` μs；`output_period_us=100000` μs |
| vehicle_profile | `max_speed_xy_m_s=12.0`、`max_speed_up_m_s=4.0`、`max_speed_down_m_s=3.0`（m/s）；`max_accel_xy_m_s2=3.0`、`max_accel_up_m_s2=2.0`、`max_accel_down_m_s2=2.0`（m/s²）；`max_jerk_m_s3=8.0`（m/s³）；`response_time_s=0.25` s |
| controller | `velocity_response_time_s=0.8` s；`state_source="truth"`；`control_type="AccelerationENU"` |
| observation | `mode="ideal"` |
| environment | `mode="zero_disturbance"` |
| execution | `lifecycle_scope="airborne_mission"`；`max_duration_s=600.0` s；`arrival_radius_m=1.0` m；`arrival_speed_m_s=0.15` m/s；`terminal_hold_s=0.0` s |
| quality | `max_speed_tolerance_m_s=0.75` m/s；`min_separation_m=2.0` m |

M1 验证保持原义：除 terminal_hold_s 和 quality 两字段可为零外，上述数值要求有限正数且不是 bool；step_us/output_period_us 要求非 bool 整数，且 \(0<\mathrm{step\_us}\le100000\)、output_period_us=100000。字符串只接受表内枚举。environment 已存在，不能遗漏。

M2 新增第八组 `reference`，只新增以下七字段；总计八组、29字段。旧稿中的其他 corner/stop/decel/barrier/inject 字段不再作为本轮公共配置提案。

| reference 字段 | 类型 / 单位 | 默认值 | 严格接受域 |
|---|---|---:|---|
| policy | 字符串枚举 | `continuous_route_v2` | 仅精确此值 |
| corner_cut_max_m | 有限实数 / m | 0.25 | \(0<x\le0.25\) |
| corner_leg_fraction | 有限实数 / 无量纲 | 0.1 | \(0<x\le0.1\) |
| tracking_tube_m | 有限实数 / m | 0.5 | \(0<x\le0.5\) |
| position_gain_per_s | 有限实数 / s⁻¹ | 1.25 | \(x>0\) |
| velocity_damping | 有限实数 / 无量纲 | 0.25 | \(0\le x\le1\) |
| preview_time_s | 有限实数 / s | 0.2 | \(0<x\le0.2\) |

所有“有限实数”接受 JSON number，明确拒绝 bool、null、字符串、NaN/Infinity；不将字符串或 bool 自动转成数值。组必须为 object，组名/字段集合严格匹配对应版本，拒绝未知字段和空缺字段。`config_schema_version` 放 source/manifest，不塞进 config 作为第九组。执行入口可以显式完成默认配置后再运行，**读取已冻结产物时不补默认**：M1必须完整七组，M2必须完整八组。v1/v2各自解析并往返相等，config_sha256 必须绑定各自完整实际运行配置，旧样本不能因新版默认值多了 reference 而变化。

### 4.3 能力、时间与来源完整性

两代初期保存以下相同能力，按键、值及 JSON 类型精确比较，不接受数值1代替 true：

```json
{"position":true,"velocity":true,"net_acceleration":true,"attitude":false,"body_rates":false,"imu":false,"motors":false,"takeoff":false,"landing":false}
```

这是 artifacts.CAPABILITIES 的存档结构，不能以 contracts.capabilities() 的另一种接口说明替换。SOURCE_DECLARATIONS 精确为：coordinate_frame=`ENU`，feature_schema=`enu_position_velocity_6_v1`，controller_state_source=`truth`，observation_dependency=`ideal observation derived from plant; no independent sensor/estimator`。source/manifest 的 simulation_backend=`fast_dynamics`、lifecycle_scope=`airborne_mission`、time_base=`sim_clock` 交叉一致。

TIME_POLICY 完整保持：version=`integer_sim_clock_half_open_v1`、time_base=`sim_clock`、tick_unit=`microsecond`、record_hz=10、output_period_us=100000、endpoint_policy=`[0,end_us)`、duration_source=`actual_end_us`。继续验证 end_us、duration、半开帧数、support两端及观测与support同刻状态相等。

QUALITY_POLICY 完整保持：version=`fast_dynamics_quality_v1`、min_observation_valid_fraction=1.0、min_truth_valid_fraction=1.0、numerical_tolerance=1e-7、zero_duration_eligible=false、lifecycle_scope=`airborne_mission`。既有数值、速度能力、世界/间距/时长/长度约束、三态语义与资格复算不删减；不把失败或 unknown 隐藏成不支持。

来源要求：非空 source_sha256/input_sha256 且值为64位小写十六进制；seed 为非 bool 非负整数；git_commit 为40–64位小写十六进制；task/config规范哈希与内容一致；附件路径在根内、哈希一致；TaskSpec重编译场景及family仍一致。读取历史产物时不要求其源码哈希等于当前 M2 工作树，不补写当前 HEAD。producer仍须验证执行开始/结束/导出的源码身份一致。

**中间失败原因更正：** `integration_attempt_01` 的 engine、adapter、能力和RNG与七个最终样本一致，实际 source 缺少 `git_commit`，触发当前“capabilities/units/seed/code identity”复合guard。不能将其说成能力版本不同，也不能通过兼容逻辑自动补上 Git 身份。七个最终样本的实际 git_commit 均为 `5e45637f2bf63054ed0ace2433fd7c9ea7b075ac`；这一历史 baseline不改写。

### 4.4 正常运行与测试参考故障的严格身份

M2 source/manifest 都必须显式提供 execution_mode，缺失、null或不一致一律拒绝，不能默认 normal。旧 M1 缺此字段仅在完整 M1 元组匹配后按旧契约处理；M1出现该新字段或任何 M2 harness/epoch身份则拒绝。

| 模式 | 必需证据 | 必须拒绝 |
|---|---|---|
| `normal` | 两处 execution_mode 精确为normal；运行配置、来源、正常事件完整 | 出现故障descriptor/故障事件/额外harness附件，或源身份声称有故障但mode写normal |
| `test_reference_fault` | 两处mode相等；两处 `harness_contract_version="fast_dynamics_test_reference_fault_v1"`；source.harness_sha256 等于 manifest.artifact_sha256 中 `test_harness.json` 的真实哈希；完整descriptor、运行记录和源码快照绑定 | descriptor、代码、配置、seed、phase/agent、实际注入事件任一缺失/矛盾/哈希失配；未知harness ID/参数形状；仅有标量偏置；未声明地修改状态/观测/完成事件 |

`test_harness.json` 的 contract_version 必须与身份值相同，至少冻结：注册harness ID及自身版本、所有实际执行harness/辅助模块源码的路径身份与SHA256、TaskSpec和完整配置哈希、seed、目标phase及排序agent、ENU方向、幅值/速度系数/时间函数、一次性触发与恢复规则、requested起止和actual生效/结束、输出到原参考的恢复策略及对应event_seq/epoch范围。模式只用于已审阅的参考层故障，例如本设计的U参考偏置/服务速度限制和保持失效边界；不得执行任意未登记代码或把故障扩展为改标签、删航点、改观测或强制结束阶段。

当前 source_snapshot 只枚举 swarm_sim 与 scripts/*fast_dynamics*.py，**不会自动绑定任意外部harness**。M2 producer必须另外对实际harness源码在运行开始/结束/导出核对哈希，并将其快照与descriptor写入同一全新外部attempt；可用根内扁平命名的独立源码附件，让现有artifact哈希机制覆盖。reader只核对这些代码附件与哈希，绝不执行产物内代码。参考注入要求以输入请求和状态响应留证，而不是在写报告时事后宣称使用了某harness。

adapter v2/reader消费对应模式的descriptor和事件：核验一次性phase/agent绑定、请求与实际生效时间、恢复状态及epoch；终点和路线资格依旧使用原始任务目标/有序路线；语义从实际support/完整观测重算，不能依据harness预期直接赋false。source环境可仍为zero_disturbance、observer仍ideal，因为测试故障改变参考而非风或传感器；execution_mode必须使这种区别可检查。正常与故障样本在metadata和汇总中显式分组，不可把故障样本伪装成正常/训练合格基线。

### 4.5 唯一受支持的读取元组与分派

注册表为三个明确分支：完整M1旧元组（新schema/behaviour/mode键均真正缺席）、完整M2正常元组、完整M2测试参考故障元组。后两者共享 M2 实现/协议/config版本，分别执行上表模式证据校验；不是独立版本值任意混搭的笛卡尔积。

读取步骤：

1. 收集有类型的 source/manifest 身份及“键不存在”哨兵；比较engine/simulator、adapter/analysis、schema/behaviour/mode等跨文件值。任何fast_dynamics与其他后端声明冲突都拒绝，不能回落SITL。只有唯一完整匹配才进入相应reader；explicit null、`v2`别名、大小写近似、前缀匹配均不允许。
2. 由版本专用config解析器校验完整形状、范围、往返相等及哈希。单纯删M2 schema不会取得M1资格；新增reference组、M2事件、M2behaviour/mode等也会阻止降级。
3. 核对TaskSpec编译及**该实现的任务能力范围**。M1严格要求两机、rapid_passage、line_abreast_v1、semantic_phase_route_v1、每机每阶段至多一个路线目标，与原run_mission guard一致。M2接受本阶段设计登记的2/3/4机、三意图四合法飞法，参考原语仅接受当前已登记的恒定规划高度/EN路线域；未登记能力须明确拒绝。不能仅改身份字符串把多点/三机数据降级为M1。
4. 验证全部来源/能力/时间/数值/原始输入及模式证据。M1使用冻结v1配置类、原build_windows/analyze_semantics/事件处理与validator身份；M2使用v2事件及窗口解析，检查event_seq/epoch、撤销后的有效证据与共同屏障。不得用新epoch规则改写M1旧窗口，也不得让旧 `_events` 的宽松规则接收M2记录。
5. 从真实support、events和原始任务重算labels、semantic_validation、phase_windows、execution_constraints、numerical、quality、eligibility，再与存档分别精确比较；只比较多个文件抄写的标签是不够的。M1保持原几何/语义判定，不以新版“修正”旧结论。phase_windows/label provenance的版本和本次重算分派必须同源。
6. 验证成功才返回既有六维x、mask、time、targets、metadata。七个最终M1样本只读可用；原中间失败仍失败。新旧数据分别可读，默认不能混导出同一dataset；M2新的完整语义协议继续触发现有混合协议拒绝规则。

普通自带内容哈希不是签名，不能证明有人同时重造全部源码身份、原始状态及所有自带哈希的产物真实。对七个已归档对象另用获准relocation index和manifest外部绑定，防止局部篡改后重哈希伪装原件；对新运行用producer执行前后源身份和完整证据复核。这个界限不构成放宽任何检查的理由。

### 4.6 M2-06 验收清单及本轮证据界限

M2-06必须实际复跑：七个最终M1只读load/audit/必要facts与描述，前后文件哈希不变；原中间attempt按缺来源身份继续拒绝；M2正常与故障两个完整链分别验收。逐项拒绝未知/混合版本、缺schema/mode、删environment、给M1加reference、数值/类型非法、漏harness附件或代码哈希、故障标签赋值、改标签后同步重哈希、改窗口epoch后重哈希、timeout改completed、新旧/SITL静默混导出。M2-04不得抢做完整链兼容。

本兼容子任务已运行 `compat_extract_and_model_03.py`：**44/44 静态模型检查通过**。提取13份源码和8组归档source/manifest（16份JSON），验证真实M1值、完整七组形状、元数据版本分派及未知/混合/缺schema/能力/来源基本格式拒绝。首轮38/39遗漏git来源完整性，第二轮因正则变量命名冲突中断，第三轮修正；脚本、失败日志、结果均独立保存。

这44项**没有验证**新增reference七字段数值解析器、M2执行模式/harness生产读取、真实TaskSpec能力guard或v2语义重算；这些仍是上述设计与M2-06测试规格，不能在摘要中写成已通过。该子任务0次生产load/audit、0次飞行/积分、0次CSV读取、0次语义重算。此零计数仅指本子任务，不覆盖attempt_01历史55项测试内实际M1仿真，后者调用/episode数未计量。


## 5. 保留真实飞行状态的配对负例设计

所有12格 actual_result=null、execution_status=NOT_RUN。以下是可证伪机制及合成谓词证据，不是实际质量合格负例。

### 5.1 必须先区分路线完成证据与任务成功条件

新设计明确：当前12格共28个阶段每机规划路线都处在一个恒定高度平面（脚本 `negative_EN_up_contract.py` 逐阶段实读核对）。有序路线进度及横向走廊只用 EN 平面；U 是真实积分和观测的状态分量，独立控制并检查世界高度/速度/加速度/jerk。最终到达仍以原始任务终点全3D距离和速度判定，完成确认/驻留/返航规则不改。

这是明确的执行契约，不能暗中把服务高度合格塞进路线完成资格。若仍坚持原始路线的全3D 1m硬管道，则下面高度机制不成立，应保持R4未决。不是放宽EN走廊或更改输入、路线点、观察阈值。

`mission_evaluation.py::_evaluate_channel` 在完整窗口内，用实际 U 是否位于 `takeoff_alt_m ± height_tolerance_m` 选择理想观察足迹；高度不符的原始样本仍保留且有限，未被执行方删除。覆盖集合小于阈值且完整窗口/原始轨迹齐全时，该注册规则返回 false，而非 null。此语义筛选与删除观测是不同操作。

原“减速/错峰必然漏扫”机制撤销。三格lawnmower若完整对应原路线且EN误差≤1m、服务高度始终合法，半径 \(4-1=3\,\mathrm m\) 的保守名义足迹已覆盖100%冻结网格；因此这类偏置/减速不可能保证coverage false。三格spiral也不能靠猜测：统一1m EN偏移24个方向的最坏静态比率仍分别0.962963/0.977778/0.977778。低于0.9的完整任务false需要不同状态机制。

### 5.2 六格侦察：共模垂向参考偏置，保留全部EN路线与原终点

设计状态：`DESIGN_SPECIFIED_STATIC_CAUSALITY_CHECKED_DYNAMIC_UNVALIDATED`。本设计**不新增任何公共 fault 配置字段**。试验性参考故障仅由仓库外、声明并哈希的测试 harness 施加，不能由未登记的入口字段或按意图隐藏的生产控制分支启动。所有控制请求最终仍经过同一真实 plant 积分；harness 不能覆盖位置、速度、加速度或事件结果。

- 作用对象：该任务全部排序agent；仅一次作用于绑定的 `p01_observe`，ENU方向 \((0,0,+1)\)，目标参考偏置 \(1.25\,\mathrm m\)，正常观察高度8m，因此偏置目标9.25m；世界允许3..40m。全机共模垂向偏置避免主动改变相互垂向差，但不据此宣称间距质量自动通过。
- 触发与升高：在真实服务阶段释放后启动；保留真实phase_started及窗口（升高阶段也计入），将EN参考保持在原始服务起点。harness通过**U速度参考**追踪平滑抬高目标，普通plant积分p/v/a，不写状态数组，不改传感有效掩码，不先写完成事件。偏置参考可用7s五次端点平滑函数 \(q(u)=10u^3-15u^4+6u^5\)，\(b(t)=1.25q(t/7)\)；其参考速度/加速度/jerk界约0.334822m/s、0.147283m/s²、0.218659m/s³。此界只约束参考，不等于实际plant已满足。
- 沿线执行：实际高度达到 \(U\ge9.15\,\mathrm m\)、\(|v_U|\le0.05\,\mathrm{m/s}\) 持续0.5s之后，才恢复原路线EN参考推进；所有原始路线原语/圈次按同一规则记录。维持UP偏置至该机原EN路线完成。不同机实际开始可能不同，全部记录实际时间，不能伪造同步开始。
- 恢复：EN参考在原始服务终点保持，7s平滑回撤U偏置至0；在lowering结束且原U参考已接管前 terminal_reference_sequence_finished_a=false，不因提前满足半径/速度便开始arrival。U参考恢复8m后该守卫才为true，并从此重新计原dwell，待真实全3D终点双条件、确认、驻留和共同屏障全部满足后结束阶段。若有return，执行原return路线到原起点。没有删航点、重新规划或强制phase_end。若闭合路线首尾相同，必须先有完整展开EN进度，不能在起点恢复并完成。
- 一次性/重入：harness状态 `not_started→raising→scan→lowering→finished`；phase/agent绑定后禁止第二次触发。到达失效或复位事件依既定状态机处理；注入记录不替代原始到达/route_complete证据。达到任何deadline仍按timeout结束并保留失败证据，不能计入要求的semantic false。
- 后续验收必须从实际支持轨迹独立核对：每一个服务高度合法的点/连接段，只能落在原起点或终点EN半径1m邻域；实际扫描时U始终大于9m（明确记录最低高度及时间）；所有原EN路线顺序完成、恢复原3D终点；原始与理想观测均完整；世界、全程间距、能力、时长、路径长度、数值积分与公共产物审计合格。若扫描途中落回高度带，实际覆盖照实计算，不能掩蔽该段；即使最终仍false，也需按实际足迹证据说明，不能继续套用下面简化上界。

### 保守几何上界（包含升降阶段服务足迹）

如果服务高度合法的所有位置都在原始起/终点EN半径1m内，则任何被覆盖格心距某个端点不超过 \(R+1=5\,\mathrm m\)。此为完整轨迹覆盖的**上界**，已经允许升降时有≤1m的EN保持误差，不遗漏升高/恢复阶段的贡献。实际扫描在高度带外不会提供足迹，正常恢复后无限驻留也不增加端点圆盘以外的覆盖。所有阈值均原样读取绑定输入：覆盖要求0.9、观察半径4m、高度容差1m、格距1m。

| 冻结格 | 格心总数 | 5m边界圆盘并集 | 覆盖上界 | 必漏格心至少 |
| --- | ---: | ---: | ---: | ---: |
| lawnmower n2 | 720 | 120 | 0.166667 | 600 |
| lawnmower n3 | 1470 | 220 | 0.149660 | 1250 |
| lawnmower n4 | 3190 | 231 | 0.072414 | 2959 |
| spiral n2 | 621 | 114 | 0.183575 | 507 |
| spiral n3 | 1530 | 174 | 0.113725 | 1356 |
| spiral n4 | 2520 | 234 | 0.092857 | 2286 |

这些是独立静态网格计数，不是飞行覆盖实测。`negative_EN_up_contract.json` 给出逐格分母与参数。额外合成分段线性轨迹调用既有注册coverage谓词，nominal六格均1.0/true，UP候选六格分别0.116667、0.097959、0.048903、0.132045、0.082353、0.065079/false，完整证据标志true。该合成轨迹未经过plant，有瞬时拐角速度变化，故不能写episode、不能证明质量合格、不能替代后续6个真实任务。

`negative_synthetic_predicates.json` 中 `route_3d_tube_1m_valid=false` 和 `candidate_approved=false` 保留当时按旧硬3D管道诊断的原始结果；后续 `negative_EN_up_contract.json` 明确登记经主审设计决定切分EN进度与U服务条件，不改写先前记录。不是将旧反例宣称为动态通过。

### 5.3 三格巡逻：全机同倍速能力限制，原阈值不动

采用服务阶段所有agent的实际参考速度能力系数0.4，而不是仅延迟一机开局或删圈。在原perimeter路径与初始空间弧长偏置下，共同降低实际巡航能力，按原路线/圈次最终完成，原规划速度及 `max_revisit_gap_factor=2.0` 保持输入值。能力扰动只在服务阶段一次性启用，结束后平滑恢复（跨阶段保留实际p/v/a）；同一方向/路径，不主动拉近队伍。每机所有支持数据保留，正式子成功条件只用 `perimeter_revisit_v2.max_gap`，visit/lap计数仍为诊断，不加回v1访问次数门槛。

| 格 | 原允许max_gap(s) | nominal合成max_gap(s) | ×0.4合成max_gap(s) | 合成服务时长(s) |
| --- | ---: | ---: | ---: | ---: |
| patrol n2 | 39.234045 | 19.7 | 49.1 | 297.255335 |
| patrol n3 | 34.420624 | 17.3 | 43.1 | 261.154682 |
| patrol n4 | 44.817543 | 22.5 | 56.1 | 451.175428 |

这些合成轨迹对既有v2子谓词得到nominal true / 候选false、原始证据完整；不是新执行器完成或质量验收。n2诊断3圈、n3诊断2圈。n4初始合成探针的nominal/candidate均因末时间表示不一致输出null；保留原结果，经第5.6节单独核查后，**修正边界的候选**四机均2圈且诊断完整。没有重跑nominal n4，不能把其原null回写成通过。TaskSpec n3/n4实际laps=2，不能沿用摘要里“三格laps都3”的错误。

冻结设计的正式接纳仍要求：完整原展开路线、全机终点/返航、共同窗口、实际间距和全部质量合格，实际 `max_gap > allowed_gap`、两通道一致false。若慢速导致timeout或非合格，只登记该结果，不算配对失败。静态表尚不能证明600s整体deadline、转角响应或动态间距；不能通过改阈值、改phase speed字段来让失败成立。

### 5.4 三格快速通过：已知M1机制与迁移范围分别列明

保持原TaskSpec，显式设置 `vehicle_profile.max_speed_xy_m_s=0.3`，让实际低速通过产生冻结 `no_dwell` 条件失败，再完整到达/确认/驻留/需要时返航。只双机M1范围已有实际机制依据；当前这12格本阶段均未执行，3/4机仅待迁移验证，不能说三格已可用。其运行时长、能力夹限、完整窗口、两通道false与质量合格都由后续实际产物验证。

### 5.5 接口与验收边界

本阶段只冻结仓库外测试 harness 的 reference-fault 协议与独立预期，**不新增任何公共 `fault`/`inject_*` 配置字段**，不修改生产业务代码。后续harness需绑定：自身源码哈希、TaskSpec哈希、配置完整值、seed、phase/agent、ENU方向、触发/恢复规则、requested/actual开始结束时刻、实际U/速度/偏置历史、执行器版本；产物元数据必须辨认“测试故障注入”，不可冒充正常无扰动参考。

每格正式负例统一门：`mission_success=false`、`mission_success_observation=false`、语义一致、`episode_quality_eligible=true`、完整route/phase/return/终端证据、公共导出/审计/加载通过。false、null、timeout、不合格、异常分别计数；未执行填null。静态谓词false不能填入真实覆盖矩阵actual_result。

这是设计层的因果论证，动态接纳仍未验证：实际状态U偏差→注册传感高度门不激活→未覆盖格心→完整窗口coverage false；巡逻实际速度变慢→原阈值下重访时间增大→完整max_gap false；快速通过实际慢速→冻结停留判定失败。没有修改标签、阈值、观测、路线点、完成事件。后续动态实施仍须验证这些条件，而非把本设计稿视作实际动态执行结果。
### 5.6 合成探针边界问题的后续核查（保留首轮结果）

上文n4圈次null已定位到**本轮合成探针**，不是既有mapper的已知缺陷：`rows()` 将支持样本时刻round至9位，却把未round的end_s传给窗口；n4末样本恰略早于window end，触发源码严格的 `trajectory_does_not_cover_common_domain`。这也是为何服务coverage/max_gap的EPS检查通过，但严格有序进度拒绝。`negative_patrol_n4_diagnostic_03.py` 只把末样本时刻设成同一end_s（不改轨迹几何或验证器）后，四机均给出2圈、`issues=[]`。后续实现必须使用公共整数微秒边界，不能模仿这个混合浮点探针。

保留失败链：`negative_patrol_n4_diagnostic.py` 因多一个右方括号SyntaxError，01日志记录，未写结果；`_02.py` 是修正语法后的只读定义提取与诊断，输出原始边界不足的JSON；`_03.py` 隔离验证一致边界后产生 `negative_patrol_n4_diagnostic_boundary_fixed.json`。没有覆盖先前脚本、JSON或日志。n4修正只证明**合成**轨迹的两圈可被v2识别，不变成实际动态飞行完成/质量验收。
### 5.7 本轮精确统计与只读交叉核对

机器读取统计：`negative_probe_statistics_final.json`。统计按身份断言、几何条件、注册子谓词和诊断分组，**不把重叠分组加成一个unit-test总数**。6次探针进程尝试：5次exit0、1次SyntaxError exit1；随后另有本轮封存前统计审计1次exit0，21/21静态核查通过。当前负例子任务实际engine调用、实际M2任务、episode写入、留出访问均0。

- 初始几何：12个fixture哈希断言；6格几何结果与144次方向几何查询不是144项单元测试。
- EN/U契约：12个fixture哈希；87个每机阶段恒定规划高度检查汇总成28阶段；6个条件覆盖上界成立（均依实际状态需满足的前提）。28与87不得重复相加。
- 注册语义子谓词：9个fixture，18个合成试验（12个coverage、6个max_gap）；9个nominal true和9个candidate false均符合预期，全部18个具有该谓词所需原始支持证据。此处false是期待的合成数据值，不是失败测试或正式负例验收。
- 首轮巡逻进度诊断18个agent结果：10个有效（n2/n3两个variant），8个unknown（n4两个variant）。随后4个unknown再现、4个修正边界候选有效结果分别保留，不能抹去旧unknown。
- `negative_patrol_n4_diagnostic.py` 的SyntaxError发生在执行前，完成运行时检查0项；后两次诊断有各自文件与日志。

只读核对主修复方 `path_static_model.py`、`path_static_verify.py` 和结果：同一12格/28阶段/87机阶段，phase名称一致；路线模型用EN生成原语并显式要求**规划输入**高度恒定。这与本文“实际U可受故障偏置、原规划U不变”一致。理想时长结果明确假设 `no faults`、恒定规划高度、阶段静止起止；不能将其当成本文升高/恢复及真实响应后的时长，也不构成完整质量验收。源文件和结果SHA256在机器统计内绑定；本子任务没有改写主修复方任何模型或探针。

## 6. 公共接口、实施顺序与停止条件

| 后续小阶段 | 预计代码/测试位置（尚未修改） | 本设计要求 |
| --- | --- | --- |
| M2-04 | references.py、必要参考辅助模块、contracts.py reference配置、单机合成测试 | 原语/弧长/独立路线证据/控制请求/折返；保留M1旧参考路径；不抢做12格全链 |
| M2-05 | mission_executor.py、engine.py、事件/执行测试 | 全机共同候选前缀、七态、epoch、deadline、屏障；继承真实p/v/a |
| M2-06 | adapter.py、artifacts.py、公共dataset/audit/loader/facts/language分派及兼容测试 | 严格版本分派、七最终M1只读兼容、旧坏样本拒绝；快速通过2/3/4机正负完整链 |
| M2-07/08 | 扫描相关测试、外部声明harness | 两种扫描各3格正负；高度故障仅改真实控制参考；完整质量和语义false分开验证 |
| M2-09 | 巡逻相关测试与正式验证器调用 | 多圈/有序进度/重访与三机数配对，保留正式v2条件 |
| 后续M2汇总 | 覆盖矩阵/报告/性能记录 | 真正执行后填actual_result、全流程wall_time、质量及失败类型；M2完成后停止 |

前两行生产模块位于 swarm_sim/fast_dynamics/，测试位于 tests/；外部harness源码及运行数据仍写SwarmData。M2-04 的 reference 配置采用独立版本类，不能给既有 M1 FastDynamicsConfig 的默认序列化悄悄增组；M2-06 才启用完整新 writer/reader 分派。既有SITL接口、六维特征、原TaskSpec/编译路线/注册阈值不变。新事件和版本字段须同步消费方，不能只升级writer。

保留的后续实现验收条件：数值求积和根隔离满足误差规格；真实闭环的几何/顺序/能力及h与h/2检查通过；高度故障实际满足论证条件并完成原3D终点；版本化normal/fault完整链和M1旧读取实际通过。若不满足，保留失败并回到设计复审，不能改阈值或假造完成。当前静态模型不保证上述动态结果。新校准/盲测仍不在本轮访问范围，M3前参考episode采集与隔离仍需单独解决。

本轮停止在M2-03设计和静态证据修复。详细B1–B14见[测试规格](M2-03_test_spec.md)，执行范围、失败记录与身份见[修复报告](M2-03_report.md)。更完整场景需求另列环境建模任务，不修改冻结12格或混入本轮基础契约修复。

