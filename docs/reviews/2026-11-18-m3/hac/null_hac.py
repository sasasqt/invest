"""Null calibration of the confirmation test (search.confirm's statistic) with overlapping labels.

Under H0 (factor independent of returns) the one-sided HAC test of mean rank IC at 5% should
reject about 5% of the time. Uses the library functions search.confirm uses: forward_returns,
daily_ic (spearman), newey_west_lags(n, h) and newey_west_mean_test(min_n=60).
Usage: python null_hac.py [reps] [sessions] [seed]
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from invest_mining.diagnostics import (
    daily_ic,
    forward_returns,
    newey_west_lags,
    newey_west_mean_test,
)

reps = int(sys.argv[1]) if len(sys.argv) > 1 else 400
T = int(sys.argv[2]) if len(sys.argv) > 2 else 300
N = 60
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 2026  # the reviewer's run used 2026
rng = np.random.default_rng(seed)
cols = [f"S{i:02d}" for i in range(N)]
for rho in (0.0, 0.98):
    for h in (1, 5, 20):
        rejections = 0
        lags = None
        for _ in range(reps):
            dates = pd.bdate_range("2025-01-01", periods=T + h + 2)
            opens = pd.DataFrame(
                100 * np.exp(np.cumsum(rng.normal(0, 0.02, (len(dates), N)), axis=0)),
                index=dates,
                columns=cols,
            )
            z = np.empty((len(dates), N))
            z[0] = rng.normal(size=N)
            for t in range(1, len(dates)):
                z[t] = rho * z[t - 1] + np.sqrt(1 - rho**2) * rng.normal(size=N)
            factor = pd.DataFrame(z, index=dates, columns=cols)
            label = forward_returns(opens, h)
            ic = daily_ic(factor, label, "spearman")["ic"].dropna()
            lags = newey_west_lags(len(ic), h)
            test = newey_west_mean_test(ic, lags, min_n=60)
            rejections += bool(test.status == "ok" and test.p_one_sided <= 0.05)
        rate = rejections / reps
        se = (0.05 * 0.95 / reps) ** 0.5
        print(
            f"factor AR(1) rho={rho:<4} h={h:<2} sessions={T} lags={lags}: one-sided 5% rejection "
            f"rate {rate:.3f} (nominal 0.050, MC s.e. {se:.3f})",
            flush=True,
        )
