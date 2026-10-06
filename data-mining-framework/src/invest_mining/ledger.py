"""Confirmation-use ledger: which periods of a market have been inspected or used to confirm.

A ledger is an append-only JSON Lines file for one market or data scope (for example the
test-only Yahoo US equities history). Keep one ledger per scope: entries are compared by
date window only, because a re-download of the same market has a new content hash but the
same history. Each line is an object with ``ledger_version`` and one ``kind``:

- ``reservation``: a window kept untouched for a future confirmation. Nothing may inspect
  it (descriptive diagnostics, development data) until a search confirms on it.
- ``inspection``: a window already looked at outside a confirmatory search, such as a
  full-sample diagnostic or a backtest. It can never again provide confirmatory evidence.
- ``experiment``: one search, or one fixed-formula confirmation (``invest-mine confirm``),
  identified by its dataset, inputs, configuration and split. A search's development
  window includes label prices, not just decision dates; a fixed formula's covers only
  the lookback history read before confirmation.

A search is ``confirmatory`` only if its confirmation window overlaps no inspection, no
earlier experiment's development or confirmation window, and is not a repeat of an
earlier experiment. Otherwise it is ``exploratory`` and the reasons are recorded. A search
whose development window touches an unused reservation, or whose confirmation window
starts before a reservation it reaches into, is refused before any data is evaluated.

The file is the record: writers append one line and fsync. It assumes a single writer.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

LEDGER_VERSION = 1
KINDS = ("reservation", "inspection", "experiment")


class LedgerError(ValueError):
    """Invalid ledger content or a request that would burn reserved data."""


@dataclass(frozen=True)
class Window:
    """Inclusive calendar-date window; ``end=None`` is open-ended."""

    start: date
    end: date | None = None

    def __post_init__(self) -> None:
        if self.end is not None and self.end < self.start:
            raise LedgerError(f"window ends ({self.end}) before it starts ({self.start})")

    @staticmethod
    def parse(start: str, end: str | None = None) -> Window:
        try:
            return Window(date.fromisoformat(start), date.fromisoformat(end) if end else None)
        except (TypeError, ValueError) as exc:
            raise LedgerError(f"invalid window {start!r}..{end!r}: {exc}") from exc

    @staticmethod
    def from_json(raw: Any) -> Window:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("start"), str):
            raise LedgerError(f"window must be an object with a start date: {raw!r}")
        return Window.parse(raw["start"], raw.get("end"))

    def to_json(self) -> dict[str, str | None]:
        end = None if self.end is None else self.end.isoformat()
        return {"start": self.start.isoformat(), "end": end}

    def overlaps(self, other: Window) -> bool:
        return (self.end is None or other.start <= self.end) and (
            other.end is None or self.start <= other.end
        )

    def contains(self, other: Window) -> bool:
        return self.start <= other.start and (
            self.end is None or (other.end is not None and other.end <= self.end)
        )

    def __str__(self) -> str:
        return f"{self.start}..{self.end or 'open'}"


def experiment_id(identity: Mapping[str, Any]) -> str:
    """Stable id of an experiment: the hash of its canonical JSON identity."""
    key = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
    return "e_" + hashlib.sha256(key.encode()).hexdigest()[:12]


def load(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Read and validate every entry; a missing file is an empty ledger."""
    p = Path(path)
    if not p.exists():
        return []
    entries = []
    for number, line in enumerate(p.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"{p}:{number}: not JSON: {exc}") from exc
        try:
            _validate_entry(entry)
        except LedgerError as exc:
            raise LedgerError(f"{p}:{number}: {exc}") from exc
        entries.append(entry)
    return entries


def _validate_entry(entry: Any) -> None:
    """Enforce the same entry contract on both sides of persistence."""
    if not isinstance(entry, dict):
        raise LedgerError("entry must be a JSON object")
    if entry.get("ledger_version") != LEDGER_VERSION:
        raise LedgerError(f"unsupported ledger_version {entry.get('ledger_version')!r}")
    kind = entry.get("kind")
    if kind not in KINDS:
        raise LedgerError(f"unknown kind {kind!r}")
    for name in _window_fields(kind):
        Window.from_json(entry.get(name))
    if kind == "experiment" and not isinstance(entry.get("experiment_id"), str):
        raise LedgerError("experiment entry without experiment_id")


def _window_fields(kind: str) -> tuple[str, ...]:
    return ("development", "confirmation") if kind == "experiment" else ("window",)


def append(
    path: str | os.PathLike[str], kind: str, fields: Mapping[str, Any], now: datetime | None = None
) -> dict[str, Any]:
    """Append one validated entry and flush it to disk.

    Invalid entries and attempts to override managed metadata raise :class:`LedgerError`
    before creating directories or changing the ledger.
    """
    if kind not in KINDS:
        raise LedgerError(f"unknown kind {kind!r}")
    managed = {"ledger_version", "kind", "recorded_at"}.intersection(fields)
    if managed:
        raise LedgerError(f"fields cannot override managed metadata: {', '.join(sorted(managed))}")
    entry = {
        "ledger_version": LEDGER_VERSION,
        "kind": kind,
        "recorded_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        **fields,
    }
    _validate_entry(entry)
    encoded = json.dumps(entry, sort_keys=True, default=str) + "\n"
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(encoded)
        fh.flush()
        os.fsync(fh.fileno())
    return entry


def _experiments(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in entries if e["kind"] == "experiment"]


def unused_reservations(entries: list[dict[str, Any]]) -> list[Window]:
    """Reserved windows that no experiment has confirmed on yet."""
    confirmed = [Window.from_json(e["confirmation"]) for e in _experiments(entries)]
    reserved = [Window.from_json(e["window"]) for e in entries if e["kind"] == "reservation"]
    return [r for r in reserved if not any(r.overlaps(c) for c in confirmed)]


def check_inspection(entries: list[dict[str, Any]], window: Window) -> None:
    """Refuse to inspect data inside a reserved window that is still untouched."""
    for reserved in unused_reservations(entries):
        if window.overlaps(reserved):
            raise LedgerError(
                f"{window} overlaps the reserved confirmation window {reserved}; "
                "it may only be used as the confirmation period of a search"
            )


def is_inspected(entries: list[dict[str, Any]], window: Window) -> bool:
    """True when one inspection entry already covers the whole window."""
    return any(
        e["kind"] == "inspection" and Window.from_json(e["window"]).contains(window)
        for e in entries
    )


def assess_confirmation(
    entries: list[dict[str, Any]], development: Window, confirmation: Window, exp_id: str
) -> tuple[str, list[str]]:
    """Classify a planned search as ``confirmatory`` or ``exploratory``, with reasons.

    Raises :class:`LedgerError` (before any data is evaluated) when the development window
    touches an unused reservation, or the confirmation window starts before one it reaches.
    """
    for reserved in unused_reservations(entries):
        if development.overlaps(reserved):
            raise LedgerError(
                f"development window {development} overlaps the reserved confirmation "
                f"window {reserved}; end the development data before {reserved.start}"
            )
        if confirmation.overlaps(reserved) and confirmation.start < reserved.start:
            raise LedgerError(
                f"confirmation window {confirmation} starts before the reserved window "
                f"{reserved}; start confirmation on or after {reserved.start} "
                "(--confirm-start) so reserved data is not mixed with inspected data"
            )
    reasons = []
    for entry in entries:
        if entry["kind"] == "inspection":
            window = Window.from_json(entry["window"])
            if confirmation.overlaps(window):
                reasons.append(f"confirmation overlaps inspected window {window}")
        elif entry["kind"] == "experiment":
            other = entry["experiment_id"]
            if other == exp_id:
                reasons.append(f"repeat of experiment {other}")
                continue
            for name in ("development", "confirmation"):
                window = Window.from_json(entry[name])
                if confirmation.overlaps(window):
                    reasons.append(f"confirmation overlaps the {name} window of {other}")
    return ("exploratory" if reasons else "confirmatory"), reasons
