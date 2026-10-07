# Data mining framework

Component folder: `data-mining-framework/`. Development branches follow the shared [Git guidelines](../GIT_GUIDELINES.md).

Implementation progress is tracked in the shared [roadmap](../ROADMAP.md) and [TODO list](../TODO.md). A known causal formula and frozen signals come first; automated search and learned models follow verified evaluation and robustness checks.

Package `invest_mining` consumes datasets described by [the dataset contract](../docs/DATA_CONTRACT.md). Implemented: typed causal expressions with a safe parser and versioned operator semantics, point-in-time fundamentals as `fund_<field>` features, and cross-sectional operators restricted to the point-in-time universe (`expressions.py`); IC/rank IC, HAC tests, quantile and tail diagnostics, Holm/BH adjustments (`diagnostics.py`); a random-search baseline with a full trial ledger, purged chronological split, redundancy filter and one-shot Holm-adjusted confirmation (`search.py`); frozen factor artifacts (`artifact.py`); signal export (`inference.py`); and saved-result reports (`reporting.py`). `export --from-search` follows the frozen family's development order (HAC rank-IC t-statistic with redundancy filtering; `--rank` chooses a position) and exports from the first confirmation date, refusing an earlier `--start`. It never filters or ranks on confirmation outcomes, including rejected and inconclusive candidates. Signals record the number of search proposals as a validated positive integer `n_trials`. `search --ledger <file>` records the experiment in a [confirmation-use ledger](../README.md#confirmation-use-ledger) (`ledger.py`) and reports reused confirmation data as `exploratory`; `--confirm-start` starts confirmation on a date, such as a reserved window. `freeze` writes a frozen artifact for one formula specified before looking at the data (no fitting, `--orientation` given explicitly), with `n_trials = 1` and an empty training window; use it for a fixed baseline such as the 5-day reversal. `confirm` tests such a fixed formula once on a confirmation window, such as a reserved one, and records the use in a required ledger; it refuses search-selected factors, which must be confirmed with their family. `export` attaches the factor's confirmation evidence to the signals (`metadata.factor_evidence`: experiment id, confirmation use, outcome, window and statistics) after the factor is chosen: automatically with `--from-search`, and with `--confirmation <search or confirm output>` for `--factor`. It refuses evidence for another factor, experiment or horizon, and never uses it to choose the factor. Evidence v2 includes the tested horizon; v1 signals with evidence must be [re-exported from original results](../docs/DATA_CONTRACT.md#signal-confirmation-evidence) without rerunning confirmation or changing the ledger. Learned models (fitted transforms, ML predictors) and GP/MCTS/RL search are not implemented yet.

Inspect confirmation evidence separately from portfolio results. Choose the replay rank and trading rule before examining confirmation results; choosing them afterward requires a separate untouched period for final portfolio validation.

`confirm` permits a zero-lookback formula such as `close` to start on the dataset's first session; its ledger history is explicitly null. A formula with a positive lookback requires preceding sessions. Empty history never bypasses checks for previously inspected or confirmed dates.

```sh
uv run invest-mine evaluate --data <market bundle> [--universe <bundle>] [--fundamentals <bundle>] \
  --expr "cs_rank(-delta(close, 5))" --out <dir>
uv run invest-mine search --data <market bundle> --trials 200 --seed 0 [--ledger <ledger.jsonl>] \
  [--confirm-start <date>] [--require-confirmatory] --out <dir>
uv run invest-mine ledger reserve|inspect|check --ledger <ledger.jsonl> --start <date> [--end <date>]
uv run invest-mine export --data <market bundle> --from-search <dir> [--rank 1] --out <signals>
uv run invest-mine export --data <market bundle> --factor <dir>/factors/<id>.json [--start <date>] \
  [--confirmation <search or confirm output>] --out <signals>
uv run invest-mine freeze --expr "close / delay(close, 5) - 1" --horizon 5 --orientation -1 --out <factor.json>
uv run invest-mine confirm --data <market bundle> --factor <factor.json> --confirm-start <date> \
  --ledger <ledger.jsonl> [--require-confirmatory] --out <dir>
uv run pytest data-mining-framework
```

Read the [factor-mining literature review](LITERATURE_REVIEW.md) for industry-oriented papers, AST and gradient-based methods, exploration versus exploitation, evaluation requirements, and a staged implementation roadmap.

The [primary-source catalog](PRIMARY_SOURCE_CATALOG.md) records the expanded arXiv search, with versioned paper links and evidence limits.

Every mined alpha must follow the [robustness and statistical validation protocol](ALPHA_VALIDATION.md) before promotion. It specifies temporal holdouts, dependence-aware uncertainty, multiple-testing control, stress scenarios, redundancy checks, and report requirements.

Use the shared [quantile analysis](../docs/QUANTILE_ANALYSIS.md) and [reporting/visualization](../docs/REPORTING.md) specifications. Factor diagnostics and portfolio backtests have different meanings even when they display the same signal buckets.

## Responsibilities

- Load CSV, SQLite and Parquet bundles through the `invest_data` contract readers and validate their manifests and data.
- Discover factors and fit models through analysis, feature engineering, training, tuning, and reproducible result export.
- Apply frozen models and preprocessing in inference to publish timestamped signals.
- Evaluate factor and prediction quality; consume separately produced strategy reports when portfolio feedback is needed.
- Fit learned preprocessing on training data only, using the same fitted transformations for validation, testing, and inference.
- Record dataset identity, configuration, random seeds, model settings, and metrics with each result.

## Suggested structure

```text
data-mining-framework/src/invest_mining/
  domain/        # Dataset, experiment, and result models
  readers/       # Thin wrappers over the invest_data contract readers
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

Each component has its own `pyproject.toml` and tests and installs independently; it depends on `invest-data` only for the public bundle contract. The tree above is the target layout. Today the package is flat modules (`expressions.py`, `diagnostics.py`, `search.py`, `ledger.py`, `artifact.py`, `inference.py`, `reporting.py`, `cli.py`) with tests directly under `tests/`; `domain/`, `features/`, `models/` and `training/` do not exist yet.

## Acceptance checks

Test the storage formats against independent contract fixtures, invalid-input errors, deterministic analysis, and training/evaluation separation. A smoke test must read a bundle and produce meaningful results. Follow [Python guidelines](../PYTHON_GUIDELINES.md) for linting, typing, packaging, and test quality.

Implement statistical calibration, causality, and robustness tests from the validation protocol. Factor confirmation and execution-aware strategy validation are separate outcomes; neither may be inferred from training scores alone.
