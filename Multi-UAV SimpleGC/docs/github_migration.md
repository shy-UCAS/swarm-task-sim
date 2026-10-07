# 精简代码包与开发目录迁移

原 Simulation 目录保留 v0.5 原始数据、旧分析、冻结判定和历史提交，用于回放及复核。
后续开发使用独立目录。待发布候选获准推送并合入远端 main 后，再从 main 克隆新目录；
当前发布分支仅在本机，尚未推送。不要把原目录的 main 合入精简分支或直接推送。

## 新电脑的环境

当前已验证的平台是 Windows、PowerShell 7、Python 3.12 和 pymavlink 2.4.50。
先建立 `.conda-env` 指定的环境（当前为 llm），然后在 Multi-UAV SimpleGC 目录中安装依赖：

```powershell
conda run -n llm --no-capture-output python -m pip install -r requirements.txt
```

使用桌面回放时额外安装 requirements-gui.txt；核心 CLI 不需要这些界面依赖。
SITL EXE、DLL、参数模板及起飞前校验所需的两组 WP-S 基线已保留。
基线共 6 个 JSON（474,774 字节），按原确认链核对哈希，未修改原判定。
它们原先不在冻结 Git 提交中，本次从本机历史证据按原样纳入发布候选。
旧 CLAUDE.md 中本机绝对路径描述原归档环境；Git 命令应在新克隆的仓库根目录执行，
PowerShell/Conda 的安装路径以新电脑实际环境为准。

## 不启动仿真的运行准备检查

在 Multi-UAV SimpleGC 目录执行：

```powershell
$env:PYTHONPATH = 'tests'
conda run -n llm --no-capture-output python -m unittest test_publication_runtime test_run_provenance
conda run -n llm --no-capture-output python main.py --help
conda run -n llm --no-capture-output python main.py plan missions/v3/recon_route_v05.json --output tests/.tmp/migration_recon.json
conda run -n llm --no-capture-output python main.py validate tests/.tmp/migration_recon.json
```

plan 的输出文件必须不存在；重复核对时选一个新名字。
这验证文件依赖、固件/模板哈希和任务编译，不启动 SITL，也不验证主机负载下的实际飞行。
实际运行仍需遵循当前用户授权及适用规则，不能因通过离线检查自行开始批量生成。

## 数据边界

新任务的规划和起飞前文件校验不需要下载全量旧轨迹。
示例目录 examples/v05_episodes 保留 4 个原样 episode，可用于加载和格式核对。
历史批量控制器绑定旧台账、绝对路径和完整证据，不是新电脑的通用启动入口。
复现全量 v0.5 分析、回放任意旧运行或接续历史控制器时，仍需另外恢复完整归档。
产生的新运行默认被 .gitignore 排除，不要强制加入 Git。
