"""REVIEW-27 / BF-2026-10-26-1: a sale that cannot complete keeps gross within leverage.

A held name whose sale is rejected (zero volume, a halt, no liquidity estimate) or cut by
the participation cap keeps value the strategy wanted sold. The other targets used to be
sized on equity that still held it, so gross exposure exceeded ``gross_leverage`` and cash
went negative. Every target is now sized on equity net of the value that cannot be sold,
at the configured leverage: ``E' = (E - P / L) / (1 - W / L)``, where ``P`` is what the
names short of their sale hold after the session's fills and ``W`` their target weights on
the side they still hold (for exits ``W`` is 0, so with ``L`` 1 it is ``E - P``). Every
expected value below is worked out by hand from the stated prices (10 unless a test says
otherwise) and zero costs.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable

import pandas as pd
import pytest

from invest_evaluation.config import BacktestConfig, CostModel, ExecutionConfig, StrategyConfig
from invest_evaluation.engine import BacktestResult, run_backtest

DATES = pd.bdate_range("2024-01-01", periods=40)
COLUMNS = ["date", "instrument", "open", "high", "low", "close", "volume"]


class EqualWeight:
    """Long every eligible name equally, ``gross`` in total."""

    def __init__(self, gross: float = 1.0) -> None:
        self.gross = gross

    def target_weights(self, scores: pd.Series) -> pd.Series:
        if not len(scores):
            return scores
        return pd.Series(self.gross / len(scores), index=scores.index)


class BySign:
    """Equal absolute weights summing to ``gross``, long a positive score, short a negative."""

    def __init__(self, gross: float = 1.0) -> None:
        self.gross = gross

    def target_weights(self, scores: pd.Series) -> pd.Series:
        if not len(scores):
            return scores
        return (scores > 0).map({True: 1.0, False: -1.0}) * (self.gross / len(scores))


class Sides:
    """Equal absolute weights summing to ``gross``, long or short by a fixed side."""

    def __init__(self, sides: dict[str, float], gross: float) -> None:
        self.sides = sides
        self.gross = gross

    def target_weights(self, scores: pd.Series) -> pd.Series:
        if not len(scores):
            return scores
        size = self.gross / len(scores)
        return pd.Series([self.sides[n] * size for n in scores.index], index=scores.index)


def market(
    names: str = "ABC",
    volume: Callable[[int, str], float] = lambda k, n: 1e9,
    missing: Callable[[int, str], bool] = lambda k, n: False,
    close: Callable[[int, str], float] = lambda k, n: 10.0,
    open_: Callable[[int, str], float] = lambda k, n: 10.0,
) -> pd.DataFrame:
    """Bars at 10 unless ``open_`` or ``close`` say otherwise (high and low span both)."""
    rows = []
    for k, d in enumerate(DATES):
        for n in names:
            if missing(k, n):
                continue
            o, c = open_(k, n), close(k, n)
            rows.append([d, n, o, max(o, c), min(o, c), c, volume(k, n)])
    return pd.DataFrame(rows, columns=COLUMNS)


def scores(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars[["date", "instrument"]].rename(columns={"date": "decision_date"})
    return out.assign(score=1.0).reset_index(drop=True)


def config(
    *,
    capital: float = 1000.0,
    cap: float = 1.0,
    every: int = 1,
    gross: float = 1.0,
    adv_window: int = 5,
    vol_window: int = 2,
) -> BacktestConfig:
    return BacktestConfig(
        strategy=StrategyConfig(rebalance_every=every, min_names=1, gross_leverage=gross),
        execution=ExecutionConfig(max_participation=cap, min_price=0.0),
        costs=CostModel(
            commission_bps=0,
            half_spread_bps=0,
            impact_coef=0,
            borrow_bps_annual=0,
            adv_window=adv_window,
            vol_window=vol_window,
        ),
        initial_capital=capital,
    )


def held(result: BacktestResult, name: str, through: int) -> float:
    """Shares of ``name`` after the fills of session ``through``."""
    fills = result.trades[
        (result.trades["instrument"] == name)
        & (result.trades["status"] == "filled")
        & (result.trades["date"] <= DATES[through])
    ]
    return float(fills["shares"].sum())


def within_leverage(result: BacktestResult, gross: float = 1.0) -> None:
    assert result.daily["gross_exposure"].max() <= gross + 1e-9
    assert result.daily["cash"].min() >= -1e-9


def test_a_rejected_exit_after_zero_volume_keeps_the_others_at_their_size() -> None:
    """A trades nothing on sessions 15 to 24, so its ADV is 0 at decisions 19 to 24 and its
    exit is rejected six times. The other two are sized on 1000 - 333.33 and keep 33.33
    shares each instead of buying up to 50 (gross 1.33 and cash -333 before the fix)."""
    bars = market(volume=lambda k, n: 0.0 if n == "A" and 15 <= k <= 24 else 1e9)
    res = run_backtest(bars, scores(bars), config(), EqualWeight())
    rejected = res.trades[res.trades["status"] == "rejected"]
    assert list(rejected["reason"]) == ["no_liquidity_estimate"] * 6
    within_leverage(res)
    for k in range(20, 26):
        assert held(res, "B", k) == pytest.approx(1000 / 3 / 10)
        assert held(res, "C", k) == pytest.approx(1000 / 3 / 10)
    assert held(res, "A", 25) == pytest.approx(1000 / 3 / 10)
    assert any("REVIEW-27" in w and w.startswith("6 ") for w in res.warnings), res.warnings


def test_a_halted_exit_keeps_the_others_at_their_size() -> None:
    """A has no bars on sessions 15 to 24: its exit is rejected for want of a bar, then of
    a volatility estimate, while it keeps its last mark of 10."""
    bars = market(missing=lambda k, n: n == "A" and 15 <= k <= 24)
    res = run_backtest(bars, scores(bars), config(), EqualWeight())
    reasons = set(res.trades.loc[res.trades["status"] == "rejected", "reason"])
    assert reasons == {"no_bar_on_fill_date", "no_liquidity_estimate"}
    within_leverage(res)
    assert held(res, "B", 20) == pytest.approx(1000 / 3 / 10)
    assert held(res, "C", 24) == pytest.approx(1000 / 3 / 10)


def test_a_capped_exit_sizes_the_others_on_equity_net_of_what_it_still_holds() -> None:
    """A trades $10k a day and the cap is 10%, so it moves 100 shares a session. Bought to
    1000 shares (a third of 30000), it loses its score from session 20 and sells 100 shares
    a session from session 21. On session 21 A still holds 900 shares (9000), so B and C are
    sized on 30000 - 9000: 10500 each, 1050 shares; then 1100, 1150, ..., and 1500 once A is
    gone (session 30). Before the fix they bought 1500 shares at once (gross 1.30)."""
    bars = market(volume=lambda k, n: 1000.0 if n == "A" else 1e9)
    signals = scores(bars)
    signals = signals[~((signals["instrument"] == "A") & (signals["decision_date"] >= DATES[20]))]
    res = run_backtest(bars, signals, config(capital=30000.0, cap=0.1), EqualWeight())
    within_leverage(res)
    assert held(res, "A", 20) == pytest.approx(1000.0)
    for k in range(21, 31):
        a_left = 1000.0 - 100.0 * (k - 20)
        assert held(res, "A", k) == pytest.approx(a_left)
        assert held(res, "B", k) == pytest.approx((30000.0 - 10.0 * a_left) / 2 / 10)
    assert held(res, "C", 30) == pytest.approx(1500.0)


def test_two_close_gaps_with_a_short_volatility_window_keep_the_others_at_their_size() -> None:
    """Weekly decisions on sessions 3, 8, 13, 18, ...; A misses sessions 15 and 17, so with
    ``vol_window`` 2 its exit decided on session 18 has no volatility estimate and is
    rejected. B and C keep a third each (they bought up to half before the fix), and at
    decision 23 A is eligible again, so all three stay at a third."""
    bars = market(missing=lambda k, n: n == "A" and k in (15, 17))
    signals = scores(bars)
    signals = signals[signals["decision_date"] >= DATES[3]]
    res = run_backtest(bars, signals, config(every=5), EqualWeight())
    rejected = res.trades[res.trades["status"] == "rejected"]
    assert list(rejected["reason"]) == ["no_liquidity_estimate"]
    within_leverage(res)
    for k in range(19, 25):
        assert held(res, "B", k) == pytest.approx(1000 / 3 / 10)
    assert held(res, "A", 24) == pytest.approx(1000 / 3 / 10)


def test_a_capped_trim_sizes_every_target_on_equity_net_of_the_excess() -> None:
    """A and B hold half each until C has two daily returns (decision 17); then each target
    is a third. A's volume falls to 50 on session 17, so the cap (10% of a $500 ADV, 5
    shares) cuts its trim from 50 to 45 shares (450). The value that cannot be sold is
    A's excess over its own target on the same sizing equity: E' = 1000 - (450 - E' / 3),
    so E' = 825 and B and C hold 27.5 shares each; gross is 450 + 2 * 275 = 1000.
    Counting only the excess over a target on the full equity (450 - 333.33) would size B
    and C on 883.33 and break the limit (gross 1.04); before the fix gross was 1.12."""
    bars = market(
        volume=lambda k, n: 50.0 if n == "A" and k >= 17 else 1e9,
        missing=lambda k, n: n == "C" and k < 15,
    )
    res = run_backtest(bars, scores(bars), config(cap=0.1, adv_window=1), EqualWeight())
    within_leverage(res)
    assert held(res, "A", 17) == pytest.approx(50.0)
    assert held(res, "A", 18) == pytest.approx(45.0)
    assert held(res, "B", 18) == pytest.approx(27.5)
    assert held(res, "C", 18) == pytest.approx(27.5)
    # Session 19: A at 40 shares, E' = (1000 - 400) / (2 / 3) = 900, so 30 shares each.
    assert held(res, "B", 19) == pytest.approx(30.0)


def test_leverage_below_one_counts_the_unsold_value_at_the_configured_leverage() -> None:
    """``gross_leverage`` 0.5: each name holds a sixth (166.67). A's exit is rejected from
    session 20, so the others are sized on 1000 - 166.67 / 0.5 = 666.67 and keep a sixth
    of 1000 each (gross 0.5). Equity minus the unsold value alone (833.33) would give
    gross 0.583; before the fix it was 0.667."""
    bars = market(volume=lambda k, n: 0.0 if n == "A" and 15 <= k <= 24 else 1e9)
    res = run_backtest(bars, scores(bars), config(gross=0.5), EqualWeight(gross=0.5))
    within_leverage(res, 0.5)
    assert held(res, "B", 22) == pytest.approx(1000 / 6 / 10)


def test_a_long_short_book_with_a_stuck_long_stays_within_its_leverage() -> None:
    """``gross_leverage`` 2: A and B long, C and D short, half each. A's exit is rejected
    from session 20, so B, C and D are sized on 1000 - 500 / 2 = 750 with two thirds each:
    500 (50 shares) long or short, and gross 500 + 3 * 500 = 2000. Before the fix they took
    666.67 each (gross 2.5)."""
    names = "ABCD"
    bars = market(names, volume=lambda k, n: 0.0 if n == "A" and 15 <= k <= 24 else 1e9)
    strategy = Sides({"A": 1.0, "B": 1.0, "C": -1.0, "D": -1.0}, gross=2.0)
    res = run_backtest(bars, scores(bars), config(gross=2.0), strategy)
    within_leverage(res, 2.0)
    assert held(res, "B", 22) == pytest.approx(50.0)
    assert held(res, "D", 22) == pytest.approx(-50.0)


def test_unsold_value_above_the_leverage_sells_everything_else() -> None:
    """``gross_leverage`` 0.5. A opens at 10 and closes at 100 on session 20 (16.67 shares,
    worth 1666.67 of equity 2500) and is halted from session 21, so its trim to a sixth
    is rejected. No sizing equity can keep gross within 0.5 then (A alone is 0.67): the
    others' targets are sized on zero, so B and C are sold and gross is A's 1666.67 / 2500."""
    bars = market(
        missing=lambda k, n: n == "A" and k >= 21,
        close=lambda k, n: 100.0 if n == "A" and k == 20 else 10.0,
    )
    res = run_backtest(bars, scores(bars), config(gross=0.5), EqualWeight(gross=0.5))
    assert held(res, "B", 20) == pytest.approx(1000 / 6 / 10)
    assert held(res, "B", 21) == pytest.approx(0.0)
    assert held(res, "C", 21) == pytest.approx(0.0)
    a_value = 1000 / 6 / 10 * 100
    assert res.daily.loc[DATES[21], "gross_exposure"] == pytest.approx(a_value / 2500)


def test_orders_that_fill_in_full_are_sized_on_the_full_open_equity() -> None:
    """Nothing is stuck, so nothing changes: each name gets a third of 1000 at 10, exactly
    the old sizing, and no warning names REVIEW-27."""
    bars = market()
    res = run_backtest(bars, scores(bars), config(), EqualWeight())
    assert (res.trades["status"] == "filled").all()
    assert held(res, "A", 39) == (1.0 / 3) * 1000.0 / 10.0
    assert not any("REVIEW-27" in w for w in res.warnings)


def test_a_rejected_exit_with_a_one_session_delay_keeps_the_others_at_their_size() -> None:
    """The zero-volume shape with ``delay`` 1: the exits decided on sessions 19 to 24 fill
    (and are rejected) on sessions 21 to 26, while B and C keep a third each."""
    bars = market(volume=lambda k, n: 0.0 if n == "A" and 15 <= k <= 24 else 1e9)
    cfg = config()
    cfg = BacktestConfig(
        strategy=cfg.strategy,
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0, delay=1),
        costs=cfg.costs,
        initial_capital=cfg.initial_capital,
    )
    res = run_backtest(bars, scores(bars), cfg, EqualWeight())
    rejected = res.trades[res.trades["status"] == "rejected"]
    assert list(rejected["date"]) == list(DATES[21:27])
    within_leverage(res)
    for k in range(21, 27):
        assert held(res, "B", k) == pytest.approx(1000 / 3 / 10)


def test_a_rejected_buy_back_of_a_short_counts_the_whole_short() -> None:
    """A is short a third (B and C long a third each, gross 1). A trades nothing on
    sessions 15 to 24, so its buy-back is rejected from session 20; the short of 333.33
    cannot be closed, so B and C are sized on 1000 - 333.33 and keep a third each (they
    bought up to half before the fix, gross 1.33)."""
    bars = market(volume=lambda k, n: 0.0 if n == "A" and 15 <= k <= 24 else 1e9)
    signals = scores(bars)
    signals["score"] = signals["instrument"].map({"A": -1.0, "B": 1.0, "C": 1.0})
    res = run_backtest(bars, signals, config(), BySign())
    within_leverage(res)
    assert held(res, "A", 22) == pytest.approx(-1000 / 3 / 10)
    assert held(res, "B", 22) == pytest.approx(1000 / 3 / 10)


def test_a_reversal_the_cap_stops_before_zero_counts_the_whole_remainder() -> None:
    """A is long half and turns short at decision 20; it trades $3000 a day, so the 10% cap
    moves 30 shares a session. On session 21 it sells 30 of its 50 shares and is still long
    20 (200), none of which its short target wants, so B is sized on 1000 - 200 = 800 and
    holds 40 shares (gross 0.6; 0.7 before the fix, within the limit either way). On
    session 22 A crosses to 10 shares short, below its target's size, so B is back at 50."""
    bars = market(volume=lambda k, n: 300.0 if n == "A" else 1e9, names="AB")
    signals = scores(bars)
    flip = (signals["instrument"] == "A") & (signals["decision_date"] >= DATES[20])
    signals.loc[flip, "score"] = -1.0
    res = run_backtest(bars, signals, config(cap=0.1), BySign())
    assert held(res, "A", 20) == pytest.approx(50.0)
    assert held(res, "A", 21) == pytest.approx(20.0)
    assert held(res, "B", 21) == pytest.approx(40.0)
    assert held(res, "A", 22) == pytest.approx(-10.0)
    assert held(res, "B", 22) == pytest.approx(50.0)
    within_leverage(res)


def test_a_rejected_top_up_changes_nothing() -> None:
    """A, B and C hold a third each; C loses its score at decision 20, so A and B should go
    to half. A has no bar on session 21, so its top-up is rejected, but it holds less than
    its target: nothing is short of a sale, B goes to half on the full equity as before,
    and gross is 0.83 on session 21."""
    bars = market(missing=lambda k, n: n == "A" and k == 21)
    signals = scores(bars)
    signals = signals[~((signals["instrument"] == "C") & (signals["decision_date"] >= DATES[20]))]
    res = run_backtest(bars, signals, config(), EqualWeight())
    assert held(res, "A", 21) == pytest.approx(1000 / 3 / 10)
    assert held(res, "B", 21) == pytest.approx(50.0)
    assert held(res, "C", 21) == pytest.approx(0.0)
    assert res.daily.loc[DATES[21], "gross_exposure"] == pytest.approx((1000 / 3 + 500) / 1000)
    assert not any("REVIEW-27" in w for w in res.warnings)


def test_leverage_above_one_when_the_stuck_targets_weigh_one() -> None:
    """``gross_leverage`` 2: A and B long, C and D short, half each (50 shares). On session
    20 A and B close at 12 and C and D at 11; A and B then have no bar on session 21, while
    C and D open at 11. Equity at that open is 1000 + 1200 - 1100 = 1100, so A and B (600
    each) should trim to 550 but cannot. They are short of their sale with targets of
    weight 1 in all: E' = (1100 - 1200 / 2) / (1 - 1 / 2) = 1000, so C and D go to 500
    short (45.45 shares) and gross is 1200 + 1000 = 2200, twice the equity. Equity minus
    the value that cannot be sold, E - (1200 - E'), has no solution here; before the fix
    C and D stayed at 550 (gross 2.09)."""
    names = "ABCD"
    rise = {"A": 12.0, "B": 12.0, "C": 11.0, "D": 11.0}
    bars = market(
        names,
        missing=lambda k, n: n in "AB" and k == 21,
        close=lambda k, n: rise[n] if k >= 20 else 10.0,
        open_=lambda k, n: rise[n] if k >= 21 else 10.0,
    )
    strategy = Sides({"A": 1.0, "B": 1.0, "C": -1.0, "D": -1.0}, gross=2.0)
    res = run_backtest(bars, scores(bars), config(gross=2.0), strategy)
    assert held(res, "A", 21) == pytest.approx(50.0)
    assert held(res, "C", 21) == pytest.approx(-500 / 11)
    assert held(res, "D", 21) == pytest.approx(-500 / 11)
    assert res.daily.loc[DATES[21], "gross_exposure"] == pytest.approx(2.0)


class Weights:
    """The scores are the target weights."""

    def target_weights(self, scores: pd.Series) -> pd.Series:
        return scores


def test_a_trim_the_cap_cuts_only_on_the_reduced_equity_is_counted_too() -> None:
    """A holds 0.3, B 0.6 and C 0.1 of 1000 (B trades $1100 a day, so the 10% cap moves 11
    shares a session). At decision 15 A drops out and B and C go to half. A has no bar on
    session 16, so its exit is rejected and it keeps 300. On 1000 - 300 = 700, B's target is
    350, a sale of 250 that the cap cuts to 110: B keeps 490, beyond its target too. With both
    short of their sale, E' = (1000 - (300 + 490)) / (1 - 0.5) = 420, B's sale stays capped,
    and C is bought to 210 (21 shares): gross 300 + 490 + 210 = 1000. Sizing once on 700
    would buy C to 350 (gross 1.14); before the fix B sold to 50 shares and C bought to 50
    (gross 1.3)."""
    bars = market(
        volume=lambda k, n: 110.0 if n == "B" else 1e9,
        missing=lambda k, n: n == "A" and k == 16,
    )
    signals = scores(bars)
    early = signals["decision_date"] < DATES[15]
    signals["score"] = signals["instrument"].map({"A": 0.3, "B": 0.6, "C": 0.1})
    signals.loc[~early, "score"] = 0.5
    signals = signals[early | (signals["instrument"] != "A")]
    res = run_backtest(bars, signals, config(cap=0.1), Weights())
    assert held(res, "A", 15) == pytest.approx(30.0)
    assert held(res, "B", 15) == pytest.approx(60.0)
    assert held(res, "C", 15) == pytest.approx(10.0)
    assert held(res, "A", 16) == pytest.approx(30.0)
    assert held(res, "B", 16) == pytest.approx(49.0)
    assert held(res, "C", 16) == pytest.approx(21.0)
    assert res.daily.loc[DATES[16], "gross_exposure"] == pytest.approx(1.0)
    within_leverage(res)


def test_every_target_stuck_sizes_on_zero_without_dividing_by_zero() -> None:
    """A long and B short a half each (50 shares). Both close at 12 on session 20, so each
    is worth 600 of equity 1000 and should trim to 500, and both have no bar on session 21.
    Their targets weigh 1, the whole leverage, so ``1 - W / L`` is 0: the sizing equity is
    0 instead of a division by zero, nothing else has weight, and the two keep their 50
    shares (gross 1200 / 1000). C, never scored, keeps session 21 on the calendar. Without
    the guard, numpy's division by zero would warn and give an infinite sizing equity."""
    bars = market(
        missing=lambda k, n: n in "AB" and k == 21,
        close=lambda k, n: 12.0 if n in "AB" and k >= 20 else 10.0,
        open_=lambda k, n: 12.0 if n in "AB" and k >= 21 else 10.0,
    )
    signals = scores(bars)
    signals = signals[signals["instrument"] != "C"]
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        res = run_backtest(bars, signals, config(), Sides({"A": 1.0, "B": -1.0}, gross=1.0))
    assert held(res, "A", 21) == pytest.approx(50.0)
    assert held(res, "B", 21) == pytest.approx(-50.0)
    assert res.daily.loc[DATES[21], "gross_exposure"] == pytest.approx(1.2)
    assert any("REVIEW-27" in w for w in res.warnings), res.warnings


def test_a_top_up_that_turns_into_a_stuck_trim_on_the_net_equity_is_counted() -> None:
    """A's exit is rejected from session 20 (zero volume). B closes at 12 on session 19 and
    has no bar on session 20, so it is worth 400 at its last mark; equity at that open is
    333.33 + 400 + 333.33 = 1066.67 and B and C target a half. On the full equity B's
    rejected order is a top-up (533.33 > 400); on E' = 1066.67 - 333.33 = 733.33 it is a
    trim (366.67 < 400), so B is short of its sale too: E' = (1066.67 - 733.33) / (1 - 0.5)
    = 666.67 and C keeps its 33.33 shares (gross 1). Stopping after the first pass gives C
    36.67 shares (gross 1.03); before the fix C bought 53.33 (gross 1.19)."""
    bars = market(
        volume=lambda k, n: 0.0 if n == "A" and 15 <= k <= 24 else 1e9,
        missing=lambda k, n: n == "B" and k == 20,
        close=lambda k, n: 12.0 if n == "B" and k >= 19 else 10.0,
        open_=lambda k, n: 12.0 if n == "B" and k >= 21 else 10.0,
    )
    res = run_backtest(bars, scores(bars), config(), EqualWeight())
    assert held(res, "C", 20) == pytest.approx(1000 / 3 / 10)
    assert res.daily.loc[DATES[20], "gross_exposure"] == pytest.approx(1.0)
    assert res.daily.loc[DATES[20], "cash"] >= -1e-9


def test_full_fills_at_an_equity_far_below_the_book_are_not_net_sized() -> None:
    """``gross_leverage`` 2: A long and B short 100 shares at 10. B opens and closes at
    20 - 1e-7 from session 21, so equity at that open is 1000 + 1000 - 100 * (20 - 1e-7)
    = 1e-5 while each leg is worth about 1000. Every order fills in full (no cap, ample
    volume), so A and B go to their targets on that equity and gross is 2, as before the
    fix. Counting the rounding of a full fill (about 1e-16 of a 1000 holding, above the
    1e-9 tolerance of a 1e-5 equity) as a sale that could not complete sized both on 0."""
    tiny = 20.0 - 1e-7
    bars = market(
        "AB",
        close=lambda k, n: tiny if n == "B" and k >= 21 else 10.0,
        open_=lambda k, n: tiny if n == "B" and k >= 21 else 10.0,
    )
    strategy = Sides({"A": 1.0, "B": -1.0}, gross=2.0)
    res = run_backtest(bars, scores(bars), config(gross=2.0), strategy)
    assert (res.trades["status"] == "filled").all()
    assert held(res, "A", 20) == pytest.approx(100.0)
    assert res.daily.loc[DATES[21], "equity"] == pytest.approx(1e-5, rel=1e-6)
    assert res.daily.loc[DATES[21], "gross_exposure"] == pytest.approx(2.0, rel=1e-6)
    assert not any("REVIEW-27" in w for w in res.warnings)
