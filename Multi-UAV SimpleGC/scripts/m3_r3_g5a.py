"""G-5a exact legacy signatures; only human-authorized path tokens normalize."""
import re
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]


def normalize_message(message, checkout_roots=()):
    # Nothing else is normalized: errno, filename, spacing and all text remain exact.
    roots={str(Path(p)) for p in checkout_roots}
    forms={s for p in roots for s in (p,p.replace('\\','/'),p.replace('\\','\\\\'))}
    for root in sorted(forms,key=len,reverse=True):message=message.replace(root,'<ROOT>')
    return re.sub(r'(?<=[\\/])tmp[a-zA-Z0-9_]+(?=[\\/])','<TMP>',message)


def signature(failure, checkout_roots=()):
    trace=failure['traceback'].rstrip('\n');lines=trace.splitlines()
    types=re.findall(r'^([A-Za-z_][\w.]*(?:Error|Exception))(?::|$)',trace,re.M)
    if not types:raise ValueError('No exception type in failed-test traceback')
    return dict(kind=failure['kind'],exception_type=types[-1],last_line=normalize_message(lines[-1],checkout_roots))
