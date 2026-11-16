"""The universe equal-weight benchmark applies delisting settlements (BH-2026-10-21-2).

Expected values are hand calculations from the fixture's prices: on each session the
benchmark is the mean return of the names that were members at the previous close and have
a return; a settled member returns its settlement price over its last close before the
event's session, minus 1 (the move the holdings book), and has no return after the event.
"""

import pandas as pd
import pytest

from invest_evaluation.config import BacktestConfig, CostModel, ExecutionConfig, StrategyConfig
from invest_evaluation.engine import BacktestResult, run_backtest
from invest_evaluation.metrics import compute_metrics

DATES = pd.bdate_range("2024-01-01", periods=25)
B_UP = 0.01  # B rises 1% a session; C stays at 30


class Fixed:
    """Strategy returning fixed weights regardless of scores."""

    def __init__(self, weights: dict[str, float]) -> None:
        self.weights = pd.Series(weights, dtype=float)

    def target_weights(self, scores: pd.Series) -> pd.Series:
        return self.weights


def market(a_closes: dict[int, float], b_up: float = B_UP) -> pd.DataFrame:
    """Bars for A (only on the sessions in ``a_closes``), B and C on every session."""
    rows: list[list[object]] = []
    for k, d in enumerate(DATES):
        if k in a_closes:
            rows.append([d, "A", a_closes[k], a_closes[k], a_closes[k], a_closes[k], 1e8])
        b = 20.0 * (1 + b_up) ** k
        rows.append([d, "B", b, b, b, b, 1e8])
        rows.append([d, "C", 30.0, 30.0, 30.0, 30.0, 1e8])
    return pd.DataFrame(
        rows, columns=["date", "instrument", "open", "high", "low", "close", "volume"]
    )


def config(start: str | None = None) -> BacktestConfig:
    return BacktestConfig(
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
        start=start,
    )


def settle(*events: tuple[str, int, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"date": DATES[k], "instrument": name, "settlement_price": p} for name, k, p in events]
    )


def run(
    bars: pd.DataFrame,
    delistings: pd.DataFrame,
    universe: pd.DataFrame | None = None,
    cfg: BacktestConfig | None = None,
    weights: dict[str, float] | None = None,
    decision: int = 2,
) -> BacktestResult:
    """Hold ``weights`` (a third each of A, B and C by default) from one decision on."""
    weights = weights or {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}
    signals = pd.DataFrame(
        {"decision_date": DATES[decision], "instrument": list(weights), "score": 1.0}
    )
    return run_backtest(
        bars, signals, cfg or config(), Fixed(weights), delistings=delistings, universe=universe
    )


def test_a_member_settled_on_its_last_bar_returns_settlement_over_previous_close() -> None:
    # A closes at 10 through session 4 and is settled at 0 at that close.
    res = run(market({k: 10.0 for k in range(5)}), settle(("A", 4, 0.0)))
    assert res.benchmark.loc[DATES[4]] == pytest.approx((-1.0 + B_UP + 0.0) / 3)
    assert res.benchmark.loc[DATES[5]] == pytest.approx((B_UP + 0.0) / 2)


def test_a_settled_member_the_strategy_does_not_hold_counts_the_same() -> None:
    # The benchmark does not depend on the holdings: only B and C are held. A's last bar is
    # session 3 (close 10); its settlement at 8 is known on session 6.
    weights = {"B": 0.5, "C": 0.5}
    res = run(market({k: 10.0 for k in range(4)}), settle(("A", 6, 8.0)), weights=weights)
    assert res.benchmark.loc[DATES[6]] == pytest.approx((8.0 / 10.0 - 1.0 + B_UP + 0.0) / 3)


def test_a_settlement_after_the_last_bar_spans_the_missing_bars_like_the_holdings() -> None:
    # A's last bar is session 3 (close 10, after 9, 9.5 and 9); the settlement at 8 is known
    # at session 6's close. Its return is 8 / 10 - 1, from the last close, not an earlier one.
    res = run(market({0: 9.0, 1: 9.5, 2: 9.0, 3: 10.0}), settle(("A", 6, 8.0)))
    for k in (4, 5):  # no bar for A: the mean of B and C, as before
        assert res.benchmark.loc[DATES[k]] == pytest.approx((B_UP + 0.0) / 2)
    assert res.benchmark.loc[DATES[6]] == pytest.approx((8.0 / 10.0 - 1.0 + B_UP + 0.0) / 3)
    # The holdings book the same move on that session: the sale at 8 from a mark of 10.
    liquidation = res.trades[res.trades["reason"] == "delisted_liquidation"]
    assert liquidation["date"].tolist() == [DATES[6]]
    assert liquidation["price"].tolist() == [8.0]


def test_a_universe_that_ends_at_the_last_bar_still_books_the_later_settlement() -> None:
    # A is a member through its last bar (session 3) and leaves on session 4; the settlement
    # at 8 is known on session 6. The benchmark could not sell A in between, so it counts.
    universe = pd.DataFrame(
        {
            "universe": ["U", "U", "U"],
            "instrument": ["A", "B", "C"],
            "start_date": [DATES[0]] * 3,
            "end_date": [DATES[4], pd.NaT, pd.NaT],
        }
    )
    res = run(market({k: 10.0 for k in range(4)}), settle(("A", 6, 8.0)), universe=universe)
    assert res.benchmark.loc[DATES[6]] == pytest.approx((8.0 / 10.0 - 1.0 + B_UP + 0.0) / 3)
    # A name that joins the universe only during the gap (session 5) was not a member at its
    # last close, so its settlement does not count.
    universe.loc[0, ["start_date", "end_date"]] = [DATES[5], pd.NaT]
    joined = run(
        market({k: 10.0 for k in range(4)}),
        settle(("A", 6, 8.0)),
        universe=universe,
        weights={"B": 0.5, "C": 0.5},
    )
    assert joined.benchmark.loc[DATES[6]] == pytest.approx((B_UP + 0.0) / 2)


def test_an_insolvent_open_on_the_event_session_keeps_the_settlement_in_the_benchmark() -> None:
    """The run stops at the open of session 6 (short B gaps from 20 to 100), so the
    holdings never apply A's settlement at that close, but the benchmark is close to close
    and still counts it (the stop row's own mismatch is BF-2026-11-02-1)."""
    bars = market({k: 10.0 for k in range(6)}, b_up=0.0)
    late_b = (bars["instrument"] == "B") & (bars["date"] >= DATES[6])
    bars.loc[late_b, ["open", "high", "low", "close"]] = 100.0
    res = run(bars, settle(("A", 6, 0.0)), weights={"C": 0.5, "B": -0.5})
    assert any(w.startswith("insolvent at the open") for w in res.warnings)
    assert res.daily.index[-1] == DATES[6]
    assert res.benchmark.loc[DATES[6]] == pytest.approx((-1.0 + (100.0 / 20.0 - 1.0) + 0.0) / 3)


def test_the_event_session_close_is_passed_through_and_later_bars_are_left_out() -> None:
    # A closes at 12 on its event session 4 (10 before) and is settled at 5 there; the data
    # keeps bars for it, doubling to 20 on session 6. Its return is 5 / 10 - 1, not 5 / 12.
    closes = {k: 10.0 if k < 4 else 12.0 if k < 6 else 20.0 for k in range(25)}
    res = run(market(closes), settle(("A", 4, 5.0)))
    assert res.benchmark.loc[DATES[4]] == pytest.approx((5.0 / 10.0 - 1.0 + B_UP) / 3)
    for k in range(5, 25):
        assert res.benchmark.loc[DATES[k]] == pytest.approx((B_UP + 0.0) / 2)


def test_a_settlement_before_the_window_leaves_the_member_out_of_it() -> None:
    closes = {k: 10.0 * 1.1**k for k in range(25)}  # A rises 10% a session after it
    res = run(
        market(closes),
        settle(("A", 0, 10.0)),
        cfg=config(start=str(DATES[5].date())),
        weights={"B": 0.5, "C": 0.5},
        decision=5,
    )
    assert res.benchmark.index[0] == DATES[5]
    assert res.benchmark.notna().all()
    assert (res.benchmark - (B_UP + 0.0) / 2).abs().max() == pytest.approx(0.0, abs=1e-12)


def test_a_settlement_on_the_first_evaluation_session_counts_from_the_close_before() -> None:
    res = run(
        market({k: 10.0 for k in range(6)}),
        settle(("A", 5, 0.0)),
        cfg=config(start=str(DATES[5].date())),
        weights={"B": 0.5, "C": 0.5},
        decision=5,
    )
    assert res.benchmark.index[0] == DATES[5]
    assert res.benchmark.loc[DATES[5]] == pytest.approx((-1.0 + B_UP + 0.0) / 3)


def test_a_member_at_its_last_close_counts_and_a_non_member_does_not() -> None:
    universe = pd.DataFrame(
        {
            "universe": ["U", "U", "U"],
            "instrument": ["A", "B", "C"],
            "start_date": [DATES[0]] * 3,
            "end_date": [DATES[4], pd.NaT, pd.NaT],  # A leaves on session 4, its event session
        }
    )
    left = run(market({k: 10.0 for k in range(5)}), settle(("A", 4, 0.0)), universe=universe)
    assert left.benchmark.loc[DATES[4]] == pytest.approx((-1.0 + B_UP + 0.0) / 3)
    universe.loc[0, "end_date"] = DATES[3]  # not a member at session 3's close
    gone = run(market({k: 10.0 for k in range(5)}), settle(("A", 4, 0.0)), universe=universe)
    assert gone.benchmark.loc[DATES[4]] == pytest.approx((B_UP + 0.0) / 2)


def test_two_settlements_on_one_session_and_one_without_an_earlier_close() -> None:
    # A settles at 4 on session 4 (last close 10); C at 0 on session 4 too. D has no bar
    # before its event on session 2, so it has no return there and none after it.
    bars = market({k: 10.0 for k in range(5)})
    bars = bars[~((bars["instrument"] == "C") & (bars["date"] > DATES[4]))]
    d_rows = pd.DataFrame(
        [[DATES[k], "D", 40.0, 40.0, 40.0, 40.0, 1e8] for k in range(6, 25)],
        columns=bars.columns,
    )
    bars = pd.concat([bars, d_rows], ignore_index=True)
    events = settle(("A", 4, 4.0), ("C", 4, 0.0), ("D", 2, 1.0))
    res = run(bars, events)
    assert res.benchmark.loc[DATES[2]] == pytest.approx((0.0 + B_UP + 0.0) / 3)
    assert res.benchmark.loc[DATES[4]] == pytest.approx((4.0 / 10.0 - 1.0 + B_UP - 1.0) / 3)
    assert res.benchmark.loc[DATES[7]] == pytest.approx(B_UP)  # only B is left


def test_the_equal_weight_universe_and_its_benchmark_lose_the_same_third() -> None:
    """The hunt's case: A, B and C held at a third each, A settled at 0 on its last bar."""
    res = run(market({k: 10.0 for k in range(5)}, b_up=0.0), settle(("A", 4, 0.0)))
    assert res.returns.loc[DATES[4]] == pytest.approx(-1 / 3)
    assert res.benchmark.loc[DATES[4]] == pytest.approx(-1 / 3)
    bench = compute_metrics(res)["benchmark"]
    assert bench["benchmark_total_return"]["value"] == pytest.approx(-1 / 3)
