"""Render a measured development abort next to its exact referenced regular run."""
import argparse
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from task_v07.io import read_json
from scripts.v07_s2_final_figures import load,draw_track


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('attempt',type=Path)
    args=parser.parse_args()
    rows=read_json(args.attempt/'episode_records.json')
    row=next(r for r in rows if r.get('group_count',0)>1 and r.get('abort_observation_valid'))
    sources=read_json(args.attempt/'registration.json')['source_attempts']
    source=next(Path(p) for p in sources if (Path(p)/row['source_skeleton_id']/'synchronous'/'metrics.json').exists())
    reference=read_json(source/row['source_skeleton_id']/'synchronous'/'metrics.json')
    fig,axes=plt.subplots(1,2,figsize=(16,8))
    for ax,root,record,title in zip(axes,[source,args.attempt],[reference,row],
            ['Referenced regular synchronous episode','Main group withdraws; other group executes original task']):
        draw_track(ax,*load(root,record))
        ax.set_title(title,fontsize=11)
    fig.suptitle(f"Exact prefix: {row['exact_prefix_comparison']['prefix_frames']} frames; main core missing; observed main timing unknown",fontsize=11)
    fig.tight_layout(rect=(0,0,1,.95))
    output=args.attempt/'abort_vs_regular_preview.png'
    fig.savefig(output,dpi=150)
    plt.close(fig)
    print(output)


if __name__=='__main__':
    main()
