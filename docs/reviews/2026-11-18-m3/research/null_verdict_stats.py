# ruff: noqa: E501  (evidence script kept as run)
"""Null size of the two verdict statistics on zero-mean daily returns (n=500):
P(bootstrap Sharpe lower bound > 0) (nominal 0.025) and P(PSR >= 0.95) (nominal 0.05)."""

import numpy as np
import pandas as pd

from invest_evaluation.stats import bootstrap_ci, probabilistic_sharpe

rng = np.random.default_rng(1)
reps, n = 300, 500
for name, draw in (
    ("normal", lambda: rng.normal(0, 0.01, n)),
    ("t3", lambda: rng.standard_t(3, n) * 0.006),
):
    ci_rej = psr_rej = 0
    for r in range(reps):
        x = pd.Series(draw())
        b = bootstrap_ci(x, 252, n_boot=1000, seed=r)
        ci_rej += b["sharpe_ci"][0] > 0
        psr_rej += probabilistic_sharpe(x)["psr"] >= 0.95
    print(
        f"{name}: P(CI low > 0) {ci_rej / reps:.3f} (nominal .025, s.e. {np.sqrt(0.025 * 0.975 / reps):.3f}); "
        f"P(PSR >= .95) {psr_rej / reps:.3f} (nominal .05, s.e. {np.sqrt(0.05 * 0.95 / reps):.3f})",
        flush=True,
    )
