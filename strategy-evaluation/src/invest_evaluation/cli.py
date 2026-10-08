"""Command line entry point: ``invest-eval``."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd

from invest_data.bundle import Manifest
from invest_data.schemas import (
    read_adjusted_market_bars,
    read_market_bars,
    read_signals,
    read_universe,
)
from invest_evaluation.config import BacktestConfig
from invest_evaluation.engine import InputError, check_price_rules, run_backtest
from invest_evaluation.metrics import compute_metrics, instrument_returns
from invest_evaluation.quantiles import QuantileConfig, run_quantile_portfolios, save_quantile_run
from invest_evaluation.reporting import save_run
from invest_evaluation.robustness import DEFAULT_SCENARIOS, run_scenarios
from invest_evaluation.stats import strategy_statistics
from invest_evaluation.validation import verdicts

T = TypeVar("T")


def code_revision(source: Path = Path(__file__)) -> tuple[str | None, bool | None]:
    """Git revision and uncommitted-changes flag of the checkout this code was loaded from.

    Looked up from the module's own location, never the caller's working directory, so a run
    started from another repository cannot record that repository's commit. Code that Git
    does not track there (an installed wheel, even inside a checkout's virtualenv) gives
    ``(None, None)``. The flag covers tracked files of the whole checkout, because the run
    also uses the other workspace packages.
    """
    source = source.resolve()

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(source.parent), *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return done.stdout.strip()

    try:
        git("ls-files", "--error-unmatch", "--", source.name)
        revision = git("rev-parse", "HEAD")
        dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
    except (OSError, subprocess.SubprocessError):
        return None, None
    return revision, dirty


def _add_inputs(cmd: argparse.ArgumentParser) -> None:
    cmd.add_argument("--data", type=Path, required=True)
    cmd.add_argument("--signals", type=Path, required=True)
    cmd.add_argument("--config", type=Path, help="JSON BacktestConfig (defaults if omitted)")
    cmd.add_argument("--out", type=Path, required=True)
    cmd.add_argument("--universe", type=Path, help="universe bundle limiting new positions")
    cmd.add_argument(
        "--delistings",
        type=Path,
        help="JSON settlements: date, instrument, settlement_price (known at date close)",
    )


def _refuse_used_out(out: Path) -> None:
    """Refuse a used or uncreatable ``--out`` before any input is read or backtest run."""
    cannot = f"--out {out} cannot be created"
    try:
        if out.exists() and (not out.is_dir() or any(out.iterdir())):
            raise SystemExit(f"--out {out} is not an empty directory; choose a new run directory")
        ancestor = out.absolute()
        while not (ancestor.exists() or ancestor.is_symlink()):
            ancestor = ancestor.parent
        if ancestor.is_symlink() and not ancestor.exists():
            raise SystemExit(f"{cannot}: {ancestor} is a broken or looping symbolic link")
        if not ancestor.is_dir():
            raise SystemExit(f"{cannot}: {ancestor} is not a directory")
        # Try it: permission bits alone do not tell (root, read-only mounts, /sys).
        os.rmdir(tempfile.mkdtemp(prefix=".invest-eval-", dir=ancestor))
        # The directories still to create must fit the file system's name limit.
        name_max = os.pathconf(ancestor, "PC_NAME_MAX")
        missing = out.absolute().relative_to(ancestor).parts
        if any(len(os.fsencode(part)) > name_max for part in missing):
            raise SystemExit(f"{cannot}: a name is longer than {name_max} bytes")
    except OSError as exc:  # for example a name too long for the file system
        raise SystemExit(f"{cannot}: {exc}") from exc


def _read(what: str, read: Callable[..., T], *args: Any) -> T:
    """Read one input; an unreadable or invalid one ends with a message, not a traceback."""
    try:
        return read(*args)
    except (ValueError, OSError) as exc:  # BundleError and JSONDecodeError are ValueErrors
        raise SystemExit(f"{what}: {exc}") from exc


def _read_delistings(path: Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    raw_events = json.loads(path.read_text())
    if not isinstance(raw_events, list):
        raise ValueError("delistings JSON must be a list of settlement events")
    return pd.DataFrame(raw_events)


def _fractions(text: str) -> tuple[float, ...]:
    try:
        return tuple(float(part) for part in text.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated fractions") from exc


def _market(path: Path, cfg: BacktestConfig) -> tuple[Manifest, pd.DataFrame]:
    """Market bars the backtest can use: adjusted closes, and the prices its rules need."""
    manifest, bars = _read("--data", read_adjusted_market_bars, path)
    try:
        check_price_rules(bars, cfg)
    except InputError as exc:
        raise SystemExit(str(exc)) from exc
    return manifest, bars


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="invest-eval", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="backtest a signals bundle on a market bundle")
    _add_inputs(run)
    run.add_argument(
        "--n-trials",
        type=int,
        help="strategies/signals tried before this one, for the deflated Sharpe "
        "(default: the signals bundle's n_trials metadata, else 1)",
    )
    run.add_argument("--no-scenarios", action="store_true")
    run.add_argument(
        "--benchmark",
        type=Path,
        help="market-bars bundle of a benchmark (e.g. SPY), reported next to the "
        "universe equal-weight benchmark",
    )
    run.add_argument(
        "--benchmark-instrument", help="instrument in --benchmark (needed if it holds several)"
    )
    quant = sub.add_parser(
        "quantiles",
        help="backtest every decile and top/bottom tail portfolio of a signals bundle",
    )
    _add_inputs(quant)
    quant.add_argument("--buckets", type=int, default=10, help="number of percentile buckets")
    quant.add_argument(
        "--tails",
        type=_fractions,
        default=(0.01, 0.05, 0.1),
        help="comma-separated tail fractions (default 0.01,0.05,0.1)",
    )
    quant.add_argument(
        "--min-names-per-bucket",
        type=int,
        default=5,
        help="fewest names a portfolio leg may hold before it is insufficient_data",
    )
    args = parser.parse_args(argv)
    _refuse_used_out(args.out)
    if args.command == "quantiles":
        return _quantiles(args)

    cfg = _read("--config", BacktestConfig.load, args.config) if args.config else BacktestConfig()
    market_manifest, bars = _market(args.data, cfg)
    signal_manifest, signals = _read("--signals", read_signals, args.signals)
    n_trials = args.n_trials
    if n_trials is None:
        n_trials = signal_manifest.metadata.get("n_trials", 1)
    if n_trials < 1:
        raise SystemExit("--n-trials must be at least 1")
    evidence = signal_manifest.metadata.get("factor_evidence")
    if evidence is not None and evidence["source"] == "search":
        # The search tried at least this many candidates; fewer would deflate less.
        searched = max(evidence["family_size"], signal_manifest.metadata.get("n_trials", 1))
        if n_trials < searched:
            raise SystemExit(
                f"--n-trials {n_trials} is below the {searched} candidates the search behind "
                "these signals tried; a count may only add trials"
            )
    unknown = sorted(set(cfg.validation.stress_scenarios) - set(DEFAULT_SCENARIOS))
    if unknown:
        raise SystemExit(f"validation.stress_scenarios: unknown scenarios {unknown}")
    if args.benchmark_instrument and not args.benchmark:
        raise SystemExit("--benchmark-instrument needs --benchmark")
    if cfg.validation.benchmark == "external" and not args.benchmark:
        raise SystemExit('validation.benchmark = "external" needs --benchmark')
    universe = _read("--universe", read_universe, args.universe)[1] if args.universe else None
    delistings = _read("--delistings", _read_delistings, args.delistings)
    external = None
    external_info = None
    if args.benchmark:
        bench_manifest, bench_bars = _read("--benchmark", read_market_bars, args.benchmark)
        for field in ("currency", "frequency", "price_adjustment", "calendar", "timezone"):
            market_value = market_manifest.metadata.get(field)
            bench_value = bench_manifest.metadata.get(field)
            if market_value != bench_value or (field != "timezone" and not market_value):
                raise SystemExit(
                    f"benchmark {field} mismatch: market={market_value!r}, "
                    f"benchmark={bench_value!r}; conversions are not supported"
                )
        if market_manifest.metadata["frequency"] != "1d":
            raise SystemExit("external benchmarks require daily (1d) market bars")
        external = _read(
            "--benchmark",
            lambda: instrument_returns(
                bench_bars,
                args.benchmark_instrument,
                sessions=pd.DatetimeIndex(bars["date"].unique()),
            ),
        )
        external_info = {
            "id": bench_manifest.dataset_id,
            "sha256": bench_manifest.content_sha256,
            "instrument": external.name,
            "metadata": bench_manifest.metadata,
        }
    try:
        result = run_backtest(bars, signals, cfg, universe=universe, delistings=delistings)
        scenarios = (
            None
            if args.no_scenarios
            else run_scenarios(bars, signals, cfg, universe=universe, delistings=delistings)
        )
    except InputError as exc:
        raise SystemExit(str(exc)) from exc
    metrics = compute_metrics(
        result,
        external,
        external_label=f"{external_info['instrument']} close-to-close ({external_info['id']})"
        if external_info
        else "external",
    )
    stats = strategy_statistics(
        result.returns,
        cfg.annualization,
        n_trials=n_trials,
        risk_free_annual=cfg.risk_free_annual,
    )
    verdict = verdicts(
        signal_manifest.metadata, cfg.validation, result.returns, metrics, stats, scenarios
    )
    revision, dirty = code_revision()
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
                "metadata": market_manifest.metadata,
            },
            "signals": {
                "id": signal_manifest.dataset_id,
                "sha256": signal_manifest.content_sha256,
                "metadata": signal_manifest.metadata,
            },
            "code_revision": revision,
            "code_dirty": dirty,
            "n_trials": n_trials,
            "external_benchmark": external_info,
            "delisting_settlements": None if delistings is None else delistings.to_dict("records"),
        },
        external_benchmark=external,
        verdict=verdict,
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
                "factor_status": verdict["factor"]["status"],
                "portfolio_status": verdict["portfolio"]["status"],
            }
        )
    )
    return 0


def _quantiles(args: argparse.Namespace) -> int:
    try:
        qcfg = QuantileConfig(
            n_buckets=args.buckets,
            tail_fractions=args.tails,
            min_names_per_bucket=args.min_names_per_bucket,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    cfg = _read("--config", BacktestConfig.load, args.config) if args.config else BacktestConfig()
    market_manifest, bars = _market(args.data, cfg)
    signal_manifest, signals = _read("--signals", read_signals, args.signals)
    universe = _read("--universe", read_universe, args.universe)[1] if args.universe else None
    delistings = _read("--delistings", _read_delistings, args.delistings)
    try:
        result = run_quantile_portfolios(
            bars, signals, cfg, qcfg, universe=universe, delistings=delistings
        )
    except InputError as exc:
        raise SystemExit(str(exc)) from exc
    revision, dirty = code_revision()
    save_quantile_run(
        args.out,
        result,
        provenance={
            "market_dataset": {
                "id": market_manifest.dataset_id,
                "sha256": market_manifest.content_sha256,
                "metadata": market_manifest.metadata,
            },
            "signals": {
                "id": signal_manifest.dataset_id,
                "sha256": signal_manifest.content_sha256,
                "metadata": signal_manifest.metadata,
            },
            "code_revision": revision,
            "code_dirty": dirty,
            "delisting_settlements": None if delistings is None else delistings.to_dict("records"),
        },
    )
    table = result.table
    print(
        json.dumps(
            {
                "run": str(args.out),
                "portfolios": len(table),
                "insufficient_data": table.loc[
                    table["status"] == "insufficient_data", "portfolio"
                ].tolist(),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
