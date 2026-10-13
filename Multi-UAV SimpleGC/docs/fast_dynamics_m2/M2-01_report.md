# M2-01 阶段报告：M1 证据迁移与外部输出约束

- 阶段 / attempt：**M2-01 / attempt_01**；前一修订为 `attempt_02_repair`；最终修订为 Codex 执行的 `attempt_03_id_guard`
- 状态：**PASS**（用户授权 Codex 直接完成最后修复并核验；最终回执 [M2-01_review_03.md](M2-01_review_03.md)）
- 上一轮 PASS 回执：[M2-00 最终放行回执](M2-00_review_03.md)，结论 `PASS`，SHA256 `d5fa9a6081163ad9514c7aacd2683f9d4b1b711c6c256eba5e086735e718f2e3`
- 本轮审阅回执：[M2-01 审阅回执](M2-01_review.md)，结论 `FIX_REQUIRED`（R1 默认输出根、R2 根归属与 run-id 逃逸），SHA256 `5e99c2428e7370117f38d7a88802345637513d0545c937ef83f04268a8a57a71`
- 撰写日期：2026-10-12；修订日期：2026-10-12（America/Los_Angeles）
- 依据：[M2-01 可转发执行指令](M2-01_instruction.md)（SHA256 `c659c690f0b612fb4b9ba273a7249b3e333a2de520292162ca0114b7af5856eb`）、[M2 分阶段指南](../fast_dynamics_engine_m2_staged_guide.md) §3–§5
- 摘要 JSON：[M2-01_summary.json](../../verification/fast_dynamics_m2/M2-01_summary.json)
- 外部 attempt：`F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m2/M2-01/`（`attempt_01` 首次执行、`attempt_02_repair` 本次修复）
- 修订范围：只改路径策略（R1/R2）、三个入口的根传递、路径测试与报告/摘要；**迁移、归档、清理、保留项未重做、未恢复、未改写**；修订记录见 §18。

## 1. 实际完成范围

| 指令条目 | 实际结果 |
| --- | --- |
| 1. 起点核对与本地检查点 | 已完成：核对 PASS 回执绑定的分支/HEAD/diff/报告/摘要/指令哈希全部一致；按显式白名单（12 文件）提交 M2-00 获准记录为 `57cca91`；未重复建分支、未改 `0f7c42d`、未 amend/reset、未 push |
| 2. 冻结迁移源清单 | 已完成：356 项逐文件路径/字节/SHA256；已批准分类 JSON（`fc2a4e66…`）200 项逐项复核，0 不符；确认候选 338（182 跟踪 + 156 忽略）、保留 18 |
| 3. 先复制并核验 | 已完成：整树复制到 `m01_archive/m01_20261012_v1/`，相对路径集合、逐文件 SHA256、总字节三项全等（356 / 30,216,091 / 0 差异）；源证据未改动 |
| 4. 验证新位置可用 | 已完成：7/7 最终样本从归档公共加载 + 审计通过，语言消费者产出 4 条描述且与新/旧位置派生结果字节一致；读取归属由审计钩子记录（归档 995 次读取、仓库证据 0 次）；中间 attempt 的失败在新旧位置完全同因 |
| 5. 验证通过后才清理 | 已完成：338 项经预检（根内、非联接、源哈希未变、归档副本哈希相同）后删除，0 错误；保留 18 项 + 小型迁移索引；旧 Git 历史未改写 |
| 6. 新输出只能进入外部根 | **首轮不合格，已修复**：默认根曾落在仓库内且目标未受所选根约束（审阅 R1/R2）。本版改为：默认根＝Git 根**同级** `SwarmData/fast_dynamics`；根与目标均在创建产物前校验（仓库外、根之下、全新、无联接逃逸），run-id 路径片段被拒；verify 向子 attempt 传递同一根。见 §7 与 §18 |
| 7. 必要验证与交付 | 已完成：路径正反例 25 项、受影响 M1 模块 64 项、离线清单 431 项、默认 run 真实完整链、verify 自定义根真实端到端；本报告与摘要 JSON，原修订当时状态 `AWAITING_REVIEW` |

## 2. Git 身份与本地检查点

| 项目 | 值 |
| --- | --- |
| 分支 | `codex/fast-dynamics`（未新建分支） |
| 迁移前检查点 | `0f7c42d8688880b1d8e1a416184383a94a5ae123`（未改写） |
| 本阶段记录检查点 | `57cca914f2e8b414e8820a1f08f6fd900f912d36`，父 `0f7c42d` |
| 检查点内容 | 12 文件（6 个入口/报告文档 + M2-00 报告/摘要 + 三轮回执 + M2-01 指令），白名单逐项核对一致，+1,079/−21 |
| 提交时跟踪 diff 身份 | 30,274 字节，SHA256 `19dc69cc4275705d97f95af3398607f33a4a3efaccf6345d78906b09a2e1c9c9`（与 M2-00 回执 §2 一致，提交后为空属正常，不回填旧回执） |
| 本轮修复期间新增提交 | 无（`57cca91` 之后 HEAD 未变） |
| `main` / `origin/main` | 仍为 `5e45637f2bf63054ed0ace2433fd7c9ea7b075ac` |
| 远端操作 | 无 push、无 tag、无 PR、无 fetch |

说明：`git diff --cached --check` 对 `M2-00_summary.json` 报 378 行 “trailing whitespace”，成因是该文件为 CRLF 行尾（其余文件为 LF）。该文件字节已被 M2-00 PASS 回执哈希 `571cb162…` 绑定，且仓库根 `.gitattributes` 为 `* -text`（保留精确字节），因此**保留原字节、不做行尾规范化**；除此之外无其它 whitespace 问题。

## 3. 迁移源冻结与逐项复核

- 源根：`Multi-UAV SimpleGC/verification/fast_dynamics_m01`；实测 **356 文件 / 30,216,091 字节**（与指令预期一致），其中跟踪 200、被忽略 156，无“未跟踪且未被忽略”的第三类。
- 冻结清单：`attempt_01/source_manifest.json`（SHA256 `b64143f154835d348562487a726b153ed49b120e284d6a6e6a2e347b6b730937`），含每项相对路径、字节、SHA256、Git 状态、保留/外置决定与理由。
- 已批准分类：`SwarmData/fast_dynamics/m2/M2-00/attempt_02_repair/evidence_classification.json`，实测 SHA256 `fc2a4e66d46f95d9da8f2e7923675c3ef6ac24cf425873a321751d1f48f55b3c`，与回执一致；其 200 项**逐项**对照源文件（路径、字节、SHA256）——**0 项不符**。
- 决定分布：保留 18 项 / 694,586 字节；外置 182 跟踪项 / 1,443,516 字节；外置 156 忽略载荷 / 28,077,989 字节。清理候选合计 **338 项 / 29,521,505 字节**；保留与候选无交集、无未分类项。156 项忽略载荷也在清单中逐项列明（64 个 CSV 轨迹/观测载荷、88 个 dataset 树内逐样本 JSON、4 个原始日志），未用“扩展名/目录即结论”的口径代替逐项登记。

## 4. 复制与逐字节核验

| 项目 | 值 |
| --- | --- |
| `migration_id` | `m01_20261012_v1` |
| 归档根 | `F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m01_archive/m01_20261012_v1/` |
| 镜像根 | `<归档根>/Multi-UAV SimpleGC/verification/fast_dynamics_m01/` |
| 映射规则 | `<仓库>/Multi-UAV SimpleGC/verification/fast_dynamics_m01/<相对路径>` ↔ `<归档根>/Multi-UAV SimpleGC/verification/fast_dynamics_m01/<相对路径>` |
| 核验结果 | 源 356 / 30,216,091，归档 356 / 30,216,091；**missing=0、extra=0、hash/size 不符=0** |
| 核验记录 | `attempt_01/copy_verification.json`，SHA256 `3149299152147627f6c9a50c652a2257e7b9cb51fd42a56ca0f4004f8adab4d5` |
| 逐文件映射索引 | `<归档根>/relocation_index.json`（291,441 字节，356 项，SHA256 `e023a4e3194f12790279710c3f2a785208a7165b1be736c5d55bdea0c5ccb55e`） |

复制采用逐文件 `shutil.copy2`（内容 + mtime），源文件未修改、未删除；历史 `run_directory` 等字段保持原义，新位置以独立索引表达，未做全树路径替换。本轮修复未触碰归档与清理结果。

## 5. 新位置可用性与可追溯性验证

在两个位置各跑同一次消费者检查（`attempt_01/consumer_check.py --root archive|repo`）：

| 消费者 | 归档结果 | 仓库对照 | 证据 |
| --- | --- | --- | --- |
| 5 个成功样本 + 语义失败样本 | `load_episode` 通过：294/294/294/294/294/1637 帧，形状 \(T\times2\times6\)，`time_base=sim_clock` | 相同 | `consumer_check_archive.json` / `consumer_check_repo.json` |
| 超时未知样本 | 1 帧、加载通过 | 相同 | 同上 |
| `audit_dataset` | 7/7 `issues=[]`；未知样本 `semantic_unknown=1` | 相同 | 同上 |
| `describe_dataset` | 4 条描述、`skipped_episodes=0`，输出写全新派生目录 | 4 条描述 | 同上 |
| `load_public_scene` | 4 个公开角点 | 相同 | 同上 |
| 中间 attempt | `ValueError: inconsistent or unsupported source capabilities, units, seed or code identity` | **完全相同** | 同上 |

- **读取归属（关键证据）**：用 `sys.addaudithook` 记录消费者调用期间的每次 `open`——归档运行 **995 次归档读取、0 次仓库证据读取**；仓库对照运行 **0 次归档读取、995 次仓库证据读取**。审阅方另行在旧载荷已移除后独立复跑，得到相同的可用性与 0 次仓库证据读取。
- 加载器元数据 `source_directory` 在归档运行下解析到归档路径，在对照运行下解析到仓库路径，进一步确认来源解析正确。
- 派生等价性：归档与对照（以及更早的一次试跑）各自生成的 `descriptions.json` SHA256 均为 `35d5f7d8d3fbe2ced7a486c6454ee579fbfdbc9310032eb83e75f1393143d752`，三份字节一致。
- 可追溯性：5 个成功样本的 `report.json` 均含 `simulation_wall_s`、`end_to_end_wall_s`、`episode_realtime_factor`；`final_historical_regression/` 5 个汇总、`m0_source_index.json`、`m0_evaluation_split.json`、`integration_attempt_01/`（completion + report + 11 个 run/analysis JSON + language 清单）与阶段级 `completion.json` 均在归档内可定位。
- 审计钩子只能覆盖 Python 审计事件，不宣称捕捉任意原生 I/O；本阶段消费者主要通过 `Path`/`open` 读取载荷，且旧轨迹载荷已不存在。

## 6. 清理（仅在上述验证通过后执行）

- 预检（删除前，全量 338 项）：绝对路径必须落在 `Multi-UAV SimpleGC/verification/fast_dynamics_m01` 内、路径链上不得有联接/符号链接、源文件哈希须与冻结值一致、归档副本须存在且哈希相同 → **338/338 通过、0 项拒绝**（另一次独立 dry-run 亦为 338/338）。
- 删除结果：**338/338 删除成功、0 错误**；清理后删除因此变为空的目录 64 个（仅限证据根内，遇联接一律跳过）。
- 删除后证据根：**18 项保留文件 / 694,586 字节**，无空目录残留；本轮修复未变动该状态。
- 清理台账：`attempt_01/cleanup_ledger.json`（逐项路径、字节、SHA256、归档副本、删除结果），SHA256 `2f084a8eceaea45e6360c96fa632df0a30d065660276bb49319a1e83c0946fda`。
- 保留 18 项：`collect_baseline.py`、8 个阶段级汇总（基线/DR130/v0.5 加载/内核基准/来源索引/划分安排/数值收敛/步长减半）、`final_historical_regression/` 5 项、`final_verification_01/` 的 `verification.json`/`tests.json`/`completion.json`/`mission_convergence.json`。
- 新增仓库侧小型索引：[migration_index.json](../../verification/fast_dynamics_m01/migration_index.json)（1,951 字节，SHA256 `96a3678d710e1a8093d008410ca2b55ecbde19ee55cb76ea3a3b9048fb6f7ad3`），指向归档根与逐文件索引。
- 旧 Git 历史不变：`0f7c42d` 仍含被清理文件的旧对象，本次只改最新树，未 amend/reset/filter-repo。

## 7. 外部输出根与路径保护（本版已修复 R1/R2）

`swarm_sim/fast_dynamics/output_policy.py`（公共库，无机器绝对路径）：

- **默认根**：`default_output_root()` = `repository_root().parent / "SwarmData" / "fast_dynamics"`，即 Git 根（`Simulation-dev`）的**同级**目录 `F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics`，解析后位于仓库外。优先级：`--output-root` > 环境变量 `FAST_DYNAMICS_OUTPUT_ROOT` > 默认根。
- **根校验** `assert_usable_root`：根必须在仓库外、不得是文件、且解析后不得因联接落回仓库；不合格根在创建任何产物前报错（`parser.error` → exit 2）。
- **目标校验** `assert_new_attempt_path(path, root)`：目标必须①在仓库外；②在所选根之下（解析后比较，覆盖 `..` 与联接逃逸）；③尚不存在。所选根可以尚未创建。
- **前缀校验** `sanitize_component`：`--run-id`/attempt 前缀拒绝空值、首尾空白、`.`/`..`、路径分隔符与盘符、Windows 保留字符/设备名、首尾点；`new_attempt_path` 因此无法被路径片段带出根。
- **创建后复核** `assert_created_within`：目录创建后再次确认其解析位置仍在仓库外且位于所选根之下，失败则删除刚建的空目录。
- **三个入口**：`run_fast_dynamics.py`（`--output` 可省略，缺省 `<root>/<UTC 时间戳>_<run-id>`）、`benchmark_fast_dynamics.py`（`--output` 必须为根下新文件；仅给 `--output-root` 时写 `<root>/<UTC 时间戳>_kernel_benchmark.json`；两者都不给则维持 stdout 分支且**不写文件**）、`verify_fast_dynamics_m01.py`（自身目标按同一规则校验，并**向子 `run_pipeline` 显式传递同一 `--output-root`**）。
- 产物身份一致性：`attempt.json`、`report.json`、`verification.json` 记录 `output.path`/`output.root`/`output.root_source`；真实端到端验证确认子 attempt 记录的根与实际路径一致。
- 未改变的行为：SITL 与其它入口未触及；`write_episode`/`build_dataset`/`describe_dataset`/`load_episode` 保持旧的宽松契约（策略只在入口脚本生效）；失败 attempt 仍保留输入、配置与 `failure.json`，不写完成标记。

## 8. 验证、命令与结果

| 验证 | 命令要点 | 结果 |
| --- | --- | --- |
| 路径保护正反例（重写扩充） | `python -B -m unittest -v test_fast_dynamics_output_policy` | **25/25 通过**、0 跳过（含：默认根位置与仓库外判定、默认 run 真实完整链、默认 verify 非自拒、显式/环境根归属、根外 `--output` 被拒且零产物、run-id 片段拒绝、三个 junction 用例真实执行、verify 自定义根贯通与产物根身份、三入口拒绝仓库输出、重复 attempt 与失败留痕） |
| 受影响 M1 模块 | `test_fast_dynamics_core + execution + artifacts + output_policy` | **64/64 通过**，20.7 s（其中 execution 的 CLI 用例按新契约显式传入隔离根） |
| 完整离线清单 | 按 `unit-tests.yml` 取 39 个模块后 `python -B -m unittest -v @modules` | 执行 **431 项：430 通过、1 跳过**，`OK (skipped=1)`，exit 0，109.5 s（墙钟 110.7 s）；日志 `attempt_02_repair/offline_ci_after_fix.log` |
| 唯一 skip | 同上 | `test_parallel_batch….test_native_windows_short_name_is_accepted`：测试临时目录定向到 F: 后该卷无 8.3 短名；用默认 C: TEMP 单独复跑为 `OK`，与路径策略无关 |
| 默认 root 真实运行 | `run_fast_dynamics.py <fixture>`（无输出参数） | exit 0，`complete`、294 帧；`output.root_source=default sibling SwarmData/fast_dynamics`；产物在默认根下的新 attempt |
| verify 真实端到端（自定义根） | `verify_fast_dynamics_m01.py --output-root <attempt_02_repair>/verify_e2e_custom_root` | exit 0，131.8 s；旧清单 36 模块 **392 项（391 通过、1 跳过）**、新清单 3 模块 **39/39**；7 个用例结果与 M0/M1 一致；`verification.json` 与子 `success_01/attempt.json` 的根身份均为该自定义根 |
| 修复前后复现对照 | `attempt_02_repair/repro_path_defects.py` | 见 §18 与 `repair_log.md` |

本轮**没有**重跑 M0/M1 的验收判定（上述 verify 端到端是路径可用性检查，不作为新的 406/406 验收结论；M0/M1 验收仍绑定原证据与原始日志）。

## 9. 文档与入口更新

| 文件 | 更新内容 |
| --- | --- |
| [M0/M1 报告](../fast_dynamics_engine_m01_report.md) | 顶部新增“证据位置迁移”说明（归档根、migration_id、索引与哈希、映射规则、计数）；被清理文件的证据链接改为指向归档绝对路径；复现命令改为 `--output-root` 外部输出并说明拒绝规则；§6 补注中间 attempt 的拒绝原因 |
| [适配备忘](../fast_dynamics_engine_adapter_memo.md) | 证据位置说明改为归档；`baseline_ci.log` 链接改为归档路径 |
| [开发交接](../fast_dynamics_engine_kickoff.md) | 头部进度、首包入口命令（外部输出）、§6 证据条目、实施登记表（M2-01 行） |
| [M2 阶段指南](../fast_dynamics_engine_m2_staged_guide.md) | 进度补注更新为 M2-00 PASS + M2-01 待审阅 |
| 根 `README.md`、根 `CLAUDE.md`、项目 `README.md` | M2-01 状态、检查点 `57cca91`、外部输出根与迁移位置、后续窗口提示词 |

**字节与结论的区分（按审阅要求表述）：** M0/M1 报告、适配备忘、交接、指南、三个 README/CLAUDE 的**文档字节已改变**（导航链接、迁移位置与进度补注）；它们的**历史验收日期、判定、数字与源身份没有改变**，也没有据此重算任何旧结论。M2-00 阶段报告与三轮回执在本阶段**未被触碰**，保持原字节（其哈希仍被回执绑定）。

## 10. 业务改动范围（未提交，待审阅）

| 文件 | 字节 | SHA256（修复后） |
| --- | ---: | --- |
| `swarm_sim/fast_dynamics/output_policy.py`（最终修订） | 9,134 | `9c49f7fe93d1af95b6fbddd83113cf4e5b23c52a0746f8e8ebcae10df7aa4909` |
| `tests/test_fast_dynamics_output_policy.py`（最终修订） | 22,417 | `25e9fb4fe1da4aea42300c35466d234b1683d67a31024576949fc8cdcfb9d9c3` |
| `tests/test_fast_dynamics_execution.py`（CLI 用例显式传入隔离根） | 8,098 | `b57dd86e6738f77b1ab930ba50e3582e4eebffb26ca462288ed25c702bacb6fa` |
| `scripts/run_fast_dynamics.py`（最终修订） | 6,648 | `f3a5864c2b74c60d2bd3ef99e78d75c7279cad4766d84212e5597c75ab79410f` |
| `scripts/benchmark_fast_dynamics.py` | 14,907 | `b14f2675ca830c3060ef32d3dfe3379f6d52765c570cbafec2680edcde9a04fb` |
| `scripts/verify_fast_dynamics_m01.py` | 7,866 | `3f2a634ada204fb49128c00fd55be8b01c8aaf7d04768918d61720667852a975` |
| `.github/workflows/unit-tests.yml` | 3,579 | `0ccb719c321fc237cbea9daae04bcbf9f3b8705d1d391f967f88e0a4b25c5267` |
| 文档、迁移索引与审阅回执 | — | 旧 16 项快照属于 attempt_02_repair 历史身份；最终可执行文件身份见 `attempt_03_id_guard/source_snapshot_final.json`，文档身份见 `final_validation.json` |

未修改：`swarm_sim` 其它模块、其余测试、`requirements.txt`、`.gitignore`、`.gitattributes`、SITL 入口与语义阈值；公共产物/loader API 契约未变。

## 11. 历史工作树状态（attempt_02_repair 结束时）

| 项目 | 值 |
| --- | --- |
| 分支 / HEAD | `codex/fast-dynamics` / `57cca914f2e8b414e8820a1f08f6fd900f912d36`（本轮无新提交） |
| 未提交条目 | 200：**182 个跟踪文件删除**（证据清理）+ 12 个跟踪文件修改 + 6 个新增（`output_policy.py`、策略测试、`migration_index.json`、本报告、摘要 JSON、审阅回执） |
| diffstat | 194 files changed, 138 insertions(+), 36,846 deletions(−)（不含未跟踪文件） |
| 跟踪 diff 原始字节身份 | 1,627,170 字节，SHA256 `19782fb7a966ba85626c9de4fd847e3b19897642472f0ebfbcf47c13150d2b4a` |
| 仓库证据根 | 18 项保留文件 + `migration_index.json`，无空目录 |
| 归档 | 356 文件 / 30,216,091 字节 + `relocation_index.json` |
| `main` / `origin/main` | 未变（`5e45637`）；无 push/tag/PR |

## 12. 资源

| 项目 | 值 |
| --- | --- |
| 阶段墙钟 | 首次执行约 06:33–07:20；本次修复约 07:28–07:55（America/Los_Angeles） |
| 迁移数据量（首次执行，未重做） | 复制 30,216,091 字节；清理 29,521,505 字节；保留 694,586 字节 |
| 外部证据体积 | `attempt_01` 30,248,334 字节；`attempt_02_repair` 约 1.9 MB（含被审副本、日志、端到端验证产物） |
| 测试运行 | 路径测试 25 项（4.3 s）、受影响模块 64 项（20.7 s）、离线清单 431 项（109.5 s）、verify 端到端 131.8 s、两次复现、默认 run 多次 |
| 默认根下的真实 attempt | 7 个完整 M1 链 attempt（14:36–14:45，各约 2.59 MB，由测试/复现/验证运行产生，全部保留） |
| 未做 | 未启动 SITL、未续跑旧批次、未准备 r3、未读盲测、未做 M2-02 数据筛选、未执行 M2 飞行功能 |

## 13. 异常与失败 attempt

| 现象 | 影响 | 处理 | 证据 |
| --- | --- | --- | --- |
| **R1 默认输出根落在仓库内**（审阅独立复现） | 默认 run/verify 被策略自行拒绝，文档默认命令失效 | 改为 Git 根同级目录并新增根校验 | `repro_before_fix.json` / `repro_after_fix.json` |
| **R2 目标未受所选根约束**（审阅独立复现） | 根外 `--output` 可写入产物；run-id 路径片段可逃逸 | 新增根归属校验与 run-id 前缀校验；verify 向子入口传根 | 同上 |
| 修复中新测试暴露：所选根尚未创建时被误拒 | 自定义根首次使用时不可用 | 删除冗余的“最近存在祖先须在根内”检查（解析后包含判断已覆盖联接逃逸） | `PASS1_TEST_LOG_OVERWRITTEN.md` |
| 修复后首轮策略测试日志被同名覆盖 | 首轮原始日志丢失 | 失败清单与原因保留在说明文件；后续改用新文件名 | `PASS1_TEST_LOG_OVERWRITTEN.md` |
| `after_fix` 复现首轮脚本未捕获预期异常而中止 | 该轮 JSON 未写出 | 保留 `repro_after_fix_pass1_crash.log`，修正脚本后用新文件名重跑 | `repro_after_fix_pass1_crash.log` |
| `before_fix` 复现首轮 argv 干扰（verify 参数解析） | 该轮 R1c 结果不可用 | 保留 `repro_before_fix_pass1_argv_artifact.json` 与说明；修正后重跑为可用基线 | `PASS1_ARGV_ARTIFACT_NOTE.md` |
| 离线清单 1 项 skip（8.3 短名，卷相关） | 与路径策略无关 | 用默认 C: TEMP 单独复跑为 `OK`；已登记分母与原因 | `offline_ci_after_fix.log` |
| 首轮迁移执行中的其它过程问题（脚本自身 bug、空目录、CRLF） | 见 §18 与 `attempt_01/commands.log` | 已在前一轮如实登记 | 本次未变更 |

没有发现迁移导致的证据损坏、缺失或哈希不符。

## 14. 留出保护

本阶段未建立、未读取、未使用任何 `calibration` / `blind_holdout` 数据，也未做 family 筛选或划分；`m0_source_index.json`、`m0_evaluation_split.json` 只是被迁移与保留，未解析用于开发决策。集合仍待 M2-02 冻结，因此本阶段不声明任何交集结论。

## 15. 未完成项

| 未完成项 | 归属 |
| --- | --- |
| 本阶段新代码、脚本改动、182 项删除与迁移索引的提交 | 本阶段已获 PASS，由用户明确启动下一阶段时按白名单提交 |
| family 预划分、12 个真实任务登记、初始覆盖矩阵 | M2-02 |
| 三意图四飞法、连续跟踪、2/3/4 机、数值/确定性/性能收口 | M2-03…M2-12 |
| 迁移索引在 M2 后续阶段的维护（新增证据一律外部） | 后续阶段遵循 §7 的策略 |

## 16. 先前提交的复审范围（已完成）

请重点核查本轮修复：

1. **R1 默认根**：`output_policy.py` 的默认值是否确为 Git 根同级 `SwarmData/fast_dynamics`（相对关系而非硬编码盘符）；默认 run/verify 是否不再被策略自行拒绝（§8 的真实运行证据与 `repro_after_fix.json`）。
2. **R2 根归属**：`assert_new_attempt_path` 的“仓库外 + 根之下 + 全新 + 联接逃逸”判定是否覆盖审阅给出的两组复现；run-id 片段拒绝是否在生成任何路径之前生效；`--output-root` + 根外 `--output` 是否零产物。
3. **根传递**：`verify_fast_dynamics_m01.py` 是否把上层根传给每个子 `run_pipeline`；真实端到端产物里 `output.root` 与子 attempt 的 `output_root` 是否与实际路径一致（而非仅 mock 通过）。
4. **测试有效性**：25 项路径测试是否按回执第 4 条覆盖全部遗漏行为（默认根位置、默认入口、根归属、run-id、junction、根传递、原有反例），junction 用例是否真实执行而非跳过。
5. **未回归项**：M1 CLI 用例改为显式隔离根后是否仍验证“失败留痕 + 重复 attempt 拒绝”；公共库 API 与语义阈值是否未被改动。
6. **一致性**：§9 是否如实区分“文档字节已改”与“历史验收结论未变”；被清理文件的链接是否全部指向归档；`attempt_01` 与审阅目录是否保持原样。

## 17. 下一步

**M2-01 已获最终 PASS。** 等待用户将 [M2-02 任务计划](M2-02_instruction.md) 交给执行模型；本轮不提交、不开始划分、不读盲测、不启动 SITL。

## 18. 历史修订记录（attempt_02_repair）

| 项 | 内容 |
| --- | --- |
| 时间与目录 | 2026-10-12 07:28–07:55；外部 `SwarmData/fast_dynamics/m2/M2-01/attempt_02_repair/` |
| 审阅基线 | 分支 `codex/fast-dynamics`、HEAD `57cca91`（未变、无新提交）；`main`/`origin/main` 仍为 `5e45637` |
| 被审版本 | 报告 `fc24355f…a8aa`、摘要 `ca294009…9dc5`、`output_policy.py` `1e485b55…7c64`、路径测试 `6f410068…597c`；副本与回执值逐字节一致 |
| 修复前复现 | 默认根在仓库内、默认 run/verify 均 `SystemExit(2)`；根外 `--output` 被接受并写出 4 个产物；run-id 逃逸路径被接受（详见 `repair_log.md` §2） |
| 修复内容 | 默认根改为 Git 根同级；新增根校验、根归属校验、run-id 前缀校验、创建后复核；三个入口统一校验并在产物创建前拒绝；verify 向子入口传根；M1 CLI 测试显式传隔离根 |
| 修复后复现 | 默认根在仓库外且符合位置规则；默认 run 走完整链；默认 verify 到达运行体；根外 `--output` 被拒且零产物；run-id 逃逸在生成路径前被拒；根内对照仍被接受（详见 `repair_log.md` §4） |
| 验证计数 | 路径测试 25/25；受影响模块 64/64；离线清单 431 项（430 通过、1 项卷相关 skip；已另行补跑通过）；verify 自定义根真实端到端 exit 0（392+39 测试，子 attempt 根身份一致） |
| 未重做 | 归档 356 项、清理 338 项、保留 18 项均未触碰；未提交、未 amend、未 push；未重跑 M0/M1 验收判定 |
| 状态 | 仍为 `AWAITING_REVIEW`，等待 Codex 复审 |

## 19. Codex 最后修复与收尾（attempt_03_id_guard）

用户授权 Codex 直接完成最后修复。新 `validate_run_id` 按公共产物既有 ASCII ID 语法及 Windows 文件名限制校验，CLI 在任何自动/显式输出分支选择、任务读取、目录创建和模拟之前无条件调用；benchmark 的通用 `.json` 前缀没有被收紧。

新增 11 类非法 ID × 两种输出模式的配对断言：参数拒绝、任务读取与模拟调用均为零、隔离目录没有新增条目。合法显式 ID 实际完成公共链（294 帧、语义 true、4 描述）；原自动/默认完整链、junction、失败留痕与重复 attempt 检查保留。

最终针对性测试 **66/66 通过，0 失败/错误/跳过**（core 15、execution 10、artifacts 14、policy 27），23.476 s；原始结果见外部 `targeted_tests_pass2.json` 和 `targeted_tests_pass2.log`。本轮不重跑完整离线清单或 verify。

首次辅助 runner 因缺少 Windows 多进程 `__main__` 保护，结果为 65 通过、1 worker 用例错误；原脚本、日志和结果保留。只修外部 runner 后以新文件名复跑，得到最终通过，不混写为业务代码错误。

归档、清理、保留项和此前真实 verify 根贯通证据保持原样。旧完整离线运行的准确计数为 431 总数、430 通过、1 跳过；该跳过用例已在 C: 独立补跑通过。本轮 66 项不是新的全量 CI 结论。

最终放行为 **PASS**，见 [最终回执](M2-01_review_03.md)。下一阶段是 [M2-02 来源、划分与任务登记](M2-02_instruction.md)，当前尚未执行。修复前 11 文件原样副本及哈希在外部 `before/`、`before_manifest.json`；最终可执行源码、差异、文档与证据索引在 `source_snapshot_final.json`、`tracked_diff_final.patch`、`final_validation.json`。
当前 HEAD 为 `57cca914f2e8b414e8820a1f08f6fd900f912d36`。跟踪差异 1634145 字节，SHA256 `49945d06b9de5a9759ee51e8d136fa737a18f82c3ac6a17b907926b096c48539`；口径为 Git 根 `git diff --binary --no-ext-diff --no-color HEAD --` stdout 原始字节，不含未跟踪文件。

当前工作区：182 项跟踪删除、12 项跟踪修改、9 项未跟踪文件；未提交。
