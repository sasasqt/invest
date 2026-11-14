"""Dataset-kind readers require their kind's primary key (K14, REVIEW-16).

The generic reader enforces only the key a manifest declares, so a bundle written with
the kind's columns but no key held duplicate rows that every kind reader accepted.
"""

import pandas as pd
import pytest

from invest_data.bundle import BundleError, write_bundle
from invest_data.schemas import (
    FUNDAMENTAL_COLUMNS,
    FUNDAMENTAL_PRIMARY_KEY,
    MARKET_BAR_COLUMNS,
    MARKET_BAR_PRIMARY_KEY,
    SIGNAL_COLUMNS,
    SIGNAL_PRIMARY_KEY,
    UNIVERSE_COLUMNS,
    UNIVERSE_PRIMARY_KEY,
    read_fundamentals,
    read_market_bars,
    read_signals,
    read_universe,
)
from invest_data.sources import SYNTHETIC_METADATA

D = pd.Timestamp
BAR = {"date": D("2024-01-02"), "instrument": "A", "open": 10.0, "high": 11.0, "low": 9.0}
KINDS = {
    "market_bars": (
        MARKET_BAR_COLUMNS,
        MARKET_BAR_PRIMARY_KEY,
        SYNTHETIC_METADATA,
        read_market_bars,
        [{**BAR, "close": 10.5, "volume": 100.0}, {**BAR, "close": 9.5, "volume": 100.0}],
    ),
    "signals": (
        SIGNAL_COLUMNS,
        SIGNAL_PRIMARY_KEY,
        {
            "available_at": "decision_date_close",
            "signal_type": "score",
            "factor_id": "f",
            "horizon_days": 1,
        },
        read_signals,
        [{"decision_date": D("2024-01-02"), "instrument": "A", "score": s} for s in (1.0, -1.0)],
    ),
    "universe": (
        UNIVERSE_COLUMNS,
        UNIVERSE_PRIMARY_KEY,
        {"interval": "start_date <= date < end_date"},
        read_universe,
        [
            {"universe": "u", "instrument": "A", "start_date": D("2024-01-02"), "end_date": end}
            for end in (D("2024-02-01"), D("2024-03-01"))
        ],
    ),
    "fundamentals": (
        FUNDAMENTAL_COLUMNS,
        FUNDAMENTAL_PRIMARY_KEY,
        {"available_at": "available_date_close"},
        read_fundamentals,
        [
            {
                "instrument": "A",
                "field": "bp",
                "period_end": D("2023-12-31"),
                "available_date": D("2024-02-01"),
                "value": v,
            }
            for v in (0.5, 5.0)
        ],
    ),
}


def _write(tmp_path, kind, rows, primary_key):
    columns, _, metadata, _, _ = KINDS[kind]
    write_bundle(
        pd.DataFrame(rows),
        tmp_path / kind,
        dataset_id="x",
        columns=columns,
        primary_key=primary_key,
        dataset_kind=kind,
        metadata=metadata,
    )
    return tmp_path / kind


@pytest.mark.parametrize("kind", KINDS)
def test_a_kind_reader_refuses_a_bundle_without_its_key(tmp_path, kind):
    _, _, _, reader, rows = KINDS[kind]
    path = _write(tmp_path, kind, rows, primary_key=())  # two rows with the same key
    with pytest.raises(BundleError, match="primary key must be"):
        reader(path)


@pytest.mark.parametrize("kind", KINDS)
def test_a_kind_reader_refuses_a_narrower_or_wider_key(tmp_path, kind):
    columns, key, _, reader, rows = KINDS[kind]
    narrower = key[:-1]
    wider = (*key, next(c.name for c in columns if c.name not in key))
    for name, declared in (("narrower", narrower), ("wider", wider)):
        path = _write(tmp_path / name, kind, rows[:1], primary_key=declared)
        with pytest.raises(BundleError, match="primary key must be"):
            reader(path)


@pytest.mark.parametrize("kind", KINDS)
def test_a_kind_reader_accepts_its_key_in_any_order(tmp_path, kind):
    _, key, _, reader, rows = KINDS[kind]
    path = _write(tmp_path, kind, rows[:1], primary_key=tuple(reversed(key)))
    assert len(reader(path)[1]) == 1
