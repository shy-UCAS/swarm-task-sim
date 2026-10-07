# 批量生成前：试生产可选返航描述只读核对

结论：通过。试生产 20/20 个 episode 的事实由原导出数据重新提取后完全一致，80/80 条描述通过现有一致性校验。`return_required=false` 共 12/20 个 episode（侦察 6/10、巡逻 6/10），对应 48/80 条描述；其中“返航条件”类句子为 0/48 条，返航相关句子均由轨迹事实 `observed.return_observed` 单独支撑。无需修改模板，无需重新生成描述，无需重飞。

异常：描述事实问题 0/48 条。这 12/12 个 episode 的双通道轨迹均支持“未全部返回各自起点”；现有返航判定使用完整主阶段结束后轨迹和相对于各机出发位置的距离，半径为 \(3.0\,\mathrm{m}\)，不使用 `return_required` 推断是否已返航。检查期间未启动仿真、未修改源码；原 dataset 和描述层 503/503 个文件前后 SHA256 一致。沙箱内 Conda 启动曾报 Windows DLL 重定位错误，随后同一只读命令在允许的提升上下文中执行成功；该启动错误未触发数据处理或改变原始文件。

| episode | 意图 | 描述核对 | 双通道返起点事实 |
|---|---|---:|---|
| 20261002T200859Z_f177aa58 | 侦察 | 4/4 | 均为 false |
| 20261002T201410Z_a923be74 | 巡逻 | 4/4 | 均为 false |
| 20261002T202007Z_7dceef98 | 侦察 | 4/4 | 均为 false |
| 20261002T202309Z_ef48c8bb | 巡逻 | 4/4 | 均为 false |
| 20261003T035249Z_3ad11f6d | 侦察 | 4/4 | 均为 false |
| 20261003T035718Z_29df35cb | 巡逻 | 4/4 | 均为 false |
| 20261003T040225Z_75fc53bf | 侦察 | 4/4 | 均为 false |
| 20261003T040757Z_a194019a | 巡逻 | 4/4 | 均为 false |
| 20261003T042137Z_23cac07b | 侦察 | 4/4 | 均为 false |
| 20261003T042523Z_9301f0d3 | 巡逻 | 4/4 | 均为 false |
| 20261003T042957Z_ac9f8289 | 侦察 | 4/4 | 均为 false |
| 20261003T043507Z_13f2d85e | 巡逻 | 4/4 | 均为 false |

证据位置：

- `audit.json`：48/48 条原文、模板 ID、事实引用、12/12 个 episode 的逐机双通道起点及末点距离、全部原文件哈希和 80/80 条一致性结果。
- `audit_pilot_returns.py`：只读核对脚本；在项目目录使用 `conda run -n llm --no-capture-output python tmp_v05/batch_return_check_20261002/audit_pilot_returns.py` 执行，已有审计输出存在时拒绝覆盖。
- 原描述层：`verification/v05_r12b_pp_20261002/dataset_language_zh_v0/`；原数据：`verification/v05_r12b_pp_20261002/dataset/`。
- 模板依据：`swarm_sim/language_templates_v0.py:339` 仅在要求返航时加入条件句；`:344` 起，观测返回句只引用轨迹事实。
- 事实依据：`swarm_sim/observer_facts_v0.py:246` 的 `_return_observed`；`:270` 起使用轨迹距离判定。原有回归覆盖在 `tests/test_wp_l_templates.py:131` 和 `tests/test_wp_l_facts.py:74`，本次未改代码，未重复运行测试套件。

本次核对的源码 SHA256：

| 文件 | SHA256 |
|---|---|
| `swarm_sim/language_templates_v0.py` | `4626a3e809073d6f861887b4360bf717c8b3ee31522e7a2879f316828badc552` |
| `swarm_sim/language_v0.py` | `17b50cda2eda21d798960e12ccfce5498b48042168c069ecb075bfc21aa1c8c2` |
| `swarm_sim/observer_facts_v0.py` | `05fb8e236934fb5cd5b6e5fed8e6225fb18c63e137845eb1f7a48f7090a7c363` |
