"""Intent-independent public split geometry, keyed by family/slot/member set."""
import math
import random

from task_v07.planning import seed_for


def public_approach_shape(family, common_slot, members, multi=True):
    ids = sorted(set(members))
    if len(ids) != len(members) or len(ids) < 2:
        raise ValueError('A task group requires at least two distinct physical IDs')
    key = f"public-approach-v1:{family.get('family_id', '')}:slot:{common_slot}:members:{','.join(ids)}"
    seed = seed_for(family.get('sampling_seed', 0), key)
    rng = random.Random(seed)
    count = 2 if len(ids) <= 5 else rng.choice((2, 3))
    if count == 2:
        differences = [rng.uniform(100., 180.)]
    else:
        differences = [rng.uniform(50., 120.), rng.uniform(50., 120.)]
    angles = [0.]
    for difference in differences:
        angles.append(angles[-1] + difference)
    order = ids[:]
    rng.shuffle(order)
    sizes = [len(ids)//count + (i < len(ids) % count) for i in range(count)]
    split = []
    begin = 0
    for size in sizes:
        split.append(order[begin:begin+size])
        begin += size
    return {'version': 'public-approach-v1', 'family_id': family.get('family_id'),
            'common_slot': common_slot, 'member_set': ids, 'seed': seed,
            'members': split if multi else [order],
            'split_count': count if multi else 1,
            'adjacent_differences_deg': differences if multi else [],
            'relative_bearings_deg': angles if multi else [0.],
            'relative_bearings_rad': [math.radians(a) for a in angles] if multi else [0.],
            'shared_between_intents': True, 'shared_between_timing_versions': True,
            'key_excludes': ['intent', 'role', 'target', 'column_seed', 'timing', 'extended_skeleton_ordinal']}
