"""Check (reviewer 2, 2026-11-08): eval/report.md must state the evaluation window.

Binding lines: strategy-evaluation/METRICS.md:9 "The report must specify base currency, timezone, valuation
frequency, period start/end, trading calendar, annualization factor, return type, risk-free series, ..." and
docs/REPORTING.md:39 "Reports need units, time ranges, gross/net labels, benchmarks, sample counts, and
missing/undefined-result explanations".

Independent reference for the window: the first and last `date` of eval/tables/daily.csv (the evaluated
sessions), cross-checked against verdict.json `portfolio.evaluation_window` when present. The check does not
read reporting.py.

Also printed (informational, METRICS.md section 9 "Default summaries should show" is a 'should'): which of
the section-9 default-summary items are absent from report.md although metrics.json computes them, and which
of the section-9 example metadata fields (sample_count, frequency, annualization_factor, return_basis,
parameters) no metric record carries.

Usage: python ra_report_window.py <eval dir>. Exit 0 when both window dates appear in report.md, 1 otherwise.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

d = Path(sys.argv[1])
report = (d / "report.md").read_text(encoding="utf-8")
rows = list(csv.DictReader((d / "tables" / "daily.csv").open(encoding="utf-8", newline="")))
start, end = rows[0]["date"], rows[-1]["date"]
verdict = json.loads((d / "verdict.json").read_text(encoding="utf-8")) if (d / "verdict.json").exists() else {}
vw = verdict.get("portfolio", {}).get("evaluation_window")
print(f"daily.csv window: {start} .. {end} ({len(rows)} sessions); verdict.json evaluation_window: {vw}")
if vw and (vw.get("start"), vw.get("end")) != (start, end):
    print("note: verdict.json window differs from daily.csv window")

dates_in_report = sorted(set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", report)))
print(f"ISO dates found in report.md: {dates_in_report or 'none'}")
has_start, has_end = start in report, end in report
cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
print(f"config.json start/end: {cfg.get('start')!r}/{cfg.get('end')!r}; annualization {cfg.get('annualization')}; "
      f"'annualization' word in report: {'annualization' in report}; 'USD'/'currency' in report: "
      f"{('USD' in report) or ('currency' in report)}")

metrics = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
perf = metrics.get("performance", {})
soft = ["net_profit", "mean_return", "median_return", "downside_deviation", "skewness", "excess_kurtosis",
        "omega", "ulcer_index", "martin", "max_recovery_duration", "time_under_water", "current_drawdown"]
computed_not_printed = [k for k in soft if k in perf and perf[k].get("value") is not None
                        and not re.search(rf"^\| {re.escape(k)} \|", report, re.M)]
trades = metrics.get("trades", {})
if "expectancy" in trades and not re.search(r"^\| expectancy \|", report, re.M):
    computed_not_printed.append("trades.expectancy")
print(f"section-9 default-summary items computed in metrics.json but not printed: {computed_not_printed}")
fields = ("sample_count", "frequency", "annualization_factor", "return_basis", "parameters")
n = sum(len(sec) for sec in metrics.values())
absent = {f: sum(1 for sec in metrics.values() for m in sec.values() if f not in m) for f in fields}
print(f"section-9 example metadata fields absent, of {n} metric records: {absent}")

if has_start and has_end:
    print(f"PASS: report.md states the evaluation window {start} .. {end}")
    sys.exit(0)
print(f"FAIL: report.md does not state the evaluation window (start {start} present: {has_start}, "
      f"end {end} present: {has_end}); METRICS.md:9 'The report must specify ... period start/end', "
      f"REPORTING.md:39 'Reports need ... time ranges'")
sys.exit(1)
