# v0.4 前置审查报告 - 第一批（基线 + A组）

**审查日期**: 2026-10-01  
**审查对象**: Multi-UAV SimpleGC v0.3.0  
**审查范围**: 基线信息 + A组（执行层是否在每个航点产生全机同步停靠）

---

## 0. 基线信息

### Git提交
- HEAD: `e13564b700934b481ad37cba053db9daabf9e4fa`
- 最新提交: `feat(viewer): 新增 PyQt 离线回放与任务计划预览`

### 版本与模块
- 版本号: `0.3.0`
- 模块数量: 23个
- 模块列表: `__init__.py`, `analysis.py`, `audit.py`, `capability.py`, `dataset.py`, `dataset_audit.py`, `episode_loader.py`, `evaluation.py`, `execution_constraints.py`, `generation.py`, `mission_evaluation.py`, `mission_planning.py`, `mission_schema.py`, `observations.py`, `processes.py`, `protocol.py`, `quality.py`, `recording.py`, `runner.py`, `scenario.py`, `tasks.py`, `truth.py`, `vehicle.py`

### 单元测试
- 总测试数: 150
- 执行时间: 7.145s
- 状态: **全部通过**

### 数据目录
- `verification/v03_pilot_final_20260930/dataset/episodes`: 10个episode
- `verification/v03_integration_20260930/dataset_final/episodes`: 5个episode
- `generated/recon_pilot_v03_20260930/missions`: 100个任务

---

## A1: 规划编译 - 一个航点是否等于一个执行阶段

### 状态
**否定**: 一个执行阶段不等于一个航点，而是一个航段（两个航点之间的飞行）。

### 证据

**源码**: `swarm_sim/mission_planning.py:130-136`
```python
routes[agent] = {"approach": [copy.deepcopy(scan[0])], "observe": scan,
                 "return": [{"east_m": vehicle["east_m"], "north_m": vehicle["north_m"]}]
                 if mission["return_required"] else []}
```

**源码**: `swarm_sim/mission_planning.py:50-84` `compile_execution_phases`函数
- 每个semantic阶段（approach/observe/return）的每个航点生成一个执行phase
- `length = max(len(routes[agent][semantic]) for agent in agents)` (行62)
- 遍历 `for index in range(length)` 生成phases (行63)

**实测数据**: 4个任务的编译结果

| 任务 | 飞机数 | 执行阶段总数 | approach | observe | return |
|------|--------|-------------|----------|---------|--------|
| recon_shared_3uav | 3 | 12 | 1 | 10 | 1 |
| recon_smoke_3uav | 3 | 8 | 1 | 6 | 1 |
| recon_smoke_2uav_north | 2 | 8 | 1 | 6 | 1 |
| recon_smoke_6uav | 6 | 8 | 1 | 6 | 1 |

**关键发现**: approach路线只有1个航点（`scan[0]`），与observe第一个航点完全相同（距离<1e-6m）。这导致**每个任务100%的飞机（所有测试任务均为全部飞机）存在零长度approach→observe航段**。

数据: `audit_v04/A1_results.json`

### 对v0.4的影响
**中度影响**。零长度航段在每个任务都存在，但实测数据显示这些航段的停靠时间很短（A4数据：平均0.62s）。如果v0.4引入新的意图类型，需要确认其规划逻辑是否也会产生类似的零长度航段。

---

## A2: 运行器 - 每个阶段的执行流程

### 状态
**证实**: 每个执行阶段确实经历独立的upload → execute → confirm流程。

### 证据

**源码**: `swarm_sim/runner.py:95-113`
```python
for phase in scenario["phases"]:
    # 1. 并行上传
    def upload_phase(client, vehicle):
        mission = mission_for(scenario, phase["name"], client.id)
        client.upload(mission, timeout=deadline - time.perf_counter())
    parallel(upload_phase)
    
    # 2. 并行执行AUTO
    def execute(client, vehicle):
        client.execute(epoch, mission_count, timeout, phase["name"])
    parallel(execute)
    
    # 3. 并行确认目标点
    def confirm(client, vehicle):
        requirement = target_confirmation(scenario, phase, client.id)
        client.confirm_target(phase["targets"][client.id], ...)
    parallel(confirm)
```

**流程图**:
```
每个phase:
  ├─ upload (LOITER模式, mission_clear_all + 上传单段航线)
  ├─ execute (AUTO模式, 等待MISSION_ITEM_REACHED最后一个航点)
  └─ confirm (保持AUTO, 几何位置验证dwell_s秒)
```

分析: `audit_v04/A2_A3_code_analysis.txt`

### 对v0.4的影响
**高度影响**。这种phase-by-phase架构是产生阶段间停靠的根本原因。每个phase结束后必须等待confirm完成才能开始下一个phase的upload，引入了不可避免的延迟。

---

## A3: 飞控交互 - 每个航段上传什么、模式如何切换

### 状态
**证实**: 每个phase独立上传，每次都执行mission_clear_all。

### 证据

**源码**: `swarm_sim/vehicle.py:217-255` `upload`函数
```python
def upload(self, mission, timeout=20):
    self.mode("BRAKE" if self.record_lifecycle else "LOITER")  # 行218
    self.send("mission_clear_all_send", ...)  # 行220
    self.send("mission_count_send", self.sysid, self.target_component, len(mission))  # 行225
    # ... 逐个发送mission_item
    self.send("mission_set_current", self.sysid, self.target_component, 1)  # 行254
```

**源码**: `swarm_sim/vehicle.py:257-274` `execute`函数
```python
def execute(self, epoch, mission_count, timeout, phase):
    # ...
    self.mode("AUTO")  # 行263
    # 等待 MISSION_ITEM_REACHED(seq=mission_count-1)
    self.event("phase_finished", self.id, phase=phase, ...)  # 行272
```

**模式切换序列**（每个phase）:
1. upload开始: **LOITER**
2. execute开始: **AUTO** (启动航点任务)
3. execute结束: 保持**AUTO** (共享任务) 或切回**LOITER**
4. confirm执行: 保持当前模式
5. 下一个phase重复上述流程

分析: `audit_v04/A2_A3_code_analysis.txt`

### 对v0.4的影响
**高度影响**。每个phase都执行`mission_clear_all`意味着：
1. 不支持累积航线
2. 每次都是全新上传
3. 模式切换频繁（每phase至少2次：LOITER→AUTO→LOITER）

---

## A4: 实测验证 - 用已有数据量化停靠

### 状态
**部分证实**: 存在零长度航段，但数量有限且停靠时间短。主要停靠在observe语义内的换线点。

### 证据

**数据来源**: 15个episode，共545个航段窗口

**航段分类统计**:

| 类别 | 数量 | 平均速度 | 平均时长 | 平均长度 |
|------|------|---------|---------|---------|
| 扫描线航段 (≥5m) | 262 | 1.569 m/s | 8.28 s | 13.81 m |
| 短航段/换线 (<5m) | 226 | 0.889 m/s | 3.20 s | 2.71 m |
| **零长度航段 (<0.1m)** | **57** | **N/A** | **0.62 s** | **0.00 m** |

**零长度航段详情**:
- 数量: 57个（占短航段的25.2%）
- 平均停靠时长: **0.62秒**
- 时长范围: [0.50, 0.76]秒
- 按语义分布: **100% observe语义**（57/57）
- 分布: 每个episode平均3.8个零长度航段

**注意**: A1发现的approach→observe零长度航段在此数据中**未体现**为独立航段。原因是A4分析基于相邻phase目标点距离，而approach的目标点与observe第一个目标点相同，因此被计算为零长度。但实际窗口数据中，这些是两个独立的phase窗口。

数据: `audit_v04/A4_segment_data.json`

### 对v0.4的影响
**中度影响**。零长度航段平均停靠0.62秒，累积影响有限：
- 15个episode × 平均3.8个零长度航段 × 0.62s = 约35秒总停靠时间
- 占任务执行时间比例：35s / (15 × 68.13s) ≈ 3.4%

但这仅是零长度航段。短航段(<5m)的平均速度仅0.889 m/s，远低于扫描线的1.569 m/s，说明换线过程存在明显减速。

---

## A5: 每个运行的时间构成

### 状态
**证实**: 任务执行占总时长约67.6%，启动和关闭各占约10%和22%。

### 证据

**数据来源**: 5个episode的events.jsonl分析

**时间构成**:

| 阶段 | 平均时长 | 占比 | 说明 |
|------|---------|------|------|
| 启动 (武装→第一阶段) | 9.75 s | 10.5% | 起飞爬升 |
| **任务执行** (第一→最后阶段) | **62.67 s** | **67.6%** | 包含所有phase |
| 关闭 (最后阶段→降落) | 20.30 s | 21.9% | 返航降落 |
| **总时长** | **92.72 s** | **100%** | 武装→降落 |

**各episode详情**:

| Episode | 启动 | 任务 | 关闭 | 总计 | 任务占比 |
|---------|------|------|------|------|---------|
| 20260930T153623Z | 9.75s | 55.93s | 20.56s | 86.24s | 64.8% |
| 20260930T153848Z | 9.60s | 71.61s | 20.38s | 101.59s | 70.5% |
| 20260930T154116Z | 9.79s | 63.59s | 20.05s | 93.43s | 68.1% |
| 20260930T155237Z | 9.85s | 53.06s | 20.17s | 83.08s | 63.9% |
| 20260930T155457Z | 9.76s | 69.16s | 20.36s | 99.27s | 69.7% |

数据: `audit_v04/A5_time_breakdown.json`

### 对v0.4的影响
**低度影响**。时间构成合理，任务执行时间占主导。启动和关闭时间相对固定（标准差<1s），不会因引入新意图类型而显著变化。

---

## A6: 改为"每机整段连续航线"的改动范围（只评估，不实现）

### 状态
**评估完成**: 需要重构4个核心模块，适配3个周边模块，工作量约7-11天。

### 证据

**影响的核心文件**:
1. `swarm_sim/mission_planning.py` - 重构compile_execution_phases
2. `swarm_sim/runner.py` - 删除phase循环，改为一次性上传
3. `swarm_sim/vehicle.py` - 调整execute和confirm逻辑
4. `swarm_sim/mission_evaluation.py` - 重构窗口构建（不再依赖phase_finished事件）

**影响的适配文件**:
5. `swarm_sim/tasks.py` - 调整target_confirmation
6. `swarm_sim/observations.py` - 适配新窗口构建逻辑
7. `swarm_sim/scenario.py` / `mission_schema.py` - schema变更

**工作量估计**:
- 规划与设计: 重新定义语义阶段与执行航线的映射
- 实现核心逻辑: 3-5天
- 适配周边模块: 2-3天
- 测试与验证: 2-3天
- **总计: 7-11天**

**风险**:
- 失去phase-by-phase的细粒度进度反馈
- 错误恢复变复杂（单段失败 vs 整段失败）
- 窗口构建从事件驱动改为轨迹分析，可能引入新边界判断问题
- 现有15个episode数据协议不兼容，需要重新生成

**优势**:
- 消除phase间停靠（当前57个零长度航段，平均0.62s/个）
- 减少模式切换次数（当前每phase一次LOITER→AUTO→LOITER）
- 更接近真实连续飞行场景

详细分析: `audit_v04/A6_refactor_scope.txt`

### 对v0.4的影响
**决策性影响**。如果v0.4决定引入巡逻(Patrol)等需要连续飞行的意图，建议**优先完成此重构**，避免在phase-by-phase架构上增加新意图后再重构的成本翻倍。

---

## A组总结

### 核心结论
1. **执行层确实在每个phase产生停靠**，但停靠时间较短（平均0.62s/个）
2. **停靠的根本原因**是phase-by-phase架构，每个phase独立upload → execute → confirm
3. **零长度航段主要在observe语义内**（换线点），approach→observe的零长度由规划编译产生但在窗口中未单独体现
4. **改为连续航线需要7-11天重构**，影响4个核心模块

### 对v0.4的建议
1. 如果v0.4只增加Patrol意图而保持当前架构：可接受3-4%的停靠时间损失
2. 如果v0.4要求真实连续飞行（如侦察+巡逻混合任务）：**强烈建议先完成连续航线重构**
3. 优先级判断依据：新意图是否包含"长距离持续跟踪"或"动态路径调整"等需要连续飞行的场景

---

## 附录：数据文件清单

所有原始数据位于 `audit_v04/`:
- `A1_results.json` - 编译分析结果
- `A2_A3_code_analysis.txt` - 代码分析文档
- `A4_segment_data.json` - 545个航段的详细数据
- `A5_time_breakdown.json` - 5个episode的时间构成
- `A6_refactor_scope.txt` - 重构范围评估

所有分析脚本:
- `A1_compile_analysis.py`
- `A4_actual_data.py`
- `A5_time_breakdown.py`
