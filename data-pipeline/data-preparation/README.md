# Data preparation

Package `invest_data`. Implemented: the v1 bundle contract (`bundle.py`: CSV, read-only SQLite and Parquet, atomic publication, content hashes); the dataset kinds `market_bars`, `universe`, `fundamentals` and `signals` (`schemas.py`); point-in-time helpers for universe membership and as-of fundamentals with revisions (`pit.py`); a deterministic synthetic market with a planted causal effect, listings/delistings, a universe and fundamentals with reporting lags and revisions, plus a local CSV importer (`sources.py`); a test-only Yahoo Finance adapter with saved raw snapshots and offline replay (`yahoo.py`); deterministic cleaning with a rejected-row report (`cleaning.py`); and fabricated Yahoo-format responses for tests (`testing.py`).

```sh
uv run invest-data synthetic --out artifacts/data/synthetic [--format csv|sqlite|parquet] \
  [--universe-out artifacts/data/universe] [--fundamentals-out artifacts/data/fundamentals]
uv run invest-data import-csv bars.csv --out artifacts/data/mine --dataset-id mine \
  --currency USD --calendar XNYS --price-adjustment total_return_adjusted
# Test-only Yahoo Finance: save raw responses once, then publish offline from the snapshot.
uv run invest-data yahoo download --snapshot artifacts/yahoo/snap --symbols-file scripts/sp100_members.txt \
  --symbols SPY --start 2010-01-01 --end 2024-12-31 [--timeout 20 --attempts 4 --pause 0.5]
uv run invest-data yahoo publish --snapshot artifacts/yahoo/snap --exclude SPY --dataset-id yahoo-test \
  --out artifacts/yahoo/market [--format parquet] [--universe-note "..."] [--start 2015-01-01 --end 2020-12-31]
uv run pytest data-pipeline/data-preparation
```

Market bars may carry an optional `close_as_traded` column: the close as it traded that session, before later split and dividend adjustments. Evaluation needs it for a minimum-price rule. The synthetic market publishes it (it simulates no corporate actions, so it equals `close`), `import-csv` keeps a `close_as_traded` column when the CSV has one, Cleaning reads a blank or a standard null marker such as `NA` as unknown (null), and nulls any other value that is not a positive number, counting those in the report's `nulled_invalid_values`; the bar itself is kept either way. Yahoo bundles do not have it, because a snapshot cannot undo splits after its window. `--price-adjustment unadjusted` can be published (with a note), but evaluation and mining refuse such bars until corporate actions are modelled; `invest_data.schemas.read_adjusted_market_bars` checks this from the manifest before reading rows.

Signals optionally carry v2 confirmation evidence whose factor identity and tested horizon must match the bundle metadata on publication and read. V1 evidence cannot establish the horizon and is refused; [re-export it from original confirmation results](../../docs/DATA_CONTRACT.md#signal-confirmation-evidence). Signals without evidence remain supported.

### Yahoo Finance (test-only)

Yahoo is for exercising the workflow on real prices, not for research claims: adjusted history is rewritten by the vendor, delisted tickers are absent, and there is no point-in-time membership. So the dataset's identity is the saved raw snapshot, not the vendor:

- `yahoo download` fetches each symbol's daily chart JSON with an explicit timeout and at most `--attempts` tries (network errors, timeouts, HTTP 408, 425, 429, 500, 502, 503 and 504 are retried with capped exponential backoff; other HTTP errors and malformed or error responses are not). It saves the untouched responses and `snapshot.json` (request, retrieval time, per-file SHA-256, and per-symbol failures). It exclusively reserves a new destination and atomically publishes the completed directory; competing writers and all existing paths are refused. Ordinary failures clean the reservation and staging files. A process crash may leave an empty reservation; use a fresh destination after inspecting it.
- `yahoo publish` never touches the network. It verifies every selected file hash, validates supported source metadata, converts timestamps to exchange session dates, scales open/high/low/close by `adjclose / close` (total-return adjusted) and volume inversely (dollar volume preserved), cleans, and publishes with the snapshot recorded in provenance. `--start`/`--end` select an inclusive subset within the original request; omitted dates default to that request. Provenance keeps the original request, selected symbols and bounds, observed dates, and source metadata per instrument. Rejected rows (for example Yahoo's `null` bars) are counted in provenance and written to `<out>.rejected.csv`. The same snapshot and selection publish the same `content_sha256`, whatever the format.
- Publication supports daily USD US equities/ETFs with Yahoo exchange codes `NYQ`, `NMS`, `NGM`, `NCM`, `ASE`, `PCX` or `BTS` and timezone `America/New_York`. Unknown or unsupported source metadata fails before publishing. Metadata records the shared US equity session calendar `XNYS`, the selection rule in `universe`, and a `TEST-ONLY` note; foreign charts are never relabeled as US data.

Keep snapshots under the ignored `artifacts/` directory; never commit vendor data. Tests use fabricated Yahoo-format responses only (`invest_data.testing`).

Download, validate, clean, and deterministically transform data, then publish versioned CSV, SQLite or Parquet bundles using the [dataset contract](../../docs/DATA_CONTRACT.md).

Keep raw snapshots separate from derived data. Record sources, units, timestamps, transformation policies, rejected rows, and provenance. Use explicit timeouts and bounded retries for external sources, and publish validated bundles atomically.

Learned transformations such as scaling, imputation fitting, and feature selection belong in mining training. This component must not import mining or strategy evaluation code.

The package has its own `pyproject.toml` and tests. See the [architecture](../../docs/ARCHITECTURE.md) and [Python guidelines](../../PYTHON_GUIDELINES.md).

Tests cover cleaning policies, point-in-time metadata, repeatable exports, CSV/SQLite/Parquet value preservation, and contract validation. Source-failure handling, competing snapshot writers, interrupted-download cleanup, tamper detection, supported-market validation, date subsets, adjustment and replay hash stability are tested offline in `tests/test_yahoo.py`.
