"""Portfolio verdict from declared rules, reported beside (never merged with) factor evidence.

The factor's confirmation evidence comes from the signals bundle's metadata, written by
whoever produced the signals; evaluation only copies it. The portfolio verdict uses only
this run's saved metrics, statistics and stress scenarios under ``config.validation``.
Neither verdict changes the other: a supported portfolio does not confirm a rejected
factor, and a confirmed factor does not make an untradable portfolio supported.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from invest_evaluation.config import ValidationConfig

VERDICT_VERSION = 1
PORTFOLIO_STATUSES = ("supported", "rejected", "inconclusive", "insufficient_data")


def factor_section(signal_metadata: dict[str, Any]) -> dict[str, Any]:
    """The factor's confirmation evidence as published with its signals, or its absence."""
    evidence = signal_metadata.get("factor_evidence")
    if evidence is None:
        return {
            "status": "not_confirmed",
            "factor_id": signal_metadata.get("factor_id"),
            "reason": "the signals carry no factor confirmation evidence",
        }
    return dict(evidence)


def _check(name: str, status: str, value: Any, threshold: Any, detail: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "value": value,
        "threshold": threshold,
        "detail": detail,
    }


def _positive(name: str, metric: dict[str, Any] | None, detail: str) -> dict[str, Any]:
    if metric is None:
        return _check(name, "not_run", None, "> 0", detail)
    value = metric.get("value")
    if value is None:
        return _check(name, "undefined", None, "> 0", f"{detail}: {metric.get('reason')}")
    return _check(name, "pass" if value > 0 else "fail", value, "> 0", detail)


def portfolio_verdict(
    rules: ValidationConfig,
    returns: pd.Series,
    metrics: dict[str, Any],
    statistics: dict[str, Any],
    scenarios: pd.DataFrame | None,
) -> dict[str, Any]:
    """Classify one fixed portfolio as supported, rejected, inconclusive or insufficient_data.

    Every rule is reported as a check (``pass``, ``fail``, ``undefined`` or ``not_run``),
    so an inconclusive verdict shows which evidence was missing or adverse.
    """
    clean = returns.dropna()
    n = len(clean)
    window = (
        {"start": str(clean.index[0].date()), "end": str(clean.index[-1].date())} if n else None
    )
    checks = [
        _check(
            "sessions",
            "pass" if n >= rules.min_sessions else "fail",
            n,
            f">= {rules.min_sessions}",
            "daily net returns in the evaluation period",
        )
    ]
    boot = statistics.get("bootstrap", {})
    ci = boot.get("sharpe_ci") if boot.get("status") == "ok" else None
    if ci is None:
        checks.append(
            _check(
                "net_sharpe_ci",
                "undefined",
                None,
                "excludes 0",
                f"bootstrap: {boot.get('reason') or boot.get('status')}",
            )
        )
    else:
        lo, hi = ci
        status = "pass" if lo > 0 else "fail"
        checks.append(
            _check(
                "net_sharpe_ci",
                status,
                [lo, hi],
                "lower bound > 0",
                f"{boot['level']:.0%} stationary-bootstrap interval of the net excess Sharpe",
            )
        )
    dsr = statistics.get("deflated_sharpe", {})
    if dsr.get("status") == "ok":
        checks.append(
            _check(
                "deflated_sharpe",
                "pass" if dsr["dsr"] >= rules.min_deflated_sharpe else "fail",
                dsr["dsr"],
                f">= {rules.min_deflated_sharpe}",
                f"n_trials = {dsr['n_trials']}",
            )
        )
    else:
        checks.append(
            _check(
                "deflated_sharpe",
                "undefined",
                None,
                f">= {rules.min_deflated_sharpe}",
                str(dsr.get("reason") or dsr.get("status")),
            )
        )
    for name in rules.stress_scenarios:
        row = None
        if scenarios is not None and name in set(scenarios["scenario"]):
            sharpe = scenarios.loc[scenarios["scenario"] == name, "sharpe"].iloc[0]
            row = {"value": None if pd.isna(sharpe) else float(sharpe), "reason": "undefined"}
        checks.append(_positive(f"stress:{name}", row, f"net Sharpe under scenario {name}"))
    if rules.benchmark != "none":
        section = "benchmark" if rules.benchmark == "universe" else "external_benchmark"
        checks.append(
            _positive(
                f"benchmark:{rules.benchmark}",
                metrics.get(section, {}).get("information_ratio"),
                f"information ratio against the {section.replace('_', ' ')}",
            )
        )

    by_name = {c["name"]: c for c in checks}
    if by_name["sessions"]["status"] != "pass" or by_name["net_sharpe_ci"]["status"] == "undefined":
        status = "insufficient_data"
    elif by_name["net_sharpe_ci"]["value"][1] < 0:
        status = "rejected"
    elif all(c["status"] == "pass" for c in checks):
        status = "supported"
    else:
        status = "inconclusive"
    return {
        "status": status,
        "reasons": [
            f"{c['name']}: {c['status']} ({c['detail']})" for c in checks if c["status"] != "pass"
        ],
        "evaluation_window": window,
        "checks": checks,
        "rules": {
            "min_sessions": rules.min_sessions,
            "min_deflated_sharpe": rules.min_deflated_sharpe,
            "stress_scenarios": list(rules.stress_scenarios),
            "benchmark": rules.benchmark,
        },
    }


def verdicts(
    signal_metadata: dict[str, Any],
    rules: ValidationConfig,
    returns: pd.Series,
    metrics: dict[str, Any],
    statistics: dict[str, Any],
    scenarios: pd.DataFrame | None,
) -> dict[str, Any]:
    return {
        "verdict_version": VERDICT_VERSION,
        "factor": factor_section(signal_metadata),
        "portfolio": portfolio_verdict(rules, returns, metrics, statistics, scenarios),
        "note": "Factor confirmation and portfolio validation are separate verdicts; "
        "neither changes the other.",
    }
