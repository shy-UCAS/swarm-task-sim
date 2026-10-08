"""Read-only r2 truncation probe; production code is imported unchanged."""
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
DATA = Path(os.environ['SIM_DATA_ROOT']).resolve()
STUDY = DATA / 'r2_fe7ac4d'
PROJECT = STUDY / 'baseline' / 'Multi-UAV SimpleGC'
ARCHIVE = Path('F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation/Multi-UAV SimpleGC')
SOURCE = Path('F:/CASIA/Drone Swarm Situational Awareness Algorithm/Simulation-dev')


def guard(event, args):
    paths = []
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        _, mode, flags = args
        if (mode and any(c in mode for c in 'wax+')) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
            paths.append(args[0])
    elif event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime'):
        paths.append(args[0])
    elif event in ('os.rename', 'os.link', 'os.symlink'):
        paths.extend(args[:2])
    for path in paths:
        if isinstance(path, (str, bytes, os.PathLike)):
            resolved = Path(os.fsdecode(path)).resolve()
            if not resolved.is_relative_to(DATA) or resolved.is_relative_to(PROJECT):
                raise PermissionError('diagnostic write outside result directory: ' + str(resolved))
    if event == 'subprocess.Popen':
        raise PermissionError('no subprocess or simulator allowed in diagnostic')


sys.addaudithook(guard)
sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)
from swarm_sim import analysis_v3, observer_facts_v0 as observer
from swarm_sim.mission_evaluation_v3 import evaluate_mission_v3
from swarm_sim.language_templates_v0 import generate_descriptions
from swarm_sim.episode_loader import load_episode


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    (STUDY / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


BATCH = ARCHIVE / 'verification/v05_batch_20261002'
DATASET = BATCH / 'dataset'
LANGUAGE = BATCH / 'dataset_language_zh_v0'
DATASET_HASH = digest(DATASET / 'dataset_manifest.json')
CONTROL = read(BATCH / 'control.json')
SELECTIONS = read(BATCH / 'analysis_selections.json')
RECORDS = [(f'PP{i+1:02d}', r) for i, r in enumerate(CONTROL['pilot_records'])]
RECORDS += [(f'B{i+1:03d}', r) for i, r in enumerate(CONTROL['records'])]
DESCRIPTIONS = read(LANGUAGE / 'descriptions.json')['descriptions']


def select():
    chosen = {}
    for number, record in RECORDS:
        if not record['episode_quality_eligible']:
            continue
        episode = DATASET / 'episodes' / record['run_id']
        task = read(episode / 'task.json')['mission']
        if task['intent'] == 'patrol':
            laps = task['intent_params']['laps']
            slot = ('patrol_3_return' if laps == 3 and task['return_required'] else
                    'patrol_2' if laps == 2 else None)
        else:
            slot = 'recon_return' if task['return_required'] else 'recon_no_return'
        if slot and slot not in chosen:
            chosen[slot] = (number, record)
        if len(chosen) == 4:
            break
    assert len(chosen) == 4, chosen
    return chosen


class Captured(Exception):
    pass


def inputs(record):
    captured = {}
    def capture(*args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        raise Captured()
    # Execute the unchanged raw-packet/clock resampling path, then stop before
    # analysis output. The captured trajectory includes its internal end bracket.
    with patch.object(analysis_v3, 'evaluate_mission_v3', capture):
        try:
            analysis_v3.analyze_run_v3(record['run_directory'], CONTROL['quality_policy'],
                progress_mapping_version='ordered_route_progress_v2',
                patrol_validator_version='perimeter_revisit_v2',
                acceptance_policy='v05_acceptance_r1_2b', acceptance_stage='batch',
                output_directory=STUDY / ('never_written_' + record['run_id']), update_latest=False)
        except Captured:
            pass
    assert captured
    return captured


def facts_for(episode, semantic, cutoff=None):
    agents = load_episode(episode, verify_hashes=True)['agent_ids']
    docs = {name: read(episode / name) for name in ('manifest.json', 'task.json')}
    docs.update({'labels.json': semantic['labels'], 'semantic_validation.json': semantic['semantic_validation'],
                 'phase_windows.json': semantic['phase_windows']})
    streams = {name: observer._traces(episode / name, agents) for name in ('truth.csv', 'observations.csv')}
    if cutoff is not None:
        streams = {name: {a: [(t, p) for t, p in rows if t <= cutoff] for a, rows in stream.items()}
                   for name, stream in streams.items()}
    # Only replace file adapters with in-memory values. All fact and language
    # computations below are the original production functions, unmodified.
    with patch.object(observer, '_json', lambda p: copy.deepcopy(docs[p.name])), \
         patch.object(observer, '_traces', lambda p, _: copy.deepcopy(streams[p.name])), \
         patch.object(observer, 'load_episode', lambda *a, **k: {'agent_ids': agents}):
        return observer.extract_observer_facts(episode, DATASET_HASH)


def language(facts, episode, split):
    seed = int(hashlib.sha256((DATASET_HASH + ':' + episode + ':templates_zh_v0').encode()).hexdigest()[:16], 16)
    return generate_descriptions(facts, episode, split, seed)


def tri(value):
    return '是' if value is True else '否' if value is False else '未知'


def summary(semantic, facts, descriptions, intent):
    condition = 'max_gap' if intent == 'patrol' else 'coverage'
    by_channel = {}
    for channel in ('truth', 'observation'):
        values = semantic['semantic_validation']['condition_results'][channel]
        by_channel[channel] = dict(intent_success=tri(values[condition]),
            return_success=tri(values['return_to_launch']),
            mission_success=tri(semantic['semantic_validation'][channel]['mission_success']),
            laps=semantic['semantic_validation'][channel].get('perimeter_revisit', {}).get('per_agent_laps_observed'))
    return dict(channels=by_channel, observed_laps=facts['observed']['per_agent_laps_observed'],
                observed_return=tri(facts['observed']['return_observed']),
                sentences=[s for s in descriptions[0]['sentences']
                           if s['template_id'].startswith(('T3.', 'T4.', 'T6.'))])


def run():
    report = dict(baseline='fe7ac4da8bb41498bcb1ba97ac20df76b71ab7c0',
                  dataset_sha256=DATASET_HASH, method='truncate both position streams in memory; keep scene, events, clocks, metadata unchanged; recompute windows, metrics, facts, text',
                  samples=[], all_pass=True)
    for slot, (number, record) in select().items():
        episode = DATASET / 'episodes' / record['run_id']
        task = read(episode / 'task.json')
        selection = SELECTIONS[str(Path(record['run_directory']))]
        assert digest(Path(selection['directory']) / 'manifest.json') == selection['manifest_sha256']
        print('Reading', number, slot, flush=True)
        captured = inputs(record)
        original = evaluate_mission_v3(*captured['args'], **captured['kwargs'])
        facts = facts_for(episode, original)
        split = next(d['episode_split'] for d in DESCRIPTIONS if d['episode_id'] == record['run_id'])
        descriptions = language(facts, record['run_id'], split)
        saved_labels = read(Path(selection['directory']) / 'labels.json')
        saved_semantic = read(Path(selection['directory']) / 'semantic_validation.json')
        checks = dict(success=all(original['labels'][k] == saved_labels[k] for k in ('mission_success', 'mission_success_observation', 'semantic_consistency')),
                      conditions=original['semantic_validation']['condition_results'] == saved_semantic['condition_results'],
                      facts=facts == read(LANGUAGE / 'facts' / (record['run_id'] + '.json')),
                      descriptions=descriptions == [d for d in DESCRIPTIONS if d['episode_id'] == record['run_id']])
        if not all(checks.values()):
            save('baseline_mismatch.json', dict(number=number, checks=checks, facts=facts, original=original, descriptions=descriptions))
            raise RuntimeError('section 7.3 baseline/archive discrepancy ' + str(checks))
        intent = task['mission']['intent']
        main = 'patrol' if intent == 'patrol' else 'observe'
        windows = original['phase_windows']['channels']['truth']
        main_windows = [w for w in windows if w['semantic_phase'] == main]
        start, end = min(w['start_s'] for w in main_windows), max(w['arrival_s'] for w in main_windows)
        cuts = [('half_main', (start + end) / 2)]
        if task['mission']['return_required']:
            before_return = min(w['phase_release_s'] for w in windows if w['semantic_phase'] == 'return') - 1e-6
            assert before_return >= end, (end, before_return)
            cuts.append(('before_return', before_return))
        sample = dict(number=number, slot=slot, run_id=record['run_id'], selected_analysis=selection,
                      return_required=task['mission']['return_required'], baseline_checks=checks,
                      original=summary(original, facts, descriptions, intent), cuts=[])
        for kind, cutoff in cuts:
            args = copy.deepcopy(captured['args'])
            for index in (1, 2):
                args = list(args)
                args[index] = {a: [(t, p) for t, p in rows if t <= cutoff] for a, rows in args[index].items()}
            perturbed = evaluate_mission_v3(*args, **copy.deepcopy(captured['kwargs']))
            new_facts = facts_for(episode, perturbed, cutoff)
            new_text = language(new_facts, record['run_id'], split)
            condition = 'max_gap' if intent == 'patrol' else 'coverage'
            results = perturbed['semantic_validation']['condition_results']
            checks = {}
            if kind == 'half_main':
                checks['intent_not_true'] = all(results[c][condition] is not True for c in results)
                if intent == 'patrol':
                    old = facts['observed']['per_agent_laps_observed']
                    new = new_facts['observed']['per_agent_laps_observed']
                    checks['laps_smaller_or_unknown'] = new is None or all(b < a for a, b in zip(old, new))
                    checks['no_original_lap_claim'] = all(not s['template_id'].startswith('T6.laps') or new != old
                                                        for d in new_text for s in d['sentences'])
            else:
                checks['return_not_true'] = all(results[c]['return_to_launch'] is not True for c in results)
                checks['no_return_claim'] = all(not s['template_id'].startswith(('T3.return_pass', 'T4.return_true'))
                                                for d in new_text for s in d['sentences'])
            passed = all(checks.values())
            sample['cuts'].append(dict(kind=kind, cutoff_s=cutoff, checks=checks, passed=passed,
                                       result=summary(perturbed, new_facts, new_text, intent)))
            save(number + '_' + kind + '.json', dict(semantic=perturbed, facts=new_facts, descriptions=new_text))
            report['all_pass'] &= passed
            print(number, kind, sample['cuts'][-1]['result']['channels'], checks, flush=True)
        report['samples'].append(sample)
        save('truncation_diagnostic.json', report)
        if not report['all_pass']:
            raise RuntimeError('section 7.4 truncation discrepancy; stop without modifying production')
    save('truncation_diagnostic.json', report)
    print('ALL PASS', len(report['samples']), flush=True)


if __name__ == '__main__':
    run()
