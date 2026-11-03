"""Confirmation-use ledger: which periods of a market have been inspected or used to confirm.

A ledger is an append-only JSON Lines file for one market or data scope (for example the
test-only Yahoo US equities history). Keep one ledger per scope: entries are compared by
date window only, because a re-download of the same market has a new content hash but the
same history. Each line is an object with ``ledger_version`` and one ``kind``:

- ``reservation``: a window kept untouched for a future confirmation. Nothing may inspect
  it (descriptive diagnostics, development data) until a search confirms on it. A
  confirmation uses it up, so it must start on the reservation's first session.
- ``inspection``: a window already looked at outside a confirmatory search, such as a
  full-sample diagnostic or a backtest. It can never again provide confirmatory evidence.
- ``experiment``: one search, or one fixed-formula confirmation (``invest-mine confirm``),
  identified by its dataset, inputs, configuration and split. A search's development
  window includes label prices, not just decision dates; a fixed formula's covers only
  the lookback history read before confirmation. For a zero-lookback fixed formula,
  ``development`` is explicitly null and ``params.lookback_sessions`` is zero.

A search is ``confirmatory`` only if its confirmation window overlaps no inspection, no
earlier experiment's development or confirmation window, and is not a repeat of an
earlier experiment. Otherwise it is ``exploratory`` and the reasons are recorded. An
experiment whose ``family`` is empty selected nothing, so no statistic was computed on its
confirmation window: that window neither uses up a reservation nor counts as used later
(:func:`used_windows`). A search whose development window touches an unused reservation,
or whose confirmation window starts before a reservation it reaches into, is refused
before any data is evaluated; so is one that starts after the first session of a
reservation it overlaps, when the data's sessions are given (the CLI always gives them).

The file is the record: writers append one line and fsync. It assumes a single writer.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
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
    entry_windows(entry)
    if kind == "experiment" and not isinstance(entry.get("experiment_id"), str):
        raise LedgerError("experiment entry without experiment_id")


def _window_fields(kind: str) -> tuple[str, ...]:
    return ("development", "confirmation") if kind == "experiment" else ("window",)


def entry_windows(entry: Mapping[str, Any]) -> dict[str, Window]:
    """Decode observation windows, allowing null history only for zero-lookback formulas.

    The entry's kind must already be validated. An absent development field is invalid;
    an explicit null denotes no observed history and therefore contributes no window.
    """
    windows = {}
    for name in _window_fields(entry["kind"]):
        if name == "development" and name in entry and entry[name] is None:
            params = entry.get("params")
            if (
                not isinstance(params, Mapping)
                or params.get("method") != "fixed_formula"
                or type(params.get("lookback_sessions")) is not int
                or params["lookback_sessions"] != 0
            ):
                raise LedgerError("null development requires a zero-lookback fixed formula")
            continue
        windows[name] = Window.from_json(entry.get(name))
    return windows


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


def used_windows(entry: Mapping[str, Any]) -> dict[str, Window]:
    """Windows an inspection or experiment has observed, by field name.

    Like :func:`entry_windows`, except that an experiment whose ``family`` is an empty list
    tested nothing on its confirmation window (every candidate was rejected on development
    data), so only its development window counts. An experiment without a ``family``
    field counts as tested. A reservation observes nothing and yields no window.
    """
    if entry["kind"] == "reservation":
        return {}
    windows = entry_windows(entry)
    if entry["kind"] == "experiment" and entry.get("family") == []:
        windows.pop("confirmation", None)
    return windows


def unused_reservations(entries: list[dict[str, Any]]) -> list[Window]:
    """Reserved windows that no experiment has tested anything on yet."""
    confirmed = [
        window
        for e in entries
        if e["kind"] == "experiment"
        for name, window in used_windows(e).items()
        if name == "confirmation"
    ]
    reserved = [Window.from_json(e["window"]) for e in entries if e["kind"] == "reservation"]
    return [r for r in reserved if not any(r.overlaps(c) for c in confirmed)]


def _reserved_regions(entries: list[dict[str, Any]]) -> list[Window]:
    """Unused reservations, overlapping ones merged into one window.

    Overlapping reservations protect one stretch of data, so a confirmation has to start
    on the first session of their union; checked one by one, no start would pass both.
    """
    regions: list[Window] = []
    for reserved in sorted(unused_reservations(entries), key=lambda w: w.start):
        if regions and regions[-1].overlaps(reserved):
            last = regions[-1]
            end = None if last.end is None or reserved.end is None else max(last.end, reserved.end)
            regions[-1] = Window(last.start, end)
        else:
            regions.append(reserved)
    return regions


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
    entries: list[dict[str, Any]],
    development: Window | None,
    confirmation: Window,
    exp_id: str,
    *,
    sessions: Iterable[date] | None = None,
) -> tuple[str, list[str]]:
    """Classify a planned search as ``confirmatory`` or ``exploratory``, with reasons.

    Raises :class:`LedgerError` (before any data is evaluated) when the development window
    touches an unused reservation, or the confirmation window starts before one it reaches.
    A zero-lookback fixed formula has no history window and passes ``development=None``.

    ``sessions`` are the data's session dates. With them, a confirmation that overlaps an
    unused reservation is also refused when a session lies between the reservation's start
    and the confirmation's first date: confirming would use up reserved sessions that
    nothing tested. Without them a reservation that starts on a non-session day cannot be
    told apart from skipped sessions, so this check is not made. The data's own sessions
    are the calendar: reserved sessions before the data's first session are not seen, so
    a confirmation needs data that covers the reservation's start. Overlapping unused
    reservations are checked as one window, their union.
    """
    days = None if sessions is None else sorted(sessions)
    for reserved in _reserved_regions(entries):
        if development is not None and development.overlaps(reserved):
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
        skipped = (
            []
            if days is None or not confirmation.overlaps(reserved)
            else [d for d in days if reserved.start <= d < confirmation.start]
        )
        if skipped:
            span = f"{skipped[0]}" if len(skipped) == 1 else f"{skipped[0]}..{skipped[-1]}"
            raise LedgerError(
                f"confirmation window {confirmation} starts after the reserved window "
                f"{reserved} begins, so its reserved session(s) {span} would be used up "
                "untested; start confirmation on the reservation's first session "
                f"(--confirm-start {reserved.start})"
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
            for name, window in used_windows(entry).items():
                if confirmation.overlaps(window):
                    reasons.append(f"confirmation overlaps the {name} window of {other}")
    return ("exploratory" if reasons else "confirmatory"), reasons
