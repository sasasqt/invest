"""Factor diagnostics with the date as the statistical unit (ALPHA_VALIDATION.md §3).

Timing convention (shared with strategy evaluation): a factor value at decision date ``t``
uses data through the close of ``t``; the position is entered at the open of ``t+1`` and
exited at the open of ``t+1+h``. The label interval of decision ``t`` is therefore
sessions ``[t+1, t+1+h]``.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

MIN_CROSS_SECTION = 5


def forward_returns(open_: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Open(t+1) -> open(t+1+h) return, indexed by decision date t.

    Instruments that stop trading before the exit have a missing label; coverage is
    reported rather than silently treated as zero.
    """
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    entry = open_.shift(-1)
    exit_ = open_.shift(-(1 + horizon))
    return (exit_ / entry - 1.0).replace([np.inf, -np.inf], np.nan)


def daily_ic(factor: pd.DataFrame, label: pd.DataFrame, method: str = "spearman") -> pd.DataFrame:
    """Per-date cross-sectional correlation. Returns columns ``ic`` and ``n``.

    Dates with fewer than MIN_CROSS_SECTION valid pairs, or constant factor/label values,
    get ``ic = NaN`` (undefined), never zero.
    """
    f, y = factor.align(label, join="inner")
    valid = f.notna() & y.notna()
    f, y = f.where(valid), y.where(valid)
    if method == "spearman":
        f, y = f.rank(axis=1), y.rank(axis=1)
    elif method != "pearson":
        raise ValueError(f"unknown method {method!r}")
    n = valid.sum(axis=1)
    fc = f.sub(f.mean(axis=1), axis=0)
    yc = y.sub(y.mean(axis=1), axis=0)
    cov = (fc * yc).sum(axis=1)
    denom = np.sqrt((fc**2).sum(axis=1) * (yc**2).sum(axis=1))
    ic = cov / denom.where(denom > 1e-15)
    ic = ic.where(n >= MIN_CROSS_SECTION)
    return pd.DataFrame({"ic": ic, "n": n})


def newey_west_lags(n: int, horizon: int = 1) -> int:
    """Default HAC lag: max(h, floor(4 (n/100)^(2/9))); overlapping h-day labels need >= h-1."""
    rule = math.floor(4 * (n / 100) ** (2 / 9)) if n > 0 else 0
    return max(horizon, rule)


@dataclass(frozen=True)
class MeanTest:
    mean: float
    se: float
    t_stat: float
    p_two_sided: float
    p_one_sided: float  # H1: mean > 0
    n: int
    lags: int
    status: str
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            k: (None if isinstance(v, float) and not math.isfinite(v) else v)
            for k, v in asdict(self).items()
        }


def newey_west_mean_test(x: pd.Series | np.ndarray, lags: int, min_n: int = 30) -> MeanTest:
    """HAC (Bartlett kernel) test of mean != 0 on a time series, ignoring NaNs."""
    arr = np.asarray(pd.Series(x).dropna(), dtype=float)
    n = len(arr)
    nan = float("nan")
    if n < min_n:
        return MeanTest(nan, nan, nan, nan, nan, n, lags, "insufficient_data", f"n={n}<{min_n}")
    mu = float(arr.mean())
    e = arr - mu
    lr_var = float(e @ e) / n
    for lag in range(1, min(lags, n - 1) + 1):
        w = 1.0 - lag / (lags + 1.0)
        lr_var += 2.0 * w * float(e[lag:] @ e[:-lag]) / n
    if lr_var <= 0:
        return MeanTest(mu, nan, nan, nan, nan, n, lags, "undefined", "zero_dispersion")
    se = math.sqrt(lr_var / n)
    t = mu / se
    nd = NormalDist()
    return MeanTest(mu, se, t, 2 * (1 - nd.cdf(abs(t))), 1 - nd.cdf(t), n, lags, "ok")


def ic_summary(ic: pd.DataFrame, horizon: int) -> dict[str, Any]:
    series = ic["ic"].dropna()
    n = len(series)
    test = newey_west_mean_test(series, newey_west_lags(n, horizon))
    std = float(series.std(ddof=1)) if n > 1 else float("nan")
    return {
        "mean_ic": float(series.mean()) if n else None,
        "std_ic": std if math.isfinite(std) else None,
        # Descriptive ratio (mean / std of daily IC); not a significance test.
        "icir": float(series.mean() / std) if n > 1 and std > 0 else None,
        "positive_share": float((series > 0).mean()) if n else None,
        "valid_dates": n,
        "total_dates": len(ic),
        "mean_cross_section": float(ic["n"][ic["ic"].notna()].mean()) if n else None,
        "hac_test": test.to_dict(),
    }


def assign_buckets(factor: pd.DataFrame, n_buckets: int = 10) -> pd.DataFrame:
    """Per-date equal-width percentile buckets 1..n (ties share a bucket; NaN stays NaN)."""
    pct = factor.rank(axis=1, method="average", pct=True)
    buckets = np.ceil(pct * n_buckets).clip(lower=1, upper=n_buckets)
    counts = factor.notna().sum(axis=1)
    buckets.loc[counts < n_buckets] = np.nan
    return buckets


def quantile_returns(
    factor: pd.DataFrame, label: pd.DataFrame, n_buckets: int = 10
) -> pd.DataFrame:
    """Date x bucket table of equal-weighted mean forward returns."""
    f = factor
    y = label.reindex(index=f.index, columns=f.columns)
    b = assign_buckets(f, n_buckets)
    stacked = pd.DataFrame({"bucket": b.stack(), "ret": y.stack()}).dropna()
    table = stacked.groupby([stacked.index.get_level_values(0), "bucket"])["ret"].mean()
    out = table.unstack("bucket").reindex(index=f.index, columns=range(1, n_buckets + 1))
    out.columns = [f"q{int(c)}" for c in out.columns]
    out.index.name = "date"
    return out


def tail_returns(
    factor: pd.DataFrame, label: pd.DataFrame, fractions: tuple[float, ...] = (0.01, 0.05, 0.1)
) -> pd.DataFrame:
    """Mean forward return of top/bottom tail slices (these overlap deciles)."""
    f = factor
    y = label.reindex(index=f.index, columns=f.columns)
    pct = f.rank(axis=1, method="average", pct=True)
    rows = {}
    for frac in fractions:
        top = y.where(pct > 1 - frac).mean(axis=1)
        bottom = y.where(pct <= frac).mean(axis=1)
        rows[f"top_{frac:g}"] = top.mean()
        rows[f"bottom_{frac:g}"] = bottom.mean()
        rows[f"n_dates_{frac:g}"] = float((top.notna() & bottom.notna()).sum())
    return pd.DataFrame(rows, index=["mean_forward_return"]).T


def rank_autocorrelation(factor: pd.DataFrame, lag: int = 1) -> float:
    """Mean per-date Spearman correlation of factor ranks with their ``lag``-day-old ranks."""
    ic = daily_ic(factor, factor.shift(lag), method="spearman")["ic"]
    return float(ic.mean()) if ic.notna().any() else float("nan")


def holm_adjust(p_values: list[float]) -> list[float]:
    """Holm step-down adjusted p-values (valid under arbitrary dependence)."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """BH FDR adjusted p-values (assumes independence or PRDS)."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i], reverse=True)
    adjusted = [0.0] * m
    running = 1.0
    for k, i in enumerate(order):
        rank = m - k
        running = min(running, p_values[i] * m / rank)
        adjusted[i] = running
    return adjusted
