"""Exploration draw, repo audit 2026-11-22 (live file step 6): files neither model reviewed in the last 28 days,
oldest first, then one area drawn at random with the run date as the seed. Rule 31: deterministic, seeded.
Usage: python exploration_draw.py <claude coverage-map.json> <gpt coverage.csv> <ls_files.txt> <run date>"""
import csv, datetime as dt, json, random, sys
cmap, gcsv, lsf, date = sys.argv[1:5]
run = dt.date.fromisoformat(date); cutoff = run - dt.timedelta(days=28)
REVIEW = {"reviewed", "partially_reviewed"}
DEEP = {"deep-read", "test-quality", "bug-hunt-deep-pass", "cross-check", "saved-results", "workflow"}
files = json.load(open(cmap))["files"]
gpt = {r["path"]: r for r in csv.DictReader(open(gcsv))}
tracked = [l.strip() for l in open(lsf) if l.strip()]
rows = []
for p in tracked:
    h = files.get(p, {}).get("history", [])
    c_last = max((x["date"] for x in h if x["status"] in REVIEW and x["lens"] in DEEP), default="")
    g = gpt.get(p, {}); g_last = g.get("last_review_date", "") if g.get("status") in ("reviewed", "partially_reviewed", "verified") else ""
    last = max(c_last, g_last)
    if not last or dt.date.fromisoformat(last[:10]) < cutoff:
        if p.endswith((".py", ".sh", ".yml", ".toml", ".json")) and "/runs/" not in p and not p.startswith("runs/"):
            n = sum(1 for _ in open(f"{sys.argv[5] if len(sys.argv) > 5 else '.'}/{p}", errors="replace")) if len(sys.argv) > 5 else 0
            rows.append((last or "never", p, c_last or "never", g_last or "never", n))
rows.sort()
print(f"{len(rows)} code/config files neither model deep-reviewed since {cutoff} (claude lenses {sorted(DEEP)}; gpt status reviewed/partially_reviewed/verified):")
for r in rows: print(f"  last={r[0]:10} claude={r[2]:10} gpt={r[3]:10} lines={r[4]:5} {r[1]}")
rng = random.Random(date)
pick = rng.choice([r[1] for r in rows]) if rows else None
print("random draw (random.Random('%s').choice over the list above):" % date, pick)
print("gpt status values:", sorted({r.get('status') for r in gpt.values()}))
