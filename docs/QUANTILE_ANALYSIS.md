# Quantile analysis for factors and strategies

This is a shared report specification. Deciles and overlapping tail slices are implemented as factor diagnostics in `invest_mining/diagnostics.py`; bucket portfolios are evaluated through the quantile strategy in `invest_evaluation`. Mining owns factor diagnostics; strategy evaluation owns actual portfolio results. See [component ownership](ARCHITECTURE.md), [alpha validation](../data-mining-framework/ALPHA_VALIDATION.md), and [strategy metrics](../strategy-evaluation/METRICS.md).

## Signal buckets

At each decision timestamp, select the point-in-time eligible universe and sort available signals using an orientation frozen during development. Assign buckets before observing future returns.

Default diagnostics include:

- Deciles: 0–10%, 10–20%, through 90–100% of the eligible cross-section.
- Bottom/top 1%, 5%, and 10% as separately labeled extreme slices.
- Top-minus-bottom spreads, overall monotonicity, and cumulative behavior over time.

Extreme slices overlap deciles. They are additional views and must not be summed as a disjoint partition. Distinguish bottom signal percentiles from the worst realized-return percentiles and from chronological early/late observations.

## Reproducible assignment rules

Record the universe, decision-time filters, signal orientation, missing-signal policy, cutpoint/ranking method, tie policy, weighting, requested intervals, and minimum observations needed to interpret a bucket.

- Derive eligibility from information available at decision time, including liquidity and universe membership. Do not select instruments because their future labels happen to exist.
- Define interval boundaries explicitly. Under empirical cutpoints, ties can produce unequal populations, duplicate boundaries, or empty buckets. Preserve ties together by default and report actual counts and unavailable buckets.
- Equal-count rank buckets are an alternative; if splitting ties, declare the deterministic tie-breaker and test whether it introduces systematic instrument bias. Do not silently switch methods when a library's quantile function fails.
- Record missing future labels and coverage separately from signal assignment. Use declared return/delisting valuation policies; silently dropping failed or delisted instruments can bias outcomes.
- Report actual counts and uncertainty. A top-1% slice of a small universe may contain too few instruments for useful inference; retain an explicit insufficient-data result.
- For cross-market comparisons, align timing, units, horizon, and eligibility conventions before comparing bucket returns.

## Factor report

For each bucket and declared target horizon, report mean/median forward return, available-label coverage, instrument count, dispersion, and date-level return series. Include top-minus-bottom separation, exposure/concentration, and stability across development/confirmation periods and declared regimes.

Use an explicit weighting convention; equal-weighted mean forward returns are a simple starting point. Infer uncertainty from date-level series with time dependence respected, rather than treating all stock-date observations as independent.

Monotonicity is a diagnostic, not a universal admission rule. Some valid signals work only in an extreme or a regime. Report the shape and assess it against the intended hypothesis rather than forcing every alpha to increase smoothly across deciles.

Overlapping multi-period forward returns and idealized bucket spreads are **signal diagnostics**, not automatically executable portfolio returns. A top-minus-bottom spread does not specify capital allocation, gross exposure, financing, rebalancing, or costs.

## Strategy report

Use explicit portfolio rules to turn selected buckets into positions: long-only or long-short, gross/net exposure, weighting, holding horizon, staggered holdings, rebalance schedule, costs, borrowing, and liquidity constraints.

Report the applicable [strategy metrics](../strategy-evaluation/METRICS.md) for each prespecified selection policy, including turnover and capacity. A 1% portfolio may have better idealized returns but worse concentration and execution costs.

Keep threshold selection and trading-rule tuning in development data. The family of confirmation tests includes examined thresholds, horizons, and revisions as specified in the validation protocol. Do not promote the best test-period bucket as if its threshold were selected beforehand.

Outcome-percentile diagnostics are separate: inspect worst/best trades or return periods, including loss contribution and tails. Those retrospective groups do not become tradable rules simply because their outcomes are informative.

## Report artifacts and tests

Save assignment methodology, bucket memberships or reproducible references, cutpoints, actual populations, forward-return coverage, dated statistics, scenario definitions, and plot inputs. Visualize bucket return profiles, cumulative spreads, rolling behavior, counts, and exposure alongside confidence intervals where available.

Tests must cover ties, constant signals, small universes, empty buckets, missing signals/labels, changed membership, frozen direction, boundary assignments, and late-arriving information. Verify factor diagnostic returns separately from a hand-calculated executable bucket portfolio. Changing future observations must not alter earlier assignments.
