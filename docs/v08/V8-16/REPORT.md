# V8-16 过境单段：执行报告

> **执行方：** Claude Code，模型 Claude Opus 5.5（`claude-opus-5-5`）。本项没有配置任何模型接入。
> **依据：** 《V8-16_过境单段_执行指令_20261105.md》（下称"指令"）与《V8-16_GPT指令评价与裁定_20261105.md》（下称"附录"）。附录与指令冲突处以附录为准。两份原文归档在仓库根 `claude/v08/`。
> **基线：** `ed44227aad3fdeeef05d4d2af5e03d91255a4054`（= `origin/dev/v0.8`，第 1 部分实测）。
> **分支：** `review/v08/V8-16-transit`，从 ed44227 新建。
> **外部运行根 `<V16_RUN>`：** `F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-05_V8-16_transit\run\`。

## 0. 开工前复述

### 0.1 部分划分

用户与附录说"八个部分"。指令开头的表格实际列了 9 项，第 9 项是"报告、提交、推送"，对应第 11 节。下面按指令完整列出 9 项，前 8 项是实质工作。

| 部分 | 内容 | 放行条件 / 交付 |
|---|---|---|
| 1 | 审查分支、输入登记、冻结快照 | `manifest.json`：commit、开发集与配置散列、源接口 blob、环境、基线目录，20/200/100/5 键；旧测试基线失败清单 |
| 2 | 意图分派（合同、骨架、优化语义、运行器）、圈层上限表、监视 20 合同字节门禁 | 监视 base 约束与旧函数在名字、顺序、几何、sense、余量上逐项相等；监视 20 合同 24 进程与 `full_v14c` 逐字节一致 |
| 3 | 过境可行弦集合、队形选择、夹持三次样条曲线 LP、进出场与时间分配 | 单次 attempt 只构造一次：抽一格、一次 LP、失败结束本 attempt；LP 不可用回退同格直线 |
| 4 | 过境预筛 `screen_transit_member`/`check_transit`、冻结核验接入、预置与自加测试 | 预置测试原样落盘并登记 SHA256；保存后从磁盘轨迹重读做独立核验 |
| 5 | 200 合同只骨架（24 进程）——**止损检查点** | 成功率 ≥95%、档差 ≤10 pp、成功合同骨架 attempts 中位数 ≤1、shape_audit ≤5%；**附录新增：成功骨架中直线回退比例 ≤50%** |
| 6 | 20 合同全链路（24 进程）——**止损检查点** | 成功 ≥16/20、成功合同 post-opt 失败中位数 ≤0、optimization_s 中位数 ≤60 s、保留段 P0 违规 0 |
| 7 | 200 合同 + 100 多样性种子全量；5 合同单进程复跑；穿越段 Fréchet；时长/速度；监视—过境逐格配对 | full 检查点（成功率 ≥80%、档差 ≤20 pp、post-opt 中位 ≤0、Fréchet 合并中位数 ≥1）；5 键 1 进程与 24 进程逐字节一致 |
| 8 | 四件小项：198 监视合同只读三阶段时长；两个低速例子的优化诊断；重访检测向量化（逐位相同才切换）；RUNNING 写 `--workers 16` | 低速诊断 optimized.json 重算逐字节相同；向量化三方逐位对照 + V8-11 200 条回归 + 监视 20 字节门禁 |
| 9 | 报告、RUNNING、`reproduce.ps1`、逐部分提交，只推 `review/v08/V8-16-transit` 并核对远端 SHA | 不合并 dev，不推 main，不强推 |

### 0.2 禁止范围（指令 0.1–0.2）

- **冻结判据与配置：** `configs/v08/criteria_segment.json` 与冻结几何余量（限制区 35 m、不得进入圈层 10 m、世界 35 m；间距 3.25/3/2 m；掉头半径下界 15/8/25 m）不改。
- **优化器：** 求解形式、变量、初值、目标、尺度、缓冲、权重、迭代设置不改。只在 `optimize_segment` 外层接入意图分派；`solve_joint`、`Prepared` 的数值路径不改。
- **其他冻结代码：** `v08/sim/` 已有文件、跟踪引导、V8-11 核验器与 `task_v07/` 不改。重访向量化只限生成层 `nominal_checks.revisit`。
- **监视抽取：** 只机械提取公共函数，调用顺序、随机数消耗、数组顺序、字段名和序列化都不变；不借推广修监视生产缺陷。
- **只读对象：** 冻结工作树 `641a9b3`、`de4d115`，`SwarmData/v07_*`，既有 `full_v14c`。`llm` 环境不装、不升级任何包。
- **Git 操作：** 不推 main，不强推，不合并 dev；只提交本项文件，不 reset/rebase/stash，不覆盖既有输出。
- **不恢复"生成—检验—重画"：** 不恢复骨架间距拒绝、1800 s 时长拒绝、局部修复、下游失败退队形、attempt 内重抽弦或形状。正常失败只消耗唯一的 20 次全链路预算。
- **写入白名单：** 只写指令 0.2 节表中所列文件；`runtime_defaults.py` 不改，默认仍是 24。
- **生产缺陷与测试：** 生产缺陷只记录不修；预置测试不改预期。

### 0.3 四条停止条件（仅 U F.1 的 P0）

| P0 | 数什么 | 正常预期 | 触发即停 |
|---|---|---|---|
| P0-1 | 推广或抽取后，监视 20 合同目录与 `full_v14c` 同键比较（文件集合 + 全部字节，排除清单 `[]`） | 全部一致 | 任一差异：停止相关推广，保留 diff，查明后重跑 |
| P0-2 | **保留**尝试的实测间距、限制区、圈层违规，或冻结段核验与保存结论不一致 | 0 | 例如过境误按 monitoring 核验、失败存成 success：停止生产 |
| P0-3 | 固定 5 键 1 进程复跑与 24 进程输出逐字节比较 | 全部一致 | 停止发布本批结果 |
| P0-4 | 重访向量化在 V8-11 200 样本逐项结果或逐位对照上出现差异 | 0 差异 | **不切换**向量化，恢复原实现，**其余部分继续** |

第 8.3 节的监视字节门禁若因候选加速失败，先撤回候选，验证原实现仍一致后继续；原路径仍不一致才按 P0-1 处理。成功率、耗时类指标不另设停止条件。

### 0.4 三个昂贵批次前的止损检查点

- **第 5 部分（只骨架 200）：**
  - 成功率 <95%；
  - 任一非空人数档低于总体 >10 pp；
  - 成功合同骨架 attempts 中位数 >1；
  - shape_audit 失败 attempts / 全部骨架 attempts >5%；
  - **（附录裁定 1 新增）成功骨架中直线回退比例 >50%**。
  - 以上任一触发，即停在检查点、不进入第 6/7 部分。等号均不触发。
- **第 6 部分（快批 20）：**
  - 成功 <16/20；
  - 成功合同 post-opt 失败中位数 >0；
  - 全部 20 合同 optimization_s 中位数 >60 s；
  - 保留段 P0 违规 >0。
- **第 7 部分（全量）：**
  - 成功率 <80%；
  - 任一非空档低于总体 >20 pp；
  - 成功合同 post-opt 中位数 >0；
  - 穿越段 Fréchet 合并中位数 <1。
  - 触发后不删失败、不调阈值，停止新的昂贵扩展，完成已有结果报告。

### 0.5 我对附录三条裁定的理解

1. **裁定 1：弯曲段范围改用"已认证的行"界定。**
   - **原规则的问题：** 指令 3.4 要求"中心线在目标预警圈内余量 ≥ 10 + D"区间的每一行都有包含 h 的已认证单元。认证还要扣距离场误差 ε_f 与单元覆盖误差 q_cell，范围两端必然通不过，非目标预警边界也会让中段失败，结果几乎每个合同都回退直线。
   - **改为：**
     - 在该区间内逐行判定；包含 h 的单元通过认证的行，记为"已认证行"。
     - 曲线范围取已认证行组成的**最长连续段**，等长取靠前那段。
     - 段两端施加 δ = h、δ′ = 0，段外保持直线 δ = h，由原直线车道证书保证合法。
     - 段长 < 80 m（4 个 20 m 节点间隔）时本次用直线，原因记 `curve_range_short`。
     - 其余（控制点区间约束、导数约束、精确复核）照指令。
   - **影响范围：** 只改 `corridor_rows` 的范围选取；预置 `curve_lp` 用例不受影响。报告新增"已认证段长度 / 预警内缩区间长度"的分布。
   - **新增止损项（第 5 部分，不是 P0）：** 成功骨架中直线回退比例 **>50%** 即停在检查点，报告 `corridor_unavailable` / `curve_range_short` / `lp_infeasible` 的分布。恰为 50% 不触发，分母是成功骨架合同。
2. **裁定 2：弦集合按单车道缓存。**
   - **单车道缓存：** 对每个（族，目标，航向，偏移）只算一次单条直线的结果，包括各约束余量沿线区间、目标预警交点、集合候选、终止站点。
   - **组合检验：** 队形检验改为各车道（偏移 h + d_i、纵向平移 l_i）对单车道结果的查表与区间运算。
   - **门禁：** 组合结果须与直接按全部车道计算的结果逐格相同，在 5 个目标 × 3 种人数上全量比对；不同就弃用组合、退回直接计算。
   - **报告：** 预建总耗时和每目标耗时；超过 30 分钟只记录，不停。
3. **裁定 3：两处确认。**
   - **梯形二分：** 步长可能不单调；沿用监视二分顺序，只保证返回值确实可行，报告二分探测日志。
   - **初始进场：** 沿用旧 `_route` 的有限候选（4 类 delta、每类最多 6 个连接候选），不重写；路由查询次数单独统计，不与骨架 attempt 混算。

## 1. 第 1 部分：分支、快照与基线（2026-11-05 17:38 → 17:52）

**结论：** 审查分支从固定 SHA 新建；输入、基线、名单齐全，未发现缺失输入。

- **分支：**
  - `git fetch origin refs/heads/dev/v0.8:refs/remotes/origin/dev/v0.8` 后，`ed44227^{commit}` 与 `origin/dev/v0.8` 均为 `ed44227aad3fdeeef05d4d2af5e03d91255a4054`。
  - `git switch -c review/v08/V8-16-transit ed44227aad3f…` 后 HEAD 为同一完整 SHA。
  - 该分支此前不存在；工作区干净，没有用户改动需要保留。
- **源接口身份：** 指令 10.1 表中 29 个文件的 git blob SHA 与本地 `HEAD:` 逐一相同，记录在 [manifest.json](manifest.json) 的 `source_blobs`。
- **预置测试：** 用 [extract_presets.py](extract_presets.py) 从指令原文按"保存为 …"后第一个 python 代码块原样提取（UTF-8、LF、末尾一个换行），4 个文件的 SHA256 与指令 9.1 表格逐一相同：

| 文件 | SHA256 |
|---|---|
| `test_preset_numeric_v16.py` | `ac15bce9…eaf4` |
| `test_preset_local_geometry_v16.py` | `6eb8c7b8…1be3` |
| `test_preset_local_revisit_v16.py` | `f3110c44…2b36` |
| `test_preset_local_artifacts_v16.py` | `7c17eee4…e2ca` |

- **manifest：** [manifest.json](manifest.json) 由 [make_manifest.py](make_manifest.py) 生成，包含 commit、开发集（40 族）与各族输入 SHA256、5 个配置 SHA256、29 个源 blob、环境版本、默认进程数 24。
  - **基线 `full_v14c`：** 8551 个文件，树摘要与 `records.json`/`summary.json` 散列；200 合同、198 保留。
  - **监视骨架基线：** `skeleton_v14b`，即 V8-14b 接受的那一批。
  - **V8-15 快批名单：** `part7/quick_selection.json`。
- **名单（全部沿用现有运行器的选择算法）：**
  - 快批 20 = V8-15 `select_quick` 结果：o01–o09、o11 各 d0/d1，全部在基线中存在；
  - 全量 200 = 40 族 × d0–d4，与 `full_v14c` 的 200 个 contract_id **完全相同**；
  - 多样性 100 = `select_diversity_families` 的 10 族 × branch 0–9（draw 0）；
  - 复跑 5 = (order, draw) 字典序前 5：o01_d0–o01_d4。
- **冻结快照：** [snapshot_part1.json](snapshot_part1.json) 由 [snapshot.py](snapshot.py) 生成。
  - 160 个输入，与 V8-14 v14c 结束快照相同；两冻结工作树 641a9b3/de4d115 干净；`v07_*` 共 22 个目录。
  - `full_v14c` 8551 个文件逐个 SHA256/大小/mtime。
  - 模块 208 个文件（configs、v08、tools/v08、tests/v08、scripts/v08、task_v07）。
  - **细粒度不变量**：用 AST 取 `check_monitoring`、`solve_joint`、`Prepared`、`prepare_problem`、`monitoring_constraints`、`nominal_checks.revisit`、`screen_member` 的源码段 SHA256；另列 26 个旧预置测试文件。
- **环境（[env.txt](env.txt)）：** PowerShell 7.6.9；Python 3.12.3；NumPy 2.5.3；SciPy 1.14.1；shapely 2.0.7；AMD Ryzen 9 9950X3D（16 核 32 线程）；63.65 GB。
  - SciPy 导入时有既有的 NumPy 版本警告，与 V8-15 相同，不装不改。
- **旧测试基线（[part1/tests_baseline.txt](part1/tests_baseline.txt)，第 2 部分改动前）：**

| 套件 | 结果 |
|---|---|
| V8-15 numeric/formation/injection/stress/defaults | 5/5、4/4、3/3、1/1、2/2 |
| V8-11 全目录 | 30/30 |
| V8-12 全目录 | 37 通过、2 失败、1 跳过（与 V8-15 同名同因） |
| V8-12（设数据根） | 39/40，只剩历史 `frechet` 预期失败（R15 维持已知失败） |
| V8-13 numeric / extra | 20/20、8/8 |
| V8-14 numeric / extra / local_geometry | 17/17、14/14、1/1 |
| V8-16 numeric / geometry 预置 | **导入失败**（新模块尚未实现，记"前提未完成"，不算失败也不算通过） |
| V8-16 revisit 预置 | **4/4 通过**：它对照的 `nominal_checks.revisit` 此时还是原实现，与冻结检测器逐位一致；这只说明原实现等于冻结版，不是向量化的证据 |

## 2. 第 2 部分：意图无关的外层，监视不变量（提交 49fbed6）

**结论：** 合同、骨架、优化语义、段核验、运行器都已按意图分派，监视原路径与序列化不变。监视 20 合同第一道字节门禁 20/20 逐字节一致，**P0-1 未触发**。

### 2.1 改动与新接口

| 文件 | 改动 |
|---|---|
| `v08/motion/layer_limits.py`（新） | `layer_limits` 只读 `criteria_segment`，缺键报错；`constraints_for_task` 按 world、障碍原序、设施原序生成 base；`constraints_identity` 作通用缓存键 |
| `v08/contract/single_intent.py`（新） | `transit_mission` 先调旧 `monitoring_mission`，再只替换唯一 TaskSpec 的 intent；`validate_single_mission` 复用旧 `validate_mission`；其他意图抛 `ContractInvalid` |
| `v08/motion/intent_dispatch.py`（新） | `skeleton_builder` / `semantic_checker` / `nominal_screen` 按模块属性取函数；`skeleton_intent` 从骨架见证取意图，缺省为 monitoring |
| `v08/motion/plan.py` | `plan_attempt` 改为 `skeleton_builder(task.intent)(...)`，监视仍是旧函数本身 |
| `v08/motion/optimize.py` | `optimize_segment` 开头按骨架意图分派，监视分支函数体不变；新增 `_optimize_segment_intent`（同一 `JointProblem`、同一 `solve_joint`；turns 为空；语义结果放 `semantic`；失败 stage = `optimize_<intent>`） |
| `v08/motion/intents/monitoring.py` | `monitoring_constraints` 的 base 改由 `constraints_for_task` 生成，patrol/warnings 不变；`_lane_points`、`_proxy_prims`、`_inward_start`、`_count`、`_route`、`_plan_starts` 的函数体逐字搬到 `shared_routes.py`，旧名保留为转导出或包装（`_route` 传原 `skeleton_planner`，`_plan_starts` 传原 `_route`） |
| `v08/motion/shared_routes.py`（新） | 上述机械抽取；`route_to_slot(..., planner_factory)`、`plan_starts(..., route_fn)` |
| `v08/runner/joint_monitoring.py` | `attempt_chain`：段核验 `SegmentTask(0, task.intent, ...)`；`skeleton_detail` 遥测按意图取 |

### 2.2 圈层表

- **六意图取值：** 预置 `test_six_values_and_seventh_unsupported` 通过，transit/monitoring/area_search/close_observation 为 1，feint 为 2，intrusion 为 3，非目标设施都为 1。
- **detour：** 固定配置没有该键，抛 ValueError，不补造取值（指令第 12 节第 1 项）。
- **监视 base 不变：** 新旧 base 在名字、顺序、几何、sense、minimum 上完全相等，佯动、突入的反例也相符（预置 `test_monitor_constraint_identity_and_counterexamples`）。
- **route 缓存：** 过境的 route 距离场缓存名为 `("route", intent, 有序约束身份)`，监视仍用 `"route"`。这只是进程内对象；原始距离按几何键共享磁盘缓存，所有批次前后缓存目录都没有改动。

### 2.3 监视字节门禁（V8-15 名单入口，真实 24 进程）

| 门禁 | 代码状态 | 结果 | 证据 |
|---|---|---|---|
| 第一道 `monitor_regression_2` | 49fbed6：推广 + 路由抽取 | 20/20 文件集与字节一致，排除清单 `[]`；缓存 259 个文件不变 | [part2/monitor_regression_2/](part2/monitor_regression_2/) |
| 复跑 `monitor_regression_2b` | 3ed0731：第 3–4 部分在 `optimize.py`、`optimize_checks.py`、`nominal_checks.py` 末尾追加了过境函数，这些文件在监视调用链上，所以再验一次 | 20/20 一致，缓存不变 | [part2/monitor_regression_2b/](part2/monitor_regression_2b/) |

第 8.3 节最终候选切换后还有第三道门禁，见第 8 节。

**旧测试（第 2 部分改动后的快速复核）：** V8-15 注入 3/3、队形 4/4、压力 1/1，V8-13 numeric 20/20（含监视源码 AST 检查），V8-14 local_geometry 1/1，V8-11 30/30。完整回归见第 9 节。

## 3. 第 3 部分：过境可行集合与直接构造（提交 3ed0731、1eba927）

### 3.1 实现要点（对应指令 3.1–3.5、附录裁定 1–2）

- **弦集合：**
  - 航向 0–340°，每 20° 一个；偏移 h = 5k m，范围取目标 warning 外接框在 n 上的投影；沿线每 5 m 采样。只抽格点本身，格内不抖动。
  - 每条车道与每个设施 warning 的 {sdf ≤ c} 精确区间（c = +10、0、−10、+50），按 Circle 二次方程、凸多边形半平面、BufferedPolygon 的"多边形 ∪ 各边胶囊（矩形条带 ∪ 顶点圆盘）"三种几何分别求。
  - 沿线采样点上，base 约束距离场下界（已扣 ε_f）的最小值 ≥ q = 2.5 m 才算合格；连续合格的采样点组成合法区间。
- **可行格条件（全部真实车道）：**
  - 目标恰有一个正长度穿越，且深入 warning 至少 10 m；
  - 终点：从最后车道出圈的编组站点起每 5 m 一站，取第一个全员距所有 warning ≥ 50 m 的站点；
  - 集合站点：x_c = 最早入圈站点 − D，D ∈ {100, 110, …, 400}（复用监视 `_plan_ingress` 的 Ds 枚举）；要求目标 warning 有符号距离在 [50, 250] m，槽位满足原 collect_phys，车道从 min(槽位, 最早入圈前 210 m) 到终点合法；
  - 其他设施的 warning 要么整段离开 ≥ 10 m，要么完整深穿越。
- **抽取与检查：** 可行格用 `rng.integers(0, len(cells))` 均匀抽一格，集合候选再均匀抽一个；之后精确弦检查一次，失败记 `chord_exact_audit`、`shape_audit_failed=True`，不换格。
- **队形：**
  - 选择顺序为 `retreat_chain(mapped_start(prior))`；梯形沿用监视的二分协议（附录裁定 3.1，probe 日志见骨架记录的 `formation_steps`）。
  - 缓存键包含实际偏移集合，不同人数不会串用；同一组偏移换槽位顺序，查询身份相同。
- **曲线（附录裁定 1）：**
  - 在中心线目标 warning 内缩 10 + D 的区间内逐行判定：行是 5 m 网格上条带完整的行，列为 h + 2k，单元中心的距离场下界 ≥ √7.25。
  - 行内包含 h 的单元通过即"已认证行"；曲线范围取已认证行的最长连续段，等长取靠前那段。段长 < 80 m 记 `curve_range_short`，没有已认证行记 `corridor_unavailable`。
  - 夹持三次 B 样条 LP 只解一次：控制点走廊取支撑内条带的交集，斜率用一阶导数控制系数 ≤ tan75°，曲率用二阶控制系数 ≤ 20κ_max，L1 目标权重为 1，用 HiGHS 默认设置。
  - LP 无解，或走廊不可用、段太短时，用本格直线回退并记录原因。
  - 精确复核：曲率极值取跨端点与 δ'''(1+δ'²) − 3δ'δ''² = 0 的实根，并核查各车道的 κ/(1−dκ)。
- **进场：**
  - 机械复用旧 `_route` / `_plan_starts`；过境的 `entry_planner` 在原 blockers 之外加目标 warning 外扩 10 + Δ，`cg_route` 加 `preentry_warning:<target>` 的 10 m 约束（只用于首次入圈前）。
  - 路由查询次数单独统计，不计入骨架 attempt（附录裁定 3.2）。
- **候选检查（逐成员，精确）：** base 用 `polyline_clearance`；`crossing_analysis` 要求目标恰一入一出；终点离所有 warning ≥ 50 m。成员映射 `member_map_transit` 保存 reference_s → member_s 以及各成员自己的入/出圈弧长。

### 3.2 弦集合的耗时与附录裁定 2 门禁

- **向量化：** 首版逐车道调用求交与距离场，单个查询（o17 梯形）用 43 s。改为按航向批量计算解析区间、先过滤目标穿越再批量采样、候选 D 向量化后降到 9.5 s，可行格数不变（2086）。
- **组合 vs 逐车道直接重算（5 个目标 × 3 种人数，横排 1/⌈n/2⌉/n 机）：**
  - 首次运行 [chord_gate_r1_failed.json](part4/chord_gate_r1_failed.json)：n = 1 的 5 组一致；n > 1 的 10 组格数相同但内容不逐位相同。
  - 原因是我的实现缺陷：单车道缓存用 1e-9 舍入的偏移作键，而且就在舍入后的偏移上计算车道。
  - 改为以精确浮点偏移作键后重跑 [chord_gate_r2.json](part4/chord_gate_r2.json)：**15/15 逐格相同**，因此采用组合检验。
- **预建耗时：** 见第 5 节（178 个查询，累计 7693 CPU·s，24 进程墙钟 448 s）。

### 3.3 偏离与待审

1. **预建并行：** 指令写的是"主进程在派发前预建"。实测单个查询 1.5–300 s、共 178 个，单进程约 2 小时，所以改为派发前由 24 进程并行预建：每族一个任务、写各自的文件，没有并发写同一文件。派发阶段 worker 只读，缺失时进程内计算、不写回。第 5 部分 200 次读取全部命中，0 次现场计算。
2. **210 m 预留的解释：** 我要求每条车道从 min(槽位, 最早入圈前 210 m) 起合法，比只要求从槽位起更保守。
3. **精确弦检查的对齐比较（第 5 部分首跑发现的缺陷）：** 首版用严格 `< 100 m`，在 D = 100 的边界候选上把 99.99999999999966 m 判为不足，与冻结 `crossing_analysis` 的 1e-6 节点容差不一致。已改为同一容差（1eba927），第 5 部分在新目录重跑，见第 5 节。

## 4. 第 4 部分：过境预筛、核验与测试接入

- **`screen_transit_member`：** 条件为：首帧在目标圈层 0；进入过 warning；目标层 ≥ 1 的连续段恰 1 个；目标最大层恰为 1；其他设施 ≤ 1；全窗口 dwell 未检出；全窗口 revisit 未检出（冻结 eligible 规则不变）；末帧所有层为 0。另记按 work_mask 调用的冻结原条件。
- **`check_transit`：** 时间网格照录 `check_monitoring`；检查 `crossing_analysis`（全部 warning、完整曲线）、目标恰一入一出、终点 ≥ 50 m，以及上述预筛条件。不调用"必须重访"。
- **冻结核验：** `attempt_chain` 用 `SegmentTask(0, "transit", target)` 调 `verify_segments`，再调 `visible_track` + `check_validity`，两项都实际调用。保存后由第 6/7 部分的预置 artifacts 测试从磁盘重读核验。
- **序列化：** 过境 `contract.json` 带 `intent="transit"`，`result.json` 带过境语义字段与 `phase_durations`，失败见证用 `semantic_failures`；监视 serializer 没有改。
- **测试（[part4/](part4/) 日志见第 9 节）：**

| 文件 | 结果 |
|---|---|
| `test_preset_numeric_v16.py`（预置） | 9/9 |
| `test_preset_local_geometry_v16.py`（预置） | 6/6 |
| `test_preset_local_revisit_v16.py`（预置） | 4/4；此时 `nominal_checks.revisit` 仍是原实现，切换后重跑见第 8 节 |
| `test_extra_numeric_v16.py`（自加） | 6/6：非均匀末跨导数系数与 SciPy 一致、LP 端点控制值固定、查询身份区分人数且与槽位顺序无关、新 CLI 默认 24 / 显式 16、200 键外连接、斜率上界 |
| `test_extra_local_v16.py`（自加） | 7/7：BufferedPolygon 圆角精确求交、纵列参考覆盖不 clamp、格索引只抽一次且审计失败不换格、进场失败不换格不换队形、多次进入/首帧在内/从不进入、Fréchet 先截后重采样、**真实 o01_d0 注入语义失败 → 下一 attempt 成功、落盘轨迹过冻结核验** |

- **全链路冒烟（开发期，scratchpad 输出，不作证据）：** o01_d0、o08_d4 首个 attempt 成功；o34_d2（12 机）第 0 次 `optimize_transit/nominal_dwell` 失败、第 1 次成功，实测最小间距 3.287 m。

## 5. 第 5 部分：200 合同只骨架——止损检查点

**结论（以修正后的 r2 为准）：** 200/200 成功，成功合同骨架 attempts 中位数 1，shape_audit 0/207，人数档差 0；**直线回退 1/200（0.5%）**。全部止损项（含附录裁定 1 新增的 > 50% 直线回退）都未触发，进入第 6 部分。

| 运行 | 代码 | 成功 | attempts 中位 | shape_audit / 全部 attempts | 直线回退 | 档差（1–4 / 5–8 / 9–12 机） | 证据 |
|---|---|---|---|---|---|---|---|
| 首跑 `skeleton_transit` | 3ed0731 + 精确键修正（提交 18:43） | 200/200 | 1 | 3/209（1.4%） | 1/200 | 0 / 0 / 0（n = 110/56/34） | [part5/](part5/) |
| **r2 `skeleton_transit_r2`** | 1eba927（对齐容差修正） | **200/200** | **1** | **0/207** | **1/200** | 0 / 0 / 0 | [part5/r2/](part5/r2/) |

- **为什么重跑：** 首跑的 3 次 shape_audit 都是 chord_exact_audit，原因是 `straight_m = 99.99999999999966 < 100`，即第 3.3 节第 3 项的工具缺陷。这是新工具的实现错误，按指令修复后在新目录重跑受影响的测量；首跑目录与结果原样保留。
- **失败 attempt（r2，7 次）：** `start_route` 3 次、`boundary_crossing` 4 次（`graze_or_touch_band`，起点路由圆角贴近某设施的 warning 带）。都是初始进场与路由的问题，符合"失败主要在初始进场/撤离"的预期，都在下一 attempt 成功。
- **队形（prior → realized）：** abreast → abreast 62、column → column 46、echelon → echelon 47、loose → abreast 45。**退让 0**（预期允许为 0）。梯形实际步长 15.2–24.3 m，二分 probe 日志在 records 的 `formation_steps`。
- **曲线：**
  - 直线回退 1 例：o34_d1，原因 `corridor_unavailable`。
  - 横向偏离 max|δ − h|：min 0，p10 102，中位 263，p90 660，max 1079 m。U C.2 原型的 63–505 m 只作参照。
  - 已认证段长 / 内缩区间长：中位 0.979，p10 0.910。
- **耗时：**
  - **预建：** 178 个查询，首跑新写，24 进程墙钟 448 s，累计 7693 CPU·s；按附录裁定 2 只记录，> 30 min 也不停。
  - **派发：** 200 合同 29 s。单 attempt 墙钟中位 1.6 s、p90 5.5 s、最大 23 s；弦集合读取中位约 0.01 s。
  - **worker 读缓存：** 200 次全部命中，现场计算 0 次。
- **路由查询（不计入 attempt，附录裁定 3.2）：** direct:proxy 2209、direct:fillet_fit 201、skel10:fillet_fit 902、skel30:fillet_fit 124 等，见 summary 的 `route_queries`。
- **缓存：** 首跑只新增 178 个 `transit_v16/*.json`，原有 259 个距离场文件未变；r2 前后缓存完全不变。

## 6. 第 6 部分：20 合同全链路——止损检查点（r2，2026-11-05 19:02 → 19:11）

**结论：** 20/20 成功；成功合同 post-opt 失败中位数 0；全部 20 合同 `optimization_s` 中位数 8.8 s；保留段 P0 违规 0。**四项都未触发，P0 未触发**，进入第 7 部分。

- **名单：** `select_quick` 既有协议重算，与 manifest 的 20 键完全一致（o01–o09、o11 各 d0/d1）。用新入口真实 24 进程派发，单合同动态分配。
- **attempts：** 18 个 1 次成功；o02_d1、o03_d1 第 0 次骨架失败、第 1 次成功（post-opt 失败 0）。全部 20 合同都是曲线穿越。
- **`optimization_s`：** 1.8–36.3 s。各环节合计 CPU：优化 216 s、仿真 215 s、骨架 90 s、核验 16 s；派发墙钟 82 s。
- **预置 artifacts 测试（[part6/tests_artifacts_quick.txt](part6/tests_artifacts_quick.txt)）：**
  - `test_completed_keys_and_paired_common_fields` 通过：20 键、intent = transit，公共字段与监视同键合同全同。
  - `test_retained_disk_tracks_with_frozen_verifiers` 通过：从磁盘重读轨迹，冻结 `verify_segments(transit)` 与 `check_validity` 全过，最小间距 ≥ 2 m。
  - `MonitoringRegressionPreset` 通过：`V8_16_MONITOR_REPEAT` 指向 monitor_regression_2b/run。
  - 5 键复跑测试此时 **skip**（复跑尚未运行），不计为通过；第 7 部分后实际执行。
- **中断记录：** 首次快批 `out/quick_transit` 用的是修正前代码；发现对齐容差缺陷后，我在预建阶段停掉了它（目录中只有 `quick_selection.json`）。目录原样保留，重跑写入 `quick_transit_r2`。
- **耗时备注：** 快批与 r2 骨架的预建在文件都已存在时仍各用约 476 s。原因是 `_prewarm_family` 为构造 probe 序列把 `cache_dir` 置空，导致在内存中重算一遍。只浪费时间，不影响输出；第 7 部分完成后再处理，见第 9 节。
