# arrival_s 与阶段切换的只读诊断

版本：`arrival_brake_readonly_diagnostic_v1`。不改变 arrival_s、控制器、参数或任何验收判定。

末航点 NAV 驻留与外层几何确认是两个环节：前者配置 terminal_hold_s；后者在 1 m 三维容差内连续 confirmation_dwell_s，但均没有由 Python 检查速度。WPNAV_RADIUS 从实测参数读出。特别要区分配置的 NAV 驻留与固件实际 CMD 记录：本诊断逐阶段读取 BIN CMD 的 Prm1；末点事件不是内部计时器开始消息，不能仅凭配置假定固件实际驻留了相同时间。

下一阶段 upload() 先请求 BRAKE 并等待新 HEARTBEAT 确认，然后传航线；最终阶段直接 LAND。历史包未记录 SET_MODE TX，所以 upload_started/landing_started 到首个对应心跳仅是发送时刻的包含区间，心跳接收不是精确模式切换时刻。JSON另保留 BIN MODE 源时间及其被动映射时间，不能与精确TX混淆。

SIM 为原 BIN SIM 全生命周期源位置（已导出 truth_source.csv）的差分速度，FCU 为 GLOBAL_POSITION_INT 速度；沿原 v3 全流去重和时钟模型独立对齐到 10 Hz。连续低速仅作诊断：水平速度≤0.3 m/s、连续样本跨度≥0.2 s，缺样断开。记录低速区间起点与0.2 s证据完成时刻，前者可能在BRAKE而后者已跨入AUTO。它不等于三维静止，特别是 LAND 期间。原 arrival_s 仍只需单个距离/速度同时合格样本。

时间均为运行启动后的主机秒数。2 m 进入是采样区间估计；若 BIN CMD 与配置不一致，事件减配置驻留更不能解释为内部计时起点。数据只能检验时间关系，不能直接读取固件内部计时器或证明 BRAKE 是停止的唯一原因。

## V06 结论

10 次运行、每通道 99 个飞机×阶段窗口独立统计。阶段间窗口中，FCU 51/61、SIM 35/61 的首次连续水平低速开始于已确认 BRAKE、下一 AUTO 请求标记之前；SIM 的其他分类为 {'confirmed_BRAKE_before_next_AUTO': 35, 'after_next_AUTO_request_marker': 26}。这是低速区间的起点分类；≥0.2 s证据积累完成的分类另记在JSON，不能断言整段均处于BRAKE。这支持减速延续到阶段切换的解释，但不证明 BRAKE 是唯一原因。最终阶段分类为 FCU {'after_LAND_heartbeat_horizontal_only': 38}、SIM {'after_LAND_heartbeat_horizontal_only': 38}，不可称为BRAKE悬停或三维停稳。配置 terminal_hold_s=[0.5]，实际末 NAV CMD Prm1=[0.0]（缺失 0）。因此必须将配置驻留、机载CMD记录、外层1 m几何确认分开描述；不能断言进入2 m后真的计满配置的0.5 s。未改 arrival_s 或任何参数。

## V1_historical 结论

4 次运行、每通道 42 个飞机×阶段窗口独立统计。阶段间窗口中，FCU 28/28、SIM 18/28 的首次连续水平低速开始于已确认 BRAKE、下一 AUTO 请求标记之前；SIM 的其他分类为 {'confirmed_BRAKE_before_next_AUTO': 18, 'after_next_AUTO_request_marker': 10}。这是低速区间的起点分类；≥0.2 s证据积累完成的分类另记在JSON，不能断言整段均处于BRAKE。这支持减速延续到阶段切换的解释，但不证明 BRAKE 是唯一原因。最终阶段分类为 FCU {'after_LAND_heartbeat_horizontal_only': 14}、SIM {'after_LAND_heartbeat_horizontal_only': 14}，不可称为BRAKE悬停或三维停稳。配置 terminal_hold_s=[0.5]，实际末 NAV CMD Prm1=[0.0]（缺失 0）。因此必须将配置驻留、机载CMD记录、外层1 m几何确认分开描述；不能断言进入2 m后真的计满配置的0.5 s。未改 arrival_s 或任何参数。

## 20261002T092201Z_3bc79cde

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 9 | 5 | 0 | 5 |
| FCU | 9 | 3 | 0 | 3 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 60.700 | 60.706 | 61.695 | 61.699 | 61.723 | 62.219 | 62.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p00_approach | 60.600 | 60.706 | 61.695 | 61.699 | 61.723 | 62.219 | 62.200 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_01/p01_observe | 131.200 | 131.202 | 132.220 | 132.316 | 132.341 | 132.727 | 132.700 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p01_observe | 131.200 | 131.202 | 132.220 | 132.316 | 132.341 | 132.727 | 132.800 | after_next_AUTO_request_marker |
| FCU/uav_01/p02_return | 150.200 | 150.211 | 151.204 | 151.209 | 151.247 | — | 151.900 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p02_return | 150.100 | 150.211 | 151.204 | 151.209 | 151.247 | — | 152.000 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 60.600 | 60.577 | 61.632 | 61.699 | 61.738 | 62.219 | 62.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 60.500 | 60.577 | 61.632 | 61.699 | 61.738 | 62.219 | 62.200 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p01_observe | 131.100 | 131.033 | 132.219 | 132.316 | 132.324 | 132.727 | 132.700 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p01_observe | 131.000 | 131.033 | 132.219 | 132.316 | 132.324 | 132.727 | 132.700 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p02_return | 150.100 | 150.098 | 151.189 | 151.209 | 151.217 | — | 151.900 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p02_return | 150.100 | 150.098 | 151.189 | 151.209 | 151.217 | — | 152.000 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_03/p00_approach | 60.600 | 60.558 | 61.585 | 61.699 | 61.707 | 62.219 | 62.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p00_approach | 60.500 | 60.558 | 61.585 | 61.699 | 61.707 | 62.219 | 62.100 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_03/p01_observe | 131.300 | 131.251 | 132.310 | 132.316 | 132.339 | 132.727 | 132.700 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p01_observe | 131.200 | 131.251 | 132.310 | 132.316 | 132.339 | 132.727 | 132.800 | after_next_AUTO_request_marker |
| FCU/uav_03/p02_return | 150.100 | 150.128 | 151.067 | 151.209 | 151.218 | — | 151.800 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_03/p02_return | 150.100 | 150.128 | 151.067 | 151.209 | 151.218 | — | 151.900 | after_LAND_heartbeat_horizontal_only |

## 20261002T092554Z_f5457bbb

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 6 | 5 | 0 | 5 |
| FCU | 6 | 4 | 0 | 2 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 59.000 | 58.979 | 59.991 | 59.996 | 60.021 | 60.516 | 60.400 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p00_approach | 58.900 | 58.979 | 59.991 | 59.996 | 60.021 | 60.516 | 60.500 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_01/p01_observe | 79.100 | 79.061 | 80.211 | 80.216 | 80.239 | 80.624 | 80.600 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p01_observe | 79.000 | 79.061 | 80.211 | 80.216 | 80.239 | 80.624 | 80.700 | after_next_AUTO_request_marker |
| FCU/uav_01/p02_return | 89.600 | 89.475 | 90.773 | 90.778 | 90.803 | — | 91.300 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p02_return | 89.500 | 89.475 | 90.773 | 90.778 | 90.803 | — | 91.200 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 59.000 | 58.918 | 59.991 | 59.996 | 60.022 | 60.516 | 60.500 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 58.900 | 58.918 | 59.991 | 59.996 | 60.022 | 60.516 | 60.600 | after_next_AUTO_request_marker |
| FCU/uav_02/p01_observe | 79.100 | 79.137 | 80.210 | 80.216 | 80.238 | 80.624 | 80.600 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p01_observe | 79.000 | 79.137 | 80.210 | 80.216 | 80.238 | 80.624 | 80.700 | after_next_AUTO_request_marker |
| FCU/uav_02/p02_return | 89.700 | 89.521 | 90.774 | 90.778 | 90.803 | — | 91.200 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p02_return | 89.600 | 89.521 | 90.774 | 90.778 | 90.803 | — | 91.200 | after_LAND_heartbeat_horizontal_only |

## 20261002T092830Z_f3b2d69b

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 18 | 12 | 0 | 12 |
| FCU | 18 | 6 | 0 | 7 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 60.500 | 60.394 | 61.556 | 61.652 | 61.657 | 62.105 | 62.000 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p00_approach | 60.400 | 60.394 | 61.556 | 61.652 | 61.657 | 62.105 | 62.000 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_01/p01_observe | 80.800 | 80.758 | 81.904 | 81.910 | 81.929 | 82.329 | 82.300 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p01_observe | 80.700 | 80.758 | 81.904 | 81.910 | 81.929 | 82.329 | 82.300 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_01/p02_return | 91.300 | 91.309 | 92.444 | 92.494 | 92.506 | — | 93.100 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p02_return | 91.300 | 91.309 | 92.444 | 92.494 | 92.506 | — | 93.100 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 60.500 | 60.500 | 61.476 | 61.652 | 61.658 | 62.104 | 62.000 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 60.400 | 60.500 | 61.476 | 61.652 | 61.658 | 62.104 | 62.000 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p01_observe | 80.800 | 80.833 | 81.766 | 81.910 | 81.937 | 82.329 | 82.300 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p01_observe | 80.800 | 80.833 | 81.766 | 81.910 | 81.937 | 82.329 | 82.400 | after_next_AUTO_request_marker |
| FCU/uav_02/p02_return | 91.200 | 91.220 | 92.349 | 92.494 | 92.506 | — | 93.000 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p02_return | 91.200 | 91.220 | 92.349 | 92.494 | 92.506 | — | 93.100 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_03/p00_approach | 60.500 | 60.519 | 61.555 | 61.652 | 61.689 | 62.104 | 62.000 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p00_approach | 60.400 | 60.519 | 61.555 | 61.652 | 61.689 | 62.104 | 62.100 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_03/p01_observe | 80.800 | 80.772 | 81.766 | 81.910 | 81.931 | 82.329 | 82.300 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p01_observe | 80.700 | 80.772 | 81.766 | 81.910 | 81.931 | 82.329 | 82.400 | after_next_AUTO_request_marker |
| FCU/uav_03/p02_return | 91.200 | 91.155 | 92.302 | 92.494 | 92.522 | — | 93.000 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_03/p02_return | 91.100 | 91.155 | 92.302 | 92.494 | 92.522 | — | 93.100 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_04/p00_approach | 60.500 | 60.352 | 61.522 | 61.652 | 61.657 | 62.104 | 62.000 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_04/p00_approach | 60.400 | 60.352 | 61.522 | 61.652 | 61.657 | 62.104 | 62.000 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_04/p01_observe | 80.600 | 80.573 | 81.735 | 81.910 | 81.914 | 82.329 | 82.200 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_04/p01_observe | 80.500 | 80.573 | 81.735 | 81.910 | 81.914 | 82.329 | 82.200 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_04/p02_return | 91.300 | 91.293 | 92.317 | 92.495 | 92.506 | — | 93.000 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_04/p02_return | 91.300 | 91.293 | 92.317 | 92.495 | 92.506 | — | 93.000 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_05/p00_approach | 60.500 | 60.380 | 61.462 | 61.652 | 61.673 | 62.104 | 62.000 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_05/p00_approach | 60.400 | 60.380 | 61.462 | 61.652 | 61.673 | 62.104 | 62.100 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_05/p01_observe | 80.800 | 80.791 | 81.795 | 81.910 | 81.914 | 82.329 | 82.300 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_05/p01_observe | 80.700 | 80.791 | 81.795 | 81.910 | 81.914 | 82.329 | 82.300 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_05/p02_return | 91.300 | 91.326 | 92.458 | 92.495 | 92.520 | — | 93.100 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_05/p02_return | 91.300 | 91.326 | 92.458 | 92.495 | 92.520 | — | 93.200 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_06/p00_approach | 60.500 | 60.517 | 61.646 | 61.652 | 61.673 | 62.104 | 62.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_06/p00_approach | 60.500 | 60.517 | 61.646 | 61.652 | 61.673 | 62.104 | 62.100 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_06/p01_observe | 80.800 | 80.756 | 81.811 | 81.910 | 81.932 | 82.329 | 82.300 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_06/p01_observe | 80.700 | 80.756 | 81.811 | 81.910 | 81.932 | 82.329 | 82.400 | after_next_AUTO_request_marker |
| FCU/uav_06/p02_return | 91.300 | 91.278 | 92.489 | 92.495 | 92.522 | — | 93.100 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_06/p02_return | 91.200 | 91.278 | 92.489 | 92.495 | 92.522 | — | 93.200 | after_LAND_heartbeat_horizontal_only |

## 20261002T100745Z_a5b07d89

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 12 | 6 | 0 | 6 |
| FCU | 12 | 6 | 0 | 6 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 61.500 | 61.469 | 62.743 | 62.748 | 62.769 | 63.248 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p00_approach | 61.400 | 61.469 | 62.743 | 62.748 | 62.769 | 63.248 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_01/p01_observe | 92.900 | 92.820 | 93.989 | 94.090 | 94.116 | — | 94.700 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p01_observe | 92.800 | 92.820 | 93.989 | 94.090 | 94.116 | — | 94.700 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 61.600 | 61.506 | 62.696 | 62.748 | 62.755 | 63.248 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 61.500 | 61.506 | 62.696 | 62.748 | 62.755 | 63.248 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p01_observe | 92.900 | 92.820 | 94.020 | 94.090 | 94.100 | — | 94.800 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p01_observe | 92.800 | 92.820 | 94.020 | 94.090 | 94.100 | — | 94.800 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_03/p00_approach | 61.600 | 61.609 | 62.711 | 62.749 | 62.773 | 63.248 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p00_approach | 61.500 | 61.609 | 62.711 | 62.749 | 62.773 | 63.248 | 63.200 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_03/p01_observe | 92.900 | 92.893 | 93.915 | 94.090 | 94.099 | — | 94.700 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_03/p01_observe | 92.900 | 92.893 | 93.915 | 94.090 | 94.099 | — | 94.700 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_04/p00_approach | 61.500 | 61.539 | 62.633 | 62.749 | 62.770 | 63.248 | 63.200 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_04/p00_approach | 61.500 | 61.539 | 62.633 | 62.749 | 62.770 | 63.248 | 63.200 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_04/p01_observe | 93.000 | 92.929 | 94.004 | 94.090 | 94.097 | — | 94.700 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_04/p01_observe | 92.900 | 92.929 | 94.004 | 94.090 | 94.097 | — | 94.800 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_05/p00_approach | 61.500 | 61.438 | 62.726 | 62.749 | 62.753 | 63.248 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_05/p00_approach | 61.400 | 61.438 | 62.726 | 62.749 | 62.753 | 63.248 | 63.200 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_05/p01_observe | 92.900 | 92.795 | 94.083 | 94.090 | 94.115 | — | 94.800 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_05/p01_observe | 92.800 | 92.795 | 94.083 | 94.090 | 94.115 | — | 94.900 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_06/p00_approach | 61.500 | 61.454 | 62.698 | 62.749 | 62.755 | 63.248 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_06/p00_approach | 61.400 | 61.454 | 62.698 | 62.749 | 62.755 | 63.248 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_06/p01_observe | 93.000 | 92.909 | 94.005 | 94.090 | 94.113 | — | 94.700 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_06/p01_observe | 92.900 | 92.909 | 94.005 | 94.090 | 94.113 | — | 94.800 | after_LAND_heartbeat_horizontal_only |

## 20261002T095856Z_e433af1b

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 6 | 3 | 0 | 3 |
| FCU | 6 | 3 | 0 | 3 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 63.700 | 63.688 | 64.737 | 64.861 | 64.890 | 65.365 | 65.200 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p00_approach | 63.700 | 63.688 | 64.737 | 64.861 | 64.890 | 65.365 | 65.300 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_01/p01_observe | 93.800 | 93.647 | 94.870 | 94.874 | 94.916 | — | 95.500 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p01_observe | 93.700 | 93.647 | 94.870 | 94.874 | 94.916 | — | 95.600 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 63.700 | 63.719 | 64.753 | 64.861 | 64.888 | 65.365 | 65.300 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 63.700 | 63.719 | 64.753 | 64.861 | 64.888 | 65.365 | 65.300 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p01_observe | 93.800 | 93.754 | 94.839 | 94.874 | 94.917 | — | 95.500 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p01_observe | 93.700 | 93.754 | 94.839 | 94.874 | 94.917 | — | 95.500 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_03/p00_approach | 63.800 | 63.725 | 64.846 | 64.861 | 64.873 | 65.365 | 65.200 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p00_approach | 63.700 | 63.725 | 64.846 | 64.861 | 64.873 | 65.365 | 65.300 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_03/p01_observe | 93.600 | 93.539 | 94.668 | 94.874 | 94.885 | — | 95.300 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_03/p01_observe | 93.500 | 93.539 | 94.668 | 94.874 | 94.885 | — | 95.400 | after_LAND_heartbeat_horizontal_only |

## 20261002T101847Z_8e82a878

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 6 | 6 | 0 | 6 |
| FCU | 6 | 3 | 0 | 3 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 60.600 | 60.639 | 61.674 | 61.709 | 61.735 | 62.173 | 62.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p00_approach | 60.500 | 60.639 | 61.674 | 61.709 | 61.735 | 62.173 | 62.200 | after_next_AUTO_request_marker |
| FCU/uav_01/p01_observe | 90.300 | 90.236 | 91.461 | 91.667 | 91.678 | — | 92.100 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p01_observe | 90.300 | 90.236 | 91.461 | 91.667 | 91.678 | — | 92.200 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 60.700 | 60.734 | 61.659 | 61.709 | 61.719 | 62.173 | 62.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 60.600 | 60.734 | 61.659 | 61.709 | 61.719 | 62.173 | 62.200 | after_next_AUTO_request_marker |
| FCU/uav_02/p01_observe | 90.500 | 90.412 | 91.601 | 91.667 | 91.694 | — | 92.300 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p01_observe | 90.500 | 90.412 | 91.601 | 91.667 | 91.694 | — | 92.300 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_03/p00_approach | 60.600 | 60.612 | 61.705 | 61.709 | 61.733 | 62.173 | 62.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p00_approach | 60.600 | 60.612 | 61.705 | 61.709 | 61.733 | 62.173 | 62.200 | after_next_AUTO_request_marker |
| FCU/uav_03/p01_observe | 90.500 | 90.443 | 91.663 | 91.667 | 91.709 | — | 92.300 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_03/p01_observe | 90.500 | 90.443 | 91.663 | 91.667 | 91.709 | — | 92.400 | after_LAND_heartbeat_horizontal_only |

## 20261002T101634Z_be00cea9

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 9 | 8 | 0 | 8 |
| FCU | 9 | 5 | 0 | 5 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 61.500 | 61.649 | 62.565 | 62.613 | 62.637 | 63.055 | 63.100 | after_next_AUTO_request_marker |
| SIM/uav_01/p00_approach | 61.400 | 61.649 | 62.565 | 62.613 | 62.637 | 63.055 | 63.200 | after_next_AUTO_request_marker |
| FCU/uav_01/p01_observe | 93.800 | 93.837 | 94.912 | 94.961 | 94.991 | 95.437 | 95.400 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p01_observe | 93.700 | 93.837 | 94.912 | 94.961 | 94.991 | 95.437 | 95.500 | after_next_AUTO_request_marker |
| FCU/uav_01/p02_return | 104.700 | 104.777 | 105.769 | 105.991 | 106.004 | — | 106.500 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p02_return | 104.600 | 104.777 | 105.769 | 105.991 | 106.004 | — | 106.600 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 61.500 | 61.600 | 62.609 | 62.614 | 62.638 | 63.055 | 63.000 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 61.500 | 61.600 | 62.609 | 62.614 | 62.638 | 63.055 | 63.100 | after_next_AUTO_request_marker |
| FCU/uav_02/p01_observe | 93.900 | 93.948 | 94.910 | 94.961 | 94.988 | 95.437 | 95.400 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p01_observe | 93.800 | 93.948 | 94.910 | 94.961 | 94.988 | 95.437 | 95.500 | after_next_AUTO_request_marker |
| FCU/uav_02/p02_return | 104.800 | 104.837 | 105.988 | 105.991 | 106.018 | — | 106.500 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p02_return | 104.700 | 104.837 | 105.988 | 105.991 | 106.018 | — | 106.600 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_03/p00_approach | 61.500 | 61.691 | 62.564 | 62.614 | 62.622 | 63.055 | 63.100 | after_next_AUTO_request_marker |
| SIM/uav_03/p00_approach | 61.500 | 61.691 | 62.564 | 62.614 | 62.622 | 63.055 | 63.200 | after_next_AUTO_request_marker |
| FCU/uav_03/p01_observe | 93.800 | 93.888 | 94.957 | 94.961 | 94.986 | 95.437 | 95.400 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p01_observe | 93.800 | 93.888 | 94.957 | 94.961 | 94.986 | 95.437 | 95.400 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_03/p02_return | 104.700 | 104.788 | 105.831 | 105.992 | 106.003 | — | 106.500 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_03/p02_return | 104.600 | 104.788 | 105.831 | 105.992 | 106.003 | — | 106.600 | after_LAND_heartbeat_horizontal_only |

## 20261002T100525Z_aafb58d3

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 18 | 12 | 0 | 16 |
| FCU | 18 | 8 | 0 | 9 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 61.100 | 61.229 | 62.305 | 62.497 | 62.504 | 63.005 | 62.800 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p00_approach | 61.000 | 61.229 | 62.305 | 62.497 | 62.504 | 63.005 | 62.900 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_01/p01_observe | 95.900 | 95.907 | 96.982 | 97.048 | 97.077 | 97.493 | 97.400 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p01_observe | 95.800 | 95.907 | 96.982 | 97.048 | 97.077 | 97.493 | 97.500 | after_next_AUTO_request_marker |
| FCU/uav_01/p02_return | 105.500 | 105.638 | 106.427 | 106.573 | 106.583 | — | 107.200 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p02_return | 105.400 | 105.638 | 106.427 | 106.573 | 106.583 | — | 107.300 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 61.400 | 61.559 | 62.492 | 62.497 | 62.520 | 63.005 | 62.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 61.300 | 61.559 | 62.492 | 62.497 | 62.520 | 63.005 | 63.000 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p01_observe | 95.900 | 95.905 | 97.042 | 97.048 | 97.086 | 97.494 | 97.500 | after_next_AUTO_request_marker |
| SIM/uav_02/p01_observe | 95.800 | 95.905 | 97.042 | 97.048 | 97.086 | 97.494 | 97.600 | after_next_AUTO_request_marker |
| FCU/uav_02/p02_return | 105.300 | 105.427 | 106.275 | 106.573 | 106.584 | — | 107.100 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p02_return | 105.200 | 105.427 | 106.275 | 106.573 | 106.584 | — | 107.200 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_03/p00_approach | 61.200 | 61.405 | 62.259 | 62.497 | 62.506 | 63.005 | 62.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p00_approach | 61.200 | 61.405 | 62.259 | 62.497 | 62.506 | 63.005 | 62.900 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_03/p01_observe | 95.800 | 95.832 | 96.937 | 97.048 | 97.071 | 97.494 | 97.500 | after_next_AUTO_request_marker |
| SIM/uav_03/p01_observe | 95.800 | 95.832 | 96.937 | 97.048 | 97.071 | 97.494 | 97.500 | after_next_AUTO_request_marker |
| FCU/uav_03/p02_return | 105.300 | 105.501 | 106.318 | 106.573 | 106.582 | — | 107.200 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_03/p02_return | 105.300 | 105.501 | 106.318 | 106.573 | 106.582 | — | 107.300 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_04/p00_approach | 61.300 | 61.449 | 62.446 | 62.497 | 62.522 | 63.005 | 62.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_04/p00_approach | 61.200 | 61.449 | 62.446 | 62.497 | 62.522 | 63.005 | 63.000 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_04/p01_observe | 95.900 | 95.909 | 97.027 | 97.048 | 97.056 | 97.494 | 97.400 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_04/p01_observe | 95.900 | 95.909 | 97.027 | 97.048 | 97.056 | 97.494 | 97.500 | after_next_AUTO_request_marker |
| FCU/uav_04/p02_return | 105.500 | 105.669 | 106.568 | 106.573 | 106.597 | — | 107.200 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_04/p02_return | 105.400 | 105.669 | 106.568 | 106.573 | 106.597 | — | 107.400 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_05/p00_approach | 61.200 | 61.294 | 62.477 | 62.498 | 62.504 | 63.005 | 62.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_05/p00_approach | 61.100 | 61.294 | 62.477 | 62.498 | 62.504 | 63.005 | 63.000 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_05/p01_observe | 95.800 | 95.846 | 96.926 | 97.048 | 97.089 | 97.494 | 97.400 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_05/p01_observe | 95.800 | 95.846 | 96.926 | 97.048 | 97.089 | 97.494 | 97.500 | after_next_AUTO_request_marker |
| FCU/uav_05/p02_return | 105.400 | 105.620 | 106.476 | 106.573 | 106.597 | — | 107.200 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_05/p02_return | 105.300 | 105.620 | 106.476 | 106.573 | 106.597 | — | 107.400 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_06/p00_approach | 61.200 | 61.330 | 62.415 | 62.498 | 62.520 | 63.005 | 62.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_06/p00_approach | 61.100 | 61.330 | 62.415 | 62.498 | 62.520 | 63.005 | 63.000 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_06/p01_observe | 96.000 | 95.952 | 96.997 | 97.048 | 97.088 | 97.494 | 97.500 | after_next_AUTO_request_marker |
| SIM/uav_06/p01_observe | 95.900 | 95.952 | 96.997 | 97.048 | 97.088 | 97.494 | 97.600 | after_next_AUTO_request_marker |
| FCU/uav_06/p02_return | 105.400 | 105.525 | 106.397 | 106.574 | 106.582 | — | 107.200 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_06/p02_return | 105.300 | 105.525 | 106.397 | 106.574 | 106.582 | — | 107.400 | after_LAND_heartbeat_horizontal_only |

## 20261002T101406Z_651c7540

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 18 | 9 | 0 | 10 |
| FCU | 18 | 7 | 0 | 6 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 66.400 | 66.342 | 67.333 | 67.496 | 67.519 | 67.995 | 67.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p00_approach | 66.300 | 66.342 | 67.333 | 67.496 | 67.519 | 67.995 | 68.000 | after_next_AUTO_request_marker |
| FCU/uav_01/p01_observe | 99.200 | 99.103 | 100.190 | 100.255 | 100.266 | 100.728 | 100.600 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p01_observe | 99.100 | 99.103 | 100.190 | 100.255 | 100.266 | 100.728 | 100.700 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_01/p02_return | 112.800 | 112.838 | 113.869 | 113.936 | 113.945 | — | 114.600 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p02_return | 112.700 | 112.838 | 113.869 | 113.936 | 113.945 | — | 114.700 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 66.500 | 66.435 | 67.489 | 67.496 | 67.519 | 67.980 | 67.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 66.400 | 66.435 | 67.489 | 67.496 | 67.519 | 67.980 | 67.900 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p01_observe | 99.200 | 99.135 | 100.190 | 100.255 | 100.266 | 100.728 | 100.700 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p01_observe | 99.100 | 99.135 | 100.190 | 100.255 | 100.266 | 100.728 | 100.700 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p02_return | 112.800 | 112.836 | 113.776 | 113.937 | 113.944 | — | 114.600 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p02_return | 112.800 | 112.836 | 113.776 | 113.937 | 113.944 | — | 114.600 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_03/p00_approach | 66.300 | 66.244 | 67.380 | 67.496 | 67.521 | 67.995 | 67.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p00_approach | 66.200 | 66.244 | 67.380 | 67.496 | 67.521 | 67.995 | 67.900 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_03/p01_observe | 99.200 | 99.117 | 100.174 | 100.255 | 100.265 | 100.728 | 100.600 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p01_observe | 99.100 | 99.117 | 100.174 | 100.255 | 100.265 | 100.728 | 100.700 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_03/p02_return | 112.900 | 112.983 | 113.841 | 113.937 | 113.962 | — | 114.700 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_03/p02_return | 112.900 | 112.983 | 113.841 | 113.937 | 113.962 | — | 114.800 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_04/p00_approach | 66.500 | 66.387 | 67.441 | 67.496 | 67.500 | 67.995 | 67.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_04/p00_approach | 66.400 | 66.387 | 67.441 | 67.496 | 67.500 | 67.995 | 68.000 | after_next_AUTO_request_marker |
| FCU/uav_04/p01_observe | 99.200 | 99.149 | 100.235 | 100.255 | 100.268 | 100.728 | 100.700 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_04/p01_observe | 99.100 | 99.149 | 100.235 | 100.255 | 100.268 | 100.728 | 100.700 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_04/p02_return | 112.800 | 112.795 | 113.883 | 113.937 | 113.959 | — | 114.700 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_04/p02_return | 112.700 | 112.795 | 113.883 | 113.937 | 113.959 | — | 114.800 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_05/p00_approach | 66.400 | 66.318 | 67.458 | 67.497 | 67.518 | 67.995 | 67.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_05/p00_approach | 66.300 | 66.318 | 67.458 | 67.497 | 67.518 | 67.995 | 67.900 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_05/p01_observe | 99.200 | 99.101 | 100.251 | 100.255 | 100.282 | 100.728 | 100.700 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_05/p01_observe | 99.100 | 99.101 | 100.251 | 100.255 | 100.282 | 100.728 | 100.800 | after_next_AUTO_request_marker |
| FCU/uav_05/p02_return | 112.800 | 112.816 | 113.852 | 113.937 | 113.945 | — | 114.500 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_05/p02_return | 112.700 | 112.816 | 113.852 | 113.937 | 113.945 | — | 114.600 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_06/p00_approach | 66.400 | 66.358 | 67.425 | 67.497 | 67.515 | 67.980 | 67.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_06/p00_approach | 66.400 | 66.358 | 67.425 | 67.497 | 67.515 | 67.980 | 68.000 | after_next_AUTO_request_marker |
| FCU/uav_06/p01_observe | 99.200 | 99.085 | 100.160 | 100.255 | 100.281 | 100.729 | 100.700 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_06/p01_observe | 99.100 | 99.085 | 100.160 | 100.255 | 100.281 | 100.729 | 100.700 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_06/p02_return | 112.900 | 112.966 | 113.930 | 113.937 | 113.960 | — | 114.600 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_06/p02_return | 112.900 | 112.966 | 113.930 | 113.937 | 113.960 | — | 114.700 | after_LAND_heartbeat_horizontal_only |

## 20261002T100117Z_eb83bd70

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 6 | 3 | 0 | 4 |
| FCU | 6 | 2 | 0 | 2 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 62.600 | 62.543 | 63.682 | 63.685 | 63.709 | 64.172 | 64.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p00_approach | 62.600 | 62.543 | 63.682 | 63.685 | 63.709 | 64.172 | 64.100 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_01/p01_observe | 90.700 | 90.549 | 91.845 | 91.849 | 91.876 | 92.290 | 92.200 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p01_observe | 90.600 | 90.549 | 91.845 | 91.849 | 91.876 | 92.290 | 92.300 | after_next_AUTO_request_marker |
| FCU/uav_01/p02_return | 101.900 | 101.926 | 102.945 | 102.994 | 103.035 | — | 103.700 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p02_return | 101.800 | 101.926 | 102.945 | 102.994 | 103.035 | — | 103.800 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 62.600 | 62.515 | 63.649 | 63.685 | 63.710 | 64.172 | 64.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 62.600 | 62.515 | 63.649 | 63.685 | 63.710 | 64.172 | 64.200 | after_next_AUTO_request_marker |
| FCU/uav_02/p01_observe | 90.700 | 90.508 | 91.722 | 91.849 | 91.875 | 92.290 | 92.200 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p01_observe | 90.600 | 90.508 | 91.722 | 91.849 | 91.875 | 92.290 | 92.200 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p02_return | 102.000 | 101.973 | 102.990 | 102.994 | 103.020 | — | 103.800 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p02_return | 101.900 | 101.973 | 102.990 | 102.994 | 103.020 | — | 103.800 | after_LAND_heartbeat_horizontal_only |

## 20261002T101201Z_c87994ef

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 9 | 6 | 0 | 7 |
| FCU | 9 | 3 | 0 | 5 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 61.900 | 61.783 | 62.935 | 62.939 | 62.971 | 63.506 | 63.400 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p00_approach | 61.800 | 61.783 | 62.935 | 62.939 | 62.971 | 63.506 | 63.400 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_01/p01_observe | 87.500 | 87.372 | 88.379 | 88.568 | 88.591 | 88.977 | 89.000 | after_next_AUTO_request_marker |
| SIM/uav_01/p01_observe | 87.400 | 87.372 | 88.379 | 88.568 | 88.591 | 88.977 | 89.000 | after_next_AUTO_request_marker |
| FCU/uav_01/p02_return | 97.900 | 97.955 | 98.859 | 98.865 | 98.892 | — | 99.600 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p02_return | 97.800 | 97.955 | 98.859 | 98.865 | 98.892 | — | 99.700 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 61.900 | 61.768 | 62.842 | 62.939 | 62.972 | 63.506 | 63.300 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 61.800 | 61.768 | 62.842 | 62.939 | 62.972 | 63.506 | 63.300 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p01_observe | 87.400 | 87.258 | 88.438 | 88.568 | 88.592 | 88.977 | 88.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p01_observe | 87.300 | 87.258 | 88.438 | 88.568 | 88.592 | 88.977 | 89.000 | after_next_AUTO_request_marker |
| FCU/uav_02/p02_return | 97.700 | 97.754 | 98.689 | 98.865 | 98.874 | — | 99.500 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p02_return | 97.700 | 97.754 | 98.689 | 98.865 | 98.874 | — | 99.600 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_03/p00_approach | 61.900 | 61.827 | 62.796 | 62.939 | 62.972 | 63.506 | 63.300 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p00_approach | 61.800 | 61.827 | 62.796 | 62.939 | 62.972 | 63.506 | 63.500 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_03/p01_observe | 87.500 | 87.408 | 88.562 | 88.568 | 88.606 | 88.977 | 89.000 | after_next_AUTO_request_marker |
| SIM/uav_03/p01_observe | 87.400 | 87.408 | 88.562 | 88.568 | 88.606 | 88.977 | 89.100 | after_next_AUTO_request_marker |
| FCU/uav_03/p02_return | 97.900 | 97.938 | 98.860 | 98.865 | 98.890 | — | 99.600 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_03/p02_return | 97.800 | 97.938 | 98.860 | 98.865 | 98.890 | — | 99.700 | after_LAND_heartbeat_horizontal_only |

## 20261002T100951Z_be922ea7

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 9 | 6 | 0 | 6 |
| FCU | 9 | 4 | 0 | 6 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 59.200 | 59.231 | 60.366 | 60.371 | 60.397 | 60.866 | 60.900 | after_next_AUTO_request_marker |
| SIM/uav_01/p00_approach | 59.100 | 59.231 | 60.366 | 60.371 | 60.397 | 60.866 | 60.900 | after_next_AUTO_request_marker |
| FCU/uav_01/p01_observe | 93.500 | 93.444 | 94.567 | 94.573 | 94.612 | 94.970 | 95.000 | after_next_AUTO_request_marker |
| SIM/uav_01/p01_observe | 93.400 | 93.444 | 94.567 | 94.573 | 94.612 | 94.970 | 95.100 | after_next_AUTO_request_marker |
| FCU/uav_01/p02_return | 101.900 | 101.827 | 103.028 | 103.031 | 103.059 | — | 103.600 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p02_return | 101.800 | 101.827 | 103.028 | 103.031 | 103.059 | — | 103.700 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 59.200 | 59.122 | 60.337 | 60.371 | 60.379 | 60.866 | 60.800 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 59.100 | 59.122 | 60.337 | 60.371 | 60.379 | 60.866 | 60.800 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p01_observe | 93.200 | 93.149 | 94.269 | 94.573 | 94.598 | 94.970 | 94.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p01_observe | 93.100 | 93.149 | 94.269 | 94.573 | 94.598 | 94.970 | 94.900 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p02_return | 101.900 | 101.847 | 102.890 | 103.031 | 103.058 | — | 103.700 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p02_return | 101.800 | 101.847 | 102.890 | 103.031 | 103.058 | — | 103.700 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_03/p00_approach | 59.200 | 59.107 | 60.151 | 60.371 | 60.396 | 60.866 | 60.700 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p00_approach | 59.100 | 59.107 | 60.151 | 60.371 | 60.396 | 60.866 | 60.700 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_03/p01_observe | 93.300 | 93.290 | 94.460 | 94.573 | 94.597 | 94.970 | 95.000 | after_next_AUTO_request_marker |
| SIM/uav_03/p01_observe | 93.300 | 93.290 | 94.460 | 94.573 | 94.597 | 94.970 | 95.000 | after_next_AUTO_request_marker |
| FCU/uav_03/p02_return | 101.800 | 101.688 | 102.890 | 103.032 | 103.073 | — | 103.500 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_03/p02_return | 101.700 | 101.688 | 102.890 | 103.032 | 103.073 | — | 103.600 | after_LAND_heartbeat_horizontal_only |

## 20261002T100325Z_6ef00e4e

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 6 | 3 | 0 | 3 |
| FCU | 6 | 3 | 0 | 3 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 61.400 | 61.516 | 62.685 | 62.689 | 62.712 | 63.186 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p00_approach | 61.400 | 61.516 | 62.685 | 62.689 | 62.712 | 63.186 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_01/p01_observe | 92.700 | 92.815 | 93.877 | 94.208 | 94.219 | — | 94.500 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p01_observe | 92.600 | 92.815 | 93.877 | 94.208 | 94.219 | — | 94.600 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 61.500 | 61.564 | 62.514 | 62.689 | 62.728 | 63.186 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 61.400 | 61.564 | 62.514 | 62.689 | 62.728 | 63.186 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p01_observe | 93.200 | 93.284 | 94.204 | 94.208 | 94.234 | — | 95.000 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p01_observe | 93.100 | 93.284 | 94.204 | 94.208 | 94.234 | — | 95.200 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_03/p00_approach | 61.500 | 61.547 | 62.575 | 62.689 | 62.697 | 63.186 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p00_approach | 61.400 | 61.547 | 62.575 | 62.689 | 62.697 | 63.186 | 63.100 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_03/p01_observe | 92.600 | 92.753 | 93.832 | 94.208 | 94.233 | — | 94.500 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_03/p01_observe | 92.600 | 92.753 | 93.832 | 94.208 | 94.233 | — | 94.800 | after_LAND_heartbeat_horizontal_only |

## 20261002T083751Z_3874072a

| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |
|---|---:|---:|---:|---:|
| SIM | 9 | 7 | 0 | 7 |
| FCU | 9 | 4 | 0 | 4 |

| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| FCU/uav_01/p00_approach | 60.700 | 60.750 | 61.764 | 61.768 | 61.794 | 62.255 | 62.200 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p00_approach | 60.600 | 60.750 | 61.764 | 61.768 | 61.794 | 62.255 | 62.300 | after_next_AUTO_request_marker |
| FCU/uav_01/p01_observe | 131.500 | 131.397 | 132.454 | 132.459 | 132.483 | 132.901 | 132.800 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_01/p01_observe | 131.400 | 131.397 | 132.454 | 132.459 | 132.483 | 132.901 | 132.900 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_01/p02_return | 150.500 | 150.460 | 151.484 | 151.488 | 151.513 | — | 152.200 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_01/p02_return | 150.400 | 150.460 | 151.484 | 151.488 | 151.513 | — | 152.200 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_02/p00_approach | 60.700 | 60.657 | 61.749 | 61.768 | 61.777 | 62.255 | 62.200 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p00_approach | 60.600 | 60.657 | 61.749 | 61.768 | 61.777 | 62.255 | 62.200 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p01_observe | 131.200 | 131.118 | 132.250 | 132.459 | 132.484 | 132.902 | 132.800 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_02/p01_observe | 131.100 | 131.118 | 132.250 | 132.459 | 132.484 | 132.902 | 132.800 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_02/p02_return | 150.400 | 150.347 | 151.343 | 151.488 | 151.512 | — | 152.100 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_02/p02_return | 150.300 | 150.347 | 151.343 | 151.488 | 151.512 | — | 152.200 | after_LAND_heartbeat_horizontal_only |
| FCU/uav_03/p00_approach | 60.700 | 60.735 | 61.701 | 61.768 | 61.793 | 62.255 | 62.200 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p00_approach | 60.700 | 60.735 | 61.701 | 61.768 | 61.793 | 62.255 | 62.300 | after_next_AUTO_request_marker |
| FCU/uav_03/p01_observe | 131.400 | 131.334 | 132.358 | 132.459 | 132.486 | 132.901 | 132.900 | confirmed_BRAKE_before_next_AUTO |
| SIM/uav_03/p01_observe | 131.300 | 131.334 | 132.358 | 132.459 | 132.486 | 132.901 | 132.900 | confirmed_BRAKE_before_next_AUTO |
| FCU/uav_03/p02_return | 150.400 | 150.410 | 151.313 | 151.488 | 151.496 | — | 152.100 | after_LAND_heartbeat_horizontal_only |
| SIM/uav_03/p02_return | 150.300 | 150.410 | 151.313 | 151.488 | 151.496 | — | 152.200 | after_LAND_heartbeat_horizontal_only |

完整 JSON 包含逐窗口原 arrival_s、进入区间、事件减驻留代理、模式心跳、速度/距离曲线、连续低速区间、时钟模型及输入 SHA256。

输入文件 902 个，执行前后 SHA256 一致：True。
