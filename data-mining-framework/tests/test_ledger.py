import json
import os
import re
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from invest_data.cli import main as data_main
from invest_data.schemas import publish_market_bars, publish_universe, read_market_bars
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
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "400"])
    manifest, bars = read_market_bars(data)
    dates = pd.DatetimeIndex(sorted(bars["date"].unique()))
    first = tmp_path / "first"
    assert _search(data, first, book, "--horizon", "80") == 0
    config = json.loads((first / "config.json").read_text())
    last_decision = dates.get_loc(pd.Timestamp(config["split"]["development"][1]))
    last_observation = dates[last_decision + 81]
    [entry] = ledger.load(book)
    assert entry["development"]["end"] == str(last_observation.date())
    assert config["split"]["development_observations"][1] == str(last_observation.date())

    # Those prices are outside the first run's decision windows, but shaped selection. The
    # 80-session horizon leaves a purge gap long enough for a confirmation with the test's
    # 60 labelled dates.
    shorter = tmp_path / "shorter"
    publish_market_bars(
        bars[bars["date"] < dates[last_decision + 82]],
        shorter,
        dataset_id="shorter",
        metadata=manifest.metadata,
    )
    start = str(dates[last_decision + 2].date())
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


@pytest.mark.parametrize("start_offset", [0, 1])
def test_cli_zero_lookback_confirmation_needs_no_history(tmp_path, start_offset):
    data, book, factor = tmp_path / "data", tmp_path / "ledger.jsonl", tmp_path / "f.json"
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "120"])
    dates = pd.DatetimeIndex(sorted(read_market_bars(data)[1]["date"].unique()))
    assert main(["freeze", "--expr", "close", "--horizon", "1", "--out", str(factor)]) == 0
    # The reservation starts where the confirmation does: confirming from a later session
    # would use up reserved sessions untested (BH-2026-10-20-1), and is refused.
    reserve_start = str(dates[start_offset].date())
    assert main(["ledger", "reserve", "--ledger", str(book), "--start", reserve_start]) == 0
    args = [
        "confirm",
        "--data",
        str(data),
        "--factor",
        str(factor),
        "--ledger",
        str(book),
        "--confirm-start",
        str(dates[start_offset].date()),
    ]
    first = tmp_path / "first"
    assert main([*args, "--require-confirmatory", "--out", str(first)]) == 0
    table = pd.read_csv(first / "confirmation.csv")
    assert table.loc[0, "confirmation_use"] == "confirmatory"
    assert table.loc[0, "test_status"] == "ok" and table.loc[0, "n_dates"] == 118 - start_offset
    entry = ledger.load(book)[-1]
    assert entry["development"] is None
    assert entry["params"]["lookback_sessions"] == 0
    assert (
        json.loads((first / "config.json").read_text())["experiment"]["identity"]["development"]
        is None
    )

    before = book.read_bytes()
    strict = tmp_path / "strict"
    with pytest.raises(SystemExit, match="already used"):
        main([*args, "--require-confirmatory", "--out", str(strict)])
    assert not strict.exists() and book.read_bytes() == before
    # A different start is also reused, so assessing its earlier null context must work.
    shifted = [*args[:-1], str(dates[start_offset + 1].date())]
    reused = tmp_path / "reused"
    assert main([*shifted, "--out", str(reused)]) == 0
    assert pd.read_csv(reused / "confirmation.csv").loc[0, "status"] == "exploratory"

    # Reserving an unrelated window must skip null context; confirmed dates remain used.
    reserve = ["ledger", "reserve", "--ledger", str(book)]
    assert main([*reserve, "--start", "2019-01-01", "--end", "2019-12-31"]) == 0
    with pytest.raises(SystemExit, match="already inspected or used"):
        main([*reserve, "--start", str(dates[-1].date())])


def test_cli_lookback_formula_still_requires_history(tmp_path):
    data, book, factor = tmp_path / "data", tmp_path / "ledger.jsonl", tmp_path / "f.json"
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "120"])
    assert (
        main(["freeze", "--expr", "delay(close, 1)", "--horizon", "1", "--out", str(factor)]) == 0
    )
    with pytest.raises(SystemExit, match="no history"):
        main(
            [
                "confirm",
                "--data",
                str(data),
                "--factor",
                str(factor),
                "--ledger",
                str(book),
                "--confirm-start",
                "2020-01-01",
                "--out",
                str(tmp_path / "result"),
            ]
        )
    assert not book.exists() and not (tmp_path / "result").exists()


@pytest.mark.parametrize(
    "params",
    [
        None,
        {},
        {"method": "fixed_formula"},
        {"method": "fixed_formula", "lookback_sessions": 1},
        {"method": "fixed_formula", "lookback_sessions": False},
        {"method": "fixed_formula", "lookback_sessions": "0"},
        {"method": "random_search", "lookback_sessions": 0},
    ],
)
def test_ledger_refuses_null_development_without_a_zero_lookback_formula(tmp_path, params):
    path = tmp_path / "ledger.jsonl"
    fields = {
        "experiment_id": "e_invalid",
        "development": None,
        "confirmation": W("2025-01-01", "2025-12-31").to_json(),
        "params": params,
    }
    with pytest.raises(LedgerError, match="zero-lookback fixed formula"):
        ledger.append(path, "experiment", fields)
    assert not path.exists()
    path.write_text(json.dumps({"ledger_version": 1, "kind": "experiment", **fields}) + "\n")
    with pytest.raises(LedgerError, match="zero-lookback fixed formula"):
        ledger.load(path)


def test_ledger_requires_explicit_null_for_empty_development(tmp_path):
    with pytest.raises(LedgerError, match="start date"):
        ledger.append(
            tmp_path / "ledger.jsonl",
            "experiment",
            {
                "experiment_id": "e_invalid",
                "confirmation": W("2025-01-01", "2025-12-31").to_json(),
                "params": {"method": "fixed_formula", "lookback_sessions": 0},
            },
        )


def _reserved_market(tmp_path, *, days=260, reserve="2020-09-01"):
    """A synthetic market from 2020-01-01, inspected before ``reserve`` and reserved from it."""
    data, book = tmp_path / "data", tmp_path / "ledger.jsonl"
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", str(days)])
    ledger_cmd = ["ledger", "--ledger", str(book)]
    end = str((pd.Timestamp(reserve) - pd.Timedelta(days=1)).date())
    assert main([*ledger_cmd, "inspect", "--start", "2020-01-01", "--end", end]) == 0
    assert main([*ledger_cmd, "reserve", "--start", reserve]) == 0
    return data, book


def _frozen(tmp_path, expr="close / delay(close, 5) - 1", horizon="5"):
    factor = tmp_path / "f.json"
    assert main(["freeze", "--expr", expr, "--horizon", horizon, "--out", str(factor)]) == 0
    return factor


@pytest.mark.parametrize("command", ["confirm", "search"])
def test_cli_confirmation_starting_inside_a_reservation_is_refused(tmp_path, command):
    # BH-2026-10-20-1: confirming from a session inside the reservation would use up the
    # reserved sessions before it, which nothing has tested (README: confirm on a
    # reservation with --confirm-start <first reserved date>, which uses it up). A
    # zero-lookback formula, or a search with an embargo, reads no reserved history, so
    # the development-window refusal does not catch it.
    data, book = _reserved_market(tmp_path)
    if command == "confirm":
        factor = _frozen(tmp_path, expr="close")
        args = ["confirm", "--data", str(data), "--factor", str(factor)]
        late = "2020-10-06"
    else:
        args = ["search", "--data", str(data), "--trials", "10", "--top-k", "2"]
        args += ["--embargo", "5"]
        late = "2020-09-08"  # five reserved sessions before it, all inside the embargo
    args += ["--ledger", str(book), "--out", str(tmp_path / "late")]
    before = book.read_bytes()
    with pytest.raises(SystemExit, match="starts after the reserved window"):
        main([*args, "--confirm-start", late])
    assert book.read_bytes() == before and not (tmp_path / "late").exists()
    [reserved] = ledger.unused_reservations(ledger.load(book))
    assert str(reserved) == "2020-09-01..open"
    with pytest.raises(SystemExit, match="reserved confirmation window"):
        main(
            [
                "ledger",
                "check",
                "--ledger",
                str(book),
                "--start",
                "2020-09-01",
                "--end",
                "2020-09-30",
            ]
        )


def test_cli_reservation_starting_on_a_non_session_day_accepts_the_next_session(tmp_path):
    # Guard: 2020-09-05 is a Saturday; the reservation's first session is Monday 2020-09-07.
    data, book = _reserved_market(tmp_path, reserve="2020-09-05")
    args = ["confirm", "--data", str(data), "--factor", str(_frozen(tmp_path))]
    out = tmp_path / "c"
    assert (
        main([*args, "--ledger", str(book), "--confirm-start", "2020-09-05", "--out", str(out)])
        == 0
    )
    entry = ledger.load(book)[-1]
    assert entry["confirmation"]["start"] == "2020-09-07"
    assert entry["confirmation_use"] == "confirmatory"
    assert ledger.unused_reservations(ledger.load(book)) == []


def test_cli_search_with_an_empty_family_leaves_the_reservation_unused(tmp_path, capsys):
    # BH-2026-10-26-1: a development window this short rejects every candidate, so nothing
    # is tested on the confirmation window; it must not use up the reservation.
    data, book = tmp_path / "data", tmp_path / "ledger.jsonl"
    data_main(["synthetic", "--out", str(data), "--instruments", "20", "--days", "160"])
    assert main(["ledger", "reserve", "--ledger", str(book), "--start", "2020-02-03"]) == 0
    search = ["search", "--data", str(data), "--trials", "5", "--ledger", str(book)]
    assert main([*search, "--confirm-start", "2020-02-03", "--out", str(tmp_path / "s1")]) == 0
    assert "No candidates qualified" in capsys.readouterr().out
    entries = ledger.load(book)
    assert entries[-1]["kind"] == "experiment" and entries[-1]["family"] == []
    # Its development window is recorded and still counts as used.
    dev = Window.from_json(entries[-1]["development"])
    assert dev.end is not None and dev.end < date(2020, 2, 3)
    [reserved] = ledger.unused_reservations(entries)
    assert str(reserved) == "2020-02-03..open"
    with pytest.raises(SystemExit, match="reserved confirmation window"):
        main(
            [
                "ledger",
                "check",
                "--ledger",
                str(book),
                "--start",
                "2020-03-02",
                "--end",
                "2020-03-31",
            ]
        )
    evaluate = ["evaluate", "--data", str(data), "--expr", "close", "--ledger", str(book)]
    with pytest.raises(SystemExit, match="reserved confirmation window"):
        main([*evaluate, "--out", str(tmp_path / "ev")])
    # A later search on the reservation is still confirmatory.
    later = Window.from_json(entries[-1]["confirmation"])
    assert ledger.assess_confirmation(entries, dev, later, "e_other") == ("confirmatory", [])


@pytest.mark.parametrize("command", ["confirm", "search"])
def test_cli_unwritable_out_is_refused_before_the_ledger_records_anything(tmp_path, command):
    # BH-2026-10-20-2: the experiment was appended before --out was created, so a bad --out
    # ended in a traceback and burnt the window's one confirmatory use.
    data, book = _reserved_market(tmp_path)
    taken = tmp_path / "taken"
    taken.write_text("")
    if command == "confirm":
        args = ["confirm", "--data", str(data), "--factor", str(_frozen(tmp_path))]
    else:
        args = ["search", "--data", str(data), "--trials", "10", "--top-k", "2"]
    args += ["--ledger", str(book), "--confirm-start", "2020-09-01"]
    before = book.read_bytes()
    for bad in (taken, taken / "sub"):
        with pytest.raises(SystemExit, match=re.escape(f"--out {bad}")):
            main([*args, "--out", str(bad)])
        assert book.read_bytes() == before
    assert main([*args, "--out", str(tmp_path / "ok")]) == 0
    assert ledger.load(book)[-1]["confirmation_use"] == "confirmatory"


@pytest.mark.skipif(
    os.name == "nt" or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="needs POSIX permission bits and a non-root user",
)
def test_cli_read_only_out_is_refused_before_the_ledger_records_anything(tmp_path):
    # Same class: an existing folder that takes no file (evaluate records an inspection).
    data, book = _reserved_market(tmp_path)
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        before = book.read_bytes()
        args = ["confirm", "--data", str(data), "--factor", str(_frozen(tmp_path))]
        args += ["--ledger", str(book), "--confirm-start", "2020-09-01", "--out", str(locked)]
        with pytest.raises(SystemExit, match=re.escape(f"--out {locked}")):
            main(args)
        assert book.read_bytes() == before
        evaluate = [
            "evaluate",
            "--data",
            str(data),
            "--expr",
            "close",
            "--ledger",
            str(tmp_path / "e"),
        ]
        with pytest.raises(SystemExit, match=re.escape(f"--out {locked}")):
            main([*evaluate, "--out", str(locked)])
        assert not (tmp_path / "e").exists()
    finally:
        locked.chmod(0o755)


@pytest.mark.parametrize("command", ["confirm", "search"])
def test_cli_confirmation_without_a_labelled_date_is_refused(tmp_path, command):
    # Same class as BH-2026-10-26-1: with horizon 1, decision t needs the opens at t+1 and
    # t+2, so a confirmation of the last two sessions has no label and tests nothing, and
    # the test needs 60 labelled dates (search.py's MIN_CONFIRM_DATES): 62 sessions.
    data = tmp_path / "data"
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "120"])
    dates = pd.DatetimeIndex(sorted(read_market_bars(data)[1]["date"].unique()))
    if command == "confirm":
        factor = _frozen(tmp_path, expr="close", horizon="1")
        base = ["confirm", "--data", str(data), "--factor", str(factor)]
    else:
        base = ["search", "--data", str(data), "--trials", "5", "--horizon", "1"]

    def run(sessions):
        start, book = str(dates[-sessions].date()), tmp_path / f"ledger{sessions}.jsonl"
        assert main(["ledger", "reserve", "--ledger", str(book), "--start", start]) == 0
        out = tmp_path / f"c{sessions}"
        return [*base, "--ledger", str(book), "--confirm-start", start, "--out", str(out)], book

    for sessions, labelled in ((2, 0), (61, 59)):
        args, book = run(sessions)
        before = book.read_bytes()
        match = rf"has {labelled} decision date\(s\) with a complete 1-session label"
        with pytest.raises(SystemExit, match=match):
            main(args)
        assert book.read_bytes() == before and not (tmp_path / f"c{sessions}").exists()
        assert len(ledger.unused_reservations(ledger.load(book))) == 1
    # Boundary: 62 sessions label decision dates[-62] to dates[-3], 60 dates.
    args, book = run(62)
    assert main(args) == 0
    assert ledger.unused_reservations(ledger.load(book)) == []


def test_cli_confirmation_after_the_universe_ends_is_refused(tmp_path):
    # Same class: enough sessions, but no universe member on them, so no date has a label
    # (the confirmation would test 0 dates and still use the reservation up).
    data, book = tmp_path / "data", tmp_path / "ledger.jsonl"
    data_main(["synthetic", "--out", str(data), "--instruments", "20", "--days", "200"])
    bars = read_market_bars(data)[1]
    dates = pd.DatetimeIndex(sorted(bars["date"].unique()))
    cut = dates[120]
    members = pd.DataFrame(
        {
            "universe": "u",
            "instrument": sorted(bars["instrument"].unique()),
            "start_date": dates[0].date(),
            "end_date": (cut - pd.Timedelta(days=1)).date(),
        }
    )
    publish_universe(members, tmp_path / "uni", dataset_id="u")
    assert main(["ledger", "reserve", "--ledger", str(book), "--start", str(cut.date())]) == 0
    factor = _frozen(tmp_path, expr="close", horizon="1")
    args = ["confirm", "--data", str(data), "--factor", str(factor), "--ledger", str(book)]
    args += ["--universe", str(tmp_path / "uni"), "--confirm-start", str(cut.date())]
    before = book.read_bytes()
    with pytest.raises(SystemExit, match=r"has 0 decision date\(s\) with a complete"):
        main([*args, "--out", str(tmp_path / "c")])
    assert book.read_bytes() == before and not (tmp_path / "c").exists()


def test_an_empty_family_does_not_use_its_confirmation_window():
    # BH-2026-10-26-1: an experiment that selected nothing tested nothing on its
    # confirmation window; only its development window was observed.
    dev, conf = W("2010-01-04", "2024-12-20"), W("2025-01-02")
    reservation = _entry("reservation", W("2025-01-01"))
    empty = {**_experiment("e_empty", dev, conf), "family": []}
    tested = {**_experiment("e_tested", dev, conf), "family": ["f_1"]}
    assert ledger.unused_reservations([reservation, empty]) == [W("2025-01-01")]
    with pytest.raises(LedgerError, match="reserved confirmation window"):
        ledger.check_inspection([reservation, empty], W("2025-02-01", "2025-02-28"))
    assert ledger.assess_confirmation([reservation, empty], dev, conf, "e_next") == (
        "confirmatory",
        [],
    )
    # Its development window still counts, and so does a repeat of it.
    use, reasons = ledger.assess_confirmation([empty], W("2000-01-03", "2004-12-31"), dev, "e_x")
    assert use == "exploratory"
    assert reasons == ["confirmation overlaps the development window of e_empty"]
    assert ledger.assess_confirmation([empty], dev, conf, "e_empty")[1] == [
        "repeat of experiment e_empty"
    ]
    # A tested family, or a legacy entry without the field, uses the window up.
    assert ledger.unused_reservations([reservation, tested]) == []
    assert ledger.unused_reservations([reservation, _experiment("e_old", dev, conf)]) == []
    assert set(ledger.used_windows(empty)) == {"development"}
    assert set(ledger.used_windows(tested)) == {"development", "confirmation"}
    assert ledger.used_windows(reservation) == {}
    assert ledger.used_windows(_entry("inspection", dev)) == {"window": dev}


def test_assess_confirmation_with_sessions_refuses_skipping_reserved_sessions():
    # BH-2026-10-20-1, at the function: 2025-01-01 is a holiday, so the reservation's
    # first session is 2025-01-02; confirming from 2025-01-06 would skip two of them.
    reserved = [_entry("reservation", W("2025-01-01"))]
    dev = W("2010-01-04", "2024-12-20")
    sessions = [date(2024, 12, 31), date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6)]
    assert ledger.assess_confirmation(reserved, dev, W("2025-01-02"), "e", sessions=sessions) == (
        "confirmatory",
        [],
    )
    match = r"reserved session\(s\) 2025-01-02\.\.2025-01-03 would be used up untested"
    with pytest.raises(LedgerError, match=match):
        ledger.assess_confirmation(reserved, dev, W("2025-01-06"), "e", sessions=sessions)
    # A bounded reservation that ends before the confirmation is not touched by it.
    bounded = [_entry("reservation", W("2025-01-01", "2025-01-03"))]
    assert ledger.assess_confirmation(bounded, dev, W("2025-01-06"), "e", sessions=sessions) == (
        "confirmatory",
        [],
    )
    assert ledger.unused_reservations(bounded) == [W("2025-01-01", "2025-01-03")]


def test_cli_out_that_takes_no_file_is_refused_before_recording(tmp_path, monkeypatch):
    # BH-2026-10-20-2 for an existing folder that refuses new files (read-only), on every
    # platform and user: the probe file cannot be created there.
    data, book = _reserved_market(tmp_path)
    locked = tmp_path / "locked"
    locked.mkdir()
    original = tempfile.TemporaryFile

    def refuse(*args, **kwargs):
        if Path(kwargs.get("dir", "")) == locked:
            raise PermissionError(13, "Permission denied", str(locked))
        return original(*args, **kwargs)

    monkeypatch.setattr(tempfile, "TemporaryFile", refuse)
    factor = _frozen(tmp_path, expr="close")
    before = book.read_bytes()
    confirm = ["confirm", "--data", str(data), "--factor", str(factor), "--ledger", str(book)]
    with pytest.raises(SystemExit, match=re.escape(f"--out {locked}")):
        main([*confirm, "--confirm-start", "2020-09-01", "--out", str(locked)])
    assert book.read_bytes() == before
    # evaluate records a full-sample inspection, so it gets a ledger without a reservation.
    fresh = tmp_path / "fresh.jsonl"
    evaluate = ["evaluate", "--data", str(data), "--expr", "close", "--ledger", str(fresh)]
    with pytest.raises(SystemExit, match=re.escape(f"--out {locked}")):
        main([*evaluate, "--out", str(locked)])
    assert not fresh.exists() and list(locked.iterdir()) == []


def test_overlapping_reservations_are_confirmed_from_their_first_session():
    # Checked one by one, R1 refuses a start after its first session and R2 a start before
    # its own, so no confirmation could use nested reservations once BH-2026-10-20-1 is
    # fixed. They are one reserved stretch, confirmed from its first session.
    dev = W("2010-01-04", "2020-05-29")
    sessions = [date(2020, 5, 29), date(2020, 6, 1), date(2020, 9, 1), date(2020, 12, 31)]
    for inner in (W("2020-09-01"), W("2020-08-01", "2020-09-30")):
        entries = [
            _entry("reservation", W("2020-06-01", "2020-12-31")),
            _entry("reservation", inner),
        ]
        late = W("2020-09-01")
        with pytest.raises(LedgerError, match=r"starts after the reserved window 2020-06-01\.\."):
            ledger.assess_confirmation(entries, dev, late, "e", sessions=sessions)
        first = W("2020-06-01")
        assert ledger.assess_confirmation(entries, dev, first, "e", sessions=sessions) == (
            "confirmatory",
            [],
        )
        used = [*entries, {**_experiment("e_r", dev, first), "family": ["f_1"]}]
        assert ledger.unused_reservations(used) == []
    # Reservations that do not overlap stay separate.
    apart = [
        _entry("reservation", W("2020-06-01", "2020-06-30")),
        _entry("reservation", W("2020-09-01")),
    ]
    with pytest.raises(
        LedgerError, match=re.escape("starts before the reserved window 2020-09-01..open")
    ):
        ledger.assess_confirmation(apart, dev, W("2020-06-01"), "e", sessions=sessions)


@pytest.mark.parametrize("command", ["confirm", "search"])
def test_cli_existing_output_that_takes_no_write_is_refused_before_recording(tmp_path, command):
    # BH-2026-10-20-2 for a rerun into the same --out whose earlier result cannot be
    # replaced (read-only, or open in another program on Windows): here a folder holds the
    # name confirmation.csv, so writing it fails on every platform and user.
    data, book = _reserved_market(tmp_path)
    out = tmp_path / "rerun"
    (out / "confirmation.csv").mkdir(parents=True)
    if command == "confirm":
        args = ["confirm", "--data", str(data), "--factor", str(_frozen(tmp_path, expr="close"))]
    else:
        args = ["search", "--data", str(data), "--trials", "10", "--top-k", "2"]
    args += ["--ledger", str(book), "--confirm-start", "2020-09-01", "--out", str(out)]
    before = book.read_bytes()
    with pytest.raises(SystemExit, match=re.escape(f"--out {out}")):
        main(args)
    assert book.read_bytes() == before


@pytest.mark.parametrize("command", ["confirm", "search", "search without a ledger"])
def test_cli_write_failure_after_recording_names_the_experiment(tmp_path, monkeypatch, command):
    # The probe cannot rule out every failure (a full disk); one after the record exits
    # with a message naming the recorded experiment instead of a traceback.
    data, book = _reserved_market(tmp_path)
    if command == "confirm":
        args = ["confirm", "--data", str(data), "--factor", str(_frozen(tmp_path, expr="close"))]
    else:
        args = ["search", "--data", str(data), "--trials", "10", "--top-k", "2"]
    if command != "search without a ledger":
        args += ["--ledger", str(book)]
    out = tmp_path / "c"

    def full(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(pd.DataFrame, "to_csv", full)
    if command == "search without a ledger":
        with pytest.raises(SystemExit, match=re.escape(f"--out {out}: [Errno 28]")) as raised:
            main([*args, "--confirm-start", "2020-09-01", "--out", str(out)])
        assert "recorded" not in str(raised.value)
        assert len(ledger.load(book)) == 2
        return
    with pytest.raises(SystemExit, match="the ledger already recorded experiment e_"):
        main([*args, "--confirm-start", "2020-09-01", "--out", str(out)])
    assert ledger.load(book)[-1]["kind"] == "experiment"


def test_cli_reserve_and_search_after_an_empty_family(tmp_path):
    # BH-2026-10-26-1 end to end: a search that selected nothing leaves its confirmation
    # window free to reserve, and a later search that selects factors there is confirmatory.
    data, book = tmp_path / "data", tmp_path / "ledger.jsonl"
    data_main(["synthetic", "--out", str(data), "--instruments", "20", "--days", "260"])
    search = ["search", "--data", str(data), "--trials", "5", "--ledger", str(book)]
    assert main([*search, "--confirm-start", "2020-02-03", "--out", str(tmp_path / "s1")]) == 0
    assert ledger.load(book)[-1]["family"] == []
    assert main(["ledger", "reserve", "--ledger", str(book), "--start", "2020-06-01"]) == 0
    later = [*search, "--confirm-start", "2020-06-01", "--require-confirmatory"]
    assert main([*later, "--out", str(tmp_path / "s2")]) == 0
    entry = ledger.load(book)[-1]
    assert entry["family"] and entry["confirmation_use"] == "confirmatory"
    assert ledger.unused_reservations(ledger.load(book)) == []


def test_reserved_regions_merge_by_the_latest_end():
    # R1 06-01..07-31 and R2 07-15..12-31 overlap; R3 from 09-01 lies only inside R2, so it
    # belongs to the same stretch only if the union ends at R2's end, not R1's.
    dev = W("2010-01-04", "2020-05-29")
    entries = [
        _entry("reservation", W("2020-06-01", "2020-07-31")),
        _entry("reservation", W("2020-07-15", "2020-12-31")),
        _entry("reservation", W("2020-09-01")),
    ]
    sessions = [date(2020, 5, 29), date(2020, 6, 1), date(2020, 9, 1)]
    assert ledger.assess_confirmation(entries, dev, W("2020-06-01"), "e", sessions=sessions) == (
        "confirmatory",
        [],
    )


def test_an_inspected_reservation_counts_as_used():
    # A ledger written before empty-family searches stopped counting: such a search used the
    # reservation up, then an inspection (refused over an unused reservation) covered it.
    # Its data has been looked at, so it must not become reserved again.
    dev, conf = W("2010-01-04", "2024-01-31"), W("2024-02-01")
    entries = [
        _entry("reservation", W("2024-02-01")),
        {**_experiment("e_empty", dev, conf), "family": []},
        _entry("inspection", W("2024-01-01", "2024-08-09")),
    ]
    assert ledger.unused_reservations(entries) == []
    ledger.check_inspection(entries, W("2024-03-01", "2024-03-29"))


def test_cli_evaluate_refuses_a_tables_folder_that_takes_no_file(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data_main(["synthetic", "--out", str(data), "--instruments", "20", "--days", "120"])
    out, book = tmp_path / "ev", tmp_path / "ledger.jsonl"
    original = tempfile.TemporaryFile

    def refuse(*args, **kwargs):
        if Path(kwargs.get("dir", "")) == out / "tables":
            raise PermissionError(13, "Permission denied", str(out / "tables"))
        return original(*args, **kwargs)

    monkeypatch.setattr(tempfile, "TemporaryFile", refuse)
    evaluate = ["evaluate", "--data", str(data), "--expr", "close", "--ledger", str(book)]
    with pytest.raises(SystemExit, match=re.escape(f"--out {out}")):
        main([*evaluate, "--out", str(out)])
    assert not book.exists()


def test_a_reservation_used_as_development_counts_as_used():
    # A ledger written before empty-family searches stopped counting: such a search used the
    # reservation up, then a later search took it into its development data. That data has
    # been looked at, so the reservation must not become reserved again (a rerun of the later
    # search would be refused).
    entries = [
        _entry("reservation", W("2020-02-03", "2020-02-28")),
        {**_experiment("e_empty", W("2010-01-04", "2020-01-31"), W("2020-02-03")), "family": []},
        _experiment("e_later", W("2020-01-01", "2020-05-29"), W("2020-06-01")),
    ]
    assert ledger.unused_reservations(entries) == []
    ledger.check_inspection(entries, W("2020-02-10", "2020-02-20"))


def test_cli_evaluate_rerun_with_a_subfolder_in_figures(tmp_path):
    # Regression test for the --out check of evaluate: only its own output files are opened,
    # so a subfolder an earlier run or the user left in figures/ or tables/ is no obstacle.
    data, out = tmp_path / "d", tmp_path / "ev"
    data_main(["synthetic", "--out", str(data), "--instruments", "20", "--days", "120"])
    args = ["evaluate", "--data", str(data), "--expr", "close", "--out", str(out)]
    assert main(args) == 0
    (out / "figures" / "old").mkdir()
    (out / "tables" / "old").mkdir()
    assert main([*args, "--ledger", str(tmp_path / "l.jsonl")]) == 0


def test_cli_evaluate_rerun_needs_no_new_file_where_every_output_exists(tmp_path, monkeypatch):
    # The --out check asks only for what the run will do: a rerun overwrites its eight
    # outputs, so folders that take no new file (mode 555, say) must not refuse it.
    data, out, book = tmp_path / "d", tmp_path / "ev", tmp_path / "l.jsonl"
    data_main(["synthetic", "--out", str(data), "--instruments", "20", "--days", "120"])
    args = ["evaluate", "--data", str(data), "--expr", "close", "--out", str(out)]
    assert main(args) == 0
    original = tempfile.TemporaryFile
    full = {out, out / "tables", out / "figures"}

    def refuse(*a, **kwargs):
        if Path(kwargs.get("dir", "")) in full:
            raise PermissionError(13, "Permission denied", str(kwargs["dir"]))
        return original(*a, **kwargs)

    monkeypatch.setattr(tempfile, "TemporaryFile", refuse)
    assert main([*args, "--ledger", str(book)]) == 0
    assert ledger.load(book)[-1]["kind"] == "inspection"
    (out / "figures" / "ic.png").unlink()
    with pytest.raises(SystemExit, match=re.escape(f"--out {out}")):
        main([*args, "--ledger", str(tmp_path / "l2.jsonl")])
    assert not (tmp_path / "l2.jsonl").exists()


@pytest.mark.skipif(
    os.name == "nt" or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="needs POSIX permission bits and a non-root user",
)
def test_cli_reruns_into_read_only_outputs_the_run_only_deletes_or_overwrites(tmp_path):
    # search only deletes an earlier run's factors/*.json, which POSIX allows for read-only
    # files in a writable folder; evaluate only overwrites its outputs, which needs no
    # writable folder. Both reruns work without the check, so the check must not refuse them.
    data = tmp_path / "d"
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "200"])
    search = ["search", "--data", str(data), "--trials", "10", "--out", str(tmp_path / "s")]
    assert main(search) == 0
    old = sorted((tmp_path / "s" / "factors").glob("*.json"))
    assert old
    for path in old:
        path.chmod(0o444)
    assert main(search) == 0
    out = tmp_path / "ev"
    evaluate = ["evaluate", "--data", str(data), "--expr", "close", "--out", str(out)]
    assert main(evaluate) == 0
    folders = [out, out / "tables", out / "figures"]
    for folder in folders:
        folder.chmod(0o555)
    try:
        assert main(evaluate) == 0
    finally:
        for folder in folders:
            folder.chmod(0o755)


def test_cli_search_rerun_refuses_a_folder_among_old_factor_files(tmp_path):
    # Guard: the search deletes an earlier run's factors/*.json, which fails for a folder, so
    # the check must still refuse such an --out before the ledger records anything.
    data, book, out = tmp_path / "d", tmp_path / "l.jsonl", tmp_path / "s"
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "200"])
    search = ["search", "--data", str(data), "--trials", "10", "--out", str(out)]
    (out / "factors" / "f_old.json").mkdir(parents=True)
    with pytest.raises(SystemExit, match=re.escape(f"--out {out}")):
        main([*search, "--ledger", str(book)])
    assert not book.exists()


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need extra rights on Windows")
def test_cli_search_rerun_deletes_an_old_factor_link_to_a_folder(tmp_path):
    # Deleting a link removes the link, not the folder it points to, so the check must not
    # refuse it as a folder.
    data, out = tmp_path / "d", tmp_path / "s"
    data_main(["synthetic", "--out", str(data), "--instruments", "25", "--days", "200"])
    (tmp_path / "elsewhere").mkdir()
    (out / "factors").mkdir(parents=True)
    (out / "factors" / "f_old.json").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    assert main(["search", "--data", str(data), "--trials", "10", "--out", str(out)]) == 0
    assert not (out / "factors" / "f_old.json").is_symlink()
    assert (tmp_path / "elsewhere").is_dir()
