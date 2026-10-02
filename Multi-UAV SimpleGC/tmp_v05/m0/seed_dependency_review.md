# M0：任务种子对 `template_id` 的依赖

**结论：有条件成立。** v0.4 的任务种子包含 `template_id`。profile 未显式填写该字段时，生成器会对整个任务模板（包括 `execution`）取 SHA256 的前 20 位作为默认 ID。因此仅修改驻留配置也会改变任务种子。V06 profile 显式填写 `recon_v04_route_v06`，同样的修改不会改变它的种子。

按 V06 profile 的第 0 个场景、第 0 个候选和第 0 个任务变体计算，场景种子为 `442445514775877568`。将模板中的 `execution.terminal_hold_s` 从 `0.5` 改为 `1`，模板规范化哈希从 `eda99bc1bff185563a467f770ce56d4618cff3ce8a147a157404507cf8a85ada` 变为 `6b77c6cbd7662031cb2397b8b622cf9b243052669e769aef50ab919c9325628f`。省略 `template_id` 时，任务种子从 `4835539782409883372` 变为 `1904240717079467866`；显式固定 V06 ID 时，两次均为 `330863698933941023`，与已有 V06 `mission_list.json` 首项一致。

源码链条：`generation.py:116-124` 将 schema 2 派发给 `generation_v2.py`；后者在 `:91-105` 读取模板并生成默认 ID，在 `:43-44` 计算任务种子，在 `:155-170` 写入 TaskSpec。场景种子的独立公式见 `:39-40`。完整输入、两组输出和源码位置见同目录的 `seed_dependency_review.json`。

这证明了**种子值**的依赖关系；当前 v0.4 侦察规划器未用该种子抽样航线。v0.5 巡逻规划器将用种子决定圈数、方向和入环点，R06 应验证新 `task_semantics_only_v1` 在修改 `execution` 时保持这些结果不变，并用 V06 原产物哈希验证缺省 `seed_scheme` 的兼容性。
