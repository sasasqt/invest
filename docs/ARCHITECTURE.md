# Component arrangement

The repository has two top-level folders and three independent logical components. Data preparation and strategy evaluation share the `data-pipeline/` parent, but have separate packages, dependencies, and tests. Model discovery, training, and inference belong in `data-mining-framework/`.

The component folders and scope documents exist. Python packages, commands, and tests below are planned, not implemented.

## Layout

```text
data-pipeline/
  data-preparation/
    README.md
    pyproject.toml                 # Planned independent package
    src/invest_data/
      sources/
      cleaning/
      transforms/                 # Deterministic transformations
      writers/
    tests/
  strategy-evaluation/
    README.md
    pyproject.toml                 # Planned independent package
    src/invest_evaluation/
      readers/
      strategies/                 # Trading and portfolio rules
      backtesting/
      execution/                  # Simulated fills and costs
      metrics/
      reporting/                  # Report assembly and plots
    tests/
data-mining-framework/
  README.md
  pyproject.toml                   # Planned independent package
  src/invest_mining/
    readers/
    expressions/                  # Factor ASTs and operators
    search/                       # GP, RL, MCTS, etc.
    features/
    models/
    training/
    inference/
    diagnostics/                  # Factor/prediction quality
    reporting/                    # Report assembly and plots
  tests/
docs/
  DATA_CONTRACT.md
  ARCHITECTURE.md
```

Create Python modules when implementing their responsibilities; do not populate this entire tree with empty modules. Give each of the three packages its own development tools and dependency lockfile. The parent pipeline folder is an organizational container, not a package that couples its children.

## Where each responsibility belongs

| Responsibility | Owner | Reason |
|---|---|---|
| Downloading, raw snapshots, schema validation, deterministic cleaning | Data preparation | Reusable data production independent of any model or strategy |
| Learned imputation, scaling, feature selection, dimensionality reduction | Mining training | Must fit within the training partition and be frozen for inference |
| Formula operators, factor search, search policies, factor combination fitting | Mining | These discover or learn signals |
| Model training, tuning, model selection, checkpoints | Mining training | Reproducible learning workflow with explicit data splits |
| Applying frozen formulas/models and fitted transforms | Mining inference | Training and inference share feature definitions and artifact-loading code |
| Signal-to-position rules, rebalance schedules, risk limits | Strategy evaluation's `strategies/` | These define how a signal becomes a portfolio |
| Order/fill simulation, fees, slippage, borrowing, account state | Strategy evaluation | A common engine evaluates supplied strategies consistently |
| IC, rank IC, feature coverage, prediction loss | Mining diagnostics | Measure signal or model quality |
| Factor uncertainty, multiple testing, stability, redundancy, perturbation robustness | Mining diagnostics | Confirm mined signals beyond their discovery scores |
| Net P&L, portfolio Sharpe, drawdown, turnover, exposures, capacity | Strategy evaluation | Measure strategy performance after construction and execution |
| Portfolio uncertainty and cost/execution stress tests | Strategy evaluation | Assess robustness of a fixed trading strategy |

“Strategy” is ambiguous. **Search strategies** such as GP, MCTS, or exploration policies belong in mining's `search/`. **Trading strategies** such as top-k selection, momentum portfolios, rebalancing, and sizing belong in evaluation's `strategies/`. A trained decision policy is learned in mining and exported through inference; simulation of its decisions belongs in evaluation.

## Data flow and dependency boundaries

```text
data preparation -> versioned market dataset -> mining training
                                                 |
                                        frozen model/factor artifacts
                                                 |
market dataset --------------------------> mining inference
                                                 |
                                          timestamped signals
                                                 |
market dataset + signals + strategy config -> strategy evaluation -> reports
```

Simple hand-written strategies may read the market dataset directly, without a mining stage. Evaluation accepts supplied strategies and signals; it does not require the miner or downloader to run.

Factor diagnostics should likewise accept supplied factor values and metadata without invoking search or training. This enables identical checks for mined, hand-written, and externally supplied alphas. Missing timing/provenance evidence limits the claims a report can make even when numerical statistics can be calculated.

- Data preparation never imports mining or evaluation code.
- Mining reads dataset artifacts and publishes fitted artifacts and signals. It never imports the downloader or simulator implementation.
- Evaluation reads market datasets and supplied signals, then applies a strategy through a stable strategy interface. It never loads the miner's training loop to run a backtest.
- An external orchestrator can run the stages as commands. Exchange artifacts rather than importing another component's private modules.
- A decoupled workflow may reuse an explicitly versioned public contract/runtime utility. Avoid shared training state, hidden mutable caches, and dependencies on another component's private modules; duplicating mathematical or schema logic is not itself a goal.
- If mining uses portfolio feedback as a search objective, consume separately produced training/validation reports through an adapter. Keep final test reports outside the search loop.

### Stateful policies need simulator feedback

Precomputed timestamped signals work for factors/predictors driven only by available market inputs. They are not a complete interface for a learned policy that depends on holdings, cash, previous fills, or recurrent state.

For such policies, define a narrow frozen-policy runtime interface: available observations plus simulator portfolio state in, target positions/orders plus updated policy state out. The simulator owns fills, cash, and execution timing and passes actual outcomes back to the policy. Training and search remain outside evaluation. The inference bridge and its dependency/serialization contract must be specified before supporting this workflow; do not replay orders precomputed under a different portfolio state as if they were an equivalent policy backtest.

## Contracts to implement

The existing [dataset contract](DATA_CONTRACT.md) describes CSV/SQLite exchange. Additional contracts below are proposals; they do not alter version 1 silently.

1. **Financial dataset metadata:** instrument keys, event and availability times, trading calendar, units, adjustments, and universe policy.
2. **Fitted artifact metadata:** model/factor version, input schema, operator version, fitted preprocessing, training cutoff, label horizon, configuration, and provenance. Inference must apply the same fitted transformations used in training.
3. **Signal output:** instrument, decision timestamp, availability timestamp, signal value, intended horizon, and model/factor version. Specify whether a value is a score, target weight, or order instruction; they are different interfaces.
4. **Strategy input:** strategy identifier and version, parameters, dataset/signal references, rebalance rules, initial capital, and execution assumptions. Use a common interface for hand-written strategies and exported learned-policy outputs.
5. **Evaluation output:** resolved configuration, dataset and signal versions, trades, positions, costs, equity curve, metrics, and validation warnings.

## Testing the separation

- Data preparation tests should produce bundles that independent readers can validate without installing mining dependencies.
- Mining tests should train on a fixture, reload the fitted artifact, and confirm inference agrees with the frozen training predictor. Test causal features, split boundaries, and exact expression semantics.
- Evaluation tests should use supplied fixture signals without installing mining. Check a hand-calculated P&L example, fees, fill timing, rebalancing, missing signals, and future-signal rejection.
- A cross-component integration test should exchange artifacts through each published boundary. It must not substitute direct imports for the intended interface.
- Strategy/parameter tuning uses training or designated validation periods. Final evaluation freezes data versions, strategy rules, models, and assumptions before the test period is examined.

Every mined alpha follows the [validation protocol](../data-mining-framework/ALPHA_VALIDATION.md). Mining publishes factor evidence; evaluation publishes portfolio evidence. Track statistical confirmation and strategy validation separately, including rejected and inconclusive outcomes.

[Quantile analysis](QUANTILE_ANALYSIS.md) specifies signal buckets and their distinct factor/portfolio interpretations. [Reporting](REPORTING.md) defines plot ownership, reproducible chart inputs, and generated artifact locations.

## Prerequisites and first implementation milestone

The current repository is a design and research collection, not a functioning framework. Before adding multiple miners or a dashboard:

1. Finalize machine-validated schemas and compatibility fixtures for financial datasets, fitted artifacts, signals, and reports. Specify availability/revision times, point-in-time membership, price adjustment/total-return rules, labels and horizons, keys, units, calendars, and content hashes. The generic CSV/SQLite contract alone does not encode this financial information.
2. Establish a supported Python version, the three package manifests/lockfiles, component test commands, and CI. Add public interfaces and modules as needed by a runnable use case rather than creating the whole proposed directory tree at once.
3. Define simulation event order: observation availability, decision, order submission, eligible fill, settlement/cash update, corporate actions, and valuation. Define partial fills, price limits, missing marks, delistings, shorting, and financing for the selected market. An OHLC bar does not reveal intrabar event order; disclose the fill approximation.
4. Implement one complete flow: a deterministic small dataset, one known formula, frozen signals, one declared bucket strategy, reconciled portfolio/trade accounting, basic metrics, and saved figures. Use golden fixtures plus causal/contract tests; then run a representative historical dataset.
5. Add dependence-aware statistics, multiple-testing protocols, robustness scenarios, and metric families incrementally once the underlying returns and accounting are verified. Persist all trials and scenario outcomes.
6. Only then compare GP, gradient-assisted search, and learned generators under matched budgets. Retain prospective frozen evaluation for final research claims; historical splits do not eliminate potential knowledge contamination from modern pretrained LLMs.

CSV and SQLite are sensible initial interchange formats. If panel scale makes them a bottleneck, add a versioned Parquet or other columnar adapter after measuring it. Do not require a database server or replace formats solely because the architecture is extensible.

## Why this arrangement

Training and inference live together because they must agree on model and feature semantics. Trading rules live with the evaluator because the same rules should work with mined, manually designed, or externally supplied signals. Data production stays independent so either consumer can reuse it.

Strategy evaluation is broader than data processing. If the repository grows, promote `strategy-evaluation/` to a top-level `backtesting/` component. Its independent package and artifact interfaces make that move possible without changing mining or preparation internals. The current layout retains the requested two pipeline subfolders.
