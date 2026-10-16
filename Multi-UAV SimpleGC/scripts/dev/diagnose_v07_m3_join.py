"""Reproduce one registered Q2 proposal for implementation-error diagnostics."""
from pathlib import Path
import sys, random, json
PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
from task_v07.io import read_json
from scripts.run_v07_s2_expansion import descriptor_jobs
from task_v07.unified.spec import build_spec, proposal_seed
from task_v07.unified.free_space import free_space, work_region
from task_v07.unified.shapes import draw_shape
from task_v07.unified.route import route_group, GeometryRejected
registered = read_json(PROJECT/'docs/v07/evidence/m3/m3_inputs.json')
sid = 'family_s12_4d13d93f9171c446_ext_005_regular'
job = descriptor_jobs(registered['descriptor_attempt'], [sid], PROJECT)[0]
d = job['descriptor']; g = d['task_groups'][1]; scene = job['scene']
spec = build_spec(d, g); free = free_space(scene, spec); rng = random.Random(proposal_seed(spec, 0))
shape = draw_shape(spec, work_region(scene, spec, free), rng, free)
try:
    bundle, template = route_group(scene, spec, shape, free, d['family_conditions']['initial_states'], rng)
    print('connection passed')
except GeometryRejected as exc:
    print(json.dumps(exc.evidence[0], ensure_ascii=False))
