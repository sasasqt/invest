"""Classify the lens's accepted-but-changed formulas into the known REVIEW-47/48 classes.
REVIEW-48 (BF-2026-11-12-2): ts_corr(x, x, w) with identical arguments. REVIEW-47 (BF-2026-11-12-1):
ts_std/ts_corr over windows of equal values: here an argument holding ts_min/ts_max (constant
stretches) or a self-correlation's output. Usage: python -I classify_scale_lens.py <lens.json>"""
import json, re, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
def args_of(expr, start):
    depth, i, parts, cur = 0, start, [], ""
    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth += 1
            if depth > 1: cur += ch
        elif ch == ")":
            depth -= 1
            if depth == 0: parts.append(cur.strip()); return parts
            cur += ch
        elif ch == "," and depth == 1: parts.append(cur.strip()); cur = ""
        else:
            if depth >= 1: cur += ch
        i += 1
    return parts
out = {"REVIEW-48 self-correlation": [], "REVIEW-47 constant window (ts_min/ts_max under ts_corr/ts_std)": [], "other": []}
for item in d["accepted_changed"]:
    e = item["expr"]; cls = "other"
    for m in re.finditer(r"ts_corr\(", e):
        a = args_of(e, m.end() - 1)
        if len(a) >= 2 and a[0] == a[1]: cls = "REVIEW-48 self-correlation"; break
    if cls == "other":
        for m in re.finditer(r"(ts_corr|ts_std)\(", e):
            a = args_of(e, m.end() - 1)
            if any(re.search(r"ts_m(in|ax)\(", x) for x in a[:2]): cls = "REVIEW-47 constant window (ts_min/ts_max under ts_corr/ts_std)"; break
    out[cls].append(e)
for k, v in out.items(): print(k, len(v)); [print("   ", x) for x in v]
print("accepted formulas:", d["accepted_same"] + len(d["accepted_changed"]), "changed:", len(d["accepted_changed"]))
sys.exit(1 if out["other"] else 0)
