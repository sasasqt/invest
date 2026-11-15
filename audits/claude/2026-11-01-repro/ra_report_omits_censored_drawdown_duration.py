"""Check: when metrics.json marks max_drawdown_duration as censored (the drawdown has not recovered by the end of
the window), report.md must say so next to the number. METRICS.md section 6: "Drawdown duration: time from peak until
recovery to that peak ... unrecovered episodes are right-censored" and the table shows the duration as a bare count.
Usage: python ra_report_omits_censored_drawdown_duration.py <eval dir with metrics.json and report.md>
Exit 0 when the report marks censoring (or nothing is censored), 1 when a censored duration is shown as a bare number, 2 on setup error."""
import json, re, sys
d = sys.argv[1]
try:
    m = json.load(open(f"{d}/metrics.json"))["performance"]["max_drawdown_duration"]; rep = open(f"{d}/report.md").read()
except Exception as exc:
    print("setup error:", exc); sys.exit(2)
censored = bool((m.get("extra") or {}).get("censored"))
row = next((l for l in rep.splitlines() if l.startswith("| max_drawdown_duration")), None)
print(f"metrics.json max_drawdown_duration value={m.get('value')} unit={m.get('unit')} censored={censored}")
print(f"report.md row: {row!r}")
if not censored:
    print("PASS: nothing censored"); sys.exit(0)
if row is None:
    print("setup error: report has no max_drawdown_duration row"); sys.exit(2)
if re.search(r"censor|unrecovered|open|ongoing|\+", row, re.I):
    print("PASS: the report marks the censored duration"); sys.exit(0)
print("FAIL: the drawdown duration is right-censored (unrecovered at the end of the window) but the report shows it as a bare count"); sys.exit(1)
