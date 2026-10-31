"""The equal-weight universe benchmark omits a supplied delisting settlement: the strategy
books the loss, the benchmark never sees it (survivorship bias in the relative metrics).

Usage: python -I benchmark_ignores_delisting_settlement.py <worktree>
"""
import sys
from pathlib import Path

sys.path[:0] = [str(Path(sys.argv[1]) / p / "src") for p in ("strategy-evaluation", "data-pipeline/data-preparation")]
import numpy as np
import pandas as pd
from invest_evaluation.config import BacktestConfig, CostModel, ExecutionConfig, StrategyConfig
from invest_evaluation.engine import run_backtest
from invest_evaluation.metrics import compute_metrics


class Fixed:
    def __init__(self, w):
        self.w = pd.Series(w, dtype=float)

    def target_weights(self, scores):
        return self.w


dates = pd.bdate_range("2024-01-01", periods=30)
rows = []
for k, d in enumerate(dates):
    for name, px in (("B", 20.0), ("C", 30.0)):
        rows.append([d, name, px, px, px, px, 1e8])
    if k <= 10:  # A's last bar is session 11; it is settled at 0 that close
        rows.append([d, "A", 10.0, 10.0, 10.0, 10.0, 1e8])
bars = pd.DataFrame(rows, columns=["date", "instrument", "open", "high", "low", "close", "volume"])
signals = pd.DataFrame({"decision_date": [dates[3]] * 3, "instrument": ["A", "B", "C"], "score": [1.0, 1.0, 1.0]})
delist = pd.DataFrame({"date": [dates[10]], "instrument": ["A"], "settlement_price": [0.0]})
cfg = BacktestConfig(
    strategy=StrategyConfig(min_names=1, rebalance_every=100),
    execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
    costs=CostModel(commission_bps=0, half_spread_bps=0, impact_coef=0, borrow_bps_annual=0, adv_window=1, vol_window=2),
)
res = run_backtest(bars, signals, cfg, Fixed({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}), delistings=delist)
event = dates[10]
strat = res.returns.loc[event]
bench = res.benchmark.loc[event]
m = compute_metrics(res)["benchmark"]
print(f"settlement day {event.date()}: strategy return {strat:.4f}, benchmark return {bench:.4f}")
print("benchmark total return", m["benchmark_total_return"]["value"], "information_ratio", m["information_ratio"])
if strat < -0.3 and abs(bench) < 1e-9:
    print("DEFECT: A (one of three equal-weight members) settled at 0 on the event date; the strategy "
          f"returns {strat:.2%} that day but the universe equal-weight benchmark returns {bench:.2%} "
          "(expected about -33%): benchmark_total_return, IR, alpha and beta ignore the settlement")
    sys.exit(1)
print("OK")
