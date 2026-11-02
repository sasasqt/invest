"""Trusted auditor code: reads source as text/AST; never imports repository code."""
import ast
import datetime as dt
import hashlib
import json
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT / 'source'
started = time.perf_counter()
tree = json.loads((ROOT / 'main-tree.json').read_text())
entries = {e['path']: e for e in tree['tree'] if e['type'] == 'blob'}
verified = []
for f in sorted(SOURCE.rglob('*')):
    if not f.is_file():
        continue
    path = f.relative_to(SOURCE).as_posix()
    b = f.read_bytes()
    digest = hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()
    assert digest == entries[path]['sha'], path
    verified.append({'path': path, 'blob': digest, 'bytes': len(b)})

def funcs(path):
    return {n.name: n for n in ast.parse((SOURCE / path).read_text()).body if isinstance(n, ast.FunctionDef)}

sp = 'data-pipeline/data-preparation/src/invest_data/schemas.py'
bp = 'data-pipeline/data-preparation/src/invest_data/bundle.py'
sf, bf = funcs(sp), funcs(bp)
observations = {
    'financial_column_comparison_fields': sorted({n.attr for n in ast.walk(sf['_check_columns']) if isinstance(n, ast.Attribute)}),
    'fundamentals_reader_direct_calls': sorted({n.func.id for n in ast.walk(sf['read_fundamentals']) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}),
    'fundamentals_reader_primary_key_references': sum(isinstance(n, ast.Attribute) and n.attr == 'primary_key' for n in ast.walk(sf['read_fundamentals'])),
    'generic_table_key_guard': ast.unparse(next(n.test for n in ast.walk(bf['_validate_table']) if isinstance(n, ast.If) and isinstance(n.test, ast.Attribute) and n.test.attr == 'primary_key')),
    'metadata_policy': 'fundamentals writer merges caller metadata after available_at default; reader does not validate available_at; unsupported timing policy is not established',
}

# Independent contract oracle: filter all visible records per decision, then select
# the newest period and its latest publication. This is not execution of pit.py.
rows = [
    {'instrument':'A','field':'bp','period_end':'2023-12-31','available_date':'2024-01-03','value':1.0},
    {'instrument':'A','field':'bp','period_end':'2023-12-31','available_date':'2024-01-06','value':1.1},
    {'instrument':'A','field':'bp','period_end':'2024-01-06','available_date':'2024-01-09','value':2.0},
    {'instrument':'A','field':'bp','period_end':'2023-12-31','available_date':'2024-01-11','value':9.9},
    {'instrument':'A','field':'other','period_end':'2024-01-06','available_date':'2024-01-09','value':99.0},
]
def expected(records, day, field='bp', instrument='A'):
    selected = [r for r in records if r['available_date'] <= day and r['field'] == field and r['instrument'] == instrument]
    keys = [(r['instrument'], r['field'], r['period_end'], r['available_date']) for r in selected]
    if len(set(keys)) != len(keys):
        raise ValueError('conflicting revision key')
    if not selected:
        return None
    newest_period = max(r['period_end'] for r in selected)
    latest = max((r for r in selected if r['period_end'] == newest_period), key=lambda r:r['available_date'])
    return latest['value']

cases=[]
for day, want in [('2024-01-02',None),('2024-01-03',1.0),('2024-01-05',1.0),('2024-01-08',1.1),('2024-01-09',2.0),('2024-01-11',2.0)]:
    actual=expected(rows,day)
    assert actual == want
    cases.append({'date':day,'oracle_expected':actual})
future=rows+[{'instrument':'A','field':'bp','period_end':'2024-01-12','available_date':'2024-01-15','value':123.0}]
assert all(expected(rows,c['date']) == expected(future,c['date']) for c in cases)
conflicting=[rows[0],{**rows[0],'value':2.0}]
try:
    expected(conflicting,'2024-01-03')
except ValueError:
    conflict_rejected=True
else:
    raise AssertionError('oracle should reject duplicate key')
result={
    'source_sha':tree['sha'], 'product_execution':False,
    'identity':{'tracked_blobs':len(entries),'verified_text_blobs':len(verified),'verified':verified,'not_materialized':[p for p in entries if p not in {x['path'] for x in verified}]},
    'static_observations':observations,
    'oracle':{'cases':cases,'future_append_prefix_unchanged':True,'duplicate_revision_rejected':conflict_rejected,'scope':'independently authored specification oracle only; no actual product result or historical investment inference'},
    'missing_runtime_check':'Read crafted synthetic conflicting fundamentals bundle and valid-key negative control twice in a proven credential-free exact-lock environment; compare actual as-of/feature output.'
}
result['elapsed_seconds']=time.perf_counter()-started
(ROOT/'static-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='identity'},indent=2))
print('canonical blobs',len(verified),'of',len(entries))
