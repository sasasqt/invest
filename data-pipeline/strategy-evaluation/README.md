# Strategy evaluation

Package `invest_evaluation`. Implemented: a daily event-driven engine (`engine.py`) with explicit event order, next-open fills, participation caps, delisting and halt handling, and exact per-instrument P&L/cost reconciliation; the cost model (commission, half-spread, square-root impact, borrow, cash interest; `config.py`); a quantile long-short/long-only strategy (`strategies.py`); metrics with explicit statuses (`metrics.py`); HAC, stationary-bootstrap, probabilistic and deflated Sharpe statistics (`stats.py`); stress scenarios (`robustness.py`); and saved-result reports and figures (`reporting.py`).

```sh
uv run invest-eval run --data <market bundle> --signals <signals bundle> \
  --config data-pipeline/strategy-evaluation/examples/quantile_long_short.json \
  --n-trials <strategies tried> --out artifacts/eval/<run>
uv run pytest data-pipeline/strategy-evaluation
```

Evaluate supplied trading strategies against versioned market datasets and optional signal artifacts. Own portfolio construction, rebalance rules, simulated execution, costs, risk constraints, and reports.

The [metric specification](METRICS.md) defines trade outcomes, net profit, mean/variance of returns, CAGR, XIRR, annual and downside volatility, Sharpe, Sortino, Calmar, Ulcer Index, tail risk, drawdowns, benchmark performance, costs, and capacity. Implement the full applicable report with explicit calculation conventions and undefined-result statuses.

Follow the shared [quantile analysis](../../docs/QUANTILE_ANALYSIS.md) and [reporting/visualization](../../docs/REPORTING.md) specifications. Bucket diagnostics do not become portfolio returns until allocation, holding periods, and execution are specified.

Trading rules belong in this component's planned `src/invest_evaluation/strategies/` package. A strategy maps information available at a decision time and portfolio state to target positions or orders through a defined interface. The simulation engine owns fill accounting and costs; individual strategies should not duplicate it.

Consume signals from mining, hand-written factors, or external sources through artifacts. Do not import a downloader or model-training loop. A simple baseline strategy may use market data directly. Model fitting and inference belong in `data-mining-framework/`.

Policies that depend on actual portfolio state need the frozen-policy runtime interface described in the [architecture](../../docs/ARCHITECTURE.md). Static signals cannot represent every state-dependent decision policy.

The package has its own `pyproject.toml` and tests and does not depend on mining. See the [architecture](../../docs/ARCHITECTURE.md) and [Python guidelines](../../PYTHON_GUIDELINES.md).

Required validation will cover hand-calculated P&L, execution timing, fees, slippage, rebalance accounting, missing/untradable instruments, and rejection of signals unavailable at decision time. Report performance assumptions alongside results. Keep strategy tuning and final evaluation on separate periods.

Apply the portfolio portion of the [alpha validation protocol](../../data-mining-framework/ALPHA_VALIDATION.md): evaluate frozen signals under base/adverse costs, execution delays, liquidity/capacity constraints, and dependence-aware uncertainty. Return a separate strategy report; statistical factor confirmation alone does not establish tradability.
