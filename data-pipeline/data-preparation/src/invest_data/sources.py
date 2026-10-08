"""Data sources: a deterministic synthetic market and a local CSV importer.

Network adapters live in their own modules (the test-only Yahoo Finance adapter is
:mod:`invest_data.yahoo`) because licensing, credentials and rate limits are source
specific. An adapter returns a raw bars DataFrame with the columns of
:data:`invest_data.schemas.MARKET_BAR_COLUMNS`, which then passes through
:func:`invest_data.cleaning.clean_bars`.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from invest_data.schemas import AS_TRADED_CLOSE


@dataclass(frozen=True)
class SyntheticConfig:
    n_instruments: int = 60
    n_days: int = 750
    start: str = "2020-01-01"
    seed: int = 7
    market_vol: float = 0.010
    idio_vol: float = 0.018
    # Planted, causal effect: next-session (open->close) return loads on minus the
    # cross-sectional z-score of the trailing ``reversal_window`` close-to-close return.
    reversal_strength: float = 0.0015
    reversal_window: int = 5
    listing_churn: float = 0.15  # share of instruments that list late or delist early
    adv_shares_range: tuple[float, float] = (2e5, 5e6)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def synthetic_market(config: SyntheticConfig | None = None) -> pd.DataFrame:
    """Generate daily OHLCV bars with a known, weak, *causal* reversal effect.

    The predictable part of each return is a function only of prices up to the previous
    close, and it is realised between the next open and close. A correct pipeline that
    trades at the next open can capture it; a pipeline with lookahead would show
    implausibly large profits. Some instruments list late or delist early to exercise
    survivorship handling.
    """
    cfg = config or SyntheticConfig()
    rng = np.random.default_rng(cfg.seed)
    n, t = cfg.n_instruments, cfg.n_days
    dates = pd.bdate_range(cfg.start, periods=t)
    names = [f"SYN{i:03d}" for i in range(n)]

    beta = rng.uniform(0.6, 1.4, n)
    vol = cfg.idio_vol * rng.uniform(0.6, 1.6, n)
    lo, hi = cfg.adv_shares_range
    adv = np.exp(rng.uniform(np.log(lo), np.log(hi), n))
    start_px = np.exp(rng.uniform(np.log(10), np.log(200), n))

    first = np.zeros(n, dtype=int)
    last = np.full(n, t - 1)
    churn = rng.random(n) < (cfg.listing_churn if t >= 60 else 0.0)
    for i in np.flatnonzero(churn).tolist():
        if rng.random() < 0.5:
            first[i] = rng.integers(20, t // 2)
        else:
            last[i] = rng.integers(t // 2, t - 20)

    log_close = np.full((t, n), np.nan)
    log_open = np.full((t, n), np.nan)
    log_close[0] = np.log(start_px)
    log_open[0] = log_close[0]
    w = cfg.reversal_window
    for d in range(1, t):
        mkt_on = rng.normal(0, cfg.market_vol * 0.4)
        mkt_id = rng.normal(0, cfg.market_vol * 0.9)
        past = log_close[d - 1] - log_close[max(d - 1 - w, 0)]
        signal = np.zeros(n)
        if d - 1 - w >= 0:
            z = (past - past.mean()) / (past.std() + 1e-12)
            signal = -cfg.reversal_strength * z
        overnight = beta * mkt_on + rng.normal(0, vol * 0.4)
        intraday = beta * mkt_id + signal + rng.normal(0, vol * 0.9)
        log_open[d] = log_close[d - 1] + overnight
        log_close[d] = log_open[d] + intraday

    open_ = np.exp(log_open)
    close = np.exp(log_close)
    span = np.abs(rng.normal(0, 0.004, (t, n)))
    high = np.maximum(open_, close) * np.exp(span)
    low = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, 0.004, (t, n))))
    volume = np.round(adv * np.exp(rng.normal(0, 0.35, (t, n))))

    frames = []
    for i, name in enumerate(names):
        sl = slice(first[i], last[i] + 1)
        frames.append(
            pd.DataFrame(
                {
                    "date": dates[sl],
                    "instrument": name,
                    "open": open_[sl, i],
                    "high": high[sl, i],
                    "low": low[sl, i],
                    "close": close[sl, i],
                    "volume": volume[sl, i],
                    # No splits or dividends are simulated, so prices trade as quoted.
                    "close_as_traded": close[sl, i],
                }
            )
        )
    out = pd.concat(frames, ignore_index=True).sort_values(["date", "instrument"])
    return out.reset_index(drop=True)


SYNTHETIC_METADATA = {
    "frequency": "1d",
    "currency": "USD",
    "price_adjustment": "total_return_adjusted",
    "calendar": "weekdays (synthetic, no holidays)",
    "timezone": "America/New_York",
    "universe": "all listed instruments on each date (point-in-time by construction)",
    "note": "Synthetic data with a planted 5-day reversal effect. Not market data.",
}


def load_csv_bars(
    path: str | os.PathLike[str],
    *,
    column_map: dict[str, str] | None = None,
    date_format: str | None = None,
) -> pd.DataFrame:
    """Load user-supplied daily bars from a local CSV (one row per date and instrument).

    ``column_map`` renames source columns to ``date, instrument, open, high, low, close,
    volume`` and, optionally, ``close_as_traded`` (the unadjusted close, needed for a
    minimum-price rule). Values are parsed but not cleaned; run :func:`clean_bars` next.
    """
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    if column_map:
        raw = raw.rename(columns=column_map)
    required = ["date", "instrument", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns {missing}")
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(raw["date"], format=date_format, errors="coerce"),
            "instrument": raw["instrument"].str.strip(),
        }
    )
    for col in required[2:]:
        out[col] = pd.to_numeric(raw[col], errors="coerce")
    if AS_TRADED_CLOSE.name in raw.columns:  # parsed by cleaning, which judges null markers
        out[AS_TRADED_CLOSE.name] = raw[AS_TRADED_CLOSE.name]
    return out


def synthetic_universe(
    bars: pd.DataFrame, *, name: str = "SYN", seasoning: int = 20, seed: int = 7
) -> pd.DataFrame:
    """Point-in-time membership derived from listings, for testing and demos.

    An instrument joins ``seasoning`` sessions after listing and leaves on its final
    session. A few members are also removed for a while and re-added later, so the
    universe changes independently of listing status.
    """
    rng = np.random.default_rng(seed)
    dates = pd.DatetimeIndex(sorted(bars["date"].unique()))
    end_of_data = dates[-1]
    rows = []
    for instrument, grp in bars.groupby("instrument"):
        first = dates.get_loc(grp["date"].min())
        last_date = grp["date"].max()
        start_i = first + seasoning
        if start_i >= len(dates) or dates[start_i] >= last_date:
            continue
        end = None if last_date == end_of_data else last_date
        start = dates[start_i]
        span = (len(dates) - 1 if end is None else dates.get_loc(end)) - start_i
        if span > 120 and rng.random() < 0.2:
            out_i = start_i + int(rng.integers(30, span // 2))
            back_i = out_i + int(rng.integers(20, 60))
            rows.append((name, instrument, start, dates[out_i]))
            rows.append((name, instrument, dates[back_i], end))
        else:
            rows.append((name, instrument, start, end))
    out = pd.DataFrame(rows, columns=["universe", "instrument", "start_date", "end_date"])
    out["end_date"] = pd.to_datetime(out["end_date"])
    return out


def synthetic_fundamentals(bars: pd.DataFrame, *, seed: int = 7) -> pd.DataFrame:
    """Quarterly ``book_to_price`` and ``earnings_yield`` with reporting lags and revisions.

    Each value is published 30-45 calendar days after its period end; about 20% are later
    revised (published again 60-90 days after period end with a changed value).
    """
    rng = np.random.default_rng(seed + 1)
    rows = []
    for instrument, grp in bars.groupby("instrument"):
        closes = grp.set_index("date")["close"]
        period_ends = closes.index[::63]
        level = {"book_to_price": rng.uniform(0.2, 1.5), "earnings_yield": rng.uniform(0.0, 0.1)}
        for pe in period_ends:
            for field, base in level.items():
                value = float(base * np.exp(rng.normal(0, 0.15)))
                avail = pe + pd.Timedelta(days=int(rng.integers(30, 46)))
                rows.append((instrument, field, pe, avail, value))
                if rng.random() < 0.2:
                    revised = value * float(np.exp(rng.normal(0, 0.1)))
                    later = pe + pd.Timedelta(days=int(rng.integers(60, 91)))
                    rows.append((instrument, field, pe, later, revised))
    return pd.DataFrame(
        rows, columns=["instrument", "field", "period_end", "available_date", "value"]
    )
