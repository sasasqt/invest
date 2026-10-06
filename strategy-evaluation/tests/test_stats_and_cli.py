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
    with pytest.raises(FileExistsError):
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
        [(d, "A", 10.0, 10.0, 10.0, 10.0, 1e9) for d in dates],
        columns=["date", "instrument", "open", "high", "low", "close", "volume"],
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


@pytest.mark.parametrize("settlement_price", [8.0, 0.0])
def test_cli_applies_cash_settlements_to_base_and_stress_runs(tmp_path, settlement_price):
    dates = pd.bdate_range("2024-01-01", periods=65)
    bars = pd.DataFrame(
        [(d, "A", 10.0, 10.0, 10.0, 10.0, 1e9) for d in dates],
        columns=["date", "instrument", "open", "high", "low", "close", "volume"],
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


def test_cli_reports_external_benchmark_next_to_equal_weight(tmp_path, market, reversal_signals):
    publish_market_bars(market, tmp_path / "m", dataset_id="m", metadata=SYNTHETIC_METADATA)
    publish_signals(
        reversal_signals,
        tmp_path / "s",
        dataset_id="s",
        metadata={"factor_id": "rev5", "horizon_days": 1},
    )
    # A benchmark bundle that starts late: sessions before it have no benchmark return.
    spy = market[market["instrument"] == "SYN003"]
    spy = spy[spy["date"] >= spy["date"].iloc[40]].assign(instrument="SPY")
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
    aligned = closes.pct_change().dropna().reindex(daily.index).dropna()
    assert ext["benchmark_total_return"]["extra"]["aligned_sessions"] == len(aligned)
    assert ext["benchmark_total_return"]["value"] == pytest.approx(np.prod(1 + aligned) - 1)
    assert daily["external_benchmark_return"].notna().sum() == len(aligned)
    assert ext["beta"]["status"] == "ok"
    manifest = json.loads((tmp_path / "run" / "manifest.json").read_text())
    assert manifest["external_benchmark"]["instrument"] == "SPY"
    assert "## External Benchmark" in (tmp_path / "run" / "report.md").read_text()
    no_bench = tmp_path / "plain"
    assert main([*base, "--out", str(no_bench)]) == 0
    assert "external_benchmark" not in json.loads((no_bench / "metrics.json").read_text())
    assert "External Benchmark" not in (no_bench / "report.md").read_text()

    with pytest.raises(ValueError, match="name one"):
        main([*base, "--out", str(tmp_path / "x"), "--benchmark", str(tmp_path / "m")])
    pick = ["--benchmark", str(tmp_path / "m"), "--benchmark-instrument", "SYN001"]
    assert main([*base, "--out", str(tmp_path / "y"), *pick]) == 0
    with pytest.raises(ValueError, match="not in bundle"):
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
