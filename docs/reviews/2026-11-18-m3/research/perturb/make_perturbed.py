"""Build perturbed copies of the synthetic bundles: everything strictly after T changes.

Usage: python make_perturbed.py <src_dir> <dst_dir> <T>
src_dir holds market/, universe/, fundamentals/ bundles. Writes the same three into dst_dir.
Prices after T get random per-(date, instrument) factors, volume random, 5% of bars after T
are dropped; universe intervals change after T only; fundamentals get revisions and late
filings whose available_date is after T. Nothing at or before T changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from invest_data.schemas import (
    publish_fundamentals,
    publish_market_bars,
    publish_universe,
    read_fundamentals,
    read_market_bars,
    read_universe,
)

src, dst, t_text = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
T = pd.Timestamp(t_text)
rng = np.random.default_rng(7)

m, bars = read_market_bars(src / "market")
after = bars["date"] > T
f = np.exp(rng.normal(0, 0.1, after.sum()))
for col in ("open", "high", "low", "close", "close_as_traded"):
    if col in bars:
        bars.loc[after, col] = bars.loc[after, col] * f
bars.loc[after, "volume"] = np.round(
    bars.loc[after, "volume"] * np.exp(rng.normal(0, 0.5, after.sum()))
)
drop = after & (rng.random(len(bars)) < 0.05)
bars = bars.loc[~drop].reset_index(drop=True)
publish_market_bars(
    bars, dst / "market", dataset_id=m.dataset_id, metadata=m.metadata, fmt="parquet"
)

mu, uni = read_universe(src / "universe")
rows = []
for r in uni.itertuples(index=False):
    live_after = pd.isna(r.end_date) or r.end_date > T
    if r.start_date > T:
        continue  # drop intervals that start after T
    if live_after and int(r.instrument[-1]) % 2 == 0:
        rows.append((r.universe, r.instrument, r.start_date, T + pd.Timedelta(days=20)))
        rows.append((r.universe, r.instrument, T + pd.Timedelta(days=80), pd.NaT))
    elif live_after:
        rows.append((r.universe, r.instrument, r.start_date, T + pd.Timedelta(days=1)))
    else:
        rows.append(tuple(r))
members = set(uni["instrument"])
for inst in sorted(set(bars["instrument"]) - members):
    rows.append(("SYN", inst, T + pd.Timedelta(days=3), pd.NaT))
uni2 = pd.DataFrame(rows, columns=["universe", "instrument", "start_date", "end_date"])
publish_universe(
    uni2, dst / "universe", dataset_id=mu.dataset_id, metadata=mu.metadata, fmt="parquet"
)

mf, fund = read_fundamentals(src / "fundamentals")
rev = fund.copy()
rev["available_date"] = rev["available_date"].clip(lower=T) + pd.Timedelta(days=5)
rev["value"] = -10 * rev["value"]
late = fund.copy()
late["period_end"] = T - pd.Timedelta(days=1)
late["available_date"] = T + pd.Timedelta(days=2)
late = late.drop_duplicates(["instrument", "field"])
late["value"] = 99.0
fund2 = pd.concat([fund, rev, late]).drop_duplicates(
    ["instrument", "field", "period_end", "available_date"]
)
publish_fundamentals(
    fund2, dst / "fundamentals", dataset_id=mf.dataset_id, metadata=mf.metadata, fmt="parquet"
)
print(
    "perturbed after",
    T.date(),
    "bars",
    len(bars),
    "universe rows",
    len(uni2),
    "fund rows",
    len(fund2),
)
