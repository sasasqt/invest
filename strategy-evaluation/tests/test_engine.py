from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from invest_evaluation.config import BacktestConfig, CostModel, ExecutionConfig, StrategyConfig
from invest_evaluation.engine import InputError, run_backtest


class Fixed:
    """Strategy returning fixed weights regardless of scores."""

    def __init__(self, weights: dict[str, float]):
        self.weights = pd.Series(weights, dtype=float)

    def target_weights(self, scores: pd.Series) -> pd.Series:
        return self.weights


def hand_market() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=6)
    a_open = [10, 10, 10, 11, 12, 12]
    a_close = [10, 10, 10.5, 11.5, 12, 13]
    rows = []
    for k, d in enumerate(dates):
        rows.append(
            [
                d,
                "A",
                a_open[k],
                max(a_open[k], a_close[k]),
                min(a_open[k], a_close[k]),
                a_close[k],
                1e9,
            ]
        )
        rows.append([d, "B", 20.0, 20.0, 20.0, 20.0, 1e9])
    return pd.DataFrame(
        rows, columns=["date", "instrument", "open", "high", "low", "close", "volume"]
    ).astype({"open": float, "high": float, "low": float, "close": float})


def hand_config(**costs) -> BacktestConfig:
    return BacktestConfig(
        strategy=StrategyConfig(rebalance_every=100, min_names=1),
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
        costs=CostModel(
            **{
                "commission_bps": 0,
                "half_spread_bps": 0,
                "impact_coef": 0,
                "borrow_bps_annual": 0,
                "adv_window": 1,
                "vol_window": 2,
                **costs,
            }
        ),
        initial_capital=1000.0,
    )


def signals_on(date, names=("A", "B")) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "decision_date": [pd.Timestamp(date)] * len(names),
            "instrument": list(names),
            "score": [1.0] * len(names),
        }
    )


def test_hand_calculated_long_position_with_commission():
    bars = hand_market()
    # Decide after the close of day 2 (2024-01-03); fill at the open of day 3 (price 11).
    res = run_backtest(
        bars, signals_on("2024-01-03"), hand_config(commission_bps=10), Fixed({"A": 1.0})
    )
    eq = res.daily["equity"]
    assert eq.index[0] == pd.Timestamp("2024-01-03")  # window starts at the first signal
    shares = 1000.0 / 11.0
    cost = 1000.0 * 10 / 1e4
    assert eq.loc["2024-01-03"] == pytest.approx(1000.0)
    assert eq.loc["2024-01-04"] == pytest.approx(1000.0 - cost + shares * (11.5 - 11))
    assert eq.loc["2024-01-08"] == pytest.approx(1000.0 - cost + shares * (13 - 11))
    fill = res.trades.iloc[0]
    assert (fill["date"], fill["price"], fill["commission"]) == (
        pd.Timestamp("2024-01-04"),
        11.0,
        pytest.approx(cost),
    )
    assert res.episodes.iloc[0]["status"] == "open"
    assert res.episodes.iloc[0]["pnl"] == pytest.approx(eq.iloc[-1] - 1000.0)


def test_spread_impact_and_borrow_costs():
    bars = hand_market()
    cfg = hand_config(half_spread_bps=20, impact_coef=1.0, borrow_bps_annual=252e4 * 0.001)
    res = run_backtest(bars, signals_on("2024-01-03"), cfg, Fixed({"A": -0.5}))
    fill = res.trades.iloc[0]
    notional = 500.0
    # 2-session volatility known at the decision close (Jan 3): returns 0% and 5%.
    vol = pd.Series([0.0, 0.05]).std(ddof=1)
    adv = 10.5 * 1e9
    assert fill["spread"] == pytest.approx(notional * 20 / 1e4)
    assert fill["impact"] == pytest.approx(notional * vol * np.sqrt(notional / adv))
    # Borrow: 0.1% of short market value per session.
    short_value_close = (500.0 / 11.0) * 11.5
    assert res.daily.loc["2024-01-04", "borrow_cost"] == pytest.approx(0.001 * short_value_close)


def test_accounting_reconciles_with_all_costs(market, reversal_signals):
    cfg = BacktestConfig(costs=CostModel(cash_rate_annual=0.02, borrow_bps_annual=100))
    res = run_backtest(market, reversal_signals, cfg)
    net = res.daily["equity"].iloc[-1] - cfg.initial_capital
    assert res.episodes["pnl"].sum() + res.daily["financing"].sum() == pytest.approx(net)
    costs = res.daily[["commission_cost", "spread_cost", "impact_cost", "borrow_cost"]].sum()
    assert costs.sum() == pytest.approx(res.daily["cum_costs"].iloc[-1])
    assert (res.daily["equity_before_costs"] - res.daily["equity"]).iloc[-1] == pytest.approx(
        costs.sum()
    )


def test_fills_happen_strictly_after_decisions(market, reversal_signals):
    for delay in (0, 2):
        cfg = BacktestConfig(execution=ExecutionConfig(delay=delay))
        res = run_backtest(market, reversal_signals, cfg)
        fills = res.trades[(res.trades["status"] == "filled") & res.trades["decision_date"].notna()]
        cal = pd.Index(sorted(market["date"].unique()))
        gap = cal.get_indexer(fills["date"]) - cal.get_indexer(
            pd.to_datetime(fills["decision_date"])
        )
        assert (gap == 1 + delay).all()


def test_future_prices_and_signals_cannot_change_the_past(market, reversal_signals):
    cut = pd.Timestamp(sorted(market["date"].unique())[150])
    base = run_backtest(market, reversal_signals).daily["equity"]

    shocked = market.copy()
    later = shocked["date"] > cut
    shocked.loc[later, ["open", "high", "low", "close"]] *= np.exp(
        np.random.default_rng(0).normal(0, 0.2, (later.sum(), 1))
    )
    shocked.loc[later, "high"] = shocked.loc[later, ["open", "high", "close"]].max(axis=1)
    shocked.loc[later, "low"] = shocked.loc[later, ["open", "low", "close"]].min(axis=1)
    alt = run_backtest(shocked, reversal_signals).daily["equity"]
    pd.testing.assert_series_equal(base.loc[:cut], alt.loc[:cut])
    assert not np.allclose(base.loc[cut:].iloc[2:], alt.loc[cut:].iloc[2:])

    flipped = reversal_signals.copy()
    on_or_after = flipped["decision_date"] >= cut
    flipped.loc[on_or_after, "score"] *= -1
    alt2 = run_backtest(market, flipped).daily["equity"]
    pd.testing.assert_series_equal(base.loc[:cut], alt2.loc[:cut])


def test_explicit_delisting_settlement_reconciles():
    bars = hand_market()
    bars = bars[~((bars["instrument"] == "A") & (bars["date"] > "2024-01-05"))]
    events = pd.DataFrame([{"date": "2024-01-05", "instrument": "A", "settlement_price": 8.0}])
    res = run_backtest(
        bars, signals_on("2024-01-03"), hand_config(), Fixed({"A": 1.0}), delistings=events
    )
    liq = res.trades[res.trades["reason"] == "delisted_liquidation"].iloc[0]
    assert liq["date"] == pd.Timestamp("2024-01-05") and liq["price"] == 8.0
    assert res.episodes.iloc[0]["exit_reason"] == "delisted"
    assert res.daily["equity"].iloc[-1] == pytest.approx(1000.0 / 11.0 * 8.0)
    assert res.episodes["pnl"].sum() == pytest.approx(res.daily["equity"].iloc[-1] - 1000.0)
    assert res.daily["n_long"].iloc[-1] == 0


@pytest.mark.parametrize("weight", [1.0, -0.5])
def test_future_bar_removal_cannot_change_past_portfolio_state(weight):
    bars = hand_market()
    cut = pd.Timestamp("2024-01-05")
    changed = bars[~((bars["instrument"] == "A") & (bars["date"] > cut))]
    cfg = hand_config(borrow_bps_annual=2520.0, cash_rate_annual=0.05)
    baseline = run_backtest(bars, signals_on("2024-01-03"), cfg, Fixed({"A": weight}))
    altered = run_backtest(changed, signals_on("2024-01-03"), cfg, Fixed({"A": weight}))
    pd.testing.assert_frame_equal(baseline.daily.loc[:cut], altered.daily.loc[:cut])
    assert "delisted_liquidation" not in altered.trades["reason"].values
    assert altered.daily["n_long" if weight > 0 else "n_short"].iloc[-1] == 1


def test_future_settlement_cannot_change_past_results():
    bars = hand_market()
    cfg = hand_config(borrow_bps_annual=2520.0)
    baseline = run_backtest(bars, signals_on("2024-01-03"), cfg, Fixed({"A": -0.5}))
    events = pd.DataFrame([{"date": "2024-01-08", "instrument": "A", "settlement_price": 0.0}])
    settled = run_backtest(
        bars, signals_on("2024-01-03"), cfg, Fixed({"A": -0.5}), delistings=events
    )
    pd.testing.assert_frame_equal(baseline.daily.iloc[:-1], settled.daily.iloc[:-1])
    assert settled.daily["n_short"].iloc[-1] == 0
    assert settled.trades.iloc[-1]["price"] == 0.0


@pytest.mark.parametrize(
    "weights, message",
    [
        (pd.Series({"TYPO": 1.0}), "unknown or ineligible"),
        (pd.Series([0.5, 0.5], index=["A", "A"]), "unique"),
        (pd.Series({"A": np.nan}), "finite"),
        (pd.Series({"A": np.inf}), "finite"),
        (pd.Series({"A": "1"}), "finite"),
        (pd.Series({"A": 2.0}), "gross_leverage"),
    ],
)
def test_invalid_strategy_targets_are_rejected(weights, message):
    strategy = Fixed({})
    strategy.weights = weights
    with pytest.raises(InputError, match=message):
        run_backtest(hand_market(), signals_on("2024-01-03"), hand_config(), strategy)


def test_strategy_cannot_trade_outside_decision_time_eligibility():
    with pytest.raises(InputError, match="ineligible"):
        run_backtest(
            hand_market(), signals_on("2024-01-03", names=("A",)), hand_config(), Fixed({"B": 1.0})
        )


@pytest.mark.parametrize(
    "event",
    [
        {"date": "2024-01-05", "instrument": "TYPO", "settlement_price": 0.0},
        {"date": "2030-01-01", "instrument": "A", "settlement_price": 0.0},
        {"date": "2024-01-05", "instrument": "A", "settlement_price": -1.0},
        {"date": "2024-01-05", "instrument": "A", "settlement_price": np.nan},
    ],
)
def test_invalid_settlement_events_are_rejected(event):
    with pytest.raises(InputError, match="delisting"):
        run_backtest(
            hand_market(), signals_on("2024-01-03"), hand_config(), delistings=pd.DataFrame([event])
        )


def test_order_rejected_when_instrument_has_no_bar_on_fill_date():
    bars = hand_market()
    bars = bars[~((bars["instrument"] == "A") & (bars["date"] == "2024-01-04"))]
    res = run_backtest(bars, signals_on("2024-01-03"), hand_config(), Fixed({"A": 1.0}))
    assert res.trades.iloc[0]["status"] == "rejected"
    assert res.trades.iloc[0]["reason"] == "no_bar_on_fill_date"
    assert (res.daily["equity"] == 1000.0).all()


def test_participation_cap_limits_fill_size():
    bars = hand_market()
    bars["volume"] = 10.0  # ADV = close * 10
    cfg = BacktestConfig(
        strategy=StrategyConfig(rebalance_every=100, min_names=1),
        execution=ExecutionConfig(max_participation=0.1, min_price=0.0),
        costs=CostModel(
            commission_bps=0, half_spread_bps=0, impact_coef=0, adv_window=1, vol_window=2
        ),
        initial_capital=1000.0,
    )
    res = run_backtest(bars, signals_on("2024-01-03"), cfg, Fixed({"A": 1.0}))
    fill = res.trades.iloc[0]
    assert fill["reason"] == "participation_cap"
    assert fill["notional"] == pytest.approx(0.1 * 10.5 * 10.0 / 11.0 * 11.0)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda s: pd.concat([s, s]), "duplicate"),
        (lambda s: s.assign(decision_date=pd.Timestamp("2030-01-01")), "not market sessions"),
        (lambda s: s.assign(instrument="ZZZ"), "unknown instruments"),
    ],
)
def test_invalid_signals_are_rejected(market, reversal_signals, mutate, message):
    with pytest.raises(InputError, match=message):
        run_backtest(market, mutate(reversal_signals.head(1)))


def test_quantile_strategy_weights_and_long_only(market, reversal_signals):
    ls = run_backtest(market, reversal_signals)
    assert ls.daily["net_exposure"].abs().mean() < 0.1  # drifts between rebalances
    assert ls.daily["gross_exposure"].iloc[-1] == pytest.approx(1.0, abs=0.15)
    lo = run_backtest(
        market, reversal_signals, BacktestConfig(strategy=StrategyConfig(short_fraction=0.0))
    )
    assert lo.daily["n_short"].max() == 0 and lo.daily["net_exposure"].iloc[-1] > 0.85


def test_config_rejects_unknown_keys():
    with pytest.raises(ValueError, match="unknown"):
        BacktestConfig.from_dict({"costs": {"comission_bps": 1}})
    with pytest.raises(ValueError):
        BacktestConfig.from_dict({"strategy": {"long_fraction": 0.6, "short_fraction": 0.6}})
    cfg = BacktestConfig.from_dict({"costs": {"commission_bps": 2}, "annualization": 260})
    assert cfg.costs.commission_bps == 2 and cfg.annualization == 260


def test_universe_limits_new_positions():
    bars = hand_market()
    uni = pd.DataFrame(
        {
            "universe": ["U"],
            "instrument": ["B"],
            "start_date": [pd.Timestamp("2024-01-01")],
            "end_date": [pd.NaT],
        }
    )
    res = run_backtest(bars, signals_on("2024-01-03"), hand_config(), QuantileOnly(), universe=uni)
    assert set(res.trades["instrument"]) == {"B"}


class QuantileOnly:
    """Long every eligible instrument equally (to observe which ones are eligible)."""

    def target_weights(self, scores: pd.Series) -> pd.Series:
        return pd.Series(1.0 / len(scores), index=scores.index) if len(scores) else scores


def split_market(*, adjusted: bool) -> pd.DataFrame:
    """A trades at 5, C at 0.5 and B at 20 on every session (as traded).

    After the last session A splits 10-for-1 and C consolidates 1-for-10. ``adjusted``
    gives the history as an adjuster publishes it once those actions are known: A's prices
    divided by 10 and C's multiplied by 10, volumes inversely, as-traded closes unchanged.
    """
    dates = pd.bdate_range("2024-01-01", periods=6)
    factor = {"A": 0.1, "B": 1.0, "C": 10.0} if adjusted else {"A": 1.0, "B": 1.0, "C": 1.0}
    traded = {"A": 5.0, "B": 20.0, "C": 0.5}
    rows = [
        [d, name, *[px * factor[name]] * 4, 1e6 / factor[name], px]
        for d in dates
        for name, px in traded.items()
    ]
    columns = ["date", "instrument", "open", "high", "low", "close", "volume", "close_as_traded"]
    return pd.DataFrame(rows, columns=columns)


def test_min_price_uses_the_as_traded_close_so_later_actions_cannot_change_eligibility():
    """K11: eligibility on a decision date must not depend on corporate actions after it."""
    cfg = replace(hand_config(), execution=ExecutionConfig(max_participation=1.0, min_price=1.0))
    signals = signals_on("2024-01-03", names=("A", "B", "C"))
    runs = [
        run_backtest(
            split_market(adjusted=adjusted),
            signals,
            cfg,
            Fixed({"B": 1.0}),
            record_decisions=True,
        )
        for adjusted in (False, True)
    ]
    for res in runs:
        # A traded at 5 (adjusted 0.5 later) and stays eligible; C traded at 0.5 (adjusted
        # 5 later) and stays excluded.
        assert sorted(res.decisions["instrument"]) == ["A", "B"]
    pd.testing.assert_frame_equal(runs[0].decisions, runs[1].decisions)
    pd.testing.assert_series_equal(runs[0].daily["equity"], runs[1].daily["equity"])

    # A name whose as-traded close is unknown on the decision date cannot pass the floor.
    # The warning counts only names nothing else excluded (C fails min_adv_dollar too).
    bars = split_market(adjusted=True)
    day = bars["date"] == "2024-01-03"
    bars.loc[day & bars["instrument"].isin(["A", "C"]), "close_as_traded"] = None
    cfg = replace(cfg, execution=replace(cfg.execution, min_adv_dollar=1e6))
    res = run_backtest(bars, signals, cfg, Fixed({"B": 1.0}), record_decisions=True)
    assert sorted(res.decisions["instrument"]) == ["B"]
    assert res.warnings == [
        "1 otherwise eligible name-decisions had no close_as_traded and failed execution.min_price"
    ]


def test_min_price_without_as_traded_closes_is_refused():
    bars = split_market(adjusted=True).drop(columns="close_as_traded")
    cfg = replace(hand_config(), execution=ExecutionConfig(max_participation=1.0, min_price=1.0))
    with pytest.raises(InputError, match="needs the as-traded close"):
        run_backtest(bars, signals_on("2024-01-03"), cfg, Fixed({"B": 1.0}))
    # A column with no known value in the evaluation window is no better than none.
    early = bars.assign(close_as_traded=5.0).assign(
        close_as_traded=lambda f: f["close_as_traded"].where(f["date"] < "2024-01-03")
    )
    for window in (cfg, replace(cfg, start="2024-01-03")):  # default: from the first signal
        with pytest.raises(InputError, match="no session in the evaluation window has one"):
            run_backtest(early, signals_on("2024-01-03"), window, Fixed({"B": 1.0}))
    for unknown in (float("nan"), None):  # float NaN, or object None from a caller's frame
        with pytest.raises(InputError, match="needs the as-traded close"):
            run_backtest(
                bars.assign(close_as_traded=unknown),
                signals_on("2024-01-03"),
                cfg,
                Fixed({"B": 1.0}),
            )
    # Without a price level there is nothing to compare, so adjusted closes suffice.
    res = run_backtest(bars, signals_on("2024-01-03"), hand_config(), Fixed({"B": 1.0}))
    assert res.daily["equity"].iloc[-1] == pytest.approx(1000.0)
