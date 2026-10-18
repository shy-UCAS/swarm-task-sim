"""Emit targeted A1 line evidence without writing to production or fixtures."""
from contextlib import contextmanager
import json
from pathlib import Path
import sys


@contextmanager
def line_evidence(label, *functions):
    filenames={f.__code__.co_filename for f in functions}
    hits={name:set() for name in filenames}
    previous=sys.gettrace()
    def trace(frame,event,arg):
        filename=frame.f_code.co_filename
        if filename not in filenames:
            return None
        if event == 'line':
            hits[filename].add(frame.f_lineno)
        return trace
    sys.settrace(trace)
    try:
        yield
    finally:
        sys.settrace(previous)
        project=Path(__file__).resolve().parents[1]
        print('A1_LINE_EVIDENCE '+json.dumps({'test':label,'files':{
            Path(name).resolve().relative_to(project).as_posix():sorted(lines)
            for name,lines in sorted(hits.items())}},sort_keys=True),flush=True)
