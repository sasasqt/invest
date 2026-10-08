import json
from datetime import UTC, date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from invest_data.bundle import BundleError, Column, read_bundle, read_manifest, write_bundle

COLS = (
    Column("id", "string", nullable=False),
    Column("text", "string"),
    Column("n", "int64"),
    Column("x", "float64"),
    Column("flag", "boolean"),
    Column("d", "date"),
    Column("ts", "timestamp"),
    Column("amount", "decimal", precision=10, scale=2),
)


def tricky_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": ["a", "b", "c", "d", "e"],
            "text": ["\\N", "", None, "\\\\N", 'ünïcødé, "quoted"\nline'],
            "n": pd.array([1, None, -3, 2**40, 0], dtype="Int64"),
            "x": [0.1, np.nan, -1e-300, 1.5, 2.0],
            "flag": pd.array([True, False, None, True, False], dtype="boolean"),
            "d": pd.to_datetime(["2024-01-02", None, "2024-03-04", "2024-01-02", "2024-12-31"]),
            "ts": pd.to_datetime(
                ["2024-01-02T15:30:00Z", None, "2024-03-04T00:00:00Z", None, None], utc=True
            ),
            "amount": [Decimal("1.10"), None, Decimal("-0.05"), Decimal("12345678.90"), None],
        }
    )


@pytest.mark.parametrize("fmt", ["csv", "sqlite", "parquet"])
def test_round_trip_preserves_values(tmp_path, fmt):
    frame = tricky_frame()
    write_bundle(frame, tmp_path / "b", dataset_id="t", fmt=fmt, columns=COLS, primary_key=["id"])
    manifest, back = read_bundle(tmp_path / "b")
    assert manifest.row_count == 5
    assert back["text"].tolist() == ["\\N", "", None, "\\\\N", frame["text"][4]]
    assert back["n"].tolist()[0] == 1 and pd.isna(back["n"][1]) and back["n"][3] == 2**40
    assert back["x"][0] == 0.1 and np.isnan(back["x"][1]) and back["x"][2] == -1e-300
    assert back["flag"].tolist()[:2] == [True, False] and pd.isna(back["flag"][2])
    assert back["amount"][0] == Decimal("1.10") and back["amount"][1] is None
    assert back["d"][0] == pd.Timestamp("2024-01-02") and pd.isna(back["d"][1])
    assert back["ts"][0] == pd.Timestamp("2024-01-02T15:30:00Z")


def test_all_formats_have_same_content_hash_and_frame(tmp_path):
    frame = tricky_frame()
    hashes, frames = set(), []
    for fmt in ("csv", "sqlite", "parquet"):
        m = write_bundle(frame, tmp_path / fmt, dataset_id="t", fmt=fmt, columns=COLS)
        hashes.add(m.content_sha256)
        frames.append(read_bundle(tmp_path / fmt)[1])
    assert len(hashes) == 1
    pd.testing.assert_frame_equal(frames[0], frames[1])
    pd.testing.assert_frame_equal(frames[0], frames[2])


def test_parquet_reader_rejects_type_mismatch(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    _published(tmp_path, fmt="parquet")
    pq.write_table(
        pa.table({"id": ["a", "b"], "d": ["2024-01-01", "2024-01-02"]}),
        tmp_path / "b" / "data.parquet",
    )
    with pytest.raises(BundleError, match="Parquet type"):
        read_bundle(tmp_path / "b")


def test_csv_null_and_escape_encoding(tmp_path):
    frame = pd.DataFrame({"s": ["\\N", None, "", "\\x"]})
    write_bundle(frame, tmp_path / "b", dataset_id="t", columns=[Column("s", "string")])
    lines = (tmp_path / "b" / "data.csv").read_text().splitlines()
    assert lines == ["s", "\\\\N", "\\N", '""', "\\\\x"]


def test_empty_dataset(tmp_path):
    frame = pd.DataFrame({"id": pd.Series([], dtype=object)})
    write_bundle(frame, tmp_path / "b", dataset_id="t", columns=[Column("id", "string", False)])
    _, back = read_bundle(tmp_path / "b")
    assert len(back) == 0


def test_rejects_existing_target_and_leaves_no_partial_output(tmp_path):
    frame = pd.DataFrame({"id": ["a", "a"]})
    with pytest.raises(BundleError, match="duplicate primary key"):
        write_bundle(frame, tmp_path / "b", dataset_id="t", primary_key=["id"])
    assert list(tmp_path.iterdir()) == []
    write_bundle(frame.iloc[:1], tmp_path / "b", dataset_id="t")
    with pytest.raises(BundleError, match="already exists"):
        write_bundle(frame.iloc[:1], tmp_path / "b", dataset_id="t")


@pytest.mark.parametrize("bad", [float("inf"), -float("inf")])
def test_rejects_infinity(tmp_path, bad):
    with pytest.raises(BundleError, match="infinity"):
        write_bundle(pd.DataFrame({"x": [bad]}), tmp_path / "b", dataset_id="t")


def test_rejects_null_in_non_nullable(tmp_path):
    with pytest.raises(BundleError, match="not nullable"):
        write_bundle(
            pd.DataFrame({"x": [1.0, None]}),
            tmp_path / "b",
            dataset_id="t",
            columns=[Column("x", "float64", nullable=False)],
        )


def test_rejects_naive_timestamp(tmp_path):
    frame = pd.DataFrame({"ts": [datetime(2024, 1, 1)]})
    with pytest.raises(BundleError, match="timezone-aware"):
        write_bundle(frame, tmp_path / "b", dataset_id="t", columns=[Column("ts", "timestamp")])
    aware = pd.DataFrame({"ts": [datetime(2024, 1, 1, tzinfo=UTC)]})
    write_bundle(aware, tmp_path / "ok", dataset_id="t", columns=[Column("ts", "timestamp")])


def _published(tmp_path, fmt="csv"):
    frame = pd.DataFrame({"id": ["a", "b"], "d": [date(2024, 1, 1), date(2024, 1, 2)]})
    cols = [Column("id", "string", False), Column("d", "date", False)]
    write_bundle(frame, tmp_path / "b", dataset_id="t", fmt=fmt, columns=cols)
    return tmp_path / "b"


def _edit_manifest(path, **changes):
    raw = json.loads((path / "manifest.json").read_text())
    raw.update(changes)
    (path / "manifest.json").write_text(json.dumps(raw))


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"contract_version": 2}, "unsupported contract_version"),
        ({"row_count": 3}, "row_count"),
        ({"storage": {"format": "csv", "path": "../x.csv"}}, "inside the bundle"),
        ({"storage": {"format": "orc", "path": "data.csv"}}, "unsupported storage"),
        ({"columns": [{"name": "id", "type": "uuid"}]}, "unsupported logical type"),
    ],
)
def test_reader_rejects_invalid_manifests(tmp_path, changes, message):
    path = _published(tmp_path)
    _edit_manifest(path, **changes)
    with pytest.raises(BundleError, match=message):
        read_bundle(path)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"storage": "x"}, "'storage' must be a JSON object"),
        ({"columns": 5}, "'columns' must be a JSON array"),
        ({"columns": ["a"]}, "column definition must be a JSON object"),
        ({"columns": [{"name": "id", "type": "decimal", "precision": "9", "scale": 2}]}, "integer"),
        ({"metadata": None}, "'metadata' must be a JSON object"),
        ({"provenance": []}, "'provenance' must be a JSON object"),
        ({"primary_key": 5}, "'primary_key' must be a JSON array"),
        ({"primary_key": [1]}, "must list column names"),
        ({"row_count": None}, "non-negative integer"),
        ({"row_count": "2"}, "non-negative integer"),
        ({"row_count": True}, "non-negative integer"),
        ({"storage": {"format": ["csv"], "path": "data.csv"}}, "'storage' values must be strings"),
        ({"storage": {"format": {}, "path": "data.csv"}}, "'storage' values must be strings"),
        ({"dataset_kind": ["signals"]}, "'dataset_kind' must be a string"),
        ({"dataset_id": 5}, "'dataset_id' must be a string"),
        ({"content_sha256": 5}, "'content_sha256' must be a string"),
    ],
)
def test_reader_rejects_malformed_manifest_structure(tmp_path, changes, message):
    """A malformed manifest is a BundleError, never a TypeError or AttributeError."""
    path = _published(tmp_path)
    _edit_manifest(path, **changes)
    with pytest.raises(BundleError, match=message):
        read_bundle(path)


@pytest.mark.parametrize("content", [b"[]", b"5", b"\xff\xfe"])
def test_reader_rejects_a_manifest_that_is_not_a_json_object(tmp_path, content):
    path = _published(tmp_path)
    (path / "manifest.json").write_bytes(content)
    with pytest.raises(BundleError, match="manifest"):
        read_bundle(path)


def test_reader_reads_a_null_created_at_as_empty(tmp_path):
    path = _published(tmp_path)
    _edit_manifest(path, created_at=None)
    assert read_bundle(path)[0].created_at == ""


def test_reader_detects_tampered_data(tmp_path):
    path = _published(tmp_path)
    csv = path / "data.csv"
    csv.write_text(csv.read_text().replace("2024-01-02", "2024-01-03"))
    with pytest.raises(BundleError, match="content hash"):
        read_bundle(path)


def test_reader_rejects_bad_values(tmp_path):
    path = _published(tmp_path)
    csv = path / "data.csv"
    csv.write_text(csv.read_text().replace("2024-01-02", "2024/01/02"))
    with pytest.raises(BundleError, match="date"):
        read_bundle(path)


def test_sqlite_reader_is_read_only_and_checks_columns(tmp_path):
    path = _published(tmp_path, fmt="sqlite")
    before = (path / "data.sqlite").read_bytes()
    read_bundle(path)
    assert (path / "data.sqlite").read_bytes() == before
    _edit_manifest(path, storage={"format": "sqlite", "path": "data.sqlite", "table": "nope"})
    with pytest.raises(BundleError):
        read_bundle(path)


def test_missing_manifest(tmp_path):
    with pytest.raises(BundleError, match="manifest"):
        read_manifest(tmp_path)
