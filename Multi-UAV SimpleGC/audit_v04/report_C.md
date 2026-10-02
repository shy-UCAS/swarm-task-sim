# v0.4 前置审查报告 — 第二批（C 组：只有侦察一类的写死位置）

**审查日期**: 2026-10-01
**HEAD**: `e13564b700934b481ad37cba053db9daabf9e4fa`　**版本**: `0.3.0`
**范围**: C1–C7

---

## C1 全仓库检索

### 状态
**证实**：8 个检索串在源码与测试中共出现 **77 处**，其中源码 **25 处**。侦察专属语义在**三个层次**写死：schema 枚举、协议常量、规划/评估实现体。

各串计数（源码 / 合计）：`reconnaissance` 1/10、`area_coverage` 1/2、`shared_coverage` 1/7、`recon_` 4/24、`equal_strip_lawnmower` 2/2、`monotone_entry_order` 1/1、`coverage_ratio` 7/21、`partition_axis` 8/11。

### 证据：按文件与用途分类

分类代码：(a) 任务本体/枚举限制　(b) 协议版本常量　(c) 生成器/采样器　(d) 验证器/指标　(e) 数据审计　(f) 测试　(g) 其他

| 检索串 | 文件:行 | 用途 | 类 |
|--------|---------|------|----|
| `reconnaissance` | `mission_schema.py:125` | `_enum(mission, "intent", "mission", ("reconnaissance",))` —— **intent 值为单元素元组** | (a) |
| | `tests/test_mission_data.py:42,138,139,140,148` | 构造 labels / 断言 requested_intent | (f) |
| | `tests/test_mission_evaluation.py:21,81` | 构造 mission spec / 断言 | (f) |
| | `tests/test_mission_planning.py:217` | 断言编译产物 intent | (f) |
| | `tests/test_v03_integration.py:110` | 断言 labels | (f) |
| `area_coverage` | `mission_schema.py:126` | `_enum(mission, "objective", "mission", ("area_coverage",))` —— **objective 值为单元素元组** | (a) |
| | `tests/test_mission_evaluation.py:21` | 构造 mission spec | (f) |
| `shared_coverage` | `protocol.py:6` | `SHARED_SEMANTIC_VERSION = "shared_coverage_v2"` | (b) |
| | `tests/test_mission_data.py:218,219,221,222` | 篡改版本串以测试拒绝 | (f) |
| | `tests/test_v03_integration.py:122,221` | 断言/篡改协议版本 | (f) |
| `recon_` | `generation.py:75` | 默认模板路径 `missions/recon_shared_3uav.json` | (c) |
| | `generation.py:104` | `task_id = f"recon_{base_index:04d}"` | (c) |
| | `generation.py:134` | `family = f"recon_{base_id}"` —— **family 前缀固定为 recon** | (c) |
| | `generation.py:156` | `mission_id = f"recon_{base_index:04d}_{variant_id}"` | (c) |
| | `tests/test_mission_data.py:26,361,365,366,372,380` | 模板路径与 mission_id 选择 | (f) |
| | `tests/test_mission_evaluation.py:319`、`test_mission_planning.py:14,45,145,146,147`、`test_replay_viewer.py:20,158`、`test_v03_integration.py:26,102,234` | 模板路径 / family 断言 | (f) |
| | `scripts/verify_replay_gui.py:60`、`scripts/verify_v03_sitl.py:34,39` | 验证脚本引用侦察任务文件 | (g) |
| `equal_strip_lawnmower` | `mission_planning.py:11` | `PLANNER_VERSION = "equal_strip_lawnmower_v1"` —— 全模块共用单一规划器版本常量 | (b) |
| | `mission_schema.py:144` | `_enum(planner, "name", "planner", ("equal_strip_lawnmower_v1",))` | (a) |
| `monotone_entry_order` | `mission_schema.py:146` | `_enum(planner, "assignment", "planner", ("monotone_entry_order",))` | (a) |
| `coverage_ratio` | `evaluation.py:26` | `def coverage_ratio(rows, vehicle, task, altitude, tolerance, max_gap)`（v1 原语评估） | (d) |
| | `evaluation.py:109` | v1 评估中调用 | (d) |
| | `mission_evaluation.py:219` | `per_agent[...]["coverage_ratio"]` | (d) |
| | `mission_evaluation.py:230` | `global_coverage_ratio=ratio` | (d) |
| | `dataset_audit.py:91,140,173` | 聚合 `global_coverage_ratio`；`missing_metrics` 把它列为必需项 | (e) |
| | `tests/test_mission_evaluation.py:51,52,61,72,94,115,167,168`、`test_quality.py:15,176`、`test_research.py:13,126,128,129` | 断言 | (f) |
| `partition_axis` | `mission_schema.py:143,145` | planner 字段白名单 + `_enum(..., ("east","north"))` | (a) |
| | `generation.py:108,110` | 采样剖分轴并写入 spec / 记录 | (c) |
| | `mission_planning.py:120,153` | **规划器实现体**：`axis = planner["partition_axis"]`，据此切条带；写入 `planning` | (a)注 |
| | `dataset_audit.py:125,128` | 统计 `partition_axes`；粗签名含轴 | (e) |
| | `tests/test_mission_planning.py:19,95,152` | 断言 / 非法轴被拒 | (f) |

> 注：任务书的 7 个类别中没有"规划器实现体"一项。`mission_planning.py` 是唯一的规划实现，一行条带式 lawnmower 的全部假设都写在这里，故归入 (a) 任务本体，并在此标注归类不完全对应。

### 源码层面（不含测试/脚本）的三类写死点

| 层次 | 位置 | 内容 |
|------|------|------|
| **枚举层** | `mission_schema.py:125,126,134,135,144,146,155,156,168` | 9 处 `_enum` 全部为单元素或多元素硬枚举；intent、objective、观察模型、规划器名、分配法、平台 id 各只有一种合法值 |
| **协议常量层** | `protocol.py:6,7,8`、`mission_planning.py:11,12` | `SHARED_SEMANTIC_VERSION`、`SHARED_CONSTRAINT_VERSION`、`SHARED_LABEL_SCHEMA_VERSION`、`PLANNER_VERSION`、`SEMANTIC_PLAN_VERSION` 均为全局单值常量 |
| **实现体层** | `mission_planning.py:116-164`（整个 `compile_shared_mission_v2`）、`mission_evaluation.py:188-238`（`_evaluate_channel` 只做覆盖）、`mission_evaluation.py:263-268`（`planned_behaviors=["area_scan"]`、`observed_behaviors=[name="coverage"]` 硬编码） | 规划与评估的算法本体只实现了"等分条带 + 蛇形扫描 + 覆盖判定" |

### 对 v0.4 的影响
新增第二类意图需要同时改动上述三层。仅放开枚举不足够——`compile_shared_mission_v2` 与 `_evaluate_channel` 的算法本体只产出与判定覆盖。

---

## C2 family 标识

### 状态
**证实**：`family_namespace` **包含 `template_spec` 的全部内容**，因此改动模板中任一字段都会改变 `family_id`。

### 证据

`swarm_sim/generation.py:132-135`（原样摘录）:

```python
    family_namespace = canonical_hash({key: value for key, value in profile.items()
        if key not in ("base_scene_count", "max_candidates_per_base", "variant_speed_factors")})
    for base_index in range(profile["base_scene_count"]):
        base_id = canonical_hash([GENERATOR_VERSION, family_namespace, profile["master_seed"], base_index])[:20]
        family = f"recon_{base_id}"
```

`swarm_sim/generation.py:72-78`（原样摘录，说明 `template` → `template_spec` 的转换）:

```python
    if "template" in data and "template_spec" in data:
        raise ValueError("provide template or template_spec, not both")
    if "template_spec" not in data:
        template = Path(data.pop("template", str(PROJECT / "missions/recon_shared_3uav.json")))
        if not template.is_absolute():
            template = base / template
        data["template_spec"] = json.loads(template.read_text(encoding="utf-8-sig"))
```

**`template` 键在 `_profile` 中被 pop 掉，内容转存为 `template_spec`；`template_spec` 不在排除名单中，故整个模板 spec 被计入 `family_namespace`。**

实测（`audit_v04/C2_family.py`）：

- `template_spec` 在 `_profile` 处理后的 profile 中：**存在**（`'template' in prof == False`）
- 计入 `family_namespace` 的字段共 **13 个**：`entry_distance_m, entry_sides, master_seed, partition_axes, region_east_m, region_north_m, return_required, schema_version, speeds_m_s, strip_width_m, sweep_length_m, **template_spec**, vehicle_counts`
- 实际 bundle 校验：`base_index=0` → `base_id=d30e405969398e0c2f76`，与 `generated/recon_pilot_v03_20260930/missions/recon_0000_v00.json` 中的 `family_id: "recon_d30e405969398e0c2f76"` 一致。

### 干跑：同 `master_seed` + 同 `base_index`，只改 `template_spec` 一个字段

输出目录：`audit_v04/tmp/c2_*`（各含完整 bundle）

| 变体 | 被改字段 | family_namespace 相同? | family_id 相同? | 新 family_id |
|------|---------|----------------------|----------------|-------------|
| 原始 | — | — | — | `recon_d30e405969398e0c2f76` |
| V1 | `planner.tracking_margin_m` 1.0 → 2.0 | **否** | **否** | `recon_7afadaf18c9f7a2e2466` |
| V2 | `mission.observation_model.grid_m` 1.0 → 2.0 | **否** | **否** | `recon_d548c67240c69fbc2cb2` |
| V3 | `platform.max_path_length_m` 1000 → 2000 | **否** | **否** | `recon_1036f7f4858ebd488265` |

**3/3 变体均改变了 `family_id`。** 即 `family_id` 不是"物理场景身份"，而是"整个模板 + 采样参数"的哈希。

### `recon_<id>` 与 `patrol_<id>` 的 split 一致性

`swarm_sim/dataset.py:15-17`（原样摘录）:

```python
def family_split(family_id, salt="simplegc-v02"):
    bucket = int(hashlib.sha256((salt + ":" + family_id).encode()).hexdigest()[:16], 16) % 100
    return "train" if bucket < 70 else ("validation" if bucket < 85 else "test")
```

| 数据集 | 落入同一 split 的比例 |
|--------|---------------------|
| 已生成 bundle 中的 100 个真实 `base_id` | **54/100 = 0.5400** |
| 对照：100 个 SHA256 前缀 id | 58/100 = 0.5800 |
| 理论期望（哈希均匀，70/15/15） | 0.70² + 0.15² + 0.15² = **0.5350** |

**实测与理论一致**：两个 family 字符串仅前缀不同（`recon_` vs `patrol_`，4–6 字符），其余 20 位十六进制相同，SHA256 的雪崩效应使二者 split 近似独立。因此**约 46% 的物理场景会被拆到不同 split**（同一场景的一半进 train、另一半进 test）。

### 对 v0.4 的影响
- 若 v0.4 在同一 `generation.generate` 中让 `family = f"recon_{base_id}"` 变为按意图分流（如 `patrol_{base_id}`），则同一物理场景的两个意图会以约 0.54 的概率留在同一 split、以约 0.46 的概率被拆开。
- `family_id` 对 `template_spec` 全字段敏感，意味着任何模板微调都会重新洗牌 family 归属与 split 分配。
- `dataset_audit.audit_dataset:142-144` 会把"同一 family 跨 split"记为 issue（`family_split_leaks`）；前缀分流不触发该检查，因为两条 family 字符串本身不同。

---

## C3 协议

### 状态
**证实**（逐项回答见下）。

### 证据：`protocol.py` 全部协议字段及当前常量值

`swarm_sim/protocol.py:6-11`（原样摘录）:

```python
SHARED_SEMANTIC_VERSION = "shared_coverage_v2"
SHARED_CONSTRAINT_VERSION = "execution_limits_v2"
SHARED_LABEL_SCHEMA_VERSION = 2

PROTOCOL_FIELDS = ("task_kind", "ontology_version", "label_schema_version", "semantic_validation_version",
                   "eligibility_protocol_version", "execution_constraints_version")
```

`swarm_sim/protocol.py:14-21`（原样摘录）:

```python
def semantic_protocol(scene):
    if scene.get("task_spec", {}).get("schema_version") == 2:
        return dict(task_kind="mission_v2", ontology_version="shared_mission_v1", label_schema_version=SHARED_LABEL_SCHEMA_VERSION,
                    semantic_validation_version=SHARED_SEMANTIC_VERSION, eligibility_protocol_version="shared_quality_v1",
                    execution_constraints_version=SHARED_CONSTRAINT_VERSION)
    return dict(task_kind="primitive_v1", ontology_version="primitives_v1", label_schema_version=1,
                semantic_validation_version="fcu_geometric_v1", eligibility_protocol_version="primitive_quality_v022",
                execution_constraints_version="not_applicable")
```

| 字段 | v2 当前值 | v1 当前值 |
|------|----------|----------|
| `task_kind` | `mission_v2` | `primitive_v1` |
| `ontology_version` | `shared_mission_v1` | `primitives_v1` |
| `label_schema_version` | `2`（= `SHARED_LABEL_SCHEMA_VERSION`） | `1` |
| `semantic_validation_version` | `shared_coverage_v2`（= `SHARED_SEMANTIC_VERSION`） | `fcu_geometric_v1` |
| `eligibility_protocol_version` | `shared_quality_v1` | `primitive_quality_v022` |
| `execution_constraints_version` | `execution_limits_v2`（= `SHARED_CONSTRAINT_VERSION`） | `not_applicable` |

其余相关常量：`mission_planning.py:11-12` 的 `PLANNER_VERSION = "equal_strip_lawnmower_v1"`、`SEMANTIC_PLAN_VERSION = "shared_semantics_v1"`（这两个**不属于** `PROTOCOL_FIELDS`，不参与协议一致性校验）。

### 协议的全部校验点

| # | 位置 | 校验内容 |
|---|------|---------|
| 1 | `protocol.py:26-28` `manifest_protocol` | 6 个字段要么全在 manifest 中、要么全不在；部分存在即报 `incomplete semantic protocol in analysis manifest` |
| 2 | `protocol.py:30-33` | 全不在时，仅 `analysis_version ∈ {0.2.0, 0.2.1, 0.2.2}` 允许回退到 v1 默认值，否则 `analysis is missing semantic protocol; reanalyze the run` |
| 3 | `protocol.py:35-36` | 每个值须为非 bool、非空字符串或整数 |
| 4 | `protocol.py:43-59` `validate_artifact_protocol` | v2 下要求 `labels.json` 等 4 个 artifact 已在 `artifact_sha256` 中；且 manifest、`quality.json`、`labels.json`（`schema_version`、`task_kind`、`label_provenance.semantic_validation_version`、全部 `observed_behaviors[].rule_version`）、`semantic_validation.json`、`execution_constraints.json` 五处的版本声明必须一致 |
| 5 | `dataset.py:37-40` `build_dataset` | `protocols` 集合 > 1 即 `incompatible semantic/eligibility protocols: export separate datasets` |
| 6 | `episode_loader.py:24-27` `load_episode` | `protocol != supported` 即 `unsupported semantic protocol in episode`，其中 `supported` 由 `semantic_protocol({"task_spec": {"schema_version": 2}})` 给出，即**只接受当前常量** |
| 7 | `episode_loader.py:47-49` | dataset manifest、episode entry、episode manifest 三者协议必须一致 |
| 8 | `analysis.py:212` | `quality.update(protocol)` —— 把协议写入 quality.json |
| 9 | `dataset_audit.py:73-74,145-146` | 用 `canonical_hash(protocol)` 分组，>1 组即 issue `mixed label/quality/eligibility protocols` |

### 回答

**问 1：新增 Patrol 任务并使用不同的 `semantic_validation_version`，在哪一步会被拒绝？**

分两种情形：

- **若 Patrol 任务本身不合法**（`intent != "reconnaissance"`）：在**规划编译**阶段即被拒绝，早于任何 SITL 运行。`mission_schema.py:125` 的 `_enum(mission, "intent", "mission", ("reconnaissance",))` 抛 `mission.intent must be one of ['reconnaissance']`，该函数由 `mission_planning.py:117` 的 `compile_shared_mission_v2` 调用。
- **若 Patrol 任务合法但协议版本不同**：`semantic_protocol()` 只依据 `task_spec.schema_version == 2` 取值，**不读 `intent`**，因此只要 `SHARED_SEMANTIC_VERSION` 未改，两类任务仍得到同一协议。若把版本常量改为按意图分流，则依次在以下位置被拒：
  1. **同一数据集内混装** → `dataset.py:39-40`：`incompatible semantic/eligibility protocols: export separate datasets`
  2. **单独加载某 episode** → `episode_loader.py:26-27`：`unsupported semantic protocol in episode`（因为 `supported` 只由当前常量生成）
  3. **artifact 内部不一致** → `protocol.py:53-59`：`inconsistent semantic protocol across analysis artifacts`

**问 2：`mission.intent` 本身是否是协议字段？**

**否。** `PROTOCOL_FIELDS`（`protocol.py:10-11`）为 6 个字段，不含 `intent`。`intent` 出现在两处**数据**而非协议：
- `mission_evaluation.py:262`：`requested_intent=mission["intent"], assigned_intent=mission["intent"]` 写入 `labels.json`
- `analysis.py:198`：`"mission.json": scene["task_spec"]["mission"]` 作为 artifact 输出

因此两类意图在协议层面**可以共存**，只要共享 `schema_version == 2` 与同一个 `semantic_validation_version`。

**问 3：要让两类意图共存于一个数据集，最少需要改动哪些常量或函数？**

分两种目标：

- **目标 A：两类意图共用同一套语义校验版本**（例如 Patrol 的"行为正确"仍用覆盖/几何判定）
  - 协议常量**无需改动**；`semantic_protocol()` 无需改动；`episode_loader` 的 `supported` 无需改动。
  - 最少需要放开的是枚举：`mission_schema.py:125`（intent）、`:126`（objective）；若 Patrol 用不同规划器还要放开 `:144`（planner.name）、`:146`（assignment）。
- **目标 B：两类意图各用不同的 `semantic_validation_version`**
  - `protocol.py:6` `SHARED_SEMANTIC_VERSION` 必须由单值改为按意图取值；
  - `protocol.py:14-21` `semantic_protocol()` 必须新增对 `intent` 的读取；
  - `episode_loader.py:25` 的 `supported` 计算必须接受多版本（否则每条 Patrol episode 都会被拒）；
  - `dataset.py:39-40` 的混装拒绝逻辑需按意图分组而非全局分组。

### 对 v0.4 的影响
- 协议不区分意图，故"一类意图一个数据集"与"两类意图一个数据集"在协议层都可行。
- 协议版本的粒度是**整个数据集**（`dataset.py:38-40`、`episode_loader.py:25-27`），没有 episode 级或窗口级的版本表达。
- `PLANNER_VERSION` 与 `SEMANTIC_PLAN_VERSION` 不参与协议校验，新增规划器不会触发 `validate_artifact_protocol`。

---

## C4 任务 schema

### 状态
**证实**。

### 证据：`normalize_mission` 中的取值限制位置

`swarm_sim/mission_schema.py:33-35`（原样摘录，`_enum` 本体）:

```python
def _enum(obj, key, path, choices):
    if not isinstance(obj[key], str) or obj[key] not in choices:
        raise ValueError(f"{path}.{key} must be one of {list(choices)}")
```

`swarm_sim/mission_schema.py:123-126`（原样摘录）:

```python
    mission = _object(spec["mission"], "mission", (
        "intent", "objective", "target_region_id", "coverage_required", "return_required", "observation_model"))
    _enum(mission, "intent", "mission", ("reconnaissance",))
    _enum(mission, "objective", "mission", ("area_coverage",))
```

`swarm_sim/mission_schema.py:132-135`（原样摘录）:

```python
    model = _object(mission["observation_model"], "observation_model", (
        "type", "radius_m", "height_tolerance_m", "grid_m", "activation"))
    _enum(model, "type", "observation_model", ("ideal_horizontal_disk",))
    _enum(model, "activation", "observation_model", ("observe_phase_only",))
```

`swarm_sim/mission_schema.py:142-146`（原样摘录）:

```python
    planner = _object(spec["planner"], "planner", (
        "name", "partition_axis", "assignment", "lane_spacing_m", "tracking_margin_m"))
    _enum(planner, "name", "planner", ("equal_strip_lawnmower_v1",))
    _enum(planner, "partition_axis", "planner", ("east", "north"))
    _enum(planner, "assignment", "planner", ("monotone_entry_order",))
```

**`normalize_mission` 全部 9 处 `_enum` 调用**：

| 行 | 路径 | 当前合法值 |
|----|------|-----------|
| 89 | `region.type` | `("rectangle",)` |
| **125** | **`mission.intent`** | **`("reconnaissance",)`** |
| **126** | **`mission.objective`** | **`("area_coverage",)`** |
| 134 | `observation_model.type` | `("ideal_horizontal_disk",)` |
| 135 | `observation_model.activation` | `("observe_phase_only",)` |
| **144** | **`planner.name`** | **`("equal_strip_lawnmower_v1",)`** |
| 145 | `planner.partition_axis` | `("east", "north")` |
| **146** | **`planner.assignment`** | **`("monotone_entry_order",)`** |
| 155 | `platform.id` | `("basic_multirotor_nominal_v1",)` |
| 156 | `platform.dynamics_validation` | `("execution_proxy_only",)` |
| 168 | `execution.backend` | `("AUTO",)` |

非枚举但同样构成限制的约束：
- `mission_schema.py:84-85`：`regions` 必须恰好 1 个（`v2 supports exactly one shared rectangle region`）
- `mission_schema.py:81-82`：`restricted_regions` 必须为空
- `mission_schema.py:127`：`mission.target_region_id` 必须等于该唯一 region 的 id
- `mission_schema.py:139-140`：覆盖网格上限 10000 cell
- `mission_schema.py:149-150`：`planner.lane_spacing_m <= 2 * model.radius_m`
- `mission_schema.py:179-180`：`min(region.width, region.height) > 2 * arrival_tolerance_m`

### 新增 `intent=patrol` 时需要修改的校验分支

**必须改（3 处枚举）**：
1. `mission_schema.py:125`：`_enum(mission, "intent", "mission", ("reconnaissance",))` → 加入 `"patrol"`
2. `mission_schema.py:126`：`_enum(mission, "objective", "mission", ("area_coverage",))` → 加入 Patrol 的目标值
3. `mission_schema.py:144` / `:146`：若 Patrol 使用不同规划器或分配法，`planner.name` / `planner.assignment` 的枚举需加入新值

**可能需要改（4 处非枚举约束）**：
4. `mission_schema.py:84-85`：若 Patrol 需要非矩形区域或多区域，`len(regions) != 1` 的限制需放宽
5. `mission_schema.py:134-135`：若 Patrol 使用不同观察模型（`ideal_horizontal_disk` / `observe_phase_only` 之外），两处枚举需放宽
6. `mission_schema.py:139-140`：Patrol 若不需要覆盖网格，10000 cell 上限与 `mission.coverage_required` 的存在性需重新界定
7. `mission_schema.py:149-150`：`lane_spacing_m <= 2*radius_m` 是 lawnmower 专属约束，对 Patrol 不适用

**schema 之外但同属校验的分支**：
- `mission_planning.py:123-124`：`responsibility strip too small for declared arrival tolerance`（条带式剖分专属）
- `mission_planning.py:126-127`：`1 + 2*lanes + return > 100`（阶段数上限，依赖 `2*lanes` 这一 lawnmower 结构）
- `mission_planning.py:142-143`：`nominal global coverage ... below required coverage`
- `mission_evaluation.py:244-245`：`evaluate_mission` 强制 `schema_version == 2`

### 对 v0.4 的影响
- 枚举层是**单点**改动（每个 `_enum` 一行），但枚举之后的**算法体**（`compile_shared_mission_v2` 的条带剖分、`_evaluate_channel` 的覆盖判定、`mission_schema.py:139/149/179` 的 lawnmower 专属约束）不会因为枚举放开而适用于 Patrol。
- `coverage_required`、`observation_model`、`lane_spacing_m`、`partition_axis` 都是 `mission`/`planner` 的**必填字段**（`_object` 无 `optional`），Patrol 若不使用这些字段，或需将其改为可选，或需另设 schema 版本。

---

## C5 场景采样器与随机起点的干跑实验

### 状态
**证实**（采样器事实核查全部成立；随机布局下接受率显著下降，且拒绝原因随布局类型系统性变化）。

### C5-1 采样器核查：`generation._sample`

`swarm_sim/generation.py:86-112`（原样摘录）:

```python
def _sample(profile, base_index, candidate_index, family):
    seed = int(canonical_hash([GENERATOR_VERSION, profile["master_seed"], base_index, candidate_index])[:16], 16) % (2**63)
    rng = random.Random(seed)
    spec = copy.deepcopy(profile["template_spec"])
    count = rng.choice(profile["vehicle_counts"])
    axis = rng.choice(profile["partition_axes"])
    side = rng.choice(profile["entry_sides"])
    strip = rng.uniform(*profile["strip_width_m"])
    sweep = rng.uniform(*profile["sweep_length_m"])
    east, north = (rng.uniform(*profile[key]) for key in ("region_east_m", "region_north_m"))
    entry = rng.uniform(*profile["entry_distance_m"])
    width, height = (count * strip, sweep) if axis == "east" else (sweep, count * strip)
    region = dict(id="R1", type="rectangle", min_east_m=east, min_north_m=north,
                  width_m=width, height_m=height)
    vehicles = []
    for i in range(count):
        lane = (i + 0.5) * strip
        outside = -entry if side == "low" else sweep + entry
        e, n = (east + lane, north + outside) if axis == "east" else (east + outside, north + lane)
        vehicles.append(dict(id=f"uav_{i + 1:02d}", sysid=i + 1, east_m=e, north_m=n, heading_deg=0.0))
```

| 核查项 | 结论 | 证据 |
|--------|------|------|
| 区域尺寸是否由飞机数决定 | **是**，`count × strip_width` | `generation.py:97`：`width, height = (count * strip, sweep) if axis == "east" else (sweep, count * strip)` |
| 生成点是否在各自未来条带中线上 | **是** | `generation.py:101`：`lane = (i + 0.5) * strip`，第 i 条带 `[i*strip, (i+1)*strip]` 的中点为 `(i+0.5)*strip` |
| `entry_sides` 默认值 | `_profile` 默认 **`["low"]`**；本 profile 实际取值 **`["low", "high"]`** | `generation.py:52`（默认值）、`generation_profiles/recon_pilot_v03.json`（实际值） |
| `heading_deg` 是否固定 | **固定为 0.0，无采样** | `generation.py:103` 硬编码 `heading_deg=0.0` |

`high` 分支的 `outside = sweep + entry`（`generation.py:100`）在两种轴下均正确：`axis == "east"` 时区域北向跨度为 `height = sweep`，`axis == "north"` 时区域东向跨度为 `width = sweep`（`generation.py:97`），故两处偏移量都恰好把飞机放在区域边界外 `entry` 处。

### C5-2 干跑实验

方法：保持 `strip_width_m`、`sweep_length_m`、`region_*`、`entry_distance_m`、`vehicle_counts`、`partition_axes`、`entry_sides`、`speeds_m_s`、`return_required` 的分布不变，
只替换车辆生成点的布局；每布局 **200 个样本**；在内存中调用 `compile_task`，**不启动 SITL**。
脚本：`audit_v04/C5_dryrun.py`、`audit_v04/C5_dryrun2.py`。

**布局 1：区域一侧随机散布** — 在进入侧的方向上固定，沿剖分轴在区域内随机散布
**布局 2：区域外随机方向的随机散布** — 以区域中心为原点，随机方位角 + 随机距离
**布局 3：紧凑编队，整体随机平移和旋转** — 间距 `2 × min_separation_m = 10 m` 的直线队形，随机旋转角 + 随机平移

#### 第一轮（不对初始布局做任何筛选）

| 布局 | 接受率 | 拒绝原因分布 |
|------|--------|-------------|
| baseline（原采样器，条带中线） | **200/200 = 1.000** | — |
| 区域一侧随机散布 | **51/200 = 0.255** | 初始间距不足 144/200 (0.720)、同阶段路径间距不足/交叉 5/200 (0.025) |
| 区域外随机方向散布 | **134/200 = 0.670** | 初始间距不足 39/200 (0.195)、同阶段路径间距不足/交叉 27/200 (0.135) |
| 紧凑编队 | **60/200 = 0.300** | 同阶段路径间距不足/交叉 **140/200 (0.700)** |

#### 第二轮（拒绝采样，先保证初始布局合法：全部点在世界边界内且两两间距 ≥ `min_separation_m` = 5 m）

| 布局 | 接受率 | 拒绝原因分布 |
|------|--------|-------------|
| baseline | **200/200 = 1.000** | — |
| 区域一侧随机散布 | **127/200 = 0.635** | 初始间距不足 59/200 (0.295)、路径间距/交叉 14/200 (0.070) |
| 区域外随机方向散布 | **155/200 = 0.775** | 路径间距/交叉 30/200 (0.150)、初始间距不足 15/200 (0.075) |
| 紧凑编队 | **60/200 = 0.300** | 路径间距/交叉 **140/200 (0.700)** |

> 第二轮中仍有"初始间距不足"残留，原因是**规划器的初始间距门槛严于场景自身的 `min_separation_m`**：
> `capability.py:26` 要求 `required_clearance = min_separation_m + 2 * tracking_margin_m = 5 + 2×1 = **7 m**`，
> 而本轮筛选只保证了 5 m。故上表是接受率的**下界**。

**要点**：
- 原采样器（条带中线）接受率 **200/200**，不存在任何几何冲突——因为它把每架飞机预先放在其条带中线上，且 `strip_width_m ∈ [12,16] m` 远大于 7 m 的间距门槛。
- 换成与意图无关的布局后，接受率降到 **0.255–0.775**；拒绝原因从"初始间距"（随机散布偶然过近）转为"同阶段路径间距不足/交叉"（紧凑编队下 70%）。
- 即：**当前规划器对"起点是否按条带对齐"高度敏感**。

### C5-3 `monotone_entry_order` 在随机布局下是否容易产生交叉的进入路径

分配规则（`mission_planning.py:128`，原样摘录）:

```python
    ordering = sorted(scenario["vehicles"], key=lambda v: (v[f"{axis}_m"], v["id"]))
```

即按剖分轴坐标排序，第 k 个飞机拿第 k 个条带。进入路径定义为 `spawn → 该机条带 lane-0 中线起点 scan[0]`，用 `tasks.segment_clearance` 做**精确线段相交检测**（`audit_v04/C5_dryrun2.py`）。

| 布局 | 存在交叉的样本 | 交叉机对 |
|------|--------------|---------|
| baseline（条带中线） | **0/200 = 0.000** | 0/1284 = 0.000 |
| 区域一侧随机散布 | **0/200 = 0.000** | 0/674 = 0.000 |
| 区域外随机方向散布 | **6/200 = 0.030** | 7/1058 = 0.007 |
| 紧凑编队（随机方向 + 随机旋转） | **58/200 = 0.290** | 214/1204 = 0.178 |

**结论**：
- `monotone_entry_order` 的"按轴排序分配条带"本身**不会**制造交叉——只要所有飞机从同一侧进入，排序后的分配使进入路径呈扇形散开（布局 1 与 baseline 均为 0 交叉）。
- 交叉出现在**飞机起点分布在区域的不同方位**时（布局 2，3.0%）或**整体旋转的紧凑编队**时（布局 3，**29.0%**）：此时"按轴坐标排序"得到的顺序与"条带沿轴排列"的顺序在几何上不再一致。
- 因此交叉的成因是**起点布局与条带分配规则不匹配**，而非 `monotone_entry_order` 本身有缺陷。

### 对 v0.4 的影响
- 若 v0.4 需要"与意图无关的随机起点"（例如让 Patrol 的起点不暴露航迹意图），当前规划器会把 **22.5%–74.5%** 的样本判为几何不可行，主要卡在 `capability.py:60-62` 的同阶段路径间距门槛（`min_separation_m + 2×tracking_margin_m`）与 `capability.py:31-32` 的初始间距门槛上。
- 拒绝原因集中在**间距与交叉**，与意图语义无关。
- 交叉检测目前只在 `compile_shared_mission_v2` 之内通过 `nominal_capability` 的 segment clearance 间接生效（`capability.py:57-62`），不存在独立的"进入路径交叉"判据。

---

## C6 数据审计的侦察专用部分

### 状态
**证实**（部分指标确为侦察专用；`_content_hash` 只能检测身份字段剔除后完全相同的输入）。

### C6-1 `dataset_audit.audit_dataset` 的指标分类

`swarm_sim/dataset_audit.py:84-136` 收集的全部指标：

| 指标 | 位置 | 是否侦察专用 |
|------|------|-------------|
| `episode_duration_s` | :84 | 通用 |
| `observation_valid_fraction` | :85 | 通用 |
| `truth_valid_fraction` | :86 | 通用 |
| **`global_coverage_ratio`** | :91 | **侦察专用**（区域覆盖是 `area_coverage` 目标的度量） |
| **`repeated_coverage_cell_ratio`** | :92 | **侦察专用**（重复覆盖是 lawnmower 多机冗余的度量） |
| `executed_path_length_m` | :102 | 通用 |
| `airborne_time_s` | :103 | 通用 |
| `executed_stage_count` | :115 | 半通用：阶段数在 v2 下等于航点数（1 节），对任何"逐航点分阶段"的意图都成立 |
| `barrier_wait_s` | :117 | 通用（屏障机制与意图无关） |
| `scheduling_wait_s` | :118 | 通用 |
| **`region_width_m` / `region_height_m`** | :122-123 | **侦察专用**（单矩形共享区域是 v2 schema 的强制结构） |
| `speed_m_s` | :124 | 通用 |
| **`partition_axes`** | :125 | **侦察专用**（`partition_axis` 只对条带剖分有意义） |
| `return_choices` | :126 | 通用 |
| **`spawn_east_span_m` / `spawn_north_span_m`** | :134-135 | 半通用：度量起点散布，但当前采样器把它们绑到条带上（C5-1） |

**整段侦察专用的结构**：

`swarm_sim/dataset_audit.py:119-131`（原样摘录）:

```python
        if task.get("schema_version") == 2:
            scenario = task["scenario"]
            target = next((r for r in scenario["regions"] if r["id"] == task["mission"]["target_region_id"]), {})
            metrics["region_width_m"].append(target.get("width_m"))
            metrics["region_height_m"].append(target.get("height_m"))
            metrics["speed_m_s"].append(task["execution"]["speed_m_s"])
            axes[task["planner"]["partition_axis"]] += 1
            return_choices[str(task["mission"]["return_required"]).lower()] += 1
            # Coarse bins are only a simple template concentration diagnostic.
            signature = (len(episode["agent_ids"]), task["planner"]["partition_axis"],
                         round(target.get("width_m", 0) / 10), round(target.get("height_m", 0) / 10),
                         task["mission"]["return_required"])
            template_counts[str(signature)] += 1
```

粗签名 `signature` 含 `partition_axis` 与区域尺寸分箱，是 lawnmower 拓扑的指纹；`diversity.coarse_template_counts` 与 `largest_coarse_template_fraction`（:166-168）都建立在该签名上。

**另有 2 处把侦察专用指标写成了硬性要求**：

`swarm_sim/dataset_audit.py:173-175`（原样摘录）:

```python
        missing_metrics=[key for key in ("global_coverage_ratio", "barrier_wait_s", "executed_path_length_m")
                         if not _distribution(metrics[key])["count"]],
        limitation="single mission class; no classification accuracy or claim of intention identifiability; coarse bins do not identify all near-duplicates")
```

`missing_metrics` 把 `global_coverage_ratio` 列为**必需指标**；`limitation` 字段自身声明 `single mission class`。

**通用的部分**：`rates`（:151-158）、`splits` / `family_split_leaks`（:142-144）、`clock_grades`、`protocols`、`duplicates`、`issues`、资格计数——这些与任务类型无关。

### C6-2 `_content_hash` 的检测能力

`swarm_sim/dataset_audit.py:33-39`（原样摘录）:

```python
def _content_hash(task):
    task = copy.deepcopy(task)
    if isinstance(task, dict):
        for name in ("task_id", "family_id", "seed"):
            task.pop(name, None)
        task.get("scenario", {}).pop("scene_id", None)
    return canonical_hash(task)
```

- 剔除的字段恰为 **4 个**：`task_id`、`family_id`、`seed`（顶层）与 `scenario.scene_id`。
- 输出用于 `dataset_audit.py:136` 的 `input_hashes[_content_hash(task)] += 1`，并在 :170-171 只报告计数 `> 1` 的组：

```python
        duplicates=dict(normalized_input_groups={k: v for k, v in input_hashes.items() if v > 1},
                        identity_fields_excluded=["task_id", "family_id", "seed", "scene_id"]),
```

**结论：只能检测"剔除这 4 个身份字段后完全逐字节相同"的输入。** 任何非身份字段的微小差异（例如区域平移 1 cm、速度 3.0 → 3.01、`tracking_margin_m` 1.0 → 1.01）都会产生不同的哈希，因此**近重复一概检不出**。这与 `limitation` 字段中 `coarse bins do not identify all near-duplicates` 的自述一致。

### 对 v0.4 的影响
- 引入 Patrol 后，`missing_metrics` 会把 Patrol 数据集的 `global_coverage_ratio` 报为缺失（因为 Patrol 不产生覆盖证据），从而在审计中呈现为"缺指标"而非"不适用"。
- `diversity` 的三个子项（`vehicle_counts` 通用，`partition_axes` 与 `coarse_template_counts` 侦察专用）在混合数据集上会把两类意图的拓扑混在同一个计数器里。
- `_content_hash` 的近重复检测能力为"精确重复"级别，不覆盖参数微抖动；若 v0.4 依赖它来量化跨类别重复度，需要另建指标。

---

## C7 样本资格的粒度

### 状态
**证实**：`benchmark_eligible` **只在 episode 级定义**，不存在窗口级或前缀级资格字段。

### 证据

**定义处**（唯一）：`swarm_sim/quality.py:82-88`（原样摘录）:

```python
def eligibility(quality, mission_success):
    other_checks = (quality["data_quality_pass"] and quality["truth_available_pass"] and
                    quality["run_completed"] and quality["separation_status"] == "clear_observed" and
                    quality["truth_separation"]["status"] == "clear_observed" and mission_success is True)
    grade = quality["clock_quality"]["overall"]
    return dict(benchmark_eligible=bool(other_checks and grade in ("strict", "acceptable")),
                strict_benchmark_eligible=bool(other_checks and grade == "strict"))
```

**唯一调用点**：`swarm_sim/analysis.py:206` `quality.update(eligibility(quality, labels["mission_success"]))`，其后在 `analysis.py:209-211` 追加 v2 专属条件：

```python
        additional = (quality["execution_constraints_pass"] is True and
                      labels["semantic_consistency"] == "agree" and labels["mission_success_observation"] is True)
        quality["benchmark_eligible"] &= additional
        quality["strict_benchmark_eligible"] &= additional
```

**`mission_success` 在资格判断中的位置**：

| 层次 | 位置 | 角色 |
|------|------|------|
| 语义标签 | `mission_evaluation.py:270` `mission_success=left`（SIM truth 通道）、`:270` `mission_success_observation=right`（FCU 通道） | 生成两个通道的布尔/None |
| **资格判据（硬门禁）** | `quality.py:85` `mission_success is True` | `other_checks` 的第 6 项；为 `False` **或 `None`** 均使 `benchmark_eligible=False` |
| **资格判据（仅 v2 追加）** | `analysis.py:209-210` `labels["mission_success_observation"] is True` 与 `semantic_consistency == "agree"` | 观测通道须同样为 True，且两通道一致 |
| 打包进 episode | `analysis.py:242-243` → `manifest.json` 的 `benchmark_eligible` / `strict_benchmark_eligible` | 单布尔值 |
| 数据集层再收紧 | `dataset.py:72` `benchmark_eligible=bool(family) and manifest["benchmark_eligible"]` | 追加"必须有 family_id" |
| 审计层读取 | `dataset_audit.py:81-82,139,157-158` | 计数与比率，分母 `len(entries)` |

**全部 `eligible` 字段出现处**（`grep -rn "eligible" swarm_sim/`，共 17 处）：
`analysis.py:206,210,211,242,243`、`dataset.py:50,72,73,99,100`、`dataset_audit.py:52,81,82,139,157,158`、`episode_loader.py:117`、`quality.py:87,88`、`runner.py:152,159,160,168,171`。
**全部为 episode 级**：`quality.json` / `manifest.json` 每 run 一份，`dataset_manifest.json` 每 episode 一条，`episode_loader` 把两个布尔放进 `metadata`。**没有任何窗口级（`phase_windows`）或前缀级（时间子序列）的资格字段。**

### 对 v0.4 的影响
- 资格是"整段 run 通过/不通过"的二元判断。若某个 episode 部分窗口有效、部分无效（例如中途出现数据缺口），没有表达手段，只能整段判不合格。
- `mission_success is True` 是硬门禁，`None`（证据不足）与 `False`（证据否证）的后果相同。
- v2 的资格还额外要求 `semantic_consistency == "agree"`，即真值通道与观测通道必须给出**相同**的 `mission_success`；两类意图若共用该门禁，需要两通道对两类意图都给出可比判据。

---

## 本批自检

| 编号 | 是否有对应小节 | 状态 |
|------|--------------|------|
| C1 | 有 | 完成（8 个检索串、77 处、三层写死点） |
| C2 | 有 | 完成（family_namespace 含 template_spec；3 变体干跑；100 base_id split 实测） |
| C3 | 有 | 完成（协议字段、9 个校验点、3 问逐条回答） |
| C4 | 有 | 完成（9 处 `_enum` + 4 处非枚举约束 + 3 处 schema 外分支） |
| C5 | 有 | 完成（采样器核查 4 项 + 3 布局 × 200 样本 × 2 轮 + 精确交叉检测） |
| C6 | 有 | 完成（指标分类 + `_content_hash` 能力边界） |
| C7 | 有 | 完成（唯一资格函数、唯一调用点、17 处字段全为 episode 级） |

**本批未完成项**：无。

**新增脚本与产物**：

| 文件 | 用途 |
|------|------|
| `C2_family.py` / `C2_family.json` | family_id 构造、template_spec 敏感性干跑、split 一致性 |
| `C5_dryrun.py` / `C5_dryrun.json` | 采样器核查 + 3 布局 × 200 样本（第一轮）+ 粗交叉判据 |
| `C5_dryrun2.py` / `C5_dryrun2.json` | 强制初始间距的第二轮 + 精确线段交叉检测 |
| `audit_v04/tmp/c2_*` | C2 干跑生成的 4 个完整 bundle（每个含 missions/scenes/candidates） |

---

## 更正记录

**更正 1（C1 节 与本批自检表）**

- 原文：C1 节导语 `8 个检索串在源码与测试中共出现 84 处，其中源码 26 处`；自检表 `| C1 | 有 | 完成（8 个检索串、84 处、三层写死点） |`。
- 问题：计数有误。
- 依据：逐串复核（`grep -rn --include="*.py"`，排除 `__pycache__`）：
  | 检索串 | 源码 | 合计 |
  |--------|------|------|
  | `reconnaissance` | 1 | 10 |
  | `area_coverage` | 1 | 2 |
  | `shared_coverage` | 1 | 7 |
  | `recon_` | 4 | 24 |
  | `equal_strip_lawnmower` | 2 | 2 |
  | `monotone_entry_order` | 1 | 1 |
  | `coverage_ratio` | 7 | 21 |
  | `partition_axis` | 8 | 11 |
  | **合计** | **25** | **77** |
- 改为：**77 处（源码 25 处）**；C1 节导语已同步补入逐串计数。C1 表格本身逐行列举的 77 条记录未受影响。

**更正 2（C5-1 节）**

- 原文：`补充事实：outside = -entry if side == "low" else sweep + entry —— high 分支用的是 sweep，当 axis == "north" 时区域在该方向的实际跨度是 count*strip 而非 sweep（generation.py:100,102）。这是本审查中发现的额外不一致，见第 4 节。`
- 问题：论断不成立。
- 依据：`generation.py:97` `width, height = (count * strip, sweep) if axis == "east" else (sweep, count * strip)`。
  `high` 分支的 `outside` 加在垂直于剖分轴的方向上（`generation.py:102`：`axis == "east"` 时加在 north，否则加在 east）。该方向的区域跨度恰为 `sweep`：
  - `axis == "east"`：区域北向跨度 = `height` = `sweep`
  - `axis == "north"`：区域东向跨度 = `width` = `sweep`
  故两种轴下 `sweep + entry` 都把飞机放在区域边界外恰好 `entry` 处，**不存在不一致**。
- 改为：删除该论断，替换为上述两轴一致性的说明。

**更正 3（C 组自检表措辞）**

- 说明：自检表原写 `84 处`，已改为 `77 处`（见更正 1）。
