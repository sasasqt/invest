"""Scheduled decisions on sessions without scores (BH-2026-10-09-2, BH-2026-10-15-4).

The market is three names at constant prices with ample volume and no costs, so every
expected value below follows from the decision rule alone: a decision is due every
``rebalance_every`` sessions counted from the last decision made; a due session that has
no score keeps the holdings and the decision is made on the next session with a score.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from invest_evaluation.config import BacktestConfig, CostModel, ExecutionConfig, StrategyConfig
from invest_evaluation.engine import InputError, run_backtest
from invest_evaluation.quantiles import QuantileConfig, run_quantile_portfolios

DATES = pd.bdate_range("2024-01-01", periods=30)
PRICES = {"A": 10.0, "B": 20.0, "C": 40.0}


def flat_market() -> pd.DataFrame:
    rows = [[d, name, px, px, px, px, 1e9] for d in DATES for name, px in PRICES.items()]
    return pd.DataFrame(
        rows, columns=["date", "instrument", "open", "high", "low", "close", "volume"]
    )


def scores_on(sessions: dict[int, dict[str, float]]) -> pd.DataFrame:
    rows = [
        [DATES[k], name, score]
        for k, by_name in sessions.items()
        for name, score in by_name.items()
    ]
    return pd.DataFrame(rows, columns=["decision_date", "instrument", "score"])


def top_name_config(
    rebalance_every: int = 5,
    min_names: int = 1,
    start: str | None = None,
    end: str | None = None,
    delay: int = 0,
) -> BacktestConfig:
    """Long the single highest score (1/3 of three names), no costs, 1000 of capital."""
    return BacktestConfig(
        strategy=StrategyConfig(
            long_fraction=0.34,
            short_fraction=0.0,
            rebalance_every=rebalance_every,
            min_names=min_names,
        ),
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0, delay=delay),
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
        end=end,
    )


A_TOP = {"A": 3.0, "B": 2.0, "C": 1.0}
C_TOP = {"A": 1.0, "B": 2.0, "C": 3.0}


def filled(trades: pd.DataFrame) -> pd.DataFrame:
    return trades[trades["status"] == "filled"].reset_index(drop=True)


def test_a_due_decision_without_scores_keeps_the_holdings_until_the_next_scored_session() -> None:
    """Scores on sessions 3 (A on top) and 14 (C on top), a decision due every 5 sessions.

    Session 3 decides (fill at the open of 4: 100 A at 10). Session 8 is due but has no
    score, so nothing is sold; the decision waits for session 14, the next session with a
    score (fill at 15: sell the 100 A, buy 25 C at 40). The next decision is due on session
    19, which has no score either, so C is held to the end. One name is held on every
    session from 4 to 29. Before the fix, session 8 sold A at the open of 9 and session 14,
    not a multiple of 5 sessions after 3, was never used.
    """
    res = run_backtest(flat_market(), scores_on({3: A_TOP, 14: C_TOP}), top_name_config())
    fills = filled(res.trades)
    assert fills["date"].tolist() == [DATES[4], DATES[15], DATES[15]]
    assert fills["decision_date"].tolist() == [DATES[3], DATES[14], DATES[14]]
    assert fills["instrument"].tolist() == ["A", "A", "C"]
    assert fills["shares"].tolist() == pytest.approx([100.0, -100.0, 25.0])
    held = res.daily.loc[DATES[4] :, "n_long"]
    assert len(held) == 26
    assert (held == 1).all()
    assert res.daily["equity"].to_numpy() == pytest.approx(np.full(len(res.daily), 1000.0))
    assert res.episodes[["instrument", "status"]].values.tolist() == [
        ["A", "closed"],
        ["C", "open"],
    ]
    assert (
        "2 scheduled decisions fell on sessions without any score; the holdings were kept "
        "and each decision was made on the next session with a score, if any (first on "
        "2024-01-11)"
    ) in res.warnings


def test_the_schedule_counts_from_the_decision_that_waited() -> None:
    """Scores on session 3 and on every session from 11 on. Session 8 is due without a
    score, so the decision is made on 11; the next ones are due 5 sessions apart from
    there: 16, 21 and 26 (26 fills on 27, inside the 30 sessions). Keeping the old phase
    would decide on 13, 18, 23 and 28 instead. The top name alternates between those
    decisions (C on 11 and 21, A on 16 and 26), so each one trades."""
    sessions = {3: A_TOP, **{k: (C_TOP if k % 2 else A_TOP) for k in range(11, 30)}}
    res = run_backtest(flat_market(), scores_on(sessions), top_name_config(), record_decisions=True)
    decided = sorted(res.decisions["decision_date"].unique())
    assert decided == [DATES[k] for k in (3, 11, 16, 21, 26)]
    assert sorted(filled(res.trades)["decision_date"].unique()) == decided


def test_dense_scores_keep_the_fixed_schedule() -> None:
    """With a score on every session from the first one on, decisions stay on sessions
    3, 8, 13, ... as before the fix, and no decision waits."""
    sessions = {k: (A_TOP if k % 2 else C_TOP) for k in range(3, 30)}
    res = run_backtest(flat_market(), scores_on(sessions), top_name_config(), record_decisions=True)
    decided = sorted(res.decisions["decision_date"].unique())
    assert decided == [DATES[k] for k in (3, 8, 13, 18, 23, 28)]
    assert not any("without any score" in w for w in res.warnings)


def test_a_last_session_without_scores_is_not_counted_as_a_wait() -> None:
    """A decision due on the last session could not fill inside the window (its fill is
    the next session), so a missing score there keeps nothing waiting and is not counted.
    Scores on sessions 3 to 28, a decision due every session: no warning about sessions
    without scores."""
    sessions = {k: (A_TOP if k % 2 else C_TOP) for k in range(3, 29)}
    res = run_backtest(flat_market(), scores_on(sessions), top_name_config(rebalance_every=1))
    assert not any("without any score" in w for w in res.warnings)
    assert filled(res.trades)["decision_date"].max() == DATES[28]


def test_a_scored_decision_that_selects_nothing_still_sells_and_is_counted() -> None:
    """A session with a score is a decision even when the strategy selects nothing: with
    ``min_names`` 2, session 8 scores only A, so the decision holds nothing and A is sold
    at the open of 9 (the rule strategy-evaluation/README.md documents). Session 13 is
    then due without a score. The run counts the decision that held nothing (REVIEW-20)."""
    res = run_backtest(
        flat_market(), scores_on({3: A_TOP, 8: {"A": 1.0}}), top_name_config(min_names=2)
    )
    fills = filled(res.trades)
    assert fills["date"].tolist() == [DATES[4], DATES[9]]
    assert fills["shares"].tolist() == pytest.approx([100.0, -100.0])
    assert (res.daily.loc[DATES[9] :, "n_long"] == 0).all()
    assert (
        "1 of 2 decisions held nothing: no eligible name had a score, or the strategy "
        "selected no name (fewer eligible names than it needs, an empty leg, or a leg "
        "below its minimum number of names)"
    ) in res.warnings
    assert any(w.startswith("1 scheduled decisions fell on sessions") for w in res.warnings)


@pytest.mark.parametrize(
    ("start", "end"),
    [("2024-01-15", None), ("2024-01-02", "2024-01-03")],
    ids=["start-after-the-last-signal", "window-before-the-first-signal"],
)
def test_an_evaluation_window_without_a_signal_is_refused(start: str, end: str | None) -> None:
    """BH-2026-10-15-4: the only scores are on session 3 (2024-01-04). A configured window
    that holds no score would be a flat, cost-free run; it is refused like the default
    window without signals."""
    with pytest.raises(InputError, match="no signal falls in the evaluation window"):
        run_backtest(flat_market(), scores_on({3: A_TOP}), top_name_config(start=start, end=end))


@pytest.mark.parametrize(
    ("end", "delay", "last"),
    [("2024-01-04", 0, "its last session"), ("2024-01-05", 1, "one of its last 2 sessions")],
    ids=["delay-0", "delay-1"],
)
def test_a_window_whose_scores_cannot_fill_runs_flat_with_a_warning(
    end: str, delay: int, last: str
) -> None:
    """The only score is on session 3 (2024-01-04). In a window from session 1 its order
    would fill at the open of session 4 + ``delay``, after the window's last session (3, or
    4 with a delay of 1), so no decision is made and the run is flat; the run says so
    instead of passing as a cost-free result (a sibling of BH-2026-10-15-4). It is a
    warning, not a refusal, because stress scenarios that add a delay rerun a valid base
    run's window."""
    res = run_backtest(
        flat_market(),
        scores_on({3: A_TOP}),
        top_name_config(start="2024-01-02", end=end, delay=delay),
    )
    assert filled(res.trades).empty
    assert (res.daily["traded_notional"] == 0).all()
    assert (
        "no decision was made: every session with a score in the evaluation window is "
        f"{last}, so no order could fill inside the window and the run held nothing"
    ) in res.warnings


def test_a_configured_start_before_the_signals_still_runs() -> None:
    """A window that starts before the first score but holds one is valid: the sessions
    before the first decision are flat, then the decision on session 3 fills on 4 (one
    decision only, so this also passes before the fix)."""
    res = run_backtest(
        flat_market(),
        scores_on({3: A_TOP}),
        top_name_config(rebalance_every=100, start="2024-01-02"),
    )
    assert res.daily.index[0] == DATES[1]
    assert filled(res.trades)["date"].tolist() == [DATES[4]]


def test_bucket_portfolios_decide_only_on_scored_sessions() -> None:
    """`invest-eval quantiles` with scores on sessions 3 and 14 and two buckets: every
    portfolio decides on exactly those two sessions. Before the fix the due session 8 had
    no score, sold every bucket's holdings and was not counted, and session 14, not on
    the fixed schedule, was never used (one decision counted)."""
    result = run_quantile_portfolios(
        flat_market(),
        scores_on({3: A_TOP, 14: C_TOP}),
        top_name_config(),
        QuantileConfig(n_buckets=2, tail_fractions=(0.5,), min_names_per_bucket=1),
    )
    table = result.table.set_index("portfolio")
    assert (table["decisions"] == 2).all()
    assert sorted(result.memberships["decision_date"].unique()) == [DATES[3], DATES[14]]


def test_a_bucket_below_its_minimum_number_of_names_is_counted_as_holding_nothing() -> None:
    """Three names in two buckets: the bucket rule puts one name in q1 and two in q2. With
    ``min_names_per_bucket`` 2, q1's leg is not empty but below its minimum, so its only
    decision holds nothing, and the warning names that reason."""
    result = run_quantile_portfolios(
        flat_market(),
        scores_on({3: C_TOP}),
        top_name_config(rebalance_every=100),
        QuantileConfig(n_buckets=2, tail_fractions=(0.5,), min_names_per_bucket=2),
    )
    assert (
        "1 of 1 decisions held nothing: no eligible name had a score, or the strategy "
        "selected no name (fewer eligible names than it needs, an empty leg, or a leg "
        "below its minimum number of names)"
    ) in result.warnings["q1"]
