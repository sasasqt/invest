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

Both commands refuse market bars whose `price_adjustment` is not `total_return_adjusted` or `split_adjusted`, because returns from unadjusted closes count every split as a gain or loss. `execution.min_price` (default 1.0) compares the as-traded close `close_as_traded` on the decision date, since an adjusted close depends on later splits and dividends; with `min_price > 0`, bars without that column are refused before any backtest. Set `min_price` to 0 for such bars, as the historical workflow does for Yahoo data.

`invest-eval quantiles` backtests each bucket portfolio separately with the config's costs, execution, `rebalance_every`, `min_names` and `gross_leverage` (split evenly between legs for long-short); `long_fraction` and `short_fraction` are not used. Decisions with fewer eligible names than `max(min_names, buckets)` hold nothing in every portfolio, as the factor diagnostics do with `invest-mine evaluate --min-cross-section <min_names>`. See the [root README](../README.md#decile-and-tail-portfolios) for the membership and small-sample rules and the saved files. `run_backtest(..., record_decisions=True)` also returns `decisions`: each decision's eligible instruments, scores and target weights (bucket reports use it; it is empty by default).

`--n-trials` sets the number of trials for the deflated Sharpe. It defaults to the signals bundle's optional `n_trials` metadata (written by `invest-mine export`), else 1; the value used is recorded in the run's `manifest.json`. The metadata must be a positive integer; booleans, fractions, strings and null values are rejected. An explicit CLI value overrides valid metadata, but with search evidence it may only add trials: it never goes below the bundle's `n_trials` or the evidence's family size. Search proposal counts describe mining effort; include additional portfolio/rule trials when specifying a count for a broader selection experiment. DSR remains supplementary and does not repair holdout reuse.

`--benchmark` adds an `external_benchmark` metric section (total return, tracking error, information ratio, correlation, beta, alpha) computed from one instrument's close-to-close returns, for example a total-return adjusted SPY bundle. It appears alongside the gross universe equal-weight `benchmark` section. Before backtesting, the CLI requires matching currency, daily frequency, price adjustment, calendar and timezone metadata (timezone may be absent in both bundles); conversions are unsupported. Both market and benchmark metadata, plus the benchmark id, hash and instrument, are saved in `manifest.json`.

`manifest.json` also records `code_revision` and `code_dirty` (uncommitted changes to tracked files) for the Git checkout the evaluator was loaded from, whatever the working directory; both are `null` when Git does not track that code, for example an installed wheel.

Benchmark closes are aligned to the full market session calendar before computing returns, retaining history before the evaluation starts. Missing prices invalidate the missing session and its following return; no forward filling or multi-session return is treated as daily. `tables/daily.csv` saves these gaps. Relative metrics use complete aligned intervals and record both aligned and evaluation session counts. The readable report identifies each benchmark and shows those counts, including an explicit `insufficient_data` reason when fewer than 20 returns align. Benchmark total return compounds this aligned sample, which may differ from the full-period buy-and-hold return. The equity figure omits leading missing history and stops the benchmark growth path at its first internal gap rather than inventing zero returns.

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
| `stress_scenarios` | `["costs_x2", "delay_1"]` | net Sharpe above zero under each named scenario; `not_run` with `--no-scenarios` |
| `benchmark` | `"none"` | `"universe"` or `"external"`: information ratio above zero against that benchmark (`"external"` needs `--benchmark`) |

`supported` needs every check to pass; anything else that is neither `rejected` nor `insufficient_data` is `inconclusive`, and `reasons` lists the checks that did not pass. Setting `stress_scenarios = []` disables the optional stress checks but preserves the mandatory solvency and base-Sharpe checks. Unknown scenario names are refused before the backtest; the available scenarios are `base`, `no_costs`, `costs_x2`, `costs_x3`, `delay_1`, `delay_2`, `participation_1pct` and `capital_x10` (`robustness.py`). `min_sessions` must be at least 60 and `min_deflated_sharpe` at most 1. The verdict covers only the evaluated window and does not read the confirmation-use ledger, so a run on already inspected data is exploratory whatever its status.

Evaluate supplied trading strategies against versioned market datasets and optional signal artifacts. Own portfolio construction, rebalance rules, simulated execution, costs, risk constraints, and reports.

The [metric specification](METRICS.md) defines trade outcomes, net profit, mean/variance of returns, CAGR, XIRR, annual and downside volatility, Sharpe, Sortino, Calmar, Ulcer Index, tail risk, drawdowns, benchmark performance, costs, and capacity. Implement the full applicable report with explicit calculation conventions and undefined-result statuses.

Follow the shared [quantile analysis](../docs/QUANTILE_ANALYSIS.md) and [reporting/visualization](../docs/REPORTING.md) specifications. Bucket diagnostics do not become portfolio returns until allocation, holding periods, and execution are specified; `invest-eval quantiles` specifies them explicitly.

The baseline score-to-weight trading rule is in `src/invest_evaluation/strategies.py`. Targets must be a Series with unique eligible instrument identifiers, finite real weights, and gross exposure within configured leverage. Configuration rejects invalid types, non-finite numbers, invalid timing/windows, and unsupported ranges before simulation. The simulation engine owns fill accounting and costs; individual strategies should not duplicate it.

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
