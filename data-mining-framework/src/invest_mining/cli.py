"""Command line entry point: ``invest-mine``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from invest_data.schemas import read_fundamentals, read_market_bars, read_universe
from invest_mining.artifact import FrozenFactor
from invest_mining.diagnostics import (
    daily_ic,
    forward_returns,
    ic_summary,
    quantile_returns,
    rank_autocorrelation,
    tail_returns,
)
from invest_mining.expressions import build_panel, canonical, evaluate, restrict
from invest_mining.inference import export_signals
from invest_mining.reporting import write_factor_report
from invest_mining.search import run_search


def _optional_inputs(args: argparse.Namespace) -> dict[str, pd.DataFrame | None]:
    return {
        "universe": read_universe(args.universe)[1] if args.universe else None,
        "fundamentals": read_fundamentals(args.fundamentals)[1] if args.fundamentals else None,
    }


def _evaluate(args: argparse.Namespace) -> int:
    manifest, bars = read_market_bars(args.data)
    panel = build_panel(bars, **_optional_inputs(args))
    values = restrict(evaluate(args.expr, panel), panel)
    label = restrict(forward_returns(panel["open"], args.horizon), panel)
    ic = daily_ic(values, label, "spearman")
    summary = ic_summary(ic, args.horizon)
    summary["pearson_mean_ic"] = ic_summary(daily_ic(values, label, "pearson"), args.horizon)[
        "mean_ic"
    ]
    summary["rank_autocorrelation_1d"] = rank_autocorrelation(values)
    write_factor_report(
        args.out,
        expression=canonical(args.expr),
        summary=summary,
        ic=ic,
        quantiles=quantile_returns(values, label, args.buckets),
        tails=tail_returns(values, label),
        config={
            "dataset_id": manifest.dataset_id,
            "dataset_sha256": manifest.content_sha256,
            "horizon": args.horizon,
            "buckets": args.buckets,
            "note": "Descriptive diagnostics on the full sample; not a confirmatory test.",
        },
    )
    print(
        json.dumps(
            {
                "report": str(args.out),
                "mean_rank_ic": summary["mean_ic"],
                "hac_t": summary["hac_test"]["t_stat"],
            }
        )
    )
    return 0


def _search(args: argparse.Namespace) -> int:
    manifest, bars = read_market_bars(args.data)
    result = run_search(
        build_panel(bars, **_optional_inputs(args)),
        n_trials=args.trials,
        seed=args.seed,
        horizon=args.horizon,
        dev_fraction=args.dev_fraction,
        embargo=args.embargo,
        top_k=args.top_k,
        dataset_id=manifest.dataset_id,
        dataset_sha256=manifest.content_sha256,
    )
    out = Path(args.out)
    (out / "factors").mkdir(parents=True, exist_ok=True)
    result.ledger.to_csv(out / "ledger.csv", index=False)
    result.confirmation.to_csv(out / "confirmation.csv", index=False)
    (out / "config.json").write_text(json.dumps(result.config, indent=2) + "\n")
    for factor in result.family:
        factor.save(out / "factors" / f"{factor.factor_id}.json")
    if not result.family:
        print("No candidates qualified for confirmation; see ledger.csv for rejection reasons.")
        return 0
    print(
        result.confirmation[
            ["factor_id", "expression", "confirm_mean_rank_ic", "p_holm", "status"]
        ].to_string(index=False)
    )
    return 0


def _export(args: argparse.Namespace) -> int:
    manifest, bars = read_market_bars(args.data)
    factor = FrozenFactor.load(args.factor)
    if factor.dataset_sha256 and factor.dataset_sha256 != manifest.content_sha256:
        print(
            "note: exporting on a different dataset than the factor was selected on",
            file=sys.stderr,
        )
    out = export_signals(
        factor,
        bars,
        args.out,
        dataset_id=manifest.dataset_id,
        start=args.start,
        fmt=args.format,
        **_optional_inputs(args),
    )
    print(
        json.dumps({"signals": str(args.out), "rows": out.row_count, "factor_id": factor.factor_id})
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="invest-mine", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ev = sub.add_parser("evaluate", help="diagnose one expression")
    ev.add_argument("--data", type=Path, required=True)
    ev.add_argument("--expr", required=True)
    ev.add_argument("--horizon", type=int, default=1)
    ev.add_argument("--buckets", type=int, default=10)
    ev.add_argument("--out", type=Path, required=True)

    se = sub.add_parser("search", help="random search with a ledger and frozen confirmation")
    se.add_argument("--data", type=Path, required=True)
    se.add_argument("--trials", type=int, default=200)
    se.add_argument("--seed", type=int, default=0)
    se.add_argument("--horizon", type=int, default=1)
    se.add_argument("--dev-fraction", type=float, default=0.6)
    se.add_argument("--embargo", type=int, default=0)
    se.add_argument("--top-k", type=int, default=5)
    se.add_argument("--out", type=Path, required=True)

    ex = sub.add_parser("export", help="apply a frozen factor and publish a signals bundle")
    ex.add_argument("--data", type=Path, required=True)
    ex.add_argument("--factor", type=Path, required=True)
    ex.add_argument("--out", type=Path, required=True)
    ex.add_argument("--start", help="first decision date to export (YYYY-MM-DD)")
    ex.add_argument("--format", choices=["csv", "sqlite", "parquet"], default="csv")

    for p in (ev, se, ex):
        p.add_argument("--universe", type=Path, help="universe bundle (point-in-time membership)")
        p.add_argument("--fundamentals", type=Path, help="fundamentals bundle (fund_<field>)")

    args = parser.parse_args(argv)
    return {"evaluate": _evaluate, "search": _search, "export": _export}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
