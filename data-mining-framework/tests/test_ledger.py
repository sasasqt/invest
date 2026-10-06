import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from invest_data.cli import main as data_main
from invest_mining import ledger
from invest_mining.cli import main
from invest_mining.ledger import LedgerError, Window
from invest_mining.search import chronological_split, mark_confirmation_use

W = Window.parse


def test_window_overlap_containment_and_validation():
    assert W("2020-01-01", "2020-06-30").overlaps(W("2020-06-30", "2020-12-31"))
    assert not W("2020-01-01", "2020-06-29").overlaps(W("2020-06-30"))
    assert W("2025-01-01").overlaps(W("2030-01-01", "2030-02-01"))
    assert W("2010-01-01", "2024-12-31").contains(W("2012-01-03", "2024-12-31"))
    assert not W("2010-01-01", "2024-12-31").contains(W("2012-01-03"))
    assert W("2025-01-01").contains(W("2026-01-01"))
    assert str(W("2025-01-01")) == "2025-01-01..open"
    assert Window.from_json(W("2020-01-01").to_json()) == Window(date(2020, 1, 1))
    with pytest.raises(LedgerError, match="before it starts"):
        W("2020-02-01", "2020-01-01")
    with pytest.raises(LedgerError, match="invalid window"):
        W("2020-13-01")
    with pytest.raises(LedgerError, match="start date"):
        Window.from_json({"end": "2020-01-01"})


def test_append_load_round_trip_and_rejects_corrupt_lines(tmp_path):
    path = tmp_path / "ledger.jsonl"
    assert ledger.load(path) == []
    now = datetime(2026, 10, 6, tzinfo=UTC)
    entry = ledger.append(path, "reservation", {"window": W("2025-01-01").to_json()}, now)
    assert ledger.load(path) == [entry]
    assert entry["recorded_at"] == "2026-10-06T00:00:00+00:00"
    with pytest.raises(LedgerError, match="unknown kind"):
        ledger.append(path, "note", {})
    with pytest.raises(LedgerError):
        ledger.append(path, "inspection", {"window": {"start": "nope"}})
    for bad, message in [
        ("{", "not JSON"),
        ("[]", "JSON object"),
        ('{"ledger_version": 2, "kind": "inspection"}', "ledger_version"),
        ('{"ledger_version": 1, "kind": "note"}', "unknown kind"),
        ('{"ledger_version": 1, "kind": "inspection", "window": {}}', "start date"),
        (
            '{"ledger_version": 1, "kind": "experiment", '
            '"development": {"start": "2020-01-01"}, "confirmation": {"start": "2021-01-01"}}',
            "experiment_id",
        ),
    ]:
        broken = tmp_path / "broken.jsonl"
        broken.write_text(bad + "\n")
        with pytest.raises(LedgerError, match=message):
            ledger.load(broken)


def _experiment(exp_id, dev, conf):
    return {
        "ledger_version": 1,
        "kind": "experiment",
        "experiment_id": exp_id,
        "development": dev.to_json(),
        "confirmation": conf.to_json(),
    }


def _entry(kind, window):
    return {"ledger_version": 1, "kind": kind, "window": window.to_json()}


def test_assess_confirmation_classifies_fresh_reused_and_reserved_data():
    dev, conf = W("2010-01-01", "2019-12-31"), W("2020-01-01", "2024-12-31")
    assert ledger.assess_confirmation([], dev, conf, "e_a") == ("confirmatory", [])

    inspected = [_entry("inspection", W("2010-01-01", "2024-12-31"))]
    use, reasons = ledger.assess_confirmation(inspected, dev, conf, "e_a")
    assert use == "exploratory" and "inspected window" in reasons[0]

    earlier = [_experiment("e_a", dev, conf)]
    assert ledger.assess_confirmation(earlier, dev, conf, "e_a")[1] == ["repeat of experiment e_a"]
    use, reasons = ledger.assess_confirmation(earlier, dev, conf, "e_b")
    assert use == "exploratory" and reasons == [
        "confirmation overlaps the confirmation window of e_a"
    ]
    # An earlier development window is inspected data too.
    later = W("2015-01-01", "2016-12-31")
    use, reasons = ledger.assess_confirmation(earlier, W("2010-01-01", "2014-12-31"), later, "e_c")
    assert reasons == ["confirmation overlaps the development window of e_a"]

    reserved = [*inspected, _entry("reservation", W("2025-01-01"))]
    with pytest.raises(LedgerError, match="development window"):
        ledger.assess_confirmation(reserved, W("2010-01-01", "2025-03-31"), W("2025-04-01"), "e")
    with pytest.raises(LedgerError, match="starts before the reserved window"):
        ledger.assess_confirmation(reserved, dev, W("2024-06-01", "2025-06-30"), "e")
    fresh = W("2025-01-02", "2025-12-31")
    assert ledger.assess_confirmation(reserved, W("2010-01-04", "2024-12-20"), fresh, "e") == (
        "confirmatory",
        [],
    )
    # Once a search confirmed on it, the reservation is used and no longer blocks.
    used = [*reserved, _experiment("e_r", W("2010-01-04", "2024-12-20"), fresh)]
    assert ledger.unused_reservations(used) == []
    ledger.check_inspection(used, W("2025-01-01", "2025-12-31"))
    use, _ = ledger.assess_confirmation(used, W("2010-01-04", "2025-06-30"), W("2025-07-01"), "f")
    assert use == "exploratory"


def test_check_inspection_and_is_inspected():
    entries = [
        _entry("reservation", W("2025-01-01")),
        _entry("inspection", W("2010-01-01", "2024-12-31")),
    ]
    ledger.check_inspection(entries, W("2010-01-04", "2024-12-31"))
    with pytest.raises(LedgerError, match="reserved confirmation window"):
        ledger.check_inspection(entries, W("2024-06-01", "2025-01-02"))
    assert ledger.is_inspected(entries, W("2012-01-01", "2013-01-01"))
    assert not ledger.is_inspected(entries, W("2009-12-31", "2013-01-01"))


def test_split_can_start_confirmation_on_a_date():
    dates = pd.bdate_range("2024-01-01", periods=100)
    s = chronological_split(dates, 0.9, horizon=2, embargo=1, confirm_start="2024-03-02")
    assert s.confirm_dates[0] == pd.Timestamp("2024-03-04")  # first session on/after
    assert len(s.purged_dates) == 3
    with pytest.raises(ValueError, match="no development or confirmation"):
        chronological_split(dates, 0.6, horizon=1, confirm_start="2030-01-01")


def test_mark_confirmation_use_keeps_the_raw_outcome():
    table = pd.DataFrame({"status": ["confirmation_passed", "rejected"]})
    fresh = mark_confirmation_use(table, "confirmatory")
    assert list(fresh["status"]) == ["confirmation_passed", "rejected"]
    reused = mark_confirmation_use(table, "exploratory")
    assert list(reused["status"]) == ["exploratory", "exploratory"]
    assert list(reused["test_outcome"]) == ["confirmation_passed", "rejected"]
    assert (reused["confirmation_use"] == "exploratory").all()
    with pytest.raises(ValueError):
        mark_confirmation_use(table, "maybe")


def _search(data, out, book, *extra):
    args = ["search", "--data", str(data), "--trials", "10", "--top-k", "2", "--out", str(out)]
    return main([*args, "--ledger", str(book), *extra])


def test_cli_search_records_experiments_and_flags_reuse(tmp_path, capsys):
    data, book = tmp_path / "data", tmp_path / "ledger.jsonl"
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "260"])

    assert _search(data, tmp_path / "first", book) == 0
    first = json.loads((tmp_path / "first" / "config.json").read_text())["experiment"]
    assert first["confirmation_use"] == "confirmatory" and first["reasons"] == []
    table = pd.read_csv(tmp_path / "first" / "confirmation.csv")
    assert (table["confirmation_use"] == "confirmatory").all()
    assert (table["status"] == table["test_outcome"]).all()
    factor = json.loads(next((tmp_path / "first" / "factors").glob("*.json")).read_text())
    assert factor["selection"]["experiment_id"] == first["experiment_id"]
    [entry] = ledger.load(book)
    assert entry["experiment_id"] == first["experiment_id"]
    assert entry["family"] == list(table["factor_id"]) and entry["n_proposals"] == 17

    # The identical search again is a repeat: still runs, but cannot claim confirmation.
    capsys.readouterr()
    assert _search(data, tmp_path / "again", book) == 0
    assert "Exploratory" in capsys.readouterr().out
    again = pd.read_csv(tmp_path / "again" / "confirmation.csv")
    assert (again["status"] == "exploratory").all()
    assert list(again["test_outcome"]) == list(table["status"])
    assert len(ledger.load(book)) == 2

    # A different seed confirms on the same window: exploratory, or refused on request.
    with pytest.raises(SystemExit, match="already used"):
        _search(data, tmp_path / "strict", book, "--seed", "5", "--require-confirmatory")
    assert not (tmp_path / "strict").exists() and len(ledger.load(book)) == 2

    # Without a ledger nothing is recorded or classified.
    plain = ["search", "--data", str(data), "--trials", "5", "--out", str(tmp_path / "plain")]
    assert main(plain) == 0
    experiment = json.loads((tmp_path / "plain" / "config.json").read_text())["experiment"]
    assert experiment["confirmation_use"] == "unrecorded" and experiment["ledger"] is None


def test_cli_reserved_window_is_only_usable_for_confirmation(tmp_path):
    data, book = tmp_path / "data", tmp_path / "ledger.jsonl"
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "260"])
    ledger_cmd = ["ledger", "--ledger", str(book)]
    assert main([*ledger_cmd, "inspect", "--start", "2020-01-01", "--end", "2020-08-31"]) == 0
    assert main([*ledger_cmd, "reserve", "--start", "2020-09-01", "--note", "holdout"]) == 0
    with pytest.raises(SystemExit, match="already inspected"):
        main([*ledger_cmd, "reserve", "--start", "2020-06-01", "--end", "2020-06-30"])
    with pytest.raises(SystemExit, match="reserved confirmation window"):
        main([*ledger_cmd, "inspect", "--start", "2020-10-01"])
    with pytest.raises(SystemExit, match="reserved confirmation window"):
        main([*ledger_cmd, "check", "--start", "2020-01-01", "--end", "2020-12-31"])
    assert main([*ledger_cmd, "check", "--start", "2019-01-01", "--end", "2020-08-31"]) == 0

    # Full-sample diagnostics and default splits would look at reserved data.
    evaluate = ["evaluate", "--data", str(data), "--expr", "close", "--ledger", str(book)]
    with pytest.raises(SystemExit, match="reserved confirmation window"):
        main([*evaluate, "--out", str(tmp_path / "ev")])
    with pytest.raises(SystemExit, match="development window"):
        _search(data, tmp_path / "s0", book, "--dev-fraction", "0.9")
    with pytest.raises(SystemExit, match="starts before the reserved window"):
        _search(data, tmp_path / "s1", book)
    assert len(ledger.load(book)) == 2

    # Confirming exactly on the reservation is confirmatory, and uses it up.
    assert _search(data, tmp_path / "s2", book, "--confirm-start", "2020-09-01") == 0
    config = json.loads((tmp_path / "s2" / "config.json").read_text())
    assert config["experiment"]["confirmation_use"] == "confirmatory"
    assert config["split"]["confirmation"][0] == "2020-09-01"
    assert config["dev_fraction"] is None and config["confirm_start"] == "2020-09-01"
    assert ledger.unused_reservations(ledger.load(book)) == []
    assert _search(data, tmp_path / "s3", book, "--confirm-start", "2020-09-01", "--seed", "1") == 0
    reused = json.loads((tmp_path / "s3" / "config.json").read_text())["experiment"]
    assert reused["confirmation_use"] == "exploratory"

    # Diagnostics now record their window once, and only once.
    assert main([*evaluate, "--out", str(tmp_path / "ev")]) == 0
    assert main([*evaluate, "--out", str(tmp_path / "ev2")]) == 0
    inspections = [e for e in ledger.load(book) if e["kind"] == "inspection"]
    assert len(inspections) == 2 and inspections[-1]["window"]["start"] == "2020-01-01"

    with pytest.raises(SystemExit, match="development period is empty"):
        _search(data, tmp_path / "s4", book, "--confirm-start", "2020-01-02")
    with pytest.raises(SystemExit, match="no development or confirmation"):
        _search(data, tmp_path / "s5", book, "--confirm-start", "2030-01-01")
