# Strategy evaluation metrics

Implement the following metric families in `invest_evaluation/metrics.py`. Return the full applicable report, not just Sharpe or win rate. The core of sections 1–6 and 8–9 is implemented (`invest_evaluation/metrics.py`); XIRR, rolling/calendar tables, MAE/MFE and conditional drawdown at risk are not yet.

Metrics describe an evaluated strategy under declared data, trading, cost, and cash-flow assumptions. They do not establish statistical robustness by themselves; apply the [validation protocol](../data-mining-framework/ALPHA_VALIDATION.md) separately.

## 1. Accounting and conventions

The report must specify base currency, timezone, valuation frequency, period start/end, trading calendar, annualization factor, return type, risk-free series, minimum acceptable return (MAR), benchmark, transaction-cost model, position accounting, trade-matching method, missing-price policy, and external cash-flow timing.

- Use **simple periodic portfolio returns** for the default metrics below. Label log-return metrics separately. Never average trade returns as a substitute for portfolio returns.
- For daily observations, an annualization factor such as 252 is a declared convention, not a universal constant. Use a calendar appropriate to the market and sampling frequency. Resample irregular observations or use an explicitly time-aware method; do not apply daily formulas to irregular timestamps.
- Use sample variance and sample standard deviation (`ddof=1`) for return dispersion unless a metric explicitly says otherwise. Fewer than two returns cannot establish variance.
- Derive returns and drawdowns from a **cash-flow-adjusted unit NAV/wealth index**. Deposits are not profit, and withdrawals are not losses. Segment valuations around external flows for exact time-weighted returns; disclose approximations such as Modified Dietz when flow-time valuations are unavailable.
- Count internal financing interest, dividends, fees, taxes where modeled, slippage, and borrow costs as strategy outcomes, not external contributions. Avoid subtracting slippage twice when it is already reflected in execution prices.
- Define a trade as a closed position episode or a matched lot under a declared rule (for example FIFO). Scaling, partial exits, reversals, and multi-leg positions need explicit attribution. Use this definition consistently across trade metrics.
- Trade P&L includes allocated costs. Open positions contribute unrealized portfolio P&L but are excluded from closed-trade win rates and expectancy; report them separately.
- Define positive trade P&L as a win, negative as a loss, and zero as flat, with a declared rounding/tolerance policy. Default win rate includes flats in the denominator; also report the non-flat win rate.
- Calculate gross and net variants where meaningful and identify which is shown. State the capital/notional denominator of percentage trade returns, especially for leverage and shorts.

Notation: `r_t` is the net portfolio return in period `t`; `e_t = r_t - rf_t` is excess return; `m_t` is the period MAR; `A` is periods per year; `N` is the number of returns; `V_t` is the cash-flow-adjusted wealth index. Include the starting value `V_0` when computing peaks. Ratios are dimensionless unless noted; return and volatility fields use decimal units internally.

## 2. Trade outcome measures

| Metric / suggested key | Definition | Notes |
|---|---|---|
| Closed trades / `closed_trade_count` | Number of completed trades under the matching rule | Also report open trades, fills, and rejected orders |
| Wins, losses, flats | Counts by net closed-trade P&L sign | Counts must reconcile to closed trades |
| Win rate / `win_rate` | Wins / closed trades | Undefined with no closed trades; losing/flat rates complement it |
| Non-flat win rate | Wins / (wins + losses) | Report separately; do not silently exclude flats |
| Average P&L / `average_trade_pnl` | Mean net currency P&L per closed trade | Also median and standard deviation |
| Average trade return | Mean trade P&L / declared trade capital, computed per trade | Equal-weighted trade statistic; differs from portfolio mean return |
| Average win / loss | Mean positive P&L / mean negative P&L | Average loss is signed; report absolute magnitude where used |
| Payoff ratio | Average win / absolute average loss | A high win rate can coexist with poor payoff |
| Trade expectancy | `p_win * average_win + p_loss * average_loss` | Flats contribute zero; equals mean trade P&L under consistent accounting |
| Gross profit / gross loss | Sum of positive trade P&Ls / absolute sum of negative trade P&Ls | “Gross” here means summing outcomes by sign; state whether underlying P&L is before or after costs |
| Profit factor | Sum of positive P&L / absolute sum of negative P&L | Undefined denominator cases get a status, not an arbitrary large number |
| Total closed-trade P&L | Sum of net closed-trade P&L | Does not necessarily equal portfolio net profit with open positions or unallocated income/costs |
| Best/worst trade and trade quantiles | Extremes and selected quantiles of P&L/return | Identify trades and quantile convention |
| Win/loss streaks | Longest consecutive runs in closed-trade order | Define handling of flats and simultaneous closes |
| Holding duration | Mean, median, quantiles of elapsed/calendar or trading time | Separate wins/losses where useful |
| MAE / MFE | Maximum adverse/favorable excursion over each trade's life | Needs intratrade marks; close-only data cannot establish intrabar excursions |
| Long/short breakdown | Counts, outcomes, durations, and P&L per side | Include instrument/sector/strategy breakdowns when sample size permits |

## 3. Portfolio performance and cash-flow measures

| Metric / suggested key | Definition | Notes |
|---|---|---|
| Net profit / `net_profit` | Ending account equity − starting equity − net external contributions | Include unrealized marked P&L and internally earned income/costs; disclose valuation assumptions |
| Net/gross P&L decomposition | Realized + unrealized + income − costs, with reconciled components | Also show deposited and withdrawn capital separately |
| Total time-weighted return | `product(1 + r_t) - 1` | Use flow-adjusted subperiod returns |
| Mean return / `mean_return` (`meanret`) | Arithmetic mean of periodic net portfolio returns | Report sampling period; add median and geometric mean separately |
| Geometric mean period return | `product(1 + r_t)^(1/N) - 1` | Requires a valid positive wealth path for the real-valued interpretation |
| Variance / `variance_return` (`varret`) | Sample variance of periodic returns | This is variance, not Value at Risk |
| Annual arithmetic mean | `A * mean(r_t)` | A scaled statistic, not realized compound growth |
| CAGR / `cagr` | `(V_end / V_start)^(1/Y) - 1`, with elapsed years `Y` | Use positive flow-adjusted wealth endpoints and declare day-count convention; do not annualize raw account growth with deposits |
| XIRR / `xirr` | Rate `x` satisfying `sum(CF_i / (1+x)^((date_i-date_0)/365)) = 0` | Investor perspective: initial value/contributions negative, withdrawals/terminal liquidation value positive; use exact dates and ACT/365 for the default convention |
| Rolling returns and growth | Fixed-window total return, mean, and annualized growth where meaningful | Avoid interpreting short-window annualization as a forecast |
| Monthly/yearly returns | Calendar aggregation of compounded period returns | Include full and partial periods explicitly |
| Best/worst period | Extremes by declared day/week/month/year | Do not compare unlike horizons |
| Portfolio hit rate | Fraction of periods with positive portfolio return | Distinct from trade win rate; specify net, excess, or active return basis |

For XIRR, require cash flows of both signs, restrict the usual real-valued rate domain to `x > -1`, specify date aggregation and solver bounds/tolerance, verify the root's residual, and check for possible multiple roots. Do not double-count an opening contribution already represented by starting value, or a terminal withdrawal already represented by liquidation value. Do not assume one root or report a solver guess as a valid result. Return `no_solution`, `multiple_solutions`, or `inconclusive` as appropriate. CAGR measures time-weighted growth; XIRR measures money-weighted investor experience. Neither is an arithmetic mean.

## 4. Volatility, downside, and tail risk

| Metric / suggested key | Definition | Notes |
|---|---|---|
| Period volatility | Sample standard deviation of `r_t` | Identify return frequency |
| Annual volatility / `annual_volatility` (`annvol`) | `std(r_t) * sqrt(A)` | Conventional scaling; disclose serial dependence and show dependence-aware estimates when material |
| Downside deviation / `downside_deviation` (`downdev`) | `sqrt(mean(min(r_t - m_t, 0)^2))`, over **all** periods | Lower partial moment of order 2; denominator is `N`, not just below-MAR observations |
| Annual downside volatility / `annual_downside_volatility` (`downvol`) | Downside deviation `* sqrt(A)` under the stated convention | MAR must be aligned to the return frequency |
| Conditional downside dispersion | Dispersion conditional on below-target periods, if requested | Label separately; it is not the default Sortino denominator |
| Lower partial moments | `mean(max(m_t-r_t, 0)^k)` for declared `k` | Report target and moment order |
| Skewness | Asymmetry of the return distribution | Declare bias correction and minimum valid sample |
| Kurtosis | Tail/shape statistic | Default excess kurtosis; distinguish it from raw kurtosis |
| Historical VaR / `var_loss_95`, etc. | Quantile of loss `L_t = -r_t` at the stated confidence/horizon | Specify quantile interpolation and sign convention; `variance_return` is a separate field |
| Expected shortfall / CVaR | Mean loss in the upper tail under the declared estimator | Define tail probability and treatment of ties/fractional tail mass; interval estimates matter with few tail observations |
| Tail ratio | Positive upper return quantile / absolute lower quantile | For example 95th/5th; define behavior when expected tail signs do not hold |
| Gain/loss concentration | Contribution of largest winners, losers, dates, or instruments | Reveals dependence on a few observations |
| Stress losses | Observed and scenario losses under specified shocks | Distinguish historical outcomes from hypothetical scenarios |

Do not silently clamp a negative estimated VaR to zero or convert signs inconsistently. Historical tails are horizon-specific and do not guarantee limits on future losses. Normal-distribution VaR may be an optional explicitly labeled model estimate, not a replacement for historical and stressed measures.

## 5. Risk-adjusted return measures

| Metric / suggested key | Default definition | Notes |
|---|---|---|
| Sharpe / `sharpe` | `mean(e_t) / std(e_t) * sqrt(A)` | Use aligned period risk-free returns; sample standard deviation; zero dispersion is not a finite Sharpe |
| Sortino / `sortino` | `mean(r_t - m_t) * A / (downside_deviation * sqrt(A))` | Arithmetic annualized excess over MAR with matching downside denominator; a CAGR-based alternative must be separately labeled |
| Calmar / `calmar` (`clmar`) | CAGR / absolute maximum drawdown | Same declared evaluation window for numerator and denominator; traditional trailing-window variants need explicit names |
| Omega / `omega` | `sum(max(r_t-m_t,0)) / sum(max(m_t-r_t,0))` | Frequency/target-specific gain versus loss, with defined zero-denominator handling |
| Martin / Ulcer Performance Index | Annualized mean excess over MAR / Ulcer Index | Use decimal Ulcer Index and the same time window; label CAGR-based variants separately |
| Gain-to-pain | Sum of period returns / absolute sum of negative returns | Define whether total return means an arithmetic sum here; this is not Omega or compounded return |
| Return over drawdown variants | Declared return numerator / chosen drawdown statistic | Do not present custom ratios under standard metric names |

Convert annual risk-free/MAR inputs to period returns under a declared convention (for example `(1 + annual_rate)^(1/A) - 1` for a constant effective annual rate). Use actual period-aligned rates when available. Do not mix annual thresholds with daily returns or subtract an annual rate from each observation.

The usual square-root annualization assumes a particular dependence structure. Report autocorrelation diagnostics and, when appropriate, a separately named HAC/long-run-variance-adjusted Sharpe with documented assumptions. Confidence intervals and bootstrap methodology belong in the statistical report; a high point estimate alone is not a pass.

## 6. Drawdown and recovery measures

Compute running peak `P_t = max(V_0, ..., V_t)` and signed drawdown `D_t = V_t/P_t - 1`. Default maximum drawdown is the **positive loss magnitude** `-min(D_t)`; export the full signed series as well.

| Metric / suggested key | Definition | Notes |
|---|---|---|
| Maximum drawdown / `max_drawdown` | Largest peak-to-trough percentage loss | Record peak, trough, and recovery dates |
| Current drawdown | Latest loss magnitude from the running peak | Unrecovered drawdowns remain open |
| Drawdown duration | Time from peak until recovery to that peak | Report trading/calendar durations; unrecovered episodes are right-censored |
| Recovery duration | Trough-to-recovery time | Do not assign zero to an unrecovered episode |
| Time under water | Share of valuation periods below prior peak | Include sampling convention and current episode |
| Average drawdown | Mean drawdown loss across valuation periods | Distinguish from mean severity across drawdown episodes |
| Episode severity/duration | Distribution and worst episodes | Provide episode-level records rather than only a headline |
| Ulcer Index / `ulcer_index` | `sqrt(mean(D_t^2))` | RMS drawdown, using decimal drawdowns over the declared sampled window; percentage-point versions differ by 100 |
| Conditional drawdown at risk | Mean of worst sampled drawdowns at specified tail level | Define the drawdown series, tail estimator, and horizon; not return CVaR |
| Recovery factor | Net profit / maximum currency drawdown under defined capital accounting | Currency drawdown with external flows needs an adjusted accounting basis; do not mix currency profit with percentage drawdown |

If NAV reaches zero or becomes negative, flag insolvency and the limits of percentage-return/growth metrics. Do not produce a plausible CAGR or Sharpe by dropping the bankruptcy observation.

## 7. Benchmark-relative performance and exposure

| Metric | Definition / purpose | Notes |
|---|---|---|
| Active returns | Strategy return minus aligned benchmark return | Same currency, frequency, and total-return basis |
| Tracking error | Sample standard deviation of active returns, conventionally annualized | Show uncertainty and dependence assumptions |
| Information ratio | Mean active return / standard deviation of active return, conventionally annualized | Different from factor ICIR |
| Alpha and beta | Intercept and slope of excess strategy returns regressed on excess benchmark returns | Label model, period/annual units, controls, HAC uncertainty, and fit diagnostics |
| Regression R² | Variance explained under the chosen exposure model | Does not measure profitability |
| Treynor ratio | Annualized mean excess return / beta | Undefined or hard to interpret near zero or negative beta; report that status |
| Up/down capture | Relative compounded performance in benchmark-up/down periods | Specify calculation and denominator conventions |
| Correlation and rolling beta | Co-movement and stability versus benchmark/risk factors | Report valid observations and rolling-window rules |
| Gross/net exposure, leverage | Position exposure under specified capital denominator | Provide time series and maxima; define cash, derivatives, and margin treatment |
| Concentration and attribution | Instrument/sector/country/factor contribution and weight concentration | Separate raw market exposure from claimed incremental alpha |

## 8. Costs, turnover, liquidity, and capacity

Report total fees, slippage attribution, spread estimates, financing/borrow costs, modeled taxes, gross-to-net performance degradation, order and fill counts, rejected/unfilled orders, participation rates, and liquidity exposure.

Turnover must have a declared denominator and convention. For example, one-way portfolio turnover can be `0.5 * sum(abs(weight_after - weight_before))` at rebalance, with cash included under the chosen accounting rule. Notional traded divided by NAV is another measure; name it separately and avoid comparing them as though identical.

Capacity evaluation varies capital, participation limits, fill assumptions, and costs while freezing the strategy rules. Include delay and adverse-cost scenarios. When the simulator lacks a necessary input (for example borrow availability), record the limitation rather than implying that constraint was tested.

## 9. Report schema and edge cases

Every metric should return a value plus metadata/status:

```json
{
  "metric": "sharpe",
  "value": null,
  "unit": "ratio",
  "status": "undefined",
  "reason": "zero_excess_return_dispersion",
  "sample_count": 252,
  "frequency": "daily",
  "annualization_factor": 252,
  "return_basis": "net_simple",
  "parameters": {"ddof": 1}
}
```

Use distinct statuses such as `ok`, `undefined`, `insufficient_data`, `not_applicable`, `not_computed`, and `invalid_input`. For XIRR, add explicit solution statuses. Emit undefined/no-loss profit factors as null with a reason instead of Infinity, which is not valid standard JSON. A zero denominator is not a reason to assign zero or an arbitrary upper limit.

Include assumptions, time series, sample counts, calculation version, result provenance, gross/net labels, uncertainty where computed, and cash-flow reconciliation. Default summaries should show:

- **Performance:** net profit, time-weighted return, CAGR, XIRR when applicable, mean/median return.
- **Trades:** counts, win rate, average P&L, payoff ratio, expectancy, profit factor, holding duration.
- **Risk:** variance, annual volatility, downside deviation/volatility, VaR/ES, skewness/kurtosis.
- **Risk-adjusted:** Sharpe, Sortino, Calmar, Omega, Ulcer Index and Martin ratio.
- **Drawdowns:** magnitude, duration, recovery, time under water.
- **Relative/operational:** benchmark measures, exposure, turnover, costs, liquidity/capacity scenarios.

Publish numerical results as structured artifacts and readable tables/plots. Missing benchmarks, no external flows, or absent intratrade marks should explain unavailable metrics rather than prevent unrelated metrics from being computed.

Specify uncertainty for metrics used in decisions. Trade-outcome intervals must account for clustered or overlapping trades rather than blindly assuming independent Bernoulli trials. Portfolio-return inference should preserve serial dependence. Drawdowns and recovery are path-dependent; resampling them requires a valid reconstructed wealth path and explicit methodology. Keep exploratory subgroup comparisons separate from prespecified confirmatory claims.

## 10. Implementation acceptance tests

- Reconcile starting/ending equity, external flows, realized/unrealized P&L, income, and costs using hand-calculated portfolios.
- Verify flat, winning-only, losing-only, mixed, partial-close, short, and open-position trade cases.
- Verify sample mean/variance and Sharpe/Sortino with small reference series; catch return-frequency and threshold unit mistakes.
- Test downside deviation against the all-period definition, including no below-MAR observations and a nonzero MAR.
- Use known wealth paths to verify drawdown, duration, censoring, Ulcer Index, and Calmar; include initial NAV in the first running peak.
- Verify deposits/withdrawals do not create apparent investment gains or drawdowns; contrast TWR/CAGR with XIRR under unequal cash-flow timing.
- Test known XIRR solutions, no solution, multiple-root possibilities, duplicate dates, and residual verification under ACT/365.
- Test insolvency, zero denominators, sparse samples, missing prices, irregular dates, benchmark alignment, and decimal/percentage scaling.
- Verify historical VaR/ES tails and quantile conventions, including ties and small-tail samples.
- Compare implemented metrics with independent reference calculations under matching definitions; library defaults are not assumed interchangeable.
- Keep statistical uncertainty/calibration tests separate from deterministic accounting tests, and run end-to-end fixtures from supplied signals to the complete report.
