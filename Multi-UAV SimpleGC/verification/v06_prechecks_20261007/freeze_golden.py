"""Generate full DR130 with unchanged baseline, compare actual PP/B bundles."""
import copy
import json
from pathlib import Path
from diagnose import PROJECT, STUDY, ARCHIVE, read, save, digest
from swarm_sim.generation import canonical_hash, verify_generation
from swarm_sim.generation_v2 import generate_v2


def first_diff(a, b, path='$'):
    if type(a) is not type(b):
        return dict(path=path, generated=a, archived=b)
    if isinstance(a, dict):
        if set(a) != set(b):
            return dict(path=path, generated_keys=sorted(a), archived_keys=sorted(b))
        for key in a:
            difference = first_diff(a[key], b[key], path + '.' + key)
            if difference:
                return difference
    elif isinstance(a, list):
        if len(a) != len(b):
            return dict(path=path, generated_length=len(a), archived_length=len(b))
        for index, (left, right) in enumerate(zip(a, b)):
            difference = first_diff(left, right, path + f'[{index}]')
            if difference:
                return difference
    elif a != b:
        return dict(path=path, generated=a, archived=b)


def exact(a, b, subject):
    difference = first_diff(a, b)
    if difference:
        save('golden_mismatch.json', dict(subject=subject, difference=difference))
        raise RuntimeError('section 7.3 baseline/archive difference: ' + subject + ' ' + str(difference))


output = STUDY / 'generated_DR130'
generate_v2(PROJECT / 'generation_profiles/dual_intent_v05c.json', output)
listing, _ = verify_generation(output / 'mission_list.json')
assert len(listing['missions']) == 260
archive_dr = ARCHIVE / 'tmp_v05/dr_v05c/generated_130'
exact(listing, read(archive_dr / 'mission_list.json'), 'full DR130 mission_list')
by_id = {e['mission_id']: e for e in listing['missions']}
rows = []
bundle_checks = []
for tag, base_start, base_stop, field, relative in (
        ('PP', 0, 10, 'pilot_index', 'verification/v05_r12b_pp_20261002/bundle'),
        ('B', 10, 130, 'batch_index', 'verification/v05_batch_20261002/bundle')):
    bundle = ARCHIVE / relative
    archived = read(bundle / 'mission_list.json')
    expected = []
    for base in range(base_start, base_stop):
        for intent in ('reconnaissance', 'patrol'):
            entry = copy.deepcopy(next(e for e in listing['missions'] if e['base_index'] == base and e['intent'] == intent))
            entry[field] = len(expected)
            entry.update(task=f"missions/{entry['mission_id']}.json", scene=f"scenes/{entry['mission_id']}.json")
            entry['task_sha256'] = digest(output / entry['task'])
            entry['scene_sha256'] = digest(output / entry['scene'])
            expected.append(entry)
    expected_listing = dict(listing, missions=expected)
    exact(expected_listing, archived, tag + ' complete actual mission_list including controller fields')
    for index, entry in enumerate(expected):
        task, scene = read(output / entry['task']), read(output / entry['scene'])
        exact(task, read(bundle / entry['task']), f'{tag}{index+1} task')
        exact(scene, read(bundle / entry['scene']), f'{tag}{index+1} plan')
        assert digest(output / entry['task']) == digest(bundle / entry['task'])
        assert digest(output / entry['scene']) == digest(bundle / entry['scene'])
        original_entry = by_id[entry['mission_id']]
        rows.append(dict(global_index=len(rows), batch=tag, batch_index=index,
                         mission_id=entry['mission_id'], base_index=entry['base_index'], intent=entry['intent'],
                         entry_sha256=canonical_hash(original_entry), task_sha256=canonical_hash(task),
                         plan_sha256=canonical_hash(scene), archived_entry_sha256=canonical_hash(entry)))
    bundle_checks.append(dict(batch=tag, matched=len(expected), total=len(archived['missions']),
                              listing_sha256=digest(bundle / 'mission_list.json'),
                              controller_field=field, complete_listing_exact=True, task_plan_bytes_exact=True))
    print(tag, len(expected), 'exact matches', flush=True)
fixture = dict(schema_version=1, baseline_commit='fe7ac4da8bb41498bcb1ba97ac20df76b71ab7c0',
               master_seed=2026100205, base_scene_count=130, task_count=260,
               canonicalization='UTF-8 JSON: sort_keys=True, separators=(comma,colon), ensure_ascii=False, allow_nan=False',
               profile_canonical_sha256=canonical_hash(read(output / 'generation_profile.json')),
               listing_canonical_sha256=canonical_hash(listing), archive_checks=bundle_checks, tasks=rows)
save('intent_registry_DR130_golden.json', fixture)
assert (STUDY / 'intent_registry_DR130_golden.json').stat().st_size < 5 * 1024 * 1024
save('golden_summary.json', dict(pass_all=True, counts=dict(PP=20, B=240, total=260),
     fixture_sha256=digest(STUDY / 'intent_registry_DR130_golden.json'),
     fixture_bytes=(STUDY / 'intent_registry_DR130_golden.json').stat().st_size,
     baseline_commit=fixture['baseline_commit'], archive_checks=bundle_checks))
print('Golden ready:', len(rows), (STUDY / 'intent_registry_DR130_golden.json').stat().st_size, flush=True)
