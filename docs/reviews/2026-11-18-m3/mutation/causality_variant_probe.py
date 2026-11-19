"""R3 probe: the release-gate causality test of test_engine.py:209 with a decision on
every session (rebalance_every=1) and the decisions compared too. Same data and shocks."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from invest_data.sources import SyntheticConfig, synthetic_market
from invest_evaluation.config import BacktestConfig, StrategyConfig
from invest_evaluation.engine import run_backtest


@pytest.fixture(scope="module")
def market():
    return synthetic_market(SyntheticConfig(n_instruments=30, n_days=260, seed=5))


@pytest.fixture(scope="module")
def reversal_signals(market):
    close = market.pivot(index="date", columns="instrument", values="close")
    score = -(close / close.shift(5) - 1)
    long = score.stack().rename("score").reset_index()
    long.columns = ["decision_date", "instrument", "score"]
    return long.dropna().reset_index(drop=True)


@pytest.mark.parametrize("every", [5, 1])
def test_future_prices_and_signals_cannot_change_the_past(market, reversal_signals, every):
    cfg = replace(BacktestConfig(), strategy=replace(StrategyConfig(), rebalance_every=every))
    cut = pd.Timestamp(sorted(market["date"].unique())[150])
    base = run_backtest(market, reversal_signals, cfg).daily["equity"]
    shocked = market.copy()
    later = shocked["date"] > cut
    shocked.loc[later, ["open", "high", "low", "close"]] *= np.exp(
        np.random.default_rng(0).normal(0, 0.2, (later.sum(), 1))
    )
    shocked.loc[later, "high"] = shocked.loc[later, ["open", "high", "close"]].max(axis=1)
    shocked.loc[later, "low"] = shocked.loc[later, ["open", "low", "close"]].min(axis=1)
    alt = run_backtest(shocked, reversal_signals, cfg).daily["equity"]
    pd.testing.assert_series_equal(base.loc[:cut], alt.loc[:cut])
    flipped = reversal_signals.copy()
    on_or_after = flipped["decision_date"] >= cut
    flipped.loc[on_or_after, "score"] *= -1
    alt2 = run_backtest(market, flipped, cfg).daily["equity"]
    pd.testing.assert_series_equal(base.loc[:cut], alt2.loc[:cut])
