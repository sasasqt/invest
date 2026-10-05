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
