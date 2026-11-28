# ruff: noqa: E501  (evidence script kept as run)
# Mutation sample for REVIEW-10 R3. Each mutant: one-line change in the COPY at R3/repo.
EV = "strategy-evaluation/src/invest_evaluation/"
MI = "data-mining-framework/src/invest_mining/"
DA = "data-pipeline/data-preparation/src/invest_data/"
ET = "strategy-evaluation/tests/"
MT = "data-mining-framework/tests/"
DT = "data-pipeline/data-preparation/tests/"
MUTANTS = [
    (
        "M1",
        EV + "engine.py",
        "eligible = tradable & (traded_close[i] >= ex.min_price)",
        "eligible = tradable & (px_close[i] >= ex.min_price)",
        [
            ET
            + "test_engine.py::test_min_price_uses_the_as_traded_close_so_later_actions_cannot_change_eligibility"
        ],
        [ET],
    ),
    (
        "M2",
        EV + "engine.py",
        "adv = dollar_vol.rolling(cm.adv_window, min_periods=cm.adv_window).mean()",
        "adv = dollar_vol.rolling(cm.adv_window, min_periods=cm.adv_window).mean().shift(-1)",
        [ET + "test_engine.py::test_future_prices_and_signals_cannot_change_the_past"],
        [ET, "tests/test_pipeline.py", "tests/test_quantile_consistency.py"],
    ),
    (
        "M3",
        EV + "engine.py",
        'sc = pd.Series(S[i][eligible], index=instruments[eligible], name="score")',
        'sc = pd.Series(S[min(i + 1, len(S) - 1)][eligible], index=instruments[eligible], name="score")',
        [ET + "test_engine.py::test_future_prices_and_signals_cannot_change_the_past"],
        [ET],
    ),
    (
        "M4",
        EV + "engine.py",
        'day_costs_paid = daily[[f"{k}_cost" for k in (*COST_KINDS, "borrow")]].sum(axis=1)',
        'day_costs_paid = daily[[f"{k}_cost" for k in COST_KINDS]].sum(axis=1)',
        [ET + "test_engine.py::test_gross_of_costs_metrics_are_not_diluted_by_past_costs"],
        [ET, "tests/test_pipeline.py"],
    ),
    (
        "M5",
        EV + "engine.py",
        "        if equity <= 0:\n            break",
        "        if equity < 0:\n            break",
        [ET + "test_engine.py", ET + "test_validation.py"],
        [ET],
    ),
    (
        "M6",
        EV + "strategies.py",
        'numbers = np.searchsorted(cutpoints, values.to_numpy(), side="left") + 1',
        'numbers = np.searchsorted(cutpoints, values.to_numpy(), side="right") + 1',
        [ET + "test_quantiles.py"],
        [ET, "tests/test_quantile_consistency.py"],
    ),
    (
        "M7",
        MI + "diagnostics.py",
        "return lower.where(pct <= pct_from_top, upper).clip(lower=1, upper=n_buckets)",
        "return lower.where(pct < pct_from_top, upper).clip(lower=1, upper=n_buckets)",
        [MT + "test_diagnostics.py"],
        [MT, "tests/test_quantile_consistency.py"],
    ),
    (
        "M8",
        EV + "strategies.py",
        "longs = scores.index[(from_top <= cfg.long_fraction).to_numpy()]",
        "longs = scores.index[(from_top < cfg.long_fraction).to_numpy()]",
        [ET + "test_engine.py", ET + "test_quantiles.py"],
        [ET, "tests/test_quantile_consistency.py", "tests/test_pipeline.py"],
    ),
    (
        "M9",
        EV + "metrics.py",
        "ex_std = float(excess.std(ddof=1))",
        "ex_std = float(excess.std(ddof=0))",
        [ET + "test_metrics.py"],
        [ET],
    ),
    (
        "M10",
        EV + "engine.py",
        "            k = int(earlier[-1])",
        "            k = i - 1",
        [
            ET
            + "test_benchmark_delistings.py::test_a_settlement_after_the_last_bar_spans_the_missing_bars_like_the_holdings"
        ],
        [ET],
    ),
    (
        "M11",
        MI + "ledger.py",
        "return (self.end is None or other.start <= self.end) and (",
        "return (self.end is None or other.start < self.end) and (",
        [MT + "test_ledger.py::test_window_overlap_containment_and_validation"],
        [MT],
    ),
    (
        "M12",
        MI + "expressions.py",
        'SCALE_EXPONENTS: dict[str, int] = {"open": 1, "high": 1, "low": 1, "close": 1, "volume": -1}',
        'SCALE_EXPONENTS: dict[str, int] = {"open": 1, "high": 1, "low": 0, "close": 1, "volume": -1}',
        [MT + "test_scale_check.py"],
        [MT],
    ),
    (
        "M13",
        MI + "expressions.py",
        'if OPS[sub.op].kind in ("ts", "ts2"):',
        'if OPS[sub.op].kind in ("ts",):',
        [MT + "test_scale_check.py"],
        [MT],
    ),
    (
        "M14",
        DA + "schemas.py",
        "    if adjustment not in ADJUSTED_PRICES:",
        "    if adjustment not in PRICE_ADJUSTMENTS:",
        [ET + "test_stats_and_cli.py"],
        [ET, MT, DT],
    ),
    (
        "M15",
        DA + "bundle.py",
        '            raise BundleError("content hash mismatch: data does not match its manifest")',
        "            pass",
        [DT + "test_bundle.py"],
        [DT],
    ),
]
