# ruff: noqa: E501  (evidence script kept as run)
EV = "strategy-evaluation/src/invest_evaluation/"
MI = "data-mining-framework/src/invest_mining/"
ET = "strategy-evaluation/tests/"
MT = "data-mining-framework/tests/"
MED_OLD = "return lower.where(pct <= pct_from_top, upper).clip(lower=1, upper=n_buckets)"
MED_NEW = "return lower.where(pct < pct_from_top, upper).clip(lower=1, upper=n_buckets)"
MUTANTS2 = [
    (
        "M16",
        [
            (
                EV + "engine.py",
                "        for j in np.flatnonzero(stale).tolist():",
                "        for j in []:",
            )
        ],
        [ET],
        [ET, "tests/test_pipeline.py"],
    ),
    (
        "M17",
        [
            (
                EV + "robustness.py",
                'cfg = replace(cfg, initial_capital=cfg.initial_capital * spec["capital_multiplier"])',
                "cfg = replace(cfg, initial_capital=cfg.initial_capital)",
            )
        ],
        [ET],
        [ET, "tests/test_pipeline.py"],
    ),
    (
        "M18",
        [(MI + "diagnostics.py", MED_OLD, MED_NEW), (EV + "strategies.py", MED_OLD, MED_NEW)],
        [
            MT + "test_diagnostics.py",
            ET + "test_quantiles.py",
            "tests/test_quantile_consistency.py",
        ],
        [MT, ET, "tests/test_pipeline.py"],
    ),
    ("M21", [(EV + "strategies.py", MED_OLD, MED_NEW)], [ET + "test_quantiles.py"], [ET]),
]
