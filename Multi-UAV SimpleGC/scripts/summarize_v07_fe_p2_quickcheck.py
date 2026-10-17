"""Read-only FE-P2 cohort registration and paired planning evidence; never runs planners."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import platform
import importlib.metadata
from pathlib import Path

BASE = '92068b95416a53d8e84a90488d06112d367f0c09'
WATCH = ('shape_search_budget_exhausted','ingress_line_blocked','survey_area_unavailable',
         'work_segment_clearance','inner_alignment_blocked','no_interior_connection',
         'connection_search_budget_exhausted','whole_route_check','existing_output_precheck')

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def save(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')

def walk(value):
    if isinstance(value,dict):
        yield value
        for v in value.values(): yield from walk(v)
    elif isinstance(value,list):
        for v in value: yield from walk(v)

def distribution(values):
    values=sorted(v for v in values if v is not None)
    def q(p):
        i=(len(values)-1)*p; low=int(i)
        return values[low]+(values[min(low+1,len(values)-1)]-values[low])*(i-low)
    return {'count':len(values),'min':min(values) if values else None,
            'p50':q(.5) if values else None,'p90':q(.9) if values else None,
            'max':max(values) if values else None}

def records(directory):
    with (Path(directory)/'proposals.jsonl').open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]

def register(attempt_paths, descriptors, cohort, arm):
    descriptors=Path(descriptors); ids=read(cohort)
    assert len(ids)==32 and len(set(ids))==32
    ds={d['skeleton_id']:d for d in read(descriptors/'private_skeleton_descriptors.json')}
    assert set(ids)=={sid for sid,d in ds.items() if d['base_intent']=='reconnaissance'}
    result={'schema':'fe_p2_cohort/1','arm':arm,'fixed_algorithm_base':BASE,
            'created_utc':datetime.now(timezone.utc).isoformat(),'selected_skeletons':ids,
            'descriptors':str(descriptors),'descriptors_sha256':sha(descriptors/'private_skeleton_descriptors.json'),
            'selection_path':str(Path(cohort).resolve()),'selection_sha256':sha(cohort),
            'attempts':[],'skeletons':{},'unfinished':[],'duplicate_completed_results':[],
            'environment':{'python':platform.python_version(),'platform':platform.platform(),
                'packages':{name:importlib.metadata.version(name) for name in ('numpy','scipy','shapely')}}}
    hashes=None; commit=None; prior_unfinished=set(ids)
    assert 1<=len(attempt_paths)<=2
    for raw in attempt_paths:
        path=Path(raw); reg=read(path/'registration.json'); run=read(path/'run_result.json')
        assert reg['descriptors_sha256']==result['descriptors_sha256']
        assert reg['workers']==8 and reg['wall_limit_s']==2400
        assert set(reg['selected_skeletons'])==prior_unfinished
        assert run['status'] in ('completed','TIME_LIMIT_STOP'),run.get('stop')
        assert run['runtime_sha256_stable']
        if hashes is None: hashes=reg['runtime_sha256'];commit=reg['entry_commit']
        assert reg['runtime_sha256']==hashes and reg['entry_commit']==commit
        assert set(run['completed']).isdisjoint(run['unfinished'])
        assert set(run['completed'])|set(run['unfinished'])==set(reg['selected_skeletons'])
        result['attempts'].append({'path':str(path),'registration_sha256':sha(path/'registration.json'),
            'run_result_sha256':sha(path/'run_result.json'),'registration':reg,'run_result':run,
            'excluded_unfinished_evidence':{sid:{'directory':str(path/sid),'file_sha256':{name:sha(path/sid/name) for name in ('progress.json','proposals.jsonl','planning_result.json','candidate_pool.json') if (path/sid/name).exists()}} for sid in run['unfinished']}})
        # Choose only scheduler-confirmed complete results. Partial journals are retained but excluded.
        for sid in run['completed']:
            root=path/sid; planning=read(root/'planning_result.json'); pool=read(root/'candidate_pool.json')
            assert sid not in result['skeletons'],sid
            assert planning['status'] in ('PASS','REJECT')
            journal=records(root); keys=[(r['group_id'],r['candidate_index']) for r in journal]
            assert len(keys)==len(set(keys))
            group_counts=Counter(r['group_id'] for r in journal)
            assert dict(group_counts)==planning['group_attempts']==pool['group_attempt_counts']
            assert pool['candidate_budget']==200 and pool['combination_search']['budget']==1000
            assert set(group_counts)=={g['group_id'] for g in ds[sid]['task_groups']}
            accepted=Counter(r['group_id'] for r in journal if not r['reason'])
            for gid,n in group_counts.items():
                assert n==200
                assert sorted(r['candidate_index'] for r in journal if r['group_id']==gid)==list(range(200))
                assert accepted[gid]==pool['group_search_metrics'][gid]['feasible_candidates']
                assert sorted(r['candidate_index'] for r in journal if r['group_id']==gid and not r['reason'])==sorted(pool['group_feasible_candidate_indices'][gid])
            result['skeletons'][sid]={'directory':str(root),'status':planning['status'],
                'planning_wall_s':planning['planning_wall_s'],'group_attempts':dict(group_counts),
                'accepted_by_group':{gid:accepted[gid] for gid in group_counts},
                'rejection_reasons':planning['rejection_reasons'],
                'eligible_combinations':planning['eligible_combinations'],
                'whole_route_pass':planning['whole_route_pass'],
                'file_sha256':{name:sha(root/name) for name in ('planning_result.json','candidate_pool.json','proposals.jsonl','selected_checks.json','selected_skeleton.json') if (root/name).exists()}}
        prior_unfinished=set(ids)-set(result['skeletons'])
    result.update(unfinished=sorted(prior_unfinished),unfinished_details={sid:{'status':'TIME_LIMIT_STOP','last_attempt':str(path),'last_observed_planning_wall_s':run['planning_wall_s'].get(sid)} for sid in prior_unfinished},entry_commit=commit,runtime_sha256=hashes,
                  production_sha256={k:v for k,v in hashes.items() if not k.startswith('scripts/')},
                  status='COMPLETE' if not prior_unfinished else 'P2_AB_INCOMPLETE')
    return result

def load_manifest(path, descriptors):
    path=Path(path)
    if path.is_dir():
        reg=read(path/'registration.json')
        return register([path],descriptors,reg['skeletons_file'],'unspecified')
    value=read(path); assert value['schema']=='fe_p2_cohort/1'
    assert value['descriptors_sha256']==sha(Path(descriptors)/'private_skeleton_descriptors.json')
    for item in value['attempts']:
        root=Path(item['path'])
        assert sha(root/'registration.json')==item['registration_sha256']
        assert sha(root/'run_result.json')==item['run_result_sha256']
    for row in value['skeletons'].values():
        for name,h in row['file_sha256'].items(): assert sha(Path(row['directory'])/name)==h
    return value

def target_hit(record, target, entities):
    hit=False
    for node in walk(record):
        if 'phase' not in node: continue
        entity=node.get('entity_id'); assert isinstance(entity,str)
        assert entity=='world' or entity in entities,entity
        is_target=entity==target or entity.startswith(target+'_')
        if entity!='world':
            obj=entities[entity];owner=obj.get('facility_id',entity if obj['type']=='facility' else None)
            assert (owner==target)==is_target
        hit |= node['phase']=='entry_to_work_start' and is_target
    return hit

def entity_maps(descriptors):
    reg=read(Path(descriptors)/'registration.json')
    candidates={r['candidate_index']:r for r in read(Path(reg['source_attempt'])/'candidates.json')}
    maps={}
    for row in reg['selected']:
        scene=read(Path(candidates[row['candidate_index']]['directory'])/'public_scene.json')
        assert scene.get('world'), 'Scene world boundary not registered'
        maps[row['family_id']]={e['id']:e for e in scene['entities']}
        assert len(maps[row['family_id']])==len(scene['entities']), 'Duplicate scene entity ID'
    return maps

def new_bucket():
    return {'skeleton_ids':set(),'proposals':0,'accepted':0,'final_reasons':Counter(),
            'proposal_reason_hits':Counter(),'shape_attempt_reasons':Counter(),
            'rejected_proposal_shape_reasons':Counter(),'connection_attempt_reasons':Counter(),
            'phase_evidence_entries':Counter(),'proposal_phase_hits':Counter()}

def collect(manifest, ds, entities):
    buckets=defaultdict(new_bucket); by_key={}; skeletons={}; anomalies=[]; all_checks=0
    for sid,row in manifest['skeletons'].items():
        d=ds[sid]; root=Path(row['directory']); planning=read(root/'planning_result.json')
        groups={g['group_id']:g for g in d['task_groups']}; checks=read(root/'selected_checks.json') if (root/'selected_checks.json').exists() else {}
        success=(planning['status']=='PASS' and planning['eligible_combinations']>0 and planning['whole_route_pass'] is True and set(checks)==set(groups) and all(c.get('status')=='PASS' and c.get('existing_precheck',{}).get('status')=='PASS' for c in checks.values()))
        if planning['status']=='PASS' and not success: anomalies.append({'code':'INVALID_SELECTED_CHECKS','sid':sid})
        skeletons[sid]={'approach_mode':d['common_draw']['approach_mode'],'methods':sorted({g['execution_method'] for g in groups.values()}),
                        'intent':d['base_intent'],'common_draw_seed':d['common_draw']['seed'],'common_draw_slot':d['common_draw']['slot'],
                        'success':success,'status':planning['status'],'planning_wall_s':planning['planning_wall_s'],
                        'heading_by_group_deg':planning['planned_heading_by_group_deg']}
        for g in groups.values():
            assert g['target_id'] in entities[d['family_id']] and entities[d['family_id']][g['target_id']]['type']=='facility'
        for r in records(root):
            gid=r['group_id']; g=groups[gid]; key=(sid,gid,r['candidate_index']); assert key not in by_key
            accepted=not r['reason']; checks=r.get('whole_route_checks',{})
            if accepted:
                all_checks+=1
                if r['stage']!='group_feasible' or checks.get('status')!='PASS' or checks.get('existing_precheck',{}).get('status')!='PASS':
                    anomalies.append({'code':'INVALID_ACCEPTED_CHECKS','key':key})
            b=buckets[(d['common_draw']['approach_mode'],g['execution_method'])]
            b['skeleton_ids'].add(sid);b['proposals']+=1;b['accepted']+=int(accepted)
            if r['reason']:b['final_reasons'][r['reason']]+=1
            nodes=list(walk(r));b['proposal_reason_hits'].update({n['reason'] for n in nodes if n.get('reason')})
            phases=set()
            for n in nodes:
                if n.get('reason') and 'draw' in n:
                    b['shape_attempt_reasons'][n['reason']]+=1
                    if not accepted:b['rejected_proposal_shape_reasons'][n['reason']]+=1
                if n.get('reason') and 'attempt' in n and 'draw' not in n:b['connection_attempt_reasons'][n['reason']]+=1
                if 'phase' in n:
                    phase=n['phase']; b['phase_evidence_entries'][phase]+=1;phases.add(phase)
            b['proposal_phase_hits'].update(phases)
            target=target_hit(r,g['target_id'],entities[d['family_id']])
            by_key[key]={'record':r,'accepted':accepted,'target_entry_hit':target,
                         'method':g['execution_method'],'mode':d['common_draw']['approach_mode'],
                         'proposal_seed':r['draws_by_group'][gid]['proposal_seed']}
    normalized={}
    for key,b in buckets.items():
        normalized['/'.join(key)]={k:(sorted(v) if isinstance(v,set) else dict(v) if isinstance(v,Counter) else v) for k,v in b.items()}
        normalized['/'.join(key)]['acceptance_rate']=b['accepted']/b['proposals']
    return normalized,by_key,skeletons,anomalies,all_checks

ANCHOR_TOL_M = 1e-6  # Existing planning numerical tolerance; not an acceptance margin.

def anchor_locations(points, cumulative, anchor):
    found=[]
    for i,(a,b) in enumerate(zip(points,points[1:])):
        length=cumulative[i+1]-cumulative[i]
        if length==0:continue
        delta=[y-x for x,y in zip(a,b)]
        t=max(0.,min(1.,sum((x-y)*v for x,y,v in zip(anchor,a,delta))/(length*length)))
        projected=[x+t*v for x,v in zip(a,delta)];residual=math.dist(projected,anchor)
        if residual<=ANCHOR_TOL_M:
            item={'segment_index':i,'fraction':t,'arclength_m':cumulative[i]+t*length,
                  'residual_m':residual,'exact_vertex':anchor==a or anchor==b}
            duplicate=next((v for v in found if abs(v['arclength_m']-item['arclength_m'])<=ANCHOR_TOL_M),None)
            if duplicate is None:found.append(item)
            elif item['residual_m']<duplicate['residual_m']:duplicate.update(item)
    return found

def route_details(manifest, skeletons, ds):
    details=[]; missing=[]; headings=[]; exact_ratios=[]; total=0
    for sid, s in skeletons.items():
        if not s['success'] or 'area_search' not in s['methods']: continue
        data=read(Path(manifest['skeletons'][sid]['directory'])/'selected_skeleton.json')
        groups={g['group_id']:g for g in ds[sid]['task_groups']}
        for gid,g in groups.items():
            if g['execution_method']!='area_search':continue
            group=data['group_skeletons'][gid]
            headings.append({'skeleton_id':sid,'group_id':gid,'value_deg':s['heading_by_group_deg'].get(gid)})
            for agent,ref in group['references'].items():
                total+=1;points=ref['points_enu_m'];stage=ref['stage_geometry'];gate=stage['warning_entry'];work=stage['work_start']
                line=math.dist(gate,work);row={'skeleton_id':sid,'group_id':gid,'agent_id':agent}
                cumulative=[0.]
                for a,b in zip(points,points[1:]):cumulative.append(cumulative[-1]+math.dist(a,b))
                exact_pairs=[(i,j) for i,p in enumerate(points) if p==gate for j,q in enumerate(points) if q==work and j>=i]
                if exact_pairs and line>0:
                    i,j=min(exact_pairs);exact_ratios.append((cumulative[j]-cumulative[i])/line)
                starts=anchor_locations(points,cumulative,gate);ends=anchor_locations(points,cumulative,work)
                pairs=[(a,b) for a in starts for b in ends if b['arclength_m']>=a['arclength_m']]
                if len(pairs)!=1 or line<=0:
                    reason='zero_line_length' if line<=0 else 'ambiguous_anchors' if len(pairs)>1 else 'anchor_missing_or_out_of_order'
                    missing.append({**row,'reason':reason,'entry_locations':starts,'work_locations':ends});continue
                a,b=pairs[0];length=b['arclength_m']-a['arclength_m']
                details.append({**row,'entry_location':a,'work_location':b,'L_route_m':length,'L_line_m':line,'ratio':length/line})
    return {'ratios':distribution([r['ratio'] for r in details]),'members':details,'unlocated_count':len(missing),
            'unlocated':missing,'headings':headings,'anchor_localization_tolerance_m':ANCHOR_TOL_M,
            'method':'Locate unique ordered anchors on actual polyline segments; accumulate actual segment arclength, including endpoint fractions. No acceptance criterion changes.',
            'exact_vertex_only':{'ratios':distribution(exact_ratios),'unlocated_count':total-len(exact_ratios)},
            'max_localization_residual_m':max((v[k]['residual_m'] for v in details for k in ('entry_location','work_location')),default=None)}

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'---|'*len(headers),*['| '+' | '.join(str(x) for x in row)+' |' for row in rows]])

def compare(a,b,descriptors,validation=None):
    assert a['selected_skeletons']==b['selected_skeletons']
    assert a['environment']==b['environment']
    assert a['selection_sha256']==b['selection_sha256'] and a['descriptors_sha256']==b['descriptors_sha256']
    ds={d['skeleton_id']:d for d in read(Path(descriptors)/'private_skeleton_descriptors.json')}; entities=entity_maps(descriptors)
    ba,pa,sa,ea,ca=collect(a,ds,entities);bb,pb,sb,eb,cb=collect(b,ds,entities)
    changed=sorted(k for k in set(a['production_sha256'])|set(b['production_sha256']) if a['production_sha256'].get(k)!=b['production_sha256'].get(k))
    hard_stops=ea+eb
    if changed!=['task_v07/unified/construction.py']:hard_stops.append({'code':'UNEXPECTED_SOURCE_DIFFERENCE','paths':changed})
    proposal_rows=[]; witnesses=[]; nonarea=[]; migrations=Counter()
    for key in sorted(set(pa)&set(pb)):
        x,y=pa[key],pb[key];rx,ry=x['record'],y['record']; assert x['proposal_seed']==y['proposal_seed']
        equal=rx==ry
        if x['method']!='area_search' and not equal:nonarea.append(key)
        migrations[(x['mode'],x['method'],rx['stage'],rx['reason'],ry['stage'],ry['reason'])]+=1
        proposal_rows.append({'skeleton_id':key[0],'group_id':key[1],'candidate_index':key[2],
            'proposal_seed':x['proposal_seed'],'method':x['method'],'approach_mode':x['mode'],
            'a_stage':rx['stage'],'b_stage':ry['stage'],'a_reason':rx['reason'],'b_reason':ry['reason'],
            'a_rejection_sha256':digest(rx['rejection']),'b_rejection_sha256':digest(ry['rejection']),
            'rejection_equal':rx['rejection']==ry['rejection'],'record_equal':equal,
            'a_accepted':x['accepted'],'b_accepted':y['accepted'],'a_target_entry_conflict':x['target_entry_hit']})
        if not x['accepted'] and x['target_entry_hit'] and y['accepted']:
            witnesses.append({'skeleton_id':key[0],'group_id':key[1],'candidate_index':key[2],
                'proposal_seed':x['proposal_seed'],'approach_mode':x['mode'],'a_reason':rx['reason'],
                'a_nested_reasons':dict(Counter(n['reason'] for n in walk(rx) if n.get('reason') and 'draw' in n)),
                'b_stage':ry['stage'],'b_whole_route_checks':ry['whole_route_checks'],
                'a_journal':str(Path(a['skeletons'][key[0]]['directory'])/'proposals.jsonl'),
                'b_journal':str(Path(b['skeletons'][key[0]]['directory'])/'proposals.jsonl')})
    if nonarea:hard_stops.append({'code':'NON_AREA_SEMANTIC_CHANGE','keys':nonarea})
    paired_ids=set(sa)&set(sb)
    paired_buckets={}
    for label,values in [('a',pa),('b',pb)]:
        cells=defaultdict(lambda:{'skeleton_ids':set(),'proposals':0,'accepted':0})
        for (sid,gid,index),value in values.items():
            if sid not in paired_ids:continue
            cell=cells[value['mode']+'/'+value['method']];cell['skeleton_ids'].add(sid)
            cell['proposals']+=1;cell['accepted']+=int(value['accepted'])
        paired_buckets[label]={k:{**v,'skeleton_ids':sorted(v['skeleton_ids']),'acceptance_rate':v['accepted']/v['proposals']} for k,v in cells.items()}
    paired_A=[]
    for key in sorted(set(paired_buckets['a'])|set(paired_buckets['b'])):
        x,y=paired_buckets['a'].get(key),paired_buckets['b'].get(key)
        delta=100*(y['acceptance_rate']-x['acceptance_rate']) if x and y else None
        paired_A.append({'stratum':key,'a':x,'b':y,'percentage_point_change':delta})
        if key=='same_direction/area_search' and delta is not None and delta < -5:
            hard_stops.append({'code':'SAME_DIRECTION_DEGRADATION','percentage_point_change':delta,'population':'paired_complete_skeletons'})
    A=[]
    for k in sorted(set(ba)|set(bb)):
        x,y=ba.get(k),bb.get(k)
        row={'stratum':k,'a':x,'b':y,'percentage_point_change':100*(y['acceptance_rate']-x['acceptance_rate']) if x and y and x['skeleton_ids']==y['skeleton_ids'] else None};A.append(row)
    C=[]
    for mode in ('multi_direction','same_direction'):
        for method in ('area_search','close_observation','ALL_RECONNAISSANCE'):
            ids={sid for sid in a['selected_skeletons'] if ds[sid]['common_draw']['approach_mode']==mode and (method=='ALL_RECONNAISSANCE' or any(g['execution_method']==method for g in ds[sid]['task_groups']))}
            row={'approach_mode':mode,'method':method,'registered':len(ids)}
            for name,values in [('a',sa),('b',sb)]:
                done=ids&set(values); row[name]={'pass':sum(values[s]['success'] for s in done),'completed':len(done),'unfinished':sorted(ids-done)}
            C.append(row)
    draw_rows=[]
    for sid in a['selected_skeletons']:
        d=ds[sid];draw_rows.append({'skeleton_id':sid,'base_intent':d['base_intent'],'common_draw':d['common_draw'],
            'methods':sorted({g['execution_method'] for g in d['task_groups']}),'a':sa.get(sid),'b':sb.get(sid)})
    draw_summary=[]
    for mode,slot in sorted({(ds[sid]['common_draw']['approach_mode'],ds[sid]['common_draw']['slot']) for sid in a['selected_skeletons']}):
        for method in ('area_search','close_observation','ALL_RECONNAISSANCE'):
            ids={sid for sid in a['selected_skeletons'] if ds[sid]['common_draw']['approach_mode']==mode and ds[sid]['common_draw']['slot']==slot and (method=='ALL_RECONNAISSANCE' or any(g['execution_method']==method for g in ds[sid]['task_groups']))}
            row={'approach_mode':mode,'common_slot':slot,'base_intent':'reconnaissance','method':method,'registered':len(ids)}
            for name,values in [('a',sa),('b',sb)]:
                done=ids&set(values);row[name]={'pass':sum(values[s]['success'] for s in done),'completed':len(done),'unfinished':sorted(ids-done)}
            draw_summary.append(row)
    times={}
    for name,m in [('a',a),('b',b)]:
        walls=[x['run_result']['wall_s'] for x in m['attempts']]
        times[name]={'planning_wall_s':distribution([r['planning_wall_s'] for r in m['skeletons'].values()]),
            'skeleton_wall_s':{sid:r['planning_wall_s'] for sid,r in m['skeletons'].items()},
            'total_attempt_wall_s':sum(walls),'resume_wall_s':sum(walls[1:]),'unfinished':m['unfinished'],
            'source_fingerprints_stable':all(x['run_result']['runtime_sha256_stable'] for x in m['attempts'])}
    unmatched_a=sorted(set(pa)-set(pb));unmatched_b=sorted(set(pb)-set(pa))
    incomplete=bool(a['unfinished'] or b['unfinished'] or unmatched_a or unmatched_b)
    gained=(bb.get('multi_direction/area_search',{}).get('accepted',0)>ba.get('multi_direction/area_search',{}).get('accepted',0) or any(not sa[sid]['success'] and sb[sid]['success'] and 'area_search' in sa[sid]['methods'] for sid in set(sa)&set(sb)))
    ingress_a=sum(v['shape_attempt_reasons'].get('ingress_line_blocked',0) for k,v in ba.items() if k.endswith('/area_search'))
    ingress_b=sum(v['shape_attempt_reasons'].get('ingress_line_blocked',0) for k,v in bb.items() if k.endswith('/area_search'))
    if hard_stops:status='HARD_STOP'
    elif incomplete:status='P2_AB_INCOMPLETE'
    elif not validation or validation.get('status')!='PASS':status='P2_NO_PROVEN_GAIN'
    elif gained and witnesses:status='P2_PLANNING_GAIN_CONFIRMED'
    elif ingress_b<ingress_a:status='P2_PRECHECK_ONLY_IMPROVED'
    else:status='P2_NO_PROVEN_GAIN'
    return {'schema':'fe_p2_ab_comparison/1','status':status,'generated_utc':datetime.now(timezone.utc).isoformat(),
        'a_registration':a,'b_registration':b,'production_changed_files':changed,'validation':validation,
        'hard_stops':hard_stops,'P0_stop_count':sum(x['run_result']['status']=='P0_STOP' for m in (a,b) for x in m['attempts']),
        'all_accepted_checks_verified':{'a':ca,'b':cb},'table_A':A,'paired_complete_skeletons':sorted(paired_ids),'table_A_paired':paired_A,'table_B':{'a':ba,'b':bb},'table_C':C,
        'table_D':{'matched':len(proposal_rows),'unmatched_a':unmatched_a,'unmatched_b':unmatched_b,
            'non_area_changed_keys':nonarea,'proposals':proposal_rows,
            'migrations':[{'mode':k[0],'method':k[1],'a_stage':k[2],'a_reason':k[3],'b_stage':k[4],'b_reason':k[5],'count':v} for k,v in migrations.items()],
            'recovery_witness_count':len(witnesses),'recovery_witnesses':witnesses[:10],
            'witness_status':'VERIFIED_FROM_SAVED_CONTRACTS' if witnesses else 'NO_DIRECT_RECOVERY_WITNESS'},
        'table_E':route_details(b,sb,ds),'table_F':times,'public_draw_skeleton_detail':draw_rows,'public_draw_summary':draw_summary,
        'interpretation':'Planning only. No inference about five-intent yield, M2, fastsim, M1 or production. Mixed-method skeleton strata overlap.'}

def markdown(r):
    lines=['# FE-P2 同输入 A/B 纯规划对照','',f"结论：{r['status']}",'',
        'A/B 固定同一 32 骨架及描述符。每个骨架只取一份完整结果；未完成与缺失单列。混合方法骨架同时进入各方法分层，不能把方法分母相加。主意图始终为 reconnaissance。',
        '本报告只涉及规划，不推算五意图齐全率，也不代表 M2/fastsim/M1 端到端通过。','',
        '## 表 A：组提案接受率','',table(['approach/method','A 完成骨架','A 接受/提案','B 完成骨架','B 接受/提案','变化 pp'],[
            [x['stratum'],len(x['a']['skeleton_ids']) if x['a'] else 0,f"{x['a']['accepted']}/{x['a']['proposals']}" if x['a'] else None,
             len(x['b']['skeleton_ids']) if x['b'] else 0,f"{x['b']['accepted']}/{x['b']['proposals']}" if x['b'] else None,x['percentage_point_change']] for x in r['table_A']]),'',
        '同一方法分层的完成骨架集合不同时，不直接计算全体接受率差。可配对骨架 ID 与配对后的接受率另存 JSON 的 table_A_paired；完整批次时两种口径一致。','','## 表 B：拒绝阶段与统计单位','',
        '终局原因每提案只计一次；proposal_reason_hits 对各嵌套原因在每个提案内去重，属于可重叠标签。形态尝试统计含最终成功提案中此前失败的尝试，并另存仅被拒提案子集，不能与终局计数相加。连接尝试与 phase 证据均单列。','']
    for key in sorted(set(r['table_B']['a'])|set(r['table_B']['b'])):
        x=r['table_B']['a'].get(key,{});y=r['table_B']['b'].get(key,{})
        lines+=['### '+key,'']
        for unit in ('final_reasons','proposal_reason_hits','shape_attempt_reasons','rejected_proposal_shape_reasons','connection_attempt_reasons','phase_evidence_entries','proposal_phase_hits'):
            reasons=sorted(set(WATCH if unit not in ('phase_evidence_entries','proposal_phase_hits') else ())|set(x.get(unit,{}))|set(y.get(unit,{})))
            lines += [unit,'',table(['reason/phase','A','B'],[[k,x.get(unit,{}).get(k,0),y.get(unit,{}).get(k,0)] for k in reasons]),'']
    lines+=['## 表 C：完整骨架','',table(['approach','分层','登记','A PASS/完成','B PASS/完成'],[
        [x['approach_mode'],x['method'],x['registered'],f"{x['a']['pass']}/{x['a']['completed']}",f"{x['b']['pass']}/{x['b']['completed']}"] for x in r['table_C']]),'',
        '## 表 D：固定提案索引配对','',f"已配对 {r['table_D']['matched']} 条；非 area_search 变化 {len(r['table_D']['non_area_changed_keys'])} 条。直接恢复案例 {r['table_D']['recovery_witness_count']} 个。",'',
        '全部索引的 stage/reason/rejection 哈希与接受状态、阶段迁移、原始日志定位见同名 JSON。', '',r['table_D']['witness_status'],'']
    for w in r['table_D']['recovery_witnesses'][:3]:
        lines += [f"- {w['skeleton_id']} / {w['group_id']} / {w['candidate_index']}；seed={w['proposal_seed']}；A={w['a_reason']} 且含目标入口直线冲突；B={w['b_stage']}，whole_route={w['b_whole_route_checks']['status']}，existing_precheck={w['b_whole_route_checks']['existing_precheck']['status']}。"]
    lines+=['','## 表 E：实际绕行','',json.dumps(r['table_E']['ratios'],ensure_ascii=False),f"无法定位的成员数：{r['table_E']['unlocated_count']}。同时保留精确顶点匹配口径；共线顶点被清理时，按原有数值精度 1e-6 m 验证锚点位于实际线段并唯一有序定位，记录残差，再累加真实路线段及端点所在段的相应部分。不存在则单列，不改变任何接受判据。详情见 JSON。",'',
        '## 表 F：时间及未完成项','',table(['组','骨架耗时 p50/p90/max (s)','总 attempt 墙钟 (s)','续跑 (s)','未完成'],[
            [k,' / '.join(str(v['planning_wall_s'][q]) for q in ('p50','p90','max')),v['total_attempt_wall_s'],v['resume_wall_s'],len(v['unfinished'])] for k,v in r['table_F'].items()]),'',
        '耗时仅为观测值，不将非隔离批次时间差归因于单项修改。每骨架时间、未完成清单和指纹稳定性见 JSON。','',
        '## 公共抽签分层','',table(['approach','slot','method','登记','A PASS/完成','B PASS/完成'],[[x['approach_mode'],x['common_slot'],x['method'],x['registered'],str(x['a']['pass'])+'/'+str(x['a']['completed']),str(x['b']['pass'])+'/'+str(x['b']['completed'])] for x in r['public_draw_summary']]),'','## 正确性与限制','',f"硬停止事件：{json.dumps(r['hard_stops'],ensure_ascii=False)}",f"P0 停止事件：{r['P0_stop_count']}",
        f"全部合法提案原始合同核验数：{r['all_accepted_checks_verified']}",f"测试登记：{json.dumps(r['validation'],ensure_ascii=False)}",'']
    return '\n'.join(lines)+'\n'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--a',type=Path);p.add_argument('--b',type=Path);p.add_argument('--descriptors',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--register',choices=['A','B']);p.add_argument('--attempts',nargs='+',type=Path)
    p.add_argument('--cohort',type=Path);p.add_argument('--validation',type=Path)
    args=p.parse_args()
    if args.register:
        result=register(args.attempts,args.descriptors,args.cohort,args.register);save(args.out,result)
        print(json.dumps({'status':result['status'],'completed':len(result['skeletons']),'unfinished':result['unfinished'],'out':str(args.out)}));return
    assert args.a and args.b
    result=compare(load_manifest(args.a,args.descriptors),load_manifest(args.b,args.descriptors),args.descriptors,read(args.validation) if args.validation else None)
    args.out.mkdir(parents=True,exist_ok=True)
    save(args.out/'p2_ab_comparison.json',result)
    (args.out/'p2_ab_comparison.md').write_text(markdown(result),encoding='utf-8',newline='\n')
    print(json.dumps({'status':result['status'],'hard_stops':result['hard_stops'],'table_C':result['table_C'],'witnesses':result['table_D']['recovery_witness_count']},indent=2))

if __name__=='__main__':main()
