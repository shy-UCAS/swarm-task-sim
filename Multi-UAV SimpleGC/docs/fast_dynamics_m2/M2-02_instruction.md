# M2-02 任务计划：冻结 family 划分与真实任务登记

本文件仅提供下一小节计划。M2-01 最终 PASS 后，用户将下方指令交给执行模型才启动 M2-02；当前尚未读取 r2 候选、生成划分或运行覆盖任务。

本阶段交付是可复算的来源/划分与任务清单，不是飞行实现。分成四个顺序步骤完成本轮，然后统一停下审阅：

| 步骤 | 要完成的内容 | 检查结果 |
| --- | --- | --- |
| A | 核对来源与使用记录，建立可用/排除/待核实清单 | 14 个 T1/T4 family 保持开发角色，候选不混入已使用资料 |
| B | 先登记重复关联规则，再按分量冻结校准/盲测划分 | 固定种子、稳定序列化、无 family/关联分量跨组 |
| C | 从开发来源登记 12 个真实任务及配对负例方案 | 4 个合法意图—飞法 × 2/3/4 机全部有原始任务来源 |
| D | 静态验证、报告及停止 | 清单可复算、输入与结果字段分开、未运行候选或盲测 |

```text
现在只授权执行 M2-02：来源审计、family预划分、真实任务矩阵登记。
完成后写报告和摘要，状态AWAITING_REVIEW并停止，不执行M2-03或飞行任务。

工作目录：
F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-dev/Multi-UAV SimpleGC
Git根：其父目录Simulation-dev
输出根：F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics

先读根README/CLAUDE、项目AGENTS、.conda-env、M2阶段指南的通用指令与M2-02，
以及 docs/fast_dynamics_m2/M2-01_review_03.md 最终PASS回执、阶段报告和摘要。
先核对当前HEAD/diff/源码与回执绑定；不要重复迁移、重建分支或重做M0/M1检查点。

启动本阶段时可用显式白名单提交上一轮已获PASS的M2-01代码、测试、报告、索引、
必要入口文档、审阅回执及本指令。已批准的182项跟踪删除须逐项纳入检查点清单，
不使用无筛选git add -A；新增原始证据仍留在仓库外。记录新本地SHA，不push、不amend。
本轮新实现和结果留待审阅，不自行提交或PASS。

A. 来源与使用记录
1. 以M0已有来源索引、现有TaskSpec/scene元数据和来源记录为依据，核对T1/T4的
   14个family仍全部为development_reference。T系列的K是并行任务数，不是任务飞机数。
   合并重复运行、跨意图、后端和参数变体；同family不因换源或引擎获得新测试身份。
2. 检查r2未进入任何T系列的其余family及使用史。只能读取身份/使用记录所需元数据，
   不读取候选轨迹、质量/成功结果、标签、描述或性能结果来筛选“容易的盲测”。
   未进入T不等于从未用于调参或诊断；已使用、近重复、使用史不明分别记录，
   使用史不明者进入quarantine/待核实，不默认纳入blind_holdout。
3. 冻结候选roster，含原来源路径及哈希、family_scheme/family ID、规范scene身份、
   与T/已用来源的关联、使用史证据、纳入/排除/待核实原因。大清单写外部新attempt。
   若无法仅凭安全元数据确认身份，登记缺口，不靠打开留出结果来补证。

B. 先定关联规则，再确定划分
4. 查项目已有的规范scene/family/近重复规则，先把采用的方法、字段、单位、精度、
   对ID/顺序/平移等变体的处理及局限写成方法登记，才进行候选分组。
   同family、相同规范scene或预登记近重复关联形成泄漏连通分量，全分量同组。
   不把“只比原文件SHA256”说成排除了近重复；不得按运行结果反向决定关联阈值。
5. 固定划分算法如下，不反复换种子求均衡：seed=2026101202。
   每分量family ID去重，按Unicode码点排序；用json.dumps(ids,ensure_ascii=True,
   separators=(',',':'))序列化，UTF-8字节SHA256十六进制为component_id。
   按SHA256(UTF-8('2026101202|' + component_id))排序，哈希并列按component_id。
   G个可用分量的前floor(G/2)个为calibration，其余为blind_holdout。
   分量大小不同可能使family数不是各半，报告实际数量，不重抽。
   G<2或无法找到可确认未使用的候选时明确BLOCKED，不能宣称有效盲测划分已完成。
6. 冻结evaluation_split.json与来源/排除/关联清单哈希、种子、方法版本和分组结果。
   固定小型合成ID用例证明：输入顺序/重复运行不改变归属，关联分量不跨组，
   同配置重算一致。写完后不更改分组；发现源身份错误时保留原版并停止请求审阅。
   M2不运行calibration/blind_holdout；未来M3只用calibration与登记开发资料，
   blind_holdout保留给独立验收。开盲后改模型会使该集合降为开发，需要新的最终测试。

C. 12个真实任务与负例设计
7. 从已知开发来源选任务，不用刚冻结的校准/盲测池补覆盖。四个合法组合是：
   reconnaissance / equal_strip_lawnmower；
   reconnaissance / equal_strip_rectangular_spiral；
   patrol / staggered_same_loop；
   rapid_passage / line_abreast。
   每组合登记真实2/3/4机TaskSpec各一个，共12个单元；机数从任务scenario实际读取。
   保留原字节、来源路径和哈希，不删飞机、改名字或改输入凑格，不复制源成功标签。
   输入复制可作为小型fixture，但只能是已知开发输入，标明来源；大详情写外部。
8. 每个任务配一个拟定的状态改变负例方案，共12组正负配对。此阶段不运行：
   记录计划改变的执行配置/时段、预期影响及正式失败条件，actual_result=null、
   execution_status=NOT_RUN。失败要来自实际状态变化，不能改标签、语义阈值或删观测。
   区分任务失败false、未知null、质量不合格和引擎错误；不能预填实测成功。
9. 登记返航/无返航、阶段释放、终点悬停、错峰、航点数、扫描转弯、窄条带、
   巡逻圈次/重访与多机相对时序。真实任务不足的特征由合成边界用例补充计划，
   合成用例单列，不计入真实12格。缺真实单元就报告缺口，不借用blind任务。
   巡逻正式成功条件以注册perimeter_revisit_v2为准，不恢复v1的旧群体访问次数门槛。

D. 静态验收与停止
10. 验证family/规范scene/泄漏分量在development、calibration、blind之间无交集；
    方法、候选排除、使用史和局限可追溯；划分能从冻结输入复算。
    验证12格的意图/飞法/机数、输入哈希、配对方案和NOT_RUN状态；未知/缺口如实列出。
    所有验证只用安全元数据和合成单元测试，不调用快速引擎/SITL，不拟合控制参数。
11. 原始清单、静态验证日志放 SwarmData/fast_dynamics/m2/M2-02/<全新attempt>/；
    划分详情可放 splits/<split_id>/。仓库只保留小型摘要、必要小输入和报告，
    单个摘要JSON<=256KiB，超出时外置详情并保留索引。
    交付：docs/fast_dynamics_m2/M2-02_report.md；
    verification/fast_dynamics_m2/M2-02_summary.json、evaluation_split.json、coverage_matrix.json。
    报告列出实际读取范围、来源与排除计数、分量/family/任务分母、固定方法/种子/哈希、
    12格及负例方案、静态验证命令和结果、未解决项，以及本轮没有执行任何覆盖任务。
12. 状态AWAITING_REVIEW，完成后停止；必要输入缺失时为BLOCKED并说明具体缺口。
    不自行修成“看起来完整”的数据划分，不执行M2-03，不运行M3/M4/M5、SITL或训练。

Windows使用PowerShell7，Python使用项目Conda环境。保持旧证据只读；不覆盖旧attempt，
不push、PR、标签、reset/clean；不修改冻结Simulation或Simulation-dev-wip。
```
