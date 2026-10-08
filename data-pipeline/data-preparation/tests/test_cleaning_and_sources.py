import json

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


@pytest.mark.parametrize("fmt", ["csv", "sqlite", "parquet"])
def test_as_traded_close_is_optional_and_validated(tmp_path, fmt):
    raw = raw_rows().assign(close_as_traded=lambda f: f["close"] * 10)
    raw.loc[len(raw)] = ["2024-01-08", "CCC", 10, 11, 9, 10.5, 100, 0.0]
    raw.loc[len(raw)] = ["2024-01-08", "DDD", 10, 11, 9, 10.5, 100, None]
    raw.loc[len(raw)] = ["2024-01-08", "EEE", 10, 11, 9, 10.5, 100, float("inf")]
    raw.loc[len(raw)] = ["2024-01-08", "FFF", 10, 11, 9, 10.5, 100, "12.3x"]
    raw.loc[len(raw)] = ["2024-01-08", "GGG", 10, 11, 9, 10.5, 100, " "]
    raw.loc[len(raw)] = ["2024-01-08", "HHH", 10, 11, 9, 10.5, 100, "N/A"]
    raw.loc[len(raw)] = ["2024-01-08", "III", 10, 11, 9, 10.5, 100, "Null"]
    raw.loc[len(raw)] = ["2024-01-08", "JJJ", 10, 11, 9, 10.5, 100, True]
    clean, report = clean_bars(raw)
    # The optional column never costs a bar: a null marker means unknown, and any other
    # value that is not a positive number is nulled and counted.
    assert clean["instrument"].tolist() == ["AAA", *(c * 3 for c in "CDEFGHIJ")]
    assert clean["close_as_traded"].iloc[0] == 105.0
    assert clean["close_as_traded"].iloc[1:].isna().all()
    assert set(report.rejected["instrument"]) == {"AAA", "BBB", " "}  # required-column faults
    nulled = report.summary()["nulled_invalid_values"]
    assert nulled == {"close_as_traded": 4}  # CCC, EEE, FFF and the boolean JJJ
    assert "nulled_invalid_values" not in clean_bars(raw_rows())[1].summary()
    clean = clean.iloc[:2]

    publish_market_bars(clean, tmp_path / "m", dataset_id="x", metadata=SYNTHETIC_METADATA, fmt=fmt)
    manifest, back = read_market_bars(tmp_path / "m")
    assert manifest.column_names[-1] == "close_as_traded"
    assert back["close_as_traded"].iloc[0] == 105.0 and pd.isna(back["close_as_traded"].iloc[1])
    for column, bad in (("volume", True), ("close_as_traded", 5 + 1j), ("close", "1.5")):
        with pytest.raises(BundleError, match="must hold real numbers"):
            publish_market_bars(
                clean.assign(**{column: bad}),
                tmp_path / "b",
                dataset_id="x",
                metadata=SYNTHETIC_METADATA,
            )
    # pandas' nullable floats are accepted, nulls included.
    nullable = clean.assign(close_as_traded=pd.array([105.0, None], dtype="Float64"))
    publish_market_bars(nullable, tmp_path / "f", dataset_id="x", metadata=SYNTHETIC_METADATA)
    assert read_market_bars(tmp_path / "f")[1]["close_as_traded"].isna().tolist() == [False, True]
    # The declared adjustment must be one the contract names.
    for adjustment in ("split-adjusted", None):
        with pytest.raises(BundleError, match="is not one of"):
            publish_market_bars(
                clean,
                tmp_path / "a",
                dataset_id="x",
                metadata={**SYNTHETIC_METADATA, "price_adjustment": adjustment},
            )
    for bad, match in ((0.0, "positive"), (-1.0, "positive"), (float("inf"), "close_as_traded")):
        with pytest.raises(BundleError, match=match):
            publish_market_bars(
                clean.assign(close_as_traded=bad),
                tmp_path / f"bad{bad}",
                dataset_id="x",
                metadata=SYNTHETIC_METADATA,
                fmt=fmt,
            )


def test_import_csv_and_synthetic_publish_as_traded_closes(tmp_path, capsys):
    src = tmp_path / "in.csv"
    src.write_text(
        "date,instrument,open,high,low,close,volume,close_as_traded\n"
        "2024-01-02,AAA,1,2,0.5,1.5,10,15\n"
        "2024-01-02,BBB,1,2,0.5,1.5,10,\n"
        "2024-01-02,CCC,1,2,0.5,1.5,10,1.5x\n"
        "2024-01-02,DDD,1,2,0.5,1.5,10,NA\n"
        "2024-01-02,EEE,1,2,0.5,1.5,10,0\n"
    )
    args = ["--currency", "USD", "--calendar", "XNYS", "--price-adjustment", "split_adjusted"]
    assert (
        main(["import-csv", str(src), "--out", str(tmp_path / "m"), "--dataset-id", "m", *args])
        == 0
    )
    printed = json.loads(capsys.readouterr().out)
    assert printed["rejected_rows"] == 0
    assert printed["nulled_invalid_values"] == {"close_as_traded": 2}  # CCC and EEE
    _, frame = read_market_bars(tmp_path / "m")
    assert frame["instrument"].tolist() == ["AAA", "BBB", "CCC", "DDD", "EEE"]
    assert frame["close_as_traded"].iloc[0] == 15.0
    assert frame["close_as_traded"].iloc[1:].isna().all()
    # The loader leaves parsing to cleaning; publishing its raw output is refused.
    with pytest.raises(BundleError, match="must hold real numbers"):
        publish_market_bars(
            load_csv_bars(src), tmp_path / "raw", dataset_id="r", metadata=SYNTHETIC_METADATA
        )
    assert not (tmp_path / "m.rejected.csv").exists()

    assert (
        main(["synthetic", "--out", str(tmp_path / "s"), "--instruments", "3", "--days", "30"]) == 0
    )
    _, frame = read_market_bars(tmp_path / "s")
    # Synthetic prices have no splits or dividends, so they trade as quoted.
    assert frame["close_as_traded"].equals(frame["close"])


def test_unadjusted_bars_publish_with_a_note_and_are_refused_from_the_manifest(tmp_path, capsys):
    from invest_data.schemas import read_adjusted_market_bars

    src = tmp_path / "in.csv"
    src.write_text("date,instrument,open,high,low,close,volume\n2024-01-02,AAA,1,2,0.5,1.5,10\n")
    args = ["--currency", "USD", "--calendar", "XNYS", "--price-adjustment", "unadjusted"]
    out = tmp_path / "m"
    assert main(["import-csv", str(src), "--out", str(out), "--dataset-id", "m", *args]) == 0
    assert "refuse 'unadjusted' bars" in capsys.readouterr().err
    assert len(read_market_bars(out)[1]) == 1
    # The adjustment is judged from the manifest, before any row is read.
    (out / "data.csv").unlink()
    with pytest.raises(BundleError, match="'unadjusted' is not supported"):
        read_adjusted_market_bars(out)
    # Another kind of bundle is named as such, not as unadjusted bars.
    from invest_data.schemas import publish_universe

    universe = pd.DataFrame(
        {"universe": ["U"], "instrument": ["AAA"], "start_date": ["2024-01-02"], "end_date": [None]}
    )
    publish_universe(universe, tmp_path / "u", dataset_id="u")
    with pytest.raises(BundleError, match="expected dataset_kind 'market_bars'"):
        read_adjusted_market_bars(tmp_path / "u")


def test_one_real_number_rule_for_bar_columns(tmp_path):
    """Booleans and complex numbers are not quantities, wherever they appear."""
    from decimal import Decimal

    from invest_data.schemas import validate_market_frame

    raw = raw_rows().iloc[:1].assign(close_as_traded=5.0)
    rows = pd.concat([raw] * 4, ignore_index=True).astype(object)
    rows["instrument"] = ["A", "B", "C", "D"]
    rows.loc[1, "volume"] = True  # a required column: the bar is rejected
    rows.loc[2, "close_as_traded"] = 5 + 1j  # the optional column: nulled and counted
    rows.loc[3, "close_as_traded"] = True
    clean, report = clean_bars(rows)
    assert clean["instrument"].tolist() == ["A", "C", "D"]
    assert report.rejected[["instrument", "reason"]].values.tolist() == [
        ["B", "missing_or_nonfinite_value"]
    ]
    assert report.summary()["nulled_invalid_values"] == {"close_as_traded": 2}

    # Publication validates from the converted values: Decimal prices are real numbers,
    # while nulls in required columns and infinities anywhere are refused.
    validate_market_frame(clean.assign(close=[Decimal("10.5")] * 3))
    for column, bad in (("close", np.nan), ("volume", None), ("close_as_traded", np.inf)):
        frame = clean.astype({column: object})
        frame.loc[0, column] = bad
        with pytest.raises(BundleError, match=f"{column} must be finite"):
            validate_market_frame(frame)


def test_import_csv_converts_raw_prices_to_total_return_bars(tmp_path, capsys):
    from invest_data.schemas import read_adjusted_market_bars

    src = tmp_path / "raw.csv"
    src.write_text(
        "date,instrument,open,high,low,close,volume,adj\n"
        "2024-01-02,AAA,100,110,90,100,1000,50\n"  # a later 2-for-1 split (or dividends)
        "2024-01-03,AAA,100,110,90,104,1000,52\n"
        "2024-01-03,BBB,10,11,9,10,500,\n"  # no adjusted close: no usable bar
        "2024-01-03,CCC,10,11,9,0,500,5\n"  # a bad raw price is reported as such
        "2024-01-03,DDD,10,11,9,10,500,abc\n"
        "2024-01-03,EEE,10,11,9,10,500,1e-320\n"  # volume / factor would overflow
    )
    args = ["--currency", "USD", "--calendar", "XNYS", "--dataset-id", "m"]
    raw = [*args, "--price-adjustment", "unadjusted", "--adjusted-close", "adj"]
    assert main(["import-csv", str(src), "--out", str(tmp_path / "m"), *raw]) == 0
    assert "note:" not in capsys.readouterr().err
    manifest, frame = read_adjusted_market_bars(tmp_path / "m")  # evaluation accepts it
    assert manifest.metadata["price_adjustment"] == "total_return_adjusted"
    assert manifest.provenance["converted"] == {
        "from": "unadjusted",
        "adjusted_close_column": "adj",
    }
    assert frame["instrument"].tolist() == ["AAA", "AAA"]
    assert frame[["open", "high", "low", "close"]].iloc[0].tolist() == [50.0, 55.0, 45.0, 50.0]
    assert frame["close"].tolist() == [50.0, 52.0]
    assert frame["volume"].tolist() == [2000.0, 2000.0]  # dollar volume is kept
    assert frame["close_as_traded"].tolist() == [100.0, 104.0]  # the raw close as traded
    # The rejected-row report shows the CSV's own values and the rule each row broke.
    rejected = pd.read_csv(tmp_path / "m.rejected.csv")
    assert rejected[["instrument", "close", "reason"]].values.tolist() == [
        ["BBB", 10.0, "invalid_adjusted_close"],
        ["CCC", 0.0, "non_positive_price"],
        ["DDD", 10.0, "invalid_adjusted_close"],
        ["EEE", 10.0, "invalid_adjusted_close"],
    ]
    assert rejected.columns.tolist() == [
        *"date instrument open high low close".split(),
        "volume",
        "adj",
        "reason",
    ]  # the CSV's own columns, no close_as_traded added
    assert rejected["adj"].tolist()[1:] == ["5", "abc", "1e-320"]

    # Split-adjusted prices convert too; they are not as traded, so no close_as_traded.
    split = [*args, "--price-adjustment", "split_adjusted", "--adjusted-close", "adj"]
    assert main(["import-csv", str(src), "--out", str(tmp_path / "s"), *split]) == 0
    assert "close_as_traded" not in read_adjusted_market_bars(tmp_path / "s")[1]

    refused = (
        ("total_return_adjusted", "adj", "converts unadjusted or split_adjusted"),
        ("unadjusted", "missing", "has no column 'missing'"),
        ("unadjusted", "", "has no column ''"),
        ("total_return_adjusted", "missing", "converts unadjusted or split_adjusted"),
        # Naming a bar column would scale by 1 and label raw prices as adjusted.
        ("unadjusted", "close", "'close' is a bar column"),
        ("split_adjusted", "volume", "'volume' is a bar column"),
        ("unadjusted", "date", "'date' is a bar column"),
    )
    for adjustment, column, message in refused:
        flags = [*args, "--price-adjustment", adjustment, "--adjusted-close", column]
        with pytest.raises(SystemExit, match=message):
            main(["import-csv", str(src), "--out", str(tmp_path / "x"), *flags])
    both = tmp_path / "both.csv"
    both.write_text("date,instrument,open,high,low,close,volume,adj,close_as_traded\n")
    with pytest.raises(SystemExit, match="already have a close_as_traded column"):
        main(["import-csv", str(both), "--out", str(tmp_path / "x"), *raw])
    assert not (tmp_path / "x").exists()

    # Conversion is explicit: a stray adjusted-close-like column changes nothing.
    stray = load_csv_bars(src, extra_columns=["adj"]).rename(columns={"adj": "adjusted_close"})
    clean, _ = clean_bars(stray)
    assert clean.loc[clean["instrument"] == "AAA", "close"].tolist() == [100.0, 104.0]


def test_clean_bars_refuses_misused_conversion_arguments():
    raw = raw_rows().assign(adj=1.0, reason=1.0)
    for column in ("close", "close_as_traded", "reason"):
        with pytest.raises(ValueError, match=f"cannot be the column '{column}'"):
            clean_bars(raw, adjusted_close=column)
    with pytest.raises(ValueError, match="as_traded needs adjusted_close"):
        clean_bars(raw, as_traded=True)
    with pytest.raises(ValueError, match="already have a close_as_traded column"):
        clean_bars(raw.assign(close_as_traded=1.0), adjusted_close="adj", as_traded=True)


def test_clean_bars_matches_rows_by_position_not_index_label():
    """Frames concatenated without ignore_index repeat labels; values must stay on their row."""
    raw = pd.concat([raw_rows().iloc[:1]] * 4)
    raw = raw.assign(instrument=["A", "B", "C", "D"], close_as_traded=["10", "x", "y", "21"])
    raw.index = [0, 0, 1, 1]
    clean, report = clean_bars(raw)
    assert clean["instrument"].tolist() == ["A", "B", "C", "D"]
    assert clean["close_as_traded"].tolist()[::3] == [10.0, 21.0]
    assert clean["close_as_traded"].isna().tolist() == [False, True, True, False]
    assert report.summary()["nulled_invalid_values"] == {"close_as_traded": 2}


def test_clean_bars_reads_nullable_numeric_columns():
    raw = raw_rows().iloc[:2].assign(volume=[100, 100], instrument=["A", "B"])
    raw = raw.astype({"open": "Float64", "volume": "Int64"})
    raw.loc[1, "open"] = pd.NA
    clean, report = clean_bars(raw)
    assert clean["instrument"].tolist() == ["A"] and clean["volume"].dtype == "float64"
    assert report.summary()["rejected_by_reason"] == {"missing_or_nonfinite_value": 1}


def test_clean_bars_judges_dtypes_not_only_values():
    """Boolean and complex columns are not quantities; categoricals parse like their values."""
    raw = raw_rows().iloc[:2].assign(instrument=["A", "B"], volume=100, close_as_traded=5.0)
    clean, report = clean_bars(raw.assign(volume=[True, True]))
    assert clean.empty
    assert report.summary()["rejected_by_reason"] == {"missing_or_nonfinite_value": 2}
    clean, report = clean_bars(raw.assign(close_as_traded=np.array([5 + 2j, 5 + 0j])))
    assert clean["close_as_traded"].isna().all()
    assert report.summary()["nulled_invalid_values"] == {"close_as_traded": 2}
    clean, _ = clean_bars(raw.astype({"volume": "category"}))  # a single category
    assert clean["volume"].tolist() == [100.0, 100.0]

    from invest_data.schemas import validate_market_frame

    validate_market_frame(clean.astype({"volume": "category", "close_as_traded": "category"}))
    with pytest.raises(BundleError, match="volume must hold real numbers"):
        validate_market_frame(clean.assign(volume=["a", "a"]).astype({"volume": "category"}))
