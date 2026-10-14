"""Read-only sampling and shortcut audit of an existing S2 attempt.

This tool does not import planners, relabel trajectories, or run simulations.
It writes new statistical evidence; existing attempts remain untouched.
"""
import argparse
import ast
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import sklearn
import scipy
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix
from sklearn.tree import DecisionTreeClassifier


INTENTS = ("transit", "reconnaissance", "monitoring", "feint", "penetration")
NAMES = dict(zip(INTENTS, ("过境", "侦察", "游弋监视", "佯动", "突防")))
SIZE_BINS = ("2–3", "4–6", "7以上")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def size_bin(n):
    if n < 2:
        raise ValueError(f"Unexpected group size {n}")
    return SIZE_BINS[0] if n <= 3 else SIZE_BINS[1] if n <= 6 else SIZE_BINS[2]


def successful_pair(rows):
    return (len(rows) == 2 and {r["mode"] for r in rows} == {"synchronous", "sequential"}
            and all(r["state"] == "generated" and r["task_result"] == "success"
                    and r["quality_valid"] and r["audit_passed"] for r in rows))


def candidate_reasons(detail):
    """Decode saved nested Counter representations without evaluating code."""
    start = detail.find("{")
    if start < 0:
        return Counter({detail: 1})
    try:
        parsed = ast.literal_eval(detail[start:])
    except (SyntaxError, ValueError):
        return Counter({detail: 1})
    if not isinstance(parsed, dict):
        return Counter({detail: 1})
    result = Counter()
    for key, count in parsed.items():
        if not isinstance(count, int) or count < 0:
            return Counter({detail: 1})
        nested = candidate_reasons(str(key)) if "{" in str(key) else Counter({str(key): 1})
        for reason, occurrences in nested.items():
            result[reason] += count * occurrences
    return result


def matrix(descriptors, rows_by_id, facilities, attempt, dimension, values):
    def categories(d):
        if dimension == "approach_mode":
            return {d["common_draw"]["approach_mode"]}
        if dimension == "facility_count":
            return {str(facilities[d["family_id"]])}
        if dimension == "group_count":
            return {str(len(d["task_groups"]))}
        return {size_bin(len(g["members"])) for g in d["task_groups"]}

    result = []
    for intent in INTENTS:
        for value in values:
            selected = [d for d in descriptors if d["base_intent"] == intent and value in categories(d)]
            ids = [d["skeleton_id"] for d in selected]
            successes = [sid for sid in ids if successful_pair(rows_by_id[sid])]
            categories_count, details = Counter(), []
            reason_counts = Counter()
            for sid in ids:
                if sid in successes:
                    continue
                rows = rows_by_id[sid]
                rejected = next((r for r in rows if r["state"] == "infeasible"), None)
                category = rejected["reason"] if rejected else ("generation_error" if any(
                    r["state"] == "generation_error" or r.get("quality_valid") is False for r in rows
                ) else "non_successful_pair")
                categories_count[category] += 1
                evidence = []
                history = rejected.get("geometry_attempts", []) if rejected else []
                for entry in history:
                    path = attempt / sid / f"geometry_{entry['geometry_variant']:02d}" / "planning_rejection.json"
                    saved = read(path)
                    if saved != entry:
                        raise ValueError(f"Record and saved rejection differ: {path}")
                    reason_counts.update(candidate_reasons(entry["detail"]))
                    evidence.append({"path": str(path), "sha256": digest(path), "saved": saved})
                details.append({"skeleton_id": sid, "category": category,
                                "recorded_candidate_rejections": evidence})
            result.append({"intent": intent, "dimension": dimension, "value": value,
                           "registered": len(ids), "successful": len(successes),
                           "fraction": len(successes) / len(ids) if ids else None,
                           "successful_skeleton_ids": successes, "skeleton_ids": ids,
                           "failure_categories_skeleton_count": dict(categories_count),
                           "saved_candidate_reason_counts": dict(reason_counts.most_common()),
                           "failure_evidence": details})
    return result


def shortcut_cv(records, facilities):
    """Fixed shallow tree, no tuning; leave one complete family out."""
    ids = [r["episode_id"] for r in records]
    families = np.array([r["family_id"] for r in records])
    targets = np.array([r["intent"] for r in records])
    features = {
        "duration_only": np.array([[r["duration_s"]] for r in records], dtype=float),
        "approach_group_facility_only": np.array([
            [int(r["approach_mode"] == "multi_direction"), r["group_count"], facilities[r["family_id"]]]
            for r in records], dtype=float),
    }
    result = {}
    for name, x in features.items():
        predictions, folds, majorities = np.full(len(records), "", dtype=object), [], np.full(len(records), "", dtype=object)
        for family in sorted(set(families)):
            test = families == family
            train = ~test
            if set(families[train]) & set(families[test]):
                raise ValueError("Family leakage")
            model = DecisionTreeClassifier(max_depth=2, min_samples_leaf=3, random_state=0)
            model.fit(x[train], targets[train])
            predictions[test] = model.predict(x[test])
            # Independent traversal checks the exported model's predictions.
            manual = []
            for sample in x[test].astype(np.float32):
                node = 0
                while model.tree_.children_left[node] != model.tree_.children_right[node]:
                    node = (model.tree_.children_left[node] if sample[model.tree_.feature[node]] <= model.tree_.threshold[node]
                            else model.tree_.children_right[node])
                manual.append(model.classes_[np.argmax(model.tree_.value[node][0])])
            if not np.array_equal(manual, predictions[test]):
                raise ValueError('Independent tree traversal differs')
            majority = Counter(targets[train]).most_common(1)[0][0]
            majorities[test] = majority
            folds.append({"held_out_family": family, "train_n": int(train.sum()), "test_n": int(test.sum()),
                          "accuracy": accuracy_score(targets[test], predictions[test]),
                          "test_class_counts": dict(Counter(targets[test])),
                          "train_class_counts": dict(Counter(targets[train])),
                          "majority_prediction": majority,
                          "majority_baseline_accuracy": accuracy_score(targets[test], majorities[test])})
        if any(p == "" for p in predictions):
            raise ValueError("Unassigned out-of-family prediction")
        result[name] = {"classifier": "DecisionTreeClassifier(max_depth=2, min_samples_leaf=3, random_state=0)",
                        "feature_names": ["duration_s"] if name == "duration_only" else
                            ["multi_direction_indicator", "merged_group_count", "map_facility_count"],
                        "accuracy": accuracy_score(targets, predictions),
                        "balanced_accuracy": balanced_accuracy_score(targets, predictions),
                        "family_macro_accuracy": float(np.mean([f["accuracy"] for f in folds])),
                        "majority_baseline_accuracy": accuracy_score(targets, majorities),
                        "uniform_five_class_reference": .2, "independent_prediction_traversal": "PASS",
                        "confusion_matrix": confusion_matrix(targets, predictions, labels=INTENTS).tolist(),
                        "confusion_matrix_label_order": INTENTS, "folds": folds,
                        "predictions": [{"episode_id": ids[i], "family_id": families[i], "actual": targets[i],
                                         "prediction": predictions[i], "features": x[i].tolist()}
                                        for i in range(len(records))]}
    return result


def pct(x):
    return "未登记" if x is None else f"{100*x:.2f}%"


def table(headers, rows):
    def escape(x):
        return str(x).replace("|", "\\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(map(escape, headers)) + " |", "|" + "---|" * len(headers),
                       *["| " + " | ".join(map(escape, row)) + " |" for row in rows]])


def render_report(data, output):
    lines = ["# S2 第二段现有数据：抽样偏差与捷径审计", "",
             f"来源 attempt：`{data['source_attempt']}`；冻结生成提交：`{data['source_generator_commit']}`。",
             "本报告只读取已有结果，没有修改规划器、判据、标签或随机流，没有重新仿真。A–C 及航线候选扩展未实施，因此没有修订后的结果；不得将本报告作为本轮完整修订的验收报告。",
             "", "## 1. 分母与复核口径", "",
             "骨架成功要求同步、递次两版均生成、任务成功、质量有效且独立审计通过。分母为全部 60 个登记常规骨架。",
             "任务组规模按合并后组成员数分档：骨架含某档任务组就计入该档一次；含不同档任务组的骨架会跨档重复，三档不得相加作为总样本数。另提供以任务组为单位的补充表。",
             "保留轨迹与捷径检查采用质量有效且独立审计通过的常规单条轨迹，排除中止、诊断、规划拒绝和生成错误。两个时序版本始终在同一个 family 留出折中。",
             "", "## 2. 修订前骨架成功率矩阵", ""]
    labels = {"approach_mode": "逼近方式", "facility_count": "地图设施数", "group_count": "合并后任务组数", "group_size_bin": "任务组规模"}
    for dimension, values in data["matrices"].items():
        lines += [f"### 意图 × {labels[dimension]}", "", table(
            ["意图", labels[dimension], "成功/登记", "成功率"],
            [[NAMES[r["intent"]], r["value"], f"{r['successful']}/{r['registered']}", pct(r["fraction"])] for r in values]), ""]
    lines += ["任务组口径补充（成功仍要求所属整个骨架两版成功）：", "", table(
        ["意图", "成员数", "成功组/登记组", "比例"],
        [[NAMES[r['intent']], r['size_bin'], f"{r['successful']}/{r['registered']}", pct(r['fraction'])]
         for r in data['group_weighted_size']]), "", "## 3. 零成功组合与保存的拒绝证据", "",
        "只列有登记骨架但成功数为 0 的组合；未抽中的组合标为“未登记”，不计零成功。以下是已保存原因的统计，不表示地图数学上无解。",
        "最终类别按骨架计数；候选原因是解析已保存嵌套计数后的出现次数，不是独立骨架数，不用于跨角色比较拒绝概率。相同骨架可能出现在多个交叉表中。", ""]
    for row in data['zero_success_combinations']:
        reasons = list(row['saved_candidate_reason_counts'].items())[:3]
        reason_text = "；".join(f"`{k}` × {v}" for k, v in reasons) or "没有规划拒绝记录；见最终质量/结果类别"
        lines += [f"- **{NAMES[row['intent']]} × {labels[row['dimension']]}={row['value']}**：0/{row['registered']}。"
                  f"最终类别 `{json.dumps(row['failure_categories_skeleton_count'], ensure_ascii=False)}`；保存的主要原因：{reason_text}。"]
    lines += ["", f"逐骨架记录、每次拒绝原文、来源路径和 SHA256 见 [diagnostics.json](<{(output / 'diagnostics.json').as_posix()}>)。",
              "", "## 4. 保留轨迹中的意图与逼近方式", "", table(
        ["意图", "同向条数/该意图总数", "同向比例", "多向条数/该意图总数", "多向比例"],
        [[NAMES[r['intent']], f"{r['same_direction']}/{r['total']}", pct(r['same_fraction']),
          f"{r['multi_direction']}/{r['total']}", pct(r['multi_fraction'])] for r in data['retained_proportions']]),
              "", "同一意图两种方式的骨架成功率差（绝对百分点）：", "", table(
        ["意图", "同向成功率", "多向成功率", "绝对差（百分点）"],
        [[NAMES[r['intent']], pct(r['same']), pct(r['multi']), f"{r['absolute_gap_pp']:.2f}"] for r in data['approach_gaps']]),
              "", "侦察包含两种方法，不能用合并后的侦察比例掩盖方法内部缺口。下表按含该角色的骨架去重，成功要求整个骨架成功：", "", table(
        ["角色/方法", "逼近方式", "成功/登记骨架"],
        [[r['role'], r['approach'], f"{r['successful']}/{r['registered']}"] for r in data['role_approach']]),
              "", "方法级零成功组合的保存原因（计数口径同第 3 节）：", "",
              *[f"- `{r['role']} × {r['approach']}`：" + "；".join(f"`{k}` × {v}" for k, v in list(r['saved_candidate_reason_counts'].items())[:3])
                for r in data['role_approach'] if r['registered'] and not r['successful']],
              "", "## 5. 按 family 留出的快速捷径检查", "",
              "固定浅层决策树：`max_depth=2, min_samples_leaf=3, random_state=0`；不调参、不看测试折拟合。每次留出一个完整 family，共 6 折。两项分别单独训练。",
              "时长指模拟时间轴 `duration_s`，不使用受机器负载影响的墙钟时间。组合特征仅为逼近方式、合并后任务组数与地图设施数。准确率按全部留出预测汇总；同时报告宏平均召回率和按 family 平均准确率。",
              f"样本量 {data['retained_n']}，类别计数 `{json.dumps(data['retained_class_counts'], ensure_ascii=False)}`。五类均匀随机参考为 20%，类别不均衡时它不是最强的无特征基线；因此额外报告仅用训练折多数类的基线。", "", table(
        ["特征", "留出准确率", "宏平均召回率", "family 平均准确率", "训练折多数类基线", "五类随机参考"],
        [[name, pct(r['accuracy']), pct(r['balanced_accuracy']), pct(r['family_macro_accuracy']),
          pct(r['majority_baseline_accuracy']), "20.00%"] for name, r in data['shortcut_cv'].items()]), ""]
    for name, result in data['shortcut_cv'].items():
        lines += [f"### {name}：逐折", "", table(
            ["留出 family", "训练数", "测试数", "准确率", "多数类基线"],
            [[r['held_out_family'], r['train_n'], r['test_n'], pct(r['accuracy']), pct(r['majority_baseline_accuracy'])]
             for r in result['folds']]), "", "混淆矩阵：行是真实类别，列是预测类别。", "", table(
            ["真实\\预测", *[NAMES[x] for x in INTENTS]],
            [[NAMES[intent], *counts] for intent, counts in zip(INTENTS, result['confusion_matrix'])]), ""]
    lines += ["以上只作诊断，不设通过门槛。六个 family 的结果不能证明更广泛地图分布上的泛化能力；单一特征具有预测力也不等于已证明因果捷径。",
              "运行环境提示：现有 SciPy 声明支持 NumPy <2.3，而项目环境为 NumPy 2.5.3，导入时产生兼容性警告。本次未更改项目依赖；树模型完成全部拟合和预测，并逐折用独立节点遍历核对预测一致。该检查不能替代依赖兼容性认证。", "",
              "## 6. 主对照与交叉否定基线", "", table(
        ["项目", "修订前", "修订后"],
        [["主对照视图条数", data['baseline_counts']['primary'], "未运行"],
         ["交叉否定实际执行项", data['baseline_counts']['cross_executed'], "未运行"],
         ["交叉否定 not_run", data['baseline_counts']['cross_not_run'], "未运行"]]),
              "", "本次仅新增离线审计脚本、报告和统计证据。未修改共享规划代码或 `labels.measure`，未重跑固定回归、全量请求或交叉否定，未更新任何既有基准。",
              "", f"[来源文件哈希与验证记录](<{(output / 'provenance.json').as_posix()}>)。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.report.exists():
        raise FileExistsError("Use new output/report paths")
    attempt = args.attempt.resolve()
    registration = read(attempt / "registration.json")
    infra = Path(registration['source_attempt'])
    source_paths = [attempt / name for name in ('registration.json', 'episode_records.json', 'view_index.json', 'cross_negation.json')]
    source_paths += [infra / name for name in ('registration.json', 'private_skeleton_descriptors.json')]
    before_hashes = {str(p): digest(p) for p in source_paths}
    descriptors = [d for d in read(infra / 'private_skeleton_descriptors.json') if d['subset'] == 'regular' and not d.get('diagnostic_only')]
    records = [r for r in read(attempt / 'episode_records.json') if not r.get('aborted') and not r.get('diagnostic_only')]
    if len(descriptors) != 60 or len(records) != 120 or len({r['episode_id'] for r in records}) != 120:
        raise ValueError('Expected 60 skeletons / 120 unique regular requests')
    facilities = {r['family_id']: r['facility_count'] for r in read(infra / 'registration.json')['selected']}
    by_id = defaultdict(list)
    for row in records:
        by_id[row['skeleton_id']].append(row)
    dimensions = {'approach_mode': ('same_direction', 'multi_direction'), 'facility_count': ('1', '2', '3'),
                  'group_count': ('1', '2', '3'), 'group_size_bin': SIZE_BINS}
    matrices = {key: matrix(descriptors, by_id, facilities, attempt, key, values) for key, values in dimensions.items()}
    for key in ('approach_mode', 'facility_count', 'group_count'):
        if sum(r['registered'] for r in matrices[key]) != 60:
            raise ValueError('Matrix denominator mismatch')
    retained = [r for r in records if r['state'] == 'generated' and r['quality_valid'] and r['audit_passed']]
    proportions, gaps, sizes, roles = [], [], [], []
    for intent in INTENTS:
        counts = Counter(r['approach_mode'] for r in retained if r['intent'] == intent)
        total = counts.total()
        proportions.append({'intent': intent, **{k: counts[k] for k in dimensions['approach_mode']}, 'total': total,
                            'same_fraction': counts['same_direction']/total if total else None,
                            'multi_fraction': counts['multi_direction']/total if total else None})
        values = {r['value']: r['fraction'] for r in matrices['approach_mode'] if r['intent'] == intent}
        gaps.append({'intent': intent, 'same': values['same_direction'], 'multi': values['multi_direction'],
                     'absolute_gap_pp': 100*abs(values['same_direction']-values['multi_direction'])})
        for size in SIZE_BINS:
            selected = [(d, g) for d in descriptors if d['base_intent'] == intent for g in d['task_groups'] if size_bin(len(g['members'])) == size]
            successes = sum(successful_pair(by_id[d['skeleton_id']]) for d, _ in selected)
            sizes.append({'intent': intent, 'size_bin': size, 'registered': len(selected), 'successful': successes,
                          'fraction': successes/len(selected) if selected else None})
    for role in sorted({g['execution_method'] for d in descriptors for g in d['task_groups']}):
        for approach in dimensions['approach_mode']:
            selected = [d for d in descriptors if d['common_draw']['approach_mode'] == approach and any(g['execution_method'] == role for g in d['task_groups'])]
            reasons = Counter()
            for d in selected:
                rejected_row = next((r for r in by_id[d['skeleton_id']] if r['state'] == 'infeasible'), None)
                for entry in rejected_row.get('geometry_attempts', []) if rejected_row else []:
                    reasons.update(candidate_reasons(entry['detail']))
            roles.append({'role': role, 'approach': approach, 'registered': len(selected),
                          'saved_candidate_reason_counts': dict(reasons.most_common()),
                          'successful': sum(successful_pair(by_id[d['skeleton_id']]) for d in selected)})
    cross = read(attempt / 'cross_negation.json')
    views = read(attempt / 'view_index.json')
    data = {'source_attempt': str(attempt), 'source_generator_commit': registration['commit'], 'matrices': matrices,
            'zero_success_combinations': [r for rows in matrices.values() for r in rows if r['registered'] and not r['successful']],
            'group_weighted_size': sizes, 'role_approach': roles, 'retained_proportions': proportions, 'approach_gaps': gaps,
            'retained_n': len(retained), 'retained_class_counts': dict(Counter(r['intent'] for r in retained)),
            'shortcut_cv': shortcut_cv(retained, facilities), 'baseline_counts': {'primary': views['counts']['primary'],
                'cross_executed': sum(r['status'] != 'not_run' for r in cross['rows']),
                'cross_not_run': sum(r['status'] == 'not_run' for r in cross['rows'])}}
    after_hashes = {str(p): digest(p) for p in source_paths}
    if before_hashes != after_hashes:
        raise ValueError('Source evidence changed during audit')
    args.output.mkdir(parents=True, exist_ok=False)
    write(args.output / 'diagnostics.json', data)
    provenance = {'created_utc': datetime.now(timezone.utc).isoformat(), 'source_sha256': before_hashes,
                  'sources_unchanged': True, 'simulation_runs': 0, 'registered_skeletons': len(descriptors),
                  'regular_requests': len(records), 'retained_episodes': len(retained), 'family_folds': 6,
                  'numpy_version': np.__version__, 'sklearn_version': sklearn.__version__, 'scipy_version': scipy.__version__,
                  'environment_warning': 'Installed SciPy requests NumPy <2.3; NumPy 2.5.3 is installed. Dependencies unchanged.',
                  'audit_code_sha256': digest(__file__),
                  'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()}
    write(args.output / 'provenance.json', provenance)
    args.report.write_bytes(render_report(data, args.output.resolve()).encode('utf-8'))
    print(json.dumps({'report': str(args.report.resolve()), 'output': str(args.output.resolve()),
                      'zero_success_combinations': len(data['zero_success_combinations']),
                      'shortcut_accuracy': {k: v['accuracy'] for k, v in data['shortcut_cv'].items()},
                      'baseline_counts': data['baseline_counts']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
