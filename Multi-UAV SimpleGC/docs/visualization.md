# 离线 episode 俯视图

`scripts/viz_episodes.py` 是只读诊断工具，不启动 SITL、不重算标签或质量，也不改变数据协议。轨迹严格来自 `load_episode()` 的原始 ENU 位置与 mask，目标区域来自 `load_public_scene()`；没有 CSV 回退、插值、平滑或归一化。

在 `Multi-UAV SimpleGC` 中读取 `.conda-env` 后运行：

```powershell
$EnvName = (Get-Content .conda-env -Raw).Trim()
# 环境缺少 matplotlib 时才安装可选依赖。
conda run -n $EnvName --no-capture-output python -m pip install -r requirements-viz.txt

# 四个 v0.5 示例：四张单次图，以及每个 family 的横向对比图。
conda run -n $EnvName --no-capture-output python -B scripts/viz_episodes.py --source examples/v05_episodes --family --show-split

# 只画指定 family；同 family 的所有可用飞行横向并排。
conda run -n $EnvName --no-capture-output python -B scripts/viz_episodes.py --source examples/v05_episodes --family scene_6d1987b34d9556dee551

# 批次目录也可作为输入；按所属数据集的冻结组件版本加载。
conda run -n $EnvName --no-capture-output python -B scripts/viz_episodes.py --source '../../SwarmData/parallel_batch/v06_pilot30b_seed2026100811' --family
```

`--source` 支持单个 episode、示例目录、带 `dataset_manifest.json` 的数据集及已导出数据集的批次。默认输出到仓库外 `SwarmData/viz/<来源名>_<UTC时间>/`，也可用 `--out` 指定该 `viz` 根下的独立子目录。禁止输出进源目录或归档，已有同名图片不覆盖。

输出为 `episode_<目录名>.png`；加上 `--family` 后另有 `family_<family_id>.png`。带 ID 时只选择该 family；不带 ID 时对所有具有 family ID 的 episode 分组。不同 family 不拼在一起，不猜补缺少的意图。单次图与 family 图都保持横纵 1:1，family 内使用相同坐标范围和机号配色。

灰色矩形是公开目标区域；虚线是场景的世界边界，属于场景上下文。世界边界读取已通过加载器哈希核验的 `task.json`，不作为观测特征。当前 v2/v3 场景协议要求 `restricted_regions` 为空，故现有数据没有限制区域；脚本可画采用现有矩形字段的限制区，不推测其他几何格式，也不放宽加载器约束。

实线是模型观测轨迹，mask=false 处用 NaN 断开；圆点和叉号分别是第一、最后一个有效观测点，不是起飞/落地事件或计划航点。标题只显示意图、明确保存的计划飞法、SIM 通道任务成功和 episode 质量资格；缺少值显示“—”，不会根据轨迹或 planner 猜飞法。失败运行或不合格样本标红，仍绘制已有有效观测；无有效观测时保留场景并注明。

`--show-split` 在图下显示冻结 split。独立 v0.5 示例没有数据集清单时，仅使用同目录 `sample_index.json` 的 `original_split` 并标为 original split，不重新划分。

加载器的哈希绑定与协议校验保持不变。v0.6 episode 的组件版本必须与所属数据集清单中的条目一致；同一组件名在整个数据集中只能对应一个版本，不同 episode 可以使用不同组件。组件名按现有标识最后的 `_v` 分隔，如 `perimeter_revisit_v2` 的组件名为 `perimeter_revisit`，不建立意图或飞法的适用范围表。metadata 原样返回数据自己的组件版本，不要求与当前注册表相同；没有所属数据集清单的独立分析产物保留原校验。旧 pilot 的 `observer_facts_v06` 因而可直接读取，无需改写旧清单、哈希或标签。

加载失败会打印具体错误并继续其他 episode，最终返回 1；其 family 对比图不生成，以免产生不完整对比。输入或输出配置错误返回 2；所有图片成功返回 0。

旧 `replay_viewer/` 保留，用于历史阶段目标点格式的运行回放；当前连续航线及 episode 静态图使用本脚本。按时间播放请用[离线 episode 播放器](episode_player.md)，它直接复用本脚本的目录发现和加载函数。真值/规划叠加、时间曲线和阶段着色留待以后需要时再加。
