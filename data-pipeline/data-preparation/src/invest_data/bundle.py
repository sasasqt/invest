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
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CONTRACT_VERSION = 1
NULL_TOKEN = "\\N"
LOGICAL_TYPES = ("string", "int64", "float64", "boolean", "date", "timestamp", "decimal")
STORAGE_FORMATS = {"csv": "data.csv", "sqlite": "data.sqlite", "parquet": "data.parquet"}
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
        try:
            col = Column(
                name=str(raw["name"]),
                type=str(raw["type"]),
                nullable=bool(raw.get("nullable", True)),
                precision=raw.get("precision"),
                scale=raw.get("scale"),
                unit=raw.get("unit"),
                description=raw.get("description"),
            )
        except KeyError as exc:
            raise BundleError(f"column definition missing {exc}") from exc
        if col.type not in LOGICAL_TYPES:
            raise BundleError(f"column {col.name!r}: unsupported logical type {col.type!r}")
        if col.type == "decimal" and (col.precision is None or col.scale is None):
            raise BundleError(f"decimal column {col.name!r} must declare precision and scale")
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


def _format_value(col: Column, value: Any) -> str | int | float | None:
    """Convert a Python/pandas value to its stored text (CSV) form, or None for null."""
    # pandas missing values (None, NaN, NaT, pd.NA) are stored as null; infinity is rejected.
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if col.type == "string":
        return str(value)
    if col.type == "int64":
        if isinstance(value, bool | np.bool_):
            raise BundleError(f"column {col.name!r}: boolean given for int64")
        if isinstance(value, float | np.floating) and not float(value).is_integer():
            raise BundleError(f"column {col.name!r}: non-integer value {value!r}")
        return int(value)
    if col.type == "float64":
        return _check_finite(col.name, float(value))
    if col.type == "boolean":
        if not isinstance(value, bool | np.bool_):
            raise BundleError(f"column {col.name!r}: expected boolean, got {value!r}")
        return "true" if bool(value) else "false"
    if col.type == "date":
        return pd.Timestamp(value).date().isoformat()
    if col.type == "timestamp":
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            raise BundleError(f"column {col.name!r}: timestamps must be timezone-aware")
        return ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ").replace(".000000Z", "Z")
    if col.type == "decimal":
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
        if not dec.is_finite():
            raise BundleError(f"column {col.name!r}: non-finite decimal")
        assert col.scale is not None
        return str(dec.quantize(Decimal(1).scaleb(-col.scale)))
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
            return Decimal(str(raw))
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
    """Format-independent content hash, so CSV and SQLite copies of a dataset agree."""
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
        [_format_value(col, v) for col, v in zip(cols, rec, strict=True)]
        for rec in frame.itertuples(index=False, name=None)
    ]
    created = (created_at or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
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
        (tmp / "manifest.json").write_text(json.dumps(manifest.to_json(), indent=2) + "\n")
        read_bundle(tmp)  # round-trip validation before publication
        os.rename(tmp, target)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return manifest


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


def read_manifest(path: str | os.PathLike[str]) -> Manifest:
    root = Path(path)
    mpath = root / "manifest.json"
    if not mpath.is_file():
        raise BundleError(f"missing manifest.json in {root}")
    try:
        raw = json.loads(mpath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BundleError(f"invalid manifest JSON: {exc}") from exc
    version = raw.get("contract_version")
    if version != CONTRACT_VERSION:
        raise BundleError(f"unsupported contract_version {version!r}")
    for key in ("dataset_id", "storage", "row_count", "columns"):
        if key not in raw:
            raise BundleError(f"manifest missing {key!r}")
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
        row_count=int(raw["row_count"]),
        primary_key=tuple(raw.get("primary_key", [])),
        created_at=str(raw.get("created_at", "")),
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
    if manifest.content_sha256 is not None:
        canonical = [
            [_format_value(c, v) for c, v in zip(manifest.columns, r, strict=True)] for r in rows
        ]
        if _content_sha256(manifest.columns, canonical) != manifest.content_sha256:
            raise BundleError("content hash mismatch: data does not match its manifest")
    return manifest, _to_frame(manifest.columns, rows)


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
    """Canonical stored value (see _format_value) -> Python object for pyarrow."""
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
        columns.append([_format_value(col, v) for v in table.column(col.name).to_pylist()])
    return [list(r) for r in zip(*columns, strict=True)] if columns else []
