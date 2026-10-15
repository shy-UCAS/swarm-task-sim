"""Search evidence distinguishes a failed proposal from a proof of no solution."""
from collections import Counter


def rejection(reason, *, scope='proposal', evidence=None, exhausted=False):
    evidence = list(evidence or [])
    category = ('search_budget_exhausted' if exhausted else
                'geometric_infeasibility' if evidence else 'local_proposal_failure')
    return {'classification': category, 'scope': scope, 'reason': reason,
            'geometric_evidence': evidence,
            'global_infeasibility_claimed': scope == 'entire_feasible_domain' and bool(evidence)}


def summarize(records):
    counts = Counter(r['rejection']['classification'] for r in records if r.get('rejection'))
    return dict(sorted(counts.items()))


def ring_evidence(ctx, samples):
    """Witnesses for this proposed ring only, not all allowed radii."""
    import numpy as np
    from task_v07.geometry import geometry_facts
    from .geometry_checks import check_polyline
    evidence = []
    distances = geometry_facts(ctx.geometry, samples)['signed_distance_m']
    for mask, constraint, limit in (
        (distances <= ctx.zones['alert']['offset_m']+5., 'target_alert_pad', ctx.zones['alert']['offset_m']+5.),
        (distances >= ctx.zones['warning']['offset_m']-5., 'target_warning_interior', ctx.zones['warning']['offset_m']-5.)):
        if np.any(mask):
            index = int(np.flatnonzero(mask)[0])
            evidence.append({'constraint': constraint, 'entity_id': ctx.group['target_id'],
                             'sample_index': index, 'signed_distance_m': float(distances[index]), 'limit_m': limit})
    check = check_polyline(ctx.scene, [[*p,ctx.altitude] for p in samples], margin_m=35.)
    # One witness per constraint/entity is sufficient; preserve exact segment.
    seen = set()
    for issue in check['issues']:
        key = (issue['code'],issue.get('entity_id'))
        if key not in seen:
            seen.add(key); evidence.append({'constraint': issue['code'], **issue})
    for entity,pad in ctx.forbidden:
        for index,(a,b) in enumerate(zip(samples,samples[1:])):
            clearance = float(geometry_facts(entity['geometry'],np.asarray([a,b]),footprint=True)['clearance_m'])
            if clearance < pad-1e-6:
                evidence.append({'constraint':'forbidden_region_pad','entity_id':entity['id'],
                                 'segment':index,'clearance_m':clearance,'required_m':pad})
                break
    return evidence
