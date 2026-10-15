"""Fixed-order same-map fallback only when a registered reference cannot plan."""
def select_abort_reference(requested, by_id, by_episode):
    family_candidates=sorted(sid for sid,job in by_id.items()
        if job['descriptor']['family_id']==requested['family_id'] and job['descriptor']['base_intent']=='penetration')
    original=requested.get('source_skeleton_id') or requested.get('reference_skeleton_id') or family_candidates[0]
    if original not in family_candidates:
        from .contracts import P0ContractError
        raise P0ContractError('Initial abort reference must name a registered same-family penetration skeleton')
    map_id=by_id[original]['descriptor']['map_id']
    alternatives=sorted(sid for sid,job in by_id.items() if sid!=original
        and job['descriptor']['map_id']==map_id and job['descriptor']['base_intent']=='penetration')
    attempts=[]
    for sid in [original,*alternatives]:
        record=by_episode[sid+'_synchronous']
        planning_failed=record['state']=='infeasible' and record.get('path') is None
        attempts.append({'skeleton_id':sid,'state':record['state'],'reason':record.get('reason'),
                         'planning_failed':planning_failed})
        if not planning_failed:
            return sid,{'original_reference_skeleton_id':original,'selected_reference_skeleton_id':sid,
                        'same_map_id':map_id,'replaced':sid!=original,'all_planning_failed':False,
                        'fixed_order':'registered reference first; all remaining same-map penetration IDs ascending',
                        'attempts':attempts}
    return original,{'original_reference_skeleton_id':original,'selected_reference_skeleton_id':None,
                     'same_map_id':map_id,'replaced':False,'all_planning_failed':True,
                     'fixed_order':'registered reference first; all remaining same-map penetration IDs ascending',
                     'attempts':attempts}
