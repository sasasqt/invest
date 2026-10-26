# Strategy evaluation

Package `invest_evaluation`. Implemented: a daily event-driven engine (`engine.py`) with explicit event order, next-open fills, participation caps, explicit cash delisting settlements, last-known marks for missing bars, and per-instrument P&L/cost reconciliation; the cost model (commission, half-spread, square-root impact, borrow, cash interest; `config.py`); a quantile long-short/long-only strategy with optional point-in-time universe eligibility (`strategies.py`, `engine.py`); executable decile and tail bucket portfolios sharing the factor diagnostics' tie rule (`strategies.py`, `quantiles.py`); metrics with explicit statuses (`metrics.py`); HAC, stationary-bootstrap, probabilistic and deflated Sharpe statistics (`stats.py`); stress scenarios (`robustness.py`); a rule-based portfolio verdict reported beside the factor's confirmation evidence (`validation.py`); and saved-result reports and figures (`reporting.py`).

```sh
uv run invest-eval run --data <market bundle> --signals <signals bundle> [--universe <bundle>] \
  --config strategy-evaluation/examples/quantile_long_short.json \
  [--n-trials <strategies tried>] [--benchmark <market bundle> [--benchmark-instrument SPY]] \
  --out artifacts/eval/<run>
uv run invest-eval quantiles --data <market bundle> --signals <signals bundle> [--universe <bundle>] \
  [--config <BacktestConfig JSON>] [--buckets 10] [--tails 0.01,0.05,0.1] \
  [--min-names-per-bucket 5] --out artifacts/eval/<run>-quantiles
uv run pytest strategy-evaluation
```

Both commands refuse market bars whose `price_adjustment` is not `total_return_adjusted`: returns from unadjusted closes count every split as a gain or loss, and returns from split-adjusted closes drop dividends. `execution.min_price` (default 1.0) compares the as-traded close `close_as_traded` on the decision date, since an adjusted close depends on later splits and dividends; a name with a null as-traded close that day is not eligible, and the run's warnings count such exclusions. With `min_price > 0`, bars without that column are refused before any backtest, and `run_backtest` refuses an evaluation window with no known as-traded close before it simulates. `run_backtest` takes frames without their manifest, so callers that bypass the CLI check the adjustment themselves, for example with `read_adjusted_market_bars`. Set `min_price` to 0 for such bars, as the historical workflow does for Yahoo data.

Both commands refuse an `--out` that exists and is not an empty directory, or that cannot be created (for example under a file), before they read any input or run a backtest. An unreadable or invalid input (`--data`, `--signals`, `--universe`, `--benchmark` or its instrument, `--config`, `--delistings`, including a malformed bundle manifest) ends with a message rather than a traceback, and nothing is written; read and parse errors name the option. `--benchmark-instrument` without `--benchmark` is refused. Output checks use a filesystem creation probe when `os.pathconf` is unavailable, avoiding a Unix-only requirement. Delisting JSON must contain a list of objects with exactly `date`, `instrument` and `settlement_price`; each instrument must be a nonempty string. Invalid records name their event number and are refused before backtesting, and the engine validates instrument types for Python callers as well.

`invest-eval quantiles` backtests each bucket portfolio separately with the config's costs, execution, `rebalance_every`, `min_names` and `gross_leverage` (split evenly between legs for long-short); `long_fraction` and `short_fraction` are not used. Decisions with fewer eligible names than `max(min_names, buckets)` hold nothing in every portfolio, as the factor diagnostics do with `invest-mine evaluate --min-cross-section <min_names>`. See the [root README](../README.md#decile-and-tail-portfolios) for the membership and small-sample rules and the saved files. `run_backtest(..., record_decisions=True)` also returns `decisions`: each decision's eligible instruments, scores and target weights (bucket reports use it; it is empty by default).

`--n-trials` sets the number of trials for the deflated Sharpe. It defaults to the signals bundle's optional `n_trials` metadata (written by `invest-mine export`), else 1; the value used is recorded in the run's `manifest.json`. The metadata must be a positive integer; booleans, fractions, strings and null values are rejected. An explicit CLI value overrides valid metadata, but with search evidence it may only add trials: it never goes below the bundle's `n_trials` or the evidence's family size. Search proposal counts describe mining effort; include additional portfolio/rule trials when specifying a count for a broader selection experiment. DSR remains supplementary and does not repair holdout reuse.

`--benchmark` adds an `external_benchmark` metric section (total return, tracking error, information ratio, correlation, beta, alpha) computed from one instrument's close-to-close returns, for example a total-return adjusted SPY bundle. It appears alongside the gross universe equal-weight `benchmark` section. Before backtesting, the CLI requires matching currency, daily frequency, price adjustment, calendar and timezone metadata (timezone may be absent in both bundles); conversions are unsupported. Both market and benchmark metadata, plus the benchmark id, hash and instrument, are saved in `manifest.json`.

`manifest.json` also records `code_revision` and `code_dirty` (uncommitted changes to tracked files) for the Git checkout the evaluator was loaded from, whatever the working directory; both are `null` when Git does not track that code, for example an installed wheel.

Benchmark closes are aligned to the full market session calendar before computing returns, retaining history before the evaluation starts. Missing prices invalidate the missing session and its following return; no forward filling or multi-session return is treated as daily. `tables/daily.csv` saves these gaps. Relative metrics use complete aligned intervals and record both aligned and evaluation session counts. The readable report identifies each benchmark and shows those counts, including an explicit `insufficient_data` reason when fewer than 20 returns align. Benchmark total return compounds this aligned sample, which may differ from the full-period buy-and-hold return. The equity figure omits leading missing history and stops the benchmark growth path at its first internal gap rather than inventing zero returns. The universe equal-weight benchmark is likewise missing, not 0%, on a session where no name held in the universe has a return, and its metrics drop that session.

Figures and reports plot only saved values and never draw a missing value as zero: the rolling 6-month Sharpe uses excess returns over `risk_free_annual`, like the reported Sharpe; a stress scenario without a Sharpe has no bar and is labelled with its reason (for example `insolvent 2023-10-16`), and a decile portfolio without a CAGR is labelled with its reason (for example `insolvent_wealth_path`) or else its status; the quantile figure names each long-short portfolio it leaves out with its own status, and the quantile report shows each status with its reason. `tables/scenarios.csv` records `sharpe_reason` and the first `insolvency` date for each scenario, and the verdict table in `report.md` shows each check's detail.

The baseline `QuantileStrategy` holds the largest `k` names with `k / n ≤ long_fraction` (and likewise for `short_fraction`), the bucket portfolios' cutpoint rule; `floor(n × fraction)` would give 28 rather than 29 names for 29% of 100.

## Factor and portfolio verdicts

Each run writes `verdict.json` (`verdict_version = 2`) with two separate sections, also shown as two sections at the top of `report.md`. Version 2 adds mandatory solvency and base-Sharpe validity checks. Previously saved v1 reports remain renderable; rerun their evaluation to obtain the corrected verdict.

- `factor`: the signals bundle's v2 `factor_evidence` metadata copied unchanged (experiment id, tested horizon, confirmation use, test outcome, status, window and statistics), or `status = not_confirmed` when the signals carry none. Evaluation never recomputes or changes it. V1 evidence has no tested horizon and must be re-exported from the original confirmation output; see the [data contract](../docs/DATA_CONTRACT.md#signal-confirmation-evidence).
- `portfolio`: `supported`, `rejected`, `inconclusive` or `insufficient_data`, from the config's `validation` rules, with one saved check (`pass`, `fail`, `undefined` or `not_run`) per rule and the evaluated window.

| rule (`validation` key) | default | check |
|---|---|---|
| (always) | | solvency: finite net returns and positive wealth throughout; known insolvency gives `rejected`, even with too few sessions or missing statistics |
| (always) | | base net Sharpe: finite value and `status = ok`; invalid, undefined or missing values cannot support a portfolio |
| `min_sessions` | 252 | daily net returns in the run; fewer gives `insufficient_data` |
| (always) | | net excess Sharpe stationary-bootstrap interval: lower bound above zero; upper bound below zero gives `rejected`; undefined gives `insufficient_data` |
| `min_deflated_sharpe` | 0.95 | deflated Sharpe ratio with the run's `n_trials` |
| `stress_scenarios` | `["costs_x2", "delay_1"]` | net Sharpe above zero under each named scenario; a scenario that loses all capital `fail`s with its first insolvent session, an undefined Sharpe is `undefined` with its reason, and `--no-scenarios` gives `not_run` |
| `benchmark` | `"none"` | `"universe"` or `"external"`: information ratio above zero against that benchmark (`"external"` needs `--benchmark`); fewer than 20 aligned returns give `undefined` with that reason |

`supported` needs every check to pass; anything else that is neither `rejected` nor `insufficient_data` is `inconclusive`, and `reasons` lists the checks that did not pass. Setting `stress_scenarios = []` disables the optional stress checks but preserves the mandatory solvency and base-Sharpe checks. Unknown scenario names are refused before the backtest; the available scenarios are `base`, `no_costs`, `costs_x2`, `costs_x3`, `delay_1`, `delay_2`, `participation_1pct` and `capital_x10` (`robustness.py`). `min_sessions` must be at least 60 and `min_deflated_sharpe` at most 1. The verdict covers only the evaluated window and does not read the confirmation-use ledger, so a run on already inspected data is exploratory whatever its status.

Evaluate supplied trading strategies against versioned market datasets and optional signal artifacts. Own portfolio construction, rebalance rules, simulated execution, costs, risk constraints, and reports.

The [metric specification](METRICS.md) defines trade outcomes, net profit, mean/variance of returns, CAGR, XIRR, annual and downside volatility, Sharpe, Sortino, Calmar, Ulcer Index, tail risk, drawdowns, benchmark performance, costs, and capacity. Implement the full applicable report with explicit calculation conventions and undefined-result statuses.

Follow the shared [quantile analysis](../docs/QUANTILE_ANALYSIS.md) and [reporting/visualization](../docs/REPORTING.md) specifications. Bucket diagnostics do not become portfolio returns until allocation, holding periods, and execution are specified; `invest-eval quantiles` specifies them explicitly.

The baseline score-to-weight trading rule is in `src/invest_evaluation/strategies.py`. Targets must be a Series with unique eligible instrument identifiers, finite real weights, and gross exposure within configured leverage. A name is eligible on a decision date when it has a finite score and a close, is a universe member (with `--universe`), has not been settled by a delisting event, passes `execution.min_price`, and has both trailing estimates the fill's costs need: an ADV above `execution.min_adv_dollar` over `costs.adv_window` bars and a volatility over `costs.vol_window` daily returns. A missing bar interrupts both windows, so the name is ineligible until they are complete again; a held name is then sold at the next rebalance, with the bars and daily returns its windows still hold setting the sale's costs and participation cap. The sale is rejected when the fill date has no bar, or when those windows hold no traded volume or fewer than two daily returns: after a halt, after zero volume, or for a few sessions after a single missing bar when `costs.vol_window` is below 4 (REVIEW-27). The participation cap can make it partial. Configuration rejects invalid types, non-finite numbers, invalid timing/windows, and unsupported ranges before simulation. The simulation engine owns fill accounting and costs; individual strategies should not duplicate it.

Consume signals from mining, hand-written factors, or external sources through artifacts. Do not import a downloader or model-training loop. A simple baseline strategy may use market data directly. Model fitting and inference belong in `data-mining-framework/`.

Policies that depend on actual portfolio state need the frozen-policy runtime interface described in the [architecture](../docs/ARCHITECTURE.md). Static signals cannot represent every state-dependent decision policy.

The package has its own `pyproject.toml` and tests and does not depend on mining. See the [architecture](../docs/ARCHITECTURE.md) and [Python guidelines](../PYTHON_GUIDELINES.md).

Tests cover hand-calculated P&L, execution timing, fees, slippage, rebalance accounting, missing/untradable instruments, delisting settlements, and rejection of signals unavailable at decision time (`tests/test_engine.py`), configuration validation (`tests/test_config.py`), plus metrics, statistics, benchmarks and the CLI (`tests/test_metrics.py`, `tests/test_stats_and_cli.py`), bucket portfolios (`tests/test_quantiles.py`) and the portfolio verdict (`tests/test_validation.py`). Report performance assumptions alongside results. Keep strategy tuning and final evaluation on separate periods.

Apply the portfolio portion of the [alpha validation protocol](../data-mining-framework/ALPHA_VALIDATION.md): evaluate frozen signals under base/adverse costs, execution delays, liquidity/capacity constraints, and dependence-aware uncertainty. Return a separate strategy report; statistical factor confirmation alone does not establish tradability.

## Delisting settlements

Pass `--delistings events.json` to the CLI or a `delistings` DataFrame to `run_backtest`. The JSON file is a list of records:

```json
[
  {"date": "2024-01-05", "instrument": "A", "settlement_price": 8.0}
]
```

Each record describes a cash settlement known at that date's close. Prices are finite and nonnegative (zero supports a worthless holding); identifiers and dates must match the market data/calendar. Do not backdate an event to a final bar if the settlement became known later. The engine marks holdings to the settlement price, reconciles P&L, converts them to cash, and prevents later purchases. Events are included in report provenance and applied identically to stress scenarios. One settlement per instrument is supported; relisting and separate settlement fees are outside this baseline.

Absent an event, missing bars retain the last known mark with a warning. This preserves causality but can leave stale valuations: supplying reliable settlement data is required for credible historical delisting performance.

Sharpe confidence intervals, PSR, and DSR use excess returns under the same configured annual risk-free conversion as the performance metric. Mean-return HAC tests and annual-mean bootstrap intervals describe raw returns. Flat portfolios retain explicit undefined Sharpe statuses and can be reported normally.
