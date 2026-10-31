"""C1 check: do the mining factor figures draw a point at an undefined date inside the cumulative lines?
Builds a daily_ic.csv / quantile_returns.csv with NaN on the first 3 dates and on one interior date,
renders the figures with invest_mining.reporting.render_factor_figures and records every y value that
Axes.plot received. Exit 1 if any plotted cumulative line has a finite value on an undefined date
(fails on main because of .fillna(0)); exit 0 when undefined dates are left out of the line."""
import sys, tempfile
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
from matplotlib.axes import Axes
from invest_mining import reporting

captured = []
orig = Axes.plot
def spy(self, *args, **kw):
    captured.append((self.get_ylabel(), self.get_title(), args[0]))
    return orig(self, *args, **kw)
Axes.plot = spy

root = Path(tempfile.mkdtemp())
(root / "tables").mkdir(); (root / "figures").mkdir()
dates = pd.bdate_range("2020-01-01", periods=12)
ic = pd.Series(0.1, index=dates); ic.iloc[:3] = np.nan; ic.iloc[7] = np.nan
pd.DataFrame({"ic": ic, "n": 50}).rename_axis("date").to_csv(root / "tables/daily_ic.csv")
q = pd.DataFrame({f"q{i}": 0.001 * i for i in range(1, 11)}, index=dates).rename_axis("date")
q.iloc[:3] = np.nan; q.iloc[7] = np.nan
q.to_csv(root / "tables/quantile_returns.csv")
pd.DataFrame({"x": []}).to_csv(root / "tables/tail_returns.csv")
reporting.render_factor_figures(root)
undefined = dates[[0, 1, 2, 7]]
bad = []
for ylabel, title, series in captured:
    if not isinstance(series, pd.Series):
        continue
    vals = series.reindex(undefined)
    finite = vals[np.isfinite(vals.to_numpy(dtype=float))]
    print(f"line ylabel={ylabel!r} title={title!r}: values on undefined dates -> {vals.to_dict()}")
    if len(finite):
        bad.append((ylabel or title, finite.to_dict()))
print("figures:", sorted(p.name for p in (root / "figures").iterdir()))
if bad:
    print("FAIL: cumulative lines carry finite points on undefined dates:", bad)
    sys.exit(1)
print("OK: no plotted point on an undefined date")
