# Data mining framework

Component folder: `data-mining-framework/` on `main`.

This folder is reserved for a Python framework that consumes datasets described by [the dataset contract](../docs/DATA_CONTRACT.md). This document defines scope; executable code has not been added yet.

Read the [factor-mining literature review](LITERATURE_REVIEW.md) for industry-oriented papers, AST and gradient-based methods, exploration versus exploitation, evaluation requirements, and a staged implementation roadmap.

The [primary-source catalog](PRIMARY_SOURCE_CATALOG.md) records the expanded arXiv search, with versioned paper links and evidence limits.

Every mined alpha must follow the [robustness and statistical validation protocol](ALPHA_VALIDATION.md) before promotion. It specifies temporal holdouts, dependence-aware uncertainty, multiple-testing control, stress scenarios, redundancy checks, and report requirements.

Use the shared [quantile analysis](../docs/QUANTILE_ANALYSIS.md) and [reporting/visualization](../docs/REPORTING.md) specifications. Factor diagnostics and portfolio backtests have different meanings even when they display the same signal buckets.

## Responsibilities

- Load CSV and SQLite bundles through input adapters and validate their manifests and data.
- Discover factors and fit models through analysis, feature engineering, training, tuning, and reproducible result export.
- Apply frozen models and preprocessing in inference to publish timestamped signals.
- Evaluate factor and prediction quality; consume separately produced strategy reports when portfolio feedback is needed.
- Fit learned preprocessing on training data only, using the same fitted transformations for validation, testing, and inference.
- Record dataset identity, configuration, random seeds, model settings, and metrics with each result.

## Suggested structure

```text
data-mining-framework/src/invest_mining/
  domain/        # Dataset, experiment, and result models
  readers/       # CSV and read-only SQLite adapters
  expressions/   # Typed factor ASTs and operators
  search/        # Factor-search strategies: GP, RL, MCTS, etc.
  features/      # Shared training/inference feature semantics
  models/        # Model definitions and fitted-artifact loading
  training/      # Fitting, tuning, and model selection
  inference/     # Apply frozen artifacts and publish signals
  diagnostics/   # Factor and prediction quality
  reporting/     # Saved-result reports and plots
  cli.py         # Thin command entry point
data-mining-framework/tests/
  unit/
  integration/
  fixtures/
```

Start with a dataset-reader interface and one representative analysis workflow. Introduce algorithm extension points when a second implementation needs them. Keep algorithm dependencies within this component. No downloader, source credentials, or pipeline imports are required to read a published bundle.

Trading rules, portfolio accounting, and execution simulation belong in [strategy evaluation](../data-pipeline/strategy-evaluation/README.md). Search policies belong here. See the [architecture guide](../docs/ARCHITECTURE.md) for artifact boundaries and the distinction between factor diagnostics and strategy evaluation.

Each component should have its own `pyproject.toml`, dependency lockfile, and tests. Install and validate independently without depending on another component's private modules. Any shared public contract/runtime utility must have an explicit versioned interface. The paths above are planned, not implemented files.

## Acceptance checks

Test both storage adapters against independent contract fixtures, invalid-input errors, deterministic analysis, and training/evaluation separation. A smoke test must read a bundle and produce meaningful results. Follow [Python guidelines](../PYTHON_GUIDELINES.md) for linting, typing, packaging, and test quality.

Implement statistical calibration, causality, and robustness tests from the validation protocol. Factor confirmation and execution-aware strategy validation are separate outcomes; neither may be inferred from training scores alone.
