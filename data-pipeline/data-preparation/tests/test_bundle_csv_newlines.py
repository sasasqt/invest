"""Carriage returns in CSV bundles (BH-2026-10-23-1, REVIEW-26).

The CSV reader read ``data.csv`` with universal newlines, so a carriage return inside a
quoted string field became a newline before the CSV parser saw it. DATA_CONTRACT.md asks
for standard CSV quoting, which keeps a quoted field's content exactly (RFC 4180 2.6).
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from invest_data.bundle import Column, read_bundle, write_bundle

COLUMNS = (Column("k", "int64", nullable=False), Column("s", "string", nullable=False))
TEXTS = ["a\rb", "a\r\nb", "\r", "a\nb", "end\r"]


def _write(path: Path, texts: list[str], fmt: str = "csv") -> None:
    frame = pd.DataFrame({"k": list(range(len(texts))), "s": pd.Series(texts, dtype=object)})
    write_bundle(frame, path, dataset_id="t", fmt=fmt, columns=COLUMNS, primary_key=("k",))


def _strings(path: Path) -> list[str]:
    return list(read_bundle(path)[1]["s"])


@pytest.mark.parametrize("fmt", ["csv", "sqlite", "parquet"])
def test_strings_with_carriage_returns_round_trip(tmp_path: Path, fmt: str) -> None:
    """The writer refused these strings with a content hash mismatch (CSV only)."""
    _write(tmp_path / "b", TEXTS, fmt)
    assert _strings(tmp_path / "b") == TEXTS


def test_quoted_carriage_returns_in_a_bundle_without_hash_read_exactly(tmp_path: Path) -> None:
    """A bundle without content_sha256 read 'a\\rb' silently as 'a\\nb'."""
    path = tmp_path / "b"
    _write(path, ["x", "y"])
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    del manifest["content_sha256"]
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (path / "data.csv").write_bytes(b'k,s\n0,"a\rb"\n1,"c\r\nd"\n')
    assert _strings(path) == ["a\rb", "c\r\nd"]


@pytest.mark.parametrize("terminator", [b"\r\n", b"\r"])
def test_row_terminators_outside_quotes_still_end_rows(tmp_path: Path, terminator: bytes) -> None:
    """CRLF files from Windows producers, and lone CR, keep reading as rows with a valid hash."""
    path = tmp_path / "b"
    _write(path, ["x", "y"])
    data = path / "data.csv"
    data.write_bytes(data.read_bytes().replace(b"\n", terminator))
    assert _strings(path) == ["x", "y"]
