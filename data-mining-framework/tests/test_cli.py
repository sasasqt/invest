import json

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
