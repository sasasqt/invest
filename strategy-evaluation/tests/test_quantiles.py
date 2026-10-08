import gzip
import json

import numpy as np
import pandas as pd
import pytest

from invest_data.schemas import publish_market_bars, publish_signals
from invest_data.sources import SYNTHETIC_METADATA, SyntheticConfig, synthetic_market
from invest_evaluation.cli import main
from invest_evaluation.config import BacktestConfig, CostModel, ExecutionConfig, StrategyConfig
from invest_evaluation.engine import run_backtest
from invest_evaluation.quantiles import (
    QUANTILE_REPORT_VERSION,
    QuantileConfig,
    bucket_portfolios,
    run_quantile_portfolios,
    save_quantile_run,
)
from invest_evaluation.strategies import BucketStrategy, Slice


def two_name_market() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=6)
    a_open = [10, 10, 10, 11, 12, 12]
    a_close = [10, 10, 10.5, 11.5, 12, 13]
    rows = []
    for k, d in enumerate(dates):
        lo, hi = min(a_open[k], a_close[k]), max(a_open[k], a_close[k])
        rows.append([d, "A", a_open[k], hi, lo, a_close[k], 1e9])
        rows.append([d, "B", 20.0, 20.0, 20.0, 20.0, 1e9])
    return pd.DataFrame(
        rows, columns=["date", "instrument", "open", "high", "low", "close", "volume"]
    ).astype({"open": float, "high": float, "low": float, "close": float})


def free_config(**strategy) -> BacktestConfig:
    return BacktestConfig(
        strategy=StrategyConfig(**{"rebalance_every": 100, "min_names": 1, **strategy}),
        execution=ExecutionConfig(max_participation=1.0, min_price=0.0),
        costs=CostModel(
            commission_bps=10, half_spread_bps=0, impact_coef=0, borrow_bps_annual=0,
            adv_window=1, vol_window=2,
        ),
        initial_capital=1000.0,
    )  # fmt: skip


def scores(values: dict[str, float]) -> pd.Series:
    return pd.Series(values, dtype=float, name="score")


@pytest.mark.parametrize(
    ("kind", "value", "n"),
    [("middle", 1, 10), ("bucket", 0, 10), ("bucket", 11, 10), ("bucket", 1.5, 10),
     ("top", 0.0, 10), ("top", 0.6, 10), ("bottom", np.nan, 10), ("bucket", 1, 1),
     ("top", True, 10)],
)  # fmt: skip
def test_invalid_slices_are_rejected(kind, value, n):
    with pytest.raises(ValueError):
        Slice(kind, value, n)


def held(long: Slice, s: pd.Series) -> set[str]:
    strategy = BucketStrategy(long, None, gross_leverage=1.0, min_names=1, min_names_per_bucket=1)
    return set(strategy.target_weights(s).index)


def test_bucket_strategy_keeps_ties_in_one_bucket():
    # Ten names, four tied at the top: average rank 8.5 -> q = 0.25 -> bucket 11 - 3 = 8,
    # the mirror of four names tied at the bottom (p = 0.25 -> bucket 3).
    s = scores({**{f"N{i}": float(i) for i in range(6)}, **{f"T{i}": 9.0 for i in range(4)}})
    w = BucketStrategy(
        Slice("bucket", 8, 10), None, gross_leverage=1.0, min_names=1, min_names_per_bucket=1
    ).target_weights(s)
    assert sorted(w.index) == ["T0", "T1", "T2", "T3"] and w.sum() == pytest.approx(1.0)
    for k in (9, 10):  # nobody is split off by instrument id
        assert held(Slice("bucket", k, 10), s) == set()
    assert held(Slice("bucket", 3, 10), -s) == {"T0", "T1", "T2", "T3"}


@pytest.mark.parametrize("n", [28, 87, 95, 100, 255])
def test_deciles_are_symmetric_and_end_buckets_equal_the_tails(n):
    s = scores({f"N{i:03d}": float(i) for i in range(n)})
    members = {k: held(Slice("bucket", k, 10), s) for k in range(1, 11)}
    counts = [len(members[k]) for k in range(1, 11)]
    # 28 names: 2, 3, ..., 3, 2. With odd n the median name sits in one middle bucket.
    median_bucket = next(k for k in members if f"N{(n - 1) // 2:03d}" in members[k])
    mirrored = [c - int(n % 2 == 1 and k + 1 == median_bucket) for k, c in enumerate(counts)]
    assert sum(counts) == n and mirrored == mirrored[::-1]
    assert members[1] == held(Slice("bottom", 0.1), s)
    assert members[10] == held(Slice("top", 0.1), s)
    # Reversing the scores swaps bucket k and 11 - k; only an exact median name (odd n)
    # keeps its bucket.
    median = {f"N{(n - 1) // 2:03d}"} if n % 2 else set()
    for k in range(1, 11):
        assert held(Slice("bucket", k, 10), -s) - median == members[11 - k] - median


@pytest.mark.parametrize(
    ("n", "f", "count"), [(100, 0.07, 7), (100, 0.1, 10), (250, 0.01, 2), (250, 0.05, 12)]
)
def test_top_and_bottom_tails_hold_the_same_number_of_names(n, f, count):
    # p > 1 - f held 8 names for f = 0.07 (float rounding) and one name more than the
    # bottom tail whenever f * n is fractional (250 names: 3 vs 2 at 1%, 13 vs 12 at 5%).
    s = scores({f"N{i:03d}": float(i) for i in range(n)})
    top, bottom = held(Slice("top", f), s), held(Slice("bottom", f), s)
    assert len(top) == len(bottom) == count
    assert top == {f"N{i:03d}" for i in range(n - count, n)}


@pytest.mark.parametrize("seed", range(5))
def test_top_tail_is_the_bottom_tail_of_reversed_scores(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(10, 300))
    s = scores({f"N{i}": float(v) for i, v in enumerate(rng.integers(0, max(3, n // 5), n))})
    for f in (0.01, 0.05, 0.07, 0.1, 0.25, 0.5):
        assert held(Slice("top", f), s) == held(Slice("bottom", f), -s)
        assert not held(Slice("top", f), s) & held(Slice("bottom", f), s)


def test_bucket_strategy_refuses_small_buckets_and_cross_sections():
    s = scores({f"N{i}": float(i) for i in range(20)})
    long_short = BucketStrategy(
        Slice("top", 0.2, 10),
        Slice("bottom", 0.2, 10),
        gross_leverage=2.0,
        min_names=1,
        min_names_per_bucket=4,
    )
    w = long_short.target_weights(s)
    assert (w > 0).sum() == 4 and (w < 0).sum() == 4
    assert w[w > 0].sum() == pytest.approx(1.0) and w[w < 0].sum() == pytest.approx(-1.0)
    assert sorted(w[w > 0].index) == ["N16", "N17", "N18", "N19"]
    strict = BucketStrategy(
        Slice("top", 0.2, 10), None, gross_leverage=1.0, min_names=1, min_names_per_bucket=5
    )
    assert strict.target_weights(s).empty  # 4 names < 5: hold nothing, not 4 names
    # Fewer names than buckets: no decision, as the factor diagnostics skip such dates.
    assert long_short.target_weights(s.iloc[:9]).empty
    assert long_short.target_weights(s.where(s > 10)).empty  # NaN scores are ignored


def test_hand_calculated_bucket_portfolio():
    bars = two_name_market()
    signals = pd.DataFrame(
        {
            "decision_date": [pd.Timestamp("2024-01-03")] * 2,
            "instrument": ["A", "B"],
            "score": [2.0, 1.0],
        }
    )
    strategy = BucketStrategy(
        Slice("bucket", 2, 2), None, gross_leverage=1.0, min_names=1, min_names_per_bucket=1
    )
    assert run_backtest(bars, signals, free_config(), strategy).decisions.empty  # off by default
    res = run_backtest(bars, signals, free_config(), strategy, record_decisions=True)
    # Decide after the close of 2024-01-03; buy A (upper bucket) at the next open (11).
    shares, cost = 1000.0 / 11.0, 1000.0 * 10 / 1e4
    eq = res.daily["equity"]
    assert eq.loc["2024-01-04"] == pytest.approx(1000.0 - cost + shares * (11.5 - 11))
    assert eq.loc["2024-01-08"] == pytest.approx(1000.0 - cost + shares * (13 - 11))
    assert res.trades["instrument"].tolist() == ["A"]
    d = res.decisions
    assert d["instrument"].tolist() == ["A", "B"] and d["weight"].tolist() == [1.0, 0.0]
    assert (d["decision_date"] == pd.Timestamp("2024-01-03")).all()


def test_portfolio_list_separates_deciles_and_overlapping_tails():
    names = [p.name for p in bucket_portfolios(QuantileConfig(tail_fractions=(0.1, 0.05)))]
    assert names[:10] == [f"q{k}" for k in range(1, 11)]
    assert names[10:] == [
        "top_0.05", "bottom_0.05", "top_minus_bottom_0.05",
        "top_0.1", "bottom_0.1", "top_minus_bottom_0.1",
    ]  # fmt: skip


def test_close_tail_fractions_keep_distinct_reports_and_return_series(
    tmp_path, market, reversal_signals
):
    cfg = BacktestConfig()
    qcfg = QuantileConfig(n_buckets=2, tail_fractions=(0.1, 0.10000001), min_names_per_bucket=1)
    result = run_quantile_portfolios(market, reversal_signals, cfg, qcfg)
    assert result.table["portfolio"].is_unique
    assert len(result.table) == len(result.returns.columns) == 8
    for row in result.table.itertuples():
        returns = result.returns[row.portfolio].dropna()
        cagr = (1 + returns).prod() ** (cfg.annualization / len(returns)) - 1
        assert cagr == pytest.approx(row.net_cagr)
    out = save_quantile_run(tmp_path / "q", result, provenance={})
    table = pd.read_csv(out / "tables/portfolios.csv")
    returns = pd.read_csv(out / "tables/daily_returns.csv.gz", index_col=0)
    assert table["portfolio"].tolist() == returns.columns.tolist()
    assert {"top_0.1", "top_0.10000001"} <= set(returns.columns)


@pytest.mark.parametrize(
    "kwargs",
    [{"n_buckets": 1}, {"tail_fractions": (0.6,)}, {"tail_fractions": (0.1, 0.1)},
     {"tail_fractions": "0.1"}, {"min_names_per_bucket": 0}],
)  # fmt: skip
def test_invalid_quantile_config(kwargs):
    with pytest.raises(ValueError):
        QuantileConfig(**kwargs)


def test_quantile_portfolios_report_small_samples(market, reversal_signals):
    cfg = BacktestConfig(strategy=StrategyConfig(min_names=10))
    q = QuantileConfig(tail_fractions=(0.05, 0.1), min_names_per_bucket=2)
    res = run_quantile_portfolios(market, reversal_signals, cfg, q)
    t = res.table.set_index("portfolio")
    # 28 to 30 eligible names: deciles hold 2 or 3, each 5% tail holds only 1.
    assert (t.loc[[f"q{k}" for k in range(1, 11)], "status"] == "ok").all()
    for name in ("top_0.05", "bottom_0.05", "top_minus_bottom_0.05"):
        assert t.loc[name, "status"] == "insufficient_data"
        assert pd.isna(t.loc[name, "net_sharpe"]) and pd.isna(t.loc[name, "net_cagr"])
        assert t.loc[name, "insufficient_decisions"] == t.loc[name, "decisions_with_cross_section"]
    # The 10% tails are the end deciles under one rule, and they mirror each other.
    assert t.loc["top_0.1", "net_cagr"] == pytest.approx(t.loc["q10", "net_cagr"])
    assert t.loc["bottom_0.1", "net_cagr"] == pytest.approx(t.loc["q1", "net_cagr"])
    for f in (0.05, 0.1):
        assert t.loc[f"top_{f}", "mean_names"] == t.loc[f"bottom_{f}", "mean_names"]
        assert t.loc[f"top_{f}", "min_names"] == t.loc[f"bottom_{f}", "min_names"]
    # Deciles partition each decision's eligible names.
    m = res.memberships
    assert m.groupby("decision_date")["bucket"].nunique().eq(10).all()
    assert len(m) == len(m.drop_duplicates(["decision_date", "instrument"]))
    assert res.returns.shape[1] == len(t)


def test_constant_signals_fill_one_bucket_and_leave_the_rest_empty(market, reversal_signals):
    flat = reversal_signals.assign(score=1.0)
    q = QuantileConfig(tail_fractions=(0.1,), min_names_per_bucket=1)
    t = run_quantile_portfolios(market, flat, BacktestConfig(), q).table.set_index("portfolio")
    # Every name ties: p = (n + 1) / (2n), just above 0.5, so all names sit in bucket 6.
    assert t.loc["q6", "status"] == "ok" and t.loc["q6", "min_names"] >= 28
    others = t.drop(index="q6")
    assert (others["status"] == "insufficient_data").all()
    assert (others["min_names"] == 0).all()


def test_future_data_cannot_change_earlier_bucket_holdings(market, reversal_signals):
    cfg = BacktestConfig(strategy=StrategyConfig(min_names=10))
    q = QuantileConfig(tail_fractions=(0.1,), min_names_per_bucket=2)
    cut = pd.Timestamp(sorted(market["date"].unique())[180])
    base = run_quantile_portfolios(market, reversal_signals, cfg, q)
    later = reversal_signals["decision_date"] > cut
    changed_signals = reversal_signals.assign(
        score=reversal_signals["score"].where(~later, -reversal_signals["score"])
    )
    future_bars = market["date"] > cut
    changed_bars = market.assign(
        open=market["open"].where(~future_bars, market["open"] * 1.5),
        close=market["close"].where(~future_bars, market["close"] * 0.5),
    )
    for bars, sig in ((market, changed_signals), (changed_bars, reversal_signals)):
        other = run_quantile_portfolios(bars, sig, cfg, q)
        early = base.memberships["decision_date"] <= cut
        pd.testing.assert_frame_equal(
            base.memberships[early].reset_index(drop=True),
            other.memberships[other.memberships["decision_date"] <= cut].reset_index(drop=True),
        )
        pd.testing.assert_frame_equal(base.returns.loc[:cut], other.returns.loc[:cut])


def test_cli_quantiles_writes_versioned_report(tmp_path, market, reversal_signals, capsys):
    publish_market_bars(market, tmp_path / "m", dataset_id="m", metadata=SYNTHETIC_METADATA)
    publish_signals(
        reversal_signals,
        tmp_path / "s",
        dataset_id="s",
        metadata={"factor_id": "rev5", "horizon_days": 1},
    )
    out = tmp_path / "q"
    args = ["quantiles", "--data", str(tmp_path / "m"), "--signals", str(tmp_path / "s")]
    assert main([*args, "--out", str(out), "--min-names-per-bucket", "2"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["portfolios"] == 19
    assert "top_0.01" in printed["insufficient_data"] and "q1" not in printed["insufficient_data"]
    report = json.loads((out / "quantiles.json").read_text())
    assert report["report_version"] == QUANTILE_REPORT_VERSION
    assert report["settings"] == {
        "n_buckets": 10, "tail_fractions": [0.01, 0.05, 0.1], "min_names_per_bucket": 2,
    }  # fmt: skip
    assert len(report["portfolios"]) == 19
    for name in ("config.json", "manifest.json", "report.md", "figures/quantile_portfolios.png"):
        assert (out / name).is_file()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["signals"]["id"] == "s" and "code_revision" in manifest
    with gzip.open(out / "tables" / "memberships.csv.gz", "rt") as fh:
        assert fh.readline().strip() == "decision_date,instrument,score,pct,pct_from_top,bucket"
    assert "insufficient_data" in (out / "report.md").read_text()
    with pytest.raises(SystemExit):
        main([*args, "--out", str(tmp_path / "bad"), "--tails", "0.7"])
    with pytest.raises(SystemExit, match="not an empty directory"):
        main([*args, "--out", str(out)])


def test_memberships_are_computed_once_and_checked_against_every_portfolio():
    from invest_evaluation.quantiles import _membership_for

    d = pd.DataFrame(
        {
            "decision_date": pd.to_datetime(["2024-01-02"] * 3 + ["2024-01-03"] * 3),
            "instrument": ["A", "B", "C"] * 2,
            "score": [3.0, 1.0, 2.0, 1.0, 2.0, 3.0],
        }
    )
    current, member = _membership_for(None, d.iloc[:3], 2)  # an insolvent first run
    assert len(current) == len(member) == 3
    current, member = _membership_for(member, d, 2)  # a longer run replaces it
    assert len(current) == len(member) == 6
    assert member["pct_from_top"].tolist() == pytest.approx([1 / 3, 1, 2 / 3, 1, 2 / 3, 1 / 3])
    current, kept = _membership_for(member, d.iloc[:3], 2)
    assert kept is member and len(current) == 3
    with pytest.raises(RuntimeError, match="different decision-time eligible names"):
        _membership_for(member, d.assign(score=d["score"].where(d.index != 4, 9.0)), 2)
    with pytest.raises(RuntimeError, match="different decision-time eligible names"):
        _membership_for(member.iloc[:3].assign(instrument=["A", "C", "B"]), d, 2)


def test_tail_masks_use_their_own_percentiles_and_json_values_are_plain():
    from invest_evaluation.reporting import finite

    pct = pd.Series([0.5, 1.0])
    assert Slice("bottom", 0.5).mask(pct, 1 + 1 / 2 - pct).tolist() == [True, False]
    assert Slice("top", 0.5).mask(pct, 1 + 1 / 2 - pct).tolist() == [False, True]
    out = finite({"a": [np.bool_(True), np.int64(2), np.float64("nan"), np.float32(0.5)]})
    assert out == {"a": [True, 2, None, 0.5]}
    assert [type(v) for v in out["a"]] == [bool, int, type(None), float]


def test_twenty_five_bucket_report_does_not_discard_boundary_names():
    bars = synthetic_market(SyntheticConfig(n_instruments=125, n_days=35, listing_churn=0, seed=13))
    signals = bars[["date", "instrument"]].rename(columns={"date": "decision_date"})
    names = sorted(signals["instrument"].unique())
    score_by_name = dict(zip(names, range(125), strict=True))
    signals["score"] = signals["instrument"].map(score_by_name).astype(float)
    cfg = BacktestConfig(costs=CostModel(adv_window=1, vol_window=2))
    result = run_quantile_portfolios(
        bars, signals, cfg, QuantileConfig(n_buckets=25, tail_fractions=())
    )
    # Every bucket should hold five names. Previously 0.28 * 25 rounded above seven,
    # shrinking q7/q19 to four and falsely withholding their performance.
    assert result.table["min_names"].eq(5).all()
    assert result.table["status"].eq("ok").all()
    assert result.table["net_cagr"].notna().all()
    members = result.memberships
    assert members.groupby(["decision_date", "bucket"]).size().eq(5).all()
    s = scores(score_by_name)
    assert held(Slice("bucket", 19, 25), s) == set(names[90:95])


def _saved_quantile_run(tmp_path, long_short_status, long_short_reason):
    """A saved report whose q10 has no CAGR and whose long-short is not ok."""
    from invest_evaluation.quantiles import render_quantiles

    root = tmp_path / "run"
    (root / "tables").mkdir(parents=True)
    (root / "figures").mkdir()
    rows = [
        {
            "portfolio": f"q{k}",
            "kind": "bucket",
            "status": "ok" if k != 10 else "invalid_input",
            "reason": None if k != 10 else "insolvent_wealth_path",
            "gross_cagr": 0.05 if k != 10 else None,
            "net_cagr": 0.04 if k != 10 else None,
        }
        for k in range(1, 11)
    ]
    rows.append(
        {
            "portfolio": "top_minus_bottom_0.1",
            "kind": "long_short",
            "status": long_short_status,
            "reason": long_short_reason,
            "gross_cagr": None,
            "net_cagr": None,
        }
    )
    filler = dict.fromkeys(
        [
            "mean_names",
            "net_sharpe",
            "net_sharpe_ci_low",
            "net_sharpe_ci_high",
            "max_drawdown",
            "turnover_one_way_annual",
            "cost_drag_annual",
        ]
    )
    report = {
        "report_version": QUANTILE_REPORT_VERSION,
        "settings": {"min_names_per_bucket": 5},
        "membership_rule": "",
        "min_cross_section": 10,
        "note": "",
        "portfolios": [{**filler, **row} for row in rows],
    }
    (root / "quantiles.json").write_text(json.dumps(report))
    pd.DataFrame({"q1": [0.0]}, index=pd.bdate_range("2024-01-01", periods=1)).to_csv(
        root / "tables" / "daily_returns.csv.gz"
    )
    return root, render_quantiles


@pytest.mark.parametrize(
    ("status", "reason"),
    [("insufficient_data", "fewer_than_5_names"), ("invalid_input", "insolvent_wealth_path")],
)
def test_quantile_figure_draws_no_bar_for_a_missing_cagr_and_names_each_status(
    tmp_path, monkeypatch, status, reason
):
    """K6: a missing CAGR is not a 0% bar, and a skipped long-short shows its own status."""
    from matplotlib.axes import Axes

    calls = []
    for method in ("bar", "text"):
        original = getattr(Axes, method)

        def spy(ax, *args, _original=original, _method=method, **kwargs):
            calls.append((_method, args))
            return _original(ax, *args, **kwargs)

        monkeypatch.setattr(Axes, method, spy)
    root, render_quantiles = _saved_quantile_run(tmp_path, status, reason)
    render_quantiles(root)
    heights = [np.asarray(args[1], dtype=float) for method, args in calls if method == "bar"]
    assert len(heights) == 2
    assert all(np.isnan(h[9]) and (h[:9] > 0).all() for h in heights)
    texts = [str(args[2]) for method, args in calls if method == "text"]
    assert any("n/a (insolvent_wealth_path)" in t for t in texts)  # the q10 label
    assert any(f"top_minus_bottom_0.1 ({status})" in t for t in texts)
    if status != "insufficient_data":
        assert not any("insufficient_data" in t for t in texts)
    report = (root / "report.md").read_text()
    assert "| q10 | invalid_input (insolvent_wealth_path) |" in report
    assert f"| top_minus_bottom_0.1 | {status} ({reason}) |" in report
