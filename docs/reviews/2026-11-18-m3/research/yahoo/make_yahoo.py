# ruff: noqa: B905  (evidence script kept as run)
"""Perturbed copies of the replayed Yahoo market bundle (kept outside the repository).

Y1: prices and volume strictly after T randomised, 3% of bars after T dropped.
Y2: a later corporate action per instrument: OHLC on dates <= T times c_i, volume / c_i
    (the adjusted history a split or dividend after T would rewrite).
Usage: python make_yahoo.py <market bundle> <out dir> <T>
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from invest_data.schemas import publish_market_bars, read_market_bars

src, dst, T = Path(sys.argv[1]), Path(sys.argv[2]), pd.Timestamp(sys.argv[3])
m, bars = read_market_bars(src)
rng = np.random.default_rng(11)
prices = ["open", "high", "low", "close"]

y1 = bars.copy()
after = y1["date"] > T
f = np.exp(rng.normal(0, 0.1, after.sum()))
for c in prices:
    y1.loc[after, c] *= f
y1.loc[after, "volume"] = np.round(
    y1.loc[after, "volume"] * np.exp(rng.normal(0, 0.5, after.sum()))
)
y1 = y1.loc[~(after & (rng.random(len(y1)) < 0.03))]
publish_market_bars(
    y1, dst / "Y1" / "market", dataset_id=m.dataset_id, metadata=m.metadata, fmt="parquet"
)

y2 = bars.copy()
insts = sorted(y2["instrument"].unique())
c = dict(zip(insts, rng.choice([0.25, 0.5, 0.8, 0.97, 1.03, 2.0, 3.0], len(insts))))
before = y2["date"] <= T
scale = y2.loc[before, "instrument"].map(c).to_numpy()
for col in prices:
    y2.loc[before, col] *= scale
y2.loc[before, "volume"] = y2.loc[before, "volume"] / scale
publish_market_bars(
    y2, dst / "Y2" / "market", dataset_id=m.dataset_id, metadata=m.metadata, fmt="parquet"
)
print("bars", len(bars), "Y1", len(y1), "Y2", len(y2), "T", T.date())
