# M2-02B 新来源补充实施报告

日期：2026-10-12。实现完成，复核 **PASS**；见 [复核回执](M2-02B_review.md)。下一步可由用户启动 M2-03 设计，本轮没有进入 M2-03。

## 1. 本轮解决的问题

原 M2-02 修复正确，但原 r2 全部 300 个 family 有历史开发诊断使用，合格留出为 0。用户随后授权按修正计划修改代码，补充新的未使用来源。本轮保持原判定和划分种子，新增独立来源；不将旧诊断来源重新命名后当作盲测。旧 BLOCKED 报告、回执、旧划分均保持原字节。

## 2. 实际代码与生成前登记

- 新增 `swarm_sim/fast_dynamics/holdout.py`：历史输入身份验证、保守几何视图、D4/平移/编号无关近重复、一一匹配、base 谱系传递排除、实际 family ID 的固定哈希划分、拒绝覆盖。
- 新增 `scripts/prepare_fast_dynamics_holdout.py`：register / freeze 两步入口；freeze 必须带登记文件 SHA256，核对全部源码和历史输入身份后才生成。
- 新增 `scripts/verify_fast_dynamics_holdout.py`：不导入 holdout 实现，以全排列匹配及图遍历独立重建结果。
- 新增 28 项合成测试并登记 CI。既有 generate_v2、动力学、执行器、语义规则和数据消费者未修改。
- 原生产 profile 仅改变 master_seed=2026101203、base_scene_count=144。原 20 次规划候选上限、采样分布、模板和准入规则保持不变。
- 生成前方法：[M2-02B_method.md](M2-02B_method.md)，SHA256 `c418767bfae99fa31b73cefef3acdfd38c63a16a74b1238b4885edc1752db453`。
- registration.json：`ea365803918b4f5f30628bfd4ad73cf27fd47dc5e68d36a9ae284a3a55ef181c`，登记时间 `2026-10-12T17:09:18.295266+00:00`。先 register 成功，随后显式携带该哈希执行 freeze；未事后调整方法、种子或批量。

## 3. 来源范围和访问记录

对原 6,380 条 batch 绑定记录、旧库存中的生成任务与开发 TaskSpec fixture、项目 v3 模板按路径合并，核验 **24,220** 份输入字节，投影为 **1,142** 个 scene_content_v1 物理身份。v2 的顶层 platform 仅作规范投影，未修改旧文件或旧 family 标签。这些历史输入一律排除，包含未执行/规划拒绝输入，规则比只排除已诊断来源更保守。

准备阶段结构探查曾解析 known_development_fixture 类中的 15 份历史非 TaskSpec 测试基准/哈希文件，未以其值筛选候选；正式登记将这三种文件名及副本排除且不打开。未读取历史候选轨迹、盲测运行结果或新留出结果。新生成器只运行静态 compile_task 规划准入。

所有任务运行数并非 0：回归测试确实执行了既有 M1 开发 fixture 的仿真和产物链；单次仿真调用、episode 数未计量。**本批 calibration / blind_holdout 的飞行执行数为 0**，未启动 SITL、M3 或训练。

## 4. 冻结结果

| 项目 | 数量 |
| --- | ---: |
| 固定 base / 规划接纳 base | 144 / 144 |
| 全部候选 family（包括规划拒绝） | 341 |
| 接纳 / 规划拒绝候选 | 144 / 197 |
| 接纳 TaskSpec | 432 |
| 历史关联排除分量 | 2（接纳 family 2，接纳任务 6） |
| 合格分量 | 142 |
| 校准 | 71 分量、178 个全候选 family、71 接纳 family、213 任务 |
| 盲测 | 71 分量、160 个全候选 family、71 接纳 family、213 任务 |

197 个规划拒绝候选和 289 条拒绝 variant 记录全部保留，不是 197 次执行失败。谱系中的拒绝候选也参与关联，不能只比最后选中场景。

实际排除：接纳 family `scene_7afb61d0e98bb0880239` 的分量接触旧 `scene_202e4bd5518e2273c398`；`scene_813099ddacb06dc82365` 的分量接触旧 `scene_f40618dbbc077ec0f6c4`。独立实现复现相同关系。

使用原 split seed=2026101202，按真实 family ID 去重排序、固定 JSON 字节、component/rank SHA256 和 floor(G/2) 冻结。未补抽或重排。新来源的任务名称可能与旧批相同，身份始终使用 source_id / family / 规范哈希，不以裸 mission_id 合并。

当前入口为 [evaluation_split_current.json](../../verification/fast_dynamics_m2/evaluation_split_current.json)，指向仓库外本轮原始冻结清单。旧 evaluation_split.json 继续保存历史 BLOCKED 记录，避免覆写回执绑定证据。新分配仅为 **FROZEN_INPUTS_ONLY**：NOT_RUN、actual_result=null、reference_episode_available=false；不代表 M3 对照数据就绪。

## 5. 验证证据

| 验证 | 结果 |
| --- | --- |
| 初轮针对性测试 | 80/80，0 skip，17.065 s |
| 最终新增模块及 M1 回归 | 67/67（28 新测试 + 39 M1），0 skip，16.669 s |
| 不导入新模块的独立实际复核 | 18/18 |
| 旧报告/回执/划分、12 份开发 fixture | 原字节身份复核，未修改 |
| Git | HEAD `16b7cb740d081f7c66e73ed80eff4c7bad8dbb5f`，无提交/推送，main 与 origin/main 未变 |

两轮测试有重叠，不相加宣称 147 项独立测试。未重跑完整离线 CI、DR130 或历史 M0/M1 验收；本次检查覆盖新增静态工具及所复用的生成器、路径策略和 M1 兼容范围。独立复核是同一作者的不同算法，不声称第二位审阅者。

原始日志在 `SwarmData/fast_dynamics/m2/M2-02B/work_01/`；冻结输入在 `.../M2-02B/attempt_01/`。命令复现表为 work_01/commands.md（事后整理，原始输出单独保留）。本轮未发生测试失败、生成流程中止或同名日志覆盖；规划拒绝按正常准入规则完整登记。

## 6. 局限和下一步

历史排除只保证所登记的本地输入范围，不保证未知外部来源。几何规则忽略平台、朝向、世界边界并含旋转/镜像，属于保守排除；没有证明任意尺度变化或非矩形拓扑的全部近重复。

旧 12 格开发矩阵与负例计划未变；其中 9 格物理负例机制仍待 M2-03 设计。新留出不能补开发覆盖格。M3 前仍需单独安排 reference episode 采集与访问隔离。下一步只执行 [M2-03 指令](M2-03_instruction.md) 的设计和测试规格，不提前实现控制器。
