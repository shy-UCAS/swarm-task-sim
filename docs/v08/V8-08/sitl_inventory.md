# V8-08 第 5 部分：旧软件在环数据只读盘点（摘要）

只查清"有什么、在哪里、什么格式"，**不下标定结论**。全部数字见同目录 [sitl_inventory.json](sitl_inventory.json)；脚本 `Multi-UAV SimpleGC/scripts/v08/v8_08_sitl_inventory.py`。速度为 v_meas（由位置差分得到），加速度同理。

## 1. 结论

- **可用的软件在环飞行：** `parallel_batch` 下有 929 个分析目录含 `truth.csv`，3 层内能找到 `firmware_parameters.json`，按指令规则记为"软件在环"。`fast_dynamics` 下按同一规则为 0 个。
- **格式：**
  - `truth.csv` 列为 `t_s, agent_id, valid, east_m, north_m, up_m`；
  - 采样间隔中位数 0.100 s（56/56 架机）；
  - 有效行比例 1.0（56/56）。
- **速度范围窄：** 抽样中水平 v_meas 中位数只有 1.91–2.97 m/s，p95 不超过 3.41 m/s。
  - 飞控 `WPNAV_SPEED` = 500 cm/s，`WPNAV_ACCEL` = 100 cm/s²。
  - 用这批数据标定 a_lat、a_lon，只能覆盖约 2–3.4 m/s，v0.8 需要的 4–10 m/s 没有数据。

## 2. 目录概况

| 根 | 实际位置 | 大小 | 文件数 | 一级子目录 |
|---|---|---|---|---|
| `SwarmData\parallel_batch` | `D:\T2L\SwarmData\parallel_batch` | 57.38 GB | 116 342 | 10 个批次；`v06_production900r2` 28.79 GB、`v06_production900` 18.16 GB，其余 ≤ 2.7 GB |
| `SwarmData\fast_dynamics` | `D:\T2L\SwarmData\fast_dynamics` | 43.64 GB | 120 626 | `m3` 42.78 GB，`m2` 0.49 GB，`performance` 0.23 GB，38 个 attempt 目录各约 42 个文件 |

`F:\…\SwarmData` 是指向 `D:\T2L\SwarmData` 的链接，两根合计 101.0 GB。遍历 141 s，无遍历错误。

**指定文件计数：**

| 文件 | parallel_batch | fast_dynamics |
|---|---|---|
| truth.csv | 1992 | 4010 |
| observations.csv | 1992 | 4010 |
| manifest.json | 1992 | 4049 |
| scenario.json | 929 | 50 |
| metadata.json | 929 | 3856 |
| firmware_parameters.json | 929 | 10 |
| *.parm | 2768 | 30 |
| *.BIN | 2768 | 0 |
| *.bin | 2768 | 5 |

parallel_batch 的 `*.bin` 全是 `eeprom.bin`。fast_dynamics 的 `*.bin` 是 git diff 证据文件，不是日志。

**路径格式（软件在环）：**
`<批次>\shards\shard_NN\attempts\aNNNNNN\run\attempts\<uuid>\<意图>_<编号>_v00_<时间戳>_<id>\`，其中：
- 运行目录含 `scenario.json`、`metadata.json`、`firmware_parameters.json`，以及 `sitl\uav_NN\{defaults.parm, eeprom.bin, logs\00000001.BIN}`；
- 分析结果在 `analysis_v050-dev_<时间戳>_<id>\`，含 `truth.csv`、`observations.csv`、`manifest.json` 等。

## 3. 来源分类与不确定项

| 根 | truth.csv | 软件在环 | 其他 |
|---|---|---|---|
| parallel_batch | 1992 | 929（全部凭 firmware_parameters.json） | 1063 |
| fast_dynamics | 4010 | 0 | 4010 |

不确定的情况：

1. **parallel_batch 的 1063 个"其他"不是 fastsim 输出。** 它们在 `<批次>\dataset\episodes\<时间戳>_<id>\truth.csv`，目录名与软件在环运行的时间戳和 id 相同，应是导出的数据集副本。按规则（3 层内没有固件参数）记为"其他"。数量多于 929，可能含重试或多次导出，未核对。
2. **fast_dynamics 的 `m3` 下有基线检出副本。** 例如 `m3\m3_r3_r1_revalidate03\baseline_checkout\…\runs\spike_v04_*`，含 10 个 firmware_parameters.json 和 50 个 scenario.json，但它们附近 3 层内没有 truth.csv，所以没有记为软件在环。是否另有对应的软件在环轨迹，未核对。
3. **跳过的 v0.7 目录。** fast_dynamics 下有 4 个 `v07_dataset` 目录，按"不读取任何 v0.7 数据"跳过，没有进入：
   - `m3\m3_r3_r1_revalidate04\SwarmData\`
   - `m3\m3_r3_r1_revalidate05\SwarmData\`
   - `m3\m3_r3_r3_attempt01\SwarmData\`
   - `m3\m3_r3_r3_attempt02\SwarmData\`

## 4. 抽样（20 个，步长 46，按路径排序）

批次分布：
- v061_T1：1 个；
- v061_T2：1 个；
- v061_T4：1 个；
- v06_pilot30b：1 个；
- v06_production900：7 个；
- v06_production900r2：9 个。

19 个有数据，共 56 架机，每次运行 2–4 架；时长 33.8–257.6 s。第 1 个样本（v061_T2）的 truth.csv 只有表头、0 行，其 manifest 的 `effective_start_sim_s` 为 null。

前 2 个样本的 `manifest.json`（在分析目录）和 `scenario.json`（在上一层运行目录）的键结构已写进 JSON。
- manifest 的字段包括：
  - `quality_policy`、`evaluation_context.{mission, platform, world, execution}`；
  - `time_epoch_host_s`、`observation_window.{time_base, effective_start_sim_s, time_mapping_available}`；
  - `execution.sim_speedup` 等。
- scenario 的字段包括：
  - `origin`、`vehicles[]`（east/north/heading/sysid）；
  - `phases[]`（name、semantic_phase、routes、speed_m_s、terminal_hold_s）；
  - `task_spec.execution`（含 speed_m_s、sim_speedup）、`family_id`、`flight_pattern`、`mission` 等。

  各阶段的 `speed_m_s` 可作为对应 v_cmd 的来源。

**运动统计预览：** 只用 valid = 1 的行，降采样到 ≥ 0.1 s，中心差分，只统计水平速度 > 1 m/s 的帧。下表每格是 56 架机各自统计量的最小–最大范围。

| 量 | p50 | p95 | p99 | 最大 |
|---|---|---|---|---|
| a_lat (m/s²) | 0.00–0.23 | 0.35–1.30 | 0.50–1.69 | 0.66–2.51 |
| \|a_lon\| (m/s²) | 0.19–0.42 | 0.84–1.59 | 1.15–2.73 | 1.44–5.92 |
| 水平 v_meas (m/s) | 1.91–2.97 | 2.10–3.41 | — | — |

转弯帧（a_lat / |v| > 0.05 rad/s）占运动帧的 32–71%。v_meas 中位数在转弯帧为 1.87–2.74 m/s，其余帧为 1.93–2.99 m/s。

## 5. 飞控参数

- **抽样回读值：** 前 2 个样本共 6 架机，每架回读 36 个符合前缀的参数，彼此**无不一致**。主要取值：
  - `WPNAV_SPEED` 500、`WPNAV_ACCEL` 100、`WPNAV_RADIUS` 200；
  - `WPNAV_SPEED_UP` 250、`WPNAV_SPEED_DN` 150、`WPNAV_ACCEL_Z` 100（单位 cm、cm/s、cm/s²）；
  - `ANGLE_MAX` 4500（0.01°）、`LOIT_ACC_MAX` 500、`LOIT_SPEED` 1250；
  - `PSC_VELXY_P` 2.0 / I 1.0 / D 0.5、`PSC_POSXY_P` 1.0；
  - `ATC_ACCEL_P/R_MAX` 110000。

  完整列表见 JSON 的 `params.from_samples`。
- **仓库副本：** 仓库 `ArducopterSITL/copter.parm` 中没有以这些前缀开头的行，这些参数取的是固件缺省值或运行目录里的 `defaults.parm`。各运行目录的 `defaults.parm` 未读。

## 6. V8-09 标定时可能遇到的问题

1. **速度覆盖。** 数据主要在 2–3.4 m/s，`WPNAV_SPEED` 只有 5 m/s，`WPNAV_ACCEL` 只有 1 m/s²。
   - 在这批数据里，a_lat、a_lon 反映的是 ArduCopter 航点导航在低速、低加速度设置下的行为，不能直接外推到 4–10 m/s。
   - |a_lon| 最大值达 5.9 m/s²，远高于 `WPNAV_ACCEL`，可能来自起飞、着陆、悬停转换或差分噪声。标定前需要先按任务阶段（`phase_windows.json`）裁掉这些段。
2. **时钟映射。**
   - manifest 同时有主机时间（`time_epoch_host_s`、`*_host_s`）和仿真时间（`effective_*_sim_s`）字段，还有 `time_mapping_available` 与 `sim_speedup`。本次没有核对 `truth.csv` 的 `t_s` 用的是哪个时基，冻结的 M3 标定代码会经 `clock_models.json` 变换时间。
   - 若 `t_s` 是主机时间且 sim_speedup ≠ 1，速度和加速度会被整体缩放，V8-09 须先确认。
3. **空数据与失败运行。** 至少有 1 个分析目录的 truth.csv 为空（T2 中途暂停的批次）。929 个目录还包括 r1/r2 重复批次和质量不合格的运行，需要先按 `run_status` 和质量结论过滤，并按 family 去重。
4. **数据集副本。** `dataset\episodes` 下的 1063 个 truth.csv 是副本，标定时不能与分析目录重复计数。
5. **有效行。** 抽样中有效行比例都是 1.0。但 manifest 的质量策略里有 `min_truth_valid_fraction`，未抽到的运行仍可能缺行。

## 7. 只读核对

- 遍历只用 `os.walk` 和 `os.stat`，抽样只打开文件读取。写出的文件只在 `docs/v08/V8-08/`；脚本在运行前检查输出目录不在任何根之下。
- 被读的 26 个文件（20 个 truth.csv，以及前 2 个样本的 manifest.json、scenario.json、firmware_parameters.json 各 2 个）读取前后对比如下：
  - 大小、修改时间、创建时间：**0 个变化**；
  - 最后访问时间（atime）：**26 个都变了**。本机 NTFS 的 `DisableLastAccess = 2`（系统管理，开启了访问时间更新），读文件就会由文件系统自动更新 atime。这不是写入，但严格说属于"时间戳变化"，在报告的执行方观察中单列。
