"""Yahoo test-only adapter: offline, with fabricated Yahoo-format responses."""

import io
import json
import urllib.error

import numpy as np
import pandas as pd
import pytest

from invest_data.cleaning import clean_bars
from invest_data.cli import main
from invest_data.schemas import publish_market_bars, read_market_bars
from invest_data.sources import SyntheticConfig, synthetic_market
from invest_data.testing import fake_chart, write_fake_snapshot
from invest_data.yahoo import (
    RetryPolicy,
    SourceError,
    chart_url,
    download_snapshot,
    fetch_symbol,
    load_snapshot,
    parse_chart,
    yahoo_metadata,
)


def bars(n_instruments=3, n_days=40, seed=3):
    return synthetic_market(SyntheticConfig(n_instruments=n_instruments, n_days=n_days, seed=seed))


def http_error(code):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b""))  # type: ignore[arg-type]


def test_chart_url_covers_inclusive_range():
    url = chart_url("BRK-B", "2024-01-02", "2024-01-05")
    assert "/chart/BRK-B?" in url
    assert "period1=1704153600" in url and "period2=1704499200" in url
    with pytest.raises(ValueError, match="precedes"):
        chart_url("X", "2024-01-05", "2024-01-01")


def test_parse_chart_uses_exchange_dates_and_keeps_nulls():
    src = bars(1, 5)
    src.loc[2, "close"] = np.nan
    raw = parse_chart(json.dumps(fake_chart(src, "SYN000", adj_factor=0.5)).encode(), "SYN000")
    assert raw["date"].tolist() == src["date"].tolist()
    assert raw["close"].isna().sum() == 1 and raw["adjclose"].isna().sum() == 1
    np.testing.assert_allclose(raw["adjclose"].dropna(), src["close"].dropna() * 0.5)


@pytest.mark.parametrize(
    "payload, match",
    [
        ({"chart": {"result": None, "error": {"code": "Not Found"}}}, "source error"),
        ({"nope": 1}, "no 'chart'"),
        ({"chart": {"result": [], "error": None}}, "exactly one"),
    ],
)
def test_parse_chart_rejects_bad_responses(payload, match):
    with pytest.raises(SourceError, match=match):
        parse_chart(payload, "X")


def test_parse_chart_rejects_misaligned_arrays():
    payload = fake_chart(bars(1, 5), "X")
    payload["chart"]["result"][0]["indicators"]["quote"][0]["open"].pop()
    with pytest.raises(SourceError, match="open has 4 values"):
        parse_chart(payload, "X")


def test_fetch_retries_transient_errors_with_bounded_backoff():
    body = json.dumps(fake_chart(bars(1, 5), "X")).encode()
    calls, sleeps = [], []
    outcomes = [http_error(429), urllib.error.URLError("reset"), TimeoutError("slow"), body]

    def fetcher(url, timeout):
        calls.append(timeout)
        out = outcomes[len(calls) - 1]
        if isinstance(out, Exception):
            raise out
        return out

    got = fetch_symbol(
        "X",
        "2020-01-01",
        "2020-02-01",
        fetcher=fetcher,
        timeout=3.0,
        retry=RetryPolicy(attempts=4, backoff_seconds=1, max_backoff_seconds=3),
        sleep=sleeps.append,
    )
    assert got == body and calls == [3.0] * 4 and sleeps == [1, 2, 3]


def test_fetch_gives_up_after_attempts_and_does_not_retry_permanent_errors():
    sleeps: list[float] = []

    def always(code):
        def fetcher(url, timeout):
            always.calls += 1  # type: ignore[attr-defined]
            raise http_error(code)

        return fetcher

    always.calls = 0  # type: ignore[attr-defined]
    with pytest.raises(SourceError, match="after 3 attempts"):
        fetch_symbol(
            "X",
            "2020-01-01",
            "2020-02-01",
            fetcher=always(503),
            retry=RetryPolicy(attempts=3),
            sleep=sleeps.append,
        )
    assert always.calls == 3 and len(sleeps) == 2  # type: ignore[attr-defined]
    always.calls = 0  # type: ignore[attr-defined]
    with pytest.raises(SourceError, match="HTTP 404"):
        fetch_symbol("X", "2020-01-01", "2020-02-01", fetcher=always(404), sleep=sleeps.append)
    assert always.calls == 1  # type: ignore[attr-defined]
    with pytest.raises(SourceError, match="not JSON"):
        fetch_symbol("X", "2020-01-01", "2020-02-01", fetcher=lambda u, t: b"<html>")


def test_download_records_failures_and_is_immutable(tmp_path):
    good = json.dumps(fake_chart(bars(1, 5), "AAA")).encode()

    def fetcher(url, timeout):
        if "/chart/BAD" in url:
            raise http_error(404)
        return good

    snap = download_snapshot(
        ["AAA", "BAD", "AAA"],
        "2020-01-01",
        "2020-02-01",
        tmp_path / "s",
        fetcher=fetcher,
        sleep=lambda s: None,
    )
    assert list(snap["files"]) == ["AAA"] and "HTTP 404" in snap["failures"]["BAD"]
    assert snap["request"]["symbols"] == ["AAA", "BAD"] and snap["test_only"] is True
    assert (tmp_path / "s" / "raw" / "AAA.json").read_bytes() == good
    with pytest.raises(FileExistsError):
        download_snapshot(["AAA"], "2020-01-01", "2020-02-01", tmp_path / "s", fetcher=fetcher)


def test_replay_adjusts_prices_and_preserves_dollar_volume(tmp_path):
    src = bars(2, 30)
    write_fake_snapshot(src, tmp_path / "s", adj_factors={"SYN000": 0.8})
    raw, prov = load_snapshot(tmp_path / "s")
    a = raw[raw["instrument"] == "SYN000"].reset_index(drop=True)
    s = src[src["instrument"] == "SYN000"].reset_index(drop=True)
    np.testing.assert_allclose(a["close"], s["close"] * 0.8)
    np.testing.assert_allclose(a["open"] / a["close"], s["open"] / s["close"])
    np.testing.assert_allclose(a["close"] * a["volume"], s["close"] * s["volume"])
    assert prov["test_only"] and set(prov["snapshot"]["files"]) == {"SYN000", "SYN001"}
    only, _ = load_snapshot(tmp_path / "s", ["SYN001"])
    assert set(only["instrument"]) == {"SYN001"}
    with pytest.raises(SourceError, match="not in snapshot"):
        load_snapshot(tmp_path / "s", ["ZZZ"])


def test_same_snapshot_gives_same_dataset_hash(tmp_path):
    write_fake_snapshot(bars(4, 60), tmp_path / "s")
    hashes = set()
    for i, fmt in enumerate(["csv", "parquet", "csv"]):
        raw, prov = load_snapshot(tmp_path / "s")
        clean, _ = clean_bars(raw.sample(frac=1, random_state=i))
        m = publish_market_bars(
            clean,
            tmp_path / f"b{i}",
            dataset_id="y",
            fmt=fmt,
            metadata=yahoo_metadata("USD", "test"),
            provenance=prov,
        )
        hashes.add(m.content_sha256)
    assert len(hashes) == 1


def test_replay_detects_modified_snapshot(tmp_path):
    write_fake_snapshot(bars(1, 10), tmp_path / "s")
    path = tmp_path / "s" / "raw" / "SYN000.json"
    path.write_bytes(path.read_bytes().replace(b'"USD"', b'"EUR"'))
    with pytest.raises(SourceError, match="SHA-256"):
        load_snapshot(tmp_path / "s")
    with pytest.raises(SourceError, match=r"no snapshot\.json"):
        load_snapshot(tmp_path / "missing")


def test_cli_download_and_offline_publish_reports_rejected_rows(tmp_path, monkeypatch, capsys):
    src = bars(2, 20)
    src.loc[src.index[3], "close"] = np.nan  # Yahoo returns null rows; cleaning rejects them
    payloads = {s: json.dumps(fake_chart(g, s)).encode() for s, g in src.groupby("instrument")}
    monkeypatch.setattr(
        "invest_data.yahoo.http_get",
        lambda url, timeout: payloads[url.split("/chart/")[1].split("?")[0]],
    )
    monkeypatch.setattr("invest_data.yahoo.time.sleep", lambda s: None)
    symbols = tmp_path / "symbols.txt"
    symbols.write_text("# test list\nSYN000\nSYN001  # second\n")
    snap = tmp_path / "snap"
    assert (
        main(
            [
                "yahoo",
                "download",
                "--snapshot",
                str(snap),
                "--symbols-file",
                str(symbols),
                "--start",
                "2020-01-01",
                "--end",
                "2020-03-01",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["downloaded"] == 2

    monkeypatch.setattr("invest_data.yahoo.http_get", None)  # publishing never touches the network
    out = tmp_path / "bundle"
    assert (
        main(
            [
                "yahoo",
                "publish",
                "--snapshot",
                str(snap),
                "--out",
                str(out),
                "--dataset-id",
                "yahoo-test",
                "--format",
                "parquet",
            ]
        )
        == 0
    )
    manifest, frame = read_market_bars(out)
    assert len(frame) == len(src) - 1
    assert manifest.metadata["calendar"] == "XNYS" and "TEST-ONLY" in manifest.metadata["note"]
    assert manifest.provenance["cleaning"]["rejected_by_reason"] == {
        "missing_or_nonfinite_value": 1
    }
    rejected = pd.read_csv(tmp_path / "bundle.rejected.csv")
    assert rejected["reason"].tolist() == ["missing_or_nonfinite_value"]


def test_cli_download_without_symbols_or_results_fails(tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        main(
            [
                "yahoo",
                "download",
                "--snapshot",
                str(tmp_path / "s"),
                "--start",
                "2020-01-01",
                "--end",
                "2020-02-01",
            ]
        )

    def refuse(url, timeout):
        raise http_error(404)

    monkeypatch.setattr("invest_data.yahoo.http_get", refuse)
    assert (
        main(
            [
                "yahoo",
                "download",
                "--snapshot",
                str(tmp_path / "s"),
                "--symbols",
                "X",
                "--start",
                "2020-01-01",
                "--end",
                "2020-02-01",
            ]
        )
        == 1
    )
