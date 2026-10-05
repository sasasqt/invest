# Roadmap

A first end-to-end baseline (most of M1 and M2) is implemented and tested on synthetic data. M0's market and data-source decisions are still open. See [TODO.md](TODO.md) for actionable work and [the architecture](docs/ARCHITECTURE.md) for ownership and interfaces.

Order work by dependencies and acceptance evidence, rather than calendar promises. Keep the three components independently installable in their own top-level folders. Start with one declared market, instrument universe, bar frequency, and execution convention; broaden support through explicit contracts.

## M0 — Finalize contracts and scope

**Status:** planned; architecture and behavioral specifications are documented.

Select the initial market and data source, supported Python version, dependency manager, and minimal runnable use case. Finalize machine-readable schemas for financial datasets, fitted artifacts, signals, strategy configuration, and evaluation reports. Include units, availability/revision times, point-in-time membership, adjustments, calendars, label intervals, provenance, and content identity. Define compatible schema evolution without silently changing dataset contract version 1.

**Acceptance gate:** independent compatibility fixtures cover valid and invalid bundles; decisions and financial timing rules are explicit enough for producers and consumers to implement separately.

## M1 — Establish independent packages and quality checks

**Status:** mostly done; Markdown/link checks and wheel builds remain. **Depends on:** M0's scope and initial interfaces.

Create `invest_data`, `invest_mining`, and `invest_evaluation` with component manifests, lockfiles, thin entry points, and tests as behavior is introduced. Establish Ruff, mypy, pytest, packaging checks, and CI. Create only modules needed by the first workflow. Add deterministic small fixtures and contract checks that remain effective when assertions are disabled.

**Acceptance gate:** each package installs and passes its relevant checks independently; CI checks all components and documentation links. Actual commands and prerequisites are recorded in the README files.

## M2 — Deliver one correct end-to-end baseline

**Status:** done on synthetic data; a run on representative historical data (FLOW-02) waits on M0's data-source decision. **Depends on:** M0 and M1.

Produce a small, deterministic financial dataset in CSV and SQLite; evaluate one known causal formula; export frozen signals; run one declared bucket strategy. Specify event order, eligible fills, fees, cash/position accounting, corporate actions, missing marks, and the selected market's constraints. Save basic metrics, result tables, and figures without rerunning calculations during rendering. Then exercise the same flow on a representative historical dataset.

**Acceptance gate:** golden calculations reconcile equity, external flows, trade P&L, and costs; independent readers agree; future data cannot alter earlier signals; the evaluator runs without mining or download dependencies. Reports disclose supported assumptions and approximations.

## M3 — Complete diagnostics, statistics, and robustness

**Status:** planned. **Depends on:** M2's verified accounting and returns.

Implement the [metric specification](strategy-evaluation/METRICS.md), [quantile analysis](docs/QUANTILE_ANALYSIS.md), and [alpha validation protocol](data-mining-framework/ALPHA_VALIDATION.md) incrementally. Add effect sizes, dependence-aware intervals, trial ledgers, multiple-testing control where applicable, temporal confirmation, redundancy checks, and cost/execution stress scenarios. Distinguish undefined or insufficient evidence from rejection and success.

**Acceptance gate:** hand-calculated metric fixtures and statistical calibration checks pass; deciles and overlapping tails follow declared rules; reports separate factor confirmation from executable strategy validation and retain failed/inconclusive trials.

## M4 — Add reproducible mining, training, and frozen inference

**Status:** planned. **Depends on:** M3; a fixed formula already works in M2.

Implement typed causal AST operators and a simple search baseline, then learned preprocessing and model fitting inside development splits. Export reloadable fitted artifacts with versioned operator semantics and provenance. Compare subsequent search methods using identical data, objectives, budgets, and evaluation protocols.

**Acceptance gate:** reloaded frozen inference agrees with the original predictor; confirmation data cannot influence fitting or selection; invalid ASTs and numerical domains have declared outcomes. Search experiments include all trials, seeds, and compute budgets.

## M5 — Expand research methods and measured capabilities

**Status:** planned. **Depends on:** M4 and evidence of a specific need.

Use the [literature review](data-mining-framework/LITERATURE_REVIEW.md) to prioritize GP, gradient-assisted AST search, MCTS/exploration policies, and learned generators. Add stateful-policy simulation only after specifying the frozen runtime/portfolio-feedback interface. Add columnar storage, parallelism, caching, additional markets, or an interactive dashboard when measured scale or usage justifies them.

**Acceptance gate:** each extension preserves public contracts, has independent correctness evidence, and demonstrates value against a baseline. Final claims use frozen prospective evaluation where appropriate; historical tests alone do not resolve pretrained-model knowledge contamination.

## Keeping this plan current

- Mark milestones complete only when their acceptance gates have recorded evidence; link the implementing commit or pull request.
- Keep actionable checkboxes in [TODO.md](TODO.md), rather than maintaining duplicate task lists here.
- Update the root README's status and next milestone when progress changes, and component READMEs when capabilities or commands change.
- Record scope changes and new dependencies here before presenting them as supported behavior. Do not add dates or performance promises without a basis.
