# ruff: noqa: E501  (evidence script kept as run)
from pathlib import Path

EV = "strategy-evaluation/src/invest_evaluation/"
MI = "data-mining-framework/src/invest_mining/"
DA = "data-pipeline/data-preparation/src/invest_data/"
ET = "strategy-evaluation/tests/"
MT = "data-mining-framework/tests/"
DT = "data-pipeline/data-preparation/tests/"
PROBE = str(Path(__file__).with_name("causality_variant_probe.py"))
M1 = (
    EV + "engine.py",
    "eligible = tradable & (traded_close[i] >= ex.min_price)",
    "eligible = tradable & (px_close[i] >= ex.min_price)",
)
M2 = (
    EV + "engine.py",
    "adv = dollar_vol.rolling(cm.adv_window, min_periods=cm.adv_window).mean()",
    "adv = dollar_vol.rolling(cm.adv_window, min_periods=cm.adv_window).mean().shift(-1)",
)
M3 = (
    EV + "engine.py",
    'sc = pd.Series(S[i][eligible], index=instruments[eligible], name="score")',
    'sc = pd.Series(S[min(i + 1, len(S) - 1)][eligible], index=instruments[eligible], name="score")',
)
MUTANTS3 = [
    ("M1e", [M1], ["tests/test_pipeline.py"], ["tests/test_pipeline.py"]),
    (
        "M25",
        [
            (
                MI + "expressions.py",
                "    if _scale(node) != _FREE:",
                "    if False and _scale(node) != _FREE:",
            )
        ],
        ["tests/test_pipeline.py"],
        [MT + "test_cli.py", MT + "test_search_and_inference.py"],
    ),
    (
        "M22",
        [
            (
                DA + "cleaning.py",
                '    out["volume"] = raw["volume"] / factor',
                '    out["volume"] = raw["volume"]',
            )
        ],
        [DT + "test_cleaning_and_sources.py", DT + "test_yahoo.py"],
        [DT, "tests/test_pipeline.py"],
    ),
    (
        "M23",
        [(MI + "diagnostics.py", "    entry = open_.shift(-1)", "    entry = open_")],
        [MT + "test_diagnostics.py"],
        [MT],
    ),
    (
        "M3q",
        [M3],
        [ET + "test_quantiles.py::test_future_data_cannot_change_earlier_bucket_holdings"],
        [ET + "test_quantiles.py"],
    ),
    ("M3p", [M3], [PROBE + "::test_future_prices_and_signals_cannot_change_the_past[5]"], [PROBE]),
    ("M2p", [M2], [PROBE + "::test_future_prices_and_signals_cannot_change_the_past[5]"], [PROBE]),
]
