# V8-05 随机数键派生与多样性度量 报告

- 工作项：V8-05（里程碑 ③ 单段原型，实现类，分三部分）；执行日期 2026-11-02；执行方：Claude Code（Windows 主机）。
- 依据：`_handoff/2026-11-02_V8-05_pilot/V8-05_经济实现方试点_执行指令_20261102.md`（下文"指令"），以及用户在对话中的"执行方式调整"（以其为准）：执行方改为 Claude Code，不使用 Aider、不建 `t2l-pilot` 环境与独立克隆；指令第 1–3 节的 Aider 操作、第 0.3 节固定追加语、第 5 节试点统计不适用；在开发工作树 `Simulation-v08` 中工作，分支名改为 `review/v08/V8-05-keys-diversity`。

---

## 0. 复述与环境

### 0.1 任务复述

实现三组与场景、仿真无关的纯函数，供 ③ 后续使用：（1）`v08/sampler/keys.py`：r3 13.5 的随机数键 `RngKey`、校验、family 熵、键的 8 个 32 位字、`SeedSequence` 与 `PCG64` 生成器；（2）`v08/diagnostics/diversity.py`：折线等弧长重采样、离散 Fréchet 距离（迭代动态规划）、两两 Fréchet 矩阵；（3）同文件追加变异系数。先快进合并已接受的 V8-04 进 `dev/v0.8` 并推送，再新建审查分支；预置测试原样放入、核对 SHA256、单独提交；每部分单独提交并运行对应测试。

停止条件：快进或推送被拒（不加 `--force`，停下询问）；预置测试 SHA256 与指令第 1.6 节不一致；提交中出现指令第 0.2 节以外的实现文件；认为预置测试预期有错（停该部分并写入本报告）。不得：推送 `main`、强制推送、修改冻结工作树、写入 `SwarmData\v07_*`、在 `llm` 中安装或升级包、修改或删除预置测试。

### 0.2 合并与环境

| 项 | 结果 |
|---|---|
| 开工前 | 开发工作树在 `review/v08/V8-04-sim-adapter`，`status` 为空；`dev/v0.8` = `97e757f` |
| 合并 V8-04 | `fetch origin refs/heads/review/v08/V8-04-sim-adapter:…` 后 `merge --ff-only` 成功，`dev/v0.8` = `0d525ef` |
| 推送 `dev/v0.8` | 成功（`97e757f..0d525ef`）；`git ls-remote` 核对远端 `dev/v0.8` = `0d525ef7125c4513d2c9bff8104b664e6af15084` |
| 审查分支 | 从 `dev/v0.8`（`0d525ef`）新建 `review/v08/V8-05-keys-diversity` |
| 预置测试 SHA256 | 指令包原件与放入仓库后、全部完成后三次核对，均与指令第 1.6 节一致（见第 4 节） |
| 冻结工作树 | 完成后 `Simulation-fe-prod-r3`、`Simulation-fe-s3` 的 `status --porcelain` 均为空 |
| 运行环境 | `conda run -n llm --no-capture-output python -B`；Python 3.12.3、NumPy 2.5.3；`PYTHONDONTWRITEBYTECODE=1`、`OMP_NUM_THREADS=1`；未安装或升级任何包 |
| 停止条件 | **未触发** |

---

## 1. 每部分结论

| 部分 | 内容 | 预置测试 | 首次运行 | 提交 |
|---|---|---|---|---|
| 1 | 随机数键派生 | 7/7 通过 | 通过 | `1b9b4e5` |
| 2 | 折线重采样、离散 Fréchet、两两矩阵 | 6/6 通过 | 通过 | `7eef263` |
| 3 | 变异系数 | 2/2 通过 | 通过 | `9699643` |

- **第 1 部分：通过。** 按规格实现；`family_entropy`、`key_words`、两条随机流前 4 个整数均与预置测试中由 NumPy 直接算出的预期逐位一致。模块无全局可变状态（只有两个不可变常量）。首次运行通过后加了一处校验（见第 6 节），复跑仍 7/7。
- **第 2 部分：通过。** Fréchet 为逐行动态规划的双层循环，只保留上一行，无递归；1500×1500 用例连同本部分其余 5 项共 0.55 s。重采样用"跳过零长度腿后的腿终点弧长"做 `searchsorted` 定位腿，比例截断到 [0, 1]。
- **第 3 部分：通过。** 按规格实现；同时把 `diversity.py` 模块文档字符串补上"变异系数"一词，其他已有函数未改。

---

## 2. 分支与提交

分支 `review/v08/V8-05-keys-diversity`，基于 `dev/v0.8` = `0d525ef`：

| 提交 | 说明 |
|---|---|
| `d7dd4f9` | V8-05 预置测试（规划审查方） |
| `1b9b4e5` | V8-05 第 1 部分：随机数键派生 |
| `7eef263` | V8-05 第 2 部分：折线重采样与离散 Fréchet 距离 |
| `9699643` | V8-05 第 3 部分：变异系数 |
| `cae027f` | V8-05 报告与测试输出 |

远端提交号：首次推送 `review/v08/V8-05-keys-diversity` = `cae027fce5adbe687d25ee35e3eb5d4e8ebb5784`；本行所在的补记提交随后推送（只改本报告）。

---

## 3. 改动文件清单

`git diff --stat dev/v0.8...HEAD`（第 3 部分提交后、本报告提交前）：

```
 .../tests/v08/V8-05/test_preset_v8_05_part1.py     |  86 ++++++++++++++++
 .../tests/v08/V8-05/test_preset_v8_05_part2.py     |  96 ++++++++++++++++++
 .../tests/v08/V8-05/test_preset_v8_05_part3.py     |  37 +++++++
 Multi-UAV SimpleGC/v08/diagnostics/__init__.py     |   1 +
 Multi-UAV SimpleGC/v08/diagnostics/diversity.py    | 112 +++++++++++++++++++++
 Multi-UAV SimpleGC/v08/sampler/__init__.py         |   1 +
 Multi-UAV SimpleGC/v08/sampler/keys.py             |  78 ++++++++++++++
 7 files changed, 411 insertions(+)
```

本报告提交另加 `docs/v08/V8-05/REPORT.md`、`docs/v08/V8-05/preset_tests_all.txt`。除三份预置测试外，实现文件都在指令第 0.2 节清单内；两个 `__init__.py` 均只有一行模块文档字符串，不导入任何东西。

---

## 4. 预置测试

SHA256（指令包原件、放入仓库后、全部完成后三次一致）：

| 文件 | SHA256 |
|---|---|
| `test_preset_v8_05_part1.py` | `ccf67eb57b69e22d1b33b2a30233ba9604f9c638c9f28d21ce79494bd96afd8f` |
| `test_preset_v8_05_part2.py` | `64ff9a7e95b6fb2552096de0a8304d4428f1b59f90721a15e3b2fbc632cd7c0b` |
| `test_preset_v8_05_part3.py` | `d0a2ae4c250c063a75a85946396bb56ad85b0a7b0a929f16ebc9b84d62d57c1c` |

全量运行（`-p "test_preset_v8_05_part*.py"`）：**15/15 通过**，0.509 s，原始输出见 [preset_tests_all.txt](preset_tests_all.txt)。

| # | 部分 | 测试 | 结果 |
|---|---|---|---|
| 1 | 1 | `test_attempt_changes_only_its_own_stream_and_order_does_not_matter` | ok |
| 2 | 1 | `test_family_entropy` | ok |
| 3 | 1 | `test_frozen` | ok |
| 4 | 1 | `test_invalid_keys` | ok |
| 5 | 1 | `test_key_words` | ok |
| 6 | 1 | `test_purposes` | ok |
| 7 | 1 | `test_streams` | ok |
| 8 | 2 | `test_frechet_invalid_and_large` | ok |
| 9 | 2 | `test_frechet_known_values` | ok |
| 10 | 2 | `test_frechet_properties` | ok |
| 11 | 2 | `test_pairwise` | ok |
| 12 | 2 | `test_resample_edge_cases` | ok |
| 13 | 2 | `test_resample_straight_and_corner` | ok |
| 14 | 3 | `test_invalid` | ok |
| 15 | 3 | `test_values` | ok |

测量范围：只覆盖预置测试；未加自写测试，未跑仓库其他测试集（本次改动只新增文件，不触及已有模块）。

---

## 5. 偏离指令之处及原因

1. **执行方式**：按用户调整，由 Claude Code 在开发工作树直接实现，无 Aider 会话、无对话记录、无 `PILOT_LOG.md`，指令第 5 节试点统计（一次通过率、轮次、费用等）不产生。
2. **`seed_sequence` 开头加了 `validate_key(key)`**（第 1 部分）。规格写法 `SeedSequence(entropy=family_entropy(key.family_id), spawn_key=key_words(key))` 会先求 `key.family_id`，传入非 `RngKey` 对象时抛 `AttributeError` 而不是规格要求的 `ValueError`。加校验后合法键的结果完全不变（预置测试复跑 7/7），只是合法键会被校验两次（第二次在 `key_words` 内），开销可忽略。
3. **输入转换失败统一转成 `ValueError`**（第 2、3 部分）：`np.asarray(..., dtype=float)` 对参差列表、非数值对象可能抛 `ValueError` 或 `TypeError`，实现中统一转成 `ValueError`；`spacing_m` 不能转成浮点数时同样抛 `ValueError`。规格未明说这两类输入，此处取与其他非法输入一致的处理。
4. **`pairwise_discrete_frechet` 先对每条折线做一次公共检查并转成数组**，再两两调用 `discrete_frechet`；空列表抛 `ValueError`。规格的"每条都要通过公共检查"由此满足，即使只有一条折线（不发生任何配对）也会检查它。

---

## 6. 疑似预期错误

无。15 项预期均与规格一致，未发现需要停下的情况。

---

## 7. 复跑命令

在仓库根目录（PowerShell 7）：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:OMP_NUM_THREADS='1'
C:/Users/shy/anaconda3/Scripts/conda.exe run -n llm --no-capture-output python -B -m unittest discover -s "Multi-UAV SimpleGC/tests/v08/V8-05" -p "test_preset_v8_05_part*.py" -v
```

单个部分把 `-p` 换成 `test_preset_v8_05_partN.py`（N = 1、2、3）。

---

## 8. 执行方观察（个人判断，与上文事实分开）

1. **Fréchet 的内存是 O(n·m)。** 当前实现用 NumPy 一次算出整张距离矩阵再 `tolist()`，1500×1500 约几十 MB，没有问题；若 ③ 之后对 10⁴ 量级点数的折线直接求 Fréchet，内存会到 GB 级。届时可改为逐行即时计算距离（DP 本来只保留一行），结果不变。建议在调用方先用 `resample_polyline` 控制点数。
2. **重采样终点可能与原终点差一个浮点舍入。** 规格中 `floor(L/spacing + 1e-9)` 与 `L − s_n > 1e-9` 的组合意味着：当 `L/spacing` 恰为整数但浮点上略大（如 0.9/0.3），最后一点是 `n·spacing`（比 `L` 小约 1e-16），而不是精确的原终点。预置测试以 `atol=1e-12` 接受这一点；若下游要求首末点与原折线逐位相同（例如做哈希或等值比较），需另行约定。
3. **`key_words` 依赖 `json.dumps` 的整数序列化。** 当前校验已排除 `bool`、浮点和 NumPy 整数（`np.int64` 不是 `int` 子类，会被拒），所以规范串是稳定的；调用方从 NumPy 数组取下标作 `draw`/`mission` 时需先转成 `int`，否则会得到 `ValueError`。这是有意的严格，但值得在 ③ 的调用处注意。
4. **试点统计缺失。** 本次由 Claude Code 执行，三部分均首次运行即通过，但这一结果不能代表 DeepSeek/Aider 的表现，指令原定的低价模型评估仍未做。
