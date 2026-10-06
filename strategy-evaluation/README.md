# Strategy evaluation

Package `invest_evaluation`. Implemented: a daily event-driven engine (`engine.py`) with explicit event order, next-open fills, participation caps, explicit cash delisting settlements, last-known marks for missing bars, and per-instrument P&L/cost reconciliation; the cost model (commission, half-spread, square-root impact, borrow, cash interest; `config.py`); a quantile long-short/long-only strategy with optional point-in-time universe eligibility (`strategies.py`, `engine.py`); metrics with explicit statuses (`metrics.py`); HAC, stationary-bootstrap, probabilistic and deflated Sharpe statistics (`stats.py`); stress scenarios (`robustness.py`); and saved-result reports and figures (`reporting.py`).

```sh
uv run invest-eval run --data <market bundle> --signals <signals bundle> [--universe <bundle>] \
  --config strategy-evaluation/examples/quantile_long_short.json \
  [--n-trials <strategies tried>] --out artifacts/eval/<run>
uv run pytest strategy-evaluation
```

`--n-trials` sets the number of trials for the deflated Sharpe. It defaults to the signals bundle's optional `n_trials` metadata (written by `invest-mine export`), else 1; the value used is recorded in the run's `manifest.json`.

Evaluate supplied trading strategies against versioned market datasets and optional signal artifacts. Own portfolio construction, rebalance rules, simulated execution, costs, risk constraints, and reports.

The [metric specification](METRICS.md) defines trade outcomes, net profit, mean/variance of returns, CAGR, XIRR, annual and downside volatility, Sharpe, Sortino, Calmar, Ulcer Index, tail risk, drawdowns, benchmark performance, costs, and capacity. Implement the full applicable report with explicit calculation conventions and undefined-result statuses.

Follow the shared [quantile analysis](../docs/QUANTILE_ANALYSIS.md) and [reporting/visualization](../docs/REPORTING.md) specifications. Bucket diagnostics do not become portfolio returns until allocation, holding periods, and execution are specified.

The baseline score-to-weight trading rule is in `src/invest_evaluation/strategies.py`. Targets must be a Series with unique eligible instrument identifiers, finite real weights, and gross exposure within configured leverage. Configuration rejects invalid types, non-finite numbers, invalid timing/windows, and unsupported ranges before simulation. The simulation engine owns fill accounting and costs; individual strategies should not duplicate it.

Consume signals from mining, hand-written factors, or external sources through artifacts. Do not import a downloader or model-training loop. A simple baseline strategy may use market data directly. Model fitting and inference belong in `data-mining-framework/`.

Policies that depend on actual portfolio state need the frozen-policy runtime interface described in the [architecture](../docs/ARCHITECTURE.md). Static signals cannot represent every state-dependent decision policy.

The package has its own `pyproject.toml` and tests and does not depend on mining. See the [architecture](../docs/ARCHITECTURE.md) and [Python guidelines](../PYTHON_GUIDELINES.md).

Required validation will cover hand-calculated P&L, execution timing, fees, slippage, rebalance accounting, missing/untradable instruments, and rejection of signals unavailable at decision time. Report performance assumptions alongside results. Keep strategy tuning and final evaluation on separate periods.

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
