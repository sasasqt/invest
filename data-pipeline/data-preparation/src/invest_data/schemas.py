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
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from invest_data.bundle import BundleError, Column, Manifest, read_bundle, write_bundle

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
