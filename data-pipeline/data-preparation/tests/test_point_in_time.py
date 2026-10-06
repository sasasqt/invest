import numpy as np
import pandas as pd
import pytest

from invest_data.bundle import BundleError
from invest_data.pit import fundamentals_asof, membership_panel
from invest_data.schemas import (
    publish_fundamentals,
    publish_universe,
    read_fundamentals,
    read_universe,
)
from invest_data.sources import (
    SyntheticConfig,
    synthetic_fundamentals,
    synthetic_market,
    synthetic_universe,
)

D = pd.Timestamp


def universe_rows():
    return pd.DataFrame(
        {
            "universe": ["U", "U", "U"],
            "instrument": ["A", "A", "B"],
            "start_date": [D("2024-01-02"), D("2024-01-08"), D("2024-01-03")],
            "end_date": [D("2024-01-04"), pd.NaT, pd.NaT],
        }
    )


def test_membership_intervals_are_half_open():
    dates = pd.bdate_range("2024-01-01", periods=7)
    m = membership_panel(universe_rows(), dates, pd.Index(["A", "B", "C"]))
    assert m["A"].tolist() == [False, True, True, False, False, True, True]
    assert m["B"].tolist() == [False, False, True, True, True, True, True]
    assert not m["C"].any()


def test_membership_requires_name_with_several_universes():
    rows = pd.concat([universe_rows(), universe_rows().assign(universe="V")])
    with pytest.raises(ValueError, match="several universes"):
        membership_panel(rows, pd.bdate_range("2024-01-01", periods=3), pd.Index(["A"]))
    m = membership_panel(rows, pd.bdate_range("2024-01-01", periods=3), pd.Index(["A"]), "V")
    assert m["A"].tolist() == [False, True, True]


@pytest.mark.parametrize("fmt", ["csv", "parquet"])
def test_universe_bundle_round_trip_and_validation(tmp_path, fmt):
    publish_universe(universe_rows(), tmp_path / "u", dataset_id="u", fmt=fmt)
    _, back = read_universe(tmp_path / "u")
    assert len(back) == 3 and back["end_date"].isna().sum() == 2
    overlapping = universe_rows()
    overlapping.loc[0, "end_date"] = D("2024-01-09")
    with pytest.raises(BundleError, match="overlapping"):
        publish_universe(overlapping, tmp_path / "x", dataset_id="u")
    backwards = universe_rows()
    backwards.loc[0, "end_date"] = D("2024-01-01")
    with pytest.raises(BundleError, match="after start_date"):
        publish_universe(backwards, tmp_path / "y", dataset_id="u")


def fundamentals_rows():
    return pd.DataFrame(
        {
            "instrument": ["A", "A", "A", "A"],
            "field": ["bp"] * 4,
            "period_end": [D("2023-12-31"), D("2023-12-31"), D("2024-01-06"), D("2023-12-31")],
            "available_date": [D("2024-01-03"), D("2024-01-05"), D("2024-01-09"), D("2024-01-11")],
            "value": [1.0, 1.1, 2.0, 1.2],
        }
    )


def test_fundamentals_asof_uses_only_published_values_and_revisions():
    dates = pd.bdate_range("2024-01-01", periods=10)
    v = fundamentals_asof(fundamentals_rows(), "bp", dates, pd.Index(["A", "B"]))["A"]
    expected = [np.nan, np.nan, 1.0, 1.0, 1.1, 1.1, 2.0, 2.0, 2.0, 2.0]
    # Jan 11 revises the *older* period; the newer period's value (2.0) stays in force.
    np.testing.assert_array_equal(v.to_numpy(), expected)


def test_fundamentals_asof_ignores_future_rows():
    rows = fundamentals_rows()
    dates = pd.bdate_range("2024-01-01", periods=10)
    cut = D("2024-01-08")
    full = fundamentals_asof(rows, "bp", dates, pd.Index(["A"]))
    known = fundamentals_asof(rows[rows["available_date"] <= cut], "bp", dates, pd.Index(["A"]))
    pd.testing.assert_frame_equal(full.loc[:cut], known.loc[:cut])


def test_fundamentals_bundle_validation(tmp_path):
    publish_fundamentals(fundamentals_rows(), tmp_path / "f", dataset_id="f", fmt="sqlite")
    m, back = read_fundamentals(tmp_path / "f")
    assert m.metadata["available_at"] == "available_date_close" and len(back) == 4
    early = fundamentals_rows()
    early.loc[0, "available_date"] = D("2023-12-01")
    with pytest.raises(BundleError, match="before period_end"):
        publish_fundamentals(early, tmp_path / "g", dataset_id="f")


def test_synthetic_universe_and_fundamentals_are_valid(tmp_path):
    bars = synthetic_market(SyntheticConfig(n_instruments=20, n_days=300, seed=4))
    uni = synthetic_universe(bars, seed=4)
    fund = synthetic_fundamentals(bars, seed=4)
    publish_universe(uni, tmp_path / "u", dataset_id="u")
    publish_fundamentals(fund, tmp_path / "f", dataset_id="f")
    dates = pd.DatetimeIndex(sorted(bars["date"].unique()))
    m = membership_panel(uni, dates, pd.Index(sorted(bars["instrument"].unique())))
    listed = bars.pivot(index="date", columns="instrument", values="close").notna()
    assert not (m & ~listed).to_numpy().any()  # never a member without a bar
    assert (fund["available_date"] > fund["period_end"]).all()
    assert fund.duplicated(["instrument", "field", "period_end"]).any()  # has revisions
