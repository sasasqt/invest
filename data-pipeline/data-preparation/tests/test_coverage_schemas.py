"""Refusals of the dataset-kind readers and writers that no other test reached.

Expected messages are the ones each check documents; every case calls a public function of
`invest_data`, as a caller would.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from invest_data.bundle import BundleError, write_bundle
from invest_data.schemas import (
    FACTOR_EVIDENCE_STATISTICS,
    UNIVERSE_COLUMNS,
    UNIVERSE_PRIMARY_KEY,
    non_real,
    publish_fundamentals,
    publish_market_bars,
    publish_signals,
    publish_universe,
    read_fundamentals,
    read_signals,
    read_universe,
    validate_factor_evidence,
)
from invest_data.sources import SYNTHETIC_METADATA

D = pd.Timestamp
SIGNAL_METADATA = {"factor_id": "f", "horizon_days": 1}


def _universe(path: Path) -> Path:
    rows = [{"universe": "u", "instrument": "A", "start_date": D("2024-01-02"), "end_date": None}]
    publish_universe(pd.DataFrame(rows), path, dataset_id="u")
    return path


def _signals(path: Path) -> Path:
    rows = [{"decision_date": D("2024-01-02"), "instrument": "A", "score": 1.0}]
    publish_signals(pd.DataFrame(rows), path, dataset_id="s", metadata=SIGNAL_METADATA)
    return path


def test_a_kind_reader_refuses_a_bundle_whose_columns_are_in_another_order(
    tmp_path: Path,
) -> None:
    rows = [{"universe": "u", "instrument": "A", "start_date": D("2024-01-02"), "end_date": None}]
    columns = tuple(reversed(UNIVERSE_COLUMNS))
    write_bundle(
        pd.DataFrame(rows)[[c.name for c in columns]],
        tmp_path / "u",
        dataset_id="u",
        columns=columns,
        primary_key=UNIVERSE_PRIMARY_KEY,
        dataset_kind="universe",
        metadata={"interval": "start_date <= date < end_date"},
    )
    with pytest.raises(BundleError, match=r"^universe: columns \[\('end_date'"):
        read_universe(tmp_path / "u")


@pytest.mark.parametrize(
    "values",
    [[1.5, -2.0, np.nan], [3, 0, -7]],
    ids=["float", "integer"],
)
def test_non_real_marks_no_value_of_a_real_column(values: list[float]) -> None:
    # Floats and integers are quantities; only booleans and complex numbers are not.
    assert non_real(pd.Series(values)).tolist() == [False] * len(values)


def test_factor_evidence_refuses_a_confirmation_date_that_does_not_exist() -> None:
    evidence: dict[str, Any] = {
        "evidence_version": 2,
        "factor_id": "f",
        "horizon_days": 1,
        "experiment_id": "e_1",
        "source": "search",
        "confirmation_use": "confirmatory",
        "test_outcome": "rejected",
        "status": "rejected",
        "family_size": 3,
        "confirmation_window": {"start": "2024-01-01", "end": "2024-02-30"},
        # Every statistic undefined (null) but present, so only the date is wrong.
        "statistics": dict.fromkeys(FACTOR_EVIDENCE_STATISTICS),
    }
    with pytest.raises(BundleError, match="confirmation_window must have ISO start <= end"):
        validate_factor_evidence(evidence)


def test_market_bars_refuse_negative_volume(tmp_path: Path) -> None:
    bar = {"date": D("2024-01-02"), "instrument": "A", "open": 10.0, "high": 11.0}
    rows = [{**bar, "low": 9.0, "close": 10.5, "volume": -1.0}]
    with pytest.raises(BundleError, match="market_bars: volume must be non-negative"):
        publish_market_bars(
            pd.DataFrame(rows), tmp_path / "m", dataset_id="m", metadata=SYNTHETIC_METADATA
        )
    assert not (tmp_path / "m").exists()


def test_signals_refuse_another_availability_convention_when_published(tmp_path: Path) -> None:
    rows = [{"decision_date": D("2024-01-02"), "instrument": "A", "score": 1.0}]
    metadata = {**SIGNAL_METADATA, "available_at": "next_open"}
    with pytest.raises(BundleError, match="only available_at='decision_date_close'"):
        publish_signals(pd.DataFrame(rows), tmp_path / "s", dataset_id="s", metadata=metadata)
    assert not (tmp_path / "s").exists()


def test_signals_refuse_another_availability_convention_when_read(tmp_path: Path) -> None:
    path = _signals(tmp_path / "s")
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    manifest["metadata"]["available_at"] = "next_open"
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BundleError, match="signals: unsupported available_at convention"):
        read_signals(path)


def test_signals_and_fundamentals_readers_refuse_another_kind(tmp_path: Path) -> None:
    path = _universe(tmp_path / "u")
    with pytest.raises(BundleError, match="expected dataset_kind 'signals', got 'universe'"):
        read_signals(path)
    with pytest.raises(BundleError, match="expected dataset_kind 'fundamentals', got 'universe'"):
        read_fundamentals(path)


@pytest.mark.parametrize("field", ["Book_to_price", "1bp", "book-to-price", ""])
def test_fundamentals_refuse_field_names_outside_the_documented_pattern(
    tmp_path: Path, field: str
) -> None:
    rows = [
        {
            "instrument": "A",
            "field": field,
            "period_end": D("2023-12-31"),
            "available_date": D("2024-02-01"),
            "value": 0.5,
        }
    ]
    with pytest.raises(BundleError, match=r"field names must match \[a-z\]\[a-z0-9_\]\*"):
        publish_fundamentals(pd.DataFrame(rows), tmp_path / "f", dataset_id="f")
    assert not (tmp_path / "f").exists()
