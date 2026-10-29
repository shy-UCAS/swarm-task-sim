"""Regenerate the selected PPT media from read-only, completed evidence.

Run serially in the project's llm environment; no simulator or package install.
The cover frame is a complete overview, followed by a labelled rewind to zero.
All event clocks are measured; the shared clock never normalizes each episode.
"""
import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import uuid
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import viz2_render as old
from viz2_inspect import replay

av, vp = old.av, old.vp
OUT = old.OUT_ROOT
BG, INK, MUTED, TEAL, ORANGE = old.BACKGROUND, old.TEXT, old.SECONDARY, old.PRIMARY, old.ACCENT
COLORS = av.GROUP_COLORS
AUDIT = {'iteration': 2, 'iteration_changes': [
    'Remove figure-level top titles and subtitles, keep footnotes',
    'Enlarge equally scaled maps and reduce horizontal panel spacing',
    'B canvas 1500x1200; preserve legend and overview cover',
    'D left column 35 percent; independent cumulative-distance speed curves',
    'Preserve the prior time-based D image byte-for-byte'], 'issues_fixed': [
    'B manifest lookup omitted mode and selected sequential episodes',
    'B/C only replayed a short late interval, omitting core events and complete scans',
    'A rebuilt a legacy 35 m graph rather than using the selected unified replay',
    'C labels clipped at left edge and row identities changed with event sorting',
    'B caption incorrectly asserted identical role partitions across all intents',
    'D small maps and unlabelled mean curves obscured the comparison'],
    'files': {}, 'sources_sha256': {}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(path):
    path = Path(path)
    AUDIT['sources_sha256'][str(path)] = sha(path)
    return path


def read(path):
    return old.read_json(record(path))


def setup():
    vp.setup()
    from matplotlib import rcParams, font_manager
    font = font_manager.findfont('Microsoft YaHei', fallback_to_default=False)
    AUDIT['font'] = font
    rcParams.update({'font.size': 11, 'text.color': INK, 'axes.labelcolor': INK,
                     'axes.titlecolor': INK, 'figure.facecolor': BG,
                     'axes.facecolor': BG, 'savefig.facecolor': BG})


def guard():
    root = old.PROJECT.parent
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    subprocess.run(['git', 'merge-base', '--is-ancestor', 'v0.7-first-edition-frozen', 'HEAD'],
                   cwd=root, check=True)
    AUDIT['head'] = head
    p = read(old.DATA_ROOT / old.B_RUN / 'progress.json')
    record(old.DATA_ROOT / old.B_RUN / 'manifest.json')
    assert p['completed'] == p['total'] and not p['active'] and not p['pending']
    AUDIT['completed_run'] = {'run': old.B_RUN, 'completed': p['completed'], 'total': p['total']}
    reg = read(old.DATA_ROOT / old.B_RUN / 'registration.json')
    assert reg['reference_version'] == 'r3'
    AUDIT['reference_version'] = reg['reference_version']
    AUDIT['r3_config_sha256'] = reg['r3_config_sha256']
    for directory in ('task_v07', 'scene_v07', 'swarm_sim', 'configs'):
        for path in (old.PROJECT / directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                record(path)
    record(Path(__file__).with_name('animate_v07.py'))


def episode(intent, mode='synchronous'):
    directory = vp.episode_for(old.B_RUN, old.B_FAMILY, old.B_SLOT, intent, mode)
    for name in ('truth_10hz.npz', 'task.json', 'source.json', 'labels.json', 'public_scene.json'):
        record(directory / name)
    ep = av.load_episode(directory)
    assert ep['mode'] == mode
    # Derive departures from actual displacement; never use planned delays.
    ep['departure'] = {a: vp._departure_time(ep['t'], ep['p'][:, i]) for i, a in enumerate(ep['ids'])}
    for a in ep['ids']:
        ev = ep['labels']['agents'][a]['observed'].get('core_event') or {}
        ep['core'][a] = ev.get('frame_index') if ev.get('status') == 'known' else None
    return ep


def text(fig, x, y, s, size=12, color=INK, **kwargs):
    return fig.text(x, y, s, fontsize=size, color=color, **kwargs)


def footer(fig, note=''):
    if note:
        text(fig, .025, .012, note, 9, MUTED, va='bottom')
    text(fig, .985, .012, '抽象合成场景', 9, MUTED, ha='right', va='bottom')


def map_row(fig, count, box, bottom, height, gap_px, center=.5):
    """Pack equal-aspect maps using their actual dimensions, not loose slots."""
    fw, fh = fig.get_size_inches() * fig.dpi
    width = height * fh * (box[1]-box[0]) / (box[3]-box[2]) / fw
    gap = gap_px/fw
    left = center-(count*width+(count-1)*gap)/2
    assert left >= 0 and left+count*width+(count-1)*gap <= 1
    return [fig.add_axes([left+i*(width+gap),bottom,width,height]) for i in range(count)]


def record_map_layout(fig, axes, name):
    fig.canvas.draw()
    fw,fh=fig.get_size_inches()*fig.dpi
    boxes=[[a.get_position().x0*fw,a.get_position().y0*fh,
            a.get_position().width*fw,a.get_position().height*fh] for a in axes]
    assert np.allclose([b[2:] for b in boxes],boxes[0][2:])
    assert all(np.allclose(a.get_xlim(),axes[0].get_xlim()) and
               np.allclose(a.get_ylim(),axes[0].get_ylim()) for a in axes)
    AUDIT.setdefault('layout',{})[name]={'map_bounds_px':boxes,'equal_scale_and_crop':True}


def map_base(ax, ep, box):
    av.draw_map(ax, ep['scene'], box, False)
    # Move the scale away from the tightly packed physical start locations.
    for line in list(ax.lines):
        line.remove()
    for item in list(ax.texts):
        item.remove()
    from scene_v07.geometry import to_shape
    for ent in ep['scene']['entities']:
        if ent['type'] == 'facility':
            p = to_shape(ent['geometry']).centroid
            number = int(ent['id'].split('_')[-1])
            ax.text(p.x, p.y, f'设施{number}', ha='center', va='center', fontsize=10,
                    color='white', zorder=12,
                    bbox=dict(boxstyle='round,pad=.16', fc='#3F6A85', ec='none', alpha=.93))
    x0, x1, y0, y1 = box
    bar = 500.0
    if (x1-x0) < 2200:
        bar = 200.
    bx, by = x1 - .06*(x1-x0) - bar, y0 + .048*(y1-y0)
    ax.plot([bx, bx+bar], [by, by], color=INK, lw=2, zorder=14)
    ax.text(bx+bar/2, by+.018*(y1-y0), f'{bar:.0f} m', fontsize=8, ha='center', color=INK,
            bbox=dict(fc=BG, ec='none', alpha=.8, pad=.4), zorder=14)
    for spine in ax.spines.values():
        spine.set_color('#C9D1D6')


def history_indices(k):
    # Fixed 1 s samples, plus exact current point, prevent a drifting/jagged tail.
    return np.unique(np.r_[np.arange(0, k+1, 10), k])


class Map:
    def __init__(self, ax, ep, box, title, summary=False):
        self.ax, self.ep = ax, ep
        map_base(ax, ep, box)
        ax.set_title(title, fontsize=19, pad=12, weight='bold')
        self.past, self.recent, self.dots, self.core = {}, {}, {}, {}
        for a in ep['ids']:
            color = ep['color'][a]
            self.past[a], = ax.plot([], [], color=color, lw=.95, alpha=.65, zorder=4)
            self.recent[a], = ax.plot([], [], color=color, lw=2.7, alpha=.97, zorder=5)
            self.dots[a] = ax.scatter([], [], s=44, color=color, edgecolors='white', linewidths=.9, zorder=9)
            self.core[a] = ax.scatter([], [], s=55, marker='^', color=ORANGE, edgecolors='white', linewidths=.5, zorder=8)
        self.status = ax.text(.97, .97, '', transform=ax.transAxes, ha='right', va='top', fontsize=10,
                              color=TEAL, zorder=15, bbox=dict(fc=BG, ec='none', alpha=.92, pad=3))
        self.summary = summary

    def update(self, now, cover=False):
        ep = self.ep
        k = int(np.clip(np.searchsorted(ep['t'], now, side='right')-1, 0, len(ep['t'])-1))
        start = int(np.searchsorted(ep['t'], now-75))
        for i, a in enumerate(ep['ids']):
            h = ep['p'][history_indices(k), i]
            self.past[a].set_data(h[:, 0], h[:, 1])
            self.past[a].set_linewidth(1.3 if cover else .95)
            self.past[a].set_alpha(.88 if cover else .65)
            h = ep['p'][start:k+1:3, i]
            self.recent[a].set_data(h[:, 0], h[:, 1]) if len(h) and not cover else self.recent[a].set_data([], [])
            self.dots[a].set_offsets([ep['p'][k, i]])
            departed = ep['departure'][a] is not None and now >= ep['departure'][a]
            self.dots[a].set_facecolors(ep['color'][a] if departed else BG)
            self.dots[a].set_edgecolors('white' if departed else MUTED)
            core = ep['core'][a]
            self.core[a].set_offsets([ep['p'][core, i]] if core is not None and core <= k else np.empty((0, 2)))
        if cover:
            status = f'完整轨迹 · {av.fmt_clock(ep["t"][-1])}'
        elif now >= ep['t'][-1]:
            status = f'已结束 · {av.fmt_clock(ep["t"][-1])}'
        elif self.summary:
            done = sum(v is not None and ep['t'][v] <= now for v in ep['core'].values())
            status = f'已开始作业 {done} / {len(ep["ids"])} 架'
        else:
            status = '回放中'
        self.status.set_text(status)


def remember_file(path, **extra):
    with Image.open(path) as im:
        data = {'size_px': list(im.size), 'bytes': Path(path).stat().st_size,
                'sha256': sha(path), 'frames': getattr(im, 'n_frames', 1)}
        if im.format == 'GIF':
            data['loop'] = im.info.get('loop')
    AUDIT['files'][str(path)] = {**data, **extra}


def save_static(fig, path):
    import matplotlib.pyplot as plt
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=100, facecolor=BG)
    remember_file(path)
    plt.close(fig)
    print(f'Saved {path}', flush=True)


def encode(fig, update, times, gif, first_png):
    """Quantize per frame using one palette; bounded memory, opaque disposal."""
    import matplotlib.pyplot as plt
    gif.parent.mkdir(parents=True, exist_ok=True)
    update(float(times[-1]), True)
    fig.canvas.draw()
    cover = Image.fromarray(np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy())
    palette = cover.quantize(colors=112, method=Image.Quantize.MEDIANCUT)
    # Reserve the semantic colors: rare third-group pixels must not quantize
    # to the much more common first-group pink when the canvas is tightened.
    from PIL import ImageColor
    reserved=[BG,INK,MUTED,TEAL,ORANGE,*COLORS,vp.WAIT,vp.APPROACH,vp.RETREAT,
              old.SITL_GRAY,'white',*[c for _,c,_ in av.LAYER_STYLE]]
    pal=palette.getpalette()
    for j,color in enumerate(reserved):
        pal[3*(112+j):3*(113+j)]=ImageColor.getrgb(color)
    palette.putpalette(pal)
    palette=cover.quantize(palette=palette,dither=Image.Dither.NONE)
    frames = [palette]
    palette.convert('RGB').save(first_png)
    # The saved PNG is pixel-identical to the encoded cover frame.
    checks = {0, len(times)//3, 2*len(times)//3, len(times)-1}
    thumbnails = [cover.copy()]
    for i, now in enumerate(times):
        update(float(now), False)
        fig.canvas.draw()
        frame = Image.fromarray(np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy())
        frames.append(frame.quantize(palette=palette, dither=Image.Dither.NONE))
        if i in checks:
            thumbnails.append(frame.copy())
        if (i+1) % 35 == 0:
            print(f'{gif.name}: {i+1}/{len(times)} playback frames', flush=True)
    durations = [1800] + [110]*len(times)
    durations[-1] = 1400
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True, disposal=1)
    assert len(frames) <= 150 and gif.stat().st_size <= 8_000_000
    with Image.open(gif) as decoded:
        assert decoded.n_frames == len(frames)
        assert decoded.info.get('loop') == 0
        for i, expected in enumerate(frames):
            decoded.seek(i)
            assert np.array_equal(np.asarray(decoded.convert('RGB')),
                                  np.asarray(expected.convert('RGB'))), ('GIF decode mismatch', gif.name, i)
    remember_file(gif, times_s=['overview', *[float(t) for t in times]], cover_hold_ms=1800)
    AUDIT['files'][str(gif)]['decoded_frames_pixel_verified'] = len(frames)
    remember_file(first_png)
    # Contact sheets show original-size content scaled down only for QA.
    qa = gif.parent / 'repair_qa'
    qa.mkdir(exist_ok=True)
    width = 720
    h = round(cover.height*width/cover.width)
    sheet = Image.new('RGB', (width*3, h*2), BG)
    for j, thumb in enumerate(thumbnails):
        sheet.paste(thumb.resize((width, h), Image.Resampling.LANCZOS), ((j%3)*width, (j//3)*h))
    sheet.save(qa / (gif.stem+'_contact.png'))
    plt.close(fig)
    print(f'Saved {gif}: {len(frames)} frames, {gif.stat().st_size/1e6:.2f} MB', flush=True)


def group_legend(ax):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    ax.axis('off')
    ax.text(.08, .94, '同一场景 · 同一组起点', fontsize=19, weight='bold', va='top', color=INK)
    ax.text(.08, .84, '8 架飞机 · 2 座设施 · 同步版', fontsize=13, color=TEAL)
    ax.text(.08, .73, '统一仿真时钟，完整回放\n细线：累计轨迹   粗线：最近 75 秒', fontsize=12, color=MUTED, linespacing=1.8)
    handles = [Line2D([], [], color=c, lw=2.3, label=f'第{i+1}任务编组') for i,c in enumerate(COLORS)]
    handles += [Line2D([], [], marker='o', ls='', color=MUTED, label='当前位置'),
                Line2D([], [], marker='^', ls='', color=ORANGE, label='开始核心作业')]
    handles += [Patch(fc=c, ec='#8AA5BA', label=name) for _,c,name in av.LAYER_STYLE]
    ax.legend(handles=handles, loc='center left', bbox_to_anchor=(.05, .43), frameon=False,
              fontsize=12, ncol=2, labelspacing=1.25, columnspacing=1.6)
    ax.text(.08, .13, '突防按角色分为 3 个任务编组；\n其余意图为 2 个任务编组。', fontsize=11, color=MUTED, linespacing=1.8)


def render_b(eps):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(15,12), dpi=100)
    fig.subplots_adjust(left=.012, right=.988, bottom=.052, top=.952, wspace=.025, hspace=.10)
    box = vp.crop_box(eps)
    panels = [Map(ax, ep, box, vp.INTENT_ZH[ep['intent']]) for ax, ep in zip(axes.flat, eps)]
    group_legend(axes.flat[5])
    clock = axes.flat[5].text(.08,.005,'',fontsize=11,color=TEAL,va='bottom')
    footer(fig, '首帧为全程概览；随后从起点回放。各图保持相同地图比例。')
    progress = fig.add_axes([.035, .038, .93, .005])
    progress.set_xlim(0,1); progress.set_ylim(0,1); progress.axis('off')
    progress.axhline(.5, color='#D9DEDC', lw=5)
    bar, = progress.plot([], [], color=TEAL, lw=5)
    tmax = max(ep['t'][-1] for ep in eps)
    def update(now, cover):
        for panel in panels:
            panel.update(now, cover)
        clock.set_text('全程概览 · 随后从 00:00 回放' if cover else f'仿真时间 {av.fmt_clock(now)} / {av.fmt_clock(tmax)}')
        bar.set_data([0, 1 if cover else now/tmax], [.5,.5])
    times = np.linspace(0, tmax, 148)
    record_map_layout(fig,list(axes.flat[:5]),'B')
    encode(fig, update, times, OUT/'B'/'b_five_intents.gif', OUT/'B'/'b_first_frame.png')
    AUDIT['B'] = {'mode': 'synchronous', 'episodes': [str(ep['dir']) for ep in eps],
                  'crop': box, 'time_range_s': [0,float(tmax)],
                  'role_groups': [[g['members'] for g in ep['groups']] for ep in eps]}


def timeline(ep):
    data = vp.load_timeline(ep['dir'])
    for g in data['groups']:
        # Both modes retain exactly the same physical aircraft on each row.
        g['members'].sort(key=lambda row: row['agent'])
    return data


def timeline_legend(fig, y):
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    handles = [Patch(fc=c, label=l) for c,l in [(vp.WAIT,'等待出发'),(vp.APPROACH,'进场'),(TEAL,'核心作业'),(vp.RETREAT,'撤离')]]
    handles += [Line2D([],[],marker='^',ls='',color=ORANGE,label='开始核心作业')]
    fig.legend(handles=handles, loc='center', bbox_to_anchor=(.5,y), ncol=5, fontsize=11, frameon=False, columnspacing=2.4)


def draw_timeline(ax, data, title, tmax, fontsize=10):
    y=0.; positions=[]; names=[]
    for gi, group in enumerate(data['groups']):
        start=y
        for row in group['members']:
            for phase,a,b in row['phases']:
                color={'waiting':vp.WAIT,'approach':vp.APPROACH,'core':TEAL,'retreat':vp.RETREAT}[phase]
                ax.broken_barh([(a,b-a)], (y-.29,.58), fc=color, ec='none', zorder=3)
            if row['core'] is not None:
                ax.scatter(row['core'], y, marker='^', s=48, color=ORANGE, ec='white', lw=.5, zorder=6)
            positions.append(y)
            number=int(row['agent'].split('_')[-1])
            names.append(f'飞机{number}')
            y+=1
        end=y-1
        events=[r['core'] for r in group['members'] if r['core'] is not None]
        if events:
            lo,hi=min(events),max(events)
            ax.vlines([lo,hi],start-.4,end+.4,colors=ORANGE,linestyles=(0,(3,3)),lw=1,zorder=5)
            ax.annotate('',(hi,end+.62),(lo,end+.62),arrowprops=dict(arrowstyle='|-|',color=ORANGE,lw=.8))
            ax.text((lo+hi)/2,end+.95,f'相差 {hi-lo:.1f} 秒',ha='center',va='center',fontsize=fontsize,color=ORANGE,
                    bbox=dict(fc=BG,ec='none',pad=.6),zorder=8)
        ax.text(-.105,(start+end)/2,f'第{gi+1}\n编组',transform=ax.get_yaxis_transform(),ha='center',va='center',
                fontsize=fontsize,color=COLORS[gi],weight='bold',linespacing=1.5)
        y+=1.65
    ax.set_yticks(positions,names,fontsize=fontsize-1,color=MUTED)
    ax.tick_params(axis='y',length=0,pad=8)
    ax.set_ylim(y-1.15,-.8)
    ax.set_xlim(0,tmax)
    ax.set_xticks(np.arange(0,tmax+1,200))
    ax.tick_params(axis='x',labelsize=fontsize-1,colors=MUTED)
    ax.grid(axis='x',color='#E0E3E1',lw=.7)
    ax.set_axisbelow(True)
    for key in ('top','right','left'):
        ax.spines[key].set_visible(False)
    ax.spines['bottom'].set_color('#CDD4D2')
    ax.set_title(title,loc='left',fontsize=14,weight='bold',pad=12)


def render_c(sync, seq):
    import matplotlib.pyplot as plt
    data=[timeline(sync),timeline(seq)]
    tmax=max(d['last'] for d in data)
    box=vp.crop_box([sync,seq])
    AUDIT['C']={'episodes':[str(sync['dir']),str(seq['dir'])], 'crop':box, 'time_range_s':[0,tmax],
                'groups': [[{'members':g['members']} for g in d['groups']] for d in data]}
    fig=plt.figure(figsize=(18,11),dpi=100)
    clock=text(fig,.53,.71,'',12,TEAL,ha='center',va='center',linespacing=1.7)
    map_axes=map_row(fig,2,box,.385,.565,160,center=.53)
    panels=[Map(ax,ep,box,title,True) for ax,ep,title in zip(map_axes,[sync,seq],['同步版','递次版'])]
    tl_axes=[fig.add_axes([.09,.092,.385,.242]),fig.add_axes([.585,.092,.385,.242])]
    for ax,d,title in zip(tl_axes,data,['同步版 · 实测事件','递次版 · 实测事件']):
        draw_timeline(ax,d,title,tmax,9)
        ax.set_xlabel('仿真时间（秒）',fontsize=10,labelpad=5)
    pointers=[ax.axvline(0,color=ORANGE,lw=1.8,zorder=15) for ax in tl_axes]
    timeline_legend(fig,.037)
    footer(fig,'同一飞机在两侧固定为同一行；关键事件处减速回放。')
    # Include every measured core timestamp and its immediate lead-in so a
    # 5-second synchronization window cannot vanish between sampled frames.
    core=np.array([r['core'] for d in data for g in d['groups'] for r in g['members'] if r['core'] is not None])
    exact=np.unique(np.r_[core,np.maximum(core-1,0),core+1,0.,tmax])
    budget=148-len(exact)
    candidates=np.linspace(0,tmax,700)
    # Extra frames target the core interval; all earlier/later times still play.
    candidates=np.unique(np.r_[np.linspace(0,650,25),np.linspace(650,1150,200),np.linspace(1150,tmax,25)])
    candidates=np.array([t for t in candidates if np.min(abs(exact-t))>.15])
    fill=candidates[np.round(np.linspace(0,len(candidates)-1,budget)).astype(int)]
    times=np.sort(np.r_[exact,fill])
    def update(now,cover):
        for panel in panels:panel.update(now,cover)
        for pointer in pointers:
            pointer.set_visible(not cover);pointer.set_xdata([now,now])
        clock.set_text('全程概览\n↓\n从起点回放' if cover else f'仿真时间\n{av.fmt_clock(now)}')
    record_map_layout(fig,map_axes,'C')
    encode(fig,update,times,OUT/'C'/'c1_sync_seq.gif',OUT/'C'/'c1_first_frame.png')
    fig=plt.figure(figsize=(18,9),dpi=100)
    axes=[fig.add_axes([.13,.58,.84,.36]),fig.add_axes([.13,.135,.84,.36])]
    for ax,d,title in zip(axes,data,['同步版','递次版']):draw_timeline(ax,d,title,tmax,11)
    axes[0].tick_params(labelbottom=False)
    axes[1].set_xlabel('仿真时间（秒）',fontsize=12)
    timeline_legend(fig,.045)
    footer(fig,'出发：首次离起点超过 1 m；其他阶段边界来自实测标签。')
    save_static(fig,OUT/'C'/'c2_timeline.png')


def render_a(ep):
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    from scene_v07.geometry import to_shape
    result=replay(ep)
    free,pool,selected,group,errors,descriptor,index=result
    assert all(e is not None and e < 1e-6 for e in errors.values()), errors
    record(descriptor)
    record(ep['dir'].parents[2]/'planning'/ep['dir'].parent.name/'candidate_pool.pkl')
    task=read(ep['dir']/'task.json')
    agent=sorted(group['members'])[0]
    ref=task['references'][agent]
    route=np.asarray(ref['points_enu_m'])
    planner=free._planners[(0.,False,False)]
    edges=np.array([[planner.vertices[i],planner.vertices[j]] for i,adj in enumerate(planner.adjacency) for j,_ in adj if j>i])
    box=vp.crop_box([ep])
    fig=plt.figure(figsize=(24,10),dpi=100)
    axes=map_row(fig,4,box,.105,.845,28)
    titles=['① 自由空间','② 作业模板','③ 可见图最短路','④ 仿真轨迹']
    for ax,title in zip(axes,titles):
        map_base(ax,ep,box)
        ax.set_title(title,fontsize=20,weight='bold',pad=15)
    starts=np.array([s['position_enu_m'][:2] for s in task['initial_states']])
    axes[0].scatter(starts[:,0],starts[:,1],marker='*',s=70,color=TEAL,ec='white',lw=.6,zorder=10)
    for constraint in free.constraints:
        shape=to_shape(constraint['geometry'],96).buffer(constraint['margin_m'])
        x,y=shape.exterior.xy
        axes[0].plot(x,y,color=ORANGE if constraint['kind']=='obstacle' else MUTED,lw=1,ls=(0,(5,3)),zorder=3)
    axes[0].annotate('共享起点',starts.mean(axis=0),xytext=(8,40),textcoords='offset points',color=TEAL,fontsize=12,
                     arrowprops=dict(arrowstyle='-',color=TEAL),bbox=dict(fc=BG,ec='none',pad=3))
    seen=set();n=0
    for candidate in pool:
        other=candidate['skeleton']['references'][agent]
        pts=np.asarray(other.get('scan_lane_endpoints_m',[]))
        key=pts.tobytes()
        if key in seen or np.array_equal(pts,np.asarray(ref['scan_lane_endpoints_m'])):continue
        seen.add(key)
        axes[1].plot(pts[:,0],pts[:,1],color=MUTED,lw=.8,alpha=.3,zorder=4)
        n+=1
        if n==5:break
    scan=np.asarray(ref['scan_lane_endpoints_m'])
    axes[1].plot(scan[:,0],scan[:,1],color=TEAL,lw=7,alpha=.1,zorder=5)
    axes[1].plot(scan[:,0],scan[:,1],color=TEAL,lw=2.6,zorder=6)
    axes[1].text(.04,.96,f'实际采用：{ref["scan_strip_count"]} 条扫描带',transform=axes[1].transAxes,
                 fontsize=12,color=TEAL,va='top',bbox=dict(fc=BG,ec='none',pad=4),zorder=12)
    # Exactly the graph from the verified replay, not a visually similar graph.
    axes[2].add_collection(LineCollection(edges,colors='#B6C2C2',linewidths=.35,alpha=.35,zorder=2))
    axes[2].plot(route[:,0],route[:,1],color='white',lw=5,zorder=6)
    axes[2].plot(route[:,0],route[:,1],color=TEAL,lw=2.5,zorder=7)
    for ax in axes[1:3]:
        ax.scatter(route[0,0],route[0,1],s=45,color=TEAL,ec='white',zorder=10)
    for i,a in enumerate(ep['ids']):
        p=ep['p'][history_indices(len(ep['t'])-1),i]
        axes[3].plot(p[:,0],p[:,1],color=ep['color'][a],lw=1.35,alpha=.84,zorder=5)
        core=ep['core'][a]
        if core is not None:
            axes[3].scatter(*ep['p'][core,i],marker='^',s=55,color=ORANGE,ec='white',lw=.5,zorder=10)
    legends=[
        [Line2D([],[],ls='--',color=ORANGE,label='限制区外扩 35 m'),Line2D([],[],ls='--',color=MUTED,label='角色禁入边界')],
        [Line2D([],[],color=TEAL,lw=2.5,label='采用模板'),Line2D([],[],color=MUTED,lw=.8,label='其他已存候选')],
        [Line2D([],[],color='#B6C2C2',lw=.8,label='重放可见图边'),Line2D([],[],color=TEAL,lw=2.5,label='已核验规划航线')],
        [Line2D([],[],color=COLORS[0],lw=2,label='第1编组'),Line2D([],[],color=COLORS[1],lw=2,label='第2编组'),
         Line2D([],[],marker='^',ls='',color=ORANGE,label='开始核心作业')]]
    for ax,handles in zip(axes,legends):
        ax.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,-.032),ncol=len(handles),
                  fontsize=10,frameon=False,columnspacing=1.2)
    footer(fig,'模板与航线按已存输入重放；逐点偏差 0 m。全图保持相同地图比例。')
    AUDIT['A']={'episode':str(ep['dir']),'representative_agent':agent,'group':group['group_id'],
                'proposal_index':index,'replay_errors_m':errors,'graph_vertices':len(planner.vertices),
                'graph_edges':len(edges),'alternate_templates':n,'crop':box,
                'graph_source':'verified unified FreeSpace._planners[(0, False, False)]'}
    record_map_layout(fig,axes,'A')
    save_static(fig,OUT/'A'/'a_planner_steps.png')


def csv_series(path):
    result={}
    with record(path).open(encoding='utf-8-sig') as stream:
        for row in csv.DictReader(stream):
            if row.get('valid','1') != '1':continue
            result.setdefault(row['agent_id'],[]).append([float(row[k]) for k in
                ['t_s','east_m','north_m']])
    return {a:np.array(sorted(v)) for a,v in result.items()}


def distance_speed(series):
    """Right-endpoint arclength and segment speed, no filtering or alignment."""
    dt=np.diff(series[:,0])
    assert np.all(dt>0)
    ds=np.linalg.norm(np.diff(series[:,1:3],axis=0),axis=1)
    return np.cumsum(ds), ds/dt


def render_d():
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    pairs=read(old.M3_ROOT/'m3_r3_r2_attempt01'/'paired_results.json')
    assert len(pairs)==282
    registration=read(old.M3_ROOT/'m3_r3_r2_attempt01'/'registration.json')
    assert registration['config_sha256']==AUDIT['r3_config_sha256']
    median=float(np.median([abs(p['duration_relative_error']) for p in pairs]))
    fig=plt.figure(figsize=(20,8),dpi=100)
    handles=[Line2D([],[],color=old.SITL_GRAY,lw=2,label='真实飞控'),Line2D([],[],color=TEAL,lw=2,ls='--',label='快速仿真（转弯修正版）')]
    fig.legend(handles=handles,loc='upper right',bbox_to_anchor=(.985,1.0),frameon=False,ncol=2,fontsize=11)
    records=[]
    for i,(name,mode,pattern,_) in enumerate(old.D_TASKS):
        pair=next(p for p in pairs if p['mission_id']==name)
        assert pair['reference_quality'] and pair['candidate_quality']
        assert pair['reference_status']==pair['candidate_status']=='completed'
        eligible=[p for p in pairs if p['flight_pattern']==pattern]
        assert name == min(eligible,key=lambda p:abs(abs(p['duration_relative_error'])-median))['mission_id']
        meta=old.M3_ROOT/'calibration_20261013'/'attempt_02_resume'/'default_baseline'/name/'sitl_r2.json'
        reference=read(meta)
        sitl_path=next(Path(p) for p in reference['evidence_sha256'] if p.endswith('truth.csv'))
        assert sha(sitl_path)==reference['evidence_sha256'][str(sitl_path)]
        fast_path=old.M3_ROOT/'m3_r3_r2_attempt01'/'runs'/name/'run'/'analysis'/'truth.csv'
        sitl,fast=csv_series(sitl_path),csv_series(fast_path)
        # Fix identity by lexical ID, not by which individual curve looks best.
        agent=sorted(set(sitl)&set(fast))[0]
        y=.70-i*.295
        ax=fig.add_axes([.02,y,.35,.245])
        points=np.concatenate([v[:,1:3] for d in (sitl,fast) for v in d.values()])
        low,high=points.min(axis=0),points.max(axis=0)
        pad=(high-low)*.05
        for d,color,ls in [(sitl,old.SITL_GRAY,'-'),(fast,TEAL,(0,(5,3)))]:
            for a,v in d.items():ax.plot(v[:,1],v[:,2],color=color,ls=ls,lw=1.25,alpha=.95)
        ax.set_xlim(low[0]-pad[0],high[0]+pad[0]);ax.set_ylim(low[1]-pad[1],high[1]+pad[1])
        ax.set_aspect('equal');ax.set_xticks([]);ax.set_yticks([])
        for spine in ax.spines.values():spine.set_color('#C9D1D6')
        title=f'{mode}  |  总时长误差 {pair["duration_relative_error"]*100:+.2f}%'
        row_title=text(fig,.035,y+.263,title,14,weight='bold')
        sx=fig.add_axes([.425,y,.55,.245])
        vmax=0
        distances={}
        for source,d,color,ls in [('sitl',sitl,old.SITL_GRAY,'-'),('fast',fast,TEAL,(0,(5,3)))]:
            distance,speed=distance_speed(d[agent])
            vmax=max(vmax,float(speed.max()))
            curve,=sx.plot(distance,speed,color=color,ls=ls,lw=1.7)
            distances[source]={'total_m':float(distance[-1]),'samples':len(distance),
                               'xy_sha256':hashlib.sha256(np.c_[curve.get_xdata(),curve.get_ydata()].astype('<f8').tobytes()).hexdigest()}
        sx.set_xlim(0,max(d['total_m'] for d in distances.values())*1.015)
        sx.set_ylim(0,vmax*1.12)
        sx.set_ylabel('水平速度（m/s）',fontsize=10,labelpad=9)
        sx.set_xlabel('沿航线累计距离（米）' if i==2 else '',fontsize=10,labelpad=3)
        sx.grid(color='#E0E3E1',lw=.7);sx.set_axisbelow(True)
        sx.tick_params(labelsize=9,colors=MUTED)
        for spine in ('top','right'):sx.spines[spine].set_visible(False)
        for spine in ('left','bottom'):sx.spines[spine].set_color('#CDD4D2')
        records.append({'task':name,'mode':mode,'signed_duration_error':pair['duration_relative_error'],
                        'duration_s':pair['duration_s'],'speed_agent':agent,'sitl':str(sitl_path),'fast':str(fast_path),
                        'distance_curves':distances})
        fig.canvas.draw()
        assert row_title.get_window_extent().x1 < sx.get_window_extent().x0
    footer(fig,'横轴为各自沿航线的累计距离；速度由位置差分计算，未做平滑')
    AUDIT['D']={'tasks':records,'median_abs_duration_error':median,'paired_tasks':len(pairs),
                'x_axis':'independent horizontal cumulative distance, segment right endpoints',
                'map_column_fraction':.35,'time_backup_sha256':sha(OUT/'D'/'d_calibration_time.png')}
    save_static(fig,OUT/'D'/'d_calibration.png')


def backup():
    names={'A':['a_planner_steps.png'],'B':['b_five_intents.gif','b_first_frame.png'],
           'C':['c1_sync_seq.gif','c1_first_frame.png','c2_timeline.png'],'D':['d_calibration.png']}
    backed=[]
    dirname='before_iteration2_20261020_'+uuid.uuid4().hex[:8]
    AUDIT['backup_directory_name']=dirname
    for folder,files in names.items():
        if folder=='A':files=files+['repair_report.json','repair_report.md']
        if folder=='D':files=files+['d_calibration_time.png']
        dest=OUT/folder/dirname
        dest.mkdir(parents=True,exist_ok=True)
        for name in files:
            original=OUT/folder/name
            if original.exists() and not (dest/name).exists():
                shutil.copy2(original,dest/name)
            if (dest/name).exists():backed.append(str(dest/name))
    AUDIT['backups']=backed
    # Preserve iteration 1's current time-based plot before distance rendering.
    time_backup=OUT/'D'/'d_calibration_time.png'
    if not time_backup.exists():
        shutil.copy2(OUT/'D'/'d_calibration.png',time_backup)
    remember_file(time_backup)


def finish():
    changed=[p for p,digest in AUDIT['sources_sha256'].items() if sha(p)!=digest]
    assert not changed, changed
    AUDIT['source_hashes_unchanged']=True
    AUDIT['renderer_sha256']={str(Path(__file__)):sha(__file__),
                             str(Path(__file__).with_name('viz2_inspect.py')):sha(Path(__file__).with_name('viz2_inspect.py'))}
    AUDIT['status']='VIZ2_OK'
    report=OUT/'A'/'repair_report.json'
    report.write_text(json.dumps(AUDIT,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['VIZ2_OK','','# PPT-VIZ2 迭代 2 验收','',f'代码基线：`{AUDIT["head"]}`。冻结标签祖先门禁通过。',
           '',f'覆盖前备份目录：各 A/B/C/D 目录下的 `{AUDIT["backup_directory_name"]}`。原有历史备份保留。',
           '','全部图已删除顶部大标题和副标题，保留页脚及“抽象合成场景”。',
           'A：四格地图等比例放大，实际水平间距缩至 28 px。B：1500×1200，五格地图共同放大、裁切范围一致，第六格说明保留。',
           'C：地图等比例放大，水平间距 160 px；动画时间轴位置与内容不变。C2 删除总标题并扩大时间轴高度。',
           'D：轨迹列分配画布宽度的 35%；行标题固定在左列；速度图横轴为各自轨迹的累计平面距离。',
           '','| 文件 | 尺寸 | 大小 MB | 帧数 |','|---|---|---:|---:|']
    for path,d in AUDIT['files'].items():
        lines.append(f'| {Path(path).parent.name}/{Path(path).name} | {d["size_px"][0]}×{d["size_px"][1]} | {d["bytes"]/1e6:.3f} | {d["frames"]} |')
    if 'A' in AUDIT:
        lines+=['',f'A：代表编组 4 架航点逐点误差均为 0 m；真实重放图 {AUDIT["A"]["graph_vertices"]} 顶点、{AUDIT["A"]["graph_edges"]} 边。']
    if 'B' in AUDIT:
        lines+=['',f'B：同步版；回放 0–{AUDIT["B"]["time_range_s"][1]} 秒，覆盖所有意图完整观测。首帧完整概览后明确从零回放。',
                '突防角色编组为 2+4+2，其余意图为 4+4，因此将“同一编组划分”纠正为“同一场景 · 同一组起点”。']
    if 'C' in AUDIT:
        lines+=['','C：同步组内 4.9 / 5.5 秒；递次 226.6 / 192.9 秒。只使用 observed 事件及实测位移出发时间。',
                'GIF 包含全部核心事件时刻，并在事件前后加帧；两侧时钟一致，关键事件处减速，未对单图独立归一化时间。']
    if 'D' in AUDIT:
        lines+=['','D：使用量产 r3，282 条绝对总时长误差中位数 1.7605%。所选三条为各运动模式最接近该中位数者。',
                '速度图固定使用同一编号的首架飞机。分别累加两条轨迹的平面位移；每段速度为该段位移除以该段时间差，放在该段末端累计距离处。未平滑、未拉伸或统一终点距离。总时长误差仍为任务级指标。',
                '当前按时间绘制的旧版本逐字节另存为 D/d_calibration_time.png，未删除。']
    lines+=['','生产代码、配置、所读数据和原有 animate_v07.py 未修改；读取文件 SHA256 前后相同。未启动 SITL，未安装包，单进程顺序渲染。',
            '本次仅本地修复，未提交或推送。完整来源与逐帧时间见 repair_report.json。']
    (OUT/'A'/'repair_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('VIZ2_OK',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only',choices=['all','a','b','c','d'],default='all')
    args=parser.parse_args()
    # A targeted rerender retains the already-verified audit of other panels.
    prior=OUT/'A'/'repair_report.json'
    if args.only != 'all' and prior.exists():
        AUDIT.update(old.read_json(prior))
    setup();guard();backup()
    if args.only in ('all','a'):
        render_a(episode('reconnaissance'))
    if args.only in ('all','b'):
        render_b([episode(i) for i in vp.INTENT_ORDER])
    if args.only in ('all','c'):
        render_c(episode('transit'),episode('transit','sequential'))
    if args.only in ('all','d'):
        render_d()
    finish()


if __name__=='__main__':main()
