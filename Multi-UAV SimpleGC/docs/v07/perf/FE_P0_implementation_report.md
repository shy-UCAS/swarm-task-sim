# P0 性能优化实施报告

基线：09279c2501002a670e77ed4db7b9f9ab0cb71c73。开发分支：perf/v07-first-edition-p0。

本机适配：只读 base 复用 Simulation-v07scene；新建同级 Simulation-perf，使用项目 .conda-env 指定的 llm 环境。P1 分支不合并、不改动。输出在同级 SwarmData/v07_dataset 的全新 perf_fe_p0 目录。按本会话已批准的本机适配跳过重复 fetch；基线与存档来源三处源码差异为空。

G0 PASS：12 组共 100 项基线测试通过；6 单机及 1 同步联合重放与归档完全一致；突防样本两次独立进程规划一致。只剔除指定墙钟字段，精确比较结果见 FE_P0_baseline.json。

后续门禁待执行。

## G3 静态前提

- E1 PASS：command 位于快照前；快照到回滚只调用 observe_segment；observe_sample 位于事务后。 定位：task_v07/execution.py:83-107, task_v07/dwell.py:41-61。
- E2 PASS：witnesses.append(event) 与 events.extend(emitted)，未修改已有元素。 定位：swarm_sim/fast_dynamics/route_tracker.py:337-434。
- E3 PASS：全仓 Python 的 .witnesses/.events 写入已核对。执行相关列表只有构造、deepcopy 赋值及追加；replay_viewer 的排序、诊断 RNG 的 events、测试假对象属于不同类型。已有测试读取或 deepcopy 切片，没有改 tracker 的旧元素。 定位：G3_event_writes_search.txt。
- E4 PASS：同一新 event 字典加入 witnesses 与 emitted 后进入 events；deepcopy 使用共享 memo。新快照保留元素身份，S1 检验 is 共享。 定位：swarm_sim/fast_dynamics/route_tracker.py:194-201, swarm_sim/fast_dynamics/route_tracker.py:350-355, swarm_sim/fast_dynamics/route_tracker.py:433。
- E5 PASS：tracker 构造及使用局限于 execute；dwell_trackers 只保存整数。循环局部 t 在回滚后读取前即重新绑定；events 不持有 tracker。Dwell 的内层引用封装在 wrapper 内，递归恢复。新增 snapshots 是私有事务引用，不导出。 定位：task_v07/execution.py:40-49, task_v07/execution.py:67-101。

静态定位使用基线源码行号；全仓搜索原始输出保留。S1/S2 共 4 项通过；三夹具新旧路径分别触发 6、6、2 次回滚，积分步数与全部指定字段完全一致。

G3 PASS：31 条单机、6 条联合重放，共 37 项全部与存档精确一致，包含监视同步长仿真（74.59 秒）；未使用超时降级。12 组原测试共 100 项通过。新增 4 项快照测试通过。诊断脚本编辑曾造成 5 项缺少 parity，已在新目录重跑全部通过，原始记录保留，不计为通过证据。详见 parity_results 的 rerun_note。

## G1 预检

SKIPPED：max(saved_within)=1.2246%，saved_family=9.0138%，低于 15%。A 组同进程三骨架规划合计 53.45 秒，B 组单进程 52.46 秒。未实现 visibility_cache.py、_from_blueprint 或 FreeSpace 缓存接入；对应缓存单元测试不适用。预检的三个指定规划样本与 base 完全一致。原始记录与决策见 FE_P0_G1_precheck.json。

## G2 保守几何预筛选

PASS：四组场景每组 20000 线段与 5000 点，共 100000 次布尔对照一致；圆相切、多边形边界 ±1e-7、正/负/零 buffer 与重叠障碍物通过。真实有效 view（margin=0）与原 scene（margin=35）的 vertices/adjacency 完全相同。参考 free 与 _visible_uncached 从基线逐字复制，仅改函数名，并已核对字面内容一致。三个指定真实规划样本的五类输出精确一致。世界检查、端点顺序、障碍物顺序、原判据与 path 算法保持不变。exact_calls/skipped 仅计障碍物查询，不含世界检查。
