"""Signals carry validated trial counts across the producer/consumer boundary."""

import json
from datetime import date

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
    metadata = {"factor_id": "f", "horizon_days": 1, "n_trials": 3, "factor_evidence": _evidence()}
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
        ({"source": "confirm"}, "family_size must be 1"),
        ({"confirmation_window": {"start": "2024-06-28", "end": "2024-01-01"}}, "window"),
        ({"confirmation_window": {"start": "2024-01-01", "end": None}}, "window"),
        ({"statistics": {"p_holm": 0.1}}, "exactly the keys"),
        ({"statistics": {**_evidence()["statistics"], "p_holm": "0.1"}}, "finite number"),
        ({"statistics": {**_evidence()["statistics"], "confirm_t": float("inf")}}, "finite"),
    ],
)
def test_invalid_factor_evidence_fails_before_publication_and_on_read(tmp_path, changes, message):
    metadata = {
        "factor_id": "f",
        "horizon_days": 1,
        "n_trials": 3,
        "factor_evidence": _evidence(**changes),
    }
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
    metadata = {
        "factor_id": "f",
        "horizon_days": invalid,
        "n_trials": 3,
        "factor_evidence": _evidence(),
    }
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


@pytest.mark.parametrize("n_trials", [None, 1, 2])
def test_search_evidence_needs_at_least_its_family_size_in_trials(tmp_path, n_trials):
    """A searched factor re-labelled as one trial cannot keep its search evidence (K8)."""
    metadata = {"factor_id": "f", "horizon_days": 1, "factor_evidence": _evidence()}
    if n_trials is not None:
        metadata["n_trials"] = n_trials
    with pytest.raises(BundleError, match="n_trials >= its family_size"):
        publish_signals(_scores(), tmp_path / "invalid", dataset_id="s", metadata=metadata)
    assert not (tmp_path / "invalid").exists()

    metadata["n_trials"] = 3
    publish_signals(_scores(), tmp_path / "external", dataset_id="s", metadata=metadata)
    path = tmp_path / "external" / "manifest.json"
    manifest = json.loads(path.read_text())
    if n_trials is None:
        del manifest["metadata"]["n_trials"]
    else:
        manifest["metadata"]["n_trials"] = n_trials
    path.write_text(json.dumps(manifest))
    with pytest.raises(BundleError, match="n_trials >= its family_size"):
        read_signals(tmp_path / "external")

    # A fixed formula's own confirmation has a family of one.
    confirm = _evidence(source="confirm", family_size=1)
    fixed = {"factor_id": "f", "horizon_days": 1, "factor_evidence": confirm}
    publish_signals(_scores(), tmp_path / "fixed", dataset_id="s", metadata=fixed)


def test_search_evidence_signals_start_at_the_confirmation_window(tmp_path):
    """Decisions before a search's confirmation window selected the factor (K1)."""
    early = pd.DataFrame(
        {
            "decision_date": pd.to_datetime(["2023-12-29", "2024-01-02"]),
            "instrument": ["A", "A"],
            "score": [1.0, 2.0],
        }
    )
    metadata = {"factor_id": "f", "horizon_days": 1, "n_trials": 3, "factor_evidence": _evidence()}
    with pytest.raises(BundleError, match="precede the search evidence's confirmation window"):
        publish_signals(early, tmp_path / "invalid", dataset_id="s", metadata=metadata)
    assert not (tmp_path / "invalid").exists()

    # The same rows published without evidence, then given the evidence, fail on read.
    plain = {"factor_id": "f", "horizon_days": 1, "n_trials": 3}
    publish_signals(early, tmp_path / "external", dataset_id="s", metadata=plain)
    path = tmp_path / "external" / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["metadata"]["factor_evidence"] = _evidence()
    path.write_text(json.dumps(manifest))
    with pytest.raises(BundleError, match="precede the search evidence's confirmation window"):
        read_signals(tmp_path / "external")

    # Confirm evidence describes a fixed formula: earlier dates selected nothing.
    confirm = _evidence(source="confirm", family_size=1)
    fixed = {"factor_id": "f", "horizon_days": 1, "factor_evidence": confirm}
    publish_signals(early, tmp_path / "fixed", dataset_id="s", metadata=fixed)
    assert read_signals(tmp_path / "fixed")[1]["decision_date"].min() == pd.Timestamp("2023-12-29")


@pytest.mark.parametrize("early", ["2023-12-29", date(2023, 12, 29), pd.Timestamp("2023-12-29")])
def test_search_window_check_covers_every_date_representation(tmp_path, early):
    """The writer accepts strings and date objects too; none may bypass the window check."""
    frame = pd.DataFrame(
        {"decision_date": [early, early], "instrument": ["A", "B"], "score": [1.0, 2.0]}
    )
    metadata = {"factor_id": "f", "horizon_days": 1, "n_trials": 3, "factor_evidence": _evidence()}
    with pytest.raises(BundleError, match="precede the search evidence's confirmation window"):
        publish_signals(frame, tmp_path / "invalid", dataset_id="s", metadata=metadata)
    assert not (tmp_path / "invalid").exists()


@pytest.mark.parametrize(
    "dates",
    [
        ["2024-01-02", "29 Dec 2023"],  # a later value in another format
        [20240102, 20240103],  # integers, which the writer stores as 1970 dates
    ],
)
def test_search_window_check_sees_the_dates_the_writer_stores(tmp_path, dates):
    frame = pd.DataFrame({"decision_date": dates, "instrument": ["A", "B"], "score": [1.0, 2.0]})
    metadata = {"factor_id": "f", "horizon_days": 1, "n_trials": 3, "factor_evidence": _evidence()}
    with pytest.raises(BundleError, match="precede the search evidence's confirmation window"):
        publish_signals(frame, tmp_path / "invalid", dataset_id="s", metadata=metadata)
    assert not (tmp_path / "invalid").exists()


def test_search_window_check_accepts_what_other_evidence_accepts(tmp_path):
    """Mixed time zones after the window publish with search evidence as without it."""
    dates = ["2024-01-03T01:00+09:00", "2024-01-04T00:00-05:00"]
    frame = pd.DataFrame({"decision_date": dates, "instrument": ["A", "B"], "score": [1.0, 2.0]})
    metadata = {"factor_id": "f", "horizon_days": 1, "n_trials": 3, "factor_evidence": _evidence()}
    publish_signals(frame, tmp_path / "s", dataset_id="s", metadata=metadata)
    assert read_signals(tmp_path / "s")[1]["decision_date"].min() == pd.Timestamp("2024-01-03")


def test_search_window_check_leaves_null_dates_to_the_column_checks(tmp_path):
    frame = pd.DataFrame({"decision_date": [pd.NaT], "instrument": ["A"], "score": [1.0]})
    metadata = {"factor_id": "f", "horizon_days": 1, "n_trials": 3, "factor_evidence": _evidence()}
    with pytest.raises(BundleError, match="not nullable"):
        publish_signals(frame, tmp_path / "invalid", dataset_id="s", metadata=metadata)
    assert not (tmp_path / "invalid").exists()
