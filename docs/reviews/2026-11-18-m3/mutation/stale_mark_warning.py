"""R3 probe: a held name loses its bars (no settlement); the engine keeps its last mark and
warns (README.md:165, strategy-evaluation/README.md:83). Run on the checkout's code."""

import pandas as pd

from invest_evaluation.config import BacktestConfig, CostModel, ExecutionConfig, StrategyConfig
from invest_evaluation.engine import run_backtest

dates = pd.bdate_range("2024-01-01", periods=8)
rows = []
for k, d in enumerate(dates):
    if k < 5:
        rows.append([d, "A", 10.0, 10.0, 10.0, 10.0, 1e9])
    rows.append([d, "B", 20.0, 20.0, 20.0, 20.0, 1e9])
bars = pd.DataFrame(rows, columns=["date", "instrument", "open", "high", "low", "close", "volume"])
sig = pd.DataFrame({"decision_date": [dates[2]] * 2, "instrument": ["A", "B"], "score": [1.0, 0.0]})
cfg = BacktestConfig(
    strategy=StrategyConfig(
        long_fraction=0.5, short_fraction=0.0, rebalance_every=100, min_names=2
    ),
    execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
    costs=CostModel(
        commission_bps=0,
        half_spread_bps=0,
        impact_coef=0,
        borrow_bps_annual=0,
        adv_window=1,
        vol_window=2,
    ),
)
res = run_backtest(bars, sig, cfg)
print("n_long at end:", int(res.daily["n_long"].iloc[-1]))
print("warnings:", res.warnings)
