# v0.7 已知环境性测试失败

CL2 核对日期：2026-10-29（America/Los_Angeles）。只登记，不修代码、测试或数据。
T13/T14 只存在于 S3 一侧，production 基线没有这两项；CL1 的集合差异不构成合并回归证据。
在冻结 S3 de4d115 和合并结果 fba455a 上，使用同一 llm 环境、同一测试目录和模块入口，异常类型及信息逐字相同。

## test_T13_byte_identical_exports

异常类型：`task_v07.s3._common.RunNotReady`。

```text
Export already exists: D:\T2L\SwarmData\v07_first_edition_s3\s3_dev_f000_005_r2_repro01
```

## test_T14_real_multigroup_penetration

异常类型：`ValueError`。

```text
'D:\\T2L\\SwarmData\\v07_first_edition\\pilot_f000_005\\episodes\\family_s15_38bedc9d791d547b_ext_009_regular\\sequential' is not in the subpath of 'F:\\CASIA\\Drone Swarm Situational Awareness Algorithm\\SwarmData\\v07_first_edition'
```

T13：既有导出目录的防覆盖保护触发。T14：目录联接将路径解析为 D 盘后，无法对 F 盘逻辑根计算相对路径。
这两项登记为已知环境性测试失败；没有删除或重导既有结果，也没有更改路径比较逻辑。
本次仅复核这两项；不将其他历史失败重新标为通过。完整日志和逐字比较在 _handoff/2026-10-29_cleanup/out/cl2/ 下。
