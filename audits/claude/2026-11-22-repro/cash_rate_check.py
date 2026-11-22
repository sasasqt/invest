"""Cash interest check (open place of reviewer 2, 2026-11-22): with costs.cash_rate_annual = r, the daily financing
should be the cash held over the session times r / 252 (config.py and strategy-evaluation/README.md: cash interest
accrues at the close; 252 sessions a year per the annualization). Independent of the engine's formula: reads daily.csv.
Usage: python cash_rate_check.py <eval dir> <annual rate>. Exit 0 when every session's financing / cash basis equals r/252
within 1e-9 relative for one of the two bases (previous close cash, or cash after the open's fills), 1 otherwise."""
import csv, sys
d, r = sys.argv[1], float(sys.argv[2])
rows = list(csv.DictReader(open(f"{d}/tables/daily.csv", encoding="utf-8")))
init = None
ratios_prev, bad = [], 0
prev_cash = None
for row in rows:
    cash, fin = float(row["cash"]), float(row["financing"])
    if prev_cash is not None and prev_cash != 0:
        ratios_prev.append(fin / prev_cash)
    prev_cash = cash
target = r / 252
import statistics
print(f"sessions {len(rows)}; financing/previous-close cash: median {statistics.median(ratios_prev):.12g}, min {min(ratios_prev):.12g}, max {max(ratios_prev):.12g}; r/252 = {target:.12g}")
off = [x for x in ratios_prev if abs(x - target) > 1e-9 * target]
print(f"sessions off r/252 on the previous-close basis: {len(off)} of {len(ratios_prev)} (expected on fill days: the open's fills move cash first)")
# engine.py docstring event order: fills at the open, then at the close interest accrues on the cash held then,
# so the basis is the close cash before financing and borrow: cash_t - financing_t + borrow_t
close_basis = [float(x["financing"]) / (float(x["cash"]) - float(x["financing"]) + float(x["borrow_cost"])) for x in rows]
off2 = [x for x in close_basis if abs(x - target) > 1e-9 * target]
print(f"sessions off r/252 on the close-cash basis (event order, engine.py:1-12): {len(off2)} of {len(close_basis)}")
sys.exit(0 if not off2 else 1)
