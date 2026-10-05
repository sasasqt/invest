"""Command line entry point: ``invest-eval``."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from invest_data.schemas import read_market_bars, read_signals
from invest_evaluation.config import BacktestConfig
from invest_evaluation.engine import run_backtest
from invest_evaluation.metrics import compute_metrics
from invest_evaluation.reporting import save_run
from invest_evaluation.robustness import run_scenarios
from invest_evaluation.stats import strategy_statistics


def _git_revision() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="invest-eval", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="backtest a signals bundle on a market bundle")
    run.add_argument("--data", type=Path, required=True)
    run.add_argument("--signals", type=Path, required=True)
    run.add_argument("--config", type=Path, help="JSON BacktestConfig (defaults if omitted)")
    run.add_argument("--out", type=Path, required=True)
    run.add_argument(
        "--n-trials",
        type=int,
        default=1,
        help="strategies/signals tried before this one (for the deflated Sharpe)",
    )
    run.add_argument("--no-scenarios", action="store_true")
    args = parser.parse_args(argv)

    market_manifest, bars = read_market_bars(args.data)
    signal_manifest, signals = read_signals(args.signals)
    cfg = BacktestConfig.load(args.config) if args.config else BacktestConfig()
    result = run_backtest(bars, signals, cfg)
    metrics = compute_metrics(result)
    stats = strategy_statistics(result.returns, cfg.annualization, n_trials=args.n_trials)
    scenarios = None if args.no_scenarios else run_scenarios(bars, signals, cfg)
    save_run(
        args.out,
        result,
        metrics,
        stats,
        scenarios,
        provenance={
            "market_dataset": {
                "id": market_manifest.dataset_id,
                "sha256": market_manifest.content_sha256,
            },
            "signals": {
                "id": signal_manifest.dataset_id,
                "sha256": signal_manifest.content_sha256,
                "metadata": signal_manifest.metadata,
            },
            "code_revision": _git_revision(),
        },
    )
    perf = metrics["performance"]
    print(
        json.dumps(
            {
                "run": str(args.out),
                "cagr": perf["cagr"]["value"],
                "sharpe": perf["sharpe"]["value"],
                "max_drawdown": perf["max_drawdown"]["value"],
                "warnings": len(result.warnings),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
