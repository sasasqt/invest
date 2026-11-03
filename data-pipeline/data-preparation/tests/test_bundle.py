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


# ---------------------------------------------------------------------------
# Values a column cannot store exactly are refused, never rounded or truncated
# (REVIEW-16: K4, BH-2026-10-19-1 to -4, BH-2026-10-13-9, BH-2026-10-23-2 to -4, S3-2).

FORMATS = ["csv", "sqlite", "parquet"]


def _one_column(tmp_path, values, column, fmt="csv", name="b"):
    frame = pd.DataFrame({column.name: pd.Series(values, dtype=object)})
    write_bundle(frame, tmp_path / name, dataset_id="t", fmt=fmt, columns=(column,))
    return read_bundle(tmp_path / name)


def _refused(tmp_path, values, column, message, fmt="csv"):
    with pytest.raises(BundleError, match=message):
        _one_column(tmp_path, values, column, fmt=fmt, name="refused")
    assert not (tmp_path / "refused").exists()
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".refused")]


@pytest.mark.parametrize(
    "value",
    [
        pd.Timestamp("2024-03-01 20:00"),  # filed after the close: dropping 20:00 is look-ahead
        "2024-03-01T00:00:01",
        pd.Timestamp("2024-03-01", tz="UTC"),  # a time zone makes it a timestamp
        datetime(2024, 3, 1, tzinfo=UTC),
        "2024-03-01T01:00+09:00",
    ],
)
def test_a_date_column_refuses_a_time_of_day_or_time_zone(tmp_path, value):
    _refused(tmp_path, [value], Column("d", "date"), "is not a date")


def test_a_date_column_accepts_every_date_representation(tmp_path):
    values = [
        date(2024, 3, 1),
        "2024-03-02",
        pd.Timestamp("2024-03-03"),
        np.datetime64("2024-03-04"),
    ]
    _, frame = _one_column(tmp_path, values, Column("d", "date"))
    assert frame["d"].tolist() == list(
        pd.to_datetime(["2024-03-01", "2024-03-02", "2024-03-03", "2024-03-04"])
    )


@pytest.mark.parametrize("value", [20240102, np.int64(20240102), 1.5, Decimal(3), True])
@pytest.mark.parametrize("kind", ["date", "timestamp"])
def test_date_and_timestamp_columns_refuse_numbers(tmp_path, value, kind):
    """pandas reads a number as nanoseconds since 1970, so 20240102 became 1970-01-01."""
    _refused(tmp_path, [value], Column("d", kind), "got the number")


def test_date_and_timestamp_columns_refuse_text_that_is_no_date(tmp_path):
    _refused(tmp_path, ["not a date"], Column("d", "date"), "cannot read")
    _refused(tmp_path, ["NaT"], Column("d", "timestamp"), "cannot read")


def test_a_timestamp_column_refuses_nanoseconds(tmp_path):
    """Timestamps are stored to the microsecond; .123456789 was stored as .123456."""
    value = pd.Timestamp("2024-03-01 12:00:00.123456789", tz="UTC")
    _refused(tmp_path, [value], Column("ts", "timestamp"), "nanoseconds")
    _, frame = _one_column(tmp_path, [value.floor("us")], Column("ts", "timestamp"))
    assert frame["ts"].iloc[0] == value.floor("us")


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize(
    ("value", "precision", "scale", "message"),
    [
        (Decimal("1.005"), 10, 2, "more than 2 decimal places"),  # was rounded to 1.00
        (Decimal("2.675"), 10, 2, "more than 2 decimal places"),  # was rounded to 2.68
        (Decimal("123456.789"), 4, 2, "does not fit"),  # CSV and SQLite stored 123456.79
        (Decimal("100"), 4, 2, "does not fit"),
        (Decimal("99.999"), 4, 2, "more than 2 decimal places"),  # rounds up to 100.00
        ("abc", 4, 2, "cannot read"),
    ],
)
def test_a_decimal_column_refuses_values_beyond_its_precision_or_scale(
    tmp_path, fmt, value, precision, scale, message
):
    column = Column("x", "decimal", precision=precision, scale=scale)
    _refused(tmp_path, [value], column, message, fmt=fmt)


@pytest.mark.parametrize("fmt", FORMATS)
def test_a_decimal_column_stores_values_that_fit_exactly(tmp_path, fmt):
    big = Decimal("1234567890123456789012345678901234.56")  # 36 digits: beyond 28 (BH-2026-10-13-9)
    values = [Decimal("1.5"), Decimal("99.99"), Decimal("-99.99"), Decimal("1.5000"), "0.25", big]
    column = Column("x", "decimal", precision=38, scale=2)
    _, frame = _one_column(tmp_path, values, column, fmt=fmt)
    assert frame["x"].tolist() == [Decimal(str(v)) for v in values]
    assert [str(v) for v in frame["x"]][:4] == ["1.50", "99.99", "-99.99", "1.50"]


@pytest.mark.parametrize(("precision", "scale"), [(0, 0), (39, 2), (5, -1), (2, 3)])
def test_decimal_precision_and_scale_stay_within_decimal128(tmp_path, precision, scale):
    column = Column("x", "decimal", precision=precision, scale=scale)
    _refused(tmp_path, [Decimal("1")], column, "precision must be 1 to 38")
    path = _published(tmp_path)
    raw = json.loads((path / "manifest.json").read_text())
    raw["columns"][1] = {"name": "d", "type": "decimal", "precision": precision, "scale": scale}
    (path / "manifest.json").write_text(json.dumps(raw))
    with pytest.raises(BundleError, match="precision must be 1 to 38"):
        read_bundle(path)


@pytest.mark.parametrize("fmt", FORMATS)
def test_int64_columns_refuse_values_outside_int64(tmp_path, fmt):
    """2**63 escaped as TypeError or OverflowError from pandas, sqlite3 or pyarrow."""
    column = Column("n", "int64")
    _refused(tmp_path, [2**63], column, "outside the int64 range", fmt=fmt)
    _refused(tmp_path, [-(2**63) - 1], column, "outside the int64 range", fmt=fmt)
    _, frame = _one_column(tmp_path, [2**63 - 1, -(2**63)], column, fmt=fmt)
    assert frame["n"].tolist() == [2**63 - 1, -(2**63)]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (Decimal("1.5"), "non-integer"),
        ("abc", "cannot store"),
        (Decimal("Infinity"), "cannot store"),
    ],
)
def test_int64_columns_refuse_values_that_are_not_integers(tmp_path, value, message):
    """int(Decimal("1.5")) is 1: the fraction was dropped."""
    _refused(tmp_path, [value], Column("n", "int64"), message)


def test_float64_columns_refuse_text_that_is_no_number(tmp_path):
    _refused(tmp_path, ["abc"], Column("x", "float64"), "cannot store")
    _refused(tmp_path, [Decimal("1e400")], Column("x", "float64"), "NaN/infinity")


def test_negative_zero_publishes_in_every_format_with_one_content_hash(tmp_path):
    """SQLite reads a stored -0.0 back as 0.0 and Parquet's decimal128 drops the sign of
    -0.00, so either one failed its round trip with a content hash mismatch."""
    frame = pd.DataFrame({"x": [-0.0, 1.0], "amount": [Decimal("-0.00"), Decimal("-0")]})
    cols = (Column("x", "float64"), Column("amount", "decimal", precision=4, scale=2))
    hashes = set()
    for fmt in FORMATS:
        manifest = write_bundle(frame, tmp_path / fmt, dataset_id="z", fmt=fmt, columns=cols)
        hashes.add(manifest.content_sha256)
        _, back = read_bundle(tmp_path / fmt)
        assert np.copysign(1.0, back["x"].iloc[0]) == 1.0
        assert [str(v) for v in back["amount"]] == ["0.00", "0.00"]
    assert len(hashes) == 1


def _legacy_negative_zero_bundle(tmp_path, stored_x, stored_amount, hashed_x, hashed_amount):
    """A CSV bundle as the writer made it before negative zeros were stored as 0."""
    from invest_data.bundle import _content_sha256

    cols = (Column("x", "float64"), Column("amount", "decimal", precision=4, scale=2))
    frame = pd.DataFrame({"x": [0.0], "amount": [Decimal("0.00")]})
    write_bundle(frame, tmp_path / "old", dataset_id="z", columns=cols)
    (tmp_path / "old" / "data.csv").write_text(f"x,amount\n{stored_x},{stored_amount}\n")
    _edit_manifest(
        tmp_path / "old", content_sha256=_content_sha256(cols, [[hashed_x, hashed_amount]])
    )
    return tmp_path / "old"


def test_bundles_written_with_a_negative_zero_stay_readable(tmp_path):
    path = _legacy_negative_zero_bundle(tmp_path, "-0.0", "-0.00", -0.0, "-0.00")
    _, frame = read_bundle(path)
    assert np.copysign(1.0, frame["x"].iloc[0]) == -1.0
    assert str(frame["amount"].iloc[0]) == "-0.00"


def test_parquet_bundles_written_with_a_negative_zero_stay_readable(tmp_path):
    """Exported Yahoo signals hold 747 scores of -0.0 in Parquet; their recorded hash
    keeps the sign."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    from invest_data.bundle import _content_sha256

    cols = (Column("x", "float64"),)
    write_bundle(
        pd.DataFrame({"x": [0.0, 1.0]}),
        tmp_path / "old",
        dataset_id="z",
        fmt="parquet",
        columns=cols,
    )
    table = pa.table({"x": pa.array([-0.0, 1.0], type=pa.float64())})
    pq.write_table(table, tmp_path / "old" / "data.parquet")
    _edit_manifest(tmp_path / "old", content_sha256=_content_sha256(cols, [[-0.0], [1.0]]))
    _, frame = read_bundle(tmp_path / "old")
    assert np.copysign(1.0, frame["x"].iloc[0]) == -1.0
    _edit_manifest(tmp_path / "old", content_sha256=_content_sha256(cols, [[0.5], [1.0]]))
    with pytest.raises(BundleError, match="content hash mismatch"):
        read_bundle(tmp_path / "old")


@pytest.mark.parametrize(
    ("stored_x", "stored_amount", "hashed_x", "hashed_amount"),
    [
        ("0.0", "0.00", -0.0, "-0.00"),  # signs dropped from the data
        ("-0.0", "-0.00", -0.0, "0.00"),  # a sign added to the data
        ("-0.0", "-0.00", 1.0, "-0.00"),  # another value
    ],
)
def test_the_negative_zero_allowance_still_detects_changed_data(
    tmp_path, stored_x, stored_amount, hashed_x, hashed_amount
):
    path = _legacy_negative_zero_bundle(tmp_path, stored_x, stored_amount, hashed_x, hashed_amount)
    with pytest.raises(BundleError, match="content hash mismatch"):
        read_bundle(path)


@pytest.mark.parametrize(
    "changes",
    [
        {"metadata": {"threshold": float("nan")}},
        {"provenance": {"fit": {"loss": float("inf")}}},
        {"metadata": {"when": pd.Timestamp("2024-01-02")}},  # no JSON form
    ],
)
def test_metadata_and_provenance_must_be_json_with_finite_numbers(tmp_path, changes):
    frame = pd.DataFrame({"k": ["a"]})
    with pytest.raises(BundleError, match="JSON values with finite numbers"):
        write_bundle(frame, tmp_path / "b", dataset_id="x", **changes)
    assert not (tmp_path / "b").exists()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_reader_refuses_a_manifest_with_non_finite_numbers(tmp_path, literal):
    """Python's json reads NaN and Infinity, which no strict JSON parser accepts."""
    path = _published(tmp_path)
    text = (path / "manifest.json").read_text()
    (path / "manifest.json").write_text(
        text.replace('"provenance": {}', f'"provenance": {{"x": {literal}}}')
    )
    assert literal in (path / "manifest.json").read_text()
    with pytest.raises(BundleError, match="manifest numbers must be finite"):
        read_manifest(path)


def test_created_at_must_be_timezone_aware_and_is_written_in_utc(tmp_path):
    from datetime import timedelta, timezone

    frame = pd.DataFrame({"k": ["a"]})
    with pytest.raises(BundleError, match="created_at must be timezone-aware"):
        write_bundle(frame, tmp_path / "naive", dataset_id="x", created_at=datetime(2026, 1, 1, 12))
    eastern = datetime(2026, 1, 1, 12, tzinfo=timezone(timedelta(hours=-5)))
    manifest = write_bundle(frame, tmp_path / "b", dataset_id="x", created_at=eastern)
    assert manifest.created_at == "2026-01-01T17:00:00Z"


@pytest.mark.parametrize(
    ("column", "message"),
    [
        ({"name": "d", "type": "date", "nullable": "no"}, "nullable must be true or false"),
        ({"name": "d", "type": "date", "unit": 5}, "unit must be a string"),
        ({"name": "d", "type": "date", "description": ["x"]}, "description must be a string"),
        ({"name": 5, "type": "date"}, "name must be a string"),
        ({"name": "d", "type": None}, "type must be a string"),
    ],
)
def test_column_definitions_are_not_coerced(tmp_path, column, message):
    """`nullable: "no"` was read as true and a numeric unit was accepted (S3-2)."""
    path = _published(tmp_path)
    raw = json.loads((path / "manifest.json").read_text())
    raw["columns"][1] = column
    (path / "manifest.json").write_text(json.dumps(raw))
    with pytest.raises(BundleError, match=message):
        read_bundle(path)


def _without_hash(path):
    raw = json.loads((path / "manifest.json").read_text())
    del raw["content_sha256"]
    (path / "manifest.json").write_text(json.dumps(raw))


def _replace_in_csv(path, old, new):
    data = path / "data.csv"
    text = data.read_text(encoding="utf-8")
    assert old in text
    data.write_text(text.replace(old, new, 1), encoding="utf-8", newline="")


@pytest.mark.parametrize("token", ["NaN", "sNaN", "Infinity"])
def test_a_decimal_column_refuses_nan_and_infinity_on_read(tmp_path, token):
    """A stored null changed to NaN still matched the hash, and sNaN raised InvalidOperation."""
    column = Column("c", "decimal", precision=5, scale=2)
    _one_column(tmp_path, [None, Decimal("1.00")], column)
    _replace_in_csv(tmp_path / "b", "\\N", token)
    with pytest.raises(BundleError, match="NaN/infinity is not allowed"):
        read_bundle(tmp_path / "b")


@pytest.mark.parametrize("kind", ["int64", "float64", "decimal"])
def test_a_signaling_nan_is_refused_on_write(tmp_path, kind):
    column = Column(
        "c",
        kind,
        precision=5 if kind == "decimal" else None,
        scale=2 if kind == "decimal" else None,
    )
    _refused(tmp_path, [Decimal("sNaN")], column, "signaling NaN")


@pytest.mark.parametrize(
    ("column", "value", "stored", "message"),
    [
        (Column("c", "decimal", precision=5, scale=2), Decimal("1.00"), "1.234", "decimal places"),
        (Column("c", "decimal", precision=5, scale=2), Decimal("1.00"), "1234.00", "does not fit"),
        (
            Column("t", "timestamp"),
            pd.Timestamp("2020-01-01T00:00:00.123456Z"),
            "2020-01-01T00:00:00.123456789Z",
            "nanoseconds",
        ),
        (Column("d", "date"), date(2000, 1, 1), "1500-01-01", "outside the dates"),
    ],
)
def test_readers_check_every_value_without_a_content_hash(tmp_path, column, value, stored, message):
    """Without content_sha256 the reader returned 1.234 for decimal(5, 2) and nanoseconds."""
    _one_column(tmp_path, [value], column)
    path = tmp_path / "b"
    _without_hash(path)
    text = (path / "data.csv").read_text(encoding="utf-8").splitlines()[1]
    _replace_in_csv(path, text, stored)
    with pytest.raises(BundleError, match=message):
        read_bundle(path)


def test_int64_columns_refuse_other_numbers_with_a_fraction(tmp_path):
    """int() truncated them: Fraction(7, 2) was stored as 3."""
    from fractions import Fraction

    _refused(tmp_path, [Fraction(7, 2)], Column("n", "int64"), "non-integer value")
    if np.finfo(np.longdouble).nmant > 52:  # an 80-bit long double (not on Windows)
        value = np.longdouble(2**53) + np.longdouble(0.5)
        _refused(tmp_path, [value], Column("n", "int64"), "non-integer value")
    assert _one_column(tmp_path, [Fraction(6, 2)], Column("n", "int64"))[1]["n"].tolist() == [3]


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize(
    ("column", "value"),
    [
        (Column("d", "date"), date(1500, 1, 1)),
        (Column("d", "date"), date(2262, 4, 12)),
        (Column("d", "date"), date(1677, 9, 21)),
        (Column("t", "timestamp"), datetime(1500, 1, 1, tzinfo=UTC)),
        (Column("t", "timestamp"), datetime(2262, 4, 12, tzinfo=UTC)),
    ],
)
def test_dates_and_timestamps_outside_the_reader_range_are_refused(tmp_path, fmt, column, value):
    """They escaped as pandas OutOfBoundsDatetime from the writer's own read-back."""
    _refused(tmp_path, [value], column, "outside the", fmt=fmt)


@pytest.mark.parametrize("fmt", FORMATS)
def test_dates_at_the_edges_of_the_reader_range_round_trip(tmp_path, fmt):
    _, frame = _one_column(
        tmp_path, [date(1677, 9, 22), date(2262, 4, 11)], Column("d", "date"), fmt=fmt
    )
    assert frame["d"].dt.date.tolist() == [date(1677, 9, 22), date(2262, 4, 11)]


@pytest.mark.parametrize("kind", ["int64", "float64", "decimal", "date"])
def test_integers_too_long_for_text_are_refused_as_bundle_errors(tmp_path, kind):
    """Building the message raised ValueError (the int-to-text digit limit)."""
    column = Column(
        "c",
        kind,
        precision=5 if kind == "decimal" else None,
        scale=0 if kind == "decimal" else None,
    )
    with pytest.raises(BundleError, match="integer of"):
        _one_column(tmp_path, [10**5000], column, name="refused")


def test_a_string_with_a_lone_surrogate_is_refused(tmp_path):
    _refused(tmp_path, ["a\ud800b"], Column("s", "string"), "not valid Unicode text")


@pytest.mark.parametrize(
    "changes",
    [
        {"metadata": {1: "a", "1": "b"}},  # json.dumps kept only "1": "b"
        {"metadata": {"nested": [{None: 1}]}},  # written as "null"
        {"provenance": {True: "x"}},  # written as "true"
    ],
)
def test_metadata_and_provenance_keys_must_be_strings(tmp_path, changes):
    frame = pd.DataFrame({"k": ["a"]})
    with pytest.raises(BundleError, match="is not a string"):
        write_bundle(frame, tmp_path / "b", dataset_id="x", **changes)
    assert not list(tmp_path.iterdir())


def test_deeply_nested_metadata_is_refused_on_write_and_read(tmp_path):
    deep: dict = {}
    node = deep
    for _ in range(100_000):
        node["a"] = {}
        node = node["a"]
    frame = pd.DataFrame({"k": ["a"]})
    with pytest.raises(BundleError, match="metadata"):
        write_bundle(frame, tmp_path / "w", dataset_id="x", metadata=deep)
    path = _published(tmp_path)
    text = (path / "manifest.json").read_text()
    (path / "manifest.json").write_text(
        text.replace(
            '"provenance": {}', '"provenance": ' + '{"a": ' * 100_000 + "1" + "}" * 100_000
        )
    )
    with pytest.raises(BundleError, match="invalid manifest JSON"):
        read_manifest(path)


def test_created_at_must_be_a_datetime(tmp_path):
    frame = pd.DataFrame({"k": ["a"]})
    with pytest.raises(BundleError, match="created_at must be timezone-aware"):
        write_bundle(frame, tmp_path / "b", dataset_id="x", created_at=date(2026, 1, 1))  # type: ignore[arg-type]


def test_parquet_readers_refuse_a_stored_nan_like_csv_readers(tmp_path):
    """Writers store a missing float as null; a NaN in the file is refused in every format."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    _one_column(tmp_path, [1.0, None], Column("x", "float64"), fmt="parquet")
    path = tmp_path / "b"
    pq.write_table(
        pa.table({"x": pa.array([1.0, float("nan")], type=pa.float64())}), path / "data.parquet"
    )
    with pytest.raises(BundleError, match="NaN/infinity is not allowed"):
        read_bundle(path)
    _one_column(tmp_path, [1.0, None], Column("x", "float64"), name="c")
    _replace_in_csv(tmp_path / "c", "\\N", "NaN")
    with pytest.raises(BundleError, match="NaN/infinity is not allowed"):
        read_bundle(tmp_path / "c")
