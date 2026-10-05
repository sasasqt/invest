"""End-to-end: components exchange only published artifacts, through their CLIs."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[1]


def run(module: str, *args: str) -> str:
    out = subprocess.run(
        [sys.executable, "-m", module, *args], capture_output=True, text=True, check=False, cwd=ROOT
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


@pytest.mark.parametrize("fmt", ["csv", "sqlite"])
def test_prepare_mine_evaluate(tmp_path, fmt):
    data, search, signals, report = (tmp_path / p for p in ("data", "search", "signals", "run"))
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
    )
    run(
        "invest_mining.cli",
        "search",
        "--data",
        str(data),
        "--trials",
        "40",
        "--top-k",
        "3",
        "--out",
        str(search),
    )
    confirmation = (search / "confirmation.csv").read_text().splitlines()
    assert len(confirmation) == 4
    best = sorted((search / "factors").glob("*.json"))
    first_id = confirmation[1].split(",")[0]
    factor = next(p for p in best if p.stem == first_id)
    split = json.loads((search / "config.json").read_text())["split"]
    confirm_start = split["confirmation"][0]
    run(
        "invest_mining.cli",
        "export",
        "--data",
        str(data),
        "--factor",
        str(factor),
        "--out",
        str(signals),
        "--start",
        confirm_start,
        "--format",
        fmt,
    )
    out = run(
        "invest_evaluation.cli",
        "run",
        "--data",
        str(data),
        "--signals",
        str(signals),
        "--config",
        str(ROOT / "data-pipeline/strategy-evaluation/examples/quantile_long_short.json"),
        "--out",
        str(report),
        "--n-trials",
        "47",
    )
    summary = json.loads(out)
    metrics = json.loads((report / "metrics.json").read_text())
    manifest = json.loads((report / "manifest.json").read_text())
    assert summary["sharpe"] == metrics["performance"]["sharpe"]["value"]
    assert manifest["signals"]["metadata"]["factor_id"] == first_id
    # Only out-of-sample (confirmation-period) decisions are traded.
    trades = (report / "tables" / "trades.csv").read_text().splitlines()[1:]
    decisions = {line.split(",")[4] for line in trades if line.split(",")[4]}
    assert min(decisions) >= confirm_start
