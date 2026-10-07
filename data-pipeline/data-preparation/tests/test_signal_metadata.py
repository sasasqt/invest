"""Signals carry validated trial counts across the producer/consumer boundary."""

import json

import pandas as pd
import pytest

from invest_data.bundle import BundleError
from invest_data.schemas import publish_signals, read_signals, validate_factor_evidence


def _scores():
    return pd.DataFrame(
        {"decision_date": pd.to_datetime(["2024-01-02"]), "instrument": ["A"], "score": [1.0]}
    )


@pytest.mark.parametrize("fmt", ["csv", "sqlite", "parquet"])
@pytest.mark.parametrize("n_trials", [None, 1, 47])
def test_signal_trial_counts_round_trip_without_coercion(tmp_path, fmt, n_trials):
    metadata = {"factor_id": "f", "horizon_days": 1}
    if n_trials is not None:
        metadata["n_trials"] = n_trials
    publish_signals(_scores(), tmp_path / "signals", dataset_id="s", metadata=metadata, fmt=fmt)
    manifest, _ = read_signals(tmp_path / "signals")
    if n_trials is None:
        assert "n_trials" not in manifest.metadata
    else:
        assert manifest.metadata["n_trials"] == n_trials
        assert type(manifest.metadata["n_trials"]) is int


@pytest.mark.parametrize("invalid", [0, -1, True, False, 2.9, 1.0, "3", None, []])
def test_invalid_trial_counts_fail_before_publication_and_on_external_read(tmp_path, invalid):
    metadata = {"factor_id": "f", "horizon_days": 1, "n_trials": invalid}
    with pytest.raises(BundleError, match="n_trials must be a positive integer"):
        publish_signals(_scores(), tmp_path / "invalid", dataset_id="s", metadata=metadata)
    assert not (tmp_path / "invalid").exists()

    metadata["n_trials"] = 1
    publish_signals(_scores(), tmp_path / "external", dataset_id="s", metadata=metadata)
    path = tmp_path / "external" / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["metadata"]["n_trials"] = invalid
    path.write_text(json.dumps(manifest))
    with pytest.raises(BundleError, match="n_trials must be a positive integer"):
        read_signals(tmp_path / "external")


def _evidence(**changes):
    evidence = {
        "evidence_version": 2,
        "factor_id": "f",
        "horizon_days": 1,
        "experiment_id": "e_1",
        "source": "search",
        "confirmation_use": "confirmatory",
        "test_outcome": "rejected",
        "status": "rejected",
        "family_size": 3,
        "confirmation_window": {"start": "2024-01-01", "end": "2024-06-28"},
        "statistics": {
            "confirm_mean_rank_ic": 0.01,
            "confirm_t": 0.5,
            "p_one_sided": 0.3,
            "p_holm": 0.9,
            "n_dates": 120,
        },
    }
    evidence.update(changes)
    return evidence


@pytest.mark.parametrize("fmt", ["csv", "sqlite", "parquet"])
def test_factor_evidence_round_trips_with_signals(tmp_path, fmt):
    metadata = {"factor_id": "f", "horizon_days": 1, "factor_evidence": _evidence()}
    publish_signals(_scores(), tmp_path / "s", dataset_id="s", metadata=metadata, fmt=fmt)
    assert read_signals(tmp_path / "s")[0].metadata["factor_evidence"] == _evidence()
    # Exploratory use overrides the outcome; undefined statistics are null.
    stats = {**_evidence()["statistics"], "confirm_t": None}
    validate_factor_evidence(
        _evidence(confirmation_use="exploratory", status="exploratory", statistics=stats)
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"evidence_version": 1}, "re-export signals"),
        ({"evidence_version": True}, "evidence_version"),
        ({"evidence_version": 2.0}, "evidence_version"),
        ({"evidence_version": 3}, "evidence_version"),
        ({"factor_id": "g"}, "is for factor 'g'"),
        ({"horizon_days": 5}, "does not match signals"),
        ({"horizon_days": None}, "horizon_days"),
        ({"horizon_days": True}, "horizon_days"),
        ({"horizon_days": 1.0}, "horizon_days"),
        ({"horizon_days": 0}, "horizon_days"),
        ({"experiment_id": ""}, "experiment_id"),
        ({"source": "manual"}, "source"),
        ({"confirmation_use": "fresh"}, "confirmation_use"),
        ({"status": "confirmation_passed"}, "contradicts"),
        ({"confirmation_use": "exploratory"}, "contradicts"),
        ({"confirmation_use": "unrecorded", "status": "exploratory"}, "contradicts"),
        ({"family_size": True}, "family_size"),
        ({"family_size": 0}, "family_size"),
        ({"confirmation_window": {"start": "2024-06-28", "end": "2024-01-01"}}, "window"),
        ({"confirmation_window": {"start": "2024-01-01", "end": None}}, "window"),
        ({"statistics": {"p_holm": 0.1}}, "exactly the keys"),
        ({"statistics": {**_evidence()["statistics"], "p_holm": "0.1"}}, "finite number"),
        ({"statistics": {**_evidence()["statistics"], "confirm_t": float("inf")}}, "finite"),
    ],
)
def test_invalid_factor_evidence_fails_before_publication_and_on_read(tmp_path, changes, message):
    metadata = {"factor_id": "f", "horizon_days": 1, "factor_evidence": _evidence(**changes)}
    with pytest.raises(BundleError, match=message):
        publish_signals(_scores(), tmp_path / "invalid", dataset_id="s", metadata=metadata)
    assert not (tmp_path / "invalid").exists()

    metadata["factor_evidence"] = _evidence()
    publish_signals(_scores(), tmp_path / "external", dataset_id="s", metadata=metadata)
    path = tmp_path / "external" / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["metadata"]["factor_evidence"] = _evidence(**changes)
    path.write_text(json.dumps(manifest))
    with pytest.raises(BundleError, match=message):
        read_signals(tmp_path / "external")


def test_factor_evidence_must_be_an_object():
    with pytest.raises(BundleError, match="JSON object"):
        validate_factor_evidence(["rejected"])


@pytest.mark.parametrize("invalid", [None, True, 1.0, 0, -1, "1"])
def test_invalid_bundle_horizon_cannot_bypass_evidence_binding(tmp_path, invalid):
    metadata = {"factor_id": "f", "horizon_days": invalid, "factor_evidence": _evidence()}
    with pytest.raises(BundleError, match="horizon_days"):
        publish_signals(_scores(), tmp_path / "invalid", dataset_id="s", metadata=metadata)
    assert not (tmp_path / "invalid").exists()
    metadata["horizon_days"] = 1
    publish_signals(_scores(), tmp_path / "external", dataset_id="s", metadata=metadata)
    path = tmp_path / "external/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["metadata"]["horizon_days"] = invalid
    path.write_text(json.dumps(manifest))
    with pytest.raises(BundleError, match="horizon_days"):
        read_signals(tmp_path / "external")


def test_factor_evidence_requires_a_tested_horizon():
    evidence = _evidence()
    del evidence["horizon_days"]
    with pytest.raises(BundleError, match="horizon_days"):
        validate_factor_evidence(evidence)
