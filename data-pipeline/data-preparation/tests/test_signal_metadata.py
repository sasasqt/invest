"""Signals carry validated trial counts across the producer/consumer boundary."""

import json

import pandas as pd
import pytest

from invest_data.bundle import BundleError
from invest_data.schemas import publish_signals, read_signals


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
