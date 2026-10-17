"""FE-P2 read-only diagnosis with registered entity attribution and explicit units."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from scripts.summarize_v07_s15_yield import classify, load_attempts
from task_v07.io import read_json, sha
MODES=('multi_direction','same_direction')
WATCH=('ingress_line_blocked','inner_alignment_blocked','no_interior_connection','connection_search_budget_exhausted','whole_route_check')

def walk(node):
    if isinstance(node,dict):
        yield node
        for value in node.values():yield from walk(value)
    elif isinstance(node,list):
        for value in node:yield from walk(value)

def load_inputs(directory):
    directory=Path(directory); descriptors={d['skeleton_id']:d for d in read_json(directory/'private_skeleton_descriptors.json')}
    reg=read_json(directory/'registration.json'); candidates={r['candidate_index']:r for r in read_json(Path(reg['source_attempt'])/'candidates.json')}
    maps={}; verification=[]
    for r in reg['selected']:
        root=Path(candidates[r['candidate_index']]['directory']); scene=read_json(root/'public_scene.json'); family=read_json(root/'family_initial.json')
        entities={e['id']:e for e in scene['entities']}
        if len(entities)!=len(scene['entities']):raise ValueError('Duplicate entity ID: '+str(root))
        for entity in entities.values():
            if entity.get('facility_id'):
                fid=entity['facility_id']
                if fid not in entities or entities[fid]['type']!='facility' or not (entity['id']==fid or entity['id'].startswith(fid+'_')):
                    raise ValueError('Entity/facility registration mismatch: '+repr(entity))
        maps[r['family_id']]={'scene':scene,'entities':entities,'placements':{v['obstacle_id']:v['placement'] for v in family['obstacle_placements']}}
        verification.append({'family_id':r['family_id'],'scene_path':str(root/'public_scene.json'),'scene_sha256':sha(root/'public_scene.json'),'facility_layers':{k:v.get('facility_id',k) for k,v in entities.items() if v['type']=='facility' or v.get('facility_id')}})
    for d in descriptors.values():
        for group in d['task_groups']:
            target=group['target_id']; entities=maps[d['family_id']]['entities']
            if target not in entities or entities[target]['type']!='facility':raise ValueError('Unregistered target: '+target)
    return descriptors,maps,verification

def attribution(evidence,target,mapping):
    entity=evidence.get('entity_id')
    if not isinstance(entity,str):raise ValueError('Phase evidence has no entity_id: '+repr(evidence))
    if entity=='world':
        if not mapping['scene'].get('world'):raise ValueError('World boundary absent from scene')
    elif entity not in mapping['entities']:raise ValueError('Unregistered evidence entity: '+entity)
    is_target=entity==target or entity.startswith(target+'_')
    if entity in mapping['entities']:
        item=mapping['entities'][entity]
        owner=item.get('facility_id',entity if item['type']=='facility' else None)
        if (owner==target)!=is_target:raise ValueError('Entity prefix disagrees with registered owner: '+entity)
    anomalies=[]; category=classify(entity,target,mapping['placements'],anomalies)
    if anomalies or (category=='target_facility')!=is_target:raise ValueError('classify attribution mismatch: '+repr(anomalies))
    return is_target

def empty():
    return {'proposals':0,'accepted_proposals':0,'rejected_proposals':0,'top_reasons':Counter(),'shape_reasons':Counter(),'phase_evidence':Counter(),'proposal_reason_hits':Counter(),'proposal_phase_hits':Counter(),'reason_node_occurrences':Counter()}

def add(stats,record,target,mapping):
    stats['proposals']+=1
    if not record['reason']:
        stats['accepted_proposals']+=1;return
    stats['rejected_proposals']+=1;stats['top_reasons'][record['reason']]+=1
    nodes=list(walk(record)); reasons=set(); phases=set()
    for node in nodes:
        if node.get('reason'):
            reasons.add(node['reason']);stats['reason_node_occurrences'][node['reason']]+=1
            if 'draw' in node:stats['shape_reasons'][node['reason']]+=1
        if 'phase' in node:
            key=(node['phase'],node.get('kind','<missing>'),attribution(node,target,mapping))
            stats['phase_evidence'][key]+=1;phases.add(key)
    stats['proposal_reason_hits'].update(reasons);stats['proposal_phase_hits'].update(phases)

def serial(stats):
    out={k:dict(v) if isinstance(v,Counter) else v for k,v in stats.items() if k not in ('phase_evidence','proposal_phase_hits')}
    out['shape_attempt_rejections']=sum(stats['shape_reasons'].values())
    out['evidence_entries']=sum(stats['phase_evidence'].values())
    out['phase_evidence']=[{'phase':k[0],'kind':k[1],'is_target':k[2],'count':v,'proposals_with_evidence':stats['proposal_phase_hits'][k]} for k,v in sorted(stats['phase_evidence'].items())]
    return out

def diagnose(directories,descriptors,maps):
    attempts,owners,scope=load_attempts([Path(d) for d in directories],descriptors)
    views={name:{mode:empty() for mode in MODES} for name in ('all_recorded_attempts','completed_owner')};journals=[];identities=Counter()
    for attempt in attempts:
        for f in sorted(attempt['dir'].glob('*/proposals.jsonl')):
            sid=f.parent.name;d=descriptors[sid];groups={g['group_id']:g for g in d['task_groups']};n=0;ids=set()
            with f.open(encoding='utf-8') as stream:
                for lineno,line in enumerate(stream,1):
                    if not line.strip():continue
                    record=json.loads(line);g=groups[record['group_id']]
                    if record['proposal_id'] in ids:raise ValueError(f'Duplicate proposal in {f}:{lineno}')
                    ids.add(record['proposal_id'])
                    if g['execution_method']!='area_search':continue
                    n+=1; identities[(sid,record['proposal_id'])]+=1;mode=d['common_draw']['approach_mode']
                    add(views['all_recorded_attempts'][mode],record,g['target_id'],maps[d['family_id']])
                    if sid in owners and owners[sid]['dir']==attempt['dir']:
                        add(views['completed_owner'][mode],record,g['target_id'],maps[d['family_id']])
            if n:journals.append({'path':str(f),'sha256':sha(f),'area_search_proposals':n,'completed_owner':sid in owners and owners[sid]['dir']==attempt['dir']})
    result={name:{mode:serial(value) for mode,value in stats.items()} for name,stats in views.items()}
    gates={}
    for name,view in result.items():
        multi=view['multi_direction']; shapes=multi['shape_attempt_rejections']; ingress=multi['shape_reasons'].get('ingress_line_blocked',0)
        target=sum(r['count'] for r in multi['phase_evidence'] if r['is_target']); entry=sum(r['count'] for r in multi['phase_evidence'] if r['is_target'] and r['phase']=='entry_to_work_start')
        gates[name]={'ingress_shape_attempts':ingress,'all_rejected_shape_attempts':shapes,'ingress_fraction':ingress/shapes if shapes else None,'entry_to_work_target_evidence':entry,'all_target_phase_evidence':target,'entry_target_fraction':entry/target if target else None,'pass':bool(shapes and target and ingress/shapes>=.5 and entry/target>=.8)}
    return {'views':result,'gates':gates,'journals':journals,'unique_proposal_identities':len(identities),'repeated_proposal_identities_across_attempts':sum(v>1 for v in identities.values()),'repeated_execution_records':sum(v-1 for v in identities.values())}

def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','|'+'---|'*len(headers),*['| '+' | '.join(str(v) for v in row)+' |' for row in rows]])
def write_report(result,out):
    lines=['# FE-P2 area_search 拒绝阶段诊断','',f"状态：{result['status']}。",'', '统计单位独立：提案执行记录、被拒形态尝试、带 phase 的证据条目。单个提案可包含多个尝试及多条 slot/segment 证据；proposal_reason_hits 与 proposals_with_evidence 均在每个提案内去重。','目标归因使用 entity_id == target_id 或 entity_id.startswith(target_id + "_")；同时核验场景实体登记及 facility_id，不匹配时停止。','all_recorded_attempts 遍历两个历史 attempt 的所有日志；completed_owner 只取每个完成骨架所属 attempt，与原汇总口径一致。不同 attempt 中重复执行的同一提案不冒充独立提案身份。','']
    if result.get('anomalies'):lines+=['## 异常','',json.dumps(result['anomalies'],ensure_ascii=False,indent=2)]
    else:
        lines += [f"跨 attempt 重复提案身份 {result['repeated_proposal_identities_across_attempts']} 个，额外执行记录 {result['repeated_execution_records']} 条。",'']
        for name,views in result['views'].items():
            lines+=['## '+name,'',table(['单位/指标',*MODES],[[key,*[views[m][key] for m in MODES]] for key in ['proposals','accepted_proposals','rejected_proposals','shape_attempt_rejections','evidence_entries']]),'', '### 表 1：形态尝试拒绝原因（单位：形态尝试）','']
            reasons=sorted(set().union(*(set(views[m]['shape_reasons']) for m in MODES)))
            lines += [table(['reason',*MODES],[[reason,*[views[m]['shape_reasons'].get(reason,0) for m in MODES]] for reason in reasons]),'', '### 表 2：phase × kind × 目标归因（单位：证据条目）','']
            keys=sorted({(v['phase'],v['kind'],v['is_target']) for m in MODES for v in views[m]['phase_evidence']})
            counts={m:{(v['phase'],v['kind'],v['is_target']):v for v in views[m]['phase_evidence']} for m in MODES}
            lines += [table(['phase','kind','is_target',*MODES],[[*k,*[counts[m].get(k,{}).get('count',0) for m in MODES]] for k in keys]),'', '### 含上述证据的提案数（同一提案内去重）','',table(['phase','kind','is_target',*MODES],[[*k,*[counts[m].get(k,{}).get('proposals_with_evidence',0) for m in MODES]] for k in keys]),'', '门槛：'+json.dumps(result['gates'][name],ensure_ascii=False),'']
    out.parent.mkdir(parents=True,exist_ok=True)
    out.with_suffix('.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    out.with_suffix('.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--summary',type=Path,default=PROJECT/'docs/v07/evidence/s15/s15_yield_summary.json');parser.add_argument('--out',type=Path,default=PROJECT/'docs/v07/evidence/fe/p2_area_search_diagnosis');args=parser.parse_args()
    result={'generated_utc':datetime.now(timezone.utc).isoformat(),'status':'STOP','anomalies':[]}
    try:
        summary=read_json(args.summary);provenance=summary['provenance'];ds,maps,verification=load_inputs(provenance['descriptors'])
        result.update(descriptors=provenance['descriptors'],entity_registry_verification=verification,**diagnose([r['attempt'] for r in provenance['attempts']],ds,maps))
        result['status']='PASS' if result['gates']['all_recorded_attempts']['pass'] else 'GATE_NOT_MET'
    except Exception as exc:result['anomalies'].append({'type':type(exc).__name__,'message':str(exc)})
    write_report(result,args.out);print(json.dumps({k:result[k] for k in ('status','anomalies','gates') if k in result},ensure_ascii=False,indent=2));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
