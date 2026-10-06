"""Command line entry point: ``invest-eval``."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from invest_data.schemas import read_market_bars, read_signals, read_universe
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
        help="strategies/signals tried before this one, for the deflated Sharpe "
        "(default: the signals bundle's n_trials metadata, else 1)",
    )
    run.add_argument("--no-scenarios", action="store_true")
    run.add_argument("--universe", type=Path, help="universe bundle limiting new positions")
    run.add_argument(
        "--delistings",
        type=Path,
        help="JSON settlements: date, instrument, settlement_price (known at date close)",
    )
    args = parser.parse_args(argv)

    market_manifest, bars = read_market_bars(args.data)
    signal_manifest, signals = read_signals(args.signals)
    n_trials = args.n_trials
    if n_trials is None:
        n_trials = int(signal_manifest.metadata.get("n_trials", 1))
    if n_trials < 1:
        raise SystemExit("--n-trials must be at least 1")
    cfg = BacktestConfig.load(args.config) if args.config else BacktestConfig()
    universe = read_universe(args.universe)[1] if args.universe else None
    delistings = None
    if args.delistings:
        raw_events = json.loads(args.delistings.read_text())
        if not isinstance(raw_events, list):
            raise ValueError("delistings JSON must be a list of settlement events")
        delistings = pd.DataFrame(raw_events)
    result = run_backtest(bars, signals, cfg, universe=universe, delistings=delistings)
    metrics = compute_metrics(result)
    stats = strategy_statistics(
        result.returns,
        cfg.annualization,
        n_trials=n_trials,
        risk_free_annual=cfg.risk_free_annual,
    )
    scenarios = (
        None
        if args.no_scenarios
        else run_scenarios(bars, signals, cfg, universe=universe, delistings=delistings)
    )
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
            "n_trials": n_trials,
            "delisting_settlements": None if delistings is None else delistings.to_dict("records"),
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
