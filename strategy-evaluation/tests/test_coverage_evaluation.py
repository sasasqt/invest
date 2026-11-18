"""Stress-scenario settings and `invest-eval` refusals that no other test reached.

Expected messages are the ones each check documents; the CLI cases also check that a
refused run creates no output folder.
"""

from pathlib import Path

import pandas as pd
import pytest

from invest_data.schemas import publish_market_bars, publish_signals
from invest_data.sources import SYNTHETIC_METADATA
from invest_evaluation.cli import main
from invest_evaluation.config import BacktestConfig
from invest_evaluation.robustness import scenario_config


def test_a_scenario_can_change_the_rebalance_interval() -> None:
    base = BacktestConfig()
    cfg = scenario_config(base, {"rebalance_every": 21.0})
    assert cfg.strategy.rebalance_every == 21
    assert isinstance(cfg.strategy.rebalance_every, int)
    # Everything else stays as configured.
    assert cfg.costs == base.costs and cfg.execution == base.execution
    assert cfg.strategy.long_fraction == base.strategy.long_fraction


def _inputs(tmp_path: Path, market: pd.DataFrame, signals: pd.DataFrame) -> list[str]:
    publish_market_bars(market, tmp_path / "m", dataset_id="m", metadata=SYNTHETIC_METADATA)
    metadata = {"factor_id": "rev5", "horizon_days": 1}
    publish_signals(signals, tmp_path / "s", dataset_id="s", metadata=metadata)
    return ["--data", str(tmp_path / "m"), "--signals", str(tmp_path / "s")]


@pytest.mark.parametrize("tails", ["0.1,abc", "", "0.05;0.1"])
def test_quantiles_refuse_tail_fractions_that_are_not_numbers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], tails: str
) -> None:
    out = tmp_path / "q"
    args = ["quantiles", "--data", "m", "--signals", "s", "--out", str(out), "--tails", tails]
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2  # argparse's usage error
    assert "expected comma-separated fractions" in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize("n_trials", ["0", "-3"])
def test_run_refuses_fewer_than_one_trial(
    tmp_path: Path, market: pd.DataFrame, reversal_signals: pd.DataFrame, n_trials: str
) -> None:
    inputs = _inputs(tmp_path, market, reversal_signals)
    out = tmp_path / "run"
    with pytest.raises(SystemExit, match="--n-trials must be at least 1"):
        main(["run", *inputs, "--n-trials", n_trials, "--out", str(out)])
    assert not out.exists()


def test_an_external_benchmark_needs_daily_bars_even_when_both_are_weekly(
    tmp_path: Path, market: pd.DataFrame, reversal_signals: pd.DataFrame
) -> None:
    weekly = {**SYNTHETIC_METADATA, "frequency": "1wk"}
    publish_market_bars(market, tmp_path / "m", dataset_id="m", metadata=weekly)
    publish_signals(
        reversal_signals,
        tmp_path / "s",
        dataset_id="s",
        metadata={"factor_id": "rev5", "horizon_days": 1},
    )
    benchmark = market[market["instrument"] == "SYN003"].assign(instrument="SPY")
    publish_market_bars(benchmark, tmp_path / "b", dataset_id="b", metadata=weekly)
    out = tmp_path / "run"
    inputs = ["--data", str(tmp_path / "m"), "--signals", str(tmp_path / "s")]
    with pytest.raises(SystemExit, match=r"external benchmarks require daily \(1d\) market bars"):
        main(["run", *inputs, "--benchmark", str(tmp_path / "b"), "--out", str(out)])
    assert not out.exists()


def test_without_pathconf_the_output_probe_skips_parent_references(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Without os.pathconf (as on Windows) the probe creates each missing name of --out in a
    # temporary folder. "missing/../new" can be created, so the run goes on to read its
    # inputs (here a --data folder without a manifest) and leaves nothing behind.
    monkeypatch.delattr("invest_evaluation.cli.os.pathconf", raising=False)
    out = tmp_path / "missing" / ".." / "new"
    before = set(tmp_path.rglob("*"))
    with pytest.raises(SystemExit, match=r"--data: missing manifest\.json"):
        main(["run", "--data", str(tmp_path / "nodata"), "--signals", "s", "--out", str(out)])
    assert set(tmp_path.rglob("*")) == before
