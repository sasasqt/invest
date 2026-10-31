from dataclasses import replace
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from invest_evaluation.config import BacktestConfig, CostModel, ExecutionConfig, StrategyConfig
from invest_evaluation.engine import InputError, check_price_rules, run_backtest


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


@pytest.mark.parametrize("categorical", [False, True])
def test_explicit_delisting_settlement_reconciles(categorical):
    bars = hand_market()
    bars = bars[~((bars["instrument"] == "A") & (bars["date"] > "2024-01-05"))]
    events = pd.DataFrame([{"date": "2024-01-05", "instrument": "A", "settlement_price": 8.0}])
    if categorical:
        events = events.astype({"instrument": "category"})
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


@pytest.mark.parametrize("instrument", [[], {}, ["A"], None, 1, True, "", " "])
def test_delisting_instruments_are_validated_before_index_operations(instrument):
    events = pd.DataFrame(
        [{"date": "2024-01-05", "instrument": instrument, "settlement_price": 1.0}]
    )
    with pytest.raises(InputError, match="delisting instrument must be a nonempty string"):
        run_backtest(hand_market(), signals_on("2024-01-03"), hand_config(), delistings=events)


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
        "1 otherwise eligible name-decisions had no positive finite close_as_traded and failed "
        "execution.min_price"
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
        with pytest.raises(
            InputError, match="no session in the evaluation window has a positive finite one"
        ):
            run_backtest(early, signals_on("2024-01-03"), window, Fixed({"B": 1.0}))
    # NaN, object None from a caller's frame, or a value that is not a positive finite price.
    for unknown in (float("nan"), None, float("inf"), -5.0):
        with pytest.raises(InputError, match="needs the as-traded close"):
            run_backtest(
                bars.assign(close_as_traded=unknown),
                signals_on("2024-01-03"),
                cfg,
                Fixed({"B": 1.0}),
            )
    for text in ("five", "5.0", True, 5 + 1j):  # text, booleans and complex are not prices
        dtype = bars.assign(close_as_traded=text)["close_as_traded"].dtype  # named as given
        with pytest.raises(InputError, match=f"must hold real numbers, not {dtype}"):
            run_backtest(
                bars.assign(close_as_traded=text), signals_on("2024-01-03"), cfg, Fixed({"B": 1.0})
            )
    for huge, message in ((10**400, " that fit a float"), (Decimal("sNaN"), ", not object")):
        column = pd.Series(huge, index=bars.index, dtype=object)
        with pytest.raises(InputError, match=f"must hold real numbers{message}"):
            run_backtest(
                bars.assign(close_as_traded=column), signals_on("2024-01-03"), cfg, Fixed({})
            )
    # Categoricals are judged by their values.
    with pytest.raises(InputError, match="must hold real numbers"):
        check_price_rules(
            bars.assign(close_as_traded="five").astype({"close_as_traded": "category"}), cfg
        )
    full = split_market(adjusted=True)
    categorical = full.astype({"close_as_traded": "category"})
    assert check_price_rules(categorical, cfg).equals(check_price_rules(full, cfg))
    single = full.assign(close_as_traded=5.0).astype({"close_as_traded": "category"})
    assert (check_price_rules(single, cfg) == 5.0).all()  # one category: no TypeError
    # Real numbers in an object column (e.g. after a concat with None) are prices.
    mixed = split_market(adjusted=True)
    values = mixed["close_as_traded"].astype(object)
    values[mixed["instrument"] == "A"] = Decimal("5")
    values.iloc[0] = None
    mixed["close_as_traded"] = values
    cfg_floor = replace(cfg, start=None)
    res = run_backtest(
        mixed,
        signals_on("2024-01-03", names=("A", "B", "C")),
        cfg_floor,
        Fixed({"B": 1.0}),
        record_decisions=True,
    )
    assert sorted(res.decisions["instrument"]) == ["A", "B"]
    # Without a price level there is nothing to compare, so adjusted closes suffice.
    res = run_backtest(bars, signals_on("2024-01-03"), hand_config(), Fixed({"B": 1.0}))
    assert res.daily["equity"].iloc[-1] == pytest.approx(1000.0)


def test_universe_benchmark_is_missing_on_a_session_with_no_member_return():
    """K17: a session where no held-universe name has a return is not a 0% benchmark day."""
    dates = pd.bdate_range("2024-01-01", periods=30)
    rows = []
    for k, d in enumerate(dates):
        # A and B skip session 15; C trades only then, so the session exists in the calendar.
        for name, base in (("A", 10.0), ("B", 20.0), ("C", 30.0)):
            if (name == "C") != (k == 15):
                continue
            px = base * 1.01**k
            rows.append([d, name, px, px, px, px, 1e9])
    bars = pd.DataFrame(
        rows, columns=["date", "instrument", "open", "high", "low", "close", "volume"]
    )
    signals = pd.DataFrame(
        {"decision_date": [dates[0]] * 2, "instrument": ["A", "B"], "score": [1.0, 2.0]}
    )
    cfg = BacktestConfig(
        strategy=StrategyConfig(rebalance_every=100, min_names=1),
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
        costs=CostModel(
            commission_bps=0,
            half_spread_bps=0,
            impact_coef=0,
            borrow_bps_annual=0,
            adv_window=1,
            vol_window=2,
        ),
        initial_capital=1000.0,
    )
    bench = run_backtest(bars, signals, cfg).benchmark
    assert np.isnan(bench.loc[dates[15]])
    # The sessions around it keep the members' 1% return.
    assert bench.loc[dates[14]] == pytest.approx(0.01)
    assert bench.loc[dates[17]] == pytest.approx(0.01)


@pytest.mark.parametrize(
    ("n", "fraction", "count"), [(100, 0.29, 29), (100, 0.57, 57), (10, 0.3, 3)]
)
def test_quantile_strategy_leg_size_is_exact(n, fraction, count):
    """K20: ``floor(100 * 0.29)`` is 28 in floating point; the leg must hold 29 names."""
    from invest_evaluation.strategies import QuantileStrategy, leg_size

    assert leg_size(n, fraction) == count
    scores = pd.Series(np.arange(n, dtype=float), index=[f"N{i:03d}" for i in range(n)])
    weights = QuantileStrategy(
        StrategyConfig(long_fraction=fraction, short_fraction=0.0, min_names=1)
    ).target_weights(scores)
    assert int((weights > 0).sum()) == count


def test_leg_size_matches_the_bucket_cutpoint_rule():
    """The largest k with k / n <= f, for every n and fraction on a fine grid."""
    from invest_evaluation.strategies import leg_size

    assert leg_size(0, 0.5) == 0
    for n in range(1, 301):
        for f in np.round(np.arange(0.0, 1.0001, 0.01), 2):
            expected = max(k for k in range(n + 1) if k / n <= f)
            assert leg_size(n, float(f)) == expected, (n, f)


class EqualWeight:
    """Long every eligible name equally."""

    def target_weights(self, scores: pd.Series) -> pd.Series:
        return pd.Series(1.0 / len(scores), index=scores.index) if len(scores) else scores


def listing_market() -> tuple[pd.DatetimeIndex, pd.DataFrame]:
    """A, B and C trade for 40 sessions; NEW lists on session 11 (index 10)."""
    dates = pd.bdate_range("2024-01-01", periods=40)
    rows = []
    for k, d in enumerate(dates):
        for name, px in (("A", 10.0), ("B", 20.0), ("C", 30.0)):
            rows.append([d, name, px, px, px, px * (1 + 0.001 * ((k % 3) - 1)), 1e8])
        if k >= 10:
            rows.append([d, "NEW", 50.0, 50.0, 50.0, 50.0 * (1 + 0.002 * ((k % 2) - 0.5)), 1e8])
    columns = ["date", "instrument", "open", "high", "low", "close", "volume"]
    return dates, pd.DataFrame(rows, columns=columns)


@pytest.mark.parametrize(
    ("decision", "new_eligible"),
    [(29, False), (30, True)],  # NEW has 20 bars (19 returns), then 21 bars (20 returns)
)
def test_a_name_without_a_volatility_estimate_is_not_eligible(decision, new_eligible):
    """BH-2026-10-21-1: ADV needs ``adv_window`` bars but volatility ``vol_window`` returns.

    A name with the first but not the second used to get weight and then be rejected
    ``no_liquidity_estimate`` at the fill, leaving its weight in cash.
    """
    dates, bars = listing_market()
    cfg = BacktestConfig(
        strategy=StrategyConfig(min_names=1, rebalance_every=100),
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
        costs=CostModel(adv_window=20, vol_window=20),
    )
    names = ("A", "B", "C", "NEW")
    res = run_backtest(
        bars, signals_on(dates[decision], names), cfg, EqualWeight(), record_decisions=True
    )
    assert ("NEW" in set(res.decisions["instrument"])) is new_eligible
    assert (res.trades["status"] == "filled").all(), res.trades[["instrument", "reason"]]
    fill_day = res.daily.loc[dates[decision + 1]]
    assert fill_day["gross_exposure"] == pytest.approx(1.0, abs=1e-3)


@pytest.mark.parametrize("quantile", [False, True])
def test_a_missing_bar_does_not_block_the_exit_of_a_held_name(quantile):
    """BH-2026-10-09-1: one missing bar left A's trailing ADV incomplete for
    ``adv_window`` sessions, so every sell of A was rejected ``no_liquidity_estimate``
    while the other names were sized on equity that still held A (gross 1.33 > 1.0).
    The exit now uses the bars and daily returns its trailing windows still hold."""
    from invest_evaluation.strategies import QuantileStrategy

    dates = pd.bdate_range("2024-01-01", periods=40)
    rows = [
        [d, name, 10.0, 10.0, 10.0, 10.0, 1e8 * (1 + k)]
        for k, d in enumerate(dates)
        for name in ("A", "B", "C")
    ]
    full = pd.DataFrame(
        rows, columns=["date", "instrument", "open", "high", "low", "close", "volume"]
    )
    gap = dates[15]
    bars = full[~((full["instrument"] == "A") & (full["date"] == gap))]
    signals = full[["date", "instrument"]].rename(columns={"date": "decision_date"})
    signals = signals.assign(score=1.0)
    strategy_cfg = StrategyConfig(
        long_fraction=1.0, short_fraction=0.0, min_names=1, rebalance_every=1
    )
    cfg = BacktestConfig(
        strategy=strategy_cfg,
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
        costs=CostModel(
            commission_bps=0,
            half_spread_bps=0,
            impact_coef=0,
            borrow_bps_annual=0,
            adv_window=5,
            vol_window=2,
        ),
        initial_capital=1000.0,
    )
    strategy = QuantileStrategy(strategy_cfg) if quantile else EqualWeight()
    res = run_backtest(bars, signals, cfg, strategy, record_decisions=True)

    # The gap leaves A's ADV undefined at decisions 15 to 19, so A is ineligible there;
    # eligibility never uses the incomplete windows an exit may use.
    decided = res.decisions[res.decisions["instrument"] == "A"]["decision_date"]
    assert not set(decided) & set(dates[15:20])
    assert dates[20] in set(decided)
    rejected = res.trades[res.trades["status"] == "rejected"]
    assert set(rejected["reason"]) <= {"no_bar_on_fill_date"}, rejected
    assert res.daily["gross_exposure"].max() <= 1.0 + 1e-9
    assert res.daily["cash"].min() >= -1e-9
    # A is ineligible at the gap's decision (no close) and sold at the next open, with
    # the ADV of the bars its window holds at that decision: sessions 11 to 14.
    exit_a = res.trades[(res.trades["instrument"] == "A") & (res.trades["date"] == dates[16])]
    assert len(exit_a) == 1 and exit_a.iloc[0]["status"] == "filled"
    assert exit_a.iloc[0]["shares"] < 0
    adv_in_window = 10.0 * 1e8 * np.mean([1 + k for k in range(11, 15)])
    assert exit_a.iloc[0]["participation"] == pytest.approx(
        abs(exit_a.iloc[0]["notional"]) / adv_in_window
    )


def test_an_exit_after_a_missing_bar_pays_impact_on_the_bars_its_windows_hold():
    """The exit that BH-2026-10-09-1 unblocked prices its impact with the daily returns and
    bars its trailing windows hold at its decision (the gap's session 15), never with an
    older complete window or a later one."""
    dates = pd.bdate_range("2024-01-01", periods=30)
    rows = [
        [d, name, px, px, px, px, 1e6]
        for k, d in enumerate(dates)
        for name, px in (("A", 10.0 + 0.3 * (k % 4) + 0.1 * (k % 7)), ("B", 20.0), ("C", 30.0))
    ]
    full = pd.DataFrame(
        rows, columns=["date", "instrument", "open", "high", "low", "close", "volume"]
    )
    bars = full[~((full["instrument"] == "A") & (full["date"] == dates[15]))]
    signals = full[["date", "instrument"]].rename(columns={"date": "decision_date"})
    signals = signals.assign(score=1.0)
    cost_model = CostModel(
        commission_bps=0,
        half_spread_bps=0,
        impact_coef=0.5,
        borrow_bps_annual=0,
        adv_window=5,
        vol_window=3,
    )
    cfg = BacktestConfig(
        strategy=StrategyConfig(min_names=1, rebalance_every=1),
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
        costs=cost_model,
        initial_capital=1000.0,
    )
    res = run_backtest(bars, signals, cfg, EqualWeight())

    exit_a = res.trades[(res.trades["instrument"] == "A") & (res.trades["date"] == dates[16])]
    assert len(exit_a) == 1 and exit_a.iloc[0]["status"] == "filled"
    assert exit_a.iloc[0]["shares"] < 0
    close_a = bars[bars["instrument"] == "A"].set_index("date")["close"].reindex(dates)
    returns = close_a / close_a.shift(1) - 1
    vol = returns.rolling(3, min_periods=2).std()  # returns 13 and 14
    adv = (close_a * 1e6).rolling(5, min_periods=1).mean()  # bars 11 to 14
    vol_15, adv_15 = vol.iloc[15], adv.iloc[15]
    # An older complete window or a later one would give another cost.
    assert vol_15 != pytest.approx(returns.rolling(3).std().iloc[14])
    assert vol_15 != pytest.approx(vol.iloc[19])
    notional = abs(exit_a.iloc[0]["notional"])
    assert exit_a.iloc[0]["impact"] == pytest.approx(
        notional * 0.5 * vol_15 * np.sqrt(notional / adv_15)
    )


def gapped_market(n_sessions, missing_a, volume=lambda name, k: 1e8, price=lambda name, k: 10.0):
    """A, B and C (by default at a constant price of 10); A has no bar on the sessions in
    ``missing_a``. Signals score every name on every session, including A's missing ones."""
    dates = pd.bdate_range("2024-01-01", periods=n_sessions)
    rows = [
        [d, name, *[price(name, k)] * 4, volume(name, k)]
        for k, d in enumerate(dates)
        for name in ("A", "B", "C")
    ]
    full = pd.DataFrame(
        rows, columns=["date", "instrument", "open", "high", "low", "close", "volume"]
    )
    bars = full[~((full["instrument"] == "A") & full["date"].isin(dates[list(missing_a)]))]
    signals = full[["date", "instrument"]].rename(columns={"date": "decision_date"})
    return dates, bars, signals.assign(score=1.0)


def free_costs(adv_window, vol_window):
    return CostModel(
        commission_bps=0,
        half_spread_bps=0,
        impact_coef=0,
        borrow_bps_annual=0,
        adv_window=adv_window,
        vol_window=vol_window,
    )


@pytest.mark.parametrize(
    ("adv_window", "vol_window", "eligible_again"),
    [(5, 3, 20), (3, 8, 24)],  # the ADV window, then the volatility window, completes last
)
def test_after_a_missing_bar_a_name_is_eligible_once_both_windows_are_complete(
    adv_window, vol_window, eligible_again
):
    """A missing bar at session 15 takes one bar out of the ADV window and two daily returns
    out of the volatility window; A is eligible again only when both windows are complete."""
    dates, bars, signals = gapped_market(40, [15])
    cfg = BacktestConfig(
        strategy=StrategyConfig(min_names=1, rebalance_every=1),
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
        costs=free_costs(adv_window, vol_window),
        initial_capital=1000.0,
    )
    res = run_backtest(bars, signals, cfg, EqualWeight(), record_decisions=True)
    decided = set(res.decisions[res.decisions["instrument"] == "A"]["decision_date"])
    assert not decided & set(dates[15:eligible_again])
    assert dates[eligible_again] in decided


def test_an_exit_decided_after_a_missing_bar_uses_the_bars_its_windows_hold():
    """BH-2026-10-09-1 with weekly decisions: A misses session 16 and is sold at the decision
    on session 20, which has a close but incomplete windows. The sale fills, with its
    participation measured on the four bars the ADV window holds (17 to 20) and its impact
    on the three daily returns the volatility window holds (18 to 20; none spans the gap)."""

    def price(name, k):
        return 10.0 + 0.3 * (k % 4) + 0.1 * (k % 7) if name == "A" else 20.0

    dates, bars, signals = gapped_market(
        40, [16], volume=lambda name, k: 1e8 * (1 + k), price=price
    )
    cfg = BacktestConfig(
        strategy=StrategyConfig(min_names=1, rebalance_every=5),
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
        costs=replace(free_costs(5, 4), impact_coef=0.5),
        initial_capital=1000.0,
    )
    res = run_backtest(bars, signals, cfg, EqualWeight())
    exit_a = res.trades[(res.trades["instrument"] == "A") & (res.trades["date"] == dates[21])]
    assert len(exit_a) == 1 and exit_a.iloc[0]["status"] == "filled"
    assert exit_a.iloc[0]["shares"] < 0
    close_a = pd.Series([price("A", k) for k in range(21)])
    adv_in_window = np.mean([close_a[k] * 1e8 * (1 + k) for k in range(17, 21)])
    vol_in_window = (close_a / close_a.shift(1) - 1)[18:21].std()
    notional = abs(exit_a.iloc[0]["notional"])
    assert exit_a.iloc[0]["participation"] == pytest.approx(notional / adv_in_window)
    assert exit_a.iloc[0]["impact"] == pytest.approx(
        notional * 0.5 * vol_in_window * np.sqrt(notional / adv_in_window)
    )
    # Costs are paid after sizing, so allow a little above 1.0.
    assert res.daily["gross_exposure"].max() <= 1.0 + 1e-3
    assert res.daily["cash"].min() >= -1.0


@pytest.mark.parametrize(
    ("adv_window", "vol_window", "halt_start", "delay", "first_sale"),
    [
        (10, 10, 20, 0, 38),  # the sale waits for two daily returns after the halt (36, 37)
        (2, 20, 30, 0, 36),  # the volatility window still holds returns from before the halt
        (2, 20, 32, 0, 36),  # the last complete ADV, from session 31, is three sessions old
        (5, 5, 30, 0, 36),  # no return after the halt; the volatility from 29 is 6 old
        (5, 5, 29, 1, 39),  # with a delay, sales decided late in the halt fill after it
        (5, 6, 29, 0, 36),  # a halt of `vol_window` sessions: the volatility is 7 old
        (5, 8, 27, 0, 36),  # ... 9 old
        (5, 11, 24, 0, 36),  # ... 12 old
    ],
)
def test_an_exit_after_a_halt_is_capped_by_the_volume_traded_since(
    adv_window, vol_window, halt_start, delay, first_sale
):
    """A has no bars from ``halt_start`` to session 34 (at least ``adv_window`` sessions),
    then trades 1/1000 of its old volume. Its exit is capped by the bars its trailing window
    holds, never by the volume from before the halt (which sold 50 times a session's dollar
    volume)."""
    old, new = 1e8, 1e5
    dates, bars, signals = gapped_market(
        60, range(halt_start, 35), volume=lambda name, k: new if name == "A" and k >= 35 else old
    )
    cfg = BacktestConfig(
        strategy=StrategyConfig(min_names=1, rebalance_every=1),
        execution=ExecutionConfig(delay=delay, max_participation=0.05, min_price=0.0),
        costs=free_costs(adv_window, vol_window),
        initial_capital=3e8,
    )
    res = run_backtest(bars, signals, cfg, EqualWeight())
    after = res.trades[(res.trades["instrument"] == "A") & (res.trades["date"] >= dates[35])]
    fills = after[after["status"] == "filled"]  # sales, then purchases once A is eligible
    assert (fills["shares"] < 0).any()
    assert fills["date"].min() == dates[first_sale]
    session_dollar_volume = 10.0 * new
    assert (fills["notional"].abs() <= 0.05 * session_dollar_volume * (1 + 1e-9)).all(), fills
    assert fills["participation"].to_numpy() == pytest.approx(
        fills["notional"].abs().to_numpy() / session_dollar_volume
    )


def test_an_exit_whose_adv_window_holds_one_bar_still_fills():
    """With ``adv_window`` 2, A's window at the gap's decision (session 15) holds only the bar
    of session 14; the exit fills with that bar's dollar volume as its ADV."""
    dates, bars, signals = gapped_market(40, [15], volume=lambda name, k: 1e8 * (1 + k))
    cfg = BacktestConfig(
        strategy=StrategyConfig(min_names=1, rebalance_every=1),
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
        costs=free_costs(2, 4),
        initial_capital=1000.0,
    )
    res = run_backtest(bars, signals, cfg, EqualWeight())
    exit_a = res.trades[(res.trades["instrument"] == "A") & (res.trades["date"] == dates[16])]
    assert len(exit_a) == 1 and exit_a.iloc[0]["status"] == "filled"
    assert exit_a.iloc[0]["participation"] == pytest.approx(
        abs(exit_a.iloc[0]["notional"]) / (10.0 * 1e8 * 15)
    )


@pytest.mark.parametrize("sale", [False, True])
def test_a_delayed_fill_uses_the_estimates_known_at_its_decision(sale):
    """With ``delay`` 2 a decision on session 25 fills at the open of session 28; its
    participation is measured on the ADV known at the decision, not a later one. A is
    bought there, or, when it was bought at session 10 and loses its score, sold."""
    dates, bars, _ = gapped_market(40, [], volume=lambda name, k: 1e8 * (1 + k))
    cfg = BacktestConfig(
        strategy=StrategyConfig(min_names=1, rebalance_every=15),
        execution=ExecutionConfig(delay=2, max_participation=1.0, min_price=0.0),
        costs=free_costs(5, 4),
        initial_capital=1000.0,
    )
    if sale:
        signals = pd.concat(
            [signals_on(dates[10], ("A", "B", "C")), signals_on(dates[25], ("B", "C"))]
        )
    else:
        signals = signals_on(dates[25], ("A", "B", "C"))
    res = run_backtest(bars, signals, cfg, EqualWeight())
    fill_a = res.trades[(res.trades["instrument"] == "A") & (res.trades["status"] == "filled")]
    assert fill_a["date"].iloc[-1] == dates[28]
    assert bool(fill_a["shares"].iloc[-1] < 0) is sale
    fill_a = fill_a.iloc[[-1]]
    adv_at_decision = 10.0 * 1e8 * np.mean([1 + k for k in range(21, 26)])
    assert fill_a.iloc[0]["participation"] == pytest.approx(
        abs(fill_a.iloc[0]["notional"]) / adv_at_decision
    )


@pytest.mark.parametrize("offset", [0, 1, 2, 3])
@pytest.mark.parametrize(("adv_window", "vol_window"), [(1, 2), (2, 2), (5, 2), (5, 3), (3, 8)])
def test_a_single_missing_bar_never_blocks_the_exit(adv_window, vol_window, offset):
    """BH-2026-10-09-1 for every window size: a window too short to hold a bar or two returns
    without the missing one falls back on its last complete estimate. A misses one session
    and the next weekly decision comes ``offset`` sessions later."""
    _, bars, signals = gapped_market(40, [15 - offset])
    cfg = BacktestConfig(
        strategy=StrategyConfig(min_names=1, rebalance_every=5),
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
        costs=free_costs(adv_window, vol_window),
        initial_capital=1000.0,
    )
    res = run_backtest(bars, signals, cfg, EqualWeight())
    rejected = res.trades[res.trades["status"] == "rejected"]
    assert "no_liquidity_estimate" not in set(rejected["reason"]), rejected
    assert res.daily["gross_exposure"].max() <= 1.0 + 1e-9
    assert res.daily["cash"].min() >= -1e-9


@pytest.mark.parametrize(
    ("adv_window", "vol_window", "halt", "rebalance_every", "decision"),
    [
        (2, 20, [33, 34], 1, 34),  # the ADV window is empty; the last complete ADV is 2 old
        (5, 2, [12, 13], 5, 15),  # one return in the window; the last volatility is 4 old
    ],
)
def test_the_exit_fallback_reaches_back_one_session_for_adv_and_vol_window_plus_one_for_volatility(
    adv_window, vol_window, halt, rebalance_every, decision
):
    """A two-session halt is not a single missing bar: an ADV window that holds no bar after
    it gets no older ADV, so the sale is not sized on the trading before the halt, and a
    volatility window with one return gets no estimate older than ``vol_window`` + 1
    sessions, so the sale decided on ``decision`` is rejected (REVIEW-27)."""
    dates, bars, signals = gapped_market(40, halt)
    cfg = BacktestConfig(
        strategy=StrategyConfig(min_names=1, rebalance_every=rebalance_every),
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
        costs=free_costs(adv_window, vol_window),
        initial_capital=1000.0,
    )
    res = run_backtest(bars, signals, cfg, EqualWeight())
    sale = res.trades[
        (res.trades["instrument"] == "A") & (res.trades["date"] == dates[decision + 1])
    ]
    assert list(sale["status"]) == ["rejected"]
    assert list(sale["reason"]) == ["no_liquidity_estimate"]


@pytest.mark.parametrize(
    ("vol_window", "missing"),
    [
        *((4, missing) for missing in ([32, 34], [31, 33], [31, 34])),
        *((5, missing) for missing in ([32, 34], [31, 33], [31, 34])),
        (3, [32, 34]),  # no return in the window; the volatility from 31 is 4 old
    ],
)
def test_two_missing_bars_a_few_sessions_apart_do_not_block_the_exit(vol_window, missing):
    """Two missing bars two or three sessions apart leave a volatility window of 3 to 5
    returns with fewer than two of them for a few sessions. The exit decided on session 35
    falls back on the volatility from just before the first gap, at most ``vol_window`` + 1
    sessions old, so it fills instead of being rejected while the other targets are sized on
    equity that still holds A (review rounds 8 and 9, R8-1 and R9-2)."""
    dates, bars, signals = gapped_market(40, missing)
    cfg = BacktestConfig(
        strategy=StrategyConfig(min_names=1, rebalance_every=5),
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
        costs=free_costs(5, vol_window),
        initial_capital=1000.0,
    )
    res = run_backtest(bars, signals, cfg, EqualWeight())
    sale = res.trades[(res.trades["instrument"] == "A") & (res.trades["date"] == dates[36])]
    assert list(sale["status"]) == ["filled"], sale
    assert bool(sale["shares"].iloc[0] < 0)
    assert res.daily["gross_exposure"].max() <= 1.0 + 1e-9
    assert res.daily["cash"].min() >= -1e-9
