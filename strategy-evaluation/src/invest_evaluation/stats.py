"""Statistical uncertainty for strategy returns (dependence-aware where it matters).

* Newey-West (Bartlett) HAC test for the mean daily return.
* Stationary bootstrap (Politis & Romano 1994) confidence intervals for Sharpe and mean.
* Probabilistic Sharpe Ratio and Deflated Sharpe Ratio (Bailey & Lopez de Prado), which
  account for non-normal returns and, for DSR, the number of strategies tried.

These quantify sampling uncertainty of a *fixed* strategy. They do not correct for
search effort unless the trial count is supplied (DSR) and cannot repair leakage.
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

_ND = NormalDist()
EULER_GAMMA = 0.5772156649015329


def newey_west_mean(x: np.ndarray, lags: int | None = None) -> dict[str, Any]:
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 30:
        return {"status": "insufficient_data", "n": n}
    if lags is None:
        lags = math.floor(4 * (n / 100) ** (2 / 9))
    e = x - x.mean()
    lr = float(e @ e) / n
    for lag in range(1, min(lags, n - 1) + 1):
        lr += 2 * (1 - lag / (lags + 1)) * float(e[lag:] @ e[:-lag]) / n
    if lr <= 0:
        return {"status": "undefined", "reason": "zero_dispersion", "n": n}
    se = math.sqrt(lr / n)
    t = float(x.mean() / se)
    return {
        "status": "ok",
        "mean": float(x.mean()),
        "se": se,
        "t_stat": t,
        "p_two_sided": 2 * (1 - _ND.cdf(abs(t))),
        "lags": lags,
        "n": n,
    }


def stationary_bootstrap_indices(
    n: int, mean_block: float, n_boot: int, rng: np.random.Generator
) -> np.ndarray:
    """(n_boot, n) index matrix; block lengths are geometric with mean ``mean_block``."""
    p = 1.0 / mean_block
    idx = np.empty((n_boot, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, n_boot)
    restart = rng.random((n_boot, n)) < p
    fresh = rng.integers(0, n, (n_boot, n))
    for t in range(1, n):
        idx[:, t] = np.where(restart[:, t], fresh[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def sharpe(x: np.ndarray, annualization: int, axis: int = -1) -> np.ndarray:
    sd = np.std(x, axis=axis, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(sd > 1e-15, np.mean(x, axis=axis) / sd * math.sqrt(annualization), np.nan)


def bootstrap_ci(
    returns: pd.Series,
    annualization: int,
    *,
    n_boot: int = 2000,
    mean_block: float | None = None,
    level: float = 0.95,
    seed: int = 0,
) -> dict[str, Any]:
    x = returns.dropna().to_numpy(dtype=float)
    n = len(x)
    if n < 60:
        return {"status": "insufficient_data", "n": n}
    block = mean_block or max(1.0, round(n ** (1 / 3), 1))
    idx = stationary_bootstrap_indices(n, block, n_boot, np.random.default_rng(seed))
    samples = x[idx]
    sr = sharpe(samples, annualization)
    mu = samples.mean(axis=1) * annualization
    lo, hi = (1 - level) / 2, 1 - (1 - level) / 2
    return {
        "status": "ok",
        "method": "stationary bootstrap (percentile)",
        "mean_block_length": block,
        "replications": n_boot,
        "seed": seed,
        "level": level,
        "sharpe_ci": [float(np.nanquantile(sr, lo)), float(np.nanquantile(sr, hi))],
        "annual_mean_ci": [float(np.quantile(mu, lo)), float(np.quantile(mu, hi))],
        "share_sharpe_le_0": float(np.nanmean(sr <= 0)),
    }


def probabilistic_sharpe(returns: pd.Series, benchmark_sr: float = 0.0) -> dict[str, Any]:
    """P(true per-period SR > benchmark_sr) given skew/kurtosis of the sample."""
    x = returns.dropna().to_numpy(dtype=float)
    n = len(x)
    if n < 30:
        return {"status": "insufficient_data", "n": n}
    sd = x.std(ddof=1)
    if sd <= 1e-15:
        return {"status": "undefined", "reason": "zero_dispersion"}
    sr = x.mean() / sd
    m = x - x.mean()
    s2 = np.mean(m**2)
    skew = float(np.mean(m**3) / s2**1.5)
    kurt = float(np.mean(m**4) / s2**2)  # raw (non-excess) kurtosis
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr**2
    if denom <= 0:
        return {"status": "undefined", "reason": "non_positive_variance_term"}
    z = (sr - benchmark_sr) * math.sqrt(n - 1) / math.sqrt(denom)
    return {
        "status": "ok",
        "psr": _ND.cdf(z),
        "sharpe_per_period": float(sr),
        "benchmark_sharpe_per_period": benchmark_sr,
        "skewness": skew,
        "kurtosis": kurt,
        "n": n,
    }


def expected_max_sharpe(n_trials: int, trial_sr_variance: float) -> float:
    """Expected maximum per-period SR among ``n_trials`` unskilled strategies."""
    if n_trials < 2:
        return 0.0
    a = _ND.inv_cdf(1 - 1 / n_trials)
    b = _ND.inv_cdf(1 - 1 / (n_trials * math.e))
    return math.sqrt(trial_sr_variance) * ((1 - EULER_GAMMA) * a + EULER_GAMMA * b)


def deflated_sharpe(
    returns: pd.Series, n_trials: int, trial_sr_variance: float | None = None
) -> dict[str, Any]:
    """DSR = PSR against the expected maximum SR of ``n_trials`` null strategies.

    If the variance of trial Sharpe ratios is unknown, the null sampling variance
    ``1 / (n - 1)`` of a per-period SR estimate is used (labelled in the output).
    """
    x = returns.dropna()
    n = len(x)
    var = trial_sr_variance if trial_sr_variance is not None else 1.0 / max(n - 1, 1)
    sr0 = expected_max_sharpe(n_trials, var)
    out = probabilistic_sharpe(x, sr0)
    out.update(
        {
            "n_trials": n_trials,
            "trial_sr_variance": var,
            "trial_sr_variance_source": "supplied"
            if trial_sr_variance is not None
            else "null_sampling_variance",
        }
    )
    if "psr" in out:
        out["dsr"] = out.pop("psr")
    return out


def autocorrelations(returns: pd.Series, lags: int = 5) -> dict[str, float]:
    x = returns.dropna()
    return {f"lag_{k}": float(x.autocorr(k)) for k in range(1, lags + 1)}


def strategy_statistics(
    returns: pd.Series, annualization: int, n_trials: int = 1, seed: int = 0
) -> dict[str, Any]:
    return {
        "hac_mean_return": newey_west_mean(returns.to_numpy()),
        "bootstrap": bootstrap_ci(returns, annualization, seed=seed),
        "probabilistic_sharpe_vs_zero": probabilistic_sharpe(returns),
        "deflated_sharpe": deflated_sharpe(returns, n_trials),
        "return_autocorrelation": autocorrelations(returns),
    }
