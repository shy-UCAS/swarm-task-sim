# M2-03 任务计划：冻结连续跟踪、阶段事件与版本设计

本文件供用户转发后执行。本轮 M2-02B 只建立了新的留出输入，未开始 M2-03。先核对 `M2-02B_review.md` 的 PASS 与文件身份，不能将本任务计划视为已经实现的功能。

## 可转发指令

```text
现在只执行 M2-03：设计冻结与独立验收规格。完成后 AWAITING_REVIEW 并停止。
不实现 M2-04 跟踪器，不运行 M2 覆盖任务，不执行 M3、SITL 或训练。

工作目录：F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-dev/Multi-UAV SimpleGC
输出根：F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics
先读项目 AGENTS/.conda-env、根 README/CLAUDE、阶段指南通用约束、M2-02_review_02.md、
M2-02B_method.md、M2-02B_report.md 和 M2-02B_review.md。

0. 核对起点及本地检查点
   - 核对 HEAD、diff 和回执文件哈希，保留现有未提交工作。
   - 原 M2-02 的 BLOCKED 是历史结论；M2-02B 已按用户授权补充新来源。
     当前划分入口是 verification/fast_dynamics_m2/evaluation_split_current.json。
     不改旧 evaluation_split.json，不恢复旧 71/72 分配，不重新生成/划分新来源。
   - 用户启动本阶段后，可按指南为上轮获准工作创建本地检查点：五份入口文档、CI、
     M2-02 修复报告/回执/摘要/旧划分/覆盖矩阵/12 个开发 fixture，以及本轮 M2-02B
     方法/报告/回执/摘要/当前划分索引、holdout.py、prepare/verify_holdout 两个脚本、
     对应测试和本指令。展开为逐文件显式白名单，核对 staged 集合和回执再提交。
     不用 git add -A，不纳入外部批量输入；不 amend/reset/push/tag/PR。
     新增本阶段设计产出留待审阅，不自行提交。

A. 从已有开发任务提取契约（不使用新校准/盲测输入）
1. 只使用 coverage_matrix.json 绑定的 12 个 T1/T4 开发 TaskSpec，验证原字节和来源。
   可静态 compile_task 提取 semantic_plan；不运行快速飞行引擎。
2. 阅读 references.py、controllers.py、mission_executor.py、adapter.py、contracts.py、
   artifacts.py 及真实注册验证器。登记实际函数/字段/调用路径，不能只写概念方案。
3. 按三意图给出一份路线—角色—阶段映射：中间点、停留点、阶段终点、各机职责、
   服务机集合和等待条件。返回任务规定的空中位置不等于实现降落。

B. 冻结单机连续跟踪方案
4. 明确定义有序航段索引和段内进度；闭环用展开圈次，不用空间最近点跳圈。
   规定前瞻允许访问的相邻航段、拐角必经条件、可行转弯速度/减速距离、终点停止。
5. 逐一处理直角、180 度折返、很短航段、重复点/零长段、窄条带和多圈路径。
   中间点不默认停车；180 度折返可以物理减速至零，但不能瞬转或把实际位置投影回线。
   公式写明变量、单位、上限和约束冲突处理；不得通过放宽到达半径跳过拐角。

C. 冻结多机状态与事件契约
6. 给出每机状态转移表：等待阶段释放、等待个人延迟、执行、到达确认、驻留、完成、超时。
   每步所有飞机读取共同时间的状态后再同步积分；等待时仍受保持控制，不冻结状态数组。
7. 给出阶段屏障：以实际角色和参与条件判定，先到后离开怎样重置确认/驻留；
   进入下一阶段时沿用实际 p/v/a，不清零速度或加速度。
8. 明确 requested_release、actual_release、motion_start、arrival、confirmed、hold_complete、
   phase_end 各时刻含义、顺序、不变量和来源。非整步延迟、步内事件、同刻事件须有定位
   和稳定排序方案；不能将 release 直接当 motion_start。
9. 保持 10 Hz 半开观测网格与独立 support trajectory/终点状态；sim_time 与 wall_time 分开。

D. 版本、失败与测试规格
10. 列出最小新增配置字段、单位、默认值、拒绝条件；区分结构版本、实现版本、行为版本。
    给出旧 M1 产物读取兼容矩阵，不允许以新功能为由拒绝全部已迁移 M1 样本。
11. 回看修正后的 12 格负例方案：9 格仍为机制待设计，不能称已有可用负例。
    按正式验证条件提出改变实际飞行状态的可行机制，写清作用时段、证据与失败条件。
    降低速度不必然造成覆盖失败；timeout/null、质量不合格、引擎异常不算完整语义 false。
    不改成功标签、阈值或删除观测；如需新故障注入字段，只在设计中登记，待审阅。
12. 为至少以下边界分别写独立预期、计算方法、数值容差和失败反例：直角、折返、短段、
    重复点、窄条带、多圈/重访、非整步错峰、先到后离开、返航、最终驻留、超时。
    至少指定 h 与 h/2 的验收比较；预期不能调用未来同一跟踪函数生成。
    巡逻条件以 perimeter_revisit_v2 为准；飞法和圈次证据来自未来实际状态，不能复制配置。

E. 交付并停止
13. 仓库内交付 docs/fast_dynamics_m2/M2-03_design.md、M2-03_test_spec.md、M2-03_report.md
    和 verification/fast_dynamics_m2/M2-03_summary.json（小于 256 KiB）。
    静态提取、原始日志及输入清单写外部 M2-03/全新 attempt，不覆盖旧证据。
14. 列出预计修改文件、公共接口影响、可推导的正常/边界事件表和所有未决问题；
    不把设计中的字段/控制器写成已经存在。摘要区分静态检查与尚未运行的飞行验证。
15. 验证只使用开发输入、12 格哈希不变、留出索引和冻结清单哈希不变；
    状态 AWAITING_REVIEW，立即停止等 Codex 审阅，不自行进入 M2-04。
```

## 放行判断

审阅者应能按设计推导一条连续路线和一条非对称多机任务的事件序列，并据独立规格判断是否跳角、跳圈、错误释放或丢失驻留条件。存在上述未解决语义问题时，修设计，不提前堆控制代码。

新校准/盲测来源只有 TaskSpec 和静态规划输入，没有 SITL reference episode。M2-03 不负责补采；M3 前须单独解决采集和访问隔离，不能以这次输入冻结代替对照数据就绪。
