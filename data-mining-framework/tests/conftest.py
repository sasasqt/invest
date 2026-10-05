import numpy as np
import pandas as pd
import pytest

from invest_data.sources import SyntheticConfig, synthetic_market


@pytest.fixture(scope="session")
def bars() -> pd.DataFrame:
    return synthetic_market(SyntheticConfig(n_instruments=40, n_days=400, seed=11))


@pytest.fixture
def tiny_panel() -> dict[str, pd.DataFrame]:
    idx = pd.bdate_range("2024-01-01", periods=6)
    close = pd.DataFrame(
        {
            "A": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "B": [6.0, 5.0, 4.0, 3.0, 2.0, 1.0],
            "C": [1.0, 1.0, 1.0, 1.0, 1.0, np.nan],
        },
        index=idx,
    )
    return {
        "close": close,
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "volume": close * 0 + 100.0,
        "returns": close / close.shift(1) - 1,
        "dollar_volume": close * 100.0,
        "intraday_return": close / (close * 0.99) - 1,
    }
