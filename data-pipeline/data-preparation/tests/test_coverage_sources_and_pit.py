"""CSV import, the synthetic universe and point-in-time fundamentals: branches no other
test reached. Expected values follow from each function's docstring by hand."""

from pathlib import Path

import pandas as pd
import pytest

from invest_data.pit import fundamentals_asof
from invest_data.sources import load_csv_bars, synthetic_universe

D = pd.Timestamp


def test_csv_import_names_every_missing_required_column(tmp_path: Path) -> None:
    path = tmp_path / "bars.csv"
    path.write_text("date,instrument,open,high,low\n2024-01-02,A,10,11,9\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"missing required columns \['close', 'volume'\]"):
        load_csv_bars(path)


def test_synthetic_universe_leaves_out_names_that_never_finish_seasoning() -> None:
    dates = pd.bdate_range("2024-01-02", periods=30)
    long = pd.DataFrame({"date": dates, "instrument": "LONG"})
    # Lists on session 25 of 30: seasoning of 20 sessions ends after the data does.
    late = pd.DataFrame({"date": dates[25:], "instrument": "LATE"})
    # Trades sessions 0 to 10 only: its last session comes before seasoning ends.
    short = pd.DataFrame({"date": dates[:11], "instrument": "SHORT"})
    bars = pd.concat([long, late, short], ignore_index=True)
    universe = synthetic_universe(bars, seasoning=20)
    # LONG joins 20 sessions after listing; the other two never join.
    assert set(universe["instrument"]) == {"LONG"}
    assert universe["start_date"].min() == dates[20]


def test_fundamentals_asof_ignores_instruments_that_were_not_asked_for() -> None:
    fundamentals = pd.DataFrame(
        {
            "instrument": ["A", "B"],
            "field": ["bp", "bp"],
            "period_end": [D("2023-12-31"), D("2023-12-31")],
            "available_date": [D("2024-01-03"), D("2024-01-02")],
            "value": [0.5, 9.0],
        }
    )
    dates = pd.DatetimeIndex([D("2024-01-02"), D("2024-01-03"), D("2024-01-04")])
    out = fundamentals_asof(fundamentals, "bp", dates, pd.Index(["A"]))
    assert out.columns.tolist() == ["A"]
    # A's value is known from its available date on, never before it.
    assert out["A"].isna().tolist() == [True, False, False]
    assert out["A"].iloc[1:].tolist() == [0.5, 0.5]
