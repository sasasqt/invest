"""Exported signals carry the factor's confirmation evidence without being chosen by it."""

import json
import re

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


def _search(data, out, book, seed=0, top_k=2):
    args = ["search", "--data", str(data), "--trials", "10", "--top-k", str(top_k)]
    return main([*args, "--out", str(out), "--seed", str(seed), "--ledger", str(book)])


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


def _two_searches(tmp_path, data):
    """Run two experiments into one ledger; return each one's factor ids.

    Same seed, so both rank the same proposals; the family is chosen greedily in rank order,
    so `other`'s top two are exactly the first two of `first`'s top three. The overlap is
    built in rather than depending on which proposals a seed draws.
    """
    book = tmp_path / "ledger.jsonl"
    assert _search(data, tmp_path / "first", book, top_k=3) == 0
    assert _search(data, tmp_path / "other", book) == 0
    first, other = (
        set(pd.read_csv(tmp_path / name / "confirmation.csv")["factor_id"])
        for name in ("first", "other")
    )
    assert other < first and len(first - other) == 1
    return first, other


def _experiment_id(root):
    return json.loads((root / "config.json").read_text(encoding="utf-8"))["experiment"][
        "experiment_id"
    ]


def test_factor_from_another_experiment_is_refused(tmp_path, data):
    # A factor both searches selected reaches the experiment-identity guard; picking a file
    # by directory order could pick one the other search never tested (REVIEW-22).
    first, other = _two_searches(tmp_path, data)
    shared = sorted(first & other)
    first_id, other_id = _experiment_id(tmp_path / "first"), _experiment_id(tmp_path / "other")
    assert first_id != other_id
    member = tmp_path / "first" / "factors" / f"{shared[0]}.json"
    with pytest.raises(
        SystemExit, match=re.escape(f"was selected in experiment {first_id}, not {other_id}")
    ):
        _export(
            data, tmp_path / "x", "--factor", str(member), "--confirmation", str(tmp_path / "other")
        )
    assert not (tmp_path / "x").exists()


def test_factor_another_search_never_tested_is_refused(tmp_path, data):
    first, other = _two_searches(tmp_path, data)
    only_first = sorted(first - other)
    member = tmp_path / "first" / "factors" / f"{only_first[0]}.json"
    with pytest.raises(SystemExit, match="was not confirmed in this output"):
        _export(
            data, tmp_path / "x", "--factor", str(member), "--confirmation", str(tmp_path / "other")
        )
    assert not (tmp_path / "x").exists()


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


def test_search_evidence_keeps_factor_export_out_of_sample(tmp_path, data):
    """`--factor --confirmation <search>` is guarded like `--from-search` (K1)."""
    book = tmp_path / "ledger.jsonl"
    assert _search(data, tmp_path / "s", book) == 0
    config = json.loads((tmp_path / "s" / "config.json").read_text())
    confirm_start = config["split"]["confirmation"][0]
    family = pd.read_csv(tmp_path / "s" / "confirmation.csv")["factor_id"]
    member = str(tmp_path / "s" / "factors" / f"{family.iloc[0]}.json")
    source = ("--factor", member, "--confirmation", str(tmp_path / "s"))

    early = pd.Timestamp(confirm_start) - pd.Timedelta(days=30)
    with pytest.raises(SystemExit, match="precedes the confirmation period"):
        _export(data, tmp_path / "early", *source, "--start", str(early.date()))
    assert not (tmp_path / "early").exists()

    # Without --start the export begins at the confirmation start, as with --from-search.
    assert _export(data, tmp_path / "sig", *source) == 0
    _, frame = read_signals(tmp_path / "sig")
    assert frame["decision_date"].min() == pd.Timestamp(confirm_start)
    assert _export(data, tmp_path / "auto", "--from-search", str(tmp_path / "s")) == 0
    assert read_signals(tmp_path / "auto")[1].equals(frame)

    for bad in ("2020-13-01", "2020-09-01T12:00", "2020-09-01T00:00Z", "2020-9-1", "20200901"):
        with pytest.raises(SystemExit, match="not a YYYY-MM-DD date"):
            _export(data, tmp_path / "bad", *source, "--start", bad)
        with pytest.raises(SystemExit, match="not a YYYY-MM-DD date"):
            _export(data, tmp_path / "bad", "--factor", member, "--start", bad)
    assert not (tmp_path / "bad").exists()

    # The same factor without evidence may still be exported from any date.
    assert _export(data, tmp_path / "plain", "--factor", member, "--start", str(early.date())) == 0


def test_search_evidence_is_refused_for_a_refrozen_formula(tmp_path, data):
    """A `freeze` copy of a searched formula cannot take the search's evidence (K8)."""
    book = tmp_path / "ledger.jsonl"
    assert _search(data, tmp_path / "s", book) == 0
    family = pd.read_csv(tmp_path / "s" / "confirmation.csv")["factor_id"]
    searched = FrozenFactor.load(tmp_path / "s" / "factors" / f"{family.iloc[0]}.json")
    copy = tmp_path / "copy.json"
    freeze = ["freeze", "--expr", searched.expression, "--orientation", str(searched.orientation)]
    assert main([*freeze, "--horizon", str(searched.horizon_days), "--out", str(copy)]) == 0
    assert FrozenFactor.load(copy).factor_id == searched.factor_id
    with pytest.raises(SystemExit, match="not this search's own factor file"):
        _export(data, tmp_path / "x", "--factor", str(copy), "--confirmation", str(tmp_path / "s"))
    assert not (tmp_path / "x").exists()

    # Any factor file not tagged with the search's experiment is refused the same way.
    raw = json.loads((tmp_path / "s" / "factors" / f"{family.iloc[0]}.json").read_text())
    del raw["selection"]["experiment_id"]
    (tmp_path / "untagged.json").write_text(json.dumps(raw))
    with pytest.raises(SystemExit, match="not this search's own factor file"):
        _export(
            data,
            tmp_path / "x",
            "--factor",
            str(tmp_path / "untagged.json"),
            "--confirmation",
            str(tmp_path / "s"),
        )
    assert not (tmp_path / "x").exists()


@pytest.fixture
def inputs(tmp_path):
    """Market data with a universe and fundamentals, plus bundles that differ from them."""
    # Imported here so the module's import lines stay as they are on main.
    import shutil

    from invest_data.schemas import (
        publish_fundamentals,
        publish_universe,
        read_fundamentals,
        read_universe,
    )

    path = tmp_path / "inputs"
    data_main(
        [
            "synthetic",
            "--out",
            str(path / "market"),
            "--instruments",
            "25",
            "--days",
            "260",
            "--universe-out",
            str(path / "universe"),
            "--fundamentals-out",
            str(path / "fundamentals"),
        ]
    )
    shutil.copytree(path / "universe", path / "universe_copy")
    _, frame = read_universe(path / "universe")
    dropped = sorted(frame["instrument"].unique())[0]
    publish_universe(
        frame[frame["instrument"] != dropped], path / "universe_other", dataset_id="other"
    )
    _, frame = read_fundamentals(path / "fundamentals")
    publish_fundamentals(
        frame[frame["instrument"] != dropped], path / "fundamentals_other", dataset_id="other"
    )
    # A valid bundle whose manifest has no content hash (the hash is optional).
    shutil.copytree(path / "universe", path / "universe_hashless")
    manifest = json.loads(
        (path / "universe_hashless" / "manifest.json").read_text(encoding="utf-8")
    )
    del manifest["content_sha256"]
    (path / "universe_hashless" / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return path


def _universe_hash(path):
    from invest_data.schemas import read_universe

    return read_universe(path)[0].content_sha256


def _search_on(inputs, out, *options):
    book = out.parent / f"{out.name}.jsonl"
    args = ["search", "--data", str(inputs / "market"), "--trials", "10", "--top-k", "2"]
    return main([*args, *options, "--out", str(out), "--seed", "0", "--ledger", str(book)])


def test_search_evidence_needs_the_universe_the_search_used(tmp_path, inputs):
    """The evidence describes scores on the search's universe (BH-2026-10-20-3).

    The experiment identity in config.json records the universe's content hash; scores
    computed without it, or on another universe, include names or ranks it never tested.
    """
    universe = ("--universe", str(inputs / "universe"))
    assert _search_on(inputs, tmp_path / "s", *universe) == 0
    source = ("--from-search", str(tmp_path / "s"))
    for options in [(), ("--universe", str(inputs / "universe_other"))]:
        with pytest.raises(SystemExit, match="--universe"):
            _export(inputs / "market", tmp_path / "x", *source, *options)
        assert not (tmp_path / "x").exists()

    # The same universe content under another path is the same input.
    copy = ("--universe", str(inputs / "universe_copy"))
    assert _export(inputs / "market", tmp_path / "sig", *source, *copy) == 0
    evidence = read_signals(tmp_path / "sig")[0].metadata["factor_evidence"]
    assert evidence["experiment_id"] == _experiment_id(tmp_path / "s")

    # The search's own factor file with --confirmation follows the same rule.
    own = tmp_path / "s" / "factors" / f"{evidence['factor_id']}.json"
    source = ("--factor", str(own), "--confirmation", str(tmp_path / "s"))
    with pytest.raises(SystemExit, match="--universe"):
        _export(inputs / "market", tmp_path / "x", *source)
    assert not (tmp_path / "x").exists()
    assert _export(inputs / "market", tmp_path / "sig2", *source, *copy) == 0


def test_search_without_universe_gives_no_evidence_to_universe_scores(tmp_path, inputs):
    assert _search_on(inputs, tmp_path / "s") == 0
    source = ("--from-search", str(tmp_path / "s"))
    with pytest.raises(SystemExit, match="--universe"):
        _export(inputs / "market", tmp_path / "x", *source, "--universe", str(inputs / "universe"))
    assert not (tmp_path / "x").exists()
    assert _export(inputs / "market", tmp_path / "sig", *source) == 0


def test_search_evidence_needs_the_fundamentals_the_search_used(tmp_path, inputs):
    universe = ("--universe", str(inputs / "universe"))
    fundamentals = ("--fundamentals", str(inputs / "fundamentals"))
    assert _search_on(inputs, tmp_path / "s", *universe, *fundamentals) == 0
    source = ("--from-search", str(tmp_path / "s"), *universe)
    for options in [(), ("--fundamentals", str(inputs / "fundamentals_other"))]:
        with pytest.raises(SystemExit, match="--fundamentals"):
            _export(inputs / "market", tmp_path / "x", *source, *options)
        assert not (tmp_path / "x").exists()
    assert _export(inputs / "market", tmp_path / "sig", *source, *fundamentals) == 0

    # A search without fundamentals gives no evidence to an export that uses them.
    assert _search_on(inputs, tmp_path / "s2", *universe) == 0
    source = ("--from-search", str(tmp_path / "s2"), *universe)
    with pytest.raises(SystemExit, match="--fundamentals"):
        _export(inputs / "market", tmp_path / "x", *source, *fundamentals)
    assert not (tmp_path / "x").exists()


def test_inputs_that_cannot_be_matched_get_no_evidence(tmp_path, inputs):
    """Unreadable, unhashed or unrecorded inputs end in a refusal, not in evidence."""
    universe = ("--universe", str(inputs / "universe"))
    assert _search_on(inputs, tmp_path / "s", *universe) == 0
    source = ("--from-search", str(tmp_path / "s"))
    # Another kind of bundle is refused with a message, not a traceback.
    with pytest.raises(SystemExit, match="dataset_kind"):
        _export(
            inputs / "market", tmp_path / "x", *source, "--universe", str(inputs / "fundamentals")
        )
    # A bundle without a content hash cannot be shown to be the search's universe.
    with pytest.raises(SystemExit, match="content_sha256"):
        _export(
            inputs / "market",
            tmp_path / "x",
            *source,
            "--universe",
            str(inputs / "universe_hashless"),
        )
    assert not (tmp_path / "x").exists()

    # A config.json that does not record the universe gives no evidence.
    config = json.loads((tmp_path / "s" / "config.json").read_text(encoding="utf-8"))
    del config["experiment"]["identity"]["universe_sha256"]
    (tmp_path / "s" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(SystemExit, match="does not record the --universe") as refused:
        _export(inputs / "market", tmp_path / "x", *source)
    assert not (tmp_path / "x").exists()
    # The remedy keeps the protocol: no rerun of a used confirmation (INV-PR41-O1).
    assert "cannot be matched" in str(refused.value)
    assert "restore the confirmation's original config.json" in str(refused.value)
    assert "without evidence" in str(refused.value)
    assert "untouched data" in str(refused.value)
    assert "rerun the confirmation" not in str(refused.value)
    del config["experiment"]["identity"]["fundamentals_sha256"]
    config["experiment"]["identity"]["universe_sha256"] = _universe_hash(inputs / "universe")
    (tmp_path / "s" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(SystemExit, match="does not record the --fundamentals") as refused:
        _export(inputs / "market", tmp_path / "x", *source, *universe)
    assert "without evidence" in str(refused.value)
    assert not (tmp_path / "x").exists()


def test_refusal_does_not_claim_a_hashless_universe_was_none(tmp_path, inputs):
    """A search on a universe without a content hash recorded none: the refusal says only that.

    Telling the user to omit --universe would publish the non-member scores the search's
    universe excluded (the documented limit of hashless bundles).
    """
    hashless = ("--universe", str(inputs / "universe_hashless"))
    assert _search_on(inputs, tmp_path / "s", *hashless) == 0
    source = ("--from-search", str(tmp_path / "s"))
    with pytest.raises(SystemExit, match="recorded no --universe content hash") as refused:
        _export(inputs / "market", tmp_path / "x", *source, "--universe", str(inputs / "universe"))
    assert "the confirmation used no --universe" not in str(refused.value)
    assert "omit --universe only if" in str(refused.value)
    assert not (tmp_path / "x").exists()


def test_confirm_evidence_needs_the_universe_the_confirmation_used(tmp_path, inputs):
    book, factor = tmp_path / "ledger.jsonl", tmp_path / "f.json"
    freeze = ["freeze", "--expr", "close / delay(close, 5) - 1", "--horizon", "5"]
    assert main([*freeze, "--orientation", "-1", "--out", str(factor)]) == 0
    universe = ("--universe", str(inputs / "universe"))
    confirm = ["confirm", "--data", str(inputs / "market"), "--factor", str(factor), *universe]
    confirm += ["--ledger", str(book), "--confirm-start", "2020-09-01"]
    assert main([*confirm, "--out", str(tmp_path / "c")]) == 0
    source = ("--factor", str(factor), "--confirmation", str(tmp_path / "c"))
    with pytest.raises(SystemExit, match="--universe"):
        _export(inputs / "market", tmp_path / "x", *source)
    assert not (tmp_path / "x").exists()
    assert _export(inputs / "market", tmp_path / "sig", *source, *universe) == 0
    # Without evidence, any universe may be used.
    assert _export(inputs / "market", tmp_path / "plain", "--factor", str(factor)) == 0


@pytest.mark.parametrize("route", ["from-search", "confirmation"])
@pytest.mark.parametrize("option", ["universe", "fundamentals"])
def test_scores_use_the_bundle_read_whose_hash_was_checked(
    tmp_path, inputs, monkeypatch, option, route
):
    """Evidence and scores come from one read of each bundle (INV-PR41-001).

    A path that points to another valid bundle by the time scoring reads it (an alias
    switched between the evidence check and scoring, both published bundles unchanged)
    must not pair the second bundle's scores with evidence checked against the first.
    """
    import os
    import shutil

    import invest_mining.cli as cli
    from invest_data.schemas import read_fundamentals, read_universe

    paths = {name: inputs / name for name in ("universe", "fundamentals")}
    options = [f"--{name}={path}" for name, path in paths.items()]
    assert _search_on(inputs, tmp_path / "s", *options) == 0
    if route == "from-search":
        source = ("--from-search", str(tmp_path / "s"))
    else:
        confirmed = pd.read_csv(tmp_path / "s" / "confirmation.csv")["factor_id"]
        own = tmp_path / "s" / "factors" / f"{confirmed.iloc[0]}.json"
        source = ("--factor", str(own), "--confirmation", str(tmp_path / "s"))
    reader = {"universe": read_universe, "fundamentals": read_fundamentals}[option]
    checked = reader(paths[option])[1]
    assert not checked.equals(reader(inputs / f"{option}_other")[1])

    scored = []
    real_export, real_bars = cli.export_signals, cli._market_bars

    def spy(*args, **kwargs):
        scored.append(kwargs[option])
        return real_export(*args, **kwargs)

    monkeypatch.setattr(cli, "export_signals", spy)
    for attempt in range(2):
        alias = tmp_path / f"alias{attempt}"
        shutil.copytree(paths[option], alias)

        def switch(*args, alias=alias, attempt=attempt, **kwargs):
            # Between the evidence check and scoring: the alias now names the other bundle.
            bars = real_bars(*args, **kwargs)
            os.replace(alias, tmp_path / f"old{attempt}")
            shutil.copytree(inputs / f"{option}_other", alias)
            return bars

        monkeypatch.setattr(cli, "_market_bars", switch)
        used = [o for o in options if not o.startswith(f"--{option}=")]
        out = tmp_path / f"sig{attempt}"
        assert _export(inputs / "market", out, *source, *used, f"--{option}={alias}") == 0
        pd.testing.assert_frame_equal(scored[-1], checked)
        evidence = read_signals(out)[0].metadata["factor_evidence"]
        assert evidence["experiment_id"] == _experiment_id(tmp_path / "s")
