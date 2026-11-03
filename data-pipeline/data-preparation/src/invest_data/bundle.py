"""Version 1 dataset bundle contract: manifest + CSV, SQLite or Parquet data.

See docs/DATA_CONTRACT.md.

This module is the public, versioned contract API shared by producers and consumers.
Readers validate everything they rely on and raise :class:`BundleError` on violations;
they never silently coerce data.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import numbers
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Context, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CONTRACT_VERSION = 1
NULL_TOKEN = "\\N"
LOGICAL_TYPES = ("string", "int64", "float64", "boolean", "date", "timestamp", "decimal")
STORAGE_FORMATS = {"csv": "data.csv", "sqlite": "data.sqlite", "parquet": "data.parquet"}
# int64 bounds, and the most digits a Parquet decimal128 holds.
_INT64_MIN, _INT64_MAX = -(2**63), 2**63 - 1
_MAX_DECIMAL_PRECISION = 38
# Readers return dates and timestamps as datetime64[ns], which holds only this span.
_MIN_TIME, _MAX_TIME = pd.Timestamp.min, pd.Timestamp.max
_MIN_DATE, _MAX_DATE = date(1677, 9, 22), date(2262, 4, 11)
_SQLITE_TYPES = {
    "string": "TEXT",
    "int64": "INTEGER",
    "float64": "REAL",
    "boolean": "INTEGER",
    "date": "TEXT",
    "timestamp": "TEXT",
    "decimal": "TEXT",
}


class BundleError(ValueError):
    """Raised when a bundle or its manifest violates the dataset contract."""


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    nullable: bool = True
    precision: int | None = None
    scale: int | None = None
    unit: str | None = None
    description: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "type": self.type, "nullable": self.nullable}
        for key in ("precision", "scale", "unit", "description"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out

    @staticmethod
    def from_json(raw: Mapping[str, Any]) -> Column:
        if not isinstance(raw, Mapping):
            raise BundleError(f"column definition must be a JSON object, not {raw!r}")
        for key in ("name", "type"):
            if key in raw and not isinstance(raw[key], str):
                raise BundleError(f"column {raw.get('name')!r}: {key} must be a string")
        for key in ("precision", "scale"):
            value = raw.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise BundleError(f"column {raw.get('name')!r}: {key} must be an integer")
        if not isinstance(raw.get("nullable", True), bool):
            raise BundleError(f"column {raw.get('name')!r}: nullable must be true or false")
        for key in ("unit", "description"):
            if raw.get(key) is not None and not isinstance(raw[key], str):
                raise BundleError(f"column {raw.get('name')!r}: {key} must be a string")
        try:
            col = Column(
                name=raw["name"],
                type=raw["type"],
                nullable=raw.get("nullable", True),
                precision=raw.get("precision"),
                scale=raw.get("scale"),
                unit=raw.get("unit"),
                description=raw.get("description"),
            )
        except KeyError as exc:
            raise BundleError(f"column definition missing {exc}") from exc
        if col.type not in LOGICAL_TYPES:
            raise BundleError(f"column {col.name!r}: unsupported logical type {col.type!r}")
        if col.type == "decimal":
            if col.precision is None or col.scale is None:
                raise BundleError(f"decimal column {col.name!r} must declare precision and scale")
            # The bounds of Parquet's decimal128, so every storage format holds the column.
            if (
                not 1 <= col.precision <= _MAX_DECIMAL_PRECISION
                or not 0 <= col.scale <= col.precision
            ):
                raise BundleError(
                    f"decimal column {col.name!r}: precision must be 1 to "
                    f"{_MAX_DECIMAL_PRECISION} and scale 0 to the precision, got "
                    f"({col.precision}, {col.scale})"
                )
        return col


@dataclass(frozen=True)
class Manifest:
    dataset_id: str
    columns: tuple[Column, ...]
    storage: dict[str, str]
    row_count: int
    primary_key: tuple[str, ...] = ()
    created_at: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    # Optional extensions (backward compatible with v1 readers that ignore unknown keys).
    dataset_kind: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    content_sha256: str | None = None

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "contract_version": CONTRACT_VERSION,
            "dataset_id": self.dataset_id,
            "created_at": self.created_at,
            "storage": dict(self.storage),
            "row_count": self.row_count,
            "primary_key": list(self.primary_key),
            "columns": [c.to_json() for c in self.columns],
            "provenance": self.provenance,
        }
        if self.dataset_kind is not None:
            out["dataset_kind"] = self.dataset_kind
        if self.metadata:
            out["metadata"] = self.metadata
        if self.content_sha256 is not None:
            out["content_sha256"] = self.content_sha256
        return out


# ---------------------------------------------------------------------------
# Value encoding


def _escape_csv(text: str) -> str:
    return "\\" + text if text.startswith("\\") else text


def _unescape_csv(raw: str) -> str | None:
    if raw == NULL_TOKEN:
        return None
    return raw[1:] if raw.startswith("\\") else raw


def _check_finite(name: str, value: float) -> float:
    if not math.isfinite(value):
        raise BundleError(f"column {name!r}: NaN/infinity is not allowed (use null)")
    return value


def _show(value: Any) -> str:
    """``repr(value)`` for an error message; an integer too long for text is described."""
    try:
        return repr(value)
    except ValueError:  # beyond sys.get_int_max_str_digits()
        return f"an integer of {int(value).bit_length()} bits"


def _as_timestamp(col: Column, value: Any) -> pd.Timestamp:
    """A ``date`` or ``timestamp`` value as a pandas Timestamp. Numbers are refused:
    pandas would read them as nanoseconds since 1970."""
    if isinstance(value, bool | numbers.Number | np.number | np.bool_):
        raise BundleError(
            f"column {col.name!r}: expected a {col.type}, got the number {_show(value)}"
        )
    try:
        ts = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BundleError(f"column {col.name!r}: cannot read {value!r} as a {col.type}") from exc
    if ts is pd.NaT:
        raise BundleError(f"column {col.name!r}: cannot read {value!r} as a {col.type}")
    return ts


def _decimal(col: Column, value: Any) -> str:
    """The stored text of a decimal that fits ``decimal(precision, scale)`` exactly.

    A value with more fractional digits than the scale, or more integer digits than
    ``precision - scale``, is refused rather than rounded; a signed zero is stored as 0
    (Parquet's decimal128 has no negative zero).
    """
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:  # ValueError: an int too long for text
        raise BundleError(f"column {col.name!r}: cannot read {_show(value)} as a decimal") from exc
    if not dec.is_finite():
        raise BundleError(f"column {col.name!r}: non-finite decimal")
    assert col.precision is not None and col.scale is not None
    declared = f"decimal({col.precision}, {col.scale})"
    if dec.copy_abs() >= Decimal(1).scaleb(col.precision - col.scale):
        raise BundleError(f"column {col.name!r}: {_show(value)} does not fit {declared}")
    # Enough context digits that quantize never fails on a value that fits (the default
    # context holds 28), plus one so an inexact value rounding up is caught below.
    stored = dec.quantize(Decimal(1).scaleb(-col.scale), context=Context(prec=col.precision + 1))
    if stored != dec:
        raise BundleError(
            f"column {col.name!r}: {value!r} has more than {col.scale} decimal places "
            f"for {declared}; bundles store decimals exactly and never round them"
        )
    return str(stored.copy_abs() if stored.is_zero() else stored)


def format_value(col: Column, value: Any) -> str | int | float | None:
    """Convert a Python/pandas value to its stored text (CSV) form, or None for null.

    Public so that contract checks judge the values exactly as they will be stored. A
    value the column cannot store exactly is refused, never rounded or truncated.
    """
    # A signaling NaN raises decimal.InvalidOperation in any comparison, pd.isna included.
    if isinstance(value, Decimal) and value.is_snan():
        raise BundleError(f"column {col.name!r}: cannot store the signaling NaN {value!r}")
    # pandas missing values (None, NaN, NaT, pd.NA) are stored as null; infinity is rejected.
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if col.type == "string":
        text = str(value)
        try:
            text.encode("utf-8")
        except UnicodeEncodeError as exc:  # a lone surrogate has no UTF-8 form
            raise BundleError(f"column {col.name!r}: {text!r} is not valid Unicode text") from exc
        return text
    if col.type == "int64":
        if isinstance(value, bool | np.bool_):
            raise BundleError(f"column {col.name!r}: boolean given for int64")
        if isinstance(value, float | np.floating) and not float(value).is_integer():
            raise BundleError(f"column {col.name!r}: non-integer value {value!r}")
        if isinstance(value, Decimal) and value != value.to_integral_value():
            raise BundleError(f"column {col.name!r}: non-integer value {value!r}")
        try:
            number = int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise BundleError(f"column {col.name!r}: cannot store {_show(value)} as int64") from exc
        # int() truncates any other real number with a fraction (Fraction(7, 2), a long
        # double that a float cannot hold exactly).
        if isinstance(value, numbers.Real | np.floating) and number != value:
            raise BundleError(f"column {col.name!r}: non-integer value {value!r}")
        if not _INT64_MIN <= number <= _INT64_MAX:
            raise BundleError(f"column {col.name!r}: {_show(value)} is outside the int64 range")
        return number
    if col.type == "float64":
        try:
            real = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise BundleError(
                f"column {col.name!r}: cannot store {_show(value)} as float64"
            ) from exc
        _check_finite(col.name, real)
        # -0.0 is stored as 0.0: SQLite reads a stored -0.0 back as 0.0, and the copies in
        # every format must hold the same values.
        return 0.0 if real == 0 else real
    if col.type == "boolean":
        if not isinstance(value, bool | np.bool_):
            raise BundleError(f"column {col.name!r}: expected boolean, got {value!r}")
        return "true" if bool(value) else "false"
    if col.type == "date":
        ts = _as_timestamp(col, value)
        if ts.tzinfo is not None or ts != ts.normalize():
            raise BundleError(
                f"column {col.name!r}: {value!r} is not a date; a date column holds no time "
                "of day or time zone"
            )
        day = ts.date()
        if not _MIN_DATE <= day <= _MAX_DATE:
            raise BundleError(
                f"column {col.name!r}: {day} is outside the dates a reader can return "
                f"({_MIN_DATE} to {_MAX_DATE})"
            )
        return day.isoformat()
    if col.type == "timestamp":
        ts = _as_timestamp(col, value)
        if ts.tzinfo is None:
            raise BundleError(f"column {col.name!r}: timestamps must be timezone-aware")
        if ts.nanosecond:
            raise BundleError(
                f"column {col.name!r}: {value!r} has nanoseconds; timestamps are stored to "
                "the microsecond"
            )
        utc = ts.tz_convert("UTC")
        if not _MIN_TIME <= utc.tz_localize(None) <= _MAX_TIME:
            raise BundleError(
                f"column {col.name!r}: {value!r} is outside the times a reader can return "
                f"({_MIN_TIME} to {_MAX_TIME} UTC)"
            )
        return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ").replace(".000000Z", "Z")
    if col.type == "decimal":
        return _decimal(col, value)
    raise BundleError(f"unsupported type {col.type}")  # pragma: no cover


def _parse_value(col: Column, raw: Any) -> Any:
    """Parse a stored value (CSV text or SQLite value) into the logical Python value."""
    if raw is None:
        return None
    try:
        if col.type == "string":
            if not isinstance(raw, str):
                raise BundleError(f"column {col.name!r}: expected text, got {type(raw).__name__}")
            return raw
        if col.type == "int64":
            if isinstance(raw, float):
                raise BundleError(f"column {col.name!r}: expected integer, got REAL")
            return int(raw)
        if col.type == "float64":
            return _check_finite(col.name, float(raw))
        if col.type == "boolean":
            if raw in ("true", 1) and not isinstance(raw, float):
                return True
            if raw in ("false", 0) and not isinstance(raw, float):
                return False
            raise BundleError(f"column {col.name!r}: invalid boolean {raw!r}")
        if col.type == "date":
            text = str(raw)
            if len(text) != 10:
                raise BundleError(f"column {col.name!r}: invalid date {raw!r}")
            return datetime.strptime(text, "%Y-%m-%d").date()
        if col.type == "timestamp":
            text = str(raw)
            if not text.endswith("Z"):
                raise BundleError(f"column {col.name!r}: timestamp must be UTC with 'Z'")
            return pd.Timestamp(text)
        if col.type == "decimal":
            dec = Decimal(str(raw))
            if not dec.is_finite():  # NaN, sNaN and infinity, as in float columns
                raise BundleError(f"column {col.name!r}: NaN/infinity is not allowed (use null)")
            return dec
    except (ValueError, InvalidOperation) as exc:
        if isinstance(exc, BundleError):
            raise
        raise BundleError(f"column {col.name!r}: cannot parse {raw!r} as {col.type}") from exc
    raise BundleError(f"unsupported type {col.type}")  # pragma: no cover


def _to_frame(columns: Sequence[Column], rows: list[list[Any]]) -> pd.DataFrame:
    data: dict[str, pd.Series] = {}
    for j, col in enumerate(columns):
        values = [row[j] for row in rows]
        if col.type == "float64":
            series = pd.Series([np.nan if v is None else v for v in values], dtype="float64")
        elif col.type == "int64":
            series = pd.Series(values, dtype="Int64")
        elif col.type == "boolean":
            series = pd.Series(values, dtype="boolean")
        elif col.type == "date":
            series = pd.Series(pd.to_datetime(values), dtype="datetime64[ns]")
        elif col.type == "timestamp":
            series = pd.Series(pd.to_datetime(values, utc=True))
        else:
            series = pd.Series(values, dtype="object")
        data[col.name] = series
    return pd.DataFrame(data, columns=[c.name for c in columns])


# ---------------------------------------------------------------------------
# Schema inference helper


def infer_columns(
    frame: pd.DataFrame,
    nullable: Mapping[str, bool] | None = None,
    units: Mapping[str, str] | None = None,
) -> tuple[Column, ...]:
    """Infer logical columns from pandas dtypes (dates without time become ``date``)."""
    nullable = nullable or {}
    units = units or {}
    cols = []
    for name in frame.columns:
        s = frame[name]
        if pd.api.types.is_bool_dtype(s):
            t = "boolean"
        elif pd.api.types.is_integer_dtype(s):
            t = "int64"
        elif pd.api.types.is_float_dtype(s):
            t = "float64"
        elif isinstance(s.dtype, pd.DatetimeTZDtype):
            t = "timestamp"
        elif pd.api.types.is_datetime64_any_dtype(s):
            t = "date"
        else:
            t = "string"
        cols.append(
            Column(
                str(name),
                t,
                nullable=nullable.get(str(name), bool(s.isna().any())),
                unit=units.get(str(name)),
            )
        )
    return tuple(cols)


# ---------------------------------------------------------------------------
# Writing


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _content_sha256(columns: Sequence[Column], rows: list[list[Any]]) -> str:
    """Format-independent content hash, so CSV, SQLite and Parquet copies of a dataset agree."""
    h = hashlib.sha256()
    h.update(json.dumps([c.to_json() for c in columns], sort_keys=True).encode())
    for row in rows:
        h.update(json.dumps(row, default=str, separators=(",", ":")).encode())
        h.update(b"\n")
    return h.hexdigest()


def _validate_table(manifest: Manifest, rows: list[list[Any]]) -> None:
    names = manifest.column_names
    if len(set(names)) != len(names):
        raise BundleError("column names must be unique")
    if len(rows) != manifest.row_count:
        raise BundleError(f"row_count {manifest.row_count} != stored rows {len(rows)}")
    for j, col in enumerate(manifest.columns):
        if not col.nullable and any(row[j] is None for row in rows):
            raise BundleError(f"column {col.name!r} is not nullable but contains nulls")
    if manifest.primary_key:
        missing = set(manifest.primary_key) - set(names)
        if missing:
            raise BundleError(f"primary key columns not in schema: {sorted(missing)}")
        idx = [names.index(k) for k in manifest.primary_key]
        seen: set[tuple[Any, ...]] = set()
        for row in rows:
            key = tuple(row[i] for i in idx)
            if any(v is None for v in key):
                raise BundleError("primary key contains null")
            if key in seen:
                raise BundleError(f"duplicate primary key {key!r}")
            seen.add(key)


def write_bundle(
    frame: pd.DataFrame,
    path: str | os.PathLike[str],
    *,
    dataset_id: str,
    fmt: str = "csv",
    columns: Sequence[Column] | None = None,
    primary_key: Sequence[str] = (),
    provenance: Mapping[str, Any] | None = None,
    dataset_kind: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    table: str = "observations",
    created_at: datetime | None = None,
) -> Manifest:
    """Validate ``frame`` and publish it atomically as a new bundle directory at ``path``.

    The target must not exist (published bundles are immutable). On any failure no
    partial bundle is left at ``path``.
    """
    target = Path(path)
    if target.exists():
        raise BundleError(f"bundle already exists: {target}")
    if fmt not in STORAGE_FORMATS:
        raise BundleError(f"unsupported storage format {fmt!r}")
    if not table.isidentifier():
        raise BundleError(f"invalid SQLite table name {table!r}")
    cols = tuple(columns) if columns is not None else infer_columns(frame)
    if [c.name for c in cols] != [str(c) for c in frame.columns]:
        raise BundleError("declared columns must match frame columns in order")
    for c in cols:
        Column.from_json(c.to_json())  # validates type/decimal declaration

    rows = [
        [format_value(col, v) for col, v in zip(cols, rec, strict=True)]
        for rec in frame.itertuples(index=False, name=None)
    ]
    when = datetime.now(UTC) if created_at is None else created_at
    if not isinstance(when, datetime) or when.utcoffset() is None:
        raise BundleError(
            f"created_at must be timezone-aware: a datetime with a UTC offset, not {when!r}"
        )
    created = when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    storage = {"format": fmt, "path": STORAGE_FORMATS[fmt]}
    if fmt == "sqlite":
        storage["table"] = table
    manifest = Manifest(
        dataset_id=dataset_id,
        columns=cols,
        storage=storage,
        row_count=len(rows),
        primary_key=tuple(primary_key),
        created_at=created,
        provenance=dict(provenance or {}),
        dataset_kind=dataset_kind,
        metadata=dict(metadata or {}),
        content_sha256=_content_sha256(cols, rows),
    )
    _validate_table(manifest, rows)
    # Strict JSON: NaN and infinity have no JSON form, and other objects have none either.
    try:
        _require_string_keys(manifest.metadata, "metadata")
        _require_string_keys(manifest.provenance, "provenance")
        manifest_text = json.dumps(manifest.to_json(), indent=2, allow_nan=False) + "\n"
    except BundleError:
        raise
    except (TypeError, ValueError, RecursionError) as exc:
        raise BundleError(
            f"metadata and provenance must be JSON values with finite numbers: {exc}"
        ) from exc

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        data_path = tmp / storage["path"]
        if fmt == "csv":
            _write_csv(data_path, cols, rows)
        elif fmt == "parquet":
            _write_parquet(data_path, cols, rows)
        else:
            _write_sqlite(data_path, cols, rows, table)
        (tmp / "manifest.json").write_text(manifest_text, encoding="utf-8")
        read_bundle(tmp)  # round-trip validation before publication
        os.rename(tmp, target)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return manifest


def _require_string_keys(value: Any, where: str) -> None:
    """Refuse object keys that are not strings: JSON would write 1, True or None as "1",
    "true" or "null", and keep only the last of two keys that become equal."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise BundleError(f"{where}: key {key!r} is not a string")
            _require_string_keys(item, where)
    elif isinstance(value, list | tuple):
        for item in value:
            _require_string_keys(item, where)


def _write_csv(path: Path, cols: Sequence[Column], rows: list[list[Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow([c.name for c in cols])
        for row in rows:
            out = []
            for col, v in zip(cols, row, strict=True):
                if v is None:
                    out.append(NULL_TOKEN)
                elif col.type == "string":
                    out.append(_escape_csv(str(v)))
                elif col.type == "float64":
                    out.append(repr(float(v)))
                else:
                    out.append(str(v))
            writer.writerow(out)


def _write_sqlite(path: Path, cols: Sequence[Column], rows: list[list[Any]], table: str) -> None:
    con = sqlite3.connect(path)
    try:
        defs = ", ".join(f'"{c.name}" {_SQLITE_TYPES[c.type]}' for c in cols)
        con.execute(f'CREATE TABLE "{table}" ({defs})')
        sql_rows = [
            [
                (v == "true") if (c.type == "boolean" and v is not None) else v
                for c, v in zip(cols, row, strict=True)
            ]
            for row in rows
        ]
        placeholders = ", ".join("?" for _ in cols)
        con.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', sql_rows)
        con.commit()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Reading


def _refuse_json_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON: manifest numbers must be finite")


def _finite_json_number(text: str) -> float:
    number = float(text)
    if not math.isfinite(number):
        raise ValueError(f"{text} is beyond the float range: manifest numbers must be finite")
    return number


def read_manifest(path: str | os.PathLike[str]) -> Manifest:
    root = Path(path)
    mpath = root / "manifest.json"
    if not mpath.is_file():
        raise BundleError(f"missing manifest.json in {root}")
    try:
        raw = json.loads(
            mpath.read_text(encoding="utf-8"),
            parse_constant=_refuse_json_constant,
            parse_float=_finite_json_number,
        )
    except (ValueError, RecursionError) as exc:  # also JSONDecodeError and UnicodeDecodeError
        raise BundleError(f"invalid manifest JSON: {exc}") from exc
    # A malformed manifest is a BundleError like any other invalid bundle, never a TypeError.
    if not isinstance(raw, dict):
        raise BundleError("manifest must be a JSON object")
    version = raw.get("contract_version")
    if version != CONTRACT_VERSION:
        raise BundleError(f"unsupported contract_version {version!r}")
    for key in ("dataset_id", "storage", "row_count", "columns"):
        if key not in raw:
            raise BundleError(f"manifest missing {key!r}")
    for key, kind, name in (
        ("storage", dict, "object"),
        ("columns", list, "array"),
        ("primary_key", list, "array"),
        ("provenance", dict, "object"),
        ("metadata", dict, "object"),
    ):
        if key in raw and not isinstance(raw[key], kind):
            raise BundleError(f"manifest {key!r} must be a JSON {name}")
    for key in ("dataset_kind", "content_sha256", "created_at"):
        if raw.get(key) is not None and not isinstance(raw[key], str):
            raise BundleError(f"manifest {key!r} must be a string")
    if not isinstance(raw["dataset_id"], str):
        raise BundleError("manifest 'dataset_id' must be a string")
    if not all(isinstance(v, str) for v in raw["storage"].values()):
        raise BundleError("manifest 'storage' values must be strings")
    if not all(isinstance(k, str) for k in raw.get("primary_key", [])):
        raise BundleError("manifest 'primary_key' must list column names")
    row_count = raw["row_count"]
    if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 0:
        raise BundleError(f"manifest 'row_count' must be a non-negative integer, not {row_count!r}")
    storage = raw["storage"]
    if storage.get("format") not in STORAGE_FORMATS:
        raise BundleError(f"unsupported storage format {storage.get('format')!r}")
    rel = Path(str(storage.get("path", "")))
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise BundleError("storage path must be relative and stay inside the bundle")
    if storage["format"] == "sqlite" and not str(storage.get("table", "")).isidentifier():
        raise BundleError("SQLite storage requires a valid table identifier")
    return Manifest(
        dataset_id=str(raw["dataset_id"]),
        columns=tuple(Column.from_json(c) for c in raw["columns"]),
        storage={k: str(v) for k, v in storage.items()},
        row_count=row_count,
        primary_key=tuple(raw.get("primary_key", [])),
        created_at=raw.get("created_at") or "",
        provenance=dict(raw.get("provenance", {})),
        dataset_kind=raw.get("dataset_kind"),
        metadata=dict(raw.get("metadata", {})),
        content_sha256=raw.get("content_sha256"),
    )


def read_bundle(path: str | os.PathLike[str]) -> tuple[Manifest, pd.DataFrame]:
    """Read and fully validate a bundle; returns its manifest and a typed DataFrame."""
    root = Path(path)
    manifest = read_manifest(root)
    data_path = (root / manifest.storage["path"]).resolve()
    if root.resolve() not in data_path.parents:
        raise BundleError("storage path escapes the bundle root")
    if not data_path.is_file():
        raise BundleError(f"missing data file {manifest.storage['path']}")
    if manifest.storage["format"] == "csv":
        stored = _read_csv(data_path, manifest)
    elif manifest.storage["format"] == "parquet":
        stored = _read_parquet(data_path, manifest)
    else:
        stored = _read_sqlite(data_path, manifest)
    rows = [[_parse_value(c, v) for c, v in zip(manifest.columns, r, strict=True)] for r in stored]
    _validate_table(manifest, rows)
    # Every stored value must be one a writer could store (decimal precision and scale,
    # microseconds, the date range), whether or not the manifest carries a hash.
    canonical = [
        [format_value(c, v) for c, v in zip(manifest.columns, r, strict=True)] for r in rows
    ]
    if manifest.content_sha256 is not None:
        if _content_sha256(
            manifest.columns, canonical
        ) != manifest.content_sha256 and not _signed_zero_hash_matches(manifest, rows, canonical):
            raise BundleError("content hash mismatch: data does not match its manifest")
    return manifest, _to_frame(manifest.columns, rows)


def _signed_zero(value: Any) -> bool:
    return isinstance(value, float | Decimal) and value == 0 and math.copysign(1.0, value) < 0


def _signed_zero_hash_matches(
    manifest: Manifest, rows: list[list[Any]], canonical: list[list[Any]]
) -> bool:
    """Whether the bundle's hash is that of its values with negative zeros kept.

    Bundles written before -0.0 and -0.00 were stored as 0 hashed them with their sign
    (CSV and Parquet kept it); they stay readable.
    """
    if not any(_signed_zero(v) for row in rows for v in row):
        return False
    legacy = [
        [
            (value if col.type == "float64" else "-" + str(stored))
            if _signed_zero(value)
            else stored
            for col, value, stored in zip(manifest.columns, row, crow, strict=True)
        ]
        for row, crow in zip(rows, canonical, strict=True)
    ]
    return _content_sha256(manifest.columns, legacy) == manifest.content_sha256


def _read_csv(path: Path, manifest: Manifest) -> list[list[Any]]:
    text = path.read_text(encoding="utf-8")
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise BundleError("CSV file has no header") from exc
    if header != manifest.column_names:
        raise BundleError(f"CSV header {header} does not match manifest columns")
    rows = []
    for line_no, rec in enumerate(reader, start=2):
        if len(rec) != len(header):
            raise BundleError(f"CSV line {line_no}: expected {len(header)} fields")
        rows.append([_unescape_csv(v) for v in rec])
    return rows


def _read_sqlite(path: Path, manifest: Manifest) -> list[list[Any]]:
    table = manifest.storage["table"]
    con = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        info = con.execute(f'PRAGMA table_info("{table}")').fetchall()
        if [r[1] for r in info] != manifest.column_names:
            raise BundleError(f"SQLite table {table!r} columns do not match manifest")
        cols = ", ".join(f'"{n}"' for n in manifest.column_names)
        return [list(r) for r in con.execute(f'SELECT {cols} FROM "{table}" ORDER BY rowid')]
    except sqlite3.Error as exc:
        raise BundleError(f"SQLite error: {exc}") from exc
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Parquet (typed columnar storage; no custom null/escape convention needed)


def _arrow_type(col: Column) -> Any:
    import pyarrow as pa

    if col.type == "decimal":
        assert col.precision is not None and col.scale is not None
        return pa.decimal128(col.precision, col.scale)
    return {
        "string": pa.string(),
        "int64": pa.int64(),
        "float64": pa.float64(),
        "boolean": pa.bool_(),
        "date": pa.date32(),
        "timestamp": pa.timestamp("us", tz="UTC"),
    }[col.type]


def _to_arrow_value(col: Column, v: Any) -> Any:
    """Canonical stored value (see format_value) -> Python object for pyarrow."""
    if v is None:
        return None
    if col.type == "boolean":
        return v == "true"
    if col.type == "date":
        return datetime.strptime(v, "%Y-%m-%d").date()
    if col.type == "timestamp":
        return pd.Timestamp(v).to_pydatetime()
    if col.type == "decimal":
        return Decimal(v)
    return v


def _write_parquet(path: Path, cols: Sequence[Column], rows: list[list[Any]]) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    arrays = [
        pa.array([_to_arrow_value(c, r[j]) for r in rows], type=_arrow_type(c))
        for j, c in enumerate(cols)
    ]
    schema = pa.schema([pa.field(c.name, _arrow_type(c), nullable=c.nullable) for c in cols])
    pq.write_table(pa.Table.from_arrays(arrays, schema=schema), path)


def _read_parquet(path: Path, manifest: Manifest) -> list[list[Any]]:
    import pyarrow.parquet as pq

    try:
        table = pq.read_table(path)
    except Exception as exc:  # pyarrow raises several unrelated exception types
        raise BundleError(f"Parquet error: {exc}") from exc
    if table.column_names != manifest.column_names:
        raise BundleError("Parquet columns do not match manifest")
    columns = []
    for col, arrow_field in zip(manifest.columns, table.schema, strict=True):
        if not arrow_field.type.equals(_arrow_type(col)):
            raise BundleError(f"column {col.name!r}: Parquet type {arrow_field.type} != {col.type}")
        # Re-encode to the canonical stored form so one parser validates every format.
        # Floats pass as stored: canonical form would turn a -0.0 into 0.0, and a bundle
        # written before negative zero was stored as 0 is verified with its sign. A stored
        # NaN is then refused like a CSV "NaN", where canonical form read it as null.
        values = table.column(col.name).to_pylist()
        columns.append(values if col.type == "float64" else [format_value(col, v) for v in values])
    return [list(r) for r in zip(*columns, strict=True)] if columns else []
