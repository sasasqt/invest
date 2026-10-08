"""Command line entry point: ``invest-mine``."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from invest_data.bundle import BundleError
from invest_data.schemas import (
    FACTOR_EVIDENCE_STATISTICS,
    FACTOR_EVIDENCE_VERSION,
    read_fundamentals,
    read_market_bars,
    read_universe,
    validate_factor_evidence,
)
from invest_mining import ledger
from invest_mining.artifact import FrozenFactor
from invest_mining.diagnostics import (
    BUCKET_RULE,
    TAIL_RULE,
    daily_ic,
    forward_returns,
    ic_summary,
    quantile_returns,
    rank_autocorrelation,
    tail_returns,
)
from invest_mining.expressions import (
    OPERATOR_VERSION,
    build_panel,
    canonical,
    evaluate,
    restrict,
)
from invest_mining.inference import export_signals
from invest_mining.ledger import LedgerError, Window
from invest_mining.reporting import write_factor_report
from invest_mining.search import chronological_split, confirm, mark_confirmation_use, run_search


def _optional_inputs(args: argparse.Namespace) -> dict[str, pd.DataFrame | None]:
    return {
        "universe": read_universe(args.universe)[1] if args.universe else None,
        "fundamentals": read_fundamentals(args.fundamentals)[1] if args.fundamentals else None,
    }


def _input_hashes(args: argparse.Namespace) -> dict[str, str | None]:
    return {
        "universe_sha256": read_universe(args.universe)[0].content_sha256
        if args.universe
        else None,
        "fundamentals_sha256": read_fundamentals(args.fundamentals)[0].content_sha256
        if args.fundamentals
        else None,
    }


def _span(dates: pd.DatetimeIndex, what: str) -> Window:
    if len(dates) == 0:
        raise SystemExit(f"the {what} period is empty; adjust the split")
    return Window(dates[0].date(), dates[-1].date())


def _record_inspection(path: Path, window: Window, manifest: Any, note: str) -> None:
    """Refuse reserved data, then record the window unless already recorded."""
    entries = ledger.load(path)
    try:
        ledger.check_inspection(entries, window)
    except LedgerError as exc:
        raise SystemExit(f"{path}: {exc}") from exc
    if not ledger.is_inspected(entries, window):
        ledger.append(
            path,
            "inspection",
            {
                "window": window.to_json(),
                "dataset_id": manifest.dataset_id,
                "dataset_sha256": manifest.content_sha256,
                "note": note,
            },
        )


def _evaluate(args: argparse.Namespace) -> int:
    # Validate settings before the ledger records an inspection.
    for flag, value, minimum in (
        ("--buckets", args.buckets, 1),
        ("--min-tail-names", args.min_tail_names, 1),
        ("--min-cross-section", args.min_cross_section, 1),
    ):
        if value < minimum:
            raise SystemExit(f"{flag} must be an integer >= {minimum}")
    manifest, bars = read_market_bars(args.data)
    if args.ledger is not None:
        dates = pd.DatetimeIndex(sorted(bars["date"].unique()))
        _record_inspection(
            args.ledger, _span(dates, "data"), manifest, "invest-mine evaluate (full sample)"
        )
    panel = build_panel(bars, **_optional_inputs(args))
    values = restrict(evaluate(args.expr, panel) * args.orientation, panel)
    label = restrict(forward_returns(panel["open"], args.horizon), panel)
    ic = daily_ic(values, label, "spearman")
    summary = ic_summary(ic, args.horizon)
    summary["orientation"] = args.orientation
    summary["pearson_mean_ic"] = ic_summary(daily_ic(values, label, "pearson"), args.horizon)[
        "mean_ic"
    ]
    summary["rank_autocorrelation_1d"] = rank_autocorrelation(values)
    # Deciles and tails use the same dates; portfolios apply this threshold to eligible names.
    min_cross_section = max(args.buckets, args.min_cross_section)
    write_factor_report(
        args.out,
        expression=canonical(args.expr),
        summary=summary,
        ic=ic,
        quantiles=quantile_returns(values, label, args.buckets, min_cross_section),
        tails=tail_returns(
            values,
            label,
            min_names=args.min_tail_names,
            n_buckets=args.buckets,
            min_cross_section=min_cross_section,
        ),
        config={
            "dataset_id": manifest.dataset_id,
            "dataset_sha256": manifest.content_sha256,
            "horizon": args.horizon,
            "orientation": args.orientation,
            "buckets": args.buckets,
            "min_tail_names": args.min_tail_names,
            "min_cross_section": min_cross_section,
            "bucket_rule": BUCKET_RULE,
            "tail_rule": TAIL_RULE,
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
    panel = build_panel(bars, **_optional_inputs(args))
    params: dict[str, Any] = {
        "n_trials": args.trials,
        "seed": args.seed,
        "horizon": args.horizon,
        "dev_fraction": None if args.confirm_start else args.dev_fraction,
        "confirm_start": args.confirm_start,
        "embargo": args.embargo,
        "top_k": args.top_k,
    }
    try:
        split = chronological_split(
            pd.DatetimeIndex(panel["close"].index),
            args.dev_fraction,
            args.horizon,
            args.embargo,
            args.confirm_start,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    # Decision dates alone omit prices used by forward-return labels in the purge gap.
    development = _span(split.dev_observation_dates, "development")
    confirmation = _span(split.confirm_dates, "confirmation")
    identity = {
        "dataset_sha256": manifest.content_sha256,
        **_input_hashes(args),
        "operator_version": OPERATOR_VERSION,
        "params": params,
        "development": development.to_json(),
        "confirmation": confirmation.to_json(),
    }
    exp_id = ledger.experiment_id(identity)
    use, reasons = "unrecorded", list[str]()
    if args.ledger is not None:
        # Decided before any candidate is scored, so the outcome cannot influence it.
        try:
            use, reasons = ledger.assess_confirmation(
                ledger.load(args.ledger), development, confirmation, exp_id
            )
        except LedgerError as exc:
            raise SystemExit(f"{args.ledger}: {exc}") from exc
        if use == "exploratory" and args.require_confirmatory:
            raise SystemExit(
                f"{args.ledger}: confirmation data was already used ({'; '.join(reasons)})"
            )
    result = run_search(
        panel,
        n_trials=args.trials,
        seed=args.seed,
        horizon=args.horizon,
        dev_fraction=args.dev_fraction,
        confirm_start=args.confirm_start,
        embargo=args.embargo,
        top_k=args.top_k,
        dataset_id=manifest.dataset_id,
        dataset_sha256=manifest.content_sha256,
    )
    result.confirmation = mark_confirmation_use(result.confirmation, use)
    tag = {"experiment_id": exp_id, "confirmation_use": use}
    result.family = [replace(f, selection={**f.selection, **tag}) for f in result.family]
    result.config["experiment"] = {
        **tag,
        "reasons": reasons,
        "ledger": None if args.ledger is None else str(args.ledger),
        "identity": identity,
    }
    if args.ledger is not None:
        # Recorded before any result is written, so no confirmation output goes unrecorded.
        ledger.append(
            args.ledger,
            "experiment",
            {
                "experiment_id": exp_id,
                "dataset_id": manifest.dataset_id,
                **identity,
                "family": [f.factor_id for f in result.family],
                "n_proposals": len(result.ledger),
                "confirmation_use": use,
                "reasons": reasons,
            },
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
    if use == "exploratory":
        print(f"Exploratory: confirmation data was already used ({'; '.join(reasons)}).")
    return 0


def _confirm(args: argparse.Namespace) -> int:
    """Test one fixed, pre-registered formula once on a confirmation window.

    Only ``freeze`` artifacts qualify: a factor selected by a search belongs to its
    Holm-adjusted family, and confirming members one by one would undo that adjustment.
    The ledger records the run before any result is written, exactly like ``search``.
    """
    factor = FrozenFactor.load(args.factor)
    if factor.selection.get("method") != "fixed_formula":
        raise SystemExit(
            f"{args.factor}: only fixed formulas from `invest-mine freeze` can be confirmed "
            "alone; confirm search-selected factors with their family (`search --confirm-start`)"
        )
    manifest, bars = read_market_bars(args.data)
    panel = build_panel(bars, **_optional_inputs(args))
    dates = pd.DatetimeIndex(panel["close"].index)
    start = pd.Timestamp(args.confirm_start)
    k = int(dates.searchsorted(start))
    if k >= len(dates) or start < dates[0] or (k == 0 and factor.lookback > 0):
        raise SystemExit(
            f"--confirm-start {args.confirm_start} leaves no history or confirmation data"
        )
    # Sessions before confirmation are read only as formula inputs, never as outcomes.
    context = _span(dates[max(k - factor.lookback, 0) : k], "history") if factor.lookback else None
    confirmation = _span(dates[k:], "confirmation")
    identity = {
        "dataset_sha256": manifest.content_sha256,
        **_input_hashes(args),
        "operator_version": OPERATOR_VERSION,
        "params": {
            "method": "fixed_formula",
            "factor_id": factor.factor_id,
            "horizon": factor.horizon_days,
            "lookback_sessions": factor.lookback,
        },
        "development": context.to_json() if context is not None else None,
        "confirmation": confirmation.to_json(),
    }
    exp_id = ledger.experiment_id(identity)
    try:
        use, reasons = ledger.assess_confirmation(
            ledger.load(args.ledger), context, confirmation, exp_id
        )
    except LedgerError as exc:
        raise SystemExit(f"{args.ledger}: {exc}") from exc
    if use == "exploratory" and args.require_confirmatory:
        raise SystemExit(
            f"{args.ledger}: confirmation data was already used ({'; '.join(reasons)})"
        )
    label = restrict(forward_returns(panel["open"], factor.horizon_days), panel)
    table = mark_confirmation_use(
        confirm([factor], panel, label.loc[dates[k:]], factor.horizon_days), use
    )
    ledger.append(
        args.ledger,
        "experiment",
        {
            "experiment_id": exp_id,
            "dataset_id": manifest.dataset_id,
            **identity,
            "family": [factor.factor_id],
            "n_proposals": 1,
            "confirmation_use": use,
            "reasons": reasons,
        },
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "confirmation.csv", index=False)
    config = {
        "factor": factor.to_json(),
        "horizon": factor.horizon_days,
        "confirm_start": args.confirm_start,
        "experiment": {
            "experiment_id": exp_id,
            "confirmation_use": use,
            "reasons": reasons,
            "ledger": str(args.ledger),
            "identity": identity,
        },
    }
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    print(
        table[
            ["factor_id", "expression", "confirm_mean_rank_ic", "p_one_sided", "status"]
        ].to_string(index=False)
    )
    if use == "exploratory":
        print(f"Exploratory: confirmation data was already used ({'; '.join(reasons)}).")
    return 0


def _from_search(root: Path, rank: int) -> FrozenFactor:
    """Export in the family order frozen on development data before confirmation.

    The confirmation table retains that order. Read only candidate IDs: neither
    confirmation statistics nor pass/reject outcomes may select the replayed factor.
    """
    family = pd.read_csv(root / "confirmation.csv", usecols=["factor_id"])
    if rank < 1 or rank > len(family):
        raise SystemExit(
            f"{root}: {len(family)} factor(s) in the frozen family; cannot export rank {rank}"
        )
    factor_id = str(family.iloc[rank - 1]["factor_id"])
    return FrozenFactor.load(root / "factors" / f"{factor_id}.json")


def _out_of_sample_start(confirm_start: str, start: str | None) -> str:
    """First export date with search evidence: never before its confirmation period.

    Both are ISO dates (``YYYY-MM-DD``), so they compare as strings.
    """
    if start is not None and start < confirm_start:
        raise SystemExit(
            f"--start {start} precedes the confirmation period ({confirm_start}); "
            "those decisions were used for selection"
        )
    return start or confirm_start


def _json_number(value: Any) -> float | int | None:
    """A CSV number as JSON; undefined (NaN or infinite) statistics become null."""
    value = value.item() if isinstance(value, np.generic) else value
    return value if isinstance(value, int | float) and math.isfinite(value) else None


def _confirmation_evidence(root: Path, factor: FrozenFactor) -> dict[str, Any]:
    """Factor evidence from a ``search`` or ``confirm`` output, for the exported signals.

    Called only after the factor is chosen: the outcome describes the factor and travels
    with its signals to portfolio reports, but never decides which factor is exported.
    """
    try:
        table = pd.read_csv(root / "confirmation.csv")
        config = json.loads((root / "config.json").read_text())
    except (OSError, ValueError) as exc:
        raise SystemExit(f"{root}: cannot read confirmation output ({exc})") from exc
    needed = {"factor_id", "status", "test_outcome", "confirmation_use", "family_size"}
    if missing := sorted(needed - set(table.columns)):
        raise SystemExit(f"{root}: confirmation.csv lacks {missing}; rerun the confirmation")
    rows = table[table["factor_id"] == factor.factor_id]
    if len(rows) != 1:
        raise SystemExit(f"{root}: factor {factor.factor_id} was not confirmed in this output")
    row = rows.iloc[0]
    experiment = config.get("experiment") or {}
    identity = experiment.get("identity") or {}
    if row["confirmation_use"] != experiment.get("confirmation_use"):
        raise SystemExit(f"{root}: confirmation.csv and config.json disagree on confirmation use")
    tagged = factor.selection.get("experiment_id")
    if tagged is not None and tagged != experiment.get("experiment_id"):
        raise SystemExit(
            f"{root}: factor {factor.factor_id} was selected in experiment {tagged}, "
            f"not {experiment.get('experiment_id')}"
        )
    params = identity.get("params") or {}
    tested_horizon = params.get("horizon")
    if type(tested_horizon) is not int or tested_horizon != factor.horizon_days:
        raise SystemExit(
            f"{root}: confirmation horizon {tested_horizon!r} does not match "
            f"factor horizon {factor.horizon_days!r}"
        )
    source = "confirm" if params.get("method") == "fixed_formula" else "search"
    if source == "search" and tagged != experiment.get("experiment_id"):
        # Only the search's own factor file carries its trial count. A `freeze` copy of the
        # same formula has the same factor id but would export n_trials = 1.
        raise SystemExit(
            f"{root}: factor {factor.factor_id} is not this search's own factor file "
            f"(selection {factor.selection.get('method')!r}); export the file in "
            f"{root / 'factors'} instead"
        )
    evidence = {
        "evidence_version": FACTOR_EVIDENCE_VERSION,
        "factor_id": factor.factor_id,
        "horizon_days": tested_horizon,
        "experiment_id": experiment.get("experiment_id"),
        "source": source,
        "confirmation_use": row["confirmation_use"],
        "test_outcome": row["test_outcome"],
        "status": row["status"],
        "family_size": int(row["family_size"]),
        "confirmation_window": identity.get("confirmation"),
        "statistics": {
            key: _json_number(row[key]) if key in row else None
            for key in FACTOR_EVIDENCE_STATISTICS
        },
    }
    try:
        validate_factor_evidence(
            evidence, factor_id=factor.factor_id, horizon_days=factor.horizon_days
        )
    except BundleError as exc:
        raise SystemExit(f"{root}: {exc}") from exc
    return evidence


def _freeze(args: argparse.Namespace) -> int:
    """Freeze one formula chosen before looking at the data: no fitting, one trial."""
    if args.horizon < 1:
        raise SystemExit("--horizon must be at least 1")
    factor = FrozenFactor(
        expression=args.expr,
        orientation=args.orientation,
        horizon_days=args.horizon,
        training_start="",
        training_end="",
        dataset_id="",
        dataset_sha256=None,
        selection={
            "method": "fixed_formula",
            "n_proposals": 1,
            "note": "specified a priori; no data were used to select or orient it",
        },
    )
    path = factor.save(args.out)
    print(json.dumps({"factor": str(path), "factor_id": factor.factor_id, "n_trials": 1}))
    return 0


def _export(args: argparse.Namespace) -> int:
    start = args.start
    if start is not None:
        try:
            start = datetime.strptime(start, "%Y-%m-%d").date().isoformat()
        except ValueError as exc:
            raise SystemExit(f"--start {start!r} is not a YYYY-MM-DD date") from exc
    evidence: dict[str, Any] | None
    if args.from_search is not None:
        if args.confirmation is not None:
            raise SystemExit("--from-search already attaches its own confirmation evidence")
        factor = _from_search(args.from_search, args.rank)
        evidence = _confirmation_evidence(args.from_search, factor)
    else:
        factor = FrozenFactor.load(args.factor)
        evidence = (
            None if args.confirmation is None else _confirmation_evidence(args.confirmation, factor)
        )
    if evidence is not None and evidence["source"] == "search":
        # Search evidence covers only the confirmation period; earlier dates chose the factor.
        start = _out_of_sample_start(evidence["confirmation_window"]["start"], start)
    manifest, bars = read_market_bars(args.data)
    if factor.dataset_sha256 and factor.dataset_sha256 != manifest.content_sha256:
        print(
            "note: exporting on a different dataset than the factor was selected on",
            file=sys.stderr,
        )
    try:
        out = export_signals(
            factor,
            bars,
            args.out,
            dataset_id=manifest.dataset_id,
            start=start,
            fmt=args.format,
            evidence=evidence,
            **_optional_inputs(args),
        )
    except BundleError as exc:
        raise SystemExit(f"{args.out}: {exc}") from exc
    print(
        json.dumps(
            {
                "signals": str(args.out),
                "rows": out.row_count,
                "factor_id": factor.factor_id,
                "start": start,
                "factor_status": None if evidence is None else evidence["status"],
            }
        )
    )
    return 0


def _ledger(args: argparse.Namespace) -> int:
    try:
        window = Window.parse(args.start, args.end)
        entries = ledger.load(args.ledger)
        if args.action == "check":
            ledger.check_inspection(entries, window)
            print(json.dumps({"window": str(window), "reserved": False}))
            return 0
        if args.action == "reserve":
            used = [
                e
                for e in entries
                if e["kind"] != "reservation"
                and any(window.overlaps(observed) for observed in ledger.entry_windows(e).values())
            ]
            if used:
                raise LedgerError(f"{window} was already inspected or used by a search")
        else:
            ledger.check_inspection(entries, window)
    except LedgerError as exc:
        raise SystemExit(f"{args.ledger}: {exc}") from exc
    kind = "reservation" if args.action == "reserve" else "inspection"
    entry = ledger.append(args.ledger, kind, {"window": window.to_json(), "note": args.note})
    print(json.dumps(entry))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="invest-mine", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ev = sub.add_parser("evaluate", help="diagnose one expression")
    ev.add_argument("--data", type=Path, required=True)
    ev.add_argument("--expr", required=True)
    ev.add_argument(
        "--orientation",
        type=int,
        choices=(-1, 1),
        default=1,
        help="frozen score direction, as used by export (default 1)",
    )
    ev.add_argument("--horizon", type=int, default=1)
    ev.add_argument("--buckets", type=int, default=10)
    ev.add_argument(
        "--min-tail-names",
        type=int,
        default=5,
        help="fewest names a tail slice may hold on a date before it is insufficient_data",
    )
    ev.add_argument(
        "--min-cross-section",
        type=int,
        default=1,
        help="skip dates with fewer scored names in deciles and tails (at least --buckets); "
        "pass the evaluation config's strategy.min_names to use the bucket portfolios' "
        "threshold (they count decision-time eligible names)",
    )
    ev.add_argument("--out", type=Path, required=True)

    se = sub.add_parser("search", help="random search with a ledger and frozen confirmation")
    se.add_argument("--data", type=Path, required=True)
    se.add_argument("--trials", type=int, default=200)
    se.add_argument("--seed", type=int, default=0)
    se.add_argument("--horizon", type=int, default=1)
    se.add_argument("--dev-fraction", type=float, default=0.6)
    se.add_argument("--embargo", type=int, default=0)
    se.add_argument("--top-k", type=int, default=5)
    se.add_argument(
        "--confirm-start",
        help="first confirmation date (YYYY-MM-DD); overrides --dev-fraction, "
        "e.g. to confirm on a reserved window",
    )
    se.add_argument(
        "--require-confirmatory",
        action="store_true",
        help="with --ledger: refuse to run if the confirmation data was already used",
    )
    se.add_argument("--out", type=Path, required=True)

    fr = sub.add_parser("freeze", help="freeze a fixed, pre-specified formula (n_trials=1)")
    fr.add_argument("--expr", required=True)
    fr.add_argument("--horizon", type=int, required=True, help="intended holding horizon")
    fr.add_argument(
        "--orientation",
        type=int,
        choices=[1, -1],
        default=1,
        help="+1: higher value is more attractive; -1: lower is (e.g. reversal)",
    )
    fr.add_argument("--out", type=Path, required=True, help="frozen factor JSON to write")

    co = sub.add_parser(
        "confirm", help="test one fixed formula once on a confirmation window (ledger required)"
    )
    co.add_argument("--data", type=Path, required=True)
    co.add_argument("--factor", type=Path, required=True, help="frozen factor JSON from freeze")
    co.add_argument(
        "--confirm-start",
        required=True,
        help="first confirmation date (YYYY-MM-DD), e.g. the start of a reserved window",
    )
    co.add_argument(
        "--ledger",
        type=Path,
        required=True,
        help="confirmation-use ledger: classify the run as confirmatory or exploratory",
    )
    co.add_argument(
        "--require-confirmatory",
        action="store_true",
        help="refuse to run if the confirmation data was already used",
    )
    co.add_argument("--out", type=Path, required=True)

    ex = sub.add_parser("export", help="apply a frozen factor and publish a signals bundle")
    ex.add_argument("--data", type=Path, required=True)
    source = ex.add_mutually_exclusive_group(required=True)
    source.add_argument("--factor", type=Path, help="frozen factor JSON")
    source.add_argument(
        "--from-search",
        type=Path,
        help="search output: export a development-selected factor from its confirmation start",
    )
    ex.add_argument(
        "--rank", type=int, default=1, help="with --from-search: n-th factor in the frozen family"
    )
    ex.add_argument("--out", type=Path, required=True)
    ex.add_argument(
        "--start",
        help="first decision date to export (YYYY-MM-DD); with search evidence (--from-search, "
        "or --confirmation <search output>) it defaults to, and may not precede, the "
        "confirmation start",
    )
    ex.add_argument("--format", choices=["csv", "sqlite", "parquet"], default="csv")
    ex.add_argument(
        "--confirmation",
        type=Path,
        help="with --factor: `search` or `confirm` output whose confirmation of this factor "
        "is attached to the signals as evidence (it never selects the factor)",
    )

    for p in (ev, se, co, ex):
        p.add_argument("--universe", type=Path, help="universe bundle (point-in-time membership)")
        p.add_argument("--fundamentals", type=Path, help="fundamentals bundle (fund_<field>)")
    ev.add_argument(
        "--ledger", type=Path, help="confirmation-use ledger: refuse reserved data, record use"
    )
    se.add_argument(
        "--ledger",
        type=Path,
        help="confirmation-use ledger: classify the run as confirmatory or exploratory",
    )

    le = sub.add_parser("ledger", help="reserve, record or check windows in a ledger")
    le.add_argument(
        "action",
        choices=["reserve", "inspect", "check"],
        help="reserve: keep a window untouched for confirmation; inspect: record a window "
        "as already looked at; check: fail if a window touches an unused reservation",
    )
    le.add_argument("--ledger", type=Path, required=True)
    le.add_argument("--start", required=True, help="first date (YYYY-MM-DD)")
    le.add_argument("--end", help="last date (YYYY-MM-DD); open-ended if omitted")
    le.add_argument("--note", default="", help="why (stored with reserve/inspect)")

    args = parser.parse_args(argv)
    commands = {
        "evaluate": _evaluate,
        "search": _search,
        "freeze": _freeze,
        "confirm": _confirm,
        "export": _export,
        "ledger": _ledger,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
