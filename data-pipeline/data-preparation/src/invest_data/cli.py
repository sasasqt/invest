"""Command line entry point: ``invest-data``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from invest_data.cleaning import clean_bars
from invest_data.schemas import publish_fundamentals, publish_market_bars, publish_universe
from invest_data.sources import (
    SYNTHETIC_METADATA,
    SyntheticConfig,
    load_csv_bars,
    synthetic_fundamentals,
    synthetic_market,
    synthetic_universe,
)


def _publish(
    raw: pd.DataFrame, out: Path, dataset_id: str, metadata: dict, provenance: dict, fmt: str
) -> int:
    clean, report = clean_bars(raw)
    provenance = {**provenance, "cleaning": report.summary()}
    manifest = publish_market_bars(
        clean, out, dataset_id=dataset_id, metadata=metadata, provenance=provenance, fmt=fmt
    )
    if len(report.rejected):
        report.rejected.to_csv(out.with_name(out.name + ".rejected.csv"), index=False)
    print(json.dumps({"bundle": str(out), "rows": manifest.row_count, **report.summary()}))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="invest-data", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    syn = sub.add_parser("synthetic", help="publish a deterministic synthetic market dataset")
    syn.add_argument("--out", type=Path, required=True)
    syn.add_argument("--format", choices=["csv", "sqlite", "parquet"], default="csv")
    syn.add_argument("--instruments", type=int, default=SyntheticConfig.n_instruments)
    syn.add_argument("--days", type=int, default=SyntheticConfig.n_days)
    syn.add_argument("--seed", type=int, default=SyntheticConfig.seed)
    syn.add_argument("--universe-out", type=Path, help="also publish a universe bundle")
    syn.add_argument("--fundamentals-out", type=Path, help="also publish a fundamentals bundle")

    imp = sub.add_parser("import-csv", help="clean and publish user-supplied daily bars")
    imp.add_argument("source", type=Path)
    imp.add_argument("--out", type=Path, required=True)
    imp.add_argument("--dataset-id", required=True)
    imp.add_argument("--format", choices=["csv", "sqlite", "parquet"], default="csv")
    imp.add_argument("--currency", required=True)
    imp.add_argument("--calendar", required=True, help="e.g. XNYS")
    imp.add_argument(
        "--price-adjustment",
        required=True,
        choices=["total_return_adjusted", "split_adjusted", "unadjusted"],
    )

    args = parser.parse_args(argv)
    if args.command == "synthetic":
        cfg = SyntheticConfig(n_instruments=args.instruments, n_days=args.days, seed=args.seed)
        bars = synthetic_market(cfg)
        prov = {"sources": ["invest_data.sources"], "config": cfg.to_dict()}
        if args.universe_out:
            publish_universe(
                synthetic_universe(bars, seed=cfg.seed),
                args.universe_out,
                dataset_id=f"synthetic-universe-{cfg.seed}",
                provenance=prov,
                fmt=args.format,
            )
        if args.fundamentals_out:
            publish_fundamentals(
                synthetic_fundamentals(bars, seed=cfg.seed),
                args.fundamentals_out,
                dataset_id=f"synthetic-fundamentals-{cfg.seed}",
                provenance=prov,
                fmt=args.format,
            )
        return _publish(
            bars,
            args.out,
            f"synthetic-{cfg.seed}",
            SYNTHETIC_METADATA,
            {"sources": ["invest_data.sources.synthetic_market"], "config": cfg.to_dict()},
            args.format,
        )
    meta = {
        "frequency": "1d",
        "currency": args.currency,
        "calendar": args.calendar,
        "price_adjustment": args.price_adjustment,
    }
    return _publish(
        load_csv_bars(args.source),
        args.out,
        args.dataset_id,
        meta,
        {"sources": [args.source.name]},
        args.format,
    )


if __name__ == "__main__":
    sys.exit(main())
