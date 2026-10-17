"""Read-only D0b oracle imports; production imports remain this worktree's."""
import importlib.util,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
D0_PROJECT=PROJECT.parents[1]/'Simulation-fe-corner-audit/Multi-UAV SimpleGC'

def d0b_oracle():
    from task_v07 import execution
    from swarm_sim.fast_dynamics import route_tracker
    name='scripts.probe_v07_fe_corner_fillet'
    if name in sys.modules:return sys.modules[name]
    previous=list(sys.path)
    try:
        for short in ('qc_v07_fe_corner_dwell','probe_v07_fe_corner_cap','probe_v07_fe_corner_fillet'):
            full='scripts.'+short
            spec=importlib.util.spec_from_file_location(full,D0_PROJECT/'scripts'/f'{short}.py')
            module=importlib.util.module_from_spec(spec);sys.modules[full]=module;spec.loader.exec_module(module)
        return sys.modules[name]
    finally:sys.path[:]=previous
