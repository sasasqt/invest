# Data download and preparation pipeline

Component folder: `data-pipeline/` on `main`.

This folder is reserved for a Python pipeline that publishes datasets described by [the dataset contract](../docs/DATA_CONTRACT.md). This document defines scope; executable code has not been added yet.

## Responsibilities

- Download data through source adapters with explicit timeouts, bounded retries, and source-specific configuration.
- Preserve raw inputs separately from derived artifacts for traceability.
- Validate schemas, normalize types and units, handle duplicates and missing values through explicit policies, and apply deterministic domain transformations.
- Export validated, immutable CSV or SQLite bundles with manifests and provenance.
- Report rejected rows and transformation counts. Avoid silent data loss.

## Suggested structure

```text
data-pipeline/src/invest_pipeline/
  domain/        # Source, schema, and transformation models
  sources/       # Download adapters
  transforms/    # Deterministic cleaning and preparation
  writers/       # CSV and SQLite bundle publication
  workflows/     # Download -> validate -> transform -> export
  cli.py         # Thin command entry point
data-pipeline/tests/
  unit/
  integration/
  fixtures/
```

Start with one source adapter and one end-to-end export workflow. Keep source configuration separate from cleaning policies and storage selection. Inject HTTP clients and storage boundaries where needed for testing. Do not import mining code or add model-training dependencies.

Learned transformations belong in mining workflows so fitting respects training partitions. Preserve records and stable identifiers needed by consumers to make their own train/test splits. Document any time-sensitive transformations and their assumptions.

Each component should have its own `pyproject.toml`, dependency lockfile, and tests. Install and validate components independently; neither package depends on the other. The paths above are the planned layout, not implemented files.

## Acceptance checks

Test timeout and retry behavior with controlled HTTP responses, cleaning policies with representative fixtures, repeated runs, failure cleanup, and atomic publication. Verify CSV and SQLite exports preserve the same logical values, including nulls and decimals. A smoke test must turn a fixture source into a valid bundle that an independent contract reader can consume. Follow [Python guidelines](../PYTHON_GUIDELINES.md) for linting, typing, packaging, and test quality.
