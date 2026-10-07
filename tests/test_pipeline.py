"""End-to-end: components exchange only published artifacts, through their CLIs."""

import json
import os
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
    env = {
        **os.environ,
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "SNAPSHOT": str(snapshot),
        "LEDGER": str(ledger),
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
    manifest = json.loads((out / "eval" / "manifest.json").read_text())
    assert manifest["n_trials"] == 1
    assert manifest["external_benchmark"]["instrument"] == "SPY"
    assert manifest["signals"]["metadata"]["n_trials"] == 1
    metrics = json.loads((out / "eval" / "metrics.json").read_text())
    assert metrics["external_benchmark"]["beta"]["status"] == "ok"
    verdict = json.loads((out / "eval" / "verdict.json").read_text())
    assert verdict["factor"]["status"] == "not_confirmed"  # fixed formula, not yet confirmed
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
    eval_manifest = json.loads((out / "eval" / "manifest.json").read_text())
    assert {"code_revision", "code_dirty"} <= eval_manifest.keys()
    eval_manifest.update(code_revision="0" * 40, code_dirty=False)
    (out / "eval" / "manifest.json").write_text(json.dumps(eval_manifest))
    record = tmp_path / "record"
    saved = {str(p) for p in save_run.save_run(out, record, snapshot)}
    assert set(save_run.REQUIRED) | {"data/benchmark/manifest.json"} <= saved
    assert {"README.md", "snapshot/snapshot.json"} <= saved
    assert "data/market/manifest.json" in saved
    assert not any(p.endswith((".parquet", "trades.csv", "daily.csv")) for p in saved)
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
