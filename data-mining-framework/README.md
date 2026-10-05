# Data mining framework

Component folder: `data-mining-framework/`. Development branches follow the shared [Git guidelines](../GIT_GUIDELINES.md).

Implementation progress is tracked in the shared [roadmap](../ROADMAP.md) and [TODO list](../TODO.md). A known causal formula and frozen signals come first; automated search and learned models follow verified evaluation and robustness checks.

Package `invest_mining` consumes datasets described by [the dataset contract](../docs/DATA_CONTRACT.md). Implemented: typed causal expressions with a safe parser and versioned operator semantics (`expressions.py`); IC/rank IC, HAC tests, quantile and tail diagnostics, Holm/BH adjustments (`diagnostics.py`); a random-search baseline with a full trial ledger, purged chronological split, redundancy filter and one-shot Holm-adjusted confirmation (`search.py`); frozen factor artifacts (`artifact.py`); signal export (`inference.py`); and saved-result reports (`reporting.py`). Learned models (fitted transforms, ML predictors) and GP/MCTS/RL search are not implemented yet.

```sh
uv run invest-mine evaluate --data <market bundle> --expr "cs_rank(-delta(close, 5))" --out <dir>
uv run invest-mine search --data <market bundle> --trials 200 --seed 0 --out <dir>
uv run invest-mine export --data <market bundle> --factor <dir>/factors/<id>.json --start <date> --out <signals>
uv run pytest data-mining-framework
```

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

Trading rules, portfolio accounting, and execution simulation belong in [strategy evaluation](../strategy-evaluation/README.md). Search policies belong here. See the [architecture guide](../docs/ARCHITECTURE.md) for artifact boundaries and the distinction between factor diagnostics and strategy evaluation.

Each component has its own `pyproject.toml` and tests and installs independently; it depends on `invest-data` only for the public bundle contract. The tree above is the target layout; `domain/`, `features/`, `models/` and `training/` do not exist yet.

## Acceptance checks

Test both storage adapters against independent contract fixtures, invalid-input errors, deterministic analysis, and training/evaluation separation. A smoke test must read a bundle and produce meaningful results. Follow [Python guidelines](../PYTHON_GUIDELINES.md) for linting, typing, packaging, and test quality.

Implement statistical calibration, causality, and robustness tests from the validation protocol. Factor confirmation and execution-aware strategy validation are separate outcomes; neither may be inferred from training scores alone.
