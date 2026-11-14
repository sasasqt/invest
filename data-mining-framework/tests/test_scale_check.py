"""Mining commands refuse formulas whose value depends on the scale of adjusted bars.

BH-2026-11-10-1 and the user's decision of 2026-11-11: bars are total-return adjusted
backwards, so a split or dividend after date T multiplies one instrument's whole earlier price
history by a constant c and its volume by 1/c. A formula is causal only when that constant
cancels; a level such as ``cs_rank(-close)`` ranks names by splits they have not made yet.
"""

import json
import re

import numpy as np
import pandas as pd
import pytest

from invest_data.cli import main as data_main
from invest_data.schemas import publish_market_bars, publish_universe, read_signals
from invest_data.sources import SYNTHETIC_METADATA, SyntheticConfig, synthetic_market
from invest_mining import expressions as ex
from invest_mining.artifact import FrozenFactor
from invest_mining.cli import main

# The decision's "already allowed" list, its exceptions, the README's new example and a few
# cases that follow from the same rule (a log level whose constant cancels).
ALLOWED = [
    "close / delay(close, 5) - 1",
    "close / open",
    "(high - low) / close",
    "close / ts_max(close, 252)",
    "close / ts_mean(close, 20)",
    "delta(log(close), 5)",
    "log(close) - log(open)",
    "ts_rank(close, 20)",
    "ts_corr(close, volume, 20)",
    "sign(delta(close, 5))",
    "volume / ts_mean(volume, 20)",
    "dollar_volume",
    "log(dollar_volume)",
    "cs_rank(log(dollar_volume))",
    "abs(returns) / dollar_volume",
    "volume * delta(open, 3)",
    "fund_book_to_price",
    "cs_rank(fund_book_to_price)",
    "close_as_traded",
    "cs_rank(-close_as_traded)",
    "log(close_as_traded)",
    "cs_zscore(log(close_as_traded))",
    "cs_rank(open * close_as_traded / close)",
    "cs_rank(volume * close / close_as_traded)",
    "sign(close_as_traded - 5)",
    "fund_eps / close_as_traded",
    "cs_rank(fund_eps / close_as_traded)",
    "cs_rank(-delta(close, 5) / close)",
    "log(close) + log(volume)",
    "ts_std(log(close), 20)",
    "ts_rank(log(close), 10)",
    "cs_rank(log(close) - delay(log(close), 5))",
    "ts_mean(returns, 10) * cs_zscore(ts_mean(returns, 10))",
    # Log levels follow exact offsets: these cancel only because the multiples add up to 0.
    "ts_sum(log(close), 3) - 3 * log(close)",
    "log(close) / 2 - log(open) / 2",
    "cs_rank(log(close) * 0)",
]

# Refused formulas with fragments of the safe form their message must name (the decision's
# six cases, plus mixes and log levels).
LEVEL = ["close_as_traded", "close / ts_max(close, 252)"]
VOLUME = ["volume * close / close_as_traded", "log(dollar_volume)"]
CHANGE = ["delta(close, 5) / close", "delta(log(close), 5)"]
AS_TRADED_TS = ["close / delay(close, 5) - 1", "delta(log(close), 5)"]
FACTOR = ["no safe form"]
REFUSED = [
    ("close", LEVEL),
    ("cs_rank(-close)", LEVEL),
    ("cs_rank(log(close))", ["log(close_as_traded)", "delta(log(close), 5)"]),
    ("cs_zscore(log(close))", ["log(close_as_traded)"]),
    ("delay(close, 1)", LEVEL),
    ("cs_rank(ts_mean(high, 20))", LEVEL),
    ("cs_rank(volume)", VOLUME),
    ("ts_mean(volume, 20)", VOLUME),
    ("cs_rank(log(volume))", ["log(dollar_volume)"]),
    ("fund_eps / close", ["fund_eps / close_as_traded"]),
    ("cs_rank(fund_book_to_price / close)", ["fund_book_to_price / close_as_traded"]),
    # The price change keeps its own sign; a level that falls with the price is a volume level.
    ("cs_rank(-delta(close, 5))", [*CHANGE, "(neg(delta(close, 5)) / close)"]),
    ("cs_rank(dollar_volume / close)", VOLUME),
    ("cs_rank(volume / close)", VOLUME),
    ("cs_rank(1 / close)", LEVEL),
    ("cs_rank(returns / close)", LEVEL),
    ("cs_rank(returns / ts_std(close, 20))", CHANGE),
    ("delta(close, 5)", CHANGE),
    ("cs_rank(ts_std(close, 20))", CHANGE),
    ("high - low", CHANGE),
    ("delta(close_as_traded, 5)", AS_TRADED_TS),
    ("ts_mean(close_as_traded, 20)", AS_TRADED_TS),
    ("ts_corr(close_as_traded, returns, 20)", ["ts_corr(close, returns, 20)"]),
    ("ts_rank(close_as_traded, 20)", ["ts_rank(close, 20)"]),
    ("delay(open * close_as_traded / close, 1)", AS_TRADED_TS),
    ("close / close_as_traded", FACTOR),
    ("cs_rank(close_as_traded / close)", FACTOR),
    # The adjustment factor inside a sum gets its own message, not the generic mixed one.
    ("cs_rank(close / close_as_traded - 1)", FACTOR),
    # An adjusted price change times the as-traded price still names the price change form.
    ("cs_rank(close_as_traded * delta(close, 5))", [*FACTOR, "delta(close, 5) / close"]),
    ("cs_rank(close_as_traded * volume)", ["dollar_volume", "volume * close / close_as_traded"]),
    # Parts whose scale a cross-sectional operator, ts_rank, ts_corr or sign removed do not
    # choose the message: the level here is "* close", not the as-traded rank.
    ("cs_rank(log(close_as_traded)) * close", LEVEL),
    ("cs_rank(fund_eps) * close", LEVEL),
    ("cs_rank(close * sign(delta(close, 5)))", LEVEL),
    ("cs_rank(close * sign(fund_eps / close))", LEVEL),
    # The price-floor flag and per-share fundamentals keep their idea in the safe form.
    ("sign(close - 5)", ["sign(close_as_traded - 5)"]),
    ("cs_rank(close - 5)", ["close_as_traded - 5"]),
    ("cs_rank(log(fund_eps / close))", ["fund_eps / close_as_traded"]),
    ("cs_rank(fund_eps * close)", ["fund_eps * close_as_traded"]),
    ("cs_rank(close / fund_eps)", ["close_as_traded / fund_eps"]),
    # The fundamental's own formula, read with the as-traded close, when the check passes it.
    ("cs_rank(1 / (fund_eps / close))", ["(1.0 / (fund_eps / close_as_traded))"]),
    ("cs_rank(-(fund_eps / close))", ["neg((fund_eps / close_as_traded))"]),
    ("cs_rank(fund_eps / close - 1)", ["((fund_eps / close_as_traded) - 1.0)"]),
    # Price and log levels quote their own formula with the as-traded close when it passes.
    ("cs_rank(close * 2)", ["(close_as_traded * 2.0)"]),
    ("cs_rank(returns / close)", ["(returns / close_as_traded)"]),
    ("cs_rank(log(close) * 2)", ["(log(close_as_traded) * 2.0)"]),
    ("log(close) + fund_eps", ["log(close_as_traded)", "delta(log(close), 5)"]),
    ("close + 1", ["scale differently"]),
    ("returns + close", ["scale differently"]),
    ("abs(log(close))", ["delta(log(close), 5)"]),
    ("sign(log(close))", ["delta(log(close), 5)"]),
    ("log(log(close))", ["delta(log(close), 5)"]),
    ("log(close) * returns", ["delta(log(close), 5)"]),
    # Near misses of the exact offset rule: each keeps a multiple of log c that is not 0.
    ("log(close) + log(open)", ["delta(log(close), 5)"]),
    ("2 * log(close) - log(close)", ["delta(log(close), 5)"]),
    ("ts_sum(log(close), 5) - log(close)", ["delta(log(close), 5)"]),
    ("log(close) / log(open)", ["delta(log(close), 5)"]),
    ("delta(delta(log(close), 5) * log(close), 3)", ["delta(log(close), 5)"]),
]
SAYS_WHY = "split or dividend"


# Every safe form a refusal message quotes as a formula must itself pass the check.
QUOTED = [
    "close_as_traded",
    "open * close_as_traded / close",
    "close / ts_max(close, 252)",
    "volume * close / close_as_traded",
    "log(dollar_volume)",
    "volume / ts_mean(volume, 20)",
    "dollar_volume",
    "delta(close, 5) / close",
    "delta(log(close), 5)",
    "log(close_as_traded)",
    "close / delay(close, 5) - 1",
    "sign(close_as_traded - 5)",
    "fund_eps / close_as_traded",
    "log(fund_eps / close_as_traded)",
    "fund_eps * close_as_traded",
    "close_as_traded / fund_eps",
    "ts_rank(close, 20)",
    "ts_corr(close, returns, 20)",
]


@pytest.mark.parametrize("formula", [*ALLOWED, *QUOTED])
def test_scale_free_formulas_pass(formula):
    ex.check_scale_free(ex.parse(formula))


@pytest.mark.parametrize(("formula", "safe"), REFUSED)
def test_scale_dependent_formulas_are_refused_with_the_safe_form(formula, safe):
    with pytest.raises(ex.ScaleError) as caught:
        ex.check_scale_free(ex.parse(formula))
    message = str(caught.value)
    assert SAYS_WHY in message
    for fragment in safe:
        assert fragment in message, (formula, message)


def test_search_never_draws_a_refused_formula():
    from invest_mining.search import SEED_TEMPLATES

    for text in SEED_TEMPLATES:
        ex.check_scale_free(ex.parse(text))
    drawn = set()
    for seed in range(60):
        rng = np.random.default_rng(seed)
        for _ in range(20):
            node = ex.random_expression(rng)
            ex.check_scale_free(node)
            assert not ex.features_used(node) & set(ex.AS_TRADED_FEATURES)
            drawn |= ex.features_used(node)
    # The grammar still draws every feature it drew before, levels inside ratios included.
    assert drawn == set(ex.FEATURES)


@pytest.mark.parametrize(
    "formula",
    [
        "ts_corr(close_as_traded, close, 20)",
        "ts_mean(close_as_traded / close, 20)",
        "ts_rank(close_as_traded / close, 20)",
    ],
)
def test_as_traded_series_message_suggests_no_constant_formula(formula):
    """Swapping close_as_traded for close is suggested only where nothing else reads an
    adjusted field: here it would give ts_corr(close, close, 20) or close / close."""
    with pytest.raises(ex.ScaleError) as caught:
        ex.check_scale_free(ex.parse(formula))
    assert "adjusted close instead" not in str(caught.value), str(caught.value)


@pytest.mark.parametrize(
    "formula", ["ts_mean(fund_eps / close, 5)", "cs_rank(ts_rank(fund_eps / close_as_traded, 5))"]
)
def test_suggestions_that_swap_close_and_close_as_traded_end(formula):
    """A fundamental over close suggests close_as_traded; a time-series operator over that
    suggests close again. The message must still be built once, with a plain suggestion."""
    with pytest.raises(ex.ScaleError, match=SAYS_WHY):
        ex.check_scale_free(ex.parse(formula))


def test_a_suggested_form_parses_as_written():
    """A tree built in code can hold a constant inside a time-series operator, which the
    parser refuses; a message must not suggest that tree with ``close`` swapped in."""
    node = ex.Call("ts_corr", (ex.Feature("close_as_traded"), ex.Const(0.5)), 5)
    with pytest.raises(ex.ScaleError) as refused:
        ex.check_scale_free(node)
    assert "ts_corr(close, 0.5, 5)" not in str(refused.value)


LONG = ex.MAX_DEPTH  # summed terms; the longest sums the parser takes nest this deep
LONG_FORMULAS = [
    (" + ".join(["close / open"] * LONG), None),
    (" + ".join(["close"] * LONG), "adjusted price level"),
    ("cs_rank(" + " + ".join(["close"] * LONG) + ")", "adjusted price level"),
    (
        " + ".join(["log(close) - log(open)"] * (LONG // 2 - 1)) + " + log(close)",
        "log of an adjusted",
    ),
    (" + ".join(["fund_eps / close"] * LONG), "per-share fundamental"),
]


@pytest.mark.parametrize(
    "text, refusal", LONG_FORMULAS, ids=["ratios", "closes", "cs", "logs", "fund"]
)
def test_a_long_formula_gets_a_clean_answer(text, refusal):
    """A formula the parser accepts passes or is refused with a message, never a traceback
    (Python 3.11 spends two frames per level in a comprehension)."""
    node = ex.parse(text)
    if refusal is None:
        ex.check_scale_free(node)
    else:
        with pytest.raises(ex.ScaleError, match=refusal):
            ex.check_scale_free(node)
    assert ex.features_used(node) <= {"close", "open", "fund_eps"}  # the CLI's column check


def _negated(node: ex.Node, times: int) -> ex.Node:
    for _ in range(times):
        node = ex.Call("neg", (node,))
    return node


@pytest.mark.parametrize(
    "inner, refusal",
    [("close / open", None), ("close", "price level"), ("delta(close, 5)", "price change")],
)
def test_a_deep_tree_built_in_code_gets_a_clean_answer(inner, refusal):
    """No recursion limit applies to the check, its message or the CLI's column check."""
    node = _negated(ex.parse(inner), 3000)
    assert ex.features_used(node) == ex.features_used(ex.parse(inner))
    if refusal is None:
        ex.check_scale_free(node)
    else:
        with pytest.raises(ex.ScaleError, match=refusal):
            ex.check_scale_free(node)


# ---------------------------------------------------------------------------
# A later split, end to end


def _split_pair(n_instruments=20, n_days=140, seed=3):
    """Bars A and B that tell the same story; in B one name splits 2:1 at session T."""
    a = synthetic_market(SyntheticConfig(n_instruments=n_instruments, n_days=n_days, seed=seed))
    dates = sorted(a["date"].unique())
    t = dates[n_days // 2]
    name = sorted(a["instrument"].unique())[3]
    b = a.copy()
    before = (b["instrument"] == name) & (b["date"] < t)
    for column in ("open", "high", "low", "close"):
        b.loc[before, column] *= 0.5  # back-adjusted for the split (exact in binary)
    b.loc[before, "volume"] *= 2.0  # volume inversely; close_as_traded is unchanged
    return a, b, pd.Timestamp(t)


def _same(x: pd.DataFrame, y: pd.DataFrame) -> bool:
    if not x.isna().equals(y.isna()):
        return False
    # Halving prices is exact in binary; a log shifts by log(2) with rounding, which a
    # correlation of correlations can amplify to about 1e-6.
    return bool(np.allclose(x.to_numpy(), y.to_numpy(), rtol=1e-6, atol=1e-6, equal_nan=True))


def _random_tree(rng: np.random.Generator, depth: int) -> ex.Node:
    leaves = (*ex.FEATURES, *ex.AS_TRADED_FEATURES)
    if depth <= 1 or rng.random() < 0.25:
        return ex.Feature(str(rng.choice(leaves)))
    kind = str(rng.choice(["unary", "binary", "ts", "ts2", "cs", "const"]))
    if kind == "unary":
        return ex.Call(
            str(rng.choice(["neg", "abs", "log", "sign"])), (_random_tree(rng, depth - 1),)
        )
    if kind in ("binary", "const"):
        other = (
            ex.Const(float(rng.choice([0.5, 2.0, 5.0])))
            if kind == "const"
            else _random_tree(rng, depth - 1)
        )
        return ex.Call(
            str(rng.choice(["add", "sub", "mul", "div"])), (_random_tree(rng, depth - 1), other)
        )
    if kind == "ts":
        op = str(rng.choice([k for k, s in ex.OPS.items() if s.kind == "ts"]))
        return ex.Call(op, (_random_tree(rng, depth - 1),), int(rng.choice([2, 3, 5, 10])))
    if kind == "ts2":
        args = (_random_tree(rng, depth - 1), _random_tree(rng, depth - 1))
        return ex.Call("ts_corr", args, int(rng.choice([5, 10])))
    return ex.Call(
        str(rng.choice(["cs_rank", "cs_zscore", "cs_demean"])), (_random_tree(rng, depth - 1),)
    )


def test_every_formula_the_check_passes_ignores_a_later_split():
    """Generated property: a passed formula gives the same values before T in A and B."""
    a, b, t = _split_pair()
    panels = ex.build_panel(a), ex.build_panel(b)
    rng = np.random.default_rng(20261112)
    passed, refused, changed_by_split = 0, 0, 0
    ops_seen: set[str] = set()
    features_seen: set[str] = set()
    for _ in range(1500):
        try:
            node = ex.parse(str(_random_tree(rng, 4)))
        except ex.ExpressionError:
            continue  # constant-only or similar; the parser's own business
        before = [ex.evaluate(node, p).loc[lambda f: f.index < t] for p in panels]
        try:
            ex.check_scale_free(node)
        except ex.ScaleError:
            refused += 1
            changed_by_split += not _same(*before)
            continue
        passed += 1
        features_seen |= ex.features_used(node)
        stack = [node]
        while stack:
            n = stack.pop()
            if isinstance(n, ex.Call):
                ops_seen.add(n.op)
                stack.extend(n.args)
        assert _same(*before), f"{node} passed the check but a later split changed it"
    # The generator reached every operator and feature, and the split is visible to it.
    assert passed >= 150 and refused >= 150, (passed, refused)
    assert ops_seen == set(ex.OPS), set(ex.OPS) - ops_seen
    assert features_seen == {*ex.FEATURES, *ex.AS_TRADED_FEATURES}
    assert changed_by_split >= refused // 3, (changed_by_split, refused)


def _time_series_over_as_traded(node: ex.Node) -> bool:
    if not isinstance(node, ex.Call):
        return False
    if ex.OPS[node.op].kind in ("ts", "ts2") and ex.features_used(node) & set(
        ex.AS_TRADED_FEATURES
    ):
        return True
    return any(_time_series_over_as_traded(a) for a in node.args)


def test_refused_levels_do_change_with_a_later_split():
    """The split pair can see the defect: each refused level case moves earlier values."""
    a, b, t = _split_pair()
    panels = ex.build_panel(a), ex.build_panel(b)
    fundamentals = {"fund_eps", "fund_book_to_price"}
    for formula, safe in REFUSED:
        node = ex.parse(formula)
        if (
            safe == FACTOR
            or _time_series_over_as_traded(node)
            or ex.features_used(node) & fundamentals
        ):
            continue  # as-traded series and the factor are refused for other reasons
        if formula in ("sign(log(close))", "sign(close - 5)"):
            continue  # changes only where a price crosses 1 or 5; synthetic prices stay above
        before = [ex.evaluate(node, p).loc[lambda f: f.index < t] for p in panels]
        assert not _same(*before), formula


def _publish(frame: pd.DataFrame, path) -> None:
    publish_market_bars(frame, path, dataset_id="m", metadata=SYNTHETIC_METADATA)


def test_export_scores_before_a_later_split_are_unchanged_for_allowed_formulas(tmp_path):
    a, b, t = _split_pair()
    _publish(a, tmp_path / "a")
    _publish(b, tmp_path / "b")
    for i, formula in enumerate(["close / delay(close, 5) - 1", "cs_rank(-close_as_traded)"]):
        factor = tmp_path / f"f{i}.json"
        assert main(["freeze", "--expr", formula, "--horizon", "1", "--out", str(factor)]) == 0
        scores = []
        for side in ("a", "b"):
            out = tmp_path / f"sig{i}{side}"
            args = ["export", "--data", str(tmp_path / side), "--factor", str(factor)]
            assert main([*args, "--out", str(out)]) == 0
            signals = read_signals(out)[1]
            scores.append(signals[signals["decision_date"] < t].reset_index(drop=True))
        assert len(scores[0]) > 0
        pd.testing.assert_frame_equal(scores[0], scores[1], rtol=1e-9)


# ---------------------------------------------------------------------------
# Every command refuses before the ledger or an output is written


@pytest.fixture
def market(tmp_path):
    data = tmp_path / "data"
    data_main(["synthetic", "--out", str(data), "--instruments", "15", "--days", "200"])
    return data


LEVELS = ["cs_rank(-close)", "fund_book_to_price / close", "cs_rank(-delta(close, 5))"]


@pytest.mark.parametrize("formula", [*LEVELS, "delta(close_as_traded, 5)"])
def test_freeze_refuses_a_scale_dependent_formula(tmp_path, formula):
    out = tmp_path / "f.json"
    with pytest.raises(SystemExit, match=SAYS_WHY):
        main(["freeze", "--expr", formula, "--horizon", "1", "--out", str(out)])
    assert not out.exists()


@pytest.mark.parametrize("formula", LEVELS)
def test_evaluate_refuses_a_scale_dependent_formula_before_the_ledger(tmp_path, market, formula):
    book, out = tmp_path / "ledger.jsonl", tmp_path / "ev"
    args = ["evaluate", "--data", str(market), "--expr", formula, "--ledger", str(book)]
    with pytest.raises(SystemExit, match=SAYS_WHY):
        main([*args, "--out", str(out)])
    assert not book.exists() and not out.exists()


def _old_artifact(tmp_path, formula: str) -> str:
    """A factor file written before this check existed (freeze now refuses the formula)."""
    factor = FrozenFactor(
        expression=formula,
        orientation=1,
        horizon_days=1,
        training_start="",
        training_end="",
        dataset_id="",
        dataset_sha256=None,
        selection={"method": "fixed_formula", "n_proposals": 1},
    )
    return str(factor.save(tmp_path / "old.json"))


def test_confirm_and_export_refuse_an_old_scale_dependent_artifact(tmp_path, market):
    factor = _old_artifact(tmp_path, "cs_rank(-close)")
    book = tmp_path / "ledger.jsonl"
    confirm = ["confirm", "--data", str(market), "--factor", factor, "--ledger", str(book)]
    with pytest.raises(SystemExit, match=SAYS_WHY):
        main([*confirm, "--confirm-start", "2020-04-01", "--out", str(tmp_path / "c")])
    assert not book.exists() and not (tmp_path / "c").exists()
    export = ["export", "--data", str(market), "--factor", factor, "--out", str(tmp_path / "s")]
    with pytest.raises(SystemExit, match=SAYS_WHY):
        main(export)
    assert not (tmp_path / "s").exists()


def test_export_from_search_refuses_a_scale_dependent_member(tmp_path, market):
    loaded = FrozenFactor.load(_old_artifact(tmp_path, "cs_rank(volume)"))
    root = tmp_path / "search"
    loaded.save(root / "factors" / f"{loaded.factor_id}.json")
    pd.DataFrame({"factor_id": [loaded.factor_id]}).to_csv(root / "confirmation.csv", index=False)
    (root / "config.json").write_text(json.dumps({}), encoding="utf-8")
    args = ["export", "--data", str(market), "--from-search", str(root)]
    with pytest.raises(SystemExit, match="volume \\* close / close_as_traded"):
        main([*args, "--out", str(tmp_path / "s")])
    assert not (tmp_path / "s").exists()


def test_search_trials_are_all_scale_free(tmp_path, market):
    out = tmp_path / "search"
    assert main(["search", "--data", str(market), "--trials", "40", "--out", str(out)]) == 0
    expressions = pd.read_csv(out / "ledger.csv")["expression"].dropna()
    assert len(expressions) > 0
    for text in expressions:
        ex.check_scale_free(ex.parse(text))


def test_as_traded_formula_needs_the_column(tmp_path):
    bars = synthetic_market(SyntheticConfig(n_instruments=12, n_days=80, seed=5))
    _publish(bars, tmp_path / "with")
    _publish(bars.drop(columns="close_as_traded"), tmp_path / "without")
    _publish(bars.assign(close_as_traded=np.nan), tmp_path / "empty")
    formula = "cs_rank(-close_as_traded)"
    args = ["evaluate", "--expr", formula, "--horizon", "1"]
    assert main([*args, "--data", str(tmp_path / "with"), "--out", str(tmp_path / "ok")]) == 0
    for side in ("without", "empty"):
        book = tmp_path / f"{side}.jsonl"
        with pytest.raises(SystemExit, match="no close_as_traded"):
            main(
                [
                    *args,
                    "--data",
                    str(tmp_path / side),
                    "--ledger",
                    str(book),
                    "--out",
                    str(tmp_path / side),
                ]
            )
        assert not book.exists()
    factor = tmp_path / "f.json"
    assert main(["freeze", "--expr", formula, "--horizon", "1", "--out", str(factor)]) == 0
    export = ["export", "--data", str(tmp_path / "without"), "--factor", str(factor)]
    with pytest.raises(SystemExit, match="no close_as_traded"):
        main([*export, "--out", str(tmp_path / "s")])
    assert not (tmp_path / "s").exists()
    book = tmp_path / "confirm.jsonl"
    confirm = ["confirm", "--data", str(tmp_path / "without"), "--factor", str(factor)]
    with pytest.raises(SystemExit, match="no close_as_traded"):
        main(
            [
                *confirm,
                "--confirm-start",
                "2020-03-02",
                "--ledger",
                str(book),
                "--out",
                str(tmp_path / "c"),
            ]
        )
    assert not book.exists() and not (tmp_path / "c").exists()


# ---------------------------------------------------------------------------
# The as-traded close must have values where the formula is scored


def _as_traded_until(path, cut_at: int = 100) -> str:
    """Bars whose as-traded close is known only before session ``cut_at``; its date."""
    bars = synthetic_market(SyntheticConfig(n_instruments=25, n_days=200, seed=5))
    cut = pd.Timestamp(sorted(bars["date"].unique())[cut_at])
    bars.loc[bars["date"] >= cut, "close_as_traded"] = np.nan
    _publish(bars, path)
    return str(cut.date())


def _frozen_as_traded(tmp_path) -> str:
    factor = tmp_path / "f.json"
    args = ["freeze", "--expr", "cs_rank(-close_as_traded)", "--horizon", "1"]
    assert main([*args, "--out", str(factor)]) == 0
    return str(factor)


def test_confirm_refuses_a_window_without_as_traded_values(tmp_path):
    """Values before the window do not count: confirming would test nothing and still use
    the reserved window up, so a later confirmation there would be exploratory."""
    start = _as_traded_until(tmp_path / "m")
    book = tmp_path / "ledger.jsonl"
    assert main(["ledger", "reserve", "--ledger", str(book), "--start", start]) == 0
    before = book.read_bytes()
    args = ["confirm", "--data", str(tmp_path / "m"), "--factor", _frozen_as_traded(tmp_path)]
    args += ["--confirm-start", start, "--ledger", str(book), "--out", str(tmp_path / "c")]
    with pytest.raises(SystemExit, match=f"no close_as_traded value .* from {start} on"):
        main(args)
    assert book.read_bytes() == before and not (tmp_path / "c").exists()


def test_confirm_counts_only_universe_members(tmp_path):
    """Values of names outside the universe are not scored, so they do not count."""
    bars = synthetic_market(SyntheticConfig(n_instruments=25, n_days=200, seed=5))
    names = sorted(bars["instrument"].unique())
    dates = pd.DatetimeIndex(sorted(bars["date"].unique()))
    cut = dates[100]
    late = bars["date"] >= cut
    bars.loc[late & bars["instrument"].isin(names[:20]), "close_as_traded"] = np.nan
    _publish(bars, tmp_path / "m")
    members = pd.DataFrame(
        {"universe": "u", "instrument": names[:20], "start_date": dates[0].date(), "end_date": None}
    )
    publish_universe(members, tmp_path / "uni", dataset_id="u")
    book = tmp_path / "ledger.jsonl"
    assert main(["ledger", "reserve", "--ledger", str(book), "--start", str(cut.date())]) == 0
    before = book.read_bytes()
    args = ["confirm", "--data", str(tmp_path / "m"), "--factor", _frozen_as_traded(tmp_path)]
    args += ["--universe", str(tmp_path / "uni"), "--confirm-start", str(cut.date())]
    with pytest.raises(SystemExit, match="no close_as_traded value"):
        main([*args, "--ledger", str(book), "--out", str(tmp_path / "c")])
    assert book.read_bytes() == before and not (tmp_path / "c").exists()


def test_confirm_refuses_a_window_with_too_few_as_traded_values(tmp_path):
    """Values on the window's first sessions only: the formula has no value on the rest, so
    the test would see too few dates and still use the reserved window up."""
    bars = synthetic_market(SyntheticConfig(n_instruments=25, n_days=300, seed=5))
    dates = sorted(bars["date"].unique())
    start = str(pd.Timestamp(dates[150]).date())
    bars.loc[bars["date"] >= dates[180], "close_as_traded"] = np.nan  # 30 sessions with values
    _publish(bars, tmp_path / "m")
    book = tmp_path / "ledger.jsonl"
    assert main(["ledger", "reserve", "--ledger", str(book), "--start", start]) == 0
    before = book.read_bytes()
    args = ["confirm", "--data", str(tmp_path / "m"), "--factor", _frozen_as_traded(tmp_path)]
    args += ["--confirm-start", start, "--ledger", str(book), "--out", str(tmp_path / "c")]
    with pytest.raises(SystemExit, match=r"has \d+ decision date\(s\) with a complete"):
        main(args)
    assert book.read_bytes() == before and not (tmp_path / "c").exists()


def test_export_refuses_a_start_without_as_traded_values(tmp_path):
    start = _as_traded_until(tmp_path / "m")
    args = ["export", "--data", str(tmp_path / "m"), "--factor", _frozen_as_traded(tmp_path)]
    with pytest.raises(SystemExit, match=f"no close_as_traded value .* from {start} on"):
        main([*args, "--start", start, "--out", str(tmp_path / "late")])
    assert not (tmp_path / "late").exists()
    assert main([*args, "--out", str(tmp_path / "all")]) == 0  # earlier dates have values


@pytest.mark.parametrize("flag", ["--universe", "--fundamentals"])
@pytest.mark.parametrize("command", ["evaluate", "search", "confirm", "export"])
def test_a_wrong_input_bundle_is_refused_with_a_message(tmp_path, market, command, flag):
    """A market bundle passed as --universe or --fundamentals ends in a message that names
    that flag and path, not a BundleError traceback or the output folder, before the ledger
    or --out is touched."""
    factor, book, out = tmp_path / "f.json", tmp_path / "ledger.jsonl", tmp_path / "out"
    assert main(["freeze", "--expr", "close / open", "--horizon", "1", "--out", str(factor)]) == 0
    args = {
        "evaluate": ["--expr", "close / open", "--horizon", "1", "--ledger", str(book)],
        "search": ["--trials", "5", "--ledger", str(book)],
        "confirm": ["--factor", str(factor), "--confirm-start", "2020-06-01"],
        "export": ["--factor", str(factor)],
    }[command]
    if command == "confirm":
        args += ["--ledger", str(book)]
    with pytest.raises(SystemExit, match=re.escape(f"{flag} {market}: ") + ".*dataset_kind"):
        main([command, "--data", str(market), *args, flag, str(market), "--out", str(out)])
    assert not book.exists() and not out.exists()


@pytest.mark.parametrize("flag", ["--universe", "--fundamentals"])
@pytest.mark.parametrize("evidence", ["--confirmation", "--from-search"])
def test_export_with_evidence_names_a_wrong_input_bundle(tmp_path, market, evidence, flag):
    """INV-PR51-O1 on the evidence path: an export with evidence reads --universe and
    --fundamentals once for the evidence and the scores, and a bundle of another kind is
    named there by its flag and path too, not by the output folder."""
    factor, out = tmp_path / "f.json", tmp_path / "out"
    assert main(["freeze", "--expr", "close / open", "--horizon", "1", "--out", str(factor)]) == 0
    if evidence == "--confirmation":
        # The bundles are read before the confirmation folder, so none is needed here.
        args = ["--factor", str(factor), "--confirmation", str(tmp_path / "conf")]
    else:
        loaded = FrozenFactor.load(factor)
        root = tmp_path / "search"
        loaded.save(root / "factors" / f"{loaded.factor_id}.json")
        pd.DataFrame({"factor_id": [loaded.factor_id]}).to_csv(
            root / "confirmation.csv", index=False
        )
        (root / "config.json").write_text(json.dumps({}), encoding="utf-8")
        args = ["--from-search", str(root)]
    with pytest.raises(SystemExit, match=re.escape(f"{flag} {market}: ") + ".*dataset_kind"):
        main(["export", "--data", str(market), *args, flag, str(market), "--out", str(out)])
    assert not out.exists()


# ---------------------------------------------------------------------------
# Reserved data stays unread until the ledger allows the plan


def _reserved_pair(tmp_path, cut_at: int = 100) -> str:
    """Two bundles with the same dates and names: no as-traded close at all in "absent",
    and one only from session ``cut_at`` on in "reserved"; that session's date."""
    bars = synthetic_market(SyntheticConfig(n_instruments=25, n_days=200, seed=5))
    cut = pd.Timestamp(sorted(bars["date"].unique())[cut_at])
    _publish(bars.assign(close_as_traded=np.nan), tmp_path / "absent")
    bars.loc[bars["date"] < cut, "close_as_traded"] = np.nan
    _publish(bars, tmp_path / "reserved")
    return str(cut.date())


@pytest.mark.parametrize("command", ["evaluate", "confirm"])
def test_a_refused_plan_tells_nothing_about_reserved_as_traded_values(tmp_path, command):
    """Whether reserved rows hold an as-traded close is reserved data too. A plan the ledger
    refuses gets the ledger's refusal, the same for both bundles, so the answer cannot tell
    them apart; a plan it allows still gets the missing-value message (INV-PR51-001)."""
    start = _reserved_pair(tmp_path)
    reserved = tmp_path / "reserved.jsonl"
    assert main(["ledger", "reserve", "--ledger", str(reserved), "--start", start]) == 0
    if command == "evaluate":
        # Every session is read, the reserved ones too.
        refused = ["evaluate", "--expr", "cs_rank(-close_as_traded)", "--horizon", "1"]
        allowed, book, says = refused, tmp_path / "empty.jsonl", "overlaps the reserved"
    else:
        factor = _frozen_as_traded(tmp_path)
        early = str((pd.Timestamp(start) - pd.Timedelta(days=30)).date())
        refused = ["confirm", "--factor", factor, "--confirm-start", early]
        allowed = ["confirm", "--factor", factor, "--confirm-start", start]
        book, says = tmp_path / "allowed.jsonl", "starts before the reserved window"
        assert main(["ledger", "reserve", "--ledger", str(book), "--start", start]) == 0
    before = reserved.read_bytes()
    answers = []
    for side in ("absent", "reserved"):
        out = tmp_path / f"refused-{side}"
        with pytest.raises(SystemExit) as stop:
            main(
                [
                    *refused,
                    "--data",
                    str(tmp_path / side),
                    "--ledger",
                    str(reserved),
                    "--out",
                    str(out),
                ]
            )
        answers.append(str(stop.value.code))
        assert reserved.read_bytes() == before and not out.exists()
    assert answers[0] == answers[1] and says in answers[0]
    allowed_before = book.read_bytes() if book.exists() else None
    out = tmp_path / "allowed-absent"
    with pytest.raises(SystemExit, match="no close_as_traded value"):
        main(
            [*allowed, "--data", str(tmp_path / "absent"), "--ledger", str(book), "--out", str(out)]
        )
    assert (book.read_bytes() if book.exists() else None) == allowed_before and not out.exists()
    out = tmp_path / "allowed-reserved"
    assert (
        main(
            [
                *allowed,
                "--data",
                str(tmp_path / "reserved"),
                "--ledger",
                str(book),
                "--out",
                str(out),
            ]
        )
        == 0
    )


# ---------------------------------------------------------------------------
# A changed proposal stream is a new experiment


def test_a_new_search_version_gets_a_new_experiment_id(tmp_path, market, monkeypatch):
    """The scale check changed which formulas a seed draws; an experiment id that ignores
    that would let one search's confirmation output vouch for another's family."""
    import invest_mining.cli as cli

    args = ["search", "--data", str(market), "--trials", "10", "--seed", "0", "--top-k", "2"]
    ids = []
    for version in ("old", "new"):
        monkeypatch.setattr(cli, "SEARCH_VERSION", version, raising=False)
        out = tmp_path / version
        assert main([*args, "--out", str(out)]) == 0
        experiment = json.loads((out / "config.json").read_text())["experiment"]
        assert experiment["identity"]["search_version"] == version
        ids.append(experiment["experiment_id"])
    assert ids[0] != ids[1]


# ---------------------------------------------------------------------------
# Bad or very long formulas get a message, never a traceback


def test_freeze_refuses_an_unknown_feature_with_a_message(tmp_path):
    with pytest.raises(SystemExit, match="--expr: unknown feature 'foo'"):
        main(["freeze", "--expr", "foo", "--horizon", "1", "--out", str(tmp_path / "f.json")])
    assert not (tmp_path / "f.json").exists()


@pytest.mark.parametrize("terms", [250, 990])
def test_freeze_refuses_a_formula_too_long_to_save(tmp_path, terms):
    """The factor file stores the canonical text, which nests one pair of parentheses per
    operator; Python parses at most 200 levels, so such a file could not be read again."""
    text = " + ".join(["close / open"] * terms)
    out = tmp_path / "f" / "f.json"
    with pytest.raises(SystemExit, match=r"--expr: .*nested too deeply"):
        main(["freeze", "--expr", text, "--horizon", "1", "--out", str(out)])
    assert not out.parent.exists()


@pytest.mark.parametrize(
    "text",
    [
        " + ".join(["close / open"] * (ex.MAX_DEPTH + 1)),
        " + ".join(["close / open"] * 2000),
        # CPython's own parser raises MemoryError when its stack overflows.
        "-" * 20000 + "close",
        "close" + " ** close" * 5000,
    ],
    ids=["151-terms", "2000-terms", "unary-minus", "powers"],
)
def test_a_formula_too_deep_to_parse_is_refused(text):
    with pytest.raises(ex.ExpressionError, match="nested too deeply"):
        ex.parse(text)


def test_the_deepest_formula_the_parser_takes_is_saved_read_and_scored(tmp_path, market):
    """Every tool takes what the parser takes: the factor file reads again, ``confirm`` and
    ``export`` get its lookback, and evaluation does not run out of stack (Python 3.11)."""
    text = " + ".join(["close / open"] * ex.MAX_DEPTH)
    assert ex._fold(ex.parse(text), ex._nesting) == ex.MAX_DEPTH
    factor = tmp_path / "f.json"
    assert main(["freeze", "--expr", text, "--horizon", "1", "--out", str(factor)]) == 0
    assert FrozenFactor.load(factor).lookback == 0
    args = ["export", "--data", str(market), "--factor", str(factor)]
    assert main([*args, "--out", str(tmp_path / "s")]) == 0
    args = ["evaluate", "--data", str(market), "--expr", text, "--horizon", "1"]
    assert main([*args, "--out", str(tmp_path / "e")]) == 0


def test_evaluate_refuses_a_formula_too_deep_to_parse(tmp_path, market):
    text = " + ".join(["close / open"] * 2000)
    args = ["evaluate", "--data", str(market), "--expr", text, "--horizon", "1"]
    with pytest.raises(SystemExit, match=r"--expr: .*nested too deeply"):
        main([*args, "--out", str(tmp_path / "e")])
    assert not (tmp_path / "e").exists()
