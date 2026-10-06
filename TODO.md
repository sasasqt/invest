# TODO

This is the actionable backlog for the [roadmap](ROADMAP.md). Unchecked items are planned, not implemented. Items are grouped by milestone; identifiers remain stable when tasks move. Keep detailed formulas and interface rules in their linked specifications.

## Completed documentation foundations

- [x] DOC-01: Document three independent components in three top-level folders and their artifact boundaries ([architecture](docs/ARCHITECTURE.md)).
- [x] DOC-02: Document [Python](PYTHON_GUIDELINES.md), [Git](GIT_GUIDELINES.md), and [design-by-contract](DESIGN_BY_CONTRACT.md) practices.
- [x] DOC-03: Record factor-mining literature and primary-source evidence ([review](data-mining-framework/LITERATURE_REVIEW.md), [catalog](data-mining-framework/PRIMARY_SOURCE_CATALOG.md)).
- [x] DOC-04: Specify [alpha validation](data-mining-framework/ALPHA_VALIDATION.md), [strategy metrics](strategy-evaluation/METRICS.md), [quantiles](docs/QUANTILE_ANALYSIS.md), and [reporting](docs/REPORTING.md).
- [x] DOC-05: Add roadmap, actionable backlog, and README maintenance rules.
- [x] DOC-06: Document [rapid software development practices](RAPID_DEVELOPMENT.md) and link them from development guidance.

## M0 — Contracts and initial scope

- [ ] SCOPE-01: Select the first market, universe, frequency, licensed/authorized data source, and minimum strategy; document exclusions and execution assumptions. *Decided 2026-10-06: Yahoo Finance daily bars as a test-only source (no delisted tickers, no point-in-time membership, adjusted history is revised). The research market, benchmark and authorized source remain open.*
- [x] CONTRACT-01: Finalize financial dataset schema and manifest validation, including keys, units, availability/revision times, membership, adjustments, calendar, missing values, and hashes. *`market_bars`, `universe`, `fundamentals`, `signals` in `invest_data/schemas.py`; [DATA_CONTRACT.md](docs/DATA_CONTRACT.md).*
- [ ] CONTRACT-02: Define fitted artifact and signal schemas, including score/weight/order distinctions, operator versions, training cutoff, horizons, and fitted transforms. *Implemented: `FrozenFactor` artifact v1 (orientation, horizon, training window, dataset hash, operator version; `invest_mining/artifact.py`) and the `signals` kind with `signal_type = score` and optional `n_trials`. Missing: fitted-model/transform artifacts, weight and order signal types, compatibility fixtures.*
- [ ] CONTRACT-03: Define strategy configuration and evaluation result schemas, including fills, positions, equity, external flows, costs, metric statuses, and provenance. *Implemented: validated `BacktestConfig` (`config.py`); runs save the resolved config, daily/trade/episode ledgers, metrics with statuses, and provenance (`reporting.py`). Missing: a versioned machine-readable result schema and external flows.*
- [ ] CONTRACT-04: Define version compatibility/migration rules and independent valid/invalid CSV/SQLite/Parquet fixtures; preserve the documented null/escaping rules in [DATA_CONTRACT.md](docs/DATA_CONTRACT.md).

## M1 — Packages and tooling

- [x] BUILD-01: Declare supported Python and dependency-tool versions; add three component `pyproject.toml` files and reproducible lockfiles. *Python ≥ 3.11, uv workspace with one `uv.lock`; CI installs each component on its own.*
- [x] BUILD-02: Add minimal packages and thin CLI entry points as real behavior is implemented; document installation and command usage. *`invest-data`, `invest-mine`, `invest-eval`; see README.*
- [x] QUALITY-01: Configure Ruff, mypy, pytest, and packaging checks per component; add CI with independent component jobs and Markdown validation. *`.github/workflows/ci.yml`: `checks` (Ruff, mypy, pytest, `scripts/check_markdown_links.py`), `independent-install`, and `wheels` (build, clean install, CLI smoke, tests against installed wheels); link checker tests in `tests/test_markdown_links.py`.*
- [ ] QUALITY-02: Add reusable contract fixtures and meaningful unit/integration checks; verify critical validation with assertions disabled. *Component and end-to-end tests exist; critical boundary validation uses explicit exceptions. Still missing: committed fixture bundles shared by all components.*
- [x] REVIEW-01: Fix PR #1 correctness findings: explicit causal settlement events, decision-time quantiles, validated strategy targets/configuration, consistent excess-return Sharpe statistics, undefined/empty result handling, and metadata validation before publication. *Regression coverage in component tests; README and evaluator event contract updated.*
- [x] REVIEW-02: Preserve loss/drawdown evidence and complete base/stress reports when a settlement makes the portfolio insolvent; handle short-series autocorrelations without numerical warnings. *Regression coverage in evaluator metric and CLI tests.*
- [x] REVIEW-03: Fix [PR #2](https://github.com/sasasqt/invest/pull/2) findings: export follows the development-frozen candidate order without conditioning on confirmation results; heading anchors preserve inline-code text; signal trial counts are validated before publication and on consumption without coercion. *Regression coverage in mining CLI/inference tests, `test_signal_metadata.py`, `test_markdown_links.py` and evaluator CLI tests.*
- [x] REVIEW-04: Re-review the merged workflow and Markdown checks, preserving literal underscores and globally unique heading anchors and recognizing matching code fences. *Regression and repository-link checks in [test_markdown_links.py](tests/test_markdown_links.py); correct the stale component-folder count in DOC-01.*

## M2 — First runnable workflow

- [x] DATA-01: Implement one source adapter with raw snapshot provenance, explicit timeouts, bounded retries, and source-error handling. *Test-only Yahoo Finance adapter (`invest_data/yahoo.py`, `invest-data yahoo download|publish`): immutable raw snapshots with per-file SHA-256 and failures, offline replay with hash checks, rejected-row reports, same snapshot → same `content_sha256`. Offline tests with fabricated responses in `test_yahoo.py`. An authorized research source is still open (SCOPE-01).*
- [x] DATA-02: Implement deterministic cleaning, rejected-row reporting, semantic validation, and atomic CSV/SQLite/Parquet publication.
- [x] DATA-03: Harden Yahoo replay and snapshot publication: exclusive atomic snapshots, interrupted-download cleanup, supported US equity/ETF metadata, explicit date subsets and selection provenance. *Regression tests cover competing writers, unsupported markets and workflow scope overrides.*
- [x] MINE-01: Implement independent readers, one known causal formula, frozen artifact loading, and aligned timestamped signal export.
- [ ] EVAL-01: Specify and implement event order, portfolio state, fill eligibility, fees, external flows, corporate actions, and valuation for the initial market. *Done for adjusted daily bars without external flows (`invest_evaluation/engine.py`); external flows and unadjusted corporate actions remain.*
- [x] EVAL-02: Implement one fixed bucket strategy using supplied signals, with explicit rebalance/holding rules and point-in-time eligibility.
- [x] EVAL-03: Implement basic net P&L, returns, volatility, Sharpe, and drawdown with explicit units and undefined-result statuses.
- [x] REPORT-01: Save resolved configuration, ledgers, metrics, chart inputs, and basic figures under ignored artifacts; render only saved results.
- [x] FLOW-01: Verify CSV/SQLite parity, hand-calculated accounting, invalid-input handling, future-data causality, and artifact-only cross-component integration. *`tests/test_pipeline.py` and component tests.*
- [x] FLOW-03: Run the synthetic workflow with one command and no hand-copied factor ids or dates. *`scripts/synthetic_workflow.sh`; `invest-mine export --from-search`; `invest-eval run` takes `n_trials` from the signals bundle; covered by `tests/test_pipeline.py`.*
- [x] FLOW-02: Run the documented workflow on representative historical data; record data identity, limitations, and reproducibility instructions. *`scripts/historical_workflow.sh` (today's S&P 100, 2010–2024, SPY benchmark, 5-day reversal frozen with `invest-mine freeze`, `n_trials = 1`); results, hashes and limitations in [HISTORICAL_BASELINE.md](docs/HISTORICAL_BASELINE.md); covered offline by `tests/test_pipeline.py`. Survivorship-biased and test-only.*

## M3 — Evaluation completeness and robust alpha evidence

- [ ] METRIC-01: Add remaining applicable trade, portfolio, cash-flow, downside, tail, drawdown, benchmark, exposure, cost, and capacity metrics from the specification. *External benchmark metrics enforce comparable metadata and complete daily intervals, retain provenance and show gaps in saved report inputs. Structured and readable reports show benchmark identity, coverage counts and insufficient-data reasons. Remaining metrics and uncertainty are still open.*
- [ ] QUANTILE-01: Implement deciles and top/bottom 1%, 5%, and 10% diagnostics with tie/missing/small-sample policies; keep partition buckets distinct from overlapping tails. *Implemented for factor diagnostics: per-date deciles (ties share a bucket, dates with fewer names than buckets excluded) and separate top/bottom 1/5/10% tails (`invest_mining/diagnostics.py`, saved by `invest-mine evaluate`). Missing: executable decile and tail portfolios in evaluation, small-sample statuses for tails.*
- [ ] STATS-01: Implement effect sizes and dependence-aware uncertainty with documented HAC/block-bootstrap choices and calibration checks. *HAC tests, stationary bootstrap, PSR/DSR done; calibration across repeated null simulations remains (one null-market search test exists).*
- [x] STATS-02: Implement development/confirmation splits, label-overlap purging, trial ledgers, frozen selection, and applicable multiple-testing procedures. *`invest_mining/search.py` (purge + embargo, full ledger, frozen top-k family, one-shot Holm), Holm/BH in `diagnostics.py`; tests in `test_search_and_inference.py`, `test_diagnostics.py`, `test_cli.py`.*
- [x] STATS-03: Persist experiment identities and confirmation-use history so repeated searches cannot silently reuse the same confirmation period. *`invest_mining/ledger.py` and `invest-mine search --ledger`/`ledger reserve|inspect|check`: append-only JSON Lines ledger with experiment ids, inspections and reserved windows; reused confirmation data is reported `exploratory`, and reserved data is refused outside a confirmation period. [`ledgers/yahoo-test.jsonl`](ledgers/yahoo-test.jsonl) records 2010–2024 as inspected and reserves 2025-01-01 onward. Tests in `test_ledger.py` and `tests/test_pipeline.py`.*
- [ ] STATS-04: Confirm one frozen, pre-registered factor (for example the 5-day reversal from `invest-mine freeze`) once on a reserved window, recording the use in the ledger, so a fixed baseline can use the reserved Yahoo 2025+ window without running a search. *Today only `invest-mine search --confirm-start` confirms on a reservation; `invest-mine evaluate --ledger` refuses reserved data, and without `--ledger` it runs unrecorded.*
- [ ] ROBUST-01: Add time/universe/parameter/data/timing perturbations, redundancy diagnostics, and separate factor outcome statuses. *Implemented: a redundancy filter in family selection and factor confirmation statuses. Missing: regime, universe, parameter, data and timing perturbations.*
- [ ] ROBUST-02: Add base/adverse costs, delays, liquidity/capacity scenarios, and uncertainty for fixed strategies; publish separate portfolio validation outcomes. *Scenarios done (`robustness.py`); a portfolio validation status is not emitted yet.*
- [ ] REPORT-02: Extend saved-result reports with quantile tables, uncertainty, robustness scenarios, and reasons for undefined/inconclusive results. *Implemented: factor reports save quantile and tail tables; strategy reports save statistics, scenarios and undefined-result reasons. Missing: portfolio quantile tables and factor confirmation reported side by side with, but separate from, portfolio validation.*

## M4 — Search, training, and inference

- [ ] AST-01: Implement typed AST grammar, causal operator semantics, lookbacks, numerical-domain policies, and serialization compatibility tests. *Implemented: typed AST with a safe parser, causal operators, `lookback()`, missing-not-infinite domain policy, `OPERATOR_VERSION` checked on artifact load (`expressions.py`, `artifact.py`). Missing: saved-artifact compatibility fixtures across operator versions.*
- [x] SEARCH-01: Add a simple search baseline with objective definition, trial capture, seeds, budgets, duplicate handling, and repeatable experiments.
- [ ] TRAIN-01: Fit learned preprocessing and models only within development splits; persist transforms and configuration with fitted artifacts.
- [ ] INFER-01: Verify frozen export/reload parity, schema compatibility, historical-context requirements, and inference without fitting. *Implemented for expression factors: reload with version and id checks, export without fitting, causal-score tests (`inference.py`, `test_search_and_inference.py`). Missing: parity for fitted models (after TRAIN-01).*
- [ ] COMPARE-01: Establish matched-budget comparisons with locked endpoints and independent confirmation before promoting search methods.

## M5 — Extensions after baseline evidence

- [ ] SEARCH-02: Evaluate GP, differentiable/gradient-assisted AST search, MCTS, and learned generators against the baseline; prioritize using literature evidence and observed bottlenecks.
- [ ] POLICY-01: Specify and test a frozen stateful-policy interface with actual holdings/cash/fill feedback before enabling policy simulation.
- [ ] SCALE-01: Profile representative workloads before adding further storage adapters, parallel execution, or caching; verify correctness and reproducibility of each extension.
- [ ] PRODUCT-01: Assess additional markets and optional dashboard requirements after saved reports satisfy the baseline workflow.

## Updating the backlog and README

For every implementation change:

1. Update affected task states in the same commit and link the relevant implementation/check evidence when marking an item complete. Split partially completed tasks instead of checking them prematurely.
2. Update the root README when project status, next milestone, layout, supported capabilities, or setup commands change. Update affected component READMEs with exact commands and limitations.
3. Update the roadmap if milestone scope, ordering, or acceptance gates change. Keep one authoritative location for each detailed specification.
4. Run the applicable code checks and documentation link/whitespace checks. Record blocked tasks with their dependency and reason; never treat a skipped check as passing.

The root README remains the entry point, the roadmap explains sequencing and acceptance, and this file records actionable progress. Generated runs and reports belong in artifact storage, not in these planning files.
