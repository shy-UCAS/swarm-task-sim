# S3 r2 措辞修订与复验报告

结果：**S3_R2_PASS**。2026-10-18（America/Los_Angeles），收尾核验 UTC 时间 2026-10-18T07:59:45.9721110Z。
本报告追加记录 r2，不改写 S3_report.md 的 r1 验收和历史停止记录。

## 授权修订

批准人：用户（本会话明确授权）。模板版本以新文件 templates_v07_s3_r2.json 标识，原 r1 文件完整保留。

| 项目 | 原内容 | r2 内容 |
|---|---|---|
| 扇区名称 | 东、东北、北、西北、西、西南、南、东南 | 正东、东北、正北、西北、正西、西南、正南、东南 |
| 编组句序 | approach → role → coordination → exit | approach → coordination → role → exit |
| role_feint/B2 | 随后抵近至设施{f}的警戒区内，再行折返。 | 随后抵近并进入设施{f}的警戒区，之后折返。 |

其余 63 条模板逐值相同。门控和首句补主语规则保留；独立验证器同步采用新顺序和方位表。
from_sector 的角度算法不变，仅名称改变，slots 同步更新。
随机种子及抽签算法不变；按新句序抽签，协调句和作业句可能相应选用同一模板组内另一现有变体。
归一化、family 划分、加载器、导出脚本均未改动。

## 工作树与提交

- 工作树：F:\CASIA\Drone Swarm Situational Awareness Algorithm\Simulation-fe-s3
- 分支：fe/s3-language-loader
- 本轮起点：6fb6d2c181fa521dfc546b90e060715bd590d89f
- 实现提交：d3aeea9b7e0f342e3dd32145f1256b65f936cbfd
- 提交标题：feat(s3-r2): 更新方位名称、编组句序和佯动措辞
- 环境：PowerShell 7.6.5；conda llm；Python 3.12.3；NumPy 2.5.3。单进程，数值库线程数限制为 1。
- 本报告与日志另行提交；最终提交 SHA 和远端一致性见交付回复。

## T1–T14

本轮完整重跑 **14 项，14 PASS，0 FAIL，0 ERROR，0 SKIP**，没有沿用 r1 的测试结果充当本轮通过。

运行命令（项目目录下，PYTHONPATH 含项目和 tests）：

```text
python -B -m unittest -v test_v07_s3_unit -f
python -B -m unittest -v test_v07_s3_integration -f
```

| 范围 | 结果 | 日志与覆盖 |
|---|---|---|
| T1–T12 | 12 PASS，0.114 s | T1_T12_r2_attempt01.log |
| T13–T14 | 2 PASS，506.016 s | T13_T14_r2_attempt01.log；包括主导出、独立复现导出及全量检查 |

T1 覆盖八方位、扇区边界、跨零点圆周平均、四个正方位 slots/渲染一致性、任一同向成员航向为 None 时拒绝。
T2 保留原省略门控断言，补充同步/递次的新顺序；对单编组和多编组、A/B 两组，验证省略 approach 后由 coordination、role 或 exit 中首个剩余句补主语；验证旧顺序被独立核验器拒绝。
T6 验证模板版本 r2，且 64 条模板中只有获批的 role_feint/B2 改变。
T14 在锁定的真实多编组突防样例上验证两个编组的准确句序，intrusion 仍不输出退出句。
T3–T12 的原有门控、绑定、归一化、白名单、划分和输入校验断言保留。

## Q0–Q4 与导出

主导出：F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_first_edition_s3\s3_dev_f000_005_r2

独立复现导出：F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_first_edition_s3\s3_dev_f000_005_r2_repro01

T13 直接调用原 export_runs，两个目录都是本轮新建；Q0–Q4 由原导出流程执行，没有改动导出逻辑。

| 检查 | 结果 |
|---|---|
| Q0 | PASS；60 条保留 episode，6 draw × 5 intent × 2 mode，实际保留 4 个 family；产物哈希检查通过 |
| Q1 | PASS；60 条索引、160 条描述；禁用词 0、独立事实绑定不一致 0；两次 JSONL 逐字节一致 |
| Q2 | 完成；460 个成员样本，全部指标与 r1 完全相同；实际 stop_hold 为 1 s |
| Q3 | PASS（自动核验）；10 条样例，五种意图同步/递次各一条，逐条生成并核验 A/B 文本 |
| Q4 | PASS；每次 60 episode、120 输入视图、160 目标；主导出 137.155 s，复现导出 135.144 s |

划分仍为 train/val/test = 10/30/20 条 episode，描述分别为 30 A / 90 A / 20 B + 20 A 诊断。没有调整 family 哈希规则。

两条指定的多编组样例仍在 samples_for_review.md：

- family_s15_79c93b22d09e8a7a_ext_001_regular/sequential：区域搜索 + 抵近观察。
- family_s15_38bedc9d791d547b_ext_009_regular/sequential：佯动 + intrusion。

## 哈希与保护范围

| 产物 | SHA256 |
|---|---|
| r2 模板 | ae691f11bc483e0d17636b6c5bf9dc755d0478c1c8c8a623e1dfc085f2b5f54b |
| r1 模板（未变） | 09ccf43753a04fc5557c42b07aa8b5e2cc66edb662bed868c94a1fafa7e1a5c4 |
| 两次 episodes.jsonl | 8b61df1ac4b5f8caf5db353c880edfa82599109a6d0854028c23cc121a923a71 |
| 两次 descriptions.jsonl | 9591c528535fa8a62a6584e943bef2f1478f942e041f2ee86e0b3988434240d0 |

逐条比较 r1/r2 的 60 条索引：仅 32 个编组 from_sector 和 16 个 slots.from_sector 值按批准规则增加“正”；其他全部字段（含锚点、划分、事实和引用）相同。
两次导出的 9 个 S3 源码指纹与收尾时一致；模板指纹一致。输入 manifest/registration 哈希与 r1 相同。
旧两个导出目录共 10 个文件的 SHA256 前后完全一致，详细清单在 S3_r2_gate.json。
原 S3 报告、准备文档和历史失败证据保持原样。相对生产起点 debfadf，既有文件无修改或删除。

## Q2 完整统计

单位为秒，各指标为中位数 / p90；成员级统计，episode 时长按成员加权，另列独立 episode 数。

| intent | mode | 成员 | episode | stop_hold | raw 末端等待 | 归一化末端可见 | 成员可见时长 | episode 长度 |
|---|---|---:|---:|---|---|---|---|---|
| feint | sequential | 46 | 6 | 1 | 142.350000 / 356.450000 | 1.000000 / 1.000000 | 1118.900000 / 1544.400000 | 1734.200000 / 2275.800000 |
| feint | synchronous | 46 | 6 | 1 | 2.300000 / 6.850000 | 1.000000 / 1.000000 | 1118.900000 / 1544.400000 | 1485.000000 / 1777.000000 |
| monitoring | sequential | 46 | 6 | 1 | 210.950000 / 707.150000 | 1.000000 / 1.000000 | 3083.300000 / 4651.050000 | 3618.400000 / 5319.800000 |
| monitoring | synchronous | 46 | 6 | 1 | 151.300000 / 734.600000 | 1.000000 / 1.000000 | 3083.300000 / 4651.100000 | 3460.200000 / 5222.900000 |
| penetration | sequential | 46 | 6 | 1 | 87.600000 / 247.050000 | 1.000000 / 1.000000 | 936.250000 / 1328.150000 | 1585.000000 / 3003.300000 |
| penetration | synchronous | 46 | 6 | 1 | 6.600000 / 74.950000 | 1.000000 / 1.000000 | 936.250000 / 1328.150000 | 1338.500000 / 2989.300000 |
| reconnaissance | sequential | 46 | 6 | 1 | 94.800000 / 289.800000 | 1.000000 / 1.000000 | 978.200000 / 1594.200000 | 1360.700000 / 2041.100000 |
| reconnaissance | synchronous | 46 | 6 | 1 | 4.900000 / 12.250000 | 1.000000 / 1.000000 | 978.200000 / 1594.200000 | 1167.000000 / 1674.300000 |
| transit | sequential | 46 | 6 | 1 | 96.550000 / 292.550000 | 1.000000 / 1.000000 | 907.950000 / 1713.250000 | 1261.600000 / 2396.100000 |
| transit | synchronous | 46 | 6 | 1 | 40.050000 / 116.100000 | 1.000000 / 1.000000 | 907.950000 / 1713.250000 | 1253.400000 / 1953.400000 |

## 范围与限制

仅描述完整 episode，不覆盖截断前缀；登记 5 个 family、实际保留 4 个，样本不足以评估划分或泛化能力。
释放前的帧保持遮挡，协调语义继续通过成员可见起点与共同时间轴保留。
没有写入第一批生产目录，没有读取第二批，没有运行规划、仿真、SITL 或训练。未合并、冻结或打标签。
工具修复额度使用 0/3。新样例按用户批准的三处修订生成，供本轮交付审阅。
