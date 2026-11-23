"""`invest_evaluation.reporting` branches that no other test reached.

docs/REPORTING.md: reporting consumes saved numerical results and prints what a run
saved, so a run saved by older code, or by a caller that saved fewer statistics, renders
as it was saved and nothing is recomputed. Every run here holds nothing, so its
expected lines follow by hand from the saved values: a metric without a value prints as
``n/a (<reason>)``, and README.md (strategy-evaluation) gives the reason format of the
bootstrap and deflated Sharpe lines and their minimum return counts (60 and 30); the
deflated Sharpe label is the one in the saved record runs/yahoo-test/2026-10-07, and the
unavailable-bootstrap label the one test_stats_and_cli.py already checks (BH-2026-10-09-6).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from invest_evaluation.config import BacktestConfig, ExecutionConfig, StrategyConfig
from invest_evaluation.engine import BacktestResult, run_backtest
from invest_evaluation.metrics import compute_metrics
from invest_evaluation.reporting import render, save_run
from invest_evaluation.stats import strategy_statistics

FIGURES_LINE = "Figures: `figures/`. Tables: `tables/`. Full metrics: `metrics.json`."


class _Flat:
    """Holds nothing, so every return is zero and the run needs no random input."""

    def target_weights(self, scores: pd.Series) -> pd.Series:
        return pd.Series(dtype=float)


def _flat_result(periods: int = 20) -> BacktestResult:
    dates = pd.bdate_range("2024-01-01", periods=periods)
    bars = pd.DataFrame(
        [[d, "A", 10.0, 10.0, 10.0, 10.0, 1e9] for d in dates],
        columns=["date", "instrument", "open", "high", "low", "close", "volume"],
    )
    signals = pd.DataFrame({"decision_date": [dates[0]], "instrument": ["A"], "score": [1.0]})
    cfg = BacktestConfig(
        strategy=StrategyConfig(min_names=1), execution=ExecutionConfig(min_price=0.0)
    )
    return run_backtest(bars, signals, cfg, _Flat())


def _save(root: Path, result: BacktestResult, statistics: dict[str, Any]) -> Path:
    return save_run(root, result, compute_metrics(result), statistics, None, {})


def _report(root: Path) -> list[str]:
    return (root / "report.md").read_text(encoding="utf-8").splitlines()


def test_save_run_refuses_a_run_directory_that_is_not_empty(tmp_path: Path) -> None:
    """One directory holds one run: saving into a used one would mix two runs' files, so
    nothing is written and the old files stay. An existing empty directory is accepted."""
    result = _flat_result()
    stats = strategy_statistics(result.returns, 252)
    used = tmp_path / "used"
    used.mkdir()
    (used / "notes.txt").write_text("keep\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="is not empty"):
        _save(used, result, stats)
    assert [p.name for p in used.iterdir()] == ["notes.txt"]
    assert (used / "notes.txt").read_text(encoding="utf-8") == "keep\n"

    empty = tmp_path / "empty"
    empty.mkdir()
    assert _save(empty, result, stats) == empty
    assert (empty / "report.md").is_file()


def test_a_benchmark_saved_without_coverage_counts_renders_no_coverage_line(
    tmp_path: Path,
) -> None:
    """Before PR #6 (2026-10-06) a benchmark with fewer than 20 aligned returns was saved
    with no ``extra`` (no ``aligned_sessions``): rendered again, its section keeps the
    table and prints no benchmark name or coverage line, since none was saved."""
    result = _flat_result()
    root = _save(tmp_path / "run", result, strategy_statistics(result.returns, 252))
    path = root / "metrics.json"
    metrics = json.loads(path.read_text(encoding="utf-8"))
    entry = metrics["benchmark"]["benchmark"]
    assert entry["status"] == "insufficient_data"
    assert entry["reason"] == "fewer_than_20_aligned_returns"
    assert "aligned_sessions" in entry["extra"]
    # Today's format: the coverage line is there.
    assert any(line.startswith("Aligned daily returns: ") for line in _report(root))

    del entry["extra"]  # the entry as PR #5's code saved it
    path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    render(root)
    lines = _report(root)
    start = lines.index("## Benchmark")
    assert lines[start : start + 5] == [
        "## Benchmark",
        "",
        "| metric | value |",
        "|---|---|",
        "| benchmark | n/a (fewer_than_20_aligned_returns) |",
    ]
    assert not any(line.startswith(("Benchmark: ", "Aligned daily returns: ")) for line in lines)


def test_a_benchmark_saved_with_its_name_only_renders_no_coverage_line(tmp_path: Path) -> None:
    """The first commit (2026-10-05, before PR #5) saved a benchmark with 20 or more aligned
    returns with only its name in ``extra``, no ``aligned_sessions``: rendered again, its
    table prints and no coverage line does, since no counts were saved."""
    result = _flat_result(25)  # 24 aligned returns: the first session has no earlier close
    root = _save(tmp_path / "run", result, strategy_statistics(result.returns, 252))
    path = root / "metrics.json"
    metrics = json.loads(path.read_text(encoding="utf-8"))
    entry = metrics["benchmark"]["benchmark_total_return"]
    assert entry["extra"]["aligned_sessions"] == 24
    entry["extra"] = {"benchmark": entry["extra"]["benchmark"]}  # as the first commit saved it
    path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    render(root)
    lines = _report(root)
    # Flat closes: the benchmark gained nothing.
    assert "| benchmark_total_return | 0.00% |" in lines
    assert not any(line.startswith("Aligned daily returns: ") for line in lines)


@pytest.mark.parametrize(
    "missing",
    [("bootstrap",), ("deflated_sharpe",), ("bootstrap", "deflated_sharpe")],
)
def test_a_statistic_that_was_never_saved_gets_no_report_line(
    tmp_path: Path, missing: tuple[str, ...]
) -> None:
    """report.md prints the bootstrap interval and the deflated Sharpe for every saved
    status, with the reason when unavailable; an entry that was never saved has no status,
    so today it gets no line, and the other entry keeps its line. This pins today's
    behavior: TODO.md REVIEW-50 asks for a line for every picked performance row of an
    insolvent run, and a change of that rule for statistics changes this test too."""
    result = _flat_result()
    n = len(result.returns)
    assert n < 30  # both statistics are insufficient_data on this run
    full = strategy_statistics(result.returns, 252)
    root = _save(tmp_path / "run", result, {k: v for k, v in full.items() if k not in missing})
    lines = _report(root)
    bootstrap = f"Sharpe stationary-bootstrap CI: n/a (insufficient_data: {n} returns, needs 60)"
    dsr = f"Deflated Sharpe ratio (n_trials=1): n/a (insufficient_data: {n} returns, needs 30)"
    expected = [
        line
        for key, line in (("bootstrap", bootstrap), ("deflated_sharpe", dsr))
        if key not in missing
    ]
    printed = [line for line in lines if "bootstrap" in line or "Deflated Sharpe" in line]
    assert printed == expected
    # Nothing else stands between the last metrics table and the closing line.
    body = [line for line in lines if line]
    assert body[-1] == FIGURES_LINE
    assert body[len(body) - 1 - len(expected) : -1] == expected
    assert body[-2 - len(expected)].startswith("| ")
