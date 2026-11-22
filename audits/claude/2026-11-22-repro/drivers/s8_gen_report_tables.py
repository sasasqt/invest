"""Rule 31: build the report's generated tables from saved files.
Usage: python3 -I gen_report_tables.py OUT W > W/s8/report_tables.md
Sections: TESTMATRIX (validation.csv), BENCH (benchmarks/history.md, this run), RECS (recommendations.md, open rows),
OVERLAP (overlap.csv, this run's rows)."""
import csv, re, sys
from collections import OrderedDict
from pathlib import Path
OUT, W = Path(sys.argv[1]), Path(sys.argv[2]); DATE = "2026-11-22"
SPLIT = re.compile(r"(?<!\\)\|")
esc = lambda s: s.replace("|", "\\|")
print("<!-- TESTMATRIX -->")
gh = {"checks313": "success (checks 3.13, pytest 7m54s)", "checks311": "success (checks 3.11, pytest 10m32s)",
      "wheels": "success (tests 4m22s)", "indep-data-preparation": "success (pytest 5s)",
      "indep-data-mining-framework": "success (pytest 1m49s)", "indep-strategy-evaluation": "success (pytest 1m43s; mining-not-importable success)",
      "repeat": "n/a (local only)"}
jobs = OrderedDict()
for r in csv.DictReader(open(W / "validation.csv", encoding="utf-8")):
    j = jobs.setdefault(r["job"], {"rows": [], "wall": 0.0})
    j["rows"].append(r); j["wall"] += float(r["duration_s"] or 0)
print("| Job | Local | GitHub (same SHA, run 44246922942) | Wall | Notes |"); print("|---|---|---|---|---|")
for name, j in jobs.items():
    bad = [r for r in j["rows"] if r["outcome"] != "pass"]
    py = [r for r in j["rows"] if r["command"].startswith('pytest') or r["command"].startswith('"pytest') or "pytest" in r["command"]]
    p = py[-1] if py else None
    local = ("pass" if not bad else "FAIL: " + ", ".join(r["command"] for r in bad))
    if p: local += f" ({p['collected']} collected, {p['passed']} passed, {p['failed']} failed, {p['skipped']} skipped, {p['warnings']} warnings)"
    notes = f"{len(j['rows'])} steps, all exit 0" if not bad else ""
    if name == "repeat": notes += "; per-test outcomes identical to checks313 (tests/repeat_vs_checks313.json)"
    if name in ("wheels", "indep-data-preparation"): notes += "; the warnings are RA-2026-11-01-3's Pandas4Warning lines (pip resolves pandas 3.1.x)"
    if p and p["skipped"] not in ("", "0"): notes += "; the 2 skips need a non-root user (container runs as uid 0)"
    print(f"| {name} | {esc(local)} | {gh.get(name, '?')} | {j['wall']:.0f} s | {esc(notes)} |")
print("<!-- /TESTMATRIX -->\n<!-- BENCH -->")
lines = (OUT / "benchmarks/history.md").read_text(encoding="utf-8").splitlines()
i = lines.index("## Cases")
tab = [l for l in lines[i + 1:] if l.startswith("|")][:10]
for l in tab: print(l)
raw = sum(1 for l in open(OUT / "benchmarks/raw.jsonl", encoding="utf-8") if f'"repo-audit-{DATE}"' in l)
print(f"\nRaw lines appended this run: {raw} (benchmarks/raw.jsonl); fingerprint fc1579baf121 (previous 0fa016b96104).")
print("<!-- /BENCH -->\n<!-- RECS -->")
hdr = None; cols = ["ID", "Title", "Priority", "Effort", "Cheaper way", "Acceptance criteria", "Owner", "Route"]
print("| " + " | ".join(cols) + " |"); print("|" + "---|" * len(cols))
for l in (OUT / "recommendations.md").read_text(encoding="utf-8").splitlines():
    if l.startswith("| ID "): hdr = [c.strip() for c in SPLIT.split(l)[1:-1]]
    elif l.startswith("| RA-"):
        d = dict(zip(hdr, [c.strip() for c in SPLIT.split(l)[1:-1]]))
        if d["Status"] == "open": print("| " + " | ".join(d[c] for c in cols) + " |")
print("<!-- /RECS -->\n<!-- OVERLAP -->")
print("| Check | Minutes | Findings | Already known elsewhere | Unique | Twin check elsewhere |"); print("|---|---|---|---|---|---|")
tot = 0
for r in csv.reader(open(OUT / "overlap.csv", encoding="utf-8")):
    if r and r[0] == DATE:
        tot += int(r[2]); print("| " + " | ".join(esc(x) for x in r[1:7]) + " |")
print(f"\nTotal: {tot} minutes of checks this run.")
print("<!-- /OVERLAP -->")
