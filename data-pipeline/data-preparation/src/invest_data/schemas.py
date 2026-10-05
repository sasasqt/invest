"""Financial dataset kinds layered on the generic v1 bundle contract.

Two kinds are defined so producers and consumers can validate independently:

``market_bars`` (daily bars)
    Keys ``(date, instrument)``. ``date`` is the trading session. ``open`` is observable at
    the session open and ``high/low/close/volume`` at the session close. Prices are adjusted
    according to ``metadata.price_adjustment``. An instrument's absence from a session means
    it was not tradable (not listed, halted, or delisted).

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
REQUIRED_MARKET_METADATA = ("frequency", "currency", "price_adjustment", "calendar")
REQUIRED_SIGNAL_METADATA = ("available_at", "signal_type", "factor_id", "horizon_days")


def _check_columns(manifest: Manifest, expected: tuple[Column, ...]) -> None:
    got = [(c.name, c.type) for c in manifest.columns]
    want = [(c.name, c.type) for c in expected]
    if got != want:
        raise BundleError(f"{manifest.dataset_kind}: columns {got} != expected {want}")


def _check_metadata(manifest: Manifest, required: tuple[str, ...]) -> None:
    missing = [k for k in required if k not in manifest.metadata]
    if missing:
        raise BundleError(f"{manifest.dataset_kind}: metadata missing {missing}")


def publish_market_bars(
    frame: pd.DataFrame,
    path: str | os.PathLike[str],
    *,
    dataset_id: str,
    metadata: dict[str, Any],
    provenance: dict[str, Any] | None = None,
    fmt: str = "csv",
) -> Manifest:
    frame = frame[[c.name for c in MARKET_BAR_COLUMNS]].sort_values(["date", "instrument"])
    validate_market_frame(frame)
    manifest = write_bundle(
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
    _check_metadata(manifest, REQUIRED_MARKET_METADATA)
    return manifest


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
