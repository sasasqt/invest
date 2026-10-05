import pandas as pd
import pytest

from invest_data.sources import SyntheticConfig, synthetic_market


@pytest.fixture(scope="session")
def market() -> pd.DataFrame:
    return synthetic_market(SyntheticConfig(n_instruments=30, n_days=260, seed=5))


@pytest.fixture(scope="session")
def reversal_signals(market: pd.DataFrame) -> pd.DataFrame:
    """Five-day reversal score computed with pandas only (no mining dependency)."""
    close = market.pivot(index="date", columns="instrument", values="close")
    score = -(close / close.shift(5) - 1)
    long = score.stack().rename("score").reset_index()
    long.columns = ["decision_date", "instrument", "score"]
    return long.dropna().reset_index(drop=True)
