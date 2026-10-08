import json
from dataclasses import replace

import pandas as pd
import pytest

from invest_data.bundle import BundleError
from invest_data.schemas import read_signals
from invest_data.sources import SyntheticConfig, synthetic_market
from invest_mining.artifact import FrozenFactor
from invest_mining.diagnostics import forward_returns
from invest_mining.expressions import build_panel
from invest_mining.inference import compute_scores, export_signals
from invest_mining.search import chronological_split, run_search


def test_split_purges_overlapping_labels():
    dates = pd.bdate_range("2024-01-01", periods=100)
    s = chronological_split(dates, 0.6, horizon=5, embargo=2)
    k = dates.get_loc(s.confirm_dates[0])
    last_dev = dates.get_loc(s.dev_dates[-1])
    assert last_dev + 1 + 5 < k - 2  # label end before confirmation data and the embargo
    assert len(s.dev_dates) + len(s.purged_dates) + len(s.confirm_dates) == 100


@pytest.mark.parametrize(("fraction", "k"), [(0.29, 29), (0.57, 57), (0.7, 70), (0.6, 60)])
def test_split_development_share_is_exact(fraction, k):
    """``int(100 * 0.29)`` is 28 in floating point; confirmation must start at session 29."""
    dates = pd.bdate_range("2024-01-01", periods=100)
    split = chronological_split(dates, fraction, horizon=1)
    assert split.confirm_dates[0] == dates[k]


@pytest.mark.parametrize("horizon", [1, 5, 40])
@pytest.mark.parametrize("embargo", [0, 2])
def test_reserved_prices_cannot_change_development_labels(horizon, embargo):
    dates = pd.bdate_range("2024-01-01", periods=100)
    split = chronological_split(dates, 0.6, horizon=horizon, embargo=embargo)
    prices = pd.DataFrame({"A": range(1, 101), "B": range(101, 201)}, index=dates)
    before = forward_returns(prices, horizon).loc[split.dev_dates]
    changed = prices.copy()
    changed.loc[split.confirm_dates] *= 2
    pd.testing.assert_frame_equal(before, forward_returns(changed, horizon).loc[split.dev_dates])


@pytest.mark.parametrize("horizon,embargo", [(0, 0), (1, -1)])
def test_split_rejects_invalid_label_horizon_and_embargo(horizon, embargo):
    with pytest.raises(ValueError, match="must be >="):
        chronological_split(pd.bdate_range("2024-01-01", periods=100), 0.6, horizon, embargo)


def test_search_recovers_planted_signal_and_records_every_trial(bars):
    result = run_search(build_panel(bars), n_trials=60, seed=1, top_k=3)
    assert len(result.ledger) == 60 + 7  # random proposals + templates, none dropped
    assert result.ledger["selected"].sum() == len(result.family) == 3
    best = result.confirmation.iloc[0]
    assert best["expression"] == "((close / delay(close, 5)) - 1.0)"
    assert best["orientation"] == -1  # reversal: chosen on development data
    assert best["status"] == "confirmation_passed"
    assert set(result.confirmation["status"]) <= {"confirmation_passed", "rejected", "inconclusive"}


def test_search_on_null_market_does_not_confirm_noise():
    null = synthetic_market(
        SyntheticConfig(n_instruments=40, n_days=400, seed=3, reversal_strength=0.0)
    )
    result = run_search(build_panel(null), n_trials=60, seed=2, top_k=5)
    assert (result.confirmation["status"] == "confirmation_passed").sum() <= 1


def _factor() -> FrozenFactor:
    return FrozenFactor(
        expression="-(close / delay(close, 5) - 1)",
        orientation=1,
        horizon_days=1,
        training_start="2020-01-01",
        training_end="2020-06-30",
        dataset_id="d",
        dataset_sha256=None,
    )


def test_artifact_round_trip_and_integrity(tmp_path):
    f = _factor()
    path = f.save(tmp_path / "f.json")
    assert FrozenFactor.load(path) == f
    raw = json.loads(path.read_text())
    raw["orientation"] = -1
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="factor_id"):
        FrozenFactor.load(path)
    raw["orientation"], raw["operator_version"] = 1, "0"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="operator_version"):
        FrozenFactor.load(path)


def test_scores_are_causal_and_only_for_trading_instruments(bars):
    f = _factor()
    full = compute_scores(f, bars)
    cut = pd.Timestamp(sorted(bars["date"].unique())[200])
    part = compute_scores(f, bars[bars["date"] <= cut])
    pd.testing.assert_frame_equal(full[full["decision_date"] <= cut].reset_index(drop=True), part)
    keys = set(zip(bars["date"], bars["instrument"], strict=True))
    assert all(k in keys for k in zip(full["decision_date"], full["instrument"], strict=True))


def test_export_signals_bundle(tmp_path, bars):
    f = _factor()
    export_signals(f, bars, tmp_path / "sig", dataset_id="d", start="2020-06-01")
    manifest, sig = read_signals(tmp_path / "sig")
    assert sig["decision_date"].min() >= pd.Timestamp("2020-06-01")
    assert manifest.metadata["factor_id"] == f.factor_id
    assert manifest.metadata["available_at"] == "decision_date_close"


@pytest.mark.parametrize("invalid", [True, 2.9, 0])
def test_export_does_not_coerce_or_drop_invalid_search_trial_counts(tmp_path, bars, invalid):
    factor = replace(_factor(), selection={"n_proposals": invalid})
    with pytest.raises(BundleError, match="n_trials must be a positive integer"):
        export_signals(factor, bars, tmp_path / "signals", dataset_id="d")
    assert not (tmp_path / "signals").exists()


def test_scores_respect_universe(bars):
    from invest_data.sources import synthetic_universe

    uni = synthetic_universe(bars, seed=11)
    scores = compute_scores(_factor(), bars, universe=uni)
    for row in scores.sample(200, random_state=0).itertuples():
        spans = uni[uni["instrument"] == row.instrument]
        inside = (spans["start_date"] <= row.decision_date) & (
            spans["end_date"].isna() | (row.decision_date < spans["end_date"])
        )
        assert inside.any()
    assert len(scores) < len(compute_scores(_factor(), bars))
