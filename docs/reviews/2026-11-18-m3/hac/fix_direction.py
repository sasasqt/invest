"""Fix direction for R2-2: same MA(h-1) null, other lag choices (library test unchanged)."""

import numpy as np

from invest_mining.diagnostics import newey_west_mean_test

rng = np.random.default_rng(9)
reps = 3000
for n, h in ((250, 5), (750, 20)):
    for mult in (1, 2, 3):
        L = mult * h
        rej = 0
        for _ in range(reps):
            ic = np.convolve(rng.normal(size=n + h - 1), np.ones(h) / h, mode="valid")
            t = newey_west_mean_test(ic, L, min_n=60)
            rej += t.p_one_sided <= 0.05
        print(f"n={n} h={h} lags={L} ({mult}h): size {rej / reps:.3f}", flush=True)
