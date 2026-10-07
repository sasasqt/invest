# Backtest summary

## Factor confirmation

Status: **not_confirmed** (the signals carry no factor confirmation evidence).

## Portfolio validation

Status: **inconclusive**, from the declared rules in `config.json` (`validation`), separate from the factor status above.

| check | status | value | threshold |
|---|---|---|---|
| solvency | pass | True | positive wealth throughout |
| net_sharpe_validity | pass | -0.4668 | finite value with status ok |
| sessions | pass | 3769 | >= 252 |
| net_sharpe_ci | fail | [-0.9736, 0.03461] | lower bound > 0 |
| deflated_sharpe | fail | 0.03645 | >= 0.95 |
| stress:costs_x2 | fail | -1.006 | > 0 |
| stress:delay_1 | fail | -0.6458 | > 0 |

## Performance

| metric | value |
|---|---|
| total_return | -58.04% |
| cagr | -5.64% |
| annual_volatility | 11.12% |
| sharpe | -0.467 |
| sortino | -0.656 |
| calmar | -0.091 |
| max_drawdown | 61.76% |
| max_drawdown_duration | 3485 |
| var_loss_95 | 1.11% |
| expected_shortfall_95 | 1.65% |

## Gross Of Costs

| metric | value |
|---|---|
| cagr | 0.50% |
| sharpe | 0.107 |

## Trading

| metric | value |
|---|---|
| total_costs | 657,110.441 |
| cost_drag_annual | 5.91% |
| turnover_one_way_annual | 4397.23% |
| average_gross_exposure | 99.91% |
| rejected_orders | 1 |
| participation_capped_fills | 0 |

## Trades

| metric | value |
|---|---|
| closed_trades | 11720 |
| win_rate | 49.45% |
| payoff_ratio | 0.946 |
| profit_factor | 0.925 |
| average_holding_sessions | 5.743 |

## Benchmark

Benchmark: universe_equal_weight_daily_rebalanced_gross

Aligned daily returns: 3769 of 3769 evaluation sessions. Benchmark total return compounds only those aligned intervals.

| metric | value |
|---|---|
| benchmark_total_return | 1210.01% |
| beta | 0.111 |
| information_ratio | -1.254 |

## External Benchmark

Benchmark: SPY close-to-close (yahoo-test-SPY-2010-01-01-2024-12-31)

Aligned daily returns: 3769 of 3769 evaluation sessions. Benchmark total return compounds only those aligned intervals.

| metric | value |
|---|---|
| benchmark_total_return | 573.91% |
| beta | 0.112 |
| alpha_annual | -6.78% |
| correlation | 0.172 |
| information_ratio | -1.038 |

Sharpe 95% stationary-bootstrap CI: [-0.97, 0.03]
Deflated Sharpe ratio (n_trials=1): 0.036

Figures: `figures/`. Tables: `tables/`. Full metrics: `metrics.json`.
