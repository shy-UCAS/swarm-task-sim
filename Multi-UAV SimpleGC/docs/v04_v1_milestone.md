# v0.4 V1 里程碑：V01 预检失败，停止后续运行

日期：2026-10-01。结论：**WP-E 离线验收通过，但 V1 未通过、未完成。V01 在参数预检时失败，三机没有进入起飞步骤；已停止 V02–V05，未执行 V06。实际使用 SITL 预算 1/6 次。**

这是按停止规则提交的阶段报告，不是 V05 完成报告。没有修改飞控参数、质量阈值、停靠阈值、时间容忍量或覆盖几何来取得通过，也没有自动重试。当前参数比较策略仍保留失败时的原样。

## 1. WP-E 入口与实施结果

[WP-E 报告](v04_wp_e_milestone.md)记录 E1–E3 的实现、验收及兼容性说明。最终全量离线测试 **344/344 PASS**，原有测试 **150/150 PASS**；E01–E10、R01–R06 全部通过，证据为 `tmp_v04/wp_e/unit_test_results_final.json` 和 `offline_acceptance.json`。338 项中间测试记录保留，后续新增边界测试有独立最终记录。

已接通连续航线 schema 2、零长度段清理、100 点上限、时间感知间距、绑定、逐运行参数 TX 日志及固件指纹、阶段超时、no-op、航点事件、双通道第 7.5 节 arrival、v3 全流观测处理与四版本传播。v2 修改前后的真实分析结果可以混合导出和加载，具体验证器版本位于 `labels.json` 的 `label_provenance.validator_versions`。

这些离线 PASS 没有证明所有真实启动状态均已覆盖。V01 暴露了 E2 参数分类缺口，当前不能把生产可运行性判为通过。

## 2. 实际运行矩阵与预算

| 项目 | 计划 | 实际启动 | 结果 |
| --- | --- | --- | --- |
| V01 | 三机旧屏障模式，1 次 | 1 | FAIL：参数预检拒绝，未起飞 |
| V02 | 同场景连续模式，2 次 | 0 | NOT_RUN：已停止 |
| V03 | 两机北向剖分连续模式，1 次 | 0 | NOT_RUN：已停止 |
| V04 | 六机连续模式，1 次 | 0 | NOT_RUN：已停止 |
| V05 | 受控阶段超时，1 次 | 0 | NOT_RUN：未将 V01 普通预检失败冒充受控超时 |
| V06 | 十场景试生产 | 0 | 未获本轮授权 |

V01 的 run ID 为 `20261001T182936Z_6bca981d`。运行目录为 `verification/v04_v1_20261001/runs/recon_shared_demo_3uav_20261001T182936Z_6bca981d`；日志为 `verification/v04_v1_20261001/V01_r1.console.log`。运行器退出码 1，`status=failed`，`elapsed_s=12.3427537`。

三架 SITL 进程是同一次多机试验，因此预算记 1 次，不记 3 次；尽管未起飞，也不退还这次启动预算。`verification/v04_v1_20261001/records.json` 已写入 `stopped_reason`，后续调用受限运行脚本会拒绝继续。

## 3. 失败证据与根因判断

失败发生在约 12.26 s：`unexplained parameter readback differences require review/new WP-S GO: STAT_RESET`。两架飞机完成参数读回并发现差异，另一架因统一取消保留了部分读回。

| 参数证据 | 第一份已接受 WP-S | 第二份已接受 WP-S | 本次 V01 |
| --- | --- | --- | --- |
| STAT_RESET | 三机均 339262368 | 三机均 339262688 | uav_02、uav_03 均 339272992 |
| STAT_BOOTCNT | 1 | 1 | 完整读回两机均 1 |
| STAT_FLTTIME | 0 | 0 | 完整读回两机均 0 |
| STAT_RUNTIME | 0 | 0 | 完整读回两机均 0 |

本次 uav_02、uav_03 各完整读回 1202/1202 项；uav_01 的运行附件保留 1105/1202 项、缺 97 项，不能写成全机完整。只读复查其原始日志可见 1163/1202 个带索引参数，仍不完整，不能回写附件冒充运行时完成；其中 STAT_RESET 也为 339272992。已完整比较的两架飞机，除已声明的实例差异外，唯一触发门禁的字段为 STAT_RESET，WPNAV_* 没有变化。

官方 Copter 4.0.4 参数说明将 STAT_RESET 定义为从 2016-01-01 起计算的统计重置时间，并标记为只读。这一资料说明其参数类别；它不是对本地 dev 固件确切源码的替代。[官方参数说明](https://ardupilot.org/copter/docs/parameters-Copter-stable-V4.0.4.html#stat-reset-statistics-reset-time)

结合两次已接受 WP-S 自身的差异，我的判断是：**比较器未区分统计状态与固定飞行配置，因而错误要求 STAT_RESET 跨运行相等。** 本次没有证据表明导航参数改变，也不是固件或模板指纹变化导致的拒绝。不能通过改写历史 WP-S 参数表或直接把本次值设为新固定值来解决这个问题。

| 固定指纹 | 本次值 | 与 WP-S |
| --- | --- | --- |
| 固件版本 | ArduCopter V4.0.4-dev (de791682) | 一致；来自二进制元数据 |
| 固件 SHA256 | `0c0c1be702858dad5ed07e319efffda641cfc358423a65608ff949d3becc8532` | 一致 |
| 参数模板 SHA256 | `4f780ced6a47582cec2b66dfce7ce995f0ad20683e16909541f58b2837f1dee5` | 一致 |

## 4. 失败保留、分析与清理

没有 `flight_epoch_monotonic_s`、`mission_end_monotonic_s`，没有阶段飞行窗口。每机原始日志各 11 个心跳全部未解锁，relative_alt 全程为 0，事件无起飞或放行。metadata、原始遥测、参数附件、各请求发送前后时刻、事件、SITL 文件及失败分析均已保存。三架拥有的 SITL 子进程均结束，metadata 中退出码均为 1；这表示失败后结束，不能描述成正常任务降落成功。运行结束后复查没有仍在运行的 arducopter 进程。

生成的分析目录为 `analysis_v040-dev_20261001T182948Z_e7b7bad0`。`mission_success` 与 `mission_success_observation` 均为 null，`semantic_consistency=unknown`；`episode_quality_eligible`、`benchmark_eligible`、`strict_benchmark_eligible` 及 `usable` 均为 false。四个处理版本和具体验证器身份都有记录。

详细只读诊断为 `tmp_v04/wp_v/v01_preflight_diagnosis/diagnosis.json`：48 个输入文件前后哈希一致，manifest 的源与产物哈希、版本核对及 `load_episode` 均通过。可读取 \(124\times3\times6\) 的地面观测，掩码有效 232/372；它仍是不合格失败样本。`build_dataset` 仅验证到首个输出目录创建前，未实际复制导出数据集，不能将该检查称为完整导出成功。

起飞前地面观测仍可导出，但它们不能作为任务执行指标。自动核验报告中的地面覆盖下界、地面机间距离或部分观测停靠值，不属于 V01 飞行效果，更不能替代 V02–V04 的验收证据。

最新只读核验输出为 `tmp_v04/wp_v/stopped_after_v01_20261001_r02/v04_v1_verification.json` 和同名 Markdown。初版核验目录也保留。r02 表格明确区分尝试次数齐备与验收通过，并将没有任务飞行窗口的地面数值显示为 NOT_MEASURED；原值保留在 JSON。完整 V02–V04 矩阵的 AC1–AC6 均为 UNKNOWN，未将缺运行转换为 PASS；输入哈希前后不变。

## 5. 计划 8.3 的新旧模式对照

下表保留完整要求，缺测显式标记。V01 未形成任务飞行窗口，V02 未执行，因此当前没有可比较的飞行效果。

| 指标 | V01 旧屏障模式 | V02 连续模式第 1 次 | V02 连续模式第 2 次 |
| --- | --- | --- | --- |
| 每机停靠数 | NOT_MEASURED | NOT_RUN | NOT_RUN |
| 中间航点停靠率 | NOT_MEASURED | NOT_RUN | NOT_RUN |
| 全机同步停靠比例 | NOT_MEASURED | NOT_RUN | NOT_RUN |
| 静止时间占比 | NOT_MEASURED | NOT_RUN | NOT_RUN |
| 到达滞后 | NOT_MEASURED | NOT_RUN | NOT_RUN |
| 上传＋放行＋确认占比 | NOT_MEASURED | NOT_RUN | NOT_RUN |
| 任务跨度 | NOT_MEASURED | NOT_RUN | NOT_RUN |
| elapsed_s | 12.3427537，预检失败全过程 | NOT_RUN | NOT_RUN |
| 覆盖率：SIM / FCU | NOT_MEASURED / NOT_MEASURED | NOT_RUN | NOT_RUN |
| 真值最小机间距离 | NOT_MEASURED | NOT_RUN | NOT_RUN |

旧 barrier 产物本身不提供第 7.5 节 `arrival_s`。为后续有效 V01 补充了只读独立诊断 `scripts/v04_barrier_arrival_diagnostic.py`：按 FCU 轨迹和原始终点事件计算，写为 `report_only_arrival_lag_s`，不覆盖旧 `execution_metrics` 或窗口。本次全部 36 个阶段—飞机组合都保持 UNKNOWN，不能用阶段结束事件假造 arrival。两个手算正例和两个缺证据反例通过；证据位于 `tmp_v04/wp_v/barrier_arrival_helper_review_01/`。

## 6. 按扫描线长度分组的最低过点速度

要求口径为 FCU 水平速度、每个中间点 2 m 邻域的最小值，按完整规划扫描线长度分组，速度单位 m/s；不使用换线段长度。V03、V04 都未执行，不能生成真实分布。

| 场景 | 规划扫描线长度 | 已执行运行数 | 有效速度样本 / 实测点总数 | 未知数 | min / p10 / median / p90 / max |
| --- | --- | --- | --- | --- | --- |
| V03 两机北向 | 8 m | 0 | NOT_RUN | NOT_RUN | NOT_RUN |
| V04 六机 | 8 m | 0 | NOT_RUN | NOT_RUN | NOT_RUN |

这里的 8 m 来自待执行计划，只说明分组规则，不是实测结果。没有将尚未执行的规划点冒充实测分母，也没有用 0 m/s 表示缺测。诊断模块对完整扫描线与换线段的分组区别已有独立单元测试。

## 7. 下一步方案与暂停边界

本节只提出方案，本轮不实施、不续跑：

1. 将参数比较策略升级为独立版本，例如 `wp_s_parameter_comparison_v2`。为明确列出的统计状态参数保存原始值、差异、依据和分类，不再要求跨运行相等。先只处理已证实的 STAT_RESET，不能笼统忽略所有只读字段或所有 `STAT_*`。
2. 对导航/控制配置、WPNAV_*、参数集合与读取完整性继续严格核对；固件/模板 SHA256 门禁保留。未解释的其他变化继续阻止起飞。固件或模板实际变化仍必须重新 WP-S。
3. 加入历史两次 WP-S 与本次失败包的离线比较测试，覆盖“统计时间变化可解释、导航参数变化仍拒绝、部分读回绝不通过”，并记录新比较策略版本到 metadata/参数附件。不得将旧失败运行改成成功。
4. 经确认后重新执行有效 V01 对照，再继续完整 V02×2、V03、V04、V05。原预算已消耗 1 次，剩余 5 次不足以补齐这 6 次有效计划；若保留完整矩阵，需要确认追加 1 次预算，即本阶段累计上限从 6 调整为 7，或由用户重新指定验证矩阵。

当前已暂停。未对参数分类门禁做上述放宽，未追加 SITL，未开始 V06。历史保护最终检查为 **7,994 文件全部不变**，详见 `tmp_v04/wp_e/final_preservation.json`；原两份 UNKNOWN 报告及其运行目录、WP-S 复核和 GO、WP-G 里程碑均保留。
