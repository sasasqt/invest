# Data mining framework

Component folder: `data-mining-framework/` on `main`.

This folder is reserved for a Python framework that consumes datasets described by [the dataset contract](../docs/DATA_CONTRACT.md). This document defines scope; executable code has not been added yet.

## Responsibilities

- Load CSV and SQLite bundles through input adapters and validate their manifests and data.
- Offer analysis workflows, feature engineering, training, evaluation, and reproducible result export.
- Fit learned preprocessing on training data only, using the same fitted transformations for validation, testing, and inference.
- Record dataset identity, configuration, random seeds, model settings, and metrics with each result.

## Suggested structure

```text
data-mining-framework/src/invest_mining/
  domain/        # Dataset, experiment, and result models
  readers/       # CSV and read-only SQLite adapters
  workflows/     # Analysis, training, and evaluation
  algorithms/    # Implementations added as requirements emerge
  cli.py         # Thin command entry point
data-mining-framework/tests/
  unit/
  integration/
  fixtures/
```

Start with a dataset-reader interface and one representative analysis workflow. Introduce algorithm extension points when a second implementation needs them. Keep algorithm dependencies within this component. No downloader, source credentials, or pipeline imports are required to read a published bundle.

Each component should have its own `pyproject.toml`, dependency lockfile, and tests. Install and validate components independently; neither package depends on the other. The paths above are the planned layout, not implemented files.

## Acceptance checks

Test both storage adapters against independent contract fixtures, invalid-input errors, deterministic analysis, and training/evaluation separation. A smoke test must read a bundle and produce meaningful results. Follow [Python guidelines](../PYTHON_GUIDELINES.md) for linting, typing, packaging, and test quality.
