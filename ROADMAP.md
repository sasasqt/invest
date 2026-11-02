# Roadmap

A first end-to-end baseline (M1 and M2) is implemented and tested on synthetic data and has run on test-only Yahoo Finance history, with parts of M3 and M4 already in place. The next goal is credible alpha and portfolio evidence: validation on the historical baseline and an authorized research data source. Yahoo Finance is the test-only data source; the research market and authorized source are still open. See [TODO.md](TODO.md) for actionable work and [the architecture](docs/ARCHITECTURE.md) for ownership and interfaces.

Order work by dependencies and acceptance evidence, rather than calendar promises. Keep the three components independently installable in their own top-level folders. Start with one declared market, instrument universe, bar frequency, and execution convention; broaden support through explicit contracts.

## M0 — Finalize contracts and scope

**Status:** partly done. The dataset contract (CONTRACT-01) is finalized and Yahoo Finance is chosen as a test-only source. The research market and source, artifact and result schemas (CONTRACT-02/03), and compatibility fixtures (CONTRACT-04) remain.

Select the initial market and data source, supported Python version, dependency manager, and minimal runnable use case. Finalize machine-readable schemas for financial datasets, fitted artifacts, signals, strategy configuration, and evaluation reports. Include units, availability/revision times, point-in-time membership, adjustments, calendars, label intervals, provenance, and content identity. Define compatible schema evolution without silently changing dataset contract version 1.

**Acceptance gate:** independent compatibility fixtures cover valid and invalid bundles; decisions and financial timing rules are explicit enough for producers and consumers to implement separately.

## M1 — Establish independent packages and quality checks

**Status:** done except shared contract fixtures (QUALITY-02) and Windows support (BUILD-03). CI runs lint, types, tests, Markdown link checks, independent installs and built-wheel tests. **Depends on:** M0's scope and initial interfaces.

Create `invest_data`, `invest_mining`, and `invest_evaluation` with component manifests, lockfiles, thin entry points, and tests as behavior is introduced. Establish Ruff, mypy, pytest, packaging checks, and CI. Create only modules needed by the first workflow. Add deterministic small fixtures and contract checks that remain effective when assertions are disabled.

**Acceptance gate:** each package installs and passes its relevant checks independently; CI checks all components and documentation links. Actual commands and prerequisites are recorded in the README files.

## M2 — Deliver one correct end-to-end baseline

**Status:** done except external flows and unadjusted corporate actions (EVAL-01); its checkpoint review (REVIEW-10) is still due, and bug hunts found defects that affect it (REVIEW-15 to REVIEW-17, REVIEW-20, REVIEW-21; REVIEW-19 fixed the gross-of-costs returns, REVIEW-13 fixed the `min_price` look-ahead and now refuses bars that are not total-return adjusted, and REVIEW-14 fixed the evaluation reports; REVIEW-18 records low-severity edge cases it left). Runs with one command on synthetic data (FLOW-03) and on test-only Yahoo Finance history from a saved snapshot (DATA-01, FLOW-02; [results](docs/HISTORICAL_BASELINE.md)). The historical run is survivorship-biased, so it checks the workflow, not alpha. **Depends on:** M0 and M1.

Snapshot publication is exclusive and atomic, replay resolves saved dates or explicit subsets, and supported-market and external-benchmark compatibility checks prevent misleading metadata or daily returns (DATA-03). These checks have offline regression coverage; the historical results remain those of the recorded original run.

Reported historical runs are committed as small records without vendor data (FLOW-04, [runs/](runs/yahoo-test/2026-10-07/README.md)). Saving a record requires a complete run and a clean, recorded code revision of the checkout the evaluator was loaded from (REVIEW-06).

Produce a small, deterministic financial dataset in CSV and SQLite; evaluate one known causal formula; export frozen signals; run one declared bucket strategy. Specify event order, eligible fills, fees, cash/position accounting, corporate actions, missing marks, and the selected market's constraints. Save basic metrics, result tables, and figures without rerunning calculations during rendering. Then exercise the same flow on a representative historical dataset.

**Acceptance gate:** golden calculations reconcile equity, external flows, trade P&L, and costs; independent readers agree; future data cannot alter earlier signals; the evaluator runs without mining or download dependencies. Reports disclose supported assumptions and approximations.

## M3 — Complete diagnostics, statistics, and robustness

**Status:** in progress. Implemented: HAC, stationary-bootstrap and PSR/DSR statistics; purged development/confirmation search with a trial ledger and Holm adjustment (STATS-02); a confirmation-use ledger with a reserved, untouched Yahoo window from 2025-01-01 (STATS-03) and one-shot confirmation of a fixed formula on it (STATS-04); factor decile and tail diagnostics and executable decile/tail portfolios with one shared tie rule and small-sample statuses (QUANTILE-01); cost, delay and liquidity stress scenarios; factor confirmation evidence carried through signals into portfolio reports, shown beside a separate rule-based portfolio verdict (REPORT-02, ROBUST-02). Remaining, in the agreed order: the staged bug-hunt fixes (REVIEW-15 to REVIEW-17; REVIEW-18's low-severity edge cases may follow later), the first checkpoint review (REVIEW-10), null-simulation calibration and robustness perturbations, then shared contract fixtures (M0/M1), with REPORT-03 and SCOPE-01 alongside; METRIC-01's remaining metrics are not yet scheduled. **Depends on:** M2's verified accounting and returns.

Implement the [metric specification](strategy-evaluation/METRICS.md), [quantile analysis](docs/QUANTILE_ANALYSIS.md), and [alpha validation protocol](data-mining-framework/ALPHA_VALIDATION.md) incrementally. Add effect sizes, dependence-aware intervals, trial ledgers, multiple-testing control where applicable, temporal confirmation, redundancy checks, and cost/execution stress scenarios. Distinguish undefined or insufficient evidence from rejection and success.

**Acceptance gate:** hand-calculated metric fixtures and statistical calibration checks pass; deciles and overlapping tails follow declared rules; reports separate factor confirmation from executable strategy validation and retain failed/inconclusive trials.

## M4 — Add reproducible mining, training, and frozen inference

**Status:** in progress. A typed causal AST, a random-search baseline and frozen expression-factor inference exist. Remaining: artifact compatibility fixtures, learned preprocessing and models, fitted-artifact inference parity, and matched-budget comparisons. **Depends on:** M3; a fixed formula already works in M2.

Implement typed causal AST operators and a simple search baseline, then learned preprocessing and model fitting inside development splits. Export reloadable fitted artifacts with versioned operator semantics and provenance. Compare subsequent search methods using identical data, objectives, budgets, and evaluation protocols.

**Acceptance gate:** reloaded frozen inference agrees with the original predictor; confirmation data cannot influence fitting or selection; invalid ASTs and numerical domains have declared outcomes. Search experiments include all trials, seeds, and compute budgets.

## M5 — Expand research methods and measured capabilities

**Status:** planned. **Depends on:** M4 and evidence of a specific need.

Use the [literature review](data-mining-framework/LITERATURE_REVIEW.md) to prioritize GP, gradient-assisted AST search, MCTS/exploration policies, and learned generators. Add stateful-policy simulation only after specifying the frozen runtime/portfolio-feedback interface. Add further storage adapters, parallelism, caching, additional markets, or an interactive dashboard when measured scale or usage justifies them.

**Acceptance gate:** each extension preserves public contracts, has independent correctness evidence, and demonstrates value against a baseline. Final claims use frozen prospective evaluation where appropriate; historical tests alone do not resolve pretrained-model knowledge contamination.

## Keeping this plan current

- Mark milestones complete only when their acceptance gates have recorded evidence; link the implementing commit or pull request.
- Close a milestone only after a [checkpoint review](RAPID_DEVELOPMENT.md#11-step-back-between-milestones) of the whole system, or a recorded reason for skipping it.
- Keep actionable checkboxes in [TODO.md](TODO.md), rather than maintaining duplicate task lists here.
- Update the root README's status and next milestone when progress changes, and component READMEs when capabilities or commands change.
- Record scope changes and new dependencies here before presenting them as supported behavior. Do not add dates or performance promises without a basis.
