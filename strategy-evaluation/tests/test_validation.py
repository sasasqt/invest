"""Portfolio verdicts follow declared rules and stay separate from factor evidence."""

import json

import numpy as np
import pandas as pd
import pytest

from invest_data.schemas import publish_market_bars, publish_signals
from invest_data.sources import SYNTHETIC_METADATA
from invest_evaluation.cli import main
from invest_evaluation.config import BacktestConfig, ValidationConfig
from invest_evaluation.metrics import return_metrics
from invest_evaluation.stats import strategy_statistics
from invest_evaluation.validation import factor_section, portfolio_verdict

RETURNS = pd.Series(0.001, index=pd.bdate_range("2020-01-01", periods=300))
SCENARIOS = pd.DataFrame({"scenario": ["base", "costs_x2", "delay_1"], "sharpe": [1.0, 0.5, 0.2]})
METRICS = {
    "performance": {"sharpe": {"value": 1.0, "status": "ok"}},
    "benchmark": {"information_ratio": {"value": 0.3, "status": "ok"}},
}


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
        "solvency",
        "net_sharpe_validity",
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


@pytest.mark.parametrize("loss", [-1.0, -1.1])
def test_insolvency_overrides_positive_statistics_without_stress_rules(loss):
    returns = pd.Series(
        np.random.default_rng(0).normal(0.044, 0.001, 400),
        index=pd.bdate_range("2020-01-01", periods=400),
    )
    returns.iloc[-1] = loss
    performance = return_metrics(returns, v0=1000.0, annualization=252)
    metrics = {"performance": {key: value.to_dict() for key, value in performance.items()}}
    stats = strategy_statistics(returns, 252)
    assert stats["bootstrap"]["sharpe_ci"][0] > 0
    assert stats["deflated_sharpe"]["dsr"] >= 0.95
    assert metrics["performance"]["sharpe"]["status"] == "invalid_input"
    verdict = portfolio_verdict(
        ValidationConfig(stress_scenarios=[]), returns, metrics, stats, None
    )
    assert verdict["status"] == "rejected"
    assert any(reason.startswith("solvency: fail") for reason in verdict["reasons"])


def test_known_insolvency_is_rejected_even_with_too_few_returns():
    returns = pd.Series([0.1, -1.0], index=pd.bdate_range("2020-01-01", periods=2))
    verdict = portfolio_verdict(ValidationConfig(), returns, {}, {}, None)
    assert verdict["status"] == "rejected"
    assert any(reason.startswith("solvency: fail") for reason in verdict["reasons"])


def test_saved_insolvency_metric_overrides_apparently_valid_returns():
    metrics = {
        "performance": {
            **METRICS["performance"],
            "insolvency": {"value": "2020-06-01", "status": "ok"},
        }
    }
    assert _verdict(metrics=metrics)["status"] == "rejected"


@pytest.mark.parametrize(
    "sharpe",
    [
        None,
        {"value": 1.0, "status": "invalid_input", "reason": "invalid_net_returns"},
        {"value": None, "status": "undefined", "reason": "zero_dispersion"},
        {"value": float("inf"), "status": "ok"},
        {"value": True, "status": "ok"},
    ],
)
def test_invalid_or_missing_base_sharpe_cannot_be_supported(sharpe):
    verdict = _verdict(
        rules=ValidationConfig(stress_scenarios=[]), metrics={"performance": {"sharpe": sharpe}}
    )
    assert verdict["status"] == "inconclusive"
    assert any(reason.startswith("net_sharpe_validity: undefined") for reason in verdict["reasons"])


def test_missing_and_non_finite_returns_cannot_establish_solvency():
    for returns in (RETURNS.iloc[:0], RETURNS.copy()):
        if len(returns):
            returns.iloc[-1] = float("inf")
        verdict = _verdict(returns=returns)
        assert verdict["status"] != "supported"
        assert any(reason.startswith("solvency: undefined") for reason in verdict["reasons"])


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
        "evidence_version": 2,
        "factor_id": "rev5",
        "horizon_days": 1,
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
    assert verdict["verdict_version"] == 2
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


def test_cli_rejects_insolvent_portfolio_with_positive_statistics(tmp_path, capsys):
    dates = pd.bdate_range("2020-01-01", periods=400)
    closes = 10 * np.cumprod(np.full(len(dates), 1.04))
    opens = np.r_[10.0, closes[:-1]]
    market = pd.DataFrame(
        {
            "date": dates,
            "instrument": "A",
            "open": opens,
            "close": closes,
            "high": closes,
            "low": opens,
            "volume": 1e15,
        }
    )
    signals = pd.DataFrame({"decision_date": dates, "instrument": "A", "score": 1.0})
    publish_market_bars(market, tmp_path / "m", dataset_id="m", metadata=SYNTHETIC_METADATA)
    publish_signals(
        signals, tmp_path / "s", dataset_id="s", metadata={"factor_id": "fixed", "horizon_days": 1}
    )
    cfg = {
        "initial_capital": 1000.0,
        "strategy": {
            "long_fraction": 1.0,
            "short_fraction": 0.0,
            "gross_leverage": 1.1,
            "rebalance_every": 1,
            "min_names": 1,
        },
        "execution": {"max_participation": 1.0, "min_price": 0.0},
        "costs": {
            "commission_bps": 0,
            "half_spread_bps": 0,
            "impact_coef": 0,
            "borrow_bps_annual": 0,
            "adv_window": 1,
            "vol_window": 2,
        },
        "validation": {"stress_scenarios": []},
    }
    (tmp_path / "cfg.json").write_text(json.dumps(cfg))
    (tmp_path / "events.json").write_text(
        json.dumps(
            [
                {"date": str(dates[-1].date()), "instrument": "A", "settlement_price": 0.0},
            ]
        )
    )
    out = tmp_path / "run"
    assert (
        main(
            [
                "run",
                "--data",
                str(tmp_path / "m"),
                "--signals",
                str(tmp_path / "s"),
                "--config",
                str(tmp_path / "cfg.json"),
                "--delistings",
                str(tmp_path / "events.json"),
                "--no-scenarios",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["portfolio_status"] == "rejected"
    stats = json.loads((out / "statistics.json").read_text())
    assert stats["bootstrap"]["sharpe_ci"][0] > 0
    assert stats["deflated_sharpe"]["dsr"] >= 0.95
    perf = json.loads((out / "metrics.json").read_text())["performance"]
    assert perf["sharpe"]["reason"] == "insolvent_wealth_path"
    verdict = json.loads((out / "verdict.json").read_text())["portfolio"]
    assert verdict["status"] == "rejected"
    assert any(reason.startswith("solvency: fail") for reason in verdict["reasons"])
    report = (out / "report.md").read_text()
    assert "Status: **rejected**" in report and "| solvency | fail |" in report


def test_cli_refuses_fewer_trials_than_the_search_family(tmp_path, market, reversal_signals):
    """`--n-trials` cannot undercut the candidates a search tried (K8)."""
    publish_market_bars(market, tmp_path / "m", dataset_id="m", metadata=SYNTHETIC_METADATA)
    start = str(reversal_signals["decision_date"].min().date())
    evidence = {
        **_evidence(),
        "source": "search",
        "confirmation_use": "confirmatory",
        "status": "confirmation_passed",
        "family_size": 3,
        "confirmation_window": {"start": start, "end": "2030-12-31"},
    }
    metadata = {"factor_id": "rev5", "horizon_days": 1, "n_trials": 40, "factor_evidence": evidence}
    publish_signals(reversal_signals, tmp_path / "s", dataset_id="s", metadata=metadata)
    base = ["run", "--data", str(tmp_path / "m"), "--signals", str(tmp_path / "s")]
    with pytest.raises(SystemExit, match="below the 40 candidates"):
        main([*base, "--n-trials", "39", "--out", str(tmp_path / "x")])
    assert not (tmp_path / "x").exists()
    assert main([*base, "--n-trials", "40", "--no-scenarios", "--out", str(tmp_path / "ok")]) == 0
