# ruff: noqa: E501  (evidence script kept as run)
"""BH-2026-10-21-2: universe benchmark with a delisting settled at 0 must count -100% that day."""

import sys

import pandas as pd

from invest_data.schemas import read_market_bars
from invest_evaluation.config import BacktestConfig
from invest_evaluation.engine import run_backtest

_, bars = read_market_bars(sys.argv[1])
dates = sorted(bars["date"].unique())
sym = "SYN010"
ev = dates[300]
bars = bars[~((bars["instrument"] == sym) & (bars["date"] > ev))]
sig = bars[bars["date"].isin(dates[260:320])][["date", "instrument", "close"]].rename(
    columns={"date": "decision_date", "close": "score"}
)
cfg = BacktestConfig.from_dict({"execution": {"min_price": 0.0}, "start": str(dates[250].date())})
res = run_backtest(
    bars,
    sig,
    cfg,
    delistings=pd.DataFrame([{"date": ev, "instrument": sym, "settlement_price": 0.0}]),
)
plain = run_backtest(bars, sig, cfg)
n = bars[bars["date"] == ev]["instrument"].nunique()
print(
    f"benchmark on {ev.date()}: with settlement {res.benchmark.loc[ev]:.5f}, without {plain.benchmark.loc[ev]:.5f}; "
    f"difference {res.benchmark.loc[ev] - plain.benchmark.loc[ev]:.5f} ~ expected about -1/{n} = {-1 / n:.5f} (plus the name's own day return)"
)
