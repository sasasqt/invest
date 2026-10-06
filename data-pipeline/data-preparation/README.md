# Data preparation

Package `invest_data`. Implemented: the v1 bundle contract (`bundle.py`: CSV, read-only SQLite and Parquet, atomic publication, content hashes); the dataset kinds `market_bars`, `universe`, `fundamentals` and `signals` (`schemas.py`); point-in-time helpers for universe membership and as-of fundamentals with revisions (`pit.py`); a deterministic synthetic market with a planted causal effect, listings/delistings, a universe and fundamentals with reporting lags and revisions, plus a local CSV importer (`sources.py`); and deterministic cleaning with a rejected-row report (`cleaning.py`).

```sh
uv run invest-data synthetic --out artifacts/data/synthetic [--format csv|sqlite|parquet] \
  [--universe-out artifacts/data/universe] [--fundamentals-out artifacts/data/fundamentals]
uv run invest-data import-csv bars.csv --out artifacts/data/mine --dataset-id mine \
  --currency USD --calendar XNYS --price-adjustment total_return_adjusted
uv run pytest data-pipeline/data-preparation
```

No vendor download adapter is bundled yet.

Download, validate, clean, and deterministically transform data, then publish versioned CSV or SQLite bundles using the [dataset contract](../../docs/DATA_CONTRACT.md).

Keep raw snapshots separate from derived data. Record sources, units, timestamps, transformation policies, rejected rows, and provenance. Use explicit timeouts and bounded retries for external sources, and publish validated bundles atomically.

Learned transformations such as scaling, imputation fitting, and feature selection belong in mining training. This component must not import mining or strategy evaluation code.

The package has its own `pyproject.toml` and tests. See the [architecture](../../docs/ARCHITECTURE.md) and [Python guidelines](../../PYTHON_GUIDELINES.md).

Required validation will cover source failures, cleaning policies, point-in-time metadata, repeatable exports, CSV/SQLite value preservation, and independent contract readers.
