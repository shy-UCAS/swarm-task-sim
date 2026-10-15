"""Verify the saved 8412/ext_001 collision is rejected before joint execution."""
from pathlib import Path
import sys,subprocess
import numpy as np
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from scripts.run_v07_s2_expansion import DEFAULT_DATA,new_attempt
from task_v07.io import read_json,save_json,sha
from task_v07.expansion.solo_spacing import load_saved_solos,solo_interval_check,prediction_error


def main():
    source=DEFAULT_DATA/'attempt_s2x_final_20261015T053115Z_a3b834e8/family_s12_8412c1cdb40e54b1_ext_001_regular'
    timing=read_json(source/'timing_calibration.json')
    matches=[p for p in source.glob('geometry_*') if (p/'timing_calibration.json').is_file() and read_json(p/'timing_calibration.json')==timing]
    if len(matches)!=1:raise ValueError('Cannot uniquely locate the selected saved solo round')
    calibration=matches[0]
    plans=timing['timing_plans']
    ids=sorted(plans['synchronous']['departure_delays_s'])
    files=[calibration/f'single_agent_{a}.npz' for a in ids]+[source/'timing_calibration.json',source/'planning_layer_interval.json']
    files += [source/m/'truth_10hz.npz' for m in ('synchronous','sequential')]
    hashes={str(p):sha(p) for p in files}
    solos=load_saved_solos(calibration,ids)
    prediction=solo_interval_check(solos,plans)
    errors={}
    for mode in ('synchronous','sequential'):
        with np.load(source/mode/'truth_10hz.npz',allow_pickle=False) as saved:
            actual={k:saved[k].copy() for k in ('p','time_us')}
            actual['agent_ids']=saved['agent_ids'].tolist()
        errors[mode]=prediction_error(solos,plans[mode],actual,prediction[mode])
    old=read_json(source/'planning_layer_interval.json')
    if any(old[m]['below_warning'] for m in ('synchronous','sequential')):raise AssertionError('Not an additional rejection relative to old screen')
    if not prediction['sequential']['below_warning']:raise AssertionError('Registered collision was not intercepted')
    if abs(errors['sequential']['actual']['minimum_m']-.6893642384836755)>1e-8:raise AssertionError('Registered evidence changed')
    if abs(prediction['sequential']['minimum_m']-.6894344153873819)>1e-8:raise AssertionError('Saved trajectory projection disagrees with offline baseline')
    if hashes!={str(p):sha(p) for p in files}:raise ValueError('Source evidence changed')
    out=new_attempt('attempt_s2_search_overlay_witness')
    data={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True).strip(),
          'source_attempt':str(source),'source_sha256':hashes,'simulation_runs':0,
          'prediction':prediction,'prediction_errors':errors,'old_interval':old,
          'additional_rejection':True,'status':'PASS','scope':'archived real trajectory replay; no new flights'}
    save_json(out/'diagnostics.json',data)
    with (PROJECT/'docs/v07/S2_search_revision_report.md').open('a',encoding='utf-8',newline='\n') as f:
        p=prediction['sequential']['minimum_m'];a=errors['sequential']['actual']['minimum_m']
        f.write(f"\n### 已存 0.689 m 样本的提前拦截验证\n\n证据 `{out}`；新仿真 0。8412/ext_001 递次版本原预筛通过，新叠加预测 {p:.9f} m，存档实测 {a:.9f} m，预测误差 {p-a:+.9f} m；10 m 预检将整对提前拒绝。源轨迹与时间计划哈希验证未变。\n")
    print({'output':str(out),'status':'PASS','prediction':prediction['sequential'],'additional_rejection':True},flush=True)


if __name__=='__main__':main()
