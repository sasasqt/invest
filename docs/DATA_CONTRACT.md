# Dataset exchange contract

Status: architecture specification for the two independent components. Readers, writers, and validation tests are not implemented yet.

## Boundary

The data pipeline downloads, cleans, and preprocesses data. It publishes immutable dataset artifacts. The mining framework consumes those artifacts and produces analysis results. Neither component imports the other's implementation or requires the other's service to run.

Both components implement this versioned contract independently. Changes to it require compatibility review and producer/consumer fixture tests. Both components live in separate folders on main; the artifact contract provides runtime decoupling without cross-component imports.

## Version 1 dataset bundle

Each dataset is a directory containing `manifest.json` and either `data.csv` or `data.sqlite`. The initial formats are CSV and SQLite, both usable without a database server. Other database systems can be added behind separate adapters later.

Example manifest for CSV:

```json
{
  "contract_version": 1,
  "dataset_id": "example-observations",
  "created_at": "2026-01-01T00:00:00Z",
  "storage": {"format": "csv", "path": "data.csv"},
  "row_count": 2,
  "primary_key": ["record_id"],
  "columns": [
    {"name": "record_id", "type": "string", "nullable": false},
    {"name": "value", "type": "float64", "nullable": true}
  ],
  "provenance": {
    "sources": ["example-source"],
    "transforms": ["deduplicate-record-id"]
  }
}
```

For SQLite, use `"storage": {"format": "sqlite", "path": "data.sqlite", "table": "observations"}`. The manifest defines logical types for both formats: `string`, `int64`, `float64`, `boolean`, `date`, `timestamp`, and `decimal`. Decimal columns additionally declare precision and scale. Column names are unique, ordered, and match the stored dataset. Nullable columns may contain nulls; a declared primary key must be non-null and unique. `row_count` must equal the stored row count.

## Serialization rules

- CSV uses UTF-8, a header, comma delimiters, and standard CSV quoting. Use the literal `\N` for null. To preserve strings, prefix a backslash to any non-null string beginning with a backslash; readers reverse that escape after detecting the null token. An empty string remains an empty string.
- Dates use ISO 8601 `YYYY-MM-DD`. Timestamps use RFC 3339 in UTC with a `Z` suffix. Boolean values are `true` or `false` in CSV. Numeric serialization is locale independent; NaN and infinity are rejected. Decimal values use base-10 strings without conversion through float.
- SQLite uses SQL NULL, INTEGER for int64 and booleans (0 or 1), REAL for float64, and TEXT for string, date, timestamp, and decimal. Readers enforce the manifest's logical types rather than relying on SQLite affinity alone.
- Artifact paths are relative to the bundle root and may not escape it. SQLite table names come from validated metadata and must be quoted safely; readers open databases read-only.
- Include units, currency, and feature meanings as optional column metadata where relevant. Provenance must not contain credentials or private access URLs.

## Publication and consumption

Write and validate an artifact in a temporary directory, then publish it atomically on the same filesystem. Never modify a published bundle in place. Consumers reject unsupported contract versions, missing files, schema mismatches, invalid values, and inconsistent row counts with actionable errors.

Preprocessing that learns from data, such as imputation, scaling, feature selection, or dimensionality reduction, belongs in the mining training workflow and must be fitted only on training partitions. Pipeline preprocessing is limited to deterministic cleaning and explicit domain transformations to avoid evaluation leakage.

## Required compatibility tests

Use shared fixture bundles, independent of either component's code, for CSV and SQLite. Include empty datasets, nulls, empty strings, escaped backslashes, Unicode, decimals, UTC timestamps, duplicate keys, invalid types, and unsupported versions. The producer must generate valid artifacts; the consumer must read valid fixtures and reject invalid ones. A future end-to-end check should publish a pipeline dataset and run mining against that artifact without importing pipeline modules.
