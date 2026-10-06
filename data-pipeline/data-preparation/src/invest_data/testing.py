"""Test support: fabricated Yahoo-format chart responses and snapshots.

Real vendor data is never committed. Tests build Yahoo-shaped responses from known bars
instead, so parsing, adjustment, hashing and replay can be checked offline and exactly.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from invest_data.yahoo import download_snapshot

SESSION_OPEN = pd.Timedelta(hours=9, minutes=30)


def fake_chart(
    bars: pd.DataFrame,
    symbol: str,
    *,
    adj_factor: float | pd.Series = 1.0,
    tz: str = "America/New_York",
    currency: str = "USD",
) -> dict[str, Any]:
    """A chart response for one symbol's bars (``date, open, high, low, close, volume``).

    Timestamps are the session open in ``tz``, as Yahoo reports them. ``adjclose`` is
    ``close * adj_factor``. NaN values become JSON ``null``.
    """
    df = bars.sort_values("date")
    stamps = (pd.to_datetime(df["date"]) + SESSION_OPEN).dt.tz_localize(tz).dt.tz_convert("UTC")
    factor = adj_factor if isinstance(adj_factor, float | int) else adj_factor.to_numpy()

    def values(series: pd.Series) -> list[float | None]:
        return [None if pd.isna(v) else float(v) for v in series]

    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": currency,
                        "symbol": symbol,
                        "exchangeTimezoneName": tz,
                        "dataGranularity": "1d",
                    },
                    "timestamp": [int(t.timestamp()) for t in stamps],
                    "indicators": {
                        "quote": [
                            {k: values(df[k]) for k in ("open", "high", "low", "close", "volume")}
                        ],
                        "adjclose": [{"adjclose": values(df["close"] * factor)}],
                    },
                }
            ],
            "error": None,
        }
    }


def write_fake_snapshot(
    bars: pd.DataFrame,
    out: str | os.PathLike[str],
    *,
    start: str | None = None,
    end: str | None = None,
    adj_factors: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Write a snapshot for every instrument in ``bars`` through the real download path."""
    payloads = {
        str(sym): json.dumps(
            fake_chart(grp, str(sym), adj_factor=(adj_factors or {}).get(str(sym), 1.0))
        ).encode()
        for sym, grp in bars.groupby("instrument")
    }

    def fetcher(url: str, timeout: float) -> bytes:
        symbol = url.split("/chart/", 1)[1].split("?", 1)[0]
        return payloads[symbol]

    dates = pd.to_datetime(bars["date"])
    return download_snapshot(
        sorted(payloads),
        start or str(dates.min().date()),
        end or str(dates.max().date()),
        Path(out),
        fetcher=fetcher,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
