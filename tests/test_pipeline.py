"""End-to-end: components exchange only published artifacts, through their CLIs."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "strategy-evaluation/examples/quantile_long_short.json"


def run(module: str, *args: str) -> str:
    out = subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


@pytest.mark.parametrize("fmt", ["csv", "sqlite", "parquet"])
def test_prepare_mine_evaluate(tmp_path, fmt):
    data, uni, fund = tmp_path / "data", tmp_path / "universe", tmp_path / "fund"
    search, signals, report = tmp_path / "search", tmp_path / "signals", tmp_path / "run"
    run(
        "invest_data.cli",
        "synthetic",
        "--out",
        str(data),
        "--format",
        fmt,
        "--instruments",
        "40",
        "--days",
        "500",
        "--universe-out",
        str(uni),
        "--fundamentals-out",
        str(fund),
    )

    run(
        "invest_mining.cli",
        "evaluate",
        "--data",
        str(data),
        "--universe",
        str(uni),
        "--fundamentals",
        str(fund),
        "--expr",
        "cs_rank(fund_book_to_price)",
        "--out",
        str(tmp_path / "fund_eval"),
    )
    assert json.loads((tmp_path / "fund_eval" / "metrics.json").read_text())["valid_dates"] > 0

    run(
        "invest_mining.cli",
        "search",
        "--data",
        str(data),
        "--universe",
        str(uni),
        "--trials",
        "40",
        "--top-k",
        "3",
        "--out",
        str(search),
    )
    confirmation = (search / "confirmation.csv").read_text().splitlines()
    assert len(confirmation) == 4
    split = json.loads((search / "config.json").read_text())["split"]
    confirm_start = split["confirmation"][0]

    # No ids or dates are copied by hand: export reads the search output directly.
    exported = json.loads(
        run(
            "invest_mining.cli",
            "export",
            "--data",
            str(data),
            "--universe",
            str(uni),
            "--from-search",
            str(search),
            "--out",
            str(signals),
            "--format",
            fmt,
        )
    )
    first_id = exported["factor_id"]
    assert first_id == confirmation[1].split(",")[0]  # frozen development ranking
    assert exported["start"] == confirm_start
    out = run(
        "invest_evaluation.cli",
        "run",
        "--data",
        str(data),
        "--signals",
        str(signals),
        "--universe",
        str(uni),
        "--config",
        str(CONFIG),
        "--out",
        str(report),
    )

    summary = json.loads(out)
    metrics = json.loads((report / "metrics.json").read_text())
    manifest = json.loads((report / "manifest.json").read_text())
    assert summary["sharpe"] == metrics["performance"]["sharpe"]["value"]
    assert manifest["signals"]["metadata"]["factor_id"] == first_id
    # The deflated Sharpe counts every search proposal (40 random + 7 templates).
    assert manifest["n_trials"] == 47
    statistics = json.loads((report / "statistics.json").read_text())
    assert statistics["deflated_sharpe"]["n_trials"] == 47
    # The development-selected candidate is replayed on confirmation-period decisions.
    trades = (report / "tables" / "trades.csv").read_text().splitlines()[1:]
    decisions = {line.split(",")[4] for line in trades if line.split(",")[4]}
    assert min(decisions) >= confirm_start


def test_synthetic_workflow_script(tmp_path):
    """The README's one-command workflow runs end to end on a small market."""
    env = {
        **os.environ,
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "INSTRUMENTS": "40",
        "DAYS": "500",
        "TRIALS": "40",
    }
    out = tmp_path / "wf"
    done = subprocess.run(
        ["bash", str(ROOT / "scripts/synthetic_workflow.sh"), str(out)],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
        env=env,
    )
    assert done.returncode == 0, done.stderr
    metrics = json.loads((out / "eval" / "metrics.json").read_text())
    assert metrics["performance"]["sharpe"]["status"] == "ok"
    assert json.loads((out / "eval" / "manifest.json").read_text())["n_trials"] == 47
    quantiles = json.loads((out / "quantiles" / "quantiles.json").read_text())
    assert [p["portfolio"] for p in quantiles["portfolios"]][:10] == [f"q{k}" for k in range(1, 11)]
    [experiment] = [
        json.loads(line) for line in (out / "mining/ledger.jsonl").read_text().splitlines()
    ]
    assert experiment["kind"] == "experiment"
    assert experiment["confirmation_use"] == "confirmatory"
    # The factor's confirmation evidence reaches the portfolio report beside, not inside,
    # the portfolio verdict.
    verdict = json.loads((out / "eval" / "verdict.json").read_text())
    assert verdict["factor"]["experiment_id"] == experiment["experiment_id"]
    assert verdict["factor"]["confirmation_use"] == "confirmatory"
    assert verdict["factor"]["factor_id"] == experiment["family"][0]
    assert verdict["portfolio"]["status"] in (
        "supported",
        "rejected",
        "inconclusive",
        "insufficient_data",
    )


@pytest.mark.parametrize("subset", [False, True])
def test_historical_workflow_script_replays_snapshot_offline(tmp_path, subset):
    """The Yahoo workflow runs end to end from a saved (here fabricated) snapshot."""
    from invest_data.sources import SyntheticConfig, synthetic_market
    from invest_data.testing import write_fake_snapshot

    bars = synthetic_market(SyntheticConfig(n_instruments=31, n_days=300, seed=11))
    bars["instrument"] = bars["instrument"].replace({"SYN000": "SPY"})
    snapshot = tmp_path / "snapshot"
    write_fake_snapshot(bars, snapshot, adj_factors={"SYN001": 0.9})
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text((ROOT / "ledgers/yahoo-test.jsonl").read_text())
    # A minimum cross-section that differs from the bucket count. With the example config's
    # 10, the diagnostics report 10 with or without the workflow's --min-cross-section, and
    # the comparison of the two reports below could not fail (BH-2026-10-08-1).
    config = json.loads(CONFIG.read_text())
    config["strategy"]["min_names"] = 12
    (tmp_path / "config.json").write_text(json.dumps(config))
    env = {
        **os.environ,
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "SNAPSHOT": str(snapshot),
        "LEDGER": str(ledger),
        "CONFIG": str(tmp_path / "config.json"),
        "SYMBOLS_FILE": "/nonexistent",  # never read: the snapshot exists
        "START": "2020-03-01" if subset else "",
        "END": "2020-11-30" if subset else "",
    }
    out = tmp_path / "wf"
    done = subprocess.run(
        ["bash", str(ROOT / "scripts/historical_workflow.sh"), str(out)],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
        env=env,
    )
    assert done.returncode == 0, done.stderr
    assert "no download" in done.stderr
    # Yahoo bars have no as-traded close, so the price floor is off in both evaluations,
    # while the rest of the configuration is the given one's.
    assert "execution.min_price 1.0 -> 0" in done.stderr
    for used in (
        json.loads((out / "eval" / "config.json").read_text()),
        json.loads((out / "quantiles" / "config.json").read_text())["backtest"],
    ):
        assert used["execution"]["min_price"] == 0.0
        assert used["strategy"] == {**used["strategy"], **config["strategy"]}
        assert used["execution"] == {**used["execution"], **config["execution"], "min_price": 0.0}
    manifest = json.loads((out / "eval" / "manifest.json").read_text())
    assert manifest["n_trials"] == 1
    assert manifest["external_benchmark"]["instrument"] == "SPY"
    assert manifest["signals"]["metadata"]["n_trials"] == 1
    metrics = json.loads((out / "eval" / "metrics.json").read_text())
    assert metrics["external_benchmark"]["beta"]["status"] == "ok"
    verdict = json.loads((out / "eval" / "verdict.json").read_text())
    assert verdict["factor"]["status"] == "not_confirmed"  # fixed formula, not yet confirmed
    quantiles = json.loads((out / "quantiles" / "quantiles.json").read_text())
    assert quantiles["report_version"] == 2 and len(quantiles["portfolios"]) == 19
    # 30 names: the 1% tails never reach five names, so they report no performance.
    tails = {p["portfolio"]: p for p in quantiles["portfolios"]}
    assert tails["top_0.01"]["status"] == "insufficient_data"
    assert tails["top_0.01"]["net_sharpe"] is None
    market = json.loads((out / "data" / "market" / "manifest.json").read_text())
    assert "SPY" not in market["provenance"]["snapshot"]["files"]
    assert market["metadata"]["universe"].endswith("(survivorship-biased)")
    assert "S&P 100" not in market["metadata"]["universe"]
    requested = market["provenance"]["snapshot"]["request"]
    selection = market["provenance"]["selection"]
    first, last = (env["START"], env["END"]) if subset else (requested["start"], requested["end"])
    assert market["dataset_id"] == f"yahoo-test-{first}-{last}"
    assert selection["start"] == first and selection["end"] == last
    from invest_data.schemas import read_market_bars

    _, published = read_market_bars(out / "data" / "market")
    # Diagnostics and exported signals use the same frozen orientation, not reversed
    # meanings for q1/q10. Compare membership on the evaluator's eligible cross-section.
    import pandas as pd

    from invest_mining.diagnostics import (
        BUCKET_RULE,
        TAIL_RULE,
        assign_buckets,
        tail_percentiles,
    )
    from invest_mining.expressions import build_panel, evaluate

    diagnostic_config = json.loads((out / "mining/diagnostics/config.json").read_text())
    factor = json.loads((out / "mining/factor.json").read_text())
    assert diagnostic_config["orientation"] == factor["orientation"] == -1
    # Both reports apply the same minimum cross-section threshold, the config's min_names.
    assert diagnostic_config["min_cross_section"] == quantiles["min_cross_section"] == 12
    assert diagnostic_config["tail_rule"] == TAIL_RULE
    assert diagnostic_config["bucket_rule"] == BUCKET_RULE
    values = evaluate(factor["expression"], build_panel(published)) * factor["orientation"]
    members = pd.read_csv(
        out / "quantiles/tables/memberships.csv.gz",
        parse_dates=["decision_date"],
        float_precision="round_trip",
    )
    for date, group in members.groupby("decision_date"):
        if len(group) < 10:
            continue
        expected = values.loc[[date], group["instrument"]]
        buckets = assign_buckets(expected, 10).iloc[0]
        actual = group.set_index("instrument")["bucket"]
        # CSV may infer StringDtype while the bundle reader uses object identifiers.
        # Compare every instrument's assignment, independent of pandas storage dtype.
        assert buckets.astype(int).to_dict() == actual.to_dict()
        # Tails: q is the percentile counted from the highest score (tail_returns' rule).
        from_top = tail_percentiles(expected)["top"].iloc[0]
        assert from_top.to_dict() == group.set_index("instrument")["pct_from_top"].to_dict()
    assert published["date"].min().date().isoformat() >= first
    assert published["date"].max().date().isoformat() <= last
    assert set(published["date"]) == set(bars.loc[bars["date"].between(first, last), "date"])
    assert market["provenance"]["source_metadata"]["SYN001"]["exchangeName"] == "NMS"
    # These dates lie inside the recorded inspected window, so the ledger is unchanged.
    assert ledger.read_text() == (ROOT / "ledgers/yahoo-test.jsonl").read_text()

    # The committed run record holds reports and manifests, never vendor data or bundles.
    # Records need committed code; this test may run from a dirty tree or installed wheels,
    # so it states a clean revision after checking the fields exist.
    save_run = _save_run_module()
    for part in ("eval", "quantiles"):
        code_manifest = json.loads((out / part / "manifest.json").read_text())
        assert {"code_revision", "code_dirty"} <= code_manifest.keys()
        code_manifest.update(code_revision="0" * 40, code_dirty=False)
        (out / part / "manifest.json").write_text(json.dumps(code_manifest))
    record = tmp_path / "record"
    saved = {str(p) for p in save_run.save_run(out, record, snapshot)}
    assert set(save_run.REQUIRED) | {"data/benchmark/manifest.json"} <= saved
    assert {"README.md", "snapshot/snapshot.json"} <= saved
    assert "data/market/manifest.json" in saved
    # Bundles, trade and daily ledgers and the quantile membership and daily-return tables
    # stay out; only a record file over the size limit may end in .gz (none does here).
    assert not any(p.endswith((".parquet", "trades.csv", "daily.csv")) for p in saved)
    assert not any(p.endswith(("memberships.csv.gz", "daily_returns.csv.gz")) for p in saved)
    assert not any(p.endswith(".gz") for p in saved)
    assert not any(p.startswith("snapshot/") and p != "snapshot/snapshot.json" for p in saved)
    assert json.loads((record / "eval/verdict.json").read_text()) == verdict
    readme = (record / "README.md").read_text()
    assert market["dataset_id"] in readme and "`not_confirmed`" in readme
    with pytest.raises(SystemExit, match="never overwritten"):
        save_run.save_run(out, record, snapshot)


def _save_run_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("save_run", ROOT / "scripts/save_run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo, *args):
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _clean_checkout_of_the_workflow(path):
    """A committed copy of the workflow script and save_run.py. RECORD needs a clean
    checkout and the one running the tests may not be clean; the script resolves its own
    folder, so everything else it needs comes from this checkout through the environment."""
    (path / "scripts").mkdir(parents=True)
    for name in ("historical_workflow.sh", "save_run.py"):
        shutil.copy(ROOT / "scripts" / name, path / "scripts")
    _git(path, "init", "-q")
    _git(path, "add", "scripts")
    _git(path, "commit", "-q", "-m", "workflow")
    return path / "scripts/historical_workflow.sh"


def _run_workflow(script, out, env):
    return subprocess.run(
        ["bash", str(script), str(out)],
        capture_output=True,
        text=True,
        check=False,
        cwd=script.parents[1],
        env={
            **os.environ,
            "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
            **env,
        },
    )


def _no_global_git_config(monkeypatch, tmp_path):
    """Git reads no global configuration for the rest of the test.

    The developer's excludes file would otherwise decide what the workflow's own Git calls
    and the temporary repository see: one that ignores ``out/``, as JetBrains' template
    does, passes the output-location check for ``<checkout>/out``, and ``commit.gpgsign``
    would stop the checkout's commits. The evaluator's ``code_dirty`` and the test's own
    ``code_revision()`` then read the same configuration. Git before 2.32 does not know
    ``GIT_CONFIG_GLOBAL`` and would read the developer's configuration as before, so the
    test first checks that Git reads the file the variable names, and is skipped when it
    does not. The system configuration is left out for the same reason."""
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    # The deprecated GIT_CONFIG variable names a config file for `git config` alone, which
    # then refuses --global ("only one config file at a time"), and the check below would
    # blame the Git version.
    monkeypatch.delenv("GIT_CONFIG", raising=False)
    marker = tmp_path / "gitconfig-marker"
    marker.write_text(f"[invest]\n\tisolated = {tmp_path.name}\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(marker))
    read = subprocess.run(
        ["git", "config", "--global", "invest.isolated"],
        capture_output=True,
        text=True,
        check=False,
    )
    if read.stdout.strip() != tmp_path.name:
        version = subprocess.run(["git", "--version"], capture_output=True, text=True, check=False)
        pytest.skip(
            "isolating the global Git configuration needs GIT_CONFIG_GLOBAL (Git 2.32 and "
            f"later); {version.stdout.strip() or 'git'} ignores it"
        )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-global-gitconfig"))


def test_historical_workflow_record_run_records_an_uninspected_window_first(tmp_path, monkeypatch):
    """K3: the diagnostics append the market bundle's dates to the ledger unless an
    inspection already covers them, which modified the tracked ledger before the evaluation
    recorded ``code_dirty``, so ``save_run.py`` refused every record of a new window. A
    RECORD run now records the inspection first and stops before publishing; the rerun
    finds the window recorded and leaves the ledger as it is."""
    from invest_data.sources import SyntheticConfig, synthetic_market
    from invest_data.testing import write_fake_snapshot

    _no_global_git_config(monkeypatch, tmp_path)
    bars = synthetic_market(SyntheticConfig(n_instruments=31, n_days=300, seed=11))
    bars["instrument"] = bars["instrument"].replace({"SYN000": "SPY"})
    snapshot = tmp_path / "snapshot"
    write_fake_snapshot(bars, snapshot, adj_factors={"SYN001": 0.9})
    script = _clean_checkout_of_the_workflow(tmp_path / "checkout")
    # Only the reservation: nothing records the fabricated snapshot's dates as inspected.
    committed = [
        json.loads(line)
        for line in (ROOT / "ledgers/yahoo-test.jsonl").read_text().splitlines()
        if line.strip()
    ]
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        "".join(json.dumps(e) + "\n" for e in committed if e["kind"] == "reservation")
    )
    env = {
        "SNAPSHOT": str(snapshot),
        "LEDGER": str(ledger),
        "CONFIG": str(CONFIG),
        "SYMBOLS_FILE": "/nonexistent",
        "RECORD": str(tmp_path / "record"),
        "START": "",
        "END": "",
    }
    out = tmp_path / "wf"
    done = _run_workflow(script, out, env)
    assert done.returncode != 0
    assert "commit it, then rerun" in done.stderr, done.stderr
    assert not out.exists() and not (tmp_path / "record").exists()
    entries = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert [e["kind"] for e in entries] == ["reservation", "inspection"]
    # The rerun, again with RECORD, finds the window recorded, appends nothing and goes on
    # to the run. Its last step, save_run.py, needs committed code, and the evaluator
    # records the state of the checkout running the tests (dirty, or an installed wheel):
    # only that refusal is accepted as a failure, once every workflow output exists, and
    # only when that state, read before the rerun, already warranted it, so a run that
    # dirties the checkout itself cannot hide behind it.
    from invest_evaluation.cli import code_revision

    revision, dirty = code_revision()
    recorded = ledger.read_text()
    done = _run_workflow(script, out, env)
    assert "commit it, then rerun" not in done.stderr, done.stderr
    if revision and dirty is False:
        assert done.returncode == 0, done.stderr
    elif done.returncode != 0:
        refusal = "rerun from a clean checkout" if revision else "no code revision"
        assert refusal in done.stderr, done.stderr
    assert (tmp_path / "record").is_dir() == (done.returncode == 0)
    assert ledger.read_text() == recorded
    market = json.loads((out / "data/market/manifest.json").read_text())
    # The pre-check records the cleaned bundle's dates, as the diagnostics do; they equal
    # the snapshot's observed range here because cleaning rejects nothing.
    selection = market["provenance"]["selection"]
    assert entries[-1]["window"] == {
        "start": selection["observed_start"],
        "end": selection["observed_end"],
    }
    assert entries[-1]["dataset_id"] == market["dataset_id"]
    assert (out / "quantiles/manifest.json").is_file()


@pytest.mark.parametrize("invalid", ["benchmark", "benchmark_rejected", "config", "stale_output"])
def test_historical_workflow_record_run_leaves_the_ledger_on_an_invalid_invocation(
    tmp_path, monkeypatch, invalid
):
    """INV-PR40-001: without RECORD, a benchmark missing from the snapshot, a benchmark whose
    every bar cleaning rejects, an invalid CONFIG or a market bundle left in OUT_DIR by an
    earlier run that stopped stops the workflow at publication or at the CONFIG step, before
    the diagnostics record the window. The RECORD pre-check, which runs before both, must
    refuse the same invocation and leave the ledger as it was, instead of recording an
    inspection that the retry cannot use."""
    from invest_data.sources import SyntheticConfig, synthetic_market
    from invest_data.testing import write_fake_snapshot

    _no_global_git_config(monkeypatch, tmp_path)
    bars = synthetic_market(SyntheticConfig(n_instruments=31, n_days=300, seed=11))
    bars["instrument"] = bars["instrument"].replace({"SYN000": "SPY"})
    if invalid == "benchmark_rejected":  # each SPY bar's high is below its open and close
        spy = bars["instrument"] == "SPY"
        bars.loc[spy, ["high", "low"]] = bars.loc[spy, ["open", "close"]].min(axis=1) * 0.9
    snapshot = tmp_path / "snapshot"
    write_fake_snapshot(bars, snapshot)
    script = _clean_checkout_of_the_workflow(tmp_path / "checkout")
    committed = [
        json.loads(line)
        for line in (ROOT / "ledgers/yahoo-test.jsonl").read_text().splitlines()
        if line.strip()
    ]
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        "".join(json.dumps(e) + "\n" for e in committed if e["kind"] == "reservation")
    )
    before = ledger.read_bytes()
    config = json.loads(CONFIG.read_text())
    if invalid == "config":
        config["strategy"]["min_names"] = 0  # BacktestConfig refuses it
    (tmp_path / "config.json").write_text(json.dumps(config))
    env = {
        "SNAPSHOT": str(snapshot),
        "LEDGER": str(ledger),
        "CONFIG": str(tmp_path / "config.json"),
        "SYMBOLS_FILE": "/nonexistent",
        "RECORD": str(tmp_path / "record"),
        "START": "",
        "END": "",
        "BENCHMARK": "QQQ" if invalid == "benchmark" else "SPY",
    }
    out = tmp_path / "wf"
    if invalid == "stale_output":
        (out / "data/market").mkdir(parents=True)
    done = _run_workflow(script, out, env)
    assert done.returncode != 0
    assert "commit it, then rerun" not in done.stderr, done.stderr
    expected = {
        "benchmark": "QQQ",
        "benchmark_rejected": "yahoo-test-SPY-",
        "config": "min_names",
        "stale_output": "already exists",
    }
    assert expected[invalid] in done.stderr, done.stderr
    if invalid == "benchmark_rejected":
        assert "every row was rejected" in done.stderr, done.stderr
    assert ledger.read_bytes() == before
    assert out.exists() == (invalid == "stale_output")
    assert not (tmp_path / "record").exists()
    # Without RECORD the same invocation stops as well, and the ledger stays as it was.
    plain = tmp_path / "wf-plain"
    if invalid == "stale_output":
        (plain / "data/market").mkdir(parents=True)
    done = _run_workflow(script, plain, {**env, "RECORD": ""})
    assert done.returncode != 0
    assert expected[invalid] in done.stderr, done.stderr
    assert ledger.read_bytes() == before


def test_historical_workflow_record_run_refuses_an_unclean_checkout_before_work(
    tmp_path, monkeypatch
):
    """K15: ``code_dirty`` counts untracked files Git does not ignore, so the workflow's
    own check does too, before any work, and outputs inside the checkout that Git would
    not ignore are refused for the same reason."""
    _no_global_git_config(monkeypatch, tmp_path)
    checkout = tmp_path / "checkout"
    script = _clean_checkout_of_the_workflow(checkout)
    env = {"SNAPSHOT": str(tmp_path / "missing-snapshot"), "RECORD": str(tmp_path / "record")}
    out = tmp_path / "wf"
    (checkout / "notes.txt").write_text("")
    done = _run_workflow(script, out, env)
    assert done.returncode != 0
    assert "remove or ignore untracked files" in done.stderr, done.stderr
    assert not out.exists()
    (checkout / "notes.txt").unlink()
    for inside in (checkout / "out", checkout / "runs" / "wf"):
        done = _run_workflow(script, inside, env)
        assert done.returncode != 0
        assert "under a folder Git ignores" in done.stderr, done.stderr
        assert not inside.exists()
    # Ignored outputs (the ignored folder itself included, before it exists) and outputs
    # outside the checkout pass both checks; the run then fails at the download, which has
    # no symbols file here.
    (checkout / ".gitignore").write_text("/artifacts/\n")
    _git(checkout, "add", ".gitignore")
    _git(checkout, "commit", "-q", "-m", "ignore artifacts")
    for allowed in (checkout / "artifacts", checkout / "artifacts" / "wf", out):
        done = _run_workflow(script, allowed, {**env, "SYMBOLS_FILE": "/nonexistent"})
        assert done.returncode != 0
        assert "RECORD needs" not in done.stderr, done.stderr
        assert not allowed.exists()


def test_historical_workflow_refuses_an_existing_record_before_work(tmp_path):
    record = tmp_path / "record"
    record.mkdir()
    env = {
        **os.environ,
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "SNAPSHOT": str(tmp_path / "missing-snapshot"),
        "RECORD": str(record),
    }
    done = subprocess.run(
        ["bash", str(ROOT / "scripts/historical_workflow.sh"), str(tmp_path / "wf")],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
        env=env,
    )
    assert done.returncode != 0
    assert "never overwritten" in done.stderr
    assert not (tmp_path / "wf").exists()


def test_historical_workflow_rejects_out_of_snapshot_range_before_publication(tmp_path):
    from invest_data.sources import SyntheticConfig, synthetic_market
    from invest_data.testing import write_fake_snapshot

    write_fake_snapshot(
        synthetic_market(SyntheticConfig(n_instruments=2, n_days=80)), tmp_path / "s"
    )
    out = tmp_path / "wf"
    done = subprocess.run(
        ["bash", str(ROOT / "scripts/historical_workflow.sh"), str(out)],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
            "SNAPSHOT": str(tmp_path / "s"),
            "START": "2019-01-01",
            "END": "2024-01-01",
        },
    )
    assert done.returncode != 0
    assert "within the snapshot" in done.stderr
    assert not out.exists()


def test_historical_workflow_refuses_the_reserved_window_before_download(tmp_path):
    """The committed Yahoo ledger keeps 2025 onward untouched for confirmation."""
    out = tmp_path / "wf"
    done = subprocess.run(
        ["bash", str(ROOT / "scripts/historical_workflow.sh"), str(out)],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
            "SYMBOLS_FILE": "/nonexistent",
            "END": "2025-06-30",
        },
    )
    assert done.returncode != 0
    assert "reserved confirmation window 2025-01-01..open" in done.stderr
    assert not out.exists()
