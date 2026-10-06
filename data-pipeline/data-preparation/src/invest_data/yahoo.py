"""Yahoo Finance daily bars: a **test-only** source with raw snapshots and offline replay.

Yahoo is useful for exercising the workflow on real prices, not for research claims: its
adjusted history is rewritten after every dividend or split, delisted tickers are not
available, and there is no point-in-time index membership. Dataset identity therefore
comes from a saved raw snapshot, not from the vendor:

1. :func:`download_snapshot` fetches each symbol's chart JSON once, with explicit timeouts
   and bounded retries, and saves the untouched responses plus a ``snapshot.json``
   manifest (request, retrieval time, per-file SHA-256, failures).
2. :func:`load_snapshot` replays a snapshot offline: it verifies every file hash, parses
   the responses and returns raw bars and provenance. Publishing the same snapshot always
   gives the same dataset ``content_sha256``.

Snapshots belong under the ignored ``artifacts/`` directory; never commit vendor data.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SNAPSHOT_VERSION = 1
SOURCE = "yahoo_finance_chart_v8"
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
TRANSIENT_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})
USER_AGENT = "Mozilla/5.0 (compatible; invest-data research test adapter)"

Fetcher = Callable[[str, float], bytes]


class SourceError(RuntimeError):
    """The source returned an unusable response, or a snapshot failed verification."""


@dataclass(frozen=True)
class RetryPolicy:
    """At most ``attempts`` tries per symbol, with capped exponential backoff."""

    attempts: int = 4
    backoff_seconds: float = 2.0
    max_backoff_seconds: float = 16.0

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be at least 1")
        if self.backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise ValueError("backoff must be non-negative")

    def delay(self, attempt: int) -> float:
        return float(min(self.backoff_seconds * 2 ** (attempt - 1), self.max_backoff_seconds))


def http_get(url: str, timeout: float) -> bytes:
    """GET ``url`` with a timeout; raises ``urllib.error`` exceptions on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body: bytes = resp.read()
    return body


def chart_url(symbol: str, start: str, end: str) -> str:
    """Daily chart URL covering sessions ``start`` to ``end`` inclusive (YYYY-MM-DD)."""
    first = pd.Timestamp(start, tz="UTC")
    stop = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    if stop <= first:
        raise ValueError(f"end {end} precedes start {start}")
    query = urllib.parse.urlencode(
        {
            "period1": int(first.timestamp()),
            "period2": int(stop.timestamp()),
            "interval": "1d",
            "events": "div,split",
            "includeAdjustedClose": "true",
        }
    )
    return CHART_URL.format(symbol=urllib.parse.quote(symbol, safe="")) + "?" + query


def _chart_result(payload: dict[str, Any], symbol: str) -> dict[str, Any]:
    chart = payload.get("chart") if isinstance(payload, dict) else None
    if not isinstance(chart, dict):
        raise SourceError(f"{symbol}: response has no 'chart' object")
    if chart.get("error"):
        raise SourceError(f"{symbol}: source error {chart['error']}")
    results = chart.get("result")
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        raise SourceError(f"{symbol}: expected exactly one chart result")
    result: dict[str, Any] = results[0]
    return result


def fetch_symbol(
    symbol: str,
    start: str,
    end: str,
    *,
    fetcher: Fetcher | None = None,
    timeout: float = 20.0,
    retry: RetryPolicy | None = None,
    sleep: Callable[[float], None] | None = None,
) -> bytes:
    """Return the raw chart response body for one symbol.

    Network errors, timeouts and transient HTTP statuses (429, 5xx) are retried up to
    ``retry.attempts`` times; other HTTP errors and malformed or error responses are not.
    Raises :class:`SourceError` when no usable response was obtained.
    """
    policy = retry or RetryPolicy()
    get = fetcher or http_get
    wait = sleep or time.sleep
    url = chart_url(symbol, start, end)
    last = "no attempt made"
    for attempt in range(1, policy.attempts + 1):
        try:
            body = get(url, timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in TRANSIENT_HTTP:
                raise SourceError(f"{symbol}: HTTP {exc.code}") from exc
            last = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = f"{type(exc).__name__}: {exc}"
        else:
            try:
                payload = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SourceError(f"{symbol}: response is not JSON") from exc
            _chart_result(payload, symbol)
            return body
        if attempt < policy.attempts:
            wait(policy.delay(attempt))
    raise SourceError(f"{symbol}: no response after {policy.attempts} attempts ({last})")


def _file_name(symbol: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in symbol)
    return f"raw/{safe}.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def download_snapshot(
    symbols: Iterable[str],
    start: str,
    end: str,
    out: str | os.PathLike[str],
    *,
    fetcher: Fetcher | None = None,
    timeout: float = 20.0,
    retry: RetryPolicy | None = None,
    sleep: Callable[[float], None] | None = None,
    pause_seconds: float = 0.0,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Fetch every symbol and save an immutable raw snapshot under ``out``.

    Symbols that fail after retries are recorded under ``failures`` rather than aborting
    the whole download. An existing snapshot is never overwritten.
    """
    root = Path(out)
    if (root / "snapshot.json").exists():
        raise FileExistsError(f"{root} already holds a snapshot; snapshots are immutable")
    names = list(dict.fromkeys(s.strip() for s in symbols if s.strip()))
    if not names:
        raise ValueError("no symbols to download")
    chart_url(names[0], start, end)  # validates the date range before any request
    files: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    for i, symbol in enumerate(names):
        if i and pause_seconds:
            (sleep or time.sleep)(pause_seconds)
        try:
            body = fetch_symbol(
                symbol, start, end, fetcher=fetcher, timeout=timeout, retry=retry, sleep=sleep
            )
        except SourceError as exc:
            failures[symbol] = str(exc)
            continue
        rel = _file_name(symbol)
        _atomic_write(root / rel, body)
        files[symbol] = {"path": rel, "sha256": _sha256(body), "bytes": len(body)}
    manifest = {
        "snapshot_version": SNAPSHOT_VERSION,
        "source": SOURCE,
        "url_template": CHART_URL,
        "request": {"symbols": names, "start": start, "end": end, "interval": "1d"},
        "retrieved_at": now().isoformat(timespec="seconds"),
        "files": files,
        "failures": failures,
        "test_only": True,
    }
    _atomic_write(root / "snapshot.json", (json.dumps(manifest, indent=2) + "\n").encode())
    return manifest


def parse_chart(payload: bytes | dict[str, Any], symbol: str) -> pd.DataFrame:
    """Raw rows ``date, instrument, open, high, low, close, adjclose, volume``.

    ``date`` is the session date in the exchange's time zone. Yahoo's ``open/high/low/
    close/volume`` are split-adjusted; ``adjclose`` is also dividend-adjusted. Missing
    values (``null``) stay NaN so cleaning can reject and report them.
    """
    data = json.loads(payload) if isinstance(payload, bytes | bytearray) else payload
    result = _chart_result(data, symbol)
    tz = result.get("meta", {}).get("exchangeTimezoneName")
    if not tz:
        raise SourceError(f"{symbol}: meta.exchangeTimezoneName is missing")
    stamps = result.get("timestamp") or []
    indicators = result.get("indicators", {})
    quote = (indicators.get("quote") or [{}])[0]
    adj = (indicators.get("adjclose") or [{}])[0].get("adjclose")
    n = len(stamps)

    def column(values: Any, name: str) -> np.ndarray:
        if values is None:
            values = [None] * n
        if len(values) != n:
            raise SourceError(f"{symbol}: {name} has {len(values)} values for {n} timestamps")
        return np.array([np.nan if v is None else v for v in values], dtype="float64")

    dates = pd.to_datetime(pd.Series(stamps, dtype="int64"), unit="s", utc=True)
    out = pd.DataFrame(
        {
            "date": dates.dt.tz_convert(tz).dt.tz_localize(None).dt.normalize(),
            "instrument": symbol,
        }
    )
    for name in ("open", "high", "low", "close", "volume"):
        out[name] = column(quote.get(name), name)
    out["adjclose"] = column(adj, "adjclose")
    return out


def total_return_adjust(raw: pd.DataFrame) -> pd.DataFrame:
    """Scale OHLC by ``adjclose / close``; scale volume inversely to keep dollar volume.

    The result has the market-bars columns and ``price_adjustment = total_return_adjusted``.
    Rows lacking a positive close or adjusted close get NaN prices, which cleaning rejects.
    """
    close = raw["close"].where(raw["close"] > 0)
    factor = raw["adjclose"].where(raw["adjclose"] > 0) / close
    out = raw[["date", "instrument"]].copy()
    for name in ("open", "high", "low", "close"):
        out[name] = raw[name] * factor
    out["volume"] = raw["volume"] / factor
    return out


def read_snapshot_manifest(path: str | os.PathLike[str]) -> dict[str, Any]:
    root = Path(path)
    try:
        manifest: dict[str, Any] = json.loads((root / "snapshot.json").read_text())
    except FileNotFoundError as exc:
        raise SourceError(f"{root}: no snapshot.json") from exc
    if manifest.get("snapshot_version") != SNAPSHOT_VERSION or manifest.get("source") != SOURCE:
        raise SourceError(
            f"{root}: unsupported snapshot {manifest.get('source')!r} "
            f"version {manifest.get('snapshot_version')!r}"
        )
    return manifest


def load_snapshot(
    path: str | os.PathLike[str], symbols: Iterable[str] | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Replay a saved snapshot offline: verify hashes, parse and adjust.

    Returns ``(raw bars, provenance)``. ``raw bars`` has the market-bars columns and is not
    yet cleaned; pass it to :func:`invest_data.cleaning.clean_bars`. ``symbols`` selects a
    subset (every name must be present in the snapshot). Output order is deterministic.
    """
    root = Path(path)
    manifest = read_snapshot_manifest(root)
    files: dict[str, dict[str, Any]] = manifest["files"]
    wanted = sorted(files) if symbols is None else list(dict.fromkeys(symbols))
    missing = [s for s in wanted if s not in files]
    if missing:
        raise SourceError(f"{root}: symbols not in snapshot: {missing}")
    if not wanted:
        raise SourceError(f"{root}: snapshot holds no symbols")
    frames = []
    currencies: dict[str, str | None] = {}
    for symbol in sorted(wanted):
        entry = files[symbol]
        body = (root / entry["path"]).read_bytes()
        if _sha256(body) != entry["sha256"]:
            raise SourceError(f"{root}: {entry['path']} does not match its recorded SHA-256")
        payload = json.loads(body)
        currencies[symbol] = _chart_result(payload, symbol).get("meta", {}).get("currency")
        frames.append(total_return_adjust(parse_chart(payload, symbol)))
    raw = pd.concat(frames, ignore_index=True)
    provenance = {
        "sources": [SOURCE],
        "test_only": True,
        "snapshot": {
            "request": manifest["request"],
            "retrieved_at": manifest["retrieved_at"],
            "files": {s: files[s]["sha256"] for s in sorted(wanted)},
            "download_failures": manifest.get("failures", {}),
        },
        "adjustment": "OHLC x adjclose/close; volume / (adjclose/close)",
        "currencies": currencies,
    }
    return raw, provenance


def yahoo_metadata(currency: str, universe: str) -> dict[str, Any]:
    """Market-bars metadata for a Yahoo publication; ``universe`` describes the selection."""
    return {
        "frequency": "1d",
        "currency": currency,
        "price_adjustment": "total_return_adjusted",
        "calendar": "XNYS",
        "timezone": "America/New_York",
        "universe": universe,
        "source": SOURCE,
        "note": (
            "TEST-ONLY Yahoo Finance data: adjusted history is revised by the vendor, "
            "delisted names are absent and membership is not point-in-time. Identity is the "
            "saved raw snapshot recorded in provenance."
        ),
    }
