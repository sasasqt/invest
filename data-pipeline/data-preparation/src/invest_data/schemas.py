"""Financial dataset kinds layered on the generic v1 bundle contract.

Two kinds are defined so producers and consumers can validate independently:

``market_bars`` (daily bars)
    Keys ``(date, instrument)``. ``date`` is the trading session. ``open`` is observable at
    the session open and ``high/low/close/volume`` at the session close. Prices are adjusted
    according to ``metadata.price_adjustment``. An instrument's absence from a session means
    it was not tradable (not listed, halted, or delisted).

``universe``
    Point-in-time membership intervals ``(universe, instrument, start_date, end_date)``.
    An instrument is a member on date ``d`` when ``start_date <= d < end_date``
    (``end_date`` null = still a member). Intervals are known on their ``start_date``.

``fundamentals``
    Point-in-time values ``(instrument, field, period_end, available_date, value)``. A row
    may be used for decisions at the close of ``available_date`` or later. A revision is a
    new row for the same ``(instrument, field, period_end)`` with a later
    ``available_date``; earlier rows are never overwritten.

``signals``
    Keys ``(decision_date, instrument)``. ``score`` uses only information available at the
    close of ``decision_date`` (``metadata.available_at == "decision_date_close"``); a
    consumer may act on it no earlier than the next session. Higher score = more attractive.
    Optional ``metadata.factor_evidence`` carries the factor's confirmation evidence
    (experiment identity, confirmation use and outcome) to portfolio reports; see
    :func:`validate_factor_evidence`. Search evidence also requires ``n_trials`` of at least
    its family size and no decision before its confirmation window.
"""

from __future__ import annotations

import math
import os
from datetime import date
from typing import Any, NoReturn

import pandas as pd

from invest_data.bundle import (
    BundleError,
    Column,
    Manifest,
    format_value,
    read_bundle,
    write_bundle,
)

MARKET_BARS = "market_bars"
UNIVERSE = "universe"
FUNDAMENTALS = "fundamentals"
SIGNALS = "signals"

MARKET_BAR_COLUMNS = (
    Column("date", "date", nullable=False),
    Column("instrument", "string", nullable=False),
    Column("open", "float64", nullable=False, unit="price"),
    Column("high", "float64", nullable=False, unit="price"),
    Column("low", "float64", nullable=False, unit="price"),
    Column("close", "float64", nullable=False, unit="price"),
    Column("volume", "float64", nullable=False, unit="shares"),
)
SIGNAL_COLUMNS = (
    Column("decision_date", "date", nullable=False),
    Column("instrument", "string", nullable=False),
    Column("score", "float64", nullable=False),
)
UNIVERSE_COLUMNS = (
    Column("universe", "string", nullable=False),
    Column("instrument", "string", nullable=False),
    Column("start_date", "date", nullable=False),
    Column("end_date", "date", nullable=True),
)
FUNDAMENTAL_COLUMNS = (
    Column("instrument", "string", nullable=False),
    Column("field", "string", nullable=False),
    Column("period_end", "date", nullable=False),
    Column("available_date", "date", nullable=False),
    Column("value", "float64", nullable=False),
)
REQUIRED_MARKET_METADATA = ("frequency", "currency", "price_adjustment", "calendar")
REQUIRED_SIGNAL_METADATA = ("available_at", "signal_type", "factor_id", "horizon_days")

# Version 2 binds factor evidence to the tested prediction/holding horizon.
FACTOR_EVIDENCE_VERSION = 2
CONFIRMATION_USES = ("confirmatory", "exploratory", "unrecorded")
FACTOR_TEST_OUTCOMES = ("confirmation_passed", "rejected", "inconclusive")
FACTOR_STATUSES = (*FACTOR_TEST_OUTCOMES, "exploratory")
FACTOR_EVIDENCE_SOURCES = ("search", "confirm")
FACTOR_EVIDENCE_STATISTICS = (
    "confirm_mean_rank_ic",
    "confirm_t",
    "p_one_sided",
    "p_holm",
    "n_dates",
)


def _check_columns(manifest: Manifest, expected: tuple[Column, ...]) -> None:
    got = [(c.name, c.type) for c in manifest.columns]
    want = [(c.name, c.type) for c in expected]
    if got != want:
        raise BundleError(f"{manifest.dataset_kind}: columns {got} != expected {want}")


def _validate_metadata(metadata: dict[str, Any], required: tuple[str, ...], kind: str) -> None:
    missing = [k for k in required if k not in metadata]
    if missing:
        raise BundleError(f"{kind}: metadata missing {missing}")
    if kind == SIGNALS and "n_trials" in metadata:
        n_trials = metadata["n_trials"]
        if type(n_trials) is not int or n_trials < 1:
            raise BundleError("signals: n_trials must be a positive integer (not a boolean)")
    if kind == SIGNALS and "factor_evidence" in metadata:
        if type(metadata["horizon_days"]) is not int or metadata["horizon_days"] < 1:
            raise BundleError(
                "signals: horizon_days must be a positive integer with factor_evidence"
            )
        evidence = metadata["factor_evidence"]
        validate_factor_evidence(
            evidence,
            factor_id=metadata.get("factor_id"),
            horizon_days=metadata.get("horizon_days"),
        )
        # A searched factor was chosen from at least its family's proposals.
        if evidence["source"] == "search" and metadata.get("n_trials", 0) < evidence["family_size"]:
            raise BundleError(
                "signals: search evidence needs n_trials >= its family_size "
                f"({evidence['family_size']}), got {metadata.get('n_trials')!r}; a searched "
                "factor's signals carry the search's proposal count"
            )


def _check_signal_window(first: str | None, metadata: dict[str, Any]) -> None:
    """Signals with search evidence start at its confirmation window; earlier dates chose it.

    ``first`` is the earliest stored ``decision_date`` (ISO), or None for no rows.
    """
    evidence = metadata.get("factor_evidence")
    if evidence is None or evidence["source"] != "search":
        return
    if first is not None and first < evidence["confirmation_window"]["start"]:
        raise BundleError(
            f"signals: decisions from {first} precede the search evidence's confirmation "
            f"window ({evidence['confirmation_window']['start']}); those dates selected the "
            "factor. Re-export from the confirmation start (`invest-mine export --from-search`)"
        )


def _first_stored_date(values: pd.Series) -> str | None:
    """Earliest ISO date the bundle writer would store for ``values``, whatever their dtype."""
    return min(filter(None, map(_stored_date, values.tolist())), default=None)


def _stored_date(value: Any) -> str | None:
    """The ISO date the bundle writer stores for ``value``; None if it would refuse it."""
    try:
        stored = format_value(SIGNAL_COLUMNS[0], value)
    except (BundleError, TypeError, ValueError, OverflowError):
        return None
    return stored if isinstance(stored, str) else None


def _iso_date(value: Any) -> bool:
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def validate_factor_evidence(
    evidence: Any, *, factor_id: Any = None, horizon_days: Any = None
) -> None:
    """Check horizon-bound factor confirmation evidence carried by signals (v2).

    ``status`` is what a report may show as the factor outcome: it equals ``test_outcome``
    unless the confirmation data had already been used (``confirmation_use =
    "exploratory"``), in which case it is ``"exploratory"`` whatever the test said. The
    evidence describes the factor only; it never selects which factor was exported.
    Version 1 has no tested horizon and is refused; re-export from the original
    confirmation output rather than rerunning confirmation or relabelling old evidence.
    """

    def fail(message: str) -> NoReturn:
        raise BundleError(f"signals: factor_evidence {message}")

    if not isinstance(evidence, dict):
        fail("must be a JSON object")
    if (
        type(evidence.get("evidence_version")) is not int
        or evidence["evidence_version"] != FACTOR_EVIDENCE_VERSION
    ):
        fail(
            f"evidence_version must be {FACTOR_EVIDENCE_VERSION}; "
            "re-export signals from the original confirmation output to bind the tested horizon"
        )
    for key in ("factor_id", "experiment_id"):
        if not isinstance(evidence.get(key), str) or not evidence[key]:
            fail(f"{key} must be a non-empty string")
    if factor_id is not None and evidence["factor_id"] != factor_id:
        fail(f"is for factor {evidence['factor_id']!r}, not {factor_id!r}")
    tested_horizon = evidence.get("horizon_days")
    if type(tested_horizon) is not int or tested_horizon < 1:
        fail("horizon_days must be a positive integer")
    if horizon_days is not None and (
        type(horizon_days) is not int or tested_horizon != horizon_days
    ):
        fail(
            f"horizon_days {tested_horizon!r} does not match signals horizon_days {horizon_days!r}"
        )
    choices = (
        ("source", FACTOR_EVIDENCE_SOURCES),
        ("confirmation_use", CONFIRMATION_USES),
        ("test_outcome", FACTOR_TEST_OUTCOMES),
        ("status", FACTOR_STATUSES),
    )
    for key, allowed in choices:
        if evidence.get(key) not in allowed:
            fail(f"{key} must be one of {allowed}, got {evidence.get(key)!r}")
    expected = (
        "exploratory" if evidence["confirmation_use"] == "exploratory" else evidence["test_outcome"]
    )
    if evidence["status"] != expected:
        fail(
            f"status {evidence['status']!r} contradicts confirmation_use "
            f"{evidence['confirmation_use']!r} and test_outcome {evidence['test_outcome']!r}"
        )
    family_size = evidence.get("family_size")
    if type(family_size) is not int or family_size < 1:
        fail("family_size must be a positive integer")
    if evidence.get("source") == "confirm" and family_size != 1:
        fail("from `confirm` tests one fixed formula, so family_size must be 1")
    window = evidence.get("confirmation_window")
    if (
        not isinstance(window, dict)
        or not _iso_date(window.get("start"))
        or not _iso_date(window.get("end"))
        or window["end"] < window["start"]
    ):
        fail("confirmation_window must have ISO start <= end dates")
    stats = evidence.get("statistics")
    if not isinstance(stats, dict) or set(stats) != set(FACTOR_EVIDENCE_STATISTICS):
        fail(f"statistics must have exactly the keys {FACTOR_EVIDENCE_STATISTICS}")
    for key, value in stats.items():
        # Undefined statistics are null; NaN and infinities are not valid JSON evidence.
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
        ):
            fail(f"statistics.{key} must be a finite number or null")


def _check_metadata(manifest: Manifest, required: tuple[str, ...]) -> None:
    _validate_metadata(manifest.metadata, required, str(manifest.dataset_kind))


def publish_market_bars(
    frame: pd.DataFrame,
    path: str | os.PathLike[str],
    *,
    dataset_id: str,
    metadata: dict[str, Any],
    provenance: dict[str, Any] | None = None,
    fmt: str = "csv",
) -> Manifest:
    _validate_metadata(metadata, REQUIRED_MARKET_METADATA, MARKET_BARS)
    frame = frame[[c.name for c in MARKET_BAR_COLUMNS]].sort_values(["date", "instrument"])
    validate_market_frame(frame)
    return write_bundle(
        frame.reset_index(drop=True),
        path,
        dataset_id=dataset_id,
        fmt=fmt,
        columns=MARKET_BAR_COLUMNS,
        primary_key=("date", "instrument"),
        provenance=provenance,
        dataset_kind=MARKET_BARS,
        metadata=metadata,
    )


def validate_market_frame(frame: pd.DataFrame) -> None:
    """Semantic checks beyond types: positive prices and a consistent OHLC range."""
    px = frame[["open", "high", "low", "close"]]
    if (px <= 0).to_numpy().any():
        raise BundleError("market_bars: prices must be positive")
    if (frame["volume"] < 0).any():
        raise BundleError("market_bars: volume must be non-negative")
    hi_ok = frame["high"] >= frame[["open", "close"]].max(axis=1) * (1 - 1e-12)
    lo_ok = frame["low"] <= frame[["open", "close"]].min(axis=1) * (1 + 1e-12)
    if not (hi_ok & lo_ok).all():
        raise BundleError("market_bars: high/low inconsistent with open/close")


def read_market_bars(path: str | os.PathLike[str]) -> tuple[Manifest, pd.DataFrame]:
    manifest, frame = read_bundle(path)
    if manifest.dataset_kind != MARKET_BARS:
        raise BundleError(f"expected dataset_kind {MARKET_BARS!r}, got {manifest.dataset_kind!r}")
    _check_columns(manifest, MARKET_BAR_COLUMNS)
    _check_metadata(manifest, REQUIRED_MARKET_METADATA)
    validate_market_frame(frame)
    return manifest, frame


def publish_signals(
    frame: pd.DataFrame,
    path: str | os.PathLike[str],
    *,
    dataset_id: str,
    metadata: dict[str, Any],
    provenance: dict[str, Any] | None = None,
    fmt: str = "csv",
) -> Manifest:
    frame = frame[[c.name for c in SIGNAL_COLUMNS]].sort_values(["decision_date", "instrument"])
    meta = {"available_at": "decision_date_close", "signal_type": "score", **metadata}
    _validate_metadata(meta, REQUIRED_SIGNAL_METADATA, SIGNALS)
    if meta["available_at"] != "decision_date_close":
        raise BundleError("signals: only available_at='decision_date_close' is supported")
    _check_signal_window(_first_stored_date(frame["decision_date"]), meta)
    return write_bundle(
        frame.reset_index(drop=True),
        path,
        dataset_id=dataset_id,
        fmt=fmt,
        columns=SIGNAL_COLUMNS,
        primary_key=("decision_date", "instrument"),
        provenance=provenance,
        dataset_kind=SIGNALS,
        metadata=meta,
    )


def read_signals(path: str | os.PathLike[str]) -> tuple[Manifest, pd.DataFrame]:
    manifest, frame = read_bundle(path)
    if manifest.dataset_kind != SIGNALS:
        raise BundleError(f"expected dataset_kind {SIGNALS!r}, got {manifest.dataset_kind!r}")
    _check_columns(manifest, SIGNAL_COLUMNS)
    _check_metadata(manifest, REQUIRED_SIGNAL_METADATA)
    if manifest.metadata["available_at"] != "decision_date_close":
        raise BundleError("signals: unsupported available_at convention")
    # The reader returns validated naive datetime64 dates.
    first = frame["decision_date"].min()
    _check_signal_window(None if pd.isna(first) else first.date().isoformat(), manifest.metadata)
    return manifest, frame


def validate_universe_frame(frame: pd.DataFrame) -> None:
    end = frame["end_date"]
    if (end.notna() & (end <= frame["start_date"])).any():
        raise BundleError("universe: end_date must be after start_date")
    ordered = frame.sort_values(["universe", "instrument", "start_date"])
    prev_end = ordered.groupby(["universe", "instrument"])["end_date"].shift(1)
    first = ordered.groupby(["universe", "instrument"]).cumcount() == 0
    open_before = prev_end.isna() & ~first
    if (open_before | (prev_end > ordered["start_date"])).any():
        raise BundleError("universe: overlapping membership intervals")


def publish_universe(
    frame: pd.DataFrame,
    path: str | os.PathLike[str],
    *,
    dataset_id: str,
    metadata: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    fmt: str = "csv",
) -> Manifest:
    frame = frame[[c.name for c in UNIVERSE_COLUMNS]].sort_values(
        ["universe", "instrument", "start_date"]
    )
    validate_universe_frame(frame)
    return write_bundle(
        frame.reset_index(drop=True),
        path,
        dataset_id=dataset_id,
        fmt=fmt,
        columns=UNIVERSE_COLUMNS,
        primary_key=("universe", "instrument", "start_date"),
        provenance=provenance,
        dataset_kind=UNIVERSE,
        metadata={"interval": "start_date <= date < end_date", **(metadata or {})},
    )


def read_universe(path: str | os.PathLike[str]) -> tuple[Manifest, pd.DataFrame]:
    manifest, frame = read_bundle(path)
    if manifest.dataset_kind != UNIVERSE:
        raise BundleError(f"expected dataset_kind {UNIVERSE!r}, got {manifest.dataset_kind!r}")
    _check_columns(manifest, UNIVERSE_COLUMNS)
    validate_universe_frame(frame)
    return manifest, frame


def validate_fundamentals_frame(frame: pd.DataFrame) -> None:
    if (frame["available_date"] < frame["period_end"]).any():
        raise BundleError("fundamentals: available_date before period_end")
    if not frame["field"].astype(str).str.fullmatch(r"[a-z][a-z0-9_]*").all():
        raise BundleError("fundamentals: field names must match [a-z][a-z0-9_]*")


def publish_fundamentals(
    frame: pd.DataFrame,
    path: str | os.PathLike[str],
    *,
    dataset_id: str,
    metadata: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    fmt: str = "csv",
) -> Manifest:
    keys = ["instrument", "field", "period_end", "available_date"]
    frame = frame[[c.name for c in FUNDAMENTAL_COLUMNS]].sort_values(keys)
    validate_fundamentals_frame(frame)
    return write_bundle(
        frame.reset_index(drop=True),
        path,
        dataset_id=dataset_id,
        fmt=fmt,
        columns=FUNDAMENTAL_COLUMNS,
        primary_key=keys,
        provenance=provenance,
        dataset_kind=FUNDAMENTALS,
        metadata={"available_at": "available_date_close", **(metadata or {})},
    )


def read_fundamentals(path: str | os.PathLike[str]) -> tuple[Manifest, pd.DataFrame]:
    manifest, frame = read_bundle(path)
    if manifest.dataset_kind != FUNDAMENTALS:
        raise BundleError(f"expected dataset_kind {FUNDAMENTALS!r}, got {manifest.dataset_kind!r}")
    _check_columns(manifest, FUNDAMENTAL_COLUMNS)
    validate_fundamentals_frame(frame)
    return manifest, frame
