# Data preparation

Implementation is planned. See the shared [roadmap](../../ROADMAP.md) and [TODO list](../../TODO.md) for sequencing and progress; the first target is one source and deterministic CSV/SQLite publication.

Download, validate, clean, and deterministically transform data, then publish versioned CSV or SQLite bundles using the [dataset contract](../../docs/DATA_CONTRACT.md).

Keep raw snapshots separate from derived data. Record sources, units, timestamps, transformation policies, rejected rows, and provenance. Use explicit timeouts and bounded retries for external sources, and publish validated bundles atomically.

Learned transformations such as scaling, imputation fitting, and feature selection belong in mining training. This component must not import mining or strategy evaluation code.

The proposed Python package is `invest_data`, with its own `pyproject.toml`, lockfile, and tests. Implementation is pending. See the [architecture](../../docs/ARCHITECTURE.md) and [Python guidelines](../../PYTHON_GUIDELINES.md).

Required validation will cover source failures, cleaning policies, point-in-time metadata, repeatable exports, CSV/SQLite value preservation, and independent contract readers.
