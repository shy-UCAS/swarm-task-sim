"""Publication-style figures of exported 10 Hz evidence, with coverage receipts."""
from pathlib import Path
import numpy as np
from task_v07.io import read_json, save_json
from task_v07.expansion.sampling import INTENTS
from scripts.v07_s2_plotting import map_axes


def load(attempt, row):
    root = Path(attempt) / row['path']
    with np.load(root / 'truth_10hz.npz', allow_pickle=False) as saved:
        truth = {k: saved[k].copy() for k in ('time_us', 'p')}
        truth['agent_ids'] = saved['agent_ids'].tolist()
    return truth, read_json(root / 'public_scene.json'), read_json(root / 'task.json'), read_json(root / 'labels.json')


def draw_track(ax, truth, scene, task, labels, *, legend=True):
    map_axes(ax, scene)
    palette = ('#007f86', '#bc4b51', '#8055a6', '#c58416')
    styles = ('-', '--', '-.', ':')
    for gi, (gid, group) in enumerate(task['group_skeletons'].items()):
        for j, a in enumerate(group['members']):
            column = truth['agent_ids'].index(a)
            xy = truth['p'][:, column, :2]
            ax.plot(xy[:, 0], xy[:, 1], color=palette[gi % len(palette)], ls=styles[j % len(styles)], lw=1.1,
                    alpha=.85, label=f'{gid}: {group["execution_method"]}' if j == 0 else None)
            ax.scatter(*xy[0], color=palette[gi % len(palette)], marker='o', s=10)
            core = labels['agents'][a]['observed']['core_event']['frame_index']
            if core is not None:
                ax.scatter(*xy[core], color=palette[gi % len(palette)], marker='^', s=26, zorder=5)
            abort=labels['agents'][a]['observed']['contribution'].get('abort_observation')
            if abort and abort['turn_frame'] is not None:
                ax.scatter(*xy[abort['turn_frame']],color='#202020',marker='x',s=35,zorder=6,
                           label='Measured withdrawal turn' if j==0 else None)
            end = task['references'][a]['endpoint_enu_m'][:2]
            ax.scatter(*end, marker='*', facecolors='none', edgecolors=palette[gi % len(palette)], s=55, zorder=5)
    ax.tick_params(labelsize=8)
    if legend:
        ax.legend(loc='lower left', fontsize=7, framealpha=.94)


def topdown(attempt, row, output):
    import matplotlib.pyplot as plt
    truth, scene, task, labels = load(attempt, row)
    fig, ax = plt.subplots(figsize=(9, 8))
    draw_track(ax, truth, scene, task, labels)
    ax.set_title(f'{row["intent"]} | {row["mode"]} | {row["approach_mode"]}\n'
                 f'{row["skeleton_id"]}\n{row["group_count"]} groups; task {row["task_result"]}; '
                 f'actual minimum distance {row["minimum_separation_m"]:.3f} m', fontsize=10)
    fig.text(.08, .025, 'Abstract synthetic scene. Lines: 10 Hz truth; triangles: measured core; stars: own planned endpoints.', fontsize=8)
    fig.tight_layout(rect=(0, .05, 1, 1))
    fig.savefig(output, dpi=160)
    plt.close(fig)


def paired_timing(attempt, rows, output):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(14, 7), sharex=True, sharey=True)
    modes = ['synchronous', 'sequential']
    for ax, mode in zip(axes, modes):
        row = next(r for r in rows if r['mode'] == mode)
        _, _, task, labels = load(attempt, row)
        y, ticks, names = 0, [], []
        for gi, (gid, group) in enumerate(task['group_skeletons'].items()):
            color = ('#007f86', '#bc4b51', '#8055a6')[gi % 3]
            for a in group['members']:
                observed = labels['agents'][a]['observed']
                planned = labels['agents'][a]['assigned']['timing']
                core = observed['core_event']['t_s']
                release = task['initial_settle_s'] + planned['departure_delays_s']
                finish = observed.get('work_end_s')
                if finish is not None:
                    ax.plot([release, finish], [y, y], color=color, lw=2, alpha=.45)
                ax.scatter(release, y, marker='|', color=color, s=60)
                if core is not None:
                    ax.scatter(core, y, marker='o', color=color, s=25)
                else:
                    ax.text(release, y, ' missing core', fontsize=7, color=color)
                ax.scatter(planned['target_event_times_grid_s'], y, marker='x', color='#333333', s=30)
                ticks.append(y)
                names.append(f'{gid[-2:]} / {a}')
                y += 1
            y += .7
        ax.set_title(mode)
        ax.set_xlabel('Shared simulation time (s)')
        ax.set_yticks(ticks, names, fontsize=8)
        ax.grid(alpha=.18)
    axes[0].invert_yaxis()
    axes[0].set_xlim(left=0)
    fig.suptitle(f'{rows[0]["skeleton_id"]}\nPer-group core timing; circles measured, crosses planned, bars release', fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, .94))
    fig.savefig(output, dpi=160)
    plt.close(fig)


def render_all(attempt, records):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out = Path(attempt) / 'figures'
    out.mkdir()
    valid = [r for r in records if r['state'] == 'generated' and r.get('quality_valid') and r.get('audit_passed')]
    regular = [r for r in valid if not r.get('aborted')]
    receipts = {'topdowns': [], 'timing_pairs': [], 'abort_pairs': [], 'missing_requirements': []}
    for intent in INTENTS:
        pool = sorted([r for r in regular if r['intent'] == intent and r['mode'] == 'synchronous'],
                      key=lambda r: (r['task_result'] != 'success', r['skeleton_id']))
        chosen = []
        for predicate in (lambda r: r['group_count'] > 1, lambda r: r['approach_mode'] == 'multi_direction', lambda r: True):
            candidate = next((r for r in pool if predicate(r) and r not in chosen), None)
            if candidate is not None:
                chosen.append(candidate)
            if len(chosen) >= 2 and any(r['group_count'] > 1 for r in chosen) and any(r['approach_mode'] == 'multi_direction' for r in chosen):
                break
        for index, row in enumerate(chosen):
            name = f'{intent}_{index + 1}.png'
            topdown(attempt, row, out / name)
            receipts['topdowns'].append({'figure': name, 'episode_id': row['episode_id'],
                                         'multiple_groups': row['group_count'] > 1, 'multi_direction': row['approach_mode'] == 'multi_direction'})
        if len(chosen) < 2 or not any(r['group_count'] > 1 for r in chosen) or not any(r['approach_mode'] == 'multi_direction' for r in chosen):
            receipts['missing_requirements'].append({'intent': intent, 'requirement': 'two topdowns including multiple groups and multiple approach directions',
                                                      'reason': 'insufficient retained generated evidence; rejected samples are not plotted as successful trajectories'})
    pairs = []
    for sid in sorted({r['skeleton_id'] for r in regular}):
        pair = [r for r in regular if r['skeleton_id'] == sid]
        if len(pair) == 2:
            pairs.append(pair)
    pairs.sort(key=lambda pair: (pair[0]['group_count'] <= 1, pair[0]['task_result'] != 'success', pair[0]['skeleton_id']))
    for index, pair in enumerate(pairs[:2]):
        name = f'paired_timing_{index + 1}.png'
        paired_timing(attempt, pair, out / name)
        receipts['timing_pairs'].append({'figure': name, 'skeleton_id': pair[0]['skeleton_id'], 'group_count': pair[0]['group_count']})
    if len(pairs) < 2 or not any(p[0]['group_count'] > 1 for p in pairs[:2]):
        receipts['missing_requirements'].append({'requirement': 'two timing pairs including one multiple-group pair', 'reason': 'insufficient retained pairs'})
    aborted = next((r for r in valid if r.get('aborted') and r.get('source_episode_id') and r.get('abort_observation_valid')), None)
    source = next((r for r in regular if aborted and r['episode_id'] == aborted['source_episode_id']), None)
    if source is not None:
        fig, axes = plt.subplots(1, 2, figsize=(16, 8))
        for ax, row, title in zip(axes, [source, aborted], ['Referenced regular synchronous episode', 'Abort of main group; other groups unchanged']):
            draw_track(ax, *load(attempt, row))
            ax.set_title(title, fontsize=11)
        fig.tight_layout()
        fig.savefig(out / 'abort_vs_regular.png', dpi=160)
        plt.close(fig)
        receipts['abort_pairs'].append({'figure': 'abort_vs_regular.png', 'regular': source['episode_id'], 'aborted': aborted['episode_id']})
    else:
        receipts['missing_requirements'].append({'requirement': 'abort and referenced regular side by side', 'reason': 'no retained abort/reference pair'})
    save_json(out / 'figure_coverage.json', receipts)
    return receipts
