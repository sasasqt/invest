"""Exported signals carry the factor's confirmation evidence without being chosen by it."""

import json

import pandas as pd
import pytest

from invest_data.cli import main as data_main
from invest_data.schemas import read_signals
from invest_mining.artifact import FrozenFactor
from invest_mining.cli import main


@pytest.fixture
def data(tmp_path):
    path = tmp_path / "data"
    data_main(["synthetic", "--out", str(path), "--instruments", "25", "--days", "260"])
    return path


def _search(data, out, book, seed=0):
    args = ["search", "--data", str(data), "--trials", "10", "--top-k", "2", "--out", str(out)]
    return main([*args, "--seed", str(seed), "--ledger", str(book)])


def _export(data, out, *source):
    return main(["export", "--data", str(data), *source, "--out", str(out)])


def test_from_search_attaches_experiment_identity_use_and_outcome(tmp_path, data):
    book = tmp_path / "ledger.jsonl"
    assert _search(data, tmp_path / "first", book) == 0
    assert _export(data, tmp_path / "sig", "--from-search", str(tmp_path / "first")) == 0
    manifest, _ = read_signals(tmp_path / "sig")
    evidence = manifest.metadata["factor_evidence"]
    table = pd.read_csv(tmp_path / "first" / "confirmation.csv")
    config = json.loads((tmp_path / "first" / "config.json").read_text())
    row = table.iloc[0]
    assert evidence["factor_id"] == manifest.metadata["factor_id"] == row["factor_id"]
    assert evidence["evidence_version"] == 2
    assert evidence["horizon_days"] == manifest.metadata["horizon_days"] == 1
    assert evidence["experiment_id"] == config["experiment"]["experiment_id"]
    assert evidence["source"] == "search" and evidence["family_size"] == len(table)
    assert evidence["confirmation_use"] == "confirmatory"
    assert evidence["status"] == evidence["test_outcome"] == row["status"]
    assert evidence["confirmation_window"] == config["experiment"]["identity"]["confirmation"]
    assert evidence["statistics"]["p_holm"] == pytest.approx(row["p_holm"])
    assert evidence["statistics"]["n_dates"] == row["n_dates"]

    # The same search again reuses its confirmation data: the evidence says exploratory,
    # keeps the raw test outcome, and the exported factor is unchanged.
    assert _search(data, tmp_path / "again", book) == 0
    assert _export(data, tmp_path / "sig2", "--from-search", str(tmp_path / "again")) == 0
    manifest2, _ = read_signals(tmp_path / "sig2")
    reused = manifest2.metadata["factor_evidence"]
    assert manifest2.metadata["factor_id"] == manifest.metadata["factor_id"]
    assert reused["confirmation_use"] == reused["status"] == "exploratory"
    assert reused["test_outcome"] == evidence["test_outcome"]
    assert reused["experiment_id"] == evidence["experiment_id"]  # a repeat of the same identity

    with pytest.raises(SystemExit, match="already attaches"):
        _export(
            data,
            tmp_path / "x",
            "--from-search",
            str(tmp_path / "first"),
            "--confirmation",
            str(tmp_path / "first"),
        )


def test_fixed_formula_takes_evidence_from_its_confirm_run(tmp_path, data):
    book, factor = tmp_path / "ledger.jsonl", tmp_path / "f.json"
    expr = "close / delay(close, 5) - 1"
    freeze = ["freeze", "--expr", expr, "--horizon", "5", "--orientation", "-1"]
    assert main([*freeze, "--out", str(factor)]) == 0
    confirm = ["confirm", "--data", str(data), "--factor", str(factor), "--ledger", str(book)]
    assert main([*confirm, "--confirm-start", "2020-09-01", "--out", str(tmp_path / "c")]) == 0

    # Without --confirmation the signals carry no evidence (reports say not_confirmed).
    assert _export(data, tmp_path / "plain", "--factor", str(factor)) == 0
    assert "factor_evidence" not in read_signals(tmp_path / "plain")[0].metadata

    source = ("--factor", str(factor), "--confirmation", str(tmp_path / "c"))
    assert _export(data, tmp_path / "sig", *source) == 0
    evidence = read_signals(tmp_path / "sig")[0].metadata["factor_evidence"]
    table = pd.read_csv(tmp_path / "c" / "confirmation.csv")
    assert evidence["source"] == "confirm" and evidence["family_size"] == 1
    assert evidence["horizon_days"] == 5
    assert evidence["status"] == table.loc[0, "status"] == "confirmation_passed"
    assert evidence["confirmation_window"]["start"] == "2020-09-01"
    assert evidence["statistics"]["p_one_sided"] == pytest.approx(table.loc[0, "p_one_sided"])

    # Evidence for a different factor is refused.
    other = tmp_path / "g.json"
    assert main(["freeze", "--expr", "close", "--horizon", "1", "--out", str(other)]) == 0
    with pytest.raises(SystemExit, match="was not confirmed in this output"):
        _export(data, tmp_path / "x", "--factor", str(other), "--confirmation", str(tmp_path / "c"))

    # A confirmation table whose status contradicts its use and outcome is refused.
    table.loc[0, "status"] = "rejected"
    table.to_csv(tmp_path / "c" / "confirmation.csv", index=False)
    with pytest.raises(SystemExit, match="contradicts"):
        _export(data, tmp_path / "x", *source)

    # Outputs written before the ledger existed lack the use columns.
    table.drop(columns=["test_outcome", "confirmation_use"]).to_csv(
        tmp_path / "c" / "confirmation.csv", index=False
    )
    with pytest.raises(SystemExit, match="lacks"):
        _export(data, tmp_path / "x", *source)
    assert not (tmp_path / "x").exists()


def test_factor_from_another_experiment_is_refused(tmp_path, data):
    book = tmp_path / "ledger.jsonl"
    assert _search(data, tmp_path / "first", book) == 0
    assert _search(data, tmp_path / "other", book, seed=5) == 0
    member = next((tmp_path / "first" / "factors").glob("*.json"))
    with pytest.raises(SystemExit, match="was selected in experiment"):
        _export(
            data, tmp_path / "x", "--factor", str(member), "--confirmation", str(tmp_path / "other")
        )


def test_fixed_formula_evidence_cannot_be_reused_at_another_horizon(tmp_path, data):
    for horizon in (1, 5):
        assert (
            main(
                [
                    "freeze",
                    "--expr",
                    "close / delay(close, 5) - 1",
                    "--orientation",
                    "-1",
                    "--horizon",
                    str(horizon),
                    "--out",
                    str(tmp_path / f"f{horizon}.json"),
                ]
            )
            == 0
        )
    # Formula identity deliberately excludes the prediction/holding horizon.
    assert (
        FrozenFactor.load(tmp_path / "f1.json").factor_id
        == FrozenFactor.load(tmp_path / "f5.json").factor_id
    )
    assert (
        main(
            [
                "confirm",
                "--data",
                str(data),
                "--factor",
                str(tmp_path / "f1.json"),
                "--confirm-start",
                "2020-09-01",
                "--ledger",
                str(tmp_path / "ledger.jsonl"),
                "--out",
                str(tmp_path / "c"),
            ]
        )
        == 0
    )
    with pytest.raises(SystemExit, match="horizon"):
        _export(
            data,
            tmp_path / "wrong",
            "--factor",
            str(tmp_path / "f5.json"),
            "--confirmation",
            str(tmp_path / "c"),
        )
    assert not (tmp_path / "wrong").exists()
    assert (
        _export(
            data,
            tmp_path / "right",
            "--factor",
            str(tmp_path / "f1.json"),
            "--confirmation",
            str(tmp_path / "c"),
        )
        == 0
    )
    metadata = read_signals(tmp_path / "right")[0].metadata
    assert metadata["factor_evidence"]["horizon_days"] == metadata["horizon_days"] == 1
