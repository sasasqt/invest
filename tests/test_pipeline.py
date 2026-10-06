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
    # Only out-of-sample (confirmation-period) decisions are traded.
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
