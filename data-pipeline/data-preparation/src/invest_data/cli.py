"""Command line entry point: ``invest-data``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from invest_data.cleaning import clean_bars
from invest_data.schemas import (
    ADJUSTED_PRICES,
    PRICE_ADJUSTMENTS,
    publish_fundamentals,
    publish_market_bars,
    publish_universe,
)
from invest_data.sources import (
    SYNTHETIC_METADATA,
    SyntheticConfig,
    load_csv_bars,
    synthetic_fundamentals,
    synthetic_market,
    synthetic_universe,
)
from invest_data.yahoo import (
    RetryPolicy,
    download_snapshot,
    load_snapshot,
    read_snapshot_manifest,
    yahoo_metadata,
)


def _symbols(args: argparse.Namespace) -> list[str] | None:
    """Symbols from ``--symbols`` and ``--symbols-file`` (one per line, ``#`` comments)."""
    names = list(args.symbols or [])
    if args.symbols_file:
        for line in args.symbols_file.read_text().splitlines():
            name = line.split("#", 1)[0].strip()
            if name:
                names.append(name)
    return list(dict.fromkeys(names)) or None


def _yahoo(args: argparse.Namespace) -> int:
    symbols = _symbols(args)
    if args.yahoo_command == "download":
        if not symbols:
            raise SystemExit("give --symbols or --symbols-file")
        snap = download_snapshot(
            symbols,
            args.start,
            args.end,
            args.snapshot,
            timeout=args.timeout,
            retry=RetryPolicy(attempts=args.attempts),
            pause_seconds=args.pause,
        )
        print(
            json.dumps(
                {
                    "snapshot": str(args.snapshot),
                    "downloaded": len(snap["files"]),
                    "failures": snap["failures"],
                }
            )
        )
        return 0 if snap["files"] else 1
    if args.exclude:
        if symbols is None:
            symbols = list(read_snapshot_manifest(args.snapshot)["files"])
        symbols = [s for s in symbols if s not in set(args.exclude)]
    raw, provenance = load_snapshot(args.snapshot, symbols, start=args.start, end=args.end)
    currencies = set(provenance["currencies"].values())
    if len(currencies) != 1 or None in currencies:
        raise SystemExit(
            f"cannot publish mixed or unknown currencies {sorted(map(str, currencies))}"
        )
    return _publish(
        raw,
        args.out,
        args.dataset_id,
        yahoo_metadata(currencies.pop(), args.universe_note),
        provenance,
        args.format,
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
    if metadata["price_adjustment"] not in ADJUSTED_PRICES:
        print(
            f"note: evaluation and mining refuse {metadata['price_adjustment']!r} bars until "
            "corporate actions are modelled",
            file=sys.stderr,
        )
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
        choices=PRICE_ADJUSTMENTS,
        help="how the CSV's open/high/low/close are adjusted (unadjusted = raw, as traded)",
    )
    imp.add_argument(
        "--adjusted-close",
        metavar="COLUMN",
        help="CSV column with the total-return adjusted close: converts unadjusted or "
        "split_adjusted prices to total_return_adjusted bars (raw closes are kept as "
        "close_as_traded)",
    )

    yah = sub.add_parser("yahoo", help="test-only Yahoo Finance snapshots (download, publish)")
    ysub = yah.add_subparsers(dest="yahoo_command", required=True)
    ydl = ysub.add_parser("download", help="save raw chart responses as an immutable snapshot")
    ydl.add_argument("--start", required=True, help="first session (YYYY-MM-DD)")
    ydl.add_argument("--end", required=True, help="last session (YYYY-MM-DD)")
    ydl.add_argument("--timeout", type=float, default=20.0, help="seconds per request")
    ydl.add_argument("--attempts", type=int, default=4, help="tries per symbol (bounded)")
    ydl.add_argument("--pause", type=float, default=0.5, help="seconds between symbols")
    ypub = ysub.add_parser("publish", help="replay a snapshot offline and publish market bars")
    ypub.add_argument("--out", type=Path, required=True)
    ypub.add_argument("--dataset-id", required=True)
    ypub.add_argument("--format", choices=["csv", "sqlite", "parquet"], default="csv")
    ypub.add_argument("--start", help="inclusive subset start (defaults to snapshot request)")
    ypub.add_argument("--end", help="inclusive subset end (defaults to snapshot request)")
    ypub.add_argument(
        "--universe-note",
        default="symbols chosen today and applied to all history (survivorship-biased)",
        help="how the symbols were selected; stored in the bundle metadata",
    )
    ypub.add_argument("--exclude", nargs="+", help="symbols to leave out (e.g. the benchmark)")
    for p in (ydl, ypub):
        p.add_argument("--snapshot", type=Path, required=True, help="snapshot directory")
        p.add_argument("--symbols", nargs="+", help="symbols (publish: subset of the snapshot)")
        p.add_argument("--symbols-file", type=Path, help="one symbol per line, # comments")

    args = parser.parse_args(argv)
    if args.command == "yahoo":
        return _yahoo(args)
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
    provenance: dict[str, Any] = {"sources": [args.source.name]}
    adjustment = args.price_adjustment
    if args.adjusted_close is not None:
        if adjustment == "total_return_adjusted":
            raise SystemExit("--adjusted-close converts unadjusted or split_adjusted prices")
        provenance["converted"] = {
            "from": adjustment,
            "adjusted_close_column": args.adjusted_close,
        }
        adjustment = "total_return_adjusted"
    meta = {
        "frequency": "1d",
        "currency": args.currency,
        "calendar": args.calendar,
        "price_adjustment": adjustment,
    }
    try:
        bars = load_csv_bars(
            args.source,
            adjusted_close=args.adjusted_close,
            as_traded=args.adjusted_close is not None and args.price_adjustment == "unadjusted",
        )
    except ValueError as exc:
        raise SystemExit(f"{args.source}: {exc}") from exc
    return _publish(bars, args.out, args.dataset_id, meta, provenance, args.format)


if __name__ == "__main__":
    sys.exit(main())
