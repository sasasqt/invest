"""Delta between last week's and this week's record-vs-main comparisons. Args: <old json> <new json> <out md>."""
import json, sys
from collections import Counter
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
def idx(d): return {(x["path"], x["key"], x["kind"]): x for x in d["differences"]}
A, B = idx(a), idx(b)
new = [B[k] for k in B if k not in A]; gone = [A[k] for k in A if k not in B]
changed = [(A[k], B[k]) for k in B if k in A and str(A[k].get("replay")) != str(B[k].get("replay"))]
lines = [f"old {a['counts']} n={len(a['differences'])}; new {b['counts']} n={len(b['differences'])}",
         f"new rows: {len(new)}; gone rows: {len(gone)}; same key, replay value changed: {len(changed)}"]
lines.append("by file (new): " + str(Counter(x['path'] for x in new)))
lines.append("by file (gone): " + str(Counter(x['path'] for x in gone)))
lines.append("by file (changed): " + str(Counter(x[1]['path'] for x in changed)))
for x in new[:40]: lines.append(f"NEW {x['path']} | {x['key']} | {x['kind']} | rec={str(x.get('record'))[:80]} | main={str(x.get('replay'))[:80]} | {x['severity']}")
for x in gone[:40]: lines.append(f"GONE {x['path']} | {x['key']} | {x['kind']} | rec={str(x.get('record'))[:80]} | old main={str(x.get('replay'))[:80]}")
for o, n in changed[:60]: lines.append(f"CHG {n['path']} | {n['key']} | rec={str(n.get('record'))[:60]} | old main={str(o.get('replay'))[:60]} | new main={str(n.get('replay'))[:60]}")
print("\n".join(lines)); open(sys.argv[3], "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("extra old", sorted(set(a['extra'])-set(b['extra'])), "extra new", sorted(set(b['extra'])-set(a['extra'])))
