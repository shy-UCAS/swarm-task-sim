# v0.4 前置审查报告 — 第三批（B 组：样本协议与模型输入；D 组：多样性与近重复）

**审查日期**: 2026-10-01
**HEAD**: `e13564b700934b481ad37cba053db9daabf9e4fa`　**版本**: `0.3.0`
**范围**: B1–B5、D1–D3（合并为一批）

**数据源**
- B 组 episode 数据：`verification/v03_pilot_final_20260930/dataset`（10 个）+ `verification/v03_integration_20260930/dataset_final`（5 个）= 15 个 episode
- B4/B5/D 组任务数据：`generated/recon_pilot_v03_20260930/`（100 个已编译任务）

**原始数据表**：全部另存为 CSV，见各节的"数据表"行；汇总见第 4 节。

---

## B1 观测窗口覆盖范围

### 状态
**证实**（起止边界可确定；窗口**不含**起飞爬升与降落下降）。

### 证据

**边界依据**：`swarm_sim/analysis.py:65-73`（原样摘录）:

```python
    epoch = metadata.get("flight_epoch_monotonic_s", metadata["run_epoch_monotonic_s"])
    end = metadata.get("mission_end_monotonic_s", metadata["run_epoch_monotonic_s"] + metadata["elapsed_s"])
    output = directory / ("analysis_v" + __version__.replace(".", "") + "_" +
                          datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8])
    output.mkdir()
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    traces, truth_traces, clocks, truth_info, parameters, source_hashes = {}, {}, {}, {}, {}, {}
    count = max(0, math.floor((end - epoch) * scene["record_hz"]) + 1)
    grid = [i / scene["record_hz"] for i in range(count)]
```

两个时刻的来源：

- `flight_epoch_monotonic_s` = 第一个阶段（`leg_000`）的放行时刻，`swarm_sim/runner.py:98-101`：
  ```python
            release = time.perf_counter() + 0.3
            if "flight_epoch_monotonic_s" not in metadata:
                metadata["flight_epoch_monotonic_s"] = release
                write_json(directory / "metadata.json", metadata)
  ```
- `mission_end_monotonic_s` = 全部阶段结束后、`parallel(land)` 之前的时刻，`swarm_sim/runner.py:113-114`：
  ```python
        metadata["mission_end_monotonic_s"] = time.perf_counter()
        parallel(lambda client, vehicle: client.land())
  ```

**结论**：`observations.csv` 覆盖 `[flight_epoch, mission_end]`，即**从第一个执行阶段的放行时刻到最后一个阶段的确认事件之后**，**不含**起飞爬升（在此之前）与降落下降（在 `land()` 之后）。时间基为 host `time.perf_counter()`，`t_s = 0` 对应 `flight_epoch`。

**实测（15 个 episode）**

| 指标 | 中位数 | 范围 |
|------|--------|------|
| 首行 `t_s` − 首个阶段窗口 `start_s` | **0.0112 s** | [0.0058, 0.0249] |
| 最后阶段窗口 `end_s` − 末行 `t_s` | **−0.0604 s** | [−0.0924, −0.0007] |
| 观测跨度 / `metadata.elapsed_s` | **0.4582** | [0.3897, 0.6136] |
| 首行 `up_m` | **7.963 m** | [7.960, 7.970] |
| 末行 `up_m` | **8.014 m** | [8.010, 8.020] |

- 首行与首个阶段窗口起点相差 **0.006–0.025 s**：观测在阶段刚开始时即已记录。
- 末行的 `t_s` 比最后一个阶段窗口的 `end_s` **早 0.0007–0.0924 s**（负值即"窗口结束在网格末点之后"）。原因是网格被截断到 `floor((end − epoch) × record_hz)`，末点至多比 `mission_end` 早一个采样周期（0.1 s）。
- `up_m`：首行 7.960–7.970 m、末行 8.010–8.020 m，`takeoff_alt_m = 8.0`。**首末行都已处于巡航高度，不显示起飞爬升，也不显示降落下降。**

**数据表**：`audit_v04/B1_window_edges.csv`（15 行）

### 对 v0.4 的影响
- 观测序列只覆盖任务阶段，起止都不含起降过程；任何"整段飞行"的特征（如起飞/降落阶段的行为）在模型输入中不存在。
- 观测跨度仅占 `elapsed_s` 的 **45.82%**（中位），其余为主机侧的 SITL 启动、起飞准备与降落收尾。
- 末行与最后阶段窗口终点存在最多 0.09 s 的错位，方向固定为"网格早于窗口结束"。

---

## B2 时间网格

### 状态
**证实**：全部 episode 使用单一主机时间网格，每个 `t_s` 对所有 agent 都有行。

### 证据

**生成依据**：`swarm_sim/analysis.py:108-113`（原样摘录）:

```python
    stamps = sorted(times)
    x, mask = [], []
    for stamp in stamps:
        frame = [samples.get((stamp, agent), ([0.0] * 6, False)) for agent in expected]
        x.append([values[:] for values, _ in frame])
        mask.append([valid for _, valid in frame])
```

网格本身为 `grid = [i / scene["record_hz"] for i in range(count)]`（`analysis.py:73`），对全体 agent 共用；缺失的 `(t, agent)` 组合以 `mask=false` 补位（`episode_loader.py:111`）。

**实测（15 个 episode）**

| 指标 | 结果 |
|------|------|
| 每个 `t_s` 都有全部 agent 行的 episode | **15/15（覆盖率 1.0000）** |
| 相邻 `t_s` 步长集合 | **`{0.100}`**（唯一值，`record_hz = 10`） |
| 总行数 | 37,422 |
| `mask=false` 行数 | **132（0.3528%）** |
| 含 `mask=false` 的 episode | **1/15** |

唯一的例外是失败运行 `20260930T153556Z_bf2d3529`（`run_status=failed`，`scenario_id=recon_shared_demo_3uav_ready_timeout`）：该 run 的 132 行 `mask=false` 占其自身 354 行的 **37.288%**。**其余 14 个 episode 的 `mask=false` 行数为 0。**

**数据表**：`audit_v04/B2_time_grid.csv`（15 行）

### 对 v0.4 的影响
- 时间网格在全体 agent 上严格对齐，无逐机独立时间轴；因此"某机在某时刻无数据"必须以 mask 表达，而不能靠缺行表达。
- 合格 episode（14 个）中 mask 全为真，mask 通道在当前数据上不携带信息；只有失败运行会大量置假。

---

## B3 坐标与零填充

### 状态
**证实**（`load_episode` 不做归一化；零填充值 (0,0,0) **不**与合法位置混淆）。

### 证据

**不做归一化**：`swarm_sim/episode_loader.py:105-113`（原样摘录）:

```python
            samples[stamp, agent] = (values if valid else [0.0] * 6, valid)
            previous[agent] = stamp
            times.add(stamp)
    stamps = sorted(times)
    x, mask = [], []
    for stamp in stamps:
        frame = [samples.get((stamp, agent), ([0.0] * 6, False)) for agent in expected]
        x.append([values[:] for values, _ in frame])
        mask.append([valid for _, valid in frame])
```

归一化检查（脚本 `audit_v04/B_group.py`）：`load_episode` 返回的 `x` 中 `mask=true` 的坐标与 `observations.csv` 原值**逐位一致**；`metadata["normalized"] = False`。**无任何缩放、平移或标准化。**

**坐标取值范围（仅 `valid=1` 的行）**

| 分量 | 全局最小 | 全局最大 | 每 episode 跨度中位 |
|------|---------|---------|-------------------|
| `east_m` | −21.922 | 78.829 | 36.00 |
| `north_m` | −30.440 | 78.672 | 24.32 |
| `up_m` | −12.000（来自失败 run `bf2d3529`） | 8.020 | —— |
| `up_m`（14 个 completed episode 的中位区间） | **7.960** | **8.020** | —— |

**零填充混淆判定**

| 判据 | 结果 |
|------|------|
| `0` 落在该 episode 的 `east_m` 范围内 | **10/15** |
| `0` 落在该 episode 的 `north_m` 范围内 | **11/15** |
| `0` 落在该 episode 的 `up_m` 范围内 | **0/15** |
| **(0,0,0) 同时落在三维范围内** | **0/15** |

**结论**：由于 `up_m` 在飞行段恒为 7.96–8.02 m（`takeoff_alt_m = 8.0`），零填充值 (0,0,0) 在高度分量上与任何合法位置相差约 8 m，**不会与合法位置混淆**。水平分量单独看确实会落在范围内（east 10/15、north 11/15），但 `up_m` 分量足以区分。

**数据表**：`audit_v04/B3_coordinate_ranges.csv`（15 行）

### 对 v0.4 的影响
- 零填充在任何使用 `up_m` 的判据下可区分；但**只用水平坐标**（`east_m`/`north_m`）的下游处理会把零填充误当作区域内或区域附近的合法水平位置。
- `up_m = 0` 也恰好等于起飞前的地面高度语义，因此零填充与"地面"不能靠高度区分。
- `load_episode` 不归一化，模型输入的量纲与数值范围直接取自 FCU 遥测。

---

## B4 智能体顺序是否携带空间角色

### 状态
**证实**：agent ID 序、初始位置沿剖分轴排序、条带序三者**完全重合**。

### 证据

**加载器排序规则**：`swarm_sim/episode_loader.py:58-68`（原样摘录）:

```python
    expected = agent_ids if agent_ids is not None else manifest.get("agent_ids")
    if expected is None and (root / "task.json").is_file():
        task = json.loads((root / "task.json").read_text(encoding="utf-8"))
        if task:
            vehicles = task.get("scenario", task).get("vehicles", [])
            expected = [v["id"] for v in vehicles]
    if not isinstance(expected, (list, tuple)) or not expected or any(not isinstance(v, str) or not v for v in expected):
        raise ValueError("expected agent identities are required in manifest/task or agent_ids")
    if len(set(expected)) != len(expected):
        raise ValueError("duplicate expected agent identities")
    expected = sorted(expected)
```

即 **按 agent ID 字符串升序排序**，与物理坐标无关。

**规划器条带分配规则**：`swarm_sim/mission_planning.py:128`（原样摘录）:

```python
    ordering = sorted(scenario["vehicles"], key=lambda v: (v[f"{axis}_m"], v["id"]))
```

即先按剖分轴坐标、并列时按 ID 排序；`zip(ordering, partitions)` 使第 k 位拿到 `partitions[k]`。
另注 `mission_schema.py:120` 在归一化时已 `scenario["vehicles"] = sorted(vehicles, key=lambda v: v["id"])`。

**实测**

| 数据集 | 判据 | 一致率 |
|--------|------|--------|
| 100 个已生成任务 | k 号飞机（ID 序）== 第 k 条带 `strip_k` | **100/100 = 1.0000** |
| 100 个已生成任务 | k 号飞机（ID 序）== 初始位置沿剖分轴排序的第 k 位 | **100/100 = 1.0000** |
| 15 个实测 episode | k 号飞机（ID 序）== 第 k 条带 | **15/15 = 1.0000** |
| 15 个实测 episode | k 号飞机（ID 序）== 初始位置沿剖分轴排序的第 k 位 | **15/15 = 1.0000** |

成因：`generation._sample`（`generation.py:101-103`）把第 i 架飞机放在第 i 条带的中线上（`lane = (i + 0.5) * strip`），且 ID 为 `uav_{i+1:02d}` 升序，因此"ID 序 = 条带序 = 剖分轴坐标序"。

**数据表**：`audit_v04/B4_agent_order.csv`（100 行）、`audit_v04/B4_agent_order_episodes.csv`（15 行）

### 对 v0.4 的影响
- **agent 序号完全等价于空间角色**：第 1 个 agent 必然负责第 1 条带、必然位于剖分轴坐标最小处。模型只要按 agent 序号索引，即可在无需任何坐标的情况下推出该机的空间分工。
- 该等价在生成器（`generation._sample` 的中线布局）、schema（按 ID 排序）、规划器（按坐标排序）三处同时成立且互为因果；任一处的改动都会打破它。
- 加载器按 ID 排序，因此"第 k 个通道 = 第 k 条带"这一定义在数据集中是稳定的，不随 run 变化。

---

## B5 序列长度分布

### 状态
**证实**（T 由任务跨度决定，与飞机数的关系为间接）。

### 证据

**T 的生成依据**：`analysis.py:72-73` `count = max(0, math.floor((end - epoch) * scene["record_hz"]) + 1)`，即
**`T = floor(duration × record_hz) + 1`**，其中 `duration = mission_end − flight_epoch`（B1）。

**实测（15 个 episode）**

T 范围 **[118, 1188]**，中位 **632**。

| (飞机数, return_required, lanes) | n | T 中位 | T 范围 | T / (2·lanes + 1 + return) 中位 |
|----------------------------------|---|--------|--------|-------------------------------|
| (2, True, 3) | 1 | 481 | [481, 481] | 60.1 |
| (2, True, 4) | 2 | 692 | [657, 728] | 69.2 |
| (3, False, 4) | 1 | 536 | [536, 536] | 59.6 |
| (3, True, 4) | 2 | 668 | [632, 704] | 66.8 |
| (3, True, 5) | 3 | 1188 | [118, 1188] | 99.0 |
| (6, False, 4) | 3 | 543 | [501, 570] | 60.3 |
| (6, True, 3) | 1 | 488 | [488, 488] | 61.0 |
| (6, True, 4) | 2 | 665 | [646, 684] | 66.5 |

- **T 与飞机数无直接关系**：同为 6 机，T 可为 488 或 684；同为 3 机，T 可从 118（失败 run）到 1188。飞机数只通过扫描线长度影响路径长度，从而影响 T。
- **T 与阶段数正相关**：阶段数（`2·lanes + 1 + return`）越大，单位阶段占用的时间步越多（59.6 → 99.0），因为每个阶段引入固定的上传/放行/确认开销（A5：上传+放行 = 5.96%，确认驻留 = 15.89%）。
- 极值 118 来自失败 run `bf2d3529`（`ready_timeout`，从未起飞）；最大 1188 来自 `recon_shared_demo_3uav` 的 3 机 episode（`lanes = 5`，窗口 118.7 s，见 A4）。
- `T = floor(duration × 10) + 1` 在所有 episode 上成立（`record_hz = 10`）。

**数据表**：`audit_v04/B5_sequence_length.csv`（15 行）

### 对 v0.4 的影响
- 序列长度由**任务跨度**唯一决定，任何改变阶段数或单阶段耗时的因素（扫描线数、速度、上传/确认开销）都会线性地改变 T。若 v0.4 的意图使用不同的阶段结构，T 的分布会整体平移。
- `T` 只反映任务阶段（不含起降），且长度上限受 `timeout_s = 1200 s` 与 `max_airborne_time_s = 900 s` 约束。

---

## D1 拓扑签名分布

### 状态
**证实**，并发现 **`lanes` 在全部 100 个任务上恒为 4**，拓扑签名实际只有 12 种。

### 证据

**签名定义**：`(飞机数, partition_axis, lanes, return_required)`，其中 `lanes = ceil(条带横向宽度 / lane_spacing_m)`。
`lane_spacing_m = 4.0`（100/100 任务，见 report_A_supplement 3.5 节）；条带横向宽度取自 `planning.region_partitions[0]`，`partition_axis == "east"` 时取 `width_m`，否则取 `height_m`。

**lanes 核对**

| 判据 | 结果 |
|------|------|
| `ceil(条带宽 / 4.0)` == 实际 `observe` 阶段数 / 2 | **0/100 不一致**（即 100/100 一致） |
| `execution_phase_count == 1 + 2·lanes + return` | **0/100 不一致**（即 100/100 一致） |

**分布**

- **不同签名数：12**（n=100）。全部 12 种组合（3 种飞机数 × 2 种轴 × 2 种 return）**均出现**。
- 频数范围 6–13，最大占比 **13.0%**（`(6, 'north', 4, True)`）。

| 签名 (飞机数, 轴, lanes, return) | 频数 | 占比 |
|----------------------------------|------|------|
| (6, north, 4, True) | 13 | 13.0% |
| (2, east, 4, True) | 10 | 10.0% |
| (3, east, 4, True) | 9 | 9.0% |
| (3, north, 4, True) | 9 | 9.0% |
| (6, east, 4, True) | 9 | 9.0% |
| (6, north, 4, False) | 9 | 9.0% |
| (2, north, 4, False) | 8 | 8.0% |
| (3, east, 4, False) | 8 | 8.0% |
| (2, east, 4, False) | 7 | 7.0% |
| (2, north, 4, True) | 6 | 6.0% |
| (3, north, 4, False) | 6 | 6.0% |
| (6, east, 4, False) | 6 | 6.0% |

**轴等价版本**（把 east / north 视为同一拓扑，签名 = `(飞机数, lanes, return_required)`）

- **不同签名数：6**（= 3 种飞机数 × 2 种 return），全部出现。

| 轴等价签名 | 频数 | 占比 |
|-----------|------|------|
| (6, 4, True) | 22 | 22.0% |
| (3, 4, True) | 18 | 18.0% |
| (2, 4, True) | 16 | 16.0% |
| (2, 4, False) | 15 | 15.0% |
| (6, 4, False) | 15 | 15.0% |
| (3, 4, False) | 14 | 14.0% |

**进一步合并 `return_required`**：不同签名数降至 **3**（仅飞机数 2 / 3 / 6 之分）。

**`lanes` 恒为 4 的成因**：`generation._sample` 中 `strip = rng.uniform(*profile["strip_width_m"])`，而 profile 的 `strip_width_m = [12.0, 16.0]`（`generation_profiles/recon_pilot_v03.json`）。`ceil(strip / 4.0)` 在整个半开区间 `(12.0, 16.0]` 上恒等于 **4**；只有在 `strip` 恰为 `12.0` 时才是 3，而连续均匀分布取到端点的概率为 0。实测 `strip_width_m` 范围 **12.0116–15.9799**，全部落在 `(12, 16)` 内。

对比：手写的 `missions/*.json` 因 `strip` 恰为 12.0 而得到 `lanes = 3`（`recon_smoke_*`），`recon_shared_3uav` 的 `strip = 18.0` 得到 `lanes = 5`（见 report_A_supplement 1 节）。即 **`lanes` 只在手写任务上有变化，在采样生成的 100 个任务上完全不变**。

**数据表**：`audit_v04/D1_signatures.csv`（100 行）、`audit_v04/D1_signature_frequency.csv`（18 行）

### 对 v0.4 的影响
- 拓扑签名在 100 个任务上只有 **12 种**（轴等价后 6 种、再合并 return 后 3 种）；`lanes` 这一维度**零变异**。
- 单一签名的最大占比为 **13.0%**（轴等价后 22.0%）——即在当前 100 个任务中，任何一种拓扑都至少出现 6 次。
- `lanes` 的零变异源于 `strip_width_m` 的采样区间 `[12, 16]` 与 `lane_spacing_m = 4.0` 的整除边界重合；改变拓扑多样性必须改变其中至少一个。

---

## D2 跨 split 的签名重叠

### 状态
**证实**：**test 与 validation 中的拓扑签名 100% 在 train 中出现过**。

### 证据

`swarm_sim/dataset.py:15-17`（原样摘录）:

```python
def family_split(family_id, salt="simplegc-v02"):
    bucket = int(hashlib.sha256((salt + ":" + family_id).encode()).hexdigest()[:16], 16) % 100
    return "train" if bucket < 70 else ("validation" if bucket < 85 else "test")
```

**分 split 结果**（100 个 family，每个 family 1 个 episode）

| split | episode 数 | family 数 |
|-------|-----------|----------|
| train | 66 | 66 |
| validation | 11 | 11 |
| test | **23** | 23 |

**签名重叠**

| split | episode 数 | 拓扑签名在 train 出现过 | 轴等价签名在 train 出现过 |
|-------|-----------|----------------------|------------------------|
| **test** | 23 | **23/23 = 1.0000** | **23/23 = 1.0000** |
| validation | 11 | **11/11 = 1.0000** | **11/11 = 1.0000** |

- train 的签名集合 = **全部 12 种**（`(2,3,6) × (east,north) × (True,False)`），即 train 已覆盖整个签名空间。
- test 的签名集合 = 11 种，validation = 7 种，均为 train 的子集。
- test 中未在 train 出现的签名数：**0**。

**数据表**：`audit_v04/D2_split_signature_overlap.csv`（100 行）

### 对 v0.4 的影响
- 按拓扑签名衡量，test 集**没有引入任何新拓扑**：23 个 test episode 的签名全部可在 train 中找到同类。
- 由于 `lanes` 恒定（D1），签名空间的全部变异仅来自飞机数、剖分轴与 `return_required` 三个离散量，而这三者都是保序简单变量，train 覆盖全部组合是必然结果。
- 该结论对"签名"这一粒度成立；签名内部的连续参数差异（条带宽、扫描长、区域位置、速度）见 D3。

---

## D3 连续参数抖动幅度

### 状态
**证实**（连续参数在窄区间内抖动；同一签名内的相对标准差约 5%–20%）。

### 证据

**采样分布的实际取值（100 个任务）**

| 参数 | 最小值 | 最大值 | 极差 | 相对标准差 |
|------|--------|--------|------|-----------|
| 条带宽度 `strip_width_m` | 12.0116 | 15.9799 | 3.9683 | **0.08616** |
| 扫描长度 `sweep_length_m` | 8.0387 | 11.9551 | 3.9164 | **0.11618** |
| 进入距离 `entry_distance_m` | 10.0002 | 13.9917 | 3.9915 | **0.09980** |
| 区域位置 `region_east_m` | −19.9815 | −0.0019 | 19.9796 | 不可用（见下） |
| 区域位置 `region_north_m` | −19.9805 | −0.0026 | 19.9779 | 不可用（见下） |
| 速度 `speed_m_s` | 2.0000 | 3.0000 | 1.0000 | **0.16554** |

- 四个正参数的实测范围与其 profile 声明区间完全吻合：`strip_width_m [12,16]`、`sweep_length_m [8,12]`、`entry_distance_m [10,14]`、`speeds_m_s {2.0, 2.5, 3.0}`。
- `region_east_m` / `region_north_m` 的均值为负（约 −10），`sd/mean` 作为相对标准差无意义，故不报告；**改用极差**：两者极差均约 **19.98 m**，声明区间为 `[-20, 0]`，实测未触及端点。
- 速度只有 3 个离散取值（2.0 / 2.5 / 3.0），且 `variant_speed_factors = [1.0]`，因此不存在连续抖动，只有三档切换。

**同一拓扑签名内的相对标准差**（列出样本数 ≥ 5 的 12 个签名）

| 签名 | n | 条带宽 RSD | 扫描长 RSD | 进入距 RSD | 速度 RSD |
|------|---|-----------|-----------|-----------|---------|
| (6, north, 4, True) | 13 | 0.07545 | 0.11545 | 0.09781 | 0.13977 |
| (2, east, 4, True) | 10 | 0.07152 | 0.08331 | 0.09226 | 0.16952 |
| (3, east, 4, True) | 9 | 0.08467 | 0.08181 | 0.10851 | 0.15076 |
| (3, north, 4, True) | 9 | 0.07412 | 0.09418 | 0.07078 | 0.14420 |
| (6, east, 4, True) | 9 | 0.08460 | 0.09475 | 0.08415 | 0.20203 |
| (6, north, 4, False) | 9 | 0.08601 | 0.10761 | 0.10468 | 0.12036 |
| (2, north, 4, False) | 8 | 0.09740 | 0.14250 | 0.11837 | 0.15793 |
| (3, east, 4, False) | 8 | 0.08951 | 0.11730 | 0.04715 | 0.12948 |
| (2, east, 4, False) | 7 | 0.10689 | 0.11652 | 0.09776 | 0.16197 |
| (2, north, 4, True) | 6 | 0.09620 | 0.12205 | 0.08927 | 0.09091 |
| (3, north, 4, False) | 6 | 0.05261 | 0.10234 | 0.06701 | 0.20203 |
| (6, east, 4, False) | 6 | 0.08955 | 0.10682 | 0.11679 | 0.18570 |

- 条带宽 RSD 落在 **0.053–0.107**，扫描长 **0.082–0.143**，进入距离 **0.047–0.118**，速度 **0.091–0.202**。
- 各签名内的速度取值均为 2–3 档混合（例如 `(6, north, 4, True)` 为 {2.0:7, 2.5:5, 3.0:1}；`(2, east, 4, True)` 为 {2.0:4, 2.5:3, 3.0:3}），**没有出现单一签名内速度恒定的情形**。
- `entry_side` 分布：`low` 51 / `high` 49（近均匀，但该字段**不进入** D1 的拓扑签名）。

**数据表**：`audit_v04/D3_parameter_spread.csv`（6 行）、`audit_v04/D3_within_signature_rsd.csv`（12 行）

### 对 v0.4 的影响
- 连续参数的抖动幅度约为其均值的 **5%–20%**，分布在窄区间内；同一拓扑签名内部仍有这一量级的差异，故签名相同不等于样本相同。
- `entry_side`（来自区域哪一侧进入）在 100 个任务上近似均分，但它**不在拓扑签名中**，因此 D2 的"签名重叠"结论不覆盖这一维度。
- 速度只有 3 个离散档位，是连续参数中离散化最强的一项。

---

## 本批自检

| 编号 | 是否有对应小节 | 状态 |
|------|--------------|------|
| B1 | 有 | 完成（边界事件定位 + 15 个 episode 的首末差分布 + `up_m` 起降判定） |
| B2 | 有 | 完成（网格完整性、步长、mask 比例，失败 run 单独列出） |
| B3 | 有 | 完成（坐标范围、归一化核对、零填充三维混淆判定） |
| B4 | 有 | 完成（ID 序 vs 条带序、ID 序 vs 剖分轴坐标序，两处一致率均为 100%） |
| B5 | 有 | 完成（T 分布 + 按 (飞机数, return, lanes) 分组） |
| D1 | 有 | 完成（签名分布 + `lanes` 与已编译阶段的核对，发现 lanes 恒为 4） |
| D2 | 有 | 完成（分 split + test/validation 的签名重叠率） |
| D3 | 有 | 完成（采样范围 + 签名内 RSD） |

**本批未完成项**：无。

**新增脚本**

| 文件 | 用途 |
|------|------|
| `audit_v04/B_group.py` | B1–B5 全部分析，输出 5 个 CSV |
| `audit_v04/D_group.py` | D1–D3 全部分析，输出 5 个 CSV |

**新增 CSV 数据表**（原始数据表，均位于 `audit_v04/`）

| 文件 | 行数 | 内容 |
|------|------|------|
| `B1_window_edges.csv` | 15 | 每 episode 的观测首末行 `t_s`/`up_m`、阶段窗口起止、首末差、`elapsed_s` 比值 |
| `B2_time_grid.csv` | 15 | 每 episode 的 agent 数、不同 `t_s` 数、全覆盖 `t_s` 数、mask=false 行数与占比、步长集合 |
| `B3_coordinate_ranges.csv` | 15 | 每 episode 的 `east/north/up` 有效值范围与零填充落入判定 |
| `B4_agent_order.csv` | 100 | 每任务的 ID 序条带分配、坐标序、两项一致性标记 |
| `B4_agent_order_episodes.csv` | 15 | 每 episode 的上述两项一致性标记 |
| `B5_sequence_length.csv` | 15 | 每 episode 的 T、飞机数、`return_required`、lanes、阶段数、速度、`duration_s` |
| `D1_signatures.csv` | 100 | 每任务的签名、由 observe 阶段数反推的 lanes、核对标记 |
| `D1_signature_frequency.csv` | 18 | 12 个签名 + 6 个轴等价签名的频数与占比 |
| `D2_split_signature_overlap.csv` | 100 | 每任务的 family、split、签名、是否在 train 出现过 |
| `D3_parameter_spread.csv` | 6 | 6 个连续参数的最小/最大/极差/相对标准差 |
| `D3_within_signature_rsd.csv` | 12 | 12 个签名内的 6 个参数相对标准差 |
