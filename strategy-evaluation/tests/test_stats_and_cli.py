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
        metadata={"factor_id": "rev5", "horizon_days": 1},
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
