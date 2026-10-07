# r1.2b 已完成巡逻离线判定对照

本次仅对照语义结果，不据新旧判定变化停止，不占 SITL 预算。旧运行、分析、latest 指针和控制台账保留。
新分析显式使用 `perimeter_revisit_v2` / `multi_intent_validation_v3`，有序映射保持 `ordered_route_progress_v2`。
本轮不重评或执行 PP09 起的新停止策略。新分析不附加旧 r1.2 门禁作为新门禁判定。

| 运行 | 原真值 / 观察 | 新真值 / 观察 | 原 / 新语义一致性 | 原 / 新质量资格 |
| --- | --- | --- | --- | --- |
| VP1 | True / True | True / True | agree / agree | True / True |
| VP2 | True / True | True / True | agree / agree | True / True |
| VP3 | True / True | True / True | agree / agree | True / True |
| PP02 | True / True | True / True | agree / agree | True / True |
| PP04 | True / True | True / True | agree / agree | True / True |
| PP06 | True / True | True / True | agree / agree | True / True |
| PP08 | False / True | True / True | disagree / agree | True / True |

结果变化 1/7。逐通道访问次数、间隔、圈数和原运行内各版分析见 [comparison.json](comparison.json)。
此处“原”以最新已封存的有序映射 v2 分析作比较基准；VP1 原 r1 FAIL、PP08 原 v1/v2 分歧及停止判定仍分别保留。

旧证据 2173 个文件及受保护 11307 个文件全部保持，见 [保存性核对](preservation_result.json)。
[输入与源码哈希](input_preservation.json)绑定本次离线输入与实现。新目录中的数据是重分析附件，未导出为新数据集。
