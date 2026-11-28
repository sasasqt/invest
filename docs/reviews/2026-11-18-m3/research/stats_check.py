"""Independent checks of the statistics against published formulas and hand computations.

Prints observed (library) vs expected (independent) values. No scipy/statsmodels in the venv,
so the references are written here from the papers' formulas.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

from invest_evaluation import stats as es
from invest_mining import diagnostics as md

ND = NormalDist()
rng = np.random.default_rng(3)
ok = True


def check(name: str, observed: float, expected: float, tol: float = 1e-9) -> None:
    global ok
    good = abs(observed - expected) <= tol * max(1.0, abs(expected))
    ok &= good
    print(f"{'ok ' if good else 'BAD'} {name}: observed {observed:.10g} expected {expected:.10g}")


# 1. PSR (Bailey & Lopez de Prado 2012): Phi((SR - SR*) sqrt(n-1) / sqrt(1 - g3 SR + (g4-1)/4 SR^2))
x = rng.standard_t(5, 750) * 0.01 + 0.0006
n = len(x)
sr = x.mean() / x.std(ddof=1)
m = x - x.mean()
g3 = np.mean(m**3) / np.mean(m**2) ** 1.5
g4 = np.mean(m**4) / np.mean(m**2) ** 2
psr_ref = ND.cdf(sr * math.sqrt(n - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr**2))
check("PSR vs paper formula", es.probabilistic_sharpe(pd.Series(x))["psr"], psr_ref)

# 2. DSR (Bailey & Lopez de Prado 2014) numerical example: SR 2.5 annual, T=1250, N=100,
# V[SR_n] = 0.5 annual, skew -3, kurt 10 -> E[max SR] ~ 0.1132 per day, DSR ~ 0.9004.
emax = es.expected_max_sharpe(100, 0.5 / 250)
check("E[max SR] paper example (per day)", emax, 0.1132, tol=5e-4)
srd = 2.5 / math.sqrt(250)
z = (srd - emax) * math.sqrt(1249) / math.sqrt(1 - (-3) * srd + (10 - 1) / 4 * srd**2)
check("DSR paper example", ND.cdf(z), 0.9004, tol=5e-4)
# Library DSR on a series = PSR against E[max] with V = 1/(n-1) by default.
d = es.deflated_sharpe(pd.Series(x), 50)
emax_x = es.expected_max_sharpe(50, 1 / (n - 1))
dsr_ref = ND.cdf((sr - emax_x) * math.sqrt(n - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr**2))
check("DSR(n_trials=50) vs formula", d["dsr"], dsr_ref)
check("DSR(n_trials=1) == PSR", es.deflated_sharpe(pd.Series(x), 1)["dsr"], psr_ref)


# 3. HAC Bartlett long-run variance vs independent loop.
def hac_ref(arr: np.ndarray, L: int) -> float:
    e = arr - arr.mean()
    T = len(e)
    s = sum(e[t] * e[t] for t in range(T)) / T
    for k in range(1, L + 1):
        s += 2 * (1 - k / (L + 1)) * sum(e[t] * e[t - k] for t in range(k, T)) / T
    return arr.mean() / math.sqrt(s / T)


ar = np.zeros(300)
for t in range(1, 300):
    ar[t] = 0.5 * ar[t - 1] + rng.normal()
ar += 0.1
check("mining HAC t (L=7)", md.newey_west_mean_test(ar, 7).t_stat, hac_ref(ar, 7))
lags_eval = math.floor(4 * (300 / 100) ** (2 / 9))
check("evaluation HAC t (NW94 rule)", es.newey_west_mean(ar)["t_stat"], hac_ref(ar, lags_eval))

# 4. Holm and BH by hand.
p = [0.01, 0.04, 0.03, 0.005]
for got, want in zip(md.holm_adjust(p), [0.03, 0.06, 0.06, 0.02], strict=True):
    check("Holm", got, want)
for got, want in zip(md.benjamini_hochberg(p), [0.02, 0.04, 0.04, 0.02], strict=True):
    check("BH", got, want)

# 5. Rank IC with ties on one date vs Pearson of average ranks.
f = pd.DataFrame([[1.0, 2.0, 2.0, 3.0, np.nan, 5.0, 0.5]])
y = pd.DataFrame([[0.1, 0.3, -0.2, 0.3, 0.9, np.nan, 0.0]])
valid = f.notna() & y.notna()
rf = f.where(valid).rank(axis=1).iloc[0].dropna()
ry = y.where(valid).rank(axis=1).iloc[0].dropna()
check(
    "Spearman IC with ties",
    float(md.daily_ic(f, y)["ic"].iloc[0]),
    float(np.corrcoef(rf, ry)[0, 1]),
)

# 6. Stationary bootstrap: mean block length.
idx = es.stationary_bootstrap_indices(1000, 8.0, 200, np.random.default_rng(0))
restarts = (np.diff(idx, axis=1) != 1) & ~((idx[:, :-1] == 999) & (idx[:, 1:] == 0))
check("mean block length ~ 8", 999 / (restarts.sum(axis=1).mean() + 1) * 1.0, 8.0, tol=0.05)

print("ALL OK" if ok else "SOME CHECKS FAILED")
