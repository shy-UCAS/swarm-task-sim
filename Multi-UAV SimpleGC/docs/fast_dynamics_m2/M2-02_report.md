# M2-02 阶段报告：修复后来源登记与阻塞结论

- 阶段 / attempt：**M2-02 / attempt_02_repair**。
- 阶段结论：**BLOCKED**。R1–R4 修复及独立复核已完成；未建立有效 calibration/blind 划分，M2-03 未放行。
- 上一阶段：[M2-01 最终放行回执](M2-01_review_03.md)，SHA256 `9805bacc219c84f477006235d13ac8ae3d87c9f74f7c01dc628e57420c131168`。
- 本阶段：[首次审阅回执](M2-02_review.md)、[修复后复核回执](M2-02_review_02.md)、[摘要](../../verification/fast_dynamics_m2/M2-02_summary.json)。
- 本轮由 Codex 按用户“执行本轮修复以及再次核查”授权完成；没有进入 M2-03。

## 1. 结论与阻塞原因

固定种子、组件 ID 与使用史实现已修正，但 r2 共用的 **300 个 family 全部参加过历史开发诊断**。`SwarmData/reviews/v06_deepseek_audit_20261009/audit_core.py` 第 51–88 行对全部生产侦察任务的名义路线运行累计转向与分类阈值检查，写出 `production_turns.json`；其身份列覆盖全部 300 个 family。按同 family 跨意图不可另获测试身份的规则，这些 family 均不能作为“从未用于诊断”的留出。

这是从生产脚本用途、源名册和身份列确定的使用事实。本轮没有用转角数值、飞行成败、质量或性能来挑选候选，也没有重新执行该历史审计脚本。自动生成名册与一般离线规划准入单独登记，不会仅凭它们出现过 family ID 就认定开发污染。

| 最终互斥角色 | 分量 / family | 依据 |
| --- | ---: | --- |
| development_reference | 14 / 14 | T 系列已执行的原开发对照 |
| used_production | 141 / 141 | 已执行生产任务，沿用保守排除 |
| used_diagnostic | 145 / 145 | 主名册中未执行的 family，均已有上述几何/分类诊断 |
| used_pilot_development | 20 / 20 | pilot 台账按正确来源归属后确认实际执行 |
| candidate_eligible | **0 / 0** | 当前登记范围内无合格未使用候选 |
| quarantine | 0 / 0 | 所有分量已有足够排除证据；不表示所有引用用途均已审清 |
| calibration / blind_holdout | **0 / 0** | 没有有效分组，不是冻结好的空测试集 |
| 合计 | 320 / 320 | 320 个单-family 分量 |

仍有 **302 个 family** 出现在尚未逐一确认用途的其他引用中，作为 `unknown` 证据保留。由于它们已被更强的已执行/开发诊断证据排除，最终角色无需再列 quarantine。不能把最终 quarantine=0 写成“使用史完全明确”。

原 143 个候选及另外 2 个仅规划引用分量，现在均属于这 145 个未执行但已诊断的 family。G=0，小于预登记要求的 2，因此阶段为 BLOCKED。原 71/72 分组被拒绝，不可供 M3 使用。

## 2. 原版保留与 Git 边界

HEAD 仍为 `16b7cb740d081f7c66e73ed80eff4c7bad8dbb5f`，父提交 `57cca914f2e8b414e8820a1f08f6fd900f912d36`。本轮没有提交、amend、push、tag 或 PR；`main` / `origin/main` 仍为 `5e45637`。

原报告、摘要、划分、矩阵及方法/源码/审阅证据共 **52 个被审文件**在修复前逐项核验并复制到：

`F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m2/M2-02/attempt_02_repair/before/`

逐项映射见 `before_manifest.json`。原 `attempt_01/`、`splits/split_2026101202/` 和首次审阅回执均保持原字节；独立复核再次核对副本及旧证据哈希。

| 原交付 | 原 SHA256 |
| --- | --- |
| 报告 | `2e22c5a8be888b082fa056b2bec0896cdce25a4756e7cc374c2dc692b0aa610c` |
| 摘要 | `81a7b0772f19aca1a2cb08823fa478a730f25fa9d23316ae18b00dd9b755509c` |
| 划分 | `5cc963fd817aa3c92ea3d813b049c7467f1458eaa41065664b637d196e25ba0f` |
| 覆盖矩阵 | `2479970093a060d4f68bac5f749d7c463fbf1880a02aa8ce98cd7e80af9d564a` |

修正版 `split_2026101202_v2` 是**阻塞状态的来源/方法登记**，`effective_holdout_frozen=false`，所有 `split_group=null`；保留 `supersedes` 与原版拒绝原因。没有修改旧目录或为了保留原分组重新抽样。

## 3. R1：身份与算法修复

明确分开：

- `family_scheme=scene_content_v1`；
- 实际 `family_id=scene_<20位>`；
- `canonical_scene_sha256=<64位>`。

短 ID 与完整哈希建立显式映射，发现冲突即拒绝，不静默选择其中一个。本批映射冲突 0。

组件 ID 使用实际 family ID 去重、Unicode 排序、紧凑 `ensure_ascii=True` JSON、UTF-8 SHA256；rank 仍为 `SHA256('2026101202|' + component_id)`，排序及前 `floor(G/2)` 的规则未改。固定字节测试的 SHA256 预期值独立用 PowerShell/.NET 计算，测试会拒绝把完整场景哈希当成 family ID。

关联边使用相同规范场景及同 `(generation_profile_sha256, base_index)` 的生成谱系，跨全部来源取传递闭包。profile 区分不同生成批次的同名 base，规范身份仍能连接跨来源同场景。未增加容差几何搜索，平移/变形的近重复局限仍存在。

## 4. R2：来源、台账和引用审计修复

7 个主名册批次仍共用 900 任务 / 300 family；另有 3 个 pilot 来源。逐个源文件重算 **6,380 条批次任务记录**（包含重复来源），原任务字节及规范身份不符均为 0。

台账先用 `(batch, mission_id)` 连接该批次自身的 profile/名册，再归并规范场景。30 个跨来源同名任务不再共享使用记录。10 个台账全部成功归属，未映射记录 0；主名册独立已执行任务仍为 **465/900**，未执行 **435/900**；pilot 的 **20 个 family 均有实际执行记录**，不再统称为仅规划。

审计在运行前登记 `repair_method.json`，来源与分类规则先于本轮扫描固定。扫描保存逐文件路径、字节、SHA256、用途、编码与命中身份；同时识别短 family ID 和完整场景哈希，排除当前阶段自身产物，避免自引用。文件名中的裸任务名不作为跨来源身份。

本轮文本范围库存 **30,311 个文件**，14,208,125 字节的逐文件 JSONL 清单仅保存在仓库外：

| 扫描类别 | 文件数 |
| --- | ---: |
| 一般文件/尚未分类的引用用途 | 11,443 |
| 生成任务输入 | 17,839 |
| 自动名册/台账枚举 | 267 |
| 离线规划准入报告 | 4 |
| 明确生产几何诊断 | 1 |
| 已知开发 fixture | 16 |
| 已知 M0/M1 开发资料 | 130 |
| 排除：当前阶段自身产物 | 29 |
| 排除：已知 outcome/episode 载荷 | 542 |
| 排除：超过 4 MB 的文本 | 40 |

扫描只提取身份 token，没有把其中的结果字段用于选择。被排除或未覆盖的资料不能作为“未使用”的证明。本轮最终没有任何候选进入留出，因此不存在依赖这些扫描缺口宣称候选洁净的问题。

`production_turns.json` 身份投影与生产 plan / mission_list 逐项连接；900 行逐机诊断记录覆盖 300 个 family。用途由历史 `audit_core.py` 和 `audit_report.md` 的方法说明确认，没有读取诊断数值来决定哪些 family 排除。

## 5. R3：12 格与负例计划修复

12 份真实 TaskSpec、原路径、SHA256 和输入字节全部保留，合计 **37,763 字节**。独立复核确认四个合法意图—飞法 × 2/3/4 机构成完整且无重复的 12 格。

- 6 个侦察方案：现有速度能力字段与尚未实现的阶段/单机作用范围分开；标为 `PENDING_M2_DESIGN`。降速可能只延长任务，也可能产生 timeout，均不能直接冒充覆盖语义 false。
- 3 个巡逻方案：删除可直接使用 `execution.start_delay_s` 的暗示。已有编译场景字段是 `phases[].start_delays_s`；额外运行期延迟/停留接口仍待设计。初始延迟可能只平移窗口，未证明会违反重访条件。
- 3 个快速通过方案：保留 M1 低速机制来源，但 3/4 机及返航变体没有完成验证，标为 `M1_MECHANISM_KNOWN_M2_CELL_UNVALIDATED`。

每格已写明作用飞机、语义阶段、完整观测与质量要求、未知/超时风险以及待设计替代方案。替代方案只是候选设计，没有实现故障注入。全部 `execution_status=NOT_RUN`、`actual_result=null`，本阶段实测负例为 0。

## 6. R4：回执及数据可用性

已更正上一阶段回执哈希，原误填值属于 M2-00。报告和摘要现在绑定 M2-01 的实际回执身份。

数据可用性记录与分组角色分开：有 TaskSpec 不代表有可用 SITL episode；有 finished 台账也不自动代表数据质量合格。原 143 个候选在登记台账内无执行记录，记为 `planned_only`；没有确认对照 episode，M3 尚未就绪。其已诊断身份同时使它们不能充当当前规则下的未使用留出。

未打开候选轨迹、标签、描述、质量/飞行成败或性能结果，没有执行快速引擎、SITL、训练或参数拟合。所有业务引擎源码、旧 M0/M1 报告/回执和旧迁移证据保持不变。

## 7. 测试与独立复核

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 合成身份/台账/关联/算法/覆盖检查 | **22/22，0 失败** | `unit_tests_01.log` |
| 独立实际证据复核 | **23/23，0 失败** | `independent_recheck_01.json/log` |
| 旧被审文件副本 | 52/52 哈希相符 | `before_manifest.json` |
| 旧 attempt / 冻结目录 | 原字节不变 | 独立检查记录 |
| 当前 12 格 fixture | 原字节、原始来源、机数一致 | 独立检查记录 |
| 仓库 JSON 大小 | 均小于 256 KiB | 划分 181,369 字节；矩阵 66,545 字节 |
| 业务回归/飞行 | 本轮未运行 | 本轮只改元数据、审计工具和文档 |

22 项合成测试覆盖同名不同来源、同族跨批次合并、pilot 归属、缺台账/未映射、短 ID 和冲突、开发关联传递、固定 family ID 字节与哈希、空候选阻塞、12 格漏格/重复。23 项实际核查由另一个脚本实现，没有导入修复工具，独立用原台账和 BFS 重建归属/图，并核对来源哈希、逐文件库存、数据可用性和负例状态。

命令均在 PowerShell 7 下通过项目 Conda 环境执行：

`conda run -n llm --no-capture-output python -B <attempt_02_repair 下的脚本>`

顺序为 `test_repair_metadata.py`、`repair_m2_02.py --out .../audit_run_01`、`publish_repair.py`、`independent_recheck.py`。四次均 exit 0；本轮没有失败测试或覆盖旧失败日志。首次审阅之前的失败/错误产物仍保留。

## 8. 交付与下一步

修复工具、方法、52 份原版副本、扫描大清单及日志：

`F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m2/M2-02/attempt_02_repair/`

新版本完整登记：

`F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/splits/split_2026101202_v2/`

仓库保留本报告、摘要、划分状态登记、覆盖矩阵和 12 份原输入。最终 commit/diff 与文件哈希绑定见修复后复核回执和外部 `final_identity_manifest.json`。

**修复正确性检查通过；M2-02 阶段结论仍为 BLOCKED。** 当前来源池不足，不能靠代码修复恢复有效盲测。下一步需要用户明确采用新的未使用 family 来源，或另行决定阶段范围；推荐先预登记新的来源生成方式和使用边界，再准备其身份元数据及 family 划分。该步骤将改变原“只从 r2 剩余 family 取留出”的来源约束，本轮没有擅自生成新任务、采集 SITL 或跳过门禁进入 M2-03。

交付过程补注：最终哈希清单首轮工具在 10 项交付检查通过后因局部变量 F 未定义而中止；失败脚本及 finalize_review_01.log 原样保留，后续仅补齐清单并复核哈希。未覆盖测试日志，未改业务代码或旧证据。
