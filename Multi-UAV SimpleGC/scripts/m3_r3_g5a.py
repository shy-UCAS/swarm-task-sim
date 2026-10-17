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


def regression_g5a(candidate,baseline,known,checkout_roots=()):
    failures=[];accepted=[];unexpected_pass=[];per_test=[]
    for tid,value in candidate['outcomes'].items():
        actual=None;classification='PASS'
        if value=='ok':
            if tid in known:unexpected_pass.append(tid);classification='KNOWN_FAILURE_NOW_PASS'
        elif value in ('FAIL','ERROR') and tid in candidate['failures']:
            actual=signature(candidate['failures'][tid],checkout_roots)
            if tid in known and actual==known[tid]:accepted.append(tid);classification='BASELINE_KNOWN_FAILURE'
            else:failures.append(dict(test_id=tid,reason='NEW_FAILURE_OR_CHANGED_SIGNATURE',expected=known.get(tid),actual=actual));classification='NEW_REGRESSION'
        else:failures.append(dict(test_id=tid,reason='UNEXPECTED_SKIP_OR_OUTCOME',actual=value));classification='NEW_REGRESSION'
        per_test.append(dict(test_id=tid,baseline=baseline['outcomes'].get(tid,'NEW_TEST'),candidate=value,classification=classification,signature=actual))
    for tid in set(baseline['outcomes'])-set(candidate['outcomes']):failures.append(dict(test_id=tid,reason='MISSING_TEST'))
    return dict(name='G5a_REGRESSION_DELTA_ZERO',status='FAIL' if failures else 'PASS',executed=candidate['count'],passed=sum(v=='ok' for v in candidate['outcomes'].values()),baseline_known_failure=len(accepted),unexpected_known_passes=sorted(unexpected_pass),new_failure_count=len(failures),failures=failures,per_test=per_test)


def load_amendment():
    from scripts.audit_m3_r3_r0 import read,digest,REPORT
    record=read(REPORT/'G5a_gate_amendment.json')
    assert record['status']=='PASS' and len(record['known_signatures'])==18
    for path,sha in record['locked_evidence_sha256'].items():assert digest(path)==sha,path
    return record


def self_check(baseline,known,roots):
    import copy
    count=0
    def expect(row,status):
        nonlocal count
        assert regression_g5a(row,baseline,known,roots)['status']==status;count+=1
    expect(baseline,'PASS')
    key=next(iter(known));good=next(k for k,v in baseline['outcomes'].items() if v=='ok')
    row=copy.deepcopy(baseline);row['outcomes'][key]='ok';del row['failures'][key];expect(row,'PASS')
    row=copy.deepcopy(baseline);row['failures'][key]['traceback']+=' changed';expect(row,'FAIL')
    row=copy.deepcopy(baseline);row['failures'][key]['kind']='FAIL' if row['failures'][key]['kind']=='ERROR' else 'ERROR';expect(row,'FAIL')
    row=copy.deepcopy(baseline);row['outcomes'][good]='FAIL';row['failures'][good]=dict(kind='FAIL',traceback='AssertionError: new');expect(row,'FAIL')
    row=copy.deepcopy(baseline);del row['outcomes'][good];row['count']-=1;expect(row,'FAIL')
    row=copy.deepcopy(baseline);row['outcomes'][good]='skipped test';expect(row,'FAIL')
    return dict(status='PASS',checks=count,tests_modified=False)
