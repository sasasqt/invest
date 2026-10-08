# Dataset exchange contract

Status: implemented in `invest_data.bundle` (generic v1) and `invest_data.schemas` (financial dataset kinds), with tests in `data-pipeline/data-preparation/tests`. Fitted-model and report contracts are not yet machine-validated.

## Boundary

Data preparation downloads, cleans, and preprocesses data and publishes immutable dataset artifacts. Mining and strategy evaluation consume these artifacts independently. Mining additionally publishes factors/models and signals; strategy evaluation produces portfolio reports. No consumer requires the downloader to run during evaluation.

Producer and consumer adapters implement this versioned contract without depending on each other's private implementation. Changes require compatibility review and producer/consumer fixture tests. A shared public contract utility may be introduced if justified; runtime decoupling does not require duplicating business logic.

## Version 1 dataset bundle

Each dataset is a directory containing `manifest.json` and one data file: `data.csv`, `data.sqlite`, or `data.parquet`. All three work without a database server. Parquet is the recommended format for large panels: it is typed and columnar, so it needs no custom null/escape convention and standard tools (pandas, pyarrow, DuckDB, Polars) read it directly. CSV remains for human inspection and interchange. Other database systems can be added behind separate adapters later.

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

### Optional v1 extensions

Readers that ignore unknown keys remain compatible with these optional manifest fields:

- `content_sha256`: a format-independent hash of the column schema and canonical row values. CSV, SQLite and Parquet copies of the same data have the same hash. Readers verify it when present.
- `dataset_kind` and `metadata`: financial semantics layered on the generic table.
  - `market_bars`: keys `(date, instrument)`, columns `open, high, low, close, volume`, optionally followed by `close_as_traded`. Required metadata: `frequency`, `currency`, `price_adjustment` (`total_return_adjusted`, `split_adjusted` or `unadjusted`; other values are refused on publication and read), `calendar`. Prices are adjusted as declared and volume inversely, so `close * volume` is the session's dollar volume. `close_as_traded` is the close as it traded that session, before any later split or dividend adjustment: positive, or null when unknown. Price-level rules need it, because an adjusted level changes with every later corporate action; a name whose as-traded close is null on a decision date fails a minimum price. A missing row means the instrument was not tradable that session. Strategy evaluation and factor mining compute returns from `close` and accept only `total_return_adjusted` or `split_adjusted` bars until corporate actions are modelled (EVAL-01), and returns from `split_adjusted` bars exclude dividends; evaluation refuses `execution.min_price > 0` on bars without a known `close_as_traded` in the evaluation window.
  - `universe`: point-in-time membership intervals `(universe, instrument, start_date, end_date)`. Member on date `d` when `start_date <= d < end_date`; a null `end_date` means still a member. Intervals for one instrument must not overlap.
  - `fundamentals`: point-in-time values `(instrument, field, period_end, available_date, value)`, keyed by all but `value`. A row is usable from the close of `available_date`, which must not precede `period_end`. Revisions are new rows with a later `available_date`; nothing is overwritten. `invest_data.pit.fundamentals_asof` returns, for each date, the latest revision of the most recent period published by then.
  - `signals`: keys `(decision_date, instrument)`, column `score` (higher is more attractive). Required metadata: `available_at = "decision_date_close"`, `signal_type`, `factor_id`, `horizon_days`. Optional `n_trials`: how many candidates were tried before this signal was selected (for multiple-testing adjustments such as the deflated Sharpe). When present, it must be a JSON integer greater than zero; booleans, fractional numbers, strings and null are rejected on publication and read. Omit it when unknown; consumers default to one when it is absent. Optional `factor_evidence` (version 2) carries the factor's confirmation evidence to portfolio reports: `evidence_version = 2`, `factor_id` (equal to the bundle's), `horizon_days` (positive JSON integer, equal to the bundle's), `experiment_id`, `source` (`search` or `confirm`), `confirmation_use` (`confirmatory`, `exploratory` or `unrecorded`), `test_outcome` (`confirmation_passed`, `rejected` or `inconclusive`), `status` (equal to `test_outcome`, except `exploratory` whenever `confirmation_use` is), `family_size` (positive integer), `confirmation_window` (`start` and `end` ISO dates) and `statistics` with exactly `confirm_mean_rank_ic`, `confirm_t`, `p_one_sided`, `p_holm` and `n_dates` (finite numbers, or null when undefined). `invest_data.schemas.validate_factor_evidence` enforces this on publication and read. `confirm` evidence tests one fixed formula, so its `family_size` must be 1. Search evidence (`source = search`) also requires `n_trials` of at least `family_size`, and no decision date before `confirmation_window.start`, because earlier decisions selected the factor; both are checked on publication and read. The evidence describes the exported factor; it must never be used to choose which factor is exported. Consumers may act no earlier than the next session.

## Signal confirmation evidence

Evidence v2 binds the result to the tested prediction/holding horizon as well as the formula identity. `factor_id` identifies the formula, orientation and operator version; it deliberately excludes the horizon. `invest-mine export` therefore checks `config.json`'s `experiment.identity.params.horizon` against the frozen factor, includes that horizon in the evidence, and rejects missing or mismatched values before publishing. Publication and read both require the evidence's horizon to equal `metadata.horizon_days`; invalid or missing horizons cannot bypass the binding. CSV, SQLite and Parquet share these checks. Bundles with no `factor_evidence` remain supported.

Evidence v1 did not record the tested horizon and is refused with migration guidance. Do not change its version number or infer its horizon from the signals. Re-export to a new output directory using the original search/confirmation output and matching frozen factor:

```sh
uv run invest-mine export --data <market bundle> --from-search <original search output> --out <new signals>
uv run invest-mine export --data <market bundle> --factor <matching factor.json> \
  --confirmation <original confirmation output> --out <new signals>
```

Keep the original export options (`--rank`, `--start`, `--universe`, `--fundamentals`, `--format`) where applicable. These commands read saved results and do not rerun confirmation or change the confirmation-use ledger. If the original evidence belongs to another horizon, export its matching factor or obtain evidence for the intended horizon under the normal untouched-data protocol. Do not relabel the earlier test.

## Serialization rules

- CSV uses UTF-8, a header, comma delimiters, and standard CSV quoting. Use the literal `\N` (one backslash followed by `N`) for null. Prefix one additional backslash to any non-null string beginning with a backslash; readers reverse that escape after detecting the null token. Thus raw field content `\\N` represents the non-null string `\N`. An empty string remains an empty string. This is an explicit custom null/escape convention; generic CSV readers need a matching adapter.
- Dates use ISO 8601 `YYYY-MM-DD`. Timestamps use RFC 3339 in UTC with a `Z` suffix. Boolean values are `true` or `false` in CSV. Numeric serialization is locale independent; NaN and infinity are rejected. Decimal values use base-10 strings without conversion through float.
- SQLite uses SQL NULL, INTEGER for int64 and booleans (0 or 1), REAL for float64, and TEXT for string, date, timestamp, and decimal. Readers enforce the manifest's logical types rather than relying on SQLite affinity alone.
- Artifact paths are relative to the bundle root and may not escape it. SQLite table names come from validated metadata and must be quoted safely; readers open databases read-only.
- Include units, currency, and feature meanings as optional column metadata where relevant. Provenance must not contain credentials or private access URLs.
- Parquet stores each logical type natively: `string`, `int64`, `float64`, `bool`, `date32`, `timestamp[us, UTC]`, and `decimal128(precision, scale)`. Readers reject a file whose column names or Arrow types differ from the manifest.


## Publication and consumption

Write and validate an artifact in a temporary directory, then publish it atomically on the same filesystem. Never modify a published bundle in place. Consumers reject unsupported contract versions, missing files, schema mismatches, invalid values, and inconsistent row counts with actionable errors.

Preprocessing that learns from data, such as imputation, scaling, feature selection, or dimensionality reduction, belongs in the mining training workflow and must be fitted only on training partitions. Pipeline preprocessing is limited to deterministic cleaning and explicit domain transformations to avoid evaluation leakage.

The Yahoo test adapter validates daily USD US equity/ETF source metadata before declaring `XNYS` and `America/New_York`. Its immutable snapshots use exclusive destination reservation and atomic directory publication. Replay records the original request separately from selected symbols, inclusive date bounds and observed dates; subsets outside the saved request are refused. Strategy evaluation accepts an external daily benchmark only when currency, frequency, price adjustment, calendar and timezone match the market bundle (timezone may be omitted in both). It aligns closes before calculating returns so missing sessions cannot create multi-session observations labeled as daily returns.

## Required compatibility tests

Use shared fixture bundles, independent of either component's code, for CSV and SQLite. Include empty datasets, nulls, empty strings, escaped backslashes, Unicode, decimals, UTC timestamps, duplicate keys, invalid types, and unsupported versions. The producer must generate valid artifacts; the consumer must read valid fixtures and reject invalid ones. A future end-to-end check should publish a pipeline dataset and run mining against that artifact without importing pipeline modules.
