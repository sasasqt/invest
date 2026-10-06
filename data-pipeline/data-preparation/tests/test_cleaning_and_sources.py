import numpy as np
import pandas as pd
import pytest

from invest_data.bundle import BundleError
from invest_data.cleaning import clean_bars
from invest_data.cli import main
from invest_data.schemas import publish_market_bars, read_market_bars
from invest_data.sources import SYNTHETIC_METADATA, SyntheticConfig, load_csv_bars, synthetic_market


def raw_rows():
    return pd.DataFrame(
        [
            ["2024-01-02", "AAA", 10, 11, 9, 10.5, 100],  # ok
            ["2024-01-02", "BBB", 10, 11, 9, 10.5, -1],  # negative volume
            ["2024-01-03", "AAA", 10, 9.5, 9, 9.2, 100],  # high below open
            ["2024-01-03", "BBB", 0, 1, 0, 1, 100],  # non-positive
            ["2024-01-04", "AAA", 10, 11, 9, 10, 100],  # duplicate key
            ["2024-01-04", "AAA", 10, 11, 9, 10, 100],  # duplicate key
            ["not a date", "AAA", 10, 11, 9, 10, 100],
            ["2024-01-05", "AAA", 10, 11, 9, None, 100],
            ["2024-01-05", " ", 10, 11, 9, 10, 100],
        ],
        columns=["date", "instrument", "open", "high", "low", "close", "volume"],
    )


def test_clean_bars_rejects_with_reasons():
    clean, report = clean_bars(raw_rows())
    assert clean[["date", "instrument"]].astype(str).values.tolist() == [["2024-01-02", "AAA"]]
    assert report.summary()["rejected_by_reason"] == {
        "duplicate_key": 2,
        "high_below_open_close": 1,
        "invalid_date": 1,
        "missing_instrument": 1,
        "missing_or_nonfinite_value": 1,
        "negative_volume": 1,
        "non_positive_price": 1,
    }
    assert report.input_rows == report.output_rows + len(report.rejected)


def test_clean_bars_is_deterministic_and_order_independent():
    raw = raw_rows()
    a, _ = clean_bars(raw)
    b, _ = clean_bars(raw.sample(frac=1, random_state=3))
    pd.testing.assert_frame_equal(a, b)


def test_synthetic_market_is_deterministic_and_valid(tmp_path):
    cfg = SyntheticConfig(n_instruments=12, n_days=80, seed=1)
    a, b = synthetic_market(cfg), synthetic_market(cfg)
    pd.testing.assert_frame_equal(a, b)
    clean, report = clean_bars(a)
    assert report.summary()["rejected_rows"] == 0
    publish_market_bars(clean, tmp_path / "m", dataset_id="s", metadata=SYNTHETIC_METADATA)
    _, back = read_market_bars(tmp_path / "m")
    assert len(back) == len(a)
    assert back.groupby("instrument")["date"].count().nunique() >= 1


@pytest.mark.parametrize("fmt", ["csv", "sqlite", "parquet"])
def test_market_bars_require_metadata_and_valid_prices(tmp_path, fmt):
    clean, _ = clean_bars(raw_rows())
    with pytest.raises(BundleError, match="metadata"):
        publish_market_bars(clean, tmp_path / "m", dataset_id="x", metadata={}, fmt=fmt)
    assert not (tmp_path / "m").exists()
    publish_market_bars(clean, tmp_path / "m", dataset_id="x", metadata=SYNTHETIC_METADATA, fmt=fmt)
    assert len(read_market_bars(tmp_path / "m")[1]) == len(clean)
    bad = clean.assign(high=clean["low"] - 1)
    with pytest.raises(BundleError, match="high/low"):
        publish_market_bars(bad, tmp_path / "n", dataset_id="x", metadata=SYNTHETIC_METADATA)


def test_load_csv_bars_with_column_map(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("Date,Ticker,O,H,L,C,V\n2024-01-02,AAA,1,2,0.5,1.5,10\n")
    out = load_csv_bars(
        src,
        column_map={
            "Date": "date",
            "Ticker": "instrument",
            "O": "open",
            "H": "high",
            "L": "low",
            "C": "close",
            "V": "volume",
        },
    )
    assert out["close"].tolist() == [1.5] and np.issubdtype(out["date"].dtype, np.datetime64)


@pytest.mark.parametrize("fmt", ["csv", "sqlite", "parquet"])
def test_cli_synthetic_publishes_bundle(tmp_path, fmt, capsys):
    out = tmp_path / "bundle"
    assert (
        main(
            ["synthetic", "--out", str(out), "--format", fmt, "--instruments", "5", "--days", "30"]
        )
        == 0
    )
    manifest, frame = read_market_bars(out)
    assert manifest.storage["format"] == fmt and len(frame) > 0
    assert '"rows"' in capsys.readouterr().out
