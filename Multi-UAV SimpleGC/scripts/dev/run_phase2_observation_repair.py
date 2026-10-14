"""Re-run the diagnosed observation pair, preserving the full pilot evidence."""
import sys,json,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
from scripts.run_v07_s2_expansion import descriptor_jobs,INFRA_ATTEMPT,new_attempt,run_skeleton_job
from task_v07.io import save_json
from task_v07.expansion.views import make_views


def main():
    source=Path(sys.argv[1]).resolve();source_summary=json.loads((source/'summary.json').read_text())
    skeleton='family_s12_4d13d93f9171c446_ext_001_regular'
    assert source_summary['process_count_check']['status']=='PASS'
    out=new_attempt('attempt_s2x_observation_repair');print(f'OUTPUT {out}',flush=True)
    save_json(out/'registration.json',{'scope':'targeted actual observation pair repair; prior full pilot preserved',
        'source_pilot':str(source),'skeleton_id':skeleton,'diagnostic_only':False,
        'fixed_speed_and_timing_rules':True,'paired_geometry_shared':True})
    started=time.perf_counter();job=descriptor_jobs(INFRA_ATTEMPT,[skeleton],out)[0]
    rows=run_skeleton_job(job)
    save_json(out/'episode_records.json',rows);save_json(out/'views.json',make_views(rows))
    save_json(out/'summary.json',{'scope':'one repaired skeleton, not a new eight-skeleton pilot',
        'source_pilot':str(source),'episodes':rows,'wall_s':time.perf_counter()-started})
    print(json.dumps([{k:r.get(k) for k in ('episode_id','state','task_result','task_conditions','audit','minimum_separation_m','reason')} for r in rows],ensure_ascii=False,indent=2),flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
