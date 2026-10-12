# M2-01 修复复审：FIX_REQUIRED

日期：2026-10-12。被审修订：`attempt_02_repair`。原 [M2-01 审阅回执](M2-01_review.md) 保留不变。

**结论：FIX_REQUIRED。默认根、目标根归属、联接拒绝和 verify 根传递已通过复审；仅剩 run-id 前置校验的一处分支遗漏。显式 `--output` 会绕过前置 ID 校验并创建产物，需补齐后放行 M2-02。迁移及已经通过的路径行为无需重做。**

## 1. 被审身份与独立证据

| 对象 | 身份 |
| --- | --- |
| 分支 / HEAD | `codex/fast-dynamics` / `57cca914f2e8b414e8820a1f08f6fd900f912d36` |
| 跟踪 diff | 1,627,170 字节；SHA256 `19782fb7a966ba85626c9de4fd847e3b19897642472f0ebfbcf47c13150d2b4a` |
| 报告 SHA256 | `311c14ac61b9bc5d29e3b7b3589a3ff4e9d1cc9df0c989fdae53e935a507efc6` |
| 摘要 SHA256 | `2f210208912581eb8dd1c74f0ff6f7b0d278aefe99186f7211efbac2c917a910` |
| `output_policy.py` SHA256 | `dba5cc66cdaada630395bdba136d416a11d82338f4808fe7ee97d240756d8730` |
| `run_fast_dynamics.py` SHA256 | `33ac45acaf836d80ac77ff68d7721567e26fc16d25f948c6336be015f0c0679c` |
| 策略测试源码 SHA256 | `5508de851a186d648762aa1afe080015bfbfc7d76222c157b3fcf59ede4e5cbb` |
| 归档 relocation 索引 SHA256 | `e023a4e3194f12790279710c3f2a785208a7165b1be736c5d55bdea0c5ccb55e`，未变 |
| 原回执 SHA256 | `5e99c2428e7370117f38d7a88802345637513d0545c937ef83f04268a8a57a71`，未变 |

diff 口径为 Git 根 `git diff --binary --no-ext-diff --no-color HEAD --` 的 stdout 原始字节；新增未跟踪源码单独绑定哈希。

独立复审证据：

```text
F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/fast_dynamics/m2/review/M2-01/review_03/
  review_checks.py
  checks.json
  policy_tests.log
  short_name_test.log
  review_checks.log
  identity_and_archive.json
```

`checks.json` SHA256：`a81f67e1bf59edb4b7416e16ac0bc816f796eee0d169218402b1b6f657ec29c0`。

本轮使用 PowerShell 7、项目 `llm` 环境，复跑针对性测试和只读产物检查；未修改业务代码、提交、迁移、清理、运行 SITL 或读取留出数据。独立策略测试中的真实默认 M1 attempt 在仓库外保留。额外非法参数复现用模拟入口哨兵，不产生真实飞行结果。

## 2. 已通过的修复

- 默认根已改为 Git 根父目录下的 `SwarmData/fast_dynamics`，默认 run 完整链实际通过，默认 verify 不再被策略自拒。
- 目标解析后必须位于有效根内，根外 `--output`、`..` 与 junction 根逃逸的拒绝行为通过；尚未创建的合法根可以使用。
- 三个入口的根优先级和创建前拒绝行为，在已登记合法/非法目标用例上正确。
- 独立复跑策略测试 **25/25 通过，0 skip**，三个 junction 用例真实执行。
- 原 8.3 短名用例在正常 C: 临时目录独立复跑 **1/1 通过，0 skip**，支持其 F: skip 与本次策略无关的解释。
- 真实 verify 的阶段 completion 与 verification 哈希匹配；全部 **7/7 子 attempt** 的根和报告中的根均等于自定义根，报告 completion 哈希全部匹配，帧数仍为 294×5、1637、1。
- 修复后的 16 项源码/文档快照独立复算全部匹配；归档 **356/356** 的大小和哈希再次核对无差异，relocation 索引身份未改变。
- M1 CLI 测试只增加隔离根参数，原失败留痕和重复 attempt 拒绝断言仍保留；公共数据/产物 API 与语义阈值未被放宽。

完整离线原日志是 **431 个用例执行，其中 430 通过、1 跳过、0 失败/错误**；不能将 `Ran 431 ... OK (skipped=1)` 表述为同一次运行全部 431 通过。被跳过的 1 项有独立补跑通过证据。真实 verify 的 legacy 392 也包含同一 skip。报告计数可据此修正，不需要为改计数再重跑完整清单。

过程日志被覆盖的缺陷已明确登记；本轮不把追认说明当作找回原始日志，也不要求重造已经丢失的首轮输出。

## 3. 最后一项必修：ID 校验未覆盖显式输出分支

位置：`scripts/run_fast_dynamics.py:36`：

```python
requested = args.output if args.output is not None else new_attempt_path(root["root"], args.run_id)
```

`new_attempt_path` 内部调用 `sanitize_component`。显式给出 `--output` 时，不调用这个函数，`args.run_id` 没有同样的前置校验。它先进入 attempt 创建和模拟调用，之后才可能被 `write_episode` 的 ID 规则拒绝。

独立复现对照，`run_mission` 均换成审阅哨兵：

| 参数 | 实际结果 |
| --- | --- |
| 自动输出 + `--run-id x/../../../escaped` | `SystemExit(2)`；模拟调用 0；文件 0 |
| 显式根内 `--output` + 同一非法 ID | 模拟调用 1；写出 `input_task.json`、`config.json`、`attempt.json`、`failure.json` |
| 自动输出 + `--run-id name.with.dot` | 模拟调用 1；写出上述 4 个文件；该 ID 后续不符合公共产物的 ID 语法 |

**此次没有发生根外写入，根归属修复本身有效。** 遗漏是“非法 ID 在创建任何产物/开始计算之前拒绝”的约定没有覆盖全部分支；相同参数因为是否显式输出而得到不同校验行为。

现有 `artifacts.py`、`dataset.py` 对 run ID 均采用 `[A-Za-z0-9_-]{1,100}`。只检查 Windows 文件名安全不等于检查后端可接受的 run ID。前置校验应同时覆盖必要的文件名安全与既有公共 ID 契约，不能放宽后端规则来让 `name.with.dot` 通过。

**修复目标：** 在输出路径选择、mkdir、读取任务或模拟前，统一验证 `args.run_id`，不依赖 `new_attempt_path` 是否被调用。自动/显式输出两种模式都用同一规则，错误为明确的参数拒绝且零产物、零模拟调用。

不要把通用 `sanitize_component` 强行改成禁止所有点号的 run-ID 专用函数；benchmark 的 `kernel_benchmark.json` 前缀仍需合法。可以新增或复用单独的 ID 校验，并在 CLI 中无条件调用。

## 4. 可直接转发的有限修复指令

```text
仅补齐 M2-01 最后一项 ID 前置校验，不进入 M2-02。
依据 docs/fast_dynamics_m2/M2-01_review_02.md 第3节。
基线57cca91保持不变，不提交、不amend、不push。

1. 新建外部 attempt_03_id_guard，保存本轮被审报告/摘要及拟修改代码、测试的
   原样副本和哈希。保留此前attempt及回执。已通过的迁移/清理/默认根/根归属/
   verify根传递不重做、不恢复旧载荷。
2. 在run入口无条件前置验证run-id：不论是否给--output，都必须符合公共产物既有
   ID规则及必要文件名安全要求，在路径创建、任务读取和模拟前拒绝非法值。
   不放宽write_episode/dataset的ID规则，不破坏benchmark含.json的通用文件前缀。
3. 增加自动与显式输出的配对测试：x/../../../escaped、name.with.dot、空/超长等
   不合法ID两种模式均参数拒绝；输出根/目标零新增产物、run_mission零调用。
   合法ID在两种模式下都能运行，原重复attempt与引擎失败留痕仍正确。
4. 跑策略测试和受影响M1执行/产物测试，至少包含一个真实完整链。无需再次跑
   431项全清单或131秒verify，不重做归档验证：本次是入口参数拒绝的局部修复。
   出现新回归时按影响补验证，不删用例、不用临时目录清理掩盖“曾创建产物”。
5. 更新报告/摘要、重新绑定最终代码/diff/原始日志哈希；将原离线计数如实写成
   431总数、430通过、1跳过，另列被跳过用例的补跑证据。修复后的测试数量实测填写。
   状态AWAITING_REVIEW，完成后停止，不自行PASS，不进入M2-02。
```

后续复审仅需聚焦这一分支遗漏与新证据。已通过的归档、根解析、根归属、junction 和真实 verify 根传递不因本回执而重新变为未完成项。
