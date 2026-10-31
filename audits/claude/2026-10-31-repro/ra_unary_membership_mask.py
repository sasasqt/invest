"""RA check (cross-check of GA-2026-10-31-1): unary operators are masked by universe membership
before a time-series operator sees them, so a member's pre-entry history is lost.

Contract (expressions.build_panel docstring, main 90b5ca0): "cross-sectional operators then
rank/normalise only across members, while time-series operators still use each instrument's
full history". Expected: ts_sum(abs(close), 2) == ts_sum(close, 2) == 13 on the entry date for
positive closes 4, 9, 16 with membership False, True, True.

Usage: python -I ra_unary_membership_mask.py [<worktree>]   (an interpreter with pandas/numpy; with <worktree>
given, <worktree>/data-mining-framework/src is put on sys.path, otherwise invest_mining must be importable,
e.g. <worktree>/.venv/bin/python)
Exit 1 when the two expressions differ on the entry date (the defect), 0 otherwise.
"""
import sys
from pathlib import Path

if len(sys.argv) > 1:
    sys.path.insert(0, str(Path(sys.argv[1]).resolve() / "data-mining-framework" / "src"))

import numpy as np
import pandas as pd

from invest_mining.expressions import BASE_FIELDS, build_panel, evaluate

dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
closes = {"A": [4.0, 9.0, 16.0, 25.0], "B": [2.0, 2.0, 2.0, 2.0]}
rows = []
for inst, cl in closes.items():
    for d, c in zip(dates, cl):
        row = {"date": d, "instrument": inst}
        for f in BASE_FIELDS:
            row[f] = 1000.0 if f == "volume" else c
        rows.append(row)
bars = pd.DataFrame(rows)
universe = pd.DataFrame(
    {"universe": ["u", "u"], "instrument": ["A", "B"], "start_date": [dates[1], dates[0]],
     "end_date": [pd.NaT, pd.NaT]}
)
panel = build_panel(bars, universe=universe)
plain = evaluate("ts_sum(close, 2)", panel)["A"]
unary = evaluate("ts_sum(abs(close), 2)", panel)["A"]
neg = evaluate("ts_mean(neg(close), 2)", panel)["A"]
entry = dates[1]
print("membership A:", panel["universe"]["A"].tolist())
print("ts_sum(close,2)[A]     :", plain.tolist())
print("ts_sum(abs(close),2)[A]:", unary.tolist())
print("ts_mean(neg(close),2)[A]:", neg.tolist())
print(f"entry date {entry.date()}: plain={plain[entry]!r} unary={unary[entry]!r} expected 13.0 for both")
ok = np.isclose(plain[entry], 13.0) and np.isclose(unary[entry], 13.0)
print("RESULT:", "pass (full history kept through the unary operator)" if ok else "FAIL (unary operator masked by membership, pre-entry history lost)")
sys.exit(0 if ok else 1)
