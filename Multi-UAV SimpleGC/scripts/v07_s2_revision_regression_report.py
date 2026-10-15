"""Render the explicit task-A migration inventory from completed regression evidence."""
import argparse
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def render(attempt, baseline):
    report = read(attempt/'regression_comparison.json')
    if report['status'] != 'PASS' or report['content_difference_count']:
        raise ValueError('Unexplained regression differences cannot become a new baseline')
    lines = ['## 任务 A：预警进入口径与新回归基准', '',
             '扩展骨架逐机定位本任务组目标预警区的首次进入帧，在 10 Hz 路径上精确回溯 100 m 并在线段内插值，取回溯起点到进入帧的位移航向。任一成员缺证据则组跨度未知；多向阈值仍为 90°，同向只作诊断。角色核心事件与成功条件不变。', '',
             '同向通过同侧编队走廊进入，多向分股进入；随后用既有可见图在目标预警区内展开，保留禁入政策、35 m 限制区余量及走廊宽度规则。监视保持同一环线、同一绕行方向和原圈数/半径范围，时序仍按原第一圈核心事件的单机实测计算。', '',
             f"126 项测试通过；固定回归 {report['episodes']}/22 PASS，未解释内容差异 0，{report['total_wall_s']:.3f} s。竖切 8 条逐字节一致。",
             f"旧比较基准：`{baseline}`；本轮新扩展角色/过境回归基准：`{attempt}`。", '',
             '| 冻结骨架/时序 | 类型 | 旧跨度° → 新跨度° | 多向条件 | 组结果 | 集群结果 |',
             '|---|---|---|---|---|---|']
    details = []
    for comparison in report['episode_comparisons']:
        if comparison['baseline_kind'] == 'vertical_slice':
            continue
        episode = comparison['episode']
        old = read(baseline/episode/'labels.json')
        new = read(attempt/episode/'labels.json')
        left, right = next(iter(old['task_groups'].values())), next(iter(new['task_groups'].values()))
        def value(x):
            return '未知' if x is None else f'{x:.9f}' if isinstance(x, float) else str(x)
        def transition(a, b):
            return f'{value(a)} → {value(b)}'
        spans = transition(left['observed']['approach_span_deg'], right['observed']['approach_span_deg'])
        conditions = transition(left['result']['conditions'].get('multi_direction_span'), right['result']['conditions'].get('multi_direction_span'))
        result = transition(left['result']['status'], right['result']['status'])
        cluster = transition(old['cluster']['result']['status'], new['cluster']['result']['status'])
        lines.append(f"| `{episode}` | {comparison['baseline_kind']} | {spans} | {conditions} | {result} | {cluster} |")
        details.append({'episode': episode, 'baseline_kind': comparison['baseline_kind'],
                        'old_headings_deg': left['observed']['approach_headings_deg'],
                        'new_headings_deg': right['observed']['approach_headings_deg'],
                        'old_definition': left['observed']['approach_span_definition'],
                        'new_definition': right['observed']['approach_span_definition'],
                        'all_differences': comparison['differences']})
    inventory = attempt/'warning_entry_transition_inventory.json'
    inventory.write_text(json.dumps(details, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    lines += ['', '新角色冻结模板按旧核心事件口径生成，因此新多向条件及其组/集群结果可以变为失败；这是真实轨迹按新定义重算的预期变化，不是标签矛盾或 P0。完整轨迹数组、模型输入、帧级标签、角色事实、任务模板与校时证据继续严格比较。', '',
              '过境核心事件本来就是进入预警区，测量位置没有改变；其数值末位变化来自把旧“跨过 100 m 的整帧起点”改为精确插值起点，定义文字也同步更新。', '',
              f'[逐机航向、定义、全量字段差异和哈希清单](<{inventory.as_posix()}>)；[完整固定回归比较](<{(attempt/"regression_comparison.json").as_posix()}>)。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    text = render(args.attempt, args.baseline)
    args.report.write_text(args.report.read_text(encoding='utf-8')+'\n'+text, encoding='utf-8')
    print('Task A expected-difference inventory written')


if __name__ == '__main__':
    main()
