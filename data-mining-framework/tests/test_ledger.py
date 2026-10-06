import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from invest_data.cli import main as data_main
from invest_data.schemas import publish_market_bars, read_market_bars
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


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"experiment_id": None},
        {"experiment_id": 12},
        {"experiment_id": "e_ok", "ledger_version": 2},
        {"experiment_id": "e_ok", "kind": "inspection"},
        {"experiment_id": "e_ok", "recorded_at": "overridden"},
    ],
)
def test_append_rejects_invalid_experiments_without_changing_the_ledger(tmp_path, extra):
    path = tmp_path / "ledger.jsonl"
    initial = ledger.append(path, "inspection", {"window": W("2019-01-01", "2019-12-31").to_json()})
    before = path.read_bytes()
    fields = {
        "development": W("2020-01-01", "2020-06-30").to_json(),
        "confirmation": W("2020-07-01", "2020-12-31").to_json(),
        **extra,
    }
    for target in (path, tmp_path / "new" / "ledger.jsonl"):
        with pytest.raises(LedgerError):
            ledger.append(target, "experiment", fields)
    assert path.read_bytes() == before and ledger.load(path) == [initial]
    assert not (tmp_path / "new").exists()


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
    assert len(s.purged_dates) == 4
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


def test_cli_cannot_confirm_on_prices_used_by_an_earlier_development_label(tmp_path):
    data, book = tmp_path / "data", tmp_path / "ledger.jsonl"
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "260"])
    manifest, bars = read_market_bars(data)
    dates = pd.DatetimeIndex(sorted(bars["date"].unique()))
    first = tmp_path / "first"
    assert _search(data, first, book, "--horizon", "40") == 0
    config = json.loads((first / "config.json").read_text())
    last_decision = dates.get_loc(pd.Timestamp(config["split"]["development"][1]))
    last_observation = dates[last_decision + 41]
    [entry] = ledger.load(book)
    assert entry["development"]["end"] == str(last_observation.date())
    assert config["split"]["development_observations"][1] == str(last_observation.date())

    # Those prices are outside the first run's decision windows, but shaped selection.
    shorter = tmp_path / "shorter"
    publish_market_bars(
        bars[bars["date"] < dates[156]], shorter, dataset_id="shorter", metadata=manifest.metadata
    )
    start = str(dates[116].date())
    with pytest.raises(SystemExit, match=r"already used.*development window"):
        _search(
            shorter, tmp_path / "strict", book, "--confirm-start", start, "--require-confirmatory"
        )
    assert not (tmp_path / "strict").exists() and len(ledger.load(book)) == 1
    second = tmp_path / "second"
    assert _search(shorter, second, book, "--confirm-start", start) == 0
    assert (
        json.loads((second / "config.json").read_text())["experiment"]["confirmation_use"]
        == "exploratory"
    )


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
    assert ledger.load(book)[-1]["development"]["end"] == "2020-08-31"
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


def test_cli_confirms_a_fixed_formula_once_on_a_reserved_window(tmp_path, capsys):
    data, book, factor = tmp_path / "data", tmp_path / "ledger.jsonl", tmp_path / "f.json"
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "260"])
    ledger_cmd = ["ledger", "--ledger", str(book)]
    assert main([*ledger_cmd, "inspect", "--start", "2020-01-01", "--end", "2020-08-31"]) == 0
    assert main([*ledger_cmd, "reserve", "--start", "2020-09-01"]) == 0
    expr = "close / delay(close, 5) - 1"
    freeze = ["freeze", "--expr", expr, "--horizon", "5", "--orientation", "-1"]
    assert main([*freeze, "--out", str(factor)]) == 0

    def confirm(out, *extra, start="2020-09-01"):
        args = ["confirm", "--data", str(data), "--factor", str(factor), "--ledger", str(book)]
        return main([*args, "--confirm-start", start, *extra, "--out", str(tmp_path / out)])

    # Starting before the reservation would mix inspected and reserved data.
    with pytest.raises(SystemExit, match="starts before the reserved window"):
        confirm("early", start="2020-08-03")
    assert len(ledger.load(book)) == 2

    assert confirm("c1", "--require-confirmatory") == 0
    table = pd.read_csv(tmp_path / "c1" / "confirmation.csv")
    assert list(table["confirmation_use"]) == ["confirmatory"]
    assert table.loc[0, "status"] == table.loc[0, "test_outcome"]
    # The planted 5-day reversal is detected on the reserved window.
    assert table.loc[0, "status"] == "confirmation_passed" and table.loc[0, "n_dates"] >= 60
    entry = ledger.load(book)[-1]
    assert entry["kind"] == "experiment" and entry["n_proposals"] == 1
    assert entry["confirmation"]["start"] == "2020-09-01"
    # Only the formula's lookback before confirmation is recorded as used history.
    assert entry["development"] == {"start": "2020-08-25", "end": "2020-08-31"}
    assert ledger.unused_reservations(ledger.load(book)) == []
    config = json.loads((tmp_path / "c1" / "config.json").read_text())
    assert config["experiment"]["experiment_id"] == entry["experiment_id"]

    # A second look is a repeat: refused on request, otherwise exploratory.
    with pytest.raises(SystemExit, match="already used"):
        confirm("c2", "--require-confirmatory")
    assert not (tmp_path / "c2").exists() and len(ledger.load(book)) == 3
    capsys.readouterr()
    assert confirm("c3") == 0
    assert "Exploratory" in capsys.readouterr().out
    again = pd.read_csv(tmp_path / "c3" / "confirmation.csv")
    assert list(again["status"]) == ["exploratory"]
    assert list(again["test_outcome"]) == list(table["status"])


def test_cli_confirm_refuses_search_selected_factors_and_bad_dates(tmp_path):
    data, book = tmp_path / "data", tmp_path / "ledger.jsonl"
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "260"])
    assert _search(data, tmp_path / "s", book) == 0
    member = next((tmp_path / "s" / "factors").glob("*.json"))
    args = ["confirm", "--data", str(data), "--ledger", str(book), "--out", str(tmp_path / "c")]
    with pytest.raises(SystemExit, match="only fixed formulas"):
        main([*args, "--factor", str(member), "--confirm-start", "2020-09-01"])
    fixed = tmp_path / "f.json"
    assert main(["freeze", "--expr", "close", "--horizon", "1", "--out", str(fixed)]) == 0
    for start in ("2019-01-01", "2030-01-01"):
        with pytest.raises(SystemExit, match="no history or confirmation"):
            main([*args, "--factor", str(fixed), "--confirm-start", start])
    assert len(ledger.load(book)) == 1 and not (tmp_path / "c").exists()
