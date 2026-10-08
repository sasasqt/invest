import json

import pandas as pd
import pytest

from invest_data.cli import main as data_main
from invest_data.schemas import read_market_bars, read_signals
from invest_mining.cli import main


def test_evaluate_applies_and_records_frozen_orientation(tmp_path, bars):
    from invest_data.schemas import publish_market_bars
    from invest_data.sources import SYNTHETIC_METADATA

    data = tmp_path / "data"
    publish_market_bars(bars, data, dataset_id="m", metadata=SYNTHETIC_METADATA)
    reports = []
    for orientation in (1, -1):
        out = tmp_path / str(orientation)
        assert (
            main(
                [
                    "evaluate",
                    "--data",
                    str(data),
                    "--expr",
                    "close / delay(close, 5) - 1",
                    "--orientation",
                    str(orientation),
                    "--horizon",
                    "5",
                    "--out",
                    str(out),
                ]
            )
            == 0
        )
        config = json.loads((out / "config.json").read_text())
        metrics = json.loads((out / "metrics.json").read_text())
        assert config["orientation"] == metrics["orientation"] == orientation
        reports.append(metrics)
    assert reports[1]["mean_ic"] == pytest.approx(-reports[0]["mean_ic"])


def test_cli_evaluate_search_export(tmp_path, capsys):
    data = tmp_path / "data"
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "260"])
    assert (
        main(
            [
                "evaluate",
                "--data",
                str(data),
                "--expr",
                "-delta(close, 5)",
                "--out",
                str(tmp_path / "ev"),
            ]
        )
        == 0
    )
    metrics = json.loads((tmp_path / "ev" / "metrics.json").read_text())
    assert metrics["hac_test"]["status"] == "ok"
    assert (tmp_path / "ev" / "figures" / "ic.png").stat().st_size > 0
    assert (
        main(
            [
                "search",
                "--data",
                str(data),
                "--trials",
                "20",
                "--top-k",
                "2",
                "--out",
                str(tmp_path / "se"),
            ]
        )
        == 0
    )
    factors = sorted((tmp_path / "se" / "factors").glob("*.json"))
    assert len(factors) == 2
    assert (
        main(
            [
                "export",
                "--data",
                str(data),
                "--factor",
                str(factors[0]),
                "--out",
                str(tmp_path / "sig"),
            ]
        )
        == 0
    )
    _, sig = read_signals(tmp_path / "sig")
    assert len(sig) > 0
    capsys.readouterr()

    # --from-search follows the family order frozen before confirmation.
    confirmation = pd.read_csv(tmp_path / "se" / "confirmation.csv")
    best = confirmation.iloc[0]["factor_id"]
    split = json.loads((tmp_path / "se" / "config.json").read_text())["split"]
    common = ["export", "--data", str(data), "--from-search", str(tmp_path / "se")]
    assert main([*common, "--out", str(tmp_path / "auto")]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["factor_id"] == best and printed["start"] == split["confirmation"][0]
    manifest, auto = read_signals(tmp_path / "auto")
    assert auto["decision_date"].min() >= pd.Timestamp(split["confirmation"][0])
    assert manifest.metadata["n_trials"] == 20 + 7

    # Future confirmation outcomes cannot change the exported winner or earlier scores.
    edited = ["status", "test_outcome", "p_holm", "confirm_t"]
    confirmation.loc[0, edited] = ["rejected", "rejected", 1.0, -100.0]
    confirmation.loc[1, edited] = ["confirmation_passed", "confirmation_passed", 1e-12, 100.0]
    confirmation.to_csv(tmp_path / "se" / "confirmation.csv", index=False)
    assert main([*common, "--out", str(tmp_path / "changed")]) == 0
    changed_manifest, changed = read_signals(tmp_path / "changed")
    assert changed_manifest.metadata["factor_id"] == best
    pd.testing.assert_frame_equal(changed, auto)
    # The edited outcome is reported as evidence, after the factor was chosen.
    assert changed_manifest.metadata["factor_evidence"]["status"] == "rejected"
    assert main([*common, "--rank", "2", "--out", str(tmp_path / "second")]) == 0
    assert (
        read_signals(tmp_path / "second")[0].metadata["factor_id"]
        == confirmation.iloc[1]["factor_id"]
    )

    with pytest.raises(SystemExit, match="precedes the confirmation period"):
        main([*common, "--start", split["development"][0], "--out", str(tmp_path / "early")])
    with pytest.raises(SystemExit, match="cannot export rank"):
        main([*common, "--rank", str(len(confirmation) + 1), "--out", str(tmp_path / "none")])
    with pytest.raises(SystemExit):  # --factor and --from-search are exclusive
        main([*common, "--factor", str(factors[0]), "--out", str(tmp_path / "both")])


def test_search_with_no_qualifying_candidates_writes_structured_results(tmp_path, capsys):
    from invest_data.schemas import publish_market_bars
    from invest_data.sources import SYNTHETIC_METADATA

    dates = pd.bdate_range("2024-01-01", periods=100)
    bars = pd.DataFrame(
        [(d, f"A{i}", 10.0, 10.0, 10.0, 10.0, 1e6) for d in dates for i in range(10)],
        columns=["date", "instrument", "open", "high", "low", "close", "volume"],
    )
    publish_market_bars(bars, tmp_path / "data", dataset_id="constant", metadata=SYNTHETIC_METADATA)
    assert (
        main(
            [
                "search",
                "--data",
                str(tmp_path / "data"),
                "--trials",
                "0",
                "--out",
                str(tmp_path / "search"),
            ]
        )
        == 0
    )
    result = pd.read_csv(tmp_path / "search" / "confirmation.csv")
    assert result.empty and {"factor_id", "p_holm", "status", "test_status"} <= set(result.columns)
    ledger = pd.read_csv(tmp_path / "search" / "ledger.csv")
    assert len(ledger) == 7 and (ledger["status"] == "rejected").all()
    assert ledger["reason"].notna().all()
    assert "No candidates qualified" in capsys.readouterr().out
    with pytest.raises(SystemExit, match=r"0 factor.*frozen family"):
        main(
            [
                "export",
                "--data",
                str(tmp_path / "data"),
                "--from-search",
                str(tmp_path / "search"),
                "--out",
                str(tmp_path / "signals"),
            ]
        )
    assert not (tmp_path / "signals").exists()


def test_cli_freeze_fixed_formula_exports_one_trial(tmp_path, capsys):
    data, factor, sig = tmp_path / "data", tmp_path / "f.json", tmp_path / "sig"
    data_main(["synthetic", "--out", str(data), "--instruments", "15", "--days", "60"])
    expr = "close / delay(close, 5) - 1"
    args = ["freeze", "--expr", expr, "--horizon", "5", "--orientation", "-1", "--out", str(factor)]
    assert main(args) == 0
    frozen = json.loads(factor.read_text())
    assert frozen["orientation"] == -1 and frozen["horizon_days"] == 5
    assert frozen["selection"]["method"] == "fixed_formula"
    assert main(["export", "--data", str(data), "--factor", str(factor), "--out", str(sig)]) == 0
    manifest, signals = read_signals(sig)
    assert manifest.metadata["n_trials"] == 1 and manifest.metadata["horizon_days"] == 5
    _, bars = read_market_bars(data)
    close = bars.pivot(index="date", columns="instrument", values="close")
    expected = -(close / close.shift(5) - 1)
    row = signals.iloc[-1]
    assert row["score"] == pytest.approx(expected.loc[row["decision_date"], row["instrument"]])
    with pytest.raises(SystemExit):
        main(["freeze", "--expr", expr, "--horizon", "0", "--out", str(factor)])
    with pytest.raises(ValueError):
        main(["freeze", "--expr", "close + nope(", "--horizon", "1", "--out", str(factor)])


def test_evaluate_skips_small_dates_with_the_portfolios_minimum_cross_section(tmp_path):
    data = tmp_path / "data"
    data_main(["synthetic", "--out", str(data), "--instruments", "12", "--days", "80"])
    args = ["evaluate", "--data", str(data), "--expr", "close", "--horizon", "1"]
    for minimum, expected in (("1", 10), ("11", 11), ("13", 13)):
        out = tmp_path / minimum
        assert main([*args, "--min-cross-section", minimum, "--out", str(out)]) == 0
        assert json.loads((out / "config.json").read_text())["min_cross_section"] == expected
        deciles = pd.read_csv(out / "tables/quantile_returns.csv", index_col=0)
        tails = pd.read_csv(out / "tables/tail_returns.csv", index_col=0)
        skipped = tails["reason"] == "no_date_with_enough_scored_names"
        if expected > 12:  # more than the twelve names: no date is used
            assert deciles.isna().all().all() and skipped.all()
        else:
            assert deciles.notna().any().any() and not skipped.any()
    book = tmp_path / "ledger.jsonl"
    for flag in ("--min-cross-section", "--buckets", "--min-tail-names"):
        with pytest.raises(SystemExit):
            main([*args, flag, "0", "--ledger", str(book), "--out", str(tmp_path / "bad")])
    assert not book.exists()  # rejected before the ledger records an inspection


@pytest.mark.parametrize("adjustment", ["unadjusted"])
def test_every_command_refuses_bars_without_split_adjusted_closes(tmp_path, bars, adjustment):
    """N1: features and forward returns from unadjusted closes treat a split as a crash."""
    from invest_data.schemas import publish_market_bars
    from invest_data.sources import SYNTHETIC_METADATA

    data = tmp_path / "data"
    metadata = {**SYNTHETIC_METADATA, "price_adjustment": adjustment}
    publish_market_bars(bars, data, dataset_id="m", metadata=metadata)
    factor = tmp_path / "f.json"
    expr = "close / delay(close, 5) - 1"
    assert main(["freeze", "--expr", expr, "--horizon", "1", "--out", str(factor)]) == 0
    book = tmp_path / "ledger.jsonl"
    commands = {
        "evaluate": ["--expr", expr, "--ledger", str(book)],
        "search": ["--trials", "5", "--ledger", str(book)],
        "confirm": [
            "--factor",
            str(factor),
            "--confirm-start",
            "2020-09-01",
            "--ledger",
            str(book),
        ],
        "export": ["--factor", str(factor)],
    }
    for command, extra in commands.items():
        with pytest.raises(SystemExit, match="is not supported"):
            main([command, "--data", str(data), *extra, "--out", str(tmp_path / command)])
        assert not (tmp_path / command).exists()
    assert not book.exists()  # refused before any inspection was recorded
