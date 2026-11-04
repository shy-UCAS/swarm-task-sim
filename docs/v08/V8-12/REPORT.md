# V8-12 监视单段：报告

执行日期 2026-11-03 起。开发工作树 `Simulation-v08`，审查分支 `review/v08/V8-12-monitoring`。
本报告随各部分逐步补全；最终的提交号以 `git ls-remote` 输出为准（见对话回报）。

## 结论（先看这里）

**状态：第 1–4 部分完成；第 5 部分已按用户指示取消（改用联合时空优化方案），未完成。** 取消前已完成 35 个合同的仿真与核验（快速 10 + 全量 25），全部通过段核验与有效性检查，汇总见 `part5_partial.md`；全量还有 140 个合同未运行。

- **第 4 部分数字（登记的 40 个开发族 × 5 draw = 200 合同，单进程、只规划）：** 规划成功 **176/200 = 88.0%**；按设施数 1/2/3 档 83/85 = 97.6%、66/85 = 77.6%、27/30 = 90.0%（最大差距 10.35 个百分点）；失败 24 个合同**全是 `budget_exhausted`**（每个的最主要 attempt 级原因都是 `duration_budget`），没有 `proven_infeasible`、没有 `approx_empty`；每合同净规划用时中位数 **13.2 s**（p95 111 s）。
- **逐条止损：** `success_rate` 88.0% ≥ 80%、`facility_gap` 10.35 < 20 个百分点、`failure_evidence` 无对象、`planning_time` 13.2 s ≤ 30 s、`frechet` 合并中位数 119（< 1 才触发）——**均未触发**。但 `frechet` 的数据**不完整**：10 个多样性族里 order 2、order 10 各只取得 9/10 个成功种子（失败种子 `o02_d0_b6`、`o10_d0_b0`，`duration_budget`），按指令 4.3 不能拿少量路径通过，所以检查点返回"未完成"（CLI 状态 3）。我把它当作"缺失 → 检查未完成"而不是自行豁免，因此当时**没有进入第 5 部分**。后续：规划审查方 2026-11-03 裁定「两个缺种子的多样性族按失败报告、不补种子，检查点视为完成、未触发」并放行第 5 部分；之后用户取消了第 5 部分（见下一条）。
- **预置测试：** `test_preset_numpy_geometry` 4/4、`test_preset_numpy_motion` 7/7、`test_preset_local_monitoring` 3/3、`test_preset_local_devset` 1/1 通过；`test_preset_numpy_checkpoint` 3/4，**1 项失败 = 疑似预期错误**（`test_each_diagnostic_threshold` 的 Fréchet 断言按指令 4.4 的"逐族"语义写，与附录补充裁定"合并中位数 < 1"冲突；我按附录实现、没有改测试）。`test_preset_local_simulation.py` 在第 5 部分放行后按原文放入（SHA256 `ef4acb7a…08f3` 一致），运行 1/1 通过（33.9 s）；审查方 11-03 裁定接受 checkpoint 那 1 项失败（指令修订，不改测试）。
- **独立复核：** 176 个成功合同的 803 条成员曲线用 shapely 重算全局物理约束（world 内缩、限制区、alert、终点离预警圈、总时长、延迟网格），0 个问题，最小余量均满足。
- **必须知道的限制：** (1) 构造在这 40 个评估族上迭代过 6 轮（59.5% → 88.0%），88.0% 不是对新场景的无偏估计；(2) 1800 s 预算在多数成功合同里是约束（103 个用了半径内移、24 个降圈数、10 个降穿行次数），生成的环半径分布因此被压向小半径；(3) 成功合同的实际队形明显偏向纵列（58%，抽签倾向只有 24%）；(4) v0.7 同条件参照**缺失**（开发族的监视样本只有 4 条，且都不在多样性的 10 个族里）；(5) 近似为空与精确复核的四类对照本次全是 0（没有合同走到那一步）。
- **边界：** 冻结工作树（`641a9b3`、`de4d115`）与 `SwarmData\v07_*` 未被写入，160 个登记输入文件的 SHA256/大小/mtime 前后一致；没有推 `main`、没有强制推送。
- **第 5 部分（已取消，未完成）：** 快速 10 合同完整跑完：10/10 保留，10/10 同键复跑逐位一致，无候选失败，用时 1618 s。全量（`--rerun-every 4`）在 166 个队列合同中完成 25 个，第 26 个（`o31_d0`）仿真中途被终止，其余 140 个未运行。**已完成的 35 个合同：** 35/35 通过段核验和有效性检查；实测最小间距（10 Hz 采样）最小 3.450 m（门禁 ≥ 2 m），限制区内帧、世界外帧、非目标设施 alert 以上帧均为 0；跟踪偏差在快速 10 个合同里最大 0.286 m，但全量里 `o17_d0` 的 5 个成员各有 8–9 帧超过 0.5 m（最大 0.589 m，共 41 帧，首次超出都在约 (2828, 2733) m 附近；诊断项，不触发重做，合同仍保留）；复跑一致 17、待复跑 18（按规则未选中）、不一致 0。这是 35/176 的样本（19.9%），按 draw 轮转的顺序取到的是各族的 draw 0，不能当作全部合同的通过率，也没有失败样本可供分析失败条件。详见 `part5_partial.md`。
- 输出目录：`_handoff\2026-11-02_V8-12_monitoring\out\plan`（原始合同，不入库）；汇总、多样性、失败原始记录在 `docs/v08/V8-12/part4/`。

## 1. 开工复述与执行前提

**依据文件（均在 `_handoff\2026-11-03_V8-12_monitoring\`）：**

| 文件 | SHA256 |
|---|---|
| `V8-12_监视单段_执行指令_20261102.md`（2079 行，下称"指令"） | `87b0df5de7da7013d38d549f7cf12f60c4d64a5d72dc422c203cc90e68daa9eb` |
| `V8-12_GPT指令评价与裁定_20261103.md`（54 行，下称"附录"） | `0ed611496f985307957dce4a81a145a889891907320cf8b1f1574a803dcbd0ee` |

附录第 3 节的裁定优先于指令的对应内容（含指令第 9 节的 14 项和 4.4 节 Fréchet 止损）；其余以指令为准。

### 1.1 目标

在 V8-03 登记的 40 个开发族上，对每族做 5 次公共抽签（共 200 个合同），每个合同只有一个编组（取公共抽签的第 0 组）、一个任务段，`intent="monitoring"`、`final=True`。链路是：场景上下文 → 公共抽签 → 监视合同 → 首段汇合 → 监视规划 → **只规划止损检查** → 逐成员仿真 → 拼接 → V8-11 的段核验与实测有效性检查。不做多段、多股、组内差异、标签时间线或正式数据集生产。

### 1.2 五个部分

| 部分 | 内容 | 提交信息 |
|---|---|---|
| 1 | 快进合并 V8-11（固定提交 `4d2cf5df…`）、推送 `dev/v0.8`、建审查分支、基线测试（V8-08 与 V8-11 预置测试）、归档指令 | `V8-12 第1部分：合并V8-11与基线检查` |
| 2 | 场景上下文、NumPy 精确有符号距离、5 m 距离场、空集分类与同心环带证书、缓存；测试 `test_preset_numpy_geometry.py`、`test_preset_local_devset.py` | `V8-12 第2部分：场景上下文与精确几何` |
| 3 | 合同与公共抽签、监视运动（周期 B 样条绕圈、折返、队形、汇合/穿越/出口连接、速度剖面、名义时钟、连续时间间距、20 次预算）；测试 `test_preset_numpy_motion.py`、`test_preset_local_monitoring.py` | `V8-12 第3部分：监视单段构造与规划检查` |
| 4 | 40 族 × 5 合同只规划、同条件 10 族 × 10 种子多样性、止损检查点；测试 `test_preset_numpy_checkpoint.py` | `V8-12 第4部分：只规划检查与止损结果` |
| 5 | 先 10 个合同、再其余规划成功合同的仿真、拼接、段核验与有效性检查、同键复跑逐位比较；测试 `test_preset_local_simulation.py`。只有第 4 部分完整执行且未触发止损才开展 | `V8-12 第5部分：监视仿真与核验结果` |

### 1.3 P0 停止条件（指令 0.5）

1. 写入冻结目录、改变已读 `SwarmData\v07_*` 数据的内容或 mtime，或本任务造成冻结工作树变化：立即停止写操作，保留现场。
2. 修改预置测试、冻结判据或禁止范围，或把失败结果冒充通过：停止依赖部分，推送现场与报告。
3. 输入 SHA256 不符、成员/设施引用错、圈层显式几何与冻结核验语义不一致仍继续标注：不生成受影响合同，报告原始证据。
4. 时间线有重复帧或空洞，或同键同环境确定性载荷复跑不逐位一致：停止该批次。
5. 快速 10 合同中出现段核验/实测物理有效性的 P0 错误，或全量中把不合格段保留为成功：快速批次停在首个此类错误；全量非法保留属批次停止错误。
6. P0 预置测试失败，或必要前提使该测试无法证明所保护结论：暂停依赖链，不改测试，记录疑似预期错误。

普通候选失败（核验不过、间距不足、仿真超时）不属于 P0，在 20 次预算内重做。第 4 部分的诊断性止损和第 5 部分的两小时资源边界不属于 P0。

### 1.4 第 4 部分止损阈值（诊断性，任一触发则停在第 4 部分，不做第 5 部分；比较一律严格）

| 条件名 | 触发条件 |
|---|---|
| `success_rate` | 总成功率 < 80%（规划成功合同数 / 200；160/200 本身不触发） |
| `facility_gap` | 某设施数档成功率比总成功率低**超过** 20 个百分点（Fraction 相减，与 `Fraction("0.20")` 比较；恰好 0.20 不触发） |
| `failure_evidence` | 存在 `proven_infeasible` 却没有几何见证，或精确复核非空却记为 `proven_infeasible` |
| `planning_time` | 每段规划耗时中位数 > 30 s |
| `frechet` | 见 1.7 的附录补充裁定（取代指令 4.4 的"逐族任一触发"） |

缺失或待决数据返回"检查未完成"，不当作"未触发"。

### 1.5 不得修改的范围

冻结工作树 `Simulation-fe-prod-r3`（`641a9b3`）、`Simulation-fe-s3`（`de4d115`）；`SwarmData\v07_*` 只读；`task_v07/`、`scene_v07/`、`swarm_sim/`、`configs/criteria/`、`configs/fast_dynamics/`、`configs/generator/geometry_v07_r1.json` 只导入；`v08/sim/`、`v08/criteria/`、`v08/config.py`、`v08/sampler/keys.py`、`v08/diagnostics/diversity.py` 与其他已有文件、`configs/v08/` 已有文件、`tests/v08/` 已有测试不改不删；指令第 6 节预置测试和夹具原样放置；conda `llm` 只运行不装包；不给动力学加扰动，不做每机参数覆盖；不推 `main`、不强制推送，失败版本也推送审查分支；不得因失败换意图、换目标、缩小编组、删难场景或放宽判据。

### 1.6 附录第 3 节各项裁定：我的理解

| 项 | 裁定 | 我的理解与实现含义 |
|---|---|---|
| 1 纵列与 3 m | 同意 GPT | 纵列偏移 d = 0；不把 n 人纵列写成 (n−1)×3 m 宽度；成员对一律做连续时间 ≥ 3 m 检查（3 = 2 + 2×0.5，由冻结的 2 m 与跟踪管 0.5 m 推导，不另存常数）。 |
| 2 平滑曲率反号 | 同意 GPT | 只在**不连续**变号的接点（圆弧与圆弧、直线接圆弧等）插入 L = max(5 m, 0.6 s × 期望速度) 的直线；周期 B 样条的连续平滑反号不切断，但记录类型。 |
| 3 dataclasses | 同意 | 合同与计划用 `dataclasses`，不装 Pydantic。 |
| 4 精确几何 | 同意 | 距离、弦检查、距离场全部 NumPy 解析；shapely 只出现在 `v08/scene/visibility.py` 的函数内部，用于可视图骨架；图近似失败不能当作数学无解。 |
| 5 松散队形 | 裁定：按横排处理 | 监视段抽到 `loose` 时，从横排开始，仍走"横排 → 梯形 → 纵列"退让链；记录 `formation_prior=loose`、起点 `abreast`、`mapped_from_loose=true`，并保留最终实际队形与退让链。**我的理解：** "实际队形不同于抽签倾向"的统计中，`loose` 合同以映射后的起点（横排）为比较基准，否则所有 loose 合同都会被计为退让；两种口径的计数都会在第 4 部分列出。这条使指令第 9 节第 5 项不再"执行待决"，含 loose 的合同可以正式生成。 |
| 6 泊松事件映射 | 简化，不用不动点迭代 | 事件按时间先后逐个处理：第 k 个事件用"只含前 k−1 个变速点"的速度剖面算名义时间表，映射到名义时间不早于事件时刻的第一个参考节点，再把该变速点加入剖面。顺序确定、无循环；映射误差（事件时间与节点名义时间之差）仅作诊断。 |
| 7 Fréchet 成本 | 计算前重采样到 5 m | 多样性计算前，用 V8-05 的 `resample_polyline` 把参考路径重采样到 5 m 弧长间隔后再算离散 Fréchet；这是测量离散化（误差 ≤ 2.5 m），只作诊断，不进入生成，不改变阈值。 |
| 8 障碍与限制区余量 | 更正（P0：物理有效性的构造余量） | `hard_constraint_obstacle`（场景里的限制区）的外侧余量用 **35 m**（`obstacle_margin_m`，对应 v0.7 `free_space.py` 第 168–171 行）；10 m（`forbidden_margin_m`）用于本段**不得进入的圈层**，即目标设施与非目标设施的警戒层（及保护层）边界。指令 2.4 节写的"限制区外侧至少 10 m"据此更正为 35 m；world 内侧 35 m 不变。 |
| 9 地图尺寸 | 同意 GPT | 最大边长 6750 m；按 world 几何动态建栅格，不设 5750 m 上限。 |
| 10 快速 10 合同的停止语义 | 裁定 | 普通候选失败（核验不过、间距不足、仿真超时）照常在 20 次预算内重做，不停。只有这些情况才停快速批次：已保留为成功的段违反 D.5 的 P0 门禁（核验器或流程代码错误）、时间线不连续、同键复跑不一致、未捕获异常。 |
| 11 跟踪管 | 只作诊断，不触发重做 | 实测间距、限制区、圈层已由 P0 门禁直接检查；跟踪管横向误差只报告（最大值、p95、>0.5 m 帧数与位置），不作为重做原因。 |
| 12 缓存位置 | 同意 | 缓存放在 `_handoff` 下（见 1.8）。 |
| 13 拥挤地图可行性 | 知悉 | 不为"简化"去掉非目标预警圈；实际可行性由第 4 部分检验，我不预先承诺成功率。 |
| 14 折返与重访 | 知悉，同意 GPT | 不降低掉头半径、不放宽 30 m 重访距离；折返回程每个成员必须在完整名义轨迹上真正取得一次合格重访见证。 |
| 补充：Fréchet 止损 | 改写 4.4 | 见 1.7。 |

### 1.7 补充裁定（Fréchet 止损）的理解

10 个多样性族中，对每一对路径（每族 45 对）计算"离散 Fréchet 距离 ÷ 该族 `lateral_spacing_m`"，把全部比值**合并**后取中位数；该中位数 **< 1**（严格）才触发 `frechet`。逐族的米值、比值中位数照常报告，仅作诊断，不新增常数。某族不足 10 个成功种子时，该族标记为未完成，整个检查点返回"未完成"，不用少量路径通过。

**预期的冲突，先记在此：** 预置测试 `test_preset_numpy_checkpoint.py::test_each_diagnostic_threshold` 的第 4 个断言把"单个族的中位数 19 m < 间距 20 m"作为触发 `frechet` 的用例，这是指令 4.4 的"逐族任一触发"语义。按附录补充裁定，9 个族比值为 1.0、1 个族为 0.95，合并中位数是 1.0，不应触发。两者无法同时满足。按指令 0.1 的规则，我**不修改测试**，`checkpoint` 按附录裁定实现；若该断言因此失败，记入"疑似预期错误"，由规划审查方裁决，其余测试照常运行。第 4 部分的止损评估按附录裁定计算。

### 1.8 其他说明

- **预置测试的来源：** 指令包只有上述两份 Markdown，没有 `preset\`、`reference\` 子目录。七个预置文件的代码块在指令第 6 节，我用脚本从 Markdown 中按标题逐字提取（UTF-8、LF、末尾一个换行），核对指令 6.9 节的 SHA256 后落盘，不手工转录。
- **路径不一致：** 指令包所在文件夹是 `_handoff\2026-11-03_V8-12_monitoring\`，而指令 0.4 节、第 8 节复跑命令里的缓存与输出路径写的是 `_handoff\2026-11-02_V8-12_monitoring\`（`cache\`、`out\plan`、`out\quick`、`out\full`、`out_rerun\plan`）。我按指令 0.4 节与第 8 节的字面路径（`2026-11-02_V8-12_monitoring`）写缓存与输出，使用户的复跑命令原样可用。
- **仓库里没有 `claude/` 目录，也没有 r4 设计文档的副本。** 指令第 0.2 节允许新增 `claude/v08/V8-12_监视单段_执行指令_20261102.md`（本指令的原样归档），我按此新建；r4 的具体章节只能依据指令里引用的内容，遇到指令未写明的细节按"记录并继续"处理。
- **实际模型：** Claude Sonnet 5.5（`claude-sonnet-5-5`）。指令建议强模型（Claude），符合。
- **本机估时（不是判据）：** 第 1 部分约 10 分钟；第 2 部分约 1–2 小时（含冷缓存建场）；第 3 部分是工作量最大的一部分，估计数小时的实现与调试；第 4 部分运行时间取决于 200 合同的重试次数，目前无法预估，冷缓存和多样性耗时将另列实测；第 5 部分有 2 小时壁钟上限。
- **环境：** Windows 11，PowerShell 7；conda 环境 `llm`（Python 3.12.3、NumPy 2.5.3、shapely 2.0.7；SciPy 1.14.1，导入时报 NumPy 版本警告：需要 <2.3.0，检测到 2.5.3；本项核心代码不依赖 SciPy）。

## 2. 逐部分结论（随进度补全）

### 第 1 部分：通过（提交 `e05dcf2`）

- `dev/v0.8` 快进 `2bbe8ad → 4d2cf5d`（固定提交 `4d2cf5df48187671f0dd9aa0018a69adac829911`），`git ls-remote` 核对远端 `dev/v0.8` = `4d2cf5df…`；之后新建 `review/v08/V8-12-monitoring`。
- 基线：V8-08 24/24、V8-11 预置测试 30/30 通过，完整输出 `docs/v08/V8-12/tests_part1.txt`。
- 指令原文归档于 `claude/v08/`（SHA256 与 `_handoff` 中一致）。

### 第 2 部分：通过

**实现（均在 `Multi-UAV SimpleGC/`）：**

| 文件 | 内容 |
|---|---|
| `configs/v08/monitoring.json` | 从指令 0.8 节代码块逐字提取（27 个参数；SHA256 `327ad911…ed69`），未改动 |
| `v08/scene/exact.py` | NumPy 解析有符号距离（圆、凸多边形、BufferedPolygon），面积质心，整条弦的 sdf 取值范围（Cyrus–Beck 裁剪 + 四类端点到边距离），凸多边形内缩，膨胀 |
| `v08/scene/field.py` | `Clearance`、`DistanceField`（5 m 栅格，双线性 − 半对角线）、`build_distance_field`、保守单元集合 `conservative_cells`（整格可证 + 四叉细分，子格用精确中心距离与当前格半对角线判定）、面积加权均匀抽点 |
| `v08/scene/context.py` | `load_context`/`build_context`：核对 `public_scene_sha256`、`family_initial_sha256`；读入时核对显式圈层几何 = 设施几何 + `offset_m`；SHA256 缓存键；NPZ 缓存精确距离栅格 |
| `v08/scene/visibility.py` | 可视图骨架适配器（NumPy 内缩 world、障碍/禁止圈转显式副本、`margin_m=0`），shapely 只在函数内部惰性导入 |
| `v08/contract/monitoring.py` | `Family`、`Failure`、`family_from_initial`、`ContractInvalid` |
| `v08/motion/feasible.py` | `classify_empty`、`prove_concentric_band_empty`、`certificate_valid`（从保存的原几何重算证书） |

**测试：** 预置 `test_preset_numpy_geometry.py` 4/4、`test_preset_local_devset.py` 1/1（40 族）通过；自加 `test_own_part2.py` 5/5、`test_own_imports.py` 1/1 通过。完整输出 `docs/v08/V8-12/tests_part2.txt`。

**第 2 部分发现的事实：**
1. `SwarmData\v07_scene`（及 `v07_*` 下大多数目录）是指向 `D:\T2L\SwarmData\…` 的 **NTFS 联接**。第一版输入守卫用 `Path.resolve()` 后检查是否仍在数据根下，因此对全部 40 族误报"越出数据根"，预置本地测试 40 个子用例全报错。已改为对 `directory_rel` 做字面检查（非绝对路径、无 `..`），读取仍经联接只读。**这对输出路径守卫的含义：** 指令 0.4 节要求拒绝"通过联接指向 `v07_*` 的路径"，所以输出/缓存路径守卫必须用 `resolve()` 后的实际路径（含 `D:\T2L\SwarmData\v07_*`）做检查，该守卫在第 4 部分的 CLI 中实现。
2. 40 族几何：多边形（设施、障碍、圈层、world）全部为凸；27 个圆形设施、42 个多边形设施；每族 1–3 个 `hard_constraint_obstacle`；显式圈层几何与"设施几何 + `offset_m`"逐族一致（0 处不一致）。world 全为四边形。
3. 输入读取前后快照（160 个文件，SHA256、大小、`mtime_ns`）完全一致，见 `docs/v08/V8-12/inputs_snapshot_part2.json`。
4. 距离场耗时：最大地图（边长 6750 m，1351×1351 栅格，7 个几何）冷缓存 4.27 s，热缓存 0.23 s；边长 4000 m（801×801，3 个几何）冷 0.42 s、热 0.03 s。

**实现取舍（记录，非偏离）：**
- `Clearance.sense` 在指令的 ±1 之外增加了 `0`（要离边界至少 `minimum_m`，内外皆可）。非目标设施的预警圈边界在巡逻中需要"不被穿越就保持 10 m"，用 `|sdf| − 10` 表示；`|sdf|` 仍是 1-Lipschitz，误差界不变。
- 可视图（顶点/邻接）当前每进程重建，不落盘；落盘的是精确距离栅格。指令 2.4 节写的是图也缓存，这一项未实现，若第 4 部分耗时需要再补。

### 第 3 部分：通过（提交号见第 8 节的 git 输出）

**实现（均在 `Multi-UAV SimpleGC/`）：**

| 文件 | 内容 |
|---|---|
| `v08/contract/monitoring.py`（追加） | `SpeedProfilePrior`、`TaskSpec`、`GroupSpec`、`CommonDraw`、`Mission`、`MemberPlan`、`SegmentPlan`、`initial_states`、`validate_mission`、`to_guided`、`monitoring_mission` |
| `v08/sampler/common.py` | `sample_common(family, draw_index)`：不接受意图/目标；组数 `min(U{1,2,3}, n)`，每组先 1 人再逐个均匀抽组，`permutation` 切片分配成员，每组速度 U[4,10]、变速率 U[0,1]、队形倾向均匀 |
| `v08/motion/path.py` | 周期三次 B 样条半径及一二阶导、直线/圆弧/五次 Bézier/样条弧图元的 0.5 m 采样、曲率上界与车道曲率检查、`connect_poses`、`opposite_arc_join`、`circle_offsets` |
| `v08/motion/formation.py` | 横排/纵列/梯形槽位、`loose→abreast` 映射与退让链、成员车道派生 |
| `v08/motion/speed.py` | 泊松变速事件抽取与按参考节点名义时间的固定点离散映射（循环检测） |
| `v08/motion/nominal.py` | 复用冻结 `make_curve/speed_profile/nominal_time` 的名义运动；10 Hz 整数微秒采样；连续时间最小间距（二次运动、导数实根 + 端点，分支定界） |
| `v08/motion/nominal_checks.py` | 从固定提交 `task_v07/detectors.py` 逐字抽取 runs/work_mask/azimuth_coverage/dwell/revisit（头部记录来源与块 SHA256），加 `screen_member` |
| `v08/motion/connect.py` | 边界穿越分析（直线、单次、±10 m 带、100 m 对齐）、释放延迟（0.1 s 向上取整）、圆角折线、骨架规划器 |
| `v08/motion/intents/monitoring.py` | 约束集合、`build_candidate`（全部检查）、随机提案采样器与预算修复（见下） |
| `v08/motion/plan.py` | `plan_segment`：20 次 attempt 预算、带证书的 `proven_infeasible`、`approx_empty`（含精确复核）、`budget_exhausted` |
| `v08/scene/{exact,field,context}.py`（小改） | 折线快速路径、`CombinedGrid`、惰性缓存首次构建计时 `cold_build`（供"冷缓存另报"） |

**测试（完整输出 `docs/v08/V8-12/tests_part3.txt`）：** 预置 `test_preset_numpy_motion.py` 7/7、`test_preset_local_monitoring.py` 3/3 通过（SHA256 与指令 6.9 一致，未改一字）；自加 `test_own_part3.py` 3/3（真实场景端到端：独立精确复核 world 内缩 35 m、所有设施 alert 外 ≥10 m、终点离所有预警圈 ≥50 m、释放延迟在 0.1 s 网格、总时长 ≤1800 s、同键重规划的计划 JSON 与数组逐字节一致）、`test_own_imports.py`（核心模块导入链不含 shapely/scene_v07）通过；第 1–2 部分的测试在新代码上回归通过。

**第 3 部分的主要实现取舍与偏离（均已记录，不是对测试的迁就）：**

1. **预算检查前置。** 名义总时长（自首名成员释放到最后成员停止保持结束）只依赖名义时钟，比几何/判据/间距检查便宜得多，所以 `build_candidate` 先查它；一个 attempt 的原因链记录的是第一个失败阶段。
2. **预算修复（指令 3.9 的局部修复）。** 圈数/穿行次数已取下限仍超 1800 s 时：折返先把弧跨度缩到覆盖下限（120°）为止，其余由各结点半径同时向各自合法径向区间的内端移动补足——这是"线性长度约束＋区间箱约束"下离原抽样欧氏距离最近的点（各结点对长度的权重相同）。移动量用时间模型解析求出（需缩短比例 = (D − 0.97×预算)/巡逻用时），逐轮用 `duration_only` 的廉价构造核对并更新；目标取预算的 97% 以吸收线性模型误差；随机流固定为同一对种子，所以轮与轮之间的差异只来自几何。修复前后系数/弧跨度/时长全部写入 `repairs[*].log`。**这是我对"活动约束投影"的一种具体化，不是指令给出的公式。**
3. **队形退让也由下游几何失败触发。** 指令 3.4 的退让链（abreast→echelon→column）在我的第一版里只在环带容不下该队形时触发，结果大编组在掉头/入圈阶段整体失败。现改为：该队形的转弯、入圈、起点路由、出圈、间距、边界穿越、形状阶段失败，也退到链上的下一个队形（预算超限不触发）。`repairs` 里的 `formation_retreat.forced_by` 记录触发阶段。
4. **汇合带的槽位足迹余量。** 指令 2.4 的 [50,250] m 带约束的是汇合**参考位置**；我第一版把成员足迹余量也加在带的两侧，使 11 人以上的编组汇合集合恒为空。现在足迹余量只加在物理约束（世界、限制区、预警圈外）上，带本身不加。
5. **圈心预算筛选与 `topology_forced` 的原因。** 圈心候选先用"内边界曲线长度 × 圈数下限 + 汇合距离"的名义时间下界估计筛一遍；若绕圈因此被排除而折返可行，按 r4 6.3.4 的"只有局部弧可用"处理为强制折返并记录 `forced_reason=budget`（几何原因记 `geometry`）。**这是把"预算许可集合为空"纳入"可行"的读法**；它在 200 合同上实际没有改变任何合同的成败（见探索表第 4 轮）。
6. **`approx_empty` 的精确复核。** 全部 attempt 都是 `patrol_region`/`budget_region` 时才报 `approx_empty`，并对单车道巡逻约束在警戒圈外接框内按 0.5 m 取点做精确有符号距离复核（`exact_nonempty`、检查点数入记录）。预算原因的空集报 `approx_empty / duration_budget`，不是 `proven_infeasible`。
7. **转弯组合惰性枚举。** 6 种（形状×侧向）组合按随机排列逐个核对，取第一个可行者再枚举它的连续可行半径（半径等概率）；记录 `combos_tested`，不再记录全部 `feasible_kinds`。
8. **名义运动复用。** `release_delays` 一并返回各成员的名义运动，`build_candidate` 不再对同一曲线重复做 `make_curve/speed_profile`（自检 `nominal_time` 一致性保留）。
9. 可视图（顶点/邻接）仍每进程重建、不落盘（第 2 部分已记，指令 2.4 写的是图也缓存）；惰性构建的耗时由 `cold_build` 计入"冷缓存"而非"每段规划"。

**开发过程中的探索性整批运行（不是第 4 部分的结论；仅为迭代构造，运行在我的草稿目录，不入库）：**
同一份 40 族 × 5 draw = 200 合同、每合同 20 次 attempt 预算、8–10 个并行进程，每轮只改一处，成功率与"每合同净规划用时"如下。

| 轮 | 改动 | 成功 | 净规划用时中位数 |
|---|---|---:|---:|
| 1 | 预算检查前置 + 二分半径修复 | 119/200 (59.5%) | 30.2 s |
| 2 | 解析时间模型的预算修复（弧跨度 + 半径） | 131/200 (65.5%) | 26.5 s |
| 3 | 下游几何失败触发队形退让 | 167/200 (83.5%) | 25.9 s |
| 4 | 圈心预算筛选 | 与第 3 轮同 | — |
| 5 | 汇合带足迹余量只加在物理约束上 | 173/200 (86.5%) | 27.1 s |
| 6 | 名义运动复用、转弯惰性枚举、极坐标半径范围收紧 | 176/200 (88.0%) | 15.2 s |

> **必须说明的限制：** 这些迭代用的就是第 4 部分的评估集（登记的 40 个开发族）。构造因此在这些族上做过调参，第 4 部分报告的成功率不是对新场景的无偏估计。第 6 轮剩余的 24 个失败合同几乎全是 `duration_budget`（大地图、起点在远角、初速 4–5.5 m/s 的编组），这类合同的名义总时长下界与预算只差几个百分点（见"执行方观察"）。

### 第 4 部分：只规划检查完整执行；止损一项都未触发，检查点状态为"未完成"（提交 `e5b7419` 为运行代码，结果提交见第 8 节）

**做了什么。** 在提交 `e5b7419`（工作树干净，`git_dirty=false`，源文件 SHA256 全部记入 `part4/summary.json`）上，单进程、无仿真，按登记清单的 `order`、`draw=0…4` 规划 40 族 × 5 = 200 个合同（每合同第 0 组、独立 `sequence` 键抽目标、`final=True`、20 次 attempt 预算），随后做 10 族 × 10 种子的多样性（取 order 1–10：1/2/3 设施各自最早的 order 1、2（2 设施）、3（3 设施），再按 order 补足）。一个族一个上下文；冷缓存目录是新建的空目录。原始合同 JSON/NPZ（约 440 MB）和缓存（1.7 GB）留在 `_handoff\2026-11-02_V8-12_monitoring\{out\plan,cache}`，不入库；汇总、多样性、失败原始记录入库到 `docs/v08/V8-12/part4/`。

**新增代码（均在 `Multi-UAV SimpleGC/`）：** `v08/runner/monitoring.py`（输出/缓存路径守卫、规划、多样性、总控）、`v08/runner/monitoring_report.py`（`checkpoint`、统计汇总、ρ 的 CV 精确积分）、`scripts/v08/v8_12_monitoring.py`（CLI）、`scripts/v08/v8_12_figures.py`（三张图）、预置 `tests/v08/V8-12/test_preset_numpy_checkpoint.py`（原样），自加 `test_own_part4.py`。

**路径守卫。** `guard_path` 在创建任何文件之前，对原路径和 `Path.resolve()` 后的真实路径都检查：拒绝仓库、冻结工作树（`Simulation-fe-prod-r3`、`Simulation-fe-s3`）、数据根，以及任何祖先组件以 `v07_` 开头的路径（包含经 junction/symlink 指向它们的路径）；输出目录已存在则拒绝。自加测试用真实 NTFS 联接验证了"联接指向仓库""联接指向 `v07_*` 目标"两种情形都被拒绝。

**CLI 退出码协议**（写在 `--help` 里，不参与任何数值门禁）：0 = 完成且检查点完整、未触发；2 = 检查点触发诊断性止损；3 = 检查点未完成（缺失测量、内部错误、冒烟子集、缺多样性）；4 = P0 停止（登记清单的族 id 列表 SHA256 不符）；1 = 参数/路径/环境错误。本次运行的状态是 **3**（`conda run` 只打印"命令失败"而不回显整数；该值由 `summary.json` 的 `checkpoint.complete=false, triggers=[]` 与 CLI 代码路径确定）。

**检查点结论（`summary.json` 的 `checkpoint`）：** `triggers = []`；`complete = false`，原因两条：多样性的 order 2 族（`family_s15_af5d80bd4e407c2e`）和 order 10 族（`family_s15_ad93040ec301fb17`）都只取得 9/10 个成功种子（见 3.1 节的多样性表），按指令 4.3"完整 10 种子的结论为未取得，不拿少量路径通过止损"，Fréchet 条件的状态是"未完成"，不是"未触发"。因此**我没有开展第 5 部分**（指令第 5 部分的前提是"第 4 部分完整执行且未触发止损"）；见第 5 节。

## 3. 第 4 部分全部数字

### 3.1 总览、分档、耗时、多样性

- 合同 176/200 规划成功（88.0%）；记录 200，完成 200，缺失 0，内部错误 0；批次完整：True

**按设施数（分母含全部合同）**

| 设施数 | 成功 | 合同 | 成功率 |
|---|---:|---:|---:|
| 1 | 83 | 85 | 97.6% |
| 2 | 66 | 85 | 77.6% |
| 3 | 27 | 30 | 90.0% |

**按实际第 0 组人数**

| 人数 n | 成功 | 合同 | 成功率 |
|---:|---:|---:|---:|
| 1 | 13 | 14 | 92.9% |
| 10 | 2 | 2 | 100.0% |
| 11 | 4 | 7 | 57.1% |
| 12 | 2 | 6 | 33.3% |
| 2 | 45 | 47 | 95.7% |
| 3 | 15 | 17 | 88.2% |
| 4 | 29 | 32 | 90.6% |
| 5 | 19 | 21 | 90.5% |
| 6 | 12 | 14 | 85.7% |
| 7 | 13 | 15 | 86.7% |
| 8 | 5 | 6 | 83.3% |
| 9 | 17 | 19 | 89.5% |

**最终失败代码（每个失败合同计一次）**：budget_exhausted=24

| 最终代码 \| 集合 | 合同数 | attempt 级失败阶段（该类合同内） |
|---|---:|---|
| budget_exhausted / random_construction | 24 | duration_budget×389，start_route×35，ingress×15，nominal_revisit×13，egress×7，turns×7，separation×5，boundary_crossing×3，nominal_dwell×3，patrol_shape×2，reference/speed×1 |

**attempt 级失败阶段（全部 1228 次 attempt；与合同数分开统计）**：duration_budget×757，start_route×94，nominal_revisit×76，ingress×35，nominal_dwell×26，separation×22，patrol_shape×13，egress×12，turns×11，boundary_crossing×4，reference/speed×2

**规划耗时（秒；min/q25/中位数/q75/p95/max）**

- 每合同净规划用时（扣除惰性缓存首次构建）：0.90 / 5.96 / 13.21 / 37.65 / 111.34 / 185.80（n=200）
- 含冷缓存构建的总用时：0.90 / 6.07 / 13.36 / 37.86 / 111.34 / 185.80（n=200）
- 成功合同净用时：0.90 / 5.47 / 11.55 / 24.76 / 75.10 / 185.80（n=176）；失败合同净用时：42.96 / 65.03 / 94.29 / 120.43 / 168.26 / 176.50（n=24）
- 冷缓存（单独报告）：预热栅格 101.0 s（40 族 200 合同合计，含磁盘读入）；规划内惰性构建（可视图/边界点）21.1 s；族读入 0.25 s；族内缓存构建合计 121.9 s；磁盘缓存命中 0、未命中 259
- 墙钟：200 合同阶段 6177 s，多样性阶段 2395 s

**非目标预警途经**：成功合同中至少一个成员连续曲线进入非目标预警圈：30/176 = 17.0%；限于有非目标设施的成功合同：30/93 = 32.3%；成员级 105/803；按设施数：1设施 0/83 = 0.0%，2设施 17/66 = 25.8%，3设施 13/27 = 48.1%

**队形**：实际队形不同于抽签倾向（含 loose→abreast 映射）：87/176 = 49.4%；比映射后的起点更窄（真退让）：71/176 = 40.3%；抽签倾向 {'abreast': 55, 'column': 42, 'echelon': 43, 'loose': 36}；实际 {'abreast': 40, 'column': 102, 'echelon': 34}

**修复**：有修复的成功合同 166/176 = 94.3%；构造到候选的 attempt 中有修复 285/306 = 93.1%；成功合同内种类 {'alpha_scaling': 68, 'formation_retreat': 71, 'laps_budget_cap': 24, 'laps_fallback_to_min': 18, 'radius_shift_budget': 103, 'traversals_budget_cap': 10}；全部 attempt 内种类 {'alpha_scaling': 108, 'formation_retreat': 135, 'laps_budget_cap': 24, 'laps_fallback_to_min': 18, 'radius_shift_budget': 199, 'traversals_budget_cap': 20}
- α（amplitude scaling）：0.050 / 0.750 / 0.900 / 0.950 / 0.950 / 0.950（n=108）；echelon 横向步长比：—
- 预算修复半径移动量 m：0.0 / 0.0 / 87.8 / 224.0 / 423.7 / 659.2（n=199）；占最大可移动量的比例：0.000 / 0.000 / 0.200 / 0.578 / 1.000 / 1.000（n=199）
- 圈数预算上限：抽到→实际 [{'drawn': 2.6940392412193734, 'used': 1.5576035313802803}, {'drawn': 2.273430240038356, 'used': 1.5200924173720858}, {'drawn': 2.1977980405716617, 'used': 1.6158606515634908}, {'drawn': 2.824942785026983, 'used': 1.5312749102270908}, {'drawn': 2.249624657004137, 'used': 1.5168516531297676}, {'drawn': 2.291818872998089, 'used': 2.595294241040623}, {'drawn': 1.6758968369336524, 'used': 1.5510022387165168}, {'drawn': 1.8908975192888096, 'used': 1.596405297705706}]（共 24 条）；穿行次数：[{'drawn': 4, 'used': 2}, {'drawn': 4, 'used': 2}, {'drawn': 3, 'used': 2}, {'drawn': 3, 'used': 2}, {'drawn': 4, 'used': 2}, {'drawn': 4, 'used': 3}, {'drawn': 4, 'used': 2}, {'drawn': 4, 'used': 2}]（共 20 条）

**近似为空与精确复核**：距离场判空且执行精确复核的查询 0，其中精确非空 0（—）；证明确空 0；未知/未复核（保守集非空而环/弧构造失败）0；记录 0 条

**边界/名义语义（诊断）**：每合同边界穿越次数 2 / 6 / 10 / 16 / 24 / 56（n=176）；每成员 2 / 2 / 2 / 2 / 4 / 6（n=803）；attempt 级拒绝 {'boundary_crossing': 4, 'duration_budget': 757, 'nominal_dwell': 26, 'nominal_layers': 0, 'nominal_revisit': 76, 'separation': 22, 'terminal_clearance': 0}；驻留拒绝 26 次

**拓扑（成功合同）**：原抽签 {'loop': 76, 'retrace': 100}；强制 {'False': 173, 'True': 3}；最终 {'loop': 73, 'retrace': 103}

#### 止损检查点（程序输出）

触发：[]；检查点完整：False；未完成原因：['族 family_s15_af5d80bd4e407c2e 未取得 10 个成功种子或缺少 Fréchet 距离', '族 family_s15_ad93040ec301fb17 未取得 10 个成功种子或缺少 Fréchet 距离']

```json
{
 "facility_gap": {
  "1": {
   "contracts": 85,
   "gap_to_total": -0.09647058823529411,
   "rate": 0.9764705882352941,
   "successes": 83
  },
  "2": {
   "contracts": 85,
   "gap_to_total": 0.10352941176470588,
   "rate": 0.7764705882352941,
   "successes": 66
  },
  "3": {
   "contracts": 30,
   "gap_to_total": -0.02,
   "rate": 0.9,
   "successes": 27
  }
 },
 "failure_evidence": {
  "bad_proven_infeasible": []
 },
 "frechet": {
  "pairs": 360,
  "per_family": [
   {
    "family_id": "family_s15_9b1a9f5a704a5a43",
    "median_ratio": 100.27601993797512
   },
   {
    "family_id": "family_s15_232aa66e0775f46f",
    "median_ratio": 128.65088793893992
   },
   {
    "family_id": "family_s15_a4e519a7d128f6d1",
    "median_ratio": 131.2836559281786
   },
   {
    "family_id": "family_s15_fac1d381571b4d36",
    "median_ratio": 180.49467161946282
   },
   {
    "family_id": "family_s15_2a7eced81da133ad",
    "median_ratio": 113.51676679022947
   },
   {
    "family_id": "family_s15_c6b49487cb7c7e1f",
    "median_ratio": 109.77540540762958
   },
   {
    "family_id": "family_s15_b0c036776dcaff71",
    "median_ratio": 90.86794952864166
   },
   {
    "family_id": "family_s15_eeb311862e8c34e5",
    "median_ratio": 131.51819694739092
   }
  ],
  "pooled_median_ratio": 119.22305437281261
 },
 "planning_median_s": 13.205509949999396,
 "success_rate": {
  "contracts": 200,
  "rate": 0.88,
  "successes": 176
 }
}
```

#### 多样性表（draw=0 的同一 common 与目标；branch 0..9；Fréchet 用 5 m 重采样）

| order | 设施数 | 间距 b (m) | 成功种子 | 对数 | Fréchet min/q25/med/q75/p95/max (m) | 比值 med | 仅巡逻子路径 med (m) | ρ 的 CV（精确）min/med/max | 拓扑（原抽/最终） |
|---:|---:|---:|---:|---:|---|---:|---:|---|---|
| 1 | 1 | 23.84 | 10/10 | 45 | 967/1846/2391/3139/3669/4188 | 100 | 941 | 0.018/0.227/0.411 | {'loop': 5, 'retrace': 5}→{'loop': 5, 'retrace': 5} |
| 2 | 2 | 15.16 | 9/10 | 36 | 1091/1777/2764/3202/3827/4946 | 186 | 1178 | 0.108/0.421/0.520 | {'loop': 6, 'retrace': 3}→{'loop': 6, 'retrace': 3} |
| 3 | 3 | 18.99 | 10/10 | 45 | 1014/1963/2443/2799/3549/4131 | 129 | 1175 | 0.027/0.212/0.760 | {'loop': 2, 'retrace': 8}→{'loop': 2, 'retrace': 8} |
| 4 | 1 | 16.16 | 10/10 | 45 | 1074/1746/2122/2724/3452/3847 | 131 | 1225 | 0.106/0.385/0.567 | {'loop': 7, 'retrace': 3}→{'loop': 7, 'retrace': 3} |
| 5 | 2 | 15.13 | 10/10 | 45 | 461/2205/2731/3185/4062/4534 | 180 | 1144 | 0.013/0.195/0.524 | {'loop': 4, 'retrace': 6}→{'loop': 4, 'retrace': 6} |
| 6 | 1 | 20.65 | 10/10 | 45 | 1084/1902/2344/2706/3461/3793 | 114 | 1072 | 0.109/0.256/0.409 | {'loop': 4, 'retrace': 6}→{'loop': 4, 'retrace': 6} |
| 7 | 1 | 22.00 | 10/10 | 45 | 485/1840/2415/2860/3418/3620 | 110 | 1412 | 0.049/0.259/0.518 | {'loop': 5, 'retrace': 5}→{'loop': 5, 'retrace': 5} |
| 8 | 2 | 17.24 | 10/10 | 45 | 272/1370/1567/1808/2719/2914 | 91 | 957 | 0.097/0.230/0.602 | {'loop': 5, 'retrace': 5}→{'retrace': 10} |
| 9 | 1 | 21.50 | 10/10 | 45 | 1195/2509/2827/3238/3655/3868 | 132 | 1338 | 0.000/0.227/0.634 | {'loop': 2, 'retrace': 8}→{'loop': 2, 'retrace': 8} |
| 10 | 1 | 18.64 | 9/10 | 36 | 1207/1624/2175/2858/3303/4226 | 117 | 1277 | 0.065/0.341/0.643 | {'loop': 1, 'retrace': 8}→{'loop': 1, 'retrace': 8} |

#### 冷缓存与热缓存（单独报告，不混入每段规划耗时）

| 项 | 冷缓存（第 4 部分正式运行，缓存目录为空） | 热缓存（同一缓存目录，重做同样的 load_context + 预热，不规划） |
|---|---:|---:|
| 预热栅格合计（200 合同） | 101.0 s | 16.9 s |
| 族读入 | 0.25 s | 0.19 s |
| 磁盘缓存命中/未命中（259 个几何键） | 0 / 259 | 259 / 0 |
| 规划内的惰性构建（可视图、边界点；不落盘） | 21.1 s | — |

热缓存数字是正式运行结束后用同一缓存目录单独测的（草稿工具，未入库）。

#### 多样性耗时（单独计时，不混入每段规划）

多样性阶段墙钟 2395 s：100 次规划（每次规划净用时中位数 13.1 s，合计 2057 s）加 Fréchet。10 个族的完整参考路径离散 Fréchet（5 m 重采样，每族 45 对，路径 1717–2389 点）每族 14.4–29.2 s，合计 234.8 s；仅巡逻子路径每族 5.8–14.3 s，合计 84.4 s。


### 3.2 v0.7 参照

指令 4.3 要求：仅用登记开发族对应的已有训练样本，复用已登记清单查找监视样本，同样测量；无可用同条件样本如实写缺失。检查 `docs/v08/V8-03/sample_episodes.json`（200 条已登记 v0.7 训练样本）：属于 40 个开发族的监视样本只有 **4 条**（`family_s15_54357502e6e9ebf2`（开发 order 17）、`family_s15_cfe0ba1515187f04`（35）、`family_s15_f2adfbfae12fbbad`（23）、`family_s15_ebb78827c10a8498`（40），各 1 条），**没有一条落在多样性用的 10 个族（order 1–10）里**，且任何族都没有 ≥ 2 条同条件监视样本。因此 v0.7 参照的"同条件 10 种子 Fréchet / ρ 的 CV"**缺失**，不改找 val/test 或生产数据，不据此改变任何阈值。

### 3.3 独立复核（本报告新增的证据，不是指令要求）

对全部 176 个规划成功合同的 803 条成员曲线，用 **shapely**（与生成器的 NumPy 解析距离无关；圆和缓冲多边形用 `quad_segs=256` 的多边形近似，误差 ≪ 1 cm）重新计算：world 内缩、限制区外、所有设施 alert 外、终点离每个预警圈、名义总时长 ≤ 1800 s、释放延迟在 0.1 s 网格、成员曲线首点 = 成员初始位置。结果：**0 个合同有问题**；最小余量 world 39.78 m（要求 ≥ 35）、限制区 38.61 m（≥ 35）、alert 13.60 m（≥ 10）、终点离预警圈 56.56 m（≥ 50）。这只复核了全局物理约束，没有重算边界单次穿越、100 m 对齐、巡逻带 30/35 m、名义判据和成员对间距（这些由生成器内的精确检查负责，真实判据在第 5 部分）。脚本是草稿目录里的工具，未入库。

## 4. 逐条止损实值

| 条件 | 原阈值（严格比较） | 实值（分子/分母或观测值） | 是否触发 | 数据是否完整 |
|---|---|---|---|---|
| `success_rate` | 总成功率 < 80% | **176/200 = 88.0%** | 否 | 是（200/200 合同有结果，0 缺失，0 内部错误） |
| `facility_gap` | 某设施数档成功率比总成功率低**超过** 20 个百分点 | 总 0.880；1 设施 83/85 = 97.6%（差 −9.6 个百分点）；2 设施 66/85 = 77.6%（差 **+10.35**，最大）；3 设施 27/30 = 90.0%（差 −2.0）。分母 85/85/30，与清单分布一致 | 否 | 是 |
| `failure_evidence` | `proven_infeasible` 无几何见证，或精确复核非空却记为 `proven_infeasible` | 本次 0 个 `proven_infeasible`、0 个 `approx_empty`（24 个失败合同全是 `budget_exhausted`），没有可检对象；预置 `test_false_proof_triggers` 通过 | 否（对象为空） | 是 |
| `planning_time` | 每段规划耗时中位数 > 30 s | **13.21 s**（净规划用时；含惰性冷缓存构建为 13.36 s）；p95 111.3 s，max 185.8 s | 否 | 是 |
| `frechet` | 合并后的"Fréchet ÷ lateral_spacing_m"中位数 < 1（附录补充裁定） | 8 个取得完整 10 种子的族：360 对，合并中位数 **119.2**；把 2 个不完整族的 72 对也合并（仅诊断）：432 对，122.3；全部 432 对里最小的单对比值 15.8（order 8 族，272 m ÷ 17.24 m） | 否（不可能：最小比值也 ≫ 1） | **未完成**：order 2、10 族各 9/10 种子 |

## 5. 第 5 部分

**已取消（用户 2026-11-03 指示：改用联合时空优化方案；V8-12 第 5 部分取消）。** 取消前的状态：

- **放行与实现。** 规划审查方 11-03 放行，并裁定：缺种子的多样性族按失败报告、检查点视为完成；`test_each_diagnostic_threshold` 的失败属指令修订、接受、不改测试；下游几何失败触发的队形退让偏离了指令 3.4，不回退、在第 5 部分报告里单列；第 5 部分只用第 4 部分已规划成功的 176 个合同、不重新规划，1800 s 上限不动。实现提交 `bc6a679`（运行前）、`dd968e3`（全量阶段的 `--rerun-every`）：`v08/runner/monitoring_sim.py`（`try_segment`、`simulate_devset`、同键整链复跑逐位比较、跟踪管/变速冲高/边界/驻留诊断）、`monitoring_sim_report.py`、`plan_segment` 的 `attempt_start`/`prior_log`、CLI `--stage quick|full`；预置 `test_preset_local_simulation.py` 原样放入并通过，自加 `test_own_part5.py` 13 项通过。
- **快速 10 合同：完整跑完。** 选择规则：设施数 1/2/3 各一（`o01_d0`、`o02_d0`、`o03_d0`）、全族 `vehicle_count` 最大（12，`o11_d3`）、第 0 组人数最大（12，`o17_d1`，两种「最大机数」口径都是 12 但落在不同合同），其余按 order/draw 补足。10/10 保留、10/10 复跑逐位一致、无候选失败、无 P0，墙钟 1618 s。
- **全量：被取消中断。** 完成 25 个，第 26 个被终止，140 个未运行；`out/full/` 无 `summary.json`。
- **数字与局限：** 见 `part5_partial.md`（逐合同是否通过段核验、未通过条件、实测最小间距、跟踪偏差，以及没有跑完的部分）。没有运行实测轨迹的独立 shapely 复核；没有候选失败，重试路径只被单元测试覆盖。
- **资源估计（取消前的判断）：** 按实测 0.0063 s 墙钟/仿真秒，176 个合同只跑一遍约 2.3 小时，超过 2 小时边界；所以全量阶段加了确定性的复跑规则（每 4 个合同复跑 1 个）来多覆盖首次执行。

## 6. 失败样例完整清单

24 个失败合同（占 200 的 12.0%），最终代码**全部是 `budget_exhausted`**（20 次 attempt 用尽，保留各 attempt 的底层原因）。没有 `proven_infeasible`（无证书），没有 `approx_empty`（没有一个合同的全部 attempt 都是环带/预算集合为空）。attempt 级失败另外统计，不与合同数混在一起：全部 1228 次 attempt 中 duration_budget×757、start_route×94、nominal_revisit×76、ingress×35、nominal_dwell×26、separation×22、patrol_shape×13、egress×12、turns×11、boundary_crossing×4、reference/speed×2。"见证路径"指 `part4/failures.json` 里该合同的 `attempt_log[*].witness`（含原始数值、修复日志、约束名与弦序号）；完整原始记录在 `out\plan\contracts\<合同>.json`。

| 合同 | family_id | draw | 组 | 目标 | n | 设施数 | 初速 m/s | 最终代码（集合） | 20 次 attempt 的底层阶段 | 最后一次 attempt 的原因 | 见证路径 |
|---|---|---:|---|---|---:|---:|---:|---|---|---|---|
| o03_d2 | family_s15_232aa66e0775f46f | 2 | g0 | facility_01 | 1 | 3 | 4.9 | budget_exhausted（random_construction） | duration_budget×18，patrol_shape×1，nominal_revisit×1 | 第19次 duration_budget：局部修复后名义总时长仍为 3054.9 s > 1800.0 s | contracts/o03_d2.json → attempt_log[*].witness |
| o11_d0 | family_s15_12b1ed81bd5cde72 | 0 | g0 | facility_01 | 12 | 2 | 7.6 | budget_exhausted（random_construction） | duration_budget×11，start_route×6，egress×1，nominal_revisit×1，nominal_dwell×1 | 第19次 start_route：成员 uav_01 没有可用的起点路由 | contracts/o11_d0.json → attempt_log[*].witness |
| o11_d1 | family_s15_12b1ed81bd5cde72 | 1 | g0 | facility_02 | 12 | 2 | 8.3 | budget_exhausted（random_construction） | duration_budget×12，ingress×3，separation×2，nominal_revisit×2，start_route×1 | 第19次 duration_budget：局部修复后名义总时长仍为 2373.1 s > 1800.0 s | contracts/o11_d1.json → attempt_log[*].witness |
| o11_d2 | family_s15_12b1ed81bd5cde72 | 2 | g0 | facility_01 | 4 | 2 | 4.1 | budget_exhausted（random_construction） | duration_budget×18，start_route×2 | 第19次 duration_budget：局部修复后名义总时长仍为 2841.7 s > 1800.0 s | contracts/o11_d2.json → attempt_log[*].witness |
| o11_d4 | family_s15_12b1ed81bd5cde72 | 4 | g0 | facility_01 | 6 | 2 | 4.9 | budget_exhausted（random_construction） | duration_budget×19，turns×1 | 第19次 turns：折返端点没有可放置的掉头 | contracts/o11_d4.json → attempt_log[*].witness |
| o13_d1 | family_s15_90108df3163855bf | 1 | g0 | facility_03 | 3 | 3 | 4.6 | budget_exhausted（random_construction） | duration_budget×20 | 第19次 duration_budget：局部修复后名义总时长仍为 3493.5 s > 1800.0 s | contracts/o13_d1.json → attempt_log[*].witness |
| o13_d3 | family_s15_90108df3163855bf | 3 | g0 | facility_02 | 7 | 3 | 4.5 | budget_exhausted（random_construction） | duration_budget×20 | 第19次 duration_budget：局部修复后名义总时长仍为 3197.2 s > 1800.0 s | contracts/o13_d3.json → attempt_log[*].witness |
| o17_d2 | family_s15_54357502e6e9ebf2 | 2 | g0 | facility_02 | 5 | 2 | 5.3 | budget_exhausted（random_construction） | duration_budget×20 | 第19次 duration_budget：局部修复后名义总时长仍为 2753.5 s > 1800.0 s | contracts/o17_d2.json → attempt_log[*].witness |
| o24_d3 | family_s15_291e9f1d18c41e22 | 3 | g0 | facility_01 | 7 | 1 | 5.4 | budget_exhausted（random_construction） | duration_budget×12，start_route×6，nominal_dwell×1，boundary_crossing×1 | 第19次 duration_budget：局部修复后名义总时长仍为 3163.3 s > 1800.0 s | contracts/o24_d3.json → attempt_log[*].witness |
| o27_d2 | family_s15_6af8e2b8ab8f838d | 2 | g0 | facility_02 | 2 | 2 | 5.5 | budget_exhausted（random_construction） | duration_budget×18，nominal_revisit×1，reference/speed×1 | 第19次 duration_budget：局部修复后名义总时长仍为 2228.2 s > 1800.0 s | contracts/o27_d2.json → attempt_log[*].witness |
| o28_d0 | family_s15_84213fbe5aa46dcf | 0 | g0 | facility_01 | 11 | 2 | 4.1 | budget_exhausted（random_construction） | duration_budget×7，ingress×6，start_route×3，egress×2，separation×1，turns×1 | 第19次 duration_budget：局部修复后名义总时长仍为 3348.6 s > 1800.0 s | contracts/o28_d0.json → attempt_log[*].witness |
| o28_d1 | family_s15_84213fbe5aa46dcf | 1 | g0 | facility_02 | 6 | 2 | 4.9 | budget_exhausted（random_construction） | duration_budget×15，start_route×2，separation×1，patrol_shape×1，turns×1 | 第19次 duration_budget：局部修复后名义总时长仍为 2155.1 s > 1800.0 s | contracts/o28_d1.json → attempt_log[*].witness |
| o33_d0 | family_s15_16b7eb91a4d4194d | 0 | g0 | facility_01 | 9 | 2 | 8.1 | budget_exhausted（random_construction） | duration_budget×15，ingress×1，boundary_crossing×1，start_route×1，nominal_revisit×1，separation×1 | 第19次 duration_budget：局部修复后名义总时长仍为 2738.4 s > 1800.0 s | contracts/o33_d0.json → attempt_log[*].witness |
| o33_d3 | family_s15_16b7eb91a4d4194d | 3 | g0 | facility_01 | 4 | 2 | 4.9 | budget_exhausted（random_construction） | duration_budget×17，turns×1，start_route×1，ingress×1 | 第19次 duration_budget：局部修复后名义总时长仍为 1832.1 s > 1800.0 s | contracts/o33_d3.json → attempt_log[*].witness |
| o33_d4 | family_s15_16b7eb91a4d4194d | 4 | g0 | facility_01 | 2 | 2 | 4.5 | budget_exhausted（random_construction） | duration_budget×19，egress×1 | 第19次 duration_budget：局部修复后名义总时长仍为 2370.1 s > 1800.0 s | contracts/o33_d4.json → attempt_log[*].witness |
| o34_d0 | family_s15_3968861533cf6dd7 | 0 | g0 | facility_02 | 5 | 2 | 4.1 | budget_exhausted（random_construction） | duration_budget×19，turns×1 | 第19次 duration_budget：局部修复后名义总时长仍为 2421.7 s > 1800.0 s | contracts/o34_d0.json → attempt_log[*].witness |
| o34_d2 | family_s15_3968861533cf6dd7 | 2 | g0 | facility_01 | 12 | 2 | 4.5 | budget_exhausted（random_construction） | duration_budget×14，start_route×3，ingress×1，egress×1，nominal_revisit×1 | 第19次 start_route：成员 uav_01 没有可用的起点路由 | contracts/o34_d2.json → attempt_log[*].witness |
| o34_d3 | family_s15_3968861533cf6dd7 | 3 | g0 | facility_02 | 12 | 2 | 6.6 | budget_exhausted（random_construction） | duration_budget×18，boundary_crossing×1，start_route×1 | 第19次 duration_budget：局部修复后名义总时长仍为 2718.5 s > 1800.0 s | contracts/o34_d3.json → attempt_log[*].witness |
| o35_d2 | family_s15_cfe0ba1515187f04 | 2 | g0 | facility_01 | 4 | 2 | 5.4 | budget_exhausted（random_construction） | duration_budget×15，nominal_revisit×3，turns×1，nominal_dwell×1 | 第19次 duration_budget：局部修复后名义总时长仍为 3071.2 s > 1800.0 s | contracts/o35_d2.json → attempt_log[*].witness |
| o35_d3 | family_s15_cfe0ba1515187f04 | 3 | g0 | facility_01 | 8 | 2 | 5.4 | budget_exhausted（random_construction） | duration_budget×16，ingress×2，start_route×1，nominal_revisit×1 | 第19次 duration_budget：局部修复后名义总时长仍为 2245.4 s > 1800.0 s | contracts/o35_d3.json → attempt_log[*].witness |
| o36_d4 | family_s15_7b58eec82f695da3 | 4 | g0 | facility_01 | 9 | 2 | 5.4 | budget_exhausted（random_construction） | duration_budget×18，start_route×2 | 第19次 duration_budget：局部修复后名义总时长仍为 2258.4 s > 1800.0 s | contracts/o36_d4.json → attempt_log[*].witness |
| o37_d1 | family_s15_da9847cb8fc64ef7 | 1 | g0 | facility_02 | 11 | 2 | 4.8 | budget_exhausted（random_construction） | duration_budget×14，start_route×4，egress×2 | 第19次 duration_budget：局部修复后名义总时长仍为 2277.0 s > 1800.0 s | contracts/o37_d1.json → attempt_log[*].witness |
| o37_d4 | family_s15_da9847cb8fc64ef7 | 4 | g0 | facility_02 | 11 | 2 | 5.1 | budget_exhausted（random_construction） | duration_budget×17，start_route×2，turns×1 | 第19次 duration_budget：局部修复后名义总时长仍为 3025.0 s > 1800.0 s | contracts/o37_d4.json → attempt_log[*].witness |
| o38_d3 | family_s15_5efc7cddb20f4e95 | 3 | g0 | facility_01 | 3 | 1 | 5.5 | budget_exhausted（random_construction） | duration_budget×17，nominal_revisit×2，ingress×1 | 第19次 duration_budget：局部修复后名义总时长仍为 1983.5 s > 1800.0 s | contracts/o38_d3.json → attempt_log[*].witness |


## 7. 三张图

`docs/v08/V8-12/success_loop.png`（`o01_d3`：绕圈、6 人梯形、1740 s）、`success_retrace.png`（`o01_d0`：折返、2 人纵列、1734 s）、`failure.png`（`o03_d2`：1 人、3 设施，20 次 attempt 里 duration_budget×18，最后一次修复后总时长仍为 3054.9 s）。选择规则是确定性的（拓扑为 loop/retrace 的 order 最小的成功合同；order 最小的失败合同），不按结果好坏挑。每张图画 world、限制区（灰块）、全部三层圈层（点线保护层、虚线 alert 层、实线预警圈，目标设施红色）、参考路径（黑粗线）、各成员路径、成员初点（黑三角）、汇合参考点、入圈边界交点、入圈前 100 m 对齐起点、出口边界和终点。失败图没有成功计划，标出失败阶段计数、最后一次的原因和见证数值。**图仅供人工查看，不作成功证据。**

## 8. 分支与提交

- `dev/v0.8`：第 1 部分快进 `2bbe8ad → 4d2cf5d`；本项没有再动它。
- 审查分支 `review/v08/V8-12-monitoring`：`e05dcf2`（第 1 部分）、`cdeff15`（第 2 部分）、`693ccb5`（第 3 部分）、`e5b7419`（第 4 部分运行器与检查点，运行前）、`cb6b58e`（第 4 部分结果）、`bc6a679`（第 5 部分运行器，运行前）、`dd968e3`（全量阶段的复跑规则）、第 5 部分取消提交「V8-12 第5部分（已取消，未完成）」（含 `part5_partial.md` 与本报告的这一版）。每次推送后的真实远端头提交以 `git ls-remote origin refs/heads/review/v08/V8-12-monitoring` 的输出为准，见对话回报。报告不能包含自己的最终提交号，这里不伪造自引用。
- 不推 `main`、不强制推送；冻结工作树 `Simulation-fe-prod-r3` 仍是 `641a9b3`、`Simulation-fe-s3` 仍是 `de4d115`，`git status` 均干净。

## 9. 改动清单

见本报告随附的 `git diff --stat 4d2cf5df48187671f0dd9aa0018a69adac829911` 输出（`docs/v08/V8-12/diff_stat.txt`）。允许新增清单（指令 0.2）逐项核对：`v08/contract/`、`v08/scene/`（含 `visibility.py`）、`v08/sampler/common.py`、`v08/motion/`（含 `intents/`）、`v08/runner/`、`configs/v08/monitoring.json`、`scripts/v08/v8_12_monitoring.py`、`tests/v08/V8-12/`、`docs/v08/V8-12/`、`claude/v08/` 均在清单内；**额外新增**一个 `scripts/v08/v8_12_figures.py`（三张图的脚本，指令 0.2 只列了 `v8_12_monitoring.py`，这是可复现图所需，列为偏离，见 11 节）。没有改动任何已有文件的内容，除了第 2/3 部分对本项自己新增的 `v08/contract/monitoring.py`、`v08/scene/*.py` 的追加。**数据与冻结树前后不变的证据：** 登记的 40 族 × 4 个输入文件共 160 个，第 2 部分读入前后快照（SHA256、大小、`mtime_ns`）一致，第 4 部分运行后重做同一快照，与第 2 部分的快照**完全一致**（160/160）；两个冻结工作树的 `HEAD` 与 `git status` 不变；本项没有写 `SwarmData\v07_*`。

## 10. 测试

SHA256（与指令 6.9 逐项一致，原样提取，未改一字）：`test_preset_numpy_geometry.py` `6b62666b…adf24`、`synth_v8_12.py` `0c97df28…024d9`、`test_preset_numpy_motion.py` `e250477a…f3471`、`test_preset_local_monitoring.py` `ff12bdfa…1beb`、`test_preset_local_devset.py` `1e73d193…8d88`、`test_preset_numpy_checkpoint.py` `fc667b35…fa56`；`test_preset_local_simulation.py`（`ef4acb7a…08f3`）已在第 5 部分放入，与指令 6.9 一致。自加 `test_own_part5.py`（13 项）通过；第 5 部分提交前对较早测试回归：checkpoint 仍是 3/4（同一项疑似预期错误，审查方已接受），其余通过。

| 测试 | 结果 | 命令（cwd = `Multi-UAV SimpleGC`，conda `llm`） | 完整输出 | 退出码 / 耗时 |
|---|---|---|---|---|
| 预置 `test_preset_numpy_geometry.py` | 4/4 通过 | `python -B -m unittest discover -s tests/v08/V8-12 -p "test_preset_numpy_geometry.py" -v` | `tests_part2.txt`、`tests_part3.txt` | 0 / 1 s |
| 预置 `test_preset_local_devset.py` | 1/1 通过（40 族） | 同上换文件名，需 `V8_12_DATA_ROOT` | `tests_part2.txt`、`tests_part3.txt` | 0 / 2 s |
| 预置 `test_preset_numpy_motion.py` | 7/7 通过 | 同上 | `tests_part3.txt`、`tests_part4.txt` | 0 / 2 s |
| 预置 `test_preset_local_monitoring.py` | 3/3 通过 | 同上 | `tests_part3.txt`、`tests_part4.txt` | 0 / 3 s |
| 预置 `test_preset_numpy_checkpoint.py` | **3/4 通过，1 项失败**：`test_each_diagnostic_threshold` 的 Fréchet 断言 | 同上 | `tests_part4.txt` | 1 / 1 s |
| 预置 `test_preset_local_simulation.py` | 1/1 通过（真实 `run_guided_segment`/`stitch`/V8-11，两次运行逐位一致） | 同上换文件名，需 `V8_12_DATA_ROOT` | `tests_part5_preset.txt` | 0 / 33.9 s |
| 自加 `test_own_part2.py`、`test_own_part3.py`、`test_own_part4.py`、`test_own_imports.py` | 全部通过（5/5（1 跳过）、3/3、12/12、1/1） | 同上 | `tests_part3.txt`、`tests_part4.txt` | 0 |

`test_each_diagnostic_threshold` 的前三个断言（`success_rate`、`facility_gap`、`planning_time`）通过，**第四个断言失败**：`'frechet' not found in ()`，输入是"10 个族里 1 个族中位数 19 m、其余 9 个族 20 m，间距均 20 m"。这是第 11 节的**疑似预期错误**，我没有改测试。

## 11. 偏离指令之处、疑似预期错误

**疑似预期错误（预置测试，不改，等审查方裁决）：**
1. `test_preset_numpy_checkpoint.py::test_each_diagnostic_threshold` 第四个断言要求"单个族中位数 19 < 间距 20"触发 `frechet`，这是指令 4.4 的"逐族评价、任一族触发即停"。附录补充裁定把它改为"把每族每对路径的 Fréchet ÷ 间距合并后取中位数，< 1 才触发"，该输入合并中位数是 1.0（9 个族 1.0、1 个族 0.95），不触发。两者无法同时满足；`checkpoint` 按附录实现，测试因此失败 1 项。若审查方认为应保持逐族语义，需同时撤回附录补充裁定；本次实测的每个族的比值都在 90–190 之间，两种语义下结论相同。

**偏离或指令未规定而我做了选择的地方：**
2. **预算修复、队形退让触发、圈心预算筛选、汇合带足迹余量的取舍**（详见第 3 部分结论 1–9）。它们是我对指令 3.3–3.9 的具体化；其中"下游几何失败也触发队形退让"（第 3 点）和"预算许可集合为空视为该拓扑不可行"（第 5 点）是对指令文字的解释，不是文字本身。
3. **构造在评估集上调过参。** 第 3 部分的 6 轮探索整批运行用的就是第 4 部分的评估集（登记的 40 个开发族）；最终代码在这个集合上给出 88.0%，但它不是对新场景的无偏估计。
4. 可视图每进程重建、不落盘（指令 2.4 写的是图也缓存）；惰性构建的耗时单独记为冷缓存。
5. 参考路径取 `SegmentPlan.reference_xy`（汇合点到终点的参考中心线，含入圈/出圈），按附录裁定先用 V8-05 `resample_polyline` 重采样到 5 m 再算离散 Fréchet；"仅巡逻子路径"用 `anchors` 的巡逻起止弧长在同一条参考线上切出（诊断）。ρ 的 CV 用四点 Gauss–Legendre 在 B 样条节点段上精确积分（与 720 点等权离散近似逐项相差 < 1e-5），"修复前"指未做 α 缩放和预算半径移动之前的抽样半径；折返用有效折返方位弧。
6. 输出目录日期用 `2026-11-02_V8-12_monitoring`（指令 0.4、第 8 节的字面路径），指令包文件夹是 `2026-11-03_…`，见 1.8。
7. 额外新增 `scripts/v08/v8_12_figures.py`（指令 0.2 的新增清单未列）；独立复核脚本未入库。
8. `approx_empty` 的精确复核（0.5 m 取点）已实现并单元验证路径，但本次运行没有任何合同走到这一步（见 3.1 的"近似为空与精确复核"：0 个查询）。四类对照因此全是 0，不能据此说明复核方法在真实场景上的表现。
9. 预算修复把"目标 97% 预算"作为常数；它不是业务阈值，是线性模型的误差余量，随记录保存。
10. **第 5 部分（已取消）的选择：** (a) 全量按 `(draw_index, order)` 轮转而不是 `(order, draw)` 取合同，这样 2 小时边界截断时覆盖的是各族而不是前几个族；(b) 全量阶段每 4 个合同复跑 1 个（`--rerun-every 4`），不是每个合同都复跑，是因为复跑约占一半时间、而快速 10 个合同的复跑已全部一致；其余记「待复跑」，不计入已验证保留数；(c) 一个成员仿真超时就整个 attempt 作废，不再仿真其余成员；(d) 时间线不连续按附录裁定 10 作为 P0 停批次，而不是指令 5.2 失败代码表里的候选失败。

## 12. 复跑命令、环境与模型

用户复跑第 4 部分（200 合同 + 十族多样性；输出已存在则拒绝覆盖，所以用 `out_rerun\plan`，若已存在请换新名）：

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"; $env:OMP_NUM_THREADS = "1"; $env:OPENBLAS_NUM_THREADS = "1"; $env:MKL_NUM_THREADS = "1"
C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B scripts/v08/v8_12_monitoring.py --stage plan --data-root "F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData" --cache "F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-02_V8-12_monitoring\cache" --out "F:\CASIA\Drone Swarm Situational Awareness Algorithm\_handoff\2026-11-02_V8-12_monitoring\out_rerun\plan"
```

**环境：** Windows 11 Pro 10.0.26200；PowerShell 7；conda `llm`：Python 3.12.3、NumPy 2.5.3、SciPy 1.14.1（导入时报"需要 NumPy <2.3.0"的警告，本项核心不依赖 SciPy）、shapely 2.0.7；单线程环境变量如上；CPU 为 16 核 32 线程，本次正式运行是**单进程**，墙钟 8572 s（200 合同 6177 s、多样性 2395 s）。**实际使用的模型：** Claude Sonnet 5.5（`claude-sonnet-5-5`）。

### 执行方观察（与事实分开，不是结论）

- **1800 s 预算在大多数成功合同里是约束。** 176 个成功合同里，103 个用了半径内移（`radius_shift_budget`），24 个降低圈数、10 个降低穿行次数；24 个失败合同**每一个**的最主要 attempt 级失败阶段都是 `duration_budget`；其中 19 个是 2 设施（3 设施 3 个、1 设施 2 个），地图边长 4000–6750 m（22/24 个 ≥ 5000 m），初速 4.1–8.3 m/s（20/24 个 < 5.6 m/s）。失败合同在 20 次 attempt 里取得的最短名义总时长（`duration_budget` 的原始数值）：中位数 1977 s、最小 1808 s、最大 2325 s，即最好的一次通常只超出预算 0–30%。另一方面，我用草稿工具对 200 个合同做的粗略名义时间下界估计（直线汇合距离 + 圈数/穿行次数下限 × 环带内缘长度 + 85 m 撤离，按各合同抽到的速度剖面换算时间）最大值是绕圈 1512 s、折返 1069 s，没有一个超过 1800 s，所以没有合同能被判为"下界已超预算"（`approx_empty / duration_budget`）；实际构造与这个下界之间有很大差距（随机圈心/半径、入圈点和绕行路线），这些失败更像是构造效率问题，不是已证明的无解，我也没有证明它们可行。也就是说，抽到的环大小分布被预算明显压向小半径，数据集的环半径分布因此不是"可行环带上的均匀分布"。我对 200 个合同的粗略名义时间下界估计（直线汇合距离 + 圈数下限 × 环带内缘周长）都低于 1800 s，所以没有一个合同能被"下界已超预算"判为 `approx_empty / duration_budget`；这些失败是 20 次随机构造用尽，不是无解。
- **队形被压向纵列。** 抽签倾向里纵列只占 42/176，成功后的实际队形里纵列占 102/176（58%）；40.3% 的成功合同比映射后的起点更窄。大编组（n ≥ 11）成功率 6/13，其余人数档在 83–100%。
- **非目标预警途经**占成功合同的 17.0%（有非目标设施的合同里 32.3%；3 设施档 48.1%）。
- **Fréchet 比值约 100 倍于间距**，说明多样性主要来自圈心、半径、相位和进出路线，该止损条件在这套构造下对"近似固定模板"并不敏感；它没有触发不代表分布均匀。
- 多样性 order 2、10 两族各丢 1 个种子，两者的初速（6.3/5.0 m/s）、编组（9 人/5 人）和 `loose` 倾向都不在"最难"的一端，失败原因同样是 `duration_budget`×13–14；与 24/200 的整体失败率一致，没有看到特定于多样性协议的问题。
