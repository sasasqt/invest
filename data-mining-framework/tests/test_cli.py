import json

import pandas as pd
import pytest

from invest_data.cli import main as data_main
from invest_data.schemas import read_signals
from invest_mining.cli import main


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

    # --from-search: best confirmed factor, exported from the confirmation start.
    confirmation = pd.read_csv(tmp_path / "se" / "confirmation.csv")
    passed = confirmation[confirmation["status"] == "confirmation_passed"]
    best = passed.sort_values(["p_holm", "confirm_t"], ascending=[True, False]).iloc[0]
    best = best["factor_id"]
    split = json.loads((tmp_path / "se" / "config.json").read_text())["split"]
    common = ["export", "--data", str(data), "--from-search", str(tmp_path / "se")]
    assert main([*common, "--out", str(tmp_path / "auto")]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["factor_id"] == best and printed["start"] == split["confirmation"][0]
    manifest, auto = read_signals(tmp_path / "auto")
    assert auto["decision_date"].min() >= pd.Timestamp(split["confirmation"][0])
    assert manifest.metadata["n_trials"] == 20 + 7

    with pytest.raises(SystemExit, match="precedes the confirmation period"):
        main([*common, "--start", split["development"][0], "--out", str(tmp_path / "early")])
    with pytest.raises(SystemExit, match="cannot export rank"):
        main([*common, "--rank", str(len(passed) + 1), "--out", str(tmp_path / "none")])
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
