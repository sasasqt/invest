"""Reported-outputs lens: every numeric cell of eval/report.md's metric tables must equal the value in metrics.json /
statistics.json to the shown precision, and a missing or undefined value must stay visible (n/a with a reason), never 0.
Usage: python report_vs_metrics.py <eval dir>   Exit 0 when every cell agrees, 1 otherwise."""
import json, re, sys
d = sys.argv[1]
m = json.load(open(f"{d}/metrics.json")); st = json.load(open(f"{d}/statistics.json"))
rep = open(f"{d}/report.md", encoding="utf-8").read()
flat = {}
def walk(obj, prefix):
    if isinstance(obj, dict):
        if "value" in obj and "status" in obj: flat[prefix] = obj; return
        for k, v in obj.items(): walk(v, f"{prefix}.{k}" if prefix else k)
walk(m, "")
cells = re.findall(r"^\| ([a-z_0-9]+) \| ([^|]+) \|", rep, re.M)
checked = agree = 0; problems = []
by_leaf = {}
for key, obj in flat.items(): by_leaf.setdefault(key.split(".")[-1], []).append((key, obj))
section = None; sections = {}
for line in rep.splitlines():
    if line.startswith("## "): section = line[3:].strip().lower()
    mm = re.match(r"^\| ([a-z_0-9]+) \| ([^|]+) \|", line)
    if mm and section: sections.setdefault(section, []).append((mm.group(1), mm.group(2).strip()))
for sec, pairs in sections.items():
    for name, shown in pairs:
        cands = by_leaf.get(name, [])
        # pick the candidate whose top-level group matches the section name when possible
        pick = next((c for c in cands if c[0].split(".")[0].replace("_", " ") == sec), None) or (cands[0] if cands else None)
        if pick is None: continue
        checked += 1; key, obj = pick; val = obj.get("value")
        if val is None:
            if shown.startswith("n/a"): agree += 1
            else: problems.append(f"{sec}/{name}: value undefined ({obj.get('reason')}) but shown as {shown!r}")
            continue
        num = re.match(r"^(-?[\d,]*\.?\d+)(%?)", shown)
        if not num: problems.append(f"{sec}/{name}: cannot parse {shown!r}"); continue
        x = float(num.group(1).replace(",", "")); pct = num.group(2) == "%"
        if pct: x /= 100
        digits = len(num.group(1).split(".")[1]) if "." in num.group(1) else 0
        tol = 0.5 * 10 ** (-(digits + (2 if pct else 0)))
        if abs(x - float(val)) <= tol + 1e-15: agree += 1
        else: problems.append(f"{sec}/{name}: shown {shown!r} vs metrics.json {val!r} ({key})")
print(f"cells checked {checked}, agree {agree}, problems {len(problems)}")
for p in problems: print("  -", p)
# undefined values anywhere in metrics.json that the report must still show as n/a
undef = [k for k, o in flat.items() if o.get("value") is None]
print("undefined metrics:", len(undef), undef[:8])
print("report mentions 'n/a':", rep.count("n/a"), "| censored shown:", "censored" in rep)
sys.exit(1 if problems else 0)
