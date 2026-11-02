"""Auditor-authored expected-value oracle; imports no repository modules.

This verifies synthetic input expectations, NOT behavior of invest.
"""
from collections import Counter
from datetime import date
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEYS = ('instrument', 'field', 'period_end', 'available_date')

def expected(rows, cutoff):
    visible = [r for r in rows if r['available_date'] <= cutoff]
    if not visible:
        return None
    chosen = max(visible, key=lambda r: (r['period_end'], r['available_date']))
    return chosen['value']

def conflicts(rows):
    return [list(k) for k, n in Counter(tuple(r[k] for k in KEYS) for r in rows).items() if n > 1]

rows = [
    dict(instrument='SYN_A',field='bp',period_end='2023-12-31',available_date='2024-02-01',value=1.0),
    dict(instrument='SYN_A',field='bp',period_end='2024-03-31',available_date='2024-04-15',value=2.0),
    dict(instrument='SYN_A',field='bp',period_end='2023-12-31',available_date='2024-05-01',value=99.0),
    dict(instrument='SYN_A',field='bp',period_end='2024-03-31',available_date='2024-05-02',value=2.5),
]
expected_values = {d: expected(rows,d) for d in ['2024-01-31','2024-02-01','2024-04-15','2024-05-01','2024-05-02']}
assert list(expected_values.values()) == [None,1.0,2.0,2.0,2.5]
assert expected(rows[:2], '2024-04-15') == expected(rows, '2024-04-15') == 2.0
bad = [rows[0], {**rows[0], 'value':9.0}]
good = [rows[0], {**rows[0], 'available_date':'2024-02-02', 'value':9.0}]
assert conflicts(bad) and not conflicts(good)
out = {'label':'synthetic reference-only expectations, no product execution',
       'C1_expected':expected_values,
       'C2_conflicting_rows':bad,'C2_duplicate_keys':conflicts(bad),
       'C2_control_distinct_revisions':good,'C2_control_duplicate_keys':conflicts(good),
       'product_runs':0,'product_repeats':0,'negative_product_control_runs':0}
(ROOT/'oracle-result.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out))
