"""Portfolio verdicts follow declared rules and stay separate from factor evidence."""

import json

import pandas as pd
import pytest

from invest_data.schemas import publish_market_bars, publish_signals
from invest_data.sources import SYNTHETIC_METADATA
from invest_evaluation.cli import main
from invest_evaluation.config import BacktestConfig, ValidationConfig
from invest_evaluation.validation import factor_section, portfolio_verdict

RETURNS = pd.Series(0.001, index=pd.bdate_range("2020-01-01", periods=300))
SCENARIOS = pd.DataFrame({"scenario": ["base", "costs_x2", "delay_1"], "sharpe": [1.0, 0.5, 0.2]})
METRICS = {"benchmark": {"information_ratio": {"value": 0.3, "status": "ok"}}}


def _stats(ci=(0.2, 1.8), dsr=0.99):
    return {
        "bootstrap": {"status": "ok", "level": 0.95, "sharpe_ci": list(ci)},
        "deflated_sharpe": {"status": "ok", "dsr": dsr, "n_trials": 3},
    }


def _verdict(rules=None, returns=RETURNS, metrics=METRICS, stats=None, scenarios=SCENARIOS):
    rules = rules or ValidationConfig()
    return portfolio_verdict(rules, returns, metrics, stats or _stats(), scenarios)


def test_supported_only_when_every_declared_rule_passes():
    verdict = _verdict(ValidationConfig(benchmark="universe"))
    assert verdict["status"] == "supported" and verdict["reasons"] == []
    assert verdict["evaluation_window"] == {"start": "2020-01-01", "end": "2021-02-23"}
    assert [c["name"] for c in verdict["checks"]] == [
        "sessions",
        "net_sharpe_ci",
        "deflated_sharpe",
        "stress:costs_x2",
        "stress:delay_1",
        "benchmark:universe",
    ]
    assert verdict["rules"]["stress_scenarios"] == ["costs_x2", "delay_1"]


@pytest.mark.parametrize(
    ("kwargs", "status", "failed"),
    [
        ({"stats": _stats(ci=(-1.5, -0.1))}, "rejected", "net_sharpe_ci"),
        ({"stats": _stats(ci=(-0.3, 1.2))}, "inconclusive", "net_sharpe_ci"),
        ({"stats": _stats(dsr=0.5)}, "inconclusive", "deflated_sharpe"),
        (
            {"scenarios": SCENARIOS.assign(sharpe=[1.0, -0.2, 0.3])},
            "inconclusive",
            "stress:costs_x2",
        ),
        ({"scenarios": None}, "inconclusive", "stress:costs_x2"),
        (
            {"rules": ValidationConfig(benchmark="external"), "metrics": {}},
            "inconclusive",
            "benchmark:external",
        ),
        ({"returns": RETURNS.iloc[:100]}, "insufficient_data", "sessions"),
        (
            {"stats": {"bootstrap": {"status": "undefined", "reason": "zero_dispersion"}}},
            "insufficient_data",
            "net_sharpe_ci",
        ),
    ],
)
def test_verdict_statuses_name_the_rule_behind_them(kwargs, status, failed):
    verdict = _verdict(**kwargs)
    assert verdict["status"] == status
    assert any(reason.startswith(f"{failed}:") for reason in verdict["reasons"])


def test_undefined_scenario_sharpe_cannot_support_a_portfolio():
    verdict = _verdict(scenarios=SCENARIOS.assign(sharpe=[1.0, float("nan"), 0.3]))
    check = next(c for c in verdict["checks"] if c["name"] == "stress:costs_x2")
    assert verdict["status"] == "inconclusive" and check["status"] == "undefined"


def test_factor_section_copies_evidence_or_reports_its_absence():
    assert factor_section({"factor_id": "f"}) == {
        "status": "not_confirmed",
        "factor_id": "f",
        "reason": "the signals carry no factor confirmation evidence",
    }
    evidence = {"status": "rejected", "factor_id": "f"}
    assert factor_section({"factor_id": "f", "factor_evidence": evidence}) == evidence


@pytest.mark.parametrize(
    "validation",
    [
        {"min_sessions": 10},
        {"min_deflated_sharpe": 1.5},
        {"stress_scenarios": "costs_x2"},
        {"stress_scenarios": ["delay_1", "delay_1"]},
        {"benchmark": "spy"},
        {"unknown": 1},
    ],
)
def test_invalid_validation_rules_are_rejected(validation):
    with pytest.raises(ValueError):
        BacktestConfig.from_dict({"validation": validation})


def _evidence():
    return {
        "evidence_version": 1,
        "factor_id": "rev5",
        "experiment_id": "e_1",
        "source": "confirm",
        "confirmation_use": "exploratory",
        "test_outcome": "confirmation_passed",
        "status": "exploratory",
        "family_size": 1,
        "confirmation_window": {"start": "2020-06-01", "end": "2020-12-31"},
        "statistics": {
            "confirm_mean_rank_ic": 0.05,
            "confirm_t": 4.0,
            "p_one_sided": 3e-5,
            "p_holm": 3e-5,
            "n_dates": 150,
        },
    }


def test_cli_reports_factor_and_portfolio_verdicts_separately(
    tmp_path, market, reversal_signals, capsys
):
    publish_market_bars(market, tmp_path / "m", dataset_id="m", metadata=SYNTHETIC_METADATA)
    metadata = {"factor_id": "rev5", "horizon_days": 1, "factor_evidence": _evidence()}
    publish_signals(reversal_signals, tmp_path / "s", dataset_id="s", metadata=metadata)
    base = ["run", "--data", str(tmp_path / "m"), "--signals", str(tmp_path / "s")]
    assert main([*base, "--out", str(tmp_path / "run")]) == 0
    printed = json.loads(capsys.readouterr().out)
    verdict = json.loads((tmp_path / "run" / "verdict.json").read_text())
    assert verdict["factor"] == _evidence()
    assert printed["factor_status"] == "exploratory"
    assert printed["portfolio_status"] == verdict["portfolio"]["status"]
    assert verdict["portfolio"]["status"] in ("supported", "rejected", "inconclusive")
    saved = json.loads((tmp_path / "run" / "config.json").read_text())
    assert saved["validation"]["stress_scenarios"] == ["costs_x2", "delay_1"]
    report = (tmp_path / "run" / "report.md").read_text()
    factor_part, portfolio_part = report.split("## Portfolio validation")
    assert "## Factor confirmation" in factor_part and "**exploratory**" in factor_part
    assert "e_1 (confirm)" in factor_part and "2020-06-01 to 2020-12-31" in factor_part
    assert f"**{verdict['portfolio']['status']}**" in portfolio_part
    assert "| stress:delay_1 |" in portfolio_part

    # Without scenarios, the required stress checks are not run: never supported.
    assert main([*base, "--no-scenarios", "--out", str(tmp_path / "quick")]) == 0
    quick = json.loads((tmp_path / "quick" / "verdict.json").read_text())["portfolio"]
    assert quick["status"] != "supported"
    assert any(r.startswith("stress:costs_x2: not_run") for r in quick["reasons"])

    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"validation": {"stress_scenarios": ["costs_x9"]}}))
    with pytest.raises(SystemExit, match="unknown scenarios"):
        main([*base, "--config", str(cfg), "--out", str(tmp_path / "x")])
    cfg.write_text(json.dumps({"validation": {"benchmark": "external"}}))
    with pytest.raises(SystemExit, match="needs --benchmark"):
        main([*base, "--config", str(cfg), "--out", str(tmp_path / "x")])
    assert not (tmp_path / "x").exists()
