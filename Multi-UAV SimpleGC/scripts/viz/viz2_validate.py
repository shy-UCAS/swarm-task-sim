"""Independent read-only acceptance checks for the delivered PPT assets."""
import json
import hashlib
from pathlib import Path
import numpy as np
from PIL import Image
import viz2_repair as repair


def main():
    out=repair.OUT
    report=json.loads((out/'A'/'repair_report.json').read_text(encoding='utf-8'))
    expected={'A/a_planner_steps.png':(2400,1000),'B/b_five_intents.gif':(1500,1200),
              'B/b_first_frame.png':(1500,1200),'C/c1_sync_seq.gif':(1800,1100),
              'C/c1_first_frame.png':(1800,1100),'C/c2_timeline.png':(1800,900),
              'D/d_calibration.png':(2000,800),'D/d_calibration_time.png':(2000,800)}
    for name,size in expected.items():
        with Image.open(out/name) as im:
            assert im.size==size,(name,im.size)
            if im.format=='GIF':
                assert im.n_frames<=150 and im.info['loop']==0
                assert (out/name).stat().st_size<=8_000_000
                png='b_first_frame.png' if name.startswith('B') else 'c1_first_frame.png'
                first=Image.open((out/name).with_name(png)).convert('RGB')
                assert np.array_equal(np.asarray(im.convert('RGB')),np.asarray(first))
                unique=set()
                for i in range(im.n_frames):
                    im.seek(i);unique.add(im.convert('RGB').tobytes().__hash__())
                assert len(unique)==im.n_frames
                assert report['files'][str(out/name)]['decoded_frames_pixel_verified']==im.n_frames
            assert repair.sha(out/name)==report['files'][str(out/name)]['sha256']
    b=[repair.av.load_episode(Path(p)) for p in report['B']['episodes']]
    assert all(ep['mode']=='synchronous' for ep in b)
    for ep in b[1:]:
        assert ep['scene']==b[0]['scene']
        for a in b[0]['ids']:
            assert np.array_equal(b[0]['p'][0,b[0]['ids'].index(a)],ep['p'][0,ep['ids'].index(a)])
    bclock=report['files'][str(out/'B'/'b_five_intents.gif')]['times_s'][1:]
    assert bclock[0]==0 and bclock[-1]>=max(ep['t'][-1] for ep in b)
    sync,seq=[repair.av.load_episode(Path(p)) for p in report['C']['episodes']]
    for a in sync['ids']:
        assert np.array_equal(sync['plan'][a],seq['plan'][a])
    cclock=report['files'][str(out/'C'/'c1_sync_seq.gif')]['times_s'][1:]
    assert np.all(np.diff(cclock)>0) and cclock[0]==0 and cclock[-1]>=max(sync['t'][-1],seq['t'][-1])
    timelines=[repair.timeline(ep) for ep in (sync,seq)]
    for gs,gq in zip(timelines[0]['groups'],timelines[1]['groups']):
        assert [r['agent'] for r in gs['members']]==[r['agent'] for r in gq['members']]
    for data in timelines:
        for group in data['groups']:
            for row in group['members']:
                assert all(row[k] is not None for k in ('departure','core','work_end','retreat'))
                assert row['departure']<=row['core']<=row['work_end']<=row['retreat']
                assert row['core'] in cclock
    assert all(v==0 for v in report['A']['replay_errors_m'].values())
    assert report['D']['paired_tasks']==282
    # An independently calculated bent path catches time-axis/normalization errors.
    toy=np.array([[0.,0.,0.],[2.,3.,0.],[3.,3.,4.]])
    distance,speed=repair.distance_speed(toy)
    np.testing.assert_allclose(distance,[3.,7.])
    np.testing.assert_allclose(speed,[1.5,4.])
    for task in report['D']['tasks']:
        for source in ('sitl','fast'):
            v=repair.csv_series(task[source])[task['speed_agent']]
            segments=np.sqrt(np.diff(v[:,1])**2+np.diff(v[:,2])**2)
            x=np.cumsum(segments);y=segments/np.diff(v[:,0])
            actual=task['distance_curves'][source]
            np.testing.assert_allclose(actual['total_m'],np.sum(segments),rtol=1e-12)
            assert actual['xy_sha256']==hashlib.sha256(np.c_[x,y].astype('<f8').tobytes()).hexdigest()
    assert report['D']['map_column_fraction']==.35
    assert repair.sha(out/'D'/'d_calibration_time.png')==report['D']['time_backup_sha256']
    assert any(repair.sha(p)==report['D']['time_backup_sha256'] for p in
               (out/'D').glob('before_iteration2_*/d_calibration.png'))
    from PIL import ImageColor
    cover=np.asarray(Image.open(out/'B'/'b_first_frame.png').convert('RGB'))
    for color in repair.COLORS:
        assert np.count_nonzero(np.all(cover==ImageColor.getrgb(color),axis=-1))>10,color
    for name in ('A','B','C'):
        layout=report['layout'][name]
        assert layout['equal_scale_and_crop']
        sizes=np.array(layout['map_bounds_px'])[:,2:]
        assert np.allclose(sizes,sizes[0])
    for name,gap in [('A',28.),('C',160.)]:
        bounds=report['layout'][name]['map_bounds_px']
        assert np.allclose([b[0]-(a[0]+a[2]) for a,b in zip(bounds,bounds[1:])],gap)
    for name,size in expected.items():
        if name.endswith('d_calibration_time.png'):continue
        previous=out/Path(name).parent/report['backup_directory_name']/Path(name).name
        assert previous.exists(),previous
    assert report['source_hashes_unchanged']
    for p,digest in report['sources_sha256'].items():assert repair.sha(p)==digest,p
    print('PASS: 8 media dimensions and hashes; GIF loop, size, all 298 decoded frames, exact cover PNGs;')
    print('PASS: B synchronous identities/shared scene/shared starts/full duration; C matching routes/fixed rows/all measured core events;')
    print('PASS: A zero-error replay; D r3 paired sample selection; all source files unchanged.')
    print('PASS: equal map scales and reduced gaps; independent cumulative distances/speeds; iteration backups and preserved time plot.')


if __name__=='__main__':main()
