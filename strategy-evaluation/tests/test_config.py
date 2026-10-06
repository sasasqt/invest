import math

import pytest

from invest_evaluation.config import BacktestConfig, CostModel, ExecutionConfig, StrategyConfig


@pytest.mark.parametrize(
    "raw",
    [
        {"annualization": 0},
        {"annualization": 252.5},
        {"annualization": True},
        {"initial_capital": math.nan},
        {"initial_capital": math.inf},
        {"initial_capital": "1000"},
        {"initial_capital": -1},
        {"risk_free_annual": -1},
        {"mar_annual": math.nan},
        {"costs": {"commission_bps": -100}},
        {"costs": {"half_spread_bps": math.inf}},
        {"costs": {"impact_coef": math.nan}},
        {"costs": {"borrow_bps_annual": -1}},
        {"costs": {"adv_window": 0}},
        {"costs": {"vol_window": 1}},
        {"costs": {"cash_rate_annual": -1}},
        {"costs": []},
        {"strategy": {"gross_leverage": math.nan}},
        {"strategy": {"long_fraction": math.inf}},
        {"strategy": {"short_fraction": math.nan}},
        {"strategy": {"min_names": 0}},
        {"strategy": {"rebalance_every": 1.5}},
        {"execution": {"delay": False}},
        {"execution": {"delay": -1}},
        {"execution": {"max_participation": math.nan}},
        {"execution": {"min_price": -1}},
        {"execution": {"min_adv_dollar": math.inf}},
        {"start": "2024-13-01"},
        {"start": "20240101"},
        {"start": 20240101},
        {"start": "2024-02-01", "end": "2024-01-01"},
    ],
)
def test_invalid_config_fails_before_simulation(raw):
    with pytest.raises(ValueError):
        BacktestConfig.from_dict(raw)


def test_subconfigs_validate_when_constructed_directly():
    for cls, kwargs in (
        (CostModel, {"commission_bps": -1}),
        (ExecutionConfig, {"delay": 0.5}),
        (StrategyConfig, {"gross_leverage": math.nan}),
    ):
        with pytest.raises(ValueError):
            cls(**kwargs)


def test_zero_costs_and_negative_rates_are_valid():
    config = BacktestConfig.from_dict(
        {
            "costs": {
                "commission_bps": 0,
                "half_spread_bps": 0,
                "impact_coef": 0,
                "borrow_bps_annual": 0,
                "cash_rate_annual": -0.01,
            },
            "risk_free_annual": -0.01,
            "mar_annual": -0.01,
        }
    )
    assert config.costs.cash_rate_annual == -0.01
