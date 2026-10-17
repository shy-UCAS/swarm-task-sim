# FE-P2 A 组固定基线登记

状态：COMPLETE；完成 32/32。

算法基线：92068b95416a53d8e84a90488d06112d367f0c09；实际运行提交：e9715af44872adee98d7dd4ef3ff4a2658ce7d5d。

本报告仅登记 A 组；B 尚未执行。混合方法骨架同时出现在两种方法分层，不能相加分母。未完成不计为失败或零耗时。

## 骨架状态

| approach | 方法 | 登记 | 完成 | PASS |
|---|---|---|---|---|
| multi_direction | area_search | 11 | 11 | 2 |
| multi_direction | close_observation | 7 | 7 | 4 |
| multi_direction | ALL_RECONNAISSANCE | 15 | 15 | 6 |
| same_direction | area_search | 10 | 10 | 9 |
| same_direction | close_observation | 9 | 9 | 9 |
| same_direction | ALL_RECONNAISSANCE | 17 | 17 | 16 |

## 组提案

| approach/method | 完成骨架 | 合法候选 | 有效提案 |
|---|---|---|---|
| multi_direction/area_search | 11 | 104 | 2400 |
| multi_direction/close_observation | 7 | 1383 | 1400 |
| same_direction/area_search | 10 | 1532 | 2400 |
| same_direction/close_observation | 9 | 1715 | 1800 |

已核验合法候选原始整路线及 existing_precheck 合同：4734；异常 0。

## 时间与溯源

完成骨架规划时间分布（s）：{"count": 32, "min": 4.889323099996545, "p50": 41.42443035000906, "p90": 1303.9507265800044, "max": 2180.599047800002}
各 attempt 墙钟（s）：[2400.0629999999946, 2076.6870000000054]
未完成：[]
登记文件：F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_fe_p2_ab_20261017T105201Z\a_registration.json
描述符 SHA256：1e5e0be6332ee3edba613b024bf4ce2dfc7ba0271949860ed16fa7695782a128
固定清单 SHA256：4169d69be467c33ce6c9337382b2e5d2d4105d52f944ff6ee142f22b464b2d97
生产源码与配置共 140 个文件已核验匹配固定基线；每个 attempt 的 runtime 指纹稳定。原始结果的文件哈希、每组提案数、合法候选数和拒绝原因见同名 JSON。

- F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261017T105201Z；TIME_LIMIT_STOP
- F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData\v07_dataset\attempt_s15yield_20261017T113244Z；completed

本阶段没有修改生产算法或已有测试。新测试及 B 组须在 A 完整、基线回归通过并提交后继续。

## 修改前单元回归

FE-INT 原 15 模块 113/113 通过，无跳过；总墙钟 107.390 s，测试期间生产源码与配置哈希稳定。详细命令、日志和源码哈希见 p2_tests_before/regression.json。

本次固定 92068b9 的 A 组提案接受数与历史 S1.5 统计不同；本轮只以本次 A 组作为 B 的直接基线，历史比例不用于计算收益。
