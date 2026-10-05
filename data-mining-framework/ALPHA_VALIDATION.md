# Alpha robustness and statistical validation

Every mined alpha needs a recorded validation result before promotion to a usable factor library. A high training IC, a small unadjusted p-value, or a good backtest is insufficient on its own.

This document specifies the protocol. Sections 1–4 are implemented in baseline form (`invest_mining/search.py`, `invest_mining/diagnostics.py`); the robustness matrix of section 5 is only partly covered, by strategy-level stress scenarios. Factor diagnostics belong in mining; portfolio and execution checks belong in [strategy evaluation](../data-pipeline/strategy-evaluation/README.md). Both publish independent reports through the [architecture's artifact boundaries](../docs/ARCHITECTURE.md).

## 1. Freeze the experiment before confirmation

Record the dataset version, point-in-time universe, target and holding horizon, signal decision time, operator semantics, fitted transformations, factor orientation, candidate family, baseline, primary metric, minimum useful effect, statistical procedure, and robustness scenarios.

- Choose the sign of the alpha on training data. Do not flip it after inspecting test results or test the absolute IC as if orientation had been fixed in advance.
- Keep a ledger of all proposals, unique evaluated expressions, parameter trials, seeds, combinations, and selection rounds. Equivalent formulas still represent search effort; archive deduplication does not erase that effort.
- Distinguish discovery/selection diagnostics from confirmatory tests. Scores and p-values measured on the data that generated the winning factor are descriptive unless the selection procedure is explicitly accounted for.
- Freeze the confirmatory candidate family before accessing confirmation data. A single prespecified winner can be tested once on a genuinely independent holdout without treating every training-only trial as an additional holdout test. If multiple candidates, horizons, or successive revisions are examined on that holdout, include those tests in the declared family; selecting a winner on reused search data cannot hide the discarded trials.
- Use one prespecified primary endpoint. Treat additional metrics, horizons, and regimes as secondary or exploratory unless their multiplicity is also handled.

There is no universal acceptable IC or Sharpe. Specify practical effect sizes for the market, horizon, costs, and intended use before looking at results.

## 2. Time-aware validation design

Use chronological discovery, selection, and untouched confirmation periods. For model comparison and robustness during development, use nested walk-forward evaluation:

1. Each outer fold has a historical development window followed by a later evaluation window.
2. Mine factors, fit transformations, tune parameters, select candidates, and fit combinations using only the fold's development data, with inner chronological validation where needed.
3. Freeze the selected artifacts and evaluate them on the later outer window.
4. Store each out-of-sample observation once and identify which frozen artifact produced it. Do not report only the best fold or seed.

Purging removes training examples whose **label intervals overlap evaluation intervals**; use actual timestamps, not an assumed number of rows. Apply an embargo when justified by the information timing and sampling design, and record the rule. Historical observations before evaluation may legitimately warm up a causal rolling feature; feature lookback alone is not a reason to discard all prior history.

Outer development evaluations can also become tuning data when repeatedly inspected. Retain a separate final confirmation period or use genuinely prospective paper trading after the design is frozen. A chronological backtest of a model refitted each fold and a fixed factor tested across periods are different experiments; report which was run.

## 3. Factor quality and uncertainty

For each decision date `t`, calculate cross-sectional Pearson IC and Spearman rank IC between available factor values and the specified future returns. Report the daily series, sample size per date, valid-date count, instrument coverage, ties, missingness, and degenerate dates. Constant factors or constant labels yield an undefined correlation; do not silently replace it with zero.

The primary statistical unit for a daily cross-sectional IC analysis is the **date**, not every stock-date row treated as independent. Stocks share market shocks and adjacent dates can share overlapping future returns.

| Question | Recommended method | Required output |
|---|---|---|
| Is the mean out-of-sample IC distinguishable from zero? | Dependence-aware mean test with HAC/Newey–West standard errors on the daily IC series | Signed mean, standard error, test statistic, confidence interval, p-value, and lag-selection rule |
| How stable is the estimated effect? | Moving-block or stationary bootstrap of the daily IC sequence | Confidence interval, block-length rule, number of replications, seed, and block-length sensitivity |
| Does the result survive adverse periods? | Prespecified subperiod/regime diagnostics and chronological folds | Effect sizes and intervals per slice; disclose small samples and multiplicity |
| Is there useful benefit beyond known signals? | Out-of-sample comparison against a frozen baseline or factor combination | Paired daily performance differences with dependence-aware uncertainty, plus incremental effect size |
| Is the signal just a common exposure? | Point-in-time controls and cross-sectional regressions/neutralization under specified rules | Raw and controlled effects, exposures, and uncertainty in date-level slope or spread series |

HAC lag choices must consider label overlap, sampling frequency, and observed dependence. A holding-horizon-based lag is a starting point, not proof that all dependence has been removed. Show sensitivity to plausible lag and block-length choices. HAC asymptotics can be unreliable with few dates; short samples should produce an inconclusive result rather than a confident pass.

Report ICIR with its exact definition. Mean daily IC divided by its standard deviation is a descriptive ratio; annualization is a separate convention and does not turn it into a valid significance test under autocorrelation.

For panel resampling, preserve contemporaneous cross-sectional dependence by resampling complete date blocks together, not individual stock-date rows independently. If uncertainty must include factor-selection or training variability, rerun the relevant fitting/selection steps within the resampling design; bootstrapping a frozen factor's IC only measures uncertainty conditional on that factor.

## 4. Multiple testing and adaptive search

Hypothesis testing should occur on data independent of the search that selected the frozen candidates. Even a sophisticated p-value adjustment cannot repair leakage or arbitrary reuse of the confirmation period.

- **Holm correction** is a suitable default for a small confirmatory family when controlling the chance of any false rejection is important; it supports general dependence when the individual p-values are valid.
- **Benjamini–Hochberg FDR** can be appropriate for a larger library under its dependence assumptions. Correlated factor tests do not automatically satisfy those assumptions.
- **Benjamini–Yekutieli** is a more conservative option for FDR under general dependence. Record the method, family, and assumptions rather than using a blanket “FDR passed” label.
- Resampling-based family tests, **White's Reality Check**, or **Hansen's SPA** can help compare many candidate strategies against a baseline. Their bootstrap must preserve relevant dependence and include the declared comparison family. They do not automatically account for an undocumented adaptive search outside that family.
- **Deflated Sharpe Ratio** and **Probability of Backtest Overfitting** are supplementary portfolio-selection diagnostics. Record trial-count/correlation assumptions for DSR. PBO depends on its partition and selection design and does not replace a chronological holdout.

Report raw p-values, the correction method, adjusted p-values where applicable, declared family size, search counts, and effect-size intervals. A conventional significance level such as 0.05 is a configurable research choice, not an economic threshold. Use one-sided tests only when a direction was specified before confirmation; otherwise use two-sided tests.

## 5. Robustness matrix

Choose scenarios before examining confirmation results. Report degradation relative to the frozen base case, not only the best variant. Some scenarios probe sensitivity rather than represent plausible data-generation processes; label them accordingly.

| Dimension | Checks | Interpretation |
|---|---|---|
| Time | Rolling effects, chronological folds, early/late periods, known market regimes | Identify decay, sign reversals, and dependence on one favorable interval |
| Universe | Different point-in-time universes, sectors, size/liquidity buckets; external market when meaningful | Detect concentration or universe selection; transfer is informative only when inputs and market conventions are comparable |
| Parameters | Nearby lookback windows, lag choices, regularization, and operator thresholds | Prefer a stable region to an isolated best setting; sensitivity variants are not new opportunities to retune the final test |
| Data quality | Documented missing-data scenarios, outliers, plausible vendor revisions, alternate sources | Check whether results depend on fragile preprocessing or a vendor artifact |
| Signal timing | Later publication/execution, stale observations, realistic decision-time cutoffs | Identify signals whose apparent performance requires unavailable information |
| Formula behavior | Domain checks, near-zero denominators, invalid values, warm-up windows, exact versus relaxed evaluation | Reject mathematically unstable or semantically inconsistent candidates |
| Redundancy | Canonical syntax, output correlations, signal clusters, exposures, marginal contribution | Different ASTs need not carry different information; a factor may have little incremental value despite a high standalone score |
| Search instability | Independent seeds, different initialization, frozen search budgets, leave-one-family-out analysis | Report the distribution of discovery outcomes; do not select and report only the best seed |
| Implementation | Independent reference evaluation on small fixtures and reload/export parity | Exclude implementation errors before interpreting statistics |

Use economically plausible measurement perturbations rather than independently adding noise to OHLC fields that destroys their relationships. Decide whether preprocessing is frozen or refitted within each scenario, and preserve the training/evaluation boundary in either case.

Null diagnostics can include dependence-aware, centered bootstrap tests or appropriately constrained randomization. A naive bootstrap of the uncentered observed series approximates sampling uncertainty, not the zero-effect null distribution. Naively shuffling all dates or instruments can destroy the dependence structure the test needs to respect. Artificial null data must not be presented as proof of real-market robustness.

## 6. Trading robustness: evaluated in the separate component

Send frozen factor values or predictions to `data-pipeline/strategy-evaluation/`. Apply a declared strategy and compare with appropriate baseline portfolios.

- Include commissions, spreads/slippage, borrowing costs and constraints, price limits, market calendars, corporate actions, and untradable instruments as appropriate.
- Test base and adverse cost assumptions, execution delays, rebalance schedules, capital/participation levels, and liquidity constraints. Attribute performance to positions and costs.
- Report net P&L, drawdown, turnover, exposures, concentration, net Sharpe, uncertainty, and capacity sensitivity. Dependence and non-normal returns affect inference and Sharpe annualization.
- Keep trading-rule and combination tuning in development periods. A factor whose ranking is significant may still fail after costs; a profitable backtest may still reflect selection bias.
- A factor may be useful only as part of a collection. Evaluate its incremental contribution rather than requiring every constituent to trade profitably on its own.

## 7. Promotion gates and report artifacts

Use explicit states: `discovered`, `screened`, `confirmation_passed`, `rejected`, or `inconclusive`. Record `strategy_validated` separately: factor confirmation does not automatically imply tradability.

Promotion requires:

1. Data timing, causality, schema, and implementation checks pass.
2. Prespecified out-of-sample statistical criteria pass under the declared testing family and assumptions.
3. Effect size meets the prespecified practical requirement; uncertainty and stability are adequate for the intended use.
4. Prespecified robustness scenarios do not reveal a disqualifying failure. Explain tolerable degradation rather than inventing a universal pass percentage.
5. Redundancy and incremental contribution are acceptable for the library or combination.
6. For strategy use, execution-aware portfolio validation passes separately.

When sample size or required metadata is insufficient, emit `inconclusive` with the missing evidence. Do not count skipped checks as passes. An unsuccessful confirmatory result must not be edited into a pass by changing orientation, target horizon, costs, or thresholds; start a new development experiment and use new confirmation evidence.

The factor report should contain:

- Canonical expression, fitted parameters, orientation, and operator version.
- Dataset/version, universe rules, target definition, splits and label intervals.
- Full search/selection ledger references and frozen hypothesis family.
- Daily diagnostics, coverage, uncertainty estimates, test assumptions, raw and adjusted p-values.
- Robustness scenarios, per-scenario effect sizes, failures, and incremental contribution.
- Software/configuration versions, seeds, and status/reasons for every required check.
- Separate strategy-report references where portfolio validation exists.

CSV/SQLite can store daily diagnostics and scenario results; a JSON manifest can record methodology and provenance. These are proposed report artifacts, separate from the existing market dataset contract.

## 8. Implementation plan and meaningful tests

Planned mining modules are `diagnostics/statistics`, `diagnostics/robustness`, and `diagnostics/reports`. They consume frozen factor outputs and metadata; they do not download data or implement order fills. Planned evaluation modules own portfolio statistics and execution stress tests. Dependence-aware primitives may later share a small, explicitly versioned utility package if duplication becomes material; do not couple the three components by importing private modules.

Implement in this order: daily factor diagnostics and causality checks; HAC/bootstrap estimates; frozen candidate-family corrections; scenario evaluation and reports; integration with separate portfolio reports.

Required tests include:

- Hand-calculated Pearson/Spearman examples, ties, missing values, constant inputs, and insufficient sample handling.
- HAC estimates compared with a trusted reference, including zero/positive serial dependence and lag sensitivity.
- Reproducible block sampling that preserves date panels and known synthetic dependence. Simulation checks assess statistical calibration with Monte Carlo uncertainty, rather than asserting that one noisy sample must be significant.
- Holm/BH/BY adjustments compared with trusted implementations on declared families, including missing/invalid p-values. Test assumptions and rejection behavior explicitly.
- Purging of genuinely overlapping label intervals, causal rolling warm-up, and exclusion of future signals.
- Null and planted-signal synthetic experiments to assess false-positive behavior, power, and effect recovery; these validate the implementation, not market profitability.
- A deliberately redundant factor whose incremental benefit vanishes, and a fragile factor that fails a declared perturbation.
- Frozen-artifact evaluation that cannot call search or training and cannot change thresholds based on test results.
- Cross-component fixtures that reconcile supplied signals with hand-calculated portfolio results and costs.

## Reading references

The [literature review](LITERATURE_REVIEW.md) covers AlphaEval, factor-search methods, temporal validation, and statistical pitfalls. Additional methodological references:

- Newey and West, **A Simple, Positive Semi-definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix** (1987): [DOI](https://doi.org/10.2307/1913610).
- Politis and Romano, **The Stationary Bootstrap** (1994): [DOI](https://doi.org/10.1080/01621459.1994.10476870).
- Holm, **A Simple Sequentially Rejective Multiple Test Procedure** (1979): [JSTOR](https://www.jstor.org/stable/4615733).
- Benjamini and Hochberg, **Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing** (1995): [DOI](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x).
- Benjamini and Yekutieli, **The Control of the False Discovery Rate in Multiple Testing under Dependency** (2001): [DOI](https://doi.org/10.1214/aos/1013699998).
- Harvey, Liu, Zhu, **… and the Cross-Section of Expected Returns**: [DOI](https://doi.org/10.1093/rfs/hhv059).
- White, **A Reality Check for Data Snooping**: [DOI](https://doi.org/10.1111/1468-0262.00152).
- Hansen, **A Test for Superior Predictive Ability**: [DOI](https://doi.org/10.1198/073500105000000063).

These methodological citations are a reading list, not a claim of new full-text verification or a guarantee that their assumptions hold for a particular alpha.
