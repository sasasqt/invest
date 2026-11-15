"""Check for GA-2026-10-31-1: a unary operator inside a time-series operator loses the
pre-membership history of an instrument when a universe is given.

build_panel's docstring (invest_mining/expressions.py) promises: "cross-sectional operators then
rank/normalise only across members, while time-series operators still use each instrument's full
history". So for closes 4, 9, 16 and membership False, True, True, ts_sum(abs(close), 2) on the
entry date (the second date) must equal ts_sum(close, 2) = 13 (abs changes no value).

Usage: python ra_unary_mask_truncates_ts_history.py
Exit 0 when the contract holds, 1 when the unary path drops the history (the finding), 2 on setup error.
Runs on the pinned main SHA with the project environment (needs invest_mining and invest_data).
"""
from __future__ import annotations

import math
import sys

import pandas as pd

try:
    from invest_mining.expressions import BASE_FIELDS, build_panel, evaluate
except Exception as exc:  # pragma: no cover
    print(f"setup error: {exc}")
    sys.exit(2)

dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
rows = []
for inst, closes in (("A", [4.0, 9.0, 16.0]), ("B", [1.0, 1.0, 1.0])):
    for d, c in zip(dates, closes):
        rows.append({"date": d, "instrument": inst, "open": c, "high": c, "low": c, "close": c, "volume": 1000.0})
bars = pd.DataFrame(rows)
missing = [f for f in BASE_FIELDS if f not in bars.columns]
if missing:
    print(f"setup error: BASE_FIELDS needs {missing}")
    sys.exit(2)
universe = pd.DataFrame(
    {
        "universe": ["U", "U"],
        "instrument": ["A", "B"],
        "start_date": [dates[1], dates[0]],  # A enters on the second date, B is a member throughout
        "end_date": [pd.NaT, pd.NaT],
    }
)
panel = build_panel(bars, universe=universe)
entry = dates[1]
control = evaluate("ts_sum(close, 2)", panel).loc[entry, "A"]
unary = evaluate("ts_sum(abs(close), 2)", panel).loc[entry, "A"]
no_universe = evaluate("ts_sum(abs(close), 2)", build_panel(bars)).loc[entry, "A"]
print(f"ts_sum(close, 2) at entry (control, universe given): {control}")
print(f"ts_sum(abs(close), 2) at entry, universe given:       {unary}")
print(f"ts_sum(abs(close), 2) at entry, no universe:          {no_universe}")
ok = control == 13.0 and no_universe == 13.0
if not ok:
    print("setup error: the controls do not give 13")
    sys.exit(2)
if math.isnan(unary) or unary != 13.0:
    print("FAIL: the unary operator masked the pre-entry history; the time-series operator did not see the full history")
    sys.exit(1)
print("PASS: full history preserved")
sys.exit(0)
