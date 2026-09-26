# Multi-UAV SimpleGC 独立源码审查任务计划

## 一、审查目标

请不要把现有《改进方案与验证说明》《第二轮迭代方案与验证说明》视为事实，只把它们当作“Codex 声称已经实现的功能清单”。

你的任务是：

> 基于实际源代码、配置、测试代码和可执行实验，独立判断 Multi-UAV SimpleGC 是否已经达到“可用于无人机集群轨迹 benchmark 数据生成”的最低工程要求。

最终每一项必须给出：

**PASS / PARTIAL / FAIL / UNVERIFIABLE**

并提供可复核证据：

```text
源码文件
类/函数
关键实现位置
对应测试
实际运行结果
存在的问题
建议修改
```

如果“文档说实现了，但源码没有”，必须明确标记 `FAIL`。

如果“源码有，但没有测试或实际无法证明”，标记 `PARTIAL` 或 `UNVERIFIABLE`。

禁止仅依据 README、说明文档、代码注释得出“已实现”的结论。

---

## 二、总体目标架构

需要验证源码是否真正形成：

```text
TaskSpec / ScenarioSpec
        ↓
任务规划与静态预检
        ↓
多 UAV 参考航迹
        ↓
多个独立 ArduCopter SITL
        ↓
多机并行控制
        ↓
统一时间基准记录
        ↓
FCU Observation + Simulation Truth
        ↓
任务执行验证
        ↓
Quality Control
        ↓
Dataset Builder
```

第二轮说明声称当前已经形成“任务定义 → 几何规划与预检 → SITL执行 → 真值与观测导出 → 几何任务验证 → 按任务族组织数据集”的流程，因此需要重点验证这条链路是否真的由代码连通，而不是各模块孤立存在。

---

## 三、核心审查清单

| ID | 审查内容 | 必须验证的问题 | 最低验收标准 |
|---|---|---|---|
| A1 | 多SITL实例 | 是否真正一架UAV对应一个独立SITL进程，而非单实例串行模拟？ | N架机有N个独立进程、端口、SYSID、状态目录 |
| A2 | 实例隔离 | EEPROM、参数、日志、端口是否可能互相污染？ | 每次运行独立目录；无状态复用 |
| A3 | 进程生命周期 | 是否只回收本次启动的SITL？异常时是否残留？ | 正常/异常均无孤儿进程 |
| B1 | MAVLink连接 | 是否每机拥有独立连接？ | agent ↔ connection ↔ SITL一一对应 |
| B2 | 消息竞争 | 控制器和记录器是否同时直接recv导致抢消息？ | 一个连接只有一个实际接收者 |
| B3 | ACK处理 | COMMAND_ACK、MISSION_ACK是否真正检查结果？ | 拒绝/超时/重传均有处理 |
| C1 | 并行控制 | 多架机是真的并发执行还是循环顺序调用？ | 控制任务并发，非串行阻塞 |
| C2 | Ready Barrier | 是否所有飞机READY后才开始任务？ | 任一飞机未准备成功则不能静默启动全群 |
| C3 | Phase Barrier | 阶段间同步是否真实存在？ | 所有参与机完成当前阶段才能推进 |
| C4 | 同步语义 | 文档是否错误宣称“物理同步”？ | 必须区分命令释放同步和实际动作同步 |
| D1 | 速度控制 | desired speed是否真正下发飞控？ | MAV_CMD_DO_CHANGE_SPEED等实际执行 |
| D2 | 驻留控制 | hold_s是否真的造成驻留？ | 不能只存在JSON字段 |
| D3 | 驻留验证 | 飞控说航点完成是否直接等于任务驻留成功？ | 必须有独立几何/时间验证 |
| E1 | 初始状态 | 每个场景是否重新初始化？ | 不继承前一次飞行状态 |
| E2 | 初始位置 | 多架机位置与heading是否正确设置？ | 与ScenarioSpec一致 |
| E3 | 可重复运行 | 相同任务多次运行是否保持相同初始配置？ | 参数、地图、初始位置一致 |
| F1 | 公共时基 | 所有无人机记录是否使用同一主机单调时钟？ | 可映射到统一t轴 |
| F2 | FCU时间 | 是否保留time_boot_ms等源时间？ | 原始时间字段不丢失 |
| F3 | 时钟映射 | 文档声称的FCU→host映射是否真实实现？ | 能检查拟合残差、缺口、回退 |
| F4 | 时钟退化 | 源时钟不可用时是否伪装成正常对齐？ | 必须明确标记fallback |
| G1 | 原始数据 | raw MAVLink是否完整保存？ | 可追溯原始消息 |
| G2 | Observation | processed observation是否来自FCU状态？ | 不能误把reference当观测 |
| G3 | Simulation Truth | truth是否来自独立SIM状态，而非FCU估计复制？ | 真值和估计来源明确分开 |
| G4 | Reference | 是否单独保存规划参考？ | reference / observation / truth三者不可混淆 |
| G5 | 坐标系 | NED→ENU转换是否数学正确？ | 位置、速度符号和轴一致 |
| H1 | 重采样 | 多机是否重采样到统一时间网格？ | 输出可还原T×N×F |
| H2 | 长缺口处理 | 大时间缺口是否仍强行插值？ | 超过阈值不得插值 |
| H3 | 外推 | 是否在数据范围之外外推？ | 默认禁止 |
| H4 | Valid Mask | 缺失数据是否显式标记？ | 有valid/mask |
| I1 | 安全距离 | 是否检查UAV-UAV最小距离？ | 不只检查采样点 |
| I2 | 采样间交叉 | 两机在相邻采样间交叉是否能发现？ | 有连续/分段线性近似检查 |
| I3 | 风险语义 | 是否把“没有发现风险”错误等价为“证明无碰撞”？ | 文档/代码不得过度声明 |
| J1 | 超时机制 | 全局、命令、航点、连接是否有超时？ | 不得无限阻塞 |
| J2 | 断连 | TCP EOF等异常是否会busy loop？ | 明确退出/失败 |
| J3 | 数据持久化 | 异常时是否全部数据丢失？ | 至少增量保存 |
| J4 | 清理 | 失败后端口、进程、临时目录状态是否正常？ | 下一任务可继续执行 |
| K1 | TaskSpec | 是否存在真正独立于轨迹的结构化任务定义？ | task不等于航点文件 |
| K2 | 任务编译 | TaskSpec是否真正转换为Scenario/航点？ | 非手工重复维护两份内容 |
| K3 | 未知字段 | 不支持的约束是否会被静默忽略？ | 应拒绝或明确告警 |
| K4 | task/scene一致性 | 编译后手改航点是否仍被当成原Task？ | 应检测不一致 |
| L1 | point_visit | 是否依据真实执行轨迹判断成功？ | 进入容差＋满足驻留 |
| L2 | patrol | 是否判断顺序、圈数、驻留？ | 不能只看是否经过点 |
| L3 | coverage | 是否依据实际轨迹计算覆盖？ | 不是reference覆盖率 |
| L4 | unknown | 缺证据时是否允许unknown/null？ | 不强行归成功/失败 |
| M1 | assigned_intent | 是否保留原始任务意图？ | 执行失败不能改写assigned intent |
| M2 | observed_behavior | 是否与assigned intent区分？ | 不能字段同义复制 |
| M3 | mission_success | 是否由Validator判断？ | 不是“程序执行完=true” |
| M4 | provenance | 标签来源是否可追踪？ | 能区分人为、规则、实际验证 |
| N1 | Quality Gate | benchmark_eligible是否真正综合多个门槛？ | 非单一“程序没报错” |
| N2 | 真值有效率 | 是否检查truth coverage？ | 应独立于observation |
| N3 | 时间质量 | 时钟质量是否参与eligibility？ | 超阈值不得进入合格集 |
| N4 | 任务成功 | 几何任务失败是否仍可能进入合格集？ | 默认不能 |
| O1 | family_id | 同源派生数据是否共享family_id？ | repeat/noise/text/window必须继承 |
| O2 | split | train/val/test是否按family划分？ | 禁止按窗口随机切 |
| O3 | 派生泄漏 | 滑窗后是否可能跨集合？ | 必须先split再window |
| O4 | retry泄漏 | 失败重试是否生成新family？ | 不应生成 |
| P1 | Manifest | 是否记录源码/原始数据/产物hash？ | 修改后能检测 |
| P2 | 数据污染 | task/label/truth是否可能被意外喂给模型？ | loader默认只读允许的observation字段 |
| P3 | Failed Samples | 失败数据是否被删除？ | 应保留并明确标识 |
| Q1 | 批处理 | 是否支持多个任务连续运行？ | 单个失败不能污染下一任务 |
| Q2 | 断点续跑 | 当前若未实现，要明确标记缺失 | 不允许文档声称已实现 |
| Q3 | Retry | 重试是否有独立attempt记录？ | 不覆盖原失败 |
| R1 | 规模稳定性 | 1、2、3、6机是否实际运行？ | 至少复现代表性多机实验 |
| R2 | 资源占用 | N增加时CPU/内存是否失控？ | 给实测而非估计 |
| R3 | 连续稳定性 | 单次成功是否被误称稳定？ | 至少连续多轮测试 |
| S1 | 测试有效性 | 单元测试是否真正测试行为而不是mock掉核心功能？ | 区分mock测试/SITL集成测试 |
| S2 | 回归测试 | 修复是否有对应regression test？ | 关键历史bug应有测试 |
| S3 | 测试独立性 | 测试是否读取历史成功数据伪装实时运行？ | 明确区分 |

---

## 四、必须重点做的真实性检查

### 1. Multi-SITL 是否真的同时运行

实际启动一个3机或6机场景。

检查：

```text
进程数量
PID
TCP端口
SYSID
启动时间
任务释放时间
状态记录时间
```

必须证明不是：

```text
UAV1执行
↓
UAV2执行
↓
UAV3执行
```

而是真实并行。

### 2. 人为制造一架飞机失败

例如：

- 错误端口；
- 不启动其中一个SITL；
- 航点不可达；
- 故意超时；
- 中途杀死一个SITL。

检查：

```text
其他飞机如何处理？
全局状态如何记录？
是否正确cleanup？
失败数据是否保留？
benchmark_eligible是否false？
```

### 3. 人为制造驻留语义错误

设置：

```text
hold要求2秒
```

然后制造实际不足2秒的情况。

检查是否会出现：

```text
AUTO mission finished
mission_success = true
```

如果出现，则语义验证仍有漏洞。

### 4. 人为修改编译后的Scenario

流程：

```text
TaskSpec
→ plan
→ scenario.json
→ 手工改变某个航点
→ run
```

必须验证系统是否拒绝：

```text
TaskSpec与实际执行轨迹不一致
```

### 5. 测试数据泄漏保护

人为构造：

```text
family_A / run_1
family_A / retry
family_A / noise_variant
family_A / language_variant
family_B
```

检查所有A是否进入同一个split。

然后模拟滑窗：

```text
scene A
→ window_1
→ window_2
...
```

确认窗口没有重新随机split。

---

## 五、任务层需要额外审查的几个设计问题

目前仅实现：

```text
point_visit
rectangle_patrol
coverage_scan
```

请检查它们是否真正适合作为未来高级意图的 Task Primitive。

重点回答：

```text
coverage_scan 是否可以组合成 reconnaissance？
rectangle_patrol 是否可以作为 patrol primitive？
point_visit 是否可以用于 approach/regroup/return？
```

以及当前代码是否支持：

```text
一个高级任务由多个primitive串联
```

如果完全不支持，不属于当前版本bug，但请明确列为下一阶段架构缺口。

---

## 六、当前暂时不要求实现的能力

以下内容不要因为“没实现”就判当前整改失败：

```text
ROS
Gazebo
相机
LiDAR
雷达
真实外部跟踪
通信网络仿真
气流耦合
MARL
完整在线避碰
复杂编队控制
24/50/100机大规模运行
LLM文本生成
高级战术意图识别
```

当前版本的最低目标是：

> **可靠地产生多架无人机在任务驱动下的同步状态轨迹，并保留足够的真值、时间、任务和质量证据。**

---

## 七、必须视为关键缺陷的情况

如果存在以下任意情况，建议直接列为 P0：

```text
多个agent实际共享同一个SITL
多机实际上串行运行
多个线程同时recv同一个MAVLink socket
不同实验继承前一次SITL状态
无统一时间依据
reference被当成actual trajectory
FCU estimate被伪称simulation ground truth
失败任务仍benchmark_eligible=true
任务标签只由文件名决定，没有轨迹验证
family派生样本可以跨train/test
异常时产生孤儿SITL进程
程序可能无限等待而无timeout
```

这些问题会直接影响后续 benchmark 的可信度。

---

## 八、重点检查“看起来实现了，实际上没用”的代码

请专门检查：

```text
定义了函数但是没有被调用
CLI参数存在但没有传到执行层
Task字段被解析但没有影响飞控
desired_speed只保存没有发送
hold_s只写metadata没有执行
family_id保存但dataset split根本没使用
truth.py存在但Dataset Builder读取的仍然是FCU数据
quality.json有字段但benchmark_eligible不引用
Validator存在但run/dataset流程没有调用
异常handler存在但except过宽后直接忽略
```

这是AI自动改代码时最需要警惕的一类问题。

---

## 九、建议进行完整数据流追踪

任选一个 `coverage_scan` 样本，从头追踪：

```text
tasks/*.json
        ↓
TaskSpec parser
        ↓
task planner
        ↓
ScenarioSpec
        ↓
runner
        ↓
vehicle
        ↓
MAVLink command
        ↓
SITL
        ↓
raw MAVLink
        ↓
observation
        ↓
SIM truth
        ↓
time alignment
        ↓
coverage validator
        ↓
labels
        ↓
quality
        ↓
dataset export
```

对每一步回答：

```text
输入是什么？
输出是什么？
谁调用它？
是否真的参与最终结果？
失败会怎样？
有何测试覆盖？
```

如果某一步只存在“概念上应该有”，但实际调用链断裂，标记 `FAIL` 或 `PARTIAL`。

---

## 十、代码质量额外检查

检查：

```text
是否大量逻辑仍集中在runner/vehicle中
模块是否职责清晰
是否存在全局共享可变状态
线程安全是否有风险
是否大量bare except
是否存在无界队列
是否存在线程无法join
是否可能文件句柄泄漏
是否可能socket未关闭
是否可能端口重复占用
是否存在race condition
是否使用sleep硬编码代替状态确认
```

尤其关注：

> 多线程消息接收 + 多SITL进程 + 数据记录线程之间是否存在竞态。

---

## 十一、最终报告格式

最终报告必须包含以下结构：

```text
# Multi-UAV SimpleGC 独立源码审查报告

## 1. 总体结论

工程完成度：
- 多机执行底座：
- 数据记录：
- 时间同步：
- 真值系统：
- 任务系统：
- 语义验证：
- 数据集系统：

是否达到：
“用于第一版多无人机轨迹benchmark生成”

结论：
PASS / PASS WITH CONDITIONS / NOT READY

## 2. 文档声明与源码真实性对照

| 声明 | 源码证据 | 运行证据 | 结论 |
|------|---------|---------|------|

## 3. P0问题
会导致数据错误、标签错误、数据泄漏或不可复现的问题。

## 4. P1问题
需要在正式批量生成benchmark前解决的问题。

## 5. P2问题
可以后续增强的问题。

## 6. 未发现问题但缺乏充分验证的能力

## 7. 自动化测试覆盖情况

## 8. 实际SITL运行结果

## 9. 数据流追踪
TaskSpec → Dataset完整追踪。

## 10. 数据泄漏风险

## 11. 最终整改清单
按优先级列出：
问题
位置
原因
修改建议
验收测试
```

---

## 十二、最终必须明确回答的5个问题

无论审查结果如何，最终必须明确回答：

1. **当前系统生成的 `observations.csv` 是否可以被可信地视为多无人机意图识别模型的轨迹输入？**

2. **不同无人机的时间轴是否已经足够用于研究集群相互关系，还是仍存在会实质影响关系建模的同步问题？**

3. **当前 `truth.csv` 是否真的是独立于 FCU 估计的仿真真值？**

4. **当前任务标签和 `mission_success` 是否真正由实际执行轨迹验证，而不是由配置文件或航点完成事件直接决定？**

5. **当前 Dataset Builder 是否已经能够保证同源场景、重复实验、未来噪声版本和滑动窗口不会跨 train/val/test 泄漏？**

如果这5项都能从源码和实际实验得到肯定答案，则可以认为当前框架已经具备：

> **“任务驱动的轻量级多无人机轨迹 benchmark 生成底座”**

的核心资格。

至于“侦察、巡逻、突防、佯动、撤离”等高级意图生成，应作为下一层任务语义系统开发，不应混入这次底层整改审查。
