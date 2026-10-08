import json
import math
from statistics import NormalDist

import numpy as np
import pandas as pd
import pytest

from invest_data.schemas import publish_market_bars, publish_signals
from invest_data.sources import SYNTHETIC_METADATA
from invest_evaluation.cli import main
from invest_evaluation.stats import (
    bootstrap_ci,
    deflated_sharpe,
    expected_max_sharpe,
    newey_west_mean,
    probabilistic_sharpe,
    stationary_bootstrap_indices,
)


def test_stationary_bootstrap_indices_are_reproducible_blocks():
    a = stationary_bootstrap_indices(100, 10.0, 50, np.random.default_rng(1))
    b = stationary_bootstrap_indices(100, 10.0, 50, np.random.default_rng(1))
    assert np.array_equal(a, b) and a.shape == (50, 100)
    continued = (np.diff(a, axis=1) % 100 == 1).mean()
    assert 0.85 < continued < 0.95  # restart probability 1/10


def test_bootstrap_ci_covers_point_estimate():
    r = pd.Series(np.random.default_rng(0).normal(0.001, 0.01, 500))
    ci = bootstrap_ci(r, 252, n_boot=500)
    sr = r.mean() / r.std() * math.sqrt(252)
    assert ci["sharpe_ci"][0] < sr < ci["sharpe_ci"][1]
    assert bootstrap_ci(r[:20], 252)["status"] == "insufficient_data"


def test_probabilistic_and_deflated_sharpe():
    r = pd.Series(np.random.default_rng(3).normal(0.0008, 0.01, 750))
    psr = probabilistic_sharpe(r)
    x = r.to_numpy()
    sr = x.mean() / x.std(ddof=1)
    m = x - x.mean()
    g3 = np.mean(m**3) / np.mean(m**2) ** 1.5
    g4 = np.mean(m**4) / np.mean(m**2) ** 2
    z = sr * math.sqrt(len(x) - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr**2)
    assert psr["psr"] == pytest.approx(NormalDist().cdf(z))
    assert expected_max_sharpe(1000, 0.01) > expected_max_sharpe(10, 0.01) > 0
    assert deflated_sharpe(r, 1000)["dsr"] < deflated_sharpe(r, 10)["dsr"] < psr["psr"]


def test_newey_west_mean():
    x = np.random.default_rng(0).normal(0, 1, 200)
    out = newey_west_mean(x, lags=0)
    assert out["se"] == pytest.approx(x.std(ddof=0) / math.sqrt(200))
    assert newey_west_mean(x[:10])["status"] == "insufficient_data"


def test_cli_run_writes_complete_report(tmp_path, market, reversal_signals, capsys):
    publish_market_bars(market, tmp_path / "m", dataset_id="m", metadata=SYNTHETIC_METADATA)
    publish_signals(
        reversal_signals,
        tmp_path / "s",
        dataset_id="s",
        metadata={"factor_id": "rev5", "horizon_days": 1, "n_trials": 37},
    )
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"strategy": {"rebalance_every": 5}, "costs": {"impact_coef": 0.3}}))
    assert (
        main(
            [
                "run",
                "--data",
                str(tmp_path / "m"),
                "--signals",
                str(tmp_path / "s"),
                "--config",
                str(cfg),
                "--out",
                str(tmp_path / "run"),
                "--n-trials",
                "20",
            ]
        )
        == 0
    )
    run = tmp_path / "run"
    for rel in (
        "metrics.json",
        "statistics.json",
        "config.json",
        "manifest.json",
        "report.md",
        "tables/daily.csv",
        "tables/trades.csv",
        "tables/episodes.csv",
        "tables/scenarios.csv",
        "figures/equity_drawdown.png",
        "figures/diagnostics.png",
        "figures/scenarios.png",
    ):
        assert (run / rel).exists(), rel
    metrics = json.loads((run / "metrics.json").read_text())
    assert metrics["performance"]["sharpe"]["status"] == "ok"
    assert json.loads((run / "config.json").read_text())["costs"]["impact_coef"] == 0.3
    assert "Deflated Sharpe" in (run / "report.md").read_text()
    assert json.loads((run / "manifest.json").read_text())["n_trials"] == 20
    assert json.loads((run / "statistics.json").read_text())["deflated_sharpe"]["n_trials"] == 20
    with pytest.raises(SystemExit, match="not an empty directory"):
        main(
            [
                "run",
                "--data",
                str(tmp_path / "m"),
                "--signals",
                str(tmp_path / "s"),
                "--out",
                str(run),
                "--no-scenarios",
            ]
        )
    capsys.readouterr()


def test_sharpe_statistics_use_the_configured_excess_return_basis():
    from invest_evaluation.metrics import period_rate, return_metrics
    from invest_evaluation.stats import strategy_statistics

    annual = 0.10
    rf = period_rate(annual, 252)
    returns = pd.Series(rf + np.random.default_rng(0).normal(0, 0.0001, 252))
    stats = strategy_statistics(returns, 252, risk_free_annual=annual)
    metric = return_metrics(returns, v0=1000, annualization=252, risk_free_annual=annual)
    low, high = stats["bootstrap"]["sharpe_ci"]
    assert low < metric["sharpe"].value < high
    expected_psr = probabilistic_sharpe(returns - rf)
    assert stats["probabilistic_sharpe_vs_zero"] == expected_psr
    assert stats["deflated_sharpe"] == deflated_sharpe(returns - rf, 1)
    assert stats["sharpe_basis"] == "excess_returns"
    assert stats["risk_free_annual"] == annual


def test_flat_bootstrap_is_explicitly_undefined():
    with np.errstate(all="raise"):
        out = bootstrap_ci(pd.Series(np.zeros(65)), 252)
    assert out["status"] == "undefined"
    assert out["reason"] == "zero_excess_return_dispersion"
    assert out["sharpe_ci"] is None and out["share_sharpe_le_0"] is None
    assert out["valid_sharpe_replications"] == 0
    assert out["annual_mean_ci"] == [0.0, 0.0]


def test_cli_saves_flat_portfolio_and_undefined_statistics(tmp_path):
    dates = pd.bdate_range("2024-01-01", periods=65)
    bars = pd.DataFrame(
        [(d, "A", 10.0, 10.0, 10.0, 10.0, 1e9, 10.0) for d in dates],
        columns=["date", "instrument", "open", "high", "low", "close", "volume", "close_as_traded"],
    )
    signals = pd.DataFrame({"decision_date": [dates[0]], "instrument": ["A"], "score": [1.0]})
    publish_market_bars(bars, tmp_path / "data", dataset_id="flat", metadata=SYNTHETIC_METADATA)
    publish_signals(
        signals,
        tmp_path / "signals",
        dataset_id="s",
        metadata={"factor_id": "constant", "horizon_days": 1},
    )
    assert (
        main(
            [
                "run",
                "--data",
                str(tmp_path / "data"),
                "--signals",
                str(tmp_path / "signals"),
                "--out",
                str(tmp_path / "run"),
                "--no-scenarios",
            ]
        )
        == 0
    )
    stats = json.loads((tmp_path / "run" / "statistics.json").read_text())
    assert stats["bootstrap"]["status"] == "undefined"
    assert "n/a (zero_excess_return_dispersion)" in (tmp_path / "run" / "report.md").read_text()
    verdict = json.loads((tmp_path / "run" / "verdict.json").read_text())
    assert verdict["portfolio"]["status"] == "insufficient_data"
    assert verdict["factor"]["status"] == "not_confirmed"


@pytest.mark.parametrize("settlement_price", [8.0, 0.0])
def test_cli_applies_cash_settlements_to_base_and_stress_runs(tmp_path, settlement_price):
    dates = pd.bdate_range("2024-01-01", periods=65)
    bars = pd.DataFrame(
        [(d, "A", 10.0, 10.0, 10.0, 10.0, 1e9, 10.0) for d in dates],
        columns=["date", "instrument", "open", "high", "low", "close", "volume", "close_as_traded"],
    )
    signals = pd.DataFrame({"decision_date": dates, "instrument": "A", "score": 1.0})
    publish_market_bars(bars, tmp_path / "data", dataset_id="m", metadata=SYNTHETIC_METADATA)
    publish_signals(
        signals,
        tmp_path / "signals",
        dataset_id="s",
        metadata={"factor_id": "constant", "horizon_days": 1},
    )
    cfg = tmp_path / "cfg.json"
    cfg.write_text(
        json.dumps(
            {
                "initial_capital": 1000,
                "strategy": {"long_fraction": 1, "short_fraction": 0, "min_names": 1},
                "costs": {
                    "adv_window": 1,
                    "vol_window": 2,
                    "commission_bps": 0,
                    "half_spread_bps": 0,
                    "impact_coef": 0,
                },
            }
        )
    )
    events = [
        {
            "date": dates[40].date().isoformat(),
            "instrument": "A",
            "settlement_price": settlement_price,
        }
    ]
    event_file = tmp_path / "events.json"
    event_file.write_text(json.dumps(events))
    assert (
        main(
            [
                "run",
                "--data",
                str(tmp_path / "data"),
                "--signals",
                str(tmp_path / "signals"),
                "--config",
                str(cfg),
                "--delistings",
                str(event_file),
                "--out",
                str(tmp_path / "run"),
            ]
        )
        == 0
    )
    run = tmp_path / "run"
    trades = pd.read_csv(run / "tables" / "trades.csv")
    settlement = trades[trades["reason"] == "delisted_liquidation"]
    assert len(settlement) == 1 and settlement.iloc[0]["price"] == settlement_price
    daily = pd.read_csv(run / "tables" / "daily.csv")
    assert (daily["n_long"].iloc[40:] == 0).all()
    assert daily["equity"].iloc[40:].nunique() == 1
    assert json.loads((run / "manifest.json").read_text())["delisting_settlements"] == events
    scenarios = pd.read_csv(run / "tables" / "scenarios.csv")
    if settlement_price == 0:
        metrics = json.loads((run / "metrics.json").read_text())["performance"]
        assert metrics["total_return"]["value"] == pytest.approx(-1.0)
        assert metrics["max_drawdown"]["value"] >= 1.0 - 1e-12
        assert metrics["cagr"]["status"] == "invalid_input"
        assert scenarios["cagr"].isna().all()
        assert (scenarios["max_drawdown"] >= 1.0 - 1e-12).all()
        assert "insolvent_wealth_path" in (run / "report.md").read_text()
    else:
        assert (scenarios["cagr"] < 0).all()  # every scenario uses the loss-making settlement


def test_cli_reports_external_benchmark_next_to_equal_weight(
    tmp_path, market, reversal_signals, monkeypatch
):
    from matplotlib.axes import Axes

    curves = []
    original_plot = Axes.plot

    def plot(ax, *args, **kwargs):
        if kwargs.get("label") == "external benchmark":
            curves.append(args[0])
        return original_plot(ax, *args, **kwargs)

    monkeypatch.setattr(Axes, "plot", plot)
    publish_market_bars(market, tmp_path / "m", dataset_id="m", metadata=SYNTHETIC_METADATA)
    publish_signals(
        reversal_signals,
        tmp_path / "s",
        dataset_id="s",
        metadata={"factor_id": "rev5", "horizon_days": 1},
    )
    # A benchmark bundle that starts late: sessions before it have no benchmark return.
    spy = market[market["instrument"] == "SYN003"]
    gap = spy["date"].iloc[100]
    following = spy["date"].iloc[101]
    spy = spy[spy["date"] >= spy["date"].iloc[40]].assign(instrument="SPY")
    spy = spy[spy["date"] != gap]
    publish_market_bars(spy, tmp_path / "b", dataset_id="spy", metadata=SYNTHETIC_METADATA)
    base = [
        "run",
        "--data",
        str(tmp_path / "m"),
        "--signals",
        str(tmp_path / "s"),
        "--no-scenarios",
    ]
    assert main([*base, "--out", str(tmp_path / "run"), "--benchmark", str(tmp_path / "b")]) == 0

    metrics = json.loads((tmp_path / "run" / "metrics.json").read_text())
    ext, ew = metrics["external_benchmark"], metrics["benchmark"]
    assert ext["benchmark_total_return"]["extra"]["benchmark"] == "SPY close-to-close (spy)"
    assert ew["benchmark_total_return"]["extra"]["benchmark"].startswith("universe_equal_weight")
    closes = spy.set_index("date")["close"]
    daily = pd.read_csv(tmp_path / "run" / "tables" / "daily.csv", index_col=0, parse_dates=True)
    expected = closes.reindex(sorted(market["date"].unique())).pct_change(fill_method=None)
    aligned = expected.reindex(daily.index).dropna()
    assert ext["benchmark_total_return"]["extra"]["aligned_sessions"] == len(aligned)
    assert ext["benchmark_total_return"]["value"] == pytest.approx(np.prod(1 + aligned) - 1)
    assert daily["external_benchmark_return"].notna().sum() == len(aligned)
    assert daily.loc[[gap, following], "external_benchmark_return"].isna().all()
    assert curves[0].index[0] == aligned.index[0]  # no invented flat leading history
    assert curves[0].loc[gap:].isna().all()  # no growth path across unknown returns
    assert ext["beta"]["status"] == "ok"
    manifest = json.loads((tmp_path / "run" / "manifest.json").read_text())
    assert manifest["external_benchmark"]["instrument"] == "SPY"
    assert manifest["external_benchmark"]["metadata"] == SYNTHETIC_METADATA
    assert manifest["market_dataset"]["metadata"] == SYNTHETIC_METADATA
    assert "## External Benchmark" in (tmp_path / "run" / "report.md").read_text()
    report = (tmp_path / "run" / "report.md").read_text()
    external_report = report.split("## External Benchmark", 1)[1]
    assert "SPY close-to-close (spy)" in external_report
    assert (
        f"Aligned daily returns: {len(aligned)} of {len(daily)} evaluation sessions"
        in external_report
    )
    no_bench = tmp_path / "plain"
    assert main([*base, "--out", str(no_bench)]) == 0
    assert "external_benchmark" not in json.loads((no_bench / "metrics.json").read_text())
    assert "External Benchmark" not in (no_bench / "report.md").read_text()

    with pytest.raises(SystemExit, match="name one"):
        main([*base, "--out", str(tmp_path / "x"), "--benchmark", str(tmp_path / "m")])
    pick = ["--benchmark", str(tmp_path / "m"), "--benchmark-instrument", "SYN001"]
    assert main([*base, "--out", str(tmp_path / "y"), *pick]) == 0
    with pytest.raises(SystemExit, match="not in bundle"):
        main(
            [
                *base,
                "--out",
                str(tmp_path / "z"),
                "--benchmark",
                str(tmp_path / "b"),
                "--benchmark-instrument",
                "QQQ",
            ]
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency", "EUR"),
        ("price_adjustment", "unadjusted"),
        ("frequency", "1h"),
        ("calendar", "XAMS"),
        ("timezone", "Europe/Amsterdam"),
        ("timezone", None),
    ],
)
def test_cli_rejects_incomparable_benchmark_before_publication(
    tmp_path, market, reversal_signals, field, value
):
    publish_market_bars(market, tmp_path / "m", dataset_id="m", metadata=SYNTHETIC_METADATA)
    publish_signals(
        reversal_signals,
        tmp_path / "s",
        dataset_id="s",
        metadata={"factor_id": "rev5", "horizon_days": 1},
    )
    benchmark = market[market["instrument"] == "SYN003"].assign(instrument="SPY")
    publish_market_bars(
        benchmark, tmp_path / "b", dataset_id="b", metadata={**SYNTHETIC_METADATA, field: value}
    )
    out = tmp_path / "run"
    with pytest.raises(SystemExit, match=f"benchmark {field} mismatch"):
        main(
            [
                "run",
                "--data",
                str(tmp_path / "m"),
                "--signals",
                str(tmp_path / "s"),
                "--benchmark",
                str(tmp_path / "b"),
                "--out",
                str(out),
            ]
        )
    assert not out.exists()


@pytest.mark.parametrize("benchmark_bars", [1, 20])
def test_cli_reports_insufficient_external_benchmark_coverage(
    tmp_path, market, reversal_signals, benchmark_bars
):
    publish_market_bars(market, tmp_path / "m", dataset_id="m", metadata=SYNTHETIC_METADATA)
    publish_signals(
        reversal_signals,
        tmp_path / "s",
        dataset_id="s",
        metadata={"factor_id": "rev5", "horizon_days": 1},
    )
    benchmark = (
        market[market["instrument"] == "SYN003"].tail(benchmark_bars).assign(instrument="SPY")
    )
    publish_market_bars(benchmark, tmp_path / "b", dataset_id="spy", metadata=SYNTHETIC_METADATA)
    out = tmp_path / "run"
    assert (
        main(
            [
                "run",
                "--data",
                str(tmp_path / "m"),
                "--signals",
                str(tmp_path / "s"),
                "--benchmark",
                str(tmp_path / "b"),
                "--out",
                str(out),
                "--no-scenarios",
            ]
        )
        == 0
    )
    daily = pd.read_csv(out / "tables" / "daily.csv")
    aligned = benchmark_bars - 1
    assert daily["external_benchmark_return"].notna().sum() == aligned
    metric = json.loads((out / "metrics.json").read_text())["external_benchmark"]["benchmark"]
    assert metric["status"] == "insufficient_data"
    assert metric["extra"]["aligned_sessions"] == aligned
    assert metric["extra"]["evaluation_sessions"] == len(daily)
    report = (out / "report.md").read_text().split("## External Benchmark", 1)[1]
    assert "SPY close-to-close (spy)" in report
    assert f"Aligned daily returns: {aligned} of {len(daily)} evaluation sessions" in report
    assert "n/a (fewer_than_20_aligned_returns)" in report


def _git(repo, *args):
    import subprocess

    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def test_code_revision_comes_from_the_code_checkout_not_the_working_directory(
    tmp_path, monkeypatch
):
    from invest_evaluation.cli import code_revision

    code, other = tmp_path / "code", tmp_path / "other"
    for repo in (code, other):
        repo.mkdir()
        _git(repo, "init", "-q")
        (repo / "module.py").write_text("x = 1\n")
        _git(repo, "add", "module.py")
        _git(repo, "commit", "-q", "-m", "init")
    monkeypatch.chdir(other)  # run from another repository
    assert code_revision(code / "module.py") == (_git(code, "rev-parse", "HEAD"), False)
    (code / "module.py").write_text("x = 2\n")
    assert code_revision(code / "module.py") == (_git(code, "rev-parse", "HEAD"), True)
    # Code Git does not track there (an installed wheel) or outside any checkout: unknown.
    (code / "installed.py").write_text("")
    assert code_revision(code / "installed.py") == (None, None)
    (tmp_path / "loose.py").write_text("")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    assert code_revision(tmp_path / "loose.py") == (None, None)


@pytest.mark.parametrize("command", ["run", "quantiles"])
@pytest.mark.parametrize(
    ("adjustment", "message"),
    [
        ("unadjusted", "is not supported"),
        ("split_adjusted", "is not supported"),
        ("raw", "is not one of"),  # outside the contract
        (None, "is not one of"),
        (KeyError, r"metadata missing \['price_adjustment'\]"),
    ],
)
def test_cli_refuses_bars_without_total_return_closes(
    tmp_path, market, reversal_signals, command, adjustment, message
):
    """N1: returns from unadjusted closes count a split as a loss, so evaluation refuses them."""
    metadata = {**SYNTHETIC_METADATA, "price_adjustment": "unadjusted"}
    publish_market_bars(market, tmp_path / "m", dataset_id="m", metadata=metadata)
    # Values outside the contract can't be published; older or edited bundles may hold them.
    manifest = json.loads((tmp_path / "m" / "manifest.json").read_text())
    if adjustment is KeyError:
        del manifest["metadata"]["price_adjustment"]
    else:
        manifest["metadata"]["price_adjustment"] = adjustment
    (tmp_path / "m" / "manifest.json").write_text(json.dumps(manifest))
    publish_signals(
        reversal_signals,
        tmp_path / "s",
        dataset_id="s",
        metadata={"factor_id": "rev5", "horizon_days": 1},
    )
    args = [command, "--data", str(tmp_path / "m"), "--signals", str(tmp_path / "s")]
    with pytest.raises(SystemExit, match=message):
        main([*args, "--out", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("command", ["run", "quantiles"])
def test_cli_refuses_min_price_without_as_traded_closes(
    tmp_path, market, reversal_signals, command
):
    """K11: a price level on adjusted closes is look-ahead, so it needs as-traded closes."""
    bars = market.drop(columns="close_as_traded")
    publish_market_bars(bars, tmp_path / "m", dataset_id="m", metadata=SYNTHETIC_METADATA)
    publish_signals(
        reversal_signals,
        tmp_path / "s",
        dataset_id="s",
        metadata={"factor_id": "rev5", "horizon_days": 1},
    )
    args = [command, "--data", str(tmp_path / "m"), "--signals", str(tmp_path / "s")]
    with pytest.raises(SystemExit, match="needs the as-traded close"):
        main([*args, "--out", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()
    # A column with no known value is refused by the backtest, as a clean exit too.
    publish_market_bars(
        market.assign(close_as_traded=float("nan")),
        tmp_path / "n",
        dataset_id="n",
        metadata=SYNTHETIC_METADATA,
    )
    nulls = [command, "--data", str(tmp_path / "n"), "--signals", str(tmp_path / "s")]
    with pytest.raises(
        SystemExit, match="no session in the evaluation window has a positive finite one"
    ):
        main([*nulls, "--out", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"execution": {"min_price": 0}}))
    extra = ["--no-scenarios"] if command == "run" else ["--min-names-per-bucket", "2"]
    assert main([*args, "--config", str(cfg), *extra, "--out", str(tmp_path / "out")]) == 0


def _published(tmp_path, market, reversal_signals):
    publish_market_bars(market, tmp_path / "m", dataset_id="m", metadata=SYNTHETIC_METADATA)
    publish_signals(
        reversal_signals,
        tmp_path / "s",
        dataset_id="s",
        metadata={"factor_id": "rev5", "horizon_days": 1},
    )
    return ["--data", str(tmp_path / "m"), "--signals", str(tmp_path / "s")]


def test_rolling_sharpe_figure_uses_the_risk_free_rate(
    tmp_path, market, reversal_signals, monkeypatch
):
    """N3: the rolling Sharpe uses the same excess-return basis as the reported Sharpe."""
    from matplotlib.axes import Axes

    plotted = []
    original_plot = Axes.plot

    def plot(ax, *args, **kwargs):
        plotted.append((ax, args))
        return original_plot(ax, *args, **kwargs)

    monkeypatch.setattr(Axes, "plot", plot)
    inputs = _published(tmp_path, market, reversal_signals)
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"risk_free_annual": 0.2}))
    run = tmp_path / "run"
    assert main(["run", *inputs, "--config", str(cfg), "--no-scenarios", "--out", str(run)]) == 0
    rolling = [args[0] for ax, args in plotted if ax.get_title().startswith("Rolling")]
    assert len(rolling) == 1
    r = pd.read_csv(run / "tables" / "daily.csv", index_col=0, parse_dates=True)["return"]
    roll = (r - (1.2 ** (1 / 252) - 1)).rolling(126, min_periods=63)
    expected = roll.mean() / roll.std() * math.sqrt(252)
    pd.testing.assert_series_equal(rolling[0], expected, check_names=False)
    assert rolling[0].dropna().iloc[-1] < (r.rolling(126).mean() / r.rolling(126).std()).iloc[
        -1
    ] * math.sqrt(252)


def test_scenario_figure_draws_no_bar_for_an_undefined_sharpe(tmp_path, monkeypatch):
    """K16: an insolvent scenario has no Sharpe; it is labelled, never drawn as 0."""
    from matplotlib.axes import Axes

    from invest_evaluation.reporting import render

    calls = []
    for method in ("barh", "text"):
        original = getattr(Axes, method)

        def spy(ax, *args, _original=original, _method=method, **kwargs):
            calls.append((_method, args))
            return _original(ax, *args, **kwargs)

        monkeypatch.setattr(Axes, method, spy)
    root = tmp_path / "run"
    (root / "tables").mkdir(parents=True)
    (root / "figures").mkdir()
    idx = pd.bdate_range("2024-01-01", periods=80)
    columns = ["equity", "equity_before_costs", "return", "benchmark_return"]
    costs = ["commission_cost", "spread_cost", "impact_cost", "borrow_cost"]
    daily = pd.DataFrame(
        0.0, index=idx, columns=columns + costs + ["gross_exposure", "net_exposure"]
    )
    daily["equity"] = daily["equity_before_costs"] = 100.0
    daily["return"] = np.random.default_rng(0).normal(0, 0.01, len(idx))
    daily.to_csv(root / "tables" / "daily.csv")
    pd.DataFrame(
        {
            "scenario": ["base", "delay_1"],
            "sharpe": [0.8, None],
            "sharpe_reason": [None, "insolvent_wealth_path"],
            "insolvency": [None, "2024-03-01"],
        }
    ).to_csv(root / "tables" / "scenarios.csv", index=False)
    (root / "config.json").write_text(
        json.dumps({"initial_capital": 100.0, "annualization": 252, "risk_free_annual": 0.0})
    )
    monkeypatch.setattr("invest_evaluation.reporting._write_summary", lambda root: None)
    render(root)
    widths = [np.asarray(args[1], dtype=float) for method, args in calls if method == "barh"]
    assert len(widths) == 1 and widths[0][0] == 0.8 and np.isnan(widths[0][1])
    texts = [str(args[2]) for method, args in calls if method == "text"]
    assert any("insolvent 2024-03-01" in t for t in texts)


@pytest.mark.parametrize("command", ["run", "quantiles"])
@pytest.mark.parametrize("used", ["file", "non_empty"])
def test_cli_refuses_a_used_out_before_any_backtest(
    tmp_path, market, reversal_signals, monkeypatch, command, used
):
    """K10: a used --out is refused before reading inputs or running backtests."""

    def fail(*args, **kwargs):
        raise AssertionError("backtest ran before --out was checked")

    for name in ("run_backtest", "run_scenarios", "run_quantile_portfolios"):
        monkeypatch.setattr(f"invest_evaluation.cli.{name}", fail)
    inputs = _published(tmp_path, market, reversal_signals)
    out = tmp_path / "out"
    if used == "file":
        out.write_text("x")
    else:
        out.mkdir()
        (out / "keep.txt").write_text("x")
    with pytest.raises(SystemExit, match="not an empty directory"):
        main([command, *inputs, "--out", str(out)])
    assert (out.read_text() if used == "file" else (out / "keep.txt").read_text()) == "x"


@pytest.mark.parametrize("command", ["run", "quantiles"])
@pytest.mark.parametrize(
    ("option", "write", "message"),
    [
        ("--signals", None, "--signals: missing manifest.json"),
        ("--universe", None, "--universe: missing manifest.json"),
        ("--delistings", "not json", "--delistings: Expecting value"),
        ("--delistings", "{}", "--delistings: delistings JSON must be a list"),
        ("--config", "[1]", "--config: config must be a JSON object"),
        ("--config", None, "--config: .*No such file"),
    ],
)
def test_cli_unreadable_inputs_end_with_a_message(
    tmp_path, market, reversal_signals, command, option, write, message
):
    """Same class as REVIEW-13: an unreadable or invalid input is a clean exit, never a
    traceback, and nothing is written."""
    inputs = _published(tmp_path, market, reversal_signals)
    target = tmp_path / "input"
    if write is not None:
        target.write_text(write)
    if option == "--signals":
        inputs[inputs.index("--signals") + 1] = str(target)
        extra = []
    else:
        extra = [option, str(target)]
    out = tmp_path / "out"
    with pytest.raises(SystemExit, match=message):
        main([command, *inputs, *extra, "--out", str(out)])
    assert not out.exists()


def test_cli_unreadable_benchmark_ends_with_a_message(tmp_path, market, reversal_signals):
    inputs = _published(tmp_path, market, reversal_signals)
    out = tmp_path / "out"
    with pytest.raises(SystemExit, match=r"--benchmark: missing manifest\.json"):
        main(["run", *inputs, "--benchmark", str(tmp_path / "nope"), "--out", str(out)])
    assert not out.exists()
