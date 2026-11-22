"""Independent check of the censored marker rule after #53 (METRICS.md section 6 / reporting): the max drawdown duration
is right-censored only when the drawdown still open at the end is (one of) the longest. Recomputes episodes from
eval/tables/daily.csv equity with plain Python and compares with metrics.json.
Durations follow METRICS.md:110 (peak to recovery, in sessions; an open episode runs from its peak to the last session).
Usage: python censored_rule_check.py <eval dir> ...   Exit 0 when every eval agrees, 1 otherwise."""
import csv, json, sys
bad = 0
for d in sys.argv[1:]:
    rows = list(csv.DictReader(open(f"{d}/tables/daily.csv", encoding="utf-8")))
    eq = [float(r["equity"]) for r in rows]
    peak = eq[0]; run = 0; longest = 0; episodes = []
    for v in eq[1:]:
        if v >= peak:
            if run: episodes.append(run + 1)  # METRICS.md:110 'time from peak until recovery': recovery session index minus peak index
            peak = v; run = 0
        else:
            run += 1
    open_run = run  # open episode: last session index minus peak index
    longest = max(episodes + [open_run]) if episodes or open_run else 0
    censored = open_run > 0 and open_run >= max(episodes or [0])
    m = json.load(open(f"{d}/metrics.json", encoding="utf-8"))
    def find(o):
        if isinstance(o, dict):
            if o.get("name") == "max_drawdown_duration" or "max_drawdown_duration" in o and isinstance(o["max_drawdown_duration"], dict):
                return o if o.get("name") == "max_drawdown_duration" else o["max_drawdown_duration"]
            for v in o.values():
                r = find(v)
                if r: return r
        if isinstance(o, list):
            for v in o:
                r = find(v)
                if r: return r
    rec = find(m)
    val = rec.get("value"); cen = bool((rec.get("extra") or {}).get("censored"))
    ok = (val == longest) and (cen == censored)
    print(f"{d}: recomputed longest {longest} (recovered max {max(episodes or [0])}, open at end {open_run}) censored {censored}; metrics.json value {val} censored {cen} -> {'agree' if ok else 'DIFFER'}")
    bad += not ok
sys.exit(1 if bad else 0)
