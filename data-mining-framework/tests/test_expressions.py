import numpy as np
import pandas as pd
import pytest

from invest_mining.expressions import (
    ExpressionError,
    build_panel,
    canonical,
    evaluate,
    lookback,
    parse,
    random_expression,
    restrict,
)


@pytest.mark.parametrize(
    "text",
    [
        "__import__('os')",
        "close.__class__",
        "foo",
        "ts_mean(close, n)",
        "ts_mean(close, 2.5)",
        "ts_mean(close, 1)",
        "ts_mean(close, 1000)",
        "ts_mean(close, window=5)",
        "1 + 2",
        "ts_mean(3, 5)",
        "close ** 2",
        "lambda: close",
        "unknown_op(close)",
        "cs_rank(close, 3)",
        "close if volume else open",
    ],
)
def test_parser_rejects_unsafe_or_invalid(text):
    with pytest.raises(ExpressionError):
        parse(text)


def test_canonical_round_trip():
    text = "cs_rank(-(close / delay(close, 5) - 1)) + 0.5 * ts_corr(returns, volume, 10)"
    once = canonical(text)
    assert canonical(once) == once
    assert canonical("close+volume") == canonical("(close + volume)")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("close", 0),
        ("returns", 1),
        ("delay(close, 5)", 5),
        ("ts_mean(close, 5)", 4),
        ("ts_mean(returns, 5)", 5),
        ("ts_corr(delay(close, 2), volume, 10)", 11),
        ("cs_rank(delta(close, 3))", 3),
    ],
)
def test_lookback(text, expected):
    assert lookback(parse(text)) == expected


def test_operator_semantics_on_hand_example(tiny_panel):
    p = tiny_panel
    pd.testing.assert_series_equal(
        evaluate("ts_mean(close, 3)", p)["A"],
        pd.Series([np.nan, np.nan, 2.0, 3.0, 4.0, 5.0], index=p["close"].index, name="A"),
    )
    assert evaluate("delta(close, 2)", p)["B"].tolist()[2:] == [-2.0, -2.0, -2.0, -2.0]
    ranks = evaluate("cs_rank(close)", p).iloc[0]
    assert ranks.to_dict() == {"A": 0.5, "B": 1.0, "C": 0.5}  # ties share the average rank
    # Division by ~0, log of non-positive values and constant windows are undefined (NaN).
    assert (
        evaluate(
            "close / delta(C_close_placeholder, 1)".replace("C_close_placeholder", "close"), p
        )["C"]
        .iloc[1:]
        .isna()
        .all()
    )
    assert evaluate("log(close - 3)", p)["A"].isna().tolist() == [True] * 3 + [False] * 3
    assert evaluate("ts_std(close, 3)", p)["C"].isna().all()
    assert evaluate("ts_corr(close, volume, 3)", p).isna().all().all()
    z = evaluate("cs_zscore(close)", p).iloc[0]
    assert z.mean() == pytest.approx(0.0) and z.std(ddof=1) == pytest.approx(1.0)
    assert not np.isinf(evaluate("close / (close - close)", p).to_numpy()).any()


def test_random_expressions_are_causal(bars):
    """Truncating or perturbing the future must not change any earlier value."""
    panel = build_panel(bars)
    dates = panel["close"].index
    cut = dates[250]
    truncated = build_panel(bars[bars["date"] <= cut])
    shocked_bars = bars.copy()
    future = shocked_bars["date"] > cut
    shocked_bars.loc[future, ["open", "high", "low", "close"]] *= 3.0
    shocked_bars.loc[future, "volume"] *= 0.1
    shocked = build_panel(shocked_bars)
    rng = np.random.default_rng(0)
    for _ in range(60):
        node = random_expression(rng, max_depth=4)
        full = evaluate(node, panel).loc[:cut]
        pd.testing.assert_frame_equal(
            full, evaluate(node, truncated), check_freq=False, obj=str(node)
        )
        pd.testing.assert_frame_equal(
            full, evaluate(node, shocked).loc[:cut], check_freq=False, obj=str(node)
        )


def test_random_expressions_round_trip_and_are_deterministic():
    a = [str(random_expression(np.random.default_rng(5))) for _ in range(3)]
    b = [str(random_expression(np.random.default_rng(5))) for _ in range(3)]
    assert a == b
    for text in a:
        assert canonical(text) == text


def test_fundamental_features_and_universe_restricted_cross_sections(tiny_panel):
    p = dict(tiny_panel)
    with pytest.raises(ExpressionError, match="not in the panel"):
        evaluate("fund_bp", p)
    p["fund_bp"] = p["close"] * 0 + 2.0
    pd.testing.assert_frame_equal(evaluate("fund_bp * close", p), 2 * p["close"])
    p["universe"] = p["close"].notna() & pd.DataFrame(
        {"A": True, "B": True, "C": False}, index=p["close"].index
    )
    r = evaluate("cs_rank(close)", p).iloc[-1]
    assert r["A"] == 1.0 and r["B"] == 0.5 and np.isnan(r["C"])
    with pytest.raises(ExpressionError):
        parse("fund_BP")


def test_fundamental_expressions_are_causal(bars):
    from invest_data.sources import synthetic_fundamentals

    fund = synthetic_fundamentals(bars, seed=11)
    cut = pd.Timestamp(sorted(bars["date"].unique())[250])
    full = build_panel(bars, fundamentals=fund)
    known = build_panel(bars[bars["date"] <= cut], fundamentals=fund[fund["available_date"] <= cut])
    for text in ("fund_book_to_price", "cs_rank(fund_earnings_yield) - ts_mean(returns, 5)"):
        pd.testing.assert_frame_equal(
            evaluate(text, full).loc[:cut], evaluate(text, known), check_freq=False
        )


def _bars_and_universe() -> tuple[pd.DataFrame, pd.DataFrame, pd.DatetimeIndex]:
    """Closes 4, 9, 16 (A) and 1, 1, 1 (B); A joins the universe on the second date."""
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    rows = [
        {"date": d, "instrument": inst, "open": c, "high": c, "low": c, "close": c, "volume": 1e3}
        for inst, closes in (("A", [4.0, 9.0, 16.0]), ("B", [1.0, 1.0, 1.0]))
        for d, c in zip(dates, closes, strict=True)
    ]
    universe = pd.DataFrame(
        {
            "universe": ["U", "U"],
            "instrument": ["A", "B"],
            "start_date": [dates[1], dates[0]],
            "end_date": [pd.NaT, pd.NaT],
        }
    )
    return pd.DataFrame(rows), universe, pd.DatetimeIndex(dates)


def test_unary_operators_keep_pre_membership_history_under_time_series_operators() -> None:
    """REVIEW-28 / RA-2026-11-01-2: only cross-sectional operators see members only.

    build_panel's docstring: time-series operators use each instrument's full history. A joins the
    universe on the second date, so on that date ts_sum(abs(close), 2) must still see A's first
    close. Expected values are hand calculations on the closes 4, 9, 16 (A) and 1, 1, 1 (B).
    """
    bars, universe, dates = _bars_and_universe()
    panel = build_panel(bars, universe=universe)
    entry = dates[1]
    expected = {
        "ts_sum(close, 2)": 13.0,  # the control: no unary operator
        "ts_sum(abs(close), 2)": 13.0,  # 4 + 9
        "ts_sum(neg(close), 2)": -13.0,
        "ts_sum(sign(close), 2)": 2.0,
        "ts_sum(log(close), 2)": np.log(36.0),  # ln 4 + ln 9
        "ts_sum(abs(neg(close)), 2)": 13.0,  # nested unary operators
        "ts_mean(abs(close), 2)": 6.5,
        "delay(abs(close), 1)": 4.0,
        "delta(abs(close), 1)": 5.0,  # 9 - 4
    }
    for text, value in expected.items():
        got = evaluate(text, panel).loc[entry, "A"]
        assert got == pytest.approx(value), f"{text}: {got} != {value}"
    # Both operands of a two-input time-series operator keep the history: abs(close) and
    # neg(close) move in exact opposition over 4, 9, 16, so their correlation is -1.
    corr = evaluate("ts_corr(abs(close), neg(close), 3)", panel).loc[dates[2], "A"]
    assert corr == pytest.approx(-1.0)
    # Without a universe the same formulas give the same numbers for A.
    plain = build_panel(bars)
    for text, value in expected.items():
        assert evaluate(text, plain).loc[entry, "A"] == pytest.approx(value)


def test_cross_sections_still_see_members_only_and_restrict_masks_non_members() -> None:
    """The REVIEW-28 fix must not widen cross-sections, and callers still mask non-members."""
    bars, universe, dates = _bars_and_universe()
    panel = build_panel(bars, universe=universe)
    # On the first date A is not a member, so B ranks alone and cs_demean leaves it at 0.
    first = evaluate("cs_rank(abs(close))", panel).loc[dates[0]]
    assert np.isnan(first["A"]) and first["B"] == 1.0
    assert evaluate("cs_demean(close)", panel).loc[dates[0], "B"] == 0.0
    # A cross-sectional operator under a time-series one: A had no rank before it joined, so the
    # window over its entry date stays missing (by design, with or without the fix).
    assert np.isnan(evaluate("ts_sum(cs_rank(close), 2)", panel).loc[dates[1], "A"])
    # evaluate computes a unary operator for a non-member like the bare feature; restrict,
    # which every scoring path applies, masks it.
    assert evaluate("abs(close)", panel).loc[dates[0], "A"] == 4.0
    assert np.isnan(restrict(evaluate("abs(close)", panel), panel).loc[dates[0], "A"])
    assert restrict(evaluate("abs(close)", panel), panel).loc[dates[0], "B"] == 1.0


def test_time_series_operators_see_the_bars_of_a_membership_gap() -> None:
    """A leaves the universe and comes back: on re-entry the window uses the gap's bars."""
    dates = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"]
    )
    closes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    rows = [
        {"date": d, "instrument": "A", "open": c, "high": c, "low": c, "close": c, "volume": 1e3}
        for d, c in zip(dates, closes, strict=True)
    ]
    bars = pd.DataFrame(rows)
    universe = pd.DataFrame(
        {
            "universe": ["U", "U"],
            "instrument": ["A", "A"],
            "start_date": [dates[0], dates[5]],  # member for the first three dates, then again
            "end_date": [dates[3], pd.NaT],  # end_date is exclusive
        }
    )
    panel = build_panel(bars, universe=universe)
    assert bool(panel["universe"].loc[dates[3], "A"]) is False  # the gap starts here
    reentry = dates[5]
    assert evaluate("ts_sum(abs(close), 2)", panel).loc[reentry, "A"] == 11.0  # 5 + 6
    assert evaluate("ts_mean(neg(close), 3)", panel).loc[reentry, "A"] == -5.0  # -(4+5+6)/3
    # The reference: the same panel without a universe, which the fix does not touch.
    plain = build_panel(bars)
    for text in ("ts_sum(abs(close), 2)", "ts_mean(neg(close), 3)", "delay(abs(close), 2)"):
        assert evaluate(text, panel).loc[reentry, "A"] == evaluate(text, plain).loc[reentry, "A"]
