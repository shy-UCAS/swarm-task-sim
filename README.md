# SwarmTaskSim

基于 ArduCopter SITL 的任务驱动多无人机仿真与数据生成工程。

本仓库对应完整的 `Simulation` 工作目录，保留原始框架与多机改进版本。

| 目录 | 内容 |
|---|---|
| [Multi-UAV SimpleGC](Multi-UAV%20SimpleGC/) | 当前开发版本：多机执行、任务规划、真值导出、任务验证及数据集组织 |
| [SimpleGC](SimpleGC/) | 原始单机框架副本及其说明 |

## 使用入口

优先阅读 [多机框架 README](Multi-UAV%20SimpleGC/README.md) 与
[v0.2.2 补丁说明](Multi-UAV%20SimpleGC/v0.2.2补丁说明.md)。完整任务架构见
[第二轮迭代方案与验证说明](Multi-UAV%20SimpleGC/第二轮迭代方案与验证说明.md)。

在 Windows PowerShell 7 中进入多机工程，使用项目 `.conda-env` 指定的环境：

```powershell
Set-Location 'Multi-UAV SimpleGC'
conda run -n llm --no-capture-output python main.py validate scenarios/task_point_visit_3uav.json
conda run -n llm --no-capture-output python main.py run scenarios/task_point_visit_3uav.json
```

SITL 在本机运行。当前观测为已知身份的飞控遥测，覆盖扫描使用理想几何模型；
源时钟对齐采用被动估计，具体能力边界见工程说明。

## 保存范围

仓库包含源码、文档、任务与场景、随工程提供的 SITL 程序和说明视频，以及现有
`runs/` 和 `datasets/` 实验记录。运行失败与任务验证未通过的记录也保留。
Python 字节码缓存和测试临时文件不纳入版本管理。
