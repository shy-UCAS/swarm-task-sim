# 离线 episode 播放器

Windows 下可直接双击项目根目录的 `start_episode_player.bat`。启动器读取项目的 `.conda-env`，默认导入 `v06_pilot30b_seed2026100811`；若该批次不存在则打开空窗口，从菜单选择数据。也可以把单个 episode、示例目录、数据集或批次文件夹拖到这个 `.bat` 上打开。启动失败时命令窗口会保留错误信息。窗口打开后，双击左侧一行，再点击“播放”。

在 `Multi-UAV SimpleGC` 中运行：

```powershell
$EnvName = (Get-Content .conda-env -Raw).Trim()
conda run -n $EnvName --no-capture-output python -B -m episode_player --source examples/v05_episodes

# 导入旧 v0.6 pilot 的全部 30 个 episode。
conda run -n $EnvName --no-capture-output python -B -m episode_player --source '../../SwarmData/parallel_batch/v06_pilot30b_seed2026100811'
```

不传 `--source` 时，在窗口菜单“文件 → 打开文件夹”选择数据。支持单个 episode、示例目录、数据集和已导出 dataset 的批次目录。依赖与旧桌面工具相同，缺少时安装 `requirements-gui.txt`，不需要 matplotlib。

左侧列表先显示 manifest 的索引信息，可按意图和 family 联合筛选。双击一行后才调用共享的 `load_plot_episode()` 完成 `load_episode()` 的哈希、协议和版本校验；目录发现直接调用静态图脚本的 `discover_episodes()`。列表预览不代表数据通过校验。读取在后台线程执行，读取期间暂停播放，不能同时切换数据源。

中间为等比例 East–North 图：灰色目标区、虚线世界边界、浅色全程观测、每架机的大圆点及最近 10 秒尾迹。按原始 `t_s` 时间轴显示采样帧，两帧之间保持前一帧，不插值。mask=false 时隐藏当前位置和机号，完整航迹与尾迹也在该样本处断线。超过记录中的 `max_gap_s` 后不再显示过期位置。

底部可播放/暂停、拖动时间滑块、前后逐帧、选择 1×/5×/20×。拖动或逐帧会暂停；到末帧自动暂停，再次播放从开头开始。滑块的每个位置对应一个真实采样帧，遇到不等间隔数据时以显示的秒数为准。

顶部显示已加载 episode 的编号、意图、明确保存的飞法、SIM 通道任务成功及 episode 质量资格。未知值为“—”，失败运行或不合格样本标红。质量不合格不阻止播放已有数据。

某项加载失败时弹窗显示原始错误，该行变灰，鼠标悬停可看原因；其他 episode 可以继续加载。此前已加载的轨迹可能仍显示，顶部编号明确标识其来源。版本和哈希错误不会被绕过。v0.6 组件版本以所属数据集清单为准，同一组件名在数据集内只允许一个版本；具体规则见[静态图说明](visualization.md)。旧 pilot 可整批导入，其中失败的巡逻可播放已有观测部分。

播放器不保存设置、索引、缓存、截图或视频，不写输入文件，也不启动仿真。包入口禁用 Python 字节码写入，建议仍使用上述 `python -B` 命令。静态图脚本只复用读取和场景函数，播放器不会调用其文件输出函数；旧 `replay_viewer/` 保持原样。第一版只播放单个 episode，没有 family 同步播放、真值/规划航线、阶段着色或时间曲线。
