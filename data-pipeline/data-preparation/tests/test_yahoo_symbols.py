"""Symbols that differ only in case name one Yahoo instrument (BH-2026-10-19-5).

Yahoo answers ``SPY`` and ``spy`` with the same bars. Each spelling became its own
instrument with identical bars in the published market bundle, and the two raw files are
one file on a case-insensitive file system.
"""

import json

import pandas as pd
import pytest

from invest_data.testing import fake_chart
from invest_data.yahoo import SourceError, download_snapshot, load_snapshot

BARS = pd.DataFrame(
    {
        "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
        "open": [10.0, 10.5],
        "high": [11.0, 11.0],
        "low": [9.5, 10.0],
        "close": [10.5, 10.8],
        "volume": [1000.0, 1200.0],
    }
)


def _fetcher(calls):
    body = json.dumps(fake_chart(BARS, "SPY")).encode()

    def fetch(url, timeout):
        calls.append(url)
        return body

    return fetch


@pytest.mark.parametrize("symbols", [["SPY", "spy"], ["SPY", "QQQ", "Spy"]])
def test_download_refuses_symbols_that_differ_only_in_case(tmp_path, symbols):
    calls: list[str] = []
    with pytest.raises(ValueError, match="differ only in case"):
        download_snapshot(
            symbols, "2024-01-02", "2024-01-03", tmp_path / "s", fetcher=_fetcher(calls)
        )
    assert calls == []  # refused before any request
    assert not (tmp_path / "s").exists()


def test_replay_refuses_a_snapshot_with_symbols_that_differ_only_in_case(tmp_path):
    """A snapshot saved before the download check holds both spellings."""
    download_snapshot(
        ["SPY", "QQQ"], "2024-01-02", "2024-01-03", tmp_path / "s", fetcher=_fetcher([])
    )
    manifest_path = tmp_path / "s" / "snapshot.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["spy"] = manifest["files"].pop("QQQ")
    manifest["request"]["symbols"] = ["SPY", "spy"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SourceError, match="differ only in case"):
        load_snapshot(tmp_path / "s")
    raw, _ = load_snapshot(tmp_path / "s", ["SPY"])  # one spelling still replays
    assert raw["instrument"].unique().tolist() == ["SPY"]
