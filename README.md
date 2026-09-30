# SwarmTaskSim

基于 ArduCopter SITL 的任务驱动多无人机仿真与数据生成工程。

本仓库对应完整的 `Simulation` 工作目录，保留原始框架与多机改进版本。

| 目录 | 内容 |
|---|---|
| [Multi-UAV SimpleGC](Multi-UAV%20SimpleGC/) | 0.3.0：共享区域分工、多机执行、独立真值验证和可加载数据集 |
| [SimpleGC](SimpleGC/) | 原始单机框架副本及其说明 |

## 使用入口

优先阅读 [多机框架 README](Multi-UAV%20SimpleGC/README.md)、
[TaskSpec v2 接口说明](Multi-UAV%20SimpleGC/docs/task_spec_v2.md) 与
[v0.3 实现及验证记录](Multi-UAV%20SimpleGC/docs/v0.3_implementation_and_verification.md)。
当前源码版本为 0.3.0，具体实跑、失败及未完成范围以验证记录为准。
旧任务和质量处理仍可参考 [v0.2.2 补丁说明](Multi-UAV%20SimpleGC/v0.2.2补丁说明.md) 与
[第二轮迭代方案与验证说明](Multi-UAV%20SimpleGC/第二轮迭代方案与验证说明.md)。

在 Windows PowerShell 7 中进入多机工程，使用项目 `.conda-env` 指定的环境：

```powershell
Set-Location 'Multi-UAV SimpleGC'
conda run -n llm --no-capture-output python main.py validate scenarios/task_point_visit_3uav.json
conda run -n llm --no-capture-output python main.py run scenarios/task_point_visit_3uav.json
```

SITL 仿真计算和 Python 数据分析都在本机运行，标准入口不调用外部仿真服务器。
当前观测为已知身份的飞控遥测，覆盖扫描使用理想几何模型；
共享矩形任务支持 1～6 机集中预规划分工，SIM 真值和 FCU 观测分别验证实际覆盖。
源时钟对齐采用被动估计，不是物理锁步或真实传感器探测；具体能力边界见工程说明。

有限清单运行支持重复 `--mission-id` 选择子集，并以 `--max-runs` 限制本次尝试数；
恢复时重复相同选择集和 `--output`，输入或代码变化则使用新输出目录。
加载器返回完整 episode，不自动裁剪滑动窗口或训练识别模型。命令见 TaskSpec v2 说明。

## 保存范围

仓库包含源码、文档、任务与场景、随工程提供的 SITL 程序和说明视频，以及现有
`runs/` 和 `datasets/` 实验记录。运行失败与任务验证未通过的记录也保留。
Python 字节码缓存和测试临时文件不纳入版本管理。
