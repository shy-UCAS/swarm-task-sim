# Multi-UAV SimpleGC

基于本机 ArduCopter SITL 的多无人机实验框架。当前版本 **0.2.0**，支持 1～6 架飞机独立启动、分阶段并行任务、驻留确认、自动降落，以及任务规划、SIM 真值、时间对齐诊断和按任务族导出数据集。

当前架构、能力、验证结果和下一步计划见 [第二轮迭代方案与验证说明.md](第二轮迭代方案与验证说明.md)。[改进方案与验证说明.md](改进方案与验证说明.md) 是 0.1 版记录；复制时保留的 `框架架构与仿真能力说明.md` 描述改造前版本。

## 0.2 任务数据生成

```powershell
# 三机点访问、矩形巡逻、理想几何覆盖扫描
conda run -n llm --no-capture-output python main.py run scenarios/task_point_visit_3uav.json
conda run -n llm --no-capture-output python main.py run scenarios/task_patrol_3uav.json
conda run -n llm --no-capture-output python main.py run scenarios/task_coverage_3uav.json

# TaskSpec -> 新场景文件；输出路径应不存在
conda run -n llm --no-capture-output python main.py plan tasks/patrol_3uav.json --output scenarios/my_patrol.json
```

任务运行结束会自动导出版本化分析：`observations.csv`、`truth.csv`、`clock_models.json`、`labels.json`、`quality.json` 等。`analyze <run目录>` 可重分析历史数据；`dataset <多个run目录> --output <新目录>` 按 `family_id` 整组划分并保留失败样本。标签、数据质量和飞行是否完整结束分别记录。任务模式的退出成功要求通过新版门槛，详见第二轮说明。

时钟处理是被动估计，参考仍为事件驱动 AUTO 航点。观测是已知身份的合作式飞控遥测，几何覆盖不代表真实相机或雷达探测。

## 环境

项目 `.conda-env` 指定 `llm`。当前验证环境为 Windows、Python 3.12.3、pymavlink 2.4.50。SITL EXE 和 DLL 已随工程提供；本次改造没有安装依赖。

## 快速开始

在本工程目录的 PowerShell 7 中执行：

```powershell
conda run -n llm --no-capture-output python main.py validate scenarios/demo_2uav.json
conda run -n llm --no-capture-output python main.py run scenarios/demo_2uav.json
```

无需先运行旧版 `ConsoleApp1.exe`，新入口会管理自己的 SITL 进程。`swarm.py` 是同等入口；默认端口从 19100 起，每架间隔 10。每次运行使用全新的目录和参数状态，结束后回收本次启动的进程。

```powershell
# 单机或六机验证
conda run -n llm --no-capture-output python main.py run scenarios/demo_1uav.json
conda run -n llm --no-capture-output python main.py run scenarios/demo_6uav.json

# 顺序重复实验，输出不会覆盖
conda run -n llm --no-capture-output python main.py batch scenarios/demo_2uav.json --repeat 2

# 只检查旧轨迹，不执行，不擅自将时间索引解释成秒
conda run -n llm --no-capture-output python main.py audit loadData/uav_trajectories_persistent_20260213_164652.json

# 单元与回归测试
conda run -n llm --no-capture-output python -m unittest discover -s tests -v
```

CLI 退出码：`run/batch` 的 0 表示通过门槛，1 表示执行、质量或任务验证未通过；输入/配置错误通常为 2。无 TaskSpec 的旧航点场景沿用基础门槛：完整结束、各机有效位置覆盖率至少 99%、未发现接近风险。有 TaskSpec 的任务还要求真值覆盖、时钟诊断、真值间距与任务语义检查通过。`analyze/dataset` 返回 0 仅表示分析/导出操作成功，样本是否合格需读取结果。

## 场景定义

参考 `scenarios/demo_2uav.json`。`origin` 包含公共经纬度与海拔基准，所有 `east_m/north_m/up_m` 使用该公共坐标系。所有飞机在相同地面海拔生成，起飞后才释放第一航段。

- `vehicles`：独立 ID、MAVLink sysid、初始东西/南北位置及朝向。
- `phases`：每阶段必须为每架飞机配置一个目标点；全部完成后进入下一阶段。
- `speed_m_s`：目标航行速度，第一版限制 0.5～15 m/s，不是到达时刻约束。
- `hold_s`：到达航点后的等待时长。
- `takeoff_alt_m`：准备阶段的起飞相对高度。
- `timeout_s`：从运行开始计时的整个场景超时，包含启动与降落。
- `max_gap_s`：过期遥测判断和离线插值的最大间隔。
- `min_separation_m`：初始点预检及飞行阶段离线距离检查阈值。

支持区域被限制在原点东/北各 ±2000 m；坐标换算使用局部 WGS84 线性近似，不用于跨区域精密测量。运行倍速固定为 1。旧轨迹文件不能直接作为新场景使用，需要确认时间单位、处理跳点并转换为本场景结构。

## 输出

每次运行在 `runs/<scenario_id>_<UTC时间>_<随机后缀>/` 下输出：

| 文件 | 内容 |
|---|---|
| `scenario.json` | 验证并补全默认值后的场景 |
| `metadata.json` | 执行状态、参数、版本、源码/固件摘要、端口、PID、阶段发送偏差、进程回收结果 |
| `events.jsonl` | 连接、准备、阶段释放、完成、降落和失败事件 |
| `raw/<agent>.jsonl` | 原始 MAVLink 消息、源时间字段和高精度本机接收时间 |
| `samples.csv` | 按共同主机时间采样的多机位置、速度、姿态、消息年龄和有效标记 |
| `processed.csv` | 飞行阶段统一采样的 ENU 位置/速度，长表格式和缺失掩码 |
| `quality.json` | 覆盖率、最近距离、接近风险、是否满足基础质量门槛 |
| `sitl/<agent>/` | 独立参数、日志和持久化状态 |

失败运行保留已有原始数据和错误信息。准备阶段失败时不生成 `processed.csv`；任务阶段全部完成、但后续降落失败时可以导出已完成的飞行窗口，`usable` 仍为 false。

## 兼容性与边界

`main.py` 已改为上述子命令入口。旧单机批量执行仍可通过 `python flyControl.py` 显式调用，保留旧 JSON 格式，但不具备新的多机保障和质量报告。

阶段同步不是物理仿真锁步；主机时间重采样不是飞控源时钟同步；独立实例不包含共享碰撞动力学、气流交互或在线避碰。不要把高层队形/意图标签直接视为已实现的闭环控制。
