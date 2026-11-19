# ruff: noqa: E501  (evidence script kept as run)
"""Engine holding for one decision equals the mining label (open t+1 -> open t+1+h), zero costs."""

import sys

import pandas as pd

from invest_data.schemas import read_market_bars
from invest_evaluation.config import BacktestConfig
from invest_evaluation.engine import run_backtest
from invest_mining.diagnostics import forward_returns
from invest_mining.expressions import build_panel

_, bars = read_market_bars(sys.argv[1])
dates = sorted(bars["date"].unique())
h = 5
sym = "SYN001"
t = dates[100]


class One:
    def target_weights(self, scores):
        return pd.Series({sym: float(scores.get(sym, 0.0) > 0)})


sig = pd.DataFrame(
    {"decision_date": [t, dates[100 + h]], "instrument": [sym, sym], "score": [1.0, -1.0]}
)
cfg = BacktestConfig.from_dict(
    {
        "strategy": {"rebalance_every": h, "min_names": 1},
        "execution": {
            "delay": 0,
            "max_participation": 1.0,
            "min_price": 0.0,
            "min_adv_dollar": 0.0,
        },
        "costs": {
            "commission_bps": 0,
            "half_spread_bps": 0,
            "impact_coef": 0,
            "borrow_bps_annual": 0,
            "cash_rate_annual": 0,
            "adv_window": 20,
            "vol_window": 20,
        },
        "end": str(dates[100 + h + 3].date()),
    }
)
res = run_backtest(bars, sig, cfg, strategy=One())
eq = res.daily["equity"]
engine = eq.loc[dates[100 + h + 1]] / cfg.initial_capital - 1
label = forward_returns(build_panel(bars)["open"], h).loc[t, sym]
print(
    f"engine return held from decision {t.date()} (exit filled {dates[100 + h + 1].date()}): {engine:.12f}"
)
print(f"mining label open t+1 -> open t+1+h:                                  {label:.12f}")
