# Quantile analysis for factors and strategies

This is a shared report specification. Deciles and overlapping tail slices are implemented as factor diagnostics in `invest_mining/diagnostics.py` and as executable bucket portfolios in `invest_evaluation/quantiles.py` (`invest-eval quantiles`), which use the same membership rule: average-rank percentile `p` among decision-time eligible names, and `q`, the same percentile counted from the highest score; names with `p ≤ q` get bucket `ceil(p × n)` and the others `n + 1 − ceil(q × n)`; bottom `f` holds `p ≤ f`, top `f` holds `q ≤ f`. Buckets and tails are therefore mirror images (reversing the scores swaps bucket `k` and `n + 1 − k`, except a name or tie group exactly at the median). For at least three buckets the extremes equal the `1/n` tails. Distinct scores give equal extreme populations; preserved tie groups can make those populations unequal. Both skip dates with fewer names than `max(buckets, min_names)` (`invest-mine evaluate --min-cross-section`; the diagnostics count scored names, the portfolios eligible names) and report slices with fewer than a declared minimum of names (default 5) as `insufficient_data`. `tests/test_quantile_consistency.py` checks that the two components assign the same names, and `tests/test_pipeline.py` compares the saved reports of a workflow run. Mining owns factor diagnostics; strategy evaluation owns actual portfolio results. See [component ownership](ARCHITECTURE.md), [alpha validation](../data-mining-framework/ALPHA_VALIDATION.md), and [strategy metrics](../strategy-evaluation/METRICS.md).

## Signal buckets

At each decision timestamp, select the point-in-time eligible universe and sort available signals using an orientation frozen during development. Assign buckets before observing future returns.

Default diagnostics include:

- Deciles: ten buckets from the lowest to the highest scores, mirrored about the median as described above (roughly 0–10% through 90–100% of the eligible cross-section; upper buckets are bounded by `q`, so their exact percentile ranges differ from `p` by `1/N`).
- Bottom/top 1%, 5%, and 10% as separately labeled extreme slices.
- Top-minus-bottom spreads, overall monotonicity, and cumulative behavior over time.

Extreme slices overlap deciles. They are additional views and must not be summed as a disjoint partition. Distinguish bottom signal percentiles from the worst realized-return percentiles and from chronological early/late observations.

## Reproducible assignment rules

Record the universe, decision-time filters, signal orientation, missing-signal policy, cutpoint/ranking method, tie policy, weighting, requested intervals, and minimum observations needed to interpret a bucket.

Implement bucket boundaries by comparing percentiles directly with inclusive cutpoints `k/n`, rather than multiplying by `n` before taking a ceiling: `0.28 × 25` can round above seven and incorrectly move a boundary name. Both components use the same cutpoint comparisons; tests check them against exact rational ranks and exercise a 125-name, 25-bucket executable report.

Reversal symmetry permits unequal populations when the two ends have different tie patterns. For example, 100 scored names with eleven tied at the top can give q1 ten names and q10 eleven, with the populations swapped when scores reverse. An exact median name or tie group retains its bucket under reversal. With two buckets it belongs to q2 but neither 50% tail, so extreme-bucket/tail equivalence applies only to at least three buckets.

Use `invest-mine evaluate --orientation` with the frozen factor's direction (default 1); the historical reversal workflow uses -1 for both diagnostics and export. Compare memberships on the same eligible cross-section, because trading additionally applies liquidity and price filters. Tail identifiers use the shortest round-trip float representation, so distinct accepted fractions such as `0.1` and `0.10000001` retain separate tables and return series.

- Derive eligibility from information available at decision time, including liquidity and universe membership. Do not select instruments because their future labels happen to exist.
- Define interval boundaries explicitly. Under empirical cutpoints, ties can produce unequal populations, duplicate boundaries, or empty buckets. Preserve ties together by default and report actual counts and unavailable buckets.
- Equal-count rank buckets are an alternative; if splitting ties, declare the deterministic tie-breaker and test whether it introduces systematic instrument bias. Do not silently switch methods when a library's quantile function fails.
- Record missing future labels and coverage separately from signal assignment. Use declared return/delisting valuation policies; silently dropping failed or delisted instruments can bias outcomes.
- Report actual counts and uncertainty. A top-1% slice of a small universe may contain too few instruments for useful inference; retain an explicit insufficient-data result.
- For cross-market comparisons, align timing, units, horizon, and eligibility conventions before comparing bucket returns.

## Factor report

For each bucket and declared target horizon, report mean/median forward return, available-label coverage, instrument count, dispersion, and date-level return series. Include top-minus-bottom separation, exposure/concentration, and stability across development/confirmation periods and declared regimes.

Use an explicit weighting convention; equal-weighted mean forward returns are a simple starting point. Infer uncertainty from date-level series with time dependence respected, rather than treating all stock-date observations as independent.

`tail_returns.csv` reports assigned populations (`mean_names`, `min_names`, `insufficient_dates`) separately from coverage (`mean_observed_names`, `min_observed_names`, `insufficient_label_dates`, `missing_label_dates`). `n_dates` counts dates meeting the observed-name minimum. A tail is `insufficient_data` and has no reported mean if it lacks the assigned-name minimum, falls below the observed-name minimum on any date with observable labels among scored names, or has no usable outcome dates. Dates with no observable labels anywhere among scored names are counted as missing and excluded from the coverage check, which permits unfinished forward horizons at the sample's end. Assignments never depend on future labels.

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
