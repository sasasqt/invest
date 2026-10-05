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
      reports/
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

- Data preparation never imports mining or evaluation code.
- Mining reads dataset artifacts and publishes fitted artifacts and signals. It never imports the downloader or simulator implementation.
- Evaluation reads market datasets and supplied signals, then applies a strategy through a stable strategy interface. It never loads the miner's training loop to run a backtest.
- An external orchestrator can run the stages as commands. Exchange artifacts rather than importing another component's private modules.
- If mining uses portfolio feedback as a search objective, consume separately produced training/validation reports through an adapter. Keep final test reports outside the search loop.

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

## Why this arrangement

Training and inference live together because they must agree on model and feature semantics. Trading rules live with the evaluator because the same rules should work with mined, manually designed, or externally supplied signals. Data production stays independent so either consumer can reuse it.

Strategy evaluation is broader than data processing. If the repository grows, promote `strategy-evaluation/` to a top-level `backtesting/` component. Its independent package and artifact interfaces make that move possible without changing mining or preparation internals. The current layout retains the requested two pipeline subfolders.
