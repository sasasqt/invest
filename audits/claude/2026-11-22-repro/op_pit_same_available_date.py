"""Open place (reviewer 2, 2026-11-15): pit.fundamentals_asof when a late revision of period P-1
and the first value of period P share one available_date. Contract (DATA_CONTRACT.md:46): the
latest revision of the MOST RECENT period wins, so P's value must be returned on that date in
either row order. Exit 0 = contract holds in both orders, 1 = row order decides."""
import sys
import pandas as pd
from invest_data.pit import fundamentals_asof
d = pd.Timestamp
rows = [
    ("A", "eps", d("2024-03-31"), d("2024-04-20"), 1.0),   # P-1 first value
    ("A", "eps", d("2024-03-31"), d("2024-07-25"), 1.5),   # P-1 late revision, same day as P
    ("A", "eps", d("2024-06-30"), d("2024-07-25"), 2.0),   # P first value
]
dates = pd.DatetimeIndex([d("2024-05-01"), d("2024-07-25"), d("2024-08-01")])
ok = True
for order in (rows, list(reversed(rows))):
    f = pd.DataFrame(order, columns=["instrument", "field", "period_end", "available_date", "value"])
    out = fundamentals_asof(f, "eps", dates, pd.Index(["A"]))["A"].tolist()
    print("order", [r[4] for r in order], "->", out)
    ok &= out == [1.0, 2.0, 2.0]
print("PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
