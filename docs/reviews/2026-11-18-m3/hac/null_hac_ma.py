"""Size of the library's HAC mean test on the IC series that overlapping h-day labels produce.

A persistent factor scored against h-day forward returns gives a daily IC series that is a
moving sum of h daily IC shocks (an MA(h-1) process). Under H0 the mean is zero. This feeds
such series to invest_mining.diagnostics.newey_west_mean_test with newey_west_lags(n, h), the
exact call search.confirm makes, and counts one-sided rejections at 5%.
Usage: python null_hac_ma.py [reps] [seed]
"""

from __future__ import annotations

import sys

import numpy as np

from invest_mining.diagnostics import newey_west_lags, newey_west_mean_test

reps = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 5  # the reviewer's run used 5
rng = np.random.default_rng(seed)
for n in (60, 250, 750):
    for h in (1, 5, 10, 20):
        lags = newey_west_lags(n, h)
        rej = 0
        for _ in range(reps):
            d = rng.normal(size=n + h - 1)
            ic = np.convolve(d, np.ones(h) / h, mode="valid")  # length n, MA(h-1)
            t = newey_west_mean_test(ic, lags, min_n=min(60, n))
            rej += bool(t.status == "ok" and t.p_one_sided <= 0.05)
        print(
            f"n={n:<4} h={h:<2} lags={lags:<3} one-sided 5% size {rej / reps:.3f} "
            f"(MC s.e. {(0.05 * 0.95 / reps) ** 0.5:.3f})",
            flush=True,
        )
# Expected long-run variance captured by Bartlett weights with L = h for MA(h-1) sums of iid
# shocks, relative to the truth (finite-sample bias aside).
for h in (5, 20):
    L = h
    gam = [(h - k) / h for k in range(h)]
    bart = gam[0] + 2 * sum((1 - k / (L + 1)) * gam[k] for k in range(1, h))
    true = gam[0] + 2 * sum(gam[1:])
    print(
        f"h={h}: Bartlett(L=h) long-run variance / true = {bart / true:.3f}; "
        f"t inflated by {np.sqrt(true / bart):.3f}"
    )
