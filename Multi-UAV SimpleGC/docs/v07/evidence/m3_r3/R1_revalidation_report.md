# R1 受控修订重验：BLOCKED（验收脚本错误）

本次起点为 `316d0fa7a3fc03249db363cb4a8ab219de6ed32b`，分支 `fe/m3-r3-p2-candidate`，启动工作区干净。未新建工作树、未重置分支。

## 实际停止位置

R1a 日志与哈希核查完成后，在 R1b 输入校验准备处停止。新增 `scripts/revalidate_m3_r3_r1.py:185` 将 pathlib 路径与字符串直接相加，抛出：

```
TypeError: unsupported operand type(s) for +: 'WindowsPath' and 'str'
```

这是本轮新增验收脚本的实现错误，不能归因于 r3 曲线算法、历史数据或四项旧测试。程序写入 `R1_REVALIDATION_BLOCKED`，按用户停止规则不自动修复重跑。原始堆栈保存在 `R1_revalidated_gate.json` 和外部 attempt `summary.json`。

后续修复方向是正确组合 pathlib 路径；尚未实施。下一次还应补齐启动路径覆盖，并复核本轮未执行到的干跑、七探针、分阶段精度比较逻辑。当前脚本不可视为已验收的自动总控。

## 历史故障核查

四项均以完整 ID 登记在 `R1_legacy_failures.json`，历史 FE 基线与候选的 FAIL/ERROR 类型、测试行号、异常类型及内容一致；只归一化不同工作树路径。原测试文件及已登记关联文件通过 Git 固定提交对象与 SHA256 再核验。日志哈希均与上轮保存值一致。

- 两个候选池测试：旧断言固定 1.15，现行且与基线相同的生成配置为 1.30。
- 校准轮数测试：mock 指向已不存在的 `calibrate_episode`，实际校准/间距断言未执行。
- 驻留测试：旧 `minimum_dwell` 条件字段读取报错，实际走 `labels.measure()` 的 `criteria_labels.measure_criteria()` 分支；后续 P0 审计断言未执行。

不能将后两项称为完全不涉及安全合同。最终补充 G-1/G-5 优先于前文范围排除，允许精确基线故障登记为债务；绝不据此宣称其安全断言已通过。所有历史断言保持原样，生产合同未修改。

## 测试与探针：明确区分历史和本轮

| 项目 | 本轮状态 |
|---|---|
| 历史日志 209 项 | 205 PASS、2 FAIL、2 ERROR；仅复核既有证据，不是本轮重跑 |
| 新门禁解析/差分自测 | 7/7 PASS，正式命令 `python -B -m unittest -v test_m3_r3_r1_revalidation` |
| 固定 FE 隔离基线 200 项 | 未启动，未创建基线检出副本 |
| 本轮原 209 项完整回归 | 未启动，新失败数不可评价 |
| R1_REGRESSION_DELTA_ZERO | 未完成验收 |
| 七探针 r2 历史逐位兼容 | 0/7，未运行 |
| 七探针 r3 / D0b B2 复现 | 0/7，未运行 |
| probe_05 精度 | 仅保留历史 r2 最大 1.7849249178526083 m；0.5 m 绝对门槛历史 FAIL；本轮相对变化未知 |

新增七项测试覆盖历史故障不冒充 PASS、异常类型/位置变化、意外 SKIP、漏测、signed zero 字节差异及不完整日志。它们未覆盖此次失败的启动路径，不能替代完整流程验证。

## 门禁与保护

- R0：维持 R0_REVALIDATED_PASS。
- R1：原 FAIL 记录不变；追加重验 BLOCKED。
- R2/R3/R4：未执行，R1 未通过。
- G-1～G-5 的修订口径已登记 `R1_validation_plan_amended.json`；尚未获得可运行验收结果。
- `R1/baseline_gate_dryrun.json` 为 INCOMPLETE，不能当作基线已经完成干跑。
- 原 R1_report.md、R1_gate.json、R1/gate.json 哈希不变；前一 pipeline_state 已备份到 R1_revalidation/previous_pipeline_state.json。
- 本轮未修改生产代码、原测试、r2 冻结配置、历史数据；无 SITL、holdout、P2 合并、稳定分支合并、正式冻结、标签、量产或推送。

## 证据位置

仓库：当前目录下 R1_legacy_failures.md/json、legacy_test_debt.md、R1_validation_plan_amended.json、R1_revalidated_gate.json、R1_revalidation/。

外部：`F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\fast_dynamics\m3\m3_r3_r1_revalidate01`，包含 registration.json 与 summary.json。所有后续运行必须保留本次失败 attempt，不覆盖。
